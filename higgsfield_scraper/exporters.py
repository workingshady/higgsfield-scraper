"""Write the assembled dataset: nested JSON, per-section JSON, flat CSVs, JSON Schema and a Markdown summary."""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from .schemas import Dataset

log = logging.getLogger(__name__)


def _dump(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    return path


def _csv(path: Path, rows: Iterable[dict], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                        for k, v in r.items()})
    return path


PLAN_FIELDS = [
    "plan_set_key", "country_code", "plan_type", "name", "audience", "billing_period", "credits_per_month", "seats",
    "currency", "before_offer_per_month", "after_offer_per_month", "renewal_per_month", "before_offer_total",
    "after_offer_total", "renewal_total", "has_offer", "discount_percent", "discount_applies_to", "savings_total",
    "savings_percent", "usd_per_credit_after_offer", "unlimited_models", "stripe_price_id", "plan_id",
]


def _plan_rows(ds: dict):
    for ps in ds["plan_sets"]:
        for p in ps["plans"]:
            pr, d = p["pricing"], p.get("discount") or {}
            yield {
                "plan_set_key": p["plan_set_key"], "country_code": p["country_code"], "plan_type": p["plan_type"],
                "name": p["name"], "audience": p["audience"], "billing_period": p["billing_period"],
                "credits_per_month": p["credits_per_month"], "seats": p["seats"], "currency": p["currency"],
                "before_offer_per_month": pr["before_offer"]["per_month"], "after_offer_per_month": pr["after_offer"]["per_month"],
                "renewal_per_month": pr["renewal"]["per_month"], "before_offer_total": pr["before_offer"]["total"],
                "after_offer_total": pr["after_offer"]["total"], "renewal_total": pr["renewal"]["total"],
                "has_offer": p["has_offer"], "discount_percent": d.get("percent_off"), "discount_applies_to": d.get("applies_to"),
                "savings_total": p["savings"]["total"], "savings_percent": p["savings"]["percent"],
                "usd_per_credit_after_offer": p["price_per_credit"]["after_offer"],
                "unlimited_models": ";".join(p["unlimited_model_ids"]), "stripe_price_id": p["stripe_price_id"],
                "plan_id": p["plan_id"],
            }


def _point_rows(ds: dict):
    for m in ds["models"]:
        for pt in m["price_points"]:
            yield {"model_id": m["model_id"], "display_name": m["display_name"], "family": m["family"],
                   "category": m["category"], "component": pt["component"], **{f"dim_{k}": v for k, v in pt["dimensions"].items()},
                   "dimensions": pt["dimensions"], "unit": pt["unit"], "credits": pt["credits"],
                   "original_credits": pt["original_credits"], "discount_percent": pt["discount_percent"],
                   "example": pt["example"], "usd_estimate": pt["usd_estimate"], "formula": (pt.get("formula") or {}).get("name"),
                   "point_id": pt["point_id"]}


def _benefit_rows(ds: dict):
    for c in ds["benefit_cards"]:
        for s in c["sections"]:
            for r in s["rows"]:
                e, caps = r["entitlement"], r["entitlement"].get("caps") or {}
                yield {"plan_type": c["plan_type"], "billing_period": c["billing_period"], "tab": c["tab"],
                       "section": s["section_id"], "row_id": r["row_id"], "label": r["label"],
                       "model_ids": ";".join(r["model_ids"]), "entitlement": e["type"], "count": e["count"],
                       "duration_days": e["duration_days"], "max_resolution": caps.get("max_resolution"),
                       "max_duration_s": caps.get("max_duration_s"), "concurrency": caps.get("concurrency"),
                       "starts": e["starts"], "requirements": ";".join(e["requirements"])}


def _comparison_rows(ds: dict):
    for c in ds["comparisons"]:
        for cat in c["categories"]:
            for f in cat["features"]:
                for v in f["values"]:
                    yield {"plan_set_key": c["plan_set_key"], "billing_period": c["billing_period"], "category": cat["slug"],
                           "feature": f["name"], "detail": f["detail"], "credits": f["credits"], "per": f["per"],
                           "approx": f["approx"], "plan_type": v["plan_type"], "value": v["raw"],
                           "available": v["available"], "quantity": v["quantity"], "quantity_unit": v["quantity_unit"]}


def _marketing_rows(ds: dict):
    for m in ds["marketing"]:
        groups = [("main", None, m["main_features"])] + [(g["group_id"], g["title"], g["features"]) for g in m["feature_groups"]]
        for gid, title, feats in groups:
            for f in feats:
                yield {"config_version": m["config_version"], "billing_period": m["billing_period"], "plan_type": m["plan_type"],
                       "group": gid, "group_title": title, "feature_id": f["feature_id"], "text": f["text"],
                       "status": f["status"], "tooltip": f["tooltip"]}


