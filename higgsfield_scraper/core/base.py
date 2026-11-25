"""The contract every scraper implements (`ScraperDef`) + options shared by all scrapers (`CommonOptions`).

A scraper is a package under `higgsfield_scraper/scrapers/<name>/` whose `__init__.py` exposes `SCRAPER: ScraperDef`.
Everything else — run folders, logs, http/ archive, raw archive, validation, dedup, auth tokens, limits, media
download, JSON/CSV export, normalize — is provided by the framework. See docs/ADDING_A_SCRAPER.md.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel

MEDIA_MODES = ("none", "thumbs", "full", "all")


@dataclass
class CommonOptions:
    """Limits & safeguards shared by every scraper (CLI flags in core/cli_common.py)."""

    max_items: Optional[int] = None        # stop after N primary items (scraper decides what "primary" is)
    max_pages: Optional[int] = None        # max pages per paginated listing
    page_size: Optional[int] = None        # API page size (each scraper clamps to the API maximum)
    max_requests: int = 5000               # hard cap on HTTP responses (CLOSESPIDER_PAGECOUNT)
    max_minutes: Optional[float] = None    # wall-clock cap (CLOSESPIDER_TIMEOUT)
    delay: float = 1.0                     # DOWNLOAD_DELAY seconds (randomized ±50%)
    concurrency: int = 2                   # CONCURRENT_REQUESTS_PER_DOMAIN
    download_media: str = "none"           # none | thumbs | full | all
    max_media_files: int = 500
    max_media_mb: float = 1024.0
    auth: str = "auto"                     # auto (use a token if configured) | off | required
    stop_on_block: bool = True             # stop the crawl on bot-protection (DataDome captcha) responses

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "CommonOptions":
        d = dict(d or {})
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def settings_overrides(self) -> dict[str, Any]:
        s: dict[str, Any] = {
            "DOWNLOAD_DELAY": self.delay,
            "CONCURRENT_REQUESTS_PER_DOMAIN": self.concurrency,
            "CLOSESPIDER_PAGECOUNT": self.max_requests,
        }
        if self.max_minutes:
            s["CLOSESPIDER_TIMEOUT"] = int(self.max_minutes * 60)
        return s


@dataclass
class RunMeta:
    """What the framework knows about the current run, handed to `build_dataset`."""

    run_id: Optional[str] = None
    label: Optional[str] = None
    scraped_at: Optional[datetime] = None
    warnings: list[str] = field(default_factory=list)
    common: CommonOptions = field(default_factory=CommonOptions)
    stats: dict[str, Any] = field(default_factory=dict)
    limits_hit: list[str] = field(default_factory=list)
    totals: dict[str, Optional[int]] = field(default_factory=dict)   # API-reported totals seen during the crawl


def resolve(obj: Any) -> Any:
    """'package.module:Name' -> object (lets ScraperDef reference its spider lazily, avoiding import cycles)."""
    if isinstance(obj, str) and ":" in obj:
        import importlib
        mod, _, name = obj.partition(":")
        return getattr(importlib.import_module(mod), name)
    return obj


@dataclass
class ScraperDef:
    name: str
    description: str
    spider_cls: Any                                             # Spider class or "module:Class" (lazy)
    model_by_kind: dict[str, type[BaseModel]]                   # kinds must be globally unique across scrapers
    id_field_by_kind: dict[str, str]                            # dedup key per kind
    add_args: Callable[[argparse.ArgumentParser], None]         # scraper-specific CLI flags
    make_selection: Callable[[argparse.Namespace], Any]         # args -> selection (has .to_dict())
    selection_from_dict: Callable[[dict], Any]                  # manifest/spider -a kwargs -> selection
    parse_envelope: Callable[[Any, Any], list[dict]]            # (Envelope, selection) -> entity dicts with "kind"
    build_dataset: Callable[[dict[str, list[dict]], Any, RunMeta], dict]   # -> validated JSON-mode dataset
    write_outputs: Callable[[dict, Path], list[Path]]
    keep: Callable[[dict, Any], bool] = lambda e, s: True       # output filters
    default_label: Callable[[Any], str] = lambda s: "run"
    optional_endpoints: frozenset[str] = frozenset()            # non-200 here does not make a run "partial"
    media_urls: Optional[Callable[[dict, str], list[tuple[str, str]]]] = None  # (entity, mode) -> [(role, url)]
    counts_key: str = "counts"                                  # where dataset["meta"][...] holds counts
    dataset_model: Any = None                                   # pydantic model of the whole dataset (schema export)
    personal_data: bool = False                                 # API bodies contain other users' profiles: archives
                                                                # (raw/, http/) are redacted unless sel.with_profiles
    examples: tuple[str, ...] = ()                              # CLI help examples
