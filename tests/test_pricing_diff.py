import copy
import json

import pytest

from higgsfield_scraper import pricing_diff as pdiff
from higgsfield_scraper.assemble import build_dataset
from higgsfield_scraper.cli import main
from higgsfield_scraper.parsers import keep, parse_envelope
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.validation import validate_entity


@pytest.fixture(scope="module")
def base():
    """A dataset.json-shaped dict built from the captured fixtures (ps_a3 + default)."""
    from collections import defaultdict
    from pathlib import Path
    fixtures = Path(__file__).parent / "fixtures" / "raw"
    sel = Selection.build(sections="all", plan_sets="ps_a3,default")
    ents = defaultdict(list)
    for p in sorted(fixtures.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                ents[v["kind"]].append(v)
    ds = build_dataset(ents, sel, run_id="old", label="t")
    return json.loads(json.dumps(ds, default=str))            # same types as output/dataset.json


def _plan(ds, key="ps_a3", ptype="plus", period="monthly"):
    return next(p for ps in ds["plan_sets"] if ps["plan_set_key"] == key for p in ps["plans"]
                if p["plan_type"] == ptype and p["billing_period"] == period)


def test_identical_datasets_have_no_changes(base):
    d = pdiff.diff_datasets(base, copy.deepcopy(base))
    assert d["changed"] is False and d["summary"] == {} and d["warnings"] == []
    assert pdiff.render_markdown(d).count("No changes.") == 1


def test_plan_price_credit_and_discount_changes(base):
    new = copy.deepcopy(base)
    p = _plan(new)
    old_after = _plan(base)["pricing"]["after_offer"]["per_month"]
    p["pricing"]["after_offer"]["per_month"] = "50.00"
    p["discount"] = {**(p["discount"] or {}), "percent_off": 12.5}
    team = _plan(new, ptype="team", period="annual")
    team["credits_per_month"] += 500
    d = pdiff.diff_datasets(base, new)
    assert d["changed"] is True
    pc = next(x for x in d["plans"]["price_changes"] if x["field"] == "after_offer.per_month")
    assert (pc["old"], pc["new"], pc["plan_set_key"]) == (old_after, "50.00", "ps_a3")
    from decimal import Decimal
    assert Decimal(pc["abs_change"]) == Decimal("50.00") - Decimal(old_after)
    assert pc["pct_change"] == round(float((Decimal("50") - Decimal(old_after)) / Decimal(old_after) * 100), 2)
    cc = d["plans"]["credit_changes"]
    assert len(cc) == 1 and cc[0]["new"] - cc[0]["old"] == 500           # paired, not added + removed
    assert not d["plans"]["added"] and not d["plans"]["removed"]
    assert any(x["field"] == "percent_off" and x["new"] == 12.5 for x in d["offers"]["discount_changes"])


def test_plans_added_removed_and_special_offer(base):
    new = copy.deepcopy(base)
    ps = next(ps for ps in new["plan_sets"] if ps["plan_set_key"] == "default")
    gone = ps["plans"].pop(0)
    extra = copy.deepcopy(ps["plans"][0])
    extra["plan_type"] = "mega"
    ps["plans"].append(extra)
    ps["special_offer"] = {"id": "bf", "ends_at": "2026-11-26T00:00:00Z"}
    d = pdiff.diff_datasets(base, new)
    assert [x["plan_type"] for x in d["plans"]["added"]] == ["mega"]
    assert [x["plan_type"] for x in d["plans"]["removed"]] == [gone["plan_type"]]
    so = d["offers"]["special_offer_changes"]
    assert so == [{"plan_set_key": "default", "field": None, "old": None,
                   "new": {"id": "bf", "ends_at": "2026-11-26T00:00:00Z"}}]


def test_model_changes(base):
    new = copy.deepcopy(base)
    m = next(m for m in new["models"] if m["model_id"] == "seedance_2_5")
    pt = next(p for p in m["price_points"] if p["credits"])
    before = pt["credits"]
    pt["credits"] = before * 2
    m["options"]["resolution"] = [*m["options"].get("resolution", []), "8k"]
    removed = new["models"].pop(next(i for i, x in enumerate(new["models"]) if x["model_id"] != "seedance_2_5"))
    new["models"].append({**copy.deepcopy(m), "model_id": "brand_new", "display_name": "Brand New"})
    d = pdiff.diff_datasets(base, new, only=["models"])
    assert set(d) >= {"models"} and "plans" not in d
    ch = next(x for x in d["models"]["credit_changes"] if x["model_id"] == "seedance_2_5" and x["field"] == "credits")
    assert ch["dimensions"] == pt["dimensions"] and ch["pct_change"] == 100.0
    assert any(x["model_id"] == "seedance_2_5" and x["added"] == ["8k"] for x in d["models"]["option_changes"])
    assert [x["model_id"] for x in d["models"]["added"]] == ["brand_new"]
    assert [x["model_id"] for x in d["models"]["removed"]] == [removed["model_id"]]
    # --min-change hides the +100 % change only above the threshold
    assert pdiff.diff_datasets(base, new, only=["models"], min_change=150)["models"]["credit_changes"] == []


def test_benefit_changes(base):
    new = copy.deepcopy(base)
    card = next(c for c in new["benefit_cards"] if c["free_gens"])
    card["unlimited_model_ids"] = [*card["unlimited_model_ids"], "kling3_0"]
    card["free_gens"][0]["count"] = (card["free_gens"][0]["count"] or 0) + 10
    d = pdiff.diff_datasets(base, new, only=["benefits"])
    u = d["benefits"]["unlimited_changes"]
    assert len(u) == 1 and u[0]["added"] == ["kling3_0"] and u[0]["plan_type"] == card["plan_type"]
    f = d["benefits"]["free_gen_changes"]
    assert f and f[0]["status"] == "changed" and f[0]["new_count"] - f[0]["old_count"] == 10


def test_meta_country_and_costs_version_warn(base):
    new = copy.deepcopy(base)
    new["meta"]["country_code"] = "XX"
    new["meta"]["costs_version"] = "other"
    d = pdiff.diff_datasets(base, new)
    assert d["changed"] and d["meta"]["costs_version"]["changed"] and d["meta"]["country_code"]["changed"]
    assert any("not comparable" in w for w in d["warnings"])


def test_plan_set_mismatch_compares_intersection(base):
    new = copy.deepcopy(base)
    new["plan_sets"] = [ps for ps in new["plan_sets"] if ps["plan_set_key"] == "ps_a3"]
    new["meta"]["plan_set_keys"] = ["ps_a3"]
    d = pdiff.diff_datasets(base, new)
    assert not d["plans"]["removed"]                           # 'default' is not compared, not "removed"
    assert any("plan sets differ" in w for w in d["warnings"])


def test_bad_only_and_non_pricing_run(base):
    with pytest.raises(ValueError):
        pdiff.diff_datasets(base, base, only=["prices"])
    other = {**base, "meta": {**base["meta"], "scraper": "community"}}
    with pytest.raises(ValueError):
        pdiff.diff_datasets(base, other)


def _write_run(root, name, ds, plan_sets=("ps_a3", "default"), status="success"):
    d = root / name
    (d / "output").mkdir(parents=True)
    (d / "output" / "dataset.json").write_text(json.dumps(ds, indent=4), "utf-8")
    sel = {"sections": ["plans", "compare", "benefits", "models", "marketing"], "plan_set_keys": list(plan_sets),
           "billing_periods": ["monthly", "annual"], "plan_types": [], "models": [], "categories": [],
           "include_hidden_plans": False}
    (d / "manifest.json").write_text(json.dumps({"status": status, "scraper": "pricing", "selection": sel}), "utf-8")
    with (root / "index.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": name, "scraper": "pricing", "status": status}) + "\n")
    return d


