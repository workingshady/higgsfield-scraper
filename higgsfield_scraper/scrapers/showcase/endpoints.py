"""Showcase sources: URLs, kinds, page sizes and the `--what` groups (all verified live 2026-11-26, build 548e0f3a).

Evidence (chunk + excerpt) for every source is in docs/scrapers/showcase.md §2.
"""
from __future__ import annotations

API = "https://fnf-api-gw.higgsfield.ai/fnf"
GW = "https://fnf-api-gw.higgsfield.ai"
CMS = "https://cms.higgsfield.ai"
SITE = "https://higgsfield.ai"
CANVAS = "https://canvas-worker.higgsfield.ai"
DOCS = "https://docs.higgsfield.ai"
STATIC = "https://static.higgsfield.ai"
ASSETS = "https://assets.higgsfield.ai"

# endpoint name -> (base, path)   (paths with {x} are filled by the spider; recorded params say which)
ENDPOINTS: dict[str, tuple[str, str]] = {
    "showcase_canvas_templates": (CANVAS, "/api/templates"),
    "showcase_videoshop_examples": (CMS, "/videoshop-examples"),
    "showcase_videoshop_project_examples": (API, "/videoshop/project-examples"),
    "showcase_property_studio_page": (SITE, "/property-studio"),
    "showcase_property_studio_chunk": (ASSETS, "/tanstack/assets/{chunk}"),      # discovery (route + preset table)
    "showcase_l10n": ("https://l10n.higgsfield.ai", "/l10n/production/r/{build}/{file}"),   # lingui catalogs
    "showcase_property_studio_presets": (ASSETS, "/tanstack/assets/{chunk}"),    # synthesized: rows + titles
    "showcase_explore_categories": (CMS, "/higgsfield-multiplier/video-explore/v2/categories"),
    "showcase_explore_feed": (CMS, "/higgsfield-multiplier/video-explore/v2"),
    "showcase_effects_sitemap": (SITE, "/effects/sitemap.xml"),
    "showcase_effect_page": (SITE, "/effects/examples/{slug}"),
    "showcase_api_docs": (DOCS, "/llms-full.txt"),
    "showcase_api_openapi": (DOCS, "/docs/openapi.json"),
    "showcase_season": (GW, "/fnf-score/v1/season"),
    "showcase_cinema_controls": (CMS, "/cinema-studio-4-0/creative-controls"),
    "showcase_faceless_showcases": (CMS, "/youtube-faceless-showcases"),
    "showcase_intone_explore": (CMS, "/intone/explore"),
    "showcase_seedance_presets": (CMS, "/seedance-2-0"),
    "showcase_motion_control_presets": (CMS, "/kling-motion-control-presets"),
}
ENDPOINT_URLS = {k: b + p for k, (b, p) in ENDPOINTS.items()}
# a non-200 here does not make the run "partial" (login-only / best-effort discovery requests)
OPTIONAL_ENDPOINTS = frozenset({"showcase_season", "showcase_property_studio_chunk", "showcase_l10n",
                                "showcase_api_openapi"})
LOGIN_ENDPOINTS = frozenset({"showcase_season"})

# --what short name -> (entity kinds it produces, endpoints it calls, login-only?)
WHAT: dict[str, tuple[tuple[str, ...], tuple[str, ...], bool]] = {
    "canvas_templates": (("showcase_canvas_template",), ("showcase_canvas_templates",), False),
    "editing_room_examples": (("showcase_editing_room_example", "showcase_editing_room_project",
                               "showcase_editing_room_render"),
                              ("showcase_videoshop_examples", "showcase_videoshop_project_examples"), False),
    "property_studio_examples": (("showcase_property_studio_example",),
                                 ("showcase_property_studio_page", "showcase_property_studio_chunk",
                                  "showcase_l10n", "showcase_property_studio_presets"), False),
    "explore_categories": (("showcase_explore_category", "showcase_explore_item", "showcase_explore_variant"),
                           ("showcase_explore_categories", "showcase_explore_feed"), False),
    "effect_examples": (("showcase_effect_sample",), ("showcase_effects_sitemap", "showcase_effect_page"), False),
    "api_models": (("showcase_api_model",), ("showcase_api_openapi", "showcase_api_docs"), False),
    "cinema_controls": (("showcase_cinema_control",), ("showcase_cinema_controls",), False),
    "faceless_showcases": (("showcase_faceless_showcase",), ("showcase_faceless_showcases",), False),
    "intone_examples": (("showcase_intone_example",), ("showcase_intone_explore",), False),
    "seedance_presets": (("showcase_seedance_preset",), ("showcase_seedance_presets",), False),
    "motion_control_presets": (("showcase_motion_control_preset",), ("showcase_motion_control_presets",), False),
    "season": (("showcase_season",), ("showcase_season",), True),
}
WHATS = tuple(WHAT)
PUBLIC_WHATS = tuple(w for w, (_, _, login) in WHAT.items() if not login)
DEFAULT_WHATS = PUBLIC_WHATS                    # `season` (login-only, per-user) only by name or `all`
KIND_OF_WHAT = {k: w for w, (ks, _, _) in WHAT.items() for k in ks}
KINDS = tuple(k for w in WHATS for k in WHAT[w][0])
# kinds counted by --max-items (per kind; child kinds like variants/renders are not counted)
PRIMARY_KINDS = tuple(k for k in KINDS if k not in ("showcase_explore_variant", "showcase_editing_room_render",
                                                     "showcase_explore_category"))

# explore feed (JS: sources `higgsfield`|`community`, sort `trending`|`new`; higgsfield has no `new`; size fixed 20)
EXPLORE_SOURCES = ("higgsfield", "community")
EXPLORE_SORTS = ("new", "trending")
EXPLORE_PAGE_SIZE = 20
EXPLORE_DEFAULT_PAGES = 3                        # per feed; --explore-pages 0 = until the API says no more
CMS_LANGS = ("en", "es", "de", "ja", "ko")       # JS: d=new Set([`en`,`es`,`de`,`ja`,`ko`])
L10N_LANGS = ("en", "es", "de", "ja", "ko", "zh")

CANVAS_PAGE_SIZE = 50                            # /api/templates -> {items,total,limit:50,offset}
CMS_PAGE_SIZE = 20                               # faceless/intone: JS sets size=20, cursor paging

# Property Studio: format -> app make (JS `$t={"flash-tour":"speedramp_walkthrough",...}`)
PROPERTY_FORMAT_APP = {"flash-tour": "speedramp_walkthrough", "enhance": "enhance", "renovation": "renovation",
                       "virtual-staging": "virtual_staging", "floor-plan-3d": "floor_plan_3d"}
PROPERTY_PRESET_MARKER = "realty-studio/app-presets"
PROPERTY_ROUTE = "/_private/property-studio/"
MAX_CHUNK_PROBES = 14                            # imported chunks fetched to find the preset table

# CDN hosts whose files are user INPUTS (uploads); never used as generation keys
INPUT_HOSTS = ("d2ol7oe51mr4n9.cloudfront.net",)
