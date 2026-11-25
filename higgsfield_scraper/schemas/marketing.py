"""Marketing copy per plan from pricing.higgsfield.ai/v2/pricing-config."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from .common import SCHEMA_VERSION, Provenance, Strict


class MarketingFeature(Strict):
    feature_id: str
    text: str
    status: Optional[str] = Field(None, description="included | excluded | limited")
    tooltip: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    badges: list[Any] = Field(default_factory=list)


class MarketingFeatureGroup(Strict):
    group_id: str
    title: Optional[str] = None
    features: list[MarketingFeature]


class MarketingPlan(Strict):
    schema_version: int = SCHEMA_VERSION
    marketing_id: str
    config_version: str
    is_latest: bool
    billing_period: str
    plan_type: str
    tagline: Optional[str] = None
    credits_amount: Optional[float] = None
    credits_label: Optional[str] = None
    credits_tooltip: Optional[str] = None
    promo_items: list[dict[str, Any]] = Field(default_factory=list)
    main_features: list[MarketingFeature] = Field(default_factory=list)
    feature_groups: list[MarketingFeatureGroup] = Field(default_factory=list)
    special_deal: Optional[Any] = None
    billing_periods: Optional[dict[str, Any]] = None
    ui: Optional[dict[str, Any]] = None
    source: Provenance
