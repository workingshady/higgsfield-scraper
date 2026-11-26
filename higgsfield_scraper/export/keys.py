"""Stable record ids + cross-run / cross-scraper dedup keys.

Generation-level keys (`job:<id>`, `pub:<id>`, `media:<uuid>`, `static:<path>`) are NOT re-implemented here: they
come from `scripts/merge_generations.py` (`record_keys`, `output_urls`, `DSU`), loaded by file path because
`scripts/` is not a package. If that script is missing (e.g. an installed wheel without scripts/), a minimal
fallback (explicit generation_key/media_keys + job/generation ids) is used and `KEYS_SOURCE` says so.

Record-level ids (`record_id`) identify one row of one collection, e.g. a project asset *placement*; generation
keys identify the underlying media/job, so the same video placed in two folders or seen by two scrapers merges.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
VOLATILE = {"source", "source_url", "scraped_at", "fetched_at", "detail_source", "schema_version"}
_MERGE_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "merge_generations.py"


def _load_merge_module() -> Optional[Any]:
    if not _MERGE_SCRIPT.exists():
        return None
    name = "_hf_merge_generations"
    if name in sys.modules:
        return sys.modules[name]
    try:
        spec = importlib.util.spec_from_file_location(name, _MERGE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
        sys.modules[name] = mod
        spec.loader.exec_module(mod)                         # type: ignore[union-attr]
        return mod
    except Exception:                                        # a broken script must not break exports
        sys.modules.pop(name, None)
        return None


_MG = _load_merge_module()
KEYS_SOURCE = "scripts/merge_generations.py" if _MG else "builtin-fallback"


def _fallback_record_keys(scraper: str, coll: str, rec: dict) -> list[str]:
    keys: list[str] = []
    gk = rec.get("generation_key")
    if isinstance(gk, str) and gk:
        keys.append(gk)
    keys += [k for k in rec.get("media_keys") or [] if isinstance(k, str)]
    for f in ("generation_id", "job_id"):
        v = rec.get(f)
        if isinstance(v, str) and UUID_RE.fullmatch(v):
            keys.append(f"job:{v.lower()}")
    return list(dict.fromkeys(keys))


generation_keys: Callable[[str, str, dict], list[str]] = (_MG.record_keys if _MG else _fallback_record_keys)


def output_urls(rec: dict) -> list[str]:
    if _MG:
        try:
            return list(_MG.output_urls(rec))
        except Exception:
            return []
    return []


class DSU:
    """Union-find over string keys (path halving; the smaller key becomes the root, so roots are deterministic)."""

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


ID_PRIORITY = ("placement_id", "uid", "id")


def _singular(coll: str) -> str:
    c = coll
    for suf, rep in (("ies", "y"), ("ses", "s"), ("s", "")):
        if c.endswith(suf):
            return c[: -len(suf)] + rep
    return c


def record_id(coll: str, rec: dict, id_field: Optional[str] = None) -> str:
    """Natural id of one row: profile field > `<singular>_id` > placement_id/id/uid > first `*_id` > content hash."""
    cands = [id_field] if id_field else []
    cands += [f"{_singular(coll)}_id", *ID_PRIORITY]
    for f in cands:
        v = rec.get(f) if f else None
        if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v):
            return str(v)
    for k, v in rec.items():
        if k.endswith("_id") and isinstance(v, (str, int)) and not isinstance(v, bool) and str(v):
            return f"{k}={v}"
    body = {k: v for k, v in rec.items() if k not in VOLATILE}
    return "h:" + hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
                               .encode("utf-8")).hexdigest()[:16]


def stable_key(scraper: str, coll: str, rid: str) -> str:
    return f"rec:{scraper}:{coll}:{rid}"
