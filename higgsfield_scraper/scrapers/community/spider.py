"""CommunitySpider: paginates the public community feeds (+ optional detail / comments / pricing for estimates).

    python -m higgsfield_scraper scrape community --feeds trending,approved --max-items 500
    scrapy crawl community -a feeds=approved -a type=video -a max_items=100
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

from ...core.api_spider import BaseApiSpider
from .endpoints import (COMMENTS_ENDPOINT, COMMENTS_PATH, DETAIL_ENDPOINT, DETAIL_PATH, ENDPOINT_FEEDS, FEED_ENDPOINTS,
                        FEED_PARAMS, FEED_PATHS, JOB_COSTS_ENDPOINT, JOB_COSTS_PATH, PAGE_SIZE, PLANS_ENDPOINT,
                        COMPARE_ENDPOINT, COMPARE_PATH, BENEFITS_ENDPOINT, BENEFITS_PATH, VIRAL_ENDPOINT, VIRAL_PATH,
                        PLANS_PATH)
from .parsers import _items_of, repr_cursor


def next_page(body: Any, sent_cursor: Optional[str], new_ids: int) -> tuple[Optional[str], str]:
    """Pagination decision for one listing response -> (next cursor or None, reason).

    Stops when: the page is empty; `has_more` is false or missing (trending/top has no has_more: single page);
    the cursor is null or did not change (top ignores the cursor and repeats page 1); or the page contained no
    item we had not seen already (protects against loops when the trending order shifts).
    """
    if not isinstance(body, dict):
        return None, "non-dict body"
    items = _items_of(body)
    if not items:
        return None, "empty page"
    if body.get("has_more") is not True:
        return None, "has_more false" if "has_more" in body else "no has_more (single-page feed)"
    cur = body.get("cursor")
    if cur is None:
        return None, "cursor null"
    nxt = repr_cursor(cur)
    if sent_cursor is not None and nxt == sent_cursor:
        return None, "cursor repeated"
    if new_ids == 0:
        return None, "no new items on page"
    return nxt, "next"


class CommunitySpider(BaseApiSpider):
    name = "community"
    scraper_name = "community"
    primary_kinds = ("community_generation",)

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.seen_ids: set[str] = set()
        self.detail_requested = 0
        self.stop_reasons: dict[str, str] = {}

    # ------------------------------------------------------------ requests
    def _feed_params(self, feed: str, cursor: Optional[str] = None) -> dict:
        sel = self.selection
        default, maximum = PAGE_SIZE[feed]
        allowed = FEED_PARAMS[feed]
        p: dict[str, Any] = {"size": self.page_size(default, maximum)}
        if cursor is not None:
            p["cursor"] = cursor
        if "type" in allowed and sel.type != "all":
            p["type"] = sel.type
        if "model" in allowed and sel.models:
            p["model"] = list(sel.models)
        if "preset_id" in allowed and sel.preset_ids:
            p["preset_id"] = list(sel.preset_ids)
        if "resolution" in allowed and sel.resolution:
            p["resolution"] = sel.resolution
        return p

    def _listing(self, feed: str, cursor: Optional[str] = None):
        if not self.page_allowed(feed):
            return None
        return self.api_request(FEED_ENDPOINTS[feed], FEED_PATHS[feed], self._feed_params(feed, cursor))

    def _detail(self, publication_id: str, feed: str):
        return self.api_request(DETAIL_ENDPOINT, DETAIL_PATH.format(publication_id=publication_id), None,
                                meta={"params": {"publication_id": publication_id, "feed": feed}}, priority=5)

    def _comments(self, publication_id: str):
        return self.api_request(COMMENTS_ENDPOINT, COMMENTS_PATH.format(publication_id=publication_id), None,
                                auth="required", meta={"params": {"publication_id": publication_id}}, priority=3)

    def build_requests(self) -> Iterator[Any]:
        sel = self.selection
        if sel.estimating:
            yield self.api_request(JOB_COSTS_ENDPOINT, JOB_COSTS_PATH, None, priority=10)
            yield self.api_request(PLANS_ENDPOINT, PLANS_PATH, {"plan_set_key": sel.usd_plan_set,
                                                                "with_localization": "true"}, priority=10)
            yield self.api_request(COMPARE_ENDPOINT, COMPARE_PATH, {"plan_set_key": sel.usd_plan_set,
                                                                    "billing_period": "annual",
                                                                    "with_localization": "true"}, priority=10)
            yield self.api_request(BENEFITS_ENDPOINT, BENEFITS_PATH, {"locale": "en"}, priority=10)
            yield self.api_request(VIRAL_ENDPOINT, VIRAL_PATH, {"lang": "en"}, priority=10)
        if sel.with_comments and not self.authed:
            self.limit_hit("--with-comments skipped: login-only endpoint and no session configured")
        for pid in sel.publication_ids:
            self.detail_requested += 1
            yield self._detail(pid, "detail")
        for feed in sel.feeds:
            r = self._listing(feed)
            if r is not None:
                yield r

    def _detail_budget_left(self) -> Optional[int]:
        mx = self.common.max_items
        return None if mx is None else max(0, mx - self.detail_requested)

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env, entities, response) -> Iterator[Any]:
        sel = self.selection
        if env.endpoint in ENDPOINT_FEEDS:
            feed = ENDPOINT_FEEDS[env.endpoint]
            body = env.body if isinstance(env.body, dict) else {}
            items = _items_of(body)
            sent = env.params.get("cursor")
            if sent is None and body.get("total") is not None:
                self.totals.setdefault(feed, body.get("total"))
            new = [i for i in items if i.get("id") and str(i["id"]) not in self.seen_ids]
            self.seen_ids.update(str(i["id"]) for i in new)
            if sel.detail:                                   # generations come from the detail responses
                for i in new:
                    pid = (i.get("publication") or {}).get("id")
                    left = self._detail_budget_left()
                    if left is not None and left <= 0:
                        self.limit_hit(f"max_items={self.common.max_items} reached")
                        break
                    if pid:
                        self.detail_requested += 1
                        yield self._detail(str(pid), feed)
            if sel.with_comments and self.authed:
                for e in entities:
                    if e["kind"] == "community_generation" and e.get("publication_id"):
                        yield self._comments(e["publication_id"])
            budget = self._detail_budget_left() if sel.detail else self.budget_left()
            nxt, reason = next_page(body, sent, len(new))
            if nxt is not None and budget is not None and budget <= 0:
                nxt, reason = None, "max_items reached"
                self.limit_hit(f"max_items={self.common.max_items} reached")
            self.stop_reasons[feed] = reason
            if nxt is None:
                self.logger.info("feed %s: stop after page %d (%s)", feed, self.pages[feed], reason)
                return
            r = self._listing(feed, nxt)
            if r is not None:
                yield r
        elif env.endpoint == DETAIL_ENDPOINT and sel.with_comments and self.authed:
            for e in entities:
                if e["kind"] == "community_generation" and e.get("publication_id"):
                    yield self._comments(e["publication_id"])
