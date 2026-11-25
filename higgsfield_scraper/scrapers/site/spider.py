"""SiteSpider: sitemaps + SSR pages (TanStack router state / landing HTML) + three small public JSON APIs.

Like BlogSpider, HTML and XML responses are converted to a compact JSON envelope body *before* the shared
`parse_api` runs (raw archive, validation, limits, media), so `normalize` can re-parse `raw/` offline.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterator, Optional
from urllib.parse import urlsplit

import scrapy
from scrapy.http import TextResponse

from ...core.api_spider import BLOCK_MARKERS, BaseApiSpider
from ...raw import Envelope
from ..blog.parsers import extract_sitemap
from . import endpoints as E
from .extract import extract_page
from .parsers import (academy_index_slugs, app_category_slugs, app_index_slugs, course_lesson_paths,
                      is_landing_path, mcp_index_slugs, originals_total, sitemap_urls)
from .schemas import ID_FIELD_BY_KIND, PRIMARY_KINDS

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
PAGE_TYPE = {"apps_index": "apps_index", "app_page": "app", "academy_index": "academy_index",
             "course_page": "course", "lesson_page": "lesson", "mcp_index": "mcp_index", "mcp_skill_page": "mcp_skill",
             "mcp_bundle_page": "mcp_bundle", "originals_index": "originals_index", "episode_page": "episode",
             "mixed_media_page": "mixed_media", "landing_page": "landing", "room_page": "room"}


def _ident(e: dict) -> str:
    """Counting key for --max-items: index and page records of the same app/course/skill count once."""
    if e.get("slug") and ID_FIELD_BY_KIND.get(e["kind"]) == "record_key":
        return str(e["slug"])
    return str(e.get(ID_FIELD_BY_KIND[e["kind"]]))


class SiteSpider(BaseApiSpider):
    name = "site"
    scraper_name = "site"
    primary_kinds = ()          # --max-items is enforced per kind / per detail endpoint by this spider

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._scheduled: set[str] = set()
        self._page_budget: Counter = Counter()
        self._kept: Counter = Counter()
        self._seen: set[tuple[str, str]] = set()
        self._dropped: set[str] = set()
        self._app_categories: set[str] = set()
        self.dead_pages: list[str] = []

    # ------------------------------------------------------------ request helpers
    def page(self, endpoint: str, path: str, *, lastmod: Optional[str] = None, detail: bool = True,
             priority: int = 0) -> Optional[scrapy.Request]:
        path = path.rstrip("/") or "/"
        if path in self._scheduled:
            return None
        if detail and not self.selection.path_ok(path):
            return None
        mx = self.common.max_items
        if detail and mx is not None:
            if self._page_budget[endpoint] >= mx:
                self.limit_hit(f"max_items={mx} reached for {endpoint} (further pages not requested)")
                return None
            self._page_budget[endpoint] += 1
        self._scheduled.add(path)
        return self.api_request(endpoint, path if path != "/" else "/", base=E.SITE, headers=HTML_HEADERS,
                                priority=priority,
                                meta={"params": {"path": path}, "fmt": "html", "lastmod": lastmod, "path": path,
                                      "page_type": PAGE_TYPE.get(endpoint)})

    def sitemap(self, endpoint: str, key: str) -> Optional[scrapy.Request]:
        if E.SITEMAPS[key] in self._scheduled:
            return None
        self._scheduled.add(E.SITEMAPS[key])
        return self.api_request(endpoint, E.SITEMAPS[key], base=E.SITE, priority=5,
                                headers={"Accept": "application/xml,text/xml,*/*"}, meta={"params": {}, "fmt": "xml"})

    def api(self, endpoint: str, path: str) -> scrapy.Request:
        return self.api_request(endpoint, path, priority=8)

    # ------------------------------------------------------------ crawl
    def build_requests(self) -> Iterator[scrapy.Request]:
        s = self.selection
        reqs: list[Optional[scrapy.Request]] = []
        if s.wants("promos"):
            reqs += [self.api("datetime_settings", E.DATETIME_SETTINGS), self.api("business_unlim", E.BUSINESS_UNLIM),
                     self.api("game_gift", E.GAME_GIFT)]
        if s.wants("apps"):
            reqs.append(self.page("apps_index", E.APPS_INDEX, detail=False, priority=10))
        if s.wants("academy"):
            reqs.append(self.page("academy_index", E.ACADEMY_INDEX, detail=False, priority=10))
        if s.wants("mcp"):
            reqs.append(self.page("mcp_index", E.MCP_INDEX, detail=False, priority=10))
        if s.wants("originals"):
            reqs.append(self.page("originals_index", E.ORIGINALS_INDEX, detail=False, priority=10))
            if s.with_content:
                reqs.append(self.sitemap("originals_sitemap", "originals"))
        if s.wants("mixed-media"):
            reqs.append(self.sitemap("mixed_media_sitemap", "mixed-media"))
        if s.wants("landings") or s.wants("rooms"):
            reqs.append(self.sitemap("marketing_sitemap", "marketing"))
        yield from (r for r in reqs if r is not None)

    def parse_api(self, response, **kw):
        """Convert non-JSON bodies, then run the framework's parse_api and apply the per-kind --max-items."""
        for x in self._convert_and_parse(response, **kw):
            if isinstance(x, scrapy.Item) and x.get("kind") in PRIMARY_KINDS:
                kind, ident = x["kind"], _ident(x)
                mx = self.common.max_items
                if mx is not None and self._kept[kind] >= mx and (kind, ident) not in self._seen:
                    self.limit_hit(f"max_items={mx} reached for {kind}")
                    self._dropped.add(str(x.get(ID_FIELD_BY_KIND[kind])))
                    continue
                if (kind, ident) not in self._seen:
                    self._kept[kind] += 1
                    self._seen.add((kind, ident))
            elif isinstance(x, scrapy.Request) and x.meta.get("media") and x.meta.get("media_owner") in self._dropped:
                continue
            yield x

    def _convert_and_parse(self, response, **kw):
        fmt = response.meta.get("fmt")
        if fmt is None:
            yield from super().parse_api(response, **kw)
            return
        raw = response.body
        if response.status == 403 and any(m.encode() in raw for m in BLOCK_MARKERS):
            yield from super().parse_api(response, **kw)     # framework handles bot protection
            return
        if response.status != 200:
            self.dead_pages.append(f"{response.meta.get('path')} -> HTTP {response.status}")
            self.totals["pages_not_200"] = len(self.dead_pages)
            body: Any = {"format": fmt, "status": response.status, "_non_json": raw[:500].decode("utf-8", "replace")}
        elif fmt == "html":
            body = extract_page(raw.decode("utf-8", "replace"), response.meta.get("path"),
                                response.meta.get("lastmod"), response.meta.get("page_type"))
            if not body.get("matches") and not body.get("main_html") and response.meta.get("page_type") != "room":
                self.crawler.stats.inc_value("higgs/site/pages_without_data")
        else:
            body = extract_sitemap(raw.decode("utf-8", "replace"))
        fake = TextResponse(url=response.url, status=response.status, body=json.dumps(body).encode("utf-8"),
                            encoding="utf-8", request=response.request)
        yield from super().parse_api(fake, **kw)

    def _cap_reached(self, kind: str) -> bool:
        mx = self.common.max_items
        return mx is not None and self._kept[kind] >= mx

    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        ep, s = env.endpoint, self.selection
        out: list[Optional[scrapy.Request]] = []
        if ep == "apps_index":
            self._app_categories |= app_category_slugs(env.body)
            slugs = app_index_slugs(env.body)
            self.totals["apps_on_index"] = len(slugs)
            if s.with_content:
                out += [self.page("app_page", f"/apps/{x}") for x in slugs]
                out.append(self.sitemap("apps_sitemap", "apps"))
        elif ep == "apps_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["apps_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                parts = path.strip("/").split("/")
                if len(parts) == 2 and parts[0] == "apps" and parts[1] not in self._app_categories:
                    out.append(self.page("app_page", path, lastmod=u.get("lastmod")))
        elif ep == "academy_index":
            slugs = academy_index_slugs(env.body)
            self.totals["courses_on_index"] = len(slugs)
            if s.with_content:
                out += [self.page("course_page", f"/academy/courses/{x}", priority=2) for x in slugs]
                out.append(self.sitemap("academy_sitemap", "academy"))
        elif ep == "course_page":
            out += [self.page("lesson_page", p) for p in course_lesson_paths(env.body)]
        elif ep == "academy_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["academy_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[:2] == ["academy", "courses"]:
                    out.append(self.page("course_page", path, lastmod=u.get("lastmod"), priority=2))
                elif len(parts) == 4 and parts[:2] == ["academy", "courses"]:
                    out.append(self.page("lesson_page", path, lastmod=u.get("lastmod")))
        elif ep == "mcp_index":
            skills, bundles = mcp_index_slugs(env.body)
            self.totals["mcp_skills_on_index"] = len(skills)
            self.totals["mcp_bundles_on_index"] = len(bundles)
            if s.with_content:
                out += [self.page("mcp_skill_page", f"/mcp/{x}") for x in skills]
                out += [self.page("mcp_bundle_page", f"/mcp/bundles/{x}") for x in bundles]
        elif ep == "originals_index":
            self.totals["original_series"] = originals_total(env.body)
        elif ep == "originals_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["originals_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                if path.count("/") == 3 and path.startswith("/original-series/"):
                    out.append(self.page("episode_page", path, lastmod=u.get("lastmod")))
        elif ep == "mixed_media_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["mixed_media_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                if path.startswith("/mixed-media-presets/preset/"):
                    out.append(self.page("mixed_media_page", path, lastmod=u.get("lastmod")))
        elif ep == "marketing_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["marketing_sitemap_urls"] = len(urls)
            n_land = n_room = 0
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/") or "/"
                if path.startswith("/community/rooms/") and path.count("/") == 3:
                    n_room += 1
                    if s.wants("rooms"):
                        out.append(self.page("room_page", path, lastmod=u.get("lastmod"), priority=-1))
                elif is_landing_path(path):
                    n_land += 1
                    if s.wants("landings"):
                        out.append(self.page("landing_page", path, lastmod=u.get("lastmod")))
            self.totals["landing_urls"] = n_land
            self.totals["room_urls"] = n_room
        yield from (r for r in out if r is not None)
