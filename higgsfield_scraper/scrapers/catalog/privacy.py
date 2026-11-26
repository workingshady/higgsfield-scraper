"""Archive privacy for the catalog scraper (COMPLETENESS #5).

`catalog` is not a `personal_data` scraper (its catalogs are Higgsfield's own presets), so the framework archives
bodies untouched. One opt-in listing does carry other users' profiles: fnf-cms-api `/katana-presets` items have
`author = {user_id, username, avatar_url, badge}` (community presets). The parser already drops them from the
dataset; this downloader middleware blanks them in the response body itself *before* the http/ archive (580), the
raw/ archive and the parser see it — the same idea as the studios spider (redact first, then archive) and the
account scraper's middleware. Uses `core.privacy.redact_personal`: username / avatar_url (and name, … inside the
`author` container) become "[redacted]"; opaque ids (`author.user_id`) are kept, so `author_key` /
`creator_uid_key` still work. `--with-profiles` keeps the bodies untouched. Every other response passes through
unchanged (byte-exact).
"""
from __future__ import annotations

import json

# endpoints whose bodies hold other users' profiles (see the module docstring)
ARCHIVE_REDACT_ENDPOINTS = frozenset({"catalog_katana_presets"})


class CatalogPrivacyMiddleware:
    PRIORITY = 582            # > HttpArchiveMiddleware (580): process_response runs before the http/ archive

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider=None):
        if request.meta.get("endpoint") not in ARCHIVE_REDACT_ENDPOINTS or request.meta.get("media"):
            return response
        if spider is not None and getattr(spider, "scraper_name", None) != "catalog":
            return response
        if getattr(getattr(spider, "selection", None), "with_profiles", False):
            return response
        return response.replace(body=redact_body(response.body or b""))


def redact_body(body: bytes) -> bytes:
    """JSON body with personal fields blanked; non-JSON bodies (errors, HTML) are returned unchanged."""
    from ...core.privacy import redact_personal
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body
    return json.dumps(redact_personal(data), ensure_ascii=False).encode("utf-8")
