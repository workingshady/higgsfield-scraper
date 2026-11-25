"""Catalog scraper: parsers per kind, pagination, options, dataset/CSV completeness (offline, fixtures)."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.catalog import SCRAPER, media_urls
from higgsfield_scraper.scrapers.catalog.endpoints import DEFAULT_PUBLIC, KINDS, LOGIN_ONLY, SOURCE_BY_ENDPOINT
from higgsfield_scraper.scrapers.catalog.options import build, default_label, parse_kinds, selection_from_dict
from higgsfield_scraper.scrapers.catalog.parsers import media_refs, media_type, next_params, parse_envelope
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "catalog"
MOTION = "bbab2a35-ccba-45df-8c37-8ea2bd9e395a"


def load(name: str) -> Envelope:
    return Envelope.load(FX / name)


def kinds(entities, kind):
    return [e for e in entities if e["kind"] == kind]


@pytest.fixture
def sel():
    return build(with_samples=True, with_details=True)


def all_entities(sel) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(FX.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if SCRAPER.keep(e, sel):
                v = validate_entity(e)
                out[v["kind"]].append(v)
    return out


def synth(endpoint: str, body, params=None, status=200) -> Envelope:
    """Synthetic envelope for login-only catalogs (no session available to record real ones)."""
    src = SOURCE_BY_ENDPOINT[endpoint]
    return Envelope(endpoint=endpoint, url=f"https://fnf-api-gw.higgsfield.ai/fnf{src.path}", status=status, body=body,
                    params=params or {"size": "100"}, fetched_at=datetime(2026, 11, 25, tzinfo=timezone.utc))


# ------------------------------------------------------------------ parsers (public kinds)
def test_every_fixture_entity_validates(sel):
    ents = all_entities(sel)
    for k in ("catalog_motion", "catalog_motion_detail", "catalog_motion_sample", "catalog_avatar",
              "catalog_avatar_preset", "catalog_voice", "catalog_reference_voice", "catalog_sound", "catalog_style",
              "catalog_soul_sample", "catalog_viral_type", "catalog_viral_preset", "catalog_page"):
        assert ents[k], k
    for k, rows in ents.items():
        for r in rows:
            assert r["source"]["endpoint"].startswith("catalog_")


def test_motions_placeholder_mix_and_extra(sel):
    es = parse_envelope(load("catalog_motions__size-5.json"), sel)
    motions = kinds(es, "catalog_motion")
    assert len(motions) == 5
    kling = next(m for m in motions if m["id"] == MOTION)
    assert kling["preset_family"] == "kling" and kling["has_preview"] is False and kling["media"] == []
    hf = [m for m in motions if m["preset_family"] == "higgsfield"]
    assert all(m["has_preview"] and m["media"][0]["url"].startswith("https://") for m in hf)
    mix = next(m for m in motions if m["is_collection"])
    assert mix["mix"] and all("id" in x and "name" in x for x in mix["mix"])
    assert all(m["extra"] == {} for m in motions)          # every key of the API item is mapped
    page = kinds(es, "catalog_page")[0]
    assert page["total"] == 419 and page["first_page"] and page["next_cursor"] == "-250"


def test_motion_detail_parsed_and_merged(sel):
    d = parse_envelope(load(f"catalog_motion_detail__motion_id-{MOTION}.json"), sel)
    assert [e["kind"] for e in d] == ["catalog_motion_detail"]        # detail responses produce no page entity
    det = d[0]
    assert det["description"] and {m["role"] for m in det["media"]} >= {"preview", "preview_thumbnail",
                                                                         "preview_optimized"}
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    m = next(x for x in ds["motions"] if x["id"] == MOTION)
    assert m["detail_fetched"] and m["has_preview"] and m["description"] == det["description"]
    assert ds["summary"]["motions_with_details"] == 1


def test_motion_samples(sel):
    es = parse_envelope(load(f"catalog_motion_samples__motion_id-{MOTION}__size-100.json"), sel)
    s = kinds(es, "catalog_motion_sample")
    assert len(s) == 3 and all(x["motion_id"] == MOTION and x["sample_uid"] == f"{MOTION}:{x['id']}" for x in s)
    assert s[0]["media"][0]["type"] == "video" and s[0]["media"][0]["placeholder"] is None   # dropped by default
    keep = parse_envelope(load(f"catalog_motion_samples__motion_id-{MOTION}__size-100.json"),
                          build(keep_placeholders=True))
    assert kinds(keep, "catalog_motion_sample")[0]["media"][0]["placeholder"].startswith("data:image")


def test_avatars_and_presets(sel):
    a = kinds(parse_envelope(load("catalog_avatars__size-100.json"), sel), "catalog_avatar")[0]
    assert a["voice_id"] and a["input_image_id"] and {m["role"] for m in a["media"]} == {"preview", "input_image"}
    p = kinds(parse_envelope(load("catalog_avatar_presets__size-100.json"), sel), "catalog_avatar_preset")[0]
    assert p["quality"] and p["chunks_count"] is not None and p["media"][0]["type"] == "video"


def test_voices_reference_voices_sounds(sel):
    v = kinds(parse_envelope(load("catalog_voices__size-100.json"), sel), "catalog_voice")[0]
    assert v["voice_url"] and v["gender"] and isinstance(v["is_gpt"], bool)
    assert {m["role"]: m["type"] for m in v["media"]} == {"voice": "audio", "image": "image", "waveform": "json"}
    r = kinds(parse_envelope(load("catalog_reference_voices__size-100.json"), sel), "catalog_reference_voice")[0]
    assert r["voice_type"] == "preset" and r["audio_url"].endswith(".mp3") and "elevenlabs" in r["supported_models"]
    s = kinds(parse_envelope(load("catalog_sounds__size-100.json"), sel), "catalog_sound")[0]
    assert s["sound_url"] and s["media"][0]["type"] == "audio"


def test_styles(sel):
    st = kinds(parse_envelope(load("catalog_styles__size-100.json"), sel), "catalog_style")
    assert len(st) == 5 and all(x["params"] and x["preset_family"] == "higgsfield" for x in st)


def test_soul_samples_pseudonymous(sel):
    ss = kinds(parse_envelope(load("catalog_soul_samples__size-500.json"), sel), "catalog_soul_sample")
    assert len(ss) == 3
    s = ss[0]
    assert s["user_id"] == "redacted_user" and s["created_at"].endswith("+00:00")
    assert s["prompt"] and s["style_id"] and s["style_name"] and s["result_url"]
    assert not any(k in s for k in ("username", "avatar_url", "profile", "user"))
    assert s["extra"].keys() >= {"board_ids", "meta"}
    v = validate_entity(s)
    assert datetime.fromisoformat(v["created_at"].replace("Z", "+00:00")).tzinfo is not None


def test_viral_types_and_presets(sel):
    t = kinds(parse_envelope(load("catalog_viral_types__lang-en.json"), sel), "catalog_viral_type")
    assert len(t) == 6 and t[0]["lang"] == "en" and t[0]["slug"]
    p = kinds(parse_envelope(load("catalog_viral_presets__lang-en.json"), sel), "catalog_viral_preset")[0]
    assert p["preset_kind"] == "chain" and p["price_matrix"] and p["inputs"]
    assert p["min_credit_units"] <= p["default_credit_units"] <= p["max_credit_units"]
    assert {"preview", "preview_main", "preview_thumbnail"} <= {m["role"] for m in p["media"]}
    assert p["extra"] == {}
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    assert all(set(x["type_slugs"]) <= {y["slug"] for y in ds["viral_types"]} for x in ds["viral_presets"])
    assert any(x["type_slugs"] for x in ds["viral_presets"])


def test_non_200_yields_nothing(sel):
    assert parse_envelope(load("catalog_soul_styles__lang-en__size-100.json"), sel) == []


# ------------------------------------------------------------------ login-only (synthetic bodies)
def test_generic_login_only_parsers(sel):
    body = {"items": [{"id": "s1", "name": "Grillz", "media": {"url": "https://x/a.webp", "type": "static"},
                       "categories": ["selfie"], "weird": 1}], "total": 1, "cursor": None}
    st = kinds(parse_envelope(synth("catalog_soul_cinematic_styles", body), sel), "catalog_soul_style")[0]
    assert st["uid"] == "cinematic:s1" and st["style_set"] == "cinematic" and st["extra"] == {"weird": 1}
    assert st["media"][0]["role"] == "media" and st["media"][0]["type"] == "image"
    mm = kinds(parse_envelope(synth("catalog_kling2_6_motions", body), sel), "catalog_model_motion")[0]
    assert mm["model_family"] == "kling2_6" and mm["uid"] == "kling2_6:s1"
    color = {"items": [{"id": "c1", "type": "preset"}, {"id": "c2", "type": "user"}], "has_more": False}
    cs = kinds(parse_envelope(synth("catalog_color_presets", color), sel), "catalog_color_preset")
    assert [c["id"] for c in cs] == ["c1"]                         # a user's own presets are not catalog data
    mk = parse_envelope(synth("catalog_marketing_presets", body, {"size": "100", "category_id": "cat9"}), sel)
    assert kinds(mk, "catalog_marketing_preset")[0]["category_id"] == "cat9"
    for e in (st, mm, cs[0], kinds(mk, "catalog_marketing_preset")[0]):
        validate_entity(e)


# ------------------------------------------------------------------ pagination
def test_next_params_styles():
    motions = SOURCE_BY_ENDPOINT["catalog_motions"]
    assert next_params(motions, {"items": [1], "total": 419, "cursor": -269}, {"size": "100"}, 100) == \
        {"size": "100", "cursor": "-269"}
    assert next_params(motions, {"items": [], "cursor": None}, {"size": "100"}, 0) is None
    assert next_params(motions, {"items": [1], "cursor": 5}, {"cursor": "5"}, 1) is None       # no progress
    ref = SOURCE_BY_ENDPOINT["catalog_reference_voices"]
    assert next_params(ref, {"has_more": True, "user_cursor": None, "preset_cursor": 9}, {"size": "10"}, 10) == \
        {"size": "10", "preset_cursor": "9"}
    assert next_params(ref, {"has_more": False, "preset_cursor": 9}, {}, 10) is None
    viral = SOURCE_BY_ENDPOINT["catalog_viral_presets"]
    assert next_params(viral, {"presets": [1] * 50, "total": 87, "offset": 0, "limit": 50}, {"lang": "en"}, 50) == \
        {"lang": "en", "offset": "50", "limit": "50"}
    assert next_params(viral, {"presets": [1] * 87, "total": 87, "offset": 0, "limit": None}, {"lang": "en"}, 87) \
        is None
    soul = SOURCE_BY_ENDPOINT["catalog_soul_samples"]
    assert next_params(soul, {"items": [1], "total": 9, "cursor": 1754887483.661422}, {"size": "1"}, 1)["cursor"] \
        == "1754887483.661422"
    types = SOURCE_BY_ENDPOINT["catalog_viral_types"]
    assert next_params(types, {"items": [1], "cursor": 3}, {}, 1) is None                      # not paginated


def make_spider(sel, **common):
    from higgsfield_scraper.scrapers.catalog.spider import CatalogSpider
    sp = CatalogSpider(selection=sel, common=CommonOptions(**{"auth": "off", **common}))
    return sp


def test_spider_build_requests_public_and_login(sel):
    sp = make_spider(build())
    urls = [r.url for r in sp.build_requests()]
    assert len(urls) == len(DEFAULT_PUBLIC) - 0 and all("[auth]" not in u for u in urls)
    assert not any(r.meta["auth"] for r in make_spider(build()).build_requests())
    reqs = list(make_spider(build(kinds="all", include_login_only="yes")).build_requests())
    login = [r for r in reqs if r.meta["auth"] == "required"]
    assert {r.meta["endpoint"] for r in login} >= {"catalog_soul_styles", "catalog_kling_motions",
                                                    "catalog_marketing_catalog", "catalog_camera_settings"}
    assert not any("{id}" in r.url for r in reqs)
    assert any("lang=en" in r.url for r in reqs if r.meta["endpoint"] == "catalog_viral_presets")


def _resp(req):
    return SimpleNamespace(meta=req.meta)


def test_spider_follow_up_pagination_samples_details():
    sp = make_spider(build(kinds="motion", with_samples=True, with_details=True), max_pages=3)
    first = next(r for r in sp.build_requests() if r.meta["endpoint"] == "catalog_motions")
    env = load("catalog_motions__size-5.json")
    ents = parse_envelope(env, sp.selection)
    out = list(sp.follow_up(env, ents, _resp(first)))
    eps = [r.meta["endpoint"] for r in out]
    assert eps[0] == "catalog_motions" and "cursor=-250" in out[0].url
    assert eps.count("catalog_motion_samples") == 3 and eps.count("catalog_motion_detail") == 3   # capped by max_pages
    det = next(r for r in out if r.meta["endpoint"] == "catalog_motion_detail")
    assert det.url.endswith(f"/motions/{det.meta['params']['motion_id']}")
    assert any("max_pages=3" in x for x in sp.limits_hit)
    assert sp.totals["motion"] == 419


def test_spider_marketing_presets_from_categories():
    sp = make_spider(build(kinds="marketing_preset", include_login_only="yes"))
    first = list(sp.build_requests())
    assert [r.meta["endpoint"] for r in first] == ["catalog_marketing_catalog"]
    env = synth("catalog_marketing_catalog", {"categories": [{"id": "c1", "name": "Ads"}]}, {})
    out = list(sp.follow_up(env, parse_envelope(env, sp.selection), _resp(first[0])))
    assert len(out) == 1 and out[0].url.split("?")[0].endswith("/marketing-studio-v2/categories/c1/presets")
    assert out[0].meta["auth"] == "required" and out[0].meta["params"]["category_id"] == "c1"


def test_max_items_stops_pagination():
    sp = make_spider(build(kinds="motion"), max_items=5)
    first = next(iter(sp.build_requests()))
    sp.count_primary(5)
    env = load("catalog_motions__size-5.json")
    out = list(sp.follow_up(env, parse_envelope(env, sp.selection), _resp(first)))
    assert out == [] and any("max_items" in x for x in sp.limits_hit)


# ------------------------------------------------------------------ options
def test_options_kinds_and_login_resolution():
    assert parse_kinds(None) is None
    assert parse_kinds("motions, catalog_voice,Sound") == ["motion", "voice", "sound"]
    assert parse_kinds("all") == list(KINDS) and parse_kinds("login") == list(LOGIN_ONLY)
    with pytest.raises(ValueError):
        parse_kinds("nope")
    s = build()
    assert s.resolve_kinds(authed=False) == list(DEFAULT_PUBLIC)
    assert set(s.resolve_kinds(authed=True)) == set(DEFAULT_PUBLIC) | set(LOGIN_ONLY)
    assert build(include_login_only="yes").resolve_kinds(False)[-1] == LOGIN_ONLY[-1]
    assert not set(build(kinds="all", include_login_only="no").resolve_kinds(True)) & set(LOGIN_ONLY)
    assert "motion_sample" in build(with_samples=True).resolve_kinds(False)
    assert "motion_sample" not in build().resolve_kinds(False)


def test_selection_roundtrip_and_strings():
    s = build(kinds="motion,voice", with_samples=True, lang="de", include_login_only="no")
    assert selection_from_dict(s.to_dict()) == s
    t = selection_from_dict({"kinds": "motion", "with_details": "true", "include_login_only": "yes"})
    assert t.kinds == ["motion"] and t.with_details is True and t.include_login_only == "yes"
    assert default_label(build()) == "public" and default_label(s) == "motion-voice-samples"


def test_keep_filters_kinds():
    s = build(kinds="voice")
    assert SCRAPER.keep({"kind": "catalog_voice"}, s) and SCRAPER.keep({"kind": "catalog_page"}, s)
    assert not SCRAPER.keep({"kind": "catalog_motion"}, s)
    assert not SCRAPER.keep({"kind": "catalog_motion_sample"}, build())
    assert SCRAPER.keep({"kind": "catalog_motion_sample"}, build(with_samples=True))


def test_media_helpers_and_download_modes():
    assert media_type("https://x/a.mp4") == "video" and media_type("https://x/a", "static") == "image"
    assert media_type("https://x/w.json") == "json" and media_type("https://x/a.wav") == "audio"
    assert media_refs({"url": "<placeholder>", "type": "animated"}, "preview") == []
    e = {"kind": "catalog_voice", "media": [{"role": "voice", "url": "https://x/v.wav", "type": "audio"},
                                            {"role": "image", "url": "https://x/i.webp", "type": "image"},
                                            {"role": "waveform", "url": "https://x/w.json", "type": "json"}]}
    assert media_urls(e, "thumbs") == [("image", "https://x/i.webp")]
    assert media_urls(e, "full") == [("voice", "https://x/v.wav")]
    assert len(media_urls(e, "all")) == 3


# ------------------------------------------------------------------ dataset + outputs
def _csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return set(rows[0].keys()) if rows else set(), rows


def test_dataset_meta_summary_and_totals(sel):
    rm = RunMeta(run_id="r1", label="t", scraped_at=datetime(2026, 11, 25, tzinfo=timezone.utc))
    ds = SCRAPER.build_dataset(all_entities(sel), sel, rm)
    t = ds["meta"]["totals_available"]
    assert t["motion"] == 419 and t["voice"] == 82 and t["soul_sample"] == 1263 and t["reference_voice"] is None
    assert ds["meta"]["counts"]["motions"] == 7 and ds["summary"]["counts"]["motion"] == 7
    assert ds["summary"]["by_model_family"]["motion"]["kling"] >= 1
    assert ds["summary"]["login_only"]["soul_style"].startswith("not selected")
    assert ds["summary"]["soul_sample_styles"] and ds["summary"]["motions_without_preview"] >= 1


def test_csvs_contain_every_json_field(tmp_path, sel):
    """Nothing may exist only in JSON: every leaf of every object is a column in its CSV, rows 1:1."""
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    files = SCRAPER.write_outputs(ds, tmp_path)
    assert (tmp_path / "summary.md").exists() and (tmp_path / "schema" / "dataset.schema.json").exists()
    assert (tmp_path / "json" / "motions.json").exists() and len(files) > 20
    drop = lambda d, *ks: {k: v for k, v in d.items() if k not in ks}  # noqa: E731
    checks = {}
    for coll in ("motions", "motion_samples", "avatars", "avatar_presets", "voices", "reference_voices", "sounds",
                 "styles", "soul_samples", "viral_types", "viral_presets", "pages"):
        checks[coll] = [drop(e, "media", "mix", "price_matrix", "inputs") for e in ds[coll]]
        media = [m for e in ds[coll] for m in e.get("media") or []]
        if media:
            checks[f"{coll}_media"] = media
    checks["motion_mix"] = [x for m in ds["motions"] for x in m["mix"] or []]
    checks["viral_preset_prices"] = [p for v in ds["viral_presets"] for p in v["price_matrix"]]
    checks["viral_preset_inputs"] = [i for v in ds["viral_presets"] for i in v["inputs"]]
    checks["soul_sample_styles"] = ds["summary"]["soul_sample_styles"]
    for table, objects in checks.items():
        cols, rows = _csv(tmp_path / "csv" / f"{table}.csv")
        assert len(rows) == len(objects), table
        missing = {k for o in objects for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{table}.csv is missing JSON fields: {sorted(missing)[:10]}"
    meta_keys = {r["key"] for r in _csv(tmp_path / "csv" / "run_meta.csv")[1]}
    assert {"meta.counts.motions", "meta.totals_available.motion", "schema_version"} <= meta_keys


def test_registered():
    from higgsfield_scraper.core import registry
    assert registry.get("catalog") is SCRAPER
    models = registry.all_models()
    assert all(k in models for k in SCRAPER.model_by_kind)
