"""Assemble the validated community dataset (+ optional cost estimates) and write JSON / complete CSVs / summary."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import flatten, row, without, write_standard_outputs
from ...estimate import EstimatedCost, formula_version_in_schema, skipped
from .endpoints import (COMMUNITY_BASE, CREATORS_PATH, ENTITY_COMMENTS_PATH, FEED_PATH, FEED_PATHS, POSTS_PATH,
                        SHOTS_PATH, TALENTS_PATH)
from .endpoints import CMS_API_BASE, EXTRA_URLS, GALLERY_FEEDS, MUSIC_CARD_OPTIONS_PATH
from .endpoints import FEED_ONGOING_PATH
from .options import Selection
from .schemas import CommunityDataset, CommunityDatasetExt, CommunityDatasetGallery

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SINGLE_INPUT_PARAMS = {"input_image", "image_reference", "custom_reference", "draw_input_image", "input_audio",
                       "input_video", "end_image", "start_image"}
TOP_SETTINGS = ("resolution", "aspect_ratio", "quality", "duration", "batch_size", "model", "mode", "output_format",
                "enhance_prompt", "generate_audio", "use_unlim")


# ------------------------------------------------------------------ cost estimation
def reconstruct_params(gen: dict) -> dict:
    """Best-effort original `params` for the estimator (exact when --with-raw-params kept them)."""
    if gen.get("raw_params"):
        return dict(gen["raw_params"])
    p: dict[str, Any] = dict(gen.get("params_extra") or {})
    p.update({k: v for k, v in (gen.get("settings") or {}).items() if v is not None})
    for k in ("prompt", "negative_prompt"):
        if gen.get(k) is not None:
            p[k] = gen[k]
    groups: dict[str, list] = defaultdict(list)
    for i in gen.get("inputs") or []:
        obj = {k: i.get(k) for k in ("id", "url", "type", "name", "width", "height") if i.get(k) is not None}
        obj.update({k: v for k, v in (i.get("extra") or {}).items() if not k.startswith("_")})
        if i["param"] == "medias":
            groups["medias"].append({"role": i.get("role"), "data": obj})
        else:
            groups[i["param"]].append(obj)
    for k, v in groups.items():
        p[k] = v[0] if k in SINGLE_INPUT_PARAMS else v
    return p


def _cost_context(entities: dict[str, list[dict]], sel: Selection) -> tuple[Any, dict]:
    """-> (estimator or None, cost_basis summary dict)."""
    from ... import estimate
    bases = {b["basis_id"]: b for b in entities.get("community_cost_basis", [])}
    jc, usd = bases.get("job_costs"), bases.get("usd_reference")
    notes: list[str] = []
    summary = {"priced_models": len((jc or {}).get("job_costs", {}).get("data") or []) if jc else None,
               "usd_per_credit": (usd or {}).get("usd_per_credit"), "usd_reference": (usd or {}).get("usd_reference"),
               "fetched_at": (jc or {}).get("source", {}).get("fetched_at"),
               "estimator_available": estimate.CostEstimator is not None, "notes": notes}
    if usd:
        notes.extend(usd.get("notes") or [])
    if estimate.CostEstimator is None:
        notes.append("higgsfield_scraper.estimate.CostEstimator not available; estimates skipped")
        return None, summary
    if not jc:
        notes.append("/job-sets/costs not fetched; estimates skipped")
        return None, summary
    try:
        cls = estimate.CostEstimator if sel.estimate_version == 1 else estimate.estimator_class(sel.estimate_version)
        est = cls.from_job_costs_body(jc["job_costs"], usd_per_credit=summary["usd_per_credit"],
                                      usd_reference=summary["usd_reference"])
        if sel.estimate_version != 1:
            notes.append(f"estimator formula version {sel.estimate_version} (--estimate-version; "
                         "docs/COST_FORMULAS.md §8)")
    except Exception as e:  # never lose the dataset because of the optional estimate
        log.exception("building the cost estimator failed")
        notes.append(f"estimator init failed: {e!r}")
        return None, summary
    vir = bases.get("viral_presets")
    if vir:
        try:
            est.with_viral_presets(vir.get("body") or {})
            notes.append(f"viral preset price matrices for {len(est.viral)} presets")
        except Exception as e:  # optional
            log.exception("building viral preset prices failed")
            notes.append(f"viral preset prices failed: {e!r}")
    cmp, ben = bases.get("compare"), bases.get("benefits")
    if cmp and ben:
        try:
            est.with_compare_fallback(cmp.get("body") or {}, ben.get("body") or {})
            notes.append(f"comparison-table fallback prices for {len(est.fallback)} unlisted models: "
                         + ", ".join(sorted(est.fallback)))
        except Exception as e:  # optional
            log.exception("building the comparison-table fallback failed")
            notes.append(f"comparison fallback failed: {e!r}")
    return est, summary


def attach_estimates(gens: list[dict], est: Any, sel: Selection, reason: Optional[str]) -> None:
    for g in gens:
        if not sel.estimate_for(g.get("media_type")):
            g["estimated_cost"] = skipped(f"media_type {g.get('media_type')} not selected by "
                                          f"--estimate-cost {sel.estimate_cost}")
            continue
        if est is None:
            g["estimated_cost"] = skipped(reason or "pricing data unavailable")
            continue
        try:
            raw = est.estimate(job_set_type=g.get("job_set_type"), params=reconstruct_params(g),
                               media_type=g.get("media_type"))
            g["estimated_cost"] = EstimatedCost.model_validate(raw).model_dump(mode="json")
        except Exception as e:
            g["estimated_cost"] = EstimatedCost(status="unpriced", notes=[f"estimator error: {e!r}"]).model_dump(
                mode="json")


# ------------------------------------------------------------------ stats
def _top(counter: Counter, n: Optional[int] = None) -> dict[str, int]:
    return {str(k): v for k, v in counter.most_common(n)}


def build_stats(gens: list[dict], cost_basis: Optional[dict], sel: Selection) -> dict:
    c = defaultdict(Counter)
    settings_vals: dict[str, Counter] = defaultdict(Counter)
    credits_by_model: dict[str, float] = defaultdict(float)
    credits_total, usd_total, any_usd = 0.0, 0.0, False
    for g in gens:
        c["feed"][g["feed"]] += 1
        c["jst"][g.get("job_set_type") or "?"] += 1
        c["media"][g["media_type"]] += 1
        c["status"][g.get("status") or "?"] += 1
        s = g.get("settings") or {}
        c["res"][s.get("resolution") or "unset"] += 1
        c["ar"][s.get("aspect_ratio") or "unset"] += 1
        for k in TOP_SETTINGS:
            if s.get(k) is not None:
                settings_vals[k][str(s[k])] += 1
        c["extra"].update((g.get("params_extra") or {}).keys())
        c["inputs"].update(i["param"] for i in g.get("inputs") or [])
        ec = g.get("estimated_cost")
        if ec:
            c["est"][ec["status"]] += 1
            if ec.get("credits") is not None:
                credits_by_model[g.get("job_set_type") or "?"] += ec["credits"]
                credits_total += ec["credits"]
            if ec.get("usd") is not None:
                usd_total += ec["usd"]
                any_usd = True
    return {
        "generations": len(gens),
        "by_feed": _top(c["feed"]), "by_job_set_type": _top(c["jst"]), "by_media_type": _top(c["media"]),
        "by_status": _top(c["status"]), "by_resolution": _top(c["res"]), "by_aspect_ratio": _top(c["ar"]),
        "top_settings": {k: _top(v, 10) for k, v in settings_vals.items()},
        "params_extra_keys": _top(c["extra"]), "inputs_by_param": _top(c["inputs"]),
        "with_prompt": sum(1 for g in gens if g.get("prompt")),
        "with_inputs": sum(1 for g in gens if g.get("inputs")),
        "views_total": sum((g["engagement"].get("views") or 0) for g in gens),
        "likes_total": sum((g["engagement"].get("likes") or 0) for g in gens),
        "distinct_creators": len({g["creator"].get("user_id") for g in gens if g["creator"].get("user_id")}),
        "estimated_credits_by_model": {k: round(v, 4) for k, v in sorted(credits_by_model.items(),
                                                                         key=lambda kv: -kv[1])},
        "estimated_credits_total": round(credits_total, 4) if sel.estimating else None,
        "estimated_usd_total": round(usd_total, 4) if any_usd else None,
        "estimate_status": _top(c["est"]),
        "cost_basis": cost_basis,
    }


# ------------------------------------------------------------------ dataset
def build_dataset(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta) -> dict:
    strip = lambda e: without(e, "kind")  # noqa: E731
    gens = [strip(e) for e in entities.get("community_generation", [])]
    warnings: list[str] = []
    cost_basis = None
    if sel.estimating:
        est, cost_basis = _cost_context(entities, sel)
        warnings.extend(f"estimate: {n}" for n in cost_basis["notes"])
        attach_estimates(gens, est, sel, "; ".join(cost_basis["notes"]) or None)
    per_user = Counter(g["creator"].get("user_id") for g in gens)
    creators = []
    if sel.with_profiles:
        for e in entities.get("community_creator", []):
            if per_user.get(e["user_id"]):          # drop creators of items cut by --max-items / filters
                creators.append({**strip(e), "generations_in_dataset": per_user[e["user_id"]]})
    pubs = {g["publication_id"] for g in gens}
    ext = _extra_collections(entities) if sel.extra_feeds else None
    if ext is not None:      # comments of opt-in shots / feed items / posts are kept too
        pubs |= {x["shot_id"] for x in ext["shots"]} | {x["item_id"] for x in ext["feed_items"]} | \
            {x["post_id"] for x in ext["posts"]}
    # comments come from Community posts (fnf-community), not from the gallery publications above; keep a comment
    # when it belongs to a fetched publication or to a Community post thread
    comments = [strip(e) for e in entities.get("community_comment", [])
                if e["publication_id"] in pubs or e.get("thread_type") == "publication"]
    pages = [strip(e) for e in entities.get("community_page", [])]
    totals: dict[str, Optional[int]] = {}
    for p in pages:                               # first page of a feed: total = whole (filtered) feed size
        if p["cursor"] is None and p["total"] is not None:
            totals.setdefault(p["feed"], p["total"])
    totals.update(rm.totals or {})
    endpoints = {f: f"https://fnf-api-gw.higgsfield.ai/fnf{FEED_PATHS[f]}" for f in sel.feeds}
    if sel.detail or sel.publication_ids:
        endpoints["detail"] = "https://fnf-api-gw.higgsfield.ai/fnf/publications/{publication_id}"
    if sel.with_comments:
        endpoints["community_posts"] = "https://fnf-api-gw.higgsfield.ai/fnf-community/publications/feed"
        endpoints["comments"] = "https://fnf-api-gw.higgsfield.ai/fnf-community/publications/{publication_id}/comments"
    if sel.estimating:
        endpoints["job_costs"] = "https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs"
        endpoints["plans"] = "https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans"
    counts = {"generations": len(gens), "creators": len(creators), "comments": len(comments), "pages": len(pages)}
    if ext is not None:      # only runs with opt-in feeds get the extra counts / endpoints / collections
        counts.update({k: len(v) for k, v in ext.items()})
        endpoints.update(_extra_endpoints(sel))
    meta = make_meta("community", sel, rm, counts=counts,
                     endpoints=endpoints, totals_available=totals, warnings=warnings)
    ds = {"schema_version": SCHEMA_VERSION, "meta": meta, "generations": gens, "creators": creators,
          "comments": comments, "pages": pages, "stats": build_stats(gens, cost_basis, sel)}
    if ext is None:
        return CommunityDataset.model_validate(ds).model_dump(mode="json")
    ds.update(ext)
    ds["extra_stats"] = _extra_stats(ext, comments)
    if not any(f in GALLERY_FEEDS for f in sel.extra_feeds):
        return CommunityDatasetExt.model_validate(ds).model_dump(mode="json")
    gal = _gallery_collections(entities)          # only runs with an opt-in gallery / template source
    ds["meta"]["counts"].update({k: len(v) for k, v in gal.items()})
    ds.update(gal)
    ds["gallery_stats"] = _gallery_stats(gal)
    return CommunityDatasetGallery.model_validate(ds).model_dump(mode="json")


# ------------------------------------------------------------------ opt-in Community pages
EXTRA_COLLECTIONS = {"shots": "community_shot", "posts": "community_post", "feed_items": "community_feed_item",
                     "creator_stats": "community_creator_stats", "creator_works": "community_creator_work",
                     "shot_model_facets": "community_shot_model_facet",
                     "feed_categories": "community_feed_category"}


def _extra_collections(entities: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {c: [without(e, "kind") for e in entities.get(k, [])] for c, k in EXTRA_COLLECTIONS.items()}
    out["feed_items"].sort(key=lambda x: (x.get("position") is None, x.get("position") or 0))
    out["creator_stats"].sort(key=lambda x: (x["listing"], x.get("position") is None, x.get("position") or 0))
    # creator works: only those of kept creator cards (a card cut by --max-items drops its works), card order + rank
    order = {c["record_id"]: n for n, c in enumerate(out["creator_stats"])}
    out["creator_works"] = sorted((w for w in out["creator_works"] if w["record_id"] in order),
                                  key=lambda w: (order[w["record_id"]], w["rank"]))
    per_model = Counter(x.get("job_set_type") for x in out["shots"])
    out["shot_model_facets"] = sorted(({**f, "shots_in_run": per_model.get(f["model"], 0)}
                                       for f in out["shot_model_facets"]),
                                      key=lambda x: (x.get("position") is None, x.get("position") or 0, x["model"]))
    out["feed_categories"].sort(key=lambda x: (x["source_list"], x.get("position") is None, x.get("position") or 0))
    return out


def _extra_endpoints(sel: Selection) -> dict[str, str]:
    fnf = "https://fnf-api-gw.higgsfield.ai/fnf"
    urls = {"shots": COMMUNITY_BASE + SHOTS_PATH, "posts": COMMUNITY_BASE + POSTS_PATH, "feed": COMMUNITY_BASE + FEED_PATH,
            "creators": fnf + CREATORS_PATH, "talents": fnf + TALENTS_PATH}
    urls.update(EXTRA_URLS)
    out = {f: urls[f] for f in sel.extra_feeds}
    if "feed-categories" in sel.extra_feeds:
        out["feed-ongoing"] = COMMUNITY_BASE + FEED_ONGOING_PATH
    if "music-cards" in sel.extra_feeds:
        out["music-cards-options"] = CMS_API_BASE + MUSIC_CARD_OPTIONS_PATH
    if sel.with_comments:
        out["entity_comments"] = COMMUNITY_BASE + ENTITY_COMMENTS_PATH
    return out


def _extra_stats(ext: dict[str, list[dict]], comments: list[dict]) -> dict:
    return {"shots": len(ext["shots"]), "posts": len(ext["posts"]), "feed_items": len(ext["feed_items"]),
            "creator_stats": len(ext["creator_stats"]),
            "feed_items_by_type": _top(Counter(x["item_type"] for x in ext["feed_items"])),
            "shots_by_job_set_type": _top(Counter(x.get("job_set_type") or "?" for x in ext["shots"])),
            "shots_by_media_type": _top(Counter(x["media_type"] for x in ext["shots"])),
            "comments_by_thread_type": _top(Counter(c.get("thread_type") or "?" for c in comments)),
            "creator_works": len(ext["creator_works"]),
            "creator_works_by_type": _top(Counter(w["item_type"] for w in ext["creator_works"])),
            "shot_model_facets": len(ext["shot_model_facets"]), "feed_categories": len(ext["feed_categories"])}


def extra_csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    """Complete CSVs of the opt-in collections (one row per record + child tables for nested lists)."""
    posts, creators = ds["posts"], ds["creator_stats"]
    works = {(w["record_id"], w["rank"]): w for w in ds.get("creator_works") or []}
    wkey = lambda w: {"work_id": w["work_id"], "record_id": w["record_id"], "rank": w["rank"]}  # noqa: E731

    def work_row(c: dict, i: int, w: dict) -> dict:
        """The creator_works row (light card entry) + every column of the full work (never overwriting)."""
        r = row(w, record_id=c["record_id"], user_id=c["user_id"], listing=c["listing"], position=i)
        full = works.get((c["record_id"], i))
        if full:
            r.update({k: v for k, v in flatten(without(full, "inputs", "results", "gallery_media")).items()
                      if k not in r})
        return r

    full_works = ds.get("creator_works") or []
    feed_items = ds["feed_items"]
    return {
        "shots": ([flatten(x) for x in ds["shots"]], ["shot_id", "generation_id", "job_set_type", "media_type"]),
        "posts": ([flatten(without(x, "media")) for x in posts], ["post_id", "title", "text"]),
        "post_media": ([row(m, post_id=p["post_id"]) for p in posts for m in p["media"]], ["post_id", "index", "type"]),
        "feed_items": ([flatten(x) for x in feed_items],          # media[] as JSON + one row each below
                       ["feed_item_id", "position", "item_type", "item_id"]),
        "feed_item_media": ([row(m, feed_item_id=x["feed_item_id"], item_id=x["item_id"]) for x in feed_items
                             for m in x.get("media") or []], ["feed_item_id", "item_id", "index", "type"]),
        "creator_stats": ([flatten(without(x, "works")) for x in creators], ["record_id", "listing", "position",
                                                                             "user_id"]),
        "creator_works": ([work_row(c, i, w) for c in creators for i, w in enumerate(c["works"])],
                          ["record_id", "user_id", "position"]),
        "creator_work_inputs": ([row(i, **wkey(w), job_set_type=w.get("job_set_type")) for w in full_works
                                 for i in w.get("inputs") or []], ["work_id", "record_id", "rank", "index", "param"]),
        "creator_work_results": ([row(r, **wkey(w), position=n) for w in full_works
                                  for n, r in enumerate(w.get("results") or [])],
                                 ["work_id", "record_id", "rank", "position", "name", "type", "url"]),
        "creator_work_media": ([row(m, **wkey(w)) for w in full_works for m in w.get("gallery_media") or []],
                               ["work_id", "record_id", "rank", "role", "index", "url"]),
        "shot_model_facets": ([flatten(x) for x in ds.get("shot_model_facets") or []],
                              ["facet_id", "model", "media_type", "position", "shots_in_run"]),
        "feed_categories": ([flatten(x) for x in ds.get("feed_categories") or []],
                            ["category_id", "source_list", "position", "slug", "title", "post_count"]),
        "extra_stats": ([{"dimension": k, "value": v2, "count": n} for k, v in ds["extra_stats"].items()
                         if isinstance(v, dict) for v2, n in v.items()] +
                        [{"dimension": k, "value": None, "count": v} for k, v in ds["extra_stats"].items()
                         if not isinstance(v, dict)], ["dimension", "value", "count"]),
    }


def extra_summary_md(ds: dict) -> str:
    st = ds["extra_stats"]
    lines = ["## Opt-in Community pages", "",
             _md_table([[k, st[k]] for k in ("shots", "posts", "feed_items", "creator_stats", "creator_works",
                                             "shot_model_facets", "feed_categories")], ["collection", "rows"]),
             ""]
    for title, key in (("Feed items by type", "feed_items_by_type"), ("Shots by model", "shots_by_job_set_type"),
                       ("Comments by thread type", "comments_by_thread_type"),
                       ("Creator works by type", "creator_works_by_type")):
        if st.get(key):
            lines += [f"### {title}", "", _md_table([[k, v] for k, v in list(st[key].items())[:15]],
                                                     ["value", "count"]), ""]
    lines += ["Files: `csv/shots.csv`, `csv/posts.csv` + `csv/post_media.csv`, `csv/feed_items.csv`, "
              "`csv/creator_stats.csv` + `csv/creator_works.csv` (one row per work, full fields) + "
              "`csv/creator_work_{inputs,results,media}.csv`, `csv/feed_item_media.csv`, `csv/shot_model_facets.csv`, "
              "`csv/feed_categories.csv`, `csv/extra_stats.csv` (only in runs with opt-in feeds). Creator names, bios "
              "and avatars only with --with-profiles.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ opt-in gallery / template sources
GALLERY_COLLECTIONS = {"music_cards": "community_music_card", "music_card_options": "community_music_card_option",
                       "showcase_jobs": "community_showcase_job", "collections": "community_collection",
                       "explore_cards": "community_explore_card"}
GALLERY_ORDER = {"music_cards": ("position",), "music_card_options": ("group", "position"),
                 "showcase_jobs": ("showcase_slug", "movie_index", "movie_position"), "collections": ("slug",),
                 "explore_cards": ("position",)}


def _gallery_collections(entities: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {}
    for c, k in GALLERY_COLLECTIONS.items():
        rows = [without(e, "kind") for e in entities.get(k, [])]
        rows.sort(key=lambda x: tuple((x.get(f) is None, x.get(f) if x.get(f) is not None else 0)
                                      for f in GALLERY_ORDER[c]))
        out[c] = rows
    return out


def _gallery_stats(g: dict[str, list[dict]]) -> dict:
    return {**{k: len(v) for k, v in g.items()},
            "collection_items": sum(len(c["items"]) for c in g["collections"]),
            "music_cards_by_category": _top(Counter(x.get("category") or "?" for x in g["music_cards"])),
            "showcase_jobs_by_job_set_type": _top(Counter(x.get("job_set_type") or "?" for x in g["showcase_jobs"])),
            "explore_cards_by_media_type": _top(Counter(x.get("media_type") or "?" for x in g["explore_cards"]))}


def gallery_csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    """Complete CSVs of the gallery / template collections (child tables for nested lists)."""
    cards, jobs, cols = ds["music_cards"], ds["showcase_jobs"], ds["collections"]
    jkey = lambda j: {"generation_id": j["generation_id"], "showcase_slug": j["showcase_slug"]}  # noqa: E731
    return {
        "music_cards": ([flatten(without(x, "recipients")) for x in cards], ["music_card_id", "slug", "position",
                                                                             "title"]),
        "music_card_recipients": ([row(r, music_card_id=c["music_card_id"], index=i) for c in cards
                                   for i, r in enumerate(c["recipients"])], ["music_card_id", "index"]),
        "music_card_options": ([flatten(x) for x in ds["music_card_options"]], ["option_id", "group", "key",
                                                                                 "position"]),
        "showcase_jobs": ([flatten(without(x, "inputs", "results")) for x in jobs],
                          ["generation_id", "showcase_slug", "movie_index", "movie_position", "job_set_type",
                           "prompt"]),
        "showcase_job_inputs": ([row(i, **jkey(j)) for j in jobs for i in j["inputs"]],
                                ["generation_id", "showcase_slug", "index", "param", "role", "url"]),
        "showcase_job_results": ([row(r, **jkey(j), position=n) for j in jobs for n, r in enumerate(j["results"])],
                                 ["generation_id", "showcase_slug", "position", "name", "type", "url"]),
        "collections": ([flatten(without(x, "items")) for x in cols], ["collection_id", "slug", "name"]),
        "collection_items": ([row(i, collection_id=c["collection_id"], slug=c["slug"]) for c in cols
                              for i in c["items"]], ["collection_id", "slug", "position", "motion_id", "name"]),
        "explore_cards": ([flatten(x) for x in ds["explore_cards"]], ["card_id", "position", "name"]),
        "gallery_stats": ([{"dimension": k, "value": v2, "count": n} for k, v in ds["gallery_stats"].items()
                           if isinstance(v, dict) for v2, n in v.items()] +
                          [{"dimension": k, "value": None, "count": v} for k, v in ds["gallery_stats"].items()
                           if not isinstance(v, dict)], ["dimension", "value", "count"]),
    }


def gallery_summary_md(ds: dict) -> str:
    st = ds["gallery_stats"]
    lines = ["## Opt-in galleries and templates", "",
             _md_table([[k, st[k]] for k in ("music_cards", "music_card_options", "showcase_jobs", "collections",
                                             "collection_items", "explore_cards")], ["collection", "rows"]), ""]
    for title, key in (("Music cards by category", "music_cards_by_category"),
                       ("Showcase jobs by model", "showcase_jobs_by_job_set_type"),
                       ("Explore cards by media type", "explore_cards_by_media_type")):
        if st.get(key):
            lines += [f"### {title}", "", _md_table([[k, v] for k, v in list(st[key].items())[:15]],
                                                     ["value", "count"]), ""]
    lines += ["Files: `csv/music_cards.csv` + `csv/music_card_recipients.csv`, `csv/music_card_options.csv`, "
              "`csv/showcase_jobs.csv` + `csv/showcase_job_inputs.csv` + `csv/showcase_job_results.csv`, "
              "`csv/collections.csv` + `csv/collection_items.csv`, `csv/explore_cards.csv`, `csv/gallery_stats.csv` "
              "(only in runs with these opt-in feeds). Showcase creators' names only with --with-profiles.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ outputs
def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    gens = ds["generations"]
    keys = lambda g: {"generation_id": g["generation_id"], "publication_id": g["publication_id"]}  # noqa: E731
    stats_rows = []
    for dim, v in ds["stats"].items():
        if isinstance(v, dict) and dim != "cost_basis":
            for k, n in flatten(v).items():
                stats_rows.append({"dimension": dim, "value": k, "count": n})
        elif not isinstance(v, dict):
            stats_rows.append({"dimension": dim, "value": None, "count": v})
    stats_rows += [{"dimension": f"cost_basis.{k}", "value": v, "count": None}
                   for k, v in flatten(ds["stats"].get("cost_basis") or {}, "").items() if k]
    return {
        "generations": ([flatten(g) for g in gens],
                        ["generation_id", "publication_id", "feed", "job_set_type", "media_type", "status", "prompt"]),
        "generation_inputs": ([row(i, **keys(g), job_set_type=g["job_set_type"]) for g in gens for i in g["inputs"]],
                              ["generation_id", "publication_id", "job_set_type", "index", "param", "role", "url"]),
        "generation_results": ([row(r, **keys(g), job_set_type=g["job_set_type"], position=n)
                                for g in gens for n, r in enumerate(g["results"])],
                               ["generation_id", "publication_id", "job_set_type", "position", "name", "type", "url"]),
        "creators": ([flatten(c) for c in ds["creators"]], ["user_id", "username"]),
        "comments": ([flatten(c) for c in ds["comments"]], ["comment_id", "publication_id"]),
        "pages": ([flatten(p) for p in ds["pages"]], ["page_id", "feed", "cursor", "next_cursor", "has_more"]),
        "stats": (stats_rows, ["dimension", "value", "count"]),
    }


def _md_table(rows: list[list[Any]], header: list[str]) -> str:
    esc = lambda x: ("" if x is None else str(x)).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(esc(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def summary_md(ds: dict) -> str:
    m, st, gens = ds["meta"], ds["stats"], ds["generations"]
    lines = [f"# Higgsfield community generations — {m.get('run_id') or ''}", "",
             f"Scraped at {m['scraped_at']} · feeds: {', '.join(m['options'].get('feeds') or [])} · "
             f"type: {m['options'].get('type')} · models: {', '.join(m['options'].get('models') or []) or 'all'}", "",
             _md_table([[k, v] for k, v in m["counts"].items()], ["collection", "count"]), ""]
    if m.get("totals_available"):
        lines += ["## API totals (first page of each feed, with filters)", "",
                  _md_table([[k, v] for k, v in m["totals_available"].items()], ["feed", "total"]), ""]
    by_model: dict[str, dict] = defaultdict(lambda: {"n": 0, "views": 0, "likes": 0, "media": Counter(),
                                                     "credits": 0.0, "priced": 0})
    for g in gens:
        d = by_model[g.get("job_set_type") or "?"]
        d["n"] += 1
        d["views"] += g["engagement"].get("views") or 0
        d["likes"] += g["engagement"].get("likes") or 0
        d["media"][g["media_type"]] += 1
        ec = g.get("estimated_cost") or {}
        if ec.get("credits") is not None:
            d["credits"] += ec["credits"]
            d["priced"] += 1
    est = st.get("estimated_credits_total") is not None
    rows = []
    for k, d in sorted(by_model.items(), key=lambda kv: -kv[1]["n"])[:30]:
        r = [k, d["n"], ", ".join(f"{t}:{n}" for t, n in d["media"].most_common()), round(d["views"] / d["n"], 1),
             round(d["likes"] / d["n"], 1)]
        if est:
            r += [d["priced"], round(d["credits"], 2)]
        rows.append(r)
    lines += ["## Top models (job_set_type)", "",
              _md_table(rows, ["job_set_type", "items", "media", "avg views", "avg likes"] +
                        (["priced", "est. credits"] if est else [])), ""]
    for title, key in (("Media types", "by_media_type"), ("Feeds", "by_feed"), ("Status", "by_status"),
                       ("Resolution", "by_resolution"), ("Aspect ratio", "by_aspect_ratio")):
        lines += [f"## {title}", "", _md_table([[k, v] for k, v in list(st[key].items())[:15]], ["value", "count"]), ""]
    if st.get("top_settings"):
        lines += ["## Top settings", "", _md_table(
            [[k, ", ".join(f"{v} ({n})" for v, n in list(vals.items())[:6])] for k, vals in st["top_settings"].items()],
            ["setting", "top values (count)"]), ""]
    if est:
        cb = st.get("cost_basis") or {}
        lines += ["## Estimated cost", "",
                  f"Estimated credits total: **{st['estimated_credits_total']}**"
                  + (f" · ≈ ${st['estimated_usd_total']} at {cb.get('usd_per_credit')} $/credit "
                     f"({cb.get('usd_reference')})" if st.get("estimated_usd_total") is not None else ""), "",
                  "Status counts: " + ", ".join(f"{k}={v}" for k, v in st["estimate_status"].items()), ""]
        if m["options"].get("estimate_version", 1) != 1:     # line absent on default (v1) runs
            lines += [f"Formula version: {m['options']['estimate_version']} (`--estimate-version`, JS formulas of "
                      "docs/COST_FORMULAS.md)", ""]
        lines += ["_Estimates use the current public price list and the generation's settings; they are not what "
                  "the creator actually paid (plans, promos and unlimited modes differ)._", ""]
    top = sorted(gens, key=lambda g: -(g["engagement"].get("views") or 0))[:10]
    lines += ["## Sample prompts (most viewed)", "", _md_table(
        [[g.get("job_set_type"), g["media_type"], g["engagement"].get("views"), g["engagement"].get("likes"),
          (g.get("prompt") or "")[:140] + ("…" if len(g.get("prompt") or "") > 140 else "")] for g in top],
        ["model", "media", "views", "likes", "prompt"]), ""]
    if m.get("limits_hit") or m.get("warnings"):
        lines += ["## Limits and warnings", ""] + [f"- {x}" for x in m.get("limits_hit", []) + m.get("warnings", [])]
        lines.append("")
    lines += ["Files: `dataset.json`, `json/*.json`, `csv/generations.csv` (one row per generation), "
              "`csv/generation_inputs.csv`, `csv/generation_results.csv`, `csv/creators.csv` (only with "
              "--with-profiles), `csv/pages.csv`, `csv/stats.csv`.", ""]
    return "\n".join(lines)


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    # formula_version (v2 estimates only) appears in the JSON Schema only when the dataset contains it
    v2 = any((g.get("estimated_cost") or {}).get("formula_version") is not None for g in ds["generations"])
    json_parts = {"generations": ds["generations"], "creators": ds["creators"], "comments": ds["comments"],
                  "pages": ds["pages"], "stats": ds["stats"]}
    tables, model, md = csv_tables(ds), CommunityDataset, summary_md(ds)
    if "shots" in ds:          # opt-in feeds were used (CommunityDatasetExt)
        json_parts.update({k: ds[k] for k in (*EXTRA_COLLECTIONS, "extra_stats")})
        tables.update(extra_csv_tables(ds))
        model, md = CommunityDatasetExt, md + "\n" + extra_summary_md(ds)
    if "music_cards" in ds:    # opt-in gallery / template sources were used (CommunityDatasetGallery)
        json_parts.update({k: ds[k] for k in (*GALLERY_COLLECTIONS, "gallery_stats")})
        tables.update(gallery_csv_tables(ds))
        model, md = CommunityDatasetGallery, md + "\n" + gallery_summary_md(ds)
    with formula_version_in_schema(v2):
        return write_standard_outputs(ds, out_dir, json_parts=json_parts, csv_tables=tables, dataset_model=model,
                                      summary_md=md)
