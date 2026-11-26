"""Join validated entities into the nested Dataset (plans <-> benefits <-> models, seats, USD estimates)."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from .constants import ENDPOINTS, LOGGED_IN_PRICE_ENDPOINTS, SOURCE_PAGE
from .parsers.costs import category_of, family_of, humanize
from .schemas import Dataset
from .selection import Selection

log = logging.getLogger(__name__)


def _d(v: Any) -> Optional[Decimal]:
    return None if v is None else Decimal(str(v))


_COMPARE_SKIP = ("source", "visibility", "costs_version")


def _same_row(a: dict, b: dict) -> bool:
    strip = lambda d: {k: v for k, v in d.items() if k not in _COMPARE_SKIP}  # noqa: E731
    return strip(a) == strip(b)


def merge_logged_in(plans: list[dict], models: list[dict], attempted: bool,
                    warnings: list[str]) -> tuple[list[dict], list[dict], Optional[dict]]:
    """Opt-in --logged-in-prices. Rows parsed from the logged-in responses carry `visibility="logged_in"`.
    Anonymous rows are kept exactly as they are (same order, no new key); a logged-in row is added (still tagged) only
    when the anonymous response has no row with the same natural key (plan_id / model_id). Without logged-in rows and
    without the flag this returns the inputs untouched and no meta."""
    anon_p = [p for p in plans if not p.get("visibility")]
    li_p = [p for p in plans if p.get("visibility")]
    anon_m = [m for m in models if not m.get("visibility")]
    li_m = [m for m in models if m.get("visibility")]
    if not (li_p or li_m or attempted):
        return plans, models, None
    differing: list[str] = []

    def extras(anon: list[dict], li: list[dict], key: str, tag: str) -> list[dict]:
        known = {r[key]: r for r in anon}
        out, seen = [], set()
        for r in li:
            k = r[key]
            if k in seen:
                continue
            seen.add(k)
            if k not in known:
                out.append(r)
            elif not _same_row(known[k], r):
                differing.append(f"{tag}:{k}")
        return out

    extra_p = extras(anon_p, li_p, "plan_id", "plan")
    extra_m = extras(anon_m, li_m, "model_id", "model")
    if attempted and not (li_p or li_m):
        warnings.append("--logged-in-prices: no logged-in plans/costs response was parsed (login missing or failed)")
    if differing:
        warnings.append("--logged-in-prices: rows differ between anonymous and logged-in responses (anonymous kept): "
                        + ", ".join(differing))
    meta = {
        "costs_version_anonymous": next((m.get("costs_version") for m in anon_m if m.get("costs_version")), None),
        "costs_version_logged_in": next((m.get("costs_version") for m in li_m if m.get("costs_version")), None),
        "logged_in_only_plan_ids": [p["plan_id"] for p in extra_p],
        "logged_in_only_model_ids": [m["model_id"] for m in extra_m],
        "differing_rows": differing,
    }
    return anon_p + extra_p, anon_m + extra_m, meta


def build_dataset(entities: dict[str, list[dict]], sel: Selection, *, run_id: Optional[str] = None,
                  label: Optional[str] = None, scraped_at: Optional[datetime] = None,
                  warnings: Optional[list[str]] = None) -> dict:
    warnings = list(warnings or [])
    E = {k: [dict(x) for x in v] for k, v in entities.items()}
    for lst in E.values():
        for x in lst:
            x.pop("kind", None)
    plans, cards, models = E.get("plan", []), E.get("benefit_card", []), E.get("model", [])
    comparisons = E.get("comparison", [])
    attempted = any(ep in sel.endpoints() for ep in LOGGED_IN_PRICE_ENDPOINTS)
    plans, models, logged_in_meta = merge_logged_in(plans, models, attempted, warnings)

    # ---- seats from /compare (matched on stripe price id)
    seats = {p["stripe_price_id"]: p["seats"] for c in comparisons for p in c["plans"]
             if p.get("stripe_price_id") and p.get("seats")}
    for p in plans:
        if p.get("seats") is None:
            p["seats"] = seats.get(p.get("stripe_price_id"))

    # ---- plans <- benefit cards
    by_card = defaultdict(list)
    for c in cards:
        by_card[(c["plan_type"], c["billing_period"])].append(c)
    for p in plans:
        cs = by_card.get((p["plan_type"], p["billing_period"]), [])
        p["benefit_card_ids"] = [c["card_id"] for c in cs]
        p["unlimited_model_ids"] = list(dict.fromkeys(m for c in cs for m in c["unlimited_model_ids"]))
        p["free_gens"] = [g for c in cs for g in c["free_gens"]]

    # ---- models <- benefit labels + entitlements
    labels: dict[str, str] = {}
    ents: dict[str, list[dict]] = defaultdict(list)
    for c in cards:
        for s in c["sections"]:
            for r in s["rows"]:
                if len(r["model_ids"]) == 1 and r.get("label"):
                    labels.setdefault(r["model_ids"][0], r["label"])
                e = r["entitlement"]
                if e["type"] not in ("unlimited", "free_gens"):
                    continue
                caps = e.get("caps") or {}
                for m in r["model_ids"]:
                    ents[m].append({
                        "plan_type": c["plan_type"], "billing_period": c["billing_period"], "tab": c.get("tab"),
                        "type": e["type"], "count": e.get("count"), "duration_days": e.get("duration_days"),
                        "max_resolution": caps.get("max_resolution"), "max_duration_s": caps.get("max_duration_s"),
                        "concurrency": caps.get("concurrency"), "starts": e.get("starts"),
                        "requirements": e.get("requirements") or [], "benefit_label": r.get("label"),
                    })
    for m in models:
        if m["model_id"] in labels:
            m["display_name"] = labels[m["model_id"]]
        m["entitlements"] = ents.get(m["model_id"], [])

    # models that only appear in plan benefits (unlimited/free gens) but have no /job-sets/costs entry
    if "models" in sel.sections and cards:
        known = {m["model_id"] for m in models}
        src = cards[0]["source"]
        for mid in sorted(set(ents) - known):
            # NB: not `label` — that is the run label parameter, used for meta.label below.
            benefit_label = labels.get(mid) or next((e["benefit_label"] for e in ents[mid] if e.get("benefit_label")), None)
            name = benefit_label or humanize(mid)
            fam, cat = family_of(mid), category_of(mid, set())
            if not sel.keep_model(mid, fam, name, cat):
                continue
            models.append({
                "model_id": mid, "display_name": name, "family": fam, "category": cat, "units": [], "options": {},
                "components": [], "price_point_count": 0, "has_cost_data": False, "has_discount": False,
                "min_credits": None, "max_credits": None, "price_points": [], "entitlements": ents[mid],
                "costs_version": None, "raw_cost": None, "source": src,
            })
            warnings.append(f"model {mid} ({name}) is in plan benefits but has no cost entry")

    # ---- credit value per plan + USD reference
    credit_values = []
    for p in plans:
        after = _d(p["price_per_credit"]["after_offer"])
        credit_values.append({
            "plan_id": p["plan_id"], "plan_set_key": p["plan_set_key"], "plan_type": p["plan_type"],
            "billing_period": p["billing_period"], "credits_per_month": p["credits_per_month"],
            "usd_per_credit_before_offer": p["price_per_credit"]["before_offer"],
            "usd_per_credit_after_offer": p["price_per_credit"]["after_offer"],
            "credits_per_usd_after_offer": float(round(1 / after, 4)) if after else None,
            **({"visibility": p["visibility"]} if p.get("visibility") else {}),
        })
    usd_ref = None
    ref_type, _, ref_period = sel.usd_reference.partition(":")
    ref_set = sel.plan_set_keys[0] if sel.plan_set_keys else None
    candidates = sorted((p for p in plans if p["plan_type"] == ref_type and p["billing_period"] == (ref_period or "annual")
                         and p["plan_set_key"] == ref_set), key=lambda p: p["credits_per_month"])
    if candidates:
        ref = candidates[0]
        rate = _d(ref["price_per_credit"]["after_offer"])
        usd_ref = {"plan_id": ref["plan_id"], "plan_set_key": ref["plan_set_key"], "plan_type": ref["plan_type"],
                   "billing_period": ref["billing_period"], "credits_per_month": ref["credits_per_month"],
                   "usd_per_credit": str(rate)}
        for m in models:
            for pt in m["price_points"]:
                base = (pt.get("example") or {}).get("credits", pt.get("credits"))
                pt["usd_estimate"] = None if base is None or rate is None else float(round(Decimal(str(base)) * rate, 4))
    elif models and plans:
        warnings.append(f"usd_reference {sel.usd_reference!r} not found in plan set {ref_set}; no USD estimates")

    # ---- plan sets with nested plans
    plan_sets = []
    for ps in E.get("plan_set", []):
        ps = dict(ps)
        ps["plans"] = [p for p in plans if p["plan_set_key"] == ps["plan_set_key"]]
        plan_sets.append(ps)

    marketing = E.get("marketing_plan", [])
    first_ps = E.get("plan_set", [{}])[0] if E.get("plan_set") else {}
    costs_version = models[0].get("costs_version") if models else None
    benefit_badges = next((c.get("tab_badge") for c in cards if c.get("tab_badge")), None)
    out_cards = cards if "benefits" in sel.sections else []
    counts = {
        "plan_sets": len(plan_sets), "plans": len(plans), "models": len(models),
        "price_points": sum(len(m["price_points"]) for m in models),
        "benefit_cards": len(out_cards), "comparisons": len(comparisons), "marketing_plans": len(marketing),
        "credit_packages": len(E.get("credit_package", [])), "auth_payloads": len(E.get("auth_payload", [])),
    }
    account = E.get("pricing_account", [])
    if account:                                         # opt-in --sections account (key absent otherwise)
        counts["account_records"] = len(account)
    doc = {
        "meta": {
            "run_id": run_id, "label": label,
            "scraped_at": (scraped_at or datetime.now(timezone.utc)).isoformat(),
            "source_page": SOURCE_PAGE,
            "country_code": first_ps.get("country_code"),
            "currency": first_ps.get("currency"),
            "locale": sel.locale,
            "sections": sel.sections,
            "plan_set_keys": sel.plan_set_keys,
            "costs_version": costs_version,
            "marketing_versions": sorted({m["config_version"] for m in marketing}),
            "marketing_latest_version": next((m["config_version"] for m in marketing if m["is_latest"]), None),
            "usd_reference": usd_ref,
            "filters": {"plan_types": sel.plan_types, "models": sel.models, "categories": sel.categories},
            "counts": counts,
            "endpoints": {k: ENDPOINTS[k][0] for k in sel.endpoints()},
            "warnings": warnings,
            "logged_in_prices": logged_in_meta,         # None -> left out of the output
        },
        "plan_sets": plan_sets if "plans" in sel.sections else [],
        "credit_values": credit_values if "plans" in sel.sections else [],
        "models": models if "models" in sel.sections else [],
        "benefit_cards": out_cards,
        "tab_badges": benefit_badges and {c["tab"]: c["tab_badge"] for c in cards if c.get("tab") and c.get("tab_badge")},
        "comparisons": comparisons if "compare" in sel.sections else [],
        "marketing": marketing,
        "auth": {"credit_packages": E.get("credit_package", []), "payloads": E.get("auth_payload", [])},
        "account": {"records": account} if account else None,   # None -> left out of the output
    }
    if "plans" not in sel.sections:
        doc["meta"]["counts"].update(plan_sets=0, plans=0)
    if "compare" not in sel.sections:
        doc["meta"]["counts"]["comparisons"] = 0
    return Dataset.model_validate(doc).model_dump(mode="json")
