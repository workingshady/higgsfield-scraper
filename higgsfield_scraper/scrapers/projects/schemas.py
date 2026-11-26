"""Pydantic models of the projects scraper (one per entity kind) + the whole dataset.

Personal data: `Person` always carries a pseudonymous `author_key` (sha256 of the user id, 16 hex) and public
counters; `user_id`, `username`, `full_name`, `avatar_url`, `headline`, `location`, `profile_url` stay None unless
`--with-profiles` is given.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from ...core.dataset import CoreMeta, Provenance, Strict

Extra = dict[str, Any]


class Media(Strict):
    role: str = Field(description="cover | gallery | trailer")
    position: int = Field(description="0-based order inside its role")
    media_id: Optional[str] = None
    type: Optional[str] = Field(None, description="media (image) | video | job (a generation) | …")
    name: Optional[str] = None
    url: Optional[str] = Field(None, description="primary URL (videos: HLS .m3u8 playlist or mp4)")
    original_url: Optional[str] = Field(None, description="original upload (mp4/png) when exposed")
    preview_url: Optional[str] = Field(None, description="compressed card preview")
    thumbnail_url: Optional[str] = None
    min_url: Optional[str] = None
    download_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    object_fit: Optional[str] = None
    extra: Extra = Field(default_factory=dict)


class Badge(Strict):
    badge_id: Optional[str] = None
    name: Optional[str] = None
    icon_url: Optional[str] = None
    description: Optional[str] = None


class Person(Strict):
    role: str = Field(description="author | team | winner | contestant | submitter | series_author")
    author_key: Optional[str] = Field(None, description="pseudonymous stable key = sha256(user id)[:16]")
    creator_uid_key: Optional[str] = Field(None, description="cross-scraper pseudonymous key = "
                                                             "core.privacy.creator_uid_key(<clerk user id>)")
    is_owner: Optional[bool] = None
    total_projects_views: Optional[int] = None
    total_projects_likes: Optional[int] = None
    followers_count: Optional[int] = None
    badges: list[Badge] = Field(default_factory=list)
    # --with-profiles only
    user_id: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    profile_url: Optional[str] = None
    extra: Extra = Field(default_factory=dict)


class ContestBadge(Strict):
    contest_key: Optional[str] = None
    list_key: Optional[str] = Field(None, description="e.g. top_50, higgsfield_choice, audience_choice")
    extra: Extra = Field(default_factory=dict)


class ModelUsage(Strict):
    job_set_type: Optional[str] = None
    display_name: Optional[str] = None
    count: Optional[int] = None
    credits_spent: Optional[float] = None


class Publication(Strict):
    """A community project publication (film / series / carousel)."""

    publication_id: str
    project_id: Optional[str] = None
    snapshot_folder_id: Optional[str] = None
    original_folder_id: Optional[str] = None
    root_folder_id: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    type: Optional[str] = Field(None, description="film | series | carousel")
    state: Optional[str] = None
    description: Optional[str] = None
    duration_seconds: Optional[float] = None
    is_ongoing: Optional[bool] = None
    is_open_source: Optional[bool] = None
    has_changes_since_publish: Optional[bool] = None
    show_prompts: Optional[bool] = None
    show_canvas: Optional[bool] = None
    is_discoverable: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_higgsfield_featured: Optional[bool] = None
    is_talents_hub: Optional[bool] = None
    can_receive_audience_choice_votes: Optional[bool] = None
    featured_episode_id: Optional[str] = None
    featured_episode_slug: Optional[str] = Field(None, description="'<series>/<episode>' of /original-series")
    featured_episode_url: Optional[str] = None
    contest_key: Optional[str] = Field(None, description="ai_film_festival | talent_contest | … when it is a contest entry")
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    cover_url: Optional[str] = None
    trailer_url: Optional[str] = None
    media_count: int = 0
    media: list[Media] = Field(default_factory=list)
    episode_count: Optional[int] = Field(None, description="series only: number of gallery videos (= episodes)")
    author_count: int = 0
    author_keys: list[str] = Field(default_factory=list)
    creator_uid_keys: list[str] = Field(default_factory=list, description="authors' cross-scraper creator_uid_key")
    authors: list[Person] = Field(default_factory=list)
    team: Optional[Person] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    votes: Optional[int] = None
    awards: list[Any] = Field(default_factory=list)
    contest_badges: list[ContestBadge] = Field(default_factory=list)
    generations_count: Optional[int] = Field(None, description="detail: generations used in the project")
    credits_spent: Optional[float] = Field(None, description="detail: total credits spent on the project")
    free_generations: Optional[int] = Field(None, description="detail: generations that cost no credits")
    size_bytes: Optional[int] = Field(None, description="detail: project size")
    model_usage: list[ModelUsage] = Field(default_factory=list, description="detail: models used + credits spent")
    listing_credits_spent: Optional[float] = Field(
        None, description="stats.credits_spent as the profile listing (/user/{handle}/v2/publications) reports it: "
                          "a different unit than the detail's credits_spent (observed = credits_spent x 100)")
    listing_model_usage: list[ModelUsage] = Field(
        default_factory=list, description="stats.stack of the profile listing (credits_spent in the listing's unit)")
    created_at: Optional[str] = None
    published_at: Optional[str] = None
    project_updated_at: Optional[str] = None
    final_submitted_at: Optional[str] = None
    grant_awarded_at: Optional[str] = None
    url: Optional[str] = Field(None, description="public page https://higgsfield.ai/@<user>/projects/<slug> "
                                                 "(contains the author handle: --with-profiles only)")
    listing: Optional[str] = Field(None, description="listing in which it was first seen")
    detail_fetched: bool = False
    source: Provenance
    detail_source: Optional[Provenance] = None
    extra: Extra = Field(default_factory=dict, description="unmapped API keys (incl. viewer-specific flags)")


class Episode(Strict):
    episode_id: str
    publication_id: Optional[str] = None
    series_id: Optional[str] = None
    series_slug: Optional[str] = None
    number: Optional[int] = Field(None, description="1-based order")
    slug: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    media_id: Optional[str] = None
    type: Optional[str] = None
    duration_seconds: Optional[float] = None
    video_url: Optional[str] = None
    original_url: Optional[str] = None
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_locked: Optional[bool] = None
    is_adults_only: Optional[bool] = None
    url: Optional[str] = None
    # public series (fnf-series) media variants, added 2026-11-26 (None for publication-gallery episodes)
    thumbnail_optimized_url: Optional[str] = Field(None, description="thumbnail.optimized.url (webp)")
    hls_url: Optional[str] = Field(None, description="video.hls.url")
    hls_job_id: Optional[str] = Field(None, description="video.hls.job_id (transcode job)")
    hls_status: Optional[str] = Field(None, description="video.hls.status")
    video_original_width: Optional[int] = Field(None, description="video.original.width")
    video_original_height: Optional[int] = Field(None, description="video.original.height")
    shimmer_url: Optional[str] = Field(None, description="video.shimmer.url (animated webp placeholder)")
    shimmer_width: Optional[int] = None
    shimmer_height: Optional[int] = None
    source: Provenance
    extra: Extra = Field(default_factory=dict)


class Category(Strict):
    slug: str
    label: Optional[str] = None
    source: Provenance
    extra: Extra = Field(default_factory=dict)


class ContestSettings(Strict):
    max_submissions: Optional[int] = None
    new_project_per_submission: Optional[bool] = None
    allow_generation_move: Optional[bool] = None
    allow_generation_copy: Optional[bool] = None
    source_clip_required: Optional[bool] = None
    extra: Extra = Field(default_factory=dict)


class ContestRewards(Strict):
    first_place_credits: Optional[int] = None
    second_place_credits: Optional[int] = None
    third_place_credits: Optional[int] = None
    honorable_mention_credits: Optional[int] = None
    honorable_mentions_count: Optional[int] = None
    style_champion_credits: Optional[int] = None
    extra: Extra = Field(default_factory=dict)


class Prize(Strict):
    position: int
    label: Optional[str] = None
    type: Optional[str] = Field(None, description="usd | credits")
    value: Optional[float] = None
    count: Optional[int] = None
    extra: Extra = Field(default_factory=dict)


class Faq(Strict):
    position: int
    question: Optional[str] = None
    answer: Optional[str] = None


class Judge(Strict):
    position: int
    display_name: Optional[str] = None
    description: Optional[str] = None
    creator_uid_key: Optional[str] = Field(None, description="cross-scraper pseudonymous key of the judge's user id")
    # --with-profiles only
    user_id: Optional[str] = None
    avatar_url: Optional[str] = None
    background_url: Optional[str] = None
    external_link: Optional[str] = None
    extra: Extra = Field(default_factory=dict)


class Contest(Strict):
    contest_id: str
    slug: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    contest_type: Optional[str] = Field(None, description="global | weekly")
    status: Optional[str] = Field(None, description="created | open | shortlist | judge | finished")
    status_group: Optional[str] = Field(None, description="open | closed")
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    submissions_close_at: Optional[str] = None
    rules_effective_at: Optional[str] = None
    results_published: Optional[bool] = None
    preview_image: Optional[str] = None
    preview_video: Optional[str] = None
    logo_url: Optional[str] = None
    redirect_url: Optional[str] = None
    prize_pool: Optional[int] = Field(None, description="headline prize pool (unit: prize_pool_unit)")
    prize_pool_unit: Optional[str] = Field(None, description="usd | credits (from detail prizes; None if unknown/mixed)")
    submissions_count: Optional[int] = None
    entries_count: Optional[int] = None
    is_trending: Optional[bool] = None
    winner: Optional[Person] = None
    some_contestants_count: int = 0
    some_contestants: list[Person] = Field(default_factory=list)
    judge_count: int = 0
    judges: list[Judge] = Field(default_factory=list)
    settings: Optional[ContestSettings] = None
    rewards: Optional[ContestRewards] = None
    prizes: list[Prize] = Field(default_factory=list)
    theme_markdown: Optional[str] = None
    details_markdown: Optional[str] = None
    faq: list[Faq] = Field(default_factory=list)
    timeline: Optional[dict[str, Any]] = Field(None, description="festival programme (steps/blocks), as returned")
    winner_submission_ids: list[str] = Field(default_factory=list)
    submission_ids: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    detail_fetched: bool = False
    source: Provenance
    detail_source: Optional[Provenance] = None
    extra: Extra = Field(default_factory=dict)


class Submission(Strict):
    submission_id: str
    contest_id: Optional[str] = None
    contest_slug: Optional[str] = None
    type: Optional[str] = None
    project_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    thumbnail_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    video_preview_url: Optional[str] = None
    winner_place: Optional[str] = Field(None, description="1st | 2nd | 3rd | hm | cc")
    honorable_mention: Optional[bool] = None
    style_champion: Optional[bool] = None
    shortlisted: Optional[bool] = None
    has_source_video: Optional[bool] = None
    has_assets: Optional[bool] = None
    clone_available: Optional[bool] = None
    likes_count: Optional[int] = None
    dislikes_count: Optional[int] = None
    views_count: Optional[int] = None
    total_views: Optional[int] = None
    social_media_metrics: dict[str, Any] = Field(default_factory=dict)
    post_url_count: int = 0
    post_urls: list[str] = Field(default_factory=list, description="social posts (--with-profiles only)")
    moderation_status: Optional[str] = None
    suspend_reason: Optional[str] = None
    winner_feedback: Optional[str] = None
    winner_reviewer_name: Optional[str] = None
    winner_reviewer_company: Optional[str] = None
    badges: list[Any] = Field(default_factory=list)
    user: Optional[Person] = None
    publication_id: Optional[str] = None
    publication_slug: Optional[str] = None
    publication_url: Optional[str] = None
    listing: Optional[str] = Field(None, description="submissions | winners")
    url: Optional[str] = None
    source: Provenance
    extra: Extra = Field(default_factory=dict)


class Series(Strict):
    """Higgsfield original series (GET /series, LOGIN ONLY). Parser written from the web app's JS."""
    # ^ docstring kept verbatim: it is the description in every run's dataset.schema.json. In fact the series are
    # public on the fnf-series service (--public-series); only the legacy fnf path is session-gated (and 404s).

    series_id: str
    slug: Optional[str] = None
    title: Optional[str] = None
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    author_type: Optional[str] = None
    author: Optional[Person] = None
    is_series: Optional[bool] = None
    state: Optional[str] = None
    portrait_url: Optional[str] = None
    landscape_url: Optional[str] = None
    background_url: Optional[str] = None
    logo_url: Optional[str] = None
    trailer_url: Optional[str] = None
    trailer_hls_url: Optional[str] = None
    portrait_optimized_url: Optional[str] = Field(None, description="portrait.optimized.url (webp)")
    landscape_optimized_url: Optional[str] = Field(None, description="landscape.optimized.url (webp)")
    background_optimized_url: Optional[str] = Field(None, description="background.optimized.url (webp)")
    logo_optimized_url: Optional[str] = Field(None, description="logo.optimized.url")
    trailer_width: Optional[int] = Field(None, description="trailer.original.width")
    trailer_height: Optional[int] = Field(None, description="trailer.original.height")
    trailer_hls_job_id: Optional[str] = Field(None, description="trailer.hls.job_id")
    project_url: Optional[str] = None
    project_publication_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    likes: Optional[int] = None
    views: Optional[int] = None
    comments: Optional[int] = None
    vote_count: Optional[int] = None
    subscriber_count: Optional[int] = None
    categories: list[str] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)
    banner_images: list[str] = Field(default_factory=list)
    episode_count: Optional[int] = None
    url: Optional[str] = None
    detail_fetched: bool = False
    source: Provenance
    extra: Extra = Field(default_factory=dict)


