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
    # opt-in `--logged-in-prices`: the same public price lists fetched WITH a session (they differ: extra plans/models)
    "plans_logged_in": (f"{API_BASE}/subscriptions/v2/plans", True),
    "job_costs_logged_in": (f"{API_BASE}/job-sets/costs", True),
    # opt-in section `account` (the logged-in account's own money state; whitelisted fields only, see parsers/account.py)
    "account_wallet": (f"{API_BASE}/workspaces/wallet", True),
    "account_subscription": (f"{API_BASE}/workspaces/subscription", True),
    "account_auto_top_up": (f"{API_BASE}/v2/auto-top-ups/settings", True),
    "account_free_gens": (f"{API_BASE}/user/free-gens/v2", True),
    "account_generation_seconds": (f"{API_BASE}/user/generation-seconds", True),
    "account_generation_seconds_packs": (f"{API_BASE}/generation-seconds/packs", True),
    "account_bundle_all_unlim_status": (f"{API_BASE}/subscriptions/bundle/all-unlim/status", True),
    "account_bundle_seedance_unlimited": (f"{API_BASE}/subscriptions/bundle/seedance-unlimited", True),
}
# the `auth` section (explicit list: the newer login-only endpoints below are NOT part of it)
AUTH_ENDPOINTS = ["credit_packages", "unlim_catalog", "credit_price", "adjustable_credits"]
# `--logged-in-prices`: logged-in endpoint -> the anonymous endpoint it is merged into
LOGGED_IN_PRICE_ENDPOINTS = {"plans_logged_in": "plans", "job_costs_logged_in": "job_costs"}
ACCOUNT_ENDPOINTS = [k for k in ENDPOINTS if k.startswith("account_")]
LOGIN_ENDPOINTS = [k for k, (_, auth) in ENDPOINTS.items() if auth]      # every endpoint that needs a session

# Sections the CLI can scrape -> endpoints they hit
SECTIONS: dict[str, list[str]] = {
    "plans": ["plans"],
    "compare": ["compare"],
    "benefits": ["plan_benefits"],
    "models": ["job_costs"],
    "marketing": ["pricing_config"],
    "auth": AUTH_ENDPOINTS,
    "account": ACCOUNT_ENDPOINTS,
}
DEFAULT_SECTIONS = ["plans", "compare", "benefits", "models", "marketing"]
# never implied by `all`: only scraped when listed explicitly (`--sections all,account`)
OPT_IN_SECTIONS = ["account"]

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
