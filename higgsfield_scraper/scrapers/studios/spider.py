"""StudiosSpider: public marketplace / studio content (see docs/scrapers/studios.md for the HTTP flow).

GET only, never with a token (`auth=False`: every source is public and answers identically with a session).
Marketplace bodies have `author.name` blanked BEFORE they are archived (unless --with-profiles), so `normalize`
re-parses exactly what the parsers saw.
"""
from __future__ import annotations

import json
from collections import Counter, deque
from typing import Any, Iterator, Optional

import scrapy
from scrapy.http import TextResponse

from ...core.api_spider import BaseApiSpider
from ...raw import Envelope
from . import parsers
from .endpoints import (APPS, APPS_PAGE_SIZE, CMS, CMS_LANGS, COMMENTS_PAGE_SIZE, COMMUNITY, EMPLOYEES_PAGE_SIZE,
                        FNF, GALLERY_PAGE_SIZE, GAMES_PAGE_SIZE, PLAYABLE_PAGE_SIZE, PRIMARY_KINDS, SKILLS,
                        SKILLS_PAGE_SIZE, STUDIO_MODELS)
from .schemas import ID_FIELD_BY_KIND

# endpoint -> kind whose --max-items cap stops its pagination
CAPPED = {"studios_apps": "studios_app", "studios_games": "studios_game", "studios_skills": "studios_skill",
          "studios_employees": "studios_employee", "studios_playable_presets": "studios_playable_preset",
          "studios_gallery": "studios_gallery_item"}


