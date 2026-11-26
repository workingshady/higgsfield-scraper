"""Downloader middleware of the models scraper: turn tool-page HTML and JS chunks into their compact JSON extract
(extract.py) BEFORE the http/ archive (580), the raw/ archive and the parser see them.

Why: a run reads ~500 chunks (~20 MB of minified JS). Archiving them verbatim would make every run folder huge
(http/ + HAR) while only a few KB of each matter. The extract keeps `size` + `sha256` of the original, so a change
is still visible, and `normalize` can re-parse raw/ offline. The Shots feed body is reduced to its facet
(`available_models`, snapshot id/time): the one feed item that comes with it is another user's publication and is
never stored. Responses of other endpoints / scrapers pass through untouched.
"""
from __future__ import annotations

import json

from .endpoints import CHUNK_ENDPOINT, PAGE_ENDPOINT, SHOTS_ENDPOINT
from .extract import extract_chunk, extract_page

SHOTS_KEEP = ("available_models", "snapshot_id", "snapshot_at")


class ModelsExtractMiddleware:
    PRIORITY = 582            # > HttpArchiveMiddleware (580): process_response runs before the http/ archive

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider=None):
        ep = request.meta.get("endpoint")
        if ep not in (PAGE_ENDPOINT, CHUNK_ENDPOINT, SHOTS_ENDPOINT) or request.meta.get("media"):
            return response
        if spider is not None and getattr(spider, "scraper_name", None) != "models":
            return response
        if response.status != 200:
            return response
        return response.replace(body=convert(ep, response.body or b"", response.url,
                                             (request.meta.get("params") or {}).get("chunk")))


def convert(endpoint: str, body: bytes, url: str, chunk: str | None = None) -> bytes:
    if endpoint == SHOTS_ENDPOINT:
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return body
        out = {k: data.get(k) for k in SHOTS_KEEP} if isinstance(data, dict) else {}
    elif endpoint == PAGE_ENDPOINT:
        out = extract_page(body.decode("utf-8", "replace"), url)
    else:
        out = extract_chunk(chunk or url.rsplit("/", 1)[-1], body.decode("utf-8", "replace"))
    return json.dumps(out, ensure_ascii=False).encode("utf-8")
