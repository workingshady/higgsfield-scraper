"""Top trending video ideas, templates, reels/shorts and ads from Higgsfield, ranked and packaged per idea.

Pipeline (each step can be skipped):
  1. scrape   - runs the existing scrapers on Higgsfield's own *trending-sorted* lists, one run per feed so no
                feed can starve another (GET only, normal politeness). Nothing is crawled exhaustively.
                  showcase   main feed (home Explore), explore sort=trending, every Shorts/Reels preset
                  community  trending videos (own run) + approved videos (own run)
                  studios    trending + approved galleries of every studio (Marketing Studio ads, Cinema, ...)
                  projects   trending projects / short films
                  catalog    viral effects + ad (marketing) templates  -> "featured" (no public popularity numbers)
  2. collect  - every template / video becomes one candidate with its prompt, settings, model, reference inputs,
                example outputs and metrics.
  3. dedupe   - publication id / job id / output media key / title.
  4. score    - "really trending" = Higgsfield's own trending position + speed (views/likes per day since
                published) + usage (times made / remakes) + totals. Percentile inside each source:
                position 30 %, usage 25 %, views/day 15 %, likes/day 10 %, likes 10 %, views 10 %
                (missing signals are re-weighted). --compare <older ideas.json> adds 50 % growth ("rising").
  5. package  - exports/trending/<timestamp>/
                  index.md                      overall top N + per-category tops + featured
                  top.csv / top.json            the packaged ideas
                  ideas.json                    every candidate's metrics (use as --compare next time)
                  categories/<cat>.md|.csv      EVERY candidate of that category, ranked (links, metrics, prompt)
                  ideas/<cat>/NNN_<slug>/       README.md, contest_brief.md, prompt.txt, idea.json,
                                                assets/ (example outputs + thumbnails), inputs/ (references)
                  featured/<viral_effects|ad_templates>/NN_<slug>/   Higgsfield-featured templates with previews
                categories: reels_shorts, ads, templates, videos, films

Usage:
  python scripts/trending_ideas.py                        # scrape + rank + package (top 100 + 20 per category)
  python scripts/trending_ideas.py --no-scrape            # reuse the latest trend-* runs
  python scripts/trending_ideas.py --top 50 --per-category 10 --no-download
  python scripts/trending_ideas.py --no-scrape --compare exports/trending/<older>/ideas.json   # rising trends
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
CACHE = ROOT / "exports" / "trending" / "_cache"   # one copy per URL; idea folders get hard links (no extra disk)
LABEL = "trend-"
CATEGORIES = {
    "reels_shorts": "Reels / Shorts templates (Shorts Studio presets: remakes + the original social reel's reach)",
    "ads": "Ads (Marketing Studio / Ads Studio outputs and ad-model videos)",
    "templates": "Templates (home-feed and Explore presets people re-use: times made)",
    "videos": "Trending videos (community + Cinema Studio and other studios)",
    "films": "Trending projects / short films",
}


# --------------------------------------------------------------------------------------------- 1. scrape
def scrape_plan(a) -> list[tuple[str, list[str]]]:
    p = str(a.pages)
    return [
        ("showcase", ["scrape", "showcase", "--what", "main_feed,explore_categories,reels_presets",
                      "--main-feed-pages", p, "--explore-sort", "trending", "--explore-pages", p,
                      "--explore-sources", "higgsfield,community"]),
        ("community", ["scrape", "community", "--feeds", "trending", "--type", "video", "--max-items", str(a.videos)]),
        # the trending feed is ~97 % images and honours only one model= per request: one run per video model
        *[(f"community-{m}", ["scrape", "community", "--feeds", "trending", "--type", "video", "--models", m,
                              "--max-items", str(a.per_model)]) for m in a.video_models.split(",") if m],
        ("community-approved", ["scrape", "community", "--feeds", "approved", "--type", "video",
                                "--max-items", str(a.approved)]),
        ("studios", ["scrape", "studios", "--what", "galleries", "--gallery-feeds", "trending,approved",
                     "--gallery-pages", str(a.gallery_pages)]),
        ("projects", ["scrape", "projects", "--what", "trending", "--max-items", str(a.films)]),
        ("catalog", ["scrape", "catalog", "--kinds", "viral_preset,viral_type,marketing_preset,marketing_category"]),
    ]


def latest_runs_all() -> list[Path]:
    """Latest run of every trend-* label (fixed names + one per video model)."""
    best: dict[str, Path] = {}
    for p in sorted(RUNS.glob(f"*_{LABEL}*")):
        if (p / "output" / "json").is_dir():
            best[p.name.split("_", 1)[1]] = p
    return list(best.values())


def latest_run(name: str) -> Path | None:
    c = sorted(p for p in RUNS.glob(f"*_{LABEL}{name}") if (p / "output" / "json").is_dir())
    return c[-1] if c else None


def run_scrapers(a) -> list[Path]:
    out = []
    for name, args in scrape_plan(a):
        cmd = [sys.executable, "-m", "higgsfield_scraper", *args, "--label", f"{LABEL}{name}"]
        print(f"\n[scrape] {' '.join(cmd[3:])}", flush=True)
        t = time.time()
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.findall(r"run folder: (.+)", (p.stdout or "") + (p.stderr or ""))
        run = Path(m[-1].strip()) if m else latest_run(name)
        print(f"[scrape] {name}: exit {p.returncode} in {time.time() - t:.0f}s -> {run}", flush=True)
        if p.returncode != 0:
            print((p.stderr or p.stdout or "")[-1500:], file=sys.stderr)
        if run:
            out.append(run)
    return out


# --------------------------------------------------------------------------------------------- 2. collect
def load(run: Path, name: str) -> list[dict]:
    f = run / "output" / "json" / name
    if not f.is_file():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else []


def num(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def age_days(ts, now: dt.datetime) -> float | None:
    if not ts:
        return None
    try:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return max((now - t).total_seconds() / 86400, 0.5)     # floor: half a day, so brand-new items don't explode


def is_video_url(u: str) -> bool:
    return bool(re.search(r"\.(mp4|mov|webm)(\?|$)", u.lower()))


def media_of(items):
    """-> (outputs, thumbs) as [{url,type,role}]. Videos are outputs (full quality first); images next to a video,
    or roles named thumb/poster, are thumbnails."""
    items = [m for m in items or [] if isinstance(m, dict) and m.get("url")]
    has_video = any((m.get("type") or "") == "video" or is_video_url(m["url"]) for m in items)
    outs, thumbs = [], []
    for m in items:
        role = (m.get("role") or m.get("name") or "").lower()
        e = {"url": m["url"], "type": m.get("type") or ("video" if is_video_url(m["url"]) else None), "role": role}
        is_img = (m.get("type") or "") == "image" or re.search(r"\.(webp|png|jpe?g|gif)(\?|$)", m["url"].lower())
        if "thumb" in role or "poster" in role or (has_video and is_img):
            thumbs.append(e)
        else:
            outs.append(e)
    outs.sort(key=lambda e: ("min" in e["role"]) or ("compressed" in e["role"]))
    return outs, thumbs


def inputs_of(items) -> list[dict]:
    return [{"url": m["url"], "type": m.get("type"), "role": m.get("source_role") or m.get("role") or m.get("param")}
            for m in items or [] if isinstance(m, dict) and m.get("url")]


def cand(**kw) -> dict:
    base = dict(source="", category="", kind="", key=None, title=None, description=None, prompt=None, model=None,
                topic=None, hashtags=[], position=None, uses=None, likes=None, views=None, comments=None,
                views_per_day=None, likes_per_day=None, published_at=None, page_url=None,
                outputs=[], thumbs=[], inputs=[], settings=None, variants=[], dedupe=[])
    base.update(kw)
    return base


AD_MODELS = re.compile(r"marketing|ads?_|_ads?\b|ugc|product|commercial", re.I)


def video_category(model: str | None, source: str) -> str:
    if source.startswith("studio:") and any(s in source for s in ("marketing", "ads_studio")):
        return "ads"
    return "ads" if model and AD_MODELS.search(model) else "videos"


def with_velocity(c: dict, now) -> dict:
    d = age_days(c["published_at"], now)
    if d:
        c["age_days"] = round(d, 1)
        c["views_per_day"] = round(c["views"] / d, 1) if c["views"] is not None else None
        c["likes_per_day"] = round(c["likes"] / d, 2) if c["likes"] is not None else None
    return c


def collect(runs: list[Path], now: dt.datetime) -> tuple[list[dict], dict[str, list[dict]]]:
    C: list[dict] = []
    featured: dict[str, list[dict]] = {"viral_effects": [], "ad_templates": []}
    for run in runs:
        # --- main feed + explore presets: templates people re-use (uses = times made)
        for items_f, vars_f, src in (("main_feed_items.json", "main_feed_variants.json", "main_feed"),
                                     ("explore_items.json", "explore_variants.json", "explore")):
            variants: dict[str, list] = {}
            for v in load(run, vars_f):
                variants.setdefault(v.get("item_id"), []).append(v)
            pos_by_list: Counter = Counter()
            for it in load(run, items_f):
                lst = (it.get("feed_source"), it.get("sort"), it.get("category_filter"))
                pos_by_list[lst] += 1
                outs, thumbs, ins, prompts, vlist = [], [], [], [], []
                ov = it.get("original_video")
                if isinstance(ov, dict) and ov.get("url"):
                    outs.append({"url": ov["url"], "type": "video", "role": "original"})
                for v in variants.get(it.get("item_id"), []):
                    o, t = media_of(v.get("media"))
                    outs += o; thumbs += t; ins += inputs_of(v.get("inputs"))
                    if v.get("prompt"):
                        prompts.append(v["prompt"])
                    vlist.append({"variant_type": v.get("variant_type"), "prompt": v.get("prompt"),
                                  "params": v.get("params"), "publication_id": v.get("publication_id"),
                                  "publication_engagement": v.get("publication_engagement")})
                e = it.get("engagement") or {}
                trending_list = src == "main_feed" or it.get("sort") == "trending"
                C.append(cand(source=src, category="templates", kind="template", key=f"{src}:{it.get('item_id')}",
                              title=it.get("title"), description=it.get("description"),
                              prompt=prompts[0] if prompts else None, model=it.get("job_set_type"),
                              topic=it.get("category"),
                              position=(it.get("position") or pos_by_list[lst]) if trending_list else None,
                              uses=num(e.get("uses")), likes=num(e.get("likes")), views=num(e.get("views")),
                              comments=num(e.get("comments")), page_url=it.get("source_url"),
                              outputs=outs, thumbs=thumbs, inputs=ins, variants=vlist,
                              dedupe=[f"pub:{p}" for p in it.get("publication_ids") or []] + [f"item:{it.get('item_id')}"]))
        # --- Shorts / Reels presets: remakes on Higgsfield + reach of the social reel it is modelled on
        for r in load(run, "reels_presets.json"):
            e = r.get("engagement") or {}
            ref = r.get("reference_engagement") or {}
            o, t = media_of(r.get("media"))
            C.append(cand(source="reels", category="reels_shorts", kind="template", key=f"reels:{r.get('preset_id')}",
                          title=r.get("title"), description=r.get("description"), prompt=r.get("prompt") or r.get("script"),
                          model=r.get("job_set_type"), topic=r.get("category_label") or r.get("category"),
                          hashtags=r.get("hashtags") or [],
                          uses=num(r.get("recreates") if r.get("recreates") is not None else e.get("uses")),
                          likes=num(e.get("likes") if e.get("likes") is not None else ref.get("likes")),
                          views=num(e.get("views") if e.get("views") is not None else ref.get("views")),
                          comments=num(e.get("comments") if e.get("comments") is not None else ref.get("comments")),
                          page_url=r.get("source_url"), outputs=o, thumbs=t, inputs=inputs_of(r.get("inputs")),
                          settings={"preset_source": r.get("preset_source"), "quality": r.get("quality"),
                                    "duration_s": r.get("duration_s"), "own_recording": r.get("own_recording"),
                                    "script": r.get("script"), "instructions": r.get("instructions"),
                                    "reference_url": r.get("reference_url"), "reference_platform": r.get("reference_platform"),
                                    "reference_engagement": ref or None},
                          dedupe=[f"preset:{r.get('preset_id')}"] + (r.get("media_keys") or [])[:1]))
        # --- community videos: trending feed position = Higgsfield's own trending rank
        pos: Counter = Counter()
        for g in load(run, "generations.json"):
            o, t = media_of(g.get("results"))
            if not any((x.get("type") or "") == "video" or is_video_url(x["url"]) for x in o):
                continue
            feed = g.get("feed") or ""
            pos[feed] += 1
            e = g.get("engagement") or {}
            src = g.get("source") if isinstance(g.get("source"), dict) else {}
            px = g.get("params_extra") if isinstance(g.get("params_extra"), dict) else {}
            preset = px.get("preset") or px.get("chain_preset") or {}
            effect = preset.get("name") if isinstance(preset, dict) else None
            C.append(with_velocity(cand(
                source=f"community:{feed}", category=video_category(g.get("job_set_type"), "community"), kind="video",
                key=f"gen:{g.get('generation_id')}", prompt=g.get("prompt"), model=g.get("job_set_type"),
                title=f"Effect: {effect}" if effect and not (g.get("prompt") or "").strip() else None, topic=effect,
                position=pos[feed] if feed == "trending" else None,
                likes=num(e.get("likes")), views=num(e.get("views")), published_at=g.get("published_at"),
                page_url=src.get("url"), outputs=o, thumbs=t, inputs=inputs_of(g.get("inputs")), settings=g.get("settings"),
                dedupe=[f"pub:{g.get('publication_id')}", f"job:{g.get('generation_id')}"]), now))
        # --- studio galleries: Marketing Studio / Ads Studio (ads), Cinema Studio, AI Influencer, Canvas, ...
        for g in load(run, "gallery_items.json"):
            o, t = media_of(g.get("media"))
            if not any((x.get("type") or "") == "video" or is_video_url(x["url"]) for x in o):
                continue
            e = g.get("engagement") or {}
            preset = g.get("preset") if isinstance(g.get("preset"), dict) else {}
            source = f"studio:{g.get('studio')}"
            C.append(with_velocity(cand(
                source=source, category=video_category(g.get("job_set_type"), source), kind="video",
                key=f"gal:{g.get('job_id')}", title=preset.get("name"),
                prompt=g.get("prompt") or g.get("enhanced_prompt"), model=g.get("job_set_type"), topic=g.get("studio"),
                position=g.get("rank") if g.get("feed") == "trending" else None,
                likes=num(e.get("likes")), views=num(e.get("views")), published_at=g.get("published_at"),
                page_url=g.get("source_url"), outputs=o, thumbs=t, inputs=inputs_of(g.get("inputs")),
                settings=g.get("settings"), dedupe=[f"pub:{g.get('publication_id')}", g.get("generation_key")]), now))
        # --- trending projects / short films
        rank = {r.get("publication_id"): r.get("position") for r in load(run, "trending.json")}
        for p in load(run, "publications.json"):
            if p.get("publication_id") not in rank and "trending" not in str(p.get("listing") or ""):
                continue
            o, t = media_of(p.get("media"))
            if p.get("trailer_url"):
                o.insert(0, {"url": p["trailer_url"], "type": "video", "role": "trailer"})
            if p.get("cover_url"):
                t.insert(0, {"url": p["cover_url"], "type": "image", "role": "cover"})
            pr = rank.get(p.get("publication_id"))
            C.append(with_velocity(cand(
                source="projects", category="films", kind="film", key=f"proj:{p.get('publication_id')}",
                title=p.get("name"), description=p.get("description"), model=", ".join(
                    sorted({str(m.get("job_set_type") or m.get("model") or m) for m in (p.get("model_usage") or [])
                            if m})) or None,
                topic=", ".join(p.get("categories") or []) or None, hashtags=p.get("tags") or [],
                position=None if pr is None else pr + 1, likes=num(p.get("likes")), views=num(p.get("views")),
                comments=num(p.get("comments")), published_at=p.get("published_at"), page_url=p.get("url"),
                outputs=o, thumbs=t, settings={"duration_seconds": p.get("duration_seconds"),
                                               "credits_spent": p.get("credits_spent"), "show_prompts": p.get("show_prompts"),
                                               "model_usage": p.get("model_usage")},
                dedupe=[f"projpub:{p.get('publication_id')}"]), now))
        # --- featured templates (catalog): site order, no public popularity numbers
        for i, v in enumerate(load(run, "viral_presets.json"), 1):
            o, t = media_of(v.get("media"))
            if v.get("preview_url"):
                o.insert(0, {"url": v["preview_url"], "type": "video", "role": "preview"})
            if v.get("thumbnail_url"):
                t.insert(0, {"url": v["thumbnail_url"], "type": "image", "role": "thumbnail"})
            featured["viral_effects"].append(cand(
                source="catalog:viral_preset", category="featured", kind="template", key=f"viral:{v.get('id')}",
                title=v.get("name"), description=v.get("description"), model=v.get("job_set_type"),
                topic=", ".join(v.get("type_slugs") or []) or None, hashtags=v.get("tags") or [], position=i,
                outputs=o, thumbs=t, page_url=f"https://higgsfield.ai/effects/{v['slug']}" if v.get("slug") else None,
                settings={"is_main_page": v.get("is_main_page"), "inputs": v.get("inputs"),
                          "param_choices": v.get("param_choices"), "credits": v.get("default_credit_units"),
                          "duration": v.get("duration")}))
        for i, m in enumerate(load(run, "marketing_presets.json"), 1):
            o, t = media_of(m.get("media"))
            featured["ad_templates"].append(cand(
                source="catalog:marketing_preset", category="featured", kind="template", key=f"mkt:{m.get('id')}",
                title=m.get("name"), description=m.get("description"),
                topic=", ".join(str(x) for x in (m.get("categories") or [])) or m.get("group"),
                hashtags=m.get("tags") or [], position=i, outputs=o, thumbs=t, prompt=(m.get("params") or {}).get("prompt")
                if isinstance(m.get("params"), dict) else None, settings={"params": m.get("params"), "group": m.get("group")}))
    # catalog: Higgsfield's main-page picks first, then site order
    featured["viral_effects"].sort(key=lambda c: (not (c["settings"] or {}).get("is_main_page"), c["position"]))
    return C, featured


# --------------------------------------------------------------------------------------------- 3/4. dedupe + score
def dedupe(C: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    out = []
    order = {"templates": 0, "reels_shorts": 0, "films": 1, "ads": 2, "videos": 3}
    for c in sorted(C, key=lambda c: (order.get(c["category"], 9), c["position"] or 10**9)):
        keys = [k for k in c["dedupe"] if k and not str(k).endswith(":None")]
        if c["title"]:
            keys.append(f"title:{c['category']}:" + re.sub(r"\W+", "", c["title"].lower()))
        hit = next((seen[k] for k in keys if k in seen), None)
        if hit:
            for m in ("uses", "likes", "views", "comments", "views_per_day", "likes_per_day"):
                if c.get(m) is not None and (hit.get(m) is None or c[m] > hit[m]):
                    hit[m] = c[m]
            if c["position"] is not None and (hit["position"] is None or c["position"] < hit["position"]):
                hit["position"] = c["position"]
            hit.setdefault("also_in", []).append(c["source"])
            continue
        for k in keys:
            seen[k] = c
        out.append(c)
    return out


def pct_rank(values: list) -> list:
    xs = sorted(v for v in values if v is not None)
    n = len(xs)
    if n < 2:
        return [None if v is None else 0.5 for v in values]
    return [None if v is None else ((bisect_left(xs, v) + bisect_right(xs, v)) / 2) / n for v in values]


# signal -> (weight, getter); position is "higher is better" after negation
SIGNALS = {
    "position": (0.30, lambda c: None if c["position"] is None else -float(c["position"])),
    "uses": (0.25, lambda c: c["uses"]),
    "views_per_day": (0.15, lambda c: c["views_per_day"]),
    "likes_per_day": (0.10, lambda c: c["likes_per_day"]),
    "likes": (0.10, lambda c: c["likes"]),
    "views": (0.10, lambda c: c["views"]),
}
GROWTH = ("uses", "likes", "views")


def score(C: list[dict], previous: dict | None) -> None:
    groups: dict[str, list[dict]] = {}
    for c in C:
        groups.setdefault(c["source"], []).append(c)
    for group in groups.values():
        pr = {s: pct_rank([g(c) for c in group]) for s, (_, g) in SIGNALS.items()}
        for i, c in enumerate(group):
            parts = {s: pr[s][i] for s in SIGNALS if pr[s][i] is not None}
            den = sum(SIGNALS[s][0] for s in parts)
            c["score_popular"] = round(100 * sum(SIGNALS[s][0] * v for s, v in parts.items()) / den, 2) if den else 0.0
            c["signals"] = sorted(parts)
            # small sources (< 10 items) can't be ranked against themselves reliably: damp them
            if len(group) < 10:
                c["score_popular"] = round(c["score_popular"] * 0.8, 2)
    # global reach: the same signals ranked across ALL sources, so the best item of a weak source can't top the list
    reach = ("uses", "views_per_day", "likes_per_day", "likes", "views")
    gp = {s: pct_rank([SIGNALS[s][1](c) for c in C]) for s in reach}
    # usage is not comparable across products (a reel remake costs far more than an effect re-use): rank it per category
    for cat in {c["category"] for c in C}:
        idx = [i for i, c in enumerate(C) if c["category"] == cat]
        for i, v in zip(idx, pct_rank([C[i]["uses"] for i in idx])):
            gp["uses"][i] = v
    for i, c in enumerate(C):
        vals = [(SIGNALS[s][0], gp[s][i]) for s in reach if gp[s][i] is not None]
        c["score_reach"] = round(100 * sum(w * v for w, v in vals) / sum(w for w, _ in vals), 2) if vals else None
        within = c["score_popular"]
        c["score_popular"] = round(0.4 * within + 0.6 * c["score_reach"], 2) if vals else round(0.6 * within, 2)
    if previous:
        for c in C:
            p = previous.get(c["key"])
            if p:
                c["growth"] = {m: (c[m] - p[m]) if c[m] is not None and p.get(m) is not None else None for m in GROWTH}
        gr = {m: pct_rank([(c.get("growth") or {}).get(m) for c in C]) for m in GROWTH}
        for i, c in enumerate(C):
            vals = [gr[m][i] for m in GROWTH if gr[m][i] is not None]
            c["score_rising"] = round(100 * sum(vals) / len(vals), 2) if vals else None
    for c in C:
        r = c.get("score_rising")
        c["score"] = round(c["score_popular"] if r is None else 0.5 * c["score_popular"] + 0.5 * r, 2)
    C.sort(key=lambda c: (-c["score"], c["position"] or 10**9, -(c["uses"] or 0), -(c["views_per_day"] or 0)))
    for i, c in enumerate(C, 1):
        c["rank"] = i


def pick(C: list[dict], top: int, per_category: int, max_per_source: int) -> list[dict]:
    chosen: dict[str, dict] = {}
    per: Counter = Counter()
    for c in C:                                   # overall top N, diverse
        if len([x for x in chosen.values() if x.get("in_top")]) >= top:
            break
        if per[c["source"]] >= max_per_source:
            continue
        per[c["source"]] += 1
        c["in_top"] = True
        chosen[c["key"]] = c
    for cat in CATEGORIES:                        # + top K of every category
        for c in [x for x in C if x["category"] == cat][:per_category]:
            chosen.setdefault(c["key"], c)
    return sorted(chosen.values(), key=lambda c: c["rank"])


# --------------------------------------------------------------------------------------------- 5. package
def slug(s: str | None, n=50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:n].rstrip("-")) or "untitled"


def fmt(v, d=0):
    if v is None:
        return "–"
    return f"{v:,.{d}f}" if d else f"{int(v):,}"


def ext_of(url: str, typ: str | None) -> str:
    m = re.search(r"\.(mp4|mov|webm|webp|png|jpe?g|gif|m3u8)(\?|$)", url.lower())
    return "." + m.group(1) if m else (".mp4" if typ == "video" else ".jpg")


def _place(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def download(url: str, dest: Path, max_mb: float) -> str:
    if dest.exists() and dest.stat().st_size:
        return "cached"
    cached = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:20] + dest.suffix)
    if cached.exists() and cached.stat().st_size:
        _place(cached, dest)
        return "cached"
    st = _fetch(url, cached, max_mb)
    if st == "ok":
        _place(cached, dest)
    return st


def _fetch(url: str, dest: Path, max_mb: float) -> str:
    if not url.startswith("https://") or ".m3u8" in url:
        return "skipped"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research script)"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            size = int(r.headers.get("Content-Length") or 0)
            if size and size > max_mb * 1e6:
                return f"too big ({size / 1e6:.0f} MB)"
            data = r.read(int(max_mb * 1e6) + 1)
        if len(data) > max_mb * 1e6:
            return "too big"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return "ok"
    except Exception as e:  # noqa: BLE001 - one failed asset must not stop the package
        return f"error: {type(e).__name__}"


def title_of(c: dict) -> str:
    """Template title, else the first meaningful sentence of the prompt (skips headings such as 'SCENE CONTEXT',
    chat-log prefixes '[date] name:', short fragments and dashes)."""
    if c["title"]:
        return c["title"]
    text = re.sub(r"<<<[^>]*>>>", "", c["prompt"] or "")
    for line in re.split(r"[\n\r]+|(?<=[.!?])\s+", text):
        t = re.sub(r"^\[[^\]]*\][^:]*:\s*", "", line.strip())
        t = re.sub(r"^[\W_]+", "", t).strip()
        if len(re.findall(r"[^\W\d_]{2,}", t)) < 4 or t.isupper() or t.lower().startswith(("prompt", "scene context")):
            continue
        return (t[:70].rstrip() + "…") if len(t) > 70 else t
    return f"{c['model'] or 'video'} ({c['source']})"


def fetch_assets(c: dict, d: Path, a) -> list[dict]:
    assets = []
    if a.no_download:
        return assets
    jobs = ([("assets", f"output_{k + 1}", m) for k, m in enumerate(c["outputs"][: a.max_outputs])]
            + [("assets", f"thumb_{k + 1}", m) for k, m in enumerate(c["thumbs"][:2])]
            + [("inputs", f"ref_{k + 1}_{slug(m.get('role') or 'input', 20)}", m) for k, m in enumerate(c["inputs"][: a.max_inputs])])
    for sub, base, m in jobs:
        f = d / sub / (base + ext_of(m["url"], m.get("type")))
        st = download(m["url"], f, a.max_mb)
        assets.append({"file": f"{sub}/{f.name}" if st in ("ok", "cached") else None, "url": m["url"],
                       "role": m.get("role"), "status": st})
        if st == "ok":
            time.sleep(a.delay)
    return assets


def write_idea(c: dict, d: Path, a, brief_too=True) -> None:
    d.mkdir(parents=True, exist_ok=True)
    c["assets"] = fetch_assets(c, d, a)
    (d / "idea.json").write_text(json.dumps(c, indent=4, ensure_ascii=False, default=str), encoding="utf-8")
    if c["prompt"]:
        (d / "prompt.txt").write_text(c["prompt"], encoding="utf-8")
    (d / "README.md").write_text(readme(c), encoding="utf-8")
    if brief_too:
        (d / "contest_brief.md").write_text(brief(c), encoding="utf-8")


def package(chosen: list[dict], C: list[dict], featured: dict[str, list[dict]], out: Path, a) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(chosen, 1):
        c["folder"] = f"ideas/{c['category']}/{c['rank']:03d}_{slug(title_of(c))}"
        write_idea(c, out / c["folder"], a)
        n = sum(1 for x in c["assets"] if x["file"])
        print(f"[package] {i:3d}/{len(chosen)} {c['folder']}  ({n} files)", flush=True)
    for name, items in featured.items():
        for i, c in enumerate(items[: a.featured], 1):
            c["rank"] = i
            c["folder"] = f"featured/{name}/{i:02d}_{slug(title_of(c))}"
            write_idea(c, out / c["folder"], a)
        if items:
            print(f"[package] featured/{name}: {min(len(items), a.featured)} of {len(items)}", flush=True)

    cols = ["rank", "score", "score_popular", "score_rising", "category", "source", "title", "model", "topic",
            "position", "uses", "likes", "views", "comments", "views_per_day", "likes_per_day", "age_days",
            "published_at", "page_url", "folder", "prompt"]

    def write_csv(path: Path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for c in rows:
                w.writerow({**c, "title": title_of(c)})

    top = [c for c in chosen if c.get("in_top")]
    write_csv(out / "top.csv", top)
    (out / "top.json").write_text(json.dumps(chosen, indent=4, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "ideas.json").write_text(json.dumps(
        {c["key"]: {m: c.get(m) for m in ("uses", "likes", "views", "comments", "position")} for c in C}, indent=4),
        encoding="utf-8")
    for cat in CATEGORIES:
        rows = [c for c in C if c["category"] == cat]
        write_csv(out / "categories" / f"{cat}.csv", rows)
        (out / "categories" / f"{cat}.md").write_text(table_md(f"{CATEGORIES[cat]}: all {len(rows)}", rows, "../"),
                                                     encoding="utf-8")
    (out / "index.md").write_text(index_md(top, chosen, C, featured, a), encoding="utf-8")


def table_md(title: str, rows: list[dict], prefix="") -> str:
    L = [f"# {title}", "", "| # | score | idea | source | model | trend pos | uses | likes | views | views/day | link |",
         "|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|"]
    for c in rows:
        t = title_of(c).replace("|", "/")
        link = f"[folder]({prefix}{c['folder']}/README.md)" if c.get("folder") else (f"[page]({c['page_url']})" if c["page_url"] else "")
        L.append(f"| {c['rank']} | {c['score']} | {t} | {c['source']} | `{c['model']}` | {fmt(c['position'])} | "
                 f"{fmt(c['uses'])} | {fmt(c['likes'])} | {fmt(c['views'])} | {fmt(c['views_per_day'])} | {link} |")
    return "\n".join(L) + "\n"


def index_md(top, chosen, C, featured, a) -> str:
    L = [f"# Trending ideas, templates, reels/shorts and ads ({dt.datetime.now().strftime('%Y-%m-%d %H:%M')})", "",
         f"{len(C)} unique candidates · top {len(top)} overall + top {a.per_category} per category packaged "
         f"({len(chosen)} idea folders). Score = 40 % rank inside its source (Higgsfield trending position 30 %, "
         "usage = times made / remakes 25 %, views/day 15 %, likes/day 10 %, likes 10 %, views 10 %) + 60 % the same "
         "reach signals ranked across all sources"
         + ("; 50 % growth vs the compared snapshot." if any(c.get("score_rising") is not None for c in C) else "."), "",
         "Candidates: " + ", ".join(f"{k} {v}" for k, v in Counter(c["category"] for c in C).most_common())
         + " · sources: " + ", ".join(f"{k} {v}" for k, v in Counter(c["source"] for c in C).most_common()), "",
         "Every candidate of a category (ranked, with links): " + " · ".join(
             f"[{cat}](categories/{cat}.md)" for cat in CATEGORIES), "", ""]
    L += ["## Top overall", ""] + table_md("", top).splitlines()[2:] + [""]
    for cat, label in CATEGORIES.items():
        rows = [c for c in chosen if c["category"] == cat][: a.per_category]
        if rows:
            L += [f"## {label}", ""] + table_md("", rows).splitlines()[2:] + [""]
    for name, items in featured.items():
        if items:
            L += [f"## Featured by Higgsfield: {name.replace('_', ' ')} (site order, no public popularity numbers)", "",
                  "| # | template | type | link |", "|---:|---|---|---|"]
            L += [f"| {c['rank']} | {title_of(c)} | {c['topic'] or ''} | [folder]({c['folder']}/README.md) |"
                  for c in items[: a.featured]] + [""]
    return "\n".join(L)


def readme(c: dict) -> str:
    L = [f"# #{c['rank']} {title_of(c)}", "",
         f"**Category** {c['category']} · **source** {c['source']} · **model** `{c['model']}`"
         + (f" · **topic** {c['topic']}" if c["topic"] else ""), ""]
    if c.get("score") is not None:
        L += [f"**Score** {c['score']} (popular {c['score_popular']}"
              + (f", rising {c['score_rising']}" if c.get("score_rising") is not None else "")
              + f"; signals: {', '.join(c.get('signals') or [])})", "",
              "| trend position | uses / remakes | likes | views | comments | views/day | likes/day | age (days) |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|",
              f"| {fmt(c['position'])} | {fmt(c['uses'])} | {fmt(c['likes'])} | {fmt(c['views'])} | {fmt(c['comments'])} | "
              f"{fmt(c['views_per_day'])} | {fmt(c['likes_per_day'], 1)} | {fmt(c.get('age_days'), 1)} |", ""]
    if c.get("growth"):
        L += ["Growth since the compared snapshot: " + ", ".join(f"{k} {fmt(v)}" for k, v in c["growth"].items()), ""]
    if c["description"]:
        L += ["## What it is", c["description"], ""]
    if c["prompt"]:
        L += ["## Prompt", "```", c["prompt"], "```", ""]
    if c["hashtags"]:
        L += ["**Tags** " + " ".join("#" + str(h) for h in c["hashtags"]), ""]
    if c["inputs"]:
        L += ["## User input (references)", *[f"- {m.get('role') or 'input'} ({m.get('type') or '?'}): {m['url']}" for m in c["inputs"]], ""]
    if c["variants"]:
        L += ["## Variants", *[f"- {v['variant_type']}: {v['prompt'] or '(no prompt)'}" for v in c["variants"]], ""]
    s = {k: v for k, v in (c["settings"] or {}).items() if v not in (None, "", [], {})}
    if s:
        L += ["## Settings", "```json", json.dumps(s, indent=2, ensure_ascii=False, default=str), "```", ""]
    lines = [f"- [{x['file']}]({x['file']})" if x["file"] else f"- {x['role']}: {x['url']} ({x['status']})"
             for x in c.get("assets", [])]
    lines = lines or [f"- {m['role']}: {m['url']}" for m in c["outputs"] + c["thumbs"] + c["inputs"]]
    L += ["## Assets", *lines, ""]
    if c["page_url"]:
        L += [f"Source: {c['page_url']}", ""]
    if c.get("also_in"):
        L += ["Also found in: " + ", ".join(sorted(set(c["also_in"]))), ""]
    return "\n".join(L)


def brief(c: dict) -> str:
    ins = ", ".join(sorted({f"{m.get('type') or 'file'} ({m.get('role') or 'input'})" for m in c["inputs"]})) or "?"
    trend = (f"{fmt(c['uses'])} uses/remakes, {fmt(c['likes'])} likes, {fmt(c['views'])} views"
             + (f", {fmt(c['views_per_day'])} views/day" if c.get("views_per_day") else "")
             + (f", #{c['position']} in Higgsfield trending" if c.get("position") else "") + f" ({c['source']})")
    return "\n".join([
        f"# Contest brief draft: {title_of(c)}", "",
        "Inspiration only. The contest rejects copies of competitor templates: add your own twist and 2+ MyZesty features.", "",
        "| Field | Draft |", "|---|---|",
        f"| Idea name | _your name for the twist_ (inspired by: {title_of(c)}) |",
        "| Hook | _what stops the scroll in the first 2 s_ |",
        f"| Concept | {(c['description'] or (c['prompt'] or '')[:200]).replace('|', '/').replace(chr(10), ' ')} |",
        f"| Reference | {c['page_url'] or (c['outputs'][0]['url'] if c['outputs'] else '')} |",
        f"| Trend | {trend} |",
        f"| User input | {ins} |",
        "| Visual | see assets/ (example output) and inputs/ (reference inputs) |",
        "| Target user | _who uses it and for what_ |",
        "| MyZesty features | _AI Animate / Product Video / Story+ / Ads Creator / Templates_ |", ""])


# --------------------------------------------------------------------------------------------- main
NAMES = ("showcase", "community", "community-approved", "studios", "projects", "catalog")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--top", type=int, default=100, help="overall top ideas to package (default 100)")
    ap.add_argument("--per-category", type=int, default=20, help="also package the top K of every category (default 20)")
    ap.add_argument("--featured", type=int, default=30, help="Higgsfield-featured viral effects / ad templates to package (default 30 each)")
    ap.add_argument("--pages", type=int, default=15, help="pages (20 items) of the main feed and Explore trending (default 15)")
    ap.add_argument("--videos", type=int, default=1000, help="community trending videos (default 1000)")
    ap.add_argument("--video-models", default="seedance_2_5,seedance_2_0,kling3_0,sora2_video,wan2_5_video,minimax_hailuo,magi_2,viral_hub_video,marketing_studio_video,cinematic_studio_3_0,cinematic_studio_2_5,ai_reels_v1",
                    help="video models whose community trending list is scraped separately (comma list)")
    ap.add_argument("--per-model", type=int, default=100, help="trending videos per video model (default 100)")
    ap.add_argument("--approved", type=int, default=300, help="community approved videos (default 300)")
    ap.add_argument("--gallery-pages", type=int, default=3, help="studio gallery pages (50) per studio and feed (default 3)")
    ap.add_argument("--films", type=int, default=200, help="trending projects / films (default 200)")
    ap.add_argument("--no-scrape", action="store_true", help="reuse the latest trend-* runs")
    ap.add_argument("--runs", nargs="*", help="explicit run folders to read (implies --no-scrape)")
    ap.add_argument("--compare", help="previous ideas.json: adds a 'rising' score from the growth since then")
    ap.add_argument("--max-per-source", type=int, default=25, help="diversity cap inside the overall top (default 25)")
    ap.add_argument("--no-download", action="store_true", help="links only, no asset files")
    ap.add_argument("--max-outputs", type=int, default=2, help="example outputs per idea (default 2)")
    ap.add_argument("--max-inputs", type=int, default=4, help="reference inputs per idea (default 4)")
    ap.add_argument("--max-mb", type=float, default=80, help="skip files larger than this (default 80 MB)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between downloads (default 0.3)")
    ap.add_argument("--out", help="output folder (default exports/trending/<timestamp>)")
    a = ap.parse_args(argv)

    if a.runs:
        runs = [Path(r) for r in a.runs]
    elif a.no_scrape:
        runs = latest_runs_all()
    else:
        runs = run_scrapers(a)
    if not runs:
        print("no run folders found (run without --no-scrape first)", file=sys.stderr)
        return 1
    print("\n[collect] " + "\n          ".join(str(r) for r in runs))
    now = dt.datetime.now(dt.timezone.utc)
    raw, featured = collect(runs, now)
    C = dedupe(raw)
    if not C:
        print("no candidates found in those runs", file=sys.stderr)
        return 1
    prev = json.loads(Path(a.compare).read_text(encoding="utf-8")) if a.compare else None
    score(C, prev)
    chosen = pick(C, a.top, a.per_category, a.max_per_source)
    out = Path(a.out) if a.out else ROOT / "exports" / "trending" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"[rank] {len(raw)} candidates -> {len(C)} unique -> {len(chosen)} idea folders -> {out}")
    print("[rank] by category: " + ", ".join(f"{k} {v}" for k, v in Counter(c["category"] for c in C).most_common()))
    package(chosen, C, featured, out, a)
    print(f"\nDone: {out / 'index.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
