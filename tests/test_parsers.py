from decimal import Decimal

from higgsfield_scraper.parsers import keep, parse_envelope
from higgsfield_scraper.parsers.compare import parse_detail, parse_value
from higgsfield_scraper.parsers.costs import _Walker, family_of, humanize
from higgsfield_scraper.parsers.marketing import select_versions
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.validation import validate_entity


# ---------------------------------------------------------------- plans
def test_plans_us_prices_match_pricing_md(env, sel):
    ents = parse_envelope(env("plans__plan_set_key-ps_a3.json"), sel)
    plan_set, plans = ents[0], ents[1:]
    assert plan_set["kind"] == "plan_set" and plan_set["plan_set_key"] == "ps_a3"
    plus_annual = next(p for p in plans if p["plan_type"] == "plus" and p["billing_period"] == "annual")
    assert plus_annual["credits_per_month"] == 1200
    assert plus_annual["pricing"]["before_offer"]["per_month"] == Decimal("59.00")
    assert plus_annual["pricing"]["after_offer"]["per_month"] == Decimal("30.00")
    assert plus_annual["pricing"]["after_offer"]["total"] == Decimal("360.00")
    assert plus_annual["discount"]["applies_to"] == "all_payments"
    assert plus_annual["has_offer"] is True
    assert plus_annual["price_per_credit"]["after_offer"] == Decimal("0.0250")
    plus_monthly = next(p for p in plans if p["plan_type"] == "plus" and p["billing_period"] == "monthly")
    assert plus_monthly["discount"]["applies_to"] == "first_payment"
    assert plus_monthly["pricing"]["renewal"]["per_month"] == Decimal("59.00")   # once-only discount
    for p in plans:
        validate_entity(p)


def test_plan_ids_are_stable_and_unique(env, sel):
    a = [p["plan_id"] for p in parse_envelope(env("plans__plan_set_key-ps_a3.json"), sel)[1:]]
    b = [p["plan_id"] for p in parse_envelope(env("plans__plan_set_key-ps_a3.json"), sel)[1:]]
    assert a == b and len(set(a)) == len(a)


def test_special_offer_may_be_a_plan_type_string(env, sel):
    e = env("plans__plan_set_key-ps_a3.json")
    e.body = {**e.body, "special_offer": "ultra"}          # as returned by max_v1_ultra / max_v2_ultra
    plan_set = parse_envelope(e, sel)[0]
    assert validate_entity(plan_set)["special_offer"] == "ultra"


def test_ultra_has_three_credit_tiers(env, sel):
    plans = parse_envelope(env("plans__plan_set_key-default.json"), sel)[1:]
    ultra_m = sorted(p["credits_per_month"] for p in plans if p["plan_type"] == "ultra" and p["billing_period"] == "monthly")
    assert ultra_m == [3000, 6000, 9000]


# ---------------------------------------------------------------- costs
def _points(cost):
    w = _Walker("m")
    w.walk(cost, {}, None)
    return w.points


def test_cost_audio_on_off_becomes_dimension():
    pts = _points([{"mode": "pro", "audio": {"on": 2.5, "off": 1.75}}])
    assert {(p["dimensions"]["audio"], p["credits"]) for p in pts} == {("on", 2.5), ("off", 1.75)}
    assert all(p["unit"] == "credits_per_second" and p["dimensions"]["mode"] == "pro" for p in pts)
    assert pts[0]["example"] == {"seconds": 5, "credits": 12.5}


def test_cost_video_input_and_component():
    pts = _points([{"resolution": "720p",
                    "video": {"with_video": {"cost_per_second": 7, "original_cost_per_second": 8}},
                    "video_edit": {"model": "video_edit", "cost_per_second": 7.5}}])
    main = next(p for p in pts if p["component"] is None)
    assert main["dimensions"] == {"resolution": "720p", "video_input": "with_video"}
    assert main["original_credits"] == 8 and main["is_discounted"] and main["discount_percent"] == 12.5
    edit = next(p for p in pts if p["component"] == "video_edit")
    assert edit["dimensions"] == {"resolution": "720p"}   # redundant model=video_edit removed


def test_cost_nested_list_keeps_parent_dimensions():
    pts = _points([{"model": "seedance_2_0", "resolutions": [{"resolution": "480p", "cost_per_second": 3,
                                                              "original_cost_per_second": 6}]}])
    assert pts[0]["dimensions"] == {"model": "seedance_2_0", "resolution": "480p"}
    assert pts[0]["discount_percent"] == 50.0