class ListingEntry(Strict):
    """Membership of a publication in a listing (keeps ranks even though publications are de-duplicated)."""

    entry_id: str
    listing: str = Field(description="e.g. publications, publications:category=spotlight, recommended:community, "
                                     "entries:ai_film_festival:latest")
    publication_id: str
    position: Optional[int] = Field(None, description="0-based rank when the cursor is an offset")
    page_cursor: Optional[str] = None
    index_in_page: int
    source: Provenance


MODEL_BY_KIND = {
    "projects_publication": Publication,
    "projects_publication_detail": Publication,
    "projects_episode": Episode,
    "projects_category": Category,
    "projects_contest": Contest,
    "projects_contest_detail": Contest,
    "projects_contest_submission": Submission,
    "projects_series": Series,
    "projects_listing_entry": ListingEntry,
}
ID_FIELD_BY_KIND = {
    "projects_publication": "publication_id",
    "projects_publication_detail": "publication_id",
    "projects_episode": "episode_id",
    "projects_category": "slug",
    "projects_contest": "contest_id",
    "projects_contest_detail": "contest_id",
    "projects_contest_submission": "submission_id",
    "projects_series": "series_id",
    "projects_listing_entry": "entry_id",
}


# ====================================================================== nested project data (opt-in, 2026-11-26)
# contest -> submission -> publication -> folder -> asset (+ brief, stats/stack, comments, related).
# Only built with a --with-project-* flag; the default dataset (ProjectsDataset) is unchanged.
# Field tables and the ER diagram: docs/scrapers/projects.md "Nested data model".
class _NestedBase(Strict):
    source: Provenance
    source_url: str = Field(description="URL of the API response this row came from")
    scraped_at: str = Field(description="UTC ISO-8601 fetch time of that response")
    schema_version: int = Field(1, description="version of the nested-entity schema")


