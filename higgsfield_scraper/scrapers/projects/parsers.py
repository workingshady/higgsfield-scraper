"""Pure parsers: raw Envelope -> entity dicts (each with "kind"). No network, no Scrapy.

Dispatch is by `env.endpoint` (keys of endpoints.ENDPOINTS). Non-200 / non-JSON envelopes yield nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ...core.dataset import make_id
from . import endpoints as ep
from .options import Selection

# keys that identify a person; never copied into `extra` (they only appear as opt-in Person fields)
PROFILE_KEYS = {"id", "user_id", "username", "full_name", "display_name", "avatar_url", "headline", "location",
                "background_url", "external_link"}


# ------------------------------------------------------------------ small helpers
def iso(v: Any) -> Optional[str]:
    """Timestamp -> ISO-8601 UTC string; date-only strings are kept as-is; None stays None."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
    s = str(v).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> Optional[str]:
    return None if v in (None, "") else str(v)


def _list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _rest(d: dict, used: set[str] | tuple[str, ...], also_drop: set[str] = frozenset()) -> dict:
    return {k: v for k, v in d.items() if k not in used and k not in also_drop}


def author_key(user_id: Any) -> Optional[str]:
    return make_id("user", user_id) if user_id else None


def _img(obj: Any, fallback: Any = None) -> Optional[str]:
    """Media object ({url}|{original:{url}}|str) -> URL."""
    if isinstance(obj, str):
        return obj or _str(fallback)
    if isinstance(obj, dict):
        for k in ("url", "original_url"):
            if obj.get(k):
                return str(obj[k])
        orig = obj.get("original")
        if isinstance(orig, dict) and orig.get("url"):
            return str(orig["url"])
    return _str(fallback)


# ------------------------------------------------------------------ nested objects
PERSON_USED = {"id", "user_id", "username", "full_name", "display_name", "avatar_url", "headline", "location",
               "is_owner", "total_projects_views", "total_projects_likes", "followers_count", "badges"}


def person(d: Any, role: str, sel: Selection) -> Optional[dict]:
    if not isinstance(d, dict):
        return None
    uid = d.get("id") or d.get("user_id")
    p: dict[str, Any] = {
        "role": role,
        "author_key": author_key(uid),
        "is_owner": d.get("is_owner"),
        "total_projects_views": _int(d.get("total_projects_views")),
        "total_projects_likes": _int(d.get("total_projects_likes")),
        "followers_count": _int(d.get("followers_count")),
        "badges": [{"badge_id": _str(b.get("id")), "name": b.get("name"), "icon_url": b.get("icon_url"),
                    "description": b.get("description")} for b in _list(d.get("badges")) if isinstance(b, dict)],
        "extra": _rest(d, PERSON_USED, PROFILE_KEYS),
    }
    if sel.with_profiles:
        username = _str(d.get("username"))
        p.update(user_id=_str(uid), username=username, full_name=_str(d.get("full_name") or d.get("display_name")),
                 avatar_url=_str(d.get("avatar_url")), headline=_str(d.get("headline")),
                 location=_str(d.get("location")),
                 profile_url=f"{ep.SITE}/profile/{username}" if username else None)
    return p


MEDIA_USED = {"id", "type", "name", "url", "original_url", "preview_url", "thumbnail_url", "min_url", "download_url",
              "width", "height", "duration", "object_fit"}


def media(d: Any, role: str, position: int) -> Optional[dict]:
    if not isinstance(d, dict):
        return None
    return {"role": role, "position": position, "media_id": _str(d.get("id")), "type": d.get("type"),
            "name": d.get("name"), "url": d.get("url"), "original_url": d.get("original_url"),
            "preview_url": d.get("preview_url"), "thumbnail_url": d.get("thumbnail_url"), "min_url": d.get("min_url"),
            "download_url": d.get("download_url"), "width": _int(d.get("width")), "height": _int(d.get("height")),
            "duration_seconds": _float(d.get("duration")), "object_fit": d.get("object_fit"),
            "extra": _rest(d, MEDIA_USED)}


