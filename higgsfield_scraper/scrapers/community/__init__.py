"""`community` scraper: public Higgsfield community generations (prompts, settings, models, results, engagement).

See docs/scrapers/community.md. Spider is referenced lazily (no spider import here).
"""
from __future__ import annotations

from ...core.base import ScraperDef
from .dataset import build_dataset, write_outputs
from .endpoints import (BENEFITS_ENDPOINT, COMMENTS_ENDPOINT, COMPARE_ENDPOINT, DETAIL_ENDPOINT,
                        JOB_COSTS_ENDPOINT, PLANS_ENDPOINT, VIRAL_ENDPOINT)
from .options import add_args, default_label, make_selection, selection_from_dict
from .parsers import keep, parse_envelope
from .schemas import (CommunityComment, CommunityCostBasis, CommunityCreator, CommunityCreatorStats, CommunityDataset,
                      CommunityFeedItem, CommunityGeneration, CommunityPage, CommunityPost, CommunityShot)
from .schemas import (CommunityCollection, CommunityExploreCard, CommunityMusicCard, CommunityMusicCardOption,
                      CommunityShowcaseJob)
from .schemas import CommunityCreatorWork, CommunityFeedCategory, CommunityShotModelFacet


def media_urls(entity: dict, mode: str) -> list[tuple[str, str]]:
    """--download-media: thumbs -> preview ('min' image / video thumbnail); full -> 'raw' (+ 'h264' mp4 for video);
    all -> every result variant except the HLS playlist, thumbnails, and the input media."""
    if mode == "none":
        return []
    if entity.get("kind") in ("community_shot", "community_feed_item", "community_post"):
        return _extra_media(entity, mode)
    if entity.get("kind") in GALLERY_MEDIA_KINDS:
        return _gallery_media(entity, mode)
    if entity.get("kind") == "community_creator_work":
        return _creator_work_media(entity, mode)
    if entity.get("kind") == "community_feed_category":
        return [(f"preview{i}", u) for i, u in enumerate(entity.get("previews") or [])
                if mode != "none" and u.startswith("http")]
    if entity.get("kind") != "community_generation":
        return []
    res = {r["name"]: r for r in entity.get("results") or []}
    video = entity.get("media_type") == "video"
    out: list[tuple[str, str]] = []
    if mode == "thumbs":
        r = res.get("min") or res.get("raw") or res.get("result") or {}
        url = (r.get("thumbnail_url") or (res.get("raw") or {}).get("thumbnail_url")) if video else r.get("url")
        if url:
            out.append(("thumb", url))
    elif mode == "full":
        r = res.get("raw") or res.get("result") or {}
        if r.get("url"):
            out.append(("raw", r["url"]))
        if video and (res.get("h264") or {}).get("url"):
            out.append(("h264", res["h264"]["url"]))
    elif mode == "all":
        for name, r in res.items():
            if name != "hls" and r.get("url"):
                out.append((name, r["url"]))
            if r.get("thumbnail_url"):
                out.append((f"{name}_thumb", r["thumbnail_url"]))
        for i in entity.get("inputs") or []:
            if i.get("url"):
                out.append((f"input{i['index']}_{i.get('param')}", i["url"]))
    seen: set[str] = set()
    return [(role, u) for role, u in out if not (u in seen or seen.add(u))]


def _extra_media(e: dict, mode: str) -> list[tuple[str, str]]:
    """Opt-in feeds: thumbs = thumbnail/cover (or the preview image); full/all = + preview media and videos."""
    out: list[tuple[str, str]] = []
    thumb = e.get("thumbnail_url") or e.get("cover_url") or (e.get("media_url") if e.get("media_type") == "image"
                                                             else None)
    if thumb:
        out.append(("thumb", thumb))
    if mode in ("full", "all"):
        for k in ("media_url", "video_url"):
            if e.get(k):
                out.append((k.removesuffix("_url"), e[k]))
        for m in e.get("media") or []:
            for k in ("card_cover_url", "video_thumbnail_url", "video_url", "url"):
                if m.get(k):
                    out.append((f"media{m['index']}_{k.removesuffix('_url')}", m[k]))
    seen: set[str] = set()
    return [(r, u) for r, u in out if u.startswith("http") and ".m3u8" not in u and not (u in seen or seen.add(u))]


def _creator_work_media(e: dict, mode: str) -> list[tuple[str, str]]:
    """Creator / talent works: shots like community generations; projects: thumbs = cover, full/all = + gallery
    videos (original / download / preview mp4, never the HLS playlist) and the trailer."""
    if e.get("item_type") != "project":
        return media_urls({**e, "kind": "community_generation"}, mode) if e.get("results") else []
    out: list[tuple[str, str]] = []
    if e.get("cover_url"):
        out.append(("thumb", e["cover_url"]))
    if mode in ("full", "all"):
        for m in e.get("gallery_media") or []:
            if m.get("role") == "cover":
                continue
            u = m.get("original_url") or m.get("download_url") or m.get("preview_url") or m.get("url")
            if u:
                out.append((f"{m['role']}{m['index']}", u))
            if mode == "all" and m.get("thumbnail_url"):
                out.append((f"{m['role']}{m['index']}_thumb", m["thumbnail_url"]))
    seen: set[str] = set()
    return [(r, u) for r, u in out if u.startswith("http") and ".m3u8" not in u and not (u in seen or seen.add(u))]


