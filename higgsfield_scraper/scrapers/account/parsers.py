"""Pure parsers: raw account envelopes -> entity dicts. Every body goes through `redaction.sanitize_body` first
(idempotent), so the same code works on live bodies, on already-redacted raw/ files and on synthetic fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from ...estimate.estimator import BATCH_KEYS, DURATION_KEYS, IMAGE_PARAM_KEYS, MEDIA_LIST_KEYS, VIDEO_PARAM_KEYS
from ...estimate.estimator import _is_video_media  # same video detection as the estimator
from . import endpoints as ep
from .redaction import PROMPT_KEYS, PROMPT_MARK, sanitize_body


def iso(v: Any) -> Optional[str]:
    """Epoch seconds / ISO string -> ISO-8601 UTC; None stays None."""
    if v in (None, ""):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
    s = str(v).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def units_to_credits(units: Any) -> Optional[Decimal]:
    """Cost units (credits x 100, as in /workspaces/wallet and jobs[].cost) -> credits."""
    if units is None or isinstance(units, bool):
        return None
    try:
        return (Decimal(str(units)) / 100).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def to_credits(v: Any) -> Optional[Decimal]:
    """A value already in credits (floats on /user) -> Decimal (no binary float noise)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _first(params: dict, keys) -> Any:
    for k in keys:
        if params.get(k) not in (None, ""):
            return params[k]
    return None


def _scalar(v: Any) -> Any:
    return v if isinstance(v, (str, int, float, bool)) or v is None else None


def prompt_info(params: dict) -> tuple[Optional[int], Optional[str]]:
    """(prompt_chars, prompt text or None when redacted)."""
    for k in PROMPT_KEYS:
        v = params.get(k)
        if isinstance(v, str) and v:
            m = PROMPT_MARK.match(v)
            return (int(m.group(1)), None) if m else (len(v), v)
    return None, None


def media_counts(params: dict) -> tuple[Optional[int], Optional[int]]:
    images = videos = 0
    seen = False
    for k in MEDIA_LIST_KEYS + IMAGE_PARAM_KEYS + VIDEO_PARAM_KEYS:
        if k not in params:
            continue
        seen = True
        v = params[k]
        items = v if isinstance(v, list) else [v] if v not in (None, "", False, {}) else []
        for m in items:
            if k in VIDEO_PARAM_KEYS or _is_video_media(m):
                videos += 1
            else:
                images += 1
    return (images, videos) if seen else (None, None)


def parse_job(job: dict, env, sel) -> Optional[dict]:
    if not job.get("job_id"):
        return None
    params = job.get("params") or {}
    chars, text = prompt_info(params)
    images, videos = media_counts(params)
    cost = _int(job.get("cost"))
    return {
        "kind": "account_job",
        "job_id": job["job_id"],
        "job_set_key": job.get("job_set_key"),
        "job_set_type": job.get("job_set_type"),
        "status": job.get("status"),
        "created_at": iso(job.get("created_at")),
        "cost_units": cost,
        "actual_credits": units_to_credits(cost),
        "resolution": _scalar(_first(params, ("resolution", "output_resolution", "target_resolution"))),
        "duration": _scalar(_first(params, DURATION_KEYS)),
        "quality": _scalar(params.get("quality")),
        "batch_size": _scalar(_first(params, BATCH_KEYS)),
        "mode": _scalar(params.get("mode")),
        "aspect_ratio": _scalar(params.get("aspect_ratio")),
        "model": _scalar(params.get("model")),
        "use_unlim": params.get("use_unlim") if isinstance(params.get("use_unlim"), bool) else None,
        "input_images": images,
        "input_videos": videos,
        "prompt_chars": chars,
        "prompt": text if getattr(sel, "with_prompts", False) else None,
        "params": params if getattr(sel, "with_prompts", False) else _without_prompt_text(params),
        "source": env.provenance(),
    }


def _without_prompt_text(params: dict) -> dict:
    out = dict(params)
    for k in PROMPT_KEYS:
        v = out.get(k)
        if isinstance(v, str) and v and not PROMPT_MARK.match(v):
            out[k] = f"<redacted:{len(v)} chars>"
    return out


def parse_envelope(env, sel) -> list[dict]:
    if not env.ok:
        return []
    with_prompts = bool(getattr(sel, "with_prompts", False))
    if env.endpoint in ep.PRICING_ENDPOINTS:
        basis = env.endpoint.removeprefix("account_")
        return [{"kind": "account_cost_basis", "basis_id": basis, "body": env.body, "source": env.provenance()}]
    body = sanitize_body(env.endpoint, env.body, with_prompts)
    if env.endpoint == ep.JOBS_ENDPOINT:
        return [e for j in body.get("jobs") or [] if (e := parse_job(j, env, sel))]
    if env.endpoint in ep.SNAPSHOT_ENDPOINTS:
        part = ep.SNAPSHOT_ENDPOINTS[env.endpoint][1]
        return [{"kind": "account_snapshot_part", "part_id": part, "part": part,
                 "data": body if isinstance(body, dict) else {"value": body}, "source": env.provenance()}]
    return []


