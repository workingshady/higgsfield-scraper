"""ProjectsSpider: community project publications, recommended feeds, contest entries, contests (+detail,
+submissions) and (login-only) original series."""
from __future__ import annotations

import dataclasses
from typing import Any, Iterator
from urllib.parse import quote

from ...core.api_spider import BaseApiSpider
from . import endpoints as ep
from .parsers import _listing_name

def _path_params(**kw: Any) -> dict:
    """Record path parameters in the envelope params (URL unchanged) so raw/ file names stay unique per id
    (Envelope.filename is built from endpoint + params only)."""
    return {"params": {k: str(v) for k, v in kw.items() if v is not None}}


LISTINGS = ("projects_publications", "projects_recommended", "projects_contest_entries")


class ProjectsSpider(BaseApiSpider):
    name = "projects"
    scraper_name = "projects"
    primary_kinds = ("projects_publication", "projects_contest")

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._detail_requested: set[str] = set()
        self._contest_followed: set[str] = set()
        self._cursors_seen: set[tuple[str, str]] = set()
        self._subs_seen: dict[str, int] = {}
        self._contests_counted: dict[str, int] = {}
        # Drop repeats before they are counted against --max-items (the same publication shows up in several
        # listings; its listing entry is still emitted). The pipeline would drop them anyway, but after counting.
        base_keep, ids, seen = self.sdef.keep, self.sdef.id_field_by_kind, set()

        def keep_first(e: dict, sel: Any) -> bool:
            if not base_keep(e, sel):
                return False
            f = ids.get(e["kind"])
            if f and e.get(f) and e["kind"] != "projects_listing_entry":
                key = (e["kind"], str(e[f]))
                if key in seen:
                    return False
                seen.add(key)
            return True
        self.sdef = dataclasses.replace(self.sdef, keep=keep_first)

    # ------------------------------------------------------------ first requests
    def build_requests(self) -> Iterator:
        sel = self.selection
        if sel.wants("contests"):
            for ctype in sel.contest_types:
                yield self._contests_page(ctype, None)
        if sel.wants("publications") or sel.wants("recommended"):
            yield self.api_request("projects_categories", ep.CATEGORIES, priority=5)
        if sel.wants("publications"):
            for cat in sel.categories or (None,):
                yield self._publications_page({"category": cat}, None)
        if sel.wants("recommended"):
            for scope in sel.scopes:
                yield self._recommended_page(scope, None)
        if sel.wants("entries"):
            for key in sel.entry_keys:
                yield self._entries_page(key, None)
        if sel.wants("series"):
            if self.authed:
                yield self.api_request("projects_series", ep.SERIES,
                                       {"limit": self.page_size(ep.MAX_SERIES_LIMIT, ep.MAX_SERIES_LIMIT)},
                                       auth="required")
            else:
                self.logger.warning("original series (/series) are login-only: skipped (no session configured)")

    # ------------------------------------------------------------ request builders
    def _publications_page(self, base: dict, cursor):
        params = {"limit": self.page_size(ep.MAX_PUBLICATIONS_LIMIT, ep.MAX_PUBLICATIONS_LIMIT),
                  "category": base.get("category"), "featured": "true" if self.selection.featured else None,
                  "cursor": cursor}
        return self.api_request("projects_publications", ep.PUBLICATIONS, params)

    def _recommended_page(self, scope, cursor):
        return self.api_request("projects_recommended", ep.RECOMMENDED,
                                {"scope": scope, "limit": self.page_size(ep.MAX_RECOMMENDED_LIMIT,
                                                                         ep.MAX_RECOMMENDED_LIMIT), "cursor": cursor})

    def _entries_page(self, key, cursor):
        return self.api_request("projects_contest_entries", ep.ENTRIES,
                                {"tab": self.selection.entry_tab, "contest_key": key,
                                 "size": self.page_size(ep.MAX_ENTRIES_SIZE, ep.MAX_ENTRIES_SIZE), "cursor": cursor})

    def _contests_page(self, ctype, cursor):
        sel = self.selection
        statuses = list(sel.statuses) if sel.contest_status != "all" else None
        return self.api_request("projects_contests", ep.CONTESTS,
                                {"contest_type": ctype, "status": statuses,
                                 "size": self.page_size(ep.MAX_CONTESTS_SIZE, ep.MAX_CONTESTS_SIZE), "cursor": cursor},
                                priority=10)

    def _submissions_page(self, contest_id: str, offset: int):
        params = {"limit": self._submissions_limit(contest_id), "offset": offset or None,
                  "ordering": self.selection.submission_ordering}
        return self.api_request("projects_contest_submissions",
                                ep.CONTEST_SUBMISSIONS.format(id=quote(contest_id, safe="")), params, priority=1,
                                meta=_path_params(contest_id=contest_id, **params))

    def _submissions_limit(self, contest_id: str) -> int:
        n = self.page_size(ep.MAX_SUBMISSIONS_LIMIT, ep.MAX_SUBMISSIONS_LIMIT)
        ms = self.selection.max_submissions
        if ms is not None:
            n = max(1, min(n, ms - self._subs_seen.get(contest_id, 0)))
        return n

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env, entities, response) -> Iterator:
        body = env.body if isinstance(env.body, dict) else {}
        if env.endpoint in LISTINGS:
            yield from self._follow_listing(env, body, entities)
        elif env.endpoint == "projects_contests":
            yield from self._follow_contests(env, body, entities)
        elif env.endpoint == "projects_contest_submissions":
            yield from self._follow_submissions(env, body, entities)
        elif env.endpoint == "projects_series" and self.selection.with_details:
            for e in entities:
                if e["kind"] == "projects_series" and e.get("slug"):
                    yield self.api_request("projects_series_detail",
                                           ep.SERIES_DETAIL.format(slug=quote(e["slug"], safe="")), auth="required",
                                           meta=_path_params(slug=e["slug"]))

    def _follow_listing(self, env, body: dict, entities: list[dict]) -> Iterator:
        listing = _listing_name(env)
        if "total" in body:
            self.totals[listing] = body.get("total")
        if self.selection.with_details:
            for e in entities:
                pid = e.get("publication_id")
                if e["kind"] == "projects_publication" and pid not in self._detail_requested:
                    self._detail_requested.add(pid)
                    yield self.api_request("projects_publication_detail",
                                           ep.PUBLICATION_DETAIL.format(id=quote(pid, safe="")), priority=2,
                                           meta=_path_params(publication_id=pid))
        nxt = body.get("next_cursor")
        if not nxt or not body.get("items"):
            return
        if self.budget_left() == 0:
            self.limit_hit(f"max_items={self.common.max_items} reached")
            return
        if (listing, str(nxt)) in self._cursors_seen:
            self.logger.warning("%s: cursor %s repeated, stopping", listing, nxt)
            return
        self._cursors_seen.add((listing, str(nxt)))
        if not self.page_allowed(listing):
            return
        p = env.params or {}
        if env.endpoint == "projects_publications":
            yield self._publications_page({"category": p.get("category")}, nxt)
        elif env.endpoint == "projects_recommended":
            yield self._recommended_page(p.get("scope"), nxt)
        else:
            yield self._entries_page(p.get("contest_key"), nxt)

    def _follow_contests(self, env, body: dict, entities: list[dict]) -> Iterator:
        sel = self.selection
        ctype = (env.params or {}).get("contest_type") or "global"
        self._contests_counted[ctype] = self._contests_counted.get(ctype, 0) + len(body.get("items") or [])
        self.totals[f"contests:{ctype}"] = self._contests_counted[ctype]
        for e in entities:
            if e["kind"] != "projects_contest" or e["contest_id"] in self._contest_followed:
                continue
            cid = e["contest_id"]
            self._contest_followed.add(cid)
            self.totals[f"submissions:{e.get('slug') or cid}"] = e.get("submissions_count")
            if sel.with_details:
                yield self.api_request("projects_contest_detail",
                                       ep.CONTEST_DETAIL.format(id=quote(cid, safe="")), priority=9,
                                       meta=_path_params(contest_id=cid))
            if sel.with_submissions:
                yield self._submissions_page(cid, 0)
        if body.get("has_more") and body.get("cursor") is not None and self.page_allowed(f"contests:{ctype}"):
            yield self._contests_page(ctype, body["cursor"])

    def _follow_submissions(self, env, body: dict, entities: list[dict]) -> Iterator:
        items = body.get("items") or []
        cid = env.url.split("/contests/", 1)[1].split("/", 1)[0]
        self._subs_seen[cid] = self._subs_seen.get(cid, 0) + len(items)
        if not body.get("has_more") or not items:
            return
        ms = self.selection.max_submissions
        if ms is not None and self._subs_seen[cid] >= ms:
            self.limit_hit(f"max_submissions={ms} reached for contest {cid}")
            return
        if not self.page_allowed(f"submissions:{cid}"):
            return
        offset = int((env.params or {}).get("offset") or 0) + len(items)
        yield self._submissions_page(cid, offset)
