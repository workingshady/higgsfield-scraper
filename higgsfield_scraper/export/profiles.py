"""Per-scraper export profiles: how a scraper's tables become a browsable tree.

A profile is declarative for most scrapers (default grouping per collection + which collections are plain tables).
`projects` adds code: contest/project/folder paths from the publication + folder tables, and per-project documents
(project.json, brief.md, comments.md, stats.json). Unknown scrapers get `GenericProfile` (group by collection), so
a new scraper exports without code changes.

Grouping spec: a list of field names (`ExportRow.field`, i.e. normalized fields, profile extras or dotted record
paths); a value starting with "=" is a literal folder name. Missing values are skipped; list values expand into
several folders (e.g. a project's nested folder chain).
"""
from __future__ import annotations

import json
from typing import Any, Iterator, Optional

from .reader import RunSource
from .records import ExportRow

DocItem = tuple[list[str], str, str]        # (group parts, file name, text content)


class GenericProfile:
    name = "generic"
    default_group: list[str] = ["collection"]
    group_by_collection: dict[str, list[str]] = {}
    id_fields: dict[str, str] = {}
    table_only: set[str] = set()

    def prepare(self, run: RunSource) -> None:          # load small lookup tables
        pass

    def enrich(self, row: ExportRow) -> None:           # add profile fields to row.extra
        pass

    def group_spec(self, coll: str, override: Optional[list[str]] = None) -> list[str]:
        if override:
            return override
        return self.group_by_collection.get(coll, self.default_group)

    def is_row_collection(self, coll: str) -> bool:
        return coll not in self.table_only

    def docs(self, run: RunSource) -> Iterator[DocItem]:
        return iter(())


class CommunityProfile(GenericProfile):
    name = "community"
    default_group = ["collection", "feed", "model", "date"]
    table_only = {"pages", "stats", "creator_stats", "extra_stats", "creators", "comments"}


class CatalogProfile(GenericProfile):
    name = "catalog"
    default_group = ["collection", "group"]
    table_only = {"pages", "summary", "katana_categories", "marketing_categories", "viral_types"}


class SiteProfile(GenericProfile):
    name = "site"
    default_group = ["collection"]
    group_by_collection = {"room_items": ["collection", "room_slug"], "room_discussions": ["collection", "room_slug"],
                           "lessons": ["collection", "course_slug"], "app_templates": ["collection", "app_slug"]}
    table_only = {"summary"}


class ShowcaseProfile(GenericProfile):
    name = "showcase"
    default_group = ["collection", "model"]
    group_by_collection = {"explore_items": ["collection", "category"],
                           "effect_samples": ["collection", "preset_slug"]}
    table_only = {"explore_categories", "seasons", "summary"}


class BlogProfile(GenericProfile):
    name = "blog"
    default_group = ["collection"]


def _slugish(v: Any) -> Optional[str]:
    return str(v) if isinstance(v, (str, int)) and str(v) else None


