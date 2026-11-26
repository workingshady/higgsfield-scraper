"""Endpoints, page-size maxima and enums of the projects/contests API (reverse-engineered 2026-11-25).

Base: https://fnf-api-gw.higgsfield.ai/fnf  (constants.API_BASE). All GET, all public unless noted.
Every enum below was read from the API's own 422 validation messages or from the web app's JS bundle.
"""
from __future__ import annotations

SITE = "https://higgsfield.ai"

# endpoint key -> path template
PUBLICATIONS = "/project-publications"                       # limit<=50, cursor -> next_cursor ("<score>:<uuid>")
RECOMMENDED = "/project-publications/recommended"            # scope, limit<=50, cursor (offset string), current_publication_id
CATEGORIES = "/project-publications/categories"              # {items:[{slug,label}]}
PUBLICATION_DETAIL = "/project-publications/{id}"            # full record (+ stats, original_folder_id, featured_episode_slug)
PUBLICATION_BY_HANDLE = "/project-publications/{username}/{slug}"   # same detail, addressed like the page /@user/projects/slug
CONTESTS = "/contests"                                       # contest_type (default global), status (repeatable), size<=100, cursor
CONTEST_DETAIL = "/contests/by-id/{id}"                      # also /contests/{slug}
CONTEST_SUBMISSIONS = "/contests/{id}/submissions"           # limit<=100, offset, ordering, user_id, search -> {items, has_more}
ENTRIES = "/contest-participations/publications"             # tab, contest_key, size<=100, cursor -> {items, next_cursor, total}
# Original series. On the fnf base (/fnf/series) they answer 401 without a session and 404 with one: that path is
# wrong, not login-only. The web app calls the PUBLIC `fnf-series` service (JS: ho(`/series`) + limit=100, no login;
# 35 series on 2026-11-26). The legacy fnf requests are kept unchanged for the default run; `--public-series`
# switches to SERIES_BASE (endpoints projects_series_public[_detail], same parser and fields).
SERIES = "/series"                                           # limit (<=100), {items, total}; no cursor
SERIES_DETAIL = "/series/{slug}"
SERIES_BASE = "https://fnf-api-gw.higgsfield.ai/fnf-series"

ENDPOINTS = {
    "projects_publications": PUBLICATIONS,
    "projects_recommended": RECOMMENDED,
    "projects_categories": CATEGORIES,
    "projects_publication_detail": PUBLICATION_DETAIL,
    "projects_contests": CONTESTS,
    "projects_contest_detail": CONTEST_DETAIL,
    "projects_contest_submissions": CONTEST_SUBMISSIONS,
    "projects_contest_entries": ENTRIES,
    "projects_series": SERIES,
    "projects_series_detail": SERIES_DETAIL,
}
LOGIN_ONLY = frozenset({"projects_series", "projects_series_detail"})       # legacy fnf paths (session-gated)
PUBLIC_SERIES_ENDPOINTS = {                                  # --public-series (no login)
    "projects_series_public": SERIES,
    "projects_series_public_detail": SERIES_DETAIL,
}

