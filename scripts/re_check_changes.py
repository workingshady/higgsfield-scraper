"""Has Higgsfield changed since the last reverse-engineering checkpoint?

Two public GETs (no login):
  1. https://higgsfield.ai/ai/video  -> frontend build id (the 8-hex prefix of /tanstack/assets/<id>-*.js) and the
     public feature flags embedded as window.__HF_FF
  2. /job-sets/costs                 -> price-table version hash and the list of job_set_types

Compares them with .claude/re-state.json (the checkpoint) and prints what changed and what to re-check.

Usage:
    python scripts/re_check_changes.py            # compare only
    python scripts/re_check_changes.py --save     # compare, then store the current state as the new checkpoint
Exit code: 0 = unchanged, 1 = something changed, 2 = could not fetch.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".claude" / "re-state.json"
PAGE = "https://higgsfield.ai/ai/video"
COSTS = "https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs"


def _get(url: str) -> bytes:
    sys.path.insert(0, str(ROOT))
    from higgsfield_scraper.constants import USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def current() -> dict:
    html = _get(PAGE).decode("utf-8", "replace")
    builds = collections.Counter(re.findall(r"/tanstack/assets/([0-9a-f]{8})-", html))
    flags = dict(re.findall(r'"(f_[0-9a-f]{8})":(true|false)', html))
    costs = json.loads(_get(COSTS))
    types = sorted({row.get("job_set_type") for row in costs.get("data") or [] if row.get("job_set_type")})
    return {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "frontend_build": builds.most_common(1)[0][0] if builds else None,
            "public_flags": {k: v == "true" for k, v in sorted(flags.items())},
            "costs_version": costs.get("version"), "job_set_types": types}


def compare(old: dict, new: dict) -> list[str]:
    out = []
    if old.get("frontend_build") != new["frontend_build"]:
        out.append(f"frontend build {old.get('frontend_build')} -> {new['frontend_build']}: re-download chunks into "
                   f"samples/higgsfield/js2/ and re-check MODEL_LOADING/PRODUCTS/COST_FORMULAS evidence (chunk names change)")
    if old.get("costs_version") != new["costs_version"]:
        out.append("costs version changed: run a pricing scrape + `diff`, regenerate COST_FORMULAS tables and the "
                   "PRODUCTS catalog")
    ot, nt = set(old.get("job_set_types") or []), set(new["job_set_types"])
    if nt - ot:
        out.append(f"NEW job_set_types: {sorted(nt - ot)} -> new/launching models; check JS for a defineJob + route")
    if ot - nt:
        out.append(f"REMOVED job_set_types: {sorted(ot - nt)}")
    of, nf = old.get("public_flags") or {}, new["public_flags"]
    if not nf:
        # the page sometimes serves `"flags":{}` to anonymous requests (seen 2026-11-26; an earlier crawl got 23):
        # not evidence of a change, so flags are only compared when both sides have them
        return out
    changed = {k: (of.get(k), v) for k, v in nf.items() if of.get(k) != v}
    gone = sorted(set(of) - set(nf))
    if changed or gone:
        out.append(f"public feature flags changed: {changed}{' removed: ' + str(gone) if gone else ''} "
                   f"(gated models may have appeared/disappeared; see MODEL_LOADING §2.1)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--save", action="store_true", help="store the current state as the new checkpoint")
    a = ap.parse_args()
    try:
        new = current()
    except Exception as e:  # network, DataDome, shape change
        print(f"could not fetch current state: {e!r}")
        return 2
    old = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    print(f"checkpoint: {old.get('checked_at', 'none')}   now: {new['checked_at']}")
    print(f"build {new['frontend_build']} · costs {str(new['costs_version'])[:12]}… · "
          f"{len(new['job_set_types'])} job types · "
          f"{len(new['public_flags']) or 'no'} public flags{'' if new['public_flags'] else ' (page served an empty list)'}")
    changes = compare(old, new) if old else ["no checkpoint yet"]
    for c in changes:
        print(" -", c)
    if not changes:
        print("no changes since the checkpoint")
    if a.save:
        STATE.write_text(json.dumps(new, indent=4) + "\n", encoding="utf-8")
        print(f"saved checkpoint -> {STATE.relative_to(ROOT)}")
    return 1 if changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
