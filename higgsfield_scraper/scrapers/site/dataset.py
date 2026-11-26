"""Assemble the SiteDataset and write outputs (JSON parts, complete CSVs, summary.md, articles/*.md)."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import flatten, row, without, write_standard_outputs
from .endpoints import ENDPOINT_DOCS, ROOM_ENDPOINT_DOCS
from .options import Selection
from .schemas import SiteDataset, SiteDatasetExt

COLLECTIONS = {               # dataset key -> (kind, id field used in CSVs)
    "apps": ("site_app", "slug"),
    "app_categories": ("site_app_category", "slug"),
    "academy_categories": ("site_academy_category", "slug"),
    "courses": ("site_academy_course", "slug"),
    "lessons": ("site_academy_lesson", "lesson_id"),
    "mcp_skills": ("site_mcp_skill", "slug"),
    "mcp_bundles": ("site_mcp_bundle", "slug"),
    "original_series": ("site_original_series", "slug"),
    "original_episodes": ("site_original_episode", "episode_id"),
    "mixed_media_presets": ("site_mixed_media_preset", "preset_id"),
    "landings": ("site_landing", "page_id"),
    "promo_events": ("site_promo_event", "event_id"),
    "business_unlim_offers": ("site_business_unlim_offer", "offer_id"),
    "game_gifts": ("site_game_gift", "gift_id"),
}
ROOM_COLLECTIONS = {          # only in runs with --what room-list / room-content (SiteDatasetExt)
    "rooms": ("site_room", "room_id"),
    "room_items": ("site_room_item", "room_item_id"),
    "room_discussions": ("site_room_discussion", "post_id"),
}
MERGED = ("apps", "courses", "mcp_skills")         # index + page records merged by slug
EMPTY = (None, "", [], {})


def _strip_kind(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def merge_by_slug(records: list[dict]) -> list[dict]:
    """Page record wins; empty fields are filled from index records; list fields of index cards are unioned."""
    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["slug"], []).append(r)
    out = []
    for slug, rs in groups.items():
        rs.sort(key=lambda r: 0 if r.get("record_source") == "page" else 1)
        base = dict(rs[0])
        for other in rs[1:]:
            for k, v in other.items():
                if k in ("record_key", "record_source", "source", "extra"):
                    continue
                if k in ("category_slugs", "tags") and isinstance(v, list):
                    base[k] = list(dict.fromkeys((base.get(k) or []) + v))
                elif base.get(k) in EMPTY and v not in EMPTY:
                    base[k] = v
            base["extra"] = {**(other.get("extra") or {}), **(base.get("extra") or {})}
        base["record_key"] = f"{slug}@{base.get('record_source')}"
        out.append(base)
    return out


def build_dataset(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta) -> dict:
    data: dict[str, list[dict]] = {c: [_strip_kind(e) for e in entities.get(kind, [])]
                                   for c, (kind, _id) in COLLECTIONS.items()}
    for c in MERGED:
        data[c] = merge_by_slug(data[c])

    bundles_of: dict[str, list[str]] = {}
    for b in data["mcp_bundles"]:
        for s in b.get("skill_slugs") or []:
            bundles_of.setdefault(s, []).append(b["slug"])
    for s in data["mcp_skills"]:
        s["bundle_slugs"] = sorted(set(s.get("bundle_slugs") or []) | set(bundles_of.get(s["slug"], [])))

    cats: dict[str, list[str]] = {}
    for c in data["app_categories"]:
        for slug in c.get("app_slugs") or []:
            cats.setdefault(slug, []).append(c["slug"])
    for a in data["apps"]:
        a["category_slugs"] = list(dict.fromkeys((a.get("category_slugs") or []) + cats.get(a["slug"], [])))

    data["apps"].sort(key=lambda a: a["slug"])
    data["app_categories"].sort(key=lambda c: (c.get("priority") if c.get("priority") is not None else 999, c["slug"]))
    data["courses"].sort(key=lambda c: (c.get("featured_position") if c.get("featured_position") is not None else 999,
                                        c["slug"]))
    data["lessons"].sort(key=lambda x: (x["course_slug"], x.get("position") or 999, x["slug"]))
    data["mcp_skills"].sort(key=lambda s: s["slug"])
    data["mcp_bundles"].sort(key=lambda b: (b.get("all_presets_order") or 999, b["slug"]))
    data["original_series"].sort(key=lambda s: -(s.get("views") or 0))
    data["original_episodes"].sort(key=lambda e: (e["series_slug"], e["slug"]))
    data["landings"].sort(key=lambda x: (x["page_type"], x["path"]))
    data["promo_events"].sort(key=lambda x: (str(x.get("starts_at") or ""), x["event_id"]))

    def cost(a: dict) -> Optional[str]:
        lo, hi = a.get("min_cost_credits"), a.get("max_cost_credits")
        return None if lo is None else (str(lo) if lo == hi else f"{lo}..{hi}")

    summary = {
        "apps_by_category": dict(Counter(c for a in data["apps"] for c in (a.get("category_slugs") or ["none"]))),
        "app_cost_credits": {a["slug"]: cost(a) for a in data["apps"] if a.get("templates")},
        "lessons_by_course": dict(Counter(x["course_slug"] for x in data["lessons"])),
        "landings_by_type": dict(Counter(x["page_type"] for x in data["landings"])),
        "words_total": sum(int(x.get("word_count") or 0) for c in ("lessons", "landings") for x in data[c]),
        "with_content": {c: sum(1 for x in data[c] if x.get("content_text")) for c in ("lessons", "landings")},
    }
    counts = {c: len(v) for c, v in data.items()}
    warnings = []
    if sel.wants("landings") and not data["landings"] and sel.with_content:
        warnings.append("no landing pages parsed")
    endpoints = dict(ENDPOINT_DOCS)
    rooms = _room_collections(entities) if sel.rooms_api else None
    if rooms is not None:
        counts.update({c: len(v) for c, v in rooms.items()})
        endpoints.update(ROOM_ENDPOINT_DOCS)
    meta = make_meta("site", sel, rm, counts=counts, endpoints=endpoints, totals_available=dict(rm.totals),
                     warnings=warnings)
    if rooms is None:
        ds = SiteDataset.model_validate({"schema_version": 1, "meta": meta, **data, "summary": summary})
    else:
        ds = SiteDatasetExt.model_validate({"schema_version": 1, "meta": meta, **data, **rooms, "summary": summary})
    return ds.model_dump(mode="json")


def _room_collections(entities: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Rooms (+ room-stats merged in), room works and room discussions."""
    stats = {e["room_id"]: e for e in entities.get("site_room_stats", [])}
    out = {c: [_strip_kind(e) for e in entities.get(kind, [])] for c, (kind, _id) in ROOM_COLLECTIONS.items()}
    for r in out["rooms"]:
        st = stats.get(r["room_id"]) or {}
        r["posts_count"] = st.get("posts", r.get("posts_count"))
        r["discussions_count"] = st.get("discussions", r.get("discussions_count"))
    slug_of = {r["room_id"]: r["slug"] for r in out["rooms"]}
    for c in ("room_items", "room_discussions"):
        for x in out[c]:
            x["room_slug"] = x.get("room_slug") or slug_of.get(x.get("room_id"))
    out["rooms"].sort(key=lambda r: (r.get("position") is None, r.get("position") or 0, r["slug"]))
    out["room_items"].sort(key=lambda x: (x.get("room_slug") or "", x.get("position") or 0))
    out["room_discussions"].sort(key=lambda x: (x.get("room_slug") or "", str(x.get("created_at") or "")))
    return out


