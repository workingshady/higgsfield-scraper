"""Merge generation-like records from several run folders into one deduplicated index.

    python scripts/merge_generations.py runs/<community-run> runs/<catalog-run> runs/<showcase-run> ... \
        [--out runs/generations_index] [--latest community,catalog,projects,site,showcase]

Reads each run's `output/dataset.json` (any scraper). A record is "generation-like" when it has an output media URL
(a result video/image on a Higgsfield CDN) or a job id. Records are merged with union-find over their keys:

    job:<job id>          community generation_id, effect sample job id, explicit `generation_key: job:…`
    pub:<publication id>  ONLY for single-generation publications (community generations/feed items, explore variants)
    media:<file id>       the last UUID in an OUTPUT media URL (inputs on d2ol7oe51mr4n9 are never keys; preset previews
                          embedded in a generation are not scanned)
    static:<path>         Property Studio static example files

Output: <out>/generations_index.csv + .json (indent=4) with one row per unique generation:
    key, keys[], sources[] (scraper:collection), records, best prompt / model / media_url / likes / views / comments,
    plus <out>/duplicates.json: duplicate counts per source pair. Prints a short report.
Track likes over time: run it on two snapshots of the same scraper and diff `likes`/`views` by `key`
(`--compare <old index.json>` adds likes_delta / views_delta).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Optional

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
INPUT_HOSTS = ("d2ol7oe51mr4n9.cloudfront.net",)
OUTPUT_URL_RE = re.compile(r"^https://([a-z0-9.-]*cloudfront\.net|cdn\.higgsfield\.ai|static[a-z-]*\.higgsfield\.ai|"
                           r"[a-z0-9.-]*higgsfield\.ai)/", re.I)
# URL fields that point at the record's own output (top level or inside results/media lists)
URL_FIELD_RE = re.compile(r"(^|_)(url|video_url|media_url|result_url|min_url|h264_url|hls_url|download_url|"
                          r"raw_url|source)$")
SKIP_FIELD_RE = re.compile(r"input|reference|avatar|cover|logo|icon|preset|original|thumbnail_url_avatar|"
                           r"waveform|style_url|preview_image|profile|redirect|href|source_url|page", re.I)
# roles/names inside media/results lists that are the record's OWN output (style/preset/input previews are not)
OUTPUT_ROLE_RE = re.compile(r"^(result|results|output|outputs|final|raw|min|generation|video|image|hls|main)(_|$)",
                            re.I)
# collections whose publication_id identifies ONE generation (elsewhere it is a project/folder id)
PUB_IS_GENERATION = {("community", "generations"), ("community", "feed_items"), ("community", "shots"),
                     ("showcase", "explore_variants")}
SKIP_COLLECTIONS = {"pages", "comments", "creators", "rooms", "folders", "briefs", "project_stats", "stack_items",
                    "related", "contests", "authors", "categories", "explore_categories", "seasons", "api_models",
                    "canvas_templates", "cinema_controls"}
PROMPT_FIELDS = ("prompt", "raw_params.prompt")
MODEL_FIELDS = ("model_id", "model_name", "made_with_model", "job_set_type", "tool", "model")
LIKE_FIELDS = ("likes", "likes_count", "like_count", "engagement.likes", "publication_engagement.likes")
VIEW_FIELDS = ("views", "views_count", "view_count", "engagement.views", "publication_engagement.views")
COMMENT_FIELDS = ("comments", "comments_count", "comment_count", "engagement.comments")


def _get(d: dict, path: str) -> Any:
    cur: Any = d
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _first(d: dict, paths: Iterable[str]) -> Any:
    for p in paths:
        v = _get(d, p)
        if v not in (None, "", [], {}):
            return v
    return None


def media_key(url: str) -> Optional[str]:
    found = UUID_RE.findall(url.split("?")[0])
    return found[-1].lower() if found else None


def output_urls(rec: dict) -> list[str]:
    """Output media URLs of a record: top-level url fields + results/media/output lists (roles not input/preview)."""
    out: list[str] = []

    def take(v: Any) -> None:
        if isinstance(v, str) and OUTPUT_URL_RE.match(v) and not any(h in v for h in INPUT_HOSTS):
            out.append(v)

    for k, v in rec.items():
        if SKIP_FIELD_RE.search(k):
            continue
        if URL_FIELD_RE.search(k):
            take(v)
        elif k in ("results", "media", "output", "outputs") and isinstance(v, list):
            for m in v:
                if isinstance(m, dict) and OUTPUT_ROLE_RE.match(str(m.get("role") or m.get("name") or "result")):
                    take(m.get("url"))
                    take(m.get("min_url"))
        elif k in ("output", "media") and isinstance(v, dict):
            take(v.get("url"))
    return list(dict.fromkeys(out))


GEN_MARKERS = ("generation_key", "generation_id", "job_id", "job_set_id", "prompt", "results", "video_url")


def is_generation_like(rec: dict) -> bool:
    """A generated video/image (not a preset/catalog entry): has a job/generation id, a prompt, results or a
    video_url. Preset catalogs (motions, styles, voices, viral presets…) have none of these at the top level."""
    return any(k in rec for k in GEN_MARKERS)


def record_keys(scraper: str, coll: str, rec: dict) -> list[str]:
    if not is_generation_like(rec):
        return []
    keys: list[str] = []
    gk = rec.get("generation_key")
    if isinstance(gk, str) and gk:
        keys.append(gk)
    for k in rec.get("media_keys") or []:
        if isinstance(k, str):
            keys.append(k)
    for f in ("generation_id", "job_id"):
        if isinstance(rec.get(f), str) and UUID_RE.fullmatch(rec[f]):
            keys.append(f"job:{rec[f].lower()}")
    if (scraper, coll) in PUB_IS_GENERATION and isinstance(rec.get("publication_id"), str):
        keys.append(f"pub:{rec['publication_id'].lower()}")
    if "generation_key" not in rec:                         # showcase records list their own keys explicitly
        for u in output_urls(rec):
            mk = media_key(u)
            if mk:
                keys.append(f"media:{mk}")
    return list(dict.fromkeys(keys))


class DSU:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def load_records(run_dirs: Iterable[Path]) -> list[dict]:
    recs = []
    for d in run_dirs:
        f = Path(d) / "output" / "dataset.json"
        if not f.exists():
            print(f"skip {d}: no output/dataset.json", file=sys.stderr)
            continue
        ds = json.loads(f.read_text(encoding="utf-8"))
        scraper = (ds.get("meta") or {}).get("scraper") or "pricing"
        run_id = (ds.get("meta") or {}).get("run_id") or Path(d).name
        for coll, rows in ds.items():
            if coll in SKIP_COLLECTIONS or not isinstance(rows, list):
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                keys = record_keys(scraper, coll, r)
                if keys:
                    recs.append({"scraper": scraper, "collection": coll, "run": run_id, "keys": keys, "rec": r})
    return recs


def merge(recs: list[dict]) -> tuple[list[dict], dict[str, int], Counter]:
    dsu = DSU()
    for r in recs:
        for k in r["keys"][1:]:
            dsu.union(r["keys"][0], k)
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        groups[dsu.find(r["keys"][0])].append(r)
    rows, pairs = [], Counter()
    for root, members in groups.items():
        sources = sorted({f"{m['scraper']}:{m['collection']}" for m in members})
        for a, b in combinations(sources, 2):
            pairs[f"{a} + {b}"] += 1
        keys = sorted({k for m in members for k in m["keys"]})
        best = lambda paths: next((v for m in members if (v := _first(m["rec"], paths)) is not None), None)  # noqa: E731
        nums = lambda paths: max((v for m in members if isinstance(v := _first(m["rec"], paths), (int, float))  # noqa: E731
                                  and not isinstance(v, bool)), default=None)
        urls = [u for m in members for u in output_urls(m["rec"])]
        mk = next((m["rec"].get("media") for m in members if isinstance(m["rec"].get("media"), list)), None)
        if not urls and mk:
            urls = [x.get("url") for x in mk if isinstance(x, dict) and x.get("url")]
        job = next((k[4:] for k in keys if k.startswith("job:")), None)
        rows.append({"key": next((k for k in keys if k.startswith("job:")), root), "job_id": job,
                     "keys": keys, "sources": sources, "records": len(members),
                     "runs": sorted({m["run"] for m in members}),
                     "prompt": best(PROMPT_FIELDS), "model": best(MODEL_FIELDS),
                     "media_url": urls[0] if urls else None, "likes": nums(LIKE_FIELDS), "views": nums(VIEW_FIELDS),
                     "comments": nums(COMMENT_FIELDS)})
    rows.sort(key=lambda r: (-len(r["sources"]), r["key"]))
    per_source = Counter(s for r in rows for s in r["sources"])
    return rows, dict(per_source), pairs


def compare(rows: list[dict], old_path: Path) -> None:
    old = {r["key"]: r for r in json.loads(old_path.read_text(encoding="utf-8")).get("generations", [])}
    for r in rows:
        o = old.get(r["key"])
        for f in ("likes", "views"):
            r[f"{f}_delta"] = (r[f] - o[f]) if o and isinstance(r[f], int) and isinstance(o.get(f), int) else None


def write(rows: list[dict], per_source: dict, pairs: Counter, total_records: int, out: Path,
          records_per_source: Optional[dict] = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rps = dict(records_per_source or {})
    report = {"unique_generations": len(rows), "records": total_records, "duplicates": total_records - len(rows),
              "multi_source": sum(1 for r in rows if len(r["sources"]) > 1),
              "per_source": {s: {"records": rps.get(s), "unique": n,
                                 "within_source_duplicates": (rps[s] - n) if s in rps else None}
                             for s, n in sorted(per_source.items())},
              "duplicate_pairs": dict(pairs.most_common())}
    (out / "generations_index.json").write_text(json.dumps({"report": report, "generations": rows},
                                                           ensure_ascii=False, indent=4), encoding="utf-8")
    (out / "duplicates.json").write_text(json.dumps(report, ensure_ascii=False, indent=4), encoding="utf-8")
    cols = list(dict.fromkeys(k for r in rows for k in r)) or ["key"]
    with (out / "generations_index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else ("" if v is None else v)
                        for k, v in r.items()})


def latest_runs(runs_dir: Path, scrapers: list[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for d in sorted(runs_dir.glob("2*"), reverse=True):
        m = d / "manifest.json"
        if not (d / "output" / "dataset.json").exists() or not m.exists():
            continue
        try:
            s = json.loads(m.read_text(encoding="utf-8")).get("scraper")
        except ValueError:
            continue
        if s in scrapers and s not in found:
            found[s] = d
    return [found[s] for s in scrapers if s in found]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="*", type=Path, help="run folders (each with output/dataset.json)")
    ap.add_argument("--latest", default=None, help="add the latest run of each scraper (comma list) from --runs-dir")
    ap.add_argument("--runs-dir", type=Path, default=Path("runs"))
    ap.add_argument("--out", type=Path, default=Path("runs") / "generations_index")
    ap.add_argument("--compare", type=Path, default=None, help="previous generations_index.json: add likes/views deltas")
    a = ap.parse_args(argv)
    dirs = list(a.runs) + (latest_runs(a.runs_dir, [s.strip() for s in a.latest.split(",")]) if a.latest else [])
    if not dirs:
        ap.error("give run folders or --latest")
    recs = load_records(dirs)
    rows, per_source, pairs = merge(recs)
    if a.compare:
        compare(rows, a.compare)
    rps = Counter(f"{r['scraper']}:{r['collection']}" for r in recs)
    write(rows, per_source, pairs, len(recs), a.out, rps)
    print(f"runs: {', '.join(Path(d).name for d in dirs)}")
    print(f"records {len(recs)} -> unique {len(rows)} (duplicates {len(recs) - len(rows)}, "
          f"seen in >1 source {sum(1 for r in rows if len(r['sources']) > 1)})")
    for s, n in sorted(per_source.items()):
        print(f"  {s}: {rps[s]} records -> {n} unique")
    for p, n in pairs.most_common(15):
        print(f"  dup pair {p}: {n}")
    print(f"wrote {a.out / 'generations_index.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
