"""Write the assembled dataset: nested JSON, per-section JSON, complete flat CSVs, JSON Schema and a Markdown summary.

CSV rule: **nothing is dropped**. Every CSV row is the full JSON object flattened:
  * nested objects  -> dotted columns   (pricing.after_offer.per_month, entitlement.caps.concurrency.count)
  * lists           -> JSON text in one cell (["seedance_2_5", "kling3_0"])
  * null            -> empty cell
Child lists that are their own table (plans in a plan set, price points of a model, rows of a benefit section, …)
go to their own CSV with the parent's keys repeated, so every JSON leaf exists in exactly one CSV.
Columns = union over all rows, key columns first, then in first-seen order.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from .run.logging_setup import emit
from .schemas import Dataset

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ helpers
def _dump(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    return path


def flatten(obj: Any, prefix: str = "", out: dict | None = None) -> dict[str, Any]:
    """{'a': {'b': 1}, 'c': [1, 2]} -> {'a.b': 1, 'c': '[1, 2]'}. Empty dicts become an empty cell."""
    out = {} if out is None else out
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, dict):
        out[prefix] = None
    elif isinstance(obj, list):
        out[prefix] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix] = obj
    return out


def _row(*parts: dict, **keys: Any) -> dict[str, Any]:
    """Merge parent keys + flattened parts into one row."""
    row = dict(keys)
    for p in parts:
        row.update(flatten(p))
    return row


def write_csv(path: Path, rows: Iterable[dict], first: Iterable[str] = ()) -> Path:
    rows = list(rows)
    cols = list(dict.fromkeys([c for c in first if any(c in r for r in rows)] + [k for r in rows for k in r]))
    # a null parent ("discount": null) next to its flattened children ("discount.percent_off") is just a placeholder
    cols = [c for c in cols if not (any(o.startswith(c + ".") for o in cols)
                                    and all(r.get(c) in (None, "") for r in rows))]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: Excel shows €, ≈, … correctly
        w = csv.DictWriter(f, fieldnames=cols or ["empty"], extrasaction="ignore")  # only empty placeholders dropped
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return path


def _without(d: dict, *keys: str) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


# ------------------------------------------------------------------ tables
def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    """name -> (rows, key columns). Together these tables contain every leaf of dataset.json."""
    T: dict[str, tuple[list[dict], list[str]]] = {}

    T["run_meta"] = ([{"key": k, "value": json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}
                      for k, v in flatten({"schema_version": ds["schema_version"], "meta": ds["meta"],
                                           "tab_badges": ds.get("tab_badges")}).items()], ["key"])

    T["plan_sets"] = ([_row(_without(ps, "plans")) for ps in ds["plan_sets"]], ["plan_set_key"])
    T["plans"] = ([_row(p) for ps in ds["plan_sets"] for p in ps["plans"]],
                  ["plan_set_key", "plan_type", "name", "billing_period", "credits_per_month", "seats", "currency",
                   "pricing.before_offer.per_month", "pricing.after_offer.per_month", "pricing.renewal.per_month",
                   "pricing.before_offer.total", "pricing.after_offer.total", "pricing.renewal.total",
                   "has_offer", "discount.percent_off", "discount.applies_to", "plan_id"])
    T["credit_values"] = ([_row(c) for c in ds["credit_values"]], ["plan_set_key", "plan_type", "billing_period"])

    T["models"] = ([_row(_without(m, "price_points", "entitlements"), entitlement_count=len(m["entitlements"]))
                    for m in ds["models"]], ["model_id", "display_name", "family", "category", "has_cost_data"])
    T["model_price_points"] = ([_row(pt, model_id=m["model_id"], display_name=m["display_name"], family=m["family"],
                                     category=m["category"])
                                for m in ds["models"] for pt in m["price_points"]],
                               ["model_id", "display_name", "family", "category", "component", "unit", "credits",
                                "original_credits", "discount_percent", "usd_estimate"])
    T["model_entitlements"] = ([_row(e, model_id=m["model_id"], display_name=m["display_name"])
                                for m in ds["models"] for e in m["entitlements"]],
                               ["model_id", "display_name", "plan_type", "billing_period", "tab", "type"])

    card_keys = lambda c: {"card_id": c["card_id"], "plan_type": c["plan_type"],  # noqa: E731
                           "billing_period": c["billing_period"], "tab": c["tab"]}
    T["benefit_cards"] = ([_row(_without(c, "sections"), section_count=len(c["sections"]))
                           for c in ds["benefit_cards"]], ["card_id", "plan_type", "billing_period", "tab"])
    T["benefit_sections"] = ([_row(_without(s, "rows"), **card_keys(c), row_count=len(s["rows"]))
                              for c in ds["benefit_cards"] for s in c["sections"]],
                             ["card_id", "plan_type", "billing_period", "tab", "section_id", "kind", "title"])
    T["benefit_rows"] = ([_row(r, **card_keys(c), section_id=s["section_id"])
                          for c in ds["benefit_cards"] for s in c["sections"] for r in s["rows"]],
                         ["plan_type", "billing_period", "tab", "section_id", "row_id", "label", "model_ids",
                          "entitlement.type", "entitlement.count", "entitlement.duration_days"])

    cmp_keys = lambda c: {"comparison_id": c["comparison_id"], "plan_set_key": c["plan_set_key"],  # noqa: E731
                          "billing_period": c["billing_period"]}
    T["comparisons"] = ([_row(_without(c, "plans", "categories"), plan_count=len(c["plans"]),
                              category_count=len(c["categories"])) for c in ds["comparisons"]],
                        ["comparison_id", "plan_set_key", "billing_period"])
    T["comparison_plans"] = ([_row(p, **cmp_keys(c)) for c in ds["comparisons"] for p in c["plans"]],
                             ["plan_set_key", "billing_period", "plan_type", "name", "credits", "seats"])
    T["comparison_categories"] = ([_row(_without(cat, "features"), **cmp_keys(c), feature_count=len(cat["features"]))
                                   for c in ds["comparisons"] for cat in c["categories"]],
                                  ["plan_set_key", "billing_period", "slug", "name"])
    T["comparison_matrix"] = ([_row(_without(f, "values"), v, **cmp_keys(c), category=cat["slug"], feature=f["name"])
                               for c in ds["comparisons"] for cat in c["categories"] for f in cat["features"]
                               for v in f["values"]],
                              ["plan_set_key", "billing_period", "category", "feature", "detail", "credits", "per",
                               "approx", "plan_type", "raw", "available", "quantity", "quantity_unit"])

    mk_keys = lambda m: {"marketing_id": m["marketing_id"], "config_version": m["config_version"],  # noqa: E731
                         "billing_period": m["billing_period"], "plan_type": m["plan_type"]}
    T["marketing_plans"] = ([_row(_without(m, "main_features", "feature_groups", "promo_items"),
                                  main_feature_count=len(m["main_features"]), group_count=len(m["feature_groups"]))
                             for m in ds["marketing"]],
                            ["config_version", "billing_period", "plan_type", "tagline", "credits_amount", "credits_label"])
    T["marketing_promo_items"] = ([_row(pi, **mk_keys(m), position=i) for m in ds["marketing"]
                                   for i, pi in enumerate(m["promo_items"])],
                                  ["config_version", "billing_period", "plan_type", "position"])
    T["marketing_features"] = (
        [_row(f, **mk_keys(m), group="main", group_title=None, position=i)
         for m in ds["marketing"] for i, f in enumerate(m["main_features"])]
        + [_row(f, **mk_keys(m), group=g["group_id"], group_title=g["title"], position=i)
           for m in ds["marketing"] for g in m["feature_groups"] for i, f in enumerate(g["features"])],
        ["config_version", "billing_period", "plan_type", "group", "group_title", "position", "feature_id", "text",
         "status"])

    T["auth_credit_packages"] = ([_row(p) for p in ds["auth"]["credit_packages"]], ["package_id"])
    T["auth_payloads"] = ([_row(p) for p in ds["auth"]["payloads"]], ["endpoint", "status"])
    return T


# ------------------------------------------------------------------ summary
def _summary_md(ds: dict) -> str:
    meta = ds["meta"]
    L = [f"# Higgsfield pricing snapshot — {meta['scraped_at']}", "",
         f"- Run: `{meta.get('run_id')}`  label: `{meta.get('label')}`",
         f"- Country (by IP): **{meta.get('country_code')}**, currency **{meta.get('currency')}**, plan sets: {', '.join(meta['plan_set_keys'])}",
         f"- Model costs version: `{meta.get('costs_version')}`  marketing config: `{meta.get('marketing_latest_version')}`",
         "- Counts: " + ", ".join(f"{k}={v}" for k, v in meta["counts"].items()), ""]
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


# ------------------------------------------------------------------ main
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
        _dump(out_dir / "json" / "meta.json", {"schema_version": ds["schema_version"], "meta": ds["meta"],
                                                 "tab_badges": ds.get("tab_badges")}),
        _dump(out_dir / "schema" / "dataset.schema.json", Dataset.model_json_schema(mode="serialization")),
    ]
    for name, (rows, first) in csv_tables(ds).items():
        files.append(write_csv(out_dir / "csv" / f"{name}.csv", rows, first))
    md = out_dir / "summary.md"
    md.write_text(_summary_md(ds), encoding="utf-8")
    files.append(md)
    emit(log, "info", "output.written", f"wrote {len(files)} output files to {out_dir}", files__count=len(files),
         output__dir=str(out_dir))
    return files
