"""Account-specific privacy: field WHITELISTS for every account endpoint + a downloader middleware that applies them
to response bodies BEFORE anything is archived (http/, raw/) or parsed.

`core.privacy.redact_personal` only blanks other users' names/handles/avatars/emails and keeps ids; for the account
scraper that is not enough (user/workspace/subscription ids, Stripe ids, prompts, media URLs, trace ids). Instead of
changing core behaviour for every scraper, this package:

* keeps only whitelisted fields per endpoint (`sanitize_body`),
* replaces job / job-set ids with stable hashes (`make_id`) so records can still be joined and re-normalized,
* replaces prompt text with a length marker ``<redacted:N chars>`` unless `--with-prompts`,
* replaces input media (URLs, ids) with stubs that only keep the type / role / file extension
  (the cost estimator needs to know "1 input video, 2 images", never where they are).

`sanitize_body` is idempotent, so parsers can run it again on an already-sanitized raw/ file (`normalize`).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urlsplit

from ...core.privacy import PERSONAL_KEYS
from ...estimate.estimator import (BATCH_KEYS, COMPONENT_FLAGS, DURATION_KEYS, HDR_KEYS, IMAGE_PARAM_KEYS,
                                   MEDIA_LIST_KEYS, PARAM_DIMENSIONS, REFERENCE_KEYS, TEXT_KEYS, VIDEO_PARAM_KEYS)
from ...schemas.common import make_id
from . import endpoints as ep

PROMPT_MARK = re.compile(r"^<redacted:(\d+) chars>$")
MEDIA_STUB = "<media>"

# ------------------------------------------------------------------ snapshot whitelists
USER_FIELDS = (
    "plan_type", "billing_period", "plan_ends_at", "next_credit_allocation_at", "is_cancel_inited", "cohort",
    "promo_state", "has_unlim", "has_flex_unlim", "workspace_type", "workspace_role", "is_paused",
    "is_pause_scheduled", "is_gift_subscription", "plan_version", "trial_status", "subscription_downgrades_at",
    "subscription_downgrades_plan", "is_pro_plan_veo3_available", "veo3_fast_generations_count",
    # balances in credits (floats)
    "subscription_credits", "package_credits", "bonus_credits", "bonus_credits_expire_at", "daily_credits",
    "total_plan_credits", "soul_credits", "wan2_5_video_credits", "text2keyframes_credits", "face_swap_credits",
    "qwen_camera_control_credits", "character_swap_credits",
)
USER_META_FIELDS = ("cohort",)                       # country_code / region_code (location) dropped
WALLET_FIELDS = (
    "credits_balance", "subscription_balance", "total_credits", "on_demand_credits", "bonus_credits",
    "bonus_credits_expire_at", "expire_days", "credit_limit", "allocation_cycle", "next_credit_allocation_date",
    "group_credit_allocation", "scoped_credits",
)
SUBSCRIPTION_FIELDS = (
    "plan_name", "plan_type", "status", "billing_cycle", "total_seats", "occupied_seats", "available_seats",
    "seats_capacity", "unlimited_seats", "credits_per_seat", "current_period_start", "current_period_end",
    "cancel_at", "is_pause_scheduled", "pause_starts_at", "pause_resumes_at", "is_paused", "payment_status",
    "downgrades_at", "plan_version", "is_gift_subscription", "is_cancellation_requested",
)
NOTICE_FIELDS = ("status", "payment_method_bonus_status", "payment_method_bonus_type", "discount", "discounted_price",
                 "currency", "unlims")
AUTO_TOP_UP_FIELDS = (
    "state", "is_eligible", "is_on_demand_only", "threshold", "credits_per_dollar", "current_refill_amount",
    "on_demand_credits", "currency", "expire_days", "options", "refill_options", "selected_option", "default_option",
    "modal_type",
)
ALL_UNLIM_FIELDS = ("is_eligible_to_purchase", "has_all_unlims")
LIST_PARTS = {"workspace_settings": "configs", "free_gens": "items", "generation_seconds": "items"}
SNAPSHOT_FIELDS: dict[str, tuple[str, ...]] = {
    "user": USER_FIELDS, "user_meta": USER_META_FIELDS, "wallet": WALLET_FIELDS, "subscription": SUBSCRIPTION_FIELDS,
    "notice": NOTICE_FIELDS, "auto_top_up": AUTO_TOP_UP_FIELDS, "all_unlim_status": ALL_UNLIM_FIELDS,
}

# ------------------------------------------------------------------ job whitelists
JOB_FIELDS = ("job_id", "job_set_key", "job_set_type", "status", "created_at", "cost", "params")
#: free-text params: kept verbatim only with --with-prompts, otherwise "<redacted:N chars>"
PROMPT_KEYS = tuple(dict.fromkeys(TEXT_KEYS + ("negative_prompt",)))
#: params holding input media (URLs / ids): reduced to type/role/extension stubs
MEDIA_KEYS = tuple(dict.fromkeys(VIDEO_PARAM_KEYS + MEDIA_LIST_KEYS + IMAGE_PARAM_KEYS + REFERENCE_KEYS))
#: pricing-relevant params (everything the CostEstimator reads + a few descriptive ones)
PARAM_WHITELIST = tuple(dict.fromkeys(
    [k for keys in PARAM_DIMENSIONS.values() for k in keys] + list(PARAM_DIMENSIONS)
    + list(BATCH_KEYS) + list(DURATION_KEYS) + list(HDR_KEYS)
    + [k for keys in COMPONENT_FLAGS.values() for k in keys]
    + ["aspect_ratio", "width", "height", "tier", "preset_id", "chain_preset_id", "use_unlim", "enhance_prompt",
       "num_frames", "frames", "steps", "speed", "style_strength", "motion_strength", "upscale_factor", "scale",
       "voice_id", "language"]
    + list(MEDIA_KEYS) + list(PROMPT_KEYS)))
#: keys dropped anywhere inside unknown-shape content (lists of grants, offers, options …)
_DROP_KEY = re.compile(r"(^id$|_id$|_ids$|^ids$|url|email|avatar|stripe|customer|invoice|payment_method|card|"
                       r"trace|cluster_hash|token|secret|phone|^user$|^workspace|username|full_name|address)", re.I)


def _is_url(s: Any) -> bool:
    return isinstance(s, str) and (s.startswith(("http://", "https://", "data:", "blob:", "s3://", "//")))


def scrub(obj: Any) -> Any:
    """Generic scrub for unknown-shape content: drop id/url/personal keys; URL strings -> None."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()
                if not _DROP_KEY.search(k) and k.lower() not in PERSONAL_KEYS}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    if _is_url(obj):
        return None
    return obj