class ProjectFolder(_NestedBase):
    """A folder of a published project (GET /folders/{id} for the root, /folders/{id}/children below it)."""

    folder_id: str
    publication_id: Optional[str] = None
    root_folder_id: Optional[str] = Field(None, description="the project's snapshot folder (= the 'All assets' view)")
    parent_id: Optional[str] = None
    is_root: Optional[bool] = None
    depth: Optional[int] = Field(None, description="0 = root, 1 = top-level folder (Cast, Scenes ...), 2 = sub-folder")
    position: Optional[int] = Field(None, description="0-based order in the parent's children list")
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None
    color: Optional[str] = None
    surface: Optional[str] = Field(None, description="e.g. contests (root), cast, locations, scenes, watermarks")
    folder_kind: Optional[str] = Field(None, description="API `kind`")
    asset_count: Optional[int] = Field(None, description="API `count`: assets in the folder incl. sub-folders "
                                                         "(the number next to the folder name on the page)")
    subfolders_count: Optional[int] = None
    views_count: Optional[int] = None
    copies_count: Optional[int] = None
    access_mode: Optional[str] = None
    link_access_level: Optional[str] = None
    is_snapshot: Optional[bool] = None
    is_discoverable: Optional[bool] = None
    locked: Optional[bool] = None
    preview_url: Optional[str] = None
    cover_image_url: Optional[str] = None
    contest_key: Optional[str] = None
    contest_id: Optional[str] = None
    project_id: Optional[str] = None
    publication_state: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    archived_at: Optional[str] = None
    hidden_at: Optional[str] = None
    assets_scraped: Optional[int] = Field(None, description="assets scraped in this folder or below it "
                                                            "(build-time check against asset_count)")
    owner_key: Optional[str] = Field(None, description="pseudonymous owner key = sha256(user id)[:16]")
    creator_uid_key: Optional[str] = Field(None, description="the owner's cross-scraper creator_uid_key")
    path: Optional[str] = Field(None, description="raw id path '/<root id>/<folder id>/.../'")
    owner_user_id: Optional[str] = Field(None, description="--with-profiles only")
    owner_username: Optional[str] = Field(None, description="--with-profiles only")
    extra: Extra = Field(default_factory=dict)


