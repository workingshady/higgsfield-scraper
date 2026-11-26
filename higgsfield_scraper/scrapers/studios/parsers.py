"""Pure parsers: Envelope (raw/ archive) -> studios entity dicts. No network, no Scrapy.

Every source is a JSON API. Archives are redacted by the framework (`personal_data=True`) plus `author.name`, which
the spider blanks before archiving (`redact_author_names`), unless --with-profiles.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

from ...schemas.common import make_id
from .endpoints import INPUT_HOSTS, SITE, SKILLS, STUDIO_OF_MODEL

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
EXT_TYPE = {"mp4": "video", "webm": "video", "mov": "video", "m3u8": "hls", "webp": "image", "jpg": "image",
            "jpeg": "image", "png": "image", "gif": "image", "svg": "image", "mp3": "audio", "wav": "audio",
            "zip": "file", "html": "file"}
REDACTED = ("[redacted]", "<redacted>")
# params keys holding INPUT media (uploads, references, masks, products …) — never output keys
INPUT_KEY_RE = re.compile(r"media|image|video|input|reference|mask|combined|element|avatar|product|frame|audio",
                          re.I)
# params keys lifted to their own columns (the rest goes to `settings`)
LIFTED = ("prompt", "enhanced_prompt", "width", "height", "aspect_ratio", "resolution", "duration")


# ------------------------------------------------------------------ helpers
def _s(v: Any) -> Optional[str]:
    if v is None or isinstance(v, (dict, list)):
        return None
    v = str(v).strip()
    return v or None


def _i(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _b(v: Any) -> Optional[bool]:
    return v if isinstance(v, bool) else None


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
    if t in ("static", "image", "media_input"):
        return "image" if t != "media_input" or not url else _ext_type(url) or "image"
    if t in ("video", "audio", "hls", "file"):
        return t
    return _ext_type(url) or t


def _ext_type(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    ext = str(url).split("?")[0].rsplit("/", 1)[-1].rsplit(".", 1)
    return EXT_TYPE.get(ext[-1].lower()) if len(ext) == 2 else None


def _m(role: str, url: Any, *, type_: Any = None, width: Any = None, height: Any = None, duration: Any = None,
       key: Any = None) -> Optional[dict]:
    u = _s(url)
    if not u or u in REDACTED or u.startswith("data:"):
        return None
    return {"role": role, "type": _type(type_, u), "url": u, "width": _i(width), "height": _i(height),
            "duration_s": _f(duration), "media_key": media_key(u, key)}


def _media_obj(role: str, d: Any) -> list[dict]:
    """A CMS / SSR media object: url (+ main_url, compressed_url / compressed_video.url, thumbnail_url)."""
    if isinstance(d, str):
        d = {"url": d}
    if not isinstance(d, dict):
        return []
    out = []
    dur = d.get("duration_seconds", d.get("duration"))
    m = _m(role, d.get("url") or d.get("src"), type_=d.get("type"), width=d.get("width"), height=d.get("height"),
           duration=dur, key=d.get("media_id") or d.get("id"))
    if m:
        out.append(m)
    extras = (("main_url", f"{role}_full"), ("compressed_url", f"{role}_compressed"),
              ("thumbnail_url", f"{role}_thumbnail"))
    for k, r in extras:
        if _s(d.get(k)) and d.get(k) != d.get("url"):
            mm = _m(r, d[k], type_="image" if k == "thumbnail_url" else d.get("type"))
            if mm:
                if k == "main_url":
                    mm["width"], mm["height"] = _i(d.get("main_width")), _i(d.get("main_height"))
                out.append(mm)
    cv = d.get("compressed_video")
    if isinstance(cv, dict) and _s(cv.get("url")) and cv.get("url") != d.get("url"):
        mm = _m(f"{role}_compressed", cv["url"], type_="video", width=cv.get("width"), height=cv.get("height"))
        if mm:
            out.append(mm)
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


def author_key(uid: Any) -> Optional[str]:
    """Same hash as showcase `creator_key` (make_id('creator', user id)), so authors join across scrapers."""
    return make_id("creator", uid) if _s(uid) and str(uid) not in REDACTED else None


def _author(uid: Any, prof: Any, sel: Any, name_key: str = "name") -> tuple[Optional[str], Optional[dict]]:
    prof = prof if isinstance(prof, dict) else {}
    uid = _s(uid) or _s(prof.get("user_id")) or _s(prof.get("id"))
    key = author_key(uid)                                # also for e.g. "content_user_id" (Higgsfield content)
    out = None
    if getattr(sel, "with_profiles", False) and (uid or prof):
        name = _s(prof.get(name_key)) or _s(prof.get("username")) or _s(prof.get("name"))
        out = {"user_id": uid, "name": None if name in REDACTED else name,
               "avatar_url": None if _s(prof.get("avatar_url")) in REDACTED else _s(prof.get("avatar_url"))}
    return key, out


def _lang(env: Any, sel: Any) -> str:
    return env.params.get("lang") or getattr(sel, "lang", "en") or "en"


def _rank(env: Any, i: int) -> int:
    """0-based position in the listing: `offset` (offset paging) or the `rank_base` label (cursor paging)."""
    return (_i(env.params.get("offset")) or _i(env.params.get("rank_base")) or 0) + i


# ------------------------------------------------------------------ apps marketplace
def parse_app_categories(env: Any, sel: Any) -> list[dict]:
    out = []
    for c in (env.body or {}).get("items") or []:
        slug = _s(c.get("slug"))
        if not slug:
            continue
        e = _base("studios_app_category", env, (slug,), f"{SITE}/marketplace/apps?category={quote(slug)}")
        e.update(slug=slug, label=_s(c.get("label")), description=_s(c.get("description")),
                 position=_i(c.get("position")), app_types=[str(x) for x in c.get("app_types") or []])
        out.append(e)
    return out


def parse_apps(env: Any, sel: Any) -> list[dict]:
    out = []
    for i, a in enumerate((env.body or {}).get("items") or []):
        lid = _s(a.get("id"))
        if not lid:
            continue
        e = _base("studios_app", env, (lid,), f"{SITE}/marketplace/apps/{lid}")
        key, prof = _author(a.get("user_id"), a.get("author"), sel)
        media = [m for m in (_m("logo", a.get("logo_url")), _m("cover", a.get("cover_url")),
                             _m("cover_video", a.get("cover_video_url"), type_="video"),
                             _m("marketplace_cover", a.get("marketplace_cover_url"))) if m]
        e.update(listing_id=lid, app_id=_s(a.get("app_id")), name=_s(a.get("name")),
                 description=_s(a.get("description")), category=_s(a.get("category") or a.get("category_id")),
                 app_type=_s(a.get("type")), app_url=_s(a.get("app_url")), preview_url=_s(a.get("preview_url")),
                 media=media, author_key=key, author=prof, is_builtin=None,
                 engagement={"views": _i(a.get("views_count")), "likes": _i(a.get("likes_count")),
                             "dislikes": _i(a.get("dislikes_count")), "remixes": _i(a.get("remixes_count")),
                             "credits_usage": _f(a.get("credits_usage"))},
                 is_featured=_b(a.get("is_featured")), is_higgsfield=_b(a.get("is_higgsfield")),
                 is_pinned=_b(a.get("is_pinned")), remix_allowed=_b(a.get("remix_allowed")),
                 main_page_position=_i(a.get("main_page_position")), published_at=_ts(a.get("published_at")),
                 sort=env.params.get("sort"), rank=_rank(env, i))
        out.append(e)
    return out


# ------------------------------------------------------------------ games / skills / employees
def parse_games(env: Any, sel: Any) -> list[dict]:
    out = []
    for i, g in enumerate((env.body or {}).get("items") or []):
        lid = _s(g.get("id"))
        if not lid:
            continue
        e = _base("studios_game", env, (lid,), f"{SITE}/marketplace/games/{lid}")
        key, prof = _author(g.get("author_user_id"), g.get("author"), sel)
        media = [m for m in (_m("logo", g.get("logo_url")), _m("cover", g.get("cover_url"))) if m]
        e.update(listing_id=lid, game_id=_s(g.get("game_id")), name=_s(g.get("name")), slug=_s(g.get("slug")),
                 description=_s(g.get("description")), category=_s(g.get("category_id")),
                 game_url=_s(g.get("game_url")), source_zip_url=_s(g.get("source_url")),
                 remixed_from=_s(g.get("remixed_from_community_game_id")), media=media,
                 plays=_i(g.get("plays_count")), unique_players=_i(g.get("unique_players_count")),
                 remixes=_i(g.get("remixes_count")), created_at=_ts(g.get("created_at")),
                 updated_at=_ts(g.get("updated_at")), author_key=key, author=prof, is_builtin=None,
                 rank=_rank(env, i))
        out.append(e)
    return out


def parse_skills(env: Any, sel: Any) -> list[dict]:
    out = []
    for i, s in enumerate((env.body or {}).get("items") or []):
        sid = _s(s.get("id"))
        if not sid:
            continue
        e = _base("studios_skill", env, (sid,), f"{SITE}/marketplace/skills/{sid}")
        key, prof = _author(s.get("author_user_id"), s.get("author"), sel)
        content = _s(s.get("content_url"))
        e.update(skill_id=sid, name=_s(s.get("name")), display_name=_s(s.get("display_name")),
                 canonical_slug=_s(s.get("canonical_slug")), description=_s(s.get("description")),
                 short_description=_s(s.get("short_description")), sub_title=_s(s.get("sub_title")),
                 example_prompt=_s(s.get("example_prompt")), category=_s(s.get("category_id")),
                 color=_s(s.get("color")),
                 media=[m for u in s.get("preview_urls") or [] if (m := _m("preview", u))],
                 installs=_i(s.get("installs_count")), unique_users=_i(s.get("unique_users_count")),
                 usage=_i(s.get("usage_count")),
                 content_url=(SKILLS + content) if content and content.startswith("/") else content,
                 reference_paths=[str(x) for x in s.get("reference_paths") or []],
                 created_at=_ts(s.get("created_at")), updated_at=_ts(s.get("updated_at")),
                 author_key=key, author=prof, is_builtin=_b(s.get("is_builtin")),
                 rank=_rank(env, i))
        out.append(e)
    return out


def _example_media(ex: Any) -> list[dict]:
    out = []
    for x in (ex or {}).get("examples") or [] if isinstance(ex, dict) else []:
        if not isinstance(x, dict):
            continue
        m = _m("example", x.get("src") or x.get("url"), key=x.get("id"))
        if m:
            out.append(m)
    return out


def parse_employees(env: Any, sel: Any) -> list[dict]:
    out = []
    for i, a in enumerate((env.body or {}).get("items") or []):
        aid = _s(a.get("id"))
        if not aid:
            continue
        slug = _s(a.get("canonical_slug"))
        url = f"{SITE}/marketplace/employees/{slug or aid}"
        e = _base("studios_employee", env, (aid,), url)
        key, prof = _author(a.get("author_user_id"), a.get("author"), sel)
        media = [m for m in [_m("avatar", a.get("avatar_url"))] if m]
        media += [m for u in a.get("preview_urls") or [] if (m := _m("preview", u))]
        media += _example_media(a.get("examples_section"))
        e.update(employee_id=aid, name=_s(a.get("name")), display_name=_s(a.get("display_name")),
                 canonical_slug=slug, sub_title=_s(a.get("sub_title")), description=_s(a.get("description")),
                 public_md=_s(a.get("public_md")), example_prompt=_s(a.get("example_prompt")),
                 category=_s(a.get("category_id")), visibility=_s(a.get("visibility")), color=_s(a.get("color")),
                 skill_pool_mode=_s(a.get("skill_pool_mode")), connector_pool_mode=_s(a.get("connector_pool_mode")),
                 orchestrated_skills=[str(x.get("id") if isinstance(x, dict) else x)
                                      for x in a.get("orchestrated_skills") or []],
                 connectors=[str(x.get("id") if isinstance(x, dict) else x) for x in a.get("connectors") or []],
                 features=[{"icon": _s(f.get("icon")), "title": _s(f.get("title")),
                            "description": _s(f.get("description"))}
                           for f in a.get("features") or [] if isinstance(f, dict)],
                 media=media, installs=_i(a.get("installs_count")), unique_users=_i(a.get("unique_users_count")),
                 usage=_i(a.get("usage_count")), created_at=_ts(a.get("created_at")),
                 updated_at=_ts(a.get("updated_at")), author_key=key if a.get("author") else None,
                 author=prof if a.get("author") else None, is_builtin=_b(a.get("is_builtin")), rank=_rank(env, i))
        out.append(e)
    return out


# ------------------------------------------------------------------ CMS
def parse_playable_presets(env: Any, sel: Any) -> list[dict]:
    out = []
    lang = _lang(env, sel)
    for p in (env.body or {}).get("items") or []:
        pid = _s(p.get("id"))
        if not pid:
            continue
        e = _base("studios_playable_preset", env, (pid, lang), f"{SITE}/playable-ads")
        rc = p.get("recreate") if isinstance(p.get("recreate"), dict) else {}
        media: list[dict] = []
        for k in ("poster", "vertical_poster", "video", "widescreen_video", "input_video", "game",
                  "widescreen_game"):
            media += _media_obj(k, p.get(k))
        for j, c in enumerate(p.get("covers") or []):
            media += _media_obj(f"cover{j}", c)
        e.update(preset_id=pid, title=_s(p.get("title")), category=_s(p.get("category")),
                 priority=_i(p.get("priority")), recreate_prompt=_s(rc.get("prompt")),
                 recreate_game_type=_s(rc.get("game_type")), recreate_dimension=_s(rc.get("dimension")),
                 recreate_mode=_s(rc.get("mode")), media=media, lang=lang)
        out.append(e)
    return out


def parse_influencer_config(env: Any, sel: Any) -> list[dict]:
    out = []
    lang = _lang(env, sel)
    for c in (env.body or {}).get("categories") or []:
        ck = _s(c.get("key"))
        for sc in c.get("subcategories") or []:
            sk = _s(sc.get("key"))
            for pos, o in enumerate(sc.get("options") or []):
                ok = _s(o.get("key"))
                if not (ck and sk and ok):
                    continue
                e = _base("studios_influencer_option", env, (ck, sk, ok, lang), f"{SITE}/ai-influencer")
                e.update(category_key=ck, category_label=_s(c.get("label")),
                         category_is_advanced=_b(c.get("is_advanced")), subcategory_key=sk,
                         subcategory_label=_s(sc.get("label")), max_selections=_i(sc.get("max_selections")),
                         required_selections=_i(sc.get("required_selections")),
                         default_option=_s(sc.get("default_option")), option_key=ok,
                         option_label=_s(o.get("label")), option_type=_s(o.get("type")), position=pos,
                         media=_media_obj("option", o.get("media")), lang=lang)
                out.append(e)
    return out


# ------------------------------------------------------------------ studio galleries
def _inputs(params: dict) -> list[dict]:
    out: list[dict] = []

    def walk(v: Any, role: str) -> None:
        if isinstance(v, dict):
            data = v.get("data") if isinstance(v.get("data"), dict) else None
            if data and _s(data.get("url")):
                m = _m(_s(v.get("role")) or role, data.get("url"), type_=data.get("type"), key=data.get("id"))
                if m:
                    out.append(m)
                return
            if _s(v.get("url")):
                m = _m(role, v.get("url"), type_=v.get("type"), width=v.get("width"), height=v.get("height"),
                       key=v.get("id"))
                if m:
                    out.append(m)
                return
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, role)

    for k, v in params.items():
        if INPUT_KEY_RE.search(k) and isinstance(v, (dict, list)):
            walk(v, k)
    seen, uniq = set(), []
    for m in out:
        if m["url"] not in seen:
            seen.add(m["url"])
            uniq.append(m)
    return uniq


def _preset(params: dict) -> Optional[str]:
    p = params.get("preset")
    if isinstance(p, dict):
        v = _s(p.get("id")) or _s(p.get("slug")) or _s(p.get("name"))
        if v:
            return v
    for k in ("preset_id", "preset_slug", "template_id", "motion_id", "style_id"):
        if _s(params.get(k)):
            return _s(params[k])
    st = params.get("style")
    if isinstance(st, dict) and (_s(st.get("name")) or _s(st.get("id"))):
        return _s(st.get("name")) or _s(st.get("id"))
    mode = "/".join(x for x in (_s(params.get("mode")), _s(params.get("specific_mode"))) if x)
    return mode or _s(params.get("genre"))


def _results(item: dict) -> list[dict]:
    out: list[dict] = []
    res = item.get("results") if isinstance(item.get("results"), dict) else {}
    for k in ("raw", "min", "hls", "h264"):
        r = res.get(k)
        if isinstance(r, dict):
            m = _m(f"result_{k}", r.get("url"), type_="hls" if k == "hls" else r.get("type"))
            if m:
                out.append(m)
            t = _m(f"result_{k}_thumbnail", r.get("thumbnail_url"), type_="image")
            if t:
                out.append(t)
    single = item.get("result")
    if isinstance(single, dict) and _s(single.get("url")):
        m = _m("result", single.get("url"), type_=single.get("type"))
        if m:
            out.append(m)
    seen, uniq = set(), []
    for m in out:
        if (m["role"].endswith("thumbnail"), m["url"]) not in seen:
            seen.add((m["role"].endswith("thumbnail"), m["url"]))
            uniq.append(m)
    return uniq


def parse_gallery(env: Any, sel: Any) -> list[dict]:
    out = []
    feed = env.params.get("feed") or ("approved" if "/approved" in env.url else "trending")
    for i, it in enumerate((env.body or {}).get("items") or []):
        jid = _s(it.get("id"))
        jst = _s(it.get("job_set_type"))
        if not jid or not jst:
            continue
        studio = env.params.get("studio") or STUDIO_OF_MODEL.get(jst) or "other"
        pub = it.get("publication") if isinstance(it.get("publication"), dict) else {}
        pid = _s(pub.get("id"))
        e = _base("studios_gallery_item", env, (jid,), env.url)        # feed API URL (no stable item page)
        params = it.get("params") if isinstance(it.get("params"), dict) else {}
        media = _results(it)
        inputs = _inputs(params)
        input_keys = {k for k, v in params.items() if INPUT_KEY_RE.search(k) and isinstance(v, (dict, list))}
        settings = {k: v for k, v in params.items() if k not in LIFTED and k not in input_keys}
        key, prof = _author(it.get("user_id"), it.get("profile"), sel, name_key="username")
        if key is None and isinstance(it.get("profile"), dict):
            key = author_key(it["profile"].get("username"))
        dur = params.get("duration")
        e.update(generation_key=f"job:{jid.lower()}", media_keys=_keys(media, ("result",)), job_id=jid,
                 job_set_id=_s(it.get("job_set_id")), job_set_type=jst, studio=studio, feed=feed,
                 publication_id=pid, approved=_b(pub.get("approved")), pinned_at=_ts(pub.get("pinned_at")),
                 status=_s(it.get("status")), prompt=_s(params.get("prompt")),
                 enhanced_prompt=_s(params.get("enhanced_prompt")), preset=_preset(params),
                 width=_i(params.get("width")), height=_i(params.get("height")),
                 aspect_ratio=_s(params.get("aspect_ratio")), resolution=_s(params.get("resolution")),
                 duration_s=_f(dur), settings=settings, inputs=inputs, media=media,
                 engagement={"views": _i(pub.get("views_count")), "likes": _i(pub.get("likes_count"))},
                 published_at=_ts(it.get("published_at")), created_at=_ts(it.get("created_at")),
                 author_key=key, author=prof, rank=_rank(env, i))
        out.append(e)
    return out


def parse_comments(env: Any, sel: Any) -> list[dict]:
    out = []
    pid = env.params.get("publication_id")
    for c in (env.body or {}).get("items") or []:
        cid = _s(c.get("id"))
        if not cid:
            continue
        p = _s(c.get("publication_id")) or pid
        e = _base("studios_comment", env, (cid,), env.url)
        key, prof = _author(c.get("user_id"), c.get("author"), sel, name_key="username")
        e.update(comment_id=cid, publication_id=p, entity_type=_s(c.get("entity_type")) or "generation_publication",
                 parent_id=_s(c.get("parent_id")), content=_s(c.get("content")), likes=_i(c.get("like_count")),
                 dislikes=_i(c.get("dislike_count")), replies=_i(c.get("reply_count")),
                 created_at=_ts(c.get("created_at")), updated_at=_ts(c.get("updated_at")),
                 author_key=key, author=prof)
        out.append(e)
    return out


PARSERS = {
    "studios_app_categories": parse_app_categories,
    "studios_apps": parse_apps,
    "studios_games": parse_games,
    "studios_skills": parse_skills,
    "studios_employees": parse_employees,
    "studios_playable_presets": parse_playable_presets,
    "studios_influencer_config": parse_influencer_config,
    "studios_gallery": parse_gallery,
    "studios_comments": parse_comments,
}


def parse_envelope(env: Any, sel: Any) -> list[dict]:
    fn = PARSERS.get(env.endpoint)
    if fn is None or env.status != 200 or not isinstance(env.body, dict):
        return []
    return fn(env, sel)


def keep(entity: dict, sel: Any) -> bool:
    return True


# ------------------------------------------------------------------ archive privacy (used by the spider)
AUTHOR_ENDPOINTS = frozenset({"studios_apps", "studios_games", "studios_skills", "studios_employees"})


def redact_author_names(body: Any) -> Any:
    """`author.name` (apps/games/skills/employees) is a username but not in core PERSONAL_KEYS: blank it before the
    body is archived (the core redaction then removes avatars/usernames). Ids stay (opaque, needed for author_key)."""
    if not isinstance(body, dict):
        return body
    for it in body.get("items") or []:
        a = it.get("author") if isinstance(it, dict) else None
        if isinstance(a, dict) and a.get("name") not in (None, ""):
            a["name"] = "[redacted]"
    return body

