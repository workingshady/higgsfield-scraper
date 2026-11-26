"""Pydantic v2 models of the showcase scraper (source of truth; Scrapy items are generated from them).

Every entity carries: a stable natural-key `id` (make_id), `source_url` (the page/API URL a person can open),
`scraped_at` (UTC), `schema_version`, and `source: Provenance` (the exact request). Generation-like entities also
carry `generation_key` (job id, else CDN media id) and `media_keys` so `scripts/merge_generations.py` can
deduplicate across scrapers. Personal data: creators are `creator_key` (sha256-16 of the Clerk id) unless
`--with-profiles`, which adds `creator` (user_id, username, avatar_url).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta
from ...schemas.common import Currency, Provenance, Strict

ENTITY_SCHEMA_VERSION = 1


class Media(Strict):
    role: str = Field(description="what the file is on the page: preview|thumbnail|poster|input|output|before|"
                                  "after|tour|final|video|image|icon|hls|…")
    type: Optional[str] = Field(None, description="video|image|audio|hls (from the API `type`, else the extension)")
    url: str
    width: Optional[int] = Field(None, description="pixels")
    height: Optional[int] = Field(None, description="pixels")
    duration_s: Optional[float] = Field(None, description="seconds (API `duration` s, or `duration_ms`/1000)")
    media_key: Optional[str] = Field(None, description="CDN file id: the API media id, else the last UUID in the URL")


class Engagement(Strict):
    likes: Optional[int] = None
    views: Optional[int] = None
    comments: Optional[int] = None
    uses: Optional[int] = Field(None, description="times the preset/trend was re-made (`times_made`)")


class Creator(Strict):
    """Only with --with-profiles."""
    user_id: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class _Entity(Strict):
    id: str = Field(description="stable 16-hex id = make_id(kind, natural key)")
    source_url: str = Field(description="page or API URL where a person can see this record")
    scraped_at: AwareDatetime
    schema_version: int = ENTITY_SCHEMA_VERSION
    source: Provenance


class _Generation(_Entity):
    generation_key: Optional[str] = Field(None, description="dedup key across scrapers: `job:<job id>`, else "
                                                            "`media:<CDN file id of the main output>`")
    media_keys: list[str] = Field(default_factory=list, description="every output media key (`media:<id>`)")


# ------------------------------------------------------------------ canvas
class CanvasTemplate(_Entity):
    template_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    created_at: Optional[AwareDatetime] = None
    app_url: str = Field(description="https://higgsfield.ai/canvas/templates/{id}")
    graph_available: bool = Field(False, description="node graph is only served over the login-ticket WebSocket "
                                                     "(/api/templates/{id}/connect); not fetched")


# ------------------------------------------------------------------ editing room (videoshop)
class ExampleEdit(Strict):
    edit_id: Optional[str] = None
    tool: Optional[str] = Field(None, description="camera-move|relight|angle|genjutsu|brush")
    label: Optional[str] = None
    prompt: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    layer: Optional[int] = None


class EditingRoomExample(_Generation):
    example_id: str = Field(description="CMS slug, e.g. tea-house")
    title: Optional[str] = None
    lang: str
    media: list[Media] = Field(default_factory=list, description="thumbnail, preview, input, final")
    input_duration_ms: Optional[int] = None
    final_duration_ms: Optional[int] = None
    edits: list[ExampleEdit] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class ProjectEdit(Strict):
    edit_id: str
    number: Optional[int] = None
    tool: Optional[str] = None
    tool_mode: Optional[str] = Field(None, description="genjutsu `genjutsuWay` (change-location, swap-person, …)")
    layer: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    hidden: Optional[bool] = None
    resolution: Optional[str] = None
    prompt_enabled: Optional[bool] = None
    prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict, description="tool parameters: relight {preset, lights[az,el,"
                                                                     "color,brightness,diffuse]}, cameraMove, angle, brush")
    references: list[Media] = Field(default_factory=list)
    placed_version_id: Optional[str] = None


class EditingRoomProject(_Entity):
    project_id: str
    name: Optional[str] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    take: Optional[Media] = Field(None, description="the uploaded source video")
    take_duration_ms: Optional[int] = None
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    timeline_schema_version: Optional[int] = None
    edits: list[ProjectEdit] = Field(default_factory=list)
    render_ids: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class EditingRoomRender(_Generation):
    """One rendered version of an edit (a job): `timeline.versions[]`."""
    version_id: str
    project_id: str
    edit_id: Optional[str] = None
    number: Optional[int] = None
    job_set_id: Optional[str] = None
    batch_id: Optional[str] = None
    status: Optional[str] = None
    resolution: Optional[str] = None
    tool: Optional[str] = None
    prompt: Optional[str] = None
    made_with: dict[str, Any] = Field(default_factory=dict, description="full tool spec of the render")
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    media: list[Media] = Field(default_factory=list)


# ------------------------------------------------------------------ property studio
class PropertyStudioExample(_Generation):
    preset_index: int = Field(description="position in the JS preset table (app id = index + 100)")
    format: str = Field(description="flash-tour|enhance|renovation|virtual-staging|floor-plan-3d")
    app: Optional[str] = Field(None, description="Property Studio app make (speedramp_walkthrough, …)")
    path: str = Field(description="preset folder under realty-studio/app-presets/{v1|full-v1}/{format}/")
    title_id: Optional[str] = Field(None, description="lingui message id")
    title: Optional[str] = None
    lang: str
    input_count: int
    width: Optional[int] = None
    height: Optional[int] = None
    media: list[Media] = Field(default_factory=list, description="inputs (v1 + full-v1 original), poster, video, output")
    chunk: Optional[str] = Field(None, description="JS chunk the table came from")


# ------------------------------------------------------------------ video explore (Higgsfield Multiplier)
class ExploreCategory(_Entity):
    category: str
    trends: Optional[int] = Field(None, description="number of trends in the category")


class ExploreItem(_Entity):
    item_id: str
    feed_source: str = Field(description="higgsfield (curated) | community")
    sort: Optional[str] = Field(None, description="community feed sort the item was first seen in")
    category_filter: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    job_set_type: Optional[str] = None
    priority: Optional[int] = None
    category: Optional[str] = None
    trend_id: Optional[str] = None
    engagement: Engagement
    original_video: Optional[Media] = None
    variant_ids: list[str] = Field(default_factory=list)
    publication_ids: list[str] = Field(default_factory=list, description="community publication ids of the "
                                                                         "generation variants (join with community)")


class ExploreVariant(_Generation):
    variant_id: str
    item_id: str
    variant_type: Optional[str] = Field(None, description="original|edit|generation")
    prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    priority: Optional[int] = None
    media: list[Media] = Field(default_factory=list)
    inputs: list[Media] = Field(default_factory=list)
    publication_id: Optional[str] = None
    publication_engagement: Optional[Engagement] = None
    creator_key: Optional[str] = None
    creator_badge: Optional[str] = None
    creator: Optional[Creator] = None


# ------------------------------------------------------------------ effect examples
class EffectSample(_Generation):
    sample_id: str
    preset_slug: str
    preset_id: Optional[str] = None
    preset_kind: Optional[str] = None
    preset_name: Optional[str] = None
    catalog_ref: Optional[str] = Field(None, description="the preset itself is in the catalog scraper "
                                                         "(catalog_viral_preset id) — only the samples are new")
    sample_preset_id: Optional[str] = Field(None, description="preset id stored on the sample (mixed-media id)")
    job_id: Optional[str] = None
    job_set_id: Optional[str] = None
    job_set_type: Optional[str] = None
    status: Optional[str] = None
    prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict, description="job rawParams (input URLs removed)")
    created_at: Optional[AwareDatetime] = None
    published_at: Optional[AwareDatetime] = None
    media: list[Media] = Field(default_factory=list)
    inputs: list[Media] = Field(default_factory=list)
    creator_key: Optional[str] = None
    creator: Optional[Creator] = None
    samples_total: Optional[int] = Field(None, description="`initialSamples.total` reported on the page")


# ------------------------------------------------------------------ public API docs
class ApiParameter(Strict):
    name: str
    type: Optional[str] = None
    required: bool = False
    default: Any = None
    enum: list[Any] = Field(default_factory=list)
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    format: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class ApiPrice(Strict):
    label: str
    amount: Optional[Decimal] = Field(None, description="decimal string; per `unit`")
    currency: Optional[Currency] = Field(None, description="ISO 4217, only when the docs say USD")
    unit: Optional[str] = Field(None, description="column header / sentence the price is quoted per")
    price_raw: str


class ApiModel(_Entity):
    endpoint_id: str = Field(description="vendor/model/variant, e.g. minimax/hailuo-2.3/standard/image-to-video")
    vendor: str
    model: Optional[str] = None
    variant: Optional[str] = None
    http_method: str = "POST"
    endpoint_url: str
    title: Optional[str] = None
    family: Optional[str] = Field(None, description="model family page title, e.g. Hailuo 2.3")
    doc_url: Optional[str] = None
    playground_url: Optional[str] = None
    summary: Optional[str] = None
    usage_notes: list[str] = Field(default_factory=list)
    parameters: list[ApiParameter] = Field(default_factory=list)
    required_parameters: list[str] = Field(default_factory=list)
    json_schema: dict[str, Any] = Field(default_factory=dict)
    prices: list[ApiPrice] = Field(default_factory=list)
    price_notes: list[str] = Field(default_factory=list)
    in_openapi: bool = False


# ------------------------------------------------------------------ season (login only)
class Season(_Entity):
    """GET fnf-score/v1/season (login only). Per-user progress is never exported; only season metadata."""
    active: bool
    season_id: Optional[str] = None
    name: Optional[str] = None
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    top_level_keys: list[str] = Field(default_factory=list)
    personal_fields_dropped: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ CMS media lists
class _CmsItem(_Generation):
    item_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[int] = None
    lang: Optional[str] = None
    media: list[Media] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict, description="every other API field, unchanged")


class CinemaControl(_CmsItem):
    group: str = Field(description="camera_model|camera_lens|camera_aperture|camera_movement|color|pacing|light|"
                                   "genre|era")
    tag: Optional[str] = None
    is_auto: Optional[bool] = None
    segments: list[dict[str, Any]] = Field(default_factory=list)


class FacelessShowcase(_CmsItem):
    pass


class IntoneExample(_CmsItem):
    pass


class SeedancePreset(_CmsItem):
    duration_s: Optional[float] = None


class MotionControlPreset(_CmsItem):
    pass


# ------------------------------------------------------------------ Shorts Studio (AI Reels) — opt-in
class ReelsPreset(_Generation):
    """One Shorts Studio (ex "Genjutsu for Reels" / "AI Reels") preset = a finished example reel (output) plus the
    reference reel it recreates and the inputs used. `source` higgsfield = curated (reference = a public Instagram
    reel), community = published by a Higgsfield user (Recreate → Publish). See docs/scrapers/showcase.md §Reels."""
    preset_id: str = Field(description="API `id` (UUID); /shorts-studio/{preset_id} for curated presets")
    slug: Optional[str] = Field(None, description="detail key: GET /fnf-cms-api/ai-reels-presets/{slug}")
    preset_source: str = Field(description="higgsfield (curated) | community (user-published)")
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = Field(None, description="category id (only `style-transfer` today)")
    category_label: Optional[str] = None
    prompt: Optional[str] = Field(None, description="detail endpoint `prompt` (the brief behind the reel)")
    script: Optional[str] = Field(None, description="voice-over / caption script of the reel")
    instructions: Optional[str] = Field(None, description="free-text edit instructions (community presets)")
    hashtags: list[str] = Field(default_factory=list)
    quality: Optional[str] = Field(None, description="output quality, e.g. 1080p")
    duration_s: Optional[float] = Field(None, description="preset duration (seconds)")
    own_recording: Optional[bool] = Field(None, description="true = made from the author's own recording(s)")
    job_set_type: str = Field("ai_reels_v1", description="job set type a Recreate launches (JS Dt.AI_REELS)")
    media: list[Media] = Field(default_factory=list, description="the generated reel: output, output_compressed, "
                                                                 "output_thumbnail, thumbnail")
    inputs: list[Media] = Field(default_factory=list, description="reference (+_compressed/_thumbnail), character, "
                                                                  "background, own_video_N (+_thumbnail)")
    reference_url: Optional[str] = Field(None, description="the reference reel on its platform (curated only)")
    reference_platform: Optional[str] = Field(None, description="instagram|tiktok|youtube")
    reference_engagement: Optional[Engagement] = Field(None, description="the REFERENCE reel's own views/likes/"
                                                                         "comments on its platform (curated only)")
    reference_author_handle: Optional[str] = Field(None, description="reference reel author's handle; only with "
                                                                     "--with-profiles")
    engagement: Engagement = Field(default_factory=Engagement, description="on Higgsfield: likes (publication "
                                   "likes, community), uses = `recreates`")
    publication_id: Optional[str] = Field(None, description="community: fnf-community generation_publication id "
                                                            "(comment thread)")
    creator_key: Optional[str] = Field(None, description="community: sha256-16 of the author's Clerk id (from the "
                                                         "avatar path), else of `username:<name>`")
    creator_key_basis: Optional[str] = Field(None, description="user_id | username (what creator_key hashes)")
    creator_badge: Optional[str] = None
    creator: Optional[Creator] = None
    lang: Optional[str] = None


class ReelsComment(_Entity):
    """A comment on a community Shorts Studio preset (fnf-community generation_publication thread)."""
    comment_id: str
    publication_id: str
    preset_id: Optional[str] = None
    parent_id: Optional[str] = Field(None, description="set on replies")
    text: Optional[str] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    likes: Optional[int] = None
    dislikes: Optional[int] = None
    reply_count: Optional[int] = None
    reactions: list[dict[str, Any]] = Field(default_factory=list)
    creator_key: Optional[str] = None
    creator: Optional[Creator] = None


MODEL_BY_KIND: dict[str, type[_Entity]] = {
    "showcase_canvas_template": CanvasTemplate,
    "showcase_editing_room_example": EditingRoomExample,
    "showcase_editing_room_project": EditingRoomProject,
    "showcase_editing_room_render": EditingRoomRender,
    "showcase_property_studio_example": PropertyStudioExample,
    "showcase_explore_category": ExploreCategory,
    "showcase_explore_item": ExploreItem,
    "showcase_explore_variant": ExploreVariant,
    "showcase_effect_sample": EffectSample,
    "showcase_api_model": ApiModel,
    "showcase_season": Season,
    "showcase_cinema_control": CinemaControl,
    "showcase_faceless_showcase": FacelessShowcase,
    "showcase_intone_example": IntoneExample,
    "showcase_seedance_preset": SeedancePreset,
    "showcase_motion_control_preset": MotionControlPreset,
    "showcase_reels_preset": ReelsPreset,
    "showcase_reels_comment": ReelsComment,
}
ID_FIELD_BY_KIND = {k: "id" for k in MODEL_BY_KIND}

# kind -> dataset collection
COLLECTION_OF = {
    "showcase_canvas_template": "canvas_templates",
    "showcase_editing_room_example": "editing_room_examples",
    "showcase_editing_room_project": "editing_room_projects",
    "showcase_editing_room_render": "editing_room_renders",
    "showcase_property_studio_example": "property_studio_examples",
    "showcase_explore_category": "explore_categories",
    "showcase_explore_item": "explore_items",
    "showcase_explore_variant": "explore_variants",
    "showcase_effect_sample": "effect_samples",
    "showcase_api_model": "api_models",
    "showcase_season": "seasons",
    "showcase_cinema_control": "cinema_controls",
    "showcase_faceless_showcase": "faceless_showcases",
    "showcase_intone_example": "intone_examples",
    "showcase_seedance_preset": "seedance_presets",
    "showcase_motion_control_preset": "motion_control_presets",
    "showcase_reels_preset": "reels_presets",
    "showcase_reels_comment": "reels_comments",
}


class Summary(Strict):
    counts: dict[str, int] = Field(default_factory=dict)
    totals_available: dict[str, Optional[int]] = Field(default_factory=dict)
    by_source: dict[str, dict[str, int]] = Field(default_factory=dict)
    generation_keys: int = 0
    login: dict[str, str] = Field(default_factory=dict, description="login-only parts: fetched / skipped / not selected")


class ShowcaseDataset(Strict):
    schema_version: Literal[1] = 1
    meta: CoreMeta
    summary: Summary
    canvas_templates: list[CanvasTemplate] = Field(default_factory=list)
    editing_room_examples: list[EditingRoomExample] = Field(default_factory=list)
    editing_room_projects: list[EditingRoomProject] = Field(default_factory=list)
    editing_room_renders: list[EditingRoomRender] = Field(default_factory=list)
    property_studio_examples: list[PropertyStudioExample] = Field(default_factory=list)
    explore_categories: list[ExploreCategory] = Field(default_factory=list)
    explore_items: list[ExploreItem] = Field(default_factory=list)
    explore_variants: list[ExploreVariant] = Field(default_factory=list)
    effect_samples: list[EffectSample] = Field(default_factory=list)
    api_models: list[ApiModel] = Field(default_factory=list)
    seasons: list[Season] = Field(default_factory=list)
    cinema_controls: list[CinemaControl] = Field(default_factory=list)
    faceless_showcases: list[FacelessShowcase] = Field(default_factory=list)
    intone_examples: list[IntoneExample] = Field(default_factory=list)
    seedance_presets: list[SeedancePreset] = Field(default_factory=list)
    motion_control_presets: list[MotionControlPreset] = Field(default_factory=list)
    reels_presets: list[ReelsPreset] = Field(default_factory=list)
    reels_comments: list[ReelsComment] = Field(default_factory=list)
