"""/subscriptions/v2/compare -> Comparison entity (feature matrix per plan set x billing period)."""
from __future__ import annotations

import re

from ..schemas.common import cents_to_money, make_id

DETAIL_RE = re.compile(r"^\s*(~)?\s*([\d.,]+)\s*credits?\s*/\s*(\S+)\s*$", re.I)
QTY_RE = re.compile(r"^\s*(?:up to\s*)?([\d][\d,.]*)\s*(.*)$", re.I)


def parse_detail(detail: str | None) -> dict:
    m = DETAIL_RE.match(detail or "")
    if not m:
        return {"approx": False, "credits": None, "per": None}
    return {"approx": bool(m.group(1)), "credits": float(m.group(2).replace(",", "")), "per": m.group(3)}


def parse_value(plan_type: str, v: dict) -> dict:
    vtype, raw = (v or {}).get("type"), (v or {}).get("value")
    qty, unit = None, None
    if isinstance(raw, str):
        m = QTY_RE.match(raw)
        if m:
            qty, unit = float(m.group(1).replace(",", "")), (m.group(2) or None)
        else:
            unit = raw
    available = bool(raw) if isinstance(raw, bool) else raw not in (None, "", "0")
    return {"plan_type": plan_type, "value_type": vtype or type(raw).__name__, "raw": raw,
            "available": available, "quantity": qty, "quantity_unit": unit}


def parse_compare(body: dict, provenance: dict) -> list[dict]:
    params = provenance.get("params") or {}
    psk = body.get("plan_set_key") or params.get("plan_set_key") or "default"
    period = params.get("billing_period") or "monthly"
    plans = [{
        "plan_type": p.get("plan_type"),
        "name": p.get("name"),
        "credits": int(p.get("credits") or 0),
        "seats": p.get("seats"),
        "stripe_price_id": p.get("price_id"),
        "price_after_offer_per_month": cents_to_money(p.get("final_monthly_price")),
    } for p in body.get("plans") or [] if p.get("billing_period") == period]
    cats = [{
        "slug": c.get("slug") or "",
        "name": c.get("name") or "",
        "description": c.get("description"),
        "features": [{
            "name": f.get("name") or "",
            "detail": f.get("detail") or None,
            **parse_detail(f.get("detail")),
            "values": [parse_value(pt, v) for pt, v in (f.get("values") or {}).items()],
        } for f in c.get("features") or []],
    } for c in body.get("categories") or []]
    return [{
        "kind": "comparison",
        "comparison_id": make_id(psk, period),
        "plan_set_key": psk,
        "billing_period": period,
        "plans": plans,
        "categories": cats,
        "source": provenance,
    }]


def seats_by_price_id(body: dict) -> dict[str, int]:
    return {p["price_id"]: p["seats"] for p in body.get("plans") or [] if p.get("price_id") and p.get("seats")}
