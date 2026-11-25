"""Subscription plans with prices before / after the offer and on renewal."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field, model_validator

from .common import SCHEMA_VERSION, Currency, Money, Provenance, Strict

BillingPeriod = Literal["monthly", "quarterly", "annual"]


class PricePair(Strict):
    total: Money = Field(description="Amount charged per billing period")
    per_month: Money = Field(description="Equivalent monthly amount")


class PlanPricing(Strict):
    before_offer: PricePair = Field(description="List price (original_price)")
    after_offer: PricePair = Field(description="Price you pay now (final_price)")
    renewal: PricePair = Field(description="Price on the next renewal (renew_price)")


class Discount(Strict):
    percent_off: Optional[float] = None
    duration: Optional[str] = Field(None, description="once | forever | repeating")
    duration_months: Optional[int] = None
    applies_to: Optional[str] = Field(None, description="first_payment | all_payments | first_N_months")


class Savings(Strict):
    total: Money
    per_month: Money
    percent: Optional[float] = None


class PricePerCredit(Strict):
    before_offer: Optional[Money] = None
    after_offer: Optional[Money] = None
    renewal: Optional[Money] = None


class Plan(Strict):
    schema_version: int = SCHEMA_VERSION
    plan_id: str = Field(description="hash(plan_set_key, plan_type, billing_period, credits)")
    plan_uuid: str
    plan_set_key: str
    country_code: Optional[str] = None
    plan_type: str
    name: str
    audience: Literal["individual", "business"]
    billing_period: BillingPeriod
    billing_months: int
    credits_per_month: int
    credits_per_period: int
    seats: Optional[int] = Field(None, description="Minimum seats (from /compare); None if unknown")
    currency: Currency
    stripe_product_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    pricing: PlanPricing
    has_offer: bool
    discount: Optional[Discount] = None
    savings: Savings
    price_per_credit: PricePerCredit
    offer: Optional[dict[str, Any]] = Field(None, description="Raw promo offer object when present")
    benefit_card_ids: list[str] = Field(default_factory=list)
    unlimited_model_ids: list[str] = Field(default_factory=list)
    free_gens: list[dict[str, Any]] = Field(default_factory=list)
    source: Provenance

    @model_validator(mode="after")
    def _check(self):
        p = self.pricing
        if p.after_offer.total > p.before_offer.total:
            raise ValueError("after_offer price is higher than before_offer price")
        if self.has_offer != (p.after_offer.total < p.before_offer.total):
            raise ValueError("has_offer inconsistent with prices")
        return self


class PlanSet(Strict):
    schema_version: int = SCHEMA_VERSION
    plan_set_key: str
    country_code: Optional[str] = None
    currency: Optional[Currency] = None
    special_offer: Optional[str | dict[str, Any]] = Field(
        None, description="null, an offer object, or a plan_type string to highlight (e.g. 'ultra' in max_v*_ultra sets)")
    plan_count: int
    plan_types: list[str]
    source: Provenance
