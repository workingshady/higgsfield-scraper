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
    """Only with --with-comments. Comments come from the Community posts service (fnf-community); gallery
    publications have no comment threads. Identity fields are filled only with --with-profiles."""

    comment_id: str
    publication_id: str = Field(description="the commented publication (a Community post id for thread_type "
                                            "'publication' from fnf-community)")
    thread_type: Optional[str] = Field(None, description="API entity_type, e.g. 'publication'")
    parent_id: Optional[str] = Field(None, description="set on replies")
    text: Optional[str] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    likes: Optional[int] = None
    dislikes: Optional[int] = None
    reply_count: Optional[int] = None
    reactions: list[dict[str, Any]] = Field(default_factory=list)
    mention_count: int = 0
    user_id: Optional[str] = Field(None, description="pseudonymous commenter id")
    username: Optional[str] = Field(None, description="only with --with-profiles")
    author: dict[str, Any] = Field(default_factory=dict, description="badge/rating_points; name, avatar, headline "
                                                                     "only with --with-profiles")
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


# ------------------------------------------------------------------ opt-in Community pages
# (--feeds shots, posts, feed, creators, talents). Data model: docs/COMMUNITY_COVERAGE.md "Data model". Identity
# fields (username, names, avatars, bio, headline, location) are None unless --with-profiles; user_id is the
# pseudonymous Clerk id (as for community_generation.creator.user_id).

class PersonRef(Strict):
    """Author of a shot / post / feed item. Only user_id (+ non-identifying badge / rating) without --with-profiles."""

    user_id: Optional[str] = Field(None, description="pseudonymous Higgsfield user id (Clerk id)")
    username: Optional[str] = Field(None, description="only with --with-profiles")
    full_name: Optional[str] = Field(None, description="only with --with-profiles")
    avatar_url: Optional[str] = Field(None, description="only with --with-profiles")
    headline: Optional[str] = Field(None, description="only with --with-profiles")
    badge: Optional[str] = Field(None, description="badge key (e.g. higgs); not identifying")
    rating_points: Optional[int] = Field(None, description="creator rating points shown on cards")


class CommunityShot(Strict):
    """kind=community_shot - one item of the Shots tab (/community/generations): a published generation as listed by
    fnf-community GET /generations/feed. shot_id is the gallery publication id (joins
    community_generation.publication_id); generation_id is the job id (joins community_generation.generation_id)."""

    shot_id: str = Field(description="publication id (API `id`)")
    generation_id: Optional[str] = Field(None, description="job id (API `job_id`) = community_generation.generation_id")
    url: str = Field(description="https://higgsfield.ai/community/generations?shot=<shot_id>")
    job_set_type: Optional[str] = Field(None, description="API `model` (a job_set_type, joins pricing model_id)")
    media_type: MediaType
    media_url: Optional[str] = Field(None, description="preview-size media (..._min.webp / _min.mp4)")
    thumbnail_url: Optional[str] = Field(None, description="video poster; null for images")
    width: Optional[int] = Field(None, description="px; the UI shows 0 when missing or <= 0")
    height: Optional[int] = Field(None, description="px")
    likes: Optional[int] = Field(None, description="API like_count (shown on the card)")
    views: Optional[int] = Field(None, description="API view_count (not shown on the Shots card)")
    comments: Optional[int] = Field(None, description="API comment_count (shown on the card)")
    aesthetic_score: Optional[float] = Field(None, description="0..1 model score used for ranking (not shown)")
    aesthetic_label: Optional[bool] = Field(None, description="passes the aesthetic filter (not shown)")
    published_at: Optional[AwareDatetime] = None
    author: PersonRef
    snapshot_id: Optional[str] = Field(None, description="feed snapshot the page came from (cursor-based ranking)")
    source: Provenance


