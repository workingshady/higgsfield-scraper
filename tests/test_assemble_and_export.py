import json
from collections import defaultdict

from higgsfield_scraper.assemble import build_dataset
from higgsfield_scraper.exporters import write_outputs
from higgsfield_scraper.parsers import keep, parse_envelope
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.validation import validate_entity


def _entities(fixtures_dir, sel):
    ents = defaultdict(list)
    for p in sorted(fixtures_dir.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                ents[v["kind"]].append(v)
    return ents


def test_build_dataset_joins(fixtures_dir, sel):
    ds = build_dataset(_entities(fixtures_dir, sel), sel, run_id="t", label="t")
    meta = ds["meta"]
    assert meta["counts"]["plans"] == 28 and meta["counts"]["models"] >= 80
    assert {ps["plan_set_key"] for ps in ds["plan_sets"]} == {"ps_a3", "default"}
    team = next(p for ps in ds["plan_sets"] for p in ps["plans"] if p["plan_type"] == "team" and p["plan_set_key"] == "ps_a3")
    assert team["seats"] == 2                                   # from /compare
    assert team["benefit_card_ids"]                             # from /plan-benefits
    assert meta["usd_reference"]["usd_per_credit"] == "0.0250"  # Plus annual US
    s25 = next(m for m in ds["models"] if m["model_id"] == "seedance_2_5")
    p720 = next(p for p in s25["price_points"] if p["dimensions"] == {"resolution": "720p", "video_input": "without_video"})
    assert p720["example"]["credits"] == 35 and p720["usd_estimate"] == 0.875
    assert any(m["entitlements"] for m in ds["models"])
    benefit_only = [m for m in ds["models"] if not m["has_cost_data"]]
    assert benefit_only and all(m["entitlements"] and not m["price_points"] for m in benefit_only)
    assert "nano_banana_2" in {m["model_id"] for m in benefit_only}     # "Nano Banana Pro" unlimited row
    assert meta["marketing_latest_version"] == "v51.0.0"


def test_sections_limit_output(fixtures_dir):
    sel = Selection.build(sections="models")
    ds = build_dataset(_entities(fixtures_dir, sel), sel)
    assert ds["models"] and not ds["plan_sets"] and not ds["benefit_cards"] and not ds["comparisons"]
    assert ds["meta"]["usd_reference"] is not None             # plans fetched only for enrichment


def test_write_outputs(tmp_path, fixtures_dir, sel):
    ds = build_dataset(_entities(fixtures_dir, sel), sel)
    files = write_outputs(ds, tmp_path)
    names = {f.relative_to(tmp_path).as_posix() for f in files}
    for n in ("dataset.json", "summary.md", "csv/plans.csv", "csv/model_price_points.csv", "csv/comparison_matrix.csv",
              "json/models.json", "schema/dataset.schema.json"):
        assert n in names
    assert json.loads((tmp_path / "dataset.json").read_text("utf-8"))["schema_version"] == 1
    header = (tmp_path / "csv" / "model_price_points.csv").read_text("utf-8-sig").splitlines()[0]
    assert "dimensions.resolution" in header and "usd_estimate" in header


def _csv_cols_and_rows(path):
    import csv
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return (set(rows[0].keys()) if rows else set()), rows


def test_csvs_contain_every_json_field(tmp_path, fixtures_dir, sel):
    """Nothing may exist only in JSON: every leaf of every object must be a column in its CSV, rows 1:1."""
    from higgsfield_scraper.exporters import flatten

    ds = build_dataset(_entities(fixtures_dir, sel), sel)
    write_outputs(ds, tmp_path)
    drop = lambda d, *ks: {k: v for k, v in d.items() if k not in ks}  # noqa: E731
    checks = {
        "plan_sets": [drop(ps, "plans") for ps in ds["plan_sets"]],
        "plans": [p for ps in ds["plan_sets"] for p in ps["plans"]],
        "credit_values": ds["credit_values"],
        "models": [drop(m, "price_points", "entitlements") for m in ds["models"]],
        "model_price_points": [pt for m in ds["models"] for pt in m["price_points"]],
        "model_entitlements": [e for m in ds["models"] for e in m["entitlements"]],
        "benefit_cards": [drop(c, "sections") for c in ds["benefit_cards"]],
        "benefit_sections": [drop(s, "rows") for c in ds["benefit_cards"] for s in c["sections"]],
        "benefit_rows": [r for c in ds["benefit_cards"] for s in c["sections"] for r in s["rows"]],
        "comparisons": [drop(c, "plans", "categories") for c in ds["comparisons"]],
        "comparison_plans": [p for c in ds["comparisons"] for p in c["plans"]],
        "comparison_categories": [drop(cat, "features") for c in ds["comparisons"] for cat in c["categories"]],
        "comparison_matrix": [{**drop(f, "values"), **v} for c in ds["comparisons"] for cat in c["categories"]
                              for f in cat["features"] for v in f["values"]],
        "marketing_plans": [drop(m, "main_features", "feature_groups", "promo_items") for m in ds["marketing"]],
        "marketing_promo_items": [pi for m in ds["marketing"] for pi in m["promo_items"]],
        "marketing_features": [f for m in ds["marketing"] for f in m["main_features"]]
                              + [f for m in ds["marketing"] for g in m["feature_groups"] for f in g["features"]],
    }
    for table, objects in checks.items():
        cols, rows = _csv_cols_and_rows(tmp_path / "csv" / f"{table}.csv")
        assert len(rows) == len(objects), table
        missing = {k for o in objects for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}  # null parent of dotted cols
        assert not missing, f"{table}.csv is missing JSON fields: {sorted(missing)[:10]}"
    meta_keys = {r["key"] for r in _csv_cols_and_rows(tmp_path / "csv" / "run_meta.csv")[1]}
    assert {"meta.country_code", "meta.counts.plans", "schema_version"} <= meta_keys


def test_meta_label_is_the_run_label_not_a_benefit_row(fixtures_dir, sel):
    """Regression: a loop over benefit-only models reused the `label` parameter, so meta.label became e.g.
    "Soul V2 & Cinema" instead of the run label."""
    ents = _entities(fixtures_dir, sel)
    ds = build_dataset(ents, sel, run_id="r", label="my-run-label")
    assert ds["meta"]["label"] == "my-run-label"
    benefit_only = [m for m in ds["models"] if not m.get("price_points")]
    assert benefit_only, "fixture should contain benefit-only models so the loop actually runs"
