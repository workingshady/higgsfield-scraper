"""Cross-check a run's `ps_a3` (US) dataset against the official https://higgsfield.ai/pricing.md
(`python -m higgsfield_scraper crosscheck`).

`parse_pricing_md(text)` and `crosscheck(parsed, dataset)` are pure; `fetch_pricing_md()` is one plain GET.

What pricing.md states and how it maps to the dataset (prices per month, per seat for business plans):
  "$19/mo"                                  after_offer = before_offer = renewal = 19
  "$40 first month, then $59/mo"            after_offer = 40, renewal = before_offer = 59
  "$55/mo (list price $79/mo)"              after_offer = renewal = 55, before_offer = 79
  "$30/mo, billed $360 yearly (list ...)"   annual: after_offer/renewal per_month = 30, total = 360
Only values the text states are compared. Plans are matched on (plan_type, billing_period, credits_per_month).
Model credit costs are compared only if pricing.md has a table with a "model" and a "credit" column and the model
name equals a dataset display_name (case-insensitive). Plan benefit rows ("Unlimited & free gens") are matched by
their exact label against the dataset's benefit-card rows.
"""
from __future__ import annotations

import hashlib
import re
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

PRICING_MD_URL = "https://higgsfield.ai/pricing.md"
PLAN_SET = "ps_a3"
_MONEY = r"\$\s?([\d,]+(?:\.\d+)?)"


