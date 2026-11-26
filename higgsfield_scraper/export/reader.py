"""Read-only access to one finished run folder: manifest, streamed tables, media index.

Never writes into the run folder. Tables come from `output/json/<name>.json` (one file per collection, streamed);
when a run has no json/ folder, `output/dataset.json` is streamed instead.
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlsplit, urlunsplit

from .stream import iter_dataset, iter_json_array, iter_jsonl, peek_json_kind

NON_TABLES = {"meta", "summary", "nested_summary"}


def url_key(u: str) -> str:
    """URL without query/fragment (signed CDN URLs differ only in their query)."""
    p = urlsplit(u)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


@dataclass
class RunSource:
    path: Path
    manifest: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    @classmethod
    def open(cls, path: Path) -> "RunSource":
        path = Path(path)
        if not (path / "output").is_dir():
            raise ValueError(f"{path}: not a run folder (no output/)")
        man: dict = {}
        if (path / "manifest.json").exists():
            try:
                man = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            except ValueError:
                man = {}
        meta: dict = {}
        mj = path / "output" / "json" / "meta.json"
        if mj.exists():
            try:
                meta = (json.loads(mj.read_text(encoding="utf-8")) or {}).get("meta") or {}
            except ValueError:
                meta = {}
        elif (path / "output" / "dataset.json").exists():
            for k, v in iter_dataset(path / "output" / "dataset.json", only={"meta"}):
                meta = v if isinstance(v, dict) else {}
                break
        return cls(path=path, manifest=man, meta=meta)

    # ------------------------------------------------------------------ identity
    @property
    def scraper(self) -> str:
        return str(self.manifest.get("scraper") or self.meta.get("scraper") or "pricing")

    @property
    def run_id(self) -> str:
        return str(self.meta.get("run_id") or self.manifest.get("run_id") or self.path.name)

    @property
    def scraped_at(self) -> Optional[str]:
        return self.meta.get("scraped_at") or self.manifest.get("started_at")

    @property
    def with_profiles(self) -> bool:
        opts = self.meta.get("options") or {}
        return bool(opts.get("with_profiles") or (self.manifest.get("args") or {}).get("with_profiles"))

    @property
    def media_caps(self) -> tuple[int, float]:
        lim = self.meta.get("limits") or self.manifest.get("args") or {}
        return int(lim.get("max_media_files") or 500), float(lim.get("max_media_mb") or 1024.0)

    # ------------------------------------------------------------------ tables
    def _json_dir(self) -> Path:
        return self.path / "output" / "json"

    def tables(self) -> list[str]:
        """Names of list-valued collections (json/ files whose top level is an array, else dataset.json keys)."""
        jd = self._json_dir()
        if jd.is_dir():
            return sorted(p.stem for p in jd.glob("*.json")
                          if p.stem not in NON_TABLES and peek_json_kind(p) == "list")
        ds = self.path / "output" / "dataset.json"
        if not ds.exists():
            return []
        seen: list[str] = []
        for k, v in iter_dataset(ds):
            if k not in NON_TABLES and k not in ("schema_version",) and k not in seen and isinstance(v, dict):
                seen.append(k)
        return seen

    def iter_table(self, name: str) -> Iterator[dict]:
        f = self._json_dir() / f"{name}.json"
        if f.exists():
            for r in iter_json_array(f):
                if isinstance(r, dict):
                    yield r
            return
        ds = self.path / "output" / "dataset.json"
        if ds.exists():
            for _, r in iter_dataset(ds, only={name}):
                if isinstance(r, dict):
                    yield r

    def load_table(self, name: str) -> list[dict]:
        return list(self.iter_table(name))

    def brief_markdown(self, slug: str) -> Optional[str]:
        f = self.path / "output" / "briefs" / f"{slug}.md"
        return f.read_text(encoding="utf-8") if f.exists() else None

    # ------------------------------------------------------------------ media
    def media_index(self) -> dict[str, Path]:
        """url (and url without query) -> local file inside the run (only files that exist)."""
        idx: dict[str, Path] = {}
        f = self.path / "media" / "index.jsonl"
        if not f.exists():
            return idx
        for row in iter_jsonl(f):
            u, rel = row.get("url"), row.get("file")
            if not u or not rel:
                continue
            p = self.path / rel
            if p.exists():
                idx.setdefault(u, p)
                idx.setdefault(url_key(u), p)
        return idx

    def fingerprint(self) -> dict[str, Any]:
        """Cheap identity of the run's output (size + mtime of each output file), for the export manifest."""
        out = self.path / "output"
        files = sorted(p for p in out.rglob("*") if p.is_file())
        return {"files": len(files), "bytes": sum(p.stat().st_size for p in files),
                "latest_mtime": max((int(p.stat().st_mtime) for p in files), default=0)}


def expand_runs(specs: list[str], runs_dir: Path = Path("runs")) -> list[Path]:
    """--run values: folders, globs (runs/*nested*), or bare run ids (looked up in runs_dir). Order kept, deduped."""
    out: list[Path] = []
    for s in specs:
        cands: list[Path]
        if any(ch in s for ch in "*?["):
            cands = [Path(p) for p in sorted(glob.glob(s))]
            if not cands:
                cands = [Path(p) for p in sorted(glob.glob(str(runs_dir / s)))]
        else:
            p = Path(s)
            cands = [p if p.exists() else runs_dir / s]
        for c in cands:
            if (c / "output").is_dir() and c.resolve() not in [o.resolve() for o in out]:
                out.append(c)
            elif not any(ch in s for ch in "*?["):
                raise ValueError(f"--run {s}: not a run folder (expected <run>/output/)")
    if not out:
        raise ValueError(f"--run {specs}: no run folders matched")
    return out