class ProjectsProfile(GenericProfile):
    """projects: <contest>/<project-slug>/<Folder>/<Subfolder>/ for nested assets (website-like)."""

    name = "projects"
    default_group = ["collection"]
    group_by_collection = {
        "assets": ["contest", "project", "folder"],
        "publications": ["contest", "project"],
        "submissions": ["contest", "=submissions"],
        "episodes": ["=episodes", "series_slug"],
    }
    id_fields = {"assets": "placement_id", "publications": "publication_id", "submissions": "submission_id"}
    table_only = {"contests", "listing_entries", "folders", "briefs", "comments", "project_stats", "stack_items",
                  "related", "categories", "series", "summary"}

    def __init__(self) -> None:
        self.pubs: dict[str, dict] = {}
        self.folders: dict[str, dict] = {}

    def prepare(self, run: RunSource) -> None:
        tables = set(run.tables())
        keep = ("publication_id", "slug", "name", "contest_key", "root_folder_id")
        if "publications" in tables:
            for p in run.iter_table("publications"):
                if p.get("publication_id"):
                    self.pubs[p["publication_id"]] = {k: p.get(k) for k in keep}
        if "folders" in tables:
            for f in run.iter_table("folders"):
                if f.get("folder_id"):
                    self.folders[f["folder_id"]] = {k: f.get(k) for k in ("name", "parent_id", "is_root")}

    def _project(self, pub_id: Optional[str]) -> tuple[str, str]:
        p = self.pubs.get(pub_id or "") or {}
        contest = p.get("contest_key") or "no-contest"
        project = p.get("slug") or p.get("name") or (pub_id[:8] if pub_id else "unknown-project")
        return str(contest), str(project)

    def _folder_chain(self, row: ExportRow) -> list[str]:
        r = row.rec
        fid, root = r.get("folder_id"), r.get("root_folder_id")
        if fid and root and fid == root:
            return ["_root"]
        chain: list[str] = []
        cur, guard = fid, 0
        while cur and cur in self.folders and guard < 64:
            f = self.folders[cur]
            if f.get("is_root") or cur == root:
                break
            chain.append(str(f.get("name") or cur[:8]))
            cur, guard = f.get("parent_id"), guard + 1
        if chain:
            return list(reversed(chain))
        fp = r.get("folder_path")
        if isinstance(fp, str) and fp.strip():
            return [p.strip() for p in fp.split(" / ") if p.strip()]
        return ["_root"] if fid else []

    def enrich(self, row: ExportRow) -> None:
        r = row.rec
        if row.collection in ("assets", "publications"):
            contest, project = self._project(r.get("publication_id"))
            if row.collection == "publications":
                contest = r.get("contest_key") or contest
                project = r.get("slug") or r.get("name") or project
            row.extra["contest"] = contest
            row.extra["project"] = project
            if row.collection == "assets":
                chain = self._folder_chain(row)
                row.extra["folder"] = chain
                row.extra["folder_path"] = " / ".join(chain)
        elif row.collection == "submissions":
            row.extra["contest"] = _slugish(r.get("contest_slug")) or _slugish(r.get("contest_id")) or "no-contest"
            row.extra["project"] = _slugish(r.get("publication_slug")) or _slugish(r.get("title"))

    def docs(self, run: RunSource) -> Iterator[DocItem]:
        """Per project: project.json, brief.md, comments.md, stats.json (small tables, loaded per run)."""
        tables = set(run.tables())
        if "publications" not in tables:
            return
        by_pub: dict[str, dict[str, list]] = {}

        def bucket(pid: Optional[str], kind: str, rec: dict) -> None:
            if pid:
                by_pub.setdefault(pid, {}).setdefault(kind, []).append(rec)

        for t, kind in (("briefs", "brief"), ("comments", "comments"), ("project_stats", "stats"),
                        ("stack_items", "stack"), ("related", "related"), ("folders", "folders")):
            if t in tables:
                for rec in run.iter_table(t):
                    bucket(rec.get("publication_id"), kind, rec)
        for pub in run.iter_table("publications"):
            pid = pub.get("publication_id")
            if not pid:
                continue
            extra = by_pub.get(pid, {})
            contest = pub.get("contest_key") or "no-contest"
            project = pub.get("slug") or pub.get("name") or pid[:8]
            parts = [str(contest), str(project)]
            stats = (extra.get("stats") or [None])[0]
            stack = sorted(extra.get("stack") or [], key=lambda s: s.get("position") or 0)
            folders = extra.get("folders") or []
            project_doc = {
                "publication": pub,
                "stats": stats,
                "model_stack": stack,
                "folders": [{k: f.get(k) for k in ("folder_id", "parent_id", "name", "depth", "asset_count",
                                                   "assets_scraped", "is_root")} for f in folders],
                "related_publication_ids": [r.get("related_publication_id") for r in extra.get("related") or []],
            }
            yield parts, "project.json", json.dumps(project_doc, ensure_ascii=False, indent=4) + "\n"
            if stats or stack:
                yield parts, "stats.json", json.dumps({"stats": stats, "model_stack": stack},
                                                      ensure_ascii=False, indent=4) + "\n"
            brief = (extra.get("brief") or [None])[0]
            md = (brief or {}).get("markdown") or (run.brief_markdown(str(pub.get("slug"))) if pub.get("slug") else None)
            if md:
                title = pub.get("name") or project
                yield parts, "brief.md", f"# {title} — brief\n\n{md.rstrip()}\n"
            comments = extra.get("comments") or []
            if comments:
                yield parts, "comments.md", render_comments(pub.get("name") or project, comments)


def render_comments(title: str, comments: list[dict]) -> str:
    """Threaded Markdown. Authors are shown by their pseudonymous author_key only (never usernames)."""
    by_parent: dict[Optional[str], list[dict]] = {}
    for c in comments:
        by_parent.setdefault(c.get("parent_id"), []).append(c)
    for v in by_parent.values():
        v.sort(key=lambda c: (c.get("created_at") or "", c.get("comment_id") or ""))
    ids = {c.get("comment_id") for c in comments}
    lines = [f"# {title} — comments ({len(comments)})", ""]

    def emit(c: dict, depth: int) -> None:
        a = c.get("author") if isinstance(c.get("author"), dict) else {}
        who = a.get("author_key") or c.get("author_key") or "anonymous"
        ind = "  " * depth
        meta = f"**{who}** · {(c.get('created_at') or '')[:19].replace('T', ' ')} · likes {c.get('likes') or 0}"
        lines.append(f"{ind}- {meta}")
        for ln in str(c.get("text") or "").splitlines() or [""]:
            lines.append(f"{ind}  > {ln}")
        for ch in by_parent.get(c.get("comment_id"), []):
            emit(ch, depth + 1)

    roots = [c for c in comments if not c.get("parent_id") or c.get("parent_id") not in ids]
    roots.sort(key=lambda c: (c.get("created_at") or "", c.get("comment_id") or ""))
    for c in roots:
        emit(c, 0)
    return "\n".join(lines) + "\n"


PROFILES: dict[str, type[GenericProfile]] = {
    "projects": ProjectsProfile, "community": CommunityProfile, "catalog": CatalogProfile, "site": SiteProfile,
    "showcase": ShowcaseProfile, "blog": BlogProfile,
}


def profile_for(scraper: str) -> GenericProfile:
    return PROFILES.get(scraper, GenericProfile)()
