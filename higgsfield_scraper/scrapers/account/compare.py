"""Estimate-vs-actual comparison (pure): CostEstimator output for a job's params vs the credits actually charged.

match  := comparable and |actual - estimated| <= TOLERANCE (0.01 credits = 1 cost unit, the API's resolution)
comparable := status in CHARGED_STATUSES, actual cost known, estimate has credits, params.use_unlim is not True
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from . import endpoints as ep
from .parsers import PROMPT_MARK
from .redaction import PROMPT_KEYS

TOLERANCE = Decimal("0.01")
Q = Decimal("0.0001")


def _dec(v: Any) -> Optional[Decimal]:
    if v is None or isinstance(v, bool):
        return None
    return Decimal(str(v)).quantize(Q, rounding=ROUND_HALF_UP)


def estimator_params(params: dict) -> dict:
    """Params as the estimator expects them: '<redacted:N chars>' -> an N-character placeholder (per-character
    pricing only needs the length)."""
    out = dict(params or {})
    for k in PROMPT_KEYS:
        v = out.get(k)
        if isinstance(v, str) and (m := PROMPT_MARK.match(v)):
            out[k] = "x" * int(m.group(1))
    return out


def compare_job(job: dict, estimate: Optional[dict]) -> dict:
    """job: AccountJob (JSON mode); estimate: EstimatedCost dict (or None when no estimator)."""
    est = estimate or {"status": "skipped", "notes": ["no estimator (pricing data unavailable)"]}
    actual = _dec(job.get("actual_credits"))
    estimated = _dec(est.get("credits"))
    reason = None
    if job.get("status") not in ep.CHARGED_STATUSES:
        reason = f"status {job.get('status')!r} is not a charged status"
    elif actual is None:
        reason = "no actual cost"
    elif estimated is None:
        reason = f"estimator status {est.get('status')!r} (no credits)"
    elif (job.get("params") or {}).get("use_unlim") is True or job.get("use_unlim") is True:
        reason = "use_unlim=true (may be free on an unlimited plan)"
    diff = (actual - estimated) if actual is not None and estimated is not None else None
    ratio = (actual / estimated).quantize(Q, rounding=ROUND_HALF_UP) if diff is not None and estimated else None
    comparable = reason is None
    return {
        "job_id": job["job_id"], "job_set_type": job.get("job_set_type"), "status": job.get("status"),
        "created_at": job.get("created_at"), "actual_credits": actual, "estimated_credits": estimated,
        "diff": diff, "abs_diff": abs(diff) if diff is not None else None, "ratio": ratio,
        "match": (abs(diff) <= TOLERANCE) if comparable else None, "comparable": comparable,
        "not_comparable_reason": reason, "estimator_status": est.get("status") or "skipped",
        "price_point_id": est.get("price_point_id"), "unit": est.get("unit"), "quantity": est.get("quantity"),
        "quantity_basis": est.get("quantity_basis"), "matched": est.get("matched") or {},
        "assumed": est.get("assumed") or {}, "notes": list(est.get("notes") or []),
    }


def summarize(rows: list[dict]) -> list[dict]:
    """Per job_set_type: jobs, comparable, matches, match_rate, estimator statuses, mean diff, totals."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r.get("job_set_type") or "?"].append(r)
    out = []
    for t, rs in sorted(groups.items()):
        comp = [r for r in rs if r["comparable"]]
        matches = sum(1 for r in comp if r["match"])
        diffs = [Decimal(str(r["diff"])) for r in comp]
        act = [Decimal(str(r["actual_credits"])) for r in comp]
        est = [Decimal(str(r["estimated_credits"])) for r in comp]
        out.append({
            "job_set_type": t, "jobs": len(rs), "comparable": len(comp), "matches": matches,
            "match_rate": round(matches / len(comp), 4) if comp else None,
            "exact_estimates": sum(r["estimator_status"] == "exact" for r in rs),
            "approximate_estimates": sum(r["estimator_status"] == "approximate" for r in rs),
            "unpriced": sum(r["estimator_status"] == "unpriced" for r in rs),
            "mean_diff": (sum(diffs) / len(diffs)).quantize(Q, rounding=ROUND_HALF_UP) if diffs else None,
            "total_actual_credits": sum(act) if act else None,
            "total_estimated_credits": sum(est) if est else None,
        })
    return out