class AssetVariant(Strict):
    variant: str = Field(description="raw (original) | min (preview) | hls | h264 | ...")
    type: Optional[str] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    extra: Extra = Field(default_factory=dict)


class AssetInput(Strict):
    position: int
    role: Optional[str] = Field(None, description="image | video | start_image | ...")
    media_id: Optional[str] = None
    type: Optional[str] = Field(None, description="media_input (upload) | image_job (another generation) | ...")
    url: Optional[str] = None


class ProjectAsset(_NestedBase):
    """One asset placement of a project (GET /folders/{root}/items/v2?include_subfolders=true): a generation (job)
    or an upload (audio_input, ...). The job id is the asset id."""

    placement_id: str = Field(description="API folder_job_id (one placement of the asset in a folder)")
    asset_id: str = Field(description="job id / upload id")
    item_type: Optional[str] = Field(None, description="job | audio_input | media_input | ...")
    position: Optional[int] = Field(None, description="0-based order in its listing (the 'All assets' grid)")
    in_all_assets: bool = Field(True, description="listed by the root folder's items (the page's 'All assets'); "
                                                  "False for sub-folders that listing omits (Watermarks)")
    publication_id: Optional[str] = None
    root_folder_id: Optional[str] = None
    folder_id: Optional[str] = Field(None, description="the (sub-)folder holding the asset")
    folder_name: Optional[str] = None
    folder_path: Optional[str] = Field(None, description="folder names below the root, e.g. 'Cast / Saber'")
    status: Optional[str] = None
    media_type: Optional[str] = Field(None, description="image | video | audio")
    job_set_id: Optional[str] = None
    job_set_type: Optional[str] = Field(None, description="model key, e.g. seedance_2_5")
    job_set_parent_id: Optional[str] = None
    model_name: Optional[str] = Field(None, description="display name from the project stack (needs stats)")
    prompts_visible: bool = Field(description="the author's show_prompts flag; False -> prompt and prompt params "
                                              "are not stored")
    prompt: Optional[str] = None
    has_prompt: bool = False
    params: dict[str, Any] = Field(default_factory=dict, description="generation parameters as returned "
                                                                     "(prompt keys removed when not visible)")
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = Field(None, description="e.g. 480p, 720p, 2k (params.resolution or quality)")
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    seed: Optional[int] = None
    batch_size: Optional[int] = None
    input_media: list[AssetInput] = Field(default_factory=list, description="reference media (params.medias)")
    url: Optional[str] = Field(None, description="original file (results.raw.url, or the upload url)")
    min_url: Optional[str] = Field(None, description="compressed preview (results.min.url)")
    thumbnail_url: Optional[str] = None
    hls_url: Optional[str] = None
    h264_url: Optional[str] = None
    download_url: Optional[str] = None
    waveform_url: Optional[str] = None
    variants: list[AssetVariant] = Field(default_factory=list)
    filename: Optional[str] = None
    extension: Optional[str] = None
    size_bytes: Optional[int] = None
    cost_raw: Optional[str] = Field(None, description="job meta.cost as returned (unit not documented; not credits)")
    comments_count: Optional[int] = None
    review_status: Optional[str] = None
    created_at: Optional[str] = None
    uploaded_at: Optional[str] = None
    creator_key: Optional[str] = Field(None, description="pseudonymous creator key = sha256(user id)[:16]")
    creator_uid_key: Optional[str] = Field(None, description="cross-scraper creator_uid_key of the creator")
    creator_user_id: Optional[str] = Field(None, description="--with-profiles only")
    creator_username: Optional[str] = Field(None, description="--with-profiles only")
    extra: Extra = Field(default_factory=dict)