class PostMedia(Strict):
    """One attachment of a Community post (content.medias[])."""

    index: int
    type: Optional[str] = Field(None, description="project_publication | job | image | video | blog_post | ...")
    url: Optional[str] = Field(None, description="job_result.url / url (empty strings -> null)")
    project_publication_id: Optional[str] = None
    job_id: Optional[str] = None
    blog_post_id: Optional[str] = None
    card_id: Optional[str] = None
    card_title: Optional[str] = None
    card_slug: Optional[str] = None
    card_description: Optional[str] = None
    card_cover_url: Optional[str] = None
    video_url: Optional[str] = None
    video_hls_url: Optional[str] = None
    video_preview_url: Optional[str] = None
    video_thumbnail_url: Optional[str] = None
    width: Optional[int] = Field(None, description="px")
    height: Optional[int] = Field(None, description="px")
    duration_seconds: Optional[float] = Field(None, description="seconds (card.video.duration)")
    card_stats: Optional[dict[str, Any]] = Field(None, description="project card stats: generations_count, "
                                                 "credits_spent, free_generations, size_bytes, stack[] (per model)")
    extra: dict[str, Any] = Field(default_factory=dict)


class CommunityPost(Strict):
    """kind=community_post - a Community post (fnf-community GET /publications/feed): text + attached works.
    Room discussions (site --what room-content) are the same objects filtered by room_id."""

    post_id: str
    url: str = Field(description="https://higgsfield.ai/community/feed/<post_id>")
    title: Optional[str] = Field(None, description="title or content.title (empty -> null)")
    text: Optional[str] = Field(None, description="content.text")
    room_id: Optional[str] = Field(None, description="content.room_id when the post is a room discussion")
    post_kind: Optional[str] = Field(None, description="content.kind (e.g. discussion)")
    media: list[PostMedia] = Field(default_factory=list)
    likes: Optional[int] = None
    dislikes: Optional[int] = None
    comments: Optional[int] = None
    views: Optional[int] = Field(None, description="API views_count")
    shares: Optional[int] = Field(None, description="API share_count")
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    author: PersonRef
    extra: dict[str, Any] = Field(default_factory=dict, description="other non-null API fields")
    source: Provenance


class CommunityFeedItem(Strict):
    """kind=community_feed_item - one card of the Feed tab (/community/feed, fnf-community GET /feed): a shot,
    project, blog post or Community post with its counters as shown on the card."""

    feed_item_id: str = Field(description="make_id(item_type, item_id)")
    item_type: Literal["generation", "project_publication", "blog_post", "post", "unknown"]
    item_id: str = Field(description="publication id (generation / project), blog post id or post id")
    url: Optional[str] = Field(None, description="page URL when it can be built without the author's username")
    position: Optional[int] = Field(None, description="0-based rank in the crawled feed")
    title: Optional[str] = Field(None, description="card.title / post title / first line of the post text")
    description: Optional[str] = None
    slug: Optional[str] = None
    media_type: Optional[str] = None
    job_set_type: Optional[str] = Field(None, description="generation.model")
    generation_id: Optional[str] = Field(None, description="generation.job_id (joins community_generation)")
    made_with_tool: Optional[str] = Field(None, description="made_with.tool, e.g. video")
    made_with_model: Optional[str] = Field(None, description="made_with.model_name (display name)")
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    likes: Optional[int] = Field(None, description="item like_count (card counter)")
    comments: Optional[int] = Field(None, description="item comment_count")
    shares: Optional[int] = Field(None, description="item share_count")
    views: Optional[int] = Field(None, description="generation.view_count / card.views_count / post.views_count")
    reading_time_minutes: Optional[int] = None
    project_stats: Optional[dict[str, Any]] = Field(None, description="card.stats of a project (credits_spent ...)")
    created_at: Optional[AwareDatetime] = None
    top_comment_id: Optional[str] = None
    top_comment_likes: Optional[int] = None
    author: PersonRef
    snapshot_id: Optional[str] = None
    source: Provenance


