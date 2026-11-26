"""Pure parsers: Envelope -> entity dicts (each with "kind"). No network, no Scrapy."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlsplit

from ...core.privacy import creator_uid_key
from ...schemas.common import make_id
from .endpoints import MOTION_DETAIL_KIND, PAGE_KIND, PLACEHOLDER_URL, SOURCE_BY_ENDPOINT, Source

LIST_KEYS = ("items", "presets", "data", "results", "categories", "styles", "motions", "settings")
EXT_TYPES = {
    "image": ("webp", "png", "jpg", "jpeg", "gif", "avif", "svg", "bmp", "heic"),
    "video": ("mp4", "webm", "mov", "m4v", "mkv"),
    "audio": ("mp3", "wav", "m4a", "ogg", "aac", "flac", "opus"),
    "json": ("json",),
}
MEDIA_KEYS = {"url", "type", "width", "height", "placeholder", "optimized_url", "thumbnail_url", "main_url",
              "main_width", "main_height", "duration", "duration_ms", "content_type"}


# ------------------------------------------------------------------ helpers
def media_type(url: Optional[str], api_type: Optional[str] = None, content_type: Optional[str] = None) -> str:
    if content_type:
        major = content_type.split("/")[0]
        if major in ("image", "video", "audio"):
            return major
        if "json" in content_type:
            return "json"
    ext = urlsplit(url or "").path.rsplit(".", 1)[-1].lower() if "." in urlsplit(url or "").path else ""
    for t, exts in EXT_TYPES.items():
        if ext in exts:
            return t
    if api_type in ("video",):
        return "video"
    if api_type in ("static", "image", "animated"):
        return "image"
    if api_type in ("audio",):
        return "audio"
    return "other"


def _usable(url: Any) -> bool:
    return isinstance(url, str) and url.startswith("http") and url != PLACEHOLDER_URL


def _int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str(v: Any) -> Optional[str]:
    return None if v is None else str(v)


def _list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else ([] if v is None else [v])


def _ts(v: Any) -> Optional[str]:
    """epoch seconds (float) or ISO string -> ISO-8601 UTC."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat()
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def url_ref(role: str, url: Any, api_type: Optional[str] = None) -> list[dict]:
    if not _usable(url):
        return []
    return [{"role": role, "url": url, "type": media_type(url, api_type), "api_type": api_type}]


def media_refs(m: Any, role: str, keep_placeholders: bool = False) -> list[dict]:
    """Normalize a media object {url,type,width,height,placeholder,optimized_url,thumbnail_url,main_url,...}."""
    if isinstance(m, str):
        return url_ref(role, m)
    if not isinstance(m, dict):
        return []
    out: list[dict] = []
    api_type = _str(m.get("type"))
    if _usable(m.get("url")):
        ph = m.get("placeholder")
        out.append({"role": role, "url": m["url"], "type": media_type(m["url"], api_type, m.get("content_type")),
                    "api_type": api_type, "width": _int(m.get("width")), "height": _int(m.get("height")),
                    "duration": _num(m.get("duration")), "duration_ms": _int(m.get("duration_ms")),
                    "content_type": _str(m.get("content_type")),
                    "placeholder": ph if keep_placeholders and isinstance(ph, str) else None,
                    "extra": {k: v for k, v in m.items() if k not in MEDIA_KEYS}})
    if _usable(m.get("main_url")):
        out.append({"role": f"{role}_main", "url": m["main_url"], "type": media_type(m["main_url"], api_type),
                    "api_type": api_type, "width": _int(m.get("main_width")), "height": _int(m.get("main_height"))})
    for key, suffix in (("optimized_url", "optimized"), ("thumbnail_url", "thumbnail")):
        out += url_ref(f"{role}_{suffix}", m.get(key))
    return out


