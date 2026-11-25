"""Command-line entry point.

  python -m higgsfield_scraper scrape [pricing] [options]   # pricing (default scraper) -> runs/<ts>_<label>/
  python -m higgsfield_scraper scrape community [options]   # any registered scraper: see `scrapers`
  python -m higgsfield_scraper scrapers                     # list scrapers
  python -m higgsfield_scraper normalize --run DIR          # re-parse a run's raw/ offline (scraper auto-detected)
  python -m higgsfield_scraper show plans|models|model <id>|plan-sets|benefits|compare [--run DIR]   (pricing)
  python -m higgsfield_scraper auth-check                   # is the login/session configured and working?
  python -m higgsfield_scraper plan-sets | sections | runs | schema
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from .constants import DEFAULT_SECTIONS, ENDPOINTS, PLAN_SET_KEYS, PLAN_SET_PRESETS, PLAN_SET_TIERS, SECTIONS, US_PLAN_SET
from .core import registry
from .core.base import CommonOptions, resolve
from .core.cli_common import add_access_args, add_limit_args, add_run_args, common_from_args


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# backwards-compatible names (tests/scripts import these)
def _selection_args(p: argparse.ArgumentParser) -> None:
    registry.get("pricing").add_args(p)


def _run_args(p: argparse.ArgumentParser) -> None:
    add_run_args(p)


SECRET_ARGS = ("token",)


def _public_args(a) -> dict:
    return {k: v for k, v in vars(a).items() if k not in (*SECRET_ARGS, "func")} | {
        "token": "***" if getattr(a, "token", None) else None}


# ---------------------------------------------------------------- commands
def cmd_scrape(a) -> int:
    from .run.manager import RunManager
    sdef = registry.get(a.scraper)
    token = a.token or os.environ.get("HF_TOKEN") or None
    sel = sdef.make_selection(a)
    common = common_from_args(a)
    if a.dry_run:
        spider_cls = resolve(sdef.spider_cls)
        sp = spider_cls(selection=sel, token=token) if sdef.name == "pricing" else \
            spider_cls(selection=sel, common=CommonOptions(**{**common.to_dict(), "auth": "off"}), token=None)
        for r in sp.build_requests():
            auth = r.meta.get("auth") or "Authorization" in r.headers
            print(f"GET {r.url}" + ("   [auth]" if auth else ""))
        if sdef.name != "pricing":
            print("# (first requests only; pagination/detail requests follow at runtime)", file=sys.stderr)
        return 0
    base_label = sdef.default_label(sel)
    label = a.label or (base_label if sdef.name == "pricing" else f"{sdef.name}-{base_label}")
    mgr = RunManager(a.runs_dir, label, a.log_level, a.file_log_level, a.scrapy_log_level)
    overrides = {"HIGGS_HTTP_ARCHIVE": not a.no_http_archive, "ROBOTSTXT_OBEY": a.obey_robots}
    return mgr.scrape(sel, token=token, cache=a.cache, settings_overrides=overrides, args=_public_args(a),
                      scraper=sdef.name, common=common)


def cmd_normalize(a) -> int:
    from .run.context import latest_run
    from .run.manager import RunManager
    src = Path(a.run) if a.run else latest_run(a.runs_dir)
    if not src or not (src / "raw").exists():
        print(f"no raw/ folder found in {src}", file=sys.stderr)
        return 1
    m = json.loads((src / "manifest.json").read_text(encoding="utf-8")) if (src / "manifest.json").exists() else {}
    name = a.scraper or m.get("scraper") or registry.DEFAULT_SCRAPER
    sdef = registry.get(name)
    mgr = RunManager(a.runs_dir, a.label or "normalize", a.log_level, a.file_log_level, a.scrapy_log_level)
    if name == "pricing":                     # unchanged pricing behaviour
        sel = sdef.make_selection(a)
        if a.sections == ",".join(DEFAULT_SECTIONS) and m:
            prev = m.get("selection") or {}
            sel.sections, sel.plan_set_keys = prev.get("sections", sel.sections), prev.get("plan_set_keys", sel.plan_set_keys)
        return mgr.normalize(src, sel, args=_public_args(a), scraper=name)
    sel = sdef.selection_from_dict(m.get("selection") or {})
    return mgr.normalize(src, sel, args=_public_args(a), scraper=name, common=CommonOptions.from_dict(m.get("common")))


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
    if ds.get("meta", {}).get("scraper") not in (None, "pricing"):
        print(f"`show` reads pricing datasets; this run is {ds['meta']['scraper']!r} — open output/summary.md",
              file=sys.stderr)
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


def cmd_scrapers(a) -> int:
    for name, sdef in registry.available().items():
        print(f"{name:10} {sdef.description}")
        for ex in sdef.examples:
            print(f"           e.g. {ex}")
    return 0


def cmd_auth_check(a) -> int:
    from .core.auth import TokenProvider
    prov = TokenProvider.from_env(a.token)
    if not prov.configured:
        print("no login configured: set HF_CLERK_CLIENT (or HF_EMAIL/HF_PASSWORD) in .env, or pass --token")
        return 1
    st = prov.status()
    print(json.dumps({k: v for k, v in st.items() if k != "session_id"}, indent=4))
    return 0 if st.get("ok") else 1


def cmd_login(a) -> int:
    """Two-step login: `login` (password from .env -> Clerk emails a code), then `login --code NNNNNN`.
    Afterwards the cached session (runs/.auth/clerk_client.json) mints fresh tokens automatically."""
    from .core.auth import TokenProvider
    from .core.auth_login import LoginError, finish_login, start_login
    try:
        if a.code:
            finish_login(a.code)
        else:
            res = start_login(os.environ.get("HF_EMAIL", ""), os.environ.get("HF_PASSWORD", ""))
            if res["status"] == "code_sent":
                print(f"Clerk sent a one-time code to {res['sent_to']}.\n"
                      f"Finish with:  python -m higgsfield_scraper login --code <6-digit code>   (within 15 min)")
                return 0
    except LoginError as e:
        print(f"login failed: {e}", file=sys.stderr)
        return 1
    st = TokenProvider.from_env().status()
    print("login complete — session cached in runs/.auth/clerk_client.json (gitignored)")
    print(json.dumps({k: v for k, v in st.items() if k != "session_id"}, indent=4))
    return 0 if st.get("ok") else 1


def cmd_runs(a) -> int:
    idx = Path(a.runs_dir) / "index.jsonl"
    if not idx.exists():
        print("no runs yet")
        return 0
    lines = [json.loads(x) for x in idx.read_text(encoding="utf-8").splitlines() if x.strip()][-a.limit:]
    _table([[r["run_id"], r["status"], r.get("duration_s"), r.get("country_code") or "",
             ", ".join(f"{k}={v}" for k, v in (r.get("counts") or {}).items() if v)] for r in lines],
           ["run_id", "status", "secs", "country", "counts"])
    return 0


def cmd_schema(a) -> int:
    from .schemas import Dataset
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    (out / "dataset.schema.json").write_text(json.dumps(Dataset.model_json_schema(mode="serialization"), indent=4), "utf-8")
    n += 1
    for name, sdef in registry.available().items():
        if name != "pricing" and sdef.dataset_model is not None:
            (out / f"{name}.dataset.schema.json").write_text(
                json.dumps(sdef.dataset_model.model_json_schema(mode="serialization"), indent=4), "utf-8")
            n += 1
        for kind, model in sdef.model_by_kind.items():
            (out / f"{kind}.schema.json").write_text(json.dumps(model.model_json_schema(mode="serialization"), indent=4), "utf-8")
            n += 1
    print(f"wrote {n} schemas to {out}")
    return 0


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="higgsfield_scraper", description="Scrape Higgsfield.ai data (pricing, community, …)")
    sub = ap.add_subparsers(dest="command")

    s = sub.add_parser("scrape", help="fetch live data into a new run folder (`scrape <scraper> -h`)")
    ssub = s.add_subparsers(dest="scraper", metavar="<scraper>")
    for name, sdef in registry.available().items():
        sp = ssub.add_parser(name, help=sdef.description, description=sdef.description,
                             epilog="examples:\n  " + "\n  ".join(sdef.examples) if sdef.examples else None,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
        sdef.add_args(sp)
        if name != "pricing":
            add_limit_args(sp)
        add_access_args(sp)
        add_run_args(sp)
        sp.set_defaults(func=cmd_scrape, scraper=name)

    n = sub.add_parser("normalize", help="re-parse a run's raw/ responses offline into a new run")
    n.add_argument("--run", default=None, help="source run folder (default: latest)")
    n.add_argument("--scraper", default=None, help="override the scraper (default: from the run's manifest)")
    _selection_args(n)
    add_run_args(n)
    n.set_defaults(func=cmd_normalize)

    sh = sub.add_parser("show", help="print tables from a pricing run's dataset")
    sh.add_argument("what", choices=["plans", "models", "model", "plan-sets", "benefits", "compare"])
    sh.add_argument("filter", nargs="?", default=None, help="substring filter, or model_id for `show model`")
    sh.add_argument("--run", default=None)
    sh.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    sh.set_defaults(func=cmd_show)

    sub.add_parser("scrapers", help="list available scrapers").set_defaults(func=cmd_scrapers)
    ac = sub.add_parser("auth-check", help="check login/session configuration (never prints secrets)")
    ac.add_argument("--token", default=None)
    ac.set_defaults(func=cmd_auth_check)
    lg = sub.add_parser("login", help="log in with HF_EMAIL/HF_PASSWORD from .env (step 1), then --code (step 2)")
    lg.add_argument("--code", default=None, help="the 6-digit code Clerk emailed you")
    lg.set_defaults(func=cmd_login)
    sub.add_parser("plan-sets", help="list plan_set_keys and presets").set_defaults(func=cmd_plan_sets)
    sub.add_parser("sections", help="list pricing sections and their endpoints").set_defaults(func=cmd_sections)
    r = sub.add_parser("runs", help="list recent runs")
    r.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(func=cmd_runs)
    sc = sub.add_parser("schema", help="export JSON Schemas of every scraper")
    sc.add_argument("--out", default="schemas")
    sc.set_defaults(func=cmd_schema)
    return ap


def _normalize_argv(argv: list[str]) -> list[str]:
    """Backwards compatible: `<no args>`, `--sections …` and `scrape --sections …` mean `scrape pricing …`."""
    names = set(registry.available())
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        return ["scrape", registry.DEFAULT_SCRAPER, *argv]
    if argv[0] == "scrape" and (len(argv) == 1 or (argv[1] not in names and argv[1] not in ("-h", "--help"))):
        return ["scrape", registry.DEFAULT_SCRAPER, *argv[1:]]
    return argv


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    _load_dotenv()
    argv = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    a = build_parser().parse_args(argv)
    if not hasattr(a, "func"):
        build_parser().print_help()
        return 2
    try:
        return a.func(a)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