def _summary_md(ds: dict) -> str:
    meta = ds["meta"]
    L = [f"# Higgsfield pricing snapshot — {meta['scraped_at']}", "",
         f"- Run: `{meta.get('run_id')}`  label: `{meta.get('label')}`",
         f"- Country (by IP): **{meta.get('country_code')}**, currency **{meta.get('currency')}**, plan sets: {', '.join(meta['plan_set_keys'])}",
         f"- Model costs version: `{meta.get('costs_version')}`  marketing config: `{meta.get('marketing_latest_version')}`",
         f"- Counts: " + ", ".join(f"{k}={v}" for k, v in meta["counts"].items()), ""]
    if meta.get("warnings"):
        L += ["**Warnings:**", *[f"- {w}" for w in meta["warnings"]], ""]
    for ps in ds["plan_sets"]:
        L += [f"## Plans — plan set `{ps['plan_set_key']}`", "",
              "| Plan | Billing | Credits/mo | Seats | Before offer /mo | After offer /mo | Renewal /mo | Discount | $/credit |",
              "|---|---|---:|---:|---:|---:|---:|---|---:|"]
        for p in ps["plans"]:
            pr, d = p["pricing"], p.get("discount") or {}
            disc = f"{d.get('percent_off')}% {d.get('applies_to')}" if d else "—"
            L.append(f"| {p['name']} | {p['billing_period']} | {p['credits_per_month']:,} | {p['seats'] or ''} | "
                     f"${pr['before_offer']['per_month']} | **${pr['after_offer']['per_month']}** | ${pr['renewal']['per_month']} | "
                     f"{disc} | {p['price_per_credit']['after_offer']} |")
        L.append("")
    if ds["models"]:
        ref = meta.get("usd_reference") or {}
        L += [f"## Models ({len(ds['models'])}) — cheapest option per model",
              f"USD estimate at {ref.get('plan_type')} {ref.get('billing_period')} after-offer rate (${ref.get('usd_per_credit')}/credit)", "",
              "| Model | id | Category | Unit | Min credits | Example | ≈ USD | Options |", "|---|---|---|---|---:|---|---:|---|"]
        for m in sorted(ds["models"], key=lambda m: (m["category"], m["model_id"])):
            pts = [p for p in m["price_points"] if p["credits"] is not None]
            best = min(pts, key=lambda p: p["credits"]) if pts else None
            opts = "; ".join(f"{k}: {'/'.join(map(str, v))}" for k, v in m["options"].items())
            ex = best and best.get("example")
            L.append(f"| {m['display_name']} | `{m['model_id']}` | {m['category']} | {best['unit'] if best else ''} | "
                     f"{best['credits'] if best else ''} | {ex or ''} | {best['usd_estimate'] if best else ''} | {opts} |")
        L.append("")
    return "\n".join(L)


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    files = [
        _dump(out_dir / "dataset.json", ds),
        _dump(out_dir / "json" / "plans.json", [p for ps in ds["plan_sets"] for p in ps["plans"]]),
        _dump(out_dir / "json" / "plan_sets.json", [{k: v for k, v in ps.items() if k != "plans"} for ps in ds["plan_sets"]]),
        _dump(out_dir / "json" / "credit_values.json", ds["credit_values"]),
        _dump(out_dir / "json" / "models.json", ds["models"]),
        _dump(out_dir / "json" / "benefit_cards.json", ds["benefit_cards"]),
        _dump(out_dir / "json" / "comparisons.json", ds["comparisons"]),
        _dump(out_dir / "json" / "marketing.json", ds["marketing"]),
        _dump(out_dir / "json" / "auth.json", ds["auth"]),
        _dump(out_dir / "schema" / "dataset.schema.json", Dataset.model_json_schema(mode="serialization")),
    ]
    point_rows = list(_point_rows(ds))
    dim_cols = sorted({k for r in point_rows for k in r if k.startswith("dim_")})
    files += [
        _csv(out_dir / "csv" / "plans.csv", _plan_rows(ds), PLAN_FIELDS),
        _csv(out_dir / "csv" / "model_price_points.csv", point_rows,
             ["model_id", "display_name", "family", "category", "component", *dim_cols, "unit", "credits",
              "original_credits", "discount_percent", "example", "usd_estimate", "formula", "dimensions", "point_id"]),
        _csv(out_dir / "csv" / "models.csv", ds["models"],
             ["model_id", "display_name", "family", "category", "units", "options", "components", "price_point_count",
              "has_cost_data", "has_discount", "min_credits", "max_credits"]),
        _csv(out_dir / "csv" / "model_entitlements.csv",
             ({"model_id": m["model_id"], **e} for m in ds["models"] for e in m["entitlements"]),
             ["model_id", "plan_type", "billing_period", "tab", "type", "count", "duration_days", "max_resolution",
              "max_duration_s", "concurrency", "starts", "requirements", "benefit_label"]),
        _csv(out_dir / "csv" / "benefit_rows.csv", _benefit_rows(ds),
             ["plan_type", "billing_period", "tab", "section", "row_id", "label", "model_ids", "entitlement", "count",
              "duration_days", "max_resolution", "max_duration_s", "concurrency", "starts", "requirements"]),
        _csv(out_dir / "csv" / "comparison_matrix.csv", _comparison_rows(ds),
             ["plan_set_key", "billing_period", "category", "feature", "detail", "credits", "per", "approx", "plan_type",
              "value", "available", "quantity", "quantity_unit"]),
        _csv(out_dir / "csv" / "credit_values.csv", ds["credit_values"],
             ["plan_id", "plan_set_key", "plan_type", "billing_period", "credits_per_month", "usd_per_credit_before_offer",
              "usd_per_credit_after_offer", "credits_per_usd_after_offer"]),
        _csv(out_dir / "csv" / "marketing_features.csv", _marketing_rows(ds),
             ["config_version", "billing_period", "plan_type", "group", "group_title", "feature_id", "text", "status", "tooltip"]),
    ]
    md = out_dir / "summary.md"
    md.write_text(_summary_md(ds), encoding="utf-8")
    files.append(md)
    log.info("wrote %d output files to %s", len(files), out_dir)
    return files
