"""Command-line entry point.

  python -m higgsfield_scraper scrape [pricing] [options]   # pricing (default scraper) -> runs/<ts>_<label>/
  python -m higgsfield_scraper scrape community [options]   # any registered scraper: see `scrapers`
  python -m higgsfield_scraper scrapers                     # list scrapers
  python -m higgsfield_scraper normalize --run DIR          # re-parse a run's raw/ offline (scraper auto-detected)
  python -m higgsfield_scraper show plans|models|model <id>|plan-sets|benefits|compare [--run DIR]   (pricing)
  python -m higgsfield_scraper auth-check [--json]          # is the login/session configured and working?
  python -m higgsfield_scraper runs [--json] | runs clean --keep-last N [--keep-days D] [--yes]
  python -m higgsfield_scraper show-config [--json]         # resolved settings (flags/env/.env), secrets redacted
  python -m higgsfield_scraper plan-sets | sections | schema
  python -m higgsfield_scraper diff [--old RUN] [--new RUN] [--json] [--out FILE]   # compare two pricing runs
  python -m higgsfield_scraper crosscheck [--run RUN] [--json] [--save]            # run vs official pricing.md
  python -m higgsfield_scraper menu                         # interactive menu (also -i; default with no args on a TTY)

Exit codes: 0 success · 1 failure · 2 usage error · 3 partial · 4 blocked (bot protection) · 130 cancelled (Ctrl-C)
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
from .core.cli_common import add_access_args, add_limit_args, add_run_args, common_from_args, resolve_log_levels
from .core.redact import REDACTED, is_secret_key

EXIT_CODES_HELP = """exit codes:
  0    success
  1    failure (runtime / config error)
  2    usage error (bad arguments)
  3    partial (finished, but some requests/items failed or a limit stopped the run)
  4    blocked (bot protection stopped the run; no evasion is attempted)
  130  cancelled (Ctrl-C)"""
DOTENV_KEYS: set[str] = set()        # names (never values) of variables that came from .env


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip().strip('"').strip("'")
                DOTENV_KEYS.add(k.strip())


# backwards-compatible names (tests/scripts import these)
def _selection_args(p: argparse.ArgumentParser) -> None:
    registry.get("pricing").add_args(p)


def _run_args(p: argparse.ArgumentParser) -> None:
    add_run_args(p)


SECRET_ARGS = ("token",)


def _public_args(a) -> dict:
    return {k: v for k, v in vars(a).items() if k not in (*SECRET_ARGS, "func")} | {
        "token": "***" if getattr(a, "token", None) else None}


def _manager(a, label: str, console=None):
    from .run.manager import RunManager
    return RunManager(a.runs_dir, label, *resolve_log_levels(a), log_format=a.log_format, no_color=a.no_color,
                      heartbeat=a.heartbeat, split_logs=a.split_logs, console=console)


def first_requests(a) -> list:
    """The first requests `scrape <scraper>` would make (what --dry-run prints). No network."""
    sdef = registry.get(a.scraper)
    token = a.token or os.environ.get("HF_TOKEN") or None
    sel = sdef.make_selection(a)
    spider_cls = resolve(sdef.spider_cls)
    sp = spider_cls(selection=sel, token=token) if sdef.name == "pricing" else \
        spider_cls(selection=sel, common=CommonOptions(**{**common_from_args(a).to_dict(), "auth": "off"}), token=None)
    return list(sp.build_requests())


def default_label(a) -> str:
    """The run label `scrape` uses when --label is not given."""
    sdef = registry.get(a.scraper)
    base_label = sdef.default_label(sdef.make_selection(a))
    return base_label if sdef.name == "pricing" else f"{sdef.name}-{base_label}"


# ---------------------------------------------------------------- commands
def cmd_scrape(a, *, console=None, on_crawler=None, invocation_mode: str = "flags") -> int:
    """`console` / `on_crawler` / `invocation_mode` are used by the interactive menu's runner (live progress)."""
    sdef = registry.get(a.scraper)
    token = a.token or os.environ.get("HF_TOKEN") or None
    sel = sdef.make_selection(a)
    common = common_from_args(a)
    if a.dry_run:
        for r in first_requests(a):
            auth = r.meta.get("auth") or "Authorization" in r.headers
            print(f"GET {r.url}" + ("   [auth]" if auth else ""))
        if sdef.name != "pricing":
            print("# (first requests only; pagination/detail requests follow at runtime)", file=sys.stderr)
        return 0
    label = a.label or default_label(a)
    mgr = _manager(a, label, console=console)
    overrides = {"HIGGS_HTTP_ARCHIVE": not a.no_http_archive, "ROBOTSTXT_OBEY": a.obey_robots}
    return mgr.scrape(sel, token=token, cache=a.cache, settings_overrides=overrides, args=_public_args(a),
                      scraper=sdef.name, common=common, on_crawler=on_crawler, invocation_mode=invocation_mode)


