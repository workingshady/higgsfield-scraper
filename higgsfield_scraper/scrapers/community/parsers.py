"""Pure parsers: Envelope -> entity dicts (no network, no Scrapy). Used by the spider and by offline `normalize`."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from ...core.dataset import make_id
from ...core.privacy import creator_uid_key
from .endpoints import (BENEFITS_ENDPOINT, COMMENTS_ENDPOINT, COMPARE_ENDPOINT, CREATORS_ENDPOINT, DETAIL_ENDPOINT,
                        ENDPOINT_FEEDS, ENTITY_COMMENTS_ENDPOINT, FEED_ENDPOINT, JOB_COSTS_ENDPOINT, PLANS_ENDPOINT,
                        POSTS_LIST_ENDPOINT, SHOTS_ENDPOINT, TALENTS_ENDPOINT, VIRAL_ENDPOINT)
from .endpoints import (COLLECTIONS_ENDPOINT, EXPLORE_CARDS_ENDPOINT, JOB_SHOWCASE_ENDPOINT, JOB_SHOWCASE_PAGES,
                        MUSIC_CARD_OPTIONS_ENDPOINT, MUSIC_CARDS_ENDPOINT)
from .endpoints import FEED_CATEGORIES_ENDPOINT, FEED_ONGOING_ENDPOINT
from .options import Selection

# settings key -> accepted python types (a value of another type stays in params_extra, so nothing is lost)
SETTINGS_TYPES: dict[str, tuple[type, ...]] = {
    "width": (int,), "height": (int,), "aspect_ratio": (str,), "resolution": (str,), "quality": (str,),
    "duration": (int, float), "batch_size": (int,), "seed": (int,), "model": (str,), "mode": (str,),
    "style_id": (str,), "style_strength": (int, float), "preset_id": (str,), "chain_preset_id": (str,),
    "motion_id": (str,), "enhance_prompt": (bool,), "output_format": (str,), "background": (str,),
    "remove_bg": (bool,), "generate_audio": (bool,), "sound": (str,), "cfg_scale": (int, float), "steps": (int,),
    "thinking_level": (str,), "genre": (str,), "speedramp": (str,), "prompt_language": (str,),
    "bitrate_mode": (str,), "draft": (bool,), "multi_shots": (bool,), "multi_shot_mode": (str,),
    "use_unlim": (bool,), "use_relax": (bool,), "camera_model_id": (str,), "camera_lens_id": (str,),
}
TEXT_PARAMS = ("prompt", "negative_prompt")
# params holding input media: list params and single-object params
INPUT_LIST_PARAMS = ("medias", "input_images", "reference_elements", "kling_elements")
INPUT_ONE_PARAMS = ("input_image", "image_reference", "custom_reference", "draw_input_image", "input_audio",
                    "input_video", "end_image", "start_image")
PROFILE_FIELDS = ("username", "avatar_url", "instagram_handle", "twitter_handle", "youtube_handle", "tiktok_handle",
                  "badge", "badges")
KNOWN_TOP = {"id", "job_set_type", "job_set_id", "job_set_parent_id", "job_set_client_meta", "board_ids", "params",
             "meta", "status", "ip_check_finished", "ip_detected", "can_bypass_ip", "deepfake_consent_required",
             "result", "results", "published_at", "created_at", "user_id", "trace_id", "cluster_hash", "publication",
             "profile", "can_upgrade_to_4k", "upgrade_options", "expires_at"}
MEDIA_TYPES = ("image", "video", "audio")


# ------------------------------------------------------------------ small helpers
def iso_ts(v: Any) -> Optional[str]:
    """unix seconds (float/int/str) or ISO string -> ISO-8601 UTC; None stays None."""
    if v in (None, ""):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat()
    s = str(v).strip()
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc).isoformat()
    except ValueError:
        pass
    s = s.replace("Z", "+00:00")
    # Python 3.10 fromisoformat needs 3 or 6 fractional digits; fnf-community sends 1-6 ("…:50.21733Z")
    s = re.sub(r"(\.\d{1,6})\d*(?=[+-]\d\d:\d\d$|$)", lambda m: m.group(1).ljust(7, "0"), s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def _int(v: Any) -> Optional[int]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _bool(v: Any) -> Optional[bool]:
    return v if isinstance(v, bool) else None


def _str(v: Any) -> Optional[str]:
    return None if v is None else str(v)


def parse_upstream_usage(cost: Any) -> Optional[dict]:
    """meta.cost is a JSON *string* with the provider's token usage (or null)."""
    if cost in (None, ""):
        return None
    if isinstance(cost, dict):
        return cost
    try:
        v = json.loads(cost)
    except (TypeError, ValueError):
        return {"raw": str(cost)}
    return v if isinstance(v, dict) else {"value": v}


def media_type_of(item: dict) -> str:
    results = item.get("results") if isinstance(item.get("results"), dict) else {}
    for key in ("raw", "min", "h264", "hls"):
        v = results.get(key)
        if isinstance(v, dict) and v.get("type"):
            t = str(v["type"]).lower()
            return t if t in MEDIA_TYPES else "unknown"
    res = item.get("result")
    if isinstance(res, dict) and res.get("type"):
        t = str(res["type"]).lower()
        return t if t in MEDIA_TYPES else "unknown"
    return "unknown"


# ------------------------------------------------------------------ item parts
def _input(param: str, obj: Any, index: int) -> dict:
    if not isinstance(obj, dict):
        return {"index": index, "param": param, "role": param, "url": obj if isinstance(obj, str) else None,
                "extra": {} if isinstance(obj, str) else {"value": obj}}
    data = obj.get("data") if param == "medias" and isinstance(obj.get("data"), dict) else obj
    role = obj.get("role") if param == "medias" else (obj.get("category") or obj.get("role") or param)
    used = {"id", "url", "type", "name", "width", "height"}
    extra = {k: v for k, v in data.items() if k not in used}
    if data is not obj:
        extra.update({f"_{k}": v for k, v in obj.items() if k not in ("data", "role")})
    return {"index": index, "param": param, "role": _str(role), "url": _str(data.get("url")), "id": _str(data.get("id")),
            "type": _str(data.get("type")), "name": _str(data.get("name")), "width": _int(data.get("width")),
            "height": _int(data.get("height")), "extra": extra}


def parse_inputs(params: dict) -> tuple[list[dict], set[str]]:
    """-> (inputs, params keys consumed). Reference elements keep their own media list in `extra.medias`."""
    out: list[dict] = []
    used: set[str] = set()
    for p in INPUT_LIST_PARAMS:
        v = params.get(p)
        if isinstance(v, list):
            used.add(p)
            for obj in v:
                out.append(_input(p, obj, len(out)))
    for p in INPUT_ONE_PARAMS:
        if p in params and (params[p] is None or isinstance(params[p], (dict, str))):
            used.add(p)
            if params[p] is not None:
                out.append(_input(p, params[p], len(out)))
    return out, used


