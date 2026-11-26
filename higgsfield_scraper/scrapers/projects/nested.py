"""Pure parsers of the nested project data (opt-in `--with-project-*` flags): folders, assets, brief, stats/stack,
comments and related projects of a project publication. No network, no Scrapy.

Context that is not in a response body (publication id, root folder, the author's `show_prompts` choice) travels
in the envelope params as request *labels* (see spider `_nested_requests`), so `normalize` re-parses identically.
Every entity carries `source` (Provenance) plus the flat `source_url`, `scraped_at` and `schema_version`.
See docs/scrapers/projects.md "Nested data model".
"""
from __future__ import annotations

import base64
import dataclasses
import re
from typing import Any, Optional

from ...core.dataset import make_id
from ...core.privacy import creator_uid_key
from .options import Selection
from .parsers import (_float, _int, _list, _rest, _str, author_key, best_video_url, iso, media,
                      parse_publication_list, person)

NESTED_SCHEMA_VERSION = 1
ARCHIVE_REDACTED = "[redacted]"
USER_PATH_RE = re.compile(r"/user/[^/?#]+/")
PROMPT_KEYS = ("prompt", "negative_prompt", "enhanced_prompt", "original_prompt", "user_prompt", "system_prompt")
PERSONAL_EXTRA = {"user", "user_id", "owner_username", "workspace", "members", "username", "full_name", "avatar_url"}
# UI label overrides of the stack (JS mv(): gv={"Cinematic Studio 3.5 Video":"Cinematic Studio"})
STACK_LABELS = {"Cinematic Studio 3.5 Video": "Cinematic Studio"}


def _base(env, kind: str) -> dict[str, Any]:
    src = env.provenance()
    return {"kind": kind, "source": src, "source_url": env.url, "scraped_at": src["fetched_at"],
            "schema_version": NESTED_SCHEMA_VERSION}


def _label(env, key: str) -> Optional[str]:
    v = (env.params or {}).get(key)
    return None if v in (None, "", "None") else str(v)


def _prompts_visible(env) -> bool:
    """The author's show_prompts flag, recorded on the request. Unknown -> hidden (privacy-safe default)."""
    return str((env.params or {}).get("show_prompts", "")).lower() == "true"


def _owner(d: dict, sel: Selection, prefix: str) -> dict[str, Any]:
    user = d.get("user") if isinstance(d.get("user"), dict) else {}
    uid = _str(d.get("user_id") or user.get("id"))
    out: dict[str, Any] = {f"{prefix}_key": author_key(uid), "creator_uid_key": creator_uid_key(uid) if uid else None}
    if sel.with_profiles:
        out[f"{prefix}_user_id"] = uid
        out[f"{prefix}_username"] = _str(d.get("owner_username") or user.get("username"))
    return out


# ------------------------------------------------------------------ folders
FOLDER_USED = {
    "id", "parent_id", "root_folder_id", "is_root", "path", "name", "slug", "description", "emoji", "color",
    "surface", "kind", "count", "subfolders_count", "views_count", "copies_count", "access_mode",
    "link_access_level", "is_snapshot", "is_discoverable", "locked", "preview_url", "cover_image_url", "contest_key",
    "contest_id", "project_id", "created_at", "updated_at", "recent_jobs", "publication", "archived_at", "hidden_at",
}