def cmd_normalize(a, *, console=None, invocation_mode: str = "flags") -> int:
    from .run.context import latest_run
    src = Path(a.run) if a.run else latest_run(a.runs_dir)
    if not src or not (src / "raw").exists():
        print(f"no raw/ folder found in {src}", file=sys.stderr)
        return 1
    m = json.loads((src / "manifest.json").read_text(encoding="utf-8")) if (src / "manifest.json").exists() else {}
    name = a.scraper or m.get("scraper") or registry.DEFAULT_SCRAPER
    sdef = registry.get(name)
    mgr = _manager(a, a.label or "normalize", console=console)
    if name == "pricing":                     # unchanged pricing behaviour
        sel = sdef.make_selection(a)
        if a.sections == ",".join(DEFAULT_SECTIONS) and m:
            prev = m.get("selection") or {}
            sel.sections, sel.plan_set_keys = prev.get("sections", sel.sections), prev.get("plan_set_keys", sel.plan_set_keys)
        return mgr.normalize(src, sel, args=_public_args(a), scraper=name, invocation_mode=invocation_mode)
    sel = sdef.selection_from_dict(m.get("selection") or {})
    return mgr.normalize(src, sel, args=_public_args(a), scraper=name, common=CommonOptions.from_dict(m.get("common")),
                         invocation_mode=invocation_mode)


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
        print(f"{s:10} {'(default)' if s in DEFAULT_SECTIONS else '(needs login)' if s == 'auth' else ''}")
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
    if a.token:
        print("warning: --token is deprecated (it leaks into shell history); set HF_TOKEN in .env or run `login`",
              file=sys.stderr)
    prov = TokenProvider.from_env(a.token)
    if not prov.configured:
        if a.json:
            print(json.dumps({"configured": False, "ok": False, "source": None,
                              "error": "no login configured"}, indent=4))
        else:
            print("no login configured: run `login` (HF_EMAIL/HF_PASSWORD in .env) or set HF_CLERK_CLIENT in .env")
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
    from .run.context import normalize_status
    if getattr(a, "runs_cmd", None) == "clean":
        return cmd_runs_clean(a)
    idx = Path(a.runs_dir) / "index.jsonl"
    lines = [json.loads(x) for x in idx.read_text(encoding="utf-8").splitlines() if x.strip()][-a.limit:] \
        if idx.exists() else []
    for r in lines:
        r["status"] = normalize_status(r.get("status"))
        if r.get("duration_s") is None and r.get("duration_ms") is not None:
            r["duration_s"] = round(r["duration_ms"] / 1000, 2)
    if a.json:
        print(json.dumps(lines, indent=4, default=str))
        return 0
    if not lines:
        print("no runs yet")
        return 0
    _table([[r["run_id"], r["status"], r.get("duration_s"), r.get("country_code") or "",
             ", ".join(f"{k}={v}" for k, v in (r.get("counts") or {}).items() if v)] for r in lines],
           ["run_id", "status", "secs", "country", "counts"])
    return 0


def cmd_runs_clean(a) -> int:
    from .run.retention import apply_cleanup, plan_cleanup
    cands = plan_cleanup(a.runs_dir, a.keep_last, a.keep_days)
    todo = [c for c in cands if c.action == "delete"]
    deleted = apply_cleanup(cands) if a.yes else []
    if a.json:
        print(json.dumps({"dry_run": not a.yes, "runs": [c.to_dict() for c in cands],
                          "deleted": [c.path.name for c in deleted]}, indent=4))
        return 0
    for c in cands:
        verb = ("deleted" if c in deleted else "would delete") if c.action == "delete" else "keep"
        print(f"{verb:13} {c.path.name:45} {c.status or '-':10} {c.reason}")
    mb = sum(c.size_bytes for c in todo) / 1048576
    if a.yes:
        print(f"\ndeleted {len(deleted)} run folder(s), {mb:.1f} MB", file=sys.stderr)
    else:
        print(f"\ndry run: {len(todo)} run folder(s) ({mb:.1f} MB) would be deleted — add --yes to delete",
              file=sys.stderr)
    return 0


