"""Compare two pricing runs' `output/dataset.json` (`python -m higgsfield_scraper diff`).

The comparison itself is pure: `diff_datasets(old, new, ...)` takes two dataset dicts and returns a JSON-ready dict.
Run lookup (`runs/index.jsonl` + manifests) and rendering (Rich table / Markdown) are separate helpers.

Matching keys
  plans       (plan_set_key, plan_type, billing_period) + credits_per_month; when the credits of a plan change, the
              leftover plans of the same group are paired in credit order (equal counts only) -> `credit_changes`.
  models      model_id; price points by (component, dimensions, unit).
  benefits    benefit cards by (plan_type, billing_period, tab, campaign id).
Money is compared as Decimal and serialized as strings; credits are numbers.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

CATEGORIES = ("plans", "models", "benefits", "offers")
SECTION_OF = {"plans": "plans", "offers": "plans", "models": "models", "benefits": "benefits"}
PRICE_FIELDS = [(stage, part) for stage in ("before_offer", "after_offer", "renewal") for part in ("per_month", "total")]
DISCOUNT_FIELDS = ("percent_off", "duration", "duration_months", "applies_to")
SELECTION_KEYS = ("plan_set_keys", "billing_periods", "plan_types", "models", "categories", "include_hidden_plans")


# ------------------------------------------------------------------ helpers
def _dec(v: Any) -> Optional[Decimal]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _num_out(v: Optional[Decimal], like: Any) -> Any:
    """Serialize like the source value: money strings stay strings, credits stay numbers."""
    if v is None:
        return None
    if isinstance(like, str):
        return str(v)
    f = float(v)
    return int(f) if f.is_integer() else round(f, 6)


def change(old: Any, new: Any) -> dict:
    """{old, new, abs_change, pct_change}; pct_change is None when old is 0/missing."""
    o, n = _dec(old), _dec(new)
    out = {"old": old, "new": new, "abs_change": None, "pct_change": None}
    if o is not None and n is not None:
        out["abs_change"] = _num_out(n - o, old if isinstance(old, str) else new)
        if o != 0:
            out["pct_change"] = round(float((n - o) / abs(o) * 100), 2)
    return out


def _passes(ch: dict, min_change: float) -> bool:
    if not min_change:
        return True
    return ch["pct_change"] is None or abs(ch["pct_change"]) >= min_change


def _dims(d: dict) -> str:
    return " ".join(f"{k}={v}" for k, v in sorted((d or {}).items()))


def _dict_changes(old: Any, new: Any) -> list[dict]:
    """Key-level changes between two values (dicts are compared key by key, anything else as a whole)."""
    if old == new:
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        return [{"field": k, "old": old.get(k), "new": new.get(k)}
                for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
    return [{"field": None, "old": old, "new": new}]


def dataset_info(ds: dict, run: Optional[str] = None) -> dict:
    meta = ds.get("meta") or {}
    countries = sorted({ps.get("country_code") for ps in ds.get("plan_sets") or [] if ps.get("country_code")})
    return {"run_id": meta.get("run_id") or run, "path": run, "scraped_at": meta.get("scraped_at"),
            "country_code": meta.get("country_code"), "plan_set_countries": countries,
            "costs_version": meta.get("costs_version"), "plan_set_keys": meta.get("plan_set_keys") or [],
            "sections": meta.get("sections") or []}


# ------------------------------------------------------------------ plans
def _plan_label(p: dict) -> str:
    return f"{p['plan_set_key']}/{p['plan_type']}/{p['billing_period']}/{p['credits_per_month']}cr"


def _plan_summary(p: dict) -> dict:
    pr = p.get("pricing") or {}
    return {"plan": _plan_label(p), "plan_set_key": p["plan_set_key"], "plan_type": p["plan_type"],
            "billing_period": p["billing_period"], "credits_per_month": p.get("credits_per_month"),
            "seats": p.get("seats"),
            "before_offer_per_month": (pr.get("before_offer") or {}).get("per_month"),
            "after_offer_per_month": (pr.get("after_offer") or {}).get("per_month"),
            "renewal_per_month": (pr.get("renewal") or {}).get("per_month")}


def _plans(ds: dict, plan_sets: Optional[set]) -> list[dict]:
    return [p for ps in ds.get("plan_sets") or [] for p in ps.get("plans") or []
            if plan_sets is None or p["plan_set_key"] in plan_sets]


def match_plans(old: list[dict], new: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """-> (pairs, removed, added). Exact credit match first, then same-size leftovers paired in credit order."""
    def groups(plans):
        g: dict[tuple, list[dict]] = {}
        for p in plans:
            g.setdefault((p["plan_set_key"], p["plan_type"], p["billing_period"]), []).append(p)
        return g
    go, gn = groups(old), groups(new)
    pairs, removed, added = [], [], []
    for key in sorted(set(go) | set(gn)):
        o = sorted(go.get(key, []), key=lambda p: p.get("credits_per_month") or 0)
        n = sorted(gn.get(key, []), key=lambda p: p.get("credits_per_month") or 0)
        n_left = list(n)
        o_left = []
        for p in o:
            hit = next((q for q in n_left if q.get("credits_per_month") == p.get("credits_per_month")), None)
            if hit is not None:
                pairs.append((p, hit))
                n_left.remove(hit)
            else:
                o_left.append(p)
        if o_left and len(o_left) == len(n_left):
            pairs.extend(zip(o_left, n_left))
            o_left, n_left = [], []
        removed.extend(o_left)
        added.extend(n_left)
    return pairs, removed, added


def diff_plans(old: list[dict], new: list[dict], min_change: float = 0.0) -> dict:
    pairs, removed, added = match_plans(old, new)
    price, credits, other = [], [], []
    for o, n in pairs:
        ident = {"plan": _plan_label(n), "plan_set_key": n["plan_set_key"], "plan_type": n["plan_type"],
                 "billing_period": n["billing_period"], "credits_per_month": n.get("credits_per_month")}
        for stage, part in PRICE_FIELDS:
            ov = ((o.get("pricing") or {}).get(stage) or {}).get(part)
            nv = ((n.get("pricing") or {}).get(stage) or {}).get(part)
            if _dec(ov) != _dec(nv):
                ch = change(ov, nv)
                if _passes(ch, min_change):
                    price.append({**ident, "field": f"{stage}.{part}", **ch})
        if o.get("credits_per_month") != n.get("credits_per_month"):
            credits.append({**ident, "plan": _plan_label(o) + " -> " + str(n.get("credits_per_month")) + "cr",
                            "field": "credits_per_month", **change(o.get("credits_per_month"), n.get("credits_per_month"))})
        for f in ("seats", "name", "currency"):
            if f in o and f in n and o[f] != n[f]:
                other.append({**ident, "field": f, "old": o.get(f), "new": n.get(f)})
    return {"added": [_plan_summary(p) for p in added], "removed": [_plan_summary(p) for p in removed],
            "price_changes": price, "credit_changes": credits, "other_changes": other}


def diff_offers(old_ds: dict, new_ds: dict, plan_sets: Optional[set]) -> dict:
    """Plan-set `special_offer`, per-plan `discount` (percent_off/duration/applies_to) and raw `offer` objects,
    plus benefit-card campaigns (their `ends_at`)."""
    special = []
    o_sets = {ps["plan_set_key"]: ps for ps in old_ds.get("plan_sets") or []}
    n_sets = {ps["plan_set_key"]: ps for ps in new_ds.get("plan_sets") or []}
    for key in sorted(set(o_sets) & set(n_sets)):
        if plan_sets is not None and key not in plan_sets:
            continue
        for c in _dict_changes(o_sets[key].get("special_offer"), n_sets[key].get("special_offer")):
            special.append({"plan_set_key": key, **c})
    pairs, _, _ = match_plans(_plans(old_ds, plan_sets), _plans(new_ds, plan_sets))
    discounts, offers = [], []
    for o, n in pairs:
        ident = {"plan": _plan_label(n), "plan_set_key": n["plan_set_key"], "plan_type": n["plan_type"],
                 "billing_period": n["billing_period"]}
        od, nd = o.get("discount"), n.get("discount")
        if od != nd:
            if od is None or nd is None:
                discounts.append({**ident, "field": "discount", "old": od, "new": nd})
            else:
                for f in DISCOUNT_FIELDS:
                    if od.get(f) != nd.get(f):
                        discounts.append({**ident, "field": f, "old": od.get(f), "new": nd.get(f)})
        for c in _dict_changes(o.get("offer"), n.get("offer")):
            offers.append({**ident, **c})
    campaigns = []
    oc, nc = _cards(old_ds), _cards(new_ds)
    for key in sorted(set(oc) & set(nc)):
        for c in _dict_changes(oc[key].get("campaign"), nc[key].get("campaign")):
            campaigns.append({"card": "/".join(str(x) for x in key[:3]), **c})
    return {"special_offer_changes": special, "discount_changes": discounts, "offer_changes": offers,
            "campaign_changes": campaigns}


# ------------------------------------------------------------------ models
def _point_key(p: dict) -> tuple:
    return (p.get("component") or "", _dims(p.get("dimensions")), p.get("unit") or "")


def diff_models(old: list[dict], new: list[dict], min_change: float = 0.0) -> dict:
    om, nm = {m["model_id"]: m for m in old}, {m["model_id"]: m for m in new}
    summary = lambda m: {"model_id": m["model_id"], "display_name": m.get("display_name"),  # noqa: E731
                         "category": m.get("category"), "price_point_count": m.get("price_point_count")}
    credit, pts_added, pts_removed, options, other = [], [], [], [], []
    for mid in sorted(set(om) & set(nm)):
        o, n = om[mid], nm[mid]
        op = {_point_key(p): p for p in o.get("price_points") or []}
        np_ = {_point_key(p): p for p in n.get("price_points") or []}
        for k in sorted(set(op) & set(np_)):
            for f in ("credits", "original_credits"):
                ov, nv = op[k].get(f), np_[k].get(f)
                if _dec(ov) != _dec(nv):
                    ch = change(ov, nv)
                    if _passes(ch, min_change):
                        credit.append({"model_id": mid, "display_name": n.get("display_name"), "component": k[0] or None,
                                       "dimensions": np_[k].get("dimensions") or {}, "unit": k[2], "field": f, **ch})
        for k in sorted(set(np_) - set(op)):
            p = np_[k]
            pts_added.append({"model_id": mid, "component": k[0] or None, "dimensions": p.get("dimensions") or {},
                              "unit": k[2], "credits": p.get("credits")})
        for k in sorted(set(op) - set(np_)):
            p = op[k]
            pts_removed.append({"model_id": mid, "component": k[0] or None, "dimensions": p.get("dimensions") or {},
                                "unit": k[2], "credits": p.get("credits")})
        oo, no = o.get("options") or {}, n.get("options") or {}
        for name in sorted(set(oo) | set(no)):
            ov, nv = [str(x) for x in oo.get(name) or []], [str(x) for x in no.get(name) or []]
            add, rem = [x for x in nv if x not in ov], [x for x in ov if x not in nv]
            if add or rem or (name in oo) != (name in no):
                options.append({"model_id": mid, "option": name, "added": add, "removed": rem,
                                "option_added": name not in oo, "option_removed": name not in no})
        for f in ("display_name", "category", "has_cost_data"):
            if f in o and f in n and o[f] != n[f]:            # fields added by a newer schema are not changes
                other.append({"model_id": mid, "field": f, "old": o.get(f), "new": n.get(f)})
    return {"added": [summary(nm[k]) for k in sorted(set(nm) - set(om))],
            "removed": [summary(om[k]) for k in sorted(set(om) - set(nm))],
            "credit_changes": credit, "points_added": pts_added, "points_removed": pts_removed,
            "option_changes": options, "other_changes": other}


# ------------------------------------------------------------------ benefits
def _cards(ds: dict) -> dict[tuple, dict]:
    out = {}
    for c in ds.get("benefit_cards") or []:
        camp = (c.get("campaign") or {}).get("id") if isinstance(c.get("campaign"), dict) else c.get("campaign")
        out[(c.get("plan_type"), c.get("billing_period"), c.get("tab"), camp)] = c
    return out


def _card_label(key: tuple) -> str:
    return "/".join(str(x) for x in key[:3]) + (f"[{key[3]}]" if key[3] else "")


def diff_benefits(old_ds: dict, new_ds: dict) -> dict:
    oc, nc = _cards(old_ds), _cards(new_ds)
    unlimited, free = [], []
    for key in sorted(set(oc) & set(nc), key=str):
        o, n = oc[key], nc[key]
        ou, nu = o.get("unlimited_model_ids") or [], n.get("unlimited_model_ids") or []
        add, rem = [m for m in nu if m not in ou], [m for m in ou if m not in nu]
        if add or rem:
            unlimited.append({"card": _card_label(key), "plan_type": key[0], "billing_period": key[1], "tab": key[2],
                              "added": add, "removed": rem})
        og = {g["model_id"]: g for g in o.get("free_gens") or []}
        ng = {g["model_id"]: g for g in n.get("free_gens") or []}
        for mid in sorted(set(og) | set(ng)):
            a, b = og.get(mid) or {}, ng.get(mid) or {}
            if (a.get("count"), a.get("max_resolution")) != (b.get("count"), b.get("max_resolution")):
                free.append({"card": _card_label(key), "plan_type": key[0], "billing_period": key[1], "tab": key[2],
                             "model_id": mid, "label": b.get("label") or a.get("label"),
                             "status": "added" if not a else "removed" if not b else "changed",
                             "old_count": a.get("count"), "new_count": b.get("count"),
                             "old_max_resolution": a.get("max_resolution"),
                             "new_max_resolution": b.get("max_resolution")})
    lab = lambda keys, src: [{"card": _card_label(k), "unlimited_model_ids": src[k].get("unlimited_model_ids") or [],  # noqa: E731
                              "free_gens": [f"{g['model_id']}x{g.get('count')}" for g in src[k].get("free_gens") or []]}
                             for k in sorted(keys, key=str)]
    return {"cards_added": lab(set(nc) - set(oc), nc), "cards_removed": lab(set(oc) - set(nc), oc),
            "unlimited_changes": unlimited, "free_gen_changes": free}


# ------------------------------------------------------------------ top level
def selection_warnings(old_sel: Optional[dict], new_sel: Optional[dict]) -> list[str]:
    if not old_sel or not new_sel:
        return []
    out = []
    for k in SELECTION_KEYS:
        a, b = old_sel.get(k), new_sel.get(k)
        if a is None or b is None:          # older manifests lack some keys: unknown, not different
            continue
        if isinstance(a, list) and isinstance(b, list):
            a, b = sorted(map(str, a)), sorted(map(str, b))
        if a != b:
            out.append(f"selection differs: {k} {_short(a)} -> {_short(b)}")
    return out


def _short(v: Any, n: int = 6) -> str:
    if isinstance(v, (list, set, tuple)):
        v = sorted(map(str, v))
        return "[" + ", ".join(v) + "]" if len(v) <= n else f"[{', '.join(v[:3])}, … ({len(v)} keys)]"
    return str(v)


def _count(d: dict) -> int:
    return sum(len(v) for v in d.values() if isinstance(v, list))


def diff_datasets(old: dict, new: dict, *, only: Optional[Iterable[str]] = None, min_change: float = 0.0,
                  old_run: Optional[str] = None, new_run: Optional[str] = None,
                  old_selection: Optional[dict] = None, new_selection: Optional[dict] = None) -> dict:
    """Pure diff of two pricing dataset dicts (as loaded from output/dataset.json)."""
    only = list(only) if only else list(CATEGORIES)
    bad = [c for c in only if c not in CATEGORIES]
    if bad:
        raise ValueError(f"--only: unknown categor{'y' if len(bad) == 1 else 'ies'} {', '.join(bad)} "
                         f"(choose from {', '.join(CATEGORIES)})")
    oi, ni = dataset_info(old, old_run), dataset_info(new, new_run)
    warnings = [w for w in selection_warnings(old_selection, new_selection) if "plan_set_keys" not in w]
    for ds, info in ((old, oi), (new, ni)):
        scr = (ds.get("meta") or {}).get("scraper")
        if scr not in (None, "pricing"):
            raise ValueError(f"run {info['run_id']} is a {scr!r} run, not a pricing run")

    o_keys, n_keys = set(oi["plan_set_keys"]), set(ni["plan_set_keys"])
    plan_sets = None
    if o_keys != n_keys:
        plan_sets = o_keys & n_keys
        warnings.append(f"plan sets differ ({_short(o_keys)} vs {_short(n_keys)}); plans and offers compared only "
                        f"for {_short(plan_sets) if plan_sets else 'none'}")

    meta = {"costs_version": {"old": oi["costs_version"], "new": ni["costs_version"],
                              "changed": oi["costs_version"] != ni["costs_version"]},
            "country_code": {"old": oi["country_code"], "new": ni["country_code"],
                             "changed": oi["country_code"] != ni["country_code"]}}
    if meta["country_code"]["changed"]:
        warnings.append(f"country differs ({oi['country_code']} vs {ni['country_code']}): prices come from the "
                        f"requester's IP and are not comparable")
    o_sets = {ps["plan_set_key"]: ps.get("country_code") for ps in old.get("plan_sets") or []}
    n_sets = {ps["plan_set_key"]: ps.get("country_code") for ps in new.get("plan_sets") or []}
    for k in sorted(set(o_sets) & set(n_sets)):
        if o_sets[k] != n_sets[k] and not meta["country_code"]["changed"]:
            warnings.append(f"plan set {k}: country differs ({o_sets[k]} vs {n_sets[k]}): prices are not comparable")

    out: dict[str, Any] = {"old": oi, "new": ni, "changed": False, "only": only, "min_change_pct": min_change,
                           "warnings": warnings, "meta": meta}
    o_sec, n_sec = set(oi["sections"]), set(ni["sections"])
    for cat in only:
        sec = SECTION_OF[cat]
        if (o_sec and sec not in o_sec) or (n_sec and sec not in n_sec):
            warnings.append(f"{cat}: section {sec!r} missing from one run; skipped")
            out[cat] = None
            continue
        if cat == "plans":
            out[cat] = diff_plans(_plans(old, plan_sets), _plans(new, plan_sets), min_change)
        elif cat == "offers":
            out[cat] = diff_offers(old, new, plan_sets)
        elif cat == "models":
            out[cat] = diff_models(old.get("models") or [], new.get("models") or [], min_change)
        elif cat == "benefits":
            out[cat] = diff_benefits(old, new)
    out["summary"] = {f"{cat}.{k}": len(v) for cat in only if out.get(cat) for k, v in out[cat].items()
                      if isinstance(v, list) and v}
    out["changed"] = bool(out["summary"]) or meta["costs_version"]["changed"] or meta["country_code"]["changed"]
    return out


# ------------------------------------------------------------------ run lookup (I/O)
def _read_json(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pricing_runs(runs_dir: str | Path) -> list[Path]:
    """Successful pricing runs that have output/dataset.json, oldest first (runs/index.jsonl, then folder scan)."""
    from .run.context import normalize_status, read_manifest
    root = Path(runs_dir)
    names: list[str] = []
    idx = root / "index.jsonl"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if normalize_status(r.get("status")) == "success" and r.get("scraper") in (None, "pricing") \
                    and r.get("run_id"):
                names.append(r["run_id"])
    if not names and root.exists():
        names = sorted(d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
    out, seen = [], set()
    for name in names:
        d = root / name
        if name in seen or not (d / "output" / "dataset.json").exists():
            continue
        m = read_manifest(d)
        if m and (m.get("status") != "success" or m.get("scraper") not in (None, "pricing")):
            continue
        seen.add(name)
        out.append(d)
    return sorted(out, key=lambda d: d.name)


def resolve_run(value: str, runs_dir: str | Path) -> Path:
    p = Path(value)
    for cand in (p, Path(runs_dir) / value):
        if (cand / "output" / "dataset.json").exists():
            return cand
    raise FileNotFoundError(f"no output/dataset.json in {value!r} (or {Path(runs_dir) / value})")


def run_selection(run_dir: Path) -> dict:
    from .run.context import read_manifest
    m = read_manifest(run_dir)
    sel = dict(m.get("selection") or {})
    if not sel:
        meta = (_read_json(run_dir / "output" / "dataset.json") or {}).get("meta") or {}
        sel = {"plan_set_keys": meta.get("plan_set_keys") or [], "sections": meta.get("sections") or []}
    return sel


def compatible(old_sel: dict, new_sel: dict) -> bool:
    """Same plan sets/billing/filters/hidden-plans flag, and the old run has every compared section the new one has."""
    if selection_warnings(old_sel, new_sel):
        return False
    wanted = {"plans", "models", "benefits"} & set(new_sel.get("sections") or [])
    return wanted <= set(old_sel.get("sections") or wanted)


def resolve_pair(runs_dir: str | Path, old: Optional[str], new: Optional[str]) -> tuple[Path, Path]:
    runs = pricing_runs(runs_dir)
    new_dir = resolve_run(new, runs_dir) if new else (runs[-1] if runs else None)
    if new_dir is None:
        raise FileNotFoundError(f"no successful pricing run with output/dataset.json in {runs_dir}")
    if old:
        return resolve_run(old, runs_dir), new_dir
    new_sel = run_selection(new_dir)
    for d in reversed(runs):
        if d.name < new_dir.name and compatible(run_selection(d), new_sel):
            return d, new_dir
    raise FileNotFoundError(f"no earlier successful pricing run with a compatible selection "
                            f"(plan sets {new_sel.get('plan_set_keys')}) before {new_dir.name}; pass --old")


# ------------------------------------------------------------------ rendering
def _fmt_pct(p: Optional[float]) -> str:
    return "" if p is None else f"{p:+.2f}%"


def _rows(diff: dict) -> list[tuple[str, str, str, str, str, str]]:
    """(category, kind, item, old, new, change) rows for the console/Markdown table."""
    rows = []
    m = diff["meta"]
    for k in ("costs_version", "country_code"):
        if m[k]["changed"]:
            rows.append(("meta", k, "", str(m[k]["old"])[:16], str(m[k]["new"])[:16], ""))
    p = diff.get("plans") or {}
    for x in p.get("added", []):
        rows.append(("plans", "added", x["plan"], "", f"${x['after_offer_per_month']}/mo", ""))
    for x in p.get("removed", []):
        rows.append(("plans", "removed", x["plan"], f"${x['after_offer_per_month']}/mo", "", ""))
    for x in p.get("price_changes", []):
        rows.append(("plans", x["field"], x["plan"], f"${x['old']}", f"${x['new']}",
                     f"{x['abs_change']} ({_fmt_pct(x['pct_change'])})"))
    for x in p.get("credit_changes", []) + p.get("other_changes", []):
        rows.append(("plans", x["field"], x["plan"], str(x["old"]), str(x["new"]), _fmt_pct(x.get("pct_change"))))
    o = diff.get("offers") or {}
    for x in o.get("special_offer_changes", []):
        rows.append(("offers", "special_offer" + (f".{x['field']}" if x["field"] else ""), x["plan_set_key"],
                     json.dumps(x["old"]), json.dumps(x["new"]), ""))
    for x in o.get("discount_changes", []) + o.get("offer_changes", []):
        rows.append(("offers", str(x["field"]), x["plan"], json.dumps(x["old"]), json.dumps(x["new"]), ""))
    for x in o.get("campaign_changes", []):
        rows.append(("offers", f"campaign.{x['field']}", x["card"], json.dumps(x["old"]), json.dumps(x["new"]), ""))
    md = diff.get("models") or {}
    for x in md.get("added", []):
        rows.append(("models", "added", x["model_id"], "", f"{x['price_point_count']} points", ""))
    for x in md.get("removed", []):
        rows.append(("models", "removed", x["model_id"], f"{x['price_point_count']} points", "", ""))
    for x in md.get("credit_changes", []):
        item = f"{x['model_id']} {(x['component'] + ' ') if x['component'] else ''}{_dims(x['dimensions'])}".strip()
        rows.append(("models", x["field"], item, str(x["old"]), str(x["new"]),
                     f"{x['abs_change']} ({_fmt_pct(x['pct_change'])})"))
    for kind in ("points_added", "points_removed"):
        for x in md.get(kind, []):
            item = f"{x['model_id']} {(x['component'] + ' ') if x['component'] else ''}{_dims(x['dimensions'])}".strip()
            rows.append(("models", kind.replace("_", " "), item, "" if kind == "points_added" else str(x["credits"]),
                         str(x["credits"]) if kind == "points_added" else "", ""))
    for x in md.get("option_changes", []):
        rows.append(("models", "options", f"{x['model_id']}.{x['option']}", ",".join(x["removed"]),
                     ",".join(x["added"]), ""))
    for x in md.get("other_changes", []):
        rows.append(("models", x["field"], x["model_id"], str(x["old"]), str(x["new"]), ""))
    b = diff.get("benefits") or {}
    for kind in ("cards_added", "cards_removed"):
        for x in b.get(kind, []):
            rows.append(("benefits", kind.replace("_", " "), x["card"], "", ",".join(x["unlimited_model_ids"]), ""))
    for x in b.get("unlimited_changes", []):
        rows.append(("benefits", "unlimited", x["card"], ",".join(x["removed"]) and "-" + ",-".join(x["removed"]),
                     ",".join(x["added"]) and "+" + ",+".join(x["added"]), ""))
    for x in b.get("free_gen_changes", []):
        rows.append(("benefits", f"free gens ({x['status']})", f"{x['card']} {x['model_id']}",
                     str(x["old_count"] or ""), str(x["new_count"] or ""), ""))
    return rows


def render_console(diff: dict, console=None, max_rows: int = 200) -> None:
    from rich.console import Console
    from rich.markup import escape
    from rich.table import Table
    console = console or Console()
    o, n = diff["old"], diff["new"]
    console.print(f"[bold]pricing diff[/] {escape(str(o['run_id']))} -> {escape(str(n['run_id']))}")
    for w in diff["warnings"]:
        console.print(f"[yellow]warning:[/] {escape(w)}")
    rows = _rows(diff)
    if not rows:
        console.print("[green]no changes[/]")
        return
    t = Table(show_lines=False)
    for h in ("category", "change", "item", "old", "new", "Δ"):
        t.add_column(h, overflow="fold")
    for r in rows[:max_rows]:
        t.add_row(*(escape(c) for c in r))
    console.print(t)
    if len(rows) > max_rows:
        console.print(f"… {len(rows) - max_rows} more rows (use --json or --out)")
    console.print("summary: " + ", ".join(f"{k}={v}" for k, v in diff["summary"].items()))


def render_markdown(diff: dict) -> str:
    o, n = diff["old"], diff["new"]
    lines = [f"# Pricing diff: {o['run_id']} -> {n['run_id']}", "",
             f"- old: `{o['run_id']}` ({o['scraped_at']}, country {o['country_code']}, costs `{str(o['costs_version'])[:12]}`)",
             f"- new: `{n['run_id']}` ({n['scraped_at']}, country {n['country_code']}, costs `{str(n['costs_version'])[:12]}`)",
             f"- changed: **{str(diff['changed']).lower()}**", ""]
    if diff["warnings"]:
        lines += ["## Warnings", ""] + [f"- {w}" for w in diff["warnings"]] + [""]
    if diff["summary"]:
        lines += ["## Summary", "", "| change | count |", "| --- | --- |"]
        lines += [f"| {k} | {v} |" for k, v in diff["summary"].items()] + [""]
    rows = _rows(diff)
    lines += ["## Changes", ""]
    if not rows:
        lines += ["No changes.", ""]
    else:
        esc = lambda s: str(s).replace("|", "\\|")  # noqa: E731
        lines += ["| category | change | item | old | new | Δ |", "| --- | --- | --- | --- | --- | --- |"]
        lines += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows] + [""]
    return "\n".join(lines)
