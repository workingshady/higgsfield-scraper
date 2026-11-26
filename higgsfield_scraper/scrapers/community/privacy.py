"""Privacy for the opt-in creator listings (--feeds creators, talents).

Their bodies are lists of people (`users[]`) whose bio / headline / location / background image sit at the top level
of each user object. `core.privacy.redact_personal` (used for the http/ and raw/ archives) only blanks those keys
inside person containers (profile, author, …), so without --with-profiles this downloader middleware blanks them in
the response body BEFORE it is archived or parsed. Ids, counters, badges and works are kept. Every other request
(including every request of a default community run) passes through untouched.
"""
from __future__ import annotations

import json
from typing import Any

from .endpoints import CREATORS_ENDPOINT, TALENTS_ENDPOINT

REDACTED = "[redacted]"
USER_PERSONAL = ("username", "full_name", "headline", "bio", "location", "avatar_url", "background_image_url")
ENDPOINTS = frozenset({CREATORS_ENDPOINT, TALENTS_ENDPOINT})


def sanitize_users(body: Any) -> Any:
    """Blank personal top-level fields of every users[] entry (idempotent)."""
    if not isinstance(body, dict) or not isinstance(body.get("users"), list):
        return body
    users = []
    for u in body["users"]:
        if isinstance(u, dict):
            u = {k: (REDACTED if k in USER_PERSONAL and v not in (None, "") else v) for k, v in u.items()}
        users.append(u)
    return {**body, "users": users}


class CreatorsPrivacyMiddleware:
    """Downloader middleware (584, above HttpArchive 580): sanitizes creators / talents bodies unless --with-profiles."""

    PATH = "higgsfield_scraper.scrapers.community.privacy.CreatorsPrivacyMiddleware"
    PRIORITY = 584

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider=None):
        if request.meta.get("endpoint") not in ENDPOINTS or request.meta.get("media"):
            return response
        if getattr(getattr(spider, "selection", None), "with_profiles", False):
            return response
        try:
            data = json.loads(response.body or b"null")
        except (ValueError, UnicodeDecodeError):
            return response
        return response.replace(body=json.dumps(sanitize_users(data), ensure_ascii=False).encode("utf-8"))
