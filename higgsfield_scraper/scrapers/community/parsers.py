"""Pure parsers: Envelope -> entity dicts (no network, no Scrapy). Used by the spider and by offline `normalize`."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ...core.dataset import make_id
from .endpoints import (BENEFITS_ENDPOINT, COMMENTS_ENDPOINT, COMPARE_ENDPOINT, DETAIL_ENDPOINT, ENDPOINT_FEEDS,
                        JOB_COSTS_ENDPOINT, PLANS_ENDPOINT, VIRAL_ENDPOINT)
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
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
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
            "generations_in_dataset": None, "source": provenance}


def _items_of(body: Any) -> list[dict]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for k in ("items", "comments", "data", "results"):
            if isinstance(body.get(k), list):
                return [x for x in body[k] if isinstance(x, dict)]
    return []


def parse_comments(body: Any, publication_id: str, sel: Selection, provenance: dict) -> list[dict]:
    out = []
    for c in _items_of(body):
        cid = c.get("id") or c.get("comment_id")
        if not cid:
            continue
        user = c.get("user") if isinstance(c.get("user"), dict) else {}
        prof = c.get("profile") if isinstance(c.get("profile"), dict) else {}
        used = {"id", "comment_id", "parent_id", "text", "content", "body", "created_at", "likes_count", "likes",
                "user_id", "user", "profile"}
        out.append({
            "kind": "community_comment", "comment_id": str(cid), "publication_id": publication_id,
            "parent_id": _str(c.get("parent_id")),
            "text": _str(c.get("text") or c.get("content") or c.get("body")),
            "created_at": iso_ts(c.get("created_at")),
            "likes": _int(c.get("likes_count", c.get("likes"))),
            "user_id": _str(c.get("user_id") or user.get("id")),
            "username": _str(prof.get("username") or user.get("username")) if sel.with_profiles else None,
            "extra": {k: v for k, v in c.items() if k not in used},
            "source": provenance})
    return out


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
