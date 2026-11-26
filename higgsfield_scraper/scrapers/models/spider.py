"""ModelsSpider: tool pages -> JS chunk graph (prioritized, capped) + /job-sets/costs + Shots facet. GET only.

Bodies arrive already converted to compact JSON by middleware.py (page/chunk extract), so the shared
`BaseApiSpider.parse_api` (raw archive, validation, limits) works unchanged.
"""
from __future__ import annotations

import heapq
from typing import Any, Iterator

import scrapy

from ...core.api_spider import BaseApiSpider
from ...raw import Envelope
from ...run.logging_setup import emit
from . import endpoints as E
from .middleware import ModelsExtractMiddleware

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
JS_HEADERS = {"Accept": "*/*"}


class ModelsSpider(BaseApiSpider):
    name = "models"
    scraper_name = "models"
    primary_kinds = ()
    EXTRACT_MW = "higgsfield_scraper.scrapers.models.middleware.ModelsExtractMiddleware"

    @classmethod
    def update_settings(cls, settings) -> None:
        """Add the extract middleware to the project's DOWNLOADER_MIDDLEWARES (a plain custom_settings dict would
        REPLACE the project's middlewares in this Scrapy version; see AccountSpider)."""
        super().update_settings(settings)
        mws = dict(settings.getdict("DOWNLOADER_MIDDLEWARES"))
        mws[cls.EXTRACT_MW] = ModelsExtractMiddleware.PRIORITY
        settings.set("DOWNLOADER_MIDDLEWARES", mws, priority="spider")

    WINDOW = 4                      # chunk requests in flight; the rest wait in a priority heap (see _pump)

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._chunks: set[str] = set()            # discovered (queued or fetched)
        self._heap: list[tuple[int, int, str]] = []
        self._seq = 0
        self._inflight = 0
        self.chunks_requested = 0

    # ------------------------------------------------------------ requests
    def build_requests(self) -> Iterator[scrapy.Request]:
        s = self.selection
        for path in s.pages:
            yield self.api_request(E.PAGE_ENDPOINT, path, base=E.SITE, headers=HTML_HEADERS, priority=E.PRIO_PAGE,
                                   labels={"page": path})
        if s.with_costs:
            yield self.api_request(E.COSTS_ENDPOINT, E.COSTS_PATH, priority=E.PRIO_PAGE)
        if s.with_shots:
            yield self.api_request(E.SHOTS_ENDPOINT, E.SHOTS_PATH, {"limit": 1}, base=E.COMMUNITY_API,
                                   priority=E.PRIO_PAGE)

    def queue_chunk(self, name: str, priority: int) -> None:
        """Remember a chunk to fetch. Requests are issued by _pump in priority order (preloads of the tool pages,
        then imports of chunks with model data, then the rest) so --max-chunks cuts the least useful ones."""
        if name in self._chunks or not E.CHUNK_NAME_RE.match(name):
            return
        self._chunks.add(name)
        self._seq += 1
        heapq.heappush(self._heap, (-priority, self._seq, name))

    def _pump(self) -> list[scrapy.Request]:
        out = []
        mx = self.selection.max_chunks
        while self._heap and self._inflight < self.WINDOW:
            if mx and self.chunks_requested >= mx:
                self.totals["chunks_not_requested"] = len(self._heap)
                self.limit_hit(f"max_chunks={mx} reached (further JS chunks not requested; the registry may be "
                               f"incomplete, see builds[].coverage)")
                self._heap.clear()
                break
            neg, _, name = heapq.heappop(self._heap)
            self.chunks_requested += 1
            self._inflight += 1
            out.append(self.api_request(E.CHUNK_ENDPOINT, name, base=E.ASSETS, headers=JS_HEADERS, priority=-neg,
                                        labels={"chunk": name}, meta={"chunk_priority": -neg}))
        self.totals["chunks_requested"] = self.chunks_requested
        return out

    # ------------------------------------------------------------ responses
    def parse_api(self, response, **kw):
        yield from super().parse_api(response, **kw)
        if response.meta.get("endpoint") == E.CHUNK_ENDPOINT:
            self._inflight = max(0, self._inflight - 1)
        yield from self._pump()

    def on_error(self, failure):
        out = super().on_error(failure)
        if failure.request.meta.get("endpoint") == E.CHUNK_ENDPOINT:
            self._inflight = max(0, self._inflight - 1)
        return list(out or []) + self._pump()

    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        b = env.body if isinstance(env.body, dict) else {}
        if env.endpoint == E.PAGE_ENDPOINT:
            chunks = [str(c) for c in b.get("chunks") or []]
            self.totals[f"page_chunks:{env.params.get('page')}"] = len(chunks)
            if not chunks:
                emit(self.logger, "warning", "page.fetched", f"no JS chunks found on {env.url}",
                     endpoint__name=env.endpoint)
            for c in chunks:
                self.queue_chunk(c, E.PRIO_PRELOAD)
        elif env.endpoint == E.CHUNK_ENDPOINT:
            parent = int(response.meta.get("chunk_priority") or E.PRIO_PRELOAD)
            step = E.PRIO_DATA_STEP if b.get("markers") or b.get("menus") else E.PRIO_OTHER_STEP
            for r in dict.fromkeys([*(b.get("refs_static") or []), *(b.get("refs_dynamic") or [])]):
                self.queue_chunk(str(r), parent - step)
        return iter(())
