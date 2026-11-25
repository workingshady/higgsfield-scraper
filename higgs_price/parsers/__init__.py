"""Pure functions: raw Envelope -> list of entity dicts (each has a `kind`). No Scrapy imports, fully testable."""
from __future__ import annotations

import logging

from ..raw import Envelope
from ..selection import Selection
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
    return parse_auth_payload(ep, env.status, body, prov)


def keep(entity: dict, sel: Selection) -> bool:
    """Apply user filters (plan types, models, categories) to a parsed entity."""
    kind = entity["kind"]
    if kind in ("plan", "benefit_card", "marketing_plan"):
        return sel.keep_plan_type(entity.get("plan_type"))
    if kind == "model":
        return sel.keep_model(entity["model_id"], entity["family"], entity["display_name"], entity["category"])
    return True


__all__ = ["parse_envelope", "keep"]
