"""Pure parsers: Envelope (raw/ archive) -> showcase entity dicts. No network, no Scrapy.

Non-JSON sources are converted by the spider *before* archiving (see spider.convert_body), so `normalize` re-parses
the same small JSON bodies:
  showcase_effect_page                 {"slug", "loader": {preset, initialSamples, sample}}   (TanStack SSR state)
  showcase_property_studio_presets     {"chunk", "lang", "rows": [[format, path, title_id, inputs, w, h]], "titles"}
  showcase_api_docs                    {"text": <llms-full.txt>, "openapi": <openapi.json or null>}
  showcase_effects_sitemap             {"slugs": [...]}             (no entities)
  showcase_property_studio_page/_route_chunk                          (no entities; discovery only)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from urllib.parse import quote

from ...schemas.common import make_id
from .endpoints import INPUT_HOSTS, PROPERTY_FORMAT_APP, SITE, STATIC

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
EXT_TYPE = {"mp4": "video", "webm": "video", "mov": "video", "m3u8": "hls", "webp": "image", "jpg": "image",
            "jpeg": "image", "png": "image", "gif": "image", "mp3": "audio", "wav": "audio"}


# ------------------------------------------------------------------ helpers
def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _i(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ts(v: Any) -> Optional[str]:
    """epoch seconds (float) or ISO string -> ISO-8601 UTC."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat()
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def media_key(url: Optional[str], explicit: Any = None) -> Optional[str]:
    """CDN file id: an explicit media id, else the last UUID in the URL path."""
    if _s(explicit) and UUID_RE.fullmatch(str(explicit).strip()):
        return str(explicit).strip().lower()
    if not url:
        return None
    found = UUID_RE.findall(str(url).split("?")[0])
    return found[-1].lower() if found else None


def is_input_url(url: Optional[str]) -> bool:
    return bool(url) and any(h in str(url) for h in INPUT_HOSTS)


def _type(t: Any, url: Optional[str]) -> Optional[str]:
    t = _s(t)
    if t in ("static", "image"):
        return "image"
    if t in ("video", "audio", "hls"):
        return t
    if url:
        ext = str(url).split("?")[0].rsplit(".", 1)[-1].lower()
        return EXT_TYPE.get(ext, t)
    return t


def _media(role: str, d: Any, *, url_key: str = "url", width_key: str = "width", height_key: str = "height",
           id_key: Optional[str] = None) -> Optional[dict]:
    if isinstance(d, str):
        d = {"url": d}
    if not isinstance(d, dict) or not _s(d.get(url_key)):
        return None
    url = str(d[url_key]).strip()
    dur = _f(d.get("duration"))
    if dur is None and d.get("duration_ms") is not None:
        dur = (_f(d.get("duration_ms")) or 0) / 1000.0
    return {"role": role, "type": _type(d.get("type"), url), "url": url, "width": _i(d.get(width_key)),
            "height": _i(d.get(height_key)), "duration_s": dur,
            "media_key": media_key(url, d.get(id_key) if id_key else d.get("media_id"))}


def _media_set(role: str, d: Any) -> list[dict]:
    """A CMS media object: url (+ main_url full size, thumbnail_url, hls_url, optimized_url)."""
    out = []
    m = _media(role, d)
    if m:
        out.append(m)
    if isinstance(d, dict):
        if _s(d.get("main_url")) and d.get("main_url") != d.get("url"):
            mm = _media(f"{role}_full", {"url": d["main_url"], "type": d.get("type")}, width_key="w")
            if mm:
                mm["width"], mm["height"] = _i(d.get("main_width")), _i(d.get("main_height"))
                mm["duration_s"] = _f(d.get("duration"))
                out.append(mm)
        for k, r in (("thumbnail_url", f"{role}_thumbnail"), ("optimized_url", f"{role}_optimized"),
                     ("hls_url", f"{role}_hls")):
            if _s(d.get(k)) and d.get(k) != d.get("url"):
                out.append({"role": r, "type": "hls" if k == "hls_url" else _type(None, d[k]), "url": d[k],
                            "width": None, "height": None, "duration_s": None, "media_key": media_key(d[k])})
    return out


