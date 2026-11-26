"""CatalogSpider: fetches every selected catalog listing (+ pagination, motion samples/details, marketing presets)."""
from __future__ import annotations

from typing import Any, Iterator, Optional

import scrapy
from scrapy.exceptions import IgnoreRequest

from ...core.api_spider import BaseApiSpider
from ...raw import Envelope
from ...run.logging_setup import emit
from .endpoints import KIND_OF, PAGE_KIND, PRIMARY_KINDS, SHORT_OF, SOURCE_BY_ENDPOINT, Source, sources_for
from .parsers import next_params


class CatalogSpider(BaseApiSpider):
    name = "catalog"
    scraper_name = "catalog"
    primary_kinds = PRIMARY_KINDS

    # ------------------------------------------------------------ requests
    def _request(self, src: Source, params: Optional[dict] = None, *, path_id: Optional[str] = None,
                 extra_meta_params: Optional[dict] = None, listing: Optional[str] = None) -> Optional[scrapy.Request]:
        if not self.page_allowed(listing or src.endpoint):
            return None
        params = {k: str(v) for k, v in (params or {}).items() if v is not None}
        path = src.path.replace("{id}", path_id or "")
        meta_params = {**params, **(extra_meta_params or {})}
        return self.api_request(src.endpoint, path, params, auth="required" if src.login else False, base=src.base,
                                meta={"params": meta_params,
                                      "catalog": {"query": params, "path_id": path_id, "listing": listing,
                                                  "extra": extra_meta_params or {}}})

    def _first_params(self, src: Source) -> dict:
        p: dict[str, Any] = dict(src.fixed_params)
        if src.size_param:
            p[src.size_param] = self.page_size(src.default_size, src.max_size)
        if src.lang:
            p["lang"] = self.selection.lang
        return p

    def build_requests(self) -> Iterator[scrapy.Request]:
        kinds = self.selection.resolve_kinds(self.authed)
        self.kinds = kinds
        needs_motions = "motion" in kinds or "motion_sample" in kinds or self.selection.with_details
        wanted = {KIND_OF[k] for k in kinds} | ({KIND_OF["motion"]} if needs_motions else set())
        if "marketing_preset" in kinds:
            wanted.add(KIND_OF["marketing_category"])
        emit(self.logger, "info", "endpoint.started", f"catalog kinds: {', '.join(kinds)} "
             f"(session: {'yes' if self.authed else 'no'})", kinds=list(kinds), auth__session=self.authed)
        for kind in [KIND_OF[k] for k in KIND_OF if KIND_OF[k] in wanted]:
            for src in sources_for(kind):
                if src.kind in ("catalog_motion_sample", "catalog_marketing_preset") or "{id}" in src.path \
                        or src.follow_only:
                    continue                                  # scheduled from follow_up
                r = self._request(src, self._first_params(src))
                if r is not None:
                    yield r

    def on_error(self, failure):
        """Login-only requests skipped by AuthMiddleware (no session) are expected, not errors: keep the run
        'success' (the base errback would count them under higgs/request_errors -> 'partial')."""
        req = failure.request
        if failure.check(IgnoreRequest) and req.meta.get("auth") == "required":
            self.crawler.stats.inc_value(f"higgs/auth/skipped/{req.meta.get('endpoint')}")
            emit(self.logger, "info", "request.skipped", f"skipped login-only {req.meta.get('endpoint')}: "
                 f"{failure.value}", endpoint__name=req.meta.get("endpoint"), reason="no_session")
            return
        return super().on_error(failure)

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env: Envelope, entities: list[dict], response) -> Iterator[Any]:
        src = SOURCE_BY_ENDPOINT.get(env.endpoint)
        c = response.meta.get("catalog") or {}
        if src is None:
            return
        n_items = sum(1 for e in entities if e["kind"] not in (PAGE_KIND,))
        for e in entities:
            if e["kind"] == PAGE_KIND and e["first_page"] and src.kind != "catalog_motion_sample":
                key, t = SHORT_OF[src.kind], e.get("total")
                if key in self.totals and self.totals[key] is not None and t is not None:
                    self.totals[key] += t                     # several sources feed one kind
                elif key not in self.totals or t is None:
                    self.totals[key] = t
        # pagination
        raw_items = next((e["item_count"] for e in entities if e["kind"] == PAGE_KIND), n_items)
        nxt = next_params(src, env.body, c.get("query") or {}, raw_items)
        if nxt is not None:
            if src.kind in self.primary_kinds and self.budget_left() == 0:
                self.limit_hit(f"max_items={self.common.max_items} reached")
            else:
                r = self._request(src, nxt, path_id=c.get("path_id"), extra_meta_params=c.get("extra"),
                                  listing=c.get("listing"))
                if r is not None:
                    yield r
        # per-motion samples / details
        if src.kind == "catalog_motion":
            motions = [e for e in entities if e["kind"] == "catalog_motion"]
            if self.selection.samples or "motion_sample" in getattr(self, "kinds", []):
                s = SOURCE_BY_ENDPOINT["catalog_motion_samples"]
                for m in motions:
                    r = self._request(s, {"motion_id": m["id"], "size": self.page_size(s.default_size, s.max_size)},
                                      listing=s.endpoint)
                    if r is None:
                        break
                    yield r
            if self.selection.with_details:
                d = SOURCE_BY_ENDPOINT["catalog_motion_detail"]
                for m in motions:
                    r = self._request(d, path_id=m["id"], extra_meta_params={"motion_id": m["id"]},
                                      listing=d.endpoint)
                    if r is None:
                        break
                    yield r
        # chain presets: the show_hidden=true list strictly after the visible one (so visible rows win the dedup
        # and only the hidden-only rows keep is_hidden=True)
        if src.endpoint == "catalog_chain_presets" and self.selection.include_hidden:
            h = SOURCE_BY_ENDPOINT["catalog_chain_presets_hidden"]
            r = self._request(h, self._first_params(h))
            if r is not None:
                yield r
        # marketing presets per category
        if src.kind == "catalog_marketing_category" and "marketing_preset" in getattr(self, "kinds", []):
            p = SOURCE_BY_ENDPOINT["catalog_marketing_presets"]
            for cat in [e for e in entities if e["kind"] == "catalog_marketing_category"]:
                r = self._request(p, self._first_params(p), path_id=cat["id"],
                                  extra_meta_params={"category_id": cat["id"]}, listing=f"{p.endpoint}:{cat['id']}")
                if r is not None:
                    yield r

