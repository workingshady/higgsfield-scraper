"""Export engine: runs -> rows -> layout writer -> idempotent sink.

Two streaming passes over the selected tables of every run:
  1. plan   : filter rows, build the dedup union-find (tree: record identity; hf/webdataset/jsonl: generation keys
              from scripts/merge_generations.py + record keys), count per collection.
  2. emit   : stream again and hand the first row of every dedup group to the layout writer.
Only small lookup tables (projects publications/folders) and the dedup key sets are held in memory.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from . import keys as K
from .card import render_readme
from .media import Fetch, MediaResolver
from .paths import NameRegistry, fit_parts, safe_component, safe_ext, short_hash, slug
from .profiles import GenericProfile, profile_for
from .reader import RunSource
from .records import ExportRow, build_row, media_kind
from .sink import Sink, TMP_SUFFIX

EXPORT_VERSION = 1
LAYOUTS = ("tree", "hf", "webdataset", "jsonl")
MEDIA_MODES = ("auto", "link", "copy", "hardlink", "none")
PER_ASSET_WARN = 500
PROMPT_CSV_COLS = ("file_name", "id", "model", "media_type", "prompt", "caption", "media_url", "thumbnail_url",
                   "created_at", "author_key", "source_url")


# ---------------------------------------------------------------------------------------------- options / filters
@dataclass
class Filter:
    field: str
    negate: bool
    values: set[str]

    @staticmethod
    def norm(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v).strip().lower()

    def match(self, row: ExportRow) -> bool:
        v = row.field(self.field)
        vals = [self.norm(x) for x in v] if isinstance(v, list) else [self.norm(v)]
        hit = any(x in self.values for x in vals)
        return not hit if self.negate else hit


def parse_filters(spec: Optional[str]) -> list[Filter]:
    """"has_prompt=true,media_type=video|image,model!=null" -> [Filter…] (AND of terms; | = OR of values)."""
    out: list[Filter] = []
    for term in [t.strip() for t in (spec or "").split(",") if t.strip()]:
        m = re.match(r"^([A-Za-z0-9_.]+)\s*(!=|=)\s*(.*)$", term)
        if not m:
            raise ValueError(f"--filter: bad term {term!r} (use field=value or field!=value)")
        vals = {Filter.norm(v) if v.strip().lower() not in ("none", "null") else "null" for v in m.group(3).split("|")}
        out.append(Filter(m.group(1), m.group(2) == "!=", vals))
    return out


@dataclass
class ExportOptions:
    runs: list[Path]
    out: Path
    layout: str = "tree"
    group_by: Optional[list[str]] = None
    per_asset: bool = False
    media: str = "auto"
    download_missing: Optional[str] = None          # None | thumbs | full
    max_media_files: Optional[int] = None
    max_media_mb: Optional[float] = None
    download_delay: float = 1.0
    only: Optional[set[str]] = None
    filters: list[Filter] = field(default_factory=list)
    filter_spec: Optional[str] = None
    dry_run: bool = False
    force: bool = False
    shard_mb: float = 1024.0
    fetch: Optional[Fetch] = None
    log: Callable[[str], None] = lambda s: print(s, file=sys.stderr)

    def public(self) -> dict:
        return {"layout": self.layout, "group_by": self.group_by, "per_asset": self.per_asset, "media": self.media,
                "download_missing_media": self.download_missing, "only": sorted(self.only) if self.only else None,
                "filter": self.filter_spec, "shard_mb": self.shard_mb if self.layout == "webdataset" else None}


@dataclass
class ExportResult:
    out: Path
    counts: dict
    sink_stats: dict
    media_stats: dict
    errors: list[str]
    seconds: float
    dry_run: bool
    files: int
    bytes: int


# ---------------------------------------------------------------------------------------------- row stream
@dataclass
class RunCtx:
    run: RunSource
    profile: GenericProfile


def _selected(ctx: RunCtx, coll: str, only: Optional[set[str]]) -> bool:
    if only and coll not in only and f"{ctx.run.scraper}:{coll}" not in only:
        return False
    return True


def iter_rows(ctxs: list[RunCtx], opts: ExportOptions, *, table_only: bool = False) -> Iterator[ExportRow]:
    for ctx in ctxs:
        run, prof = ctx.run, ctx.profile
        for coll in run.tables():
            if not _selected(ctx, coll, opts.only):
                continue
            if prof.is_row_collection(coll) == table_only:
                continue
            for rec in run.iter_table(coll):
                row = build_row(run.scraper, coll, rec, run.run_id, run.scraped_at, prof.id_fields.get(coll))
                prof.enrich(row)
                if row.collection == "assets" and isinstance(rec.get("asset_id"), str):
                    row.gen_keys.append(f"asset:{rec['asset_id'].lower()}")
                if not table_only and opts.filters and not all(f.match(row) for f in opts.filters):
                    continue
                yield row


# ---------------------------------------------------------------------------------------------- dedup plan
class Plan:
    """Union-find over row keys (+ generation keys when generation-level). Holds only keys and small per-row tags."""

    def __init__(self, generation_level: bool) -> None:
        self.gen = generation_level
        self.dsu = K.DSU()
        self.records = 0
        self.by_collection: Counter = Counter()
        self.by_media_type: Counter = Counter()
        self._row_tags: dict[str, tuple[str, str]] = {}      # row key -> (scraper:collection, run_id)
        self._members: Counter = Counter()
        self._sources: dict[str, set[str]] = {}
        self._runs: dict[str, set[str]] = {}

    def add(self, row: ExportRow) -> None:
        ks = [row.key] + (row.gen_keys if self.gen else [])
        for k in ks[1:]:
            self.dsu.union(ks[0], k)
        self.dsu.find(ks[0])
        self.records += 1
        self.by_collection[f"{row.scraper}:{row.collection}"] += 1
        self.by_media_type[row.media_type or "none"] += 1
        self._row_tags.setdefault(row.key, (f"{row.scraper}:{row.collection}", row.run_id))
        if row.key in self._row_tags and self._row_tags[row.key][1] != row.run_id:   # same record in another run
            self._runs.setdefault("run:" + row.key, set()).add(row.run_id)

    def finalize(self) -> None:
        for key, (src, run) in self._row_tags.items():
            r = self.dsu.find(key)
            self._members[r] += 1
            self._sources.setdefault(r, set()).add(src)
            runs = self._runs.setdefault(r, set())
            runs.add(run)
            runs |= self._runs.pop("run:" + key, set())

    def root(self, row: ExportRow) -> str:
        return self.dsu.find(row.key)

    def info(self, root: str) -> dict:
        return {"records": self._members.get(root, 1), "sources": sorted(self._sources.get(root, ())),
                "runs": sorted(self._runs.get(root, ()))}

    @property
    def unique(self) -> int:
        return len(self._members)


# ---------------------------------------------------------------------------------------------- layout writers
class BaseWriter:
    def __init__(self, sink: Sink, media: MediaResolver, opts: ExportOptions, multi_scraper: bool) -> None:
        self.sink, self.media, self.opts = sink, media, opts
        self.multi = multi_scraper
        self.names = NameRegistry()
        self.counts: Counter = Counter()
        self.errors: list[str] = []

    def place_mode(self) -> Optional[str]:
        return {"auto": "copy", "copy": "copy", "hardlink": "hardlink"}.get(self.opts.media)

    def local_media(self, row: ExportRow) -> Optional[Path]:
        if self.opts.media in ("link", "none"):
            return None
        return self.media.resolve(row)

    def stem(self, row: ExportRow, parent: str) -> str:
        rid = re.sub(r"[^A-Za-z0-9]+", "", row.record_id.split("=")[-1])[:12] or short_hash(row.key, 12)
        label = slug(row.model or row.title or row.collection, 32)
        base = (f"{row.position:04d}_" if row.position is not None and 0 <= row.position < 100000 else "") \
            + f"{label}_{rid}"
        return self.names.claim(parent, safe_component(base, max_chars=60), row.key)

    def caption_bytes(self, row: ExportRow) -> Optional[str]:
        t = row.caption_text
        return t.strip() + "\n" if t and t.strip() else None

    def add(self, row: ExportRow, info: dict) -> None:
        raise NotImplementedError

    def finalize(self) -> None:
        pass


def _jl(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str) + "\n"


class TreeWriter(BaseWriter):
    """<group>/<subgroup>/ metadata.jsonl + prompts.csv (+ urls.txt in link mode) + media + same-stem .txt."""

    def __init__(self, *a: Any, profiles: dict[str, GenericProfile], **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.profiles = profiles
        self.groups: dict[str, str] = {}          # rel dir -> staging key
        self._dir_cache: dict[tuple, str] = {}

    def dir_for(self, scraper: str, raw_parts: list[str]) -> str:
        key = (scraper, tuple(raw_parts))
        if key in self._dir_cache:
            return self._dir_cache[key]
        parts: list[str] = [scraper] if self.multi else []
        parent = ""
        for i, rp in enumerate(raw_parts):
            comp = safe_component(rp, max_chars=60)
            comp = self.names.claim(parent, comp, "dir:" + "/".join(raw_parts[: i + 1]))
            parts.append(comp)
            parent = "/".join(parts)
        parts = fit_parts(self.sink.root, parts, "metadata.jsonl" + TMP_SUFFIX)
        rel = "/".join(parts)
        self._dir_cache[key] = rel
        return rel

    def group_parts(self, row: ExportRow) -> list[str]:
        prof = self.profiles[row.scraper]
        out: list[str] = []
        for f in prof.group_spec(row.collection, self.opts.group_by):
            if f.startswith("="):
                out.append(f[1:])
                continue
            v = row.field(f)
            if isinstance(v, list):
                out += [str(x) for x in v if x not in (None, "")]
            elif v not in (None, "", [], {}):
                out.append(str(v))
        return out or [row.collection]

    def add(self, row: ExportRow, info: dict) -> None:
        gdir = self.dir_for(row.scraper, self.group_parts(row))
        stem = self.stem(row, gdir)
        adir = f"{gdir}/{stem}" if self.opts.per_asset else gdir
        src = self.local_media(row)
        file_name = None
        if src is not None and self.place_mode():
            ext = safe_ext(src.suffix) or safe_ext(os.path.splitext(row.media_url or "")[1]) or ".bin"
            rel = f"{adir}/{stem}{ext}"
            self.sink.place_file(rel, src, self.place_mode())
            file_name = rel[len(gdir) + 1:]
            self.counts["media_files"] += 1
            cap = self.caption_bytes(row)
            if cap:
                self.sink.write_text(f"{adir}/{stem}.txt", cap)
                self.counts["captions"] += 1
        elif row.media_url or row.thumb_url:
            self.counts["media_urls_only"] += 1
        meta = {"file_name": file_name, **row.flat(), "dedup": info, "record": row.rec}
        if self.opts.per_asset:
            self.sink.write_text(f"{adir}/{stem}.json", json.dumps(meta, ensure_ascii=False, indent=4) + "\n")
            if file_name is None and self.caption_bytes(row):
                self.sink.write_text(f"{adir}/{stem}.txt", self.caption_bytes(row) or "")
        key = self.groups.setdefault(gdir, f"g{len(self.groups):06d}.jsonl")
        self.sink.append(key, _jl(meta))
        self.counts["rows"] += 1

    def add_doc(self, scraper: str, parts: list[str], name: str, text: str) -> None:
        gdir = self.dir_for(scraper, parts)
        self.sink.write_text(f"{gdir}/{safe_component(name)}", text)
        self.counts["documents"] += 1

    def add_table_row(self, row: ExportRow) -> None:
        base = f"{row.scraper}/_tables" if self.multi else "_tables"
        rel = f"{base}/{safe_component(row.collection)}.jsonl"
        key = self.groups.setdefault(rel, f"t{len(self.groups):06d}.jsonl")
        self.sink.append(key, _jl(row.rec))
        self.counts["table_rows"] += 1

    def finalize(self) -> None:
        import csv
        import io
        for rel, key in self.groups.items():
            if self.sink.dry_run:
                self.sink.files[rel if rel.endswith(".jsonl") else f"{rel}/metadata.jsonl"] = {"bytes": 0}
                continue
            staged = self.sink.staged(key)
            if rel.endswith(".jsonl"):                              # _tables/<collection>.jsonl
                self.sink.commit_tmp(rel, staged)
                continue
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=list(PROMPT_CSV_COLS), extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            urls: list[str] = []
            with open(staged, encoding="utf-8") as f:
                for line in f:
                    m = json.loads(line)
                    w.writerow({k: ("" if m.get(k) is None else m.get(k)) for k in PROMPT_CSV_COLS})
                    if self.opts.media == "link" and m.get("media_url"):
                        urls.append(m["media_url"])
            self.sink.write_bytes(f"{rel}/prompts.csv", ("﻿" + buf.getvalue()).encode("utf-8"))
            if urls:
                self.sink.write_text(f"{rel}/urls.txt", "\n".join(dict.fromkeys(urls)) + "\n")
            self.sink.commit_tmp(f"{rel}/metadata.jsonl", staged)
            self.counts["groups"] += 1


class HfWriter(BaseWriter):
    """ImageFolder / VideoFolder / AudioFolder: <images|videos|audio>/train/{metadata.jsonl, <stem>.<ext>, <stem>.txt}
    + urls.jsonl at the root listing EVERY deduplicated row (also those without a local file)."""

    KIND_DIR = {"image": "images", "video": "videos", "audio": "audio"}

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.staged_keys: dict[str, str] = {}

    def add(self, row: ExportRow, info: dict) -> None:
        flat = {**row.flat(), "dedup_records": info["records"], "dedup_sources": json.dumps(info["sources"]),
                "dedup_runs": json.dumps(info["runs"])}
        src = self.local_media(row)
        file_rel = None
        if src is not None and self.place_mode():
            kind = media_kind(src.name) or media_kind(row.media_url, row.media_type)
            kdir = self.KIND_DIR.get(kind or "", "other")
            parent = f"{kdir}/train"
            stem = self.stem(row, parent)
            ext = safe_ext(src.suffix) or ".bin"
            file_rel = f"{parent}/{stem}{ext}"
            self.sink.place_file(file_rel, src, self.place_mode())
            cap = self.caption_bytes(row)
            if cap:
                self.sink.write_text(f"{parent}/{stem}.txt", cap)
                self.counts["captions"] += 1
            key = self.staged_keys.setdefault(f"{parent}/metadata.jsonl", f"h{len(self.staged_keys):04d}.jsonl")
            self.sink.append(key, _jl({"file_name": f"{stem}{ext}", **flat}))
            self.counts["media_files"] += 1
            self.counts[f"files_{kdir}"] += 1
        elif row.media_url or row.thumb_url:
            self.counts["media_urls_only"] += 1
        key = self.staged_keys.setdefault("urls.jsonl", "urls.jsonl")
        self.sink.append(key, _jl({"file": file_rel, **flat}))
        self.counts["rows"] += 1

    def finalize(self) -> None:
        for rel, key in self.staged_keys.items():
            if self.sink.dry_run:
                self.sink.files[rel] = {"bytes": 0}
                continue
            self.sink.commit_tmp(rel, self.sink.staged(key))


class JsonlWriter(BaseWriter):
    """manifest.jsonl (one deduplicated row per asset/generation) + optional media/<kind>/<stem>.<ext> (+ .txt)."""

    def add(self, row: ExportRow, info: dict) -> None:
        src = self.local_media(row)
        file_rel = None
        if src is not None and self.place_mode():
            kind = media_kind(src.name) or "other"
            parent = f"media/{kind}"
            stem = self.stem(row, parent)
            file_rel = f"{parent}/{stem}{safe_ext(src.suffix) or '.bin'}"
            self.sink.place_file(file_rel, src, self.place_mode())
            cap = self.caption_bytes(row)
            if cap:
                self.sink.write_text(f"{parent}/{stem}.txt", cap)
                self.counts["captions"] += 1
            self.counts["media_files"] += 1
        elif row.media_url or row.thumb_url:
            self.counts["media_urls_only"] += 1
        self.sink.append("manifest.jsonl", _jl({"file": file_rel, **row.flat(), **{f"dedup_{k}": v
                                                                                  for k, v in info.items()}}))
        self.counts["rows"] += 1

    def finalize(self) -> None:
        if self.sink.dry_run:
            self.sink.files["manifest.jsonl"] = {"bytes": 0}
            return
        if self.counts["rows"]:
            self.sink.commit_tmp("manifest.jsonl", self.sink.staged("manifest.jsonl"))


class WebDatasetWriter(BaseWriter):
    """shards/shard-000000.tar …: per sample <key>.<ext> (media, if local) + <key>.json + <key>.txt (prompt).
    Deterministic tar headers (mtime 0, uid/gid 0) so an unchanged export re-creates byte-identical shards."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self.shard_bytes = int(self.opts.shard_mb * 1024 * 1024)
        self.shard_no = 0
        self.tar = None
        self.tar_path: Optional[Path] = None
        self.cur_size = 0
        self.cur_samples = 0
        self.n = 0

    def _open(self) -> None:
        import tarfile
        self.tar_path = self.sink.staging / f"shard-{self.shard_no:06d}.tar"
        os.makedirs(self.sink.staging, exist_ok=True)
        self.tar = tarfile.open(self.tar_path, "w", format=tarfile.USTAR_FORMAT)
        self.cur_size = 0
        self.cur_samples = 0

    def _close(self) -> None:
        if self.tar is None:
            return
        self.tar.close()
        self.sink.commit_tmp(f"shards/shard-{self.shard_no:06d}.tar", self.tar_path)  # type: ignore[arg-type]
        self.counts["shards"] += 1
        self.shard_no += 1
        self.tar = None

    def _member(self, name: str, data: Optional[bytes] = None, src: Optional[Path] = None) -> None:
        import io
        import tarfile
        ti = tarfile.TarInfo(name)
        ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname, ti.mode = 0, 0, 0, "", "", 0o644
        if src is not None:
            ti.size = os.path.getsize(src)
            with open(src, "rb") as f:
                self.tar.addfile(ti, f)                     # type: ignore[union-attr]
        else:
            ti.size = len(data or b"")
            self.tar.addfile(ti, io.BytesIO(data or b""))   # type: ignore[union-attr]
        self.cur_size += 512 + ((ti.size + 511) // 512) * 512

    def add(self, row: ExportRow, info: dict) -> None:
        src = self.local_media(row) if self.opts.media not in ("link", "none") else None
        key = f"{self.n:07d}_{slug(row.record_id.split('=')[-1], 24)}".replace(".", "_")
        self.n += 1
        meta = {**row.flat(), "dedup": info, "record": row.rec}
        jb = json.dumps(meta, ensure_ascii=False, default=str).encode("utf-8")
        cap = self.caption_bytes(row)
        size = len(jb) + (os.path.getsize(src) if src else 0) + (len(cap.encode()) if cap else 0) + 2048
        if self.sink.dry_run:
            self.cur_size += size
            if self.cur_size > self.shard_bytes:
                self.counts["shards"] += 1
                self.cur_size = size
            self.counts["rows"] += 1
            self.counts["media_files"] += 1 if src else 0
            return
        if self.tar is not None and self.cur_samples and self.cur_size + size > self.shard_bytes:
            self._close()
        if self.tar is None:
            self._open()
        if src is not None:
            self._member(f"{key}{safe_ext(src.suffix) or '.bin'}", src=src)
            self.counts["media_files"] += 1
        elif row.media_url or row.thumb_url:
            self.counts["media_urls_only"] += 1
        self._member(f"{key}.json", jb)
        if cap:
            self._member(f"{key}.txt", cap.encode("utf-8"))
            self.counts["captions"] += 1
        self.cur_samples += 1
        self.counts["rows"] += 1
        self.sink.append("index.jsonl", _jl({"__key__": key, "shard": f"shard-{self.shard_no:06d}.tar",
                                             "id": row.record_id, "collection": row.collection,
                                             "media_url": row.media_url, "has_media": src is not None}))

    def finalize(self) -> None:
        if self.sink.dry_run:
            self.counts["shards"] += 1 if self.counts["rows"] else 0
            self.sink.files["index.jsonl"] = {"bytes": 0}
            return
        self._close()
        if self.counts["rows"]:
            self.sink.commit_tmp("index.jsonl", self.sink.staged("index.jsonl"))


WRITERS = {"tree": TreeWriter, "hf": HfWriter, "jsonl": JsonlWriter, "webdataset": WebDatasetWriter}


# ---------------------------------------------------------------------------------------------- main entry
def _load_prev(out: Path) -> Optional[dict]:
    p = out / "export_manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def run_export(opts: ExportOptions) -> ExportResult:
    t0 = time.monotonic()
    if opts.layout not in LAYOUTS:
        raise ValueError(f"--layout must be one of {LAYOUTS}")
    if opts.media not in MEDIA_MODES:
        raise ValueError(f"--media must be one of {MEDIA_MODES}")
    out = Path(opts.out)
    runs = [RunSource.open(p) for p in opts.runs]
    for r in runs:                                         # never export into a run folder
        if out.resolve() == r.path.resolve() or r.path.resolve() in out.resolve().parents:
            raise ValueError(f"--out {out} is inside the run folder {r.path}; choose a folder outside runs/")
    prev = _load_prev(out)
    if out.exists() and any(out.iterdir()) and prev is None and not opts.force:
        raise ValueError(f"--out {out} exists, is not empty and is not an export (no export_manifest.json); "
                         f"use --force or another --out")
    if prev and prev.get("layout") != opts.layout and not opts.force:
        raise ValueError(f"--out {out} holds a '{prev.get('layout')}' export; use --force to replace it "
                         f"with '{opts.layout}'")
    sink = Sink(out, dry_run=opts.dry_run, prev_files=(prev or {}).get("files") or {})
    sink.reset_staging()
    errors: list[str] = []
    if opts.per_asset and opts.layout != "tree":
        errors.append("--per-asset only applies to --layout tree (ignored)")
        opts.per_asset = False

    profiles: dict[str, GenericProfile] = {}
    ctxs: list[RunCtx] = []
    for r in runs:
        prof = profiles.get(r.scraper) or profile_for(r.scraper)
        profiles[r.scraper] = prof
        prof.prepare(r)
        ctxs.append(RunCtx(r, prof))
    multi = len({r.scraper for r in runs}) > 1

    index: dict[str, Path] = {}
    for r in runs:
        for k, v in r.media_index().items():
            index.setdefault(k, v)
    caps = runs[0].media_caps
    media = MediaResolver(index, out / ".media_cache", download=opts.download_missing,
                          max_files=opts.max_media_files or caps[0], max_mb=opts.max_media_mb or caps[1],
                          delay=opts.download_delay, dry_run=opts.dry_run, fetch=opts.fetch, errors=errors)

    # pass 1: plan + dedup
    plan = Plan(generation_level=opts.layout != "tree")
    for row in iter_rows(ctxs, opts):
        plan.add(row)
    plan.finalize()
    opts.log(f"export: {plan.records} rows -> {plan.unique} unique "
             f"({'record' if opts.layout == 'tree' else 'generation'}-level dedup) from {len(runs)} run(s)")
    if opts.per_asset and plan.unique > PER_ASSET_WARN:
        msg = f"--per-asset with {plan.unique} assets (> {PER_ASSET_WARN}): one folder each; consider --filter/--only"
        errors.append("warning: " + msg)
        opts.log("warning: " + msg)

    # pass 2: emit
    writer_cls = WRITERS[opts.layout]
    kw = {"profiles": profiles} if opts.layout == "tree" else {}
    writer = writer_cls(sink, media, opts, multi, **kw)
    emitted: set[str] = set()
    for i, row in enumerate(iter_rows(ctxs, opts), 1):
        root = plan.root(row)
        if root in emitted:
            continue
        emitted.add(root)
        try:
            writer.add(row, plan.info(root))
        except OSError as e:
            errors.append(f"{row.key}: {type(e).__name__}: {e}")
        if i % 5000 == 0:
            opts.log(f"export: {i} rows processed")
    if isinstance(writer, TreeWriter):
        for ctx in ctxs:
            for parts, name, text in ctx.profile.docs(ctx.run):
                writer.add_doc(ctx.run.scraper, parts, name, text)
        seen_tables: set[str] = set()
        for row in iter_rows(ctxs, opts, table_only=True):
            if row.key not in seen_tables:
                seen_tables.add(row.key)
                writer.add_table_row(row)
    writer.finalize()
    errors += writer.errors

    counts = {"records_read": plan.records, "unique": plan.unique, "duplicates": plan.records - plan.unique,
              "by_collection": dict(sorted(plan.by_collection.items())),
              "by_media_type": dict(sorted(plan.by_media_type.items())), **dict(sorted(writer.counts.items()))}
    run_info = [{"run_id": r.run_id, "scraper": r.scraper, "path": r.path.as_posix(), "scraped_at": r.scraped_at,
                 "with_profiles": r.with_profiles, "output": r.fingerprint()} for r in runs]
    errors_text = "".join(f"{e}\n" for e in errors)
    sink.write_text("errors.log", errors_text)
    readme = render_readme(runs=run_info, opts=opts.public(), counts=counts, layout=opts.layout,
                           profiles={s: p.name for s, p in profiles.items()}, keys_source=K.KEYS_SOURCE,
                           media_stats=media.stats)
    sink.write_text("README.md", readme)
    sink.finish()

    manifest = {"export_version": EXPORT_VERSION, "tool": "python -m higgsfield_scraper export",
                "layout": opts.layout, "options": opts.public(), "runs": run_info,
                "profiles": {s: p.name for s, p in profiles.items()}, "dedup_keys_source": K.KEYS_SOURCE,
                "counts": counts, "files": dict(sorted(sink.files.items()))}
    if not opts.dry_run:
        body = {k: v for k, v in manifest.items()}
        old = {k: v for k, v in (prev or {}).items() if k != "exported_at"}
        if old != json.loads(json.dumps(body, default=str)):
            manifest["exported_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            data = json.dumps(manifest, ensure_ascii=False, indent=4, default=str) + "\n"
            tmp = out / ("export_manifest.json" + TMP_SUFFIX)
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, out / "export_manifest.json")
            sink.stats["written"] += 1
        else:
            sink.stats["unchanged"] += 1
    return ExportResult(out=out, counts=counts, sink_stats=sink.stats, media_stats=media.stats, errors=errors,
                        seconds=time.monotonic() - t0, dry_run=opts.dry_run, files=len(sink.files),
                        bytes=sum((f.get("bytes") or 0) for f in sink.files.values()))
