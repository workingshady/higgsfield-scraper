"""Pydantic models of the account scraper (entity kinds + the whole dataset).

Privacy: no model has a field for email, names, avatars, user/workspace/subscription/Stripe ids, media URLs or
(unless --with-prompts) prompt text. Job ids are hashed (`make_id`). Credits are Decimal (JSON: strings).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from pydantic import Field

from ...core.dataset import CoreMeta, Provenance, Strict
from ...schemas.common import Scalar

Credits = Decimal
Obj = dict[str, Any]


# ------------------------------------------------------------------ entities (one per kind)
class AccountSnapshotPart(Strict):
    """One snapshot endpoint, already whitelisted (see redaction.py); assembled into AccountSnapshot."""

    part_id: str = Field(description="part name (= dedup key): user | wallet | subscription | …")
    part: str
    data: Obj = Field(default_factory=dict)
    source: Provenance


class AccountJob(Strict):
    job_id: str = Field(description="sha256('account_job|<job id>')[:16] — the real id is never stored")
    job_set_key: Optional[str] = Field(None, description="hashed job_set_id (jobs of one batch share it)")
    job_set_type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = Field(None, description="ISO-8601 UTC")
    cost_units: Optional[int] = Field(None, description="`cost` as returned: credits x 100")
    actual_credits: Optional[Credits] = Field(None, description="cost_units / 100")
    resolution: Optional[Scalar] = None
    duration: Optional[Scalar] = None
    quality: Optional[Scalar] = None
    batch_size: Optional[Scalar] = None
    mode: Optional[Scalar] = None
    aspect_ratio: Optional[Scalar] = None
    model: Optional[Scalar] = None
    use_unlim: Optional[bool] = None
    input_images: Optional[int] = Field(None, description="input images in params (count only)")
    input_videos: Optional[int] = Field(None, description="input videos in params (count only)")
    prompt_chars: Optional[int] = Field(None, description="prompt length (always kept: per-character pricing)")
    prompt: Optional[str] = Field(None, description="only with --with-prompts")
    params: Obj = Field(default_factory=dict, description="pricing-relevant params subset; media reduced to stubs")
    source: Provenance


class AccountCostBasis(Strict):
    """Public pricing bodies used to build the CostEstimator (--compare-estimate)."""

    basis_id: str = Field(description="job_costs | viral_presets | compare | benefits")
    body: Any = None
    source: Provenance


MODEL_BY_KIND = {
    "account_snapshot_part": AccountSnapshotPart,
    "account_job": AccountJob,
    "account_cost_basis": AccountCostBasis,
}
ID_FIELD_BY_KIND = {"account_snapshot_part": "part_id", "account_job": "job_id", "account_cost_basis": "basis_id"}


# ------------------------------------------------------------------ snapshot
class Plan(Strict):
    plan_type: Optional[str] = None
    billing_period: Optional[str] = None
    plan_ends_at: Optional[str] = None
    next_credit_allocation_at: Optional[str] = None
    is_cancel_inited: Optional[bool] = None
    cohort: Optional[str] = None
    promo_state: Optional[str] = None
    has_unlim: Optional[bool] = None
    has_flex_unlim: Optional[bool] = None
    workspace_type: Optional[str] = None
    workspace_role: Optional[str] = None
    is_paused: Optional[bool] = None
    is_pause_scheduled: Optional[bool] = None
    is_gift_subscription: Optional[bool] = None
    plan_version: Optional[int] = None
    trial_status: Optional[Scalar] = None
    subscription_downgrades_at: Optional[str] = None
    subscription_downgrades_plan: Optional[str] = None
    is_pro_plan_veo3_available: Optional[bool] = None
    veo3_fast_generations_count: Optional[int] = None


class Balances(Strict):
    """From /user, already in credits."""

    subscription_credits: Optional[Credits] = None
    package_credits: Optional[Credits] = None
    bonus_credits: Optional[Credits] = None
    bonus_credits_expire_at: Optional[str] = None
    daily_credits: Optional[Credits] = None
    total_plan_credits: Optional[Credits] = None
    soul_credits: Optional[Credits] = None
    wan2_5_video_credits: Optional[Credits] = None
    text2keyframes_credits: Optional[Credits] = None
    face_swap_credits: Optional[Credits] = None
    qwen_camera_control_credits: Optional[Credits] = None
    character_swap_credits: Optional[Credits] = None


class Wallet(Strict):
    """From /workspaces/wallet: balances come in cost units (x100); `<name>` = credits, `<name>_units` = raw."""

    credits_balance: Optional[Credits] = None
    credits_balance_units: Optional[int] = None
    subscription_balance: Optional[Credits] = None
    subscription_balance_units: Optional[int] = None
    total_credits: Optional[Credits] = None
    total_credits_units: Optional[int] = None
    on_demand_credits: Optional[Credits] = None
    on_demand_credits_units: Optional[int] = None
    bonus_credits: Optional[Credits] = None
    bonus_credits_units: Optional[int] = None
    bonus_credits_expire_at: Optional[str] = None
    expire_days: Optional[int] = None
    credit_limit_units: Optional[int] = Field(None, description="raw value; unit assumed x100 like the balances")
    allocation_cycle: Optional[Scalar] = None
    next_credit_allocation_date: Optional[str] = None
    group_credit_allocation: Any = None
    scoped_credits: list[Obj] = Field(default_factory=list, description="scrubbed (no ids); balances in units")


class Subscription(Strict):
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    status: Optional[str] = None
    billing_cycle: Optional[str] = None
    total_seats: Optional[int] = None
    occupied_seats: Optional[int] = None
    available_seats: Optional[int] = None
    seats_capacity: Optional[int] = None
    unlimited_seats: Optional[bool] = None
    credits_per_seat: Optional[int] = None
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    renewal_date: Optional[str] = Field(None, description="current_period_end when the subscription renews "
                                                          "(not cancelled / cancellation not requested)")
    cancel_at: Optional[str] = None
    is_pause_scheduled: Optional[bool] = None
    pause_starts_at: Optional[str] = None
    pause_resumes_at: Optional[str] = None
    is_paused: Optional[bool] = None
    payment_status: Optional[str] = None
    downgrades_at: Optional[str] = None
    plan_version: Optional[int] = None
    is_gift_subscription: Optional[bool] = None
    is_cancellation_requested: Optional[bool] = None


class AutoTopUp(Strict):
    state: Optional[str] = None
    is_eligible: Optional[bool] = None
    is_on_demand_only: Optional[bool] = None
    threshold: Any = None
    credits_per_dollar: Optional[Scalar] = None
    current_refill_amount: Optional[Scalar] = None
    on_demand_credits: Optional[Scalar] = None
    currency: Optional[str] = None
    expire_days: Optional[int] = None
    options: list[Any] = Field(default_factory=list)
    refill_options: list[Any] = Field(default_factory=list)
    selected_option: Any = None
    default_option: Any = None
    modal_type: Optional[str] = None


class Notice(Strict):
    status: Optional[str] = None
    payment_method_bonus_status: Optional[str] = None
    payment_method_bonus_type: Optional[Scalar] = None
    discount: Any = None
    discounted_price: Any = None
    currency: Optional[str] = None
    unlims: Any = None


class AllUnlim(Strict):
    is_eligible_to_purchase: Optional[bool] = None
    has_all_unlims: Optional[bool] = None


class AccountSnapshot(Strict):
    snapshot_id: str
    scraped_at: str
    plan: Plan = Field(default_factory=Plan)
    balances: Balances = Field(default_factory=Balances)
    wallet: Wallet = Field(default_factory=Wallet)
    subscription: Subscription = Field(default_factory=Subscription)
    auto_top_up: AutoTopUp = Field(default_factory=AutoTopUp)
    notice: Notice = Field(default_factory=Notice)
    all_unlim: AllUnlim = Field(default_factory=AllUnlim)
    free_gens: list[Obj] = Field(default_factory=list)
    generation_seconds: list[Obj] = Field(default_factory=list)
    unlimited_grants: list[Obj] = Field(default_factory=list, description="/workspaces/settings configs "
                                                                         "(status=locked dropped, like the web app)")
    personal_promo: Optional[Obj] = None
    parts_fetched: list[str] = Field(default_factory=list)
    parts_missing: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ comparison
class EstimateComparison(Strict):
    job_id: str
    job_set_type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    actual_credits: Optional[Credits] = None
    estimated_credits: Optional[Credits] = None
    diff: Optional[Credits] = Field(None, description="actual - estimated (credits)")
    abs_diff: Optional[Credits] = None
    ratio: Optional[Decimal] = Field(None, description="actual / estimated")
    match: Optional[bool] = Field(None, description="|diff| <= tolerance; None when not comparable")
    comparable: bool = Field(description="charged status, actual cost known, estimate available, not use_unlim")
    not_comparable_reason: Optional[str] = None
    estimator_status: str = Field(description="exact | approximate | unpriced | skipped")
    price_point_id: Optional[str] = None
    unit: Optional[str] = None
    quantity: Optional[float] = None
    quantity_basis: Optional[str] = None
    matched: Obj = Field(default_factory=dict)
    assumed: Obj = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ComparisonGroup(Strict):
    job_set_type: str
    jobs: int
    comparable: int
    matches: int
    match_rate: Optional[float] = Field(None, description="matches / comparable")
    exact_estimates: int = 0
    approximate_estimates: int = 0
    unpriced: int = 0
    mean_diff: Optional[Credits] = None
    total_actual_credits: Optional[Credits] = None
    total_estimated_credits: Optional[Credits] = None


class PricingBasis(Strict):
    job_costs_version: Optional[str] = None
    priced_models: Optional[int] = None
    tolerance_credits: Credits = Decimal("0.01")
    notes: list[str] = Field(default_factory=list)


class Summary(Strict):
    jobs: int = 0
    jobs_by_type: dict[str, int] = Field(default_factory=dict)
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    total_actual_credits: Optional[Credits] = None
    comparable: int = 0
    matches: int = 0
    match_rate: Optional[float] = None


class AccountDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    snapshot: Optional[AccountSnapshot] = None
    jobs: list[AccountJob] = Field(default_factory=list)
    estimate_comparison: list[EstimateComparison] = Field(default_factory=list)
    comparison_summary: list[ComparisonGroup] = Field(default_factory=list)
    pricing_basis: Optional[PricingBasis] = None
    summary: Summary = Field(default_factory=Summary)