class ProjectBrief(_NestedBase):
    """The project brief (Yjs snapshot of the Lexical document) rendered as Markdown."""

    brief_id: str = Field(description="= folder_id (one brief per project folder)")
    publication_id: Optional[str] = None
    folder_id: Optional[str] = None
    publication_slug: Optional[str] = None
    title: Optional[str] = None
    has_content: bool = False
    markdown: Optional[str] = None
    updated_at: Optional[str] = Field(None, description="X-Brief-Updated-At (epoch ms) as UTC ISO-8601")
    snapshot_bytes: int = 0
    block_count: int = 0
    word_count: int = 0
    node_types: dict[str, int] = Field(default_factory=dict, description="Lexical node types -> count")
    links: list[str] = Field(default_factory=list)
    referenced_ids: list[str] = Field(default_factory=list, description="UUIDs written in the brief (job ids ...)")
    referenced_asset_ids: list[str] = Field(default_factory=list,
                                            description="referenced_ids that are assets of this project")
    file: Optional[str] = Field(None, description="output/briefs/<slug>.md")
    decode_error: Optional[str] = None


class ProjectStats(_NestedBase):
    """The page's stats block (publication detail `stats`)."""

    publication_id: str
    generations_count: Optional[int] = Field(None, description="'Generations'")
    free_generations: Optional[int] = None
    credits_spent: Optional[float] = Field(None, description="'Credits spent' (credits, not cents)")
    size_bytes: Optional[int] = None
    size_mb: Optional[float] = Field(None, description="'Size' = size_bytes / 1,000,000, 1 decimal (decimal MB)")
    model_count: int = Field(0, description="stack entries shown (count>0 or credits>0)")
    stack_generations: int = Field(0, description="sum of the shown stack counts (denominator of percent)")
    extra: Extra = Field(default_factory=dict)


class ProjectStackItem(_NestedBase):
    """One model of the page's 'Stack' (publication detail stats.stack)."""

    stack_item_id: str
    publication_id: str
    position: int
    job_set_type: Optional[str] = None
    display_name: Optional[str] = None
    label: Optional[str] = Field(None, description="label shown by the page (display_name with UI renames)")
    count: Optional[int] = Field(None, description="generations with this model")
    credits_spent: Optional[float] = None
    shown_in_ui: bool = Field(description="count>0 or credits_spent>0 (the page hides the others)")
    share: Optional[float] = Field(None, description="count / stack_generations * 100 (computed like the page)")
    percent: Optional[float] = Field(None, description="share rounded to 0.1 by largest remainder (the page's %)")
    extra: Extra = Field(default_factory=dict)


