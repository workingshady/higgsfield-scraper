"""Assemble the validated ProjectsDataset and write every output file."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Optional

from ...constants import API_BASE
from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import without, write_standard_outputs
from . import endpoints as ep
from .options import Selection
from .parsers import best_video_url
from .schemas import (EXTRA_COLLECTIONS, NESTED_COLLECTIONS, ProjectsDataset, ProjectsExtrasDataset,
                      ProjectsNestedDataset, ProjectsNestedExtrasDataset)

NEVER_OVERRIDE = {"source", "listing", "detail_source", "detail_fetched", "extra"}


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def _merge(base: Optional[dict], detail: dict, *, has_listing: bool = True) -> dict:
    """List record + detail record: detail values win unless they are missing/empty.

    A detail without a list record (e.g. `normalize` of a --max-items run: the budget keeps the list rows of the
    first primary kind only, while the *_detail rows are not budgeted) is kept as is. Only records with a
    `listing` field (publications) get the "detail" fallback; Contest has no such field (fix 2026-11-26).
    """
    if base is None:
        out = dict(detail)
        if has_listing:
            out["listing"] = out.get("listing") or "detail"
        return out
    out = dict(base)
    for k, v in detail.items():
        if k in NEVER_OVERRIDE or v is None or v == [] or v == {}:
            continue
        if k in ("media_count", "author_count", "some_contestants_count", "judge_count") and not v:
            continue
        out[k] = v
    out["extra"] = {**(base.get("extra") or {}), **(detail.get("extra") or {})}
    out["detail_fetched"] = True
    out["detail_source"] = detail.get("source")
    return out


def _merged(rows: list[dict], details: list[dict], key: str, *, has_listing: bool = True) -> list[dict]:
    by_id: dict[str, dict] = {}
    for r in rows:
        by_id.setdefault(r[key], _strip(r))
    for d in details:
        d = _strip(d)
        by_id[d[key]] = _merge(by_id.get(d[key]), d, has_listing=has_listing)
    return list(by_id.values())


def build_dataset(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta) -> dict:
    g = lambda k: entities.get(k) or []  # noqa: E731
    publications = _merged(g("projects_publication"), g("projects_publication_detail"), "publication_id")
    contests = _merged(g("projects_contest"), g("projects_contest_detail"), "contest_id", has_listing=False)
    pub_ids = {p["publication_id"] for p in publications}
    warnings: list[str] = []

    episodes = [_strip(e) for e in g("projects_episode")]
    orphans = [e for e in episodes if e.get("publication_id") and e["publication_id"] not in pub_ids]
    if orphans:
        warnings.append(f"{len(orphans)} episodes dropped: their publication is not in the dataset (max-items)")
        gone = {e["episode_id"] for e in orphans}
        episodes = [e for e in episodes if e["episode_id"] not in gone]
    entries = [_strip(e) for e in g("projects_listing_entry")]
    n = len(entries)
    entries = [e for e in entries if e["publication_id"] in pub_ids]
    if len(entries) != n:
        warnings.append(f"{n - len(entries)} listing entries dropped: publication not in the dataset (max-items)")
    submissions = [_strip(s) for s in g("projects_contest_submission")]
    categories = [_strip(c) for c in g("projects_category")]
    series = [_strip(s) for s in g("projects_series")]
    if sel.wants("series") and not series:
        warnings.append("original series: none scraped (fnf-series answered nothing)"
                        if getattr(sel, "public_series", False)
                        else "original series (/series) need a login session: none scraped")

    slug_by_contest = {c["contest_id"]: c.get("slug") for c in contests}
    summary = {
        "publications_by_type": dict(Counter(p.get("type") or "unknown" for p in publications)),
        "publications_by_listing": dict(Counter(e["listing"] for e in entries)),
        "publications_with_details": sum(1 for p in publications if p.get("detail_fetched")),
        "episodes": len(episodes),
        "contests_by_status": dict(Counter(c.get("status") or "unknown" for c in contests)),
        "contests_by_type": dict(Counter(c.get("contest_type") or "unknown" for c in contests)),
        "submissions_by_contest": dict(Counter(slug_by_contest.get(s.get("contest_id")) or s.get("contest_slug")
                                               or "unknown" for s in submissions)),
        "total_views": sum(p.get("views") or 0 for p in publications),
        "total_likes": sum(p.get("likes") or 0 for p in publications),
        "with_profiles": sel.with_profiles,
    }
    counts = {"publications": len(publications), "episodes": len(episodes), "categories": len(categories),
              "contests": len(contests), "submissions": len(submissions), "series": len(series),
              "listing_entries": len(entries)}
    nested = _nested(entities, publications, warnings) if getattr(sel, "nested", False) else None
    if nested is not None:
        counts.update({k: len(nested[k]) for k in NESTED_COLLECTIONS})
    extras = _extras(entities, sel, rm, warnings) if getattr(sel, "extras", False) else None
    if extras is not None:
        counts.update({k: len(extras[k]) for k in EXTRA_COLLECTIONS})
    meta = make_meta("projects", sel, rm, counts=counts,
                     endpoints={**{k: f"{API_BASE}{v}" for k, v in ep.ENDPOINTS.items()},
                                **({k: f"{ep.SERIES_BASE}{v}" for k, v in ep.PUBLIC_SERIES_ENDPOINTS.items()}
                                   if getattr(sel, "public_series", False) else {}),
                                **_nested_endpoints(sel)},
                     totals_available=rm.totals, warnings=warnings)
    ds = {"schema_version": 1, "meta": meta, "publications": publications, "episodes": episodes,
          "categories": categories, "contests": contests, "submissions": submissions, "series": series,
          "listing_entries": entries, "summary": summary}
    if extras is not None:                                    # opt-in extras (2026-11-26)
        model = ProjectsNestedExtrasDataset if nested is not None else ProjectsExtrasDataset
        return model.model_validate({**ds, **(nested or {}), **extras}).model_dump(mode="json")
    if nested is None:
        return ProjectsDataset.model_validate(ds).model_dump(mode="json")
    return ProjectsNestedDataset.model_validate({**ds, **nested}).model_dump(mode="json")


# ------------------------------------------------------------------ opt-in extras (trending, participation, works)
def _extras(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta, warnings: list[str]) -> dict:
    g = lambda k: [_strip(e) for e in entities.get(k) or []]  # noqa: E731
    trending = sorted(g("projects_trending_row"), key=lambda r: (r["listing"], r.get("position") is None,
                                                                 r.get("position") or 0))
    parts: dict[str, dict] = {}
    for c in g("projects_participation_counters"):
        row = parts.setdefault(c["contest_key"], {"contest_key": c["contest_key"]})
        row.update({k: c.get(k) for k in ("total", "public_total", "private_total")},
                   counters_source_url=c.get("source_url"), scraped_at=row.get("scraped_at") or c.get("scraped_at"))
        if c.get("extra"):
            row.setdefault("extra", {})["counters"] = c["extra"]
    for c in g("projects_participation_config"):
        row = parts.setdefault(c["contest_key"], {"contest_key": c["contest_key"]})
        row.update({k: v for k, v in c.items() if k not in ("contest_key", "source", "source_url", "scraped_at",
                                                              "schema_version", "extra")},
                   config_source_url=c.get("source_url"), scraped_at=row.get("scraped_at") or c.get("scraped_at"))
        if c.get("extra"):
            row.setdefault("extra", {})["config"] = c["extra"]
    for row in parts.values():
        row["contest_slug"] = ep.CONTEST_KEY_SLUG.get(row["contest_key"])
    works, stats = g("projects_user_work"), g("projects_user_stats")
    totals = rm.totals or {}
    for st in stats:
        st["works_total"] = totals.get(f"user_works:{st['creator_uid_key']}")
    if getattr(sel, "with_user_works", False) and not stats and not works:
        warnings.append("--with-user-works: no users found in this run (it follows owners of --users projects, "
                        "contest entries and contest submitters only)")
    if sel.wants("trending") and not trending:
        warnings.append("--what trending: no ranking rows scraped")
    return {"trending": trending, "contest_participation": list(parts.values()), "user_works": works,
            "user_stats": stats}


# ------------------------------------------------------------------ nested project data (opt-in)
def _nested_endpoints(sel: Selection) -> dict[str, str]:
    """meta.endpoints entries for the opt-in features actually used (none by default)."""
    keys: list[str] = []
    if getattr(sel, "contests", ()):
        keys.append("projects_contest_by_slug")
    if getattr(sel, "users", ()):
        keys.append("projects_user_publications")
    if getattr(sel, "with_project_assets", False):
        keys += ["projects_folder", "projects_folder_children", "projects_folder_items"]
    if getattr(sel, "with_project_brief", False):
        keys.append("projects_brief")
    if getattr(sel, "with_project_comments", False):
        keys.append("projects_comments")
    if getattr(sel, "with_project_related", False):
        keys.append("projects_related")
    if sel.wants("trending"):
        keys.append("projects_trending")
    if sel.wants("contest-participation"):
        keys += ["projects_participation_counters", "projects_participation_config"]
    if getattr(sel, "with_user_works", False):
        keys += ["projects_user_works", "projects_user_stats"]
    out = {}
    for k in keys:
        base, path = ep.NESTED_ENDPOINTS.get(k) or ep.EXTRA_ENDPOINTS[k]
        out[k] = f"{base or API_BASE}{path}"
    return out


def _folder_chain(fid: Optional[str], folders: dict[str, dict]) -> list[dict]:
    """[folder, parent, …] up to (excluding) the root folder."""
    chain: list[dict] = []
    seen: set[str] = set()
    while fid and fid in folders and fid not in seen:
        seen.add(fid)
        f = folders[fid]
        if f.get("is_root") or not f.get("parent_id"):
            break
        chain.append(f)
        fid = f.get("parent_id")
    return chain


def _brief_names(briefs: list[dict], pubs: dict[str, dict]) -> None:
    """briefs/<slug>.md (the slug, else the publication id); duplicates get the id appended."""
    names: dict[str, int] = Counter()
    base = {}
    for b in briefs:
        stem = b.get("publication_slug") or (pubs.get(b.get("publication_id") or "") or {}).get("slug") \
            or b.get("publication_id") or b["brief_id"]
        stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(stem))[:120] or b["brief_id"]
        base[b["brief_id"]] = stem
        names[stem] += 1
    for b in briefs:
        stem = base[b["brief_id"]]
        if names[stem] > 1:
            stem = f"{stem}-{str(b.get('publication_id') or b['brief_id'])[:8]}"
        b["file"] = f"briefs/{stem}.md" if b.get("markdown") else None


def _nested(entities: dict[str, list[dict]], publications: list[dict], warnings: list[str]) -> dict:
    g = lambda k: [_strip(e) for e in entities.get(k) or []]  # noqa: E731
    folders, assets, briefs = g("projects_folder"), g("projects_asset"), g("projects_brief")
    stats, stack, comments, related = (g("projects_stats"), g("projects_stack_item"), g("projects_comment"),
                                       g("projects_related"))
    pubs = {p["publication_id"]: p for p in publications}
    by_folder = {f["folder_id"]: f for f in folders}
    model = {(s["publication_id"], s.get("job_set_type")): s.get("display_name") for s in stack}
    under: Counter = Counter()
    for a in assets:
        chain = _folder_chain(a.get("folder_id"), by_folder)
        leaf = by_folder.get(a.get("folder_id") or "")
        a["folder_name"] = leaf.get("name") if leaf else None
        a["folder_path"] = " / ".join(f.get("name") or "?" for f in reversed(chain)) or None
        a["model_name"] = model.get((a.get("publication_id"), a.get("job_set_type")))
        for f in chain:
            under[f["folder_id"]] += 1
        if a.get("root_folder_id") and a.get("in_all_assets", True):   # root count = the "All assets" grid
            under[a["root_folder_id"]] += 1
    for f in folders:
        f["assets_scraped"] = under.get(f["folder_id"], 0) if assets else None
    mismatches = [f"{f['folder_id']}: count={f.get('asset_count')} scraped={f['assets_scraped']}"
                  for f in folders if f.get("is_root") and f["assets_scraped"] is not None
                  and f.get("asset_count") is not None and f["asset_count"] != f["assets_scraped"]]
    if mismatches:
        warnings.append(f"{len(mismatches)} project root folders: API asset count != assets scraped "
                        "(--max-pages, or items the API does not list)")
    asset_ids: dict[str, set[str]] = {}
    for a in assets:
        asset_ids.setdefault(a.get("publication_id") or "", set()).add(a["asset_id"])
    for b in briefs:
        ids = asset_ids.get(b.get("publication_id") or "", set())
        b["referenced_asset_ids"] = [i for i in b.get("referenced_ids") or [] if i in ids]
    _brief_names(briefs, pubs)
    for c in comments:
        keys = set((pubs.get(c.get("publication_id") or "") or {}).get("author_keys") or [])
        ak = (c.get("author") or {}).get("author_key")
        c["is_by_author"] = (ak in keys) if keys and ak else None
    project_ids = {x.get("publication_id") for coll in (folders, assets, briefs, stats, comments, related)
                   for x in coll if x.get("publication_id")}
    summary = {
        "projects": len(project_ids),
        "folders": len(folders),
        "assets": len(assets),
        "assets_by_media_type": dict(Counter(a.get("media_type") or "unknown" for a in assets)),
        "assets_by_model": dict(Counter(a.get("model_name") or a.get("job_set_type") or a.get("item_type")
                                        or "unknown" for a in assets)),
        "prompts_visible": sum(1 for a in assets if a.get("prompt")),
        "briefs": sum(1 for b in briefs if b.get("has_content")),
        "comments": len(comments),
        "related": len(related),
        "asset_count_mismatches": mismatches,
    }
    return {"folders": folders, "assets": assets, "briefs": briefs, "project_stats": stats, "stack_items": stack,
            "comments": comments, "related": related, "nested_summary": summary}


# ------------------------------------------------------------------ outputs
PUB_CHILDREN = ("media", "authors", "team", "model_usage")
CONTEST_CHILDREN = ("judges", "prizes", "faq", "some_contestants")


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    from ...core.exporting import row
    pubs, contests = ds["publications"], ds["contests"]
    pk = lambda p: {"publication_id": p["publication_id"]}  # noqa: E731
    ck = lambda c: {"contest_id": c["contest_id"], "contest_slug": c.get("slug")}  # noqa: E731
    return {
        "publications": ([row(without(p, *PUB_CHILDREN)) for p in pubs], ["publication_id", "name", "type"]),
        "publication_media": ([row(m, **pk(p)) for p in pubs for m in p["media"]], ["publication_id", "role"]),
        "publication_authors": ([row(a, **pk(p)) for p in pubs for a in p["authors"] + ([p["team"]] if p["team"] else [])],
                                ["publication_id", "role", "author_key"]),
        "publication_model_usage": ([row(u, **pk(p)) for p in pubs for u in p["model_usage"]], ["publication_id"]),
        "episodes": ([row(e) for e in ds["episodes"]], ["episode_id", "publication_id", "series_id", "number"]),
        "categories": ([row(c) for c in ds["categories"]], ["slug", "label"]),
        "contests": ([row(without(c, *CONTEST_CHILDREN)) for c in contests], ["contest_id", "slug", "title"]),
        "contest_judges": ([row(j, **ck(c)) for c in contests for j in c["judges"]], ["contest_id", "position"]),
        "contest_rewards": ([row(p, **ck(c)) for c in contests for p in c["prizes"]], ["contest_id", "position"]),
        "contest_faq": ([row(f, **ck(c)) for c in contests for f in c["faq"]], ["contest_id", "position"]),
        "contest_contestants": ([row(p, **ck(c)) for c in contests for p in c["some_contestants"]], ["contest_id"]),
        "submissions": ([row(s) for s in ds["submissions"]], ["submission_id", "contest_id", "title"]),
        "series": ([row(s) for s in ds["series"]], ["series_id", "slug", "title"]),
        "listing_entries": ([row(e) for e in ds["listing_entries"]], ["listing", "position", "publication_id"]),
        **(_nested_tables(ds) if "assets" in ds else {}),
        **(_extra_tables(ds) if "user_works" in ds else {}),
    }


WORK_CHILDREN = ("variants", "input_media", "params")


def _extra_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    from ...core.exporting import row
    wk = lambda w: {"work_id": w["work_id"], "creator_uid_key": w.get("creator_uid_key"),  # noqa: E731
                    "job_id": w.get("job_id")}
    return {
        "trending": ([row(r) for r in ds["trending"]], ["listing", "position", "publication_id"]),
        "contest_participation": ([row(r) for r in ds["contest_participation"]], ["contest_key", "total"]),
        "user_works": ([row(without(w, *WORK_CHILDREN), params=_json(w.get("params"))) for w in ds["user_works"]],
                       ["creator_uid_key", "position", "publication_type", "work_id", "job_set_type"]),
        "user_work_variants": ([row(v, **wk(w)) for w in ds["user_works"] for v in w["variants"]],
                               ["work_id", "variant"]),
        "user_work_inputs": ([row(i, **wk(w)) for w in ds["user_works"] for i in w["input_media"]],
                             ["work_id", "position"]),
        "user_stats": ([row(s) for s in ds["user_stats"]], ["creator_uid_key"]),
    }


def _json(v: Any) -> Optional[str]:
    import json
    return json.dumps(v, ensure_ascii=False, sort_keys=True) if v else None


ASSET_CHILDREN = ("variants", "input_media")


def _nested_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    from ...core.exporting import row
    ak = lambda a: {"placement_id": a["placement_id"], "asset_id": a["asset_id"],  # noqa: E731
                    "publication_id": a.get("publication_id")}
    return {
        "project_folders": ([row(f) for f in ds["folders"]], ["publication_id", "folder_id", "depth", "name"]),
        "project_assets": ([row(without(a, *ASSET_CHILDREN)) for a in ds["assets"]],
                           ["publication_id", "placement_id", "asset_id", "folder_path", "job_set_type"]),
        "project_asset_variants": ([row(v, **ak(a)) for a in ds["assets"] for v in a["variants"]],
                                   ["publication_id", "asset_id", "variant"]),
        "project_asset_inputs": ([row(i, **ak(a)) for a in ds["assets"] for i in a["input_media"]],
                                 ["publication_id", "asset_id", "position"]),
        "project_briefs": ([row(b) for b in ds["briefs"]], ["publication_id", "brief_id", "file"]),
        "project_stats": ([row(s) for s in ds["project_stats"]], ["publication_id"]),
        "project_stack": ([row(s) for s in ds["stack_items"]], ["publication_id", "position", "label"]),
        "project_comments": ([row(c) for c in ds["comments"]], ["publication_id", "comment_id", "parent_id"]),
        "project_related": ([row(r) for r in ds["related"]], ["publication_id", "position", "related_publication_id"]),
    }


def json_parts(ds: dict) -> dict[str, Any]:
    keys = ["publications", "episodes", "categories", "contests", "submissions", "series", "listing_entries",
            "summary"]
    if "assets" in ds:
        keys += list(NESTED_COLLECTIONS) + ["nested_summary"]
    if "user_works" in ds:
        keys += list(EXTRA_COLLECTIONS)
    return {k: ds[k] for k in keys}


def summary_md(ds: dict) -> str:
    m, s = ds["meta"], ds["summary"]
    lines = [f"# Higgsfield projects & contests — {m.get('label') or m.get('run_id') or ''}".rstrip(" —"), "",
             f"Scraped at {m['scraped_at']} · options `{m['options'].get('what')}`"
             f" · details={m['options'].get('with_details')} · submissions={m['options'].get('with_submissions')}"
             f" · profiles={m['options'].get('with_profiles')}", "", "## Counts", "", "| collection | rows |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in m["counts"].items()]
    if m.get("totals_available"):
        lines += ["", "## Totals reported by the API", "", "| listing | total |", "|---|---:|"]
        lines += [f"| {k} | {v if v is not None else '?'} |" for k, v in m["totals_available"].items()]
    if s["publications_by_type"]:
        lines += ["", "## Publications by type", ""] + [f"- {k}: {v}" for k, v in s["publications_by_type"].items()]
    if s["publications_by_listing"]:
        lines += ["", "## Publications by listing", ""] + [f"- {k}: {v}" for k, v in
                                                          s["publications_by_listing"].items()]
    top = sorted(ds["publications"], key=lambda p: p.get("views") or 0, reverse=True)[:10]
    if top:
        lines += ["", "## Top 10 publications by views", "", "| name | type | views | likes |", "|---|---|---:|---:|"]
        lines += [f"| {(p.get('name') or '').strip().replace('|', '/')} | {p.get('type')} | {p.get('views')} | "
                  f"{p.get('likes')} |" for p in top]
    if ds["contests"]:
        lines += ["", "## Contests", "", "| slug | type | status | prize pool | submissions | scraped submissions |",
                  "|---|---|---|---:|---:|---:|"]
        lines += [f"| {c.get('slug')} | {c.get('contest_type')} | {c.get('status')} | {c.get('prize_pool')} "
                  f"{c.get('prize_pool_unit') or ''} | {c.get('submissions_count')} | "
                  f"{s['submissions_by_contest'].get(c.get('slug'), 0)} |" for c in ds["contests"]]
    if "nested_summary" in ds:
        n = ds["nested_summary"]
        lines += ["", "## Nested project data", "", "| project | folders | all assets [+ listed apart] (API count) | prompts | brief | "
                  "comments | related |", "|---|---:|---:|---:|---|---:|---:|"]
        roots = {f["publication_id"]: f for f in ds["folders"] if f.get("is_root")}
        names = {p["publication_id"]: p.get("name") for p in ds["publications"]}
        for pid in sorted({x["publication_id"] for k in NESTED_COLLECTIONS for x in ds[k] if x.get("publication_id")},
                          key=lambda i: str(names.get(i) or i)):
            r = roots.get(pid) or {}
            a = [x for x in ds["assets"] if x.get("publication_id") == pid]
            b = next((x for x in ds["briefs"] if x.get("publication_id") == pid), None)
            n_all = sum(1 for x in a if x.get("in_all_assets", True))
            extra = f" + {len(a) - n_all}" if len(a) > n_all else ""
            lines.append(f"| {(names.get(pid) or pid).strip().replace('|', '/')} | "
                         f"{sum(1 for f in ds['folders'] if f.get('publication_id') == pid)} | {n_all}{extra} "
                         f"({r.get('asset_count', '?')}) | {sum(1 for x in a if x.get('prompt'))} | "
                         f"{(str(b['word_count']) + ' words') if b and b.get('has_content') else '-'} | "
                         f"{sum(1 for x in ds['comments'] if x.get('publication_id') == pid)} | "
                         f"{sum(1 for x in ds['related'] if x.get('publication_id') == pid)} |")
        if n.get("assets_by_model"):
            lines += ["", "Assets by model: " + ", ".join(f"{k} {v}" for k, v in
                                                          sorted(n["assets_by_model"].items(), key=lambda kv: -kv[1]))]
    if "user_works" in ds:
        lines += _extras_md(ds)
    if m.get("limits_hit"):
        lines += ["", "## Limits hit", ""] + [f"- {x}" for x in m["limits_hit"]]
    if m.get("warnings"):
        lines += ["", "## Warnings", ""] + [f"- {x}" for x in m["warnings"]]
    return "\n".join(lines) + "\n"


def _extras_md(ds: dict) -> list[str]:
    lines: list[str] = []
    if ds["trending"]:
        tot = {r["listing"]: r.get("total_reported") for r in ds["trending"]}
        lines += ["", "## Trending projects", "", "| listing | rows | total reported |", "|---|---:|---:|"]
        lines += [f"| {k} | {sum(1 for r in ds['trending'] if r['listing'] == k)} | {v} |" for k, v in tot.items()]
    if ds["contest_participation"]:
        lines += ["", "## Contest participation", "", "| contest | stage | total | public | private |",
                  "|---|---|---:|---:|---:|"]
        lines += [f"| {r['contest_key']} | {r.get('stage')} | {r.get('total')} | {r.get('public_total')} | "
                  f"{r.get('private_total')} |" for r in ds["contest_participation"]]
    if ds["user_works"] or ds["user_stats"]:
        by_type = Counter(w.get("publication_type") or "unknown" for w in ds["user_works"])
        lines += ["", "## User works (pseudonymous)", "", f"- users: {len(ds['user_stats'])}",
                  f"- works: {len(ds['user_works'])} ("
                  + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())) + ")",
                  f"- with prompt: {sum(1 for w in ds['user_works'] if w.get('prompt'))}"]
    return lines


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    nested = "assets" in ds
    model = ProjectsNestedDataset if nested else ProjectsDataset
    if "user_works" in ds:                                    # opt-in extras
        model = ProjectsNestedExtrasDataset if nested else ProjectsExtrasDataset
    files = write_standard_outputs(ds, out_dir, json_parts=json_parts(ds), csv_tables=csv_tables(ds),
                                   dataset_model=model, summary_md=summary_md(ds))
    for b in ds.get("briefs") or []:                          # --with-project-brief: output/briefs/<slug>.md
        if b.get("file") and b.get("markdown"):
            path = out_dir / b["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(b["markdown"], encoding="utf-8")
            files.append(path)
    return files


# ------------------------------------------------------------------ media for --download-media
def media_urls(entity: dict, mode: str) -> list[tuple[str, str]]:
    thumbs: list[tuple[str, str]] = []
    full: list[tuple[str, str]] = []
    other: list[tuple[str, str]] = []
    kind = entity.get("kind")
    if kind in ("projects_publication", "projects_publication_detail"):
        for m in entity.get("media") or []:
            tag = f"{m['role']}{m['position']}"
            if m["role"] == "cover" and m.get("url"):
                thumbs.append((tag, m["url"]))
            if m.get("thumbnail_url"):
                thumbs.append((f"{tag}_thumb", m["thumbnail_url"]))
            if m.get("type") in ("video", "job") or m["role"] == "trailer":
                if (v := best_video_url(m)):
                    full.append((tag, v))
            elif m["role"] != "cover" and m.get("url"):
                other.append((tag, m["url"]))
    elif kind in ("projects_contest", "projects_contest_detail"):
        thumbs += [(r, entity[r]) for r in ("preview_image", "logo_url") if entity.get(r)]
        full += [("preview_video", entity["preview_video"])] if entity.get("preview_video") else []
    elif kind == "projects_contest_submission":
        thumbs += [("thumbnail", entity["thumbnail_url"])] if entity.get("thumbnail_url") else []
        full += [("video", entity["video_url"])] if entity.get("video_url") else []
    elif kind == "projects_episode":
        thumbs += [("thumbnail", entity["thumbnail_url"])] if entity.get("thumbnail_url") else []
        v = best_video_url({"original_url": entity.get("original_url"), "preview_url": entity.get("preview_url"),
                            "url": entity.get("video_url")})
        full += [("video", v)] if v else []
    elif kind == "projects_series":
        thumbs += [(r, entity[r]) for r in ("portrait_url", "landscape_url", "logo_url") if entity.get(r)]
        full += [("trailer", entity["trailer_url"])] if entity.get("trailer_url") else []
    elif kind == "projects_asset":                            # --with-project-assets: <run>/media/projects_asset/
        thumb = entity.get("thumbnail_url") or (entity.get("min_url") if entity.get("media_type") == "image" else None)
        thumbs += [("thumb", thumb)] if thumb else []
        full += [("original", entity["url"])] if entity.get("url") and not str(entity["url"]).split("?")[0] \
            .endswith(".m3u8") else []
        if entity.get("min_url") and entity.get("min_url") not in (thumb, entity.get("url")):
            other.append(("preview", entity["min_url"]))
    elif kind == "projects_user_work":                        # --with-user-works: <run>/media/projects_user_work/
        thumb = entity.get("thumbnail_url") or (entity.get("min_url") if entity.get("media_type") == "image" else None)
        thumbs += [("thumb", thumb)] if thumb else []
        main = entity.get("url") or entity.get("video_url")
        full += [("original", main)] if main and not str(main).split("?")[0].endswith(".m3u8") else []
        if entity.get("min_url") and entity.get("min_url") not in (thumb, main):
            other.append(("preview", entity["min_url"]))
    if mode == "thumbs":
        return thumbs
    if mode == "full":
        return full
    if mode == "all":
        return thumbs + full + other
    return []
