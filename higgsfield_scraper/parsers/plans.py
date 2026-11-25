"""/subscriptions/v2/plans -> PlanSet + Plan entities (prices before/after offer, renewal, discount)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ..constants import BILLING_MONTHS, BUSINESS_PLAN_TYPES
from ..schemas.common import cents_to_money, make_id, percent

HIDDEN_PLAN_TYPES = {"free_trial", "trial", "secret"}  # the site's JS filters these out


def _pair(total_cents, monthly_cents, months: int) -> dict:
    total = cents_to_money(total_cents)
    monthly = cents_to_money(monthly_cents)
    if monthly is None and total is not None:
        monthly = (total / months).quantize(Decimal("0.01"))
    if total is None and monthly is not None:
        total = monthly * months
    return {"total": total, "per_month": monthly}


def _per_credit(total: Optional[Decimal], credits: int) -> Optional[Decimal]:
    if total is None or not credits:
        return None
    return (total / credits).quantize(Decimal("0.0001"))


def _applies_to(d: dict) -> Optional[str]:
    dur = d.get("duration")
    if dur == "once":
        return "first_payment"
    if dur == "forever":
        return "all_payments"
    if dur == "repeating":
        return f"first_{d.get('duration_months')}_months"
    return dur


def build_plan(p: dict, plan_set_key: str, country_code: Optional[str], provenance: dict) -> dict:
    period = p.get("billing_period") or "monthly"
    months = BILLING_MONTHS.get(period, 1)
    credits = int(p.get("credits") or 0)
    before = _pair(p.get("original_price"), p.get("original_monthly_price"), months)
    after = _pair(p.get("final_price"), p.get("final_monthly_price"), months)
    renewal = _pair(p.get("renew_price"), p.get("renew_monthly_price"), months)
    if renewal["total"] is None:
        renewal = dict(after)
    d = p.get("discount")
    plan_type = p.get("plan_type") or "unknown"
    return {
        "kind": "plan",
        "plan_id": make_id(plan_set_key, plan_type, period, credits),
        "plan_uuid": p.get("id"),
        "plan_set_key": plan_set_key,
        "country_code": country_code,
        "plan_type": plan_type,
        "name": p.get("name") or plan_type.title(),
        "audience": "business" if plan_type in BUSINESS_PLAN_TYPES else "individual",
        "billing_period": period,
        "billing_months": months,
        "credits_per_month": credits,
        "credits_per_period": credits * months,
        "seats": p.get("seats"),
        "currency": (p.get("currency") or "usd").upper(),
        "stripe_product_id": p.get("product_id"),
        "stripe_price_id": p.get("price_id"),
        "pricing": {"before_offer": before, "after_offer": after, "renewal": renewal},
        "has_offer": after["total"] < before["total"],
        "discount": None if not d else {
            "percent_off": d.get("percent_off"),
            "duration": d.get("duration"),
            "duration_months": d.get("duration_months"),
            "applies_to": _applies_to(d),
        },
        "savings": {
            "total": before["total"] - after["total"],
            "per_month": before["per_month"] - after["per_month"],
            "percent": float(percent(before["total"], after["total"]) or 0),
        },
        "price_per_credit": {
            "before_offer": _per_credit(before["total"], credits * months),
            "after_offer": _per_credit(after["total"], credits * months),
            "renewal": _per_credit(renewal["total"], credits * months),
        },
        "offer": p.get("offer"),
        "source": provenance,
    }


def parse_plans(body: dict, provenance: dict, include_hidden: bool = False) -> list[dict]:
    plan_set_key = (provenance.get("params") or {}).get("plan_set_key") or "default"
    cc = body.get("country_code")
    plans = [build_plan(p, plan_set_key, cc, provenance) for p in body.get("plans") or []
             if include_hidden or p.get("plan_type") not in HIDDEN_PLAN_TYPES]
    plan_set = {
        "kind": "plan_set",
        "plan_set_key": plan_set_key,
        "country_code": cc,
        "currency": plans[0]["currency"] if plans else None,
        "special_offer": body.get("special_offer"),
        "plan_count": len(plans),
        "plan_types": list(dict.fromkeys(p["plan_type"] for p in plans)),
        "source": provenance,
    }
    return [plan_set, *plans]