def _dedup_media(refs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in refs:
        k = (r["role"], r["url"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _extra(item: dict, known: set[str]) -> dict:
    return {k: v for k, v in item.items() if k not in known}


def items_of(body: Any) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in LIST_KEYS:
            if isinstance(body.get(k), list):
                return body[k]
    return []


def page_info(body: Any) -> dict:
    """total / next cursor / has_more as reported by the API."""
    if not isinstance(body, dict):
        return {"total": None, "next_cursor": None, "has_more": None}
    cur = body.get("cursor", body.get("next_cursor"))
    if "has_more" in body:                                  # /reference-elements/voices, /color-presets
        cur = {k: body.get(k) for k in ("user_cursor", "preset_cursor") if body.get(k) is not None} or cur
    if isinstance(cur, dict):
        cur = ",".join(f"{k}={v}" for k, v in cur.items())
    return {"total": _int(body.get("total")), "next_cursor": None if cur in (None, "") else str(cur),
            "has_more": body.get("has_more") if isinstance(body.get("has_more"), bool) else None}


def next_params(src: Source, body: Any, params: dict[str, str], n_items: int) -> Optional[dict[str, str]]:
    """Query params of the next page, or None when the API says there is no more."""
    if not src.paginate or not isinstance(body, dict) or n_items == 0:
        return None
    nxt = dict(params)
    if "has_more" in body:
        if not body.get("has_more"):
            return None
        changed = False
        for k in ("user_cursor", "preset_cursor", "cursor"):
            v = body.get(k)
            if v is not None and str(v) != params.get(k):
                nxt[k] = str(v)
                changed = True
        return nxt if changed else None
    cur = body.get("cursor", body.get("next_cursor"))
    if cur not in (None, ""):
        if str(cur) == params.get("cursor"):
            return None
        nxt["cursor"] = str(cur)
        return nxt
    if "offset" in body and body.get("total") is not None:          # /viral-hub/presets/all (limit/offset)
        off = (_int(body.get("offset")) or 0) + n_items
        if off < (_int(body.get("total")) or 0):
            nxt["offset"] = str(off)
            if "limit" not in nxt:
                nxt["limit"] = str(n_items)
            return nxt
    return None


# ------------------------------------------------------------------ per-kind item parsers
PRESET_KEYS = {"id", "name", "description", "preset_family", "categories", "tags", "priority", "cms_id", "params",
               "media"}


def _preset(item: dict, sel: Any) -> dict:
    media = media_refs(item.get("media"), "preview", _kp(sel))
    return {"id": str(item["id"]), "name": _str(item.get("name")), "description": _str(item.get("description")),
            "preset_family": _str(item.get("preset_family")), "categories": _list(item.get("categories")),
            "tags": _list(item.get("tags")), "priority": _num(item.get("priority")),
            "cms_id": _str(item.get("cms_id")),
            "params": item.get("params") if isinstance(item.get("params"), dict) else None,
            "has_preview": bool(media), "media": media}


def _kp(sel: Any) -> bool:
    return bool(getattr(sel, "keep_placeholders", False))


def p_motion(item: dict, env, sel) -> dict:
    d = _preset(item, sel)
    mix = item.get("mix")
    d["mix"] = None if mix is None else [
        {"id": _str(m.get("id")), "name": _str(m.get("name")), "extra": _extra(m, {"id", "name"})}
        if isinstance(m, dict) else {"id": _str(m), "name": None, "extra": {}} for m in _list(mix)]
    d["is_collection"] = mix is not None
    d["extra"] = _extra(item, PRESET_KEYS | {"mix"})
    return d


def p_motion_detail(item: dict, env, sel) -> dict:
    d = _preset(item, sel)
    d["extra"] = _extra(item, PRESET_KEYS)
    return d


def p_style(item: dict, env, sel) -> dict:
    d = _preset(item, sel)
    d["extra"] = _extra(item, PRESET_KEYS)
    return d


def p_motion_sample(item: dict, env, sel) -> dict:
    motion_id = env.params.get("motion_id") or ""
    return {"sample_uid": f"{motion_id}:{item['id']}", "id": str(item["id"]), "motion_id": motion_id,
            "preset_family": _str(item.get("preset_family")), "priority": _num(item.get("priority")),
            "media": media_refs(item.get("media"), "video", _kp(sel)),
            "extra": _extra(item, {"id", "media", "preset_family", "priority"})}


def p_avatar(item: dict, env, sel) -> dict:
    params = item.get("params") if isinstance(item.get("params"), dict) else None
    img = (params or {}).get("input_image") if isinstance((params or {}).get("input_image"), dict) else {}
    media = media_refs(item.get("media"), "preview", _kp(sel)) + url_ref("input_image", img.get("url"))
    return {"id": str(item["id"]), "name": _str(item.get("name")), "voice_id": _str((params or {}).get("voice_id")),
            "input_image_id": _str(img.get("id")), "params": params, "media": media,
            "extra": _extra(item, {"id", "name", "params", "media"})}


def p_avatar_preset(item: dict, env, sel) -> dict:
    params = item.get("params") if isinstance(item.get("params"), dict) else None
    return {"id": str(item["id"]), "name": _str(item.get("name")), "quality": _str((params or {}).get("quality")),
            "chunks_count": _int((params or {}).get("chunks_count")), "params": params,
            "media": media_refs(item.get("media"), "preview", _kp(sel)),
            "extra": _extra(item, {"id", "name", "params", "media"})}


def p_voice(item: dict, env, sel) -> dict:
    keys = {"id", "name", "gender", "age", "categories", "is_gpt", "voice_url", "waveform_url", "image_url"}
    return {"id": str(item["id"]), "name": _str(item.get("name")), "gender": _str(item.get("gender")),
            "age": _str(item.get("age")), "categories": _list(item.get("categories")),
            "is_gpt": item.get("is_gpt") if isinstance(item.get("is_gpt"), bool) else None,
            "voice_url": _str(item.get("voice_url")), "waveform_url": _str(item.get("waveform_url")),
            "image_url": _str(item.get("image_url")),
            "media": url_ref("voice", item.get("voice_url")) + url_ref("image", item.get("image_url"))
            + url_ref("waveform", item.get("waveform_url")),
            "extra": _extra(item, keys)}


def p_reference_voice(item: dict, env, sel) -> dict:
    keys = {"id", "name", "gender", "age", "type", "supported_models", "source", "thumbnail_url", "waveform_url"}
    return {"id": str(item["id"]), "name": _str(item.get("name")), "gender": _str(item.get("gender")),
            "age": _str(item.get("age")), "voice_type": _str(item.get("type")),
            "supported_models": [str(x) for x in _list(item.get("supported_models"))],
            "audio_url": _str(item.get("source")), "thumbnail_url": _str(item.get("thumbnail_url")),
            "waveform_url": _str(item.get("waveform_url")),
            "media": url_ref("voice", item.get("source")) + url_ref("thumbnail", item.get("thumbnail_url"))
            + url_ref("waveform", item.get("waveform_url")),
            "extra": _extra(item, keys)}


def p_sound(item: dict, env, sel) -> dict:
    keys = {"id", "name", "description", "sound_url", "waveform_url"}
    return {"id": str(item["id"]), "name": _str(item.get("name")), "description": _str(item.get("description")),
            "sound_url": _str(item.get("sound_url")), "waveform_url": _str(item.get("waveform_url")),
            "media": url_ref("sound", item.get("sound_url")) + url_ref("waveform", item.get("waveform_url")),
            "extra": _extra(item, keys)}


def p_soul_sample(item: dict, env, sel) -> dict:
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    style = params.get("style") if isinstance(params.get("style"), dict) else {}
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    results = item.get("results") if isinstance(item.get("results"), dict) else {}
    media = media_refs(result, "result")
    for k, v in results.items():
        media += media_refs(v, f"results_{k}")
    media += url_ref("style", style.get("url"))
    keys = {"id", "status", "job_set_type", "job_set_id", "user_id", "created_at", "published_at", "params", "result",
            "results"}
    return {"id": str(item["id"]), "status": _str(item.get("status")), "job_set_type": _str(item.get("job_set_type")),
            "job_set_id": _str(item.get("job_set_id")), "user_id": _str(item.get("user_id")),
            "created_at": _ts(item.get("created_at")), "published_at": _ts(item.get("published_at")),
            "prompt": _str(params.get("prompt")), "width": _int(params.get("width")),
            "height": _int(params.get("height")), "steps": _int(params.get("steps")), "seed": _int(params.get("seed")),
            "batch_size": _int(params.get("batch_size")), "quality": _str(params.get("quality")),
            "style_id": _str(params.get("style_id") or style.get("id")), "style_name": _str(style.get("name")),
            "style_url": _str(style.get("url")),
            "style_strength": _num(params.get("style_strength", style.get("strength"))),
            "result_url": _str(result.get("url")), "result_type": _str(result.get("type")),
            "params": params or None, "media": _dedup_media(media), "extra": _extra(item, keys)}


def p_viral_type(item: dict, env, sel) -> dict:
    return {"id": str(item["id"]), "slug": _str(item.get("slug")), "name": _str(item.get("name")),
            "priority": _num(item.get("priority")), "lang": env.params.get("lang"),
            "extra": _extra(item, {"id", "slug", "name", "priority"})}


def p_viral_preset(item: dict, env, sel) -> dict:
    kp = _kp(sel)
    media = (media_refs(item.get("preview_media"), "preview", kp) + media_refs(item.get("widescreen_media"),
             "widescreen", kp) + media_refs(item.get("preview_image"), "preview_image", kp)
             + media_refs(item.get("widescreen_image"), "widescreen_image", kp))
    urls = {r["url"] for r in media}
    for role, key in (("preview", "preview_url"), ("thumbnail", "thumbnail_url")):
        if item.get(key) not in urls:
            media += url_ref(role, item.get(key))
    prices = [{"key": str(p.get("key") or ""), "credit_units": _num(p.get("credit_units")),
               "extra": _extra(p, {"key", "credit_units"})} for p in _list(item.get("price_matrix"))
              if isinstance(p, dict)]
    units = [p["credit_units"] for p in prices if p["credit_units"] is not None]
    default = next((p["credit_units"] for p in prices if p["key"] == ""), None)
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else None
    keys = {"id", "slug", "kind", "name", "description", "job_set_type", "duration", "ip_check_required",
            "is_main_page", "priority", "tags", "type_ids", "preview_url", "thumbnail_url", "pricing", "price_matrix",
            "param_choices", "inputs", "param_inputs", "preview_media", "widescreen_media", "preview_image",
            "widescreen_image"}
    return {"id": str(item["id"]), "slug": _str(item.get("slug")), "preset_kind": _str(item.get("kind")),
            "name": _str(item.get("name")), "description": _str(item.get("description")),
            "job_set_type": _str(item.get("job_set_type")), "duration": _num(item.get("duration")),
            "ip_check_required": item.get("ip_check_required"), "is_main_page": item.get("is_main_page"),
            "priority": _num(item.get("priority")), "tags": _list(item.get("tags")),
            "type_ids": [str(x) for x in _list(item.get("type_ids"))], "type_slugs": [],
            "preview_url": _str(item.get("preview_url")), "thumbnail_url": _str(item.get("thumbnail_url")),
            "pricing_type": _str((pricing or {}).get("type")), "pricing": pricing,
            "default_credit_units": default, "min_credit_units": min(units) if units else None,
            "max_credit_units": max(units) if units else None, "price_matrix": prices,
            "param_choices": item.get("param_choices") if isinstance(item.get("param_choices"), dict) else None,
            "inputs": [i for i in _list(item.get("inputs")) if isinstance(i, dict)],
            "param_inputs": _list(item.get("param_inputs")), "lang": env.params.get("lang"),
            "media": _dedup_media(media),
            "extra": {**_extra(item, keys),
                      **({"inputs_non_dict": [i for i in _list(item.get("inputs")) if not isinstance(i, dict)]}
                         if any(not isinstance(i, dict) for i in _list(item.get("inputs"))) else {})}}


GENERIC_KEYS = {"id", "name", "slug", "description", "preset_family", "categories", "tags", "priority", "cms_id",
                "params"}
GENERIC_GROUP_FIELD = {"catalog_soul_style": "style_set", "catalog_model_motion": "model_family",
                       "catalog_marketing_preset": "category_id"}
USER_OWNED_TYPES = {"user", "custom", "manual", "personal"}
# person objects inside catalog items (e.g. katana_presets[].author = {user_id, username, avatar_url, badge}):
# identifying fields are dropped unless --with-profiles.
PERSON_KEYS = ("author", "user", "creator", "owner")
PERSON_ID_FIELDS = {"id", "user_id", "username", "full_name", "name", "email", "avatar_url", "headline", "profile_url"}


def redact_people(item: dict) -> dict:
    """Copy of `item` without user identities (top-level user_id/username/email; person sub-objects keep only
    non-identifying fields such as `badge`, plus `redacted: true`)."""
    out = {k: v for k, v in item.items() if k not in ("user_id", "username", "email")}
    for k in PERSON_KEYS:
        v = out.get(k)
        if isinstance(v, dict):
            out[k] = {**{kk: vv for kk, vv in v.items() if kk not in PERSON_ID_FIELDS}, "redacted": True}
    return out


def _profiles(sel: Any) -> bool:
    return bool(getattr(sel, "with_profiles", False))


def author_keys(item: dict) -> dict:
    """{author_key, creator_uid_key} from the raw item's author user id (katana: author.user_id). Pseudonymous
    hashes, kept with and without --with-profiles; None when the id is missing or redacted."""
    a = item.get("author") if isinstance(item.get("author"), dict) else {}
    uid = a.get("user_id") or a.get("id") or item.get("user_id")
    if isinstance(uid, str) and "redacted" in uid.lower():       # "<redacted>" in older samples / archives
        uid = None
    key = creator_uid_key(uid)
    return {"author_key": key, "creator_uid_key": key}


def p_generic(item: dict, env, sel, src: Source) -> Optional[dict]:
    kp = _kp(sel)
    keys = author_keys(item) if src.kind == "catalog_katana_preset" else {}
    if not _profiles(sel):
        item = redact_people(item)
    group = src.group or env.params.get("category_id")
    ident = item.get("id", item.get("slug", item.get("key", item.get("name"))))
    if ident is None:
        ident = make_id(src.endpoint, str(sorted(item.items()))[:500])
    media: list[dict] = []
    mapped = set(GENERIC_KEYS)
    for k, v in item.items():                       # media-like values: {url: ...} objects and *_url strings
        if k in GENERIC_KEYS:
            continue
        if isinstance(v, dict) and ("url" in v or "source" in v):
            media += media_refs(v if "url" in v else {**v, "url": v.get("source")}, k, kp)
            mapped.add(k)
        elif isinstance(v, str) and (k.endswith("_url") or k in ("url", "image", "video", "preview", "thumbnail")) \
                and _usable(v):
            media += url_ref(k.removesuffix("_url"), v)
            mapped.add(k)
    d = {"uid": f"{group}:{ident}" if group else str(ident), "id": str(ident), "group": group,
         "name": _str(item.get("name") or item.get("title")), "slug": _str(item.get("slug")),
         "description": _str(item.get("description")), "preset_family": _str(item.get("preset_family")), "categories": _list(item.get("categories")),
         "tags": _list(item.get("tags")), "priority": _num(item.get("priority")), "cms_id": _str(item.get("cms_id")),
         "params": item.get("params"), "lang": env.params.get("lang"), "media": _dedup_media(media),
         "extra": _extra(item, mapped)}
    field = GENERIC_GROUP_FIELD.get(src.kind)
    if field:
        d[field] = group
    d.update(keys)
    return d


# ------------------------------------------------------------------ opt-in extras (2026-11-26)
def _flat_prov(env) -> dict:
    return {"source_url": env.url, "scraped_at": env.fetched_at.isoformat(), "schema_version": 1}


def _credits(v: Any) -> Optional[int | float]:
    """Credit amounts as numbers: int when integral (34), float otherwise; None for missing/non-numeric."""
    n = _num(v)
    if n is None:
        return None
    return int(n) if n.is_integer() else n


def _dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


CHAIN_KEYS = {"id", "product_key", "name", "description", "collaborate", "category", "image_preview", "previews",
              "duration", "priority", "discount_credits", "cost_credits", "pricing_mode", "pricing_schema", "inputs",
              "preset_family", "model", "runtime", "runtime_params"}


def p_chain_preset(item: dict, env, sel) -> dict:
    kp = _kp(sel)
    rp = _dict(item.get("runtime_params"))
    preview = _dict(item.get("image_preview"))
    media = media_refs(preview, "image_preview", kp)
    previews = sorted((p for p in _list(item.get("previews")) if isinstance(p, dict)),
                      key=lambda p: not p.get("is_main"))            # main preview first, like the app
    for p in previews:
        for m in media_refs(p.get("media"), "preview", kp):
            m["extra"] = {**m.get("extra", {}), "aspect_ratio": _str(p.get("aspect_ratio")),
                          "is_main": p.get("is_main"), "preview_id": _str(p.get("id"))}
            media.append(m)
    inputs = []
    for i in _list(item.get("inputs")):
        if not isinstance(i, dict):
            continue
        props = _dict(i.get("properties"))
        inputs.append({"id": _str(i.get("id")), "type": _str(i.get("type")), "min": _int(props.get("min")),
                       "max": _int(props.get("max")), "properties": props,
                       "extra": _extra(i, {"id", "type", "properties"})})
    cost, regular = _credits(item.get("cost_credits")), _credits(item.get("discount_credits"))
    collab = item.get("collaborate") if isinstance(item.get("collaborate"), str) and item["collaborate"].strip() \
        else None
    return {"id": str(item["id"]), "product_key": _str(item.get("product_key")), "name": _str(item.get("name")),
            "description": _str(item.get("description")), "category": _str(item.get("category")) or None,
            "priority": _num(item.get("priority")), "model": _str(item.get("model")),
            "preset_family": _str(item.get("preset_family")), "runtime": _str(item.get("runtime")),
            "chain_type": _str(rp.get("chain_type")), "runtime_endpoint": _str(rp.get("endpoint")),
            "runtime_model": _str(rp.get("model")), "runtime_params": rp,
            "pricing_mode": _str(item.get("pricing_mode")), "pricing_schema": _dict(item.get("pricing_schema")),
            "cost_credits": cost, "discount_credits": regular,
            "is_discounted": cost is not None and regular is not None and cost != regular,
            "duration": _num(item.get("duration")), "inputs": inputs,
            "is_hidden": SOURCE_BY_ENDPOINT[env.endpoint].group == "hidden",
            "has_collaborator": collab is not None,
            "collaborator": collab.strip() if collab and _profiles(sel) else None,
            "image_preview_url": _str(preview.get("url")) if _usable(preview.get("url")) else None,
            "lang": env.params.get("lang"), "media": _dedup_media(media), "extra": _extra(item, CHAIN_KEYS),
            **_flat_prov(env)}


def p_restyle_preset(item: dict, env, sel) -> dict:
    kp = _kp(sel)
    media: list[dict] = []
    for key, role in (("image", "image"), ("preview_video", "preview"), ("video", "video"),
                      ("original_video", "original_video")):
        media += media_refs(item.get(key), role, kp)
    images = [m for m in _list(item.get("images")) if isinstance(m, dict)]
    for n, m in enumerate(images):
        media += media_refs(m, f"images_{n}", kp)
    variants = []
    for v in _list(item.get("variants")):
        if not isinstance(v, dict):
            continue
        vtype = _str(v.get("type"))
        media += media_refs(v.get("media"), f"variant_{vtype or 'unknown'}", kp)
        variants.append({"id": _str(v.get("id")), "type": vtype, "extra": _extra(v, {"id", "type", "media"})})
    keys = {"id", "name", "title", "description", "source", "job_set_type", "priority", "variants", "image", "images",
            "preview_video", "video", "original_video"}
    return {"id": str(item["id"]), "name": _str(item.get("name")), "title": _str(item.get("title")),
            "description": _str(item.get("description")), "preset_source": _str(item.get("source")),
            "job_set_type": _str(item.get("job_set_type")), "priority": _num(item.get("priority")),
            "variants": variants, "image_count": len(images), "lang": env.params.get("lang"),
            "media": _dedup_media(media), "extra": _extra(item, keys), **_flat_prov(env)}


def p_notices(body: Any, env) -> list[dict]:
    """{header_notices: [{view{title, description, link, …}, config{…}}], job_set_notices: [{job_set_types, params,
    variant, badge{label, tooltip}, popup{title, description}}]} -> one entity per notice (no API ids: hashed)."""
    if not isinstance(body, dict):
        return []
    out = []
    for section, key in (("header", "header_notices"), ("job_set", "job_set_notices")):
        for n in _list(body.get(key)):
            if not isinstance(n, dict):
                continue
            badge, popup, view = _dict(n.get("badge")), _dict(n.get("popup")), _dict(n.get("view"))
            types = sorted(str(t) for t in _list(n.get("job_set_types")))
            label = badge.get("label") if section == "job_set" else view.get("title")
            out.append({"id": make_id("catalog_notice", section, ",".join(types), label),
                        "section": section, "job_set_types": types, "variant": _str(n.get("variant")),
                        "badge_label": _str(badge.get("label")), "badge_tooltip": _str(badge.get("tooltip")),
                        "popup_title": _str(popup.get("title")), "popup_description": _str(popup.get("description")),
                        "title": _str(view.get("title")), "description": _str(view.get("description")),
                        "link": _str(view.get("link")), "params": _dict(n.get("params")),
                        "lang": env.params.get("lang"), "media": [],
                        "extra": {**_extra(n, {"job_set_types", "params", "variant", "badge", "popup", "view"}),
                                  **({"badge": _extra(badge, {"label", "tooltip"})}
                                     if _extra(badge, {"label", "tooltip"}) else {}),
                                  **({"popup": _extra(popup, {"title", "description"})}
                                     if _extra(popup, {"title", "description"}) else {}),
                                  **({"view": _extra(view, {"title", "description", "link"})}
                                     if _extra(view, {"title", "description", "link"}) else {})},
                        **_flat_prov(env)})
    return out


def p_outfit_character(item: dict, env, sel) -> dict:
    url = item.get("url") if _usable(item.get("url")) else None
    return {"id": str(item["id"]), "api_type": _str(item.get("type")), "url": url, "width": _int(item.get("width")),
            "height": _int(item.get("height")), "media": media_refs(item, "image", _kp(sel)),
            "extra": _extra(item, {"id", "type", "url", "width", "height"}), **_flat_prov(env)}


ITEM_PARSERS = {
    "catalog_motion": p_motion, MOTION_DETAIL_KIND: p_motion_detail, "catalog_style": p_style,
    "catalog_motion_sample": p_motion_sample, "catalog_avatar": p_avatar, "catalog_avatar_preset": p_avatar_preset,
    "catalog_voice": p_voice, "catalog_reference_voice": p_reference_voice, "catalog_sound": p_sound,
    "catalog_soul_sample": p_soul_sample, "catalog_viral_type": p_viral_type, "catalog_viral_preset": p_viral_preset,
    "catalog_chain_preset": p_chain_preset, "catalog_restyle_preset": p_restyle_preset,
    "catalog_outfit_character": p_outfit_character,
}


# ------------------------------------------------------------------ entry points
def parse_envelope(env, sel) -> list[dict]:
    src = SOURCE_BY_ENDPOINT.get(env.endpoint)
    if src is None or not env.ok:
        return []
    prov = env.provenance()
    body = env.body
    out: list[dict] = []
    if src.kind == MOTION_DETAIL_KIND:
        items = [body] if isinstance(body, dict) and body.get("id") else []
    elif src.kind == "catalog_notice":                 # two lists in one object; items have no ids
        notices = p_notices(body, env)
        items = []
        out += [{"kind": src.kind, **n, "source": prov} for n in notices]
    elif src.kind == "catalog_outfit_character":       # {characters: [...]}
        items = body.get("characters") if isinstance(body, dict) and isinstance(body.get("characters"), list) else []
    else:
        items = items_of(body)
    for item in items:
        if not isinstance(item, dict):
            continue
        if src.kind == "catalog_color_preset" and str(item.get("type", "")).lower() in USER_OWNED_TYPES:
            continue                                # a user's own presets are account data, not catalog
        if src.kind in ITEM_PARSERS:
            if item.get("id") is None:
                continue
            e = ITEM_PARSERS[src.kind](item, env, sel)
        else:
            e = p_generic(item, env, sel, src)
        if e is None:
            continue
        out.append({"kind": src.kind, **e, "source": prov})
    if src.kind != MOTION_DETAIL_KIND:
        info = page_info(body)
        params = {k: str(v) for k, v in env.params.items()}
        first = not any(k in params for k in ("cursor", "user_cursor", "preset_cursor", "offset"))
        out.append({"kind": PAGE_KIND, "page_id": make_id(env.endpoint, sorted(params.items())),
                    "endpoint": env.endpoint, "catalog": src.kind, "group": src.group or params.get("motion_id")
                    or params.get("category_id"), "params": params, "first_page": first,
                    "item_count": len(items) or sum(1 for e in out if e["kind"] == "catalog_notice"), **info, "source": prov})
    return out


def keep(entity: dict, sel) -> bool:
    kinds = sel.output_kinds() if hasattr(sel, "output_kinds") else None
    return kinds is None or entity.get("kind") in kinds
