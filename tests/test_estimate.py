"""CostEstimator against the real /job-sets/costs fixture, with params shaped like real community generations."""
from pathlib import Path

import pytest

from higgsfield_scraper.estimate import CostEstimator as ExportedEstimator, EstimatedCost
from higgsfield_scraper.estimate.estimator import CostEstimator
from higgsfield_scraper.raw import Envelope

FIXTURE = Path(__file__).parent / "fixtures" / "raw" / "job_costs.json"
IMG = {"role": "image", "data": {"id": "x", "type": "media_input", "url": "https://cdn/x.png"}}
START = {"role": "start_image", "data": {"id": "x", "type": "media_input", "url": "https://cdn/x.png"}}
VID = {"role": "video", "data": {"id": "v", "type": "video_input", "url": "https://cdn/v.mp4"}}


@pytest.fixture(scope="module")
def est():
    return CostEstimator.from_job_costs_body(Envelope.load(FIXTURE).body, usd_per_credit=0.02,
                                             usd_reference="test plan")


def check(r):
    EstimatedCost.model_validate(r)  # JSON-mode dict matching the schema
    return r


def test_exported_from_package():
    assert ExportedEstimator is CostEstimator


# --------------------------------------------------------------------------- video, per second
def test_seedance_2_5_matches_site_example(est):
    # site comparison text: Seedance 2.5 720p = 35 credits per 5 s
    r = check(est.estimate("seedance_2_5", {"resolution": "720p", "duration": 5, "generate_audio": True,
                                            "medias": [IMG], "model": "default"}, "video"))
    assert r["status"] == "exact"
    assert r["credits"] == 35 and r["unit"] == "credits_per_second" and r["unit_credits"] == 7
    assert r["quantity"] == 5 and r["quantity_basis"] == "duration=5s"
    assert r["matched"] == {"resolution": "720p", "video_input": "without_video"}
    assert r["usd"] == pytest.approx(0.7) and r["usd_reference"] == "test plan"
    assert r["price_point_id"]


def test_video_input_presence_changes_price(est):
    base = {"resolution": "4k", "duration": 10}
    without = est.estimate("seedance_2_5", {**base, "medias": []}, "video")
    with_v = est.estimate("seedance_2_5", {**base, "medias": [VID]}, "video")
    assert without["credits"] == 280 and without["matched"]["video_input"] == "without_video"
    assert with_v["credits"] == 340 and with_v["matched"]["video_input"] == "with_video"
    assert est.estimate("seedance_2_5", {**base, "input_video": {"url": "u"}})["credits"] == 340


def test_discount_reported(est):
    r = est.estimate("wan3_0", {"resolution": "1080", "duration": 10, "medias": []}, "video")
    assert r["status"] == "exact"
    assert r["matched"] == {"resolution": "1080p", "video_input": "without_video"}   # '1080' -> '1080p'
    assert r["credits"] == 30 and r["credits_before_discount"] == 55


def test_kling_audio_on_off(est):
    on = est.estimate("kling3_0", {"mode": "pro", "sound": "on", "duration": 8, "medias": [START]}, "video")
    off = est.estimate("kling3_0", {"mode": "std", "sound": False, "duration": 5}, "video")
    assert on["status"] == "exact" and on["credits"] == 20 and on["matched"] == {"mode": "pro", "audio": "on"}
    assert off["credits"] == 7.5 and off["matched"]["audio"] == "off"   # documented "~7 credits/5s"


def test_kling_missing_audio_assumed_lowest(est):
    r = est.estimate("kling3_0", {"mode": "PRO", "duration": 5}, "video")
    assert r["status"] == "approximate"
    assert r["assumed"] == {"audio": "off"} and r["credits"] == 8.75


def test_missing_duration_defaults_to_5s(est):
    r = est.estimate("seedance_2_0", {"model": "seedance_2_0_fast", "resolution": "720p"}, "video")
    assert r["status"] == "approximate"
    assert r["assumed"] == {"duration": 5.0} and r["credits"] == 12.5
    assert "assumed" in r["quantity_basis"]


def test_seedance_2_0_model_dimension(est):
    r = est.estimate("seedance_2_0", {"model": "seedance_2_0", "resolution": "720p", "duration": 15,
                                      "generate_audio": False, "medias": []}, "video")
    assert r["status"] == "exact" and r["credits"] == 67.5 and r["credits_before_discount"] == 90


def test_unknown_option_value_is_assumed(est):
    r = est.estimate("seedance_2_5", {"resolution": "8k", "duration": 5, "medias": []}, "video")
    assert r["status"] == "approximate" and r["assumed"] == {"resolution": "480p"}
    assert any("not in pricing options" in n for n in r["notes"])


