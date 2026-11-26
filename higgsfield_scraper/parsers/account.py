"""Opt-in `--sections account`: the logged-in account's own pricing state, reduced to a privacy WHITELIST.

`sanitize_account_body` keeps only the whitelisted fields of each account endpoint. It runs twice:
  * in `AccountPrivacyMiddleware` (downloader), BEFORE the body reaches the http/ archive, the raw/ archive or the
    spider — so ids, emails, names and Stripe ids are never written anywhere;
  * in `parse_account` again (idempotent), so `normalize` of an old raw/ file can never leak more than the whitelist.

Unit rule (cost units): every wallet balance (`credits_balance`, `subscription_balance`, `total_credits`,
`on_demand_credits`, `bonus_credits`, scoped credit balances) is in cost units = credits x 100 (`888` = 8.88 credits;
same rule as /subscriptions/v2/packages and job `cost`). raw/ keeps the API value; the parsed record holds credits
(`value / 100`) and lists the rule in `conversions`. Every other number is kept exactly as returned.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

from ..schemas.common import make_id

# endpoint -> top-level scalar fields kept (anything else, including every id, is dropped)
ACCOUNT_FIELDS: dict[str, tuple[str, ...]] = {
    "account_wallet": (
        "credits_balance", "subscription_balance", "total_credits", "on_demand_credits", "bonus_credits",
        "bonus_credits_expire_at", "expire_days", "credit_limit", "allocation_cycle", "next_credit_allocation_date",
    ),
    "account_subscription": (
        "plan_name", "plan_type", "status", "billing_cycle", "total_seats", "occupied_seats", "available_seats",
        "seats_capacity", "unlimited_seats", "credits_per_seat", "current_period_start", "current_period_end",
        "cancel_at", "is_pause_scheduled", "is_paused", "payment_status", "downgrades_at", "plan_version",
        "is_gift_subscription", "is_cancellation_requested",
    ),
    "account_auto_top_up": (
        "state", "is_eligible", "is_on_demand_only", "threshold", "credits_per_dollar", "current_refill_amount",
        "on_demand_credits", "currency", "expire_days", "modal_type", "selected_option", "default_option",
    ),
    "account_free_gens": (),
    "account_generation_seconds": (),
    "account_generation_seconds_packs": (),
    "account_bundle_all_unlim_status": ("is_eligible_to_purchase", "has_all_unlims"),
    "account_bundle_seedance_unlimited": (),
}
# endpoint -> list parts kept (items are scrubbed: scalars only, no id / url / personal keys)
ACCOUNT_LISTS: dict[str, tuple[str, ...]] = {
    "account_wallet": ("scoped_credits",),
    "account_auto_top_up": ("options", "refill_options"),
    "account_free_gens": ("items",),
    "account_generation_seconds": ("items",),
    "account_generation_seconds_packs": ("items",),
    "account_bundle_seedance_unlimited": ("tiers",),
}
# fields in cost units (x100) -> converted to credits in the parsed record
COST_UNIT_FIELDS: dict[str, tuple[str, ...]] = {
    "account_wallet": ("credits_balance", "subscription_balance", "total_credits", "on_demand_credits",
                       "bonus_credits"),
}
COST_UNIT_ITEM_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("account_wallet", "scoped_credits"): ("balance", "credits", "credits_balance", "amount"),
}
COST_UNIT_RULE = "credits = api_value / 100 (cost units)"

# keys never kept inside list items, whatever the endpoint returns in the future
_DROP_KEY = re.compile(r"(^id$|_id$|_ids$|^ids$|url|email|avatar|name$|^user|^workspace|stripe|customer|invoice|"
                       r"payment_method|card|token|secret|phone|address|handle|trace)", re.I)
_KEEP_NAME_KEYS = {"plan_name", "model_name", "pack_name", "tier_name", "display_name", "name"}
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")


def _scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _safe_value(v: Any) -> Any:
    if isinstance(v, str) and (_EMAIL.search(v) or v.startswith(("http://", "https://", "//"))):
        return None
    return v


def _scrub_item(item: Any) -> Optional[dict]:
    """List item of unknown shape -> {key: scalar} without ids, urls or personal keys (nested dicts flattened 1 level)."""
    if not isinstance(item, dict):
        return {"value": _safe_value(item)} if _scalar(item) else None
    out: dict[str, Any] = {}
    for k, v in item.items():
        if _DROP_KEY.search(k) and k not in _KEEP_NAME_KEYS:
            continue
        if _scalar(v):
            out[k] = _safe_value(v)
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if _scalar(v2) and not (_DROP_KEY.search(k2) and k2 not in _KEEP_NAME_KEYS):
                    out[f"{k}.{k2}"] = _safe_value(v2)
    return out


def sanitize_account_body(endpoint: str, body: Any) -> Any:
    """Whitelist one account endpoint's JSON body (idempotent). Unknown endpoints / error bodies -> {}."""
    if endpoint not in ACCOUNT_FIELDS or not isinstance(body, dict):
        return {}
    out: dict[str, Any] = {}
    for k in ACCOUNT_FIELDS[endpoint]:
        if k in body:
            v = body[k]
            out[k] = _safe_value(v) if _scalar(v) else _scrub_item(v)   # e.g. selected_option may be an object
    for k in ACCOUNT_LISTS.get(endpoint, ()):
        items = body.get(k)
        if isinstance(items, list):
            out[k] = [x for x in (_scrub_item(i) for i in items) if x is not None]
    return out


def _credits(v: Any) -> Any:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return v
    return float(Decimal(str(v)) / 100)


def parse_account(endpoint: str, status: int, body: Any, provenance: dict) -> list[dict]:
    clean = sanitize_account_body(endpoint, body)
    fields: dict[str, Any] = {}
    conversions: dict[str, str] = {}
    unit_fields = COST_UNIT_FIELDS.get(endpoint, ())
    for k in ACCOUNT_FIELDS.get(endpoint, ()):
        if k not in clean:
            continue
        v = clean[k]
        if isinstance(v, dict):                       # object-valued option -> flattened scalar fields
            for k2, v2 in v.items():
                fields[f"{k}.{k2}"] = v2
            continue
        if k in unit_fields:
            v = _credits(v)
            conversions[k] = COST_UNIT_RULE
        fields[k] = v
    lists: dict[str, list[dict]] = {}
    for part in ACCOUNT_LISTS.get(endpoint, ()):
        rows = clean.get(part)
        if rows is None:
            continue
        keys = COST_UNIT_ITEM_KEYS.get((endpoint, part), ())
        out_rows = []
        for r in rows:
            r = dict(r)
            for k in keys:
                if k in r:
                    r[k] = _credits(r[k])
                    conversions[f"{part}[].{k}"] = COST_UNIT_RULE
            out_rows.append(r)
        lists[part] = out_rows
    return [{"kind": "pricing_account", "record_id": make_id(endpoint), "endpoint": endpoint, "status": status,
             "fields": fields, "lists": lists, "conversions": conversions, "source": provenance}]
