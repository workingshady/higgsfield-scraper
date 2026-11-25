"""Site-page sources found while reverse-engineering (see docs/scrapers/site.md and REVERSE_ENGINEERING.md §14).

Every page below is server-rendered by TanStack Start: the route loader data is embedded in the HTML as
`$_TSR.router` (seroval). The spider decodes it (`extract.py`) and archives only the compact loader JSON.
Marketing landing pages have no loader data: their content is the SSR HTML (`<main>`) plus JSON-LD.
"""
from __future__ import annotations

SITE = "https://higgsfield.ai"
API = "https://fnf-api-gw.higgsfield.ai/fnf"           # same as constants.API_BASE

# --- Sitemaps (XML, listed in robots.txt) ---------------------------------------------------------------------------
SITEMAPS = {
    "apps": "/apps/sitemap.xml",                         # /apps/<app-slug> and /apps/<category-slug>   (98)
    "academy": "/academy/sitemap.xml",                   # /academy/courses/<course>[/<lesson>]          (199)
    "originals": "/original-series/sitemap.xml",         # /original-series/<series>/<episode>           (41)
    "mixed-media": "/mixed-media-presets/sitemap.xml",   # /mixed-media-presets/preset/<uuid>            (33)
    "marketing": "/sitemap-marketing.xml",               # landings, /plugins/*, /mcp/*, /community/rooms/* (396)
}

# --- SSR pages (loader keys in comments) ----------------------------------------------------------------------------
APPS_INDEX = "/apps"                                     # categories[{.., apps[cards]}] (cards capped per category)
APP_PAGE = "/apps/{slug}"                                # kind=custom|app: appPreset{.., imageTemplate.cost ..}
                                                         # kind=category: categories, initialCategoryData.items
ACADEMY_INDEX = "/academy/courses"                       # allCourses[], categories[]
COURSE_PAGE = "/academy/courses/{course}"                # course{objectives, authors, lessons[] ..}
LESSON_PAGE = "/academy/courses/{course}/{lesson}"       # lesson{video, resources ..}, summary, mdxTree (HAST)
MCP_INDEX = "/mcp"                                       # items[] (skills), bundles[], settings.agents
MCP_SKILL = "/mcp/{slug}"                                # skill{.. overview_description, medias, tutorial_*}
MCP_BUNDLE = "/mcp/bundles/{slug}"                       # bundle{..}, skills[]
ORIGINALS_INDEX = "/original-series"                     # snapshot.originals.data.items[] (+ total), hero.data[]
EPISODE_PAGE = "/original-series/{series}/{episode}"     # episode{..}, project{..}, recommended[]
MIXED_MEDIA_PRESET = "/mixed-media-presets/preset/{id}"  # preset{id,name,description}, initialItems[], initialCursor

# --- Public JSON APIs not used by any other scraper -----------------------------------------------------------------
DATETIME_SETTINGS = "/datetime-settings"                 # [{source, datetimes{starts_at, ends_at}, params}]
BUSINESS_UNLIM = "/business-unlim/state"                 # plan_cards{monthly[], annual[]}, pricing_banner{offers[]}
GAME_GIFT = "/game-gift/networks"                        # networks[{id, countries[{code, fulfillment_mode, amount_label}]}]

# --- what= values ---------------------------------------------------------------------------------------------------
WHAT = ("apps", "academy", "mcp", "originals", "mixed-media", "landings", "rooms", "promos")
DEFAULT_WHAT = ("apps", "academy", "mcp", "originals", "mixed-media", "landings", "promos")   # rooms: opt-in

# marketing-sitemap paths that are not landings (covered elsewhere or by another --what value)
LANDING_EXCLUDE_PREFIXES = ("/mcp", "/community", "/blog", "/apps", "/academy", "/effects", "/pricing",
                            "/es/", "/ja/", "/ko/", "/de/")
LANDING_EXCLUDE_EXACT = ("/es", "/ja", "/ko", "/de", "/pricing.md")

ENDPOINT_DOCS = {
    "apps_sitemap": SITE + SITEMAPS["apps"],
    "apps_index": SITE + APPS_INDEX,
    "app_page": SITE + APP_PAGE + " (SSR, $_TSR loader: appPreset | category)",
    "academy_sitemap": SITE + SITEMAPS["academy"],
    "academy_index": SITE + ACADEMY_INDEX,
    "course_page": SITE + COURSE_PAGE,
    "lesson_page": SITE + LESSON_PAGE + " (lesson + mdxTree HAST -> Markdown)",
    "mcp_index": SITE + MCP_INDEX,
    "mcp_skill_page": SITE + MCP_SKILL,
    "mcp_bundle_page": SITE + MCP_BUNDLE,
    "originals_index": SITE + ORIGINALS_INDEX,
    "originals_sitemap": SITE + SITEMAPS["originals"],
    "episode_page": SITE + EPISODE_PAGE,
    "mixed_media_sitemap": SITE + SITEMAPS["mixed-media"],
    "mixed_media_page": SITE + MIXED_MEDIA_PRESET,
    "marketing_sitemap": SITE + SITEMAPS["marketing"],
    "landing_page": SITE + "/{path} (SSR HTML <main> + JSON-LD)",
    "room_page": SITE + "/community/rooms/{slug} (head + JSON-LD only)",
    "datetime_settings": API + DATETIME_SETTINGS,
    "business_unlim": API + BUSINESS_UNLIM,
    "game_gift": API + GAME_GIFT,
}
