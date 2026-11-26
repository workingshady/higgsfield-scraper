"""`site` scraper: public higgsfield.ai pages not covered by the other scrapers — apps (with credit cost per
template), academy courses + lessons (Markdown), MCP skills + bundles, original-series episodes, mixed-media presets,
marketing/model/plugin landing pages (Markdown + FAQ/HowTo), optional community rooms, and three small public promo
APIs. See docs/scrapers/site.md."""
from __future__ import annotations

from ...core.base import ScraperDef
from .dataset import build_dataset, write_outputs
from .options import add_args, default_label, make_selection, selection_from_dict
from .parsers import keep, parse_envelope
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, SiteDataset

_THUMB_KEYS = ("thumbnail_url", "cover_url", "portrait_url", "landscape_url", "logo_url")
_MEDIA_KEYS = ("media", "input_media", "card_preview", "cover_media", "preview_media", "example_result",
               "tutorial_media")


def _is_hls(u: str) -> bool:
    return u.split("?", 1)[0].endswith(".m3u8")


def media_urls(e: dict, mode: str) -> list[tuple[str, str]]:
    """thumbs = thumbnails/posters/covers; full = + videos and full-size media (no HLS playlists);
    all = + lesson resources (PDFs), landing/lesson inline images, mixed-media sample media."""
    out: list[tuple[str, str]] = []
    for k in _THUMB_KEYS:
        if isinstance(e.get(k), str):
            out.append((k.removesuffix("_url"), e[k]))
    for k in _MEDIA_KEYS:
        m = e.get(k)
        if isinstance(m, dict):
            if m.get("thumbnail_url"):
                out.append((f"{k}_thumb", m["thumbnail_url"]))
            if mode in ("full", "all") and m.get("url"):
                out.append((k, m["url"]))
    if mode in ("full", "all"):
        for k in ("video_url", "trailer_url"):
            if isinstance(e.get(k), str):
                out.append((k.removesuffix("_url"), e[k]))
    if mode == "all":
        for i, r in enumerate(e.get("resources") or []):
            if r.get("download_url"):
                out.append((f"resource{i:02d}", r["download_url"]))
        for i, img in enumerate(e.get("images") or []):
            if img.get("url"):
                out.append((f"img{i:03d}", img["url"]))
        for i, s in enumerate(e.get("samples") or []):
            m = s.get("media") or {}
            if m.get("url"):
                out.append((f"sample{i:02d}", m["url"]))
    return [(r, u) for r, u in dict.fromkeys(out) if u.startswith("http") and not _is_hls(u)]


SCRAPER = ScraperDef(
    name="site",
    description="Site pages: apps (+ credit cost), academy courses & lessons (Markdown), MCP skills & bundles, "
                "original-series episodes, mixed-media presets, landing/plugin pages, rooms (opt-in), promo APIs",
    spider_cls="higgsfield_scraper.scrapers.site.spider:SiteSpider",
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
    optional_endpoints=frozenset({"apps_sitemap", "academy_sitemap", "originals_sitemap", "room_page", "landing_page",
                                 "mixed_media_page", "episode_page"}),   # sitemaps list some dead (404) pages
    media_urls=media_urls,
    counts_key="counts",
    dataset_model=SiteDataset,
    personal_data=True,               # mixed-media samples / episodes / app authors: archives redacted unless --with-profiles
    examples=(
        "scrape site",
        "scrape site --what apps --label apps",
        "scrape site --what academy --only blockbuster-4k",
        "scrape site --what mcp,promos --no-content",
        "scrape site --what landings --only /plugins/,kling --max-items 10",
        "scrape site --what originals,mixed-media --download-media thumbs",
        "scrape site --what all,rooms --max-items 20 --label smoke-site",
        "scrape site --what room-content --max-items 50 --label rooms",
    ),
)
