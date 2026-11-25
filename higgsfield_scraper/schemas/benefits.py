"""Plan benefit cards (unlimited models, free generations, promos) from /plan-benefits."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from .common import SCHEMA_VERSION, Provenance, Strict


class Concurrency(Strict):
    count: Optional[int] = None
    per: Optional[str] = None
    pool: Optional[Any] = None


class Caps(Strict):
    max_resolution: Optional[str] = None
    resolutions: Optional[list[Any]] = None
    max_duration_s: Optional[float] = None
    qualities: Optional[list[Any]] = None
    output_formats: Optional[list[Any]] = None
    options: Optional[Any] = None
    concurrency: Optional[Concurrency] = None


class Entitlement(Strict):
    type: str = Field(description="unlimited | free_gens | included | none")
    of: Optional[str] = None
    reason: Optional[str] = None
    count: Optional[int] = None
    duration_days: Optional[int] = None
    starts: Optional[str] = None
    available_until: Optional[str] = None
    requirements: list[str] = Field(default_factory=list)
    caps: Optional[Caps] = None


class BenefitRow(Strict):
    row_id: str
    label: Optional[str] = None
    description: Optional[str] = None
    model_ids: list[str] = Field(default_factory=list)
    entitlement: Entitlement
    placement: Optional[str] = None
    emphasis: Optional[str] = None
    tags: list[Any] = Field(default_factory=list)
    tooltip: Optional[str] = None


class BenefitSection(Strict):
    section_id: str
    kind: str
    slot: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    theme: Optional[str] = None
    info: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    rows: list[BenefitRow] = Field(default_factory=list)


class BenefitCard(Strict):
    schema_version: int = SCHEMA_VERSION
    card_id: str = Field(description="hash(billing_period, tab, plan_type)")
    plan_type: str
    billing_period: str
    tab: Optional[str] = None
    campaign: Optional[dict[str, Any]] = None
    experiment: Optional[Any] = None
    availability: Optional[dict[str, Any]] = None
    sections: list[BenefitSection]
    unlimited_model_ids: list[str] = Field(default_factory=list)
    free_gens: list[dict[str, Any]] = Field(default_factory=list)
    tab_badge: Optional[dict[str, Any]] = None
    source: Provenance