# ------------------------------------------------------------------ fetch
def fetch_pricing_md(url: str = PRICING_MD_URL, timeout: float = 30.0) -> tuple[str, dict]:
    """One plain GET with the project's User-Agent. -> (text, info)."""
    from .settings import USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/markdown, text/plain, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:          # noqa: S310 (fixed https URL)
        body = r.read()
        info = {"url": url, "status": r.status, "content_type": r.headers.get("Content-Type"),
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    return body.decode("utf-8", errors="replace"), info


# ------------------------------------------------------------------ parse
def _money(s: str) -> Optional[str]:
    try:
        return str(Decimal(s.replace(",", "")))
    except (InvalidOperation, AttributeError):
        return None


def _int(s: str) -> Optional[int]:
    m = re.search(r"\d[\d,]*", s or "")
    return int(m.group(0).replace(",", "")) if m else None


def _plan_type(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def parse_price_cell(cell: str, period: str) -> dict:
    """A 'Monthly billing' / 'Annual billing' cell -> {stage.part: Decimal-string} for the values it states."""
    cell = cell.strip()
    out: dict[str, str] = {}
    if cell.lower() == "free":
        return {f"{st}.{pt}": "0" for st in ("before_offer", "after_offer", "renewal") for pt in ("per_month", "total")}
    lst = re.search(r"list price " + _MONEY, cell)
    first = re.search(_MONEY + r" first month, then " + _MONEY + r"/mo", cell)
    if first:
        out["after_offer.per_month"] = _money(first.group(1))
        out["renewal.per_month"] = out["before_offer.per_month"] = _money(first.group(2))
    else:
        m = re.match(_MONEY + r"/mo", cell)
        if not m:
            return {}
        out["after_offer.per_month"] = out["renewal.per_month"] = _money(m.group(1))
        out["before_offer.per_month"] = _money(lst.group(1)) if lst else out["after_offer.per_month"]
    if lst:
        out["before_offer.per_month"] = _money(lst.group(1))
    billed = re.search(r"billed " + _MONEY + r" yearly", cell)
    if billed and period == "annual":
        out["after_offer.total"] = out["renewal.total"] = _money(billed.group(1))
        if not lst:
            out["before_offer.total"] = out["after_offer.total"]
    return out


def _tables(lines: list[str]) -> list[tuple[str, list[str], list[list[str]]]]:
    """Markdown tables -> [(nearest '##' heading, header cells, rows)]."""
    out, heading, i = [], "", 0
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("#"):
            heading = ln.lstrip("#").strip()
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-{3,}", lines[i + 1].strip()):
            cells = lambda s: [c.strip() for c in s.strip().strip("|").split("|")]  # noqa: E731
            header, rows = cells(ln), []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append((heading, header, rows))
            continue
        i += 1
    return out


def _col(header: list[str], *words: str, exclude: tuple[str, ...] = ()) -> Optional[int]:
    for i, h in enumerate(header):
        hl = h.lower()
        if all(w in hl for w in words) and not any(x in hl for x in exclude):
            return i
    return None


_BENEFIT_RE = re.compile(r"^-\s+(?P<label>[^()]+?)\s*\((?P<detail>[^)]*)\)\s*(?::\s*(?P<text>.*))?$")


def parse_benefit_detail(detail: str) -> dict:
    """'(2K, 7-day unlimited)' / '(300 free gens)' / '(No unlimited)' -> {status, count, duration_days, max_resolution}."""
    d = detail.strip()
    dl = d.lower()
    res = re.search(r"\b(\d+(?:K|p))\b", d)
    days = re.search(r"(\d+)-day", dl)
    out = {"status": None, "count": None, "duration_days": int(days.group(1)) if days else None,
           "max_resolution": res.group(1) if res else None, "detail": d}
    gens = re.search(r"([\d,]+)\s+free gens?\b", dl)
    if gens:
        out["status"], out["count"] = "free_gens", _int(gens.group(1))
    elif "no unlimited" in dl or "annual plan only" in dl:
        out["status"] = "none"
    elif "unlimited" in dl:
        out["status"] = "unlimited"
    return out


def parse_pricing_md(text: str) -> dict:
    lines = text.splitlines()
    out: dict[str, Any] = {"last_updated": None, "offer_note": None, "offer_ends_at": None,
                           "plans": [], "models": [], "benefits": [], "custom_pricing": []}
    m = re.search(r"^Last updated:\s*(.+)$", text, re.M)
    out["last_updated"] = m.group(1).strip() if m else None
    sec = re.search(r"^## Best prices right now\s*\n+(?!-)(.+)$", text, re.M)
    if sec:
        out["offer_note"] = sec.group(1).strip()
        e = re.search(r"ends (\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)(?: UTC)?", out["offer_note"])
        out["offer_ends_at"] = e.group(1) if e else None
    for m in re.finditer(r"^(\w[\w ]*?): custom pricing", text, re.M):
        out["custom_pricing"].append(_plan_type(m.group(1)))

    for heading, header, rows in _tables(lines):
        ip, im, ia = _col(header, "plan"), _col(header, "monthly"), _col(header, "annual")
        ic = _col(header, "credit")
        imodel = _col(header, "model")
        if ip is not None and im is not None and ia is not None:
            business = "business" in heading.lower() or _col(header, "seat") is not None
            iseat = _col(header, "seats", exclude=("credit", "billing"))
            for r in rows:
                if len(r) < len(header):
                    continue
                base = {"plan_type": _plan_type(r[ip]), "name": r[ip].strip(), "audience":
                        "business" if business else "individual",
                        "credits_per_month": _int(r[ic]) if ic is not None else None,
                        "seats": r[iseat].strip() if iseat is not None else None,
                        "per_seat": business}
                for period, idx in (("monthly", im), ("annual", ia)):
                    prices = parse_price_cell(r[idx], period)
                    out["plans"].append({**base, "billing_period": period, "raw": r[idx].strip(), "prices": prices})
        elif imodel is not None and ic is not None:
            for r in rows:
                if len(r) <= max(imodel, ic):
                    continue
                credits = re.search(r"\d+(?:\.\d+)?", r[ic].replace(",", ""))
                out["models"].append({"name": r[imodel].strip(), "credits": float(credits.group(0)) if credits else None,
                                      "raw": " | ".join(r)})

    # "### Plus, monthly billing" blocks: bullets "- Label (detail): text" under Free generations / Unlimited ...
    current, group = None, None
    for ln in lines:
        s = ln.strip()
        h = re.match(r"^###\s+(.+?),\s*(monthly|annual) billing\s*$", s, re.I)
        if h:
            current = (_plan_type(h.group(1)), h.group(2).lower())
            group = None
            continue
        if s.startswith("## ") or (s.startswith("### ") and not h):
            current = None
            continue
        if current is None:
            continue
        b = re.match(r"^\*\*(.+)\*\*$", s)
        if b:
            group = b.group(1).strip()
            continue
        if group and re.search(r"unlimited|free gen", group, re.I) and s.startswith("- "):
            bm = _BENEFIT_RE.match(s)
            if not bm:
                continue
            det = parse_benefit_detail(bm.group("detail"))
            if det["status"] is None:
                continue
            out["benefits"].append({"plan_type": current[0], "billing_period": current[1], "group": group,
                                    "label": bm.group("label").strip(), **det})
    return out


# ------------------------------------------------------------------ compare
def _dec(v) -> Optional[Decimal]:
    try:
        return Decimal(str(v)) if v is not None else None
    except InvalidOperation:
        return None


def _plan_label(plan_type, period, credits) -> str:
    return f"{plan_type}/{period}/{credits}cr"


def compare_plans(md_plans: list[dict], ds_plans: list[dict]) -> dict:
    idx = {(p["plan_type"], p["billing_period"], p["credits_per_month"]): p for p in ds_plans}
    matches, mismatches, only_md, seen = [], [], [], set()
    for mp in md_plans:
        key = (mp["plan_type"], mp["billing_period"], mp["credits_per_month"])
        label = _plan_label(*key)
        dp = idx.get(key)
        if dp is None:
            only_md.append({"plan": label, "raw": mp["raw"]})
            continue
        seen.add(key)
        if not mp["prices"]:
            mismatches.append({"plan": label, "field": "(unparsed)", "pricing_md": mp["raw"], "dataset": None,
                               "match": False})
            continue
        for field, val in mp["prices"].items():
            stage, part = field.split(".")
            dv = ((dp.get("pricing") or {}).get(stage) or {}).get(part)
            row = {"plan": label, "field": field, "pricing_md": val, "dataset": dv,
                   "match": _dec(val) is not None and _dec(val) == _dec(dv)}
            (matches if row["match"] else mismatches).append(row)
    only_ds = [{"plan": _plan_label(*k), "after_offer_per_month": idx[k]["pricing"]["after_offer"]["per_month"]}
               for k in idx if k not in seen]
    return {"matches": matches, "mismatches": mismatches, "only_in_pricing_md": only_md, "only_in_dataset": only_ds}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def compare_models(md_models: list[dict], ds_models: list[dict]) -> dict:
    """Conservative: exact (case/space-insensitive) display_name match; credits must equal one of the model's
    price-point credit values."""
    by_name: dict[str, list[dict]] = {}
    for m in ds_models:
        by_name.setdefault(_norm(m.get("display_name")), []).append(m)
    matches, mismatches, only_md = [], [], []
    for mm in md_models:
        cands = by_name.get(_norm(mm["name"]), [])
        if len(cands) != 1:
            only_md.append({"name": mm["name"], "credits": mm["credits"], "raw": mm["raw"],
                            "reason": "no dataset model with this name" if not cands else "ambiguous name"})
            continue
        m = cands[0]
        vals = sorted({float(p["credits"]) for p in m.get("price_points") or [] if p.get("credits") is not None})
        row = {"name": mm["name"], "model_id": m["model_id"], "pricing_md": mm["credits"], "dataset": vals,
               "match": mm["credits"] is not None and mm["credits"] in vals}
        (matches if row["match"] else mismatches).append(row)
    return {"matches": matches, "mismatches": mismatches, "only_in_pricing_md": only_md, "only_in_dataset": [],
            "note": None if md_models else "pricing.md lists no per-model credit costs"}


def _ds_benefit_rows(ds: dict) -> dict[tuple, dict]:
    """(plan_type, billing_period, label) -> row view from the dataset's benefit cards (non-campaign cards first)."""
    out: dict[tuple, dict] = {}
    cards = sorted(ds.get("benefit_cards") or [], key=lambda c: c.get("campaign") is not None)
    for c in cards:
        for s in c.get("sections") or []:
            for r in s.get("rows") or []:
                key = (c["plan_type"], c["billing_period"], _norm(r.get("label")))
                if key in out:
                    continue
                e = r.get("entitlement") or {}
                status = "free_gens" if e.get("type") == "free_gens" else "unlimited" if e.get("type") == "unlimited" \
                    else "none" if e.get("type") == "none" else e.get("type")
                out[key] = {"label": r.get("label"), "model_ids": r.get("model_ids") or [], "status": status,
                            "count": e.get("count"), "duration_days": e.get("duration_days"),
                            "max_resolution": (e.get("caps") or {}).get("max_resolution"),
                            "tab": c.get("tab"), "campaign": (c.get("campaign") or {}).get("id")
                            if isinstance(c.get("campaign"), dict) else c.get("campaign")}
    return out


def compare_benefits(md_benefits: list[dict], ds: dict) -> dict:
    rows = _ds_benefit_rows(ds)
    matches, mismatches, only_md = [], [], []
    for b in md_benefits:
        key = (b["plan_type"], b["billing_period"], _norm(b["label"]))
        item = f"{b['plan_type']}/{b['billing_period']} {b['label']}"
        d = rows.get(key)
        if d is None:
            only_md.append({"item": item, "detail": b["detail"]})
            continue
        diffs = {}
        for f in ("status", "count", "duration_days", "max_resolution"):
            if f == "max_resolution" and (b[f] is None or b["status"] == "none"):
                continue                                   # pricing.md omits the resolution when uncapped
            if (f == "count" and b["status"] != "free_gens") or (f == "duration_days" and b["status"] == "none"):
                continue
            if b[f] != d[f]:
                diffs[f] = {"pricing_md": b[f], "dataset": d[f]}
        row = {"item": item, "model_ids": d["model_ids"], "pricing_md": b["detail"],
               "dataset": {k: d[k] for k in ("status", "count", "duration_days", "max_resolution")},
               "match": not diffs, "differences": diffs}
        (matches if row["match"] else mismatches).append(row)
    md_keys = {(b["plan_type"], b["billing_period"], _norm(b["label"])) for b in md_benefits}
    md_plans = {k[:2] for k in md_keys}
    only_ds = [{"item": f"{k[0]}/{k[1]} {v['label']}", "model_ids": v["model_ids"], "status": v["status"]}
               for k, v in rows.items() if k[:2] in md_plans and k not in md_keys]
    return {"matches": matches, "mismatches": mismatches, "only_in_pricing_md": only_md, "only_in_dataset": only_ds}


def crosscheck(parsed: dict, ds: dict, plan_set: str = PLAN_SET) -> dict:
    """Compare parsed pricing.md with a pricing dataset dict. JSON-ready."""
    warnings = []
    meta = ds.get("meta") or {}
    ps = next((p for p in ds.get("plan_sets") or [] if p["plan_set_key"] == plan_set), None)
    if ps is None:
        raise ValueError(f"the run has no {plan_set!r} plan set (pricing.md = US prices = {plan_set}); "
                         f"scrape with --plan-sets us")
    if ps.get("country_code") and ps["country_code"] != "US":
        warnings.append(f"run fetched from country {ps['country_code']}; {plan_set} is the US price list, so plan "
                        f"prices are comparable, but other country-dependent fields may not be")
    plans = compare_plans([p for p in parsed["plans"]], ps.get("plans") or [])
    for t in parsed.get("custom_pricing") or []:
        plans["only_in_pricing_md"].append({"plan": t, "raw": "custom pricing (not compared)"})
    models = compare_models(parsed.get("models") or [], ds.get("models") or [])
    benefits = compare_benefits(parsed.get("benefits") or [], ds) if ds.get("benefit_cards") else \
        {"matches": [], "mismatches": [], "only_in_pricing_md": [], "only_in_dataset": [],
         "note": "run has no benefit cards"}
    if not parsed["plans"]:
        warnings.append("no plan tables found in pricing.md (format changed?)")
    sections = {"plans": plans, "models": models, "benefits": benefits}
    summary = {name: {k: len(v) for k, v in s.items() if isinstance(v, list)} for name, s in sections.items()}
    return {"plan_set_key": plan_set,
            "run": {"run_id": meta.get("run_id"), "scraped_at": meta.get("scraped_at"),
                    "country_code": meta.get("country_code"), "costs_version": meta.get("costs_version")},
            "pricing_md": {"last_updated": parsed.get("last_updated"), "offer_note": parsed.get("offer_note"),
                           "offer_ends_at": parsed.get("offer_ends_at"), "plans_parsed": len(parsed["plans"]),
                           "models_parsed": len(parsed.get("models") or []),
                           "benefit_rows_parsed": len(parsed.get("benefits") or [])},
            "ok": not any(s["mismatches"] for s in sections.values()),
            "mismatch_count": sum(len(s["mismatches"]) for s in sections.values()),
            "warnings": warnings, "summary": summary, **sections}


# ------------------------------------------------------------------ render
def render_console(rep: dict, console=None) -> None:
    from rich.console import Console
    from rich.markup import escape
    from rich.table import Table
    console = console or Console()
    r, md = rep["run"], rep["pricing_md"]
    console.print(f"[bold]pricing.md crosscheck[/] ({md['last_updated']}) vs {r['run_id']} / {rep['plan_set_key']}")
    if md.get("offer_note"):
        console.print(f"offer: {escape(md['offer_note'])}")
    for w in rep["warnings"]:
        console.print(f"[yellow]warning:[/] {escape(w)}")
    t = Table()
    for h in ("section", "match", "mismatch", "only pricing.md", "only dataset"):
        t.add_column(h)
    for name, s in rep["summary"].items():
        t.add_row(name, str(s.get("matches", 0)), str(s.get("mismatches", 0)), str(s.get("only_in_pricing_md", 0)),
                  str(s.get("only_in_dataset", 0)))
    console.print(t)
    if rep["models"].get("note"):
        console.print(f"models: {rep['models']['note']}")
    rows = []
    for name in ("plans", "models", "benefits"):
        s = rep[name]
        for x in s["mismatches"]:
            rows.append((name, "mismatch", x.get("plan") or x.get("name") or x.get("item"), x.get("field") or "",
                         str(x.get("pricing_md")), str(x.get("dataset") if "differences" not in x else x["differences"])))
        for x in s["only_in_pricing_md"]:
            rows.append((name, "only pricing.md", x.get("plan") or x.get("name") or x.get("item"), "",
                         str(x.get("raw") or x.get("detail") or ""), ""))
        for x in s["only_in_dataset"]:
            rows.append((name, "only dataset", x.get("plan") or x.get("name") or x.get("item") or "", "", "",
                         str(x.get("after_offer_per_month") or x.get("status") or "")))
    if rows:
        d = Table(title="differences")
        for h in ("section", "kind", "item", "field", "pricing.md", "dataset"):
            d.add_column(h, overflow="fold")
        for row in rows:
            d.add_row(*(escape(c) for c in row))
        console.print(d)
    console.print("[green]all compared values match[/]" if rep["ok"] else
                  f"[red]{rep['mismatch_count']} mismatch(es)[/]")