class ProjectComment(_NestedBase):
    comment_id: str
    publication_id: Optional[str] = None
    thread_type: Optional[str] = Field(None, description="API entity_type (project_publication)")
    parent_id: Optional[str] = None
    is_reply: bool = False
    text: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    likes: Optional[int] = None
    dislikes: Optional[int] = None
    reply_count: Optional[int] = None
    reactions: list[dict[str, Any]] = Field(default_factory=list)
    mention_count: int = 0
    author: Optional[Person] = Field(None, description="pseudonymous unless --with-profiles")
    is_by_author: Optional[bool] = Field(None, description="the commenter is one of the project's authors")
    extra: Extra = Field(default_factory=dict)


class RelatedMedia(Strict):
    position: int
    media_id: Optional[str] = None
    type: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = Field(None, description="primary URL (videos: HLS .m3u8)")
    original_url: Optional[str] = None
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    download_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = Field(None, description="seconds")


class ProjectRelated(_NestedBase):
    """One entry of the page's related-projects list (recommended?scope=...&current_publication_id=...)."""

    related_id: str
    publication_id: Optional[str] = None
    related_publication_id: str
    position: int
    scope: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    type: Optional[str] = None
    contest_key: Optional[str] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    comments: Optional[int] = None
    cover_url: Optional[str] = None
    author_keys: list[str] = Field(default_factory=list)
    feed_source: Optional[str] = None
    # project card media (added 2026-11-26, COMPLETENESS #6)
    title: Optional[str] = Field(None, description="= name (the card title)")
    description: Optional[str] = None
    duration_seconds: Optional[float] = None
    tags: list[str] = Field(default_factory=list)
    show_prompts: Optional[bool] = None
    created_at: Optional[str] = None
    cover_width: Optional[int] = None
    cover_height: Optional[int] = None
    trailer_url: Optional[str] = None
    trailer_thumbnail_url: Optional[str] = None
    trailer_width: Optional[int] = None
    trailer_height: Optional[int] = None
    trailer_duration_seconds: Optional[float] = None
    gallery_media: list[RelatedMedia] = Field(default_factory=list)
    team: Optional[Person] = None
    creator_uid_keys: list[str] = Field(default_factory=list)


NESTED_MODEL_BY_KIND = {
    "projects_folder": ProjectFolder,
    "projects_asset": ProjectAsset,
    "projects_brief": ProjectBrief,
    "projects_stats": ProjectStats,
    "projects_stack_item": ProjectStackItem,
    "projects_comment": ProjectComment,
    "projects_related": ProjectRelated,
}
NESTED_ID_FIELD_BY_KIND = {
    "projects_folder": "folder_id",
    "projects_asset": "placement_id",
    "projects_brief": "brief_id",
    "projects_stats": "publication_id",
    "projects_stack_item": "stack_item_id",
    "projects_comment": "comment_id",
    "projects_related": "related_id",
}
MODEL_BY_KIND.update(NESTED_MODEL_BY_KIND)
ID_FIELD_BY_KIND.update(NESTED_ID_FIELD_BY_KIND)


class Summary(Strict):
    publications_by_type: dict[str, int] = Field(default_factory=dict)
    publications_by_listing: dict[str, int] = Field(default_factory=dict)
    publications_with_details: int = 0
    episodes: int = 0
    contests_by_status: dict[str, int] = Field(default_factory=dict)
    contests_by_type: dict[str, int] = Field(default_factory=dict)
    submissions_by_contest: dict[str, int] = Field(default_factory=dict)
    total_views: int = 0
    total_likes: int = 0
    with_profiles: bool = False


class ProjectsDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    publications: list[Publication] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)
    categories: list[Category] = Field(default_factory=list)
    contests: list[Contest] = Field(default_factory=list)
    submissions: list[Submission] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    listing_entries: list[ListingEntry] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)


class NestedSummary(Strict):
    projects: int = Field(0, description="publications with any nested data")
    folders: int = 0
    assets: int = 0
    assets_by_media_type: dict[str, int] = Field(default_factory=dict)
    assets_by_model: dict[str, int] = Field(default_factory=dict)
    prompts_visible: int = 0
    briefs: int = 0
    comments: int = 0
    related: int = 0
    asset_count_mismatches: list[str] = Field(default_factory=list,
                                              description="root folders whose API count != assets scraped")


class ProjectsNestedDataset(ProjectsDataset):
    """ProjectsDataset + the nested project collections (only with a --with-project-* flag)."""

    folders: list[ProjectFolder] = Field(default_factory=list)
    assets: list[ProjectAsset] = Field(default_factory=list)
    briefs: list[ProjectBrief] = Field(default_factory=list)
    project_stats: list[ProjectStats] = Field(default_factory=list)
    stack_items: list[ProjectStackItem] = Field(default_factory=list)
    comments: list[ProjectComment] = Field(default_factory=list)
    related: list[ProjectRelated] = Field(default_factory=list)
    nested_summary: NestedSummary = Field(default_factory=NestedSummary)


NESTED_COLLECTIONS = ("folders", "assets", "briefs", "project_stats", "stack_items", "comments", "related")


