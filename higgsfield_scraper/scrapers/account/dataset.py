"""Assemble the validated AccountDataset and write every output file."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from ...constants import API_BASE
from ...core.base import RunMeta
from ...core.dataset import make_id, make_meta
from ...core.exporting import write_standard_outputs
from . import endpoints as ep
from .compare import TOLERANCE, compare_job, estimator_params, summarize
from .options import Selection
from .parsers import build_snapshot
from .schemas import AccountDataset

log = logging.getLogger(__name__)
NO_SESSION_STAT = "higgs/account/no_session"


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def build_estimator(bases: dict[str, dict], version: int = 1) -> tuple[Any, dict]:
    """-> (CostEstimator or None, pricing_basis dict). version 2 = CostEstimatorV2 (--estimate-version 2)."""
    from ... import estimate
    notes: list[str] = []
    jc = (bases.get("job_costs") or {}).get("body")
    basis = {"job_costs_version": (jc or {}).get("version") if isinstance(jc, dict) else None,
             "priced_models": len((jc or {}).get("data") or []) if isinstance(jc, dict) else None,
             "tolerance_credits": TOLERANCE, "notes": notes}
    if estimate.CostEstimator is None:
        notes.append("CostEstimator not available")
        return None, basis
    if not isinstance(jc, dict):
        notes.append("/job-sets/costs not fetched; estimates skipped")
        return None, basis
    try:
        cls = estimate.CostEstimator if version == 1 else estimate.estimator_class(version)
        est = cls.from_job_costs_body(jc)
        if version != 1:
            notes.append(f"estimator formula version {version} (--estimate-version; docs/COST_FORMULAS.md §8)")
    except Exception as e:  # never lose the dataset because of the optional estimate
        log.exception("building the cost estimator failed")
        notes.append(f"estimator init failed: {e!r}")
        return None, basis
    vir = (bases.get("viral_presets") or {}).get("body")
    if vir:
        try:
            est.with_viral_presets(vir)
            notes.append(f"viral preset price matrices for {len(est.viral)} presets")
        except Exception as e:
            notes.append(f"viral preset prices failed: {e!r}")
    cmp, ben = (bases.get("compare") or {}).get("body"), (bases.get("benefits") or {}).get("body")
    if cmp and ben:
        try:
            est.with_compare_fallback(cmp, ben)
            notes.append(f"comparison-table fallback prices for {len(est.fallback)} models missing from costs")
        except Exception as e:
            notes.append(f"comparison fallback failed: {e!r}")
    return est, basis


def estimate_job(est: Any, job: dict) -> Optional[dict]:
    if est is None:
        return None
    try:
        return est.estimate(job_set_type=job.get("job_set_type") or "", params=estimator_params(job.get("params")),
                            media_type=None)
    except Exception as e:
        return {"status": "unpriced", "notes": [f"estimator error: {e!r}"]}


def build_dataset(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta) -> dict:
    g = lambda k: entities.get(k) or []  # noqa: E731
    warnings: list[str] = []
    scraped_at = (rm.scraped_at or datetime.now(timezone.utc)).isoformat()
    if rm.stats.get(NO_SESSION_STAT):
        warnings.append("no login session: the account scraper needs one (run `python -m higgsfield_scraper login` "
                        "or set HF_CLERK_CLIENT / HF_EMAIL+HF_PASSWORD in .env); nothing was fetched")
    parts = {p["part"]: p.get("data") or {} for p in g("account_snapshot_part")}
    snapshot = build_snapshot(parts, scraped_at, make_id("account_snapshot", scraped_at)) if parts else None
    jobs = sorted((_strip(j) for j in g("account_job")), key=lambda j: j.get("created_at") or "", reverse=True)

    comparison: list[dict] = []
    groups: list[dict] = []
    basis = None
    if sel.compare_estimate:
        bases = {b["basis_id"]: b for b in g("account_cost_basis")}
        est, basis = build_estimator(bases, sel.estimate_version)
        comparison = [compare_job(j, estimate_job(est, j)) for j in jobs]
        groups = summarize(comparison)
        if not jobs:
            warnings.append("no jobs in this account: nothing to compare")

    comp = [c for c in comparison if c["comparable"]]
    matches = sum(1 for c in comp if c["match"])
    actual = [Decimal(str(j["actual_credits"])) for j in jobs if j.get("actual_credits") is not None]
    summary = {
        "jobs": len(jobs),
        "jobs_by_type": dict(Counter(j.get("job_set_type") or "?" for j in jobs).most_common()),
        "jobs_by_status": dict(Counter(j.get("status") or "?" for j in jobs).most_common()),
        "total_actual_credits": sum(actual) if actual else None,
        "comparable": len(comp), "matches": matches,
        "match_rate": round(matches / len(comp), 4) if comp else None,
    }
    counts = {"snapshot": 1 if snapshot else 0, "snapshot_parts": len(parts), "jobs": len(jobs),
              "estimate_comparison": len(comparison), "comparable": len(comp), "matches": matches}
    endpoints = {k: f"{API_BASE}{path}" for k, path in ep.ENDPOINT_URLS.items()
                 if k in ep.SNAPSHOT_ENDPOINTS or (k == ep.JOBS_ENDPOINT and sel.with_jobs)
                 or (k in ep.PRICING_ENDPOINTS and sel.compare_estimate)}
    meta = make_meta("account", sel, rm, counts=counts, endpoints=endpoints,
                     totals_available=dict(rm.totals), warnings=warnings)
    ds = {"schema_version": 1, "meta": meta, "snapshot": snapshot, "jobs": jobs,
          "estimate_comparison": comparison, "comparison_summary": groups, "pricing_basis": basis,
          "summary": summary}
    return AccountDataset.model_validate(ds).model_dump(mode="json")


# ------------------------------------------------------------------ outputs
def json_parts(ds: dict) -> dict[str, Any]:
    return {"account_snapshot": ds["snapshot"], "account_jobs": ds["jobs"],
            "estimate_comparison": ds["estimate_comparison"], "comparison_summary": ds["comparison_summary"],
            "summary": ds["summary"]}


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    from ...core.exporting import row
    snap = [row(ds["snapshot"])] if ds["snapshot"] else []
    jobs = [row(j) for j in ds["jobs"]]
    return {
        "account_snapshot": (snap, ["snapshot_id", "scraped_at"]),
        "account_jobs": (jobs, ["job_id", "job_set_type", "status", "created_at", "cost_units", "actual_credits"]),
        "estimate_comparison": ([row(c) for c in ds["estimate_comparison"]],
                                ["job_id", "job_set_type", "status", "actual_credits", "estimated_credits", "diff",
                                 "match", "comparable", "estimator_status"]),
        "comparison_summary": ([row(g) for g in ds["comparison_summary"]],
                               ["job_set_type", "jobs", "comparable", "matches", "match_rate"]),
    }


def summary_md(ds: dict) -> str:
    m, s, snap = ds["meta"], ds["summary"], ds["snapshot"]
    lines = [f"# account — {m.get('label') or ''}", "",
             f"- scraped_at: {m['scraped_at']}", f"- options: {m['options']}",
             "- privacy: no email/names/ids/Stripe ids/media URLs stored; job ids hashed; prompts "
             + ("STORED (--with-prompts)" if m["options"].get("with_prompts") else "length only"), ""]
    if snap:
        p, w, sub = snap["plan"], snap["wallet"], snap["subscription"]
        lines += ["## Snapshot", "",
                  f"- plan: {p.get('plan_type')} / {p.get('billing_period')} (subscription: {sub.get('plan_name')}, "
                  f"status {sub.get('status')}, cycle {sub.get('billing_cycle')}, renews {sub.get('renewal_date')})",
                  f"- wallet credits: total {w.get('total_credits')}, balance {w.get('credits_balance')}, "
                  f"subscription {w.get('subscription_balance')}, on-demand {w.get('on_demand_credits')}, "
                  f"bonus {w.get('bonus_credits')} (expire_days {w.get('expire_days')})",
                  f"- free gens: {len(snap['free_gens'])}, generation-seconds items: {len(snap['generation_seconds'])}, "
                  f"unlimited grants: {len(snap['unlimited_grants'])}",
                  f"- auto top-up: state {snap['auto_top_up'].get('state')}, eligible "
                  f"{snap['auto_top_up'].get('is_eligible')}, credits_per_dollar "
                  f"{snap['auto_top_up'].get('credits_per_dollar')}",
                  f"- parts fetched: {', '.join(snap['parts_fetched'])}"
                  + (f"; missing: {', '.join(snap['parts_missing'])}" if snap["parts_missing"] else ""), ""]
    else:
        lines += ["## Snapshot", "", "- none (no session or the account endpoints failed)", ""]
    if m["options"].get("with_jobs"):
        lines += ["## Jobs", "", f"- jobs: {s['jobs']}, total actual credits: {s['total_actual_credits']}",
                  f"- by type: {s['jobs_by_type']}", f"- by status: {s['jobs_by_status']}", ""]
    if m["options"].get("compare_estimate"):
        b = ds.get("pricing_basis") or {}
        rate = f"{s['match_rate']:.1%}" if s["match_rate"] is not None else "n/a"
        lines += ["## Estimate vs actual", "",
                  f"- comparable jobs: {s['comparable']}, matches (|diff| <= {b.get('tolerance_credits')} credits): "
                  f"{s['matches']} -> match rate {rate}",
                  f"- pricing: /job-sets/costs version {b.get('job_costs_version')}, {b.get('priced_models')} models"]
        lines += [f"- {n}" for n in b.get("notes") or []]
        if ds["comparison_summary"]:
            lines += ["", "| job_set_type | jobs | comparable | matches | match rate | exact | approx | unpriced | "
                          "mean diff | actual | estimated |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
            for gr in ds["comparison_summary"]:
                mr = f"{gr['match_rate']:.0%}" if gr["match_rate"] is not None else "n/a"
                lines.append(f"| {gr['job_set_type']} | {gr['jobs']} | {gr['comparable']} | {gr['matches']} | {mr} | "
                             f"{gr['exact_estimates']} | {gr['approximate_estimates']} | {gr['unpriced']} | "
                             f"{gr['mean_diff']} | {gr['total_actual_credits']} | {gr['total_estimated_credits']} |")
        mism = [c for c in ds["estimate_comparison"] if c["comparable"] and not c["match"]][:20]
        if mism:
            lines += ["", "### Mismatches (first 20)", "", "| job_set_type | actual | estimated | diff | basis |",
                      "|---|---:|---:|---:|---|"]
            lines += [f"| {c['job_set_type']} | {c['actual_credits']} | {c['estimated_credits']} | {c['diff']} | "
                      f"{(c.get('quantity_basis') or '').replace('|', '/')} |" for c in mism]
        lines.append("")
    if m.get("limits_hit"):
        lines += ["## Limits hit", ""] + [f"- {x}" for x in m["limits_hit"]] + [""]
    if m.get("warnings"):
        lines += ["## Warnings", ""] + [f"- {x}" for x in m["warnings"]] + [""]
    return "\n".join(lines)


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    return write_standard_outputs(ds, out_dir, json_parts=json_parts(ds), csv_tables=csv_tables(ds),
                                  dataset_model=AccountDataset, summary_md=summary_md(ds))