def hash_id(kind: str, value: Any) -> Optional[str]:
    return make_id(kind, value) if value not in (None, "") else None


def _ext(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    path = urlsplit(url).path if _is_url(url) else url
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", path)
    return f".{m.group(1).lower()}" if m else ""


def media_stub(v: Any) -> Any:
    """Input media -> {role, type, data: {type, url: '<media>.ext'}} (no ids, no URLs). Idempotent."""
    if isinstance(v, list):
        return [media_stub(x) for x in v]
    if isinstance(v, dict):
        data = v.get("data") if isinstance(v.get("data"), dict) else None
        out: dict[str, Any] = {}
        for k in ("role", "type", "kind", "media_type"):
            if isinstance(v.get(k), (str, int, float, bool)):
                out[k] = v[k]
        url = v.get("url") or v.get("raw_url") or v.get("video_url") or v.get("image_url")
        if url is not None and not data:
            out["url"] = MEDIA_STUB + _ext(url)
        if data is not None:
            d: dict[str, Any] = {}
            if isinstance(data.get("type"), str):
                d["type"] = data["type"]
            durl = data.get("url") or data.get("raw_url")
            if durl is not None:
                d["url"] = MEDIA_STUB + _ext(durl)
            out["data"] = d
        if not out:
            out["present"] = True
        return out
    if isinstance(v, str):
        return v if v.startswith(MEDIA_STUB) else (MEDIA_STUB + _ext(v) if v else v)
    return v                                           # bool / number / None


def prompt_value(v: Any, with_prompts: bool) -> Any:
    """Prompt text -> '<redacted:N chars>' (length kept for per-character pricing) unless --with-prompts."""
    if not isinstance(v, str) or with_prompts or PROMPT_MARK.match(v):
        return v
    return f"<redacted:{len(v)} chars>"


def sanitize_params(params: Any, with_prompts: bool) -> dict:
    if not isinstance(params, dict):
        return {}
    out: dict[str, Any] = {}
    for k in PARAM_WHITELIST:
        if k not in params:
            continue
        v = params[k]
        if k in PROMPT_KEYS:
            out[k] = prompt_value(v, with_prompts)
        elif k in MEDIA_KEYS:
            out[k] = media_stub(v)
        elif isinstance(v, (dict, list)):
            out[k] = scrub(v)
        elif _is_url(v):
            out[k] = MEDIA_STUB + _ext(v)
        else:
            out[k] = v
    return out


def sanitize_job(job: Any, with_prompts: bool) -> dict:
    if not isinstance(job, dict):
        return {}
    j = dict(job)
    if "job_id" not in j:
        j["job_id"] = hash_id("account_job", j.get("id"))
    if "job_set_key" not in j:
        j["job_set_key"] = hash_id("account_job_set", j.get("job_set_id"))
    out = {k: j.get(k) for k in JOB_FIELDS if k in j}
    out["params"] = sanitize_params(j.get("params"), with_prompts)
    return out


def sanitize_snapshot(part: str, body: Any) -> Any:
    if part in LIST_PARTS:
        key = LIST_PARTS[part]
        items = body.get(key) if isinstance(body, dict) else body if isinstance(body, list) else None
        return {key: scrub(items) if isinstance(items, list) else []}
    if part == "personal_promo":
        return scrub(body) if isinstance(body, dict) else {}
    fields = SNAPSHOT_FIELDS.get(part)
    if fields is None or not isinstance(body, dict):
        return scrub(body)
    return {k: (scrub(body[k]) if isinstance(body[k], (dict, list)) else body[k]) for k in fields if k in body}


def sanitize_body(endpoint: str, body: Any, with_prompts: bool = False) -> Any:
    """Whitelist one account endpoint's response body. Public pricing bodies pass through untouched."""
    if endpoint in ep.PUBLIC:
        return body
    if endpoint == ep.JOBS_ENDPOINT:
        if not isinstance(body, dict):
            return scrub(body)
        out = {k: body[k] for k in ("has_more", "cursor", "next_cursor", "total") if k in body}
        out["jobs"] = [sanitize_job(j, with_prompts) for j in (body.get("jobs") or []) if isinstance(j, dict)]
        return out
    if endpoint in ep.SNAPSHOT_ENDPOINTS:
        return sanitize_snapshot(ep.SNAPSHOT_ENDPOINTS[endpoint][1], body)
    return scrub(body)                                 # error bodies, unknown endpoints


def sanitize_error(body: Any) -> Any:
    return scrub(body)


# ------------------------------------------------------------------ downloader middleware
def block_reason(response) -> Optional[str]:
    """Bot-protection responses (never evaded): DataDome captcha or a Cloudflare challenge."""
    body = (response.body or b"")[:200000].lower()
    if b"captcha-delivery.com" in body or b"datadome" in body:
        return "datadome captcha"
    mitigated = (response.headers.get("cf-mitigated") or b"").decode("latin-1").lower()
    if mitigated:
        return f"cloudflare {mitigated}"
    return None


class AccountRedactionMiddleware:
    """Downloader middleware (582, between HttpArchive 580 and AccessLog 585). process_response runs from high to
    low priority numbers, so this rewrites the body before HttpArchiveMiddleware archives it, before the raw/
    pipeline saves it and before the spider parses it. Only active for the account spider. Also marks account
    requests `dont_cache` so the dev HTTP cache never stores unredacted personal bodies."""

    PRIORITY = 582

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    @staticmethod
    def _active(spider) -> bool:
        return getattr(spider, "scraper_name", None) == "account"

    def process_request(self, request, spider=None):
        if spider is None or self._active(spider):
            request.meta["dont_cache"] = True
        return None

    def process_response(self, request, response, spider=None):
        if spider is not None and not self._active(spider):
            return response
        endpoint = request.meta.get("endpoint")
        if endpoint in ep.PUBLIC or request.meta.get("media"):
            return response
        with_prompts = bool(getattr(getattr(spider, "selection", None), "with_prompts", False))
        try:
            data = json.loads(response.body or b"null")
        except (ValueError, UnicodeDecodeError):
            note: dict[str, Any] = {"_withheld": "non-JSON body withheld by the account scraper"}
            blocked = block_reason(response)
            if blocked:
                # keep the marker so BaseApiSpider's DataDome stop and AccountSpider's block handling still work
                note["_blocked"] = blocked
            return response.replace(body=json.dumps(note).encode("utf-8"))
        clean = sanitize_body(endpoint, data, with_prompts) if response.status == 200 else sanitize_error(data)
        return response.replace(body=json.dumps(clean, ensure_ascii=False).encode("utf-8"))