# ---- nested project data (opt-in, reverse-engineered 2026-11-26 from the /@$user/projects/$slug route; all GET,
# all anonymous, no hf-access-realm header needed). See docs/scrapers/projects.md "Nested data model".
CONTEST_BY_SLUG = "/contests/{slug}"                         # --contest <slug>: same body as /contests/by-id/{id}
FOLDER = "/folders/{id}"                                     # project root folder (snapshot): name, count, subfolders_count
FOLDER_CHILDREN = "/folders/{id}/children"                   # sub-folders ("Cast", "Scenes", …) {items, cursor}
FOLDER_ITEMS = "/folders/{id}/items/v2"                      # assets: size<=100, cursor (epoch float), include_subfolders
USER_PUBLICATIONS = "/user/{username}/v2/publications"       # profile "Projects" tab: publication_type, limit=50, cursor
BRIEF_BASE = "https://dam-editor-worker.higgsfield.ai"      # Yjs CRDT snapshot of the Lexical brief (binary)
BRIEF_SNAPSHOT = "/brief/{folder_id}/snapshot"               # header X-Brief-Updated-At (epoch ms)
COMMUNITY_BASE = "https://fnf-api-gw.higgsfield.ai/fnf-community"
PROJECT_COMMENTS = "/entities/project_publication/{id}/comments"   # limit, cursor, parent_id, order -> {items,total,next_cursor}
NESTED_ENDPOINTS = {                                          # endpoint key -> (base, path)
    "projects_contest_by_slug": (None, CONTEST_BY_SLUG),
    "projects_folder": (None, FOLDER),
    "projects_folder_children": (None, FOLDER_CHILDREN),
    "projects_folder_items": (None, FOLDER_ITEMS),
    "projects_brief": (BRIEF_BASE, BRIEF_SNAPSHOT),
    "projects_comments": (COMMUNITY_BASE, PROJECT_COMMENTS),
    "projects_related": (None, RECOMMENDED),
    "projects_user_publications": (None, USER_PUBLICATIONS),
}
SEPARATE_ITEM_SURFACES = ("watermarks",)                     # sub-folders that items/v2?include_subfolders omits
FOLDER_PERSONAL_KEYS = frozenset({"owner_username"})         # blanked in folder bodies unless --with-profiles
MAX_FOLDER_ITEMS_SIZE = 100                                  # 422 "less than or equal to 100" above
MAX_COMMENTS_LIMIT = 100                                     # the web app sends 20; 100 accepted
MAX_USER_PUBLICATIONS_LIMIT = 50                             # the web app sends 50
# related list (JS fa()/da()): scope = talent_contest | ai_film_festival | community by the project's contest_key;
# current_publication_id is only sent for community and talent_contest projects.
RELATED_SCOPE_BY_KEY = {"talent_contest": "talent_contest", "ai_film_festival": "ai_film_festival", None: "community"}
CONTEST_TABS = ("latest", "trending", "most_watched", "all_entries", "submissions")   # public tabs (liked/voted = per viewer)

MAX_PUBLICATIONS_LIMIT = 50
MAX_RECOMMENDED_LIMIT = 50
MAX_CONTESTS_SIZE = 100
MAX_SUBMISSIONS_LIMIT = 100
MAX_ENTRIES_SIZE = 100
MAX_SERIES_LIMIT = 100

WHAT = ("publications", "recommended", "contests", "entries", "series")
RECOMMENDED_SCOPES = ("community", "ai_film_festival", "talent_contest", "ad_contest", "discord")  # RecommendedFeedScope|ContestKey
CONTEST_TYPES = ("global", "weekly")
CONTEST_STATUSES = ("created", "open", "shortlist", "judge", "finished")
CONTEST_STATUS_GROUPS = {
    "open": ("created", "open", "shortlist", "judge"),       # not finished yet (announced / running / judging)
    "closed": ("finished",),
    "all": CONTEST_STATUSES,
}
SUBMISSION_ORDERINGS = ("newest", "most-liked", "most-viewed", "trending")
ENTRY_CONTEST_KEYS = ("ai_film_festival", "talent_contest")  # contest-participations accepts only these two
ENTRY_TABS = ("latest", "trending", "most_watched", "all_entries", "submissions", "liked", "voted")
PUBLICATION_TYPES = ("film", "series", "carousel")           # observed values of `type`

# contest_key used by publications/entries -> contest slug (from the web app; for joining)
CONTEST_KEY_SLUG = {"ai_film_festival": "higgsfield-global-film-festival", "talent_contest": "talent-contest"}
KEY_BY_CONTEST_SLUG = {v: k for k, v in CONTEST_KEY_SLUG.items()}   # --contest <slug> -> entries contest_key


def publication_url(username: str | None, slug: str | None) -> str | None:
    return f"{SITE}/@{username}/projects/{slug}" if username and slug else None


def contest_url(slug: str | None) -> str | None:
    return f"{SITE}/contests/{slug}" if slug else None


def submission_url(contest_slug: str | None, submission_id: str | None) -> str | None:
    return f"{SITE}/contests/{contest_slug}/submissions/{submission_id}" if contest_slug and submission_id else None


def series_url(slug: str | None, episode_slug: str | None = None) -> str | None:
    if not slug:
        return None
    return f"{SITE}/original-series/{slug}" + (f"/{episode_slug}" if episode_slug else "")