def test_kling4_hdr_rows_only_with_flag(est):
    plain = est.estimate("kling4_0", {"resolution": "1080p", "duration": 5, "medias": []})
    hdr = est.estimate("kling4_0", {"resolution": "1080p", "duration": 5, "medias": [], "hdr": True})
    assert plain["credits"] == 18.75 and plain["status"] == "exact"
    assert hdr["credits"] == 22.5 and hdr["matched"]["video_hdr"] == "without_video"


def test_base_credits_and_per_image_addons(est):
    g = est.estimate("gemini_omni", {"resolution": "720p", "duration": 4}, "video")
    assert g["credits"] == 12 and "base_credits" in g["quantity_basis"]
    r = est.estimate("reframe", {"resolution": "720p", "duration": 4, "medias": [IMG, IMG]}, "video")
    assert r["credits"] == 4.5 * 4 + 1.25 * 2 and r["status"] == "exact"


def test_video_edit_component(est):
    r = est.estimate("seedance_2_5", {"resolution": "720p", "duration": 5, "video_edit": True}, "video")
    assert r["unit_credits"] == 7.5 and r["credits"] == 37.5


# --------------------------------------------------------------------------- image, per generation
def test_gpt_image_quality_resolution(est):
    r = est.estimate("gpt_image_2_6", {"quality": "max", "resolution": "2K", "model": "aurora-img-alpha",
                                       "medias": []}, "image")
    assert r["status"] == "exact" and r["unit"] == "credits_per_generation"
    assert r["matched"] == {"quality": "max", "resolution": "2k"} and r["credits"] == 7


def test_gpt_image_2_5_model_dimension_and_discount(est):
    r = est.estimate("gpt_image_2_5", {"model": "flare", "quality": "low", "resolution": "1k"}, "image")
    assert r["credits"] == 0.25 and r["credits_before_discount"] == 1 and r["status"] == "exact"


def test_batch_size_multiplies(est):
    r = est.estimate("nano_banana_2_1", {"resolution": "4k", "batch_size": 4, "medias": [IMG]}, "image")
    assert r["credits"] == 12 and r["quantity"] == 4 and r["quantity_basis"] == "batch_size=4"


def test_image_missing_resolution_is_approximate(est):
    r = est.estimate("seedream_v5_pro", {"batch_size": 1}, "image")
    assert r["status"] == "approximate" and r["assumed"] == {"resolution": "1k"} and r["credits"] == 1.25


def test_has_references_derived(est):
    r = est.estimate("ideogram_vector", {"operation": "generate", "quality": "high",
                                         "reference_elements": [{"id": 1}]}, "image")
    assert r["matched"]["has_references"] is True and r["credits"] == 10


# --------------------------------------------------------------------------- audio formulas
def test_character_blocks_use_prompt_length(est):
    r = est.estimate("elevenlabs_v4", {"prompt": "x" * 120}, "audio")
    assert r["unit"] == "credits_per_50_characters" and r["quantity"] == 3
    assert r["credits"] == pytest.approx(0.69)


def test_character_formula_without_text_is_unpriced(est):
    assert est.estimate("elevenlabs_v4", {}, "audio")["status"] == "unpriced"


# --------------------------------------------------------------------------- unpriced / aliases / sanity
@pytest.mark.parametrize("jst", ["nano_banana_2", "text2image_soul_v2", "soul_cinematic", "image_auto",
                                 "viral_hub_video", "wan2_5_video"])
def test_unpriced_models(est, jst):
    r = check(est.estimate(jst, {"resolution": "2k", "batch_size": 4}, "image"))
    assert r["status"] == "unpriced" and r["credits"] is None and r["usd"] is None
    assert "no /job-sets/costs entry" in r["notes"][0]


def test_separator_insensitive_alias(est):
    r = est.estimate("kling4_0_flash", {"resolution": "720p", "duration": 5, "medias": []}, "video")
    assert r["status"] == "approximate" and r["credits"] == 7.5
    assert "kling_4_0_flash" in r["notes"][0]


def test_media_type_mismatch_noted(est):
    r = est.estimate("seedance_2_5", {"resolution": "720p", "duration": 5, "medias": []}, "image")
    assert any("pricing category" in n for n in r["notes"]) and r["status"] == "exact"


def test_no_usd_without_rate():
    e = CostEstimator.from_job_costs_body(Envelope.load(FIXTURE).body)
    r = e.estimate("nano_banana_2_1", {"resolution": "1k"})
    assert r["usd"] is None and r["usd_per_credit"] is None and r["credits"] == 1.5
