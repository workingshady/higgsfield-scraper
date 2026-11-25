"""BlogSpider: sitemaps + SSR pages (TanStack router state) + JSON API feeds + Yjs post bodies.

BaseApiSpider assumes JSON responses. This spider converts HTML / XML / binary responses into a compact JSON
envelope body *before* handing them to the shared `parse_api` (raw archive, validation, limits, media), so the
framework code path stays the same and `normalize` can re-parse `raw/` offline.
"""
from __future__ import annotations

import base64
import json
from collections import Counter
from typing import Any, Iterator, Optional
from urllib.parse import urlsplit

import scrapy
from scrapy.http import TextResponse

from ...core.api_spider import BLOCK_MARKERS, BaseApiSpider
from ...raw import Envelope
from . import endpoints as E
from .parsers import (case_study_slugs, enterprise_index_paths, extract_page, extract_sitemap, help_index_paths,
                      index_post_slugs, sitemap_urls)
from .schemas import ID_FIELD_BY_KIND, PRIMARY_KINDS

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


class BlogSpider(BaseApiSpider):
    name = "blog"
    scraper_name = "blog"
    primary_kinds = ()          # --max-items is enforced per collection by this spider (see _cap)

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._scheduled: set[str] = set()
        self._lastmod: dict[str, Optional[str]] = {}
        self._page_budget: Counter = Counter()             # detail pages scheduled per endpoint
        self._kept: Counter = Counter()                    # primary entities kept per kind
        self._accepted: set[str] = set()                   # ids of kept primary entities
        self._seen: set[tuple[str, str]] = set()
        self._dropped: set[str] = set()
        self._blog_categories: set[str] = set()
        self._case_categories: set[str] = {"creators", "customers"}
        self._blog_sitemap_paths: list[str] = []

    # ------------------------------------------------------------ request helpers
    def _loc(self, path: str) -> str:
        loc = self.selection.locale
        return path if loc == "en" else f"/{loc}{path}"

    def page(self, endpoint: str, path: str, *, lastmod: Optional[str] = None, detail: bool = True,
             priority: int = 0) -> Optional[scrapy.Request]:
        path = self._loc(path)
        if path in self._scheduled:
            return None
        mx = self.common.max_items
        if detail and mx is not None:
            if self._page_budget[endpoint] >= mx:
                self.limit_hit(f"max_items={mx} reached for {endpoint} (further pages not requested)")
                return None
            self._page_budget[endpoint] += 1
        self._scheduled.add(path)
        return self.api_request(endpoint, path, base=E.SITE, headers=HTML_HEADERS, priority=priority,
                                meta={"params": {"path": path}, "fmt": "html", "lastmod": lastmod, "path": path})

    def sitemap(self, endpoint: str, key: str) -> scrapy.Request:
        return self.api_request(endpoint, E.SITEMAPS[key], base=E.SITE, priority=5,
                                headers={"Accept": "application/xml,text/xml,*/*"},
                                meta={"params": {}, "fmt": "xml"})

    def feed(self, endpoint: str, path: str, cursor: Optional[str] = None) -> scrapy.Request:
        size = self.page_size(min(E.LIST_MAX, self.common.max_items or E.LIST_MAX), E.LIST_MAX)
        # the opaque cursor (~250 chars) stays in the URL; raw/ file names use the page number instead
        return self.api_request(endpoint, path, {"size": size, "cursor": cursor}, priority=3,
                                meta={"params": {"size": str(size), "page": str(self.pages[endpoint])}})

    # ------------------------------------------------------------ crawl
    def build_requests(self) -> Iterator[scrapy.Request]:
        s = self.selection
        if s.wants("changelog"):
            yield self.page("changelog", E.CHANGELOG, detail=False, priority=10)
        if s.wants("blog"):
            yield self.page("blog_index", E.BLOG_INDEX, detail=False, priority=10)   # -> blog sitemap -> pages
        if s.wants("help"):
            yield self.page("help_index", E.HELP_INDEX, detail=False, priority=10)
        if s.wants("case-studies"):
            yield self.page("case_studies_index", E.CASE_STUDIES_INDEX, detail=False, priority=10)
        if s.with_content and (s.wants("help") or s.wants("case-studies")):
            yield self.sitemap("creator_hub_sitemap", "creator-hub")
        if s.wants("enterprise-help"):
            yield self.page("enterprise_index", E.ENTERPRISE_INDEX, detail=False, priority=10)
            if s.with_content:
                yield self.sitemap("enterprise_sitemap", "enterprise")
        if s.wants("talents") and self.page_allowed("talent_posts"):
            yield self.feed("talent_posts", E.TALENT_POSTS)
        if s.wants("community") and self.page_allowed("recommended_posts"):
            yield self.feed("recommended_posts", E.RECOMMENDED_POSTS)

    def parse_api(self, response, **kw):
        """Convert non-JSON bodies, then run the framework's parse_api and apply the per-collection --max-items."""
        for x in self._convert_and_parse(response, **kw):
            if isinstance(x, scrapy.Item) and x.get("kind") in PRIMARY_KINDS:
                kind, ident = x["kind"], str(x.get(ID_FIELD_BY_KIND[x["kind"]]))
                mx = self.common.max_items
                if mx is not None and self._kept[kind] >= mx and (kind, ident) not in self._seen:
                    self.limit_hit(f"max_items={mx} reached for {kind}")
                    self._dropped.add(ident)
                    continue
                if (kind, ident) not in self._seen:
                    self._kept[kind] += 1
                    self._seen.add((kind, ident))
                    self._accepted.add(ident)
            elif isinstance(x, scrapy.Request) and x.meta.get("media") and x.meta.get("media_owner") in self._dropped:
                continue
            yield x

    def _cap_reached(self, kind: str) -> bool:
        mx = self.common.max_items
        return mx is not None and self._kept[kind] >= mx

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
            body: Any = {"format": fmt, "status": response.status,
                         "_non_json": raw[:500].decode("utf-8", "replace")}
        elif fmt == "html":
            body = extract_page(raw.decode("utf-8", "replace"), response.meta.get("path"),
                                response.meta.get("lastmod"))
            if not body.get("matches"):
                self.crawler.stats.inc_value("higgs/blog/pages_without_router_state")
        elif fmt == "xml":
            body = extract_sitemap(raw.decode("utf-8", "replace"))
        else:                                                 # yjs binary
            body = {"format": "yjs", "content_url": response.url,
                    "content_b64": base64.b64encode(raw).decode("ascii")}
        fake = TextResponse(url=response.url, status=response.status, body=json.dumps(body).encode("utf-8"),
                            encoding="utf-8", request=response.request)
        yield from super().parse_api(fake, **kw)

    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        ep, s = env.endpoint, self.selection
        if ep == "blog_index":
            posts, cats = index_post_slugs(env.body)
            self._blog_categories |= set(cats)
            self._blog_index_posts = posts
            self.totals["blog_posts_on_index"] = len(posts)
            yield self.sitemap("blog_sitemap", "blog")         # lastmod, authors, posts missing from the index
        elif ep == "blog_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["blog_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[:2] == ["blog", "author"]:
                    r = self.page("blog_author", path, lastmod=u.get("lastmod"), detail=False)
                elif len(parts) == 2 and parts[0] == "blog" and parts[1] not in self._blog_categories                         and s.with_content:
                    r = self.page("blog_page", path, lastmod=u.get("lastmod"))
                else:
                    r = None
                if r:
                    yield r
            if s.with_content:
                for slug in getattr(self, "_blog_index_posts", []):
                    r = self.page("blog_page", f"/blog/{slug}")
                    if r:
                        yield r
        elif ep == "help_index" and s.with_content:
            paths = help_index_paths(env.body)
            self.totals["help_articles_on_index"] = len(paths)
            for p in paths:
                r = self.page("help_article", p)
                if r:
                    yield r
        elif ep == "case_studies_index":
            slugs, cats = case_study_slugs(env.body)
            self._case_categories |= set(cats)
            self.totals["case_studies_on_index"] = len(slugs)
            if s.with_content:
                for slug in slugs:
                    r = self.page("case_study", f"/creator-hub/case-studies/{slug}")
                    if r:
                        yield r
        elif ep == "creator_hub_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["creator_hub_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                parts = path.strip("/").split("/")
                r = None
                if s.wants("help") and len(parts) == 4 and parts[:2] == ["creator-hub", "help-center"]:
                    r = self.page("help_article", path, lastmod=u.get("lastmod"))
                elif s.wants("case-studies") and len(parts) == 3 and parts[:2] == ["creator-hub", "case-studies"] \
                        and parts[2] not in self._case_categories:
                    r = self.page("case_study", path, lastmod=u.get("lastmod"))
                if r:
                    yield r
        elif ep == "enterprise_index" and s.with_content:
            paths = enterprise_index_paths(env.body)
            self.totals["enterprise_articles_on_index"] = len(paths)
            for p in paths:
                r = self.page("enterprise_article", p)
                if r:
                    yield r
        elif ep == "enterprise_sitemap":
            urls = sitemap_urls(env.body)
            self.totals["enterprise_sitemap_urls"] = len(urls)
            for u in urls:
                path = urlsplit(u["loc"]).path.rstrip("/")
                if path.strip("/").count("/") == 2 and path.startswith("/enterprise-help-center/"):
                    r = self.page("enterprise_article", path, lastmod=u.get("lastmod"))
                    if r:
                        yield r
        elif ep == "changelog":
            self.totals["changelog_entries"] = len(entities)
        elif ep in ("talent_posts", "recommended_posts"):
            yield from self._feed_follow(env, entities)

    def _feed_follow(self, env: Envelope, entities: list[dict]) -> Iterator[scrapy.Request]:
        ep = env.endpoint
        items = (env.body or {}).get("items") or []
        key = "talent_posts" if ep == "talent_posts" else "community_posts"
        self.totals[f"{key}_listed"] = (self.totals.get(f"{key}_listed") or 0) + len(items)
        if self.selection.with_content:
            for e in entities:
                if e.get("content_url") and e["post_id"] in self._accepted:
                    yield self.api_request("post_content", "", base=e["content_url"], priority=-1,
                                           headers={"Accept": "*/*"},
                                           meta={"params": {"post_id": e["post_id"]}, "fmt": "yjs"})
        nxt = (env.body or {}).get("next_cursor")
        if not nxt or not items:
            return
        if self._cap_reached("blog_talent_post" if ep == "talent_posts" else "blog_community_post"):
            return
        if not self.page_allowed(ep):
            return
        yield self.feed(ep, E.TALENT_POSTS if ep == "talent_posts" else E.RECOMMENDED_POSTS, cursor=nxt)