# ====================================================================== opt-in extras (2026-11-26)
# --what trending, --what contest-participation, --with-user-works. Only built when selected; the default and the
# nested datasets are unchanged. Docs: docs/scrapers/projects.md "Trending, contest participation, user works".
class TrendingRow(_NestedBase):
    """One rank of the trending project ranking (GET /project-publications/trending; the only project listing that
    reports a `total`). The publication itself is in `publications` (listing 'trending...')."""

    row_id: str = Field(description="sha256(snapshot or listing, publication_id)[:16]")
    publication_id: str
    position: Optional[int] = Field(None, description="0-based rank (API feed_position - 1, else page offset + index)")
    feed_position: Optional[int] = Field(None, description="API feed_position (1-based)")
    feed_lane: Optional[str] = Field(None, description="API feed_lane")
    listing: str = Field(description="trending[:filter=...][:sort=...][:with_contest]")
    sort: Optional[str] = Field(None, description="default | most_viewed | most_liked | newest | oldest")
    filter: Optional[str] = Field(None, description="all | non_contest | contest | talents_hub (None = not sent)")
    with_contest: bool = False
    total_reported: Optional[int] = Field(None, description="API `total` of the ranking")
    snapshot_id: Optional[str] = Field(None, description="feed.snapshot_id (one ranking snapshot)")
    feed_source: Optional[str] = None
    feed_version: Optional[str] = None
    page_cursor: Optional[str] = None
    index_in_page: int = 0


class ParticipationCounters(_NestedBase):
    """GET /contest-participations/publications/counters?contest_key=...: entry counts of a contest."""

    contest_key: str = Field(description="ai_film_festival | talent_contest")
    total: Optional[int] = None
    public_total: Optional[int] = None
    private_total: Optional[int] = None
    extra: Extra = Field(default_factory=dict)


class ParticipationConfig(_NestedBase):
    """GET /contest-participations/config?contest_key=...: stage, windows and rules of a contest."""

    contest_key: str
    display_name: Optional[str] = None
    stage: Optional[str] = Field(None, description="upcoming | open | closed | voting")
    starts_at: Optional[str] = None
    submissions_close_at: Optional[str] = None
    create_in_public_closes_at: Optional[str] = None
    submissions_visible_at: Optional[str] = None
    voting_opens_at: Optional[str] = None
    voting_closes_at: Optional[str] = None
    rules_version: Optional[int] = None
    allows_multiple_projects: Optional[bool] = None
    max_projects: Optional[int] = None
    max_team_size: Optional[int] = None
    max_public_submissions: Optional[int] = None
    votes_per_user: Optional[int] = None
    watch_required: Optional[bool] = None
    final_submissions_open_at: Optional[str] = Field(None, description="timeline.final_submissions_open_at")
    judging_closes_at: Optional[str] = Field(None, description="timeline.judging_closes_at")
    results_announced_at: Optional[str] = Field(None, description="timeline.results_announced_at")
    final_min_seconds: Optional[float] = Field(None, description="limits.final_min_seconds")
    final_max_seconds: Optional[float] = Field(None, description="limits.final_max_seconds")
    min_generations: Optional[int] = Field(None, description="limits.min_generations")
    live_min_seconds: Optional[float] = Field(None, description="limits.live_min_seconds")
    countries: Optional[list[Any]] = None
    extra: Extra = Field(default_factory=dict)


class ContestParticipation(Strict):
    """counters + config of one contest_key, merged by build_dataset (collection `contest_participation`)."""

    contest_key: str
    contest_slug: Optional[str] = None
    total: Optional[int] = None
    public_total: Optional[int] = None
    private_total: Optional[int] = None
    display_name: Optional[str] = None
    stage: Optional[str] = None
    starts_at: Optional[str] = None
    submissions_close_at: Optional[str] = None
    create_in_public_closes_at: Optional[str] = None
    submissions_visible_at: Optional[str] = None
    voting_opens_at: Optional[str] = None
    voting_closes_at: Optional[str] = None
    rules_version: Optional[int] = None
    allows_multiple_projects: Optional[bool] = None
    max_projects: Optional[int] = None
    max_team_size: Optional[int] = None
    max_public_submissions: Optional[int] = None
    votes_per_user: Optional[int] = None
    watch_required: Optional[bool] = None
    final_submissions_open_at: Optional[str] = None
    judging_closes_at: Optional[str] = None
    results_announced_at: Optional[str] = None
    final_min_seconds: Optional[float] = None
    final_max_seconds: Optional[float] = None
    min_generations: Optional[int] = None
    live_min_seconds: Optional[float] = None
    countries: Optional[list[Any]] = None
    counters_source_url: Optional[str] = None
    config_source_url: Optional[str] = None
    scraped_at: Optional[str] = None
    extra: Extra = Field(default_factory=dict)


