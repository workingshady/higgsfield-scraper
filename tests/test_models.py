"""models scraper: JS/HTML extraction, middleware, parsers, dataset join, spider crawl order + cap, options,
registry (offline). Fixtures: tests/fixtures/models/ — small hand-written chunks in the exact minified shapes of
build 548e0f3a (defineJob, route table, featured ids, plans, gating, flag constants), a trimmed tool page and the two
JSON APIs (the Shots body carries a fake user to prove the middleware drops it). A last test reads the saved real
bundle (samples/higgsfield/js2) when it is present."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.models import SCRAPER
from higgsfield_scraper.scrapers.models import endpoints as E
from higgsfield_scraper.scrapers.models.extract import extract_chunk, extract_page, resolve_flag
from higgsfield_scraper.scrapers.models.jsparse import match_bracket, parse_literal, split_top
from higgsfield_scraper.scrapers.models.middleware import ModelsExtractMiddleware, convert
from higgsfield_scraper.scrapers.models.options import build, default_label, selection_from_dict
from higgsfield_scraper.scrapers.models.parsers import parse_envelope
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "models"
JS2 = Path(__file__).parents[1] / "samples" / "higgsfield" / "js2"
REG, PICK, GATE, FLAGS, ROUTES = ("548e0f3a-ReGiStRyReGiStRy.js", "548e0f3a-PiCkErPiCkErPiCk.js",
                                  "548e0f3a-GaTiNgGaTiNgGaTi.js", "548e0f3a-FlAgSfLaGsFlAgSf.js",
                                  "548e0f3a-RoUtEsRoUtEsRoUt.js")
T0 = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)


def chunk(name: str) -> dict:
    return extract_chunk(name, (FX / name).read_text(encoding="utf-8"))


def env_for(endpoint: str, url: str, raw: bytes, params: dict) -> Envelope:
    """What the pipeline sees: the middleware-converted body, as an Envelope."""
    body = json.loads(convert(endpoint, raw, url, params.get("chunk")))
    return Envelope(endpoint=endpoint, url=url, status=200, body=body, params=params, fetched_at=T0)


def all_envelopes() -> list[Envelope]:
    out = [env_for(E.PAGE_ENDPOINT, "https://higgsfield.ai/ai/video", (FX / "page_ai_video.html").read_bytes(),
                   {"page": "/ai/video"})]
    for name in (REG, PICK, GATE, FLAGS, ROUTES):
        out.append(env_for(E.CHUNK_ENDPOINT, E.ASSETS + name, (FX / name).read_bytes(), {"chunk": name}))
    out.append(Envelope(endpoint=E.COSTS_ENDPOINT, url="https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs",
                        status=200, body=json.loads((FX / "job_sets_costs.json").read_text(encoding="utf-8")),
                        params={}, fetched_at=T0))
    out.append(env_for(E.SHOTS_ENDPOINT, "https://fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=1",
                       (FX / "shots_feed.json").read_bytes(), {"limit": "1"}))
    return out


def entities(sel=None) -> dict[str, list[dict]]:
    sel = sel or build()
    out: dict[str, list[dict]] = {}
    for env in all_envelopes():
        for e in parse_envelope(env, sel):
            v = validate_entity(e)
            out.setdefault(v["kind"], []).append(v)
    return out


@pytest.fixture(scope="module")
def ds():
    sel = build()
    return SCRAPER.build_dataset(entities(sel), sel, RunMeta(run_id="t", scraped_at=T0))


# ------------------------------------------------------------------ JS helpers
def test_bracket_matching_skips_strings_and_templates():
    s = "f({a:`}{${x({y:1})}`,b:'}',c:\"{\",d:[1,{e:2}]})+1"
    assert s[match_bracket(s, 2)] == "}" and s[match_bracket(s, 2) + 1] == ")"
    assert match_bracket(s, 1) == len(s) - 3 and match_bracket("{a:`}", 0) == -1
    assert split_top("a:1,b:[1,2],c:`x,y`,d:f(1,2)") == ["a:1", "b:[1,2]", "c:`x,y`", "d:f(1,2)"]
    assert parse_literal("{a:!0,b:!1,c:6e4,d:[`x`,\"y\"],e:null,f:.5}") == \
        {"a": True, "b": False, "c": 60000, "d": ["x", "y"], "e": None, "f": 0.5}
    text = "q=[`a`],z=1,Q={k:`v`},w=Object.values(Q)"
    assert parse_literal("Q", text, len(text)) == {"k": "v"}
    assert parse_literal("Object.values(Q)", text, len(text)) == ["v"]


# ------------------------------------------------------------------ extraction
def test_extract_page():
    p = extract_page((FX / "page_ai_video.html").read_text(encoding="utf-8"), "https://higgsfield.ai/ai/video")
    assert p["frontend_build"] == "548e0f3a" and p["build_id"] == "45857404800-1-production"
    assert p["commit"].startswith("bcc95938") and p["environment"] == "production"
    assert p["flags"] == {"f_3a0922bf": True, "f_24c5dcf4": False, "f_6a87092e": False}
    assert p["chunks"] == [REG, PICK, GATE]                         # .css ignored, duplicates collapsed


def test_extract_define_job_registry():
    c = chunk(REG)
    assert c["markers"] == ["define_job"] and c["refs_dynamic"] == [ROUTES]
    assert c["refs_static"] == ["548e0f3a-SharedSharedShar.js", "548e0f3a-SideEffectSideEf.js"]
    jobs = {j["type"]: j for j in c["jobs"]}
    kf, hf = jobs["keyframes_faceswap"], jobs["hf_fnf_video"]
    assert kf["output"] == "image" and kf["business"] == {"useUnlim": False}
    assert kf["media"]["roles"] == ["character_image", "scene_image"]
    assert kf["media"]["counts"]["scene_image"] == {"min": 1, "max": 1}
    assert kf["settings"]["quality"] == {"type": "enum", "values": ["1600p", "2048p"], "default": "1600p"}
    assert kf["settings"]["aspectRatio"]["values"] == ["Auto", "1:1", "16:9"]
    assert kf["settings"]["seed"] == {"type": "number", "optional": True}
    assert kf["credits_static"] == 2 and kf["ranges"] == {"seed": [1, 1000000]}
    assert kf["enum_checks"] == {"aspectRatio": ["Auto", "1:1", "16:9"]}
    assert {"aspect_ratio", "swap_mode", "character_input_image", "use_unlim"} <= set(kf["wire_keys"])
    assert hf["prompt"]["policy"] == {"required": True, "minLength": 1, "maxLength": 60000}
    assert hf["settings"]["duration"] == {"type": "duration", "min": 4, "max": 15, "default": 15}
    assert hf["settings"]["note"] == {"type": "string", "nullable": True}
    assert "credits_static" not in hf and "Math.ceil" in hf["credits_raw"]
    assert hf["media"]["rules_raw"].startswith("[B(") and hf["ranges"] == {"duration": [4, 15]}


def test_extract_routes_featured_plans_menus_gating_flags():
    assert chunk(ROUTES)["routes"]["character_swap_v2"] == "/jobs/character-swap/v2"
    p = chunk(PICK)
    assert p["featured"] == ["seedance_2_5", "hf_fnf_video", "kling-4-0-flash"]
    assert p["plans"]["seedance_2_5"]["tier"] == "premium" and p["plans"]["hf_fnf_video"]["tier"] == "all"
    assert p["plans"]["veo-3-fast"] == {"tier": "paid", "tier_ref": "r", "plans": ["basic", "pro"]}
    assert {m["id"] for m in p["menus"]} == {"seedance_2_5", "hf_fnf_video", "not-a-model"}
    g = chunk(GATE)
    assert g["gating_tables"] == [{"ids": ["kling_4_0_flash", "seedance_2_5_flash"], "default_model": "seedance_2_5",
                                   "retired": ["sora-2", "veo3"]}]
    sd = g["gating"]["seedance_2_5_flash"]
    assert sd["priced_as"] == "seedance_2_5_flash" and sd["cobalt_coming_soon"] is True
    f = chunk(FLAGS)
    assert f["flag_exports"] == {"xF": "sC", "CF": "cC", "Zz": "lC"}          # qq (not a flag) left out
    assert resolve_flag(sd, {FLAGS: f}) == "f_24c5dcf4"
    assert resolve_flag(g["gating"]["kling_4_0_flash"], {FLAGS: f}) == "f_3a0922bf"
    assert resolve_flag(sd, {}) is None


# ------------------------------------------------------------------ middleware
def test_middleware_converts_only_models_endpoints():
    mw = ModelsExtractMiddleware()
    sp = SimpleNamespace(scraper_name="models")
    from scrapy.http import Request, Response
    js = (FX / ROUTES).read_bytes()
    req = Request(E.ASSETS + ROUTES, meta={"endpoint": E.CHUNK_ENDPOINT, "params": {"chunk": ROUTES}})
    out = mw.process_response(req, Response(req.url, body=js, request=req), sp)
    body = json.loads(out.body)
    assert body["format"] == "chunk" and body["chunk"] == ROUTES and body["size"] == len(js)
    other = Request("https://x/y", meta={"endpoint": "catalog_motions"})
    r = Response(other.url, body=b"{\"a\": 1}", request=other)
    assert mw.process_response(other, r, sp) is r                           # untouched
    assert mw.process_response(req, Response(req.url, body=js, request=req),
                               SimpleNamespace(scraper_name="site")).body == js
    err = Response(req.url, status=404, body=b"nope", request=req)
    assert mw.process_response(req, err, sp) is err
    shots = json.loads(convert(E.SHOTS_ENDPOINT, (FX / "shots_feed.json").read_bytes(), "u"))
    assert set(shots) == {"available_models", "snapshot_id", "snapshot_at"}  # the feed item (a user) is dropped
    assert "user_Fake" not in json.dumps(shots)


# ------------------------------------------------------------------ parsers + dataset
def test_parsers_emit_valid_entities():
    ents = entities()
    assert {k: len(v) for k, v in ents.items()} == {"models_page_extract": 1, "models_chunk_extract": 5,
                                                   "models_costs_snapshot": 1, "model_shot_facet": 3}
    f = ents["model_shot_facet"][0]
    assert f["model"] == "hf_fnf_video" and f["facet_id"] and f["schema_version"] == 1 and f["source_url"]
    assert parse_envelope(Envelope(endpoint=E.CHUNK_ENDPOINT, url="u", status=200, body={"_non_json": "x"},
                                   params={}, fetched_at=T0), build()) == []


def test_dataset_job_types(ds):
    jt = {r["job_set_type"]: r for r in ds["job_types"]}
    assert set(jt) == {"keyframes_faceswap", "hf_fnf_video", "seedance_2_5", "kling3_0", "wan3_0",
                       "character_swap_v2", "scene_switch"}               # registry | routes | costs
    hf = jt["hf_fnf_video"]
    assert hf["in_registry"] and hf["in_routes"] and hf["in_costs"] and hf["in_shots"]
    assert hf["route"] == "/jobs/v2/hf_fnf_video" and hf["output"] == "video"
    assert hf["display_title"] == "Higgsfield Video" and hf["featured_rank"] == 1
    assert hf["plan"] == {"tier": "all", "plans": ["free", "basic", "pro"]}
    assert hf["prompt"]["maxLength"] == 60000 and hf["media_roles"] == ["image", "video", "audio"]
    params = {p["name"]: p for p in hf["params"]}
    assert params["duration"]["min"] == 4 and params["duration"]["max"] == 15 and params["duration"]["default"] == 15
    assert params["resolution"]["values"] == ["480p", "720p"] and params["note"]["nullable"] is True
    kf = jt["keyframes_faceswap"]
    assert kf["credits_static"] == 2 and kf["credits_formula_raw"] is None and kf["in_costs"] is False
    assert kf["shots_media_type"] == "image" and kf["defined_in"] == [REG]
    assert kf["source_url"] == E.ASSETS + REG and kf["build_id"] == "45857404800-1-production"
    sc = jt["scene_switch"]
    assert sc["in_costs"] and not sc["in_registry"] and sc["params"] == [] and sc["route"] is None
    assert jt["seedance_2_5"]["plan"]["tier"] == "premium" and jt["seedance_2_5"]["in_shots"] is False
    assert ds["summary"]["costs_only"] == ["scene_switch"]
    assert ds["summary"]["registry_not_priced"] == ["keyframes_faceswap"]
    assert len({r["id"] for r in ds["job_types"]}) == len(ds["job_types"])


def test_dataset_menu_gating_build(ds):
    me = {r["model_version_id"]: r for r in ds["menu_entries"]}
    assert set(me) == {"seedance_2_5", "hf_fnf_video"}                     # "not-a-model" is not a model
    assert me["hf_fnf_video"]["badges"] == ["New"] and me["hf_fnf_video"]["short_title"] == "HF Video"
    b = ds["builds"][0]
    assert b["frontend_build"] == "548e0f3a" and b["build_id"] == "45857404800-1-production"
    assert b["default_models"] == ["seedance_2_5"] and b["retired"] == ["sora-2", "veo3"]
    assert b["featured"][0] == "seedance_2_5" and b["costs_version"].startswith("0cee3218")
    assert b["chunks_fetched"] == 5 and b["registry_types"] == 2 and b["route_types"] == 6
    assert all(b["coverage"].values()), b["coverage"]
    assert ds["summary"]["gated"] == {}                                    # gated ids are not job types here
    assert len(ds["chunks"]) == 5 and ds["chunks"][0]["sha256"]


def test_gate_status_rules():
    from higgsfield_scraper.scrapers.models.dataset import _gate
    data = {FLAGS: chunk(FLAGS)}
    g = chunk(GATE)["gating"]
    assert _gate(g["kling_4_0_flash"], {"f_3a0922bf": True}, set(), data)["status"] == "available"
    off = _gate(g["seedance_2_5_flash"], {"f_24c5dcf4": False}, {"seedance_2_5_flash"}, data)
    assert off["status"] == "hidden" and off["flag_value"] is False and off["fallback"] == "seedance_2_5"
    unpriced = _gate(g["seedance_2_5_flash"], {"f_24c5dcf4": True}, {"seedance_2_5"}, data)
    assert unpriced["status"] == "hidden"
    assert _gate(g["seedance_2_5_flash"], {"f_24c5dcf4": True}, {"seedance_2_5_flash"}, data)["status"] == \
        "available"
    assert _gate(g["kling_4_0_flash"], {}, None, data)["flag_value"] is None


def _csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return (set(rows[0].keys()) if rows else set()), rows


def test_outputs_and_csvs_complete(ds, tmp_path):
    SCRAPER.write_outputs(ds, tmp_path)
    for name in ("job_types", "menu_entries", "builds", "chunks", "shot_facets"):
        assert (tmp_path / "json" / f"{name}.json").exists()
    cols, rows = _csv(tmp_path / "csv" / "job_types.csv")
    assert len(rows) == len(ds["job_types"])
    missing = {k for r in ds["job_types"] for k in flatten({k: v for k, v in r.items() if k != "params"})} - cols
    missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
    assert not missing, sorted(missing)[:10]
    pcols, prow = _csv(tmp_path / "csv" / "job_type_params.csv")
    assert len(prow) == sum(len(r["params"]) for r in ds["job_types"]) and "job_set_type" in pcols
    assert "registry" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert (tmp_path / "schema" / "dataset.schema.json").exists()


# ------------------------------------------------------------------ spider
def make_spider(sel=None, **common):
    from higgsfield_scraper.scrapers.models.spider import ModelsSpider
    return ModelsSpider(selection=sel or build(), common=CommonOptions(**{"auth": "off", **common}))


def test_spider_first_requests_public_get_only():
    reqs = list(make_spider().build_requests())
    assert [r.url for r in reqs] == ["https://higgsfield.ai/ai/video", "https://higgsfield.ai/ai/image",
                                     "https://higgsfield.ai/lipsync-studio", "https://higgsfield.ai/mixed-media",
                                     "https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs",
                                     "https://fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=1"]
    assert all(r.method == "GET" and not r.meta["auth"] for r in reqs)
    only = list(make_spider(build(pages="/ai/video", with_costs=False, with_shots=False)).build_requests())
    assert [r.url for r in only] == ["https://higgsfield.ai/ai/video"]


def test_spider_crawl_order_window_and_cap():
    sp = make_spider(build(max_chunks=5))
    page = env_for(E.PAGE_ENDPOINT, "https://higgsfield.ai/ai/video", (FX / "page_ai_video.html").read_bytes(),
                   {"page": "/ai/video"})
    list(sp.follow_up(page, [], SimpleNamespace(meta={})))
    first = sp._pump()
    assert [r.url.rsplit("/", 1)[-1] for r in first] == [REG, PICK, GATE]        # page order, all preloads
    assert all(r.url.startswith(E.ASSETS) and r.meta["endpoint"] == E.CHUNK_ENDPOINT for r in first)
    reg = env_for(E.CHUNK_ENDPOINT, E.ASSETS + REG, (FX / REG).read_bytes(), {"chunk": REG})
    list(sp.follow_up(reg, [], SimpleNamespace(meta={"chunk_priority": E.PRIO_PRELOAD})))
    sp._inflight = 0
    nxt = sp._pump()
    names = [r.url.rsplit("/", 1)[-1] for r in nxt]
    assert names == ["548e0f3a-SharedSharedShar.js", "548e0f3a-SideEffectSideEf.js"]   # cap 5 reached
    assert nxt[0].priority == E.PRIO_PRELOAD - E.PRIO_DATA_STEP                       # import of a data chunk
    assert any("max_chunks=5" in x for x in sp.limits_hit) and sp._pump() == []
    sp.queue_chunk("../../etc/passwd", 99)                                            # unsafe names ignored
    assert not sp._heap


def test_spider_adds_extract_middleware():
    from scrapy.settings import Settings

    from higgsfield_scraper import settings as project_settings
    from higgsfield_scraper.scrapers.models.spider import ModelsSpider
    s = Settings()
    s.setmodule(project_settings)
    ModelsSpider.update_settings(s)
    mws = s.getdict("DOWNLOADER_MIDDLEWARES")
    assert mws[ModelsSpider.EXTRACT_MW] == 582 and mws["higgsfield_scraper.middlewares.HttpArchiveMiddleware"] == 580


# ------------------------------------------------------------------ options / registry
def test_options_and_registry():
    s = build()
    assert s.pages == list(E.DEFAULT_PAGES) and s.max_chunks == 800 and s.with_costs and s.with_shots
    assert selection_from_dict(s.to_dict()) == s and default_label(s) == "registry"
    assert build(pages="ai/video").pages == ["/ai/video"] and default_label(build(pages="ai/video")) == \
        "registry-1pages"
    with pytest.raises(ValueError):
        build(pages="https://evil.example/x")
    with pytest.raises(ValueError):
        build(max_chunks=-1)
    assert "models" in registry.available() and registry.DEFAULT_SCRAPER == "pricing"
    assert set(SCRAPER.model_by_kind) == set(SCRAPER.id_field_by_kind)
    assert not SCRAPER.personal_data


# ------------------------------------------------------------------ the real saved bundle (if present)
@pytest.mark.skipif(not (JS2 / "548e0f3a-Kxdpq5YjqY_JH5zf.js").exists(), reason="samples/higgsfield/js2 not present")
def test_real_bundle_chunks():
    reg = extract_chunk("k", (JS2 / "548e0f3a-Kxdpq5YjqY_JH5zf.js").read_text(encoding="utf-8"))
    assert len(reg["jobs"]) >= 100 and not any(j.get("unparsed") for j in reg["jobs"])
    assert sum(1 for j in reg["jobs"] if j.get("settings")) >= 90
    routes = extract_chunk("r", (JS2 / "548e0f3a-j8lj58UEh2bbmHmn.js").read_text(encoding="utf-8"))["routes"]
    assert routes["seedance_2_5"] == "/jobs/v2/seedance_2_5" and len(routes) >= 80
    gate = extract_chunk("g", (JS2 / "548e0f3a-tCLaulKUdGQfxqgZ.js").read_text(encoding="utf-8"))
    video = next(t for t in gate["gating_tables"] if "wan4_0" in t["ids"])
    assert video["default_model"] == "seedance_2_5" and "sora-2" in video["retired"]