def parse_results(item: dict) -> list[dict]:
    out = []
    results = item.get("results")
    if isinstance(results, dict):
        for name, v in results.items():
            if isinstance(v, dict):
                out.append({"name": name, "type": _str(v.get("type")), "url": _str(v.get("url")),
                            "thumbnail_url": _str(v.get("thumbnail_url")),
                            "extra": {k: x for k, x in v.items() if k not in ("type", "url", "thumbnail_url")}})
            elif isinstance(v, str):
                out.append({"name": name, "url": v, "extra": {}})
    res = item.get("result")
    if isinstance(res, dict) and res.get("url") not in {r.get("url") for r in out}:
        out.append({"name": "result", "type": _str(res.get("type")), "url": _str(res.get("url")),
                    "thumbnail_url": _str(res.get("thumbnail_url")),
                    "extra": {k: x for k, x in res.items() if k not in ("type", "url", "thumbnail_url")}})
    return out


def split_params(params: dict) -> tuple[dict, dict, dict, list[dict]]:
    """-> (text {prompt, negative_prompt}, settings, params_extra, inputs). Every key lands in exactly one place."""
    text = {k: params.get(k) if isinstance(params.get(k), str) else None for k in TEXT_PARAMS}
    inputs, used = parse_inputs(params)
    settings: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for k, v in params.items():
        if k in used or (k in TEXT_PARAMS and (v is None or isinstance(v, str))):
            continue
        types = SETTINGS_TYPES.get(k)
        if types is not None and (v is None or (isinstance(v, types) and not (isinstance(v, bool) and bool not in types))):
            settings[k] = v
        else:
            extra[k] = v
    return text, settings, extra, inputs


def creator_ref(item: dict, with_profiles: bool) -> dict:
    ref: dict[str, Any] = {"user_id": _str(item.get("user_id"))}
    prof = item.get("profile") if isinstance(item.get("profile"), dict) else {}
    if with_profiles:
        ref.update({k: prof.get(k) for k in PROFILE_FIELDS})
    return ref


def parse_generation(item: dict, feed: str, sel: Selection, provenance: dict, detail: bool = False) -> dict:
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    text, settings, extra, inputs = split_params(params)
    pub = item.get("publication") if isinstance(item.get("publication"), dict) else {}
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    jst = _str(item.get("job_set_type"))
    return {
        "kind": "community_generation",
        "generation_id": str(item.get("id")),
        "publication_id": _str(pub.get("id")),
        "feed": feed,
        "detail_fetched": detail,
        "job_set_type": jst,
        "model_id": jst,
        "job_set_id": _str(item.get("job_set_id")),
        "parent_id": _str(item.get("job_set_parent_id")),
        "media_type": media_type_of(item),
        "status": _str(item.get("status")),
        "prompt": text["prompt"],
        "negative_prompt": text["negative_prompt"],
        "settings": settings,
        "params_extra": extra,
        "raw_params": params if sel.with_raw_params else None,
        "inputs": inputs,
        "results": parse_results(item),
        "engagement": {"views": _int(pub.get("views_count")), "likes": _int(pub.get("likes_count")),
                       "approved": _bool(pub.get("approved")), "pinned_at": iso_ts(pub.get("pinned_at")),
                       "is_liked_by_user": _bool(pub.get("is_liked_by_user"))},
        "created_at": iso_ts(item.get("created_at")),
        "published_at": iso_ts(item.get("published_at")),
        "expires_at": iso_ts(item.get("expires_at")),
        "can_upgrade_to_4k": _bool(item.get("can_upgrade_to_4k")),
        "upgrade_options": item.get("upgrade_options") if isinstance(item.get("upgrade_options"), list) else None,
        "moderation": {k: _bool(item.get(k)) for k in ("ip_check_finished", "ip_detected",
                                                        "deepfake_consent_required", "can_bypass_ip")},
        "cluster_hash": _str(item.get("cluster_hash")),
        "trace_id": _str(item.get("trace_id")),
        "board_ids": item.get("board_ids") if isinstance(item.get("board_ids"), list) else [],
        "client_meta": item.get("job_set_client_meta") if isinstance(item.get("job_set_client_meta"), dict) else None,
        "is_bonus_generation": _bool(meta.get("is_bonus_generation")),
        "upstream_usage": parse_upstream_usage(meta.get("cost")),
        "meta_extra": {k: v for k, v in meta.items() if k not in ("cost", "is_bonus_generation")},
        "extra": {k: v for k, v in item.items() if k not in KNOWN_TOP and v is not None},
        "creator": creator_ref(item, sel.with_profiles),
        "creator_uid_key": creator_uid_key(item.get("user_id")),
        "estimated_cost": None,
        "source": provenance,
    }


def parse_creator(item: dict, provenance: dict) -> Optional[dict]:
    uid = item.get("user_id")
    prof = item.get("profile")
    if not uid or not isinstance(prof, dict):
        return None
    return {"kind": "community_creator", "user_id": str(uid),
            **{k: prof.get(k) for k in PROFILE_FIELDS if k != "badges"},
            "badges": prof.get("badges") if isinstance(prof.get("badges"), list) else [],
            "generations_in_dataset": None, "creator_uid_key": creator_uid_key(uid), "source": provenance}


def _items_of(body: Any) -> list[dict]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for k in ("items", "comments", "data", "results"):
            if isinstance(body.get(k), list):
                return [x for x in body[k] if isinstance(x, dict)]
    return []


COMMENT_USED = {"id", "comment_id", "parent_id", "text", "content", "body", "created_at", "updated_at", "likes_count",
                "like_count", "likes", "dislike_count", "reply_count", "reactions", "mentions", "entity_type",
                "publication_id", "user_id", "user", "profile", "author", "is_mine"}
AUTHOR_PUBLIC = ("badge", "rating_points")      # kept without --with-profiles (not identifying)


