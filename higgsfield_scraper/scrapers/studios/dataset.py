"""Assemble the validated StudiosDataset and write its outputs (JSON parts, complete CSVs, summary.md).

CSV layout: one table per collection (`<collection>.csv`, child lists removed) + one table per child list
(`<collection>__<field>.csv`, keyed by `parent_id` = the parent's `id`, plus `position`). Lists of scalars
(media_keys, app_types, …) stay in the parent row as JSON text; dicts (engagement, settings, author) are
flattened to dotted columns. Every JSON leaf therefore has a column.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import row, without, write_standard_outputs
from .endpoints import ENDPOINT_URLS, WHAT
from .schemas import COLLECTION_OF, StudiosDataset

CHILD_LISTS: dict[str, tuple[str, ...]] = {
    "apps": ("media",),
    "games": ("media",),
    "skills": ("media",),
    "employees": ("media", "features"),
    "playable_presets": ("media",),
    "influencer_options": ("media",),
    "gallery_items": ("media", "inputs"),
}
# engagement sums for the summary: collection -> {label: dotted field}
ENGAGEMENT_FIELDS: dict[str, dict[str, str]] = {
    "apps": {"views": "engagement.views", "likes": "engagement.likes", "dislikes": "engagement.dislikes",
             "remixes": "engagement.remixes"},
    "games": {"plays": "plays", "unique_players": "unique_players", "remixes": "remixes"},
    "skills": {"installs": "installs", "unique_users": "unique_users", "usage": "usage"},
    "employees": {"installs": "installs", "unique_users": "unique_users", "usage": "usage"},
    "gallery_items": {"views": "engagement.views", "likes": "engagement.likes"},
    "comments": {"likes": "likes", "replies": "replies"},
}


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def _get(d: dict, path: str) -> Any:
    for p in path.split("."):
        d = d.get(p) if isinstance(d, dict) else None
    return d


def _summary(ds: dict, rm: RunMeta) -> dict:
    counts = {c: len(ds[c]) for c in COLLECTION_OF.values() if ds.get(c)}
    by: dict[str, dict[str, int]] = {}

    def cat(name: str, values) -> None:
        c = Counter(str(v) for v in values if v is not None)
        if c:
            by[name] = dict(c.most_common())

    cat("app.category", [x["category"] for x in ds["apps"]])
    cat("app.app_type", [x["app_type"] for x in ds["apps"]])
    cat("game.category", [x["category"] for x in ds["games"]])
    cat("employee.category", [x["category"] for x in ds["employees"]])
    cat("playable_preset.category", [x["category"] for x in ds["playable_presets"]])
    cat("influencer_option.subcategory", [x["subcategory_key"] for x in ds["influencer_options"]])
    cat("gallery_item.studio", [x["studio"] for x in ds["gallery_items"]])
    cat("gallery_item.job_set_type", [x["job_set_type"] for x in ds["gallery_items"]])
    cat("gallery_item.feed", [x["feed"] for x in ds["gallery_items"]])
    eng: dict[str, dict[str, int]] = {}
    for coll, fields in ENGAGEMENT_FIELDS.items():
        sums = {k: sum(v for x in ds.get(coll) or [] if isinstance(v := _get(x, f), int)) for k, f in fields.items()}
        if ds.get(coll):
            eng[coll] = sums
    keys = {x.get("generation_key") for c in COLLECTION_OF.values() for x in ds.get(c) or []
            if isinstance(x, dict) and x.get("generation_key")}
    return {"counts": counts, "totals_available": dict(rm.totals), "by_source": by, "generation_keys": len(keys),
            "engagement": eng}


def build_dataset(entities: dict[str, list[dict]], sel: Any, rm: RunMeta) -> dict:
    ds: dict[str, Any] = {c: [] for c in COLLECTION_OF.values()}
    for kind, coll in COLLECTION_OF.items():
        ds[coll] = [_strip(e) for e in entities.get(kind, [])]
    for coll in ("apps", "games", "skills", "employees"):
        ds[coll].sort(key=lambda x: (x["rank"] if x["rank"] is not None else 10**9, x["id"]))
    ds["app_categories"].sort(key=lambda x: (x["position"] or 0, x["slug"]))
    ds["playable_presets"].sort(key=lambda x: (-(x["priority"] or 0), x["preset_id"]))
    ds["influencer_options"].sort(key=lambda x: (x["category_key"], x["subcategory_key"], x["position"]))
    ds["gallery_items"].sort(key=lambda x: (x["studio"], x["feed"], x["rank"] or 0, x["job_id"]))
    ds["comments"].sort(key=lambda x: (x["publication_id"], x["created_at"] or "", x["comment_id"]))
    summary = _summary(ds, rm)
    endpoints = {ep: ENDPOINT_URLS[ep] for w in sel.resolve() for ep in WHAT[w][1]}
    meta = make_meta("studios", sel, rm, counts=summary["counts"], endpoints=endpoints,
                     totals_available=summary["totals_available"])
    full = {"schema_version": 1, "meta": meta, "summary": summary, **ds}
    return StudiosDataset.model_validate(full).model_dump(mode="json")


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    tables: dict[str, tuple[list[dict], list[str]]] = {}
    for coll in COLLECTION_OF.values():
        rows = ds.get(coll) or []
        children = CHILD_LISTS.get(coll, ())
        tables[coll] = ([row(without(r, *children)) for r in rows], ["id"])
        for f in children:
            child_rows = []
            for r in rows:
                for i, c in enumerate(r.get(f) or []):
                    child_rows.append(row(c if isinstance(c, dict) else {"value": c}, parent_id=r["id"], position=i))
            tables[f"{coll}__{f}"] = (child_rows, ["parent_id", "position"])
    return tables


def _summary_md(ds: dict) -> str:
    s = ds["summary"]
    lines = ["# Studios dataset", "", f"Run `{ds['meta'].get('run_id')}` — scraped {ds['meta']['scraped_at']}", "",
             "| collection | rows |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s["counts"].items()]
    lines += ["", f"Generation keys (for `scripts/merge_generations.py`): {s['generation_keys']}", "",
              "Totals reported by the APIs: " + ", ".join(f"{k}={v}" for k, v in s["totals_available"].items()), ""]
    if s.get("engagement"):
        lines += ["Engagement sums: " + "; ".join(f"{c}: " + ", ".join(f"{k}={v}" for k, v in e.items())
                                                 for c, e in s["engagement"].items()), ""]
    if ds["meta"].get("limits_hit"):
        lines += ["Limits hit:", *[f"- {x}" for x in ds["meta"]["limits_hit"]], ""]
    return "\n".join(lines)


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    parts = {c: ds[c] for c in COLLECTION_OF.values() if ds.get(c)}
    parts["summary"] = ds["summary"]
    return write_standard_outputs(ds, out_dir, json_parts=parts, csv_tables=csv_tables(ds),
                                  dataset_model=StudiosDataset, summary_md=_summary_md(ds))