def best_video_url(m: dict) -> Optional[str]:
    """Downloadable video: original mp4 > preview mp4 > url unless it is an HLS playlist."""
    for k in ("original_url", "download_url", "preview_url"):
        if m.get(k):
            return m[k]
    u = m.get("url")
    return u if u and not str(u).split("?")[0].endswith(".m3u8") else None


# ------------------------------------------------------------------ publications
PUB_USED = {
    "publication_id", "project_id", "snapshot_folder_id", "original_folder_id", "root_folder_id", "name", "slug",
    "type", "state", "description", "duration_seconds", "is_ongoing", "is_open_source", "has_changes_since_publish",
    "show_prompts", "show_canvas", "is_discoverable", "is_featured", "is_higgsfield_featured", "is_talents_hub",
    "can_receive_audience_choice_votes", "featured_episode_id", "featured_episode_slug", "contest_key", "tags",
    "categories", "cover", "gallery_media", "trailer", "author_user_ids", "authors", "team", "views", "likes",
    "comments", "votes", "awards", "contest_badges", "stats", "created_at", "published_at", "project_updated_at",
    "final_submitted_at", "grant_awarded_at",
}


def _owner_username(item: dict) -> Optional[str]:
    authors = [a for a in _list(item.get("authors")) if isinstance(a, dict)]
    owner = next((a for a in authors if a.get("is_owner")), authors[0] if authors else None)
    if owner and owner.get("username"):
        return str(owner["username"])
    team = item.get("team")
    return str(team["username"]) if isinstance(team, dict) and team.get("username") else None