def parse_comments(body: Any, publication_id: str, sel: Selection, provenance: dict) -> list[dict]:
    """fnf-community comments: {comments:[{id, publication_id, parent_id?, user_id, content, author{...},
    reply_count, like_count, dislike_count, reactions[{emoji,count}], mentions[], created_at, updated_at}],
    has_more}. The pseudonymous user_id is kept (as for creators); username, name, avatar and headline
    only with --with-profiles."""
    out = []
    for c in _items_of(body):
        cid = c.get("id") or c.get("comment_id")
        if not cid:
            continue
        author = c.get("author") if isinstance(c.get("author"), dict) else {}
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        prof = c.get("profile") if isinstance(c.get("profile"), dict) else {}
        person = {**user, **prof, **author}
        uid = _str(c.get("user_id") or person.get("id"))
        mentions = c.get("mentions") if isinstance(c.get("mentions"), list) else []
        out.append({
            "kind": "community_comment", "comment_id": str(cid),
            "publication_id": _str(c.get("publication_id")) or publication_id,
            "thread_type": _str(c.get("entity_type")),
            "parent_id": _str(c.get("parent_id")),
            "text": _str(c.get("content") or c.get("text") or c.get("body")),
            "created_at": iso_ts(c.get("created_at")),
            "updated_at": iso_ts(c.get("updated_at")),
            "likes": _int(c.get("like_count", c.get("likes_count", c.get("likes")))),
            "dislikes": _int(c.get("dislike_count")),
            "reply_count": _int(c.get("reply_count")),
            "reactions": [{"emoji": _str(r.get("emoji")), "count": _int(r.get("count"))}
                          for r in c.get("reactions") or [] if isinstance(r, dict)],
            "mention_count": len(mentions),
            "user_id": uid,                                 # pseudonymous id, like creator user_id
            "creator_uid_key": creator_uid_key(uid),

            "username": _str(person.get("username")) if sel.with_profiles else None,
            "author": {k: (None if person.get(k) == "" else person.get(k))
                       for k in (("full_name", "avatar_url", "headline") if sel.with_profiles else ()) + AUTHOR_PUBLIC
                       if k in person},
            "extra": {k: v for k, v in c.items() if k not in COMMENT_USED},
            "source": provenance})
    return out


def parse_posts(body: Any) -> list[dict]:
    """fnf-community posts feed -> [{id, comment_count}] (posts themselves are not stored; only used to find
    threads with comments)."""
    items = body.get("publications") if isinstance(body, dict) else None
    return [{"id": str(p["id"]), "comment_count": _int(p.get("comment_count")) or 0}
            for p in items or [] if isinstance(p, dict) and p.get("id")]


# ------------------------------------------------------------------ opt-in Community pages
# (shots, posts, feed, creators, talents; see endpoints.EXTRA_FEEDS and docs/COMMUNITY_COVERAGE.md)
SITE = "https://higgsfield.ai"
PERSON_PROFILE = ("username", "full_name", "avatar_url", "headline")


def _nz(v: Any) -> Optional[str]:
    """str or None; empty / whitespace-only strings are None (the API sends "" for missing titles, names …)."""
    if v is None or isinstance(v, (dict, list)):
        return None
    s = str(v)
    return s if s.strip() else None