def _keys(media: list[dict], roles: tuple[str, ...] = ()) -> list[str]:
    out = []
    for m in media:
        if roles and not any(m["role"] == r or m["role"].startswith(r + "_") for r in roles):
            continue
        if m.get("media_key") and not is_input_url(m["url"]):
            out.append(f"media:{m['media_key']}")
    return list(dict.fromkeys(out))


def _base(kind: str, env: Any, natural: tuple, source_url: str) -> dict:
    return {"kind": kind, "id": make_id(kind, *natural), "source_url": source_url,
            "scraped_at": env.fetched_at.isoformat(), "schema_version": 1, "source": env.provenance()}


def creator_key(uid: Any) -> Optional[str]:
    return make_id("creator", uid) if _s(uid) else None


def _creator(d: Any, sel: Any) -> tuple[Optional[str], Optional[dict]]:
    if not isinstance(d, dict):
        return None, None
    if d.get("id_hash"):                                 # archive already pseudonymised by the spider
        return d["id_hash"], None
    uid = d.get("user_id") or d.get("id")
    prof = None
    if getattr(sel, "with_profiles", False):
        prof = {"user_id": _s(uid), "username": _s(d.get("username")),
                "avatar_url": _s(d.get("avatar_url") or d.get("avatarUrl"))}
    return creator_key(uid), prof


def _lang(env: Any, sel: Any) -> str:
    return env.params.get("lang") or getattr(sel, "lang", "en") or "en"


# ------------------------------------------------------------------ canvas templates
def parse_canvas_templates(env: Any, sel: Any) -> list[dict]:
    out = []
    for t in (env.body or {}).get("items") or []:
        tid = _s(t.get("id"))
        if not tid:
            continue
        e = _base("showcase_canvas_template", env, (tid,), f"{SITE}/canvas/templates/{tid}")
        e.update(template_id=tid, name=_s(t.get("name")), description=_s(t.get("description")),
                 thumbnail_url=_s(t.get("thumbnail_url")), created_at=_ts(t.get("created_at")),
                 app_url=f"{SITE}/canvas/templates/{tid}", graph_available=False)
        out.append(e)
    return out


# ------------------------------------------------------------------ editing room
def parse_videoshop_examples(env: Any, sel: Any) -> list[dict]:
    out = []
    lang = _lang(env, sel)
    for x in (env.body or {}).get("items") or []:
        slug = _s(x.get("id"))
        if not slug:
            continue
        media = [m for m in (
            _media("thumbnail", x.get("thumbnail_url")), _media("preview", x.get("preview_url")),
            _media("input", x.get("input")), _media("input_thumbnail", (x.get("input") or {}).get("thumbnail_url")),
            _media("final", x.get("final")), _media("final_thumbnail", (x.get("final") or {}).get("thumbnail_url")),
        ) if m]
        edits = [{"edit_id": _s(ed.get("id")), "tool": _s(ed.get("tool")), "label": _s(ed.get("label")),
                  "prompt": _s(ed.get("prompt")), "start_ms": _i(ed.get("start_ms")), "end_ms": _i(ed.get("end_ms")),
                  "layer": _i(ed.get("layer"))} for ed in x.get("edits") or [] if isinstance(ed, dict)]
        keys = _keys(media, ("final",))
        e = _base("showcase_editing_room_example", env, (slug, lang), f"{SITE}/editing-room/examples/{slug}")
        e.update(example_id=slug, title=_s(x.get("title")), lang=lang, media=media,
                 input_duration_ms=_i((x.get("input") or {}).get("duration_ms")),
                 final_duration_ms=_i((x.get("final") or {}).get("duration_ms")), edits=edits,
                 tools=sorted({ed["tool"] for ed in edits if ed["tool"]}),
                 generation_key=keys[0] if keys else None, media_keys=_keys(media))
        out.append(e)
    return out


EDIT_PARAM_KEYS = ("relight", "brush", "cameraMove", "angle")


