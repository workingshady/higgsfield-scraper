import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import pytest

from higgsfield_scraper.assemble import build_dataset
from higgsfield_scraper.parsers import keep, parse_envelope
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.validation import validate_entity

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gen_pricing_snapshot.py"


@pytest.fixture(scope="module")
def snap():
    spec = importlib.util.spec_from_file_location("gen_pricing_snapshot", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dataset():
    fixtures = Path(__file__).parent / "fixtures" / "raw"
    sel = Selection.build(sections="all", plan_sets="ps_a3")
    ents = defaultdict(list)
    for p in sorted(fixtures.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                ents[v["kind"]].append(v)
    return build_dataset(ents, sel, run_id="fixture-run", label="t")


def test_render_plans_benefits_models(snap, dataset):
    md = snap.render(dataset)
    assert "`fixture-run`" in md
    # Plus annual on ps_a3: 36000 cents -> $360.00, $30.00/mo, 50 % forever, 360 / 14,400 credits = 0.0250
    ps_a3 = md.split("plan set `ps_a3`", 1)[1]          # the fixtures also hold the `default` set
    plus = next(line for line in ps_a3.splitlines() if line.startswith("| Plus | annual |"))
    assert "$360.00 ($30.00/mo)" in plus and "all_payments" in plus and "/ 0.0250 /" in plus
    assert "| 14,400 |" in plus
    # benefits: Plus annual unlimited includes Nano Banana Pro; free gens listed
    ben = next(line for line in md.splitlines() if line.startswith("| Plus | annual | Nano Banana Pro"))
    assert "`nano_banana_2`" in ben and "×" in ben
    # model summary: Seedance 2.5 cheapest at 480p, 5 s example, priced at the plus:annual rate
    s25 = next(line for line in md.splitlines() if "`seedance_2_5`" in line)
    assert "credits_per_second" in s25 and "seconds=5" in s25 and "$0.3750" in s25
    assert "no cost data" in md                         # benefit-only models are listed


def test_insert_replaces_block_only(snap):
    doc = f"intro\n{snap.BEGIN}\nold\n{snap.END}\noutro\n"
    out = snap.insert(doc, "new\n")
    assert out == f"intro\n{snap.BEGIN}\nnew\n{snap.END}\noutro\n"
    with pytest.raises(ValueError):
        snap.insert("no markers", "x")


def test_main_writes_from_run_folder(snap, dataset, tmp_path):
    run = tmp_path / "runs" / "20990101-000000_t"
    (run / "output").mkdir(parents=True)
    (run / "output" / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    doc = tmp_path / "PRICING.md"
    doc.write_text(f"# x\n{snap.BEGIN}\n{snap.END}\n", encoding="utf-8")
    assert snap.main(["--run", str(run), "--write", str(doc)]) == 0
    text = doc.read_text(encoding="utf-8")
    assert "20990101-000000_t" in text and "| Starter | monthly |" in text
