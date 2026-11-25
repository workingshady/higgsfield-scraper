"""Catalog scraper: every preset / asset catalog a user can pick in the Higgsfield generators.

Public: motions (+ samples, details), avatars, avatar presets, voices, reference voices, sounds, styles, soul samples,
viral-hub types and presets. Login-only (auth="required", skipped cleanly without a session): soul styles, mixed media
presets, per-model motions, katana, color presets, youtube-faceless presets, camera settings, marketing studio.
See docs/scrapers/catalog.md.
"""
from __future__ import annotations

from ...core.base import ScraperDef
from . import dataset, options, parsers
from .endpoints import LOGIN_ENDPOINTS
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, CatalogDataset

VIDEO_AUDIO = ("video", "audio")


def media_urls(entity: dict, mode: str) -> list[tuple[str, str]]:
    """thumbs = preview images; full = videos + audio; all = everything (incl. waveform JSON)."""
    out = []
    for m in entity.get("media") or []:
        t = m.get("type")
        if mode == "all" or (mode == "thumbs" and t == "image") or (mode == "full" and t in VIDEO_AUDIO):
            out.append((m.get("role") or "media", m["url"]))
    return out


SCRAPER = ScraperDef(
    name="catalog",
    description="Preset & asset catalogs: motions (+samples/details), avatars, voices, sounds, styles, soul samples, "
                "viral-hub presets; login-only soul styles, per-model motions, mixed media, katana, ...",
    spider_cls="higgsfield_scraper.scrapers.catalog.spider:CatalogSpider",
    model_by_kind=MODEL_BY_KIND,
    id_field_by_kind=ID_FIELD_BY_KIND,
    add_args=options.add_args,
    make_selection=options.make_selection,
    selection_from_dict=options.selection_from_dict,
    parse_envelope=parsers.parse_envelope,
    keep=parsers.keep,
    build_dataset=dataset.build_dataset,
    write_outputs=dataset.write_outputs,
    default_label=options.default_label,
    optional_endpoints=LOGIN_ENDPOINTS,
    media_urls=media_urls,
    dataset_model=CatalogDataset,
    examples=(
        "python -m higgsfield_scraper scrape catalog",
        "python -m higgsfield_scraper scrape catalog --kinds motion,voice,sound",
        "python -m higgsfield_scraper scrape catalog --kinds motion --with-samples --with-details --max-pages 50",
        "python -m higgsfield_scraper scrape catalog --kinds all --include-login-only yes",
        "python -m higgsfield_scraper scrape catalog --kinds viral_preset --lang de --download-media thumbs",
    ),
)