def parse_publication(item: dict, env, sel: Selection, *, kind: str = "projects_publication",
                      listing: Optional[str] = None) -> list[dict]:
    pid = _str(item.get("publication_id"))
    if not pid:
        return []
    src = env.provenance()
    cover = media(item.get("cover"), "cover", 0)
    trailer = media(item.get("trailer"), "trailer", 0)
    gallery = [m for i, g in enumerate(_list(item.get("gallery_media"))) if (m := media(g, "gallery", i))]
    all_media = ([cover] if cover else []) + gallery + ([trailer] if trailer else [])
    authors = [p for a in _list(item.get("authors")) if (p := person(a, "author", sel))]
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    stats_rest = _rest(stats, {"stack", "generations_count", "credits_spent", "free_generations", "size_bytes"})
    extra = _rest(item, PUB_USED)
    if stats_rest:
        extra["stats"] = stats_rest
    fe_slug = _str(item.get("featured_episode_slug"))
    is_series = item.get("type") == "series"
    pub = {
        "kind": kind,
        "publication_id": pid,
        "project_id": _str(item.get("project_id")),
        "snapshot_folder_id": _str(item.get("snapshot_folder_id")),
        "original_folder_id": _str(item.get("original_folder_id")),
        "root_folder_id": _str(item.get("root_folder_id")),
        "name": item.get("name"),
        "slug": _str(item.get("slug")),
        "type": item.get("type"),
        "state": item.get("state"),
        "description": item.get("description"),
        "duration_seconds": _float(item.get("duration_seconds")),
        **{k: item.get(k) for k in ("is_ongoing", "is_open_source", "has_changes_since_publish", "show_prompts",
                                    "show_canvas", "is_discoverable", "is_featured", "is_higgsfield_featured",
                                    "is_talents_hub", "can_receive_audience_choice_votes")},
        "featured_episode_id": _str(item.get("featured_episode_id")),
        "featured_episode_slug": fe_slug,
        "featured_episode_url": f"{ep.SITE}/original-series/{fe_slug}" if fe_slug else None,
        "contest_key": _str(item.get("contest_key")),
        "tags": [str(t) for t in _list(item.get("tags"))],
        "categories": [str(c.get("slug") if isinstance(c, dict) else c) for c in _list(item.get("categories"))],
        "cover_url": cover["url"] if cover else None,
        "trailer_url": (best_video_url(trailer) or trailer["url"]) if trailer else None,
        "media_count": len(all_media),
        "media": all_media,
        "episode_count": len(gallery) if is_series else None,
        "author_count": len(authors),
        "author_keys": [a["author_key"] for a in authors if a["author_key"]],
        "authors": authors,
        "team": person(item.get("team"), "team", sel),
        "views": _int(item.get("views")),
        "likes": _int(item.get("likes")),
        "comments": _int(item.get("comments")),
        "votes": _int(item.get("votes")),
        "awards": _list(item.get("awards")),
        "contest_badges": [{"contest_key": b.get("contest_key"), "list_key": b.get("list_key"),
                            "extra": _rest(b, {"contest_key", "list_key"})}
                           for b in _list(item.get("contest_badges")) if isinstance(b, dict)],
        "generations_count": _int(stats.get("generations_count")),
        "credits_spent": _float(stats.get("credits_spent")),
        "free_generations": _int(stats.get("free_generations")),
        "size_bytes": _int(stats.get("size_bytes")),
        "model_usage": [{"job_set_type": s.get("job_set_type"), "display_name": s.get("display_name"),
                         "count": _int(s.get("count")), "credits_spent": _float(s.get("credits_spent"))}
                        for s in _list(stats.get("stack")) if isinstance(s, dict)],
        **{k: iso(item.get(k)) for k in ("created_at", "published_at", "project_updated_at", "final_submitted_at",
                                         "grant_awarded_at")},
        "url": ep.publication_url(_owner_username(item), _str(item.get("slug"))) if sel.with_profiles else None,
        "listing": listing,
        "detail_fetched": kind == "projects_publication_detail",
        "source": src,
        "detail_source": src if kind == "projects_publication_detail" else None,
        "extra": extra,
    }
    out = [pub]
    if is_series:
        for i, m in enumerate(gallery):
            out.append({
                "kind": "projects_episode",
                "episode_id": f"{pid}:{m['media_id'] or i}",
                "publication_id": pid,
                "number": i + 1,
                "title": m["name"],
                "media_id": m["media_id"],
                "type": m["type"],
                "duration_seconds": m["duration_seconds"],
                "video_url": m["url"],
                "original_url": m["original_url"],
                "preview_url": m["preview_url"],
                "thumbnail_url": m["thumbnail_url"],
                "width": m["width"],
                "height": m["height"],
                "url": pub["url"],
                "source": src,
                "extra": m["extra"],
            })
    return out


def _listing_name(env) -> str:
    p = env.params or {}
    if env.endpoint == "projects_publications":
        name = "publications"
        if p.get("category"):
            name += f":category={p['category']}"
        if str(p.get("featured", "")).lower() == "true":
            name += ":featured"
        return name
    if env.endpoint == "projects_recommended":
        return f"recommended:{p.get('scope') or 'default'}"
    if env.endpoint == "projects_contest_entries":
        return f"entries:{p.get('contest_key')}:{p.get('tab')}"
    if env.endpoint == "projects_user_publications":                 # --users (key = sha256 of the handle)
        return f"user:{p.get('user_key')}"
    return env.endpoint


def parse_publication_list(env, sel: Selection) -> list[dict]:
    body = env.body
    items = body if isinstance(body, list) else _list(body.get("items"))
    listing = _listing_name(env)
    cursor = (env.params or {}).get("cursor")
    offset = _int(cursor) if cursor else 0          # offset cursors ("50"); score cursors -> None
    out: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        ents = parse_publication(item, env, sel, listing=listing)
        if not ents:
            continue
        out.extend(ents)
        pid = ents[0]["publication_id"]
        out.append({"kind": "projects_listing_entry", "entry_id": make_id(listing, pid), "listing": listing,
                    "publication_id": pid, "position": None if offset is None else offset + i,
                    "page_cursor": cursor, "index_in_page": i, "source": env.provenance()})
    return out