class CreatorWork(Strict):
    """A work shown on a creator card (users[].items[]; the UI shows at most 12)."""

    type: str = Field(description="project | shot")
    item_id: Optional[str] = Field(None, description="project publication_id or shot publication id")
    title: Optional[str] = Field(None, description="project name (public)")
    is_pinned: Optional[bool] = None


class CommunityCreatorStats(Strict):
    """kind=community_creator_stats - one creator card of /community/creators (listing 'creators') or of the Talents
    hub (listing 'talents'): aggregate public stats. Profile fields only with --with-profiles."""

    record_id: str = Field(description="make_id(listing, user_id)")
    listing: Literal["creators", "talents"]
    position: Optional[int] = Field(None, description="0-based rank in the listing order")
    user_id: str = Field(description="pseudonymous Clerk id")
    rating_points: Optional[int] = None
    followers_count: Optional[int] = None
    following_count: Optional[int] = None
    likes_count: Optional[int] = Field(None, description="likes received on the creator's works")
    views_count: Optional[int] = Field(None, description="views of the creator's works")
    verified_projects_count: Optional[int] = None
    latest_verified_at: Optional[AwareDatetime] = None
    is_pinned: Optional[bool] = None
    badge: Optional[str] = None
    badge_names: list[str] = Field(default_factory=list, description="badges[].name (achievements)")
    works_count: int = Field(0, description="works listed on the card")
    works: list[CreatorWork] = Field(default_factory=list)
    username: Optional[str] = Field(None, description="only with --with-profiles")
    full_name: Optional[str] = Field(None, description="only with --with-profiles")
    headline: Optional[str] = Field(None, description="only with --with-profiles")
    bio: Optional[str] = Field(None, description="only with --with-profiles")
    location: Optional[str] = Field(None, description="only with --with-profiles")
    avatar_url: Optional[str] = Field(None, description="only with --with-profiles")
    source: Provenance


class CommunityDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    generations: list[CommunityGeneration] = Field(default_factory=list)
    creators: list[CommunityCreator] = Field(default_factory=list)
    comments: list[CommunityComment] = Field(default_factory=list)
    pages: list[CommunityPage] = Field(default_factory=list)
    stats: CommunityStats


class CommunityExtraStats(Strict):
    shots: int = 0
    posts: int = 0
    feed_items: int = 0
    creator_stats: int = 0
    feed_items_by_type: dict[str, int] = Field(default_factory=dict)
    shots_by_job_set_type: dict[str, int] = Field(default_factory=dict)
    shots_by_media_type: dict[str, int] = Field(default_factory=dict)
    comments_by_thread_type: dict[str, int] = Field(default_factory=dict)


class CommunityDatasetExt(CommunityDataset):
    """Dataset of a run that used an opt-in Community page (--feeds shots|posts|feed|creators|talents). Default runs
    keep CommunityDataset, so their dataset.json / schema / CSV set are unchanged."""

    shots: list[CommunityShot] = Field(default_factory=list)
    posts: list[CommunityPost] = Field(default_factory=list)
    feed_items: list[CommunityFeedItem] = Field(default_factory=list)
    creator_stats: list[CommunityCreatorStats] = Field(default_factory=list)
    extra_stats: CommunityExtraStats = Field(default_factory=CommunityExtraStats)


# ------------------------------------------------------------------ opt-in gallery / template sources
# (--feeds music-cards, job-showcase, collections, explore-cards; docs/COMMUNITY_COVERAGE.md §3b and §5).
# None of these objects has a comment thread (fnf-community /entities/{type}/{id}/comments accepts only
# generation_publication | project_publication | blog_post) or public engagement counters.

class MusicCardRecipient(Strict):
    """A recipient of a Music Cards template (example text written by Higgsfield, not a real person's data)."""

    main: Optional[bool] = None
    name: Optional[str] = Field(None, description="example name used by the template, e.g. Mama")
    role: Optional[str] = Field(None, description="role key (joins music card option group 'role')")
    facts_wishes: list[str] = Field(default_factory=list, description="the facts / wishes the lyrics are built from")
    extra: dict[str, Any] = Field(default_factory=dict)


