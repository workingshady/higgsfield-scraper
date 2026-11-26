"""Studios sources: URLs, kinds, page sizes and the `--what` groups (all verified live 2026-11-26, build 548e0f3a).

JS evidence (chunk + excerpt) for every source is in docs/scrapers/studios.md §3. Every source here is PUBLIC
(answers anonymously, identical with a session); login-only per-user workspaces (Ads Studio brands/products/brand
research, AI Host channels, Short Drama / Production projects, Popcorn, personal apps/games/employees) are documented
there and never requested.
"""
from __future__ import annotations

GW = "https://fnf-api-gw.higgsfield.ai"
FNF = f"{GW}/fnf"
APPS = f"{GW}/fnf-apps-marketplace"        # JS `Nxe` (exported `zj`)
SKILLS = f"{GW}/fnf-skills-marketplace"    # JS `Mxe` (exported `pM`): skills, games AND ai-agents (= AI employees)
COMMUNITY = f"{GW}/fnf-community"          # JS `Axe`: entity comments
CMS = "https://cms.higgsfield.ai"
SITE = "https://higgsfield.ai"
# Shorts Studio presets (/shorts-studio = `/fnf-cms/ai-reels-presets`) belong to `scrape showcase --what reels_presets`.

# endpoint name -> (base, path)
ENDPOINTS: dict[str, tuple[str, str]] = {
    "studios_app_categories": (APPS, "/api/v1/apps/categories"),
    "studios_apps": (APPS, "/api/v1/apps/community"),
    "studios_games": (SKILLS, "/api/v1/games/community"),
    "studios_skills": (SKILLS, "/api/v1/skills/community"),
    "studios_employees": (SKILLS, "/api/v1/ai-agents/community"),
    "studios_playable_presets": (CMS, "/playable-ads-presets"),
    "studios_influencer_config": (CMS, "/ai-influencer-config"),
    "studios_gallery": (FNF, "/publications/community/{feed}"),            # approved | trending, repeated `model`
    "studios_comments": (COMMUNITY, "/entities/generation_publication/{id}/comments"),
}
ENDPOINT_URLS = {k: b + p for k, (b, p) in ENDPOINTS.items()}
OPTIONAL_ENDPOINTS = frozenset({"studios_comments"})

# --what short name -> (entity kinds, endpoints, login-only?)   (no login-only source: every one is public)
WHAT: dict[str, tuple[tuple[str, ...], tuple[str, ...], bool]] = {
    "apps": (("studios_app_category", "studios_app"), ("studios_app_categories", "studios_apps"), False),
    "games": (("studios_game",), ("studios_games",), False),
    "skills": (("studios_skill",), ("studios_skills",), False),
    "employees": (("studios_employee",), ("studios_employees",), False),
    "playable_presets": (("studios_playable_preset",), ("studios_playable_presets",), False),
    "influencer_options": (("studios_influencer_option",), ("studios_influencer_config",), False),
    "galleries": (("studios_gallery_item", "studios_comment"), ("studios_gallery", "studios_comments"), False),
}
WHATS = tuple(WHAT)
PUBLIC_WHATS = tuple(w for w, (_, _, login) in WHAT.items() if not login)
DEFAULT_WHATS = PUBLIC_WHATS
KINDS = tuple(k for w in WHATS for k in WHAT[w][0])
CHILD_KINDS = ("studios_app_category", "studios_comment")      # not counted by --max-items
PRIMARY_KINDS = tuple(k for k in KINDS if k not in CHILD_KINDS)

# ---------------------------------------------------------------- page sizes / enums (from the JS)
APPS_PAGE_SIZE = 100            # JS J=100 (limit); limit=200 is silently clamped to 100; offset + next_offset
APPS_SORTS = ("trending", "most_viewed", "popular", "newest")   # JS Ol=[...], default kl=`trending`
GAMES_PAGE_SIZE = 100           # JS ki=100; offset + next_offset
SKILLS_PAGE_SIZE = 100          # cursor (next_cursor)
EMPLOYEES_PAGE_SIZE = 100       # JS Y=100; cursor (next_cursor)
PLAYABLE_PAGE_SIZE = 100        # JS u=100; cursor = page number, `total`
GALLERY_PAGE_SIZE = 50          # community feeds cap 50 (docs/ENGAGEMENT.md §13); float cursor + has_more + total
GALLERY_FEEDS = ("approved", "trending")
GALLERY_DEFAULT_PAGES = 3       # per (studio, feed); --gallery-pages 0 = until has_more is false
COMMENTS_PAGE_SIZE = 20         # JS ea=20; cursor (next_cursor) + total
CMS_LANGS = ("en", "es", "de", "ja", "ko")

# Studio -> job_set_types of its outputs (from the community `model` enum, docs/scrapers/community.md). One request
# per (studio, feed) with `model` repeated (JS: `(Array.isArray(i)?i:[i]).forEach(e=>f.searchParams.append(`model`,e))`).
# Live totals 2026-11-26 (approved / trending): marketing 33 / 96, cinema 41 / 813, ai_influencer 0 / 1028,
# canvas 0 / 101; every other studio 0 / 0 (outputs exist but are not published to the community feeds).
STUDIO_MODELS: dict[str, tuple[str, ...]] = {
    "marketing_studio": ("marketing_studio_video", "marketing_studio_image", "marketing_studio_2_image",
                         "marketing_studio_v2_video", "marketing_studio_v2_reference2video",
                         "marketing_storyboard", "marketing_studio_hook"),
    "ads_studio": ("ads_studio_creative", "ads_studio_edit", "ads_story_result", "ad_multiplier",
                   "ad_multiplier_v2", "ad_multiplier_replace", "link_to_ad_collage", "playable_ads_agent_v1"),
    "cinema_studio": ("cinematic_studio_3_0", "cinematic_studio_image", "cinematic_studio_2_5",
                      "cinematic_studio_video", "cinematic_studio_video_v2", "cinematic_studio_video_3_5",
                      "cinematic_studio_video_4_0", "cinema_studio_4_0", "soul_cinema_studio"),
    "ai_influencer": ("ai_influencer", "ai_influencer_sheet", "ai_influencer_motion_control",
                      "ai_influencer_restyle", "ai_influencer_replace_object"),
    "canvas": ("canvas", "canvas_soul"),
    "shorts_drama": ("short_drama_result", "dramas_v1", "drama_episode_edit", "reels_studio", "reels_studio_clip",
                     "ai_reels_result", "ai_reels_v1", "youtube_faceless_video"),
    "ai_host": ("ai_host_video", "ai_host_render"),
    "property_studio": ("realtor_studio_v1", "realtor_studio_video", "realtor_studio_still"),
    "editing_room": ("videoshop_edit", "videoshop_relight", "videoshop_camera_move", "videoshop_genjutsu"),
}
STUDIOS = tuple(STUDIO_MODELS)
STUDIO_OF_MODEL = {m: s for s, ms in STUDIO_MODELS.items() for m in ms}

# CDN hosts whose files are user INPUTS (uploads); never used as generation keys
INPUT_HOSTS = ("d2ol7oe51mr4n9.cloudfront.net",)
APP_HOST = "higgsfield.app"      # community apps/games run on <slug>.higgsfield.app