# ------------------------------------------------------------------ CSV tables

BODY_LISTS = ("headings", "links", "images")
CHILDREN = {   # collection -> (csv prefix, id field, [child list fields with their own table])
    "apps": ("app", "slug", ["templates", "landing_faqs"]),
    "courses": ("course", "slug", ["lessons", "objectives", "authors"]),
    "lessons": ("lesson", "lesson_id", ["resources", *BODY_LISTS]),
    "mcp_skills": ("mcp_skill", "slug", ["agents", "example_conversation", "medias"]),
    "mcp_bundles": ("mcp_bundle", "slug", ["agents"]),
    "original_episodes": ("episode", "episode_id", ["episodes"]),
    "mixed_media_presets": ("mixed_media", "preset_id", ["samples"]),
    "landings": ("landing", "page_id", ["how_to_steps", "faq", *BODY_LISTS]),
}
JOIN_LISTS = ("category_slugs", "tags", "categories", "app_slugs", "skill_slugs", "bundle_slugs", "skills", "models",
              "languages", "tools", "sections", "breadcrumbs", "ld_types", "recommended_slugs")


def _main_row(x: dict, drop: list[str]) -> dict:
    r = row(without(x, *drop, *JOIN_LISTS))
    for k in JOIN_LISTS:
        if k in x:
            r[k] = "|".join(map(str, x.get(k) or []))
    return r


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    t: dict[str, tuple[list[dict], list[str]]] = {}
    for coll, (kind, idf) in COLLECTIONS.items():
        prefix, _, kids = CHILDREN.get(coll, ("", idf, []))
        t[coll] = ([_main_row(x, kids) for x in ds[coll]], [idf, "slug", "title", "name", "url"])
        for child in kids:
            t[f"{prefix}_{child}"] = ([row(c if isinstance(c, dict) else {"value": c}, **{idf: x[idf], "position": i})
                                       for x in ds[coll] for i, c in enumerate(x.get(child) or [])], [idf, "position"])
    return t


# ------------------------------------------------------------------ summary + markdown articles

