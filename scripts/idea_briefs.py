"""Write an idea brief (Idea name, Hook, Concept, Trend it rides, User input, Target user, Reference link, Visual
files) for every idea of a scripts/trending_ideas.py package, using ONLY the scraped data of that idea (no invented
facts). trending_ideas.py writes one for every idea it packages; run this alone to (re)write a package's briefs.

Usage:
  python scripts/idea_briefs.py exports/trending/<timestamp>
Writes <idea folder>/brief.md for every idea + <package>/briefs.md and briefs.csv (all briefs in one place).

Where each field comes from:
  Idea name   template / reel / film title; else the first meaningful words of the prompt (or the effect name)
  Hook        reel: first sentence of the narration script; prompt: its first time-coded segment (0s-2s / 0-3s ...)
              or 'Hook:' line; template: first sentence of its description; else the first visual sentence of the prompt
  Concept     description (templates, reels, films) else the first sentences of the prompt, max ~3 lines
  Trend       format/theme tags + the measured numbers (uses/remakes, views, likes, views/day, trending position,
              the original social reel's reach and platform, hashtags)
  User input  the input roles the generation actually used (photos per person, character photo, product photos,
              avatar, reference video, own recording) + the text the user types
  Target user rule from the category + the item's own topic / hashtags / themes
  Reference   Higgsfield page, the original it is modelled on (social reel / source video / trailer), direct MP4s
  Visual      up to 5 downloaded files of the idea (outputs, thumbnails, reference inputs), each <= 100 MB
Fields the source does not contain are written as "Not in the source data".
"""
from __future__ import annotations

import csv
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

NOSRC = "Not in the source data (see the preview video in assets/)"


def clean(t: str | None) -> str:
    t = re.sub(r"<<<[^>]*>>>\s?(s\b)?", " ", t or "")         # avatar/image tokens (+ a stray plural 's')
    t = re.sub(r"\b(SCENE CONTEXT|SCENE BACKGROUND|ACTIVE REFERENCES?)\b\s*:?", ". ", t)
    t = re.sub(r"@?image_?\d+|@image\d*", "the reference", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def sentences(t: str) -> list[str]:
    t = re.sub(r"\b(prompt|промт|style)\s*:", "\n", t, flags=re.I)    # labels start a new sentence
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if s.strip()]


SKIP = re.compile(r"^(prompt|style|camera( settings)?|light(ing)?|lens|aspect|format|duration|resolution|"
                  r"audio|sound|music|sfx|negative|technical|shot on|focal|aperture|\d+\s*(s|sec|seconds)\b|"
                  r"approximately|\d+:\d+|vertical|16:9|9:16)", re.I)
VERB = re.compile(r"\b(is|are|was|stands|walks|holds|films|records|sits|runs|dances|looks)\b", re.I)


def meaningful(t: str) -> list[str]:
    out = []
    for s in sentences(t):
        s2 = re.sub(r"^\[[^\]]*\][^:]*:\s*", "", s)                     # "[date] name: ..."
        s2 = re.sub(r"^[\W_]+", "", s2).strip()
        words = re.findall(r"[^\W\d_]{2,}", s2)
        style_list = s2.count(",") >= 3 and len(words) < 14 and not VERB.search(s2)
        if len(words) < 4 or s2.isupper() or SKIP.match(s2) or style_list:
            continue
        out.append(re.sub(r"\s+", " ", s2))
    return out


