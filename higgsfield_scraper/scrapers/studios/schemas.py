"""Pydantic v2 models of the studios scraper (source of truth; Scrapy items are generated from them).

Every entity carries: a stable natural-key `id` (make_id), `source_url` (a page or API URL a person can open),
`scraped_at` (UTC), `schema_version`, and `source: Provenance` (the exact request). Generation-like entities
(gallery items) also carry `generation_key` (`job:<job id>`, else `media:<CDN file id>`) and
`media_keys` so `scripts/merge_generations.py` deduplicates them across scrapers.

Personal data: authors are `author_key` (sha256-16 of the Clerk user id, same hash as showcase `creator_key`) unless
`--with-profiles`, which adds `author` (user_id, name, avatar_url). CDN media URLs keep `user_…` path segments.

ER diagram: docs/scrapers/studios.md §4.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta
from ...schemas.common import Provenance, Strict

ENTITY_SCHEMA_VERSION = 1


class Media(Strict):
    role: str = Field(description="what the file is: cover|cover_video|logo|preview|poster|video|game|result_raw|"
                                  "result_min|thumbnail|input|example|character|generated|…")
    type: Optional[str] = Field(None, description="video|image|audio|hls|file (API `type`, else the extension)")
    url: str
    width: Optional[int] = Field(None, description="pixels")
    height: Optional[int] = Field(None, description="pixels")
    duration_s: Optional[float] = Field(None, description="seconds")
    media_key: Optional[str] = Field(None, description="CDN file id: the API media id, else the last UUID in the URL")


class Author(Strict):
    """Only with --with-profiles."""
    user_id: Optional[str] = None
    name: Optional[str] = Field(None, description="username / display name shown on the card")
    avatar_url: Optional[str] = None


class _Entity(Strict):
    id: str = Field(description="stable 16-hex id = make_id(kind, natural key)")
    source_url: str = Field(description="page or API URL where a person can see this record")
    scraped_at: AwareDatetime
    schema_version: int = ENTITY_SCHEMA_VERSION
    source: Provenance


class _Authored(_Entity):
    author_key: Optional[str] = Field(None, description="pseudonymous author: make_id('creator', user_id)")
    creator_uid_key: Optional[str] = Field(None, description="shared creator key across scrapers: "
                                                             "core.privacy.creator_uid_key(<Clerk user id>) (same "
                                                             "hash as author_key)")
    author: Optional[Author] = Field(None, description="only with --with-profiles")
    is_builtin: Optional[bool] = Field(None, description="made by Higgsfield (no community author)")


class _Generation(_Entity):
    generation_key: Optional[str] = Field(None, description="dedup key across scrapers: `job:<job id>`, else "
                                                            "`media:<CDN file id of the main output>`")
    media_keys: list[str] = Field(default_factory=list, description="every output media key (`media:<id>`)")


# ------------------------------------------------------------------ apps marketplace
class AppCategory(_Entity):
    slug: str
    label: Optional[str] = None
    description: Optional[str] = None
    position: Optional[int] = None
    app_types: list[str] = Field(default_factory=list, description="app | website | …")


class AppEngagement(Strict):
    views: Optional[int] = Field(None, description="`views_count` (opens of the app)")
    likes: Optional[int] = Field(None, description="`likes_count`")
    dislikes: Optional[int] = Field(None, description="`dislikes_count`")
    remixes: Optional[int] = Field(None, description="`remixes_count` (copies made with Remix)")
    credits_usage: Optional[float] = Field(None, description="`credits_usage`: credits users spent inside the app "
                                                             "(the web UI rounds it)")


class App(_Authored):
    """One community app listing: GET fnf-apps-marketplace/api/v1/apps/community (also /community/{id})."""
    listing_id: str = Field(description="`id` (community listing; detail path id)")
    app_id: Optional[str] = Field(None, description="`app_id` (the user's app project)")
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = Field(None, description="category slug (app_categories.slug)")
    app_type: Optional[str] = Field(None, description="`type`: app | website (UI default website)")
    app_url: Optional[str] = Field(None, description="live app on <slug>.higgsfield.app")
    preview_url: Optional[str] = None
    media: list[Media] = Field(default_factory=list, description="logo, cover, cover_video, marketplace_cover")
    engagement: AppEngagement
    is_featured: Optional[bool] = None
    is_higgsfield: Optional[bool] = None
    is_pinned: Optional[bool] = None
    remix_allowed: Optional[bool] = None
    main_page_position: Optional[int] = None
    published_at: Optional[AwareDatetime] = None
    sort: Optional[str] = Field(None, description="listing order the row came from (trending|most_viewed|…)")
    rank: Optional[int] = Field(None, description="0-based position in that listing")


# ------------------------------------------------------------------ games / skills / employees (fnf-skills-marketplace)
class Game(_Authored):
    listing_id: str
    game_id: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = Field(None, description="`category_id`")
    game_url: Optional[str] = Field(None, description="playable build on <slug>.higgsfield.app")
    source_zip_url: Optional[str] = Field(None, description="`source_url`: downloadable game source (zip)")
    remixed_from: Optional[str] = Field(None, description="`remixed_from_community_game_id`")
    media: list[Media] = Field(default_factory=list)
    plays: Optional[int] = Field(None, description="`plays_count`")
    unique_players: Optional[int] = Field(None, description="`unique_players_count`")
    remixes: Optional[int] = Field(None, description="`remixes_count`")
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    rank: Optional[int] = None


class Skill(_Authored):
    skill_id: str
    name: Optional[str] = None
    display_name: Optional[str] = None
    canonical_slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    sub_title: Optional[str] = None
    example_prompt: Optional[str] = None
    category: Optional[str] = Field(None, description="`category_id`")
    color: Optional[str] = None
    media: list[Media] = Field(default_factory=list, description="preview_urls")
    installs: Optional[int] = Field(None, description="`installs_count`")
    unique_users: Optional[int] = Field(None, description="`unique_users_count`")
    usage: Optional[int] = Field(None, description="`usage_count` (skill invocations)")
    content_url: Optional[str] = Field(None, description="SKILL.md text endpoint (not fetched)")
    reference_paths: list[str] = Field(default_factory=list)
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    rank: Optional[int] = None


class Feature(Strict):
    icon: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class Employee(_Authored):
    """An AI employee (`ai-agents`) listed on /marketplace/employees."""
    employee_id: str
    name: Optional[str] = None
    display_name: Optional[str] = None
    canonical_slug: Optional[str] = Field(None, description="built-ins: /marketplace/employees/<slug>")
    sub_title: Optional[str] = None
    description: Optional[str] = None
    public_md: Optional[str] = Field(None, description="public instructions page (markdown)")
    example_prompt: Optional[str] = None
    category: Optional[str] = Field(None, description="`category_id`")
    visibility: Optional[str] = None
    color: Optional[str] = None
    skill_pool_mode: Optional[str] = None
    connector_pool_mode: Optional[str] = None
    orchestrated_skills: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    media: list[Media] = Field(default_factory=list, description="avatar, previews, examples (`examples_section`)")
    installs: Optional[int] = Field(None, description="`installs_count`")
    unique_users: Optional[int] = Field(None, description="`unique_users_count`")
    usage: Optional[int] = Field(None, description="`usage_count` (runs)")
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    rank: Optional[int] = None


# ------------------------------------------------------------------ CMS: playable presets / AI influencer options
class PlayablePreset(_Entity):
    """/playable-ads 'explore' preset: a finished playable ad + the prompt/settings to recreate it."""
    preset_id: str
    title: Optional[str] = None
    category: Optional[str] = Field(None, description="genre: action|adventure|maze|puzzles|runners|shooters|…")
    priority: Optional[int] = None
    recreate_prompt: Optional[str] = Field(None, description="`recreate.prompt` (prefilled into the generator)")
    recreate_game_type: Optional[str] = None
    recreate_dimension: Optional[str] = None
    recreate_mode: Optional[str] = None
    media: list[Media] = Field(default_factory=list, description="poster, vertical_poster, covers, video(s), "
                                                                  "input_video, game/widescreen_game (HTML builds)")
    lang: str


class InfluencerOption(_Entity):
    """One choice of the AI Influencer builder (`/ai-influencer-config`): category > subcategory > option."""
    category_key: str
    category_label: Optional[str] = None
    category_is_advanced: Optional[bool] = None
    subcategory_key: str
    subcategory_label: Optional[str] = None
    max_selections: Optional[int] = None
    required_selections: Optional[int] = None
    default_option: Optional[str] = None
    option_key: str
    option_label: Optional[str] = None
    option_type: Optional[str] = Field(None, description="text | card | color-picker | …")
    position: int = Field(description="0-based position inside the subcategory")
    media: list[Media] = Field(default_factory=list)
    lang: str


# ------------------------------------------------------------------ studio galleries (published outputs) + comments
class GalleryEngagement(Strict):
    views: Optional[int] = Field(None, description="`publication.views_count`")
    likes: Optional[int] = Field(None, description="`publication.likes_count`")


class GalleryItem(_Generation):
    """A published generation of a studio (community approved / trending feed filtered by the studio's models)."""
    job_id: str = Field(description="`id` (job id)")
    job_set_id: Optional[str] = None
    job_set_type: str = Field(description="model / tool (`job_set_type`)")
    studio: str = Field(description="studio this job_set_type belongs to (endpoints.STUDIO_MODELS)")
    feed: Literal["approved", "trending"]
    publication_id: Optional[str] = None
    approved: Optional[bool] = None
    pinned_at: Optional[AwareDatetime] = None
    status: Optional[str] = None
    prompt: Optional[str] = None
    enhanced_prompt: Optional[str] = None
    preset: Optional[str] = Field(None, description="preset/template used: params.preset id|slug, else "
                                                    "mode/specific_mode, else style/genre")
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    duration_s: Optional[float] = None
    settings: dict[str, Any] = Field(default_factory=dict, description="every other `params` field (scalars, lists "
                                                                         "and objects as returned)")
    inputs: list[Media] = Field(default_factory=list, description="input media (`params.medias`, `input_images`, "
                                                                   "…) — user uploads, never generation keys")
    media: list[Media] = Field(default_factory=list, description="results raw/min/hls/h264 (+ thumbnails)")
    engagement: GalleryEngagement
    published_at: Optional[AwareDatetime] = None
    created_at: Optional[AwareDatetime] = None
    author_key: Optional[str] = Field(None, description="pseudonymous author (sha of `user_id` if real, else of "
                                                        "the profile username)")
    creator_uid_key: Optional[str] = Field(None, description="shared creator key across scrapers: "
                                                             "core.privacy.creator_uid_key(<Clerk user id>); null when "
                                                             "author_key falls back to the username")
    author: Optional[Author] = None
    rank: Optional[int] = Field(None, description="0-based position in the feed (page*size + index)")


class Comment(_Entity):
    comment_id: str
    publication_id: str = Field(description="gallery item `publication_id`")
    entity_type: str = Field(description="generation_publication")
    parent_id: Optional[str] = None
    content: Optional[str] = None
    likes: Optional[int] = Field(None, description="`like_count`")
    dislikes: Optional[int] = Field(None, description="`dislike_count`")
    replies: Optional[int] = Field(None, description="`reply_count`")
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    author_key: Optional[str] = None
    creator_uid_key: Optional[str] = Field(None, description="shared creator key across scrapers (same hash)")
    author: Optional[Author] = None


MODEL_BY_KIND: dict[str, type[_Entity]] = {
    "studios_app_category": AppCategory,
    "studios_app": App,
    "studios_game": Game,
    "studios_skill": Skill,
    "studios_employee": Employee,
    "studios_playable_preset": PlayablePreset,
    "studios_influencer_option": InfluencerOption,
    "studios_gallery_item": GalleryItem,
    "studios_comment": Comment,
}
ID_FIELD_BY_KIND = {k: "id" for k in MODEL_BY_KIND}
COLLECTION_OF = {
    "studios_app_category": "app_categories",
    "studios_app": "apps",
    "studios_game": "games",
    "studios_skill": "skills",
    "studios_employee": "employees",
    "studios_playable_preset": "playable_presets",
    "studios_influencer_option": "influencer_options",
    "studios_gallery_item": "gallery_items",
    "studios_comment": "comments",
}


class Summary(Strict):
    counts: dict[str, int] = Field(default_factory=dict)
    totals_available: dict[str, Optional[int]] = Field(default_factory=dict)
    by_source: dict[str, dict[str, int]] = Field(default_factory=dict)
    generation_keys: int = 0
    engagement: dict[str, dict[str, int]] = Field(default_factory=dict,
                                                   description="sums of views/likes/plays/usage per collection")


class StudiosDataset(Strict):
    schema_version: Literal[1] = 1
    meta: CoreMeta
    summary: Summary
    app_categories: list[AppCategory] = Field(default_factory=list)
    apps: list[App] = Field(default_factory=list)
    games: list[Game] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    employees: list[Employee] = Field(default_factory=list)
    playable_presets: list[PlayablePreset] = Field(default_factory=list)
    influencer_options: list[InfluencerOption] = Field(default_factory=list)
    gallery_items: list[GalleryItem] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
