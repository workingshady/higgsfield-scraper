"""CostEstimatorV2 (--estimate-version 2): every implemented docs/COST_FORMULAS.md §8 item, with the doc's numbers.

The live table the doc was written against (version 0cee3218…) is samples/higgsfield/model_loading/job_sets_costs.json.
Each §8 row is checked for v1 (unchanged, the "estimator" column) and v2 (the "JS" column).
"""
import json
from pathlib import Path

import pytest

from higgsfield_scraper.estimate import (ESTIMATE_VERSIONS, CostEstimator, EstimatedCost, estimator_class,
                                         formula_version_in_schema)
from higgsfield_scraper.estimate.v2 import CostEstimatorV2, ceil_cents

LIVE = Path(__file__).resolve().parents[1] / "samples" / "higgsfield" / "model_loading" / "job_sets_costs.json"
FIXTURES = Path(__file__).parent / "fixtures" / "raw"
VID12 = {"role": "video", "data": {"type": "video_input", "url": "https://cdn/v.mp4", "duration_sec": 12}}
VID = {"role": "video", "data": {"type": "video_input", "url": "https://cdn/v.mp4"}}
IMG = {"role": "image", "data": {"type": "media_input", "url": "https://cdn/x.png"}}


@pytest.fixture(scope="module")
def body():
    return json.loads(LIVE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v1(body):
    return CostEstimator.from_job_costs_body(body)


@pytest.fixture(scope="module")
def v2(body):
    return CostEstimatorV2.from_job_costs_body(body)


# --------------------------------------------------------------------------- §8 table: (item, type, params, v1, v2)
S8 = [
    ("1 Seedance Flash 480p 5 s + video", "seedance_2_5_flash", {"resolution": "480p", "duration": 5, "medias": [VID]},
     12.5, 13),
    ("2 Seedance 2.5 edit, 12 s source", "seedance_2_5", {"resolution": "1080p", "model": "video_edit",
                                                          "medias": [VID12]}, 80, 240),
    ("3 Kling 4.0 1080p 10 s batch 2", "kling4_0", {"resolution": "1080p", "duration": 10, "batch_size": 2,
                                                    "medias": []}, 75, 37.5),
    ("4 Genjutsu 720p 5.4 s", "hf_mult_motion_control", {"resolution": "720p", "duration": 5.4}, 37.8, 42),
    ("5 Reframe 720p 10 s", "reframe", {"resolution": "720p", "duration": 10, "medias": []}, 45, 49),
    ("6 MiniMax TTS 400 chars batch 2 (kept)", "text2speech_v2", {"model": "minimax", "text": "x" * 400,
                                                                  "batch_size": 2}, 2.4, 2.4),
    ("7 Qwen TTS 60 chars", "qwen_audio_tts", {"text": "x" * 60}, 0.0257, 0.03),
    ("8 Seed Audio 400 chars", "seed_audio", {"text": "x" * 400}, 0.5, 2.7),
    ("9 Audio dubbing 8.5 s", "audio_dubbing", {"duration": 8.5}, 25.5, 24),
    ("10 Seedance 2.0 720p, no duration", "seedance_2_0", {"model": "seedance_2_0", "resolution": "720p",
                                                           "medias": []}, 22.5, 18),
    ("12 Wan 3.0 720p 5 s (0.01 ceil)", "wan3_0", {"resolution": "720p", "duration": 5, "medias": []}, 7.5, 7.5),
    ("14 Kling 3.0 multi-shot 3+4+5 s", "kling3_0", {"mode": "pro", "sound": "on", "duration": 5, "multi_shots": True,
                                                     "multi_shot_mode": "custom",
                                                     "multi_prompt": [{"duration": 3}, {"duration": 4},
                                                                      {"duration": 5}]}, 12.5, 30),
    ("15 Wan edit, 7.3 s source", "wan3_0", {"resolution": "720p", "model": "video_edit",
                                             "medias": [{"role": "video", "data": {"type": "video",
                                                                                   "duration_sec": 7.3}}]}, 15, 24),
    ("17 Nano Banana 2 4k batch 2 (static)", "nano_banana_2", {"resolution": "4k", "batch_size": 2}, None, 8),
    ("17 Soul V2 batch 4 (static)", "text2image_soul_v2", {"batch_size": 4}, None, 0.5),
    ("19 GPT Image 2.6 quality auto 2k batch 4", "gpt_image_2_6", {"quality": "auto", "resolution": "2k",
                                                                   "batch_size": 4}, 5, 8),
]


@pytest.mark.parametrize("name,jst,params,want_v1,want_v2", S8, ids=[c[0] for c in S8])
def test_section8_items(v1, v2, name, jst, params, want_v1, want_v2):
    a, b = v1.estimate(jst, params), v2.estimate(jst, params)
    assert a["credits"] == (pytest.approx(want_v1, abs=1e-4) if want_v1 is not None else None), a
    assert b["credits"] == pytest.approx(want_v2, abs=1e-4), b
    EstimatedCost.model_validate(b)
    assert b["formula_version"] == 2 and "formula_version" not in a


# --------------------------------------------------------------------------- §7 scenarios (same live table)
S7 = [
    ("Seedance 2.5 1080p 5 s text only", "seedance_2_5", {"resolution": "1080p", "duration": 5, "medias": []}, 80),
    ("Seedance 2.5 4k 10 s video batch 4", "seedance_2_5", {"resolution": "4k", "duration": 10, "batch_size": 4,
                                                            "medias": [VID]}, 1360),
    ("Seedance edit 2.5 s clip clamped to 4 s", "seedance_2_5",
     {"resolution": "1080p", "model": "video_edit", "medias": [{"role": "video", "data": {"duration_sec": 2.5,
                                                                                          "type": "video"}}]}, 80),
    ("Seedance edit 45 s clip clamped to 30 s", "seedance_2_5",
     {"resolution": "1080p", "model": "video_edit", "medias": [{"role": "video", "meta": {"durationSec": 45},
                                                                "data": {"type": "video"}}]}, 600),
    ("Seedance extend 10 s 720p", "seedance_2_5", {"resolution": "720p", "duration": 10,
                                                   "model": "video_extension", "medias": [VID]}, 70),
    ("Cinema 4.0 edit 9 s 720p", "cinematic_studio_video_4_0",
     {"resolution": "720p", "model": "video_edit", "medias": [{"role": "video", "data": {"duration_sec": 9,
                                                                                         "type": "video"}}]}, 63),
    ("Cinema 4.0 1080p 15 s ref image batch 2", "cinematic_studio_video_4_0",
     {"resolution": "1080p", "duration": 15, "batch_size": 2, "medias": [IMG]}, 480),
    ("Kling 4.0 1080p HDR video 10 s", "kling4_0", {"resolution": "1080p", "duration": 10, "hdr": True,
                                                    "medias": [VID]}, 52.5),
    ("Kling 4.0 Flash 720p 5 s video", "kling_4_0_flash", {"resolution": "720p", "duration": 5, "medias": [VID]}, 10),
    ("Kling 3.0 motion control pro 7.3 s chain", "kling3_0_motion_control",
     {"mode": "pro", "duration": 7.3, "is_chain": True}, 21),
    ("Wan 3.0 Prime 480p 2 s", "wan3_0_prime", {"resolution": "480p", "duration": 2, "medias": []}, 2.5),
    ("GPT Image 2.6 high 2k batch 4", "gpt_image_2_6", {"quality": "high", "resolution": "2k", "batch_size": 4}, 8),
    ("GPT Image 2 high 4k batch 4", "gpt_image_2", {"quality": "high", "resolution": "4k", "batch_size": 4}, 48),
    ("GPT Image 2.5 flare low 1k batch 4", "gpt_image_2_5", {"model": "flare", "quality": "low", "resolution": "1k",
                                                             "batch_size": 4}, 1),
    ("ElevenLabs v4 400 chars batch 2", "elevenlabs_v4", {"text": "x" * 400, "batch_size": 2}, 3.68),
    ("ElevenLabs v4 Turbo 1001 chars", "elevenlabs_v4_turbo", {"text": "x" * 1001}, 3.15),
    ("Higgsfield Enhance 12 s", "seedance_2_5_kling_upscale", {"resolution": "1080p", "duration": 12}, 48),
    ("Seedream v5 Pro 2k batch 4", "seedream_v5_pro", {"resolution": "2k", "batch_size": 4}, 10),
    ("Nano Banana 2.1 4k batch 4", "nano_banana_2_1", {"resolution": "4k", "batch_size": 4}, 12),
    ("H3 Lite 480p 5 s batch 2", "minimax_h3_lite", {"resolution": "480p", "duration": 5, "batch_size": 2}, 10),
]


@pytest.mark.parametrize("name,jst,params,want", S7, ids=[c[0] for c in S7])
def test_section7_scenarios(v2, name, jst, params, want):
    assert v2.estimate(jst, params)["credits"] == pytest.approx(want, abs=1e-4)


def test_strike_through_uses_same_formula(v2):
    w = v2.estimate("wan3_0", {"resolution": "720p", "duration": 5, "medias": []})
    assert w["credits"] == 7.5 and w["credits_before_discount"] == 12.5
    k = v2.estimate("kling_4_0_flash", {"resolution": "720p", "duration": 5, "medias": [VID]})
    assert k["credits"] == 10 and k["credits_before_discount"] == 20


# --------------------------------------------------------------------------- §4 static JS tables [17]
STATIC = [
    ("Veo 3.1 8 s", "veo3_1", {"duration": 8}, 58),
    ("Veo 3.1 Fast 8 s", "veo3_1", {"duration": 8, "model": "veo-3-1-fast"}, 22),
    ("Veo 3.1 ultra 8 s", "veo3_1", {"duration": 8, "quality": "ultra"}, 88),
    ("Veo 3.1 Lite 1080p audio 8 s", "veo3_1_lite", {"resolution": "1080p", "generate_audio": True, "duration": 8}, 16),
    ("Veo 3.1 Lite 720p silent 4 s", "veo3_1_lite", {"resolution": "720p", "generate_audio": False, "duration": 4}, 4),
    ("Sora 2 720p 8 s", "sora2_video", {"model": "sora-2", "resolution": "720p", "duration": 8}, 20),
    ("Sora 2 Pro 1080p 12 s", "sora2_video", {"model": "sora-2-pro", "resolution": "1080p", "duration": 12}, 149),
    ("Sora 2 Max 720p 4 s", "sora2_video", {"model": "sora-2", "max": True, "resolution": "720p", "duration": 4}, 14),
    ("Soul V2 batch 4", "text2image_soul_v2", {"batch_size": 4}, 0.5),
    ("Soul Cinema 1 image", "soul_cinematic", {"batch_size": 1}, 0.125),
    ("Flux 2 Max 2k batch 2", "flux_2", {"model": "max", "resolution": "2k", "batch_size": 2}, 12),
    ("Flux 3 image 4k", "flux_3_image", {"resolution": "4k"}, 19),
    ("Seedream v4.5 batch 4", "seedream_v4_5", {"batch_size": 4}, 4),
    ("Hailuo 2.3 Fast 6 s 1080p", "minimax_hailuo", {"model": "minimax-2.3-fast", "duration": 6,
                                                      "resolution": "1080p"}, 7),
    ("H3 Highspeed-like static H3 768p 10 s", "minimax_h3", {"resolution": "768p", "duration": 10}, 25),
    ("DoP lite 49 frames", "image2video", {"model": "lite", "frames": 49}, 3),
    ("DoP lite 81 frames", "image2video", {"model": "lite", "frames": 81}, 5),
    ("DoP standard 81 frames default steps", "image2video", {"model": "standard", "frames": 81}, 10),
    ("DoP turbo 49 frames steps 30", "image2video", {"model": "turbo", "frames": 49, "steps": 30}, 5),
    ("Speak HF v2 mid 4 s", "hf_speak_v2", {"quality": "mid", "duration": 4}, 14),
    ("Speak HF v2 mid 10 s", "hf_speak_v2", {"quality": "mid", "duration": 10}, 28),
    ("Speak HF v2 high 10 s", "hf_speak_v2", {"quality": "high", "duration": 10}, 44),
    ("Wan 2.5 Speak 1080p 10 s", "wan2_5_speak", {"resolution": "1080p", "duration": 10}, 40),
    ("Wan 2.5 Speak Fast 720p 10 s", "wan2_5_speak", {"model": "speak-wan-2.5-fast", "resolution": "720p",
                                                      "duration": 10}, 18),
    ("Infinite Talk high 12 s", "infinite_talk", {"quality": "high", "duration": 12}, 144),
    ("Kling lipsync 7 s video", "kling_lipsync", {"duration": 7}, 2.5),
    ("Kling 2.6 sound 10 s", "kling2_6", {"duration": 10, "sound": True}, 20),
    ("Seedance unlimited", "seedance_2_unlimited", {"duration": 10}, 0),
]


@pytest.mark.parametrize("name,jst,params,want", STATIC, ids=[c[0] for c in STATIC])
def test_static_js_tables(v2, name, jst, params, want):
    r = v2.estimate(jst, params)
    assert r["credits"] == pytest.approx(want, abs=1e-4), r
    assert r["status"] == "approximate" and r["price_point_id"] == f"js_static:{jst}"
    assert any("static JS price table" in n for n in r["notes"])


def test_static_table_wins_over_compare_fallback(body):
    cmp = json.loads((FIXTURES / "compare__billing_period-annual__plan_set_key-ps_a3.json").read_text("utf-8"))
    ben = json.loads((FIXTURES / "plan_benefits__locale-en.json").read_text("utf-8"))
    cmp, ben = cmp.get("body", cmp), ben.get("body", ben)
    e1 = CostEstimator.from_job_costs_body(body).with_compare_fallback(cmp, ben)
    e2 = CostEstimatorV2.from_job_costs_body(body).with_compare_fallback(cmp, ben)
    if "text2image_soul_v2" in e1.fallback:          # v1 prices Soul V2 from the comparison table (0.12)
        assert e1.estimate("text2image_soul_v2", {"batch_size": 4})["price_point_id"].startswith("compare:")
    assert e2.estimate("text2image_soul_v2", {"batch_size": 4})["credits"] == 0.5


def test_unknown_type_still_unpriced(v2):
    r = v2.estimate("totally_new_model", {"batch_size": 2})
    assert r["status"] == "unpriced" and r["formula_version"] == 2


# --------------------------------------------------------------------------- individual rules
def test_viral_preset_ceil(body):                                                    # [11]
    presets = {"presets": [{"id": "p1", "name": "odd", "price_matrix": [{"key": "", "credit_units": 1750}]},
                           {"id": "p2", "name": "floating-fall",
                            "price_matrix": [{"key": "", "credit_units": 8400},
                                             {"key": "n.resolution=1080p", "credit_units": 14400}]}]}
    e1 = CostEstimator.from_job_costs_body(body).with_viral_presets(presets)
    e2 = CostEstimatorV2.from_job_costs_body(body).with_viral_presets(presets)
    assert e1.estimate("viral_hub_video", {"chain_preset_id": "p1"})["credits"] == 17.5
    assert e2.estimate("viral_hub_video", {"chain_preset_id": "p1"})["credits"] == 18
    assert e2.estimate("viral_hub_video", {"chain_preset_id": "p2"})["credits"] == 84
    assert e2.estimate("viral_hub_video", {"chain_preset_id": "p2", "resolution": "1080p"})["credits"] == 144


def test_ceil_per_generation_then_batch(v2):                                         # [1]
    r = v2.estimate("seedance_2_5_flash", {"resolution": "480p", "duration": 5, "batch_size": 2, "medias": [VID]})
    assert r["credits"] == 26 and r["status"] == "exact"     # ceil(12.5) x 2, not ceil(25)


def test_edit_without_source_length_falls_back_to_duration(v2):                     # [2]
    r = v2.estimate("seedance_2_5", {"resolution": "1080p", "model": "video_edit", "duration": 2, "medias": [VID]})
    assert r["credits"] == 80 and r["status"] == "approximate"        # clamp(2 → 4) x 20
    assert r["assumed"]["source_duration"] == 2
    assert any("source video length not in params" in n for n in r["notes"])


def test_no_batch_types_note_ignored_batch(v2):                                       # [3]
    r = v2.estimate("wan3_0", {"resolution": "720p", "duration": 5, "batch_size": 3, "medias": []})
    assert r["credits"] == 7.5 and "ignored" in r["quantity_basis"]


def test_default_durations(v2):                                                       # [10]
    assert v2.estimate("kling4_0", {"resolution": "720p", "medias": []})["assumed"]["duration"] == 10
    assert v2.estimate("gemini_omni", {"resolution": "720p"})["credits"] == 24        # ceil(8 x 3)
    assert v2.estimate("seedance_2_5", {"resolution": "720p", "medias": []})["credits"] == 35   # JS default 5 s


def test_dubbing_lipsync_floor_and_fps(v2):                                           # [9]
    assert v2.estimate("dubbing_lipsync", {"duration": 8.5, "fps": 30})["credits"] == 29     # ceil(8 x 3.6)
    assert v2.estimate("elevenlabs_video_to_music", {"model_id": "music_v1", "duration": 61})["credits"] == 8


def test_voice_change_cent_ceil(v2):                                                  # [12]
    assert v2.estimate("voice_change_merge", {"duration": 12.34})["credits"] == ceil_cents(12.34 * 0.1) == 1.24


def test_scene_switch_addon_fields(v1, v2):                                           # [16]
    assert "cost_per_run" in v1.models["scene_switch"]["options"]              # v1 untouched: parsed as a dimension
    assert "cost_per_run" not in v2.models["scene_switch"]["options"]
    r = v2.estimate("scene_switch", {"tier": "basic", "resolution": "1080p", "duration": 5})
    assert r["credits"] == pytest.approx(5 * 4.03 + 8.87) and r["matched"] == {"tier": "basic", "resolution": "1080p"}
    assert r["status"] == "approximate" and "cost_per_run" in r["quantity_basis"]


@pytest.mark.parametrize("jst,params,expect", [
    ("gpt_image_2_6", {"quality": "high", "resolution": "2k", "use_unlim": True}, "may have been free"),
    ("gpt_image_2_6", {"quality": "high", "resolution": "2k", "batch_size": 4, "use_unlim": True}, "batch_size <= 1"),
    ("kling_4_0_flash", {"resolution": "720p", "duration": 5, "use_unlim": True}, "never unlimited"),
    ("text2image_soul_v2", {"batch_size": 2, "use_unlim": True}, "batch_size <= 1"),
])
def test_unlimited_batch_rule(v1, v2, jst, params, expect):                            # [18]
    r = v2.estimate(jst, params)
    assert any(expect in x for x in r["notes"]), r["notes"]
    assert r["credits"] is not None                     # the estimate is still the list price
    if jst in v1.models:                                # v1 note ignores the batch rule
        assert any("may have been free" in x for x in v1.estimate(jst, params)["notes"])


def test_gpt_missing_and_unknown_options_fall_back_to_high_2k(v1, v2):                 # [19]
    miss = v2.estimate("gpt_image_2_6", {"batch_size": 1})
    assert miss["credits"] == 2 and miss["assumed"] == {"quality": "high", "resolution": "2k"}
    assert miss["status"] == "approximate"
    odd = v2.estimate("gpt_image_2_6", {"quality": "ultra", "resolution": "8k"})
    assert odd["credits"] == 2 and odd["matched"] == {}
    assert v1.estimate("gpt_image_2_6", {"batch_size": 1})["credits"] == 0.75           # v1: lowest-cost low/1k


def test_kling_sound_default_kept(v1, v2):                                              # [13] kept
    p = {"mode": "pro", "duration": 5}
    assert v1.estimate("kling3_0", p)["credits"] == v2.estimate("kling3_0", p)["credits"] == 8.75


# --------------------------------------------------------------------------- versions / output shape
def test_estimator_class_and_versions():
    assert ESTIMATE_VERSIONS == (1, 2)
    assert estimator_class(1) is CostEstimator and estimator_class(2) is CostEstimatorV2
    with pytest.raises(ValueError):
        estimator_class(3)


def test_formula_version_only_on_v2_and_only_in_v2_schema():
    assert "formula_version" not in EstimatedCost(status="exact").model_dump(mode="json")
    assert EstimatedCost(status="exact", formula_version=2).model_dump(mode="json")["formula_version"] == 2
    assert "formula_version" not in json.dumps(EstimatedCost.model_json_schema(mode="serialization"))
    with formula_version_in_schema():
        assert "formula_version" in json.dumps(EstimatedCost.model_json_schema(mode="serialization"))


def test_community_option_plumbing():
    from higgsfield_scraper.scrapers.community.options import Selection, selection_from_dict
    d1 = Selection(estimate_cost="all").to_dict()
    assert "estimate_version" not in d1                                  # v1 manifests/meta unchanged
    s2 = Selection(estimate_cost="all", estimate_version="2")
    assert s2.estimate_version == 2 and s2.to_dict()["estimate_version"] == 2
    assert selection_from_dict(s2.to_dict()).estimate_version == 2
    assert selection_from_dict(d1).estimate_version == 1
    with pytest.raises(ValueError):
        Selection(estimate_version=3)


def test_community_dataset_uses_v2(body):
    from higgsfield_scraper.scrapers.community.dataset import _cost_context, attach_estimates
    from higgsfield_scraper.scrapers.community.options import Selection
    ents = {"community_cost_basis": [{"basis_id": "job_costs", "job_costs": body, "source": {}}]}
    for version, cls in ((1, CostEstimator), (2, CostEstimatorV2)):
        sel = Selection(estimate_cost="all", estimate_version=version)
        est, summary = _cost_context(ents, sel)
        assert type(est) is cls
        assert any("formula version 2" in n for n in summary["notes"]) == (version == 2)
        gens = [{"job_set_type": "seedance_2_5_flash", "media_type": "video",
                 "raw_params": {"resolution": "480p", "duration": 5, "medias": [VID]}}]
        attach_estimates(gens, est, sel, None)
        ec = gens[0]["estimated_cost"]
        assert ec["credits"] == (12.5 if version == 1 else 13)
        assert ("formula_version" in ec) == (version == 2)


def test_account_option_plumbing(body):
    from higgsfield_scraper.scrapers.account.dataset import build_estimator
    from higgsfield_scraper.scrapers.account.options import Selection, selection_from_dict
    assert "estimate_version" not in Selection.build(with_jobs=True, compare_estimate=True).to_dict()
    s = Selection.build(with_jobs=True, compare_estimate=True, estimate_version="2")
    assert s.to_dict()["estimate_version"] == 2 and selection_from_dict(s.to_dict()).estimate_version == 2
    with pytest.raises(ValueError):
        Selection.build(estimate_version=2)                              # needs --compare-estimate
    est, basis = build_estimator({"job_costs": {"body": body}}, 2)
    assert type(est) is CostEstimatorV2 and any("formula version 2" in n for n in basis["notes"])
    est1, basis1 = build_estimator({"job_costs": {"body": body}})
    assert type(est1) is CostEstimator and not any("formula version" in n for n in basis1["notes"])