def test_cost_attributes_and_formulas():
    pts = _points([{"cost_per_second": 0.5, "reference_fps": 24, "is_estimate": True}])
    assert pts[0]["attributes"] == {"reference_fps": 24, "is_estimate": True} and pts[0]["dimensions"] == {}
    tts = _points([{"formula": "character_blocks", "model": "minimax", "characters_per_block": 50,
                    "cost_units_per_block": 15, "cost_units_per_credit": 100}])[0]
    assert tts["unit"] == "credits_per_50_characters" and tts["credits"] == 0.15
    assert tts["dimensions"] == {"model": "minimax"} and tts["formula"]["name"] == "character_blocks"
    fps = _points([{"formula": "input_duration_by_fps",
                    "fps_multipliers": [{"fps": 25, "credits_per_second": 3.0}, {"fps": 60, "credits_per_second": 6.0}]}])
    assert [(p["dimensions"]["fps"], p["credits"]) for p in fps] == [(25, 3.0), (60, 6.0)]


def test_all_live_models_parse_and_validate(env, sel):
    models = parse_envelope(env("job_costs.json"), sel)
    assert len(models) >= 80
    for m in models:
        assert m["price_points"], m["model_id"]
        validate_entity(m)
    by_id = {m["model_id"]: m for m in models}
    assert by_id["seedance_2_5"]["options"]["resolution"] == ["480p", "720p", "1080p", "4k"]
    assert {"video", "image", "audio"} <= {m["category"] for m in models}


def test_naming_helpers():
    assert humanize("kling3_0") == "Kling 3.0"
    assert humanize("gpt_image_2_6") == "GPT Image 2.6"
    assert family_of("seedance_2_5_flash") == "seedance"
    assert family_of("nano_banana_2_1") == "nano_banana"
    assert family_of("text2speech_v2") == "text2speech"


# ---------------------------------------------------------------- benefits / compare / marketing
def test_benefit_cards(env, sel):
    cards = parse_envelope(env("plan_benefits__locale-en.json"), sel)
    assert {c["billing_period"] for c in cards} == {"monthly", "annual"}
    assert len({c["card_id"] for c in cards}) == len(cards)          # team appears on 2 tabs
    for c in cards:
        validate_entity(c)


def test_compare_detail_and_values():
    assert parse_detail("35 credits/5s") == {"approx": False, "credits": 35.0, "per": "5s"}
    assert parse_detail("~22 credits/5s")["approx"] is True
    assert parse_detail("2 credit/image")["per"] == "image"
    v = parse_value("plus", {"type": "string", "value": "411 videos"})
    assert v["quantity"] == 411 and v["quantity_unit"] == "videos" and v["available"]
    assert parse_value("free", {"type": "bool", "value": False})["available"] is False


def test_compare_parses(env, sel):
    [c] = parse_envelope(env("compare__billing_period-annual__plan_set_key-ps_a3.json"), sel)
    assert c["billing_period"] == "annual" and c["categories"]
    assert any(p["seats"] and p["seats"] > 1 for p in c["plans"])
    validate_entity(c)


def test_marketing_version_selection(env):
    assert select_versions(["v2.0.0", "v10.0.0", "v9.0.0"], ["latest"]) == ["v10.0.0"]
    assert select_versions(["v2.0.0", "v10.0.0"], ["all"]) == ["v2.0.0", "v10.0.0"]
    s = Selection.build(marketing_versions="latest,v50")
    ents = parse_envelope(env("pricing_config__locale-en.json"), s)
    assert {e["config_version"] for e in ents} == {"v51.0.0", "v50.0.0"}
    assert all(e["is_latest"] == (e["config_version"] == "v51.0.0") for e in ents)


def test_filters(env):
    s = Selection.build(models="seedance*,kling3_0", categories="video", plan_types="plus")
    models = [m for m in parse_envelope(env("job_costs.json"), s) if keep(m, s)]
    assert models and all(m["family"] in ("seedance", "kling") for m in models)
    plans = [p for p in parse_envelope(env("plans__plan_set_key-ps_a3.json"), s) if keep(p, s)]
    assert {p["plan_type"] for p in plans if p["kind"] == "plan"} == {"plus"}
