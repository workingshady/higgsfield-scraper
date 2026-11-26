"""Assemble the validated ShowcaseDataset and write its outputs (JSON parts, complete CSVs, summary.md).

CSV layout: one table per collection (`<collection>.csv`, child lists removed) + one table per child list
(`<collection>__<field>.csv`, keyed by `parent_id` = the parent's `id`, plus `position`). Lists of scalars
(media_keys, tools, variant_ids, …) stay in the parent row as JSON text. Every JSON leaf therefore has a column.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import row, without, write_standard_outputs
from .endpoints import ENDPOINT_URLS, WHAT
from .schemas import COLLECTION_OF, ShowcaseDataset

# collection -> child list fields that get their own CSV table
CHILD_LISTS: dict[str, tuple[str, ...]] = {
    "editing_room_examples": ("media", "edits"),
    "editing_room_projects": ("edits", "scenes"),
    "editing_room_renders": ("media",),
    "property_studio_examples": ("media",),
    "explore_variants": ("media", "inputs"),
    "effect_samples": ("media", "inputs"),
    "api_models": ("parameters", "prices"),
    "cinema_controls": ("media", "segments"),
    "faceless_showcases": ("media",),
    "intone_examples": ("media",),
    "seedance_presets": ("media",),
    "motion_control_presets": ("media",),
}
# nested lists inside a child row (e.g. project edit references) become JSON text via flatten()


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def _summary(ds: dict, rm: RunMeta, sel: Any) -> dict:
    counts = {c: len(ds[c]) for c in COLLECTION_OF.values() if ds.get(c)}
    by: dict[str, dict[str, int]] = {}

    def cat(name: str, values) -> None:
        c = Counter(str(v) for v in values if v is not None)
        if c:
            by[name] = dict(c.most_common())

    cat("explore_item.feed_source", [x["feed_source"] for x in ds["explore_items"]])
    cat("explore_item.job_set_type", [x["job_set_type"] for x in ds["explore_items"]])
    cat("explore_variant.variant_type", [x["variant_type"] for x in ds["explore_variants"]])
    cat("effect_sample.preset_slug", [x["preset_slug"] for x in ds["effect_samples"]])
    cat("api_model.vendor", [x["vendor"] for x in ds["api_models"]])
    cat("property_studio_example.format", [x["format"] for x in ds["property_studio_examples"]])
    cat("cinema_control.group", [x["group"] for x in ds["cinema_controls"]])
    cat("editing_room_render.tool", [x["tool"] for x in ds["editing_room_renders"]])
    keys = {x.get("generation_key") for c in COLLECTION_OF.values() for x in ds.get(c) or []
            if isinstance(x, dict) and x.get("generation_key")}
    login = {}
    for w, (_, _, is_login) in WHAT.items():
        if not is_login:
            continue
        if ds.get("seasons"):
            login[w] = "fetched"
        elif w in sel.resolve():
            login[w] = "skipped (no session, --auth off or HTTP 401)"
        else:
            login[w] = "not selected (login-only, per-user: opt in with --what season)"
    return {"counts": counts, "totals_available": dict(rm.totals), "by_source": by, "generation_keys": len(keys),
            "login": login}


def build_dataset(entities: dict[str, list[dict]], sel: Any, rm: RunMeta) -> dict:
    ds: dict[str, Any] = {c: [] for c in COLLECTION_OF.values()}
    for kind, coll in COLLECTION_OF.items():
        ds[coll] = [_strip(e) for e in entities.get(kind, [])]
    ds["explore_items"].sort(key=lambda x: (x["feed_source"], -(x["priority"] or 0), x["item_id"]))
    ds["api_models"].sort(key=lambda x: x["endpoint_id"])
    ds["property_studio_examples"].sort(key=lambda x: x["preset_index"])
    summary = _summary(ds, rm, sel)
    endpoints = {ep: ENDPOINT_URLS[ep] for w in sel.resolve() for ep in WHAT[w][1]}
    meta = make_meta("showcase", sel, rm, counts=summary["counts"], endpoints=endpoints,
                     totals_available=summary["totals_available"])
    full = {"schema_version": 1, "meta": meta, "summary": summary, **ds}
    return ShowcaseDataset.model_validate(full).model_dump(mode="json")


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
    lines = ["# Showcase dataset", "", f"Run `{ds['meta'].get('run_id')}` — scraped {ds['meta']['scraped_at']}", "",
             "| collection | rows |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s["counts"].items()]
    lines += ["", f"Generation keys (for `scripts/merge_generations.py`): {s['generation_keys']}", "",
              "Totals reported by the APIs: " + ", ".join(f"{k}={v}" for k, v in s["totals_available"].items()), ""]
    if s.get("login"):
        lines += ["Login-only parts: " + ", ".join(f"{k}: {v}" for k, v in s["login"].items()), ""]
    if ds["meta"].get("limits_hit"):
        lines += ["Limits hit:", *[f"- {x}" for x in ds["meta"]["limits_hit"]], ""]
    return "\n".join(lines)


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    parts = {c: ds[c] for c in COLLECTION_OF.values() if ds.get(c)}
    parts["summary"] = ds["summary"]
    return write_standard_outputs(ds, out_dir, json_parts=parts, csv_tables=csv_tables(ds),
                                  dataset_model=ShowcaseDataset, summary_md=_summary_md(ds))