def parse_videoshop_project_examples(env: Any, sel: Any) -> list[dict]:
    out = []
    for it in (env.body or {}).get("items") or []:
        p, tl = it.get("project") or {}, it.get("timeline") or {}
        pid = _s(p.get("id"))
        if not pid:
            continue
        page = f"{SITE}/editing-room/examples/{pid}"
        take = p.get("take") or {}
        edits = []
        for ed in tl.get("edits") or []:
            refs = [m for m in (_media("reference", r, id_key="id") for r in ed.get("references") or []) if m]
            edits.append({"edit_id": str(ed.get("id")), "number": _i(ed.get("number")), "tool": _s(ed.get("tool")),
                          "tool_mode": _s(ed.get("genjutsuWay")), "layer": _i(ed.get("layer")),
                          "start_ms": _i(ed.get("startMs")), "end_ms": _i(ed.get("endMs")), "hidden": ed.get("hidden"),
                          "resolution": _s(ed.get("resolution")), "prompt_enabled": ed.get("promptEnabled"),
                          "prompt": _s(ed.get("prompt")),
                          "params": {k: ed[k] for k in EDIT_PARAM_KEYS if ed.get(k) is not None},
                          "references": refs, "placed_version_id": _s(ed.get("placedVersionId"))})
        edit_tool = {e2["edit_id"]: e2 for e2 in edits}
        render_ids, children = [], []
        for v in tl.get("versions") or []:
            vid = _s(v.get("id"))
            if not vid:
                continue
            render_ids.append(vid)
            mw = v.get("madeWith") or {}
            m = v.get("media") or {}
            media = [x for x in (_media("output", m, id_key="id"),
                                 _media("output_thumbnail", m.get("thumbnail_url"))) if x]
            ed = edit_tool.get(str(v.get("editId"))) or {}
            r = _base("showcase_editing_room_render", env, (pid, vid), page)
            keys = _keys(media, ("output",))
            r.update(version_id=vid, project_id=pid, edit_id=_s(v.get("editId")), number=_i(v.get("number")),
                     job_set_id=_s(v.get("jobSetId")), batch_id=_s(v.get("batchId")), status=_s(v.get("status")),
                     resolution=_s(v.get("resolution")), tool=_s(mw.get("tool")) or ed.get("tool"),
                     prompt=_s(mw.get("prompt")), made_with=mw if isinstance(mw, dict) else {},
                     start_ms=_i((v.get("rangeMs") or {}).get("startMs")),
                     end_ms=_i((v.get("rangeMs") or {}).get("endMs")), media=media,
                     generation_key=keys[0] if keys else None, media_keys=keys)
            children.append(r)
        e = _base("showcase_editing_room_project", env, (pid,), page)
        e.update(project_id=pid, name=_s(p.get("name")), created_at=_ts(p.get("created_at")),
                 updated_at=_ts(p.get("updated_at")), take=_media("take", take, id_key="id"),
                 take_duration_ms=_i(take.get("duration_ms")),
                 scenes=[s for s in p.get("scenes") or [] if isinstance(s, dict)],
                 timeline_schema_version=_i(tl.get("schemaVersion")), edits=edits, render_ids=render_ids,
                 tools=sorted({x["tool"] for x in edits if x["tool"]}))
        out.append(e)
        out.extend(children)
    return out


# ------------------------------------------------------------------ property studio
PRESET_ROW_RE = re.compile(r"\[`(flash-tour|enhance|renovation|virtual-staging|floor-plan-3d)`,`([^`]+)`,"
                           r"\{id:`([^`]+)`[^}]*\},(\d+),(\d+),(\d+)\]")


def extract_property_rows(js: str) -> list[list]:
    """The JS preset table `[[format, path, {id: titleId}, inputs, width, height], ...]` (chunk with
    `realty-studio/app-presets`)."""
    return [[f, p, t, int(n), int(w), int(h)] for f, p, t, n, w, h in PRESET_ROW_RE.findall(js)]