def parse_folder_obj(d: dict, env, sel: Selection, *, position: Optional[int]) -> Optional[dict]:
    fid = _str(d.get("id"))
    if not fid:
        return None
    path = [p for p in str(d.get("path") or "").split("/") if p]
    pub = d.get("publication") if isinstance(d.get("publication"), dict) else {}
    return {
        **_base(env, "projects_folder"),
        "folder_id": fid,
        "publication_id": _label(env, "publication_id"),
        "root_folder_id": _str(d.get("root_folder_id")) or _label(env, "folder_id"),
        "parent_id": _str(d.get("parent_id")),
        "is_root": d.get("is_root"),
        "depth": max(0, len(path) - 1) if path else None,
        "position": position,
        "name": d.get("name"),
        "slug": _str(d.get("slug")),
        "description": d.get("description"),
        "emoji": d.get("emoji"),
        "color": d.get("color"),
        "surface": d.get("surface"),
        "folder_kind": d.get("kind"),
        "asset_count": _int(d.get("count")),
        "subfolders_count": _int(d.get("subfolders_count")),
        "views_count": _int(d.get("views_count")),
        "copies_count": _int(d.get("copies_count")),
        "access_mode": d.get("access_mode"),
        "link_access_level": d.get("link_access_level"),
        "is_snapshot": d.get("is_snapshot"),
        "is_discoverable": d.get("is_discoverable"),
        "locked": d.get("locked"),
        "preview_url": _str(d.get("preview_url")),
        "cover_image_url": _str(d.get("cover_image_url")),
        "contest_key": _str(d.get("contest_key")),
        "contest_id": _str(d.get("contest_id")),
        "project_id": _str(d.get("project_id")),
        "publication_state": pub.get("state"),
        "created_at": iso(d.get("created_at")),
        "updated_at": iso(d.get("updated_at")),
        "archived_at": iso(d.get("archived_at")),
        "hidden_at": iso(d.get("hidden_at")),
        "path": _str(d.get("path")),
        **_owner(d, sel, "owner"),
        "extra": _rest(d, FOLDER_USED, PERSONAL_EXTRA),
    }


def parse_folder(env, sel: Selection) -> list[dict]:
    f = parse_folder_obj(env.body, env, sel, position=None) if isinstance(env.body, dict) else None
    return [f] if f else []


def parse_folder_children(env, sel: Selection) -> list[dict]:
    items = _list(env.body.get("items")) if isinstance(env.body, dict) else []
    offset = _int(_label(env, "offset")) or 0
    return [f for i, d in enumerate(items) if isinstance(d, dict)
            and (f := parse_folder_obj(d, env, sel, position=offset + i))]


# ------------------------------------------------------------------ assets
ITEM_USED = {
    "id", "status", "type", "results", "result", "job_set_id", "job_set_type", "job_set_parent_id", "params", "meta",
    "created_at", "uploaded_at", "folder_job_id", "folder_id", "comments_count", "review_status", "name", "filename",
    "url", "download_url", "waveform_url", "duration", "extension", "size_bytes", "prompt", "width", "height",
    "thumbnail_url", "folder_ids", "board_ids", "published_at", "is_favourite", "is_viewed", "has_unresolved_comment",
}


EXT_MEDIA = {**dict.fromkeys(("png", "jpg", "jpeg", "webp", "gif", "avif", "heic"), "image"),
             **dict.fromkeys(("mp4", "mov", "webm", "m4v", "mkv"), "video"),
             **dict.fromkeys(("wav", "mp3", "m4a", "aac", "flac", "ogg"), "audio")}
UPLOAD_MEDIA = {"media_input": "image", "image_input": "image", "video_input": "video", "audio_input": "audio"}


def _media_type(v: Any, ext: Any = None) -> Optional[str]:
    """image | video | audio from results.raw.type, the upload type (media_input = image) or the extension."""
    s = str(v or "")
    for t in ("video", "image", "audio"):
        if t in s and s not in UPLOAD_MEDIA:
            return t
    if ext and str(ext).lower().lstrip(".") in EXT_MEDIA:
        return EXT_MEDIA[str(ext).lower().lstrip(".")]
    return UPLOAD_MEDIA.get(s)                     # e.g. an in-progress job without results -> None


def _variants(results: Any) -> list[dict]:
    out = []
    if isinstance(results, dict):
        for name, v in results.items():
            if isinstance(v, dict) and v.get("url"):
                out.append({"variant": name, "type": v.get("type"), "url": v.get("url"),
                            "thumbnail_url": _str(v.get("thumbnail_url")),
                            "extra": _rest(v, {"type", "url", "thumbnail_url"})})
    return out


