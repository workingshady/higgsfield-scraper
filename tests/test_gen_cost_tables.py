"""scripts/gen_cost_tables.py on the captured /job-sets/costs fixture (offline)."""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "raw" / "job_costs.json"


def _load():
    spec = importlib.util.spec_from_file_location("gen_cost_tables", ROOT / "scripts" / "gen_cost_tables.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rate_tables_cover_every_model():
    g = _load()
    models = g.load_models(costs=FIXTURE)
    md = g.rate_tables(models, dict(g.DEFAULT_USD))
    for m in models:
        if m["price_points"]:
            assert f"`{m['model_id']}`" in md
    # Seedance 2.5 1080p without video: 16 credits/s -> 80 for 5 s -> $2.00 at $0.025
    assert "| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |" in md
    assert "$2.0000" in md


def test_variations_follow_js_rounding():
    g = _load()
    models = g.load_models(costs=FIXTURE)
    md = g.variations(models, dict(g.DEFAULT_USD), only={"seedance_2_5", "seedance_2_5_flash", "gpt_image_2_6"})
    assert "`ceil(10 × 34) = 340`" in md                    # 4k with a reference video
    assert "`ceil(10 × 28) × 4 = 1120`" in md               # batch 4
    assert "`ceil(12 × 20) = 240`" in md                    # edit, 12 s source at 1080p
    assert "`ceil(5 × 2.5) = 13`" in md                     # Flash 480p with video: 12.5 rounds up
    assert "ceil₀.₀₁(4 × " in md                            # GPT Image batch 4


def test_rounding_helpers():
    g = _load()
    assert g.ceil_cent(Decimal("12.341")) == Decimal("12.35")
    assert g.ceil_cent(Decimal("7.5")) == Decimal("7.5")
    eq, v = g.per_second("ceil_dur", Decimal("5.4"), Decimal("7"), 1)
    assert v == 42 and eq.startswith("ceil(5.4)")


def test_replace_between_is_idempotent():
    g = _load()
    doc = "intro\n<!-- BEGIN cost-tables -->\nold\n<!-- END cost-tables -->\ntail\n"
    once = g.replace_between(doc, g.TABLE_MARKERS, "new")
    assert once == g.replace_between(once, g.TABLE_MARKERS, "new")
    assert "old" not in once and once.endswith("tail\n")
