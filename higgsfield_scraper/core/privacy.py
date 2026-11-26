"""Remove personal data from archived API bodies (raw/ and http/) unless the user opted in (--with-profiles).

Parsers already keep creators pseudonymous in the dataset; this makes the *archives* match, so a run folder shared
with someone does not leak usernames, real names, avatars or social handles of other Higgsfield users.
Ids (user_id …) are kept: they are opaque and needed to join records.
"""
from __future__ import annotations

import json
from typing import Any

REDACTED = "[redacted]"
PERSONAL_KEYS = frozenset({
    "username", "user_name", "full_name", "display_name", "first_name", "last_name", "name_full",
    "avatar_url", "avatar", "profile_image_url", "image_url_avatar", "photo_url",
    "headline", "bio", "location", "email", "email_address", "phone", "phone_number",
    "instagram_handle", "twitter_handle", "youtube_handle", "tiktok_handle", "x_handle", "discord_handle",
    "instagram", "twitter", "youtube", "tiktok", "website", "socials", "social_links", "profile_url",
    "owner_username",   # folder/room owner handle (projects nested folders, rooms): was only blanked per scraper
    "author_handle",    # social handle of a Shorts Studio reference reel's author (showcase reels_presets)
    "name",             # only inside person containers (author.name on apps/games/skills is a username)
})
PERSON_CONTAINERS = frozenset({"profile", "author", "authors", "owner", "creator", "user", "team", "members",
                               "judges", "contestants", "some_contestants", "winner", "participants"})


def redact_personal(obj: Any, _inside: bool = False) -> Any:
    """Recursively blank personal fields. Inside person-like containers every PERSONAL_KEYS value is redacted;
    elsewhere only unambiguous ones (username, avatar, handles, email…)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower()
            if lk in PERSONAL_KEYS and v not in (None, "", [], {}):
                if _inside or lk not in ("name", "website", "location", "headline", "bio"):
                    out[k] = REDACTED
                    continue
            out[k] = redact_personal(v, _inside or lk in PERSON_CONTAINERS)
        return out
    if isinstance(obj, list):
        return [redact_personal(x, _inside) for x in obj]
    return obj


def redact_json_bytes(body: bytes) -> bytes:
    """Same for a raw HTTP body; non-JSON bodies are returned unchanged."""
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    return json.dumps(redact_personal(data), ensure_ascii=False).encode("utf-8")


def creator_uid_key(user_id: Any) -> str | None:
    """One pseudonymous key per Higgsfield user across every scraper: make_id('creator', <clerk user id>).

    Same hash the showcase/studios `creator_key`/`author_key` already use, so new `creator_uid_key` columns in
    community, projects and catalog join with them. None for missing or redacted ids."""
    from ..schemas.common import make_id
    s = None if user_id is None else str(user_id).strip()
    if not s or s == REDACTED or "redacted" in s.lower():
        return None
    return make_id("creator", s)


def profiles_opt_in(selection: Any) -> bool:
    return bool(getattr(selection, "with_profiles", False))
