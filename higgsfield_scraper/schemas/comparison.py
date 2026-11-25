"""Plan comparison matrix from /subscriptions/v2/compare."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from .common import SCHEMA_VERSION, Money, Provenance, Strict


class ComparisonPlan(Strict):
    plan_type: str
    name: str
    credits: int
    seats: Optional[int] = None
    stripe_price_id: Optional[str] = None
    price_after_offer_per_month: Optional[Money] = None


class ComparisonValue(Strict):
    plan_type: str
    value_type: str
    raw: Any
    available: bool
    quantity: Optional[float] = Field(None, description="Parsed number, e.g. 411 from '411 videos'")
    quantity_unit: Optional[str] = None


class ComparisonFeature(Strict):
    name: str
    detail: Optional[str] = None
    approx: bool = False
    credits: Optional[float] = Field(None, description="From detail, e.g. 35 in '35 credits/5s'")
    per: Optional[str] = Field(None, description="From detail, e.g. '5s' or 'image'")
    values: list[ComparisonValue]


class ComparisonCategory(Strict):
    slug: str
    name: str
    description: Optional[str] = None
    features: list[ComparisonFeature]


class Comparison(Strict):
    schema_version: int = SCHEMA_VERSION
    comparison_id: str
    plan_set_key: str
    billing_period: str
    plans: list[ComparisonPlan]
    categories: list[ComparisonCategory]
    source: Provenance