def property_media(fmt: str, path: str, inputs: int) -> list[dict]:
    """Mirror of the JS mapper Qt(): v1 = web size, full-v1 = original; flash-tour has input-N + tour video."""
    c = f"{fmt}/{path}"
    v1, full = f"{STATIC}/realty-studio/app-presets/v1/{c}", f"{STATIC}/realty-studio/app-presets/full-v1/{c}"
    tour = fmt == "flash-tour"
    out = []
    for i in range(inputs):
        n = f"input-{i + 1}" if tour else "before"
        out.append({"role": "input", "type": "image", "url": f"{v1}/{n}.webp"})
        out.append({"role": "input_full", "type": "image", "url": f"{full}/{n}.webp"})
    out.append({"role": "poster", "type": "image", "url": f"{v1}/after.webp"})
    if tour:
        out.append({"role": "video", "type": "video", "url": f"{v1}/tour-preview.mp4"})
        out.append({"role": "output", "type": "video", "url": f"{full}/tour.mp4"})
    else:
        out.append({"role": "output", "type": "image", "url": f"{full}/after.webp"})
    for m in out:
        m.update(width=None, height=None, duration_s=None, media_key=None)
    return out


def parse_property_presets(env: Any, sel: Any) -> list[dict]:
    b = env.body or {}
    titles = b.get("titles") or {}
    lang = b.get("lang") or _lang(env, sel)
    out = []
    for idx, row in enumerate(b.get("rows") or []):
        fmt, path, tid, n, w, h = row
        media = property_media(fmt, path, int(n))
        e = _base("showcase_property_studio_example", env, (fmt, path, lang), f"{SITE}/property-studio")
        out_url = next(m["url"] for m in media if m["role"] == "output")
        e.update(preset_index=idx, format=fmt, app=PROPERTY_FORMAT_APP.get(fmt), path=path, title_id=tid,
                 title=(titles.get(tid) or None) if isinstance(titles.get(tid), str) else None, lang=lang,
                 input_count=int(n), width=int(w), height=int(h), media=media, chunk=b.get("chunk"),
                 generation_key="static:" + out_url.split("/realty-studio/", 1)[-1], media_keys=[])
        out.append(e)
    return out


# ------------------------------------------------------------------ video explore
def parse_explore_categories(env: Any, sel: Any) -> list[dict]:
    out = []
    for c in (env.body or {}).get("categories") or []:
        name = _s(c.get("category"))
        if not name:
            continue
        e = _base("showcase_explore_category", env, (name,), f"{SITE}/higgsfield-multiplier")
        e.update(category=name, trends=_i(c.get("trends")))
        out.append(e)
    return out


def _engagement(d: dict) -> dict:
    return {"likes": _i(d.get("likes_count")), "views": _i(d.get("views_count")),
            "comments": _i(d.get("comments_count")), "uses": _i(d.get("times_made"))}


def parse_explore_feed(env: Any, sel: Any) -> list[dict]:
    out = []
    p = env.params
    for it in (env.body or {}).get("items") or []:
        iid = _s(it.get("id"))
        if not iid:
            continue
        page = f"{SITE}/higgsfield-multiplier?trend={iid}"
        vids, pubs, children = [], [], []
        for v in it.get("variants") or []:
            vid = _s(v.get("id"))
            if not vid:
                continue
            vids.append(vid)
            media = _media_set("output", v.get("media"))
            inputs = [m for m in (_media("input", a) for a in v.get("input_assets") or []) if m]
            pub = v.get("publication") if isinstance(v.get("publication"), dict) else None
            if pub and _s(pub.get("id")):
                pubs.append(pub["id"])
            ck, prof = _creator(v.get("author"), sel)
            # the `original` variant is the source clip, not a generation: no dedup keys
            keys = [] if _s(v.get("type")) == "original" else _keys(media, ("output",))
            ve = _base("showcase_explore_variant", env, (iid, vid), page)
            ve.update(variant_id=vid, item_id=iid, variant_type=_s(v.get("type")), prompt=_s(v.get("prompt")),
                      params=v.get("params") if isinstance(v.get("params"), dict) else {},
                      priority=_i(v.get("priority")), media=media, inputs=inputs,
                      publication_id=_s(pub.get("id")) if pub else None,
                      publication_engagement=_engagement(pub) if pub else None,
                      creator_key=ck, creator_badge=_s((v.get("author") or {}).get("badge")) if v.get("author") else None,
                      creator=prof, generation_key=keys[0] if keys else None, media_keys=keys)
            if not prof:
                ve.pop("creator")
            children.append(ve)
        e = _base("showcase_explore_item", env, (iid,), page)
        e.update(item_id=iid, feed_source=_s(it.get("source")) or p.get("source") or "unknown",
                 sort=p.get("sort"), category_filter=p.get("category"), title=_s(it.get("title")),
                 description=_s(it.get("description")), job_set_type=_s(it.get("job_set_type")),
                 priority=_i(it.get("priority")), category=_s(it.get("category")), trend_id=_s(it.get("trend_id")),
                 engagement=_engagement(it), original_video=_media("original", it.get("original_video")),
                 variant_ids=vids, publication_ids=pubs)
        out.append(e)
        out.extend(children)                 # parent first: per-kind caps drop children of dropped parents
    return out