class UserWork(_NestedBase):
    """One published work of a user (GET /user/{user_id}/v2/publications, --with-user-works; only users already
    found in the run). `asset` works are full generations (prompt, params, results) and carry `generation_key` +
    `media_keys` for scripts/merge_generations.py; other types (project_publication, folder, contest_submission)
    are summary rows. Pseudonymous: user_id/username/avatar only with --with-profiles."""

    work_id: str = Field(description="sha256(creator_uid_key, publication_type, item id)[:16]")
    creator_uid_key: Optional[str] = Field(None, description="the profile owner's cross-scraper key")
    creator_key: Optional[str] = Field(None, description="= the projects author_key of the owner")
    position: Optional[int] = Field(None, description="0-based order in the profile listing")
    publication_type: Optional[str] = Field(None, description="asset | project_publication | folder | "
                                                              "contest_submission")
    publication_id: Optional[str] = Field(None, description="asset: the generation's publication id (id_); "
                                                            "project: publication_id")
    generation_key: Optional[str] = Field(None, description="'job:<job id>' for assets (merge_generations key)")
    media_keys: list[str] = Field(default_factory=list, description="'media:<uuid>' of the output URLs")
    job_id: Optional[str] = Field(None, description="asset: data.id (the job)")
    status: Optional[str] = None
    job_set_id: Optional[str] = None
    job_set_type: Optional[str] = Field(None, description="model key, e.g. seedream_v5_lite")
    job_set_parent_id: Optional[str] = None
    job_source: Optional[str] = Field(None, description="job_set_client_meta.source")
    media_type: Optional[str] = Field(None, description="image | video | audio")
    prompt: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict, description="generation parameters, verbatim")
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    seed: Optional[int] = None
    batch_size: Optional[int] = None
    input_media: list[AssetInput] = Field(default_factory=list)
    url: Optional[str] = Field(None, description="asset: results.raw.url")
    min_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    hls_url: Optional[str] = None
    h264_url: Optional[str] = None
    variants: list[AssetVariant] = Field(default_factory=list)
    likes: Optional[int] = Field(None, description="asset: publication.likes_count; project: likes")
    views: Optional[int] = Field(None, description="asset: publication.views_count; project: views")
    listing_views: Optional[int] = Field(None, description="top-level `views` of the profile item")
    clones: Optional[int] = Field(None, description="top-level `clones` of the profile item")
    approved: Optional[bool] = None
    pinned_at: Optional[str] = None
    created_at: Optional[str] = None
    published_at: Optional[str] = None
    # project_publication / folder / contest_submission summary fields
    name: Optional[str] = Field(None, description="project name / folder name / submission title")
    slug: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None
    folder_id: Optional[str] = None
    submission_id: Optional[str] = None
    contest_id: Optional[str] = None
    contest_slug: Optional[str] = None
    contest_key: Optional[str] = None
    video_url: Optional[str] = None
    preview_url: Optional[str] = None
    credits_spent_raw: Optional[float] = Field(None, description="project: stats.credits_spent (listing unit)")
    generations_count: Optional[int] = None
    # --with-profiles only
    user_id: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    extra: Extra = Field(default_factory=dict)


class UserStats(_NestedBase):
    """GET /user/{user_id}/stats (--with-user-works)."""

    creator_uid_key: str
    creator_key: Optional[str] = None
    posts_count: Optional[int] = None
    likes_count: Optional[int] = None
    views_count: Optional[int] = None
    works_total: Optional[int] = Field(None, description="filled by build_dataset: the works listing's `total`")
    user_id: Optional[str] = Field(None, description="--with-profiles only")
    extra: Extra = Field(default_factory=dict)


EXTRA_MODEL_BY_KIND = {
    "projects_trending_row": TrendingRow,
    "projects_participation_counters": ParticipationCounters,
    "projects_participation_config": ParticipationConfig,
    "projects_user_work": UserWork,
    "projects_user_stats": UserStats,
}
EXTRA_ID_FIELD_BY_KIND = {
    "projects_trending_row": "row_id",
    "projects_participation_counters": "contest_key",
    "projects_participation_config": "contest_key",
    "projects_user_work": "work_id",
    "projects_user_stats": "creator_uid_key",
}
MODEL_BY_KIND.update(EXTRA_MODEL_BY_KIND)
ID_FIELD_BY_KIND.update(EXTRA_ID_FIELD_BY_KIND)
EXTRA_COLLECTIONS = ("trending", "contest_participation", "user_works", "user_stats")


class _Extras(Strict):
    trending: list[TrendingRow] = Field(default_factory=list)
    contest_participation: list[ContestParticipation] = Field(default_factory=list)
    user_works: list[UserWork] = Field(default_factory=list)
    user_stats: list[UserStats] = Field(default_factory=list)


class ProjectsExtrasDataset(_Extras, ProjectsDataset):
    """ProjectsDataset + the opt-in extras (trending, contest participation, user works / stats)."""


class ProjectsNestedExtrasDataset(_Extras, ProjectsNestedDataset):
    """ProjectsNestedDataset + the opt-in extras."""
