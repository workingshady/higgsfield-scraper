"""Endpoints of the account scraper (the logged-in user's OWN state). See docs/LOGIN_COVERAGE.md §2.1/§2.4/§3.4.

Base: https://fnf-api-gw.higgsfield.ai/fnf (constants.API_BASE). GET only. Everything except the four public pricing
endpoints is login-only and requested with auth="required".
"""
from __future__ import annotations

# ---- snapshot (login only) -----------------------------------------------------------------------------------
USER = "/user"                                    # plan state + balances in CREDITS (floats); email/id dropped
USER_META = "/user/meta"                          # {country_code, region_code, cohort} -> cohort only
WALLET = "/workspaces/wallet"                     # balances in COST UNITS (x100): credits_balance 888 = 8.88 credits
SUBSCRIPTION = "/workspaces/subscription"         # plan, status, billing cycle, current period (renewal), payment
WORKSPACE_SETTINGS = "/workspaces/settings"       # {configs: []} -> unlimited grants (client drops status=locked)
NOTICE = "/workspaces/notice"                     # discount offers shown to this user (status, discount, currency)
FREE_GENS = "/user/free-gens/v2"                  # {items: []}
GENERATION_SECONDS = "/user/generation-seconds"   # {items: []}
AUTO_TOP_UP = "/v2/auto-top-ups/settings"         # credits_per_dollar, refill options, state, eligibility
PERSONAL_PROMO = "/user/personal-promo"           # {} when none
ALL_UNLIM_STATUS = "/subscriptions/bundle/all-unlim/status"   # {is_eligible_to_purchase, has_all_unlims}

# ---- jobs (login only, --with-jobs) ----------------------------------------------------------------------------
JOBS = "/jobs/accessible"                         # {jobs[], has_more}; size (JS default 50), cursor, job_set_type[]
JOBS_DEFAULT_SIZE = 20
JOBS_MAX_SIZE = 50                                # the web app's own default page size; larger is not verified

# ---- public pricing (for --compare-estimate) -------------------------------------------------------------------
JOB_COSTS = "/job-sets/costs"                     # price points (fetched with the session: logged-in rows, e.g. magi_2)
VIRAL_PRESETS = "/viral-hub/presets/all"          # viral_hub_* price matrices
COMPARE = "/subscriptions/v2/compare"             # fallback prices for models missing from /job-sets/costs
BENEFITS = "/subscriptions/v2/plan-benefits"      # label -> job_set_type for the fallback

# endpoint key -> (path, part name in the snapshot)
SNAPSHOT_ENDPOINTS: dict[str, tuple[str, str]] = {
    "account_user": (USER, "user"),
    "account_user_meta": (USER_META, "user_meta"),
    "account_wallet": (WALLET, "wallet"),
    "account_subscription": (SUBSCRIPTION, "subscription"),
    "account_workspace_settings": (WORKSPACE_SETTINGS, "workspace_settings"),
    "account_notice": (NOTICE, "notice"),
    "account_free_gens": (FREE_GENS, "free_gens"),
    "account_generation_seconds": (GENERATION_SECONDS, "generation_seconds"),
    "account_auto_top_up": (AUTO_TOP_UP, "auto_top_up"),
    "account_personal_promo": (PERSONAL_PROMO, "personal_promo"),
    "account_all_unlim_status": (ALL_UNLIM_STATUS, "all_unlim_status"),
}
JOBS_ENDPOINT = "account_jobs"
PRICING_ENDPOINTS: dict[str, tuple[str, dict]] = {
    "account_job_costs": (JOB_COSTS, {}),
    "account_viral_presets": (VIRAL_PRESETS, {"lang": "en"}),
    "account_compare": (COMPARE, {"plan_set_key": "ps_a3", "billing_period": "annual", "with_localization": "true"}),
    "account_benefits": (BENEFITS, {"locale": "en"}),
}
#: a run without a 200 from these is a failure (nothing about the account was read)
CORE_ENDPOINTS = frozenset({"account_user", "account_wallet"})
#: a non-200 here does not make the run "partial" (empty / team-only / not offered to this account)
OPTIONAL = frozenset(set(SNAPSHOT_ENDPOINTS) - CORE_ENDPOINTS - {"account_subscription"}) | frozenset(PRICING_ENDPOINTS)
PUBLIC = frozenset(PRICING_ENDPOINTS)

ENDPOINT_URLS = {k: v[0] for k, v in SNAPSHOT_ENDPOINTS.items()} | {JOBS_ENDPOINT: JOBS} | {
    k: v[0] for k, v in PRICING_ENDPOINTS.items()}

#: /jobs/accessible statuses whose `cost` is a real charge comparable with the estimate
CHARGED_STATUSES = frozenset({"completed"})
