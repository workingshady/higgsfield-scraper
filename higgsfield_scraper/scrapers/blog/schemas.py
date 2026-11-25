"""Pydantic models for the blog scraper (one per kind) + BlogDataset."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta, Provenance, Strict

ContentFormat = Literal["html", "markdown", "lexical"]


# ------------------------------------------------------------------ shared parts

class Heading(Strict):
    level: int
    text: str
    anchor: Optional[str] = None


class Link(Strict):
    url: str
    text: Optional[str] = None
    internal: bool = False


class Image(Strict):
    url: Optional[str] = Field(None, description="absolute URL; None for embeds referenced only by id")
    alt: Optional[str] = None
    kind: str = Field("image", description="image | video | embed")
    ref_id: Optional[str] = Field(None, description="Higgsfield media/asset id of an embed (community posts)")
    poster_url: Optional[str] = Field(None, description="video poster frame (CMS asset blocks)")


class Category(Strict):
    id: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None


class AuthorRef(Strict):
    id: Optional[str] = None
    slug: Optional[str] = None
    name: Optional[str] = None
    position: Optional[str] = None


class FaqItem(Strict):
    question: str
    answer_text: Optional[str] = None
    answer_html: Optional[str] = None


class RelatedRef(Strict):
    id: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    category_slug: Optional[str] = None
    published_at: Optional[AwareDatetime] = None


class Cta(Strict):
    title: Optional[str] = None
    description: Optional[str] = None
    text: Optional[str] = None
    link: Optional[str] = None


class BodyFields(Strict):
    """Article body (filled when --with-content, the default)."""

    content_format: Optional[ContentFormat] = None
    content_html: Optional[str] = Field(None, description="CMS HTML as published (blog, help, case studies, changelog)")
    content_markdown: Optional[str] = None
    content_text: Optional[str] = Field(None, description="plain text (Markdown syntax stripped)")
    content_blocks: Optional[list[dict[str, Any]]] = Field(
        None, description="Lexical node tree (community/talent posts decoded from the Yjs .bin)")
    word_count: Optional[int] = None
    headings: list[Heading] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)


# ------------------------------------------------------------------ kinds

class BlogPost(BodyFields):
    """kind=blog_post — a Higgsfield blog article (Sanity CMS, rendered at /blog/<slug>)."""

    post_id: str
    slug: str
    url: str
    locale: str = "en"
    title: Optional[str] = None
    breadcrumb_title: Optional[str] = None
    subtitle: Optional[str] = Field(None, description="hero/banner lead paragraph")
    description: Optional[str] = None
    seo_description: Optional[str] = None
    category: Optional[Category] = None
    tags: list[str] = Field(default_factory=list, description="category slug (CMS posts have no free tags)")
    author: Optional[AuthorRef] = None
    cover_url: Optional[str] = None
    card_url: Optional[str] = None
    banner_image_url: Optional[str] = None
    hero_media_url: Optional[str] = None
    hero_media_type: Optional[str] = None
    hero_media_width: Optional[int] = None
    hero_media_height: Optional[int] = None
    cta: Optional[Cta] = None
    reading_time: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    published_at: Optional[AwareDatetime] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    publish_date_label: Optional[str] = None
    likes_count: Optional[int] = Field(None, description="not exposed for CMS posts (always None)")
    views_count: Optional[int] = Field(None, description="not exposed for CMS posts (always None)")
    related_posts: list[RelatedRef] = Field(default_factory=list)
    faq: list[FaqItem] = Field(default_factory=list)
    about: Optional[dict[str, Any]] = None
    localization_status: Optional[str] = None
    sitemap_lastmod: Optional[str] = None
    page_title: Optional[str] = None
    record_source: Literal["page", "index"] = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class BlogAuthor(Strict):
    """kind=blog_author — /blog/author/<slug> (Higgsfield staff authors)."""

    slug: str
    author_id: Optional[str] = None
    name: Optional[str] = None
    position: Optional[str] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    url: str
    post_count: int = 0
    post_slugs: list[str] = Field(default_factory=list)
    record_source: Literal["page", "post"] = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class UserAuthor(Strict):
    user_id: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = Field(None, description="only with --include-author-avatars")


class Cover(Strict):
    id: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class UserBlogPost(BodyFields):
    """kind=blog_talent_post (talents feed) / blog_community_post (recommended feed) — creator-written posts."""

    post_id: str
    feed: Literal["talents", "community"]
    slug: Optional[str] = None
    url: Optional[str] = None
    state: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    cover: Optional[Cover] = None
    author: Optional[UserAuthor] = None
    reading_time: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    likes_count: Optional[int] = None
    views_count: Optional[int] = None
    breadcrumb_label: Optional[str] = None
    pinned_position: Optional[int] = None
    folder_id: Optional[str] = None
    content_url: Optional[str] = None
    related_posts: list[Any] = Field(default_factory=list)
    review_state: Optional[str] = None
    flagged_media: Optional[Any] = None
    published_at: Optional[AwareDatetime] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    content_status: Optional[str] = Field(None, description="ok | not_fetched | error: ... (Yjs decode)")
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class UserPostContent(BodyFields):
    """kind=blog_post_content — decoded body of one community/talent post (merged into the post by build_dataset)."""

    post_id: str
    content_url: Optional[str] = None
    content_bytes: Optional[int] = None
    content_status: str = "ok"
    source: Provenance


class HelpArticle(BodyFields):
    """kind=blog_help_article — Creator Hub help center or Enterprise help center article."""

    article_id: str
    section: Literal["creator-hub", "enterprise"]
    slug: str
    url: str
    locale: str = "en"
    category_slug: Optional[str] = None
    category: Optional[Category] = None
    title: Optional[str] = None
    card_title: Optional[str] = None
    description: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    search_keywords: list[str] = Field(default_factory=list)
    order: Optional[int] = None
    author: Optional[AuthorRef] = None
    card_image_url: Optional[str] = None
    reading_time: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    faq: list[FaqItem] = Field(default_factory=list)
    related_articles: list[RelatedRef] = Field(default_factory=list)
    previous_slug: Optional[str] = None
    next_slug: Optional[str] = None
    markdown_url: Optional[str] = None
    content_language: Optional[str] = None
    localization_status: Optional[str] = None
    breadcrumbs: list[str] = Field(default_factory=list)
    sitemap_lastmod: Optional[str] = None
    page_title: Optional[str] = None
    record_source: Literal["page", "index"] = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class Metric(Strict):
    label: Optional[str] = None
    value: Optional[str] = None


class Tool(Strict):
    name: Optional[str] = None
    slug: Optional[str] = None
    icon_url: Optional[str] = None


class CaseStudy(BodyFields):
    """kind=blog_case_study — /creator-hub/case-studies/<slug>."""

    case_study_id: str
    slug: str
    url: str
    locale: str = "en"
    title: Optional[str] = None
    breadcrumb_title: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    seo_description: Optional[str] = None
    category: Optional[Category] = None
    author: Optional[AuthorRef] = None
    cover_url: Optional[str] = None
    card_url: Optional[str] = None
    banner_image_url: Optional[str] = None
    hero_media_url: Optional[str] = None
    hero_media_type: Optional[str] = None
    cta: Optional[Cta] = None
    hero_metrics: list[Metric] = Field(default_factory=list)
    tools_used: list[Tool] = Field(default_factory=list)
    about_title: Optional[str] = None
    about_intro: Optional[str] = None
    about_facts: list[Any] = Field(default_factory=list)
    reading_time: Optional[str] = None
    reading_time_minutes: Optional[int] = None
    published_at: Optional[AwareDatetime] = None
    created_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    related_posts: list[RelatedRef] = Field(default_factory=list)
    faq: list[FaqItem] = Field(default_factory=list)
    sitemap_lastmod: Optional[str] = None
    page_title: Optional[str] = None
    record_source: Literal["page", "index"] = "page"
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


class Chip(Strict):
    id: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None


class ChangelogEntry(BodyFields):
    """kind=blog_changelog_entry — one entry of /creator-hub/changelog."""

    entry_id: str
    anchor: Optional[str] = None
    url: str
    title: Optional[str] = None
    summary: Optional[str] = None
    category: Optional[Category] = None
    category_slug: Optional[str] = None
    chips: list[Chip] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    released_at: Optional[AwareDatetime] = None
    updated_at: Optional[AwareDatetime] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source: Provenance


MODEL_BY_KIND = {
    "blog_post": BlogPost,
    "blog_author": BlogAuthor,
    "blog_talent_post": UserBlogPost,
    "blog_community_post": UserBlogPost,
    "blog_post_content": UserPostContent,
    "blog_help_article": HelpArticle,
    "blog_case_study": CaseStudy,
    "blog_changelog_entry": ChangelogEntry,
}
ID_FIELD_BY_KIND = {
    "blog_post": "post_id",
    "blog_author": "slug",
    "blog_talent_post": "post_id",
    "blog_community_post": "post_id",
    "blog_post_content": "post_id",
    "blog_help_article": "article_id",
    "blog_case_study": "case_study_id",
    "blog_changelog_entry": "entry_id",
}
PRIMARY_KINDS = ("blog_post", "blog_talent_post", "blog_community_post", "blog_help_article", "blog_case_study",
                 "blog_changelog_entry")


class BlogSummary(Strict):
    posts_by_category: dict[str, int] = Field(default_factory=dict)
    help_articles_by_section: dict[str, int] = Field(default_factory=dict)
    help_articles_by_category: dict[str, int] = Field(default_factory=dict)
    changelog_by_category: dict[str, int] = Field(default_factory=dict)
    words_total: int = 0
    with_content: dict[str, int] = Field(default_factory=dict, description="items with a non-empty body, per collection")
    newest_post_at: Optional[AwareDatetime] = None
    oldest_post_at: Optional[AwareDatetime] = None


class BlogDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    posts: list[BlogPost] = Field(default_factory=list)
    authors: list[BlogAuthor] = Field(default_factory=list)
    talent_posts: list[UserBlogPost] = Field(default_factory=list)
    community_posts: list[UserBlogPost] = Field(default_factory=list)
    help_articles: list[HelpArticle] = Field(default_factory=list)
    case_studies: list[CaseStudy] = Field(default_factory=list)
    changelog: list[ChangelogEntry] = Field(default_factory=list)
    summary: BlogSummary
