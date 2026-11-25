"""Endpoint registry and enumerations discovered while reverse-engineering https://higgsfield.ai/pricing.

See docs/REVERSE_ENGINEERING.md and docs/ENDPOINTS.md for the full write-up.
"""
from __future__ import annotations

SOURCE_PAGE = "https://higgsfield.ai/pricing"
API_BASE = "https://fnf-api-gw.higgsfield.ai/fnf"
PRICING_CONFIG_URL = "https://pricing.higgsfield.ai/v2/pricing-config"

# endpoint key -> (url, needs_auth)
ENDPOINTS: dict[str, tuple[str, bool]] = {
    "plans": (f"{API_BASE}/subscriptions/v2/plans", False),
    "compare": (f"{API_BASE}/subscriptions/v2/compare", False),
    "plan_benefits": (f"{API_BASE}/subscriptions/v2/plan-benefits", False),
    "job_costs": (f"{API_BASE}/job-sets/costs", False),
    "pricing_config": (PRICING_CONFIG_URL, False),
    # login-only (Clerk session JWT as Bearer token)
    "credit_packages": (f"{API_BASE}/subscriptions/v2/packages", True),
    "unlim_catalog": (f"{API_BASE}/subscriptions/bundle/unlim-catalog", True),
    "credit_price": (f"{API_BASE}/workspaces/credit-price", True),
    "adjustable_credits": (f"{API_BASE}/subscriptions/v2/adjustable-credits", True),
}
AUTH_ENDPOINTS = [k for k, (_, auth) in ENDPOINTS.items() if auth]

# Sections the CLI can scrape -> endpoints they hit
SECTIONS: dict[str, list[str]] = {
    "plans": ["plans"],
    "compare": ["compare"],
    "benefits": ["plan_benefits"],
    "models": ["job_costs"],
    "marketing": ["pricing_config"],
    "auth": AUTH_ENDPOINTS,
}
DEFAULT_SECTIONS = ["plans", "compare", "benefits", "models", "marketing"]

# Every plan_set_key the API accepts (from its 422 validation error, 2026-11-25).
PLAN_SET_KEYS = [
    "mcp", "default", "default_basic", "default_q", "default_ww", "default_ww_q",
    "max_v1", "max_v1_q", "max_v1_seedance_2_5", "max_v1_ultra",
    "max_v2", "max_v2_seedance_2_5", "max_v2_q", "max_v2_ultra", "max_v3",
    "ps_a1", "ps_a2", "ps_a3", "ps_a3_basic", "ps_a3_q", "ps_a4", "ps_a5", "ps_a6", "ps_a7",
    "mob_v1",
]
# How the frontend picks a plan set (JS: w_={T1:"ps_a3",T2:"default",T3:"max_v1"}, mobile -> "max_v2").
PLAN_SET_TIERS = {"T1": "ps_a3", "T2": "default", "T3": "max_v1", "mobile": "max_v2"}
# ps_a3 matches the US prices published at https://higgsfield.ai/pricing.md
US_PLAN_SET = "ps_a3"
PLAN_SET_PRESETS = {
    "us": [US_PLAN_SET],
    "tiers": ["ps_a3", "default", "max_v1", "max_v2"],
    "all": PLAN_SET_KEYS,
}

BILLING_PERIODS = ["monthly", "annual", "quarterly"]
BILLING_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}
BUSINESS_PLAN_TYPES = {"team", "scale", "enterprise"}

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://higgsfield.ai",
    "Referer": SOURCE_PAGE,
}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