def summary_md(ds: dict) -> str:
    m, s = ds["meta"], ds["summary"]
    lines = [f"# Higgsfield site pages — {m.get('label') or m.get('run_id') or ''}", "",
             f"Scraped at {m['scraped_at']}. Options: `{m['options']}`.", "", "| collection | items |", "|---|---:|"]
    lines += [f"| {c} | {len(ds[c])} |" for c in COLLECTIONS]
    lines += ["", f"Words of lesson/landing text: {s['words_total']:,}.", ""]
    if s["app_cost_credits"]:
        lines += ["## App cost (credits per generation, from the app's templates)", "", "| app | credits |", "|---|---:|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(s["app_cost_credits"].items())]
        lines.append("")
    if s["lessons_by_course"]:
        lines += ["## Lessons by course", ""] + [f"- {k}: {v}" for k, v in sorted(s["lessons_by_course"].items())]
        lines.append("")
    if m.get("totals_available"):
        lines += ["## Totals reported by the sources", ""] + [f"- {k}: {v}" for k, v in m["totals_available"].items()]
        lines.append("")
    if m.get("limits_hit") or m.get("warnings"):
        lines += ["## Limits / warnings", ""] + [f"- {x}" for x in m.get("limits_hit", []) + m.get("warnings", [])]
        lines.append("")
    lines += ["Readable copies of lessons and landing pages: `articles/<collection>/<slug>.md`.", ""]
    return "\n".join(lines)


def _fname(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:120] or "item"


def article_markdown(item: dict, coll: str) -> str:
    fm = {"title": item.get("title") or item.get("h1") or (item.get("seo") or {}).get("page_title"),
          "url": item.get("url"), "id": item.get("lesson_id") or item.get("page_id"),
          "course": item.get("course_title"), "position": item.get("position"), "video": item.get("video_url"),
          "page_type": item.get("page_type"), "word_count": item.get("word_count"), "collection": coll}
    out = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items() if v not in (None, "")]
    out += ["---", ""]
    md = item.get("content_markdown") or ""
    if not md.lstrip().startswith("# "):
        out += [f"# {fm['title'] or item.get('slug') or item.get('path') or ''}", ""]
    out.append(md or "_(no text in this run — use --with-content)_")
    for r in item.get("resources") or []:
        out += ["", f"- Resource: [{r.get('name') or 'file'}]({r.get('download_url')})"]
    if item.get("faq"):
        out += ["", "## FAQ", ""]
        for f in item["faq"]:
            out += [f"### {f['question']}", "", f.get("answer_text") or "", ""]
    return "\n".join(out).rstrip() + "\n"


def write_articles(ds: dict, out_dir: Path) -> list[Path]:
    files = []
    for coll in ("lessons", "landings"):
        d = out_dir / "articles" / coll
        for it in ds[coll]:
            if coll == "lessons":
                name = _fname(f"{it['course_slug']}__{it.get('position') or 0:02d}__{it['slug']}")
            else:
                name = _fname(it["path"].strip("/").replace("/", "__") or "home")
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{name}.md"
            p.write_text(article_markdown(it, coll), encoding="utf-8")
            files.append(p)
    return files


def room_csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    disc = ds["room_discussions"]
    return {
        "rooms": ([_main_row(r, []) for r in ds["rooms"]], ["room_id", "slug", "name", "url"]),
        "room_items": ([_main_row(x, []) for x in ds["room_items"]],
                       ["room_item_id", "room_id", "room_slug", "item_type", "item_id"]),
        "room_discussions": ([flatten(without(x, "media")) for x in disc], ["post_id", "room_id", "room_slug"]),
        "room_discussion_media": ([row(m, post_id=x["post_id"], room_id=x.get("room_id")) for x in disc
                                   for m in x.get("media") or []], ["post_id", "room_id", "index"]),
    }


def room_summary_md(ds: dict) -> str:
    rooms = ds["rooms"]
    lines = ["## Community rooms (fnf-community API)", "", "| collection | items |", "|---|---:|"]
    lines += [f"| {c} | {len(ds[c])} |" for c in ROOM_COLLECTIONS]
    if rooms:
        lines += ["", "| room | members | works | posts | discussions | call |", "|---|---:|---:|---:|---:|---|"]
        for r in sorted(rooms, key=lambda r: -(r.get("followers_count") or 0))[:30]:
            lines.append(f"| {r['slug']} | {r.get('followers_count')} | {r.get('works_count')} | "
                         f"{r.get('posts_count')} | {r.get('discussions_count')} | {r.get('call_status')} |")
    lines.append("")
    return "\n".join(lines)


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    parts: dict[str, Any] = {c: ds[c] for c in COLLECTIONS}
    parts["summary"] = ds["summary"]
    tables, model, md = csv_tables(ds), SiteDataset, summary_md(ds)
    if "rooms" in ds:              # --what room-list / room-content (SiteDatasetExt)
        parts.update({c: ds[c] for c in ROOM_COLLECTIONS})
        tables.update(room_csv_tables(ds))
        model, md = SiteDatasetExt, md + "\n" + room_summary_md(ds)
    files = write_standard_outputs(ds, out_dir, json_parts=parts, csv_tables=tables,
                                   dataset_model=model, summary_md=md)
    if (ds["meta"].get("options") or {}).get("write_markdown", True):
        files += write_articles(ds, out_dir)
    return files
