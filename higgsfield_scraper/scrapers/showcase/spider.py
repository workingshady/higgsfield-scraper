"""ShowcaseSpider: public showcase / example content (see docs/scrapers/showcase.md for the HTTP flow).

GET only. Public requests never carry a token (`auth=False`); only the login-only `season` source uses
`auth="required"` (skipped cleanly without a session, never scheduled with `--auth off`).
Non-JSON bodies (HTML, XML sitemap, JS chunks, llms-full.txt) are converted to small JSON bodies BEFORE they are
archived, so `normalize` re-parses exactly what the parsers saw.
"""
from __future__ import annotations

import json
import re
from collections import Counter, deque
from typing import Any, Iterator, Optional

import scrapy
from scrapy.exceptions import IgnoreRequest
from scrapy.http import TextResponse

from ...core.api_spider import HANDLED, BaseApiSpider
from ...raw import Envelope
from ...run.logging_setup import emit
from . import parsers
from .endpoints import (ASSETS, CANVAS, CANVAS_PAGE_SIZE, CMS, CMS_LANGS, DOCS, EXPLORE_PAGE_SIZE, GW, API,
                        MAX_CHUNK_PROBES, PRIMARY_KINDS, PROPERTY_PRESET_MARKER, PROPERTY_ROUTE, SITE, CMS_PAGE_SIZE)
from .schemas import ID_FIELD_BY_KIND

HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
TEXT_HEADERS = {"Accept": "text/plain,text/markdown,*/*;q=0.8"}
JS_HEADERS = {"Accept": "*/*"}
CHUNK_RE = re.compile(r"/tanstack/assets/([A-Za-z0-9_-]+\.js)")
IMPORT_RE = re.compile(r"""(?:from|import)\s*"\./([A-Za-z0-9_-]+\.js)\"""")
L10N_RE = re.compile(r"https://l10n\.higgsfield\.ai/[^\"'\s]+\.json")
PARENT_OF = {"showcase_explore_variant": ("showcase_explore_item", "item_id"),
             "showcase_editing_room_render": ("showcase_editing_room_project", "project_id")}
NATURAL = {"showcase_explore_item": "item_id", "showcase_editing_room_project": "project_id"}


def route_chunk_of(js: str) -> Optional[str]:
    """The lazy route chunk of `/_private/property-studio/` in the router-tree chunk:
    ``new globalThis.URL(`./X.js`,import.meta.url).href),Y=P(`/_private/property-studio/`)``."""
    i = js.find(f"(`{PROPERTY_ROUTE}`)")
    if i < 0:
        return None
    found = re.findall(r"new globalThis\.URL\(`\./([A-Za-z0-9_-]+\.js)`", js[max(0, i - 600):i])
    return found[-1] if found else None


def l10n_titles(body: Any, ids: set[str]) -> dict[str, str]:
    out = {}
    if not isinstance(body, dict):
        return out
    for k in ids:
        v = body.get(k)
        if isinstance(v, list):
            v = "".join(x for x in v if isinstance(x, str))
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


