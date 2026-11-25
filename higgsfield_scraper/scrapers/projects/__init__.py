"""projects scraper: community project publications (films / series / carousels), recommended feeds, contest
entries, contests (+ rules, rewards, prizes, judges, winners) and contest submissions. See docs/scrapers/projects.md.
"""
from __future__ import annotations

from ...core.base import ScraperDef
from . import endpoints as ep
from .dataset import build_dataset, media_urls, write_outputs
from .options import add_args, default_label, make_selection, selection_from_dict
from .parsers import keep, parse_envelope
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, ProjectsDataset

SCRAPER = ScraperDef(
    name="projects",
    description="Community projects (films/series/carousels), recommended feeds, contest entries, contests "
                "(rules, rewards, judges, winners) and contest submissions",
    spider_cls="higgsfield_scraper.scrapers.projects.spider:ProjectsSpider",
    model_by_kind=MODEL_BY_KIND,
    id_field_by_kind=ID_FIELD_BY_KIND,
    add_args=add_args,
    make_selection=make_selection,
    selection_from_dict=selection_from_dict,
    parse_envelope=parse_envelope,
    keep=keep,
    build_dataset=build_dataset,
    write_outputs=write_outputs,
    default_label=default_label,
    optional_endpoints=frozenset(ep.LOGIN_ONLY),
    personal_data=True,               # archives redacted unless --with-profiles
    media_urls=media_urls,
    dataset_model=ProjectsDataset,
    examples=(
        "python -m higgsfield_scraper scrape projects --max-items 200",
        "python -m higgsfield_scraper scrape projects --what contests --with-details --with-submissions",
        "python -m higgsfield_scraper scrape projects --what publications --categories spotlight --with-details",
        "python -m higgsfield_scraper scrape projects --what recommended --scope ai_film_festival --max-pages 2",
        "python -m higgsfield_scraper scrape projects --what contests --contest-status closed --contest-types weekly",
        "python -m higgsfield_scraper scrape projects --what publications --max-items 50 --download-media thumbs",
    ),
)
