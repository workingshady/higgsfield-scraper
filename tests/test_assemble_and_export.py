import json
from collections import defaultdict

from higgs_price.assemble import build_dataset
from higgs_price.exporters import write_outputs
from higgs_price.parsers import keep, parse_envelope
from higgs_price.raw import Envelope
from higgs_price.selection import Selection
from higgs_price.validation import validate_entity


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
    header = (tmp_path / "csv" / "model_price_points.csv").read_text("utf-8").splitlines()[0]
    assert "dim_resolution" in header and "usd_estimate" in header