class StudiosSpider(BaseApiSpider):
    name = "studios"
    scraper_name = "studios"
    primary_kinds = ()                 # --max-items is applied PER KIND below (one source must not starve the rest)

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._kept: Counter = Counter()
        self._seen: set[tuple[str, str]] = set()
        self._feed_pages: Counter = Counter()
        self._comment_queue: deque = deque()
        self._comments_started = False

    # ------------------------------------------------------------ helpers
    @property
    def lang(self) -> str:
        return self.selection.lang

    @property
    def cms_lang(self) -> str:
        return self.lang if self.lang in CMS_LANGS else "en"

    def req(self, endpoint: str, base: str, path: str, params: Optional[dict] = None, *,
            labels: Optional[dict] = None) -> scrapy.Request:
        return self.api_request(endpoint, path, params, base=base, auth=False, labels=labels)

    def _cap_reached(self, kind: str) -> bool:
        mx = self.common.max_items
        return mx is not None and self._kept[kind] >= mx

    def _more(self, endpoint: str, listing: str) -> bool:
        kind = CAPPED.get(endpoint)
        if kind and self._cap_reached(kind):
            self.limit_hit(f"max_items={self.common.max_items} reached for {kind}")
            return False
        return self.page_allowed(listing)

    # ------------------------------------------------------------ first requests
    def build_requests(self) -> Iterator[scrapy.Request]:
        s = self.selection
        for w in s.resolve():
            if w == "apps":
                yield self.req("studios_app_categories", APPS, "/api/v1/apps/categories")
                yield self._apps(0)
            elif w == "games":
                yield self.req("studios_games", SKILLS, "/api/v1/games/community",
                               {"limit": self.page_size(GAMES_PAGE_SIZE, GAMES_PAGE_SIZE), "offset": 0})
            elif w == "skills":
                yield self._cursor("studios_skills", "/api/v1/skills/community", None, 0, SKILLS_PAGE_SIZE)
            elif w == "employees":
                yield self._cursor("studios_employees", "/api/v1/ai-agents/community", None, 0, EMPLOYEES_PAGE_SIZE)
            elif w == "playable_presets":
                yield self._playable(1)
            elif w == "influencer_options":
                yield self.req("studios_influencer_config", CMS, "/ai-influencer-config", {"lang": self.cms_lang})
            elif w == "galleries":
                for studio in s.resolve_studios():
                    for feed in s.gallery_feeds:
                        # approved honours a repeated `model` (total = sum); trending only the LAST one -> per model
                        for model in ([None] if feed == "approved" else STUDIO_MODELS[studio]):
                            r = self._gallery(studio, feed, None, 0, model)
                            if r is not None:
                                yield r

    def _apps(self, offset: int) -> scrapy.Request:
        return self.req("studios_apps", APPS, "/api/v1/apps/community",
                        {"limit": self.page_size(APPS_PAGE_SIZE, APPS_PAGE_SIZE), "offset": offset,
                         "sort": self.selection.apps_sort})

    def _cursor(self, endpoint: str, path: str, cursor: Optional[str], rank_base: int, size: int) -> scrapy.Request:
        return self.req(endpoint, SKILLS, path, {"limit": self.page_size(size, size), "cursor": cursor},
                        labels={"rank_base": rank_base})

    def _playable(self, page: int) -> scrapy.Request:
        return self.req("studios_playable_presets", CMS, "/playable-ads-presets",
                        {"size": PLAYABLE_PAGE_SIZE, "cursor": page, "lang": self.cms_lang})

    def _gallery(self, studio: str, feed: str, cursor: Any, rank_base: int,
                 model: Optional[str] = None) -> Optional[scrapy.Request]:
        key = f"gallery:{studio}:{feed}" + (f":{model}" if model else "")
        mx = self.selection.gallery_pages
        if mx and self._feed_pages[key] >= mx:
            self.limit_hit(f"gallery_pages={mx} reached for {key}")
            return None
        if not self._more("studios_gallery", key):
            return None
        self._feed_pages[key] += 1
        size = self.page_size(GALLERY_PAGE_SIZE, GALLERY_PAGE_SIZE)
        p: dict[str, Any] = {"size": size, "model": model or list(STUDIO_MODELS[studio])}
        if feed == "approved":
            p["approved"] = "true"
        if cursor not in (None, ""):
            p["cursor"] = repr(cursor) if isinstance(cursor, float) else cursor   # full float precision
        return self.req("studios_gallery", FNF, f"/publications/community/{feed}", p,
                        labels={"studio": studio, "feed": feed, "page": self._feed_pages[key],
                                "rank_base": rank_base, "listing": key})

    def parse_api(self, response, **kw):
        for x in self._convert_and_parse(response, **kw):
            if isinstance(x, scrapy.Item) and x.get("kind") in PRIMARY_KINDS:
                kind = x["kind"]
                ident = str(x.get(ID_FIELD_BY_KIND[kind]))
                if (kind, ident) not in self._seen:
                    if self._cap_reached(kind):
                        self.limit_hit(f"max_items={self.common.max_items} reached for {kind}")
                        continue
                    self._kept[kind] += 1
                    self._seen.add((kind, ident))
            yield x

    def _convert_and_parse(self, response, **kw):
        ep = response.meta.get("endpoint")
        if ep in parsers.AUTHOR_ENDPOINTS and response.status == 200 and not self.selection.with_profiles:
            try:
                body = parsers.redact_author_names(json.loads(response.body))
            except ValueError:
                body = None
            if body is not None:
                yield from super().parse_api(self._fake(response, body), **kw)
                return
        yield from super().parse_api(response, **kw)
        if ep == "studios_comments" and response.status != 200:      # keep the sequential comment chain going
            yield from self._next_comments()

    def on_error(self, failure):
        out = super().on_error(failure)
        if failure.request.meta.get("endpoint") == "studios_comments":
            return list(self._next_comments())
        return out

    @staticmethod
    def _fake(response, body: Any) -> TextResponse:
        return TextResponse(url=response.url, status=200, body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                            encoding="utf-8", request=response.request)

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        ep, b = env.endpoint, env.body
        if not isinstance(b, dict):
            return
        if ep in ("studios_apps", "studios_games"):
            nxt = b.get("next_offset")
            if b.get("items") and nxt is not None and self._more(ep, ep):
                if ep == "studios_apps":
                    yield self._apps(int(nxt))
                else:
                    yield self.req(ep, SKILLS, "/api/v1/games/community",
                                   {"limit": self.page_size(GAMES_PAGE_SIZE, GAMES_PAGE_SIZE), "offset": int(nxt)})
            elif not b.get("items") or nxt is None:
                self.totals[ep.replace("studios_", "")] = int(env.params.get("offset") or 0) + len(b.get("items") or [])
        elif ep in ("studios_skills", "studios_employees"):
            nxt = b.get("next_cursor")
            base = int(env.params.get("rank_base") or 0) + len(b.get("items") or [])
            if b.get("items") and nxt and self._more(ep, ep):
                path = "/api/v1/skills/community" if ep == "studios_skills" else "/api/v1/ai-agents/community"
                size = SKILLS_PAGE_SIZE if ep == "studios_skills" else EMPLOYEES_PAGE_SIZE
                yield self._cursor(ep, path, nxt, base, size)
            elif not nxt:
                self.totals[ep.replace("studios_", "")] = base
        elif ep == "studios_playable_presets":
            self.totals.setdefault("playable_presets", b.get("total"))
            cur = b.get("cursor")
            if b.get("items") and cur not in (None, "") and self._more(ep, ep):
                yield self._playable(int(cur))
        elif ep == "studios_gallery":
            studio, feed = env.params.get("studio"), env.params.get("feed")
            model = env.params.get("model") if feed == "trending" else None
            self.totals.setdefault(f"gallery_{studio}_{feed}" + (f"_{model}" if model else ""), b.get("total"))
            if self.selection.with_comments:
                self._comment_queue.extend(e["publication_id"] for e in entities      # only rows kept by the cap
                                           if e["kind"] == "studios_gallery_item" and e.get("publication_id")
                                           and ("studios_gallery_item", str(e["id"])) in self._seen)
                if not self._comments_started:
                    self._comments_started = True
                    yield from self._next_comments()
            base = int(env.params.get("rank_base") or 0) + len(b.get("items") or [])
            if b.get("items") and b.get("has_more") and b.get("cursor") is not None:
                r = self._gallery(studio, feed, b.get("cursor"), base, model)
                if r is not None:
                    yield r
        elif ep == "studios_comments":
            self.totals["comments"] = (self.totals.get("comments") or 0) + int(b.get("total") or 0) \
                if not env.params.get("cursor") else self.totals.get("comments")
            nxt = b.get("next_cursor")
            pid = env.params.get("publication_id")
            if b.get("items") and nxt and self.page_allowed(f"comments:{pid}"):
                yield self._comments(pid, nxt)
            else:
                yield from self._next_comments()

    def _comments(self, pid: str, cursor: Optional[str] = None) -> scrapy.Request:
        return self.req("studios_comments", COMMUNITY, f"/entities/generation_publication/{pid}/comments",
                        {"limit": COMMENTS_PAGE_SIZE, "cursor": cursor}, labels={"publication_id": pid})

    def _next_comments(self) -> Iterator[scrapy.Request]:
        """One comment thread at a time (sequential, keeps ~1 req/s and a deterministic order)."""
        if self._comment_queue:
            yield self._comments(self._comment_queue.popleft())
        else:
            self._comments_started = False
