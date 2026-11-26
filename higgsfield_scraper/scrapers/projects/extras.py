"""Pure parsers of the opt-in extras (2026-11-26): the trending project ranking (`--what trending`), contest
participation counters + config (`--what contest-participation`) and a user's published works + stats
(`--with-user-works`). No network, no Scrapy.

Context that is not in a response body (the user's pseudonymous key) travels in the envelope params as request
labels, so `normalize` re-parses identically. Docs: docs/scrapers/projects.md "Trending, contest participation,
user works".
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Optional

from ...core.dataset import make_id
from ...core.privacy import creator_uid_key
from .nested import _base, _inputs, _label, _media_type, _variants
from .options import Selection
from .parsers import _float, _int, _list, _listing_name, _rest, _str, author_key, iso, parse_publication_list

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
INPUT_HOSTS = ("d2ol7oe51mr4n9.cloudfront.net",)            # uploads / reference media: never generation keys
USER_ID_PATH_RE = re.compile(r"/user/[^/?#]+/")


# ------------------------------------------------------------------ trending ranking
def parse_trending(env, sel: Selection) -> list[dict]:
    """`/project-publications/trending` -> {items, total, next_cursor, feed}. Items are publication-shaped (+
    feed_lane, feed_position): emitted as publications + listing entries (listing 'trending…') like every listing,
    plus one `projects_trending_row` per rank with the ranking's total and snapshot."""
    body = env.body if isinstance(env.body, dict) else {}
    out = parse_publication_list(env, sel)
    p = env.params or {}
    listing = _listing_name(env)
    feed = body.get("feed") if isinstance(body.get("feed"), dict) else {}
    snapshot = _str(feed.get("snapshot_id"))
    cursor = p.get("cursor")
    offset = _int(cursor) if cursor else 0
    for i, item in enumerate(_list(body.get("items"))):
        if not isinstance(item, dict) or not item.get("publication_id"):
            continue
        pid = str(item["publication_id"])
        fpos = _int(item.get("feed_position"))
        out.append({
            **_base(env, "projects_trending_row"),
            "row_id": make_id(snapshot or listing, pid),
            "publication_id": pid,
            "position": fpos - 1 if fpos is not None else (None if offset is None else offset + i),
            "feed_position": fpos,
            "feed_lane": _str(item.get("feed_lane")),
            "listing": listing,
            "sort": _str(p.get("sort")),
            "filter": _str(p.get("filter")),
            "with_contest": str(p.get("with_contest", "")).lower() == "true",
            "total_reported": _int(body.get("total")),
            "snapshot_id": snapshot,
            "feed_source": _str(feed.get("source")),
            "feed_version": _str(feed.get("version")),
            "page_cursor": _str(cursor),
            "index_in_page": i,
        })
    return out


# ------------------------------------------------------------------ contest participation
COUNTER_KEYS = ("total", "public_total", "private_total")
CONFIG_KEYS = ("display_name", "stage", "starts_at", "submissions_close_at", "create_in_public_closes_at",
               "submissions_visible_at", "voting_opens_at", "voting_closes_at", "rules_version",
               "allows_multiple_projects", "max_projects", "max_team_size", "max_public_submissions", "votes_per_user",
               "watch_required", "timeline", "limits", "countries", "contest_key")
TIMELINE_KEYS = ("final_submissions_open_at", "judging_closes_at", "results_announced_at")
LIMIT_KEYS = ("final_min_seconds", "final_max_seconds", "min_generations", "live_min_seconds")


def parse_participation_counters(env, sel: Selection) -> list[dict]:
    body = env.body if isinstance(env.body, dict) else {}
    key = _label(env, "contest_key")
    if not key or not any(k in body for k in COUNTER_KEYS):
        return []
    return [{**_base(env, "projects_participation_counters"), "contest_key": key,
             **{k: _int(body.get(k)) for k in COUNTER_KEYS}, "extra": _rest(body, COUNTER_KEYS)}]