def _config_value(name: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    risky = ("TOKEN", "PASS", "SECRET", "KEY", "COOKIE", "CLIENT", "EMAIL", "SESSION", "JWT")
    if is_secret_key(name) or any(r in name.upper() for r in risky):
        return f"{REDACTED} (set)" if value else None
    return value


def cmd_show_config(a) -> int:
    """Resolved configuration with its source (default / .env / env / flag); secret values are never printed."""
    from .core.auth import CLERK_BASE
    from .core.base import CommonOptions
    from . import settings as scrapy_settings
    env = {}
    for k in sorted(os.environ):
        if k.startswith("HF_") or k in ("NO_COLOR", "SCRAPY_SETTINGS_MODULE"):
            env[k] = {"value": _config_value(k, os.environ.get(k)), "source": ".env" if k in DOTENV_KEYS else "env"}
    def src(env_name: str) -> str:
        return (".env" if env_name in DOTENV_KEYS else "env") if os.environ.get(env_name) else "default"
    from .core.auth_login import CACHE_PATH as cached
    auth_source = ("HF_TOKEN" if os.environ.get("HF_TOKEN") else "cached login" if cached.exists()
                   else "HF_CLERK_CLIENT" if os.environ.get("HF_CLERK_CLIENT") else None)
    cfg = {
        "dotenv": {"path": str(Path(".env").resolve()), "exists": Path(".env").exists(),
                   "keys": sorted(DOTENV_KEYS)},
        "run": {"runs_dir": {"value": os.environ.get("HF_RUNS_DIR", "runs"), "source": src("HF_RUNS_DIR")},
                "log_level": {"value": os.environ.get("HF_LOG_LEVEL", "INFO"), "source": src("HF_LOG_LEVEL")},
                "log_format": {"value": os.environ.get("HF_LOG_FORMAT", "console"), "source": src("HF_LOG_FORMAT")},
                "no_color": {"value": bool(os.environ.get("NO_COLOR")), "source": src("NO_COLOR")},
                "heartbeat_s": {"value": scrapy_settings.HIGGS_HEARTBEAT, "source": "default"}},
        "auth": {"configured": bool(auth_source), "source": auth_source,
                 "clerk_url": {"value": CLERK_BASE, "source": src("HF_CLERK_URL")}},
        "limits_defaults": CommonOptions().to_dict(),
        "scrapy": {k: getattr(scrapy_settings, k) for k in (
            "CONCURRENT_REQUESTS", "CONCURRENT_REQUESTS_PER_DOMAIN", "DOWNLOAD_DELAY", "AUTOTHROTTLE_ENABLED",
            "DOWNLOAD_TIMEOUT", "RETRY_TIMES", "RETRY_HTTP_CODES", "ROBOTSTXT_OBEY", "COOKIES_ENABLED",
            "USER_AGENT", "HIGGS_HTTP_ARCHIVE")},
        "env": env,
        "precedence": "defaults < .env < environment < command-line flags",
    }
    from .core.redact import redact
    cfg = {**redact({k: v for k, v in cfg.items() if k != "env"}), "env": env}   # env values: see _config_value
    cfg["precedence"] = cfg.pop("precedence")
    if a.json:
        print(json.dumps(cfg, indent=4, default=str))
        return 0
    def walk(d, prefix=""):
        for k, v in d.items():
            if isinstance(v, dict) and set(v) == {"value", "source"}:
                print(f"{prefix}{k:28} {v['value']!s:40} ({v['source']})")
            elif isinstance(v, dict):
                print(f"{prefix}{k}:")
                walk(v, prefix + "  ")
            else:
                print(f"{prefix}{k:28} {v}")
    walk(cfg)
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


def cmd_diff(a) -> int:
    """Compare two pricing runs' output/dataset.json (logic: pricing_diff.py). Exit 0 whether or not prices changed."""
    from . import pricing_diff as pdiff
    only = [x.strip() for x in (a.only or "").split(",") if x.strip()] or None
    bad = [x for x in only or [] if x not in pdiff.CATEGORIES]
    out = Path(a.out) if a.out else None
    if bad or (out and out.suffix.lower() not in (".md", ".json")):
        print(f"error: --only takes {','.join(pdiff.CATEGORIES)}" if bad else "error: --out must end in .md or .json",
              file=sys.stderr)
        return 2
    try:
        old_dir, new_dir = pdiff.resolve_pair(a.runs_dir, a.old, a.new)
        load = lambda d: json.loads((d / "output" / "dataset.json").read_text(encoding="utf-8"))  # noqa: E731
        diff = pdiff.diff_datasets(load(old_dir), load(new_dir), only=only, min_change=a.min_change,
                                   old_run=str(old_dir), new_run=str(new_dir),
                                   old_selection=pdiff.run_selection(old_dir), new_selection=pdiff.run_selection(new_dir))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(diff, indent=4, ensure_ascii=False, default=str) if out.suffix.lower() == ".json"
                       else pdiff.render_markdown(diff), encoding="utf-8")
        print(f"# wrote {out}", file=sys.stderr)
    if a.json:
        print(json.dumps(diff, indent=4, ensure_ascii=False, default=str))
    else:
        pdiff.render_console(diff)
    return 0