def parse_publication_detail(env, sel: Selection) -> list[dict]:
    if not isinstance(env.body, dict):
        return []
    return parse_publication(env.body, env, sel, kind="projects_publication_detail", listing="detail")


def parse_categories(env, sel: Selection) -> list[dict]:
    body = env.body
    items = body if isinstance(body, list) else _list(body.get("items"))
    return [{"kind": "projects_category", "slug": str(c["slug"]), "label": c.get("label"),
             "source": env.provenance(), "extra": _rest(c, {"slug", "label"})}
            for c in items if isinstance(c, dict) and c.get("slug")]


# ------------------------------------------------------------------ contests
CONTEST_USED = {
    "id", "slug", "title", "description", "contest_type", "status", "start_at", "end_at", "submissions_close_at",
    "rules_effective_at", "results_published", "preview_image", "preview_video", "logo_url", "redirect_url",
    "prize_pool", "submissions_count", "entries_count", "is_trending", "winner", "some_contestants", "judges",
    "settings", "rewards", "prizes", "theme_markdown", "details_markdown", "faq", "timeline", "winners",
    "submission_ids",
}
SETTINGS_KEYS = ("max_submissions", "new_project_per_submission", "allow_generation_move", "allow_generation_copy",
                 "source_clip_required")
REWARD_KEYS = ("first_place_credits", "second_place_credits", "third_place_credits", "honorable_mention_credits",
               "honorable_mentions_count", "style_champion_credits")


def status_group(status: Optional[str]) -> Optional[str]:
    if not status:
        return None
    return "closed" if status in ep.CONTEST_STATUS_GROUPS["closed"] else "open"


def _judge(j: dict, i: int, sel: Selection) -> dict:
    d = {"position": i, "display_name": j.get("display_name"), "description": j.get("description"),
         "extra": _rest(j, {"user_id", "display_name", "description", "avatar_url", "background_url",
                            "external_link"})}
    if sel.with_profiles:
        d.update(user_id=_str(j.get("user_id")), avatar_url=j.get("avatar_url"), background_url=j.get("background_url"),
                 external_link=j.get("external_link"))
    return d


def parse_contest(item: dict, env, sel: Selection, *, kind: str = "projects_contest") -> list[dict]:
    cid = _str(item.get("id"))
    if not cid:
        return []
    src = env.provenance()
    settings = item.get("settings") if isinstance(item.get("settings"), dict) else None
    rewards = item.get("rewards") if isinstance(item.get("rewards"), dict) else None
    prizes = [{"position": i, "label": p.get("label"), "type": p.get("type"), "value": _float(p.get("value")),
               "count": _int(p.get("count")), "extra": _rest(p, {"label", "type", "value", "count"})}
              for i, p in enumerate(_list(item.get("prizes"))) if isinstance(p, dict)]
    units = {p["type"] for p in prizes if p["type"]}
    contestants = [p for c in _list(item.get("some_contestants")) if (p := person(c, "contestant", sel))]
    winners = [w for w in _list(item.get("winners")) if isinstance(w, dict) and w.get("id")]
    detail = kind == "projects_contest_detail"
    c = {
        "kind": kind,
        "contest_id": cid,
        "slug": _str(item.get("slug")),
        "title": item.get("title"),
        "description": item.get("description"),
        "contest_type": item.get("contest_type"),
        "status": item.get("status"),
        "status_group": status_group(item.get("status")),
        **{k: iso(item.get(k)) for k in ("start_at", "end_at", "submissions_close_at", "rules_effective_at")},
        "results_published": item.get("results_published"),
        **{k: _str(item.get(k)) for k in ("preview_image", "preview_video", "logo_url", "redirect_url")},
        "prize_pool": _int(item.get("prize_pool")),
        "prize_pool_unit": units.pop() if len(units) == 1 else None,
        "submissions_count": _int(item.get("submissions_count")),
        "entries_count": _int(item.get("entries_count")),
        "is_trending": item.get("is_trending"),
        "winner": person(item.get("winner"), "winner", sel),
        "some_contestants_count": len(contestants),
        "some_contestants": contestants if sel.with_profiles else [],
        "judge_count": len(_list(item.get("judges"))),
        "judges": [_judge(j, i, sel) for i, j in enumerate(_list(item.get("judges"))) if isinstance(j, dict)],
        "settings": None if settings is None else {**{k: settings.get(k) for k in SETTINGS_KEYS},
                                                   "extra": _rest(settings, SETTINGS_KEYS)},
        "rewards": None if rewards is None else {**{k: _int(rewards.get(k)) for k in REWARD_KEYS},
                                                 "extra": _rest(rewards, REWARD_KEYS)},
        "prizes": prizes,
        "theme_markdown": item.get("theme_markdown"),
        "details_markdown": item.get("details_markdown"),
        "faq": [{"position": i, "question": f.get("question"), "answer": f.get("answer")}
                for i, f in enumerate(_list(item.get("faq"))) if isinstance(f, dict)],
        "timeline": item.get("timeline") if isinstance(item.get("timeline"), dict) else None,
        "winner_submission_ids": [str(w["id"]) for w in winners],
        "submission_ids": [str(s) for s in _list(item.get("submission_ids"))],
        "url": ep.contest_url(_str(item.get("slug"))),
        "detail_fetched": detail,
        "source": src,
        "detail_source": src if detail else None,
        "extra": _rest(item, CONTEST_USED),
    }
    out = [c]
    for w in winners:
        out.append(parse_submission(w, env, sel, listing="winners"))
    return out


