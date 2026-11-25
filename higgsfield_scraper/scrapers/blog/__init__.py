"""`blog` scraper: Higgsfield blog posts + authors, talent/community blog posts, Creator Hub help center, case studies,
changelog and the Enterprise help center — metadata and full article text. See docs/scrapers/blog.md."""
from __future__ import annotations

from ...core.base import ScraperDef
from .dataset import build_dataset, write_outputs
from .options import add_args, default_label, make_selection, selection_from_dict
from .parsers import keep, parse_envelope
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, BlogDataset


def media_urls(e: dict, mode: str) -> list[tuple[str, str]]:
    """thumbs = cover/card images; full/all = covers + every image/video URL found in the article body."""
    out: list[tuple[str, str]] = []
    cover = e.get("cover_url") or (e.get("cover") or {}).get("url") if isinstance(e.get("cover"), dict) or \
        e.get("cover_url") else None
    for role, url in (("cover", cover), ("card", e.get("card_url")), ("photo", e.get("photo_url")),
                      ("card", e.get("card_image_url"))):
        if url:
            out.append((role, url))
    if mode in ("full", "all"):
        if e.get("hero_media_url"):
            out.append(("hero", e["hero_media_url"]))
        for i, img in enumerate(e.get("images") or []):
            if img.get("url") and (mode == "all" or img.get("kind") != "embed"):
                out.append((f"img{i:03d}", img["url"]))
    return list(dict.fromkeys(out))


SCRAPER = ScraperDef(
    name="blog",
    description="Blog posts + authors, talent/community posts, Creator Hub help center, case studies, changelog, "
                "Enterprise help center — metadata and full article text (Markdown/plain text)",
    spider_cls="higgsfield_scraper.scrapers.blog.spider:BlogSpider",
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
    optional_endpoints=frozenset({"blog_author", "post_content"}),
    media_urls=media_urls,
    counts_key="counts",
    dataset_model=BlogDataset,
    examples=(
        "scrape blog",
        "scrape blog --what help,enterprise-help --label help-only",
        "scrape blog --what blog --since 2026-10-01 --tags guides,comparisons",
        "scrape blog --no-content --label metadata-only",
        "scrape blog --what talents,community --max-pages 3",
        "scrape blog --what blog --download-media thumbs",
    ),
)
