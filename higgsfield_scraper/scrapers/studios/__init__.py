"""Studios scraper (opt-in): public content of the Higgsfield studio / marketplace products no other scraper covers.

Community apps marketplace (views/likes/dislikes/remixes/credits), community games (plays/players/remixes), community
skills and AI employees (installs/users/usage + examples), Playable Ads explore presets, AI Influencer builder
options, and published outputs of every studio (Marketing, Ads, Cinema, AI Influencer,
Canvas, Shorts/Drama, AI Host, Property, Editing Room) from the community feeds, with optional public comments.
Login-only per-user workspaces are documented but never requested; Shorts Studio presets belong to
`scrape showcase --what reels_presets`. See docs/scrapers/studios.md.
"""
from __future__ import annotations

from ...core.base import ScraperDef
from . import dataset, options, parsers
from .endpoints import OPTIONAL_ENDPOINTS
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, StudiosDataset

IMAGE_TYPES = ("image",)


def media_urls(entity: dict, mode: str) -> list[tuple[str, str]]:
    """thumbs = images; full = videos (no HLS playlists, no HTML/zip builds); all = every media URL (+ inputs)."""
    out = []
    items = (entity.get("media") or []) + (entity.get("inputs") or [] if mode == "all" else [])
    for m in items:
        t = m.get("type")
        if mode == "all" or (mode == "thumbs" and t in IMAGE_TYPES) or (mode == "full" and t == "video"):
            out.append((m.get("role") or "media", m["url"]))
    return out


SCRAPER = ScraperDef(
    name="studios",
    description="Studio & marketplace content: community apps (+views/likes/dislikes/remixes/credits), games "
                "(+plays), skills & AI employees (+usage), Playable Ads presets, AI Influencer options, "
                "published outputs of every studio (+likes/views, optional comments)",
    spider_cls="higgsfield_scraper.scrapers.studios.spider:StudiosSpider",
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
    optional_endpoints=OPTIONAL_ENDPOINTS,
    media_urls=media_urls,
    dataset_model=StudiosDataset,
    personal_data=True,          # authors / profiles / comment authors: raw/ + http/ archives redacted by default
    examples=(
        "python -m higgsfield_scraper scrape studios",
        "python -m higgsfield_scraper scrape studios --what apps --apps-sort most_viewed --max-items 500",
        "python -m higgsfield_scraper scrape studios --what games,skills,employees",
        "python -m higgsfield_scraper scrape studios --what galleries --studios marketing_studio,cinema_studio "
        "--gallery-pages 0 --with-comments",
        "python -m higgsfield_scraper scrape studios --what playable_presets --download-media thumbs",
        "python -m higgsfield_scraper scrape studios --what playable_presets,influencer_options --lang de",
    ),
)