def parse_participation_config(env, sel: Selection) -> list[dict]:
    body = env.body if isinstance(env.body, dict) else {}
    key = _str(body.get("contest_key")) or _label(env, "contest_key")
    if not key or "stage" not in body and "display_name" not in body:
        return []
    tl = body.get("timeline") if isinstance(body.get("timeline"), dict) else {}
    lim = body.get("limits") if isinstance(body.get("limits"), dict) else {}
    extra = _rest(body, CONFIG_KEYS)
    if _rest(tl, TIMELINE_KEYS):
        extra["timeline"] = _rest(tl, TIMELINE_KEYS)
    if _rest(lim, LIMIT_KEYS):
        extra["limits"] = _rest(lim, LIMIT_KEYS)
    return [{
        **_base(env, "projects_participation_config"),
        "contest_key": key,
        "display_name": body.get("display_name"),
        "stage": _str(body.get("stage")),
        **{k: iso(body.get(k)) for k in ("starts_at", "submissions_close_at", "create_in_public_closes_at",
                                         "submissions_visible_at", "voting_opens_at", "voting_closes_at")},
        "rules_version": _int(body.get("rules_version")),
        "allows_multiple_projects": body.get("allows_multiple_projects"),
        **{k: _int(body.get(k)) for k in ("max_projects", "max_team_size", "max_public_submissions",
                                          "votes_per_user")},
        "watch_required": body.get("watch_required"),
        **{k: iso(tl.get(k)) for k in TIMELINE_KEYS},
        "final_min_seconds": _float(lim.get("final_min_seconds")),
        "final_max_seconds": _float(lim.get("final_max_seconds")),
        "min_generations": _int(lim.get("min_generations")),
        "live_min_seconds": _float(lim.get("live_min_seconds")),
        "countries": body.get("countries") if isinstance(body.get("countries"), list) else None,
        "extra": extra,
    }]


