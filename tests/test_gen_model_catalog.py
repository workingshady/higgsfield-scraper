"""Offline tests for scripts/gen_model_catalog.py (no network, tiny in-memory fixtures)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("gen_model_catalog", ROOT / "scripts" / "gen_model_catalog.py")
gmc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gmc)

SEEDANCE_COST = [{"resolution": "480p", "video": {"with_video": {"cost_per_second": 3}, "without_video": {"cost_per_second": 3}}},
                 {"resolution": "720p", "video": {"with_video": {"cost_per_second": 7}, "without_video": {"cost_per_second": 7}}}]


@pytest.mark.parametrize("jst,provider", [
    ("seedance_2_5", "ByteDance (Seed)"),
    ("kling4_0", "Kuaishou (Kling)"),
    ("gpt_image_2_6", "OpenAI (GPT Image)"),
    ("nano_banana_2_1", "Google (Gemini image)"),
    ("wan3_0", "Alibaba (Wan)"),
    ("grok_video_v15", "xAI (Grok Imagine)"),
    ("topaz_video", "Topaz Labs"),
    ("text2image_soul_v2", gmc.IN_HOUSE),
])
def test_provider_map(jst, provider):
    assert gmc.provider_for(jst)[0] == provider


@pytest.mark.parametrize("jst,ver", [("seedance_2_5", "2.5"), ("kling3_0", "3.0"), ("wan2_5_video", "2.5"),
                                     ("seedream_v5_pro", "5"), ("image2video", ""), ("3d_jutsu_angles", "")])
def test_version_of(jst, ver):
    assert gmc.version_of(jst) == ver


def test_build_rows_joins_sources_and_finds_price_twins():
    costs = {"seedance_2_5": {"job_set_type": "seedance_2_5", "cost": SEEDANCE_COST},
             "intone": {"job_set_type": "intone", "cost": SEEDANCE_COST}}
    models = {"seedance_2_5": {"model_id": "seedance_2_5", "display_name": "Seedance 2.5", "family": "seedance",
                               "category": "video", "units": ["credits_per_second"], "min_credits": 3,
                               "max_credits": 7, "has_cost_data": True}}
    defs = {"seedance_2_5": "video", "magi_2": "video"}
    routes = {"seedance_2_5": "/jobs/v2/seedance_2_5"}
    rows = {r["job_set_type"]: r for r in gmc.build_rows(costs, models, defs, routes, {"magi_2": "MAGI-2"})}
    assert set(rows) == {"seedance_2_5", "intone", "magi_2"}
    s = rows["seedance_2_5"]
    assert s["in_costs"] and s["in_js"] and s["route"] == "/jobs/v2/seedance_2_5"
    assert s["price"] == "3–7 cr/second" and s["same_price_as"] == "intone"
    assert rows["magi_2"]["display_name"] == "MAGI-2" and rows["magi_2"]["route"] == "/jobs/magi-2 *"
    assert not rows["intone"]["in_js"] and rows["intone"]["same_price_as"] == "seedance_2_5"


def test_render_and_replace_block(tmp_path):
    rows = gmc.build_rows({"gif": {"job_set_type": "gif", "cost": []}}, {}, {}, {})
    block = gmc.render(rows, "test")
    assert "| `gif` |" in block and "Costs-only" in block and "`gif`" in block.split("Costs-only")[1]
    doc = f"head\n{gmc.BEGIN}\nold\n{gmc.END}\ntail\n"
    out = gmc.replace_block(doc, block)
    assert "old" not in out and out.startswith("head\n") and out.endswith("tail\n")


def test_scan_js_reads_defs_routes_titles(tmp_path):
    (tmp_path / "a.js").write_text(
        'P({type:`seedance_2_5`,output:`video`});m={seedance_2_5:`v2/seedance_2_5`,keyframes_faceswap:`face-swap`};'
        'x={id:`magi_2`,title:`MAGI-2`}', encoding="utf-8")
    defs, routes, titles = gmc.scan_js(tmp_path)
    assert defs == {"seedance_2_5": "video"}
    assert routes["keyframes_faceswap"] == "/jobs/face-swap"
    assert titles["magi_2"] == "MAGI-2"


def test_load_costs_accepts_envelope(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"data": [{"job_set_type": "gif", "cost": []}], "version": "x"}), encoding="utf-8")
    assert list(gmc.load_costs(p)) == ["gif"]
