"""Per-model ("job_set_type") credit costs, flattened into typed price points."""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import Field

from .common import (SCHEMA_VERSION, VISIBILITY_DESCRIPTION, LoginOnly, LoginOptional, Provenance, Scalar, Strict,
                     Visibility)

Category = Literal["video", "image", "audio", "other"]


class Formula(Strict):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    batch_size: Optional[dict[str, Any]] = None
    unlimited: Optional[dict[str, Any]] = None


class PricePoint(Strict):
    point_id: str
    dimensions: dict[str, Scalar] = Field(
        default_factory=dict, description="Selectors such as resolution, quality, mode, model, audio, video_input"
    )
    component: Optional[str] = Field(None, description="Sub-operation, e.g. video_edit")
    unit: str = Field(description="credits_per_generation | credits_per_second | credits_per_minute | ...")
    credits: Optional[float] = Field(None, description="Cost after discount (what you pay)")
    original_credits: Optional[float] = Field(None, description="Cost before discount")
    discount_percent: float = 0.0
    is_discounted: bool = False
    example: Optional[dict[str, float]] = Field(None, description="e.g. {'seconds': 5, 'credits': 35} for per-second units")
    attributes: dict[str, Scalar] = Field(default_factory=dict, description="is_estimate, reference_fps, ...")
    formula: Optional[Formula] = None
    usd_estimate: Optional[float] = Field(
        None, description="USD for `example` (or 1 unit) at the reference plan's after-offer price per credit"
    )


class ModelEntitlement(Strict):
    plan_type: str
    billing_period: str
    tab: Optional[str] = None
    type: str = Field(description="unlimited | free_gens")
    count: Optional[int] = None
    duration_days: Optional[int] = None
    max_resolution: Optional[str] = None
    max_duration_s: Optional[float] = None
    concurrency: Optional[dict[str, Any]] = None
    starts: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)
    benefit_label: Optional[str] = None


class Model(LoginOptional):
    __login_only__ = ("visibility",)

    schema_version: int = SCHEMA_VERSION
    model_id: str = Field(description="job_set_type")
    display_name: str
    family: str
    category: Category
    units: list[str]
    options: dict[str, list[Scalar]] = Field(
        default_factory=dict, description="Every selectable value per dimension, e.g. resolution -> [480p, 720p]"
    )
    components: list[str] = Field(default_factory=list)
    price_point_count: int
    has_cost_data: bool = Field(True, description="False = model only appears in plan benefits (no /job-sets/costs entry)")
    has_discount: bool
    min_credits: Optional[float] = None
    max_credits: Optional[float] = None
    price_points: list[PricePoint]
    entitlements: list[ModelEntitlement] = Field(default_factory=list)
    costs_version: Optional[str] = None
    raw_cost: Optional[Any] = None
    source: Provenance
    visibility: Annotated[Optional[Visibility], LoginOnly] = Field(None, description=VISIBILITY_DESCRIPTION)
