"""ProjectsSpider: community project publications, recommended feeds, contest entries, contests (+detail,
+submissions) and original series (legacy login-only fnf path, or the public fnf-series service with
--public-series)."""
from __future__ import annotations

import base64
import dataclasses
import json
from typing import Any, Iterator, Optional
from urllib.parse import quote

from scrapy.http import TextResponse

from ...core.api_spider import BaseApiSpider
from ...run.logging_setup import emit
from . import endpoints as ep
from .options import user_key
from .parsers import _listing_name

def _path_params(**kw: Any) -> dict:
    """Record path parameters in the envelope params (URL unchanged) so raw/ file names stay unique per id
    (Envelope.filename is built from endpoint + params only)."""
    return {"params": {k: str(v) for k, v in kw.items() if v is not None}}


LISTINGS = ("projects_publications", "projects_recommended", "projects_contest_entries")


def _blank_keys(obj: Any, keys: frozenset) -> Any:
    if isinstance(obj, dict):
        return {k: ("[redacted]" if k in keys and obj[k] not in (None, "") else _blank_keys(v, keys))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_blank_keys(v, keys) for v in obj]
    return obj


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
        # nested project data (--with-project-*, --contest, --users)
        self._nested_done: set[str] = set()
        self._root_folder: dict[str, str] = {}          # publication id -> root_folder_id seen in a listing
        self._folders_requested: set[str] = set()
        self._items_seen: dict[str, int] = {}
        self._replies_requested: set[str] = set()
        self._contest_listings: dict[str, int] = {}     # entries listings started by --contest -> items seen
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
        if sel.wants("contests") and sel.contests:          # --contest <slug>: by slug, not the listing
            for slug in sel.contests:
                yield self.api_request("projects_contest_by_slug", ep.CONTEST_BY_SLUG.format(slug=quote(slug, safe="")),
                                       priority=10, labels={"slug": slug})
        elif sel.wants("contests"):
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
            if sel.public_series:
                limit = self.page_size(ep.MAX_SERIES_LIMIT, ep.MAX_SERIES_LIMIT)
                if self.common.max_items is not None:          # one page, no cursor: cap via limit (own budget)
                    limit = max(1, min(limit, self.common.max_items))
                yield self.api_request("projects_series_public", ep.SERIES, {"limit": limit}, base=ep.SERIES_BASE)
            elif self.authed:
                yield self.api_request("projects_series", ep.SERIES,
                                       {"limit": self.page_size(ep.MAX_SERIES_LIMIT, ep.MAX_SERIES_LIMIT)},
                                       auth="required")
            else:
                emit(self.logger, "warning", "request.skipped",
                     "original series (/series) are login-only: skipped (no session configured)",
                     endpoint__name="series", reason="no_session")
        if sel.wants("user-projects"):
            for handle in sel.users:
                if handle.startswith("key:"):                  # a redacted manifest: the handle is not known
                    emit(self.logger, "warning", "request.skipped", "--users entry is a pseudonymous key: skipped",
                         endpoint__name="projects_user_publications", reason="no_handle")
                    continue
                yield self._user_page(handle, None)

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

    def _entries_page(self, key, cursor, tab: Optional[str] = None):
        size = self.page_size(ep.MAX_ENTRIES_SIZE, ep.MAX_ENTRIES_SIZE)
        tab = tab or self.selection.entry_tab
        listing = f"entries:{key}:{tab}"
        if listing in self._contest_listings and self.selection.max_submissions is not None:   # --contest mode
            size = max(1, min(size, self.selection.max_submissions - self._contest_listings[listing]))
        return self.api_request("projects_contest_entries", ep.ENTRIES,
                                {"tab": tab, "contest_key": key, "size": size, "cursor": cursor})

    def _user_page(self, handle: str, cursor):
        return self.api_request("projects_user_publications",
                                ep.USER_PUBLICATIONS.format(username=quote(handle, safe="")),
                                {"publication_type": "project", "limit": self.page_size(
                                    ep.MAX_USER_PUBLICATIONS_LIMIT, ep.MAX_USER_PUBLICATIONS_LIMIT), "cursor": cursor},
                                labels={"user_key": user_key(handle)}, meta={"handle": handle})

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
        elif env.endpoint == "projects_contest_by_slug":
            yield from self._follow_contest_by_slug(env, body, entities)
        elif env.endpoint == "projects_user_publications":
            yield from self._follow_user(env, body, entities, response)
        elif env.endpoint == "projects_publication_detail" and self.selection.nested:
            yield from self._nested_requests(body)
        elif env.endpoint == "projects_folder_children":
            yield from self._follow_children(env, body)
        elif env.endpoint == "projects_folder_items":
            yield from self._follow_items(env, body)
        elif env.endpoint == "projects_comments":
            yield from self._follow_comments(env, body)
        elif env.endpoint == "projects_series_public" and self.selection.with_details:
            for e in entities:
                if e["kind"] == "projects_series" and e.get("slug"):
                    yield self.api_request("projects_series_public_detail",
                                           ep.SERIES_DETAIL.format(slug=quote(e["slug"], safe="")),
                                           base=ep.SERIES_BASE, meta=_path_params(slug=e["slug"]))
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
        if self.selection.with_details or self.selection.nested:
            for e in entities:
                pid = e.get("publication_id")
                if e["kind"] == "projects_publication":
                    if e.get("root_folder_id"):
                        self._root_folder.setdefault(pid, e["root_folder_id"])
                    yield from self._detail_request(pid)
        nxt = body.get("next_cursor")
        if not nxt or not body.get("items"):
            return
        if listing in self._contest_listings:                 # --contest: cap entries per tab by --max-submissions
            self._contest_listings[listing] += len(body.get("items") or [])
            ms = self.selection.max_submissions
            if ms is not None and self._contest_listings[listing] >= ms:
                self.limit_hit(f"max_submissions={ms} reached for {listing}")
                return
        if self.budget_left() == 0:
            self.limit_hit(f"max_items={self.common.max_items} reached")
            return
        if (listing, str(nxt)) in self._cursors_seen:
            emit(self.logger, "warning", "listing.cursor_repeated", f"{listing}: cursor {nxt} repeated, stopping",
                 listing=listing, cursor=str(nxt))
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
            yield self._entries_page(p.get("contest_key"), nxt, tab=p.get("tab"))

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
        if self.selection.nested:                             # contest -> submission -> project (publication)
            # from the body, not the kept entities: a contest detail's winners are emitted first, so their rows on
            # this page are dropped as repeats but must still be followed
            for it in items:
                pub = it.get("publication") if isinstance(it, dict) and isinstance(it.get("publication"), dict) else {}
                yield from self._detail_request(pub.get("publication_id"))
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

    # ------------------------------------------------------------ --contest / --users
    def _follow_contest_by_slug(self, env, body: dict, entities: list[dict]) -> Iterator:
        sel = self.selection
        for e in entities:
            if e["kind"] != "projects_contest_detail" or e["contest_id"] in self._contest_followed:
                continue
            cid = e["contest_id"]
            self._contest_followed.add(cid)
            self.totals[f"submissions:{e.get('slug') or cid}"] = e.get("submissions_count")
            if not sel.with_submissions:
                continue
            yield self._submissions_page(cid, 0)
            key = ep.KEY_BY_CONTEST_SLUG.get(e.get("slug") or "")
            if key:                                           # talent / festival: entries tabs of the contest page
                for tab in sel.tabs_for_contest:
                    listing = f"entries:{key}:{tab}"
                    if listing not in self._contest_listings:     # first page is free, like every listing
                        self._contest_listings[listing] = 0
                        yield self._entries_page(key, None, tab=tab)

    def _follow_user(self, env, body: dict, entities: list[dict], response) -> Iterator:
        listing = _listing_name(env)
        if "total" in body:
            self.totals[listing] = body.get("total")
        if self.selection.with_details or self.selection.nested:
            for e in entities:
                if e["kind"] == "projects_publication":
                    yield from self._detail_request(e["publication_id"])
        cursor = body.get("cursor")
        if not body.get("has_more") or cursor in (None, "") or not body.get("publications"):
            return
        if self.budget_left() == 0:
            self.limit_hit(f"max_items={self.common.max_items} reached")
            return
        if (listing, str(cursor)) in self._cursors_seen:
            return
        self._cursors_seen.add((listing, str(cursor)))
        if self.page_allowed(listing):
            yield self._user_page(response.meta.get("handle"), cursor)

    # ------------------------------------------------------------ nested project data
    def _detail_request(self, pid: Optional[str]) -> Iterator:
        if pid and pid not in self._detail_requested:
            self._detail_requested.add(pid)
            yield self.api_request("projects_publication_detail", ep.PUBLICATION_DETAIL.format(id=quote(pid, safe="")),
                                   priority=2, meta=_path_params(publication_id=pid))

    def _nested_requests(self, body: dict) -> Iterator:
        """From a publication detail: the page's assets/brief folder (JS Fi(): snapshot folder, else for contest
        entries the source or root folder), then folders + items, brief, comments and related projects."""
        sel = self.selection
        pid = body.get("publication_id")
        if not pid or pid in self._nested_done:
            return
        self._nested_done.add(pid)
        contest = body.get("contest_key") is not None
        folder = body.get("snapshot_folder_id") or (body.get("original_folder_id") if contest else None) \
            or (self._root_folder.get(pid) if contest else None)
        show = "true" if body.get("show_prompts") is not False else "false"
        ctx = {"publication_id": pid, "folder_id": folder}
        if folder and sel.with_project_assets and folder not in self._folders_requested:
            self._folders_requested.add(folder)
            fq = quote(folder, safe="")
            yield self.api_request("projects_folder", ep.FOLDER.format(id=fq), priority=1, labels=ctx,
                                   callback=self.parse_folder_response)
            yield self.api_request("projects_folder_children", ep.FOLDER_CHILDREN.format(id=fq), priority=1,
                                   labels={**ctx, "parent": folder, "show_prompts": show},
                                   callback=self.parse_folder_response)
            yield self._items_page(pid, folder, show, None)
        if folder and sel.with_project_brief:
            yield self.api_request("projects_brief", ep.BRIEF_SNAPSHOT.format(folder_id=quote(folder, safe="")),
                                   base=ep.BRIEF_BASE, priority=1, callback=self.parse_brief_response,
                                   labels={**ctx, "slug": body.get("slug")})
        if sel.with_project_comments:
            yield self._comments_page(pid, None, None)
        if sel.with_project_related:
            key = body.get("contest_key")
            scope = ep.RELATED_SCOPE_BY_KEY.get(key)
            if scope:
                params = {"scope": scope,
                          "current_publication_id": pid if key in (None, "talent_contest") else None}
                yield self.api_request("projects_related", ep.RECOMMENDED, params, priority=1,
                                       labels={"publication_id": pid})

    def _items_page(self, pid: str, root: str, show: str, cursor, folder: Optional[str] = None):
        """Assets of the project: the root folder with include_subfolders (the page's "All assets"), or one
        sub-folder that this listing leaves out (surface `watermarks`: the contest packshots)."""
        folder = folder or root
        params = {"size": self.page_size(ep.MAX_FOLDER_ITEMS_SIZE, ep.MAX_FOLDER_ITEMS_SIZE),
                  "include_subfolders": "true" if folder == root else None, "cursor": cursor}
        labels = {"publication_id": pid, "folder_id": root, "show_prompts": show,
                  "offset": self._items_seen.get(folder, 0), "items_folder": folder if folder != root else None}
        return self.api_request("projects_folder_items", ep.FOLDER_ITEMS.format(id=quote(folder, safe="")), params,
                                priority=1, labels=labels)

    def _comments_page(self, pid: str, cursor, parent: Optional[str]):
        params = {"limit": self.page_size(ep.MAX_COMMENTS_LIMIT, ep.MAX_COMMENTS_LIMIT), "cursor": cursor,
                  "parent_id": parent, "order": "asc" if parent else None}
        return self.api_request("projects_comments", ep.PROJECT_COMMENTS.format(id=quote(pid, safe="")), params,
                                base=ep.COMMUNITY_BASE, priority=1, labels={"publication_id": pid})

    def _follow_children(self, env, body: dict) -> Iterator:
        p = env.params or {}
        for f in body.get("items") or []:
            fid = f.get("id") if isinstance(f, dict) else None
            if fid and (f.get("subfolders_count") or 0) > 0 and fid not in self._folders_requested:
                self._folders_requested.add(fid)
                yield self.api_request("projects_folder_children", ep.FOLDER_CHILDREN.format(id=quote(fid, safe="")),
                                       priority=1, labels={"publication_id": p.get("publication_id"),
                                                           "folder_id": p.get("folder_id"), "parent": fid,
                                                           "show_prompts": p.get("show_prompts")},
                                       callback=self.parse_folder_response)
            if fid and f.get("surface") in ep.SEPARATE_ITEM_SURFACES and (f.get("count") or 0) > 0 \
                    and f"items:{fid}" not in self._folders_requested:
                self._folders_requested.add(f"items:{fid}")
                yield self._items_page(p.get("publication_id"), p.get("folder_id"), p.get("show_prompts") or "false",
                                       None, folder=fid)

    def _follow_items(self, env, body: dict) -> Iterator:
        p = env.params or {}
        root = p.get("folder_id")
        folder = p.get("items_folder") or root
        items = body.get("items") or []
        self._items_seen[folder] = self._items_seen.get(folder, 0) + len(items)
        cursor = body.get("cursor")
        if not items or cursor in (None, ""):
            return
        if self.page_allowed(f"assets:{folder}"):
            yield self._items_page(p.get("publication_id"), root, p.get("show_prompts") or "false", cursor,
                                   folder=folder)

    def parse_folder_response(self, response, **kw):
        """Folder bodies carry `owner_username`, a handle that core privacy redaction does not list: blank it before
        the response is archived in raw/ and parsed, unless --with-profiles (the parser only reads it then)."""
        if not self.selection.with_profiles and response.status == 200 and b"owner_username" in (response.body or b""):
            try:
                body = _blank_keys(json.loads(response.text), ep.FOLDER_PERSONAL_KEYS)
                response = response.replace(body=json.dumps(body).encode())
            except ValueError:
                pass
        yield from self.parse_api(response, **kw)

    def _follow_comments(self, env, body: dict) -> Iterator:
        p = env.params or {}
        pid = p.get("publication_id")
        parent = p.get("parent_id")
        if not parent:
            self.totals[f"comments:{pid}"] = body.get("total")
            for c in body.get("items") or []:
                cid = c.get("id") if isinstance(c, dict) else None
                if cid and (c.get("reply_count") or 0) > 0 and cid not in self._replies_requested:
                    self._replies_requested.add(cid)
                    yield self._comments_page(pid, None, cid)
        nxt = body.get("next_cursor")
        if nxt and body.get("items") and self.page_allowed(f"comments:{parent or pid}"):
            yield self._comments_page(pid, nxt, parent)

    def parse_brief_response(self, response, **kw):
        """The brief snapshot is binary (Yjs update): wrap it in a JSON envelope and hand it to parse_api, so it is
        archived in raw/ and parsed (also by `normalize`) like every other response."""
        if response.status == 200:
            data = response.body or b""
            body = {"snapshot_b64": base64.b64encode(data).decode("ascii"), "bytes": len(data),
                    "updated_at_ms": (response.headers.get("X-Brief-Updated-At") or b"").decode() or None,
                    "content_type": (response.headers.get("Content-Type") or b"").decode() or None}
            response = TextResponse(response.url, status=200, body=json.dumps(body).encode(), encoding="utf-8",
                                    request=response.request, headers={"Content-Type": "application/json"})
        yield from self.parse_api(response, **kw)