def parse_contest_list(env, sel: Selection) -> list[dict]:
    out: list[dict] = []
    for item in _list(env.body.get("items")) if isinstance(env.body, dict) else []:
        if isinstance(item, dict):
            out.extend(parse_contest(item, env, sel))
    return out


def parse_contest_detail(env, sel: Selection) -> list[dict]:
    return parse_contest(env.body, env, sel, kind="projects_contest_detail") if isinstance(env.body, dict) else []


SUB_USED = {
    "id", "contest_id", "contest_slug", "type", "project_id", "title", "description", "thumbnail_id", "thumbnail_src",
    "video_id", "video_src", "video_preview_url", "winner_place", "honorable_mention", "style_champion",
    "shortlisted", "has_source_video", "has_assets", "clone_available", "likes_count", "dislikes_count",
    "views_count", "total_views", "social_media_metrics", "post_urls", "moderation_status", "suspend_reason",
    "winner_feedback", "winner_reviewer_name", "winner_reviewer_company", "badges", "user", "publication",
}


def parse_submission(item: dict, env, sel: Selection, *, listing: str = "submissions") -> dict:
    pub = item.get("publication") if isinstance(item.get("publication"), dict) else {}
    slug = _str(item.get("contest_slug"))
    sid = str(item["id"])
    posts = [str(u) for u in _list(item.get("post_urls"))]
    return {
        "kind": "projects_contest_submission",
        "submission_id": sid,
        "contest_id": _str(item.get("contest_id")),
        "contest_slug": slug,
        "type": item.get("type"),
        "project_id": _str(item.get("project_id")),
        "title": item.get("title"),
        "description": item.get("description"),
        "thumbnail_id": _str(item.get("thumbnail_id")),
        "thumbnail_url": _str(item.get("thumbnail_src")),
        "video_id": _str(item.get("video_id")),
        "video_url": _str(item.get("video_src")),
        "video_preview_url": _str(item.get("video_preview_url")),
        "winner_place": _str(item.get("winner_place")),
        **{k: item.get(k) for k in ("honorable_mention", "style_champion", "shortlisted", "has_source_video",
                                    "has_assets", "clone_available", "moderation_status", "suspend_reason",
                                    "winner_feedback", "winner_reviewer_name", "winner_reviewer_company")},
        **{k: _int(item.get(k)) for k in ("likes_count", "dislikes_count", "views_count", "total_views")},
        "social_media_metrics": item.get("social_media_metrics") if isinstance(item.get("social_media_metrics"), dict)
        else {},
        "post_url_count": len(posts),
        "post_urls": posts if sel.with_profiles else [],
        "badges": _list(item.get("badges")),
        "user": person(item.get("user"), "submitter", sel),
        "publication_id": _str(pub.get("publication_id")),
        "publication_slug": _str(pub.get("slug")),
        "publication_url": ep.publication_url(_str(pub.get("username")), _str(pub.get("slug")))
        if sel.with_profiles else None,
        "listing": listing,
        "url": ep.submission_url(slug, sid),
        "source": env.provenance(),
        "extra": _rest(item, SUB_USED),
    }


