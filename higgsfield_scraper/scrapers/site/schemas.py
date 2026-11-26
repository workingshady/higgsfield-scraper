"""Pydantic models for the site scraper (one per kind) + SiteDataset.

Every record has a stable id (UUID from the site, or `make_id(<natural key>)`), its page `url`, and `source`
(Provenance: endpoint, URL, fetched_at). `schema_version` and `scraped_at` are on the dataset (`meta.scraped_at`).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta, Provenance, Strict
from ..blog.schemas import FaqItem, Heading, Image, Link
from ..community.schemas import CommunityPost

RecordSource = Literal["page", "index", "sitemap"]


class Media(Strict):
    url: Optional[str] = None
    type: Optional[str] = Field(None, description="video | image | static | …")
    thumbnail_url: Optional[str] = Field(None, description="poster / thumbnail")
    width: Optional[int] = None
    height: Optional[int] = None


class Body(Strict):
    """Page text converted to Markdown (filled with --with-content, the default)."""

    content_format: Optional[Literal["html", "hast"]] = Field(
        None, description="hast = academy lesson mdxTree; html = landing <main>")
    content_markdown: Optional[str] = None
    content_text: Optional[str] = Field(None, description="plain text (Markdown syntax stripped)")
    word_count: Optional[int] = None
    headings: list[Heading] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)


class Seo(Strict):
    page_title: Optional[str] = None
    meta_description: Optional[str] = None
    keywords: Optional[str] = None
    canonical: Optional[str] = None
    og_image: Optional[str] = None
    robots: Optional[str] = None


# ------------------------------------------------------------------ apps

class AppTemplate(Strict):
    role: Literal["image", "video", "animate"]
    preset: Literal["primary", "secondary"] = Field("primary", description="secondary = the page's secondaryAppPreset "
                                                    "(e.g. video face swap on /apps/face-swap)")
    preset_slug: Optional[str] = None
    slug: Optional[str] = None
    cost_credits: Optional[Decimal] = Field(None, description="credits per generation shown by the app (template.cost)")
    input_types: list[str] = Field(default_factory=list, description="image | video | text … per template input")


class AppCategory(Strict):
    """kind=site_app_category — a tab of /apps (also a page /apps/<category-slug>)."""

    category_id: str
    slug: str
    url: str
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    priority: Optional[int] = None
    app_slugs: list[str] = Field(default_factory=list)
    source: Provenance


class App(Strict):
    """kind=site_app — one Higgsfield app (/apps/<slug>): what it does, its templates and their credit cost."""

    record_key: str = Field(description="<slug>@<record_source>; index and page records are merged by slug")
    app_id: str = Field(description="appPreset id (UUID); index-only records use the card id")
    slug: str
    url: str
    title: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    media_description: Optional[str] = None
    page_kind: Optional[str] = Field(None, description="loader kind: custom | app (category pages are categories)")
    slug_type: Optional[str] = Field(None, description="internal app/template family, e.g. qwen-camera-control")
    preset_type: Optional[str] = Field(None, description="appPreset.type, e.g. nano_banana")
    is_only_video_allowed: Optional[bool] = None
    category_slugs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, description="card badges (PRO, NEW, …)")
    upload_date: Optional[AwareDatetime] = None
    media: Optional[Media] = None
    input_media: Optional[Media] = None
    card_preview: Optional[Media] = None
    templates: list[AppTemplate] = Field(default_factory=list)
    min_cost_credits: Optional[Decimal] = None
    max_cost_credits: Optional[Decimal] = None
    author_name: Optional[str] = Field(None, description="creator of a community app (only with --with-profiles)")
    has_author: bool = False
    landing_how_to_title: Optional[str] = None
    landing_how_to: list[dict[str, Any]] = Field(default_factory=list)
    landing_showcase: list[dict[str, Any]] = Field(default_factory=list)
    landing_info_title: Optional[str] = None
    landing_info_description: Optional[str] = None
    landing_info_items: list[dict[str, Any]] = Field(default_factory=list)
    landing_faqs: list[FaqItem] = Field(default_factory=list)
    landing_cta_title: Optional[str] = None
    landing_cta_description: Optional[str] = None
    secondary_preset_slug: Optional[str] = None
    seo: Optional[Seo] = None
    record_source: RecordSource = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


# ------------------------------------------------------------------ academy

class AcademyCategory(Strict):
    """kind=site_academy_category"""

    category_id: str
    slug: str
    title: Optional[str] = None
    description: Optional[str] = None
    artwork: Optional[str] = None
    source: Provenance


class CourseObjective(Strict):
    title: str
    description: Optional[str] = None


class CourseAuthor(Strict):
    name: Optional[str] = None
    role: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None


class LessonRef(Strict):
    lesson_id: str
    slug: str
    url: str
    title: Optional[str] = None
    position: Optional[int] = None
    reading_minutes: Optional[int] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    homework_required: Optional[bool] = None


class Course(Strict):
    """kind=site_academy_course — /academy/courses/<slug>."""

    record_key: str = Field(description="<slug>@<record_source>; index and page records are merged by slug")
    course_id: str
    slug: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    duration_minutes: Optional[int] = None
    reading_minutes: Optional[int] = None
    lesson_count: Optional[int] = None
    categories: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    preview_media: Optional[Media] = None
    has_certificate: Optional[bool] = None
    has_examples: Optional[bool] = None
    has_creator_drop: Optional[bool] = None
    featured_position: Optional[int] = None
    published_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    objectives: list[CourseObjective] = Field(default_factory=list)
    authors: list[CourseAuthor] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    lessons: list[LessonRef] = Field(default_factory=list)
    seo: Optional[Seo] = None
    record_source: RecordSource = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class LessonResource(Strict):
    type: Optional[str] = None
    name: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    page_count: Optional[int] = None


class Lesson(Body):
    """kind=site_academy_lesson — /academy/courses/<course>/<lesson>, text as Markdown."""

    lesson_id: str
    slug: str
    course_slug: str
    course_id: Optional[str] = None
    course_title: Optional[str] = None
    url: str
    title: Optional[str] = None
    position: Optional[int] = None
    xp_reward: Optional[int] = None
    reading_minutes: Optional[int] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    video_poster_url: Optional[str] = None
    video_subtitles: list[dict[str, Any]] = Field(default_factory=list)
    video_cues: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[LessonResource] = Field(default_factory=list)
    homework_required: Optional[bool] = None
    access_allowed: Optional[bool] = None
    next_lesson_slug: Optional[str] = None
    seo: Optional[Seo] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


# ------------------------------------------------------------------ academy JSON API (opt-in --what academy-api)
# fnf-academy /api/v1/*. Separate kinds from the SSR academy records above (those stay byte-identical). Per-viewer
# state (completed, progress_pct, homework_submitted, certificate_unlocked) is never stored.

class AcademyApiCategory(Strict):
    """kind=site_academy_api_category — GET fnf-academy /api/v1/categories."""

    category_id: str
    slug: str
    title: Optional[str] = None
    description: Optional[str] = None
    artwork: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class AcademyApiLessonRef(Strict):
    lesson_id: str
    slug: str
    url: str
    title: Optional[str] = None
    position: Optional[int] = None
    reading_minutes: Optional[int] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    video_poster_url: Optional[str] = None
    homework_required: Optional[bool] = None
    access_allowed: Optional[bool] = Field(None, description="access.allowed for an anonymous visitor")
    access_reason: Optional[str] = None
    blocking_lesson_id: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict, description="other API keys (verified, layout, surface…)")


class AcademyApiCourse(Strict):
    """kind=site_academy_api_course — /api/v1/courses (record_source=list) + /api/v1/courses/<slug> (detail),
    merged by slug in the dataset (detail wins, the list fills e.g. test_count / lesson_count)."""

    record_key: str = Field(description="<slug>@<record_source>")
    course_id: str
    slug: str
    url: str = Field(description="public page of the course")
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    duration_minutes: Optional[int] = None
    reading_minutes: Optional[int] = None
    lesson_count: Optional[int] = None
    test_count: Optional[int] = None
    free_generations: Optional[int] = Field(None, description="free generations granted by the course (API only)")
    categories: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    preview_media: Optional[Media] = None
    has_certificate: Optional[bool] = None
    has_examples: Optional[bool] = None
    has_creator_drop: Optional[bool] = None
    featured_position: Optional[int] = None
    published_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    objectives: list[CourseObjective] = Field(default_factory=list)
    authors: list[CourseAuthor] = Field(default_factory=list, description="course authors (Higgsfield staff)")
    skills: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)
    lessons: list[AcademyApiLessonRef] = Field(default_factory=list)
    record_source: Literal["list", "detail"] = "detail"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class AcademyApiLesson(Strict):
    """kind=site_academy_api_lesson — GET fnf-academy /api/v1/lessons/<lesson_id> (one request per lesson)."""

    lesson_id: str
    slug: str
    course_slug: Optional[str] = None
    course_id: Optional[str] = None
    url: str
    title: Optional[str] = None
    position: Optional[int] = Field(None, description="from the course's lesson list")
    xp_reward: Optional[int] = None
    thumbnail_url: Optional[str] = None
    video_url: Optional[str] = None
    video_poster_url: Optional[str] = None
    video_subtitles: list[dict[str, Any]] = Field(default_factory=list, description="[{src, language, label}] VTT")
    video_thumbnails_url: Optional[str] = Field(None, description="thumbnail-sprite VTT")
    video_cues: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[LessonResource] = Field(default_factory=list)
    author: Optional[CourseAuthor] = None
    access_allowed: Optional[bool] = None
    updated_at: Optional[AwareDatetime] = None
    content_mdx: Optional[str] = Field(None, description="lesson body as the API sends it (MDX / Markdown source)")
    word_count: Optional[int] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


# ------------------------------------------------------------------ MCP

class AgentLink(Strict):
    agent: str = Field(description="chatgpt | claude | claude-code | …")
    destination: Optional[str] = None
    label: Optional[str] = None
    prompt: Optional[str] = None
    installations: list[dict[str, Any]] = Field(default_factory=list)


class ConversationMessage(Strict):
    message_id: Optional[str] = None
    role: Optional[str] = None
    text: Optional[str] = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class McpSkill(Strict):
    """kind=site_mcp_skill — a Higgsfield MCP skill (/mcp/<slug>)."""

    record_key: str = Field(description="<slug>@<record_source>; index and page records are merged by slug")
    skill_id: str
    slug: str
    url: str
    title: Optional[str] = None
    card_title: Optional[str] = None
    skill_label: Optional[str] = Field(None, description="the /<command> name used in agents")
    description: Optional[str] = None
    short_description: Optional[str] = None
    overview_description: Optional[str] = None
    detail_title: Optional[str] = None
    external_url: Optional[str] = None
    is_indexable: Optional[bool] = None
    tags: list[str] = Field(default_factory=list)
    cover_media: Optional[Media] = None
    cover_alt: Optional[str] = None
    card_prompt: Optional[str] = None
    agents: list[AgentLink] = Field(default_factory=list)
    apps: list[dict[str, Any]] = Field(default_factory=list)
    installations: list[dict[str, Any]] = Field(default_factory=list)
    bundle_slugs: list[str] = Field(default_factory=list)
    example_result: Optional[Media] = None
    example_conversation: list[ConversationMessage] = Field(default_factory=list)
    medias: list[Media] = Field(default_factory=list)
    tutorial_title: Optional[str] = None
    tutorial_description: Optional[str] = None
    tutorial_media: Optional[Media] = None
    seo: Optional[Seo] = None
    record_source: RecordSource = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class McpBundle(Strict):
    """kind=site_mcp_bundle — a downloadable bundle of MCP skills (/mcp/bundles/<slug>)."""

    bundle_id: str
    slug: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    badge_label: Optional[str] = None
    skill_slugs: list[str] = Field(default_factory=list)
    prompt: Optional[str] = None
    download_url: Optional[str] = None
    chatgpt_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_image_url: Optional[str] = None
    is_indexable: Optional[bool] = None
    all_presets_order: Optional[int] = None
    cover_media: Optional[Media] = None
    agents: list[AgentLink] = Field(default_factory=list)
    record_source: RecordSource = "index"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


# ------------------------------------------------------------------ original series

class OriginalSeries(Strict):
    """kind=site_original_series — a Higgsfield original film/series (/original-series)."""

    series_id: str
    slug: str
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    full_description: Optional[str] = None
    author_type: Optional[str] = None
    series_type: Optional[str] = None
    is_series: Optional[bool] = None
    state: Optional[str] = None
    category_slugs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    duration_seconds: Optional[int] = None
    likes: Optional[int] = None
    views: Optional[int] = None
    comments: Optional[int] = None
    vote_count: Optional[int] = None
    subscriber_count: Optional[int] = None
    engagement_score: Optional[float] = None
    first_episode_id: Optional[str] = None
    first_episode_slug: Optional[str] = None
    project_publication_id: Optional[str] = None
    portrait_url: Optional[str] = None
    landscape_url: Optional[str] = None
    background_url: Optional[str] = None
    logo_url: Optional[str] = None
    trailer_url: Optional[str] = None
    trailer_hls_url: Optional[str] = None
    preview_video_url: Optional[str] = None
    in_hero: bool = False
    cast: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class EpisodeRef(Strict):
    episode_id: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[float] = None


class OriginalEpisode(Strict):
    """kind=site_original_episode — /original-series/<series>/<episode>."""

    episode_id: str
    slug: str
    series_slug: str
    series_id: Optional[str] = None
    series_title: Optional[str] = None
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    episode_type: Optional[str] = None
    likes: Optional[int] = None
    dislikes: Optional[int] = None
    views: Optional[int] = None
    total_views: Optional[int] = None
    video_url: Optional[str] = Field(None, description="HLS playlist (.m3u8)")
    thumbnail_url: Optional[str] = None
    youtube_url: Optional[str] = None
    is_adults_only: Optional[bool] = None
    created_at: Optional[AwareDatetime] = None
    episodes: list[EpisodeRef] = Field(default_factory=list, description="all episodes of the series")
    project_id: Optional[str] = None
    project_slug: Optional[str] = None
    project_title: Optional[str] = None
    project_type: Optional[str] = None
    project_views: Optional[int] = None
    project_likes: Optional[int] = None
    project_created_at: Optional[AwareDatetime] = None
    project_is_ongoing: Optional[bool] = None
    project_show_prompts: Optional[bool] = None
    uploader: Optional[str] = Field(None, description="uploader username (only with --with-profiles)")
    recommended_slugs: list[str] = Field(default_factory=list)
    seo: Optional[Seo] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


# ------------------------------------------------------------------ mixed media presets

class MixedMediaSample(Strict):
    sample_id: str
    job_id: Optional[str] = None
    job_set_type: Optional[str] = None
    media: Optional[Media] = None
    likes: Optional[int] = None
    creator: Optional[str] = Field(None, description="creator username (only with --with-profiles)")


class MixedMediaPreset(Strict):
    """kind=site_mixed_media_preset — /mixed-media-presets/preset/<id> (the API list needs a login)."""

    preset_id: str
    url: str
    name: Optional[str] = None
    description: Optional[str] = None
    sample_count: int = 0
    samples: list[MixedMediaSample] = Field(default_factory=list)
    samples_cursor: Optional[float] = None
    seo: Optional[Seo] = None
    source: Provenance


# ------------------------------------------------------------------ landings and rooms

class HowToStep(Strict):
    position: Optional[int] = None
    name: Optional[str] = None
    text: Optional[str] = None
    image: Optional[str] = None


class Landing(Body):
    """kind=site_landing — a marketing/model/feature landing page or plugin page (from sitemap-marketing.xml)."""

    page_id: str = Field(description="make_id(path)")
    path: str
    url: str
    page_type: Literal["landing", "plugin", "home", "room"] = "landing"
    h1: Optional[str] = None
    sections: list[str] = Field(default_factory=list, description="h2 headings in page order")
    breadcrumbs: list[str] = Field(default_factory=list)
    ld_types: list[str] = Field(default_factory=list, description="schema.org types found in JSON-LD")
    app_name: Optional[str] = Field(None, description="JSON-LD SoftwareApplication name")
    app_description: Optional[str] = None
    app_category: Optional[str] = None
    offer_price: Optional[Decimal] = Field(None, description="JSON-LD offers.price")
    offer_currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    offer_price_raw: Optional[str] = None
    how_to_name: Optional[str] = None
    how_to_steps: list[HowToStep] = Field(default_factory=list)
    faq: list[FaqItem] = Field(default_factory=list)
    seo: Optional[Seo] = None
    sitemap_lastmod: Optional[AwareDatetime] = None
    source: Provenance


# ------------------------------------------------------------------ promos (public JSON APIs)

class PromoEvent(Strict):
    """kind=site_promo_event — /datetime-settings: scheduled sales, free-generation windows, releases."""

    event_id: str = Field(description="the event `source` key, e.g. seedance_2_5_sale")
    starts_at: Optional[AwareDatetime] = None
    ends_at: Optional[AwareDatetime] = None
    params: dict[str, Any] = Field(default_factory=dict, description="non-null params only")
    source: Provenance


class BusinessUnlimOffer(Strict):
    """kind=site_business_unlim_offer — /business-unlim/state: unlimited-model trial cards for team plans."""

    offer_id: str = Field(description="make_id(section, billing_period, plan_type)")
    section: Literal["plan_card", "pricing_banner"]
    plan_type: Optional[str] = None
    billing_period: Optional[str] = None
    duration_days: Optional[int] = None
    model: Optional[str] = None
    max_duration_seconds: Optional[int] = None
    max_resolution: Optional[str] = None
    requires_business_verification: Optional[bool] = None
    models: list[dict[str, Any]] = Field(default_factory=list, description="other models and their unlimited status")
    source: Provenance


class GameGift(Strict):
    """kind=site_game_gift — /game-gift/networks: game-store gift card promo per network and country."""

    gift_id: str = Field(description="make_id(network, country)")
    network: str
    country_code: str
    fulfillment_mode: Optional[str] = None
    amount_label: Optional[str] = Field(None, description="as shown, e.g. '$100' (not converted)")
    source: Provenance


# ------------------------------------------------------------------ community rooms (fnf-community API, opt-in)
# Data model: docs/COMMUNITY_COVERAGE.md "Data model". Room records hold no personal data beyond pseudonymous ids;
# the owner's username only with --with-profiles.

class Room(Strict):
    """kind=site_room - a Community room (/community/rooms/<slug>) from GET fnf-community/rooms (+ room-stats)."""

    room_id: str = Field(description="room UUID (API `id`)")
    slug: str
    url: str = Field(description="https://higgsfield.ai/community/rooms/<slug>")
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    works_count: Optional[int] = Field(None, description="works (shots + projects + blog posts) in the room")
    works_shots: Optional[int] = Field(None, description="works_counts.shot")
    works_projects: Optional[int] = Field(None, description="works_counts.project_publication")
    works_blog_posts: Optional[int] = Field(None, description="works_counts.blog_post")
    followers_count: Optional[int] = Field(None, description="members (the UI calls followers 'members')")
    posts_count: Optional[int] = Field(None, description="room-stats `posts` (room works feed count)")
    discussions_count: Optional[int] = Field(None, description="room-stats `discussions` (discussion posts)")
    call_status: Optional[str] = Field(None, description="live voice room status: active | inactive")
    call_participants: Optional[int] = Field(None, description="call_status.participant_count (at fetch time)")
    owner_user_id: Optional[str] = Field(None, description="author.user_id (pseudonymous)")
    owner_username: Optional[str] = Field(None, description="only with --with-profiles")
    pinned: Optional[bool] = None
    members_can_post: Optional[bool] = None
    join_approval: Optional[bool] = None
    project_publication_id: Optional[str] = Field(None, description="room linked to a project (joins projects)")
    contest_id: Optional[str] = None
    original_space_id: Optional[str] = None
    works_preview_ids: list[str] = Field(default_factory=list, description="works_preview[].item_id (card preview)")
    created_at: Optional[AwareDatetime] = None
    position: Optional[int] = Field(None, description="0-based rank in the rooms API order (newest first)")
    source: Provenance


class RoomItem(Strict):
    """kind=site_room_item - one work in a room (GET fnf-community/rooms/{id}/items): a shot (gallery generation),
    a project publication or a blog post."""

    room_item_id: str = Field(description="space_item_id")
    room_id: str
    room_slug: Optional[str] = None
    item_type: Literal["shot", "project_publication", "blog_post", "unknown"]
    item_id: Optional[str] = Field(None, description="shot: publication id (joins community_generation."
                                   "publication_id); project: publication_id; blog: post id")
    generation_id: Optional[str] = Field(None, description="shot job id (joins community_generation.generation_id)")
    pinned: Optional[bool] = None
    position: Optional[int] = Field(None, description="0-based order in the room's works feed")
    url: Optional[str] = Field(None, description="shot page URL (projects/blogs need the author's username)")
    title: Optional[str] = Field(None, description="project name / blog title / shot prompt (first 200 chars)")
    slug: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = Field(None, description="shot params.prompt (full)")
    job_set_type: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = Field(None, description="shot raw result / project or blog cover")
    thumbnail_url: Optional[str] = None
    project_type: Optional[str] = Field(None, description="film | series | carousel")
    duration_seconds: Optional[float] = Field(None, description="project duration in seconds")
    reading_time_minutes: Optional[int] = None
    likes: Optional[int] = None
    views: Optional[int] = None
    comments: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    author_user_ids: list[str] = Field(default_factory=list, description="pseudonymous ids")
    created_at: Optional[AwareDatetime] = Field(None, description="published/created time of the work")
    source: Provenance


class RoomStats(Strict):
    """kind=site_room_stats - GET fnf-community/publications/room-stats?room_id=; merged into site_room
    (posts_count, discussions_count) by build_dataset, not a collection of its own."""

    room_id: str
    posts: Optional[int] = None
    discussions: Optional[int] = None


class RoomDiscussion(CommunityPost):
    """kind=site_room_discussion - a discussion post in a room (fnf-community /publications/feed?room_id=&kind=
    discussion): same fields as community_post plus the room slug."""

    room_slug: Optional[str] = None


MODEL_BY_KIND = {
    "site_app": App,
    "site_app_category": AppCategory,
    "site_academy_category": AcademyCategory,
    "site_academy_course": Course,
    "site_academy_lesson": Lesson,
    "site_mcp_skill": McpSkill,
    "site_mcp_bundle": McpBundle,
    "site_original_series": OriginalSeries,
    "site_original_episode": OriginalEpisode,
    "site_mixed_media_preset": MixedMediaPreset,
    "site_landing": Landing,
    "site_promo_event": PromoEvent,
    "site_business_unlim_offer": BusinessUnlimOffer,
    "site_game_gift": GameGift,
    "site_room": Room,
    "site_room_item": RoomItem,
    "site_room_discussion": RoomDiscussion,
    "site_room_stats": RoomStats,
    "site_academy_api_category": AcademyApiCategory,
    "site_academy_api_course": AcademyApiCourse,
    "site_academy_api_lesson": AcademyApiLesson,
}
ID_FIELD_BY_KIND = {
    "site_app": "record_key",
    "site_app_category": "slug",
    "site_academy_category": "slug",
    "site_academy_course": "record_key",
    "site_academy_lesson": "lesson_id",
    "site_mcp_skill": "record_key",
    "site_mcp_bundle": "slug",
    "site_original_series": "slug",
    "site_original_episode": "episode_id",
    "site_mixed_media_preset": "preset_id",
    "site_landing": "page_id",
    "site_promo_event": "event_id",
    "site_business_unlim_offer": "offer_id",
    "site_game_gift": "gift_id",
    "site_room": "room_id",
    "site_room_item": "room_item_id",
    "site_room_discussion": "post_id",
    "site_room_stats": "room_id",
    "site_academy_api_category": "slug",
    "site_academy_api_course": "record_key",
    "site_academy_api_lesson": "lesson_id",
}
# kinds counted by --max-items (per kind); index-level/aux kinds are never capped
PRIMARY_KINDS = ("site_app", "site_academy_course", "site_academy_lesson", "site_mcp_skill", "site_original_episode",
                 "site_mixed_media_preset", "site_landing", "site_room", "site_room_item", "site_room_discussion",
                 "site_academy_api_course", "site_academy_api_lesson")


class SiteSummary(Strict):
    apps_by_category: dict[str, int] = Field(default_factory=dict)
    app_cost_credits: dict[str, Optional[str]] = Field(default_factory=dict, description="slug -> min..max credits")
    lessons_by_course: dict[str, int] = Field(default_factory=dict)
    landings_by_type: dict[str, int] = Field(default_factory=dict)
    words_total: int = 0
    with_content: dict[str, int] = Field(default_factory=dict)


class SiteDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    apps: list[App] = Field(default_factory=list)
    app_categories: list[AppCategory] = Field(default_factory=list)
    academy_categories: list[AcademyCategory] = Field(default_factory=list)
    courses: list[Course] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)
    mcp_skills: list[McpSkill] = Field(default_factory=list)
    mcp_bundles: list[McpBundle] = Field(default_factory=list)
    original_series: list[OriginalSeries] = Field(default_factory=list)
    original_episodes: list[OriginalEpisode] = Field(default_factory=list)
    mixed_media_presets: list[MixedMediaPreset] = Field(default_factory=list)
    landings: list[Landing] = Field(default_factory=list)
    promo_events: list[PromoEvent] = Field(default_factory=list)
    business_unlim_offers: list[BusinessUnlimOffer] = Field(default_factory=list)
    game_gifts: list[GameGift] = Field(default_factory=list)
    summary: SiteSummary


class SiteDatasetExt(SiteDataset):
    """Dataset of a run with --what room-list / room-content. Default runs keep SiteDataset (unchanged outputs)."""

    rooms: list[Room] = Field(default_factory=list)
    room_items: list[RoomItem] = Field(default_factory=list)
    room_discussions: list[RoomDiscussion] = Field(default_factory=list)


class SiteDatasetFull(SiteDatasetExt):
    """Dataset of a run with --what academy-api (rooms collections only when room-list / room-content is selected
    too: build_dataset excludes them otherwise). Runs without academy-api keep SiteDataset / SiteDatasetExt."""

    academy_api_categories: list[AcademyApiCategory] = Field(default_factory=list)
    academy_api_courses: list[AcademyApiCourse] = Field(default_factory=list)
    academy_api_lessons: list[AcademyApiLesson] = Field(default_factory=list)
