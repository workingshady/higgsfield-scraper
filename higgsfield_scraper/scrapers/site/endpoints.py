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

# --- Community rooms (fnf-community JSON API, public; opt-in --what room-list / room-content) -------------------------
# JS evidence: module community-rooms-api (chunk 548e0f3a-Pl2H2mKz4X6BJdOa.js): S(...e)=N([/rooms,...e].join(/)),
# list ce({query,kind,following,mine,sort,cursor,similarTo,limit=20}), detail _e(id), items ve(id,{type,sort,limit=20,
# cursor}); room page chunk 548e0f3a-J380-oy_aThK_vXz.js: discussions td() = /publications/feed?room_id&kind=discussion
# &offset&limit=20[&sort=new] and mu() = /publications/room-stats?room_id. See docs/COMMUNITY_COVERAGE.md.
COMMUNITY_API = "https://fnf-api-gw.higgsfield.ai/fnf-community"
ROOMS_LIST = "/rooms"                                     # ?limit<=50&cursor -> {items[room], next_cursor, total}
ROOM_STATS = "/publications/room-stats"                   # ?room_id -> {posts, discussions}
ROOM_ITEMS = "/rooms/{room_id}/items"                     # ?limit<=50&cursor -> {items[{space_item_id, item_type, item,
                                                          #   pinned}], next_cursor} (pinned items come on top of limit)
ROOM_DISCUSSIONS = "/publications/feed"                   # ?room_id&kind=discussion&offset&limit -> {publications[], has_more}
ROOMS_PAGE_SIZE = 50

# --- Academy JSON API (fnf-academy, public; opt-in --what academy-api) ----------------------------------------------
# JS evidence (build 548e0f3a, chunk H2odSMT_fOKI1GMn.js): rD(path) only allows `${base}/api/v1/...` on the academy
# origin; oD() = GET /api/v1/courses (parseCourseSummaries), sD(slug) = GET /api/v1/courses/${slug}
# (parseCourseResponse), yge(id) = GET /api/v1/lessons/${id} (parseLessonResponse). Public without a session
# (verified 2026-11-26); /api/v1/categories answers too. Not used: /api/v1/user/certificates* (login, own),
# /api/v1/certificates/{id} (one certificate by id, not enumerable).
ACADEMY_API = "https://fnf-api-gw.higgsfield.ai/fnf-academy"
ACADEMY_API_CATEGORIES = "/api/v1/categories"           # [{id, slug, title, description, artwork}]
ACADEMY_API_COURSES = "/api/v1/courses"                 # [course summary + free_generations, test_count] (17)
ACADEMY_API_COURSE = "/api/v1/courses/{slug}"           # course + objectives, authors, metadata, lessons[] (+access)
ACADEMY_API_LESSON = "/api/v1/lessons/{lesson_id}"      # lesson + mdx source, xp_reward, video tracks, resources

# --- what= values ---------------------------------------------------------------------------------------------------
WHAT = ("apps", "academy", "mcp", "originals", "mixed-media", "landings", "rooms", "promos", "room-list",
        "room-content", "academy-api")
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
ROOM_ENDPOINT_DOCS = {           # added to meta.endpoints only in runs with --what room-list / room-content
    "rooms_api": COMMUNITY_API + ROOMS_LIST,
    "room_stats": COMMUNITY_API + ROOM_STATS + "?room_id={room_id}",
    "room_items": COMMUNITY_API + ROOM_ITEMS,
    "room_discussions": COMMUNITY_API + ROOM_DISCUSSIONS + "?room_id={room_id}&kind=discussion",
}
ACADEMY_API_ENDPOINT_DOCS = {    # added to meta.endpoints only in runs with --what academy-api
    "academy_api_categories": ACADEMY_API + ACADEMY_API_CATEGORIES,
    "academy_api_courses": ACADEMY_API + ACADEMY_API_COURSES,
    "academy_api_course": ACADEMY_API + ACADEMY_API_COURSE,
    "academy_api_lesson": ACADEMY_API + ACADEMY_API_LESSON,
}
