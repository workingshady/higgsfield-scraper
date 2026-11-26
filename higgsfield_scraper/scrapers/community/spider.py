"""CommunitySpider: paginates the public community feeds (+ optional detail / comments / pricing for estimates).

    python -m higgsfield_scraper scrape community --feeds trending,approved --max-items 500
    scrapy crawl community -a feeds=approved -a type=video -a max_items=100
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterator, Optional

import scrapy

from ...core.api_spider import BaseApiSpider
from ...run.logging_setup import emit
from .endpoints import (COMMENTS_ENDPOINT, COMMENTS_PAGE_SIZE, COMMENTS_PATH, COMMUNITY_BASE, POSTS_ENDPOINT,
                        POSTS_MAX_LIMIT, POSTS_PATH, DETAIL_ENDPOINT, DETAIL_PATH, ENDPOINT_FEEDS, FEED_ENDPOINTS,
                        FEED_PARAMS, FEED_PATHS, JOB_COSTS_ENDPOINT, JOB_COSTS_PATH, PAGE_SIZE, PLANS_ENDPOINT,
                        COMPARE_ENDPOINT, COMPARE_PATH, BENEFITS_ENDPOINT, BENEFITS_PATH, VIRAL_ENDPOINT, VIRAL_PATH,
                        PLANS_PATH)
from .endpoints import (CREATORS_PATH, ENTITY_COMMENTS_ENDPOINT, ENTITY_COMMENTS_PAGE_SIZE, ENTITY_COMMENTS_PATH,
                        EXTRA_ENDPOINTS, EXTRA_KINDS, EXTRA_PAGE_SIZE, FEED_ITEM_ENTITY, FEED_PATH, SHOTS_PATH,
                        TALENTS_PATH)
from .parsers import _items_of, parse_posts, repr_cursor

EXTRA_FEED_OF = {v: k for k, v in EXTRA_ENDPOINTS.items()}
EXTRA_ID_FIELD = {"community_shot": "shot_id", "community_post": "post_id", "community_feed_item": "feed_item_id",
                  "community_creator_stats": "record_id"}


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
        # opt-in Community pages: per-feed --max-items accounting (unused by default runs)
        self._extra_kept: Counter = Counter()
        self._extra_seen: set[tuple[str, str]] = set()
        self._extra_dropped: set[str] = set()
        self._extra_ids: set[str] = set()

    @classmethod
    def update_settings(cls, settings) -> None:
        """Add the creators privacy middleware (acts only on --feeds creators/talents responses; a no-op otherwise)
        to the project's DOWNLOADER_MIDDLEWARES without replacing them (see account/spider.py)."""
        super().update_settings(settings)
        from .privacy import CreatorsPrivacyMiddleware
        mws = dict(settings.getdict("DOWNLOADER_MIDDLEWARES"))
        mws[CreatorsPrivacyMiddleware.PATH] = CreatorsPrivacyMiddleware.PRIORITY
        settings.set("DOWNLOADER_MIDDLEWARES", mws, priority="spider")

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

    def _posts(self):
        """Community posts feed (fnf-community) — only to find comment threads (see endpoints.py)."""
        limit = min(POSTS_MAX_LIMIT, self.common.max_items or 20)
        return self.api_request(POSTS_ENDPOINT, POSTS_PATH, {"limit": limit}, base=COMMUNITY_BASE, priority=3)

    def _comments(self, publication_id: str, offset: int = 0, parent_id: Optional[str] = None):
        params = {"limit": COMMENTS_PAGE_SIZE, "offset": offset or None, "parent_id": parent_id}
        return self.api_request(COMMENTS_ENDPOINT, COMMENTS_PATH.format(publication_id=publication_id), params,
                                base=COMMUNITY_BASE, labels={"publication_id": publication_id}, priority=3)

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
        if sel.with_comments and not sel.wants("posts"):   # with --feeds posts the listing itself finds threads
            yield self._posts()
        for feed in sel.extra_feeds:
            r = self._extra(feed)
            if r is not None:
                yield r
        for pid in sel.publication_ids:
            self.detail_requested += 1
            yield self._detail(pid, "detail")
        for feed in sel.feeds:
            r = self._listing(feed)
            if r is not None:
                yield r

    # ------------------------------------------------------------ opt-in Community pages
    def _extra_left(self, feed: str) -> Optional[int]:
        mx = self.common.max_items
        return None if mx is None else max(0, mx - self._extra_kept[feed])

    def _extra(self, feed: str, cursor: Optional[str] = None, offset: int = 0):
        """First / next page of an opt-in feed. The page size never exceeds what --max-items still allows."""
        left = self._extra_left(feed)
        if left is not None and left <= 0:
            self.limit_hit(f"max_items={self.common.max_items} reached for {feed}")
            return None
        if not self.page_allowed(feed):
            return None
        sel = self.selection
        size = self.page_size(*EXTRA_PAGE_SIZE[feed])
        if left is not None:
            size = max(1, min(size, left))
        ep = EXTRA_ENDPOINTS[feed]
        labels = {"offset": offset} if feed in ("shots", "feed", "creators") else None
        if feed == "shots":
            params = {"limit": size, "type": sel.type if sel.type in ("image", "video") else None,
                      "models": ",".join(sel.models) or None, "cursor": cursor}
            return self.api_request(ep, SHOTS_PATH, params, base=COMMUNITY_BASE, labels=labels)
        if feed == "posts":
            return self.api_request(ep, POSTS_PATH, {"limit": size, "offset": offset or None}, base=COMMUNITY_BASE)
        if feed == "feed":
            return self.api_request(ep, FEED_PATH, {"limit": size, "cursor": cursor}, base=COMMUNITY_BASE,
                                    labels=labels)
        if feed == "creators":
            return self.api_request(ep, CREATORS_PATH, {"all": "true", "sort": "default", "limit": size,
                                                        "cursor": cursor}, labels=labels)
        return self.api_request(ep, TALENTS_PATH, {"sort": "rating", "limit": size, "offset": offset})

    def _entity_comments(self, entity_type: str, entity_id: str, cursor: Optional[str] = None,
                         parent_id: Optional[str] = None):
        params = {"limit": ENTITY_COMMENTS_PAGE_SIZE, "cursor": cursor, "parent_id": parent_id}
        return self.api_request(ENTITY_COMMENTS_ENDPOINT,
                                ENTITY_COMMENTS_PATH.format(entity_type=entity_type, entity_id=entity_id), params,
                                base=COMMUNITY_BASE, labels={"entity_type": entity_type, "entity_id": entity_id},
                                priority=3)

    def parse_api(self, response, **kw):
        """Base parsing; with opt-in feeds, also the per-feed --max-items cap (items beyond it are dropped)."""
        if not self.selection.extra_feeds:
            yield from super().parse_api(response, **kw)
            return
        mx = self.common.max_items
        feed = EXTRA_FEED_OF.get(response.meta.get("endpoint"))
        for x in super().parse_api(response, **kw):
            if feed is not None and isinstance(x, scrapy.Item) and x.get("kind") == EXTRA_KINDS[feed]:
                ident = str(x.get(EXTRA_ID_FIELD[x["kind"]]))
                if (feed, ident) not in self._extra_seen:
                    if mx is not None and self._extra_kept[feed] >= mx:
                        self.limit_hit(f"max_items={mx} reached for {feed}")
                        self._extra_dropped.add(ident)
                        continue
                    self._extra_kept[feed] += 1
                    self._extra_seen.add((feed, ident))
                    self._extra_ids.add(ident)
            elif isinstance(x, scrapy.Request) and x.meta.get("media") and \
                    x.meta.get("media_owner") in self._extra_dropped:
                continue
            yield x

    def _extra_follow_up(self, env, entities) -> Iterator[Any]:
        sel = self.selection
        feed = EXTRA_FEED_OF[env.endpoint]
        body = env.body if isinstance(env.body, dict) else {}
        kept = [e for e in entities if str(e.get(EXTRA_ID_FIELD.get(e.get("kind"), ""), "")) in self._extra_ids]
        if sel.with_comments:                                 # comment threads of the kept items
            for e in kept:
                if not (e.get("comments") or 0) > 0:
                    continue
                if e["kind"] == "community_shot":
                    yield self._entity_comments("generation_publication", e["shot_id"])
                elif e["kind"] == "community_post":
                    yield self._comments(e["post_id"])
                elif e["kind"] == "community_feed_item":
                    if e["item_type"] == "post":
                        yield self._comments(e["item_id"])
                    elif e["item_type"] in FEED_ITEM_ENTITY:
                        yield self._entity_comments(FEED_ITEM_ENTITY[e["item_type"]], e["item_id"])
        if feed == "posts":
            n = len(body.get("publications") or [])
        elif feed in ("creators", "talents"):
            n = len(body.get("users") or [])
            if body.get("total") is not None and feed not in self.totals:
                self.totals[feed] = body.get("total")
        else:
            n = len(_items_of(body))
        offset = int(env.params.get("offset") or 0)
        nxt_cursor, nxt_offset, reason = None, None, "next"
        if n == 0:
            reason = "empty page"
        elif feed == "posts":
            reason = "next" if body.get("has_more") is True else "has_more false"
            nxt_offset = offset + n
        elif feed == "talents":
            no = body.get("next_offset")
            reason = "next" if isinstance(no, int) and no > offset else "no next_offset"
            nxt_offset = no if isinstance(no, int) else None
        else:
            nxt_cursor = body.get("next_cursor")
            if not nxt_cursor or nxt_cursor == env.params.get("cursor"):
                reason = "no next_cursor"
            nxt_offset = offset + n
        if reason == "next" and not kept:
            reason = "no new items on page"
        left = self._extra_left(feed)
        if reason == "next" and left is not None and left <= 0:
            reason = "max_items reached"
            self.limit_hit(f"max_items={self.common.max_items} reached for {feed}")
        self.stop_reasons[feed] = reason
        if reason != "next":
            emit(self.logger, "info", "listing.finished", f"feed {feed}: stop after page {self.pages[feed]} "
                 f"({reason})", listing=feed, pages__count=self.pages[feed], reason=reason)
            return
        r = self._extra(feed, nxt_cursor, nxt_offset or 0)
        if r is not None:
            yield r

    def _detail_budget_left(self) -> Optional[int]:
        mx = self.common.max_items
        return None if mx is None else max(0, mx - self.detail_requested)

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env, entities, response) -> Iterator[Any]:
        sel = self.selection
        if env.endpoint in EXTRA_FEED_OF:
            yield from self._extra_follow_up(env, entities)
        elif env.endpoint == ENTITY_COMMENTS_ENDPOINT and isinstance(env.body, dict):
            etype, eid = env.params.get("entity_type") or "", env.params.get("entity_id") or ""
            parent = env.params.get("parent_id")
            nxt = env.body.get("next_cursor")
            if nxt and entities and nxt != env.params.get("cursor") and \
                    self.page_allowed(f"comments:{eid}:{parent or ''}"):
                yield self._entity_comments(etype, eid, nxt, parent)
            if parent is None:                               # replies (one level, as in the web app)
                for e in entities:
                    if (e.get("reply_count") or 0) > 0:
                        yield self._entity_comments(etype, eid, parent_id=e["comment_id"])
        elif env.endpoint in ENDPOINT_FEEDS:
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
            budget = self._detail_budget_left() if sel.detail else self.budget_left()
            nxt, reason = next_page(body, sent, len(new))
            if nxt is not None and budget is not None and budget <= 0:
                nxt, reason = None, "max_items reached"
                self.limit_hit(f"max_items={self.common.max_items} reached")
            self.stop_reasons[feed] = reason
            if nxt is None:
                emit(self.logger, "info", "listing.finished", f"feed {feed}: stop after page {self.pages[feed]} "
                     f"({reason})", listing=feed, pages__count=self.pages[feed], reason=reason)
                return
            r = self._listing(feed, nxt)
            if r is not None:
                yield r
        elif env.endpoint == POSTS_ENDPOINT:
            posts = parse_posts(env.body)
            with_comments = [p for p in posts if p["comment_count"] > 0]
            emit(self.logger, "info", "listing.finished", f"community posts: {len(posts)} fetched, "
                 f"{len(with_comments)} with comments", listing=POSTS_ENDPOINT, items__count=len(posts))
            for p in with_comments:
                yield self._comments(p["id"])
        elif env.endpoint == COMMENTS_ENDPOINT and isinstance(env.body, dict):
            pid = env.params.get("publication_id") or ""
            parent = env.params.get("parent_id")
            if env.body.get("has_more") is True and entities:
                yield self._comments(pid, int(env.params.get("offset") or 0) + len(entities), parent)
            if parent is None:                               # replies (one level, as in the web app)
                for e in entities:
                    if (e.get("reply_count") or 0) > 0:
                        yield self._comments(pid, parent_id=e["comment_id"])
