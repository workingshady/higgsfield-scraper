"""Pydantic v2 output models of the community scraper (Strict: unknown fields are a bug)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta, Provenance, Strict
from ...estimate import EstimatedCost

Feed = Literal["trending", "approved", "top", "model-x", "detail"]
MediaType = Literal["image", "video", "audio", "unknown"]


class Settings(Strict):
    """Normalized, typed generation settings (API `params.*`). Every param not listed here is in `params_extra`."""

    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = Field(None, description="e.g. 1k|2k|4k (image) or 480p|720p|1080p (video)")
    quality: Optional[str] = None
    duration: Optional[float] = Field(None, description="video/audio length in seconds")
    batch_size: Optional[int] = Field(None, description="number of outputs requested in the job")
    seed: Optional[int] = None
    model: Optional[str] = Field(None, description="internal model name, e.g. aurora-img-alpha")
    mode: Optional[str] = None
    style_id: Optional[str] = None
    style_strength: Optional[float] = None
    preset_id: Optional[str] = None
    chain_preset_id: Optional[str] = None
    motion_id: Optional[str] = None
    enhance_prompt: Optional[bool] = None
    output_format: Optional[str] = None
    background: Optional[str] = None
    remove_bg: Optional[bool] = None
    generate_audio: Optional[bool] = None
    sound: Optional[str] = None
    cfg_scale: Optional[float] = None
    steps: Optional[int] = None
    thinking_level: Optional[str] = None
    genre: Optional[str] = None
    speedramp: Optional[str] = None
    prompt_language: Optional[str] = None
    bitrate_mode: Optional[str] = None
    draft: Optional[bool] = None
    multi_shots: Optional[bool] = None
    multi_shot_mode: Optional[str] = None
    use_unlim: Optional[bool] = Field(None, description="generated on an 'unlimited' plan allowance")
    use_relax: Optional[bool] = None
    camera_model_id: Optional[str] = None
    camera_lens_id: Optional[str] = None


class InputMedia(Strict):
    """One input media of a generation (start image, reference, character…)."""

    index: int = Field(description="position within the generation's inputs")
    param: str = Field(description="params key it came from: medias|input_images|input_image|reference_elements|"
                                   "custom_reference|image_reference|kling_elements|…")
    role: Optional[str] = Field(None, description="role (medias[].role), reference element category, or the param")
    url: Optional[str] = None
    id: Optional[str] = None
    type: Optional[str] = Field(None, description="e.g. media_input")
    name: Optional[str] = Field(None, description="reference element / custom reference name")
    width: Optional[int] = None
    height: Optional[int] = None
    extra: dict[str, Any] = Field(default_factory=dict, description="every other field of the input object")


class ResultVariant(Strict):
    name: str = Field(description="variant key: raw (original), min (preview), hls (m3u8 stream), h264 (mp4), "
                                  "result (legacy single result)")
    type: Optional[str] = Field(None, description="image|video|audio|…")
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Engagement(Strict):
    views: Optional[int] = None
    likes: Optional[int] = None
    approved: Optional[bool] = Field(None, description="curated by Higgsfield (appears in the approved feed)")
    pinned_at: Optional[AwareDatetime] = None
    is_liked_by_user: Optional[bool] = Field(None, description="always null without a login")


class Moderation(Strict):
    ip_check_finished: Optional[bool] = None
    ip_detected: Optional[bool] = None
    deepfake_consent_required: Optional[bool] = None
    can_bypass_ip: Optional[bool] = None


class CreatorRef(Strict):
    user_id: Optional[str] = Field(None, description="pseudonymous Higgsfield user id (Clerk id)")
    username: Optional[str] = Field(None, description="only with --with-profiles")
    avatar_url: Optional[str] = Field(None, description="only with --with-profiles")
    instagram_handle: Optional[str] = None
    twitter_handle: Optional[str] = None
    youtube_handle: Optional[str] = None
    tiktok_handle: Optional[str] = None
    badge: Optional[Any] = None
    badges: Optional[list[Any]] = None


class CommunityGeneration(Strict):
    generation_id: str = Field(description="job id (API item `id`)")
    publication_id: Optional[str] = Field(None, description="community publication id (GET /publications/{id})")
    feed: Feed = Field(description="listing the item was first collected from (or 'detail' for --publication-ids)")
    detail_fetched: bool = Field(False, description="fields come from GET /publications/{id} (--detail)")
    job_set_type: Optional[str] = Field(None, description="generation model/tool; joins pricing model_id")
    model_id: Optional[str] = Field(None, description="same as job_set_type (pricing join key)")
    job_set_id: Optional[str] = None
    parent_id: Optional[str] = Field(None, description="job_set_parent_id (e.g. an upscale/extend of another job)")
    media_type: MediaType
    status: Optional[str] = Field(None, description="completed | nsfw | …")
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    settings: Settings
    params_extra: dict[str, Any] = Field(default_factory=dict,
                                         description="every other params.* key, untouched (nothing is lost)")
    raw_params: Optional[dict[str, Any]] = Field(None, description="untouched params (only with --with-raw-params)")
    inputs: list[InputMedia] = Field(default_factory=list)
    results: list[ResultVariant] = Field(default_factory=list)
    engagement: Engagement
    created_at: Optional[AwareDatetime] = None
    published_at: Optional[AwareDatetime] = None
    expires_at: Optional[AwareDatetime] = None
    can_upgrade_to_4k: Optional[bool] = None
    upgrade_options: Optional[list[Any]] = None
    moderation: Moderation
    cluster_hash: Optional[str] = None
    trace_id: Optional[str] = None
    board_ids: list[Any] = Field(default_factory=list)
    client_meta: Optional[dict[str, Any]] = Field(None, description="job_set_client_meta, e.g. {source: viral_hub_web}")
    is_bonus_generation: Optional[bool] = Field(None, description="meta.is_bonus_generation")
    upstream_usage: Optional[dict[str, Any]] = Field(
        None, description="parsed meta.cost: the upstream provider's token usage. NOT Higgsfield credits")
    meta_extra: dict[str, Any] = Field(default_factory=dict, description="other meta.* keys")
    extra: dict[str, Any] = Field(default_factory=dict,
                                  description="any other non-null top-level item fields (representation, drama, …)")
    creator: CreatorRef
    estimated_cost: Optional[EstimatedCost] = Field(None, description="None unless --estimate-cost")
    source: Provenance


class CommunityCreator(Strict):
    """Only with --with-profiles (personal data)."""

    user_id: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    instagram_handle: Optional[str] = None
    twitter_handle: Optional[str] = None
    youtube_handle: Optional[str] = None
    tiktok_handle: Optional[str] = None
    badge: Optional[Any] = None
    badges: list[Any] = Field(default_factory=list)
    generations_in_dataset: Optional[int] = None
    source: Provenance


class CommunityComment(Strict):
    """Only with --with-comments (login-only endpoint). The shape was not observable without a session, so fields
    are parsed defensively and everything else is kept in `extra`."""

    comment_id: str
    publication_id: str
    parent_id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[AwareDatetime] = None
    likes: Optional[int] = None
    user_id: Optional[str] = None
    username: Optional[str] = Field(None, description="only with --with-profiles")
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class CommunityPage(Strict):
    """One listing page (crawl audit trail: cursor chain, has_more, totals)."""

    page_id: str
    feed: Feed
    cursor: Optional[str] = Field(None, description="cursor sent (None = first page)")
    next_cursor: Optional[str] = None
    has_more: Optional[bool] = None
    total: Optional[int] = Field(None, description="API `total`: items remaining from this cursor (all on page 1)")
    size: Optional[int] = None
    items: int
    source: Provenance


class CommunityCostBasis(Strict):
    """Pricing context for --estimate-cost: the /job-sets/costs body, or the USD reference from the plans."""

    basis_id: str = Field(description="job_costs | usd_reference | compare | benefits")
    job_costs: Optional[dict[str, Any]] = Field(None, description="untouched /job-sets/costs body")
    body: Optional[dict[str, Any]] = Field(None, description="compare / plan-benefits body (fallback prices)")
    usd_per_credit: Optional[float] = None
    usd_reference: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    source: Provenance


class CostBasisSummary(Strict):
    priced_models: Optional[int] = None
    usd_per_credit: Optional[float] = None
    usd_reference: Optional[str] = None
    fetched_at: Optional[AwareDatetime] = None
    estimator_available: bool = False
    notes: list[str] = Field(default_factory=list)


class CommunityStats(Strict):
    generations: int
    by_feed: dict[str, int] = Field(default_factory=dict)
    by_job_set_type: dict[str, int] = Field(default_factory=dict)
    by_media_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    by_resolution: dict[str, int] = Field(default_factory=dict)
    by_aspect_ratio: dict[str, int] = Field(default_factory=dict)
    top_settings: dict[str, dict[str, int]] = Field(default_factory=dict,
                                                    description="settings key -> top 10 values with counts")
    params_extra_keys: dict[str, int] = Field(default_factory=dict, description="how often each extra param occurs")
    inputs_by_param: dict[str, int] = Field(default_factory=dict)
    with_prompt: int = 0
    with_inputs: int = 0
    views_total: int = 0
    likes_total: int = 0
    distinct_creators: int = 0
    estimated_credits_by_model: dict[str, float] = Field(default_factory=dict)
    estimated_credits_total: Optional[float] = None
    estimated_usd_total: Optional[float] = None
    estimate_status: dict[str, int] = Field(default_factory=dict)
    cost_basis: Optional[CostBasisSummary] = None


class CommunityDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    generations: list[CommunityGeneration] = Field(default_factory=list)
    creators: list[CommunityCreator] = Field(default_factory=list)
    comments: list[CommunityComment] = Field(default_factory=list)
    pages: list[CommunityPage] = Field(default_factory=list)
    stats: CommunityStats
