"""Login-only data (needs --token). Shapes taken from the site's JS; unverified without a session."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import ConfigDict, Field

from .common import SCHEMA_VERSION, Money, Provenance, Strict


class CreditPackage(Strict):
    model_config = ConfigDict(extra="allow")  # shape not observed live; keep unknown fields

    schema_version: int = SCHEMA_VERSION
    package_id: str
    credits: Optional[float] = None
    amount: Optional[Money] = None
    original_amount: Optional[Money] = None
    display_amount: Optional[Money] = None
    tax_amount: Optional[Money] = None
    offer: Optional[dict[str, Any]] = None
    expire_days: Optional[int] = None
    source: Provenance


class AuthPayload(Strict):
    schema_version: int = SCHEMA_VERSION
    endpoint: str
    status: int
    data: Any = Field(description="Raw JSON body (shape unknown without a session)")
    source: Provenance
