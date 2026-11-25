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
