"""Opt-in `--sections account` (pricing scraper): the logged-in account's own money state, privacy-whitelisted.

One `pricing_account` entity per account endpoint. Only pricing-relevant numeric / plan fields are kept (see
parsers/account.py: ACCOUNT_FIELDS); never emails, names, avatars, user / workspace / subscription ids or Stripe ids.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from .common import SCHEMA_VERSION, Provenance, Scalar, Strict


class AccountRecord(Strict):
    schema_version: int = SCHEMA_VERSION
    record_id: str = Field(description="hash(endpoint)")
    endpoint: str = Field(description="account_wallet | account_subscription | account_auto_top_up | ...")
    status: int
    fields: dict[str, Optional[Scalar]] = Field(
        default_factory=dict, description="Whitelisted scalar fields; wallet balances converted to credits (API / 100)")
    lists: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict, description="Whitelisted list parts (packs, tiers, free gens, top-up options, ...), "
                                          "scrubbed of ids / urls / personal keys")
    conversions: dict[str, str] = Field(
        default_factory=dict, description="field -> rule applied, e.g. 'credits = api_value / 100 (cost units)'")
    source: Provenance


class AccountSection(Strict):
    records: list[AccountRecord] = Field(default_factory=list)
