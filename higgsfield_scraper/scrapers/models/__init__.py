"""Models scraper (opt-in): the model registry, rebuilt at runtime from the public frontend JS bundle.

There is no public "models" API: the generators' model list, per-model params schema (`defineJob`), routes, plan
tiers, feature-flag gating and featured order are static code in the bundle (docs/MODEL_LOADING.md §2-3). This
scraper fetches a few tool pages, follows the JS chunk graph (prioritized, --max-chunks), extracts that code with
regexes + bracket matching (no JS execution) and joins it with `/job-sets/costs` (priced job types) and the Shots
feed facet (`available_models`). One record per job type, menu entry and build. GET only, anonymous. Never part of
the default `scrape` (pricing). See docs/scrapers/models.md.
"""
from __future__ import annotations

from ...core.base import ScraperDef
from . import dataset, options, parsers
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, ModelsDataset

SCRAPER = ScraperDef(
    name="models",
    description="Model registry from the public JS bundle: ~130 job types with params schema (enums, ranges, "
                "defaults), media roles/limits, routes, plan tiers, flag gating, featured order, picker menus; "
                "+ /job-sets/costs and the Shots available_models facet; build id recorded",
    spider_cls="higgsfield_scraper.scrapers.models.spider:ModelsSpider",
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
    optional_endpoints=frozenset(),
    media_urls=None,
    dataset_model=ModelsDataset,
    personal_data=False,          # bundle code + public facets; the Shots body is reduced to its facet (middleware)
    examples=(
        "python -m higgsfield_scraper scrape models",
        "python -m higgsfield_scraper scrape models --max-chunks 300 --no-shots",
        "python -m higgsfield_scraper scrape models --pages /ai/video,/ai/image --max-chunks 0",
    ),
)