class CommunityMusicCard(Strict):
    """kind=community_music_card - one Music Cards template (fnf-cms-api GET /music-cards-presets): a personalised
    song video preset with its example lyrics, recipients and rendered preview video."""

    music_card_id: str = Field(description="API `id` (uuid)")
    slug: Optional[str] = None
    position: Optional[int] = Field(None, description="0-based order in the API list (the UI shelf order)")
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = Field(None, description="primary category id (joins option group 'category')")
    categories: list[str] = Field(default_factory=list)
    occasion: Optional[str] = Field(None, description="occasion key (joins option group 'occasion')")
    occasion_text: Optional[str] = None
    tone: Optional[str] = None
    style: Optional[str] = Field(None, description="visual style key (joins option group 'style')")
    music: Optional[str] = Field(None, description="music genre key, e.g. ballad")
    length_seconds: Optional[int] = Field(None, description="API `length` (song length, s)")
    song_title: Optional[str] = None
    lyrics: Optional[str] = None
    recipients: list[MusicCardRecipient] = Field(default_factory=list)
    senders: list[Any] = Field(default_factory=list)
    thumbnail_url: Optional[str] = Field(None, description="thumbnail_media.url (static image)")
    thumbnail_width: Optional[int] = Field(None, description="px")
    thumbnail_height: Optional[int] = Field(None, description="px")
    preview_video_url: Optional[str] = Field(None, description="video_media.url (full-size mp4)")
    preview_video_width: Optional[int] = Field(None, description="px")
    preview_video_height: Optional[int] = Field(None, description="px")
    preview_video_duration_seconds: Optional[float] = Field(None, description="s (often null)")
    preview_video_compressed_url: Optional[str] = Field(None, description="video_media.compressed_url (small mp4)")
    preview_video_compressed_width: Optional[int] = Field(None, description="px")
    preview_video_compressed_height: Optional[int] = Field(None, description="px")
    preview_video_compressed_bytes: Optional[int] = Field(None, description="bytes")
    preview_video_thumbnail_url: Optional[str] = Field(None, description="video_media.thumbnail_url (poster)")
    extra: dict[str, Any] = Field(default_factory=dict, description="other non-null API fields")
    source: Provenance


class CommunityMusicCardOption(Strict):
    """kind=community_music_card_option - one value of a Music Cards option list: category (from the presets
    response), style, occasion or role (fnf-cms-api /music-cards-{styles,occasions,roles})."""

    option_id: str = Field(description="make_id('music_card_option', group, key)")
    group: Literal["category", "style", "occasion", "role"]
    key: str = Field(description="category id / style / occasion key / role key")
    label: Optional[str] = None
    hint: Optional[str] = None
    icon_key: Optional[str] = None
    parent: Optional[str] = Field(None, description="parent category id (categories only)")
    thumbnail_url: Optional[str] = None
    categories: list[str] = Field(default_factory=list, description="occasions: categories they belong to")
    position: Optional[int] = Field(None, description="0-based order within the group")
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class CommunityShowcaseJob(Strict):
    """kind=community_showcase_job - one generation of a curated job showcase (fnf GET /jobs/showcase/{slug}; the
    'movies' of /seedance-2-community). Generation-like: generation_id / generation_key (job:) and media_keys
    (media:) join scripts/merge_generations.py. The jobs are unpublished (published_at null), so they have no
    publication id, likes, views or comments."""

    generation_id: str = Field(description="job id (API `id`)")
    generation_key: str = Field(description="'job:<generation_id>' (merge key)")
    media_keys: list[str] = Field(default_factory=list, description="'media:<uuid>' of each output file")
    showcase_slug: str = Field(description="showcase slug, e.g. seedance-2-0")
    url: Optional[str] = Field(None, description="page that shows the showcase")
    movie_index: int = Field(description="0-based index of the movie (data[]) in the showcase")
    movie_position: int = Field(description="0-based position of the job inside its movie")
    movie_logo_url: Optional[str] = None
    movie_group_image_url: Optional[str] = None
    job_set_type: Optional[str] = Field(None, description="joins pricing model_id")
    job_set_id: Optional[str] = None
    parent_id: Optional[str] = Field(None, description="job_set_parent_id")
    media_type: MediaType
    status: Optional[str] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    settings: Settings
    params_extra: dict[str, Any] = Field(default_factory=dict, description="every other params.* key")
    raw_params: Optional[dict[str, Any]] = Field(None, description="only with --with-raw-params")
    inputs: list[InputMedia] = Field(default_factory=list, description="input images/videos/elements (the assets)")
    results: list[ResultVariant] = Field(default_factory=list, description="all variants: raw, min, hls, h264")
    created_at: Optional[AwareDatetime] = None
    published_at: Optional[AwareDatetime] = None
    moderation: Moderation
    board_ids: list[Any] = Field(default_factory=list)
    client_meta: Optional[dict[str, Any]] = None
    meta_extra: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict, description="other non-null top-level job fields")
    creator: PersonRef
    source: Provenance


