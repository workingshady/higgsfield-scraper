"""Comparison-table and viral-preset fallbacks for models missing from /job-sets/costs."""
from pathlib import Path

from higgsfield_scraper.estimate import CostEstimator
from higgsfield_scraper.estimate.compare_fallback import build_fallback, estimate_viral, viral_table
from higgsfield_scraper.raw import Envelope

RAW = Path(__file__).parent / "fixtures" / "raw"


def _est():
    jc = Envelope.load(RAW / "job_costs.json").body
    cmp = Envelope.load(RAW / "compare__billing_period-annual__plan_set_key-ps_a3.json").body
    ben = Envelope.load(RAW / "plan_benefits__locale-en.json").body
    return CostEstimator.from_job_costs_body(jc, usd_per_credit=0.025, usd_reference="t").with_compare_fallback(cmp, ben)


def test_compare_fallback_prices_unlisted_models():
    est = _est()
    assert "nano_banana_2" in est.fallback and "text2image_soul_v2" in est.fallback
    r = est.estimate("nano_banana_2", {"batch_size": 2}, "image")
    assert r["status"] == "approximate" and r["credits"] == 4.0 and r["usd"] == 0.1
    assert r["price_point_id"].startswith("compare:") and "comparison table" in r["notes"][0]
    r4k = est.estimate("nano_banana_2", {"resolution": "4k"}, "image")
    assert r4k["credits"] == 4.0                                    # "Nano Banana Pro 4K · 4 credits/image"


def test_compare_fallback_never_overrides_real_costs():
    est = _est()
    assert "gpt_image_2_6" not in est.fallback                     # listed in /job-sets/costs
    assert est.estimate("gpt_image_2_6", {"quality": "low", "resolution": "1k"}, "image")["status"] == "exact"


def test_unknown_model_stays_unpriced():
    assert _est().estimate("image_auto", {}, "image")["status"] == "unpriced"


def test_viral_matrix_exact_and_default():
    body = {"presets": [{"id": "p1", "name": "Vanish", "duration": 5, "price_matrix": [
        {"key": "", "credit_units": 2250},
        {"key": "p1.aspect_ratio=16:9,p1.resolution=1080p", "credit_units": 4500},
        {"key": "p1.aspect_ratio=16:9,p1.resolution=720p", "credit_units": 2250}]}]}
    t = viral_table(body)
    assert estimate_viral(t["p1"], {"aspect_ratio": "16:9", "resolution": "1080p"})["credits"] == 45.0
    d = estimate_viral(t["p1"], {"aspect_ratio": "1:1"})
    assert d["credits"] == 22.5 and d["status"] == "approximate"
    est = _est().with_viral_presets(body)
    r = est.estimate("viral_hub_video", {"chain_preset_id": "p1", "aspect_ratio": "16:9", "resolution": "1080p"}, "video")
    assert r["status"] == "exact" and r["credits"] == 45.0 and r["price_point_id"] == "viral:p1"