GALLERY_MEDIA_KINDS = ("community_showcase_job", "community_music_card", "community_explore_card",
                       "community_collection")


def _gallery_media(e: dict, mode: str) -> list[tuple[str, str]]:
    """Opt-in galleries / templates: thumbs = poster / thumbnail / preview image; full = + the main video
    (showcase jobs: raw + h264, like community generations); all = every variant (+ showcase inputs)."""
    out: list[tuple[str, str]] = []
    k = e.get("kind")
    if k == "community_showcase_job":
        res = {r["name"]: r for r in e.get("results") or []}
        thumb = (res.get("min") or {}).get("thumbnail_url") or (res.get("raw") or {}).get("thumbnail_url")
        if thumb:
            out.append(("thumb", thumb))
        if mode == "full":
            out += [(n, res[n]["url"]) for n in ("raw", "h264") if (res.get(n) or {}).get("url")]
        elif mode == "all":
            for name, r in res.items():
                if name != "hls" and r.get("url"):
                    out.append((name, r["url"]))
                if r.get("thumbnail_url"):
                    out.append((f"{name}_thumb", r["thumbnail_url"]))
            out += [(f"input{i['index']}_{i.get('param')}", i["url"]) for i in e.get("inputs") or [] if i.get("url")]
    elif k == "community_music_card":
        for role, f in (("thumb", "thumbnail_url"), ("poster", "preview_video_thumbnail_url")):
            if e.get(f) and (role == "thumb" or mode != "thumbs"):
                out.append((role, e[f]))
        if mode in ("full", "all") and e.get("preview_video_url"):
            out.append(("video", e["preview_video_url"]))
        if mode == "all" and e.get("preview_video_compressed_url"):
            out.append(("video_compressed", e["preview_video_compressed_url"]))
    elif k == "community_explore_card":
        if e.get("media_url") and (mode != "thumbs" or e.get("media_type") == "image"):
            out.append(("media", e["media_url"]))
    elif k == "community_collection":
        out += [(f"item{i['position']}", i["media_url"]) for i in e.get("items") or [] if i.get("media_url")]
    seen: set[str] = set()
    return [(r, u) for r, u in out if u.startswith("http") and ".m3u8" not in u and not (u in seen or seen.add(u))]


SCRAPER = ScraperDef(
    name="community",
    description="Community generations: model (job_set_type), prompt, settings, inputs, results, engagement; "
                "optional creator profiles (opt-in), detail, Community-post comments and estimated credit cost",
    spider_cls="higgsfield_scraper.scrapers.community.spider:CommunitySpider",
    model_by_kind={"community_generation": CommunityGeneration, "community_creator": CommunityCreator,
                   "community_comment": CommunityComment, "community_page": CommunityPage,
                   "community_cost_basis": CommunityCostBasis, "community_shot": CommunityShot,
                   "community_post": CommunityPost, "community_feed_item": CommunityFeedItem,
                   "community_creator_stats": CommunityCreatorStats, "community_music_card": CommunityMusicCard,
                   "community_music_card_option": CommunityMusicCardOption,
                   "community_showcase_job": CommunityShowcaseJob, "community_collection": CommunityCollection,
                   "community_explore_card": CommunityExploreCard, "community_creator_work": CommunityCreatorWork,
                   "community_shot_model_facet": CommunityShotModelFacet,
                   "community_feed_category": CommunityFeedCategory},
    id_field_by_kind={"community_generation": "generation_id", "community_creator": "user_id",
                      "community_comment": "comment_id", "community_page": "page_id",
                      "community_cost_basis": "basis_id", "community_shot": "shot_id",
                      "community_post": "post_id", "community_feed_item": "feed_item_id",
                      "community_creator_stats": "record_id", "community_music_card": "music_card_id",
                      "community_music_card_option": "option_id", "community_showcase_job": "generation_id",
                      "community_collection": "collection_id", "community_explore_card": "card_id",
                      "community_creator_work": "work_id", "community_shot_model_facet": "facet_id",
                      "community_feed_category": "category_id"},
    add_args=add_args,
    make_selection=make_selection,
    selection_from_dict=selection_from_dict,
    parse_envelope=parse_envelope,
    keep=keep,
    build_dataset=build_dataset,
    write_outputs=write_outputs,
    default_label=default_label,
    optional_endpoints=frozenset({COMMENTS_ENDPOINT, DETAIL_ENDPOINT, JOB_COSTS_ENDPOINT, PLANS_ENDPOINT,
                                  COMPARE_ENDPOINT, BENEFITS_ENDPOINT, VIRAL_ENDPOINT}),
    personal_data=True,               # archives redacted unless --with-profiles
    media_urls=media_urls,
    dataset_model=CommunityDataset,
    examples=(
        "scrape community --max-items 300",
        "scrape community --feeds approved --type video --max-items 100",
        "scrape community --feeds trending --models nano_banana_2,seedream_v4_5 --max-items 500",
        "scrape community --max-items 200 --estimate-cost all",
        "scrape community --max-items 50 --with-profiles --download-media thumbs",
        "scrape community --feeds shots,posts,feed --max-items 100 --with-comments",
        "scrape community --feeds creators,talents",
        "scrape community --feeds feed-categories",
    ),
)
