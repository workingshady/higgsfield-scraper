"""Catalog endpoints (reverse-engineered 2026-11-25 from the live API + JS bundles; see docs/scrapers/catalog.md).

Every listing is described by a `Source`. A catalog *kind* may be fed by several sources (e.g. the per-model motion
lists all feed `catalog_model_motion`, distinguished by `group` = model family).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...constants import API_BASE

PREFIX = "catalog_"
# Bases found in the JS bundle (build 548e0f3a, core chunk aXyXjC_KHBp09DNW.js):
#   Ixe(path, lang) -> https://cms.higgsfield.ai{path}?lang=..   (soul/veo3 styles, per-model motions, mixed media,
#                                                               youtube faceless, marketing studio v2)
#   _V(path)        -> https://fnf-api-gw.higgsfield.ai/fnf-cms-api{path}    (katana)
CMS_BASE = "https://cms.higgsfield.ai"
CMS_API_BASE = "https://fnf-api-gw.higgsfield.ai/fnf-cms-api"


@dataclass(frozen=True)
class Source:
    endpoint: str                    # endpoint name (raw archive file prefix, manifest stats)
    kind: str                        # entity kind produced
    path: str                        # API path (may contain {id})
    group: Optional[str] = None      # sub-catalog (model family, soul style set, ...)
    login: bool = False              # 401 without a session -> requested with auth="required"
    base: str = API_BASE             # host + service prefix the path is appended to
    fixed_params: tuple[tuple[str, str], ...] = ()   # always-sent query params (as the web app sends them)
    size_param: Optional[str] = "size"
    default_size: int = 100
    max_size: int = 1000
    lang: bool = False               # sends ?lang=
    paginate: bool = True


# ------------------------------------------------------------------ kinds
# short name -> (kind, dataset collection, login-only, description)
KINDS: dict[str, tuple[str, str, bool, str]] = {
    "motion": ("catalog_motion", "motions", False, "camera motions / video effect presets (all model families)"),
    "motion_sample": ("catalog_motion_sample", "motion_samples", False, "sample videos per motion (--with-samples)"),
    "avatar": ("catalog_avatar", "avatars", False, "talking-avatar characters (image + voice id)"),
    "avatar_preset": ("catalog_avatar_preset", "avatar_presets", False, "avatar motion presets (quality, chunks)"),
    "voice": ("catalog_voice", "voices", False, "TTS voices (sample audio, gender, age, categories)"),
    "reference_voice": ("catalog_reference_voice", "reference_voices", False,
                        "preset voices for audio models (supported_models)"),
    "sound": ("catalog_sound", "sounds", False, "ambient sound effects"),
    "style": ("catalog_style", "styles", False, "image style presets"),
    "soul_sample": ("catalog_soul_sample", "soul_samples", False, "Soul model sample generations (prompt, style)"),
    "viral_type": ("catalog_viral_type", "viral_types", False, "viral-hub effect types"),
    "viral_preset": ("catalog_viral_preset", "viral_presets", False,
                     "viral-hub chain presets (inputs, params, credit price matrix)"),
    # ---- opt-in group (`--kinds login`, `--include-login-only`). Historically "login-only": the first guesses
    # (`fnf/<path>`) answered 401 without a session and 404 with one. Since 2026-11-26 the real paths are known
    # (CMS host / fnf-cms-api); only color_preset and camera_setting really need a session (Source.login below).
    "soul_style": ("catalog_soul_style", "soul_styles", True, "Soul styles (soul / cinematic / keyframe sets)"),
    "mixed_media_preset": ("catalog_mixed_media_preset", "mixed_media_presets", True, "mixed-media presets"),
    "model_motion": ("catalog_model_motion", "model_motions", True,
                     "per-model motion lists (veo3, kling, kling2.6, seedance, wan2.2, wan2.5, minimax)"),
    "katana_category": ("catalog_katana_category", "katana_categories", True, "Katana categories"),
    "katana_preset": ("catalog_katana_preset", "katana_presets", True, "Katana presets (authors redacted)"),
    "color_preset": ("catalog_color_preset", "color_presets", True, "color grading presets (needs a session)"),
    "youtube_faceless_preset": ("catalog_youtube_faceless_preset", "youtube_faceless_presets", True,
                                "YouTube faceless channel presets"),
    "camera_setting": ("catalog_camera_setting", "camera_settings", True, "camera settings presets (needs a session)"),
    "marketing_category": ("catalog_marketing_category", "marketing_categories", True,
                           "Marketing Studio v2 categories (id = slug; formats inline)"),
    "marketing_preset": ("catalog_marketing_preset", "marketing_presets", True,
                         "Marketing Studio v2 presets per category"),
}
KIND_OF = {short: v[0] for short, v in KINDS.items()}
SHORT_OF = {v[0]: short for short, v in KINDS.items()}
COLLECTION_OF = {v[0]: v[1] for v in KINDS.values()}
PUBLIC = tuple(s for s, v in KINDS.items() if not v[2])
LOGIN_ONLY = tuple(s for s, v in KINDS.items() if v[2])
DEFAULT_PUBLIC = tuple(s for s in PUBLIC if s != "motion_sample")

PAGE_KIND = "catalog_page"                    # one per listing response (totals, cursors) — auxiliary
MOTION_DETAIL_KIND = "catalog_motion_detail"  # /motions/{id}; merged into catalog_motion by build_dataset
AUX_KINDS = (PAGE_KIND, MOTION_DETAIL_KIND)
PRIMARY_KINDS = tuple(v[0] for s, v in KINDS.items() if s != "motion_sample")

# ------------------------------------------------------------------ sources
SOURCES: tuple[Source, ...] = (
    # public
    Source("catalog_motions", "catalog_motion", "/motions", default_size=1000),
    Source("catalog_motion_samples", "catalog_motion_sample", "/motion-samples"),        # + motion_id (required)
    Source("catalog_motion_detail", MOTION_DETAIL_KIND, "/motions/{id}", size_param=None, paginate=False),
    Source("catalog_avatars", "catalog_avatar", "/avatars", max_size=200),               # size=1000 -> HTTP 500
    Source("catalog_avatar_presets", "catalog_avatar_preset", "/avatar-presets", max_size=200),
    Source("catalog_voices", "catalog_voice", "/voices", default_size=500),
    Source("catalog_reference_voices", "catalog_reference_voice", "/reference-elements/voices", default_size=500),
    Source("catalog_sounds", "catalog_sound", "/sounds", default_size=500),
    Source("catalog_styles", "catalog_style", "/styles", default_size=500),
    # cursor paging (created_at) drops ~2 items at page boundaries -> fetch everything in one page by default
    Source("catalog_soul_samples", "catalog_soul_sample", "/soul-samples", default_size=2000, max_size=5000),
    Source("catalog_viral_types", "catalog_viral_type", "/viral-hub/types", size_param=None, lang=True,
           paginate=False),
    Source("catalog_viral_presets", "catalog_viral_preset", "/viral-hub/presets/all", size_param=None, lang=True),
    # opt-in group — CMS host (public; verified 2026-11-26 with and without a session)
    Source("catalog_soul_styles", "catalog_soul_style", "/soul-styles", group="soul", lang=True, base=CMS_BASE),
    Source("catalog_soul_cinematic_styles", "catalog_soul_style", "/soul-cinematic-styles", group="cinematic",
           lang=True, base=CMS_BASE),
    Source("catalog_soul_keyframe_styles", "catalog_soul_style", "/soul-keyframe-styles", group="keyframe",
           lang=True, base=CMS_BASE),
    Source("catalog_mixed_media_presets", "catalog_mixed_media_preset", "/mixed-media-presets", lang=True,
           base=CMS_BASE),
    Source("catalog_veo3_styles", "catalog_model_motion", "/veo3-styles", group="veo3", lang=True, base=CMS_BASE),
    Source("catalog_kling_motions", "catalog_model_motion", "/kling-motions", group="kling", lang=True,
           base=CMS_BASE),
    Source("catalog_kling2_6_motions", "catalog_model_motion", "/kling2-6-motions", group="kling2_6", lang=True,
           base=CMS_BASE),
    Source("catalog_seedance_motions", "catalog_model_motion", "/seedance-motions", group="seedance", lang=True,
           base=CMS_BASE),
    Source("catalog_wan2_2_motions", "catalog_model_motion", "/wan2-2-motions", group="wan2_2", lang=True,
           base=CMS_BASE),
    Source("catalog_wan2_5_motions", "catalog_model_motion", "/wan2-5-motions", group="wan2_5", lang=True,
           base=CMS_BASE),
    Source("catalog_minimax_motions", "catalog_model_motion", "/minimax-motions", group="minimax", lang=True,
           base=CMS_BASE),
    Source("catalog_youtube_faceless_presets", "catalog_youtube_faceless_preset", "/youtube-faceless-presets",
           lang=True, base=CMS_BASE),
    Source("catalog_marketing_catalog", "catalog_marketing_category", "/marketing-studio-v2/catalog", size_param=None,
           lang=True, paginate=False, base=CMS_BASE, fixed_params=(("show_hidden", "false"),)),
    Source("catalog_marketing_presets", "catalog_marketing_preset", "/marketing-studio-v2/categories/{id}/presets",
           lang=True, base=CMS_BASE, fixed_params=(("show_hidden", "false"),)),       # {id} = category slug
    # opt-in group — fnf-cms-api (public; limit 1..100, next_cursor)
    Source("catalog_katana_categories", "catalog_katana_category", "/katana-categories", size_param="limit",
           max_size=100, lang=True, base=CMS_API_BASE),
    Source("catalog_katana_presets", "catalog_katana_preset", "/katana-presets", size_param="limit", max_size=100,
           lang=True, base=CMS_API_BASE),
    # opt-in group — fnf gateway, really login-only (401 without a session, 200 with one)
    Source("catalog_color_presets", "catalog_color_preset", "/color-presets", login=True),
    Source("catalog_camera_settings", "catalog_camera_setting", "/camera-settings", login=True, size_param=None),
)
SOURCE_BY_ENDPOINT = {s.endpoint: s for s in SOURCES}
LOGIN_ENDPOINTS = frozenset(s.endpoint for s in SOURCES if s.login)          # need a session (auth="required")
ENDPOINT_URLS = {s.endpoint: f"{s.base}{s.path}" for s in SOURCES}


def sources_for(kind: str) -> list[Source]:
    return [s for s in SOURCES if s.kind == kind]


PLACEHOLDER_URL = "<placeholder>"      # /motions list returns this for non-higgsfield families (detail has real URLs)
