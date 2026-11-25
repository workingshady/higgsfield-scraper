"""Command-line entry point.

  python -m higgsfield_scraper scrape   [options]     # fetch live data -> runs/<timestamp>_<label>/
  python -m higgsfield_scraper normalize --run DIR    # re-parse a run's raw/ offline
  python -m higgsfield_scraper show plans|models|model <id>|plan-sets|benefits|compare [--run DIR]
  python -m higgsfield_scraper plan-sets              # known plan_set_keys and presets
  python -m higgsfield_scraper sections               # what each section fetches
  python -m higgsfield_scraper runs                   # recent runs
  python -m higgsfield_scraper schema --out schemas/  # export JSON Schemas
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .constants import (
    DEFAULT_SECTIONS, ENDPOINTS, PLAN_SET_KEYS, PLAN_SET_PRESETS, PLAN_SET_TIERS, SECTIONS, US_PLAN_SET,
)
from .selection import Selection


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _selection_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("what to scrape")
    g.add_argument("--sections", default=",".join(DEFAULT_SECTIONS),
                   help=f"comma list of {sorted(SECTIONS)} or 'all' (default: %(default)s)")
    g.add_argument("--plan-sets", default="us",
                   help=f"plan_set_keys or presets {sorted(PLAN_SET_PRESETS)} (default: us = {US_PLAN_SET})")
    g.add_argument("--billing", default="monthly,annual", help="billing periods for /compare (default: %(default)s)")
    g.add_argument("--marketing-versions", default="latest",
                   help="latest | all | comma list like v51,v50 (default: %(default)s)")
    g.add_argument("--locale", default=os.environ.get("HF_LOCALE", "en"), help="en, de, es, fr, ja, ko, pt-BR, zh-CN")
    f = p.add_argument_group("filters (applied to output)")
    f.add_argument("--plan-types", default=None, help="e.g. plus,ultra,team (default: all)")
    f.add_argument("--models", default=None, help="model patterns, e.g. seedance,kling*,gpt_image_2_6")
    f.add_argument("--categories", default=None, help="video,image,audio,other")
    o = p.add_argument_group("output options")
    o.add_argument("--usd-reference", default="plus:annual",
                   help="plan_type:billing_period whose after-offer $/credit prices model USD estimates")
    o.add_argument("--include-hidden-plans", action="store_true", help="keep trial/secret plan types")
    o.add_argument("--include-raw-cost", action="store_true", help="embed each model's untouched cost JSON")


def _run_args(p: argparse.ArgumentParser) -> None:
    r = p.add_argument_group("run")
    r.add_argument("--label", default=None, help="run label (folder suffix)")
    r.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    r.add_argument("--log-level", default=os.environ.get("HF_LOG_LEVEL", "INFO"), help="console level")
    r.add_argument("--file-log-level", default="DEBUG")
    r.add_argument("--scrapy-log-level", default="INFO")


def _build_selection(a, has_token: bool) -> Selection:
    return Selection.build(
        sections=a.sections, plan_sets=a.plan_sets, billing=a.billing, plan_types=a.plan_types,
        models=a.models, categories=a.categories, marketing_versions=a.marketing_versions, locale=a.locale,
        include_hidden_plans=a.include_hidden_plans, include_raw_cost=a.include_raw_cost,
        usd_reference=a.usd_reference, has_token=has_token,
    )


def _public_args(a) -> dict:
    return {k: v for k, v in vars(a).items() if k not in ("token", "func")} | {"token": "***" if getattr(a, "token", None) else None}


# ---------------------------------------------------------------- commands
def cmd_scrape(a) -> int:
    from .run.manager import RunManager
    token = a.token or os.environ.get("HF_TOKEN") or None
    sel = _build_selection(a, bool(token))
    if a.dry_run:
        from .spiders.higgsfield import HiggsfieldSpider
        sp = HiggsfieldSpider(selection=sel, token=token)
        for r in sp.build_requests():
            print(f"GET {r.url}" + ("   [auth]" if "Authorization" in r.headers else ""))
        return 0
    label = a.label or ("-".join(sel.sections) if len(sel.sections) < 3 else "full") + f"-{'-'.join(sel.plan_set_keys[:2])}"
    mgr = RunManager(a.runs_dir, label, a.log_level, a.file_log_level, a.scrapy_log_level)
    overrides = {"HIGGS_HTTP_ARCHIVE": not a.no_http_archive, "ROBOTSTXT_OBEY": a.obey_robots}
    return mgr.scrape(sel, token=token, cache=a.cache, settings_overrides=overrides, args=_public_args(a))


def cmd_normalize(a) -> int:
    from .run.context import latest_run
    from .run.manager import RunManager
    src = Path(a.run) if a.run else latest_run(a.runs_dir)
    if not src or not (src / "raw").exists():
        print(f"no raw/ folder found in {src}", file=sys.stderr)
        return 1
    sel = _build_selection(a, False)
    if a.sections == ",".join(DEFAULT_SECTIONS) and (src / "manifest.json").exists():
        m = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
        prev = m.get("selection") or {}
        sel.sections, sel.plan_set_keys = prev.get("sections", sel.sections), prev.get("plan_set_keys", sel.plan_set_keys)
    return RunManager(a.runs_dir, a.label or "normalize", a.log_level, a.file_log_level, a.scrapy_log_level) \
        .normalize(src, sel, args=_public_args(a))


def _dataset(a) -> Optional[dict]:
    from .run.context import latest_run
    run = Path(a.run) if a.run else latest_run(a.runs_dir)
    path = run / "output" / "dataset.json" if run else None
    if not path or not path.exists():
        print("no dataset found; run `python -m higgsfield_scraper scrape` first", file=sys.stderr)
        return None
    print(f"# {path}", file=sys.stderr)
    return json.loads(path.read_text(encoding="utf-8"))


def _table(rows: list[list], header: list[str]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)] if rows else [len(h) for h in header]
    print("  ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(x).ljust(w) for x, w in zip(r, widths)))


def cmd_show(a) -> int:
    ds = _dataset(a)
    if ds is None:
        return 1
    what, pat = a.what, (a.filter or "").lower()
    if what == "plans":
        rows = [[p["plan_set_key"], p["name"], p["billing_period"], p["credits_per_month"], p["seats"] or "",
                 p["pricing"]["before_offer"]["per_month"], p["pricing"]["after_offer"]["per_month"],
                 p["pricing"]["renewal"]["per_month"], f"{(p.get('discount') or {}).get('percent_off') or ''}",
                 (p.get("discount") or {}).get("applies_to") or "", p["price_per_credit"]["after_offer"]]
                for ps in ds["plan_sets"] for p in ps["plans"] if pat in p["plan_type"]]
        _table(rows, ["set", "plan", "billing", "credits/mo", "seats", "before/mo $", "after/mo $", "renew/mo $",
                      "off %", "applies", "$/credit"])
    elif what == "models":
        rows = []
        for m in sorted(ds["models"], key=lambda m: (m["category"], m["model_id"])):
            if pat and pat not in m["model_id"] and pat not in m["display_name"].lower() and pat != m["category"]:
                continue
            pts = [p for p in m["price_points"] if p["credits"] is not None]
            lo = min(pts, key=lambda p: p["credits"]) if pts else None
            rows.append([m["model_id"], m["display_name"], m["category"], m["price_point_count"],
                         lo["credits"] if lo else "", lo["unit"] if lo else "", "yes" if m["has_discount"] else "",
                         " ".join(f"{k}={'/'.join(map(str, v))}" for k, v in m["options"].items())[:80]])
        _table(rows, ["model_id", "name", "cat", "points", "min credits", "unit", "disc", "options"])
    elif what == "model":
        m = next((m for m in ds["models"] if m["model_id"] == a.filter), None)
        if not m:
            print(f"model {a.filter!r} not found", file=sys.stderr)
            return 1
        print(f"{m['display_name']} ({m['model_id']}) — {m['category']}, family {m['family']}")
        print("options:", json.dumps(m["options"]))
        rows = [[p["component"] or "", " ".join(f"{k}={v}" for k, v in p["dimensions"].items()), p["unit"], p["credits"],
                 p["original_credits"], f"{p['discount_percent']}%" if p["discount_percent"] else "",
                 json.dumps(p["example"]) if p["example"] else "", p["usd_estimate"] or ""] for p in m["price_points"]]
        _table(rows, ["component", "dimensions", "unit", "credits", "orig", "disc", "example", "≈USD"])
        if m["entitlements"]:
            print("\nentitlements:")
            _table([[e["plan_type"], e["billing_period"], e["type"], e["count"] or "", e["duration_days"] or "",
                     e["max_resolution"] or ""] for e in m["entitlements"]],
                   ["plan", "billing", "type", "count", "days", "max res"])
    elif what == "plan-sets":
        _table([[ps["plan_set_key"], ps["country_code"], ps["plan_count"], ",".join(ps["plan_types"])]
                for ps in ds["plan_sets"]], ["plan_set_key", "country", "plans", "plan types"])
    elif what == "benefits":
        rows = [[c["plan_type"], c["billing_period"], c["tab"], ",".join(c["unlimited_model_ids"])[:70],
                 ",".join(f"{g['model_id']}x{g['count']}" for g in c["free_gens"])[:50]]
                for c in ds["benefit_cards"] if pat in c["plan_type"]]
        _table(rows, ["plan", "billing", "tab", "unlimited", "free gens"])
    elif what == "compare":
        for c in ds["comparisons"]:
            print(f"\n## {c['plan_set_key']} / {c['billing_period']}")
            types = list(dict.fromkeys(p["plan_type"] for p in c["plans"]))
            rows = []
            for cat in c["categories"]:
                for f in cat["features"]:
                    if pat and pat not in f["name"].lower():
                        continue
                    vals = {v["plan_type"]: v["raw"] for v in f["values"]}
                    rows.append([cat["slug"], f["name"][:34], f["detail"] or ""] + [vals.get(t, "") for t in types])
            _table(rows, ["category", "feature", "detail"] + types)
    return 0


def cmd_plan_sets(a) -> int:
    print("Presets:")
    for k, v in PLAN_SET_PRESETS.items():
        print(f"  {k:6} -> {', '.join(v) if len(v) < 6 else f'{len(v)} keys'}")
    print("\nFrontend tier mapping (from JS):", ", ".join(f"{t}->{k}" for t, k in PLAN_SET_TIERS.items()))
    print(f"US prices (pricing.md) = {US_PLAN_SET}\n\nAll plan_set_keys accepted by the API:")
    print("  " + "\n  ".join(PLAN_SET_KEYS))
    return 0


def cmd_sections(a) -> int:
    for s, eps in SECTIONS.items():
        print(f"{s:10} {'(default)' if s in DEFAULT_SECTIONS else '(needs --token)' if s == 'auth' else ''}")
        for e in eps:
            print(f"    {ENDPOINTS[e][0]}{'   [auth]' if ENDPOINTS[e][1] else ''}")
    return 0


def cmd_runs(a) -> int:
    idx = Path(a.runs_dir) / "index.jsonl"
    if not idx.exists():
        print("no runs yet")
        return 0
    lines = [json.loads(x) for x in idx.read_text(encoding="utf-8").splitlines() if x.strip()][-a.limit:]
    _table([[r["run_id"], r["status"], r.get("duration_s"), r.get("country_code"),
             ", ".join(f"{k}={v}" for k, v in (r.get("counts") or {}).items() if v)] for r in lines],
           ["run_id", "status", "secs", "country", "counts"])
    return 0


def cmd_schema(a) -> int:
    from .schemas import MODEL_BY_KIND, Dataset
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset.schema.json").write_text(json.dumps(Dataset.model_json_schema(mode="serialization"), indent=4), "utf-8")
    for kind, model in MODEL_BY_KIND.items():
        (out / f"{kind}.schema.json").write_text(json.dumps(model.model_json_schema(mode="serialization"), indent=4), "utf-8")
    print(f"wrote {len(MODEL_BY_KIND) + 1} schemas to {out}")
    return 0


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="higgsfield_scraper", description="Scrape Higgsfield.ai plans, offers and model credit costs")
    sub = ap.add_subparsers(dest="command")

    s = sub.add_parser("scrape", help="fetch live data into a new run folder")
    _selection_args(s)
    _run_args(s)
    s.add_argument("--token", default=None, help="Clerk session JWT for --sections auth (or env HF_TOKEN)")
    s.add_argument("--cache", action="store_true", help="enable Scrapy HTTP cache (dev)")
    s.add_argument("--no-http-archive", action="store_true",
                   help="don't write <run>/http/ (per-request request.json, response.json, body.raw, curl.sh, session.har)")
    s.add_argument("--obey-robots", action="store_true",
                   help="check and obey robots.txt (default: off — robots.txt is not obeyed)")
    s.add_argument("--dry-run", action="store_true", help="print the requests that would be made and exit")
    s.set_defaults(func=cmd_scrape)

    n = sub.add_parser("normalize", help="re-parse a run's raw/ responses offline into a new run")
    n.add_argument("--run", default=None, help="source run folder (default: latest)")
    _selection_args(n)
    _run_args(n)
    n.set_defaults(func=cmd_normalize)

    sh = sub.add_parser("show", help="print tables from a run's dataset")
    sh.add_argument("what", choices=["plans", "models", "model", "plan-sets", "benefits", "compare"])
    sh.add_argument("filter", nargs="?", default=None, help="substring filter, or model_id for `show model`")
    sh.add_argument("--run", default=None)
    sh.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    sh.set_defaults(func=cmd_show)

    sub.add_parser("plan-sets", help="list plan_set_keys and presets").set_defaults(func=cmd_plan_sets)
    sub.add_parser("sections", help="list sections and their endpoints").set_defaults(func=cmd_sections)
    r = sub.add_parser("runs", help="list recent runs")
    r.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(func=cmd_runs)
    sc = sub.add_parser("schema", help="export JSON Schemas")
    sc.add_argument("--out", default="schemas")
    sc.set_defaults(func=cmd_schema)
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    _load_dotenv()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv = ["scrape", *argv]
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
