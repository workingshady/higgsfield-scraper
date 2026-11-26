"""Pure functions: raw Envelope -> list of entity dicts (each has a `kind`). No Scrapy imports, fully testable."""
from __future__ import annotations

import logging

from ..constants import ACCOUNT_ENDPOINTS, LOGGED_IN_PRICE_ENDPOINTS
from ..raw import Envelope
from ..selection import Selection
from .account import parse_account
from .auth import parse_auth_payload, parse_credit_packages
from .benefits import parse_plan_benefits
from .compare import parse_compare
from .costs import parse_job_costs
from .marketing import parse_pricing_config
from .plans import parse_plans

log = logging.getLogger(__name__)


def parse_envelope(env: Envelope, sel: Selection) -> list[dict]:
    if not env.ok:
        if env.endpoint in ("unlim_catalog", "credit_price", "adjustable_credits", "credit_packages"):
            return []
        if env.endpoint in LOGGED_IN_PRICE_ENDPOINTS or env.endpoint in ACCOUNT_ENDPOINTS:
            return []                                   # login-only, optional: the spider already warned
        log.warning("skip parse of %s: HTTP %s", env.endpoint, env.status)
        return []
    prov = env.provenance()
    body = env.body
    ep = env.endpoint
    if ep == "plans":
        return parse_plans(body, prov, sel.include_hidden_plans)
    if ep == "compare":
        return parse_compare(body, prov)
    if ep == "plan_benefits":
        return parse_plan_benefits(body, prov)
    if ep == "job_costs":
        return parse_job_costs(body, prov, sel.include_raw_cost)
    if ep == "pricing_config":
        return parse_pricing_config(body, prov, sel.marketing_versions)
    if ep == "credit_packages":
        return parse_credit_packages(body, prov)
    if ep == "plans_logged_in":
        return logged_in_rows(parse_plans(body, prov, sel.include_hidden_plans))
    if ep == "job_costs_logged_in":
        return logged_in_rows(parse_job_costs(body, prov, sel.include_raw_cost))
    if ep in ACCOUNT_ENDPOINTS:
        return parse_account(ep, env.status, body, prov)
    return parse_auth_payload(ep, env.status, body, prov)


def logged_in_rows(entities: list[dict]) -> list[dict]:
    """Entities parsed from a logged-in response: every plan / model is tagged `visibility="logged_in"`; assemble keeps
    only those the anonymous response lacks (anonymous rows always win). The logged-in plan_set row is dropped."""
    out = []
    for e in entities:
        if e["kind"] in ("plan", "model"):
            out.append({**e, "visibility": "logged_in"})
    return out


def keep(entity: dict, sel: Selection) -> bool:
    """Apply user filters (plan types, models, categories) to a parsed entity."""
    kind = entity["kind"]
    if kind in ("plan", "benefit_card", "marketing_plan"):
        return sel.keep_plan_type(entity.get("plan_type"))
    if kind == "model":
        return sel.keep_model(entity["model_id"], entity["family"], entity["display_name"], entity["category"])
    return True


__all__ = ["parse_envelope", "keep", "logged_in_rows"]
