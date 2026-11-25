"""Shared schema building blocks."""
from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Annotated, Any, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

# Money in major units (USD), serialized as a decimal string in JSON (e.g. "35.00").
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Scalar = str | int | float | bool


class Strict(BaseModel):
    """Our own output shapes: unknown fields are a bug, so forbid them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Provenance(Strict):
    endpoint: str
    url: str
    params: dict[str, str] = Field(default_factory=dict)
    fetched_at: AwareDatetime


def make_id(*parts: Any) -> str:
    """Stable 16-hex id from a natural key (never include volatile values like prices)."""
    key = "|".join("" if p is None else str(p).strip().lower() for p in parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def cents_to_money(value: Optional[int | float]) -> Optional[Decimal]:
    if value is None:
        return None
    return (Decimal(str(value)) / 100).quantize(Decimal("0.01"))


def percent(before: Optional[Decimal], after: Optional[Decimal]) -> Optional[Decimal]:
    if before in (None, 0) or after is None:
        return None
    return ((1 - after / before) * 100).quantize(Decimal("0.01"))
