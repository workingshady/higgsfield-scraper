import copy
import json
from pathlib import Path

import pytest

from higgsfield_scraper import pricing_crosscheck as pcc
from higgsfield_scraper.assemble import build_dataset
from higgsfield_scraper.parsers import keep, parse_envelope
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures"
MD = (FIX / "pricing_md" / "pricing.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ds():
    from collections import defaultdict
    sel = Selection.build(sections="all", plan_sets="ps_a3")
    ents = defaultdict(list)
    for p in sorted((FIX / "raw").glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                ents[v["kind"]].append(v)
    return json.loads(json.dumps(build_dataset(ents, sel, run_id="t", label="t"), default=str))


def test_parse_price_cells():
    assert pcc.parse_price_cell("$19/mo", "monthly") == {
        "after_offer.per_month": "19", "renewal.per_month": "19", "before_offer.per_month": "19"}
    assert pcc.parse_price_cell("$40 first month, then $59/mo", "monthly") == {
        "after_offer.per_month": "40", "renewal.per_month": "59", "before_offer.per_month": "59"}
    assert pcc.parse_price_cell("$55/mo (list price $79/mo)", "monthly") == {
        "after_offer.per_month": "55", "renewal.per_month": "55", "before_offer.per_month": "79"}
    a = pcc.parse_price_cell("$45/mo, billed $539.98 yearly (list price $79/mo)", "annual")
    assert a["after_offer.total"] == a["renewal.total"] == "539.98" and a["before_offer.per_month"] == "79"
    assert "before_offer.total" not in a                       # not stated -> not compared
    assert pcc.parse_price_cell("$1,380/mo", "monthly")["after_offer.per_month"] == "1380"
    assert pcc.parse_price_cell("call us", "monthly") == {}


def test_parse_pricing_md_fixture():
    p = pcc.parse_pricing_md(MD)
    assert p["last_updated"] == "2026-11-25" and p["offer_ends_at"] == "2026-11-26 00:00"
    types = {(x["plan_type"], x["billing_period"], x["credits_per_month"]) for x in p["plans"]}
    assert {("starter", "monthly", 270), ("ultra", "annual", 9000), ("team", "annual", 1000),
            ("scale", "monthly", 2500)} <= types
    team = next(x for x in p["plans"] if x["plan_type"] == "team" and x["billing_period"] == "monthly")
    assert team["per_seat"] and team["audience"] == "business"
    assert p["custom_pricing"] == ["enterprise"]
    assert p["models"] == []                                    # pricing.md lists no per-model credit costs
    soul = next(b for b in p["benefits"] if b["plan_type"] == "plus" and b["billing_period"] == "annual"
                and b["label"] == "Soul V2 & Cinema")
    assert (soul["status"], soul["count"]) == ("free_gens", 5000)
    nbp = next(b for b in p["benefits"] if b["plan_type"] == "plus" and b["billing_period"] == "annual"
               and b["label"] == "Nano Banana Pro")
    assert (nbp["status"], nbp["duration_days"], nbp["max_resolution"]) == ("unlimited", 7, "2K")


def test_parse_benefit_detail():
    assert pcc.parse_benefit_detail("No unlimited")["status"] == "none"
    assert pcc.parse_benefit_detail("On annual plan only")["status"] == "none"
    assert pcc.parse_benefit_detail("1K, Unlimited") | {} == {
        "status": "unlimited", "count": None, "duration_days": None, "max_resolution": "1K", "detail": "1K, Unlimited"}
    assert pcc.parse_benefit_detail("720p, 1 free gen")["count"] == 1
    assert pcc.parse_benefit_detail("Included")["status"] is None


def test_crosscheck_matches_fixture_dataset(ds):
    rep = pcc.crosscheck(pcc.parse_pricing_md(MD), ds)
    plans = rep["plans"]
    assert plans["matches"] and plans["mismatches"] == []
    assert {x["plan"] for x in plans["only_in_pricing_md"]} >= {"enterprise"}
    assert rep["models"]["note"] == "pricing.md lists no per-model credit costs"
    assert rep["benefits"]["matches"] and rep["ok"] is True
    json.dumps(rep)                                             # JSON-ready


def test_crosscheck_reports_mismatch_and_only_in_dataset(ds):
    bad = copy.deepcopy(ds)
    ps = next(p for p in bad["plan_sets"] if p["plan_set_key"] == "ps_a3")
    plus = next(p for p in ps["plans"] if p["plan_type"] == "plus" and p["billing_period"] == "annual")
    plus["pricing"]["after_offer"]["per_month"] = "31.00"
    extra = copy.deepcopy(plus)
    extra["plan_type"] = "hidden"
    ps["plans"].append(extra)
    rep = pcc.crosscheck(pcc.parse_pricing_md(MD), bad)
    mm = rep["plans"]["mismatches"]
    assert len(mm) == 1 and mm[0]["field"] == "after_offer.per_month" and mm[0]["pricing_md"] == "30"
    assert any(x["plan"].startswith("hidden/annual") for x in rep["plans"]["only_in_dataset"])
    assert rep["ok"] is False and rep["mismatch_count"] == 1


def test_model_credit_table_conservative_match(ds):
    m = next(m for m in ds["models"] if m["price_points"] and m["price_points"][0]["credits"])
    cr = m["price_points"][0]["credits"]
    md = (f"## Model costs\n\n| Model | Credits |\n| --- | --- |\n| {m['display_name']} | {cr} |\n"
          f"| {m['display_name'].upper()} | {cr + 1000} |\n| Totally Unknown Model | 5 |\n")
    p = pcc.parse_pricing_md(md)
    rep = pcc.compare_models(p["models"], ds["models"])
    assert len(rep["matches"]) == 1 and len(rep["mismatches"]) == 1
    assert rep["only_in_pricing_md"][0]["name"] == "Totally Unknown Model"


def test_crosscheck_needs_ps_a3(ds):
    other = {**ds, "plan_sets": []}
    with pytest.raises(ValueError):
        pcc.crosscheck(pcc.parse_pricing_md(MD), other)


def test_cli_crosscheck_save(tmp_path, ds, monkeypatch, capsys):
    from higgsfield_scraper.cli import main
    run = tmp_path / "20260101-000000_x"
    (run / "output").mkdir(parents=True)
    (run / "output" / "dataset.json").write_text(json.dumps(ds), "utf-8")
    (run / "manifest.json").write_text(json.dumps({"status": "success", "scraper": "pricing",
                                                   "selection": {"plan_set_keys": ["ps_a3"]}}), "utf-8")
    (tmp_path / "index.jsonl").write_text(json.dumps({"run_id": run.name, "status": "success"}) + "\n", "utf-8")
    monkeypatch.setattr(pcc, "fetch_pricing_md", lambda *a, **k: (MD, {"url": pcc.PRICING_MD_URL, "status": 200,
                                                                         "fetched_at": "2026-11-25T12:00:00Z"}))
    before = sorted(p.name for p in (run / "output").rglob("*"))
    assert main(["crosscheck", "--runs-dir", str(tmp_path), "--json", "--save"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["ok"] is True and rep["source"]["status"] == 200
    saved = sorted(p.name for p in (run / "crosscheck").iterdir())
    assert saved == ["pricing_20261125-120000.md", "report_20261125-120000.json"]
    assert (run / "crosscheck" / saved[1]).read_text("utf-8").startswith("{\n    \"source\"")
    assert sorted(p.name for p in (run / "output").rglob("*")) == before
    monkeypatch.setattr(pcc, "fetch_pricing_md", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert main(["crosscheck", "--run", str(run)]) == 1