# ------------------------------------------------------------------ effect examples
def _clean_params(d: Any) -> dict:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        if isinstance(v, (dict, list)) and "url" in json.dumps(v):
            continue                                     # input media (URLs of uploads) are in `inputs`
        out[k] = v
    return out


def parse_effect_page(env: Any, sel: Any) -> list[dict]:
    b = env.body or {}
    slug = b.get("slug") or env.params.get("slug")
    loader = b.get("loader") or {}
    preset = loader.get("preset") or {}
    samples = loader.get("initialSamples") or {}
    page = f"{SITE}/effects/examples/{slug}"
    out = []
    for s in samples.get("items") or []:
        sid = _s(s.get("id"))
        if not sid:
            continue
        job = s.get("job") or {}
        o = s.get("output") or {}
        media = [m for m in (
            _media("output", {"url": o.get("source"), "type": o.get("type"), "width": o.get("width"),
                              "height": o.get("height")}),
            _media("output_raw", o.get("rawUrl")) if o.get("rawUrl") != o.get("source") else None,
            _media("output_poster", o.get("posterUrl")), _media("output_hls", o.get("hlsUrl")),
        ) if m]
        inputs = []
        for a in s.get("attachments") or []:
            im = a.get("inputMedia") or {}
            m = _media("input", {"url": a.get("source") or im.get("url"), "type": a.get("type"),
                                 "width": a.get("width"), "height": a.get("height")})
            if m:
                m["media_key"] = media_key(m["url"], im.get("id"))
                inputs.append(m)
        user = job.get("user") if isinstance(job.get("user"), dict) else None
        ck, prof = _creator(user, sel)
        jid = _s(job.get("id"))
        keys = _keys(media, ("output",))
        e = _base("showcase_effect_sample", env, (slug, sid), f"{page}/{sid}")
        e.update(sample_id=sid, preset_slug=slug, preset_id=_s(preset.get("id")), preset_kind=_s(preset.get("kind")),
                 preset_name=_s(s.get("presetName")) or _s(preset.get("name")),
                 catalog_ref=f"catalog_viral_preset:{preset['id']}" if preset.get("id") else None,
                 sample_preset_id=_s(s.get("presetId")), job_id=jid, job_set_id=_s(job.get("jobSetId")),
                 job_set_type=_s(job.get("jobSetType")) or _s(preset.get("job_set_type")),
                 status=_s(job.get("status")), prompt=_s(s.get("prompt")) or _prompt_of(job),
                 params=_clean_params(job.get("rawParams")), created_at=_ts(job.get("createdAt")),
                 published_at=_ts(s.get("publishedAt")), media=media, inputs=inputs, creator_key=ck,
                 creator=prof, samples_total=_i(samples.get("total")),
                 generation_key=f"job:{jid}" if jid else (keys[0] if keys else None), media_keys=keys)
        if not prof:
            e.pop("creator")
        out.append(e)
    return out


def _prompt_of(job: dict) -> Optional[str]:
    p = (job.get("params") or {}).get("prompt")
    if isinstance(p, dict):
        return _s(p.get("prompt"))
    return _s(p) or _s((job.get("rawParams") or {}).get("prompt"))


# ------------------------------------------------------------------ public API docs
H1_RE = re.compile(r"^# (.+)$", re.M)
ENDPOINT_ID_RE = re.compile(r"^\*\*Endpoint ID:\*\* `([^`]+)`", re.M)
MONEY_RE = re.compile(r"\\?\$\s?([0-9]+(?:\.[0-9]+)?)")


