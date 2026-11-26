"""Scraper registry. Add a scraper by adding its module path here (module must expose `SCRAPER: ScraperDef`)."""
from __future__ import annotations

import importlib
import logging
from functools import lru_cache

from pydantic import BaseModel

from .base import ScraperDef

log = logging.getLogger(__name__)

SCRAPER_MODULES: dict[str, str] = {
    "pricing": "higgsfield_scraper.scrapers.pricing",
    "community": "higgsfield_scraper.scrapers.community",
    "catalog": "higgsfield_scraper.scrapers.catalog",
    "projects": "higgsfield_scraper.scrapers.projects",
    "blog": "higgsfield_scraper.scrapers.blog",
    "site": "higgsfield_scraper.scrapers.site",
    "account": "higgsfield_scraper.scrapers.account",
}
DEFAULT_SCRAPER = "pricing"


def get(name: str) -> ScraperDef:
    if name not in SCRAPER_MODULES:
        raise ValueError(f"unknown scraper {name!r}; available: {sorted(available())}")
    return importlib.import_module(SCRAPER_MODULES[name]).SCRAPER


@lru_cache(maxsize=1)
def available() -> dict[str, ScraperDef]:
    out = {}
    for name, mod in SCRAPER_MODULES.items():
        try:
            module = importlib.import_module(mod)
        except ModuleNotFoundError as e:
            if e.name and e.name.startswith(mod):     # scraper not built yet
                continue
            if name == DEFAULT_SCRAPER:
                raise
            log.warning("scraper %s unavailable (%s) — skipped", name, e)
            continue
        except Exception as e:                        # one broken scraper must not take down the whole CLI
            if name == DEFAULT_SCRAPER:
                raise
            log.warning("scraper %s failed to import (%s: %s) — skipped", name, type(e).__name__, e)
            continue
        sdef = getattr(module, "SCRAPER", None)
        if sdef is None:                              # package exists but is still being written
            log.debug("scraper %s has no SCRAPER yet — skipped", name)
            continue
        out[name] = sdef
    return out


@lru_cache(maxsize=1)
def all_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {}
    for name, sdef in available().items():
        for kind, model in sdef.model_by_kind.items():
            if kind in models and models[kind] is not model:
                raise RuntimeError(f"entity kind {kind!r} defined by two scrapers (last: {name})")
            models[kind] = model
    return models


@lru_cache(maxsize=1)
def all_id_fields() -> dict[str, str]:
    out: dict[str, str] = {}
    for sdef in available().values():
        out.update(sdef.id_field_by_kind)
    return out