def test_resolve_pair_and_cli(tmp_path, base, capsys):
    new = copy.deepcopy(base)
    _plan(new)["pricing"]["renewal"]["per_month"] = "99.00"
    a = _write_run(tmp_path, "20260101-000000_a", base)
    _write_run(tmp_path, "20260102-000000_us", base, plan_sets=("ps_a3",))       # incompatible selection
    _write_run(tmp_path, "20260103-000000_bad", base, status="failure")          # not successful
    c = _write_run(tmp_path, "20260104-000000_c", new)
    assert pdiff.resolve_pair(tmp_path, None, None) == (a, c)

    out = tmp_path / "report.json"
    assert main(["diff", "--runs-dir", str(tmp_path), "--json", "--out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["changed"] is True and printed == json.loads(out.read_text("utf-8"))
    assert out.read_text("utf-8").startswith("{\n    \"old\"")                     # indent=4
    md = tmp_path / "report.md"
    assert main(["diff", "--runs-dir", str(tmp_path), "--out", str(md)]) == 0
    assert "renewal.per_month" in md.read_text("utf-8")
    assert main(["diff", "--runs-dir", str(tmp_path), "--only", "nope"]) == 2
    assert main(["diff", "--runs-dir", str(tmp_path), "--out", str(tmp_path / "x.txt")]) == 2
    assert main(["diff", "--runs-dir", str(tmp_path / "empty")]) == 1
