"""Login-only data (needs a session: `login`, HF_CLERK_CLIENT or --token).

Credit packages were observed live on 2026-11-26 (GET /subscriptions/v2/packages, logged in): every field the API
returns is declared below. Scrapy items only carry declared fields, so an undeclared field would be silently dropped
from items/ and the outputs; extra="allow" stays as a safety net for the validated JSON.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict, Field

from .common import SCHEMA_VERSION, Money, Provenance, Strict


class CreditPackage(Strict):
    model_config = ConfigDict(extra="allow")

    schema_version: int = SCHEMA_VERSION
    package_id: str = Field(description="Stripe product id (API `id`)")
    price_id: Optional[str] = Field(None, description="Stripe price id")
    credits: Optional[float] = Field(None, description="credits in the pack (API value / 100)")
    currency: Optional[str] = None
    amount: Optional[Money] = Field(None, description="price you pay, USD (API cents / 100)")
    original_amount: Optional[Money] = Field(None, description="list price before the discount, USD")
    display_amount: Optional[Money] = Field(None, description="rounded price shown in the UI, USD")
    tax_amount: Optional[Money] = None
    tax_rate: Optional[Any] = None
    discount: Optional[float] = Field(None, description="discount label in percent (rounded by the API)")
    credits_per_dollar: Optional[float] = Field(None, description="as returned by the API")
    is_highlighted: Optional[bool] = None
    is_default: Optional[bool] = None
    features: list[dict[str, Any]] = Field(default_factory=list,
                                           description="[{display_number, text, type, is_available}] e.g. "
                                                       "'Up to 50 Nano Banana Pro image generations'")
    offer: Optional[dict[str, Any]] = None
    expire_days: Optional[int] = Field(None, description="days until purchased credits expire")
    source: Provenance


class AuthPayload(Strict):
    schema_version: int = SCHEMA_VERSION
    endpoint: str
    status: int
    data: Any = Field(description="Raw JSON body: unlim-catalog ({bundles: []} for a non-team account on "
                                  "2026-11-26), credit-price (500 for non-team accounts), adjustable-credits")
    source: Provenance