def cmd_crosscheck(a) -> int:
    """Fetch https://higgsfield.ai/pricing.md (one GET) and compare it with a run's ps_a3 dataset."""
    from . import pricing_crosscheck as pcc
    from .pricing_diff import pricing_runs, resolve_run, run_selection
    try:
        if a.run:
            run = resolve_run(a.run, a.runs_dir)
        else:
            run = next((d for d in reversed(pricing_runs(a.runs_dir))
                        if pcc.PLAN_SET in (run_selection(d).get("plan_set_keys") or [])), None)
            if run is None:
                raise FileNotFoundError(f"no successful pricing run with the {pcc.PLAN_SET} plan set in {a.runs_dir}")
        ds = json.loads((run / "output" / "dataset.json").read_text(encoding="utf-8"))
        text, info = pcc.fetch_pricing_md()
        rep = pcc.crosscheck(pcc.parse_pricing_md(text), ds)
    except (OSError, ValueError) as e:                    # urllib errors are OSErrors
        print(f"error: {e}", file=sys.stderr)
        return 1
    rep = {"source": info, **rep}
    rep["run"]["path"] = str(run)
    if a.save:
        d = run / "crosscheck"
        d.mkdir(exist_ok=True)
        stamp = info["fetched_at"][:19].replace("-", "").replace(":", "").replace("T", "-")
        (d / f"pricing_{stamp}.md").write_bytes(text.encode("utf-8"))
        (d / f"report_{stamp}.json").write_text(json.dumps(rep, indent=4, ensure_ascii=False), encoding="utf-8")
        print(f"# saved {d / f'pricing_{stamp}.md'} and {d / f'report_{stamp}.json'}", file=sys.stderr)
    if a.json:
        print(json.dumps(rep, indent=4, ensure_ascii=False))
    else:
        pcc.render_console(rep)
    return 0


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="higgsfield_scraper", description="Scrape Higgsfield.ai data (pricing, community, …)",
                                 epilog=EXIT_CODES_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command")

    s = sub.add_parser("scrape", help="fetch live data into a new run folder (`scrape <scraper> -h`)")
    ssub = s.add_subparsers(dest="scraper", metavar="<scraper>")
    for name, sdef in registry.available().items():
        sp = ssub.add_parser(name, help=sdef.description, description=sdef.description,
                             epilog=("examples:\n  " + "\n  ".join(sdef.examples) + "\n\n" if sdef.examples else "")
                             + EXIT_CODES_HELP,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
        sdef.add_args(sp)
        if name != "pricing":
            add_limit_args(sp)
        add_access_args(sp)
        add_run_args(sp)
        sp.set_defaults(func=cmd_scrape, scraper=name)

    n = sub.add_parser("normalize", help="re-parse a run's raw/ responses offline into a new run",
                       epilog=EXIT_CODES_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
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
    ac.add_argument("--token", default=None, help="deprecated: use HF_TOKEN in .env or `login`")
    ac.add_argument("--json", action="store_true", help="always print machine-readable JSON")
    ac.set_defaults(func=cmd_auth_check)
    lg = sub.add_parser("login", help="log in with HF_EMAIL/HF_PASSWORD from .env (step 1), then --code (step 2)")
    lg.add_argument("--code", default=None, help="the 6-digit code Clerk emailed you")
    lg.set_defaults(func=cmd_login)
    sub.add_parser("plan-sets", help="list plan_set_keys and presets").set_defaults(func=cmd_plan_sets)
    sub.add_parser("sections", help="list pricing sections and their endpoints").set_defaults(func=cmd_sections)
    r = sub.add_parser("runs", help="list recent runs (`runs clean -h`: delete old run folders)")
    r.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    r.add_argument("--limit", type=int, default=20)
    r.add_argument("--json", action="store_true", help="print the runs as JSON")
    r.set_defaults(func=cmd_runs, runs_cmd=None)
    rsub = r.add_subparsers(dest="runs_cmd", metavar="[clean]")
    rc = rsub.add_parser("clean", help="delete old run folders (dry-run unless --yes)",
                         description="Keep the newest N runs and/or runs younger than D days; delete the rest. "
                                     "Never deletes running runs, the latest successful run or folders with a KEEP "
                                     "file. Dry-run by default.")
    rc.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    rc.add_argument("--keep-last", type=int, default=None, metavar="N", help="keep the newest N runs")
    rc.add_argument("--keep-days", type=float, default=None, metavar="D", help="keep runs younger than D days")
    rc.add_argument("-y", "--yes", action="store_true", help="really delete (default: dry run)")
    rc.add_argument("--json", action="store_true")
    rc.set_defaults(func=cmd_runs)
    cfg = sub.add_parser("show-config", help="print the resolved configuration (flags/env/.env), secrets redacted")
    cfg.add_argument("--json", action="store_true")
    cfg.set_defaults(func=cmd_show_config)
    sc = sub.add_parser("schema", help="export JSON Schemas of every scraper")
    sc.add_argument("--out", default="schemas")
    sc.set_defaults(func=cmd_schema)
    df = sub.add_parser("diff", help="compare two pricing runs (plans, offers, model credits, benefits)",
                        description="Compare two pricing runs' output/dataset.json. Default: the latest successful "
                                    "pricing run vs the previous one with the same plan sets. Exit 0 whether or not "
                                    "anything changed (see `changed` in --json).")
    df.add_argument("--old", default=None, metavar="RUN", help="older run folder or run id (default: previous compatible run)")
    df.add_argument("--new", default=None, metavar="RUN", help="newer run folder or run id (default: latest pricing run)")
    df.add_argument("--json", action="store_true", help="print the structured diff as JSON")
    df.add_argument("--out", default=None, metavar="FILE", help="also write a report: FILE.md or FILE.json")
    df.add_argument("--only", default=None, metavar="LIST", help="plans,models,benefits,offers (default: all)")
    df.add_argument("--min-change", type=float, default=0.0, metavar="PCT",
                    help="hide price/credit changes smaller than PCT percent")
    df.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    df.set_defaults(func=cmd_diff)
    cc = sub.add_parser("crosscheck", help="compare a run's ps_a3 prices with the official higgsfield.ai/pricing.md",
                        description="Fetch https://higgsfield.ai/pricing.md (one GET) and compare its plan prices, "
                                    "model credits and plan benefits with a run's ps_a3 (US) dataset.")
    cc.add_argument("--run", default=None, metavar="RUN", help="run folder or run id (default: latest ps_a3 pricing run)")
    cc.add_argument("--json", action="store_true", help="print the report as JSON")
    cc.add_argument("--save", action="store_true", help="store pricing.md + the report in <run>/crosscheck/")
    cc.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    cc.set_defaults(func=cmd_crosscheck)
    sub.add_parser("menu", help="interactive menu (alias -i/--interactive; the default with no args on a terminal; "
                                "needs the `interactive` extra)").set_defaults(func=cmd_menu)
    return ap


def cmd_menu(a) -> int:
    from .interactive import launch
    return launch()


def _normalize_argv(argv: list[str]) -> list[str]:
    """Backwards compatible: `<no args>`, `--sections …` and `scrape --sections …` mean `scrape pricing …`."""
    names = set(registry.available())
    if not argv or (argv[0].startswith("-") and argv[0] not in ("-h", "--help")):
        return ["scrape", registry.DEFAULT_SCRAPER, *argv]
    if argv[0] == "scrape" and (len(argv) == 1 or (argv[1] not in names and argv[1] not in ("-h", "--help"))):
        return ["scrape", registry.DEFAULT_SCRAPER, *argv[1:]]
    return argv


def _auto_menu() -> bool:
    """No arguments on a real terminal (and not CI) -> menu; otherwise the old default (pricing scrape) stays."""
    from .interactive import should_auto_launch
    return should_auto_launch()


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    _load_dotenv()
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw[:1] in (["menu"], ["-i"], ["--interactive"]) or (argv is None and not raw and _auto_menu()):
        from .interactive import launch            # interactive mode (questionary + rich); flags are unchanged
        return launch()
    argv = _normalize_argv(raw)
    a = build_parser().parse_args(argv)
    if not hasattr(a, "func"):
        build_parser().print_help()
        return 2
    try:
        return a.func(a)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
