"""Blog / help-center sources found while reverse-engineering (see docs/scrapers/blog.md)."""
from __future__ import annotations

SITE = "https://higgsfield.ai"
API = "https://fnf-api-gw.higgsfield.ai/fnf"           # same as constants.API_BASE

# --- Sitemaps (XML) -------------------------------------------------------------------------------------------------
SITEMAPS = {
    "blog": "/blog/sitemap.xml",                         # /blog/<slug> posts, /blog/<category>, /blog/author/<slug>
    "creator-hub": "/creator-hub/sitemap.xml",           # help-center (categories + articles), case-studies, changelog
    "enterprise": "/enterprise-help-center/sitemap.xml",  # enterprise help center (categories + articles)
}

# --- TanStack Start SSR pages (router state embedded in `$_TSR.router`, seroval-serialized) -------------------------
BLOG_INDEX = "/blog"                                     # loader: mainPost, featuredPosts, categoryAndPosts[]
HELP_INDEX = "/creator-hub/help-center"                  # loader: homeScreen, navigation.groups[] (all articles)
CASE_STUDIES_INDEX = "/creator-hub/case-studies"         # loader: featuredCaseStudy, categories[{category, posts}]
CHANGELOG = "/creator-hub/changelog"                     # loader: categories[], entries[] (all entries, one page)
ENTERPRISE_INDEX = "/enterprise-help-center"             # loader: name, description, items[{name, path}]

# --- JSON API (public) ----------------------------------------------------------------------------------------------
TALENT_POSTS = "/community/discovery/talents/blog-posts"  # cursor, size (<=50) -> {items, next_cursor}
RECOMMENDED_POSTS = "/blog/posts/recommended"            # cursor, size (<=50) -> {items, next_cursor}; community feed
PUBLIC_POST = "/blog/public/posts/{id}"                   # id must be a UUID (slug -> 422)
ALL_POSTS_LOGIN = "/blog/posts"                           # 401 without login (not used: sitemap + feeds cover it)
LIST_MAX = 50                                             # size > 50 -> 422 "Input should be less than or equal to 50"

# community/talent post body: Yjs binary update of a Lexical document
CONTENT_HOST = "https://cdn.higgsfield.ai/blog/"

# --- what= values ---------------------------------------------------------------------------------------------------
WHAT = ("blog", "talents", "help", "enterprise-help", "case-studies", "changelog", "community")
DEFAULT_WHAT = ("blog", "talents", "help", "enterprise-help", "case-studies", "changelog")
LOCALES = ("en", "es", "ja", "ko", "de")                  # /<locale>/... prefix; only some posts are translated

# blog sitemap entries that are not posts
BLOG_NON_POST_PREFIXES = ("/blog/author/",)

ENDPOINT_DOCS = {
    "blog_sitemap": SITE + SITEMAPS["blog"],
    "creator_hub_sitemap": SITE + SITEMAPS["creator-hub"],
    "enterprise_sitemap": SITE + SITEMAPS["enterprise"],
    "blog_index": SITE + BLOG_INDEX,
    "blog_page": SITE + "/blog/{slug} (SSR, $_TSR router state)",
    "blog_author": SITE + "/blog/author/{slug}",
    "help_index": SITE + HELP_INDEX,
    "help_article": SITE + "/creator-hub/help-center/{category}/{slug}",
    "case_studies_index": SITE + CASE_STUDIES_INDEX,
    "case_study": SITE + "/creator-hub/case-studies/{slug}",
    "changelog": SITE + CHANGELOG,
    "enterprise_index": SITE + ENTERPRISE_INDEX,
    "enterprise_article": SITE + "/enterprise-help-center/{category}/{slug}",
    "talent_posts": API + TALENT_POSTS,
    "recommended_posts": API + RECOMMENDED_POSTS,
    "post_content": CONTENT_HOST + "{uuid}.bin (Yjs/Lexical)",
}