def parse_submissions(env, sel: Selection) -> list[dict]:
    items = _list(env.body.get("items")) if isinstance(env.body, dict) else []
    return [parse_submission(i, env, sel) for i in items if isinstance(i, dict) and i.get("id")]


# ------------------------------------------------------------------ original series (fnf-series, public)
SERIES_USED = {
    "id", "slug", "name", "short_description", "full_description", "author_type", "author", "is_series", "state",
    "portrait", "portrait_url", "landscape", "landscape_url", "background", "background_url", "logo", "logo_url",
    "trailer", "trailer_url", "project_url", "project_publication_id", "duration_seconds", "engagement",
    "categories", "project_banner_images", "tags", "vote_count", "subscriber_count", "episodes",
}
EPISODE_USED = {"id", "slug", "title", "description", "thumbnail", "thumbnail_url", "video", "video_url",
                "duration_seconds", "is_locked", "is_adults_only"}


def parse_series(item: dict, env, sel: Selection, *, detail: bool = False) -> list[dict]:
    sid = _str(item.get("id"))
    if not sid:
        return []
    src = env.provenance()
    slug = _str(item.get("slug"))
    eng = item.get("engagement") if isinstance(item.get("engagement"), dict) else {}
    trailer = item.get("trailer")
    episodes = [e for e in _list(item.get("episodes")) if isinstance(e, dict)]
    logo = item.get("logo")
    s = {
        "kind": "projects_series",
        "series_id": sid,
        "slug": slug,
        "title": item.get("name"),
        "short_description": item.get("short_description"),
        "full_description": item.get("full_description"),
        "author_type": item.get("author_type"),
        "author": person(item.get("author"), "series_author", sel),
        "is_series": item.get("is_series"),
        "state": item.get("state"),
        "portrait_url": _img(item.get("portrait"), item.get("portrait_url")),
        "landscape_url": _img(item.get("landscape"), item.get("landscape_url")),
        "background_url": _img(item.get("background"), item.get("background_url")),
        "logo_url": _img(logo.get("original") if isinstance(logo, dict) else logo, item.get("logo_url")),
        "trailer_url": _img(trailer, item.get("trailer_url")),
        "trailer_hls_url": _str((trailer.get("hls") or {}).get("url")) if isinstance(trailer, dict)
        and isinstance(trailer.get("hls"), dict) else None,
        "project_url": _str(item.get("project_url")),
        "project_publication_id": _str(item.get("project_publication_id")),
        "duration_seconds": _float(item.get("duration_seconds")),
        "likes": _int(eng.get("like_count")),
        "views": _int(eng.get("view_count")),
        "comments": _int(eng.get("comment_count")),
        "vote_count": _int(item.get("vote_count")),
        "subscriber_count": _int(item.get("subscriber_count")),
        "categories": [str(c.get("slug") if isinstance(c, dict) else c) for c in _list(item.get("categories"))],
        "tags": _list(item.get("tags")),
        "banner_images": [u for b in _list(item.get("project_banner_images")) if (u := _img(b))],
        "episode_count": len(episodes) if "episodes" in item else None,
        "url": ep.series_url(slug),
        "detail_fetched": detail,
        "source": src,
        "extra": _rest(item, SERIES_USED),
    }
    out = [s]
    for i, e in enumerate(episodes):
        video = e.get("video")
        hls = (video.get("hls") or {}).get("url") if isinstance(video, dict) and isinstance(video.get("hls"), dict) \
            else None
        out.append({
            "kind": "projects_episode",
            "episode_id": f"{sid}:{e.get('id') or i}",
            "series_id": sid,
            "series_slug": slug,
            "number": i + 1,
            "slug": _str(e.get("slug")),
            "title": e.get("title"),
            "description": e.get("description"),
            "media_id": _str(e.get("id")),
            "type": "video",
            "duration_seconds": _float(e.get("duration_seconds")),
            "video_url": None if e.get("is_locked") else (hls or _img(video, e.get("video_url"))),
            "original_url": None if e.get("is_locked") else _img(video, e.get("video_url")),
            "thumbnail_url": _img(e.get("thumbnail"), e.get("thumbnail_url")),
            "is_locked": e.get("is_locked"),
            "is_adults_only": e.get("is_adults_only"),
            "url": ep.series_url(slug, _str(e.get("slug"))),
            "source": src,
            "extra": _rest(e, EPISODE_USED),
        })
    return out


