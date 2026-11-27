"""Top trending video ideas / templates from Higgsfield, ranked and packaged one folder per idea.

Pipeline (each step can be skipped):
  1. scrape   - runs the existing scrapers with trending-sorted, capped options (GET only, same politeness as the
                CLI). Nothing is crawled exhaustively: Higgsfield already ranks these lists server-side.
  2. collect  - reads the run outputs and turns every template / video into one "candidate":
                main feed presets (uses = times_made), explore presets, Shorts/Reels presets (recreates),
                community trending + approved videos, studio gallery outputs (Marketing/Ads/Cinema/...).
  3. dedupe   - by publication id / output media key / title.
  4. score    - percentile rank inside each source (so sources with different scales compare fairly):
                usage (uses / recreates) 45 %, likes 30 %, views 25 %; missing metrics are re-weighted.
                With --compare <previous ideas.json> the growth since that snapshot adds a "rising" score.
  5. package  - exports/trending/<timestamp>/
                  index.md, top.csv, top.json, ideas.json (all scored candidates, use as --compare next time)
                  ideas/001_<slug>/README.md, contest_brief.md, idea.json, prompt.txt,
                                   assets/output_*, assets/thumb_*, inputs/ref_*   (references = what the user uploads)

Usage:
  python scripts/trending_ideas.py                       # scrape + rank + package top 100 with assets
  python scripts/trending_ideas.py --no-scrape           # reuse the latest trend-* runs
  python scripts/trending_ideas.py --runs runs/A runs/B  # use these run folders
  python scripts/trending_ideas.py --top 50 --no-download
  python scripts/trending_ideas.py --no-scrape --compare exports/trending/<older>/ideas.json   # rising trends
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import datetime as dt
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
LABEL_PREFIX = "trend-"

# --------------------------------------------------------------------------------------------- 1. scrape
def scrape_plan(a) -> list[tuple[str, list[str]]]:
    return [
        ("showcase", ["scrape", "showcase", "--what", "main_feed,explore_categories,reels_presets",
                      "--main-feed-pages", str(a.pages), "--explore-sort", "trending",
                      "--explore-pages", str(a.pages), "--explore-sources", "higgsfield,community"]),
        ("community", ["scrape", "community", "--feeds", "trending,approved", "--type", "video",
                       "--max-items", str(a.videos)]),
        ("studios", ["scrape", "studios", "--what", "galleries", "--gallery-feeds", "trending,approved",
                     "--gallery-pages", str(max(1, a.pages // 2))]),
    ]


def run_scrapers(a) -> list[Path]:
    out = []
    for name, args in scrape_plan(a):
        label = f"{LABEL_PREFIX}{name}"
        cmd = [sys.executable, "-m", "higgsfield_scraper", *args, "--label", label]
        print(f"\n[scrape] {' '.join(cmd[2:])}", flush=True)
        t = time.time()
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = re.findall(r"run folder: (.+)", (p.stdout or "") + (p.stderr or ""))
        run = Path(m[-1].strip()) if m else latest_run(label)
        print(f"[scrape] {name}: exit {p.returncode} in {time.time() - t:.0f}s -> {run}", flush=True)
        if p.returncode != 0:
            print((p.stderr or p.stdout or "")[-1500:], file=sys.stderr)
        if run:
            out.append(run)
    return out


def latest_run(label: str) -> Path | None:
    c = sorted(p for p in RUNS.glob(f"*_{label}") if (p / "output" / "json").is_dir())
    return c[-1] if c else None


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


def media_of(items):
    """-> (outputs, thumbs) as [{url,type,role}] from the media/results list of any scraper.
    Videos are outputs (full quality first); images next to a video, or roles named thumb/poster, are thumbnails."""
    items = [m for m in items or [] if isinstance(m, dict) and m.get("url")]
    has_video = any((m.get("type") or "") == "video" or str(m["url"]).lower().endswith(".mp4") for m in items)
    outs, thumbs = [], []
    for m in items:
        role = (m.get("role") or m.get("name") or "").lower()
        e = {"url": m["url"], "type": m.get("type"), "role": role}
        is_img = (m.get("type") or "") == "image" or re.search(r"\.(webp|png|jpe?g)(\?|$)", m["url"].lower())
        if "thumb" in role or "poster" in role or (has_video and is_img):
            thumbs.append(e)
        else:
            outs.append(e)
    outs.sort(key=lambda e: (("min" in e["role"]) or ("compressed" in e["role"]), ))   # full quality first
    return outs, thumbs


def inputs_of(items) -> list[dict]:
    res = []
    for m in items or []:
        if isinstance(m, dict) and m.get("url"):
            res.append({"url": m["url"], "type": m.get("type"),
                        "role": m.get("source_role") or m.get("role") or m.get("param")})
    return res


def cand(**kw) -> dict:
    base = dict(source="", kind="", key=None, title=None, description=None, prompt=None, model=None,
                category=None, hashtags=[], uses=None, likes=None, views=None, comments=None, page_url=None,
                published_at=None, outputs=[], thumbs=[], inputs=[], settings=None, variants=[], dedupe=[])
    base.update(kw)
    return base


def collect(runs: list[Path]) -> list[dict]:
    C = []
    for run in runs:
        # --- main feed + explore presets (templates people re-use: uses = times_made)
        for items_f, vars_f, src in (("main_feed_items.json", "main_feed_variants.json", "main_feed"),
                                     ("explore_items.json", "explore_variants.json", "explore")):
            variants: dict[str, list] = {}
            for v in load(run, vars_f):
                variants.setdefault(v.get("item_id"), []).append(v)
            for it in load(run, items_f):
                vs = variants.get(it.get("item_id"), [])
                outs, thumbs, ins, prompts, vlist = [], [], [], [], []
                ov = it.get("original_video")
                if isinstance(ov, dict) and ov.get("url"):
                    outs.append({"url": ov["url"], "type": "video", "role": "original"})
                for v in vs:
                    o, t = media_of(v.get("media"))
                    outs += o; thumbs += t; ins += inputs_of(v.get("inputs"))
                    if v.get("prompt"):
                        prompts.append(v["prompt"])
                    vlist.append({"variant_type": v.get("variant_type"), "prompt": v.get("prompt"),
                                  "params": v.get("params"), "publication_id": v.get("publication_id"),
                                  "publication_engagement": v.get("publication_engagement")})
                e = it.get("engagement") or {}
                C.append(cand(source=src, kind="template", key=f"{src}:{it.get('item_id')}",
                              title=it.get("title"), description=it.get("description"),
                              prompt=prompts[0] if prompts else None, model=it.get("job_set_type"),
                              category=it.get("category"), uses=num(e.get("uses")), likes=num(e.get("likes")),
                              views=num(e.get("views")), comments=num(e.get("comments")),
                              page_url=it.get("source_url"), outputs=outs, thumbs=thumbs, inputs=ins,
                              variants=vlist,
                              dedupe=[f"pub:{p}" for p in it.get("publication_ids") or []] + [f"item:{it.get('item_id')}"]))
        # --- Shorts / Reels presets (recreates = remakes)
        for r in load(run, "reels_presets.json"):
            e = r.get("engagement") or {}
            o, t = media_of(r.get("media"))
            C.append(cand(source="reels", kind="template", key=f"reels:{r.get('preset_id')}", title=r.get("title"),
                          description=r.get("description"), prompt=r.get("prompt") or r.get("script"),
                          model=r.get("job_set_type"), category=r.get("category_label") or r.get("category"),
                          hashtags=r.get("hashtags") or [], uses=num(r.get("recreates") if r.get("recreates") is not None else e.get("uses")),
                          # likes/views: the Higgsfield publication if any, else the original social reel it copies
                          likes=num(e.get("likes") if e.get("likes") is not None else (r.get("reference_engagement") or {}).get("likes")),
                          views=num(e.get("views") if e.get("views") is not None else (r.get("reference_engagement") or {}).get("views")),
                          comments=num(e.get("comments") if e.get("comments") is not None else (r.get("reference_engagement") or {}).get("comments")),
                          page_url=r.get("source_url"), outputs=o, thumbs=t, inputs=inputs_of(r.get("inputs")),
                          settings={"quality": r.get("quality"), "duration_s": r.get("duration_s"),
                                    "own_recording": r.get("own_recording"), "instructions": r.get("instructions"),
                                    "reference_url": r.get("reference_url"), "reference_platform": r.get("reference_platform"),
                                    "reference_engagement": r.get("reference_engagement")},
                          dedupe=[f"preset:{r.get('preset_id')}"] + (r.get("media_keys") or [])[:1]))
        # --- community trending / approved videos
        for g in load(run, "generations.json"):
            if (g.get("media_type") or "").lower() not in ("video", ""):
                continue
            o, t = media_of(g.get("results"))
            if not any((x.get("type") or "") == "video" or str(x["url"]).endswith(".mp4") for x in o):
                continue
            e = g.get("engagement") or {}
            src = g.get("source") if isinstance(g.get("source"), dict) else {}
            C.append(cand(source="community", kind="video", key=f"gen:{g.get('generation_id')}",
                          title=None, description=None, prompt=g.get("prompt"), model=g.get("job_set_type"),
                          likes=num(e.get("likes")), views=num(e.get("views")),
                          page_url=src.get("url") if isinstance(src, dict) else None,
                          published_at=g.get("published_at"), outputs=o, thumbs=t, inputs=inputs_of(g.get("inputs")),
                          settings=g.get("settings"),
                          dedupe=[f"pub:{g.get('publication_id')}", f"job:{g.get('generation_id')}"]))
        # --- studio gallery outputs (Marketing Studio ads, Cinema Studio, AI Influencer, Canvas, ...)
        for g in load(run, "gallery_items.json"):
            o, t = media_of(g.get("media"))
            if not any((x.get("type") or "") == "video" for x in o):
                continue
            e = g.get("engagement") or {}
            preset = g.get("preset")
            C.append(cand(source=f"studio:{g.get('studio')}", kind="video", key=f"gal:{g.get('job_id')}",
                          title=(preset or {}).get("name") if isinstance(preset, dict) else None,
                          prompt=g.get("prompt") or g.get("enhanced_prompt"), model=g.get("job_set_type"),
                          category=g.get("studio"), likes=num(e.get("likes")), views=num(e.get("views")),
                          page_url=g.get("source_url"), published_at=g.get("published_at"),
                          outputs=o, thumbs=t, inputs=inputs_of(g.get("inputs")), settings=g.get("settings"),
                          dedupe=[f"pub:{g.get('publication_id')}", g.get("generation_key")]))
    return C


# --------------------------------------------------------------------------------------------- 3/4. dedupe + score
def dedupe(C: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    out = []
    for c in sorted(C, key=lambda c: 0 if c["kind"] == "template" else 1):   # keep the template record first
        keys = [k for k in c["dedupe"] if k and not k.endswith(":None")]
        if c["title"]:
            keys.append("title:" + re.sub(r"\W+", "", c["title"].lower()))
        hit = next((seen[k] for k in keys if k in seen), None)
        if hit:   # merge metrics: keep the max of each
            for m in ("uses", "likes", "views", "comments"):
                if c[m] is not None and (hit[m] is None or c[m] > hit[m]):
                    hit[m] = c[m]
            hit.setdefault("also_in", []).append(c["source"])
            continue
        for k in keys:
            seen[k] = c
        out.append(c)
    return out


def pct_rank(values: list[float | None]) -> list[float | None]:
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return [None] * len(values)
    n = len(xs)
    from bisect import bisect_left, bisect_right
    return [None if v is None else ((bisect_left(xs, v) + bisect_right(xs, v)) / 2) / n for v in values]


WEIGHTS = {"uses": 0.45, "likes": 0.30, "views": 0.25}


def score(C: list[dict], previous: dict[str, dict] | None) -> None:
    by_src: dict[str, list[dict]] = {}
    for c in C:
        by_src.setdefault(c["source"].split(":")[0], []).append(c)
    for group in by_src.values():
        pr = {m: pct_rank([c[m] for c in group]) for m in WEIGHTS}
        for i, c in enumerate(group):
            num_, den = 0.0, 0.0
            for m, w in WEIGHTS.items():
                if pr[m][i] is not None:
                    num_ += w * pr[m][i]; den += w
            c["score_popular"] = round(100 * num_ / den, 2) if den else 0.0
            # sources with a usage signal (templates people actually re-use) rank a bit higher
            c["score_popular"] *= 1.0 if c["uses"] is not None else 0.9
    if previous:
        for c in C:
            p = previous.get(c["key"])
            if p:
                c["growth"] = {m: (c[m] - p[m]) if c[m] is not None and p.get(m) is not None else None
                               for m in WEIGHTS}
        gr = {m: pct_rank([(c.get("growth") or {}).get(m) for c in C]) for m in WEIGHTS}
        for i, c in enumerate(C):
            vals = [(WEIGHTS[m], gr[m][i]) for m in WEIGHTS if gr[m][i] is not None]
            c["score_rising"] = round(100 * sum(w * v for w, v in vals) / sum(w for w, _ in vals), 2) if vals else None
    for c in C:
        r = c.get("score_rising")
        c["score"] = round(c["score_popular"] if r is None else 0.5 * c["score_popular"] + 0.5 * r, 2)


def pick(C: list[dict], top: int, max_per_source: int) -> list[dict]:
    per: dict[str, int] = {}
    out = []
    for c in sorted(C, key=lambda c: (-c["score"], -(c["uses"] or 0), -(c["likes"] or 0), -(c["views"] or 0))):
        s = c["source"].split(":")[0]
        if per.get(s, 0) >= max_per_source:
            continue
        per[s] = per.get(s, 0) + 1
        out.append(c)
        if len(out) >= top:
            break
    return out


# --------------------------------------------------------------------------------------------- 5. package
def slug(s: str | None, n=50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:n].rstrip("-")) or "untitled"


def fmt(v):
    return "–" if v is None else f"{int(v):,}"


def ext_of(url: str, typ: str | None) -> str:
    m = re.search(r"\.(mp4|mov|webm|webp|png|jpe?g|gif|m3u8)(\?|$)", url.lower())
    return "." + m.group(1) if m else (".mp4" if typ == "video" else ".jpg")


CACHE = ROOT / "exports" / "trending" / "_cache"   # one copy per URL; idea folders get hard links (no extra disk)


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
        with urllib.request.urlopen(req, timeout=60) as r:
            size = int(r.headers.get("Content-Length") or 0)
            if size and size > max_mb * 1e6:
                return f"too big ({size / 1e6:.0f} MB)"
            data = r.read(int(max_mb * 1e6) + 1)
        if len(data) > max_mb * 1e6:
            return "too big"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return "ok"
    except Exception as e:  # noqa: BLE001 - a failed asset must not stop the package
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
        words = re.findall(r"[^\W\d_]{2,}", t)
        if len(words) < 4 or t.isupper() or t.lower().startswith(("prompt", "scene context")):
            continue
        return (t[:70].rstrip() + "…") if len(t) > 70 else t
    return f"{c['model'] or 'video'} ({c['source']})"


def package(top: list[dict], all_c: list[dict], out: Path, a) -> None:
    ideas = out / "ideas"
    ideas.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, c in enumerate(top, 1):
        name = f"{i:03d}_{slug(title_of(c))}"
        d = ideas / name
        d.mkdir(exist_ok=True)
        c["rank"], c["folder"] = i, f"ideas/{name}"
        assets = []
        if not a.no_download:
            jobs = ([("assets", f"output_{k + 1}", m) for k, m in enumerate(c["outputs"][: a.max_outputs])]
                    + [("assets", f"thumb_{k + 1}", m) for k, m in enumerate(c["thumbs"][:2])]
                    + [("inputs", f"ref_{k + 1}_{slug(m.get('role') or 'input', 20)}", m)
                       for k, m in enumerate(c["inputs"][: a.max_inputs])])
            for sub, base, m in jobs:
                f = d / sub / (base + ext_of(m["url"], m.get("type")))
                st = download(m["url"], f, a.max_mb)
                assets.append({"file": f"{sub}/{f.name}" if st in ("ok", "cached") else None, "url": m["url"],
                               "role": m.get("role"), "status": st})
                if st == "ok":
                    time.sleep(a.delay)
        c["assets"] = assets
        (d / "idea.json").write_text(json.dumps(c, indent=4, ensure_ascii=False, default=str), encoding="utf-8")
        if c["prompt"]:
            (d / "prompt.txt").write_text(c["prompt"], encoding="utf-8")
        (d / "README.md").write_text(readme(c), encoding="utf-8")
        (d / "contest_brief.md").write_text(brief(c), encoding="utf-8")
        rows.append(c)
        print(f"[package] {i:3d}/{len(top)} {name}  ({sum(1 for x in assets if x['file'])} files)", flush=True)

    cols = ["rank", "score", "score_popular", "score_rising", "source", "kind", "title", "model", "category",
            "uses", "likes", "views", "comments", "page_url", "folder", "prompt"]
    with (out / "top.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for c in rows:
            w.writerow({**c, "title": title_of(c)})
    (out / "top.json").write_text(json.dumps(rows, indent=4, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "ideas.json").write_text(json.dumps({c["key"]: {m: c[m] for m in ("uses", "likes", "views", "comments")}
                                                for c in all_c}, indent=4), encoding="utf-8")
    (out / "index.md").write_text(index_md(rows, all_c, a), encoding="utf-8")


def readme(c: dict) -> str:
    L = [f"# #{c['rank']} {title_of(c)}", "",
         f"**Score** {c['score']} (popular {c['score_popular']}" + (f", rising {c['score_rising']}" if c.get("score_rising") is not None else "") + ")  ",
         f"**Source** {c['source']} · **kind** {c['kind']} · **model** `{c['model']}`" + (f" · **category** {c['category']}" if c["category"] else ""), "",
         "| uses / remakes | likes | views | comments |", "|---:|---:|---:|---:|",
         f"| {fmt(c['uses'])} | {fmt(c['likes'])} | {fmt(c['views'])} | {fmt(c['comments'])} |", ""]
    if c.get("growth"):
        L += ["Growth since the compared snapshot: " + ", ".join(f"{k} {'+' if (v or 0) >= 0 else ''}{fmt(v)}" for k, v in c["growth"].items()), ""]
    if c["description"]:
        L += ["## What it is", c["description"], ""]
    if c["prompt"]:
        L += ["## Prompt", "```", c["prompt"], "```", ""]
    if c["hashtags"]:
        L += ["**Hashtags** " + " ".join("#" + h for h in c["hashtags"]), ""]
    if c["inputs"]:
        L += ["## User input (references)", *[f"- {m.get('role') or 'input'} ({m.get('type') or '?'}): {m['url']}" for m in c["inputs"]], ""]
    if c["variants"]:
        L += ["## Variants", *[f"- {v['variant_type']}: {v['prompt'] or '(no prompt)'}" for v in c["variants"]], ""]
    if c["settings"]:
        s = {k: v for k, v in c["settings"].items() if v not in (None, "", [], {})}
        if s:
            L += ["## Settings", "```json", json.dumps(s, indent=2, ensure_ascii=False, default=str), "```", ""]
    lines = [f"- [{x['file']}]({x['file']})" if x["file"] else f"- {x['role']}: {x['url']} ({x['status']})"
             for x in c.get("assets", [])]
    lines = lines or [f"- {m['role']}: {m['url']}" for m in c["outputs"] + c["thumbs"] + c["inputs"]]
    L += ["## Assets", *lines, ""]
    if c["page_url"]:
        L += [f"Source page: {c['page_url']}", ""]
    if c.get("also_in"):
        L += ["Also found in: " + ", ".join(sorted(set(c["also_in"]))), ""]
    return "\n".join(L)


def brief(c: dict) -> str:
    ins = ", ".join(sorted({f"{m.get('type') or 'file'} ({m.get('role') or 'input'})" for m in c["inputs"]})) or "?"
    return "\n".join([
        f"# Contest brief draft: {title_of(c)}", "",
        "Inspiration only. The contest rejects copies of competitor templates: add your own twist and 2+ MyZesty features.", "",
        "| Field | Draft |", "|---|---|",
        f"| Idea name | _your name for the twist_ (inspired by: {title_of(c)}) |",
        "| Hook | _what stops the scroll in the first 2 s_ |",
        f"| Concept | {(c['description'] or (c['prompt'] or '')[:200]).replace('|', '/')} |",
        f"| Reference | {c['page_url'] or (c['outputs'][0]['url'] if c['outputs'] else '')} |",
        f"| Trend | {fmt(c['uses'])} uses/remakes, {fmt(c['likes'])} likes, {fmt(c['views'])} views on Higgsfield ({c['source']}) |",
        f"| User input | {ins} |",
        "| Visual | see assets/ (example output) and inputs/ (reference inputs) |",
        "| Target user | _who uses it and for what_ |",
        "| MyZesty features | _AI Animate / Product Video / Story+ / Ads Creator / Templates_ |", ""])


def index_md(rows, all_c, a) -> str:
    from collections import Counter
    L = [f"# Top {len(rows)} trending video ideas and templates", "",
         f"Generated {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} from {len(all_c)} unique candidates. "
         "Score = percentile inside each source: usage (uses/remakes) 45 %, likes 30 %, views 25 %"
         + ("; 50 % rising (growth vs the compared snapshot)." if any(c.get("score_rising") is not None for c in rows) else "."), "",
         "Candidates per source: " + ", ".join(f"{k} {v}" for k, v in Counter(c["source"] for c in all_c).most_common()), "",
         "| # | score | idea | source | model | uses | likes | views | folder |", "|---:|---:|---|---|---|---:|---:|---:|---|"]
    for c in rows:
        t = title_of(c).replace("|", "/")
        L.append(f"| {c['rank']} | {c['score']} | {t} | {c['source']} | `{c['model']}` | {fmt(c['uses'])} | "
                 f"{fmt(c['likes'])} | {fmt(c['views'])} | [{c['folder']}]({c['folder']}/README.md) |")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--top", type=int, default=100, help="ideas to package (default 100)")
    ap.add_argument("--pages", type=int, default=5, help="pages per trending list: main feed, explore; studios = half (default 5)")
    ap.add_argument("--videos", type=int, default=500, help="community videos per feed, trending + approved (default 500)")
    ap.add_argument("--no-scrape", action="store_true", help="reuse the latest trend-* runs")
    ap.add_argument("--runs", nargs="*", help="explicit run folders to read (implies --no-scrape)")
    ap.add_argument("--compare", help="previous ideas.json: adds a 'rising' score from the growth since then")
    ap.add_argument("--max-per-source", type=int, default=25, help="keep the list diverse (default 25 per source)")
    ap.add_argument("--no-download", action="store_true", help="links only, no asset files")
    ap.add_argument("--max-outputs", type=int, default=2, help="output videos per idea (default 2)")
    ap.add_argument("--max-inputs", type=int, default=4, help="reference inputs per idea (default 4)")
    ap.add_argument("--max-mb", type=float, default=60, help="skip files larger than this (default 60 MB)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between downloads (default 0.3)")
    ap.add_argument("--out", help="output folder (default exports/trending/<timestamp>)")
    a = ap.parse_args(argv)

    if a.runs:
        runs = [Path(r) for r in a.runs]
    elif a.no_scrape:
        runs = [r for r in (latest_run(f"{LABEL_PREFIX}{n}") for n in ("showcase", "community", "studios")) if r]
    else:
        runs = run_scrapers(a)
    if not runs:
        print("no run folders found (run without --no-scrape first)", file=sys.stderr)
        return 1
    print("\n[collect] " + ", ".join(str(r) for r in runs))
    C = dedupe(collect(runs))
    if not C:
        print("no candidates found in those runs", file=sys.stderr)
        return 1
    prev = json.loads(Path(a.compare).read_text(encoding="utf-8")) if a.compare else None
    score(C, prev)
    top = pick(C, a.top, a.max_per_source)
    out = Path(a.out) if a.out else ROOT / "exports" / "trending" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"[rank] {len(C)} unique candidates -> top {len(top)} -> {out}")
    package(top, C, out, a)
    print(f"\nDone: {out / 'index.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
