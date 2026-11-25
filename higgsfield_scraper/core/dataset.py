"""Common dataset metadata for every non-pricing scraper (`dataset["meta"]`)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import AwareDatetime, Field

from ..schemas.common import Provenance, Strict, make_id  # re-exported for scrapers  # noqa: F401
from .base import RunMeta


class CoreMeta(Strict):
    scraper: str
    run_id: Optional[str] = None
    label: Optional[str] = None
    scraped_at: AwareDatetime
    source: str = "https://higgsfield.ai"
    options: dict[str, Any] = Field(default_factory=dict, description="scraper selection (filters/flags)")
    limits: dict[str, Any] = Field(default_factory=dict, description="CommonOptions used for the run")
    limits_hit: list[str] = Field(default_factory=list, description="e.g. max_items reached, max_pages reached")
    totals_available: dict[str, Optional[int]] = Field(default_factory=dict, description="API-reported totals")
    counts: dict[str, int] = Field(default_factory=dict)
    endpoints: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def make_meta(scraper: str, sel: Any, rm: RunMeta, *, counts: dict[str, int], endpoints: dict[str, str],
              totals_available: Optional[dict[str, Optional[int]]] = None, warnings: Optional[list[str]] = None) -> dict:
    return {
        "scraper": scraper,
        "run_id": rm.run_id,
        "label": rm.label,
        "scraped_at": (rm.scraped_at or datetime.now(timezone.utc)).isoformat(),
        "options": sel.to_dict() if hasattr(sel, "to_dict") else dict(sel or {}),
        "limits": rm.common.to_dict(),
        "limits_hit": list(rm.limits_hit),
        "totals_available": dict(totals_available or {}),
        "counts": counts,
        "endpoints": endpoints,
        "warnings": list(rm.warnings) + list(warnings or []),
    }