def parse_series_list(env, sel: Selection) -> list[dict]:
    body = env.body
    items = body if isinstance(body, list) else _list(body.get("items")) if isinstance(body, dict) else []
    return [e for i in items if isinstance(i, dict) for e in parse_series(i, env, sel)]


def parse_series_detail(env, sel: Selection) -> list[dict]:
    return parse_series(env.body, env, sel, detail=True) if isinstance(env.body, dict) else []


# ------------------------------------------------------------------ dispatch
PARSERS: dict[str, Callable[[Any, Selection], list[dict]]] = {
    "projects_publications": parse_publication_list,
    "projects_recommended": parse_publication_list,
    "projects_contest_entries": parse_publication_list,
    "projects_publication_detail": parse_publication_detail,
    "projects_categories": parse_categories,
    "projects_contests": parse_contest_list,
    "projects_contest_detail": parse_contest_detail,
    "projects_contest_submissions": parse_submissions,
    "projects_series": parse_series_list,
    "projects_series_detail": parse_series_detail,
    "projects_series_public": parse_series_list,          # --public-series: same body, same entities
    "projects_series_public_detail": parse_series_detail,
}


def parse_publication_detail_nested(env, sel: Selection) -> list[dict]:
    """Detail + (with --with-project-stats) the project stats and stack rows of the page."""
    out = parse_publication_detail(env, sel)
    if sel.with_project_stats and isinstance(env.body, dict):
        from .nested import parse_stats
        out += parse_stats(env.body, env)
    return out


def _nested_parsers() -> dict[str, Callable[[Any, Selection], list[dict]]]:
    from . import nested as n
    return {
        "projects_contest_by_slug": parse_contest_detail,      # --contest <slug>: same body as /contests/by-id/{id}
        "projects_folder": n.parse_folder,
        "projects_folder_children": n.parse_folder_children,
        "projects_folder_items": n.parse_folder_items,
        "projects_brief": n.parse_brief,
        "projects_comments": n.parse_comments,
        "projects_related": n.parse_related,
        "projects_user_publications": n.parse_user_publications,
    }


def parse_envelope(env, sel: Selection) -> list[dict]:
    if env.endpoint == "projects_publication_detail" and getattr(sel, "with_project_stats", False):
        fn = parse_publication_detail_nested
    else:
        fn = PARSERS.get(env.endpoint) or _nested_parsers().get(env.endpoint)
    if fn is None or not env.ok:
        return []
    return fn(env, sel)


def keep(entity: dict, sel: Selection) -> bool:
    """Output filters (also applied by `normalize`)."""
    if entity.get("kind") in ("projects_contest", "projects_contest_detail"):
        if entity.get("status") and entity["status"] not in sel.statuses:
            return False
        if entity.get("contest_type") and entity["contest_type"] not in sel.contest_types:
            return False
    return True