def _float(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _media_type(v: Any) -> str:
    t = str(v or "").lower()
    return t if t in MEDIA_TYPES else "unknown"


def person_ref(author: Any, user_id: Any, sel: Selection) -> dict:
    """Author block. Without --with-profiles only the pseudonymous id, the badge key and the rating are kept."""
    a = author if isinstance(author, dict) else {}
    ref: dict[str, Any] = {"user_id": _str(user_id or a.get("id") or a.get("user_id")),
                           "badge": _nz(a.get("badge")), "rating_points": _int(a.get("rating_points"))}
    if sel.with_profiles:
        ref.update({k: _nz(a.get(k)) for k in PERSON_PROFILE})
    return ref


def parse_shot(it: dict, snapshot_id: Optional[str], sel: Selection, prov: dict) -> dict:
    sid = str(it["id"])
    w, h = _int(it.get("width")), _int(it.get("height"))
    return {"kind": "community_shot", "shot_id": sid, "generation_id": _str(it.get("job_id")),
            "url": f"{SITE}/community/generations?shot={sid}", "job_set_type": _str(it.get("model")),
            "media_type": _media_type(it.get("media_type")), "media_url": _nz(it.get("media_url")),
            "thumbnail_url": _nz(it.get("thumbnail_url")), "width": w, "height": h,
            "likes": _int(it.get("like_count")), "views": _int(it.get("view_count")),
            "comments": _int(it.get("comment_count")), "aesthetic_score": _float(it.get("aesthetic_score")),
            "aesthetic_label": _bool(it.get("aesthetic_label")), "published_at": iso_ts(it.get("published_at")),
            "author": (a := person_ref(it.get("author"), it.get("author_id"), sel)),
            "creator_uid_key": creator_uid_key(a["user_id"]), "snapshot_id": snapshot_id, "source": prov}


def parse_shots(body: Any, sel: Selection, prov: dict) -> list[dict]:
    b = body if isinstance(body, dict) else {}
    snap = _str(b.get("snapshot_id"))
    return [parse_shot(it, snap, sel, prov) for it in _items_of(b) if it.get("id")] + \
        parse_shot_model_facets(b, snap, prov)


def parse_shot_model_facets(b: dict, snap: Optional[str], prov: dict) -> list[dict]:
    """available_models[] ({model, media_type}) of a Shots page -> community_shot_model_facet (every page repeats
    the list; the dedup pipeline keeps the first). No count in the API: shots_in_run is filled by the dataset."""
    am = b.get("available_models") if isinstance(b.get("available_models"), list) else []
    out = []
    for n, m in enumerate(x for x in am if isinstance(x, dict)):
        model = _nz(m.get("model"))
        if model is None:
            continue
        mt = _nz(m.get("media_type"))
        out.append({"kind": "community_shot_model_facet", "facet_id": make_id("shot_model_facet", model, mt or ""),
                    "model": model, "media_type": mt, "position": n, "shots_in_run": None, "snapshot_id": snap,
                    "extra": {k: v for k, v in m.items() if k not in ("model", "media_type") and v is not None},
                    "source": prov})
    return out


POST_MEDIA_USED = {"type", "job_result", "url", "project_publication_id", "job_id", "blog_post_id", "card"}
POST_USED = {"id", "user_id", "title", "content", "like_count", "dislike_count", "comment_count", "views_count",
             "share_count", "author", "created_at", "updated_at", "is_mine", "is_subscribed", "is_liked"}


# per-viewer state a logged-in response adds (my likes / follows / votes): never stored, so runs with and without a
# session give the same records (docs/COMMUNITY_COVERAGE.md "Anonymous vs logged in")
VIEWER_FLAGS = frozenset({"is_liked_by_user", "liked_by_me", "is_liked", "is_followed", "join_requested",
                          "is_subscribed", "is_mine", "my_vote", "notification_level", "permissions"})


def drop_viewer_flags(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: drop_viewer_flags(v) for k, v in o.items() if k not in VIEWER_FLAGS}
    if isinstance(o, list):
        return [drop_viewer_flags(x) for x in o]
    return o


def _post_media(m: dict, i: int) -> dict:
    card = m.get("card") if isinstance(m.get("card"), dict) else {}
    video = card.get("video") if isinstance(card.get("video"), dict) else {}
    jr = m.get("job_result") if isinstance(m.get("job_result"), dict) else {}
    mr = m.get("min_result") if isinstance(m.get("min_result"), dict) else {}
    return {"index": i, "type": _nz(m.get("type")), "url": _nz(jr.get("url") or m.get("url")),
            "project_publication_id": _nz(m.get("project_publication_id")), "job_id": _nz(m.get("job_id")),
            "blog_post_id": _nz(m.get("blog_post_id")), "card_id": _nz(card.get("id")),
            "card_title": _nz(card.get("title")), "card_slug": _nz(card.get("slug")),
            "card_description": _nz(card.get("description")), "card_cover_url": _nz(card.get("cover_url")),
            "video_url": _nz(video.get("url")), "video_hls_url": _nz(video.get("hls_url")),
            "video_preview_url": _nz(video.get("preview_url")), "video_thumbnail_url": _nz(video.get("thumbnail_url")),
            "width": _int(video.get("width")), "height": _int(video.get("height")),
            "duration_seconds": _float(video.get("duration")),
            "card_stats": card.get("stats") if isinstance(card.get("stats"), dict) else None,
            "card_likes": _int(card.get("like_count")), "card_views": _int(card.get("views_count")),
            "card_comments": _int(card.get("comment_count")), "card_published_at": iso_ts(card.get("published_at")),
            "job_result_thumbnail_url": _nz(jr.get("thumbnail_url")), "min_result_thumbnail_url": _nz(mr.get("thumbnail_url")),
            "extra": {k: drop_viewer_flags(v) for k, v in m.items() if k not in POST_MEDIA_USED and v not in (None, "")}}


def parse_post(p: dict, sel: Selection, prov: dict) -> dict:
    """One fnf-community publication (Community post / room discussion)."""
    content = p.get("content") if isinstance(p.get("content"), dict) else {}
    pid = str(p["id"])
    return {"kind": "community_post", "post_id": pid, "url": f"{SITE}/community/feed/{pid}",
            "title": _nz(p.get("title")) or _nz(content.get("title")), "text": _nz(content.get("text")),
            "room_id": _nz(content.get("room_id")), "post_kind": _nz(content.get("kind")),
            "media": [_post_media(m, i) for i, m in enumerate(content.get("medias") or []) if isinstance(m, dict)],
            "likes": _int(p.get("like_count")), "dislikes": _int(p.get("dislike_count")),
            "comments": _int(p.get("comment_count")), "views": _int(p.get("views_count")),
            "shares": _int(p.get("share_count")), "created_at": iso_ts(p.get("created_at")),
            "updated_at": iso_ts(p.get("updated_at")),
            "author": (a := person_ref(p.get("author"), p.get("user_id"), sel)),
            "creator_uid_key": creator_uid_key(a["user_id"]),
            "extra": {**{k: drop_viewer_flags(v) for k, v in p.items() if k not in POST_USED and v is not None},
                      **{f"content.{k}": drop_viewer_flags(v) for k, v in content.items()
                         if k not in ("title", "text", "medias", "room_id", "kind") and v is not None}},
            "source": prov}


def parse_posts_list(body: Any, sel: Selection, prov: dict) -> list[dict]:
    items = body.get("publications") if isinstance(body, dict) else None
    return [parse_post(p, sel, prov) for p in items or [] if isinstance(p, dict) and p.get("id")]


def _first_line(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    line = s.strip().splitlines()[0].strip()
    return line[:200] or None


def parse_feed_items(body: Any, offset: int, sel: Selection, prov: dict) -> list[dict]:
    b = body if isinstance(body, dict) else {}
    snap = _str(b.get("snapshot_id"))
    out = []
    for n, it in enumerate(_items_of(b)):
        if not it.get("id"):
            continue
        t = str(it.get("type") or "unknown")
        t = t if t in ("generation", "project_publication", "blog_post", "post") else "unknown"
        iid = str(it["id"])
        gen = it.get("generation") if isinstance(it.get("generation"), dict) else {}
        card = it.get("card") if isinstance(it.get("card"), dict) else {}
        post = it.get("post") if isinstance(it.get("post"), dict) else {}
        pc = post.get("content") if isinstance(post.get("content"), dict) else {}
        mw = it.get("made_with") if isinstance(it.get("made_with"), dict) else {}
        tc = it.get("top_comment") if isinstance(it.get("top_comment"), dict) else {}
        video = card.get("video") if isinstance(card.get("video"), dict) else {}
        url = {"generation": f"{SITE}/community/generations?shot={iid}", "post": f"{SITE}/community/feed/{iid}"}.get(t)
        views = gen.get("view_count") if t == "generation" else (card.get("views_count") if card else
                                                                  post.get("views_count"))
        out.append({
            "kind": "community_feed_item", "feed_item_id": make_id("feed_item", t, iid), "item_type": t,
            "item_id": iid, "url": url, "position": offset + n,
            "title": _nz(card.get("title")) or _nz(post.get("title")) or _first_line(_nz(pc.get("text"))),
            "description": _nz(card.get("description")), "slug": _nz(card.get("slug")),
            "media_type": _nz(gen.get("media_type")), "job_set_type": _nz(gen.get("model")),
            "generation_id": _nz(gen.get("job_id")), "made_with_tool": _nz(mw.get("tool")),
            "made_with_model": _nz(mw.get("model_name")), "media_url": _nz(gen.get("media_url")),
            "thumbnail_url": _nz(gen.get("thumbnail_url")) or _nz(video.get("thumbnail_url")),
            "cover_url": _nz(card.get("cover_url")), "video_url": _nz(video.get("url")),
            "video_hls_url": _nz(video.get("hls_url")), "video_preview_url": _nz(video.get("preview_url")),
            "width": _int(video.get("width")), "height": _int(video.get("height")),
            "duration_seconds": _float(video.get("duration")),
            "text": _nz(pc.get("text")) if t == "post" else None,
            "media": [_post_media(m, i) for i, m in enumerate(pc.get("medias") or []) if isinstance(m, dict)]
            if t == "post" else [],
            "likes": _int(it.get("like_count")), "comments": _int(it.get("comment_count")),
            "shares": _int(it.get("share_count")), "views": _int(views),
            "reading_time_minutes": _int(card.get("reading_time_minutes")),
            "project_stats": card.get("stats") if isinstance(card.get("stats"), dict) else None,
            "created_at": iso_ts(it.get("created_at")), "top_comment_id": _nz(tc.get("id")),
            "top_comment_likes": _int(tc.get("like_count")),
            "author": (a := person_ref(it.get("author"), None, sel)),
            "creator_uid_key": creator_uid_key(a["user_id"]), "snapshot_id": snap,
            "extra": _feed_item_extra(it), "source": prov})
    return out


FEED_ITEM_USED = {"type", "id", "author", "created_at", "like_count", "comment_count", "share_count", "made_with",
                  "top_comment", "generation", "card", "post"}
FEED_SUB_USED = {
    "generation": {"job_id", "model", "media_type", "media_url", "thumbnail_url", "view_count", "author", "id"},
    "card": {"id", "title", "slug", "description", "cover_url", "video", "stats", "views_count",
             "reading_time_minutes", "owner"},
    "post": {"id", "title", "content", "views_count", "author", "created_at", "like_count", "comment_count",
             "share_count"},
    "made_with": {"tool", "model_name"},
    "top_comment": {"id", "like_count", "author"},
}
CARD_VIDEO_USED = {"url", "hls_url", "preview_url", "thumbnail_url", "width", "height", "duration"}


def _feed_item_extra(it: dict) -> dict:
    """Every non-null field of a Feed item the typed columns do not hold (people only as ids; viewer flags never)."""
    out = {k: drop_viewer_flags(v) for k, v in it.items()
           if k not in FEED_ITEM_USED and k not in VIEWER_FLAGS and v is not None}
    for sub, used in FEED_SUB_USED.items():
        d = it.get(sub) if isinstance(it.get(sub), dict) else {}
        out.update({f"{sub}.{k}": drop_viewer_flags(v) for k, v in d.items()
                    if k not in used and k not in VIEWER_FLAGS and v is not None})
    card = it.get("card") if isinstance(it.get("card"), dict) else {}
    owner = card.get("owner") if isinstance(card.get("owner"), dict) else {}
    if owner.get("id"):
        out["card.owner.id"] = str(owner["id"])
    video = card.get("video") if isinstance(card.get("video"), dict) else {}
    out.update({f"card.video.{k}": v for k, v in video.items() if k not in CARD_VIDEO_USED and v is not None})
    post = it.get("post") if isinstance(it.get("post"), dict) else {}
    pc = post.get("content") if isinstance(post.get("content"), dict) else {}
    out.update({f"post.content.{k}": drop_viewer_flags(v) for k, v in pc.items()
                if k not in ("text", "medias") and v not in (None, "")})
    return out


CREATOR_PROFILE = ("username", "full_name", "headline", "bio", "location", "avatar_url")


def parse_creators(body: Any, listing: str, offset: int, sel: Selection, prov: dict) -> list[dict]:
    users = body.get("users") if isinstance(body, dict) else None
    out = []
    for n, u in enumerate(users or []):
        if not isinstance(u, dict) or not u.get("id"):
            continue
        works = []
        for w in u.get("items") or []:
            if not isinstance(w, dict):
                continue
            item = w.get("item") if isinstance(w.get("item"), dict) else {}
            pub = item.get("publication") if isinstance(item.get("publication"), dict) else {}
            works.append({"type": str(w.get("type") or "unknown"),
                          "item_id": _nz(item.get("publication_id")) or _nz(pub.get("id")) or _nz(item.get("id")),
                          "title": _nz(item.get("name")), "is_pinned": _bool(w.get("is_pinned"))})
        e = {"kind": "community_creator_stats", "record_id": make_id("creator_stats", listing, u["id"]),
             "listing": listing, "position": offset + n, "user_id": str(u["id"]),
             "rating_points": _int(u.get("rating_points")), "followers_count": _int(u.get("followers_count")),
             "following_count": _int(u.get("following_count")), "likes_count": _int(u.get("likes_count")),
             "views_count": _int(u.get("views_count")),
             "verified_projects_count": _int(u.get("verified_projects_count")),
             "latest_verified_at": iso_ts(u.get("latest_verified_at")), "is_pinned": _bool(u.get("is_pinned")),
             "badge": _nz(u.get("badge")),
             "badge_names": [str(x["name"]) for x in u.get("badges") or [] if isinstance(x, dict) and x.get("name")],
             "works_count": len(works), "works": works, "creator_uid_key": creator_uid_key(u["id"]), "source": prov}
        e.update({k: (_nz(u.get(k)) if sel.with_profiles else None) for k in CREATOR_PROFILE})
        out.append(e)
        rank = 0
        for w in u.get("items") or []:       # same items (and order) as `works` above: rank == works index
            if not isinstance(w, dict):
                continue
            out.append(parse_creator_work(w, rank, e, sel, prov))
            rank += 1
    return out


WORK_PROJECT_USED = {
    "publication_id", "project_id", "name", "slug", "description", "type", "state", "duration_seconds", "cover",
    "gallery_media", "trailer", "tags", "categories", "contest_key", "author_user_ids", "authors", "team", "views",
    "likes", "comments", "created_at", "published_at"}
WORK_MEDIA_USED = {"id", "type", "name", "url", "original_url", "preview_url", "thumbnail_url", "min_url",
                   "download_url", "width", "height", "duration", "object_fit"}
# shot fields copied from parse_generation (the same parser as community_generation)
WORK_GEN_FIELDS = ("generation_id", "publication_id", "job_set_type", "job_set_id", "parent_id", "media_type",
                   "status", "prompt", "negative_prompt", "settings", "params_extra", "raw_params", "inputs", "results",
                   "moderation", "created_at", "published_at", "expires_at", "can_upgrade_to_4k", "upgrade_options",
                   "cluster_hash", "trace_id", "board_ids", "client_meta", "is_bonus_generation", "upstream_usage",
                   "meta_extra")


def _work_media(d: Any, role: str, index: int) -> Optional[dict]:
    if not isinstance(d, dict):
        return None
    return {"index": index, "role": role, "media_id": _nz(d.get("id")), "type": _nz(d.get("type")),
            "name": _nz(d.get("name")), "url": _nz(d.get("url")), "original_url": _nz(d.get("original_url")),
            "preview_url": _nz(d.get("preview_url")), "thumbnail_url": _nz(d.get("thumbnail_url")),
            "min_url": _nz(d.get("min_url")), "download_url": _nz(d.get("download_url")),
            "width": _int(d.get("width")), "height": _int(d.get("height")),
            "duration_seconds": _float(d.get("duration")), "object_fit": _nz(d.get("object_fit")),
            "extra": {k: v for k, v in d.items() if k not in WORK_MEDIA_USED and v is not None}}


def parse_creator_work(w: dict, rank: int, card: dict, sel: Selection, prov: dict) -> dict:
    """One users[].items[] entry in full -> community_creator_work. `shot` items are published generation objects
    (parsed with parse_generation, like the gallery feeds); `project` items are project publication cards."""
    item = w.get("item") if isinstance(w.get("item"), dict) else {}
    t = str(w.get("type") or "unknown")
    uid = card["user_id"]
    pub = item.get("publication") if isinstance(item.get("publication"), dict) else {}
    e: dict[str, Any] = {
        "kind": "community_creator_work", "work_id": make_id("creator_work", card["listing"], uid, rank),
        "record_id": card["record_id"], "listing": card["listing"], "creator_user_id": uid,
        "creator_uid_key": creator_uid_key(uid), "rank": rank, "item_type": t,
        "item_id": _nz(item.get("publication_id")) or _nz(pub.get("id")) or _nz(item.get("id")),
        "is_pinned": _bool(w.get("is_pinned")), "source": prov}
    if t == "shot" or (t != "project" and item.get("job_set_type")):
        g = parse_generation(item, "detail", sel, prov)
        e.update({k: g[k] for k in WORK_GEN_FIELDS})
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        eng = g["engagement"]
        e.update({"enhanced_prompt": _nz(params.get("enhanced_prompt")), "likes": eng["likes"], "views": eng["views"],
                  "approved": eng["approved"], "pinned_at": eng["pinned_at"],
                  "url": f"{SITE}/community/generations?shot={g['publication_id']}" if g["publication_id"] else None,
                  "params_extra": drop_viewer_flags(g["params_extra"]),
                  "extra": drop_viewer_flags(g["extra"])})
        return e
    cover = _work_media(item.get("cover"), "cover", 0)
    trailer = _work_media(item.get("trailer"), "trailer", 0)
    gallery = [m for i, x in enumerate(item.get("gallery_media") or []) if (m := _work_media(x, "gallery", i))]
    authors = [str(a) for a in item.get("author_user_ids") or [] if a]
    team = item.get("team") if isinstance(item.get("team"), dict) else {}
    extra = {k: drop_viewer_flags(v) for k, v in item.items()
             if k not in WORK_PROJECT_USED and k not in VIEWER_FLAGS and v is not None}
    if team.get("id"):
        extra["team.id"] = str(team["id"])
    e.update({
        "title": _nz(item.get("name")), "description": _nz(item.get("description")), "slug": _nz(item.get("slug")),
        "url": None, "likes": _int(item.get("likes")), "views": _int(item.get("views")),
        "comments": _int(item.get("comments")), "created_at": iso_ts(item.get("created_at")),
        "published_at": iso_ts(item.get("published_at")),
        "project_publication_id": _nz(item.get("publication_id")), "project_id": _nz(item.get("project_id")),
        "project_type": _nz(item.get("type")), "state": _nz(item.get("state")),
        "duration_seconds": _float(item.get("duration_seconds")),
        "cover_url": cover["url"] if cover else None, "cover_width": cover["width"] if cover else None,
        "cover_height": cover["height"] if cover else None,
        "trailer_url": trailer["url"] if trailer else None,
        "trailer_thumbnail_url": trailer["thumbnail_url"] if trailer else None,
        "trailer_duration_seconds": trailer["duration_seconds"] if trailer else None,
        "gallery_media": ([cover] if cover else []) + gallery + ([trailer] if trailer else []),
        "tags": _strs(item.get("tags")),
        "categories": [str(c.get("slug") or c.get("id")) if isinstance(c, dict) else str(c)
                       for c in item.get("categories") or [] if c is not None],
        "contest_key": _nz(item.get("contest_key")), "author_user_ids": authors,
        "author_uid_keys": [k for a in authors if (k := creator_uid_key(a))], "extra": extra})
    return e


def parse_page(env, feed: str) -> dict:
    b = env.body if isinstance(env.body, dict) else {}
    nxt = b.get("cursor")
    return {"kind": "community_page", "page_id": make_id(env.endpoint, json.dumps(env.params, sort_keys=True)),
            "feed": feed, "cursor": env.params.get("cursor"), "next_cursor": None if nxt is None else repr_cursor(nxt),
            "has_more": _bool(b.get("has_more")), "total": _int(b.get("total")), "size": _int(env.params.get("size")),
            "items": len(_items_of(b)), "source": env.provenance()}


def repr_cursor(c: Any) -> str:
    """Cursors are floats (trending: score; approved/model-x: unix time). repr() keeps full precision."""
    return repr(c) if isinstance(c, float) else str(c)


def usd_per_credit_from_plans(body: dict, provenance: dict, usd_reference: str) -> tuple[Optional[float], list[str]]:
    from ...parsers.plans import parse_plans
    ref_type, _, ref_period = usd_reference.partition(":")
    for p in parse_plans(body, provenance):
        if p["kind"] == "plan" and p["plan_type"] == ref_type and p["billing_period"] == ref_period:
            rate = p["price_per_credit"]["after_offer"]
            if rate is not None:
                return float(rate), []
    return None, [f"usd_reference {usd_reference!r} not found in plan set; no USD estimates"]


# ------------------------------------------------------------------ envelope dispatch
def parse_envelope(env, sel: Selection) -> list[dict]:
    if env.status != 200 or not isinstance(env.body, (dict, list)):
        return []
    prov = env.provenance()
    ep = env.endpoint
    if ep in ENDPOINT_FEEDS:
        feed = ENDPOINT_FEEDS[ep]
        out = [parse_page(env, feed)]
        if not sel.detail:                      # with --detail the generations come from the detail responses
            for item in _items_of(env.body):
                out.extend(_generation_and_creator(item, feed, sel, prov, False))
        return out
    if ep == DETAIL_ENDPOINT and isinstance(env.body, dict) and env.body.get("id"):
        feed = env.params.get("feed") or "detail"
        return _generation_and_creator(env.body, feed, sel, prov, True)
    if ep == COMMENTS_ENDPOINT:
        return parse_comments(env.body, env.params.get("publication_id", ""), sel, prov)
    if ep == JOB_COSTS_ENDPOINT and isinstance(env.body, dict):
        n = len(env.body.get("data") or [])
        return [{"kind": "community_cost_basis", "basis_id": "job_costs", "job_costs": env.body,
                 "notes": [f"{n} job_set_types priced"], "source": prov}]
    if ep == VIRAL_ENDPOINT and isinstance(env.body, (list, dict)):
        body = env.body if isinstance(env.body, dict) else {"items": env.body}
        return [{"kind": "community_cost_basis", "basis_id": "viral_presets", "body": body,
                 "notes": ["viral preset price matrices fetched"], "source": prov}]
    if ep in (COMPARE_ENDPOINT, BENEFITS_ENDPOINT) and isinstance(env.body, dict):
        bid = "compare" if ep == COMPARE_ENDPOINT else "benefits"
        return [{"kind": "community_cost_basis", "basis_id": bid, "body": env.body,
                 "notes": [f"{bid} fetched for comparison-table fallback prices"], "source": prov}]
    if ep == PLANS_ENDPOINT and isinstance(env.body, dict):
        ref = f"{env.params.get('plan_set_key', '?')} {sel.usd_reference} after offer"
        rate, notes = usd_per_credit_from_plans(env.body, prov, sel.usd_reference)
        return [{"kind": "community_cost_basis", "basis_id": "usd_reference", "usd_per_credit": rate,
                 "usd_reference": ref, "notes": notes, "source": prov}]
    # ---- opt-in Community pages (never requested by default runs)
    if ep == SHOTS_ENDPOINT:
        return parse_shots(env.body, sel, prov)
    if ep == POSTS_LIST_ENDPOINT:
        return parse_posts_list(env.body, sel, prov)
    if ep == FEED_ENDPOINT:
        return parse_feed_items(env.body, _int(env.params.get("offset")) or 0, sel, prov)
    if ep in (CREATORS_ENDPOINT, TALENTS_ENDPOINT):
        listing = "creators" if ep == CREATORS_ENDPOINT else "talents"
        return parse_creators(env.body, listing, _int(env.params.get("offset")) or 0, sel, prov)
    if ep == ENTITY_COMMENTS_ENDPOINT:
        return parse_comments(env.body, env.params.get("entity_id", ""), sel, prov)
    # ---- opt-in gallery / template sources (never requested by default runs)
    if ep == MUSIC_CARDS_ENDPOINT:
        return parse_music_cards(env.body, prov)
    if ep == MUSIC_CARD_OPTIONS_ENDPOINT:
        return parse_music_card_options(env.body, env.params.get("group", ""), prov)
    if ep == JOB_SHOWCASE_ENDPOINT:
        return parse_job_showcase(env.body, env.params.get("slug", ""), sel, prov)
    if ep == COLLECTIONS_ENDPOINT:
        return parse_collection(env.body, env.params.get("slug", ""), prov)
    if ep == EXPLORE_CARDS_ENDPOINT:
        return parse_explore_cards(env.body, _int(env.params.get("offset")) or 0, prov)
    # ---- opt-in Feed hashtag categories (never requested by default runs)
    if ep in (FEED_CATEGORIES_ENDPOINT, FEED_ONGOING_ENDPOINT):
        return parse_feed_categories(env.body, "categories" if ep == FEED_CATEGORIES_ENDPOINT else "ongoing", prov)
    return []


def _generation_and_creator(item: dict, feed: str, sel: Selection, prov: dict, detail: bool) -> list[dict]:
    if not item.get("id"):
        return []
    out = [parse_generation(item, feed, sel, prov, detail)]
    if sel.with_profiles:
        c = parse_creator(item, prov)
        if c:
            out.append(c)
    return out


def keep(entity: dict, sel: Selection) -> bool:
    """Client-side filters (the approved feed ignores `type`; top/model-x ignore `model`)."""
    if entity.get("kind") != "community_generation" or entity.get("feed") == "detail":
        return True                             # explicitly requested --publication-ids are always kept
    if sel.models and entity.get("job_set_type") not in sel.models:
        return False
    if sel.type in ("image", "video") and entity.get("media_type") in MEDIA_TYPES and entity["media_type"] != sel.type:
        return False
    return True


# ------------------------------------------------------------------ opt-in gallery / template sources
# (--feeds music-cards, job-showcase, collections, explore-cards; docs/COMMUNITY_COVERAGE.md §3b)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
MUSIC_CARD_USED = {"id", "slug", "title", "description", "category", "categories", "thumbnail_media", "video_media",
                   "occasion", "occasion_text", "tone", "style", "music", "length", "recipients", "senders",
                   "song_title", "lyrics"}
OPTION_GROUP = {"styles": "style", "occasions": "occasion", "roles": "role"}
OPTION_KEY = {"style": "style", "occasion": "key", "role": "key"}
OPTION_USED = {"key", "style", "occasion", "role", "label", "hint", "icon_key", "parent", "thumbnail_media",
               "categories", "id"}
SHOWCASE_TOP = KNOWN_TOP | {"user"}
CARD_USED = ("id", "slug", "name", "description", "href", "href_mobile", "media")


def _dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _strs(v: Any) -> list[str]:
    return [str(x) for x in v if x is not None] if isinstance(v, list) else []


def parse_music_cards(body: Any, prov: dict) -> list[dict]:
    """fnf-cms-api /music-cards-presets -> community_music_card (+ the `categories` option list)."""
    b = _dict(body)
    out = []
    for n, it in enumerate(_items_of(b)):
        if not it.get("id"):
            continue
        th, vm = _dict(it.get("thumbnail_media")), _dict(it.get("video_media"))
        recipients = [{"main": _bool(r.get("main")), "name": _nz(r.get("name")), "role": _nz(r.get("role")),
                       "facts_wishes": _strs(r.get("facts_wishes")),
                       "extra": {k: v for k, v in r.items() if k not in ("main", "name", "role", "facts_wishes")
                                 and v is not None}}
                      for r in it.get("recipients") or [] if isinstance(r, dict)]
        out.append({
            "kind": "community_music_card", "music_card_id": str(it["id"]), "slug": _nz(it.get("slug")),
            "position": n, "title": _nz(it.get("title")), "description": _nz(it.get("description")),
            "category": _nz(it.get("category")), "categories": _strs(it.get("categories")),
            "occasion": _nz(it.get("occasion")), "occasion_text": _nz(it.get("occasion_text")),
            "tone": _nz(it.get("tone")), "style": _nz(it.get("style")), "music": _nz(it.get("music")),
            "length_seconds": _int(it.get("length")), "song_title": _nz(it.get("song_title")),
            "lyrics": _nz(it.get("lyrics")), "recipients": recipients,
            "senders": it.get("senders") if isinstance(it.get("senders"), list) else [],
            "thumbnail_url": _nz(th.get("url")), "thumbnail_width": _int(th.get("width")),
            "thumbnail_height": _int(th.get("height")),
            "preview_video_url": _nz(vm.get("url")), "preview_video_width": _int(vm.get("width")),
            "preview_video_height": _int(vm.get("height")),
            "preview_video_duration_seconds": _float(vm.get("duration_seconds")),
            "preview_video_compressed_url": _nz(vm.get("compressed_url")),
            "preview_video_compressed_width": _int(vm.get("compressed_width")),
            "preview_video_compressed_height": _int(vm.get("compressed_height")),
            "preview_video_compressed_bytes": _int(vm.get("compressed_size_bytes")),
            "preview_video_thumbnail_url": _nz(vm.get("thumbnail_url")),
            "extra": {k: v for k, v in it.items() if k not in MUSIC_CARD_USED and v is not None}, "source": prov})
    cats = b.get("categories") if isinstance(b.get("categories"), list) else []
    out += _options([c for c in cats if isinstance(c, dict)], "category", "id", prov)
    return out


def _options(items: list[dict], group: str, key_field: str, prov: dict) -> list[dict]:
    out = []
    for n, it in enumerate(items):
        key = _nz(it.get(key_field))
        if key is None:
            continue
        out.append({"kind": "community_music_card_option", "option_id": make_id("music_card_option", group, key),
                    "group": group, "key": key, "label": _nz(it.get("label")), "hint": _nz(it.get("hint")),
                    "icon_key": _nz(it.get("icon_key")), "parent": _nz(it.get("parent")),
                    "thumbnail_url": _nz(_dict(it.get("thumbnail_media")).get("url")),
                    "categories": _strs(it.get("categories")), "position": n,
                    "extra": {k: v for k, v in it.items() if k not in OPTION_USED and v is not None},
                    "source": prov})
    return out


def parse_music_card_options(body: Any, group_path: str, prov: dict) -> list[dict]:
    """fnf-cms-api /music-cards-{styles|occasions|roles} -> community_music_card_option."""
    group = OPTION_GROUP.get(group_path)
    if group is None:
        return []
    return _options(_items_of(body), group, OPTION_KEY[group], prov)


def _media_keys(results: list[dict]) -> list[str]:
    """'media:<uuid>' of every output file (the HLS playlist has no file id of its own)."""
    keys = []
    for r in results:
        if r.get("name") == "hls":
            continue
        found = UUID_RE.findall(str(r.get("url") or "").split("?")[0])
        if found:
            keys.append(f"media:{found[-1].lower()}")
    return list(dict.fromkeys(keys))


def parse_showcase_job(job: dict, slug: str, movie: dict, mi: int, pos: int, sel: Selection, prov: dict) -> dict:
    params = job.get("params") if isinstance(job.get("params"), dict) else {}
    text, settings, extra, inputs = split_params(params)
    results = parse_results(job)
    gid = str(job["id"])
    return {
        "kind": "community_showcase_job", "generation_id": gid, "generation_key": f"job:{gid.lower()}",
        "media_keys": _media_keys(results), "showcase_slug": slug, "url": JOB_SHOWCASE_PAGES.get(slug),
        "movie_index": mi, "movie_position": pos, "movie_logo_url": _nz(movie.get("logo")),
        "movie_group_image_url": _nz(movie.get("group_image_url")),
        "job_set_type": _str(job.get("job_set_type")), "job_set_id": _str(job.get("job_set_id")),
        "parent_id": _str(job.get("job_set_parent_id")), "media_type": media_type_of(job),
        "status": _str(job.get("status")), "prompt": text["prompt"], "negative_prompt": text["negative_prompt"],
        "settings": settings, "params_extra": extra, "raw_params": params if sel.with_raw_params else None,
        "inputs": inputs, "results": results, "created_at": iso_ts(job.get("created_at")),
        "published_at": iso_ts(job.get("published_at")),
        "moderation": {k: _bool(job.get(k)) for k in ("ip_check_finished", "ip_detected",
                                                       "deepfake_consent_required", "can_bypass_ip")},
        "board_ids": job.get("board_ids") if isinstance(job.get("board_ids"), list) else [],
        "client_meta": job.get("job_set_client_meta") if isinstance(job.get("job_set_client_meta"), dict) else None,
        "meta_extra": _dict(job.get("meta")),
        "extra": {k: v for k, v in job.items() if k not in SHOWCASE_TOP and v is not None},
        "creator": (c := person_ref(job.get("user"), job.get("user_id"), sel)),
        "creator_uid_key": creator_uid_key(c["user_id"]), "source": prov}


def parse_job_showcase(body: Any, slug: str, sel: Selection, prov: dict) -> list[dict]:
    """fnf /jobs/showcase/{slug} -> community_showcase_job (one per job of every movie)."""
    movies = _dict(body).get("data")
    out = []
    for mi, m in enumerate(movies if isinstance(movies, list) else []):
        if not isinstance(m, dict):
            continue
        for pos, j in enumerate(m.get("jobs") or []):
            if isinstance(j, dict) and j.get("id"):
                out.append(parse_showcase_job(j, slug, m, mi, pos, sel, prov))
    return out


def parse_collection(body: Any, slug: str, prov: dict) -> list[dict]:
    """fnf /collections/{slug} -> community_collection (items = motion presets, joined to catalog_motion)."""
    b = _dict(body)
    if not slug or not isinstance(b.get("items"), list):
        return []
    items = []
    for n, it in enumerate(x for x in b["items"] if isinstance(x, dict)):
        m = _dict(it.get("media"))
        items.append({"position": n, "motion_id": _nz(it.get("id")), "name": _nz(it.get("name")),
                      "media_url": _nz(m.get("url")), "media_type": _nz(m.get("type")), "width": _int(m.get("width")),
                      "height": _int(m.get("height")), "priority": _int(it.get("priority")),
                      "tags": _strs(it.get("tags")), "params": _dict(it.get("params"))})
    return [{"kind": "community_collection", "collection_id": _nz(b.get("id")) or slug, "slug": slug,
             "url": f"{SITE}/collection/{slug}", "name": _nz(b.get("name")), "description": _nz(b.get("description")),
             "items_count": len(items), "items": items, "source": prov}]


def parse_explore_cards(body: Any, offset: int, prov: dict) -> list[dict]:
    """cms /cards -> community_explore_card (the inline blur placeholder is not stored)."""
    out = []
    for n, it in enumerate(_items_of(body)):
        if it.get("id") is None:
            continue
        m = _dict(it.get("media"))
        extra = {k: v for k, v in it.items() if k not in CARD_USED and v is not None}
        extra.update({f"media.{k}": v for k, v in m.items()
                      if k not in ("url", "type", "width", "height", "placeholder") and v is not None})
        out.append({"kind": "community_explore_card", "card_id": str(it["id"]), "position": offset + n,
                    "slug": _nz(it.get("slug")), "name": _nz(it.get("name")),
                    "description": _nz(it.get("description")), "href": _nz(it.get("href")),
                    "href_mobile": _nz(it.get("href_mobile")), "media_type": _nz(m.get("type")),
                    "media_url": _nz(m.get("url")), "width": _int(m.get("width")), "height": _int(m.get("height")),
                    "has_placeholder": bool(m.get("placeholder")), "extra": extra, "source": prov})
    return out


# ------------------------------------------------------------------ opt-in Feed hashtag categories
FEED_CATEGORY_USED = {"slug", "short_title", "title", "description", "hashtag", "post_count", "previews"}


def parse_feed_categories(body: Any, source_list: str, prov: dict) -> list[dict]:
    """fnf-community /feed/categories ({categories[]}) and /feed/ongoing ({items[]}) -> community_feed_category."""
    b = _dict(body)
    items = b.get("categories") if isinstance(b.get("categories"), list) else _items_of(b)
    out = []
    for n, it in enumerate(x for x in items if isinstance(x, dict)):
        key = _nz(it.get("slug")) or _nz(it.get("id")) or _nz(it.get("hashtag"))
        if key is None:
            continue
        out.append({"kind": "community_feed_category", "category_id": make_id("feed_category", source_list, key),
                    "source_list": source_list, "position": n, "slug": _nz(it.get("slug")),
                    "short_title": _nz(it.get("short_title")), "title": _nz(it.get("title")),
                    "description": _nz(it.get("description")), "hashtag": _nz(it.get("hashtag")),
                    "post_count": _int(it.get("post_count")),
                    "previews": [str(u) for u in it.get("previews") or [] if isinstance(u, str) and u.strip()],
                    "extra": {k: drop_viewer_flags(v) for k, v in it.items()
                              if k not in FEED_CATEGORY_USED and k not in VIEWER_FLAGS and v is not None},
                    "source": prov})
    return out