# ------------------------------------------------------------------ user works + stats (--with-user-works)
def _user(env, sel: Selection) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(creator_uid_key, creator_key, user id) of the profile from the request labels / URL. The Clerk id is in the
    request URL (/user/{user_id}/…); the dataset only gets it with --with-profiles."""
    m = re.search(r"/user/([^/?#]+)/", env.url or "")
    uid = m.group(1) if m and not m.group(1).startswith("key:") else None
    key = _label(env, "creator_uid_key") or (creator_uid_key(uid) if uid else None)
    ckey = _label(env, "creator_key") or (author_key(uid) if uid else None)
    return key, ckey, uid


def _masked(env, sel: Selection, key: Optional[str]):
    """The envelope with the Clerk id in its URL replaced by the user's key (source_url / provenance of the rows),
    unless --with-profiles."""
    if sel.with_profiles or not key:
        return env
    return dataclasses.replace(env, url=USER_ID_PATH_RE.sub(f"/user/key:{key}/", env.url))


def media_keys(*urls: Any) -> list[str]:
    """'media:<last uuid of the URL path>' of output URLs (inputs host excluded), as scripts/merge_generations.py."""
    out = []
    for u in urls:
        if isinstance(u, str) and u and not any(h in u for h in INPUT_HOSTS):
            found = UUID_RE.findall(u.split("?")[0])
            if found:
                out.append(f"media:{found[-1].lower()}")
    return list(dict.fromkeys(out))


ASSET_USED = {"id", "status", "job_set_id", "job_set_type", "job_set_parent_id", "job_set_client_meta", "params",
              "results", "result", "created_at", "published_at", "user_id", "publication", "profile", "meta"}
PROFILE_PERSONAL = {"profile", "user_id"}
PROJECT_USED = {"publication_type", "publication_id", "name", "slug", "description", "cover", "thumbnail_url",
                "views", "likes", "clones", "stats", "contest_key", "authors", "author_user_ids", "gallery_media"}
FOLDER_USED = {"publication_type", "folder_id", "name", "thumbnail_url", "created_at"}
SUBMISSION_USED = {"publication_type", "submission_id", "contest_id", "contest_slug", "thumbnail_url", "preview_url",
                   "video_url", "title", "description", "created_at"}


def _work_base(env, sel: Selection, key, ckey, uid, ptype: str, item_id: str, position: int) -> dict[str, Any]:
    out = {**_base(env, "projects_user_work"), "work_id": make_id(key, ptype, item_id), "creator_uid_key": key, "creator_key": ckey,
           "position": position, "publication_type": ptype}
    if sel.with_profiles:
        out["user_id"] = uid
    return out


def _asset_work(item: dict, env, sel: Selection, key, ckey, uid, position: int) -> Optional[dict]:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    jid = _str(data.get("id"))
    if not jid:
        return None
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    results = data.get("results") if isinstance(data.get("results"), dict) else {}
    raw = results.get("raw") if isinstance(results.get("raw"), dict) else {}
    mini = results.get("min") if isinstance(results.get("min"), dict) else {}
    hls = results.get("hls") if isinstance(results.get("hls"), dict) else {}
    h264 = results.get("h264") if isinstance(results.get("h264"), dict) else {}
    pub = data.get("publication") if isinstance(data.get("publication"), dict) else {}
    meta = data.get("job_set_client_meta") if isinstance(data.get("job_set_client_meta"), dict) else {}
    url = _str(raw.get("url"))
    out = {
        **_work_base(env, sel, key, ckey, uid, "asset", jid, position),
        "publication_id": _str(item.get("id_")) or _str(pub.get("id")),
        "generation_key": f"job:{jid.lower()}",
        "media_keys": media_keys(url, mini.get("url"), hls.get("url"), h264.get("url")),
        "job_id": jid,
        "status": _str(data.get("status")),
        "job_set_id": _str(data.get("job_set_id")),
        "job_set_type": _str(data.get("job_set_type")),
        "job_set_parent_id": _str(data.get("job_set_parent_id")),
        "job_source": _str(meta.get("source")),
        "media_type": _media_type(raw.get("type") or mini.get("type")),
        "prompt": _str(params.get("prompt")),
        "params": params,
        "aspect_ratio": _str(params.get("aspect_ratio")),
        "resolution": _str(params.get("resolution") or params.get("quality")),
        "width": _int(params.get("width")),
        "height": _int(params.get("height")),
        "duration_seconds": _float(params.get("duration")),
        "seed": _int(params.get("seed")),
        "batch_size": _int(params.get("batch_size")),
        "input_media": _inputs(params),
        "url": url,
        "min_url": _str(mini.get("url")),
        "thumbnail_url": _str(raw.get("thumbnail_url") or mini.get("thumbnail_url")),
        "hls_url": _str(hls.get("url")),
        "h264_url": _str(h264.get("url")),
        "variants": _variants(results),
        "likes": _int(pub.get("likes_count")),
        "views": _int(pub.get("views_count")),
        "listing_views": _int(item.get("views")),
        "clones": _int(item.get("clones")),
        "approved": pub.get("approved"),
        "pinned_at": iso(pub.get("pinned_at")),
        "created_at": iso(data.get("created_at")),
        "published_at": iso(data.get("published_at")),
        "extra": {**_rest(data, ASSET_USED),
                  **({"meta": data["meta"]} if isinstance(data.get("meta"), dict) and data["meta"] else {}),
                  **({"publication": _rest(pub, {"id", "views_count", "likes_count", "approved", "pinned_at"})}
                     if _rest(pub, {"id", "views_count", "likes_count", "approved", "pinned_at"}) else {})},
    }
    if sel.with_profiles:
        prof = data.get("profile") if isinstance(data.get("profile"), dict) else {}
        out["username"] = _str(prof.get("username"))
        out["avatar_url"] = _str(prof.get("avatar_url"))
    return out


def _project_work(item: dict, env, sel: Selection, key, ckey, uid, position: int) -> Optional[dict]:
    pid = _str(item.get("publication_id"))
    if not pid:
        return None
    cover = item.get("cover") if isinstance(item.get("cover"), dict) else {}
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    return {
        **_work_base(env, sel, key, ckey, uid, str(item.get("publication_type")), pid, position),
        "publication_id": pid,
        "name": item.get("name"),
        "slug": _str(item.get("slug")),
        "description": item.get("description"),
        "cover_url": _str(cover.get("url")),
        "thumbnail_url": _str(item.get("thumbnail_url")),
        "contest_key": _str(item.get("contest_key")),
        "likes": _int(item.get("likes")),
        "views": _int(item.get("views")),
        "clones": _int(item.get("clones")),
        "duration_seconds": _float(item.get("duration_seconds")),
        "credits_spent_raw": _float(stats.get("credits_spent")),
        "generations_count": _int(stats.get("generations_count")),
        "extra": _rest(item, PROJECT_USED | {"duration_seconds"}, {"authors", "author_user_ids"}),
    }


def _folder_work(item: dict, env, sel: Selection, key, ckey, uid, position: int) -> Optional[dict]:
    fid = _str(item.get("folder_id"))
    if not fid:
        return None
    return {**_work_base(env, sel, key, ckey, uid, "folder", fid, position), "folder_id": fid,
            "name": item.get("name"), "thumbnail_url": _str(item.get("thumbnail_url")),
            "created_at": iso(item.get("created_at")), "extra": _rest(item, FOLDER_USED)}


def _submission_work(item: dict, env, sel: Selection, key, ckey, uid, position: int) -> Optional[dict]:
    sid = _str(item.get("submission_id"))
    if not sid:
        return None
    return {**_work_base(env, sel, key, ckey, uid, "contest_submission", sid, position), "submission_id": sid,
            "contest_id": _str(item.get("contest_id")), "contest_slug": _str(item.get("contest_slug")),
            "name": item.get("title"), "description": item.get("description"),
            "thumbnail_url": _str(item.get("thumbnail_url")), "preview_url": _str(item.get("preview_url")),
            "video_url": _str(item.get("video_url")), "created_at": iso(item.get("created_at")),
            "extra": _rest(item, SUBMISSION_USED)}


WORK_PARSERS = {"asset": _asset_work, "project_publication": _project_work, "project": _project_work,
                "folder": _folder_work, "contest_submission": _submission_work}


def parse_user_works(env, sel: Selection) -> list[dict]:
    """`/user/{user_id}/v2/publications` -> {publications, has_more, cursor, total}. Unknown types (blog_post …) are
    skipped like the web app does."""
    body = env.body if isinstance(env.body, dict) else {}
    key, ckey, uid = _user(env, sel)
    env = _masked(env, sel, key)
    offset = _int(_label(env, "offset")) or 0
    out = []
    for i, item in enumerate(_list(body.get("publications"))):
        if not isinstance(item, dict):
            continue
        fn = WORK_PARSERS.get(str(item.get("publication_type")))
        w = fn(item, env, sel, key, ckey, uid, offset + i) if fn else None
        if w:
            out.append(w)
    return out


def parse_user_stats(env, sel: Selection) -> list[dict]:
    body = env.body if isinstance(env.body, dict) else {}
    key, ckey, uid = _user(env, sel)
    if not key or not any(k in body for k in ("posts_count", "likes_count", "views_count")):
        return []
    env = _masked(env, sel, key)
    return [{**_base(env, "projects_user_stats"), "creator_uid_key": key, "creator_key": ckey,
             **{k: _int(body.get(k)) for k in ("posts_count", "likes_count", "views_count")},
             "works_total": None, "user_id": uid if sel.with_profiles else None,
             "extra": _rest(body, {"posts_count", "likes_count", "views_count"}, {"user_id", "username"})}]


def owner_user_ids(env) -> list[str]:
    """Clerk ids of users discovered in a response, for --with-user-works: owners of listed projects (--users
    listing, contest entries) and contest submitters. Owner = the is_owner author, else the first author id."""
    body = env.body if isinstance(env.body, dict) else {}
    out: list[str] = []
    if env.endpoint == "projects_contest_submissions":
        for it in _list(body.get("items")):
            u = it.get("user") if isinstance(it, dict) and isinstance(it.get("user"), dict) else {}
            uid = _str(u.get("id") or u.get("user_id") or (it.get("user_id") if isinstance(it, dict) else None))
            if uid:
                out.append(uid)
        return list(dict.fromkeys(out))
    items = body.get("publications") if env.endpoint == "projects_user_publications" else body.get("items")
    for it in _list(items):
        if not isinstance(it, dict):
            continue
        authors = [a for a in _list(it.get("authors")) if isinstance(a, dict)]
        owner = next((a for a in authors if a.get("is_owner")), None)
        uid = _str((owner or {}).get("id") or (owner or {}).get("user_id"))
        if not uid:
            ids = [str(x) for x in _list(it.get("author_user_ids")) if x]
            uid = ids[0] if ids else _str((authors[0] if authors else {}).get("id"))
        if uid:
            out.append(uid)
    return list(dict.fromkeys(out))