class ShowcaseSpider(BaseApiSpider):
    name = "showcase"
    scraper_name = "showcase"
    primary_kinds = ()                 # --max-items is applied PER KIND below (one source must not starve the rest)

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._kept: Counter = Counter()
        self._seen: set[tuple[str, str]] = set()
        self._dropped: dict[str, set[str]] = {}
        self._feed_pages: Counter = Counter()
        self._effect_queue: deque = deque()
        self._ps: dict[str, Any] = {"probed": set(), "queue": deque(), "l10n": deque(), "rows": None, "chunk": None,
                                    "titles": {}, "route": False}
        self._openapi: Any = None
        self.whats: list[str] = []

    # ------------------------------------------------------------ request helpers
    @property
    def lang(self) -> str:
        return self.selection.lang

    @property
    def cms_lang(self) -> str:
        return self.lang if self.lang in CMS_LANGS else "en"

    def req(self, endpoint: str, base: str, path: str, params: Optional[dict] = None, *, fmt: Optional[str] = None,
            labels: Optional[dict] = None, headers: Optional[dict] = None, auth: Any = False,
            meta: Optional[dict] = None, priority: int = 0) -> scrapy.Request:
        m = dict(meta or {})
        if fmt:
            m["fmt"] = fmt
        return self.api_request(endpoint, path, params, base=base, auth=auth, labels=labels, headers=headers,
                                meta=m, priority=priority)

    def _cap_reached(self, kind: str) -> bool:
        mx = self.common.max_items
        return mx is not None and self._kept[kind] >= mx

    # ------------------------------------------------------------ first requests
    def build_requests(self) -> Iterator[scrapy.Request]:
        s = self.selection
        self.whats = s.resolve()
        L = self.cms_lang
        for w in self.whats:
            if w == "canvas_templates":
                yield self.req("showcase_canvas_templates", CANVAS, "/api/templates")
            elif w == "editing_room_examples":
                yield self.req("showcase_videoshop_examples", CMS, "/videoshop-examples", {"lang": L})
                yield self.req("showcase_videoshop_project_examples", API, "/videoshop/project-examples")
            elif w == "property_studio_examples":
                yield self.req("showcase_property_studio_page", SITE, "/property-studio", fmt="html",
                               headers=HTML_HEADERS, labels={"lang": self.lang})
            elif w == "explore_categories":
                yield self.req("showcase_explore_categories", CMS, "/higgsfield-multiplier/video-explore/v2/categories",
                               {"lang": L})
                for src in s.explore_sources:
                    for sort in (["trending"] if src == "higgsfield" else s.explore_sorts()):
                        r = self._explore(src, sort, 1)
                        if r is not None:
                            yield r
            elif w == "effect_examples":
                if s.effects:
                    self._effect_queue.extend(s.effects)
                    yield from self._next_effects(2)
                else:
                    yield self.req("showcase_effects_sitemap", SITE, "/effects/sitemap.xml", fmt="xml",
                                   headers={"Accept": "application/xml,text/xml,*/*"})
            elif w == "api_models":
                yield self.req("showcase_api_openapi", DOCS, "/docs/openapi.json")
            elif w == "season":
                if self.common.auth != "off":
                    yield self.req("showcase_season", GW, "/fnf-score/v1/season", auth="required")
                else:
                    self.limit_hit("season skipped: --auth off (login-only source)")
            elif w == "cinema_controls":
                yield self.req("showcase_cinema_controls", CMS, "/cinema-studio-4-0/creative-controls", {"lang": L})
            elif w == "faceless_showcases":
                yield self.req("showcase_faceless_showcases", CMS, "/youtube-faceless-showcases",
                               {"lang": L, "size": CMS_PAGE_SIZE})
            elif w == "intone_examples":
                yield self.req("showcase_intone_explore", CMS, "/intone/explore",
                               {"lang": L, "size": CMS_PAGE_SIZE, "cursor": 1})
            elif w == "seedance_presets":
                yield self.req("showcase_seedance_presets", CMS, "/seedance-2-0", {"lang": L})
            elif w == "motion_control_presets":
                yield self.req("showcase_motion_control_presets", CMS, "/kling-motion-control-presets", {"lang": L})

    def _explore(self, source: str, sort: str, cursor: Any, category: Optional[str] = None) -> Optional[scrapy.Request]:
        key = f"explore:{source}:{sort}:{category or '-'}"
        mx = self.selection.explore_pages
        if mx and self._feed_pages[key] >= mx:
            self.limit_hit(f"explore_pages={mx} reached for {key}")
            return None
        if not self.page_allowed(key):
            return None
        self._feed_pages[key] += 1
        p: dict[str, Any] = {"lang": self.cms_lang, "source": source, "size": EXPLORE_PAGE_SIZE, "cursor": cursor}
        if source == "community":
            p["sort"] = sort
            if sort == "trending":
                p["view"] = "v2"
        if category:
            p["category"] = category
        return self.req("showcase_explore_feed", CMS, "/higgsfield-multiplier/video-explore/v2", p,
                        labels={"page": self._feed_pages[key], "feed": f"{source}-{sort}"},
                        meta={"explore": {"source": source, "sort": sort, "category": category}})

    def _next_effects(self, n: int = 1) -> Iterator[scrapy.Request]:
        for _ in range(n):
            if not self._effect_queue or self._cap_reached("showcase_effect_sample"):
                if self._effect_queue:
                    self.limit_hit(f"max_items={self.common.max_items} reached for showcase_effect_sample")
                return
            if not self.page_allowed("effect_pages"):
                return
            slug = self._effect_queue.popleft()
            yield self.req("showcase_effect_page", SITE, f"/effects/examples/{slug}", fmt="effect",
                           headers=HTML_HEADERS, labels={"slug": slug})

    def _chunk(self, name: str) -> Optional[scrapy.Request]:
        if name in self._ps["probed"] or len(self._ps["probed"]) >= MAX_CHUNK_PROBES:
            if len(self._ps["probed"]) >= MAX_CHUNK_PROBES:
                self.limit_hit(f"property studio: preset table not found in {MAX_CHUNK_PROBES} chunks")
            return None
        self._ps["probed"].add(name)
        return self.req("showcase_property_studio_chunk", ASSETS, f"/tanstack/assets/{name}", fmt="chunk",
                        headers=JS_HEADERS, labels={"chunk": name})

    # ------------------------------------------------------------ body conversion (before archiving)
    def convert_body(self, fmt: str, text: str, response) -> Any:
        if fmt == "html":                                   # property studio page: chunk + l10n discovery
            return {"chunks": list(dict.fromkeys(CHUNK_RE.findall(text))),
                    "l10n": list(dict.fromkeys(L10N_RE.findall(text)))}
        if fmt == "chunk":
            name = response.meta["params"].get("chunk")
            rows = parsers.extract_property_rows(text) if PROPERTY_PRESET_MARKER in text else []
            return {"chunk": name, "route_chunk": route_chunk_of(text), "imports": list(dict.fromkeys(
                IMPORT_RE.findall(text[:20000]))), "rows": rows, "size": len(text)}
        if fmt == "l10n":
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            ids = {r[2] for r in self._ps["rows"] or []}
            return {"titles": l10n_titles(data, ids), "entries": len(data) if isinstance(data, dict) else None}
        if fmt == "xml":
            return {"slugs": parsers.effect_slugs(text)}
        if fmt == "effect":
            from ..blog.tsr import router_matches          # seroval SSR state parser (read-only reuse)
            slug = response.meta["params"].get("slug")
            try:
                matches = router_matches(text)
            except Exception as e:                          # keep the run going; recorded in the body
                return {"slug": slug, "loader": None, "error": f"{type(e).__name__}: {e}"[:300]}
            m = next((x for x in matches if "$presetSlug" in str(x.get("i") or "")), None)
            loader = dict((m or {}).get("l") or {})
            if isinstance(loader.get("preset"), dict):
                loader["preset"] = {k: v for k, v in loader["preset"].items() if k != "same_categories_presets"}
            if not self.selection.with_profiles:            # archive: no names/avatars (fullname/avatarUrl are not
                for smp in ((loader.get("initialSamples") or {}).get("items") or []):   # in core PERSONAL_KEYS)
                    u = (smp.get("job") or {}).get("user")
                    if isinstance(u, dict):
                        smp["job"]["user"] = {"id_hash": parsers.creator_key(u.get("id"))}
            return {"slug": slug, "loader": {k: loader.get(k) for k in ("preset", "initialSamples", "sample")}}
        if fmt == "text":
            return {"text": text, "openapi": self._openapi}
        return {"_non_json": text[:2000]}

    def parse_api(self, response, **kw):
        for x in self._convert_and_parse(response, **kw):
            if isinstance(x, scrapy.Item) and x.get("kind") in PRIMARY_KINDS + tuple(PARENT_OF):
                kind = x["kind"]
                if kind in PARENT_OF:                       # child of a parent dropped by the cap
                    pk, field = PARENT_OF[kind]
                    if str(x.get(field)) in self._dropped.get(pk, set()):
                        continue
                    yield x
                    continue
                ident = str(x.get(ID_FIELD_BY_KIND[kind]))
                if (kind, ident) not in self._seen:
                    if self._cap_reached(kind):
                        self.limit_hit(f"max_items={self.common.max_items} reached for {kind}")
                        if kind in NATURAL:
                            self._dropped.setdefault(kind, set()).add(str(x.get(NATURAL[kind])))
                        continue
                    self._kept[kind] += 1
                    self._seen.add((kind, ident))
            yield x

    def _convert_and_parse(self, response, **kw):
        fmt = response.meta.get("fmt")
        ep = response.meta.get("endpoint")
        if fmt is None:
            yield from super().parse_api(response, **kw)
            if ep == "showcase_api_openapi" and response.status != 200:
                yield from self._docs_request()
            return
        raw = response.body
        if response.status != 200:                            # bot protection / HTTP errors: framework handling
            yield from super().parse_api(response, **kw)
            yield from self._continue_chain(ep, response)     # keep sequential chains going past a dead link
            return
        body = self.convert_body(fmt, raw.decode("utf-8", "replace"), response)
        yield from super().parse_api(self._fake(response, body), **kw)

    def _continue_chain(self, ep: str, response) -> Iterator[Any]:
        if ep == "showcase_l10n":
            yield from self._l10n_next(response)
        elif ep == "showcase_property_studio_chunk":
            yield from self._ps_next()
        elif ep == "showcase_effect_page":
            yield from self._next_effects(1)

    @staticmethod
    def _fake(response, body: Any, request: Optional[scrapy.Request] = None) -> TextResponse:
        return TextResponse(url=(request or response.request).url, status=200,
                            body=json.dumps(body, ensure_ascii=False).encode("utf-8"), encoding="utf-8",
                            request=request or response.request)

    def _docs_request(self) -> Iterator[scrapy.Request]:
        yield self.req("showcase_api_docs", DOCS, "/llms-full.txt", fmt="text", headers=TEXT_HEADERS)

    def on_error(self, failure):
        req = failure.request
        ep = req.meta.get("endpoint")
        if failure.check(IgnoreRequest) and req.meta.get("auth") == "required":
            self.crawler.stats.inc_value(f"higgs/auth/skipped/{ep}")
            emit(self.logger, "info", "request.skipped", f"skipped login-only {ep}: {failure.value}",
                 endpoint__name=ep, reason="no_session")
            return None
        out = super().on_error(failure)
        if ep == "showcase_api_openapi":                    # docs still worth fetching without the openapi
            return list(self._docs_request())
        return out

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        ep, b = env.endpoint, env.body
        if ep == "showcase_canvas_templates" and isinstance(b, dict):
            self.totals.setdefault("canvas_templates", b.get("total"))
            nxt = int(b.get("offset") or 0) + len(b.get("items") or [])
            if b.get("items") and b.get("total") is not None and nxt < int(b["total"]) \
                    and not self._cap_reached("showcase_canvas_template") and self.page_allowed(ep):
                yield self.req(ep, CANVAS, "/api/templates", {"limit": CANVAS_PAGE_SIZE, "offset": nxt})
        elif ep == "showcase_explore_categories" and isinstance(b, dict):
            cats = [c.get("category") for c in b.get("categories") or [] if c.get("category")]
            want = self.selection.explore_categories
            if want and "community" in self.selection.explore_sources:
                for c in cats if "all" in want else [c for c in cats if c in want]:
                    r = self._explore("community", "new", 1, c)
                    if r is not None:
                        yield r
        elif ep == "showcase_explore_feed" and isinstance(b, dict):
            ex = response.meta.get("explore") or {}
            key = f"explore_{ex.get('source')}_{ex.get('sort')}" + (f"_{ex['category']}" if ex.get("category") else "")
            if b.get("total") is not None:
                self.totals.setdefault(key, b.get("total"))
            cur = b.get("cursor")
            if b.get("items") and cur not in (None, "") and not self._cap_reached("showcase_explore_item"):
                r = self._explore(ex.get("source"), ex.get("sort"), cur, ex.get("category"))
                if r is not None:
                    yield r
            elif self._cap_reached("showcase_explore_item"):
                self.limit_hit(f"max_items={self.common.max_items} reached for showcase_explore_item")
        elif ep == "showcase_effects_sitemap" and isinstance(b, dict):
            slugs = b.get("slugs") or []
            self.totals["effect_pages"] = len(slugs)
            self._effect_queue.extend(slugs)
            yield from self._next_effects(2)
        elif ep == "showcase_effect_page":
            yield from self._next_effects(1)
        elif ep in ("showcase_faceless_showcases", "showcase_intone_explore") and isinstance(b, dict):
            self.totals.setdefault(ep.replace("showcase_", ""), b.get("total"))
            cur = b.get("cursor")
            if b.get("items") and cur not in (None, "") and self.page_allowed(ep):
                path = "/youtube-faceless-showcases" if ep == "showcase_faceless_showcases" else "/intone/explore"
                yield self.req(ep, CMS, path, {"lang": self.cms_lang, "size": CMS_PAGE_SIZE, "cursor": cur})
        elif ep == "showcase_api_openapi":
            self._openapi = b if isinstance(b, dict) else None
            yield from self._docs_request()
        elif ep == "showcase_api_docs":
            self.totals["api_models"] = len(entities)
        elif ep == "showcase_property_studio_page" and isinstance(b, dict):
            self._ps["l10n"].extend(self._l10n_order(b.get("l10n") or []))
            self._ps["queue"].extend(b.get("chunks") or [])
            yield from self._ps_next()
        elif ep == "showcase_property_studio_chunk" and isinstance(b, dict):
            if b.get("rows"):
                self._ps["rows"], self._ps["chunk"] = b["rows"], b.get("chunk")
                self.totals["property_studio_presets"] = len(b["rows"])
                yield from self._l10n_next(response)
                return
            if b.get("route_chunk") and not self._ps["route"]:
                self._ps["route"] = True                     # route chunk -> probe ITS imports next
                self._ps["queue"] = deque([b["route_chunk"]])
            elif self._ps["route"] and b.get("imports"):
                self._ps["queue"].extendleft(reversed([i for i in b["imports"] if i not in self._ps["probed"]]))
            yield from self._ps_next()
        elif ep == "showcase_l10n" and isinstance(b, dict):
            self._ps["titles"].update(b.get("titles") or {})
            yield from self._l10n_next(response)

    def _l10n_order(self, urls: list[str]) -> list[str]:
        lang = self.lang
        routes = [u for u in urls if f"/routes/{lang}/" in u and "/root." not in u]
        full = [u for u in urls if re.search(rf"/{lang}\.[0-9a-f]+\.json$", u)]
        return routes + full

    def _ps_next(self) -> Iterator[scrapy.Request]:
        while self._ps["queue"]:
            r = self._chunk(self._ps["queue"].popleft())
            if r is not None:
                yield r
                return

    def _l10n_next(self, response) -> Iterator[Any]:
        rows = self._ps["rows"] or []
        missing = {r[2] for r in rows} - set(self._ps["titles"])
        if missing and self._ps["l10n"]:
            u = self._ps["l10n"].popleft()
            yield scrapy.Request(u, callback=self.parse_api, errback=self._l10n_error, dont_filter=True,
                                 headers={"Accept": "application/json"},
                                 meta={"endpoint": "showcase_l10n", "fmt": "l10n", "auth": False,
                                       "params": {"file": u.rsplit("/", 1)[-1], "lang": self.lang},
                                       "handle_httpstatus_list": HANDLED})
            return
        chunk = self._ps["chunk"] or "unknown.js"
        req = scrapy.Request(f"{ASSETS}/tanstack/assets/{chunk}", dont_filter=True,
                             meta={"endpoint": "showcase_property_studio_presets", "auth": False,
                                   "params": {"chunk": chunk, "lang": self.lang}})
        body = {"chunk": chunk, "lang": self.lang, "rows": rows, "titles": dict(self._ps["titles"])}
        yield from self.parse_api(self._fake(response, body, req))

    def _l10n_error(self, failure):
        self.on_error(failure)
        return list(self._l10n_next(None))