def _sections(text: str) -> list[tuple[str, str]]:
    marks = list(H1_RE.finditer(text))
    return [(m.group(1).strip(), text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)])
            for i, m in enumerate(marks)]


def _subsection(body: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*$", body, re.M)
    if not m:
        return ""
    nxt = re.search(r"^## ", body[m.end():], re.M)
    return body[m.end(): m.end() + nxt.start() if nxt else len(body)]


def _json_schema(body: str) -> dict:
    m = re.search(r"Complete JSON schema.*?```json[^\n]*\n(.*?)```", body, re.S)
    if not m:
        return {}
    raw = "\n".join(re.sub(r"^>\s?", "", ln) for ln in m.group(1).splitlines())
    raw = raw.rsplit("```", 1)[0]
    try:
        d = json.loads(raw.strip().rstrip(">").strip())
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _params(schema: dict) -> list[dict]:
    req = set(schema.get("required") or [])
    out = []
    for name, p in (schema.get("properties") or {}).items():
        if not isinstance(p, dict):
            continue
        t = p.get("type")
        if t is None and isinstance(p.get("enum"), list) and p["enum"]:
            t = type(p["enum"][0]).__name__.replace("str", "string").replace("int", "integer")
        out.append({"name": name, "type": t if isinstance(t, str) else (json.dumps(t) if t else None),
                    "required": name in req, "default": p.get("default"),
                    "enum": list(p.get("enum") or []), "minimum": _f(p.get("minimum")), "maximum": _f(p.get("maximum")),
                    "format": _s(p.get("format")), "title": _s(p.get("title")), "description": _s(p.get("description"))})
    return out


def _dec(x: str) -> Optional[Decimal]:
    try:
        return Decimal(x)
    except InvalidOperation:
        return None


def _prices(body: str) -> tuple[list[dict], list[str]]:
    prices, notes = [], []
    lines = body.splitlines()
    header: Optional[list[str]] = None
    usd_in_text = "USD" in body
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue
            if not any(MONEY_RE.search(c) for c in cells):
                header = cells
                continue
            label = cells[0]
            for j, c in enumerate(cells[1:], 1):
                m = MONEY_RE.search(c)
                if not m:
                    continue
                unit = header[j] if header and j < len(header) else None
                prices.append({"label": label.replace("`", ""), "amount": _dec(m.group(1)),
                               "currency": "USD" if (usd_in_text or (unit and "USD" in unit)) else None,
                               "unit": unit, "price_raw": c.replace("\\$", "$")})
        else:
            header = None if not s else header
            if MONEY_RE.search(s) and not s.startswith(("```", ">", "  ")):
                notes.append(re.sub(r"\s+", " ", s.replace("\\$", "$").replace("**", ""))[:500])
    return prices, notes


def parse_api_docs(env: Any, sel: Any) -> list[dict]:
    b = env.body or {}
    text = b.get("text") or ""
    openapi = b.get("openapi") if isinstance(b.get("openapi"), dict) else {}
    oa_paths = {p.strip("/"): v for p, v in (openapi.get("paths") or {}).items() if "{" not in p}
    out, seen = [], set()
    for title, body in _sections(text):
        m = ENDPOINT_ID_RE.search(body)
        if not m:
            continue
        eid = m.group(1).strip().strip("/")
        if eid in seen:
            continue
        seen.add(eid)
        src = re.search(r"^Source: (\S+)", body, re.M)
        fam = re.search(r"^\[← ([^\]]+)\]\(", body, re.M)
        play = re.search(r"\]\((https://console\.higgsfield\.ai/models/[^)\s]+)\)", body)
        summ = next((p.strip() for p in body.split("\n\n")[1:4]
                     if p.strip() and not p.strip().startswith(("Source:", "[", "**", "#"))), None)
        notes = [re.sub(r"^\*\s+", "", ln.strip()) for ln in _subsection(body, "Usage notes").splitlines()
                 if ln.strip().startswith("*")]
        schema = _json_schema(body)
        prices, pnotes = _prices(body)
        parts = eid.split("/")
        e = _base("showcase_api_model", env, (eid,), src.group(1) if src else f"https://docs.higgsfield.ai")
        e.update(endpoint_id=eid, vendor=parts[0], model=parts[1] if len(parts) > 1 else None,
                 variant="/".join(parts[2:]) or None, http_method="POST",
                 endpoint_url=f"https://api.higgsfield.ai/{eid}", title=title, family=fam.group(1) if fam else None,
                 doc_url=src.group(1) if src else None, playground_url=play.group(1) if play else None,
                 summary=summ, usage_notes=notes, parameters=_params(schema),
                 required_parameters=list(schema.get("required") or []), json_schema=schema, prices=prices,
                 price_notes=pnotes, in_openapi=eid in oa_paths)
        out.append(e)
    for eid, ops in oa_paths.items():                    # only in openapi.json (supplementary)
        post = (ops or {}).get("post")
        if eid in seen or not isinstance(post, dict) or eid.startswith("requests"):
            continue
        schema = (((post.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
        parts = eid.split("/")
        e = _base("showcase_api_model", env, (eid,), "https://docs.higgsfield.ai/docs/openapi.json")
        e.update(endpoint_id=eid, vendor=parts[0], model=parts[1] if len(parts) > 1 else None,
                 variant="/".join(parts[2:]) or None, http_method="POST",
                 endpoint_url=f"https://api.higgsfield.ai/{eid}", title=_s(post.get("summary")), family=None,
                 doc_url=None, playground_url=None, summary=_s(post.get("description")), usage_notes=[],
                 parameters=_params(schema), required_parameters=list(schema.get("required") or []),
                 json_schema=schema, prices=[], price_notes=[], in_openapi=True)
        out.append(e)
    return out


# ------------------------------------------------------------------ season (login only)
SEASON_META = ("id", "season_id", "name", "title", "starts_at", "start_at", "ends_at", "end_at")


def parse_season(env: Any, sel: Any) -> list[dict]:
    b = env.body
    e = _base("showcase_season", env, ("season",), f"{SITE}/")
    d = b if isinstance(b, dict) else {}
    e.update(active=bool(d), season_id=_s(d.get("id") or d.get("season_id")),
             name=_s(d.get("name") or d.get("title")), starts_at=_ts(d.get("starts_at") or d.get("start_at")),
             ends_at=_ts(d.get("ends_at") or d.get("end_at")), top_level_keys=sorted(d),
             personal_fields_dropped=sorted(k for k in d if k not in SEASON_META))
    return [e]


# ------------------------------------------------------------------ CMS media lists
def _cms(kind: str, env: Any, sel: Any, x: dict, page: str, *, title_key: str = "name",
         media: list[dict], used: tuple[str, ...], extra_fields: Optional[dict] = None,
         natural: tuple = ()) -> Optional[dict]:
    iid = _s(x.get("id"))
    if not iid:
        return None
    lang = _lang(env, sel)
    keys = _keys(media)
    e = _base(kind, env, natural or (iid,), page)
    e.update(item_id=iid, title=_s(x.get(title_key)), description=_s(x.get("description")),
             category=_s(x.get("category")), priority=_i(x.get("priority")), lang=lang, media=media,
             extra=_no_placeholders({k: v for k, v in x.items()
                                     if k not in used and k not in ("id", title_key, "description", "category",
                                                                    "priority")}),
             generation_key=keys[0] if keys else None, media_keys=keys)
    e.update(extra_fields or {})
    return e


def _no_placeholders(v: Any) -> Any:
    """Drop base64 blur placeholders (data: URIs, tens of KB each)."""
    if isinstance(v, dict):
        return {k: _no_placeholders(x) for k, x in v.items()
                if not (k == "placeholder" or (isinstance(x, str) and x.startswith("data:")))}
    if isinstance(v, list):
        return [_no_placeholders(x) for x in v]
    return v


def _items(body: Any) -> list[dict]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    return [x for x in (body or {}).get("items") or [] if isinstance(x, dict)]


def parse_cinema_controls(env: Any, sel: Any) -> list[dict]:
    out = []
    for group, rows in (env.body or {}).items():
        if not isinstance(rows, list):
            continue
        for x in rows:
            if not isinstance(x, dict):
                continue
            media = _media_set("media", x.get("media"))
            if _s(x.get("url")) and not any(m["url"] == x["url"] for m in media):
                media += _media_set("image", x.get("url"))
            e = _cms("showcase_cinema_control", env, sel, x, f"{SITE}/cinema-studio", media=media,
                     used=("media", "url", "tag", "is_auto", "segments"), natural=(group, x.get("id")),
                     extra_fields={"group": group, "tag": _s(x.get("tag")), "is_auto": x.get("is_auto"),
                                   "segments": [s for s in x.get("segments") or [] if isinstance(s, dict)]})
            if e:
                out.append(e)
    return out


def parse_faceless(env: Any, sel: Any) -> list[dict]:
    out = []
    for x in _items(env.body):
        media = [m for m in (_media("video", x.get("video_url")), _media("thumbnail", x.get("thumbnail_url")),
                             _media("icon", x.get("icon_url"))) if m]
        e = _cms("showcase_faceless_showcase", env, sel, x, f"{SITE}/youtube-faceless", title_key="title",
                 media=media, used=("video_url", "thumbnail_url", "icon_url"))
        if e:
            out.append(e)
    return out


def parse_intone(env: Any, sel: Any) -> list[dict]:
    out = []
    for x in _items(env.body):
        media = _media_set("video", x.get("video")) + _media_set("image", x.get("image"))
        rec = x.get("recreate") if isinstance(x.get("recreate"), dict) else {}
        for k, v in rec.items():
            if isinstance(v, dict) and v.get("url"):
                media += _media_set(f"recreate_{k}", v)
        e = _cms("showcase_intone_example", env, sel, x, f"{SITE}/intone", title_key="title", media=media,
                 used=("video", "image"))
        if e:
            out.append(e)
    return out


def parse_seedance(env: Any, sel: Any) -> list[dict]:
    out = []
    for x in _items(env.body):
        media = _media_set("preview", x.get("preview_media")) + _media_set("preview_image", x.get("preview_image"))
        e = _cms("showcase_seedance_preset", env, sel, x, f"{SITE}/seedance-2-0", media=media,
                 used=("preview_media", "preview_image", "duration"),
                 extra_fields={"duration_s": _f(x.get("duration"))})
        if e:
            out.append(e)
    return out


def parse_motion_control(env: Any, sel: Any) -> list[dict]:
    out = []
    for x in _items(env.body):
        media = _media_set("preview", x.get("preview_media")) + _media_set("source", x.get("source_media"))
        e = _cms("showcase_motion_control_preset", env, sel, x, f"{SITE}/kling-motion-control", media=media,
                 used=("preview_media", "source_media"))
        if e:
            out.append(e)
    return out


PARSERS = {
    "showcase_canvas_templates": parse_canvas_templates,
    "showcase_videoshop_examples": parse_videoshop_examples,
    "showcase_videoshop_project_examples": parse_videoshop_project_examples,
    "showcase_property_studio_presets": parse_property_presets,
    "showcase_explore_categories": parse_explore_categories,
    "showcase_explore_feed": parse_explore_feed,
    "showcase_effect_page": parse_effect_page,
    "showcase_api_docs": parse_api_docs,
    "showcase_season": parse_season,
    "showcase_cinema_controls": parse_cinema_controls,
    "showcase_faceless_showcases": parse_faceless,
    "showcase_intone_explore": parse_intone,
    "showcase_seedance_presets": parse_seedance,
    "showcase_motion_control_presets": parse_motion_control,
}


def parse_envelope(env: Any, sel: Any) -> list[dict]:
    fn = PARSERS.get(env.endpoint)
    if fn is None or env.status != 200:
        return []
    if env.endpoint != "showcase_season" and not isinstance(env.body, (dict, list)):
        return []
    return fn(env, sel)


def keep(entity: dict, sel: Any) -> bool:
    return True


# ------------------------------------------------------------------ discovery helpers (used by the spider)
SITEMAP_LOC_RE = re.compile(r"<loc>\s*https://higgsfield\.ai/effects/examples/([A-Za-z0-9_.-]+)\s*</loc>")


def effect_slugs(xml: str) -> list[str]:
    return list(dict.fromkeys(SITEMAP_LOC_RE.findall(xml)))


def effect_page_url(slug: str) -> str:
    return f"{SITE}/effects/examples/{quote(slug)}"
