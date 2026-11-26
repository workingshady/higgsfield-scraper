"""Showcase scraper (opt-in): public example / showcase content no other scraper covers.

Canvas workflow templates, Editing Room examples (CMS + 6 full example projects with tool parameters and renders),
Property Studio example presets (JS table + lingui titles), video-explore (Higgsfield Multiplier) feeds with
engagement, /effects/examples sample generations, the public API model docs (docs.higgsfield.ai), Cinema Studio 4.0
creative controls, YouTube-faceless showcases, Intone examples, Seedance 2.0 presets, Kling motion-control presets,
(opt-in) Shorts Studio / AI Reels presets + their comment threads, (opt-in by name) the CMS home main feed, and
(login-only, opt-in) the fnf-score season.
See docs/scrapers/showcase.md.
"""
from __future__ import annotations

from ...core.base import ScraperDef
from . import dataset, options, parsers
from .endpoints import OPTIONAL_ENDPOINTS
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, ShowcaseDataset

IMAGE_ROLES = ("thumbnail", "poster", "image", "icon", "input")


# not downloaded (kept as URLs only): effect templates duplicate the catalog preset previews, and compressed videos are
# smaller copies of a video already in the list (both were added later; downloads stay as they were)
NO_DOWNLOAD_KINDS = frozenset({"showcase_effect_preset"})
NO_DOWNLOAD_ROLE_SUFFIX = "_compressed"


def media_urls(entity: dict, mode: str) -> list[tuple[str, str]]:
    """thumbs = images; full = videos (no HLS playlists); all = every media URL."""
    out = []
    if entity.get("kind") in NO_DOWNLOAD_KINDS:
        return out
    for m in (entity.get("media") or []) + ([entity["take"]] if entity.get("take") else []):
        if m.get("extra") is not None and str(m.get("role") or "").endswith(NO_DOWNLOAD_ROLE_SUFFIX):
            continue
        t = m.get("type")
        if mode == "all" or (mode == "thumbs" and t == "image") or (mode == "full" and t == "video"):
            out.append((m.get("role") or "media", m["url"]))
    return out


SCRAPER = ScraperDef(
    name="showcase",
    description="Showcase/example content: Canvas templates, Editing Room examples, Property Studio presets, "
                "video-explore feeds (+likes), effect sample generations, public API models, Cinema Studio "
                "controls, faceless/Intone/Seedance/motion-control showcases; opt-in Shorts Studio reels presets/"
                "comments, the home main feed (`--what main_feed`, by name only) and login `season`",
    spider_cls="higgsfield_scraper.scrapers.showcase.spider:ShowcaseSpider",
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
    dataset_model=ShowcaseDataset,
    personal_data=True,          # explore authors / effect-sample users: raw/ + http/ archives redacted by default
    examples=(
        "python -m higgsfield_scraper scrape showcase",
        "python -m higgsfield_scraper scrape showcase --what api_models,canvas_templates",
        "python -m higgsfield_scraper scrape showcase --what explore --explore-sort both --explore-pages 10",
        "python -m higgsfield_scraper scrape showcase --what effect_examples --effects acid,vanish",
        "python -m higgsfield_scraper scrape showcase --what property_studio_examples --lang de "
        "--download-media thumbs",
        "python -m higgsfield_scraper scrape showcase --what reels_presets,reels_comments --max-items 20",
        "python -m higgsfield_scraper scrape showcase --what all --max-items 30   # + opt-in reels, login season",
        "python -m higgsfield_scraper scrape showcase --what main_feed --main-feed-pages 2   # home feed, by name",
    ),
)