def keep(entity: dict, sel) -> bool:
    return True


# ------------------------------------------------------------------ snapshot assembly (used by dataset.py)
WALLET_BALANCES = ("credits_balance", "subscription_balance", "total_credits", "on_demand_credits", "bonus_credits")
USER_BALANCES = ("subscription_credits", "package_credits", "bonus_credits", "daily_credits", "total_plan_credits",
                 "soul_credits", "wan2_5_video_credits", "text2keyframes_credits", "face_swap_credits",
                 "qwen_camera_control_credits", "character_swap_credits")
PLAN_FIELDS = ("plan_type", "billing_period", "plan_ends_at", "next_credit_allocation_at", "is_cancel_inited",
               "cohort", "promo_state", "has_unlim", "has_flex_unlim", "workspace_type", "workspace_role",
               "is_paused", "is_pause_scheduled", "is_gift_subscription", "plan_version", "trial_status",
               "subscription_downgrades_at", "subscription_downgrades_plan", "is_pro_plan_veo3_available",
               "veo3_fast_generations_count")
TIME_FIELDS = {"plan_ends_at", "next_credit_allocation_at", "subscription_downgrades_at", "bonus_credits_expire_at",
               "next_credit_allocation_date", "current_period_start", "current_period_end", "cancel_at",
               "pause_starts_at", "pause_resumes_at", "downgrades_at"}


def _t(d: dict, k: str) -> Any:
    v = d.get(k)
    return iso(v) if k in TIME_FIELDS else v


def wallet_section(w: dict) -> dict:
    out: dict[str, Any] = {}
    for k in WALLET_BALANCES:
        out[f"{k}_units"] = _int(w.get(k))
        out[k] = units_to_credits(w.get(k))
    out.update({"bonus_credits_expire_at": _t(w, "bonus_credits_expire_at"), "expire_days": _int(w.get("expire_days")),
                "credit_limit_units": _int(w.get("credit_limit")), "allocation_cycle": _scalar(w.get("allocation_cycle")),
                "next_credit_allocation_date": _t(w, "next_credit_allocation_date"),
                "group_credit_allocation": w.get("group_credit_allocation"),
                "scoped_credits": [x for x in (w.get("scoped_credits") or []) if isinstance(x, dict)]})
    return out


def subscription_section(s: dict, now: Optional[str] = None) -> dict:
    """renewal_date = current_period_end when the subscription is active, not cancelled and the period end lies
    after the snapshot time (free plans keep a stale period end from the past: no renewal then)."""
    from .redaction import SUBSCRIPTION_FIELDS
    out = {k: _t(s, k) for k in SUBSCRIPTION_FIELDS}
    renews = (str(s.get("status") or "").lower() in ("active", "trialing", "past_due")
              and not s.get("cancel_at") and not s.get("is_cancellation_requested"))
    end = out.get("current_period_end")
    if renews and end and now:
        try:
            renews = datetime.fromisoformat(end) > datetime.fromisoformat(iso(now))
        except (TypeError, ValueError):
            pass
    out["renewal_date"] = end if renews else None
    return out


def build_snapshot(parts: dict[str, dict], scraped_at: str, snapshot_id: str) -> dict:
    from .redaction import AUTO_TOP_UP_FIELDS, NOTICE_FIELDS
    user = parts.get("user") or {}
    meta = parts.get("user_meta") or {}
    plan = {k: _t(user, k) for k in PLAN_FIELDS}
    plan["cohort"] = plan.get("cohort") or meta.get("cohort")
    balances = {k: to_credits(user.get(k)) for k in USER_BALANCES}
    balances["bonus_credits_expire_at"] = _t(user, "bonus_credits_expire_at")
    grants = (parts.get("workspace_settings") or {}).get("configs") or []
    top = parts.get("auto_top_up") or {}
    return {
        "snapshot_id": snapshot_id,
        "scraped_at": scraped_at,
        "plan": plan,
        "balances": balances,
        "wallet": wallet_section(parts.get("wallet") or {}),
        "subscription": subscription_section(parts.get("subscription") or {}, scraped_at),
        "auto_top_up": {k: (top.get(k) if k not in ("options", "refill_options") else (top.get(k) or []))
                        for k in AUTO_TOP_UP_FIELDS},
        "notice": {k: (parts.get("notice") or {}).get(k) for k in NOTICE_FIELDS},
        "all_unlim": dict(parts.get("all_unlim_status") or {}),
        "free_gens": list((parts.get("free_gens") or {}).get("items") or []),
        "generation_seconds": list((parts.get("generation_seconds") or {}).get("items") or []),
        "unlimited_grants": [g for g in grants if isinstance(g, dict) and g.get("status") != "locked"],
        "personal_promo": (parts.get("personal_promo") or None),
        "parts_fetched": sorted(parts),
        "parts_missing": sorted({v[1] for v in ep.SNAPSHOT_ENDPOINTS.values()} - set(parts)),
    }
