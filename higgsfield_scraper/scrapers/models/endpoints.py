"""Sources of the models scraper (all public, GET only). See docs/scrapers/models.md and docs/MODEL_LOADING.md.

There is no "models" API: the registry is static code in the frontend bundle. The spider fetches a few tool pages
(SSR HTML: build id, anonymous feature flags `__HF_FF`, the modulepreload chunk list), then follows the JS chunk graph
on assets.higgsfield.ai (static + dynamic imports), preloaded chunks first and the imports of chunks that hold model
data next, up to --max-chunks. Two small public JSON APIs join the result: `/job-sets/costs` (which job types are
priced) and the Shots feed facet (`available_models`: models with published shots).
"""
from __future__ import annotations

import re

from ...constants import API_BASE

SITE = "https://higgsfield.ai"
ASSETS = "https://assets.higgsfield.ai/tanstack/assets/"
COMMUNITY_API = "https://fnf-api-gw.higgsfield.ai/fnf-community"

# tool pages whose modulepreload lists (+ the imports of data chunks) reach every registry chunk (simulated on the
# saved build 548e0f3a: /ai/video + /ai/image + /lipsync-studio + /mixed-media find all 131 defineJob types, the route
# table, featured ids, gating and plans within ~540 chunks; /ai/video + /ai/image alone miss two chunks)
DEFAULT_PAGES = ("/ai/video", "/ai/image", "/lipsync-studio", "/mixed-media")
DEFAULT_MAX_CHUNKS = 800

COSTS_PATH = "/job-sets/costs"              # API_BASE: {version, data: [{job_set_type, cost}]}
SHOTS_PATH = "/generations/feed"            # COMMUNITY_API ?limit=1: {available_models: [{model, media_type}], …}

PAGE_ENDPOINT = "models_page"
CHUNK_ENDPOINT = "models_chunk"
COSTS_ENDPOINT = "models_costs"
SHOTS_ENDPOINT = "models_shots"
BODY_ENDPOINTS = frozenset({PAGE_ENDPOINT, CHUNK_ENDPOINT, SHOTS_ENDPOINT})   # bodies replaced by middleware.py

CHUNK_NAME_RE = re.compile(r"^[0-9a-f]{8}-[A-Za-z0-9_\-]{1,64}\.js$")
PAGE_PATH_RE = re.compile(r"^/[A-Za-z0-9_\-/]*$")

# crawl priorities (Scrapy: higher first)
PRIO_PAGE = 100
PRIO_PRELOAD = 50                 # chunks listed by a tool page
PRIO_DATA_STEP = 1                # imports of a chunk with model data: parent priority - 1
PRIO_OTHER_STEP = 10              # imports of any other chunk: parent priority - 10

ENDPOINT_URLS = {
    PAGE_ENDPOINT: SITE + "/{page} (SSR HTML -> build id, __HF_FF flags, chunk list)",
    CHUNK_ENDPOINT: ASSETS + "{chunk}.js (JS -> registry extract)",
    COSTS_ENDPOINT: API_BASE + COSTS_PATH,
    SHOTS_ENDPOINT: COMMUNITY_API + SHOTS_PATH + "?limit=1 (available_models facet)",
}
