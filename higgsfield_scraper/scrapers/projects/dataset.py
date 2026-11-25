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
from .schemas import ProjectsDataset

NEVER_OVERRIDE = {"source", "listing", "detail_source", "detail_fetched", "extra"}


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def _merge(base: Optional[dict], detail: dict) -> dict:
    """List record + detail record: detail values win unless they are missing/empty."""
    if base is None:
        out = dict(detail)
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


def _merged(rows: list[dict], details: list[dict], key: str) -> list[dict]:
    by_id: dict[str, dict] = {}
    for r in rows:
        by_id.setdefault(r[key], _strip(r))
    for d in details:
        d = _strip(d)
        by_id[d[key]] = _merge(by_id.get(d[key]), d)
    return list(by_id.values())


def build_dataset(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta) -> dict:
    g = lambda k: entities.get(k) or []  # noqa: E731
    publications = _merged(g("projects_publication"), g("projects_publication_detail"), "publication_id")
    contests = _merged(g("projects_contest"), g("projects_contest_detail"), "contest_id")
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
        warnings.append("original series (/series) need a login session: none scraped")

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
    meta = make_meta("projects", sel, rm, counts=counts,
                     endpoints={k: f"{API_BASE}{v}" for k, v in ep.ENDPOINTS.items()},
                     totals_available=rm.totals, warnings=warnings)
    ds = {"schema_version": 1, "meta": meta, "publications": publications, "episodes": episodes,
          "categories": categories, "contests": contests, "submissions": submissions, "series": series,
          "listing_entries": entries, "summary": summary}
    return ProjectsDataset.model_validate(ds).model_dump(mode="json")


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
    }


def json_parts(ds: dict) -> dict[str, Any]:
    return {k: ds[k] for k in ("publications", "episodes", "categories", "contests", "submissions", "series",
                               "listing_entries", "summary")}


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
    if m.get("limits_hit"):
        lines += ["", "## Limits hit", ""] + [f"- {x}" for x in m["limits_hit"]]
    if m.get("warnings"):
        lines += ["", "## Warnings", ""] + [f"- {x}" for x in m["warnings"]]
    return "\n".join(lines) + "\n"


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    return write_standard_outputs(ds, out_dir, json_parts=json_parts(ds), csv_tables=csv_tables(ds),
                                  dataset_model=ProjectsDataset, summary_md=summary_md(ds))


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
    if mode == "thumbs":
        return thumbs
    if mode == "full":
        return full
    if mode == "all":
        return thumbs + full + other
    return []
