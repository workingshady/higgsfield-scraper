"""Probe every read-only API path found in the Higgsfield JS bundles (no auth) and record what is public.

Usage:  python scripts/recon_probe.py [paths.json] [out_dir]
  paths.json  list of API paths ("/motions", "/publications/{id}") — default samples/higgsfield/inventory/js_call_paths.json
  out_dir     default samples/higgsfield/inventory/

Writes out_dir/probe_results.jsonl (one line per request: path, url, status, bytes, content_type, shape, totals)
and out_dir/bodies/<slug>.json (first 300 KB of every 200 JSON response).

Safety: only GET; any path containing a mutation word (delete, purchase, vote, upload, generate, …) is skipped;
paths with unresolved {id} placeholders are skipped unless an id is supplied in ID_FILL.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://fnf-api-gw.higgsfield.ai/fnf"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "application/json", "Origin": "https://higgsfield.ai",
           "Referer": "https://higgsfield.ai/"}
MUTATION = re.compile(
    r"(delete|remove|create|update|purchase|buy|checkout|pay|charge|subscribe|cancel|skip|expire|claim|vote|like|"
    r"report|upload|generate|/run|submit|send|accept|invite|join|leave|reset|restore|complete|mark|seen|viewed|"
    r"dismiss|close|enable|disable|retry|/set|save|start|stop|pause|resume|publish|duplicate|move|bulk|transfer|"
    r"verify|consent|logout|login|signin|sign-in|sign-up|refresh|activate|rename|pin|track|event|analytics|feedback|"
    r"notify|chase|apply|redeem|top-up|upgrade|downgrade|convert|merge|edit|approve|reject|archive|portal|"
    r"invoice|card|wallet|oauth|token|webhook|debug|admin|impersonat|instant|setup|pair|confirm|"
    r"unlock|lock|toggle|assign|grant|revoke|request|cancel|answer|rate|review|follow|block|mute|hide|"
    r"read$|/auth|/me$|/session|/password|/email|/phone)", re.I)
ID_FILL: dict[str, str] = {}   # e.g. {"{id}": "<a real uuid>"} — filled from list responses at runtime


def shape(x, depth=0):
    if isinstance(x, dict):
        if depth >= 2:
            return "{…}"
        return "{" + ", ".join(f"{k}:{shape(v, depth + 1)}" for k, v in list(x.items())[:16]) + "}"
    if isinstance(x, list):
        return f"[{len(x)}x " + (shape(x[0], depth + 1) if x else "") + "]"
    return type(x).__name__


def get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()
    except Exception as e:  # network
        return 0, "", repr(e).encode()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    paths_file = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "samples/higgsfield/inventory/js_call_paths.json"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "samples/higgsfield/inventory"
    (out / "bodies").mkdir(parents=True, exist_ok=True)
    paths = json.loads(paths_file.read_text(encoding="utf-8"))
    results = out / "probe_results.jsonl"
    results.write_text("", encoding="utf-8")
    skipped_mut, skipped_id, n = 0, 0, 0
    for p in paths:
        if MUTATION.search(p):
            skipped_mut += 1
            continue
        if "{id}" in p:
            skipped_id += 1
            continue
        url = API + p
        status, ctype, body = get(url)
        n += 1
        rec = {"path": p, "url": url, "status": status, "bytes": len(body), "content_type": ctype.split(";")[0]}
        if status == 200 and "json" in ctype:
            try:
                d = json.loads(body)
                rec["shape"] = shape(d)[:400]
                if isinstance(d, dict):
                    rec["totals"] = {k: v for k, v in d.items() if k in ("total", "count", "has_more", "total_count")}
                slug = re.sub(r"[^A-Za-z0-9]+", "_", p).strip("_")[:80] or "root"
                (out / "bodies" / f"{slug}.json").write_bytes(body[:300_000])
            except ValueError:
                pass
        elif status not in (200,):
            rec["detail"] = body[:160].decode("utf-8", "replace")
        with results.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{status:>3} {len(body):>8}  {p}", flush=True)
        time.sleep(0.4)
    print(f"\nprobed {n}, skipped {skipped_mut} mutation-like, {skipped_id} needing ids -> {results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