def short(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"


def idea_name(c: dict) -> str:
    if c.get("title") and not c["title"].lower().startswith(("a ", "the ")) and len(c["title"]) <= 45:
        return c["title"].removeprefix("Effect: ")
    src = c.get("title") or (meaningful(clean(c.get("prompt"))) or [""])[0]
    words = re.findall(r"[^\W_][\w'’-]*", src)
    stop = {"a", "an", "the", "of", "in", "on", "with", "and", "for", "to", "at", "by", "video", "second", "seconds",
            "is", "are", "or", "her", "his", "their"}
    stop |= {"no", "one", "16", "9", "take"} if re.search(r"\bone unbroken\b|\bno cuts\b", src, re.I) else set()
    keep = [w for w in words if w.lower() not in stop and not re.fullmatch(r"\d+(-second|-sec)?|\d+:\d+", w)][:5]
    fix = lambda w: w.capitalize() if w.islower() or (w.isupper() and len(w) > 3) else w
    return " ".join(fix(w) for w in keep) or (c.get("model") or "Untitled")


def hook(c: dict) -> str:
    st = c.get("settings") or {}
    if st.get("script"):                                       # reels: the narration opens the video
        s = sentences(clean(st["script"]))
        if s:
            return f'Opens with the line: "{short(s[0], 160)}"'
    p = clean(c.get("prompt"))
    m = re.search(r"\(?\b0(\.0)?\s*(s|sec)?\s*[–\-—]\s*[1-5](\.\d)?\s*(s|sec)\w*\)?\s*[:.\-—]?\s*(.+?)"
                  r"(?=\(?\b\d+(\.\d)?\s*(s|sec)?\s*[–\-—]\s*\d|$)", p, re.I | re.S)
    if m:
        return short(m.group(5), 200)
    m = re.search(r"\bhook\s*[:\-—]\s*(.+?)(?=[.!?]\s|$)", p, re.I)
    if m:
        return short(m.group(1), 200)
    if c.get("description"):
        return short(sentences(clean(c["description"]))[0], 200)
    ms = meaningful(p)
    return short(ms[0], 200) if ms else NOSRC


def concept(c: dict) -> str:
    if c.get("description"):
        base = clean(c["description"])
        extra = clean(c.get("prompt")) if c.get("category") == "reels_shorts" else ""
        return short(base + (f" Topic: {extra}" if extra and extra.lower() not in base.lower() else ""), 330)
    ms = meaningful(clean(c.get("prompt")))
    if ms:
        return short(" ".join(ms[:3]), 330)
    return short(clean(c.get("prompt")), 330) or NOSRC


def n(v):
    return f"{int(v):,}" if v is not None else None


STRICT = {"Cars / driving": r"driving|racing|race car|supercar|highway|drift|behind the wheel|car chase|road trip|convertible"}


def themes(c: dict) -> list[str]:
    """The package's theme tags, re-checked with stricter rules (a passing 'fits in my car' is not a car video)."""
    text = " ".join(str(x) for x in (c.get("title"), c.get("description"), c.get("prompt"), c.get("topic")) if x).lower()
    return [t for t in (c.get("themes") or []) if t not in STRICT or re.search(STRICT[t], text)]


def trend(c: dict) -> str:
    parts = []
    th = themes(c)
    if th:
        parts.append(" + ".join(th) + " format")
    m = []
    if c.get("uses") is not None:
        m.append(f"{n(c['uses'])} {'remakes' if c['category'] == 'reels_shorts' else 'uses'} on Higgsfield")
    st = c.get("settings") or {}
    ref = st.get("reference_engagement") or {}
    if ref.get("views"):
        m.append(f"the original {st.get('reference_platform') or 'social'} reel it is modelled on has "
                 f"{n(ref['views'])} views / {n(ref.get('likes'))} likes")
    elif c.get("views") is not None:
        m.append(f"{n(c['views'])} views, {n(c.get('likes')) or 0} likes")
    if c.get("views_per_day"):
        m.append(f"{n(c['views_per_day'])} views/day")
    if c.get("category") == "featured":
        m.append(f"featured by Higgsfield (#{c.get('rank')} in its {c['source'].split(':')[-1].replace('_', ' ')} list)")
    elif c.get("position"):
        m.append(f"#{c['position']} in Higgsfield's trending list")
    if m:
        parts.append("; ".join(m))
    if c.get("hashtags"):
        parts.append(" ".join("#" + str(h) for h in c["hashtags"][:6]))
    if c.get("published_at") and c.get("age_days") is not None:
        parts.append(f"published {c['age_days']:.0f} days ago")
    return ". ".join(parts) or "Not in the source data"


def user_input(c: dict) -> str:
    cat = c.get("category")
    st = c.get("settings") or {}
    if cat == "films":
        return "Not in the source data (published projects do not expose their inputs)"
    if cat == "featured":
        ins = st.get("inputs") or []
        if not ins:
            return "Not in the source data"

        def one(x):
            t = x.get("type") or "media"
            k = x.get("max") or x.get("min") or 1
            req = "" if x.get("required", t != "text") else " (optional)"
            return (f"{k} {t}{'s' if k > 1 else ''}" if t != "text" else "text") + f" ('{x.get('label') or t}'){req}"
        return " + ".join(one(x) for x in ins)
    roles = Counter()
    for i in c.get("inputs") or []:
        r = (i.get("role") or "").lower()
        if r in ("reference_compressed", "reference_thumbnail"):
            continue
        roles[(r, "video" if "video" in (i.get("type") or "").lower() else "image")] += 1
    out = []
    if cat == "reels_shorts":
        if roles.get(("character", "image")):
            out.append("1 photo of the presenter / character")
        if st.get("own_recording"):
            out.append("own video recording")
        out.append("a topic sentence (what the reel is about)")
        return " + ".join(out)
    for (r, t), k in sorted(roles.items()):
        if cat == "templates":
            out.append(f"{k} photo{'s' if k > 1 else ''} ({'one per person in the video' if k > 1 else 'of the person / subject'})")
        elif r == "avatars":
            out.append(f"{k} avatar / presenter photo")
        elif r == "medias":
            out.append(f"{k} product photo{'s' if k > 1 else ''}")
        elif t == "video":
            out.append(f"{k} reference video")
        else:
            out.append(f"{k} reference image{'s' if k > 1 else ''}")
    if c.get("prompt") and cat != "templates":
        out.append("a text prompt")
    return " + ".join(out) or "Text prompt only"


def target_user(c: dict) -> str:
    cat = c.get("category")
    th = set(themes(c))
    tags = " ".join("#" + str(h) for h in (c.get("hashtags") or [])[:4])
    topic = c.get("topic")
    if cat == "ads" or c.get("source", "").endswith("marketing_preset"):
        kind = ("Fashion / apparel brands" if "Get ready with me / try-on / outfit" in th else
                "E-commerce sellers reviewing products" if "Unboxing / product review" in th else
                "Brands and e-commerce sellers")
        return f"{kind} making {'UGC-style ' if 'UGC / selfie / vlog' in th else ''}video ads for TikTok / Reels / Shorts"
    if cat == "reels_shorts":
        return f"Creators and small businesses posting faceless talking reels{(' about ' + tags) if tags else ''}"
    if cat == "templates":
        text = f"{c.get('title') or ''} {c.get('description') or ''} {topic or ''}"
        group = re.search(r"\b(2|3|two|three|trio|crew|friends|couple|group)\b", text, re.I)
        who = "Friends / groups who want to star together" if group else "People who want to put themselves"
        return f"{who} in a viral {'dance ' if 'Dance / performance' in th else ''}clip for social posts" + (f" (topic: {topic})" if topic else "")
    if cat == "films":
        return "Storytellers and indie filmmakers making AI short films / series"
    if cat == "featured":
        return f"Creators applying a one-tap {topic or 'viral'} effect to their own photo / video for social posts"
    if "Commercial / brand ad" in th:
        return "Brands and agencies making cinematic product commercials"
    return "Creators making cinematic short-form videos" + (f" ({', '.join(sorted(th))})" if th else "")


FIELDS = ["Idea name", "Hook", "Concept", "Trend it rides", "User input", "Target user", "Reference link", "Visual files"]
MAX_FILE = 100 * 1024 * 1024      # visual files listed per idea: at most 5, each <= 100 MB


def reference_link(c: dict) -> str:
    """Higgsfield page, the original the idea is modelled on, and direct MP4 links (one labelled line each)."""
    st = c.get("settings") or {}

    def is_mp4(u):
        return bool(re.search(r"\.(mp4|mov|webm)(\?|$)", (u or "").lower()))

    lines = []
    page = c.get("page_url") or ""
    lines.append(f"Higgsfield: {page}" if page.startswith("https://higgsfield.ai/")
                 else "Higgsfield: no public page in the source data (use the MP4 below)")
    # original = what the idea is modelled on: the social reel (reels), the source video (templates), the trailer (films)
    orig = []
    if st.get("reference_url"):
        orig.append(f"{st['reference_url']} ({st.get('reference_platform') or 'social'} reel)")
    orig += [i["url"] for i in c.get("inputs") or [] if i.get("role") == "reference" and is_mp4(i.get("url"))]
    orig += [o["url"] for o in c.get("outputs") or [] if o.get("role") in ("original", "trailer") and is_mp4(o.get("url"))]
    lines.append("Original: " + (" · ".join(dict.fromkeys(orig)) if orig else "not in the source data"))
    used = set(orig)
    mp4 = [o["url"] for o in c.get("outputs") or [] if is_mp4(o.get("url")) and o["url"] not in used]
    if mp4:
        lines.append("MP4: " + " · ".join(list(dict.fromkeys(mp4))[:3]))
    else:
        hls = next((o["url"] for o in c.get("outputs") or [] if ".m3u8" in o.get("url", "")), None)
        lines.append("MP4: none in the source data" + (f" (HLS stream only: {hls})" if hls else ""))
    return "\n".join(lines)


def visual_files(folder: Path) -> list[Path]:
    """Up to 5 local files (<= 100 MB each): example outputs first, then thumbnails, then reference inputs."""
    order = sorted(folder.glob("assets/output_*")) + sorted(folder.glob("assets/thumb_*")) + sorted(folder.glob("inputs/*"))
    return [p.resolve() for p in order if p.is_file() and p.stat().st_size <= MAX_FILE][:5]


def brief_of(c: dict, folder: Path) -> dict:
    files = visual_files(folder)
    return {"Idea name": idea_name(c), "Hook": hook(c), "Concept": concept(c), "Trend it rides": trend(c),
            "User input": user_input(c), "Target user": target_user(c), "Reference link": reference_link(c),
            "Visual files": "\n".join(f"{p} ({p.stat().st_size / 1e6:.1f} MB)" for p in files)
            or "No downloaded file (see the links in README.md)"}


def brief_md(c: dict, folder: Path, root: Path | None = None) -> tuple[str, dict]:
    """-> (markdown, fields) for one idea folder."""
    form = brief_of(c, folder)
    rel = folder.relative_to(root).as_posix() if root else folder.name
    md = [f"# Idea brief: {form['Idea name']}", "",
          f"Source: {rel} · {c.get('source')} · rank {c.get('rank')}", "",
          "Every field comes from this idea's scraped data; fields the source does not contain say so.", ""]
    for k in FIELDS:
        if k == "Reference link":
            md += ["## Reference and visual", ""]
        val = form[k]
        if k == "Visual files" and not val.startswith("No downloaded"):
            val = "\n".join(f"- `{line}`" for line in val.splitlines())
        elif k == "Reference link":
            val = "\n".join(f"- {line}" for line in val.splitlines())
        md += [f"**{k}**", "", val, ""]
    return "\n".join(md), form


def write_brief(c: dict, folder: Path) -> dict:
    """Write <folder>/brief.md (used by trending_ideas.py) and return the fields."""
    md, form = brief_md(c, folder)
    (folder / "brief.md").write_text(md, encoding="utf-8")
    return form


def main(pkg: str) -> int:
    root = Path(pkg)
    files = sorted(glob.glob(str(root / "ideas" / "*" / "*" / "idea.json"))) + \
        sorted(glob.glob(str(root / "featured" / "*" / "*" / "idea.json")))
    rows = []
    for f in files:
        c = json.loads(Path(f).read_text(encoding="utf-8"))
        folder = Path(f).parent
        md, form = brief_md(c, folder, root)
        (folder / "brief.md").write_text(md, encoding="utf-8")
        rows.append({"folder": folder.relative_to(root).as_posix(), "category": c.get("category"),
                     "rank": c.get("rank"), **form, "source_page": c.get("page_url")})
    with (root / "briefs.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["folder", "category", "rank", *FIELDS, "source_page"])
        w.writeheader()
        w.writerows(rows)
    L = ["# Idea briefs", "", "Every field comes from the idea's own scraped data; missing ones say so.", ""]
    for r in rows:
        L += [f"## {r['folder']}", ""] + [f"- **{k}:** {r[k]}" for k in FIELDS] + [""]
    (root / "briefs.md").write_text("\n".join(L), encoding="utf-8")
    print(f"{len(rows)} briefs -> {root / 'briefs.md'} , {root / 'briefs.csv'} and brief.md in every idea folder")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("exports/trending/2*"))[-1]))
