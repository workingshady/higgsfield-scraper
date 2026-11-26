"""BaseApiSpider: shared spider machinery for JSON-API scrapers.

Subclass contract:
    scraper_name = "community"                    # registry key
    def build_requests(self) -> Iterator[Request]  # first requests (use self.api_request)
    def follow_up(self, env, entities, response)   # optional: pagination / detail requests (generator)

Provided:
    self.selection / self.common (CommonOptions) / self.sdef (ScraperDef) / self.run_ctx
    self.api_request(endpoint, path, params, auth=False|True|"required", ...)
    self.count_primary(kind) / self.budget_left() / self.page_allowed(listing)  — limits
    self.limit_hit(reason)                     — records into dataset meta.limits_hit
    self.totals[...]                           — API-reported totals, written to meta.totals_available
    bot-protection stop (DataDome captcha 403 -> close spider), media download (--download-media)
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlencode, urlsplit

import scrapy
from scrapy.exceptions import CloseSpider

from ..constants import API_BASE
from ..items import RawResponseItem, to_item
from ..raw import Envelope
from ..run.logging_setup import emit
from . import registry
from .auth import TokenProvider
from .base import CommonOptions

HANDLED = [400, 401, 403, 404, 405, 409, 422, 429]
SAFETY_LIMITS = ("bot protection", "closespider", "max_requests", "max_minutes")
BLOCK_MARKERS = ("captcha-delivery.com", "datadome")


class BaseApiSpider(scrapy.Spider):
    scraper_name: str = ""
    api_base: str = API_BASE
    primary_kinds: tuple[str, ...] = ()          # kinds counted against --max-items

    def __init__(self, selection: Any = None, common: Optional[CommonOptions] = None, token: Optional[str] = None,
                 **kwargs: Any):
        name_kw = {k: v for k, v in kwargs.items() if k in ("run_ctx", "name")}
        super().__init__(**name_kw)
        self.sdef = registry.get(self.scraper_name)
        if selection is None:                            # plain `scrapy crawl x -a key=value`
            selection = self.sdef.selection_from_dict({k: v for k, v in kwargs.items() if k not in name_kw})
        self.selection = selection
        self.common = common if isinstance(common, CommonOptions) else CommonOptions.from_dict(
            {k: _coerce(v) for k, v in kwargs.items() if k in CommonOptions.__dataclass_fields__})
        self.token = token
        self.token_provider = TokenProvider.from_env(token) if self.common.auth != "off" else None
        self.primary_count = 0
        self._counted: set[tuple[str, str]] = set()
        self.pages: Counter = Counter()
        self.limits_hit: list[str] = []
        self.totals: dict[str, Optional[int]] = {}
        self.media_files = 0
        self.media_bytes = 0
        self._media_seen: set[str] = set()

    # ------------------------------------------------------------ helpers
    @property
    def authed(self) -> bool:
        return bool(self.token_provider and self.token_provider.configured)

    def api_request(self, endpoint: str, path: str, params: Optional[dict] = None, *, auth: Any = False,
                    callback=None, cb_kwargs: Optional[dict] = None, meta: Optional[dict] = None,
                    base: Optional[str] = None, priority: int = 0, headers: Optional[dict] = None,
                    labels: Optional[dict] = None) -> scrapy.Request:
        """`labels` are recorded with the response (raw/ file name, Envelope.params, provenance) but NOT sent —
        use them for path ids, page numbers, feed names…; long cursors belong in `params` only if needed."""
        params = {k: v for k, v in (params or {}).items() if v is not None}
        query = urlencode([(k, x) for k, v in params.items() for x in (v if isinstance(v, (list, tuple)) else [v])])
        url = f"{base or self.api_base}{path}" + (f"?{query}" if query else "")
        recorded = {k: (",".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)) for k, v in params.items()}
        recorded.update({k: str(v) for k, v in (labels or {}).items() if v is not None})
        m = {"endpoint": endpoint, "params": recorded,
             "auth": auth, "handle_httpstatus_list": HANDLED, **(meta or {})}
        return scrapy.Request(url, callback=callback or self.parse_api, errback=self.on_error, cb_kwargs=cb_kwargs,
                              meta=m, dont_filter=True, priority=priority, headers=headers)

    def count_primary(self, n: int = 1) -> None:
        self.primary_count += n

    def budget_left(self) -> Optional[int]:
        mx = self.common.max_items
        return None if mx is None else max(0, mx - self.primary_count)

    def page_allowed(self, listing: str) -> bool:
        if self.common.max_pages is not None and self.pages[listing] >= self.common.max_pages:
            self.limit_hit(f"max_pages={self.common.max_pages} reached for {listing}")
            return False
        self.pages[listing] += 1
        return True

    def limit_hit(self, reason: str) -> None:
        """Record a limit (dataset meta.limits_hit) and log `limit.hit`: info for user limits, warn for safety caps."""
        if reason not in self.limits_hit:
            self.limits_hit.append(reason)
            safety = any(m in reason for m in SAFETY_LIMITS)
            emit(self.logger, "warning" if safety else "info", "limit.hit", f"limit: {reason}", limit=reason,
                 limit__kind="safety" if safety else "user")

    def page_size(self, default: int, maximum: int) -> int:
        return max(1, min(self.common.page_size or default, maximum))

    # ------------------------------------------------------------ crawl
    async def start(self):
        for r in self.build_requests():
            yield r

    def start_requests(self):
        yield from self.build_requests()

    def build_requests(self) -> Iterator[scrapy.Request]:  # pragma: no cover - abstract
        raise NotImplementedError

    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        return iter(())

    def parse_api(self, response, **_):
        endpoint, params = response.meta["endpoint"], response.meta.get("params") or {}
        stats = self.crawler.stats
        stats.inc_value(f"higgs/responses/{endpoint}/{response.status}")
        text = response.text if hasattr(response, "text") else response.body.decode("utf-8", "replace")
        if response.status == 403 and any(m in text for m in BLOCK_MARKERS):
            stats.inc_value("higgs/blocked")
            msg = f"bot protection (DataDome captcha) on {endpoint} — stopping, no evasion attempted"
            emit(self.logger, "error", "request.blocked", msg, endpoint__name=endpoint,
                 http__response__status_code=response.status, request_id=response.meta.get("request_id"),
                 stop=self.common.stop_on_block)
            self.limit_hit(msg)
            if self.common.stop_on_block:
                raise CloseSpider("blocked_by_bot_protection")
            return
        try:
            body: Any = json.loads(text)
        except ValueError:
            body = {"_non_json": text[:2000]}
            stats.inc_value("higgs/non_json_responses")
        env = Envelope(endpoint=endpoint, url=response.url, status=response.status, body=body, params=params,
                       fetched_at=datetime.now(timezone.utc))
        yield RawResponseItem(kind="raw_response", endpoint=endpoint, url=response.url, params=params,
                              status=response.status, fetched_at=env.fetched_at.isoformat(), body=body)
        if response.status != 200:
            optional = endpoint in self.sdef.optional_endpoints or response.meta.get("auth")
            emit(self.logger, "info" if optional else "warning", "page.fetched",
                 f"{endpoint} -> HTTP {response.status} {str(body)[:160]}", endpoint__name=endpoint,
                 http__response__status_code=response.status, request_id=response.meta.get("request_id"),
                 outcome="http_error", optional=bool(optional))
            return
        entities = self.sdef.parse_envelope(env, self.selection)
        kept = [e for e in entities if self.sdef.keep(e, self.selection)]
        budget = self.budget_left()
        out = []
        id_fields = self.sdef.id_field_by_kind
        for e in kept:
            if e["kind"] in self.primary_kinds:
                key = (e["kind"], str(e.get(id_fields.get(e["kind"], "")) or id(e)))
                if key in self._counted:                    # repeats (e.g. same item in two listings) are free
                    out.append(e)
                    continue
                self._counted.add(key)
                if budget is not None and budget <= 0:
                    self.limit_hit(f"max_items={self.common.max_items} reached")
                    continue
                if budget is not None:
                    budget -= 1
                self.count_primary()
            out.append(e)
        emit(self.logger, "debug", "page.fetched", f"{endpoint} {params or ''} -> {len(entities)} entities "
             f"({len(out)} kept)", endpoint__name=endpoint, http__response__status_code=response.status,
             request_id=response.meta.get("request_id"), entities__count=len(entities), kept__count=len(out),
             outcome="success")
        for e in out:
            stats.inc_value(f"higgs/parsed/{e['kind']}")
            yield to_item(e)
            if self.common.download_media != "none" and self.sdef.media_urls:
                yield from self._media_requests(e)
        yield from self.follow_up(env, out, response)

    def on_error(self, failure):
        from scrapy.exceptions import IgnoreRequest
        from scrapy.spidermiddlewares.httperror import HttpError
        req = failure.request
        endpoint = req.meta.get("endpoint")
        # HttpError subclasses IgnoreRequest: a server error on a login-only request is an error, not "no session"
        if failure.check(IgnoreRequest) and not failure.check(HttpError) and req.meta.get("auth"):
            # login-only request without a session (auth="required"): an expected skip, not an error
            self.crawler.stats.inc_value(f"higgs/auth/skipped/{endpoint}")
            emit(self.logger, "info", "request.skipped", f"skipped login-only {endpoint} (no session): {failure.value}",
                 endpoint__name=endpoint, reason="no_session")
            return
        self.crawler.stats.inc_value(f"higgs/request_errors/{endpoint}")
        emit(self.logger, "debug" if req.meta.get("_gave_up") else "error", "external.call.failed",
             f"request failed for {endpoint}: {failure.value!r}", endpoint__name=endpoint,
             request_id=req.meta.get("request_id"), error__type=type(failure.value).__name__,
             url__full=req.url)

    # ------------------------------------------------------------ media
    def _media_requests(self, entity: dict) -> Iterator[scrapy.Request]:
        for role, url in self.sdef.media_urls(entity, self.common.download_media) or []:
            if not url or url in self._media_seen:
                continue
            if self.media_files >= self.common.max_media_files:
                self.limit_hit(f"max_media_files={self.common.max_media_files} reached")
                return
            if self.media_bytes >= self.common.max_media_mb * 1024 * 1024:
                self.limit_hit(f"max_media_mb={self.common.max_media_mb} reached")
                return
            self._media_seen.add(url)
            self.media_files += 1
            yield scrapy.Request(url, callback=self.save_media, errback=self.on_error, dont_filter=True, priority=-10,
                                 meta={"media": True, "endpoint": "media", "handle_httpstatus_list": HANDLED,
                                       "media_kind": entity["kind"], "media_role": role,
                                       "media_owner": str(entity.get(self.sdef.id_field_by_kind.get(entity["kind"], "id"), "x"))})

    def save_media(self, response):
        m = response.meta
        if response.status != 200:
            self.crawler.stats.inc_value(f"higgs/media/http_{response.status}")
            return
        ext = os.path.splitext(urlsplit(response.url).path)[1][:8] or mimetypes.guess_extension(
            (response.headers.get("Content-Type") or b"").decode().split(";")[0]) or ".bin"
        name = f"{_slug(m['media_owner'])}__{_slug(m['media_role'])}__{hashlib.sha1(response.url.encode()).hexdigest()[:8]}{ext}"
        d = self.run_ctx.run_dir / "media" / m["media_kind"]
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(response.body)
        self.media_bytes += len(response.body)
        self.crawler.stats.inc_value("higgs/media/saved")
        self.crawler.stats.inc_value("higgs/media/bytes", len(response.body))
        with (self.run_ctx.run_dir / "media" / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": m["media_kind"], "owner": m["media_owner"], "role": m["media_role"],
                                "url": response.url, "file": f"media/{m['media_kind']}/{name}",
                                "bytes": len(response.body)}, ensure_ascii=False) + "\n")


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)[:60] or "x"


def _coerce(v: Any) -> Any:
    if isinstance(v, str):
        low = v.lower()
        if low in ("true", "false"):
            return low == "true"
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v
    return v