def _inputs(params: dict) -> list[dict]:
    out = []
    for i, m in enumerate(_list(params.get("medias"))):
        if not isinstance(m, dict):
            continue
        data = m.get("data") if isinstance(m.get("data"), dict) else {}
        out.append({"position": i, "role": m.get("role"), "media_id": _str(data.get("id")),
                    "type": data.get("type"), "url": _str(data.get("url"))})
    return out


def parse_asset(item: dict, env, sel: Selection, *, position: int) -> Optional[dict]:
    itype = _str(item.get("type"))
    payload = item.get("job") if isinstance(item.get("job"), dict) else item.get("input")
    if not isinstance(payload, dict):
        payload = next((v for k, v in item.items() if k != "type" and isinstance(v, dict) and v.get("id")), None)
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    aid = str(payload["id"])
    root = _label(env, "folder_id")
    visible = _prompts_visible(env)
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
    raw = results.get("raw") if isinstance(results.get("raw"), dict) else {}
    mini = results.get("min") if isinstance(results.get("min"), dict) else {}
    hls = results.get("hls") if isinstance(results.get("hls"), dict) else {}
    h264 = results.get("h264") if isinstance(results.get("h264"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    prompt = params.get("prompt") if "prompt" in params else payload.get("prompt")
    shown_params = params if visible else {k: v for k, v in params.items() if k not in PROMPT_KEYS}
    url = _str(raw.get("url")) or _str(payload.get("url"))
    url_ext = (url or "").split("?")[0].rsplit(".", 1)[-1] if url and "." in url.rsplit("/", 1)[-1] else None
    mtype = _media_type(raw.get("type") or payload.get("type") or itype, payload.get("extension") or url_ext)
    folder_id = _str(payload.get("folder_id"))
    return {
        **_base(env, "projects_asset"),
        "placement_id": _str(payload.get("folder_job_id")) or make_id(root, itype, aid, folder_id),
        "asset_id": aid,
        "item_type": itype,
        "position": position,
        "in_all_assets": _label(env, "items_folder") is None,
        "publication_id": _label(env, "publication_id"),
        "root_folder_id": root,
        "folder_id": folder_id,
        "folder_name": None,                     # filled by build_dataset from the folders
        "folder_path": None,
        "status": payload.get("status"),
        "media_type": mtype,
        "job_set_id": _str(payload.get("job_set_id")),
        "job_set_type": _str(payload.get("job_set_type")),
        "job_set_parent_id": _str(payload.get("job_set_parent_id")),
        "model_name": None,                      # filled by build_dataset from the stack (display_name)
        "prompts_visible": visible,
        "prompt": (_str(prompt) if visible else None),
        "has_prompt": bool(_str(prompt)),
        "params": shown_params,
        "aspect_ratio": _str(params.get("aspect_ratio")),
        "resolution": _str(params.get("resolution") or params.get("quality")),
        "width": _int(params.get("width") if params.get("width") is not None else payload.get("width")),
        "height": _int(params.get("height") if params.get("height") is not None else payload.get("height")),
        "duration_seconds": _float(params.get("duration") if params.get("duration") is not None
                                   else payload.get("duration")),
        "seed": _int(params.get("seed")),
        "batch_size": _int(params.get("batch_size")),
        "input_media": _inputs(params),
        "url": url,
        "min_url": _str(mini.get("url")),
        "thumbnail_url": _str(raw.get("thumbnail_url") or mini.get("thumbnail_url") or payload.get("thumbnail_url")),
        "hls_url": _str(hls.get("url")),
        "h264_url": _str(h264.get("url")),
        "download_url": _str(payload.get("download_url")),
        "waveform_url": _str(payload.get("waveform_url")),
        "variants": _variants(results),
        "filename": _str(payload.get("filename") or payload.get("name")),
        "extension": _str(payload.get("extension")),
        "size_bytes": _int(payload.get("size_bytes")),
        "cost_raw": _str(meta.get("cost")),
        "comments_count": _int(payload.get("comments_count")),
        "review_status": _str(payload.get("review_status")),
        "created_at": iso(payload.get("created_at")),
        "uploaded_at": iso(payload.get("uploaded_at")),
        **_owner(payload, sel, "creator"),
        "extra": {**_rest(payload, ITEM_USED, PERSONAL_EXTRA),
                  **({"meta": _rest(meta, {"cost"})} if _rest(meta, {"cost"}) else {})},
    }


def parse_folder_items(env, sel: Selection) -> list[dict]:
    items = _list(env.body.get("items")) if isinstance(env.body, dict) else []
    offset = _int(_label(env, "offset")) or 0
    return [a for i, d in enumerate(items) if isinstance(d, dict)
            and (a := parse_asset(d, env, sel, position=offset + i))]


# ------------------------------------------------------------------ brief
def parse_brief(env, sel: Selection) -> list[dict]:
    """Body built by the spider from the binary snapshot: {snapshot_b64, bytes, updated_at_ms, content_type}."""
    from .brief import brief_markdown
    from .yjs import YjsDecodeError
    body = env.body if isinstance(env.body, dict) else {}
    if "snapshot_b64" not in body:
        return []
    data = base64.b64decode(body.get("snapshot_b64") or "")
    md, info, error = None, {}, None
    if data:
        try:
            md, info = brief_markdown(data)
        except (YjsDecodeError, ValueError, IndexError) as e:     # keep the raw snapshot; report the failure
            error = f"{type(e).__name__}: {e}"
    ms = _int(body.get("updated_at_ms"))
    fid = _label(env, "folder_id")
    return [{
        **_base(env, "projects_brief"),
        "brief_id": fid,
        "publication_id": _label(env, "publication_id"),
        "folder_id": fid,
        "publication_slug": _label(env, "slug"),
        "title": info.get("title"),
        "has_content": bool(md and md.strip()),
        "markdown": md if md and md.strip() else None,
        "updated_at": iso(ms / 1000) if ms else None,
        "snapshot_bytes": len(data),
        "block_count": info.get("block_count", 0),
        "word_count": info.get("word_count", 0),
        "node_types": info.get("node_types", {}),
        "links": info.get("links", []),
        "referenced_ids": info.get("referenced_ids", []),
        "referenced_asset_ids": [],              # filled by build_dataset (ids that are assets of the project)
        "file": None,                            # filled by write_outputs: briefs/<slug>.md
        "decode_error": error,
    }]


# ------------------------------------------------------------------ stats (from the publication detail)
def _largest_remainder_tenths(shares: list[float]) -> list[float]:
    """JS jie(): round shares to 0.1 so that they sum to the rounded total (largest remainder first)."""
    total = sum(shares)
    if total <= 0:
        return [0.0 for _ in shares]
    rows = [{"i": i, "t": int(s * 10 // 1), "r": s * 10 - int(s * 10 // 1)} for i, s in enumerate(shares)]
    left = round(total * 10) - sum(r["t"] for r in rows)
    for r in sorted(rows, key=lambda r: -r["r"]):
        if left <= 0:
            break
        r["t"] += 1
        left -= 1
    out = [0.0] * len(shares)
    for r in rows:
        out[r["i"]] = r["t"] / 10
    return out


def parse_stats(item: dict, env) -> list[dict]:
    pid = _str(item.get("publication_id"))
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else None
    if not pid or stats is None:
        return []
    stack = [s for s in _list(stats.get("stack")) if isinstance(s, dict)]
    shown = [s for s in stack if (_int(s.get("count")) or 0) > 0 or (_float(s.get("credits_spent")) or 0) > 0]
    total = sum(_int(s.get("count")) or 0 for s in shown)
    shares = [(_int(s.get("count")) or 0) / total * 100 if total else 0.0 for s in shown]
    percents = _largest_remainder_tenths(shares)
    by_id = {id(s): (sh, pc) for s, sh, pc in zip(shown, shares, percents)}
    size = _int(stats.get("size_bytes"))
    out = [{
        **_base(env, "projects_stats"),
        "publication_id": pid,
        "generations_count": _int(stats.get("generations_count")),
        "free_generations": _int(stats.get("free_generations")),
        "credits_spent": _float(stats.get("credits_spent")),
        "size_bytes": size,
        "size_mb": round(size / 1_000_000, 1) if size is not None else None,
        "model_count": len(shown),
        "stack_generations": total,
        "extra": _rest(stats, {"stack", "generations_count", "free_generations", "credits_spent", "size_bytes"}),
    }]
    for i, s in enumerate(stack):
        display = _str(s.get("display_name"))
        if display == ARCHIVE_REDACTED:      # core privacy redaction lists display_name: raw/ (normalize) has no names
            display = None
        share, pct = by_id.get(id(s), (None, None))
        out.append({
            **_base(env, "projects_stack_item"),
            "stack_item_id": make_id(pid, s.get("job_set_type"), display),
            "publication_id": pid,
            "position": i,
            "job_set_type": _str(s.get("job_set_type")),
            "display_name": display,
            "label": STACK_LABELS.get((display or "").strip(), (display or "").strip() or _str(s.get("job_set_type"))),
            "count": _int(s.get("count")),
            "credits_spent": _float(s.get("credits_spent")),
            "shown_in_ui": share is not None,
            "share": share,
            "percent": pct,
            "extra": _rest(s, {"job_set_type", "display_name", "count", "credits_spent"}),
        })
    return out


# ------------------------------------------------------------------ comments
COMMENT_USED = {"id", "entity_type", "publication_id", "parent_id", "user_id", "content", "author", "created_at",
                "updated_at", "like_count", "dislike_count", "reply_count", "reactions", "mentions", "is_mine"}


def parse_comments(env, sel: Selection) -> list[dict]:
    """fnf-community `/entities/project_publication/{id}/comments` -> {items, total, next_cursor}. The author is a
    Person (pseudonymous author_key; username, name, avatar, headline only with --with-profiles)."""
    body = env.body if isinstance(env.body, dict) else {}
    out = []
    pid = _label(env, "publication_id")
    parent = _label(env, "parent_id")
    for c in _list(body.get("items")):
        if not isinstance(c, dict) or not c.get("id"):
            continue
        author = dict(c.get("author")) if isinstance(c.get("author"), dict) else {"id": c.get("user_id")}
        author.setdefault("id", c.get("user_id"))
        if isinstance(author.get("badge"), str):          # comments carry a single badge name; Person wants a list
            b = author.pop("badge")
            author["badges"] = [{"name": b}] if b else []
        out.append({
            **_base(env, "projects_comment"),
            "comment_id": str(c["id"]),
            "publication_id": _str(c.get("publication_id")) or pid,
            "thread_type": _str(c.get("entity_type")),
            "parent_id": _str(c.get("parent_id")) or parent,
            "is_reply": bool(_str(c.get("parent_id")) or parent),
            "text": c.get("content"),
            "created_at": iso(c.get("created_at")),
            "updated_at": iso(c.get("updated_at")),
            "likes": _int(c.get("like_count")),
            "dislikes": _int(c.get("dislike_count")),
            "reply_count": _int(c.get("reply_count")),
            "reactions": [{"emoji": _str(r.get("emoji")), "count": _int(r.get("count"))}
                          for r in _list(c.get("reactions")) if isinstance(r, dict)],
            "mention_count": len(_list(c.get("mentions"))),
            "author": person(author, "commenter", sel),
            "is_by_author": None,                         # filled by build_dataset (author is a project author)
            "extra": _rest(c, COMMENT_USED),
        })
    return out


# ------------------------------------------------------------------ related projects
def parse_related(env, sel: Selection) -> list[dict]:
    body = env.body if isinstance(env.body, dict) else {}
    pid = _label(env, "publication_id")
    scope = _label(env, "scope")
    feed = body.get("feed") if isinstance(body.get("feed"), dict) else {}
    out = []
    pos = 0
    for item in _list(body.get("items")):
        if not isinstance(item, dict) or not item.get("publication_id"):
            continue
        rid = str(item["publication_id"])
        if rid == pid:                                     # the page filters the current project out
            continue
        authors = [p for a in _list(item.get("authors")) if (p := person(a, "author", sel))]
        cover = item.get("cover") if isinstance(item.get("cover"), dict) else {}
        trailer = media(item.get("trailer"), "trailer", 0)
        gallery = [m for i, g in enumerate(_list(item.get("gallery_media"))) if (m := media(g, "gallery", i))]
        out.append({
            **_base(env, "projects_related"),
            "related_id": make_id(pid, rid, scope),
            "publication_id": pid,
            "related_publication_id": rid,
            "position": pos,
            "scope": scope,
            "name": item.get("name"),
            "slug": _str(item.get("slug")),
            "type": item.get("type"),
            "contest_key": _str(item.get("contest_key")),
            "views": _int(item.get("views")),
            "likes": _int(item.get("likes")),
            "comments": _int(item.get("comments")),
            "cover_url": _str(cover.get("url")),
            "author_keys": [a["author_key"] for a in authors if a["author_key"]],
            "feed_source": _str(feed.get("source")),
            # card media + text (COMPLETENESS #6)
            "title": item.get("name"),
            "description": item.get("description"),
            "duration_seconds": _float(item.get("duration_seconds")),
            "tags": [str(t) for t in _list(item.get("tags"))],
            "show_prompts": item.get("show_prompts"),
            "created_at": iso(item.get("created_at")),
            "cover_width": _int(cover.get("width")),
            "cover_height": _int(cover.get("height")),
            "trailer_url": (best_video_url(trailer) or trailer["url"]) if trailer else None,
            "trailer_thumbnail_url": trailer["thumbnail_url"] if trailer else None,
            "trailer_width": trailer["width"] if trailer else None,
            "trailer_height": trailer["height"] if trailer else None,
            "trailer_duration_seconds": trailer["duration_seconds"] if trailer else None,
            "gallery_media": [{"position": m["position"], "media_id": m["media_id"], "type": m["type"],
                               "name": m["name"], "url": m["url"], "original_url": m["original_url"],
                               "preview_url": m["preview_url"], "thumbnail_url": m["thumbnail_url"],
                               "download_url": m["download_url"], "width": m["width"], "height": m["height"],
                               "duration": m["duration_seconds"]} for m in gallery],
            "team": person(item.get("team"), "team", sel),
            "creator_uid_keys": [a["creator_uid_key"] for a in authors if a["creator_uid_key"]],
        })
        pos += 1
    return out


# ------------------------------------------------------------------ user projects (profile "Projects" tab)
def parse_user_publications(env, sel: Selection) -> list[dict]:
    """`/user/{handle}/v2/publications` -> {publications, has_more, cursor, total}; items are publication-shaped.
    The handle is an input: without --with-profiles it is replaced by its key in the rows' source URL."""
    body = env.body if isinstance(env.body, dict) else {}
    pubs = [p for p in _list(body.get("publications")) if isinstance(p, dict)
            and p.get("publication_type") in (None, "project_publication", "project")]
    url = env.url
    if not sel.with_profiles and _label(env, "user_key"):
        url = USER_PATH_RE.sub(f"/user/key:{_label(env, 'user_key')}/", url)
    return parse_publication_list(dataclasses.replace(env, url=url, body={"items": pubs}), sel)