class CollectionItem(Strict):
    """A motion preset in a collection (joins catalog_motion by motion_id)."""

    position: int
    motion_id: Optional[str] = None
    name: Optional[str] = None
    media_url: Optional[str] = Field(None, description="animated preview (webp)")
    media_type: Optional[str] = None
    width: Optional[int] = Field(None, description="px")
    height: Optional[int] = Field(None, description="px")
    priority: Optional[int] = None
    tags: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict, description="preset params (steps, frames, strength…)")


class CommunityCollection(Strict):
    """kind=community_collection - a curated motion collection (fnf GET /collections/{slug}), e.g. Catch the Pulse."""

    collection_id: str = Field(description="API `id`, or the slug when the API sends null")
    slug: str
    url: str = Field(description="https://higgsfield.ai/collection/<slug>")
    name: Optional[str] = None
    description: Optional[str] = None
    items_count: int = 0
    items: list[CollectionItem] = Field(default_factory=list)
    source: Provenance


class CommunityExploreCard(Strict):
    """kind=community_explore_card - one explore/home card (cms GET /cards): a tile linking to a tool, app or
    model page with a preview image/video."""

    card_id: str = Field(description="API `id` (int, as text)")
    position: Optional[int] = Field(None, description="0-based order in the API list")
    slug: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    href: Optional[str] = None
    href_mobile: Optional[str] = None
    media_type: Optional[str] = Field(None, description="media.type: image | video")
    media_url: Optional[str] = None
    width: Optional[int] = Field(None, description="px")
    height: Optional[int] = Field(None, description="px")
    has_placeholder: bool = Field(False, description="media.placeholder (inline blur data URI) present; not stored")
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class CommunityGalleryStats(Strict):
    music_cards: int = 0
    music_card_options: int = 0
    showcase_jobs: int = 0
    collections: int = 0
    collection_items: int = 0
    explore_cards: int = 0
    music_cards_by_category: dict[str, int] = Field(default_factory=dict)
    showcase_jobs_by_job_set_type: dict[str, int] = Field(default_factory=dict)
    explore_cards_by_media_type: dict[str, int] = Field(default_factory=dict)


class CommunityDatasetGallery(CommunityDatasetExt):
    """Dataset of a run that used an opt-in gallery / template source (--feeds music-cards|job-showcase|collections|
    explore-cards). Other runs keep CommunityDataset / CommunityDatasetExt unchanged."""

    music_cards: list[CommunityMusicCard] = Field(default_factory=list)
    music_card_options: list[CommunityMusicCardOption] = Field(default_factory=list)
    showcase_jobs: list[CommunityShowcaseJob] = Field(default_factory=list)
    collections: list[CommunityCollection] = Field(default_factory=list)
    explore_cards: list[CommunityExploreCard] = Field(default_factory=list)
    gallery_stats: CommunityGalleryStats = Field(default_factory=CommunityGalleryStats)
