"""Showcase scraper: parsers per source, privacy, auth gating, options, dataset/CSV completeness, merge script
(offline, fixtures in tests/fixtures/showcase — trimmed and redacted copies of a live run)."""
from __future__ import annotations

import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import pytest

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.showcase import SCRAPER, media_urls
from higgsfield_scraper.scrapers.showcase.endpoints import DEFAULT_WHATS, KINDS, WHATS
from higgsfield_scraper.scrapers.showcase.options import build, default_label, parse_what, selection_from_dict
from higgsfield_scraper.scrapers.showcase.parsers import (creator_key, extract_property_rows, media_key,
                                                          parse_envelope, property_media)
from higgsfield_scraper.scrapers.showcase.schemas import COLLECTION_OF, MODEL_BY_KIND
from higgsfield_scraper.scrapers.showcase.spider import ShowcaseSpider, l10n_titles, route_chunk_of
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "showcase"
ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> Envelope:
    return Envelope.load(FX / name)


def kinds(entities, kind):
    return [e for e in entities if e["kind"] == kind]


@pytest.fixture
def sel():
    return build()


def all_entities(sel) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    for p in sorted(FX.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            key = (e["kind"], e["id"])
            if key not in seen:                     # the framework's dedup pipeline does the same
                seen.add(key)
                out[e["kind"]].append(validate_entity(e))
    return out


# ------------------------------------------------------------------ registry / contract
def test_registered_and_kinds_unique():
    assert "showcase" in registry.available()
    models = registry.all_models()                  # raises if a kind is defined twice
    assert set(KINDS) == set(MODEL_BY_KIND) and all(k.startswith("showcase_") for k in KINDS)
    assert all(models[k] is MODEL_BY_KIND[k] for k in KINDS)
    assert set(COLLECTION_OF) == set(KINDS)
    assert SCRAPER.examples and SCRAPER.personal_data


def test_every_fixture_entity_validates(sel):
    ents = all_entities(sel)
    for k in KINDS:
        assert ents.get(k), f"no fixture produces {k}"
    for es in ents.values():
        for e in es:
            assert e["schema_version"] == 1 and e["source_url"].startswith("http") and e["scraped_at"]
            assert len(e["id"]) == 16


def test_ids_are_stable(sel):
    a = parse_envelope(load("showcase_canvas_templates.json"), sel)
    b = parse_envelope(load("showcase_canvas_templates.json"), sel)
    assert [x["id"] for x in a] == [x["id"] for x in b]


# ------------------------------------------------------------------ sources
def test_canvas_templates(sel):
    es = parse_envelope(load("showcase_canvas_templates.json"), sel)
    assert len(es) == 5 and es[0]["app_url"].startswith("https://higgsfield.ai/canvas/templates/")
    assert all(e["graph_available"] is False for e in es)
    assert es[0]["created_at"].endswith("+00:00")


def test_editing_room_examples_and_projects(sel):
    ex = parse_envelope(load("showcase_videoshop_examples.json"), sel)
    assert ex[0]["example_id"] and ex[0]["edits"] and {m["role"] for m in ex[0]["media"]} >= {"final", "input"}
    assert ex[0]["generation_key"].startswith("media:")
    pr = parse_envelope(load("showcase_videoshop_project_examples.json"), sel)
    proj = kinds(pr, "showcase_editing_room_project")
    rend = kinds(pr, "showcase_editing_room_render")
    assert pr[0]["kind"] == "showcase_editing_room_project"            # parent first (per-kind cap drops children)
    assert len(proj) == 1 and len(rend) == 3 and proj[0]["render_ids"] == [r["version_id"] for r in rend]
    relight = [e for e in proj[0]["edits"] if e["tool"] == "relight"]
    assert relight and relight[0]["params"]["relight"]["lights"][0]["az"] is not None
    assert all(r["generation_key"] and r["job_set_id"] for r in rend)


def test_property_studio_presets(sel):
    es = parse_envelope(load("showcase_property_studio_presets.json"), sel)
    assert len(es) == 4
    tour = es[0]
    assert tour["format"] == "flash-tour" and tour["app"] == "speedramp_walkthrough" and tour["title"]
    roles = [m["role"] for m in tour["media"]]
    assert roles.count("input") == tour["input_count"] and "output" in roles and "video" in roles
    assert es[-1]["title"] is None                     # no translation -> None, never ""
    assert all(e["generation_key"].startswith("static:") for e in es)


def test_property_rows_and_media_mirror_js():
    js = "en=[[`flash-tour`,`02-walnut-loft-house`,{id:`R-iA_7`},3,1920,1080],[`renovation`,`1/bedroom`,{id:`1Zi7Kr`}," \
         "1,2720,1536]]"
    rows = extract_property_rows(js)
    assert rows == [["flash-tour", "02-walnut-loft-house", "R-iA_7", 3, 1920, 1080],
                    ["renovation", "1/bedroom", "1Zi7Kr", 1, 2720, 1536]]
    m = property_media("renovation", "1/bedroom", 1)
    urls = {x["role"]: x["url"] for x in m}
    assert urls["input"].endswith("/app-presets/v1/renovation/1/bedroom/before.webp")
    assert urls["output"].endswith("/app-presets/full-v1/renovation/1/bedroom/after.webp")


def test_route_chunk_and_l10n_helpers():
    js = "x=1,new globalThis.URL(`./548e0f3a-Qhm6yOmmqVylfDqQ.js`,import.meta.url).href),X5=P(`/_private/property-studio/`)"
    assert route_chunk_of(js) == "548e0f3a-Qhm6yOmmqVylfDqQ.js"
    assert route_chunk_of("nothing") is None
    assert l10n_titles({"a": ["Walnut Loft House"], "b": "x", "c": [""]}, {"a", "c", "zz"}) == {"a": "Walnut Loft House"}


def test_explore_curated_feed(sel):
    es = parse_envelope(load("showcase_explore_feed.json"), sel)
    items = kinds(es, "showcase_explore_item")
    vars_ = kinds(es, "showcase_explore_variant")
    assert items and vars_ and es[0]["kind"] == "showcase_explore_item"
    assert items[0]["feed_source"] == "higgsfield" and items[0]["engagement"]["likes"] is None
    assert all(v["item_id"] in {i["item_id"] for i in items} for v in vars_)


def test_explore_community_engagement_and_privacy(sel):
    env = load("showcase_explore_feed_community.json")
    es = parse_envelope(env, sel)
    items = kinds(es, "showcase_explore_item")
    gens = [v for v in kinds(es, "showcase_explore_variant") if v["variant_type"] == "generation"]
    assert items[0]["feed_source"] == "community" and isinstance(items[0]["engagement"]["likes"], int)
    assert gens and gens[0]["publication_id"] and isinstance(gens[0]["publication_engagement"]["likes"], int)
    assert items[0]["publication_ids"] == [g["publication_id"] for g in gens if g["item_id"] == items[0]["item_id"]]
    # default: no profile, only a pseudonymous hash
    assert gens[0]["creator_key"] and len(gens[0]["creator_key"]) == 16 and "creator" not in gens[0]
    blob = json.dumps([validate_entity(e) for e in es])
    assert "REDACTED" not in blob and "avatar" not in blob.replace("avatar_url", "") and '"username"' not in blob
    # opt-in
    on = [v for v in kinds(parse_envelope(env, build(with_profiles=True)), "showcase_explore_variant")
          if v["variant_type"] == "generation"]
    assert on[0]["creator"]["username"] == "REDACTED" and on[0]["creator"]["user_id"].startswith("user_")


def test_effect_samples(sel):
    es = parse_envelope(load("showcase_effect_page.json"), sel)
    assert len(es) == 2
    e = es[0]
    assert e["generation_key"] == f"job:{e['job_id']}" and e["catalog_ref"].startswith("catalog_viral_preset:")
    assert e["source_url"].endswith(f"/effects/examples/{e['preset_slug']}/{e['sample_id']}")
    assert e["media"] and all(m["role"] != "input" for m in e["media"])
    assert all("url" not in json.dumps(v) for v in e["params"].values())   # input URLs live in `inputs`
    assert e["creator_key"] and "creator" not in e


def test_effect_samples_with_profiles_from_unredacted_archive():
    env = load("showcase_effect_page.json")
    for s in env.body["loader"]["initialSamples"]["items"]:
        s["job"]["user"] = {"id": "user_X", "username": "someone", "avatarUrl": "https://a/b.webp", "fullname": "N"}
    off = parse_envelope(env, build())[0]
    on = parse_envelope(env, build(with_profiles=True))[0]
    assert off["creator_key"] == creator_key("user_X") and "creator" not in off
    assert on["creator"] == {"user_id": "user_X", "username": "someone", "avatar_url": "https://a/b.webp"}


def test_api_models(sel):
    es = parse_envelope(load("showcase_api_docs.json"), sel)
    by = {e["endpoint_id"]: e for e in es}
    h = by["minimax/hailuo-2.3/standard/image-to-video"]
    assert h["vendor"] == "minimax" and h["model"] == "hailuo-2.3" and h["variant"] == "standard/image-to-video"
    assert h["in_openapi"] and h["family"] == "Hailuo 2.3" and h["usage_notes"]
    p = {x["name"]: x for x in h["parameters"]}
    assert p["prompt"]["required"] and p["duration"]["enum"] == [6, 10] and p["duration"]["default"] == 6
    g = by["higgsfield/genjutsu/restyle/v1.0"]
    assert g["prices"] and all(x["amount"] is not None for x in g["prices"])
    assert all(x["currency"] is None for x in g["prices"])     # "$" without USD in the text: not mapped blindly
    assert by["higgsfield-ai/soul/standard"]["in_openapi"]      # openapi-only endpoint still listed
    assert "requests/{request_id}/status" not in by


def test_season_login_only_and_personal(sel):
    s = parse_envelope(load("showcase_season.json"), sel)
    assert s[0]["active"] is False and s[0]["top_level_keys"] == []
    env = load("showcase_season.json")
    env.body = {"id": "s1", "name": "Season 1", "starts_at": "2026-01-01T00:00:00Z", "my_points": 5, "rank": 3}
    d = parse_envelope(env, sel)[0]
    assert d["active"] and d["name"] == "Season 1" and d["personal_fields_dropped"] == ["my_points", "rank"]
    dumped = validate_entity(d)
    assert 5 not in dumped.values() and 3 not in dumped.values()          # names only, never the user's values


def test_cms_lists(sel):
    cc = parse_envelope(load("showcase_cinema_controls.json"), sel)
    assert {e["group"] for e in cc} >= {"genre", "era", "light"} and sum(1 for e in cc if e["media"]) > 10
    assert all(e["media"] == [] and e["generation_key"] is None for e in cc if e["group"] == "color")  # no media
    assert all("placeholder" not in json.dumps(e["extra"]) for e in cc)
    for f in ("showcase_faceless_showcases.json", "showcase_intone_explore.json", "showcase_seedance_presets.json",
              "showcase_motion_control_presets.json"):
        es = parse_envelope(load(f), sel)
        assert es and all(e["media"] and e["generation_key"] for e in es), f
        assert all("data:image" not in json.dumps(e) for e in es)


def test_media_key():
    assert media_key("https://x/user_1/hf_20261119_111610_f58010df-5d68-4db4-a6c0-05e40eb6fd4a.mp4") == \
        "f58010df-5d68-4db4-a6c0-05e40eb6fd4a"
    assert media_key("https://x/a.mp4") is None
    assert media_key(None, "F58010DF-5D68-4DB4-A6C0-05E40EB6FD4A") == "f58010df-5d68-4db4-a6c0-05e40eb6fd4a"


def test_non_200_and_unknown_endpoints_yield_nothing(sel):
    env = load("showcase_canvas_templates.json")
    env.status = 404
    assert parse_envelope(env, sel) == []
    env.status, env.endpoint = 200, "showcase_property_studio_page"
    assert parse_envelope(env, sel) == []


# ------------------------------------------------------------------ options
def test_options():
    assert build().resolve() == list(DEFAULT_WHATS) and "season" not in DEFAULT_WHATS
    assert build(what="all").resolve() == list(WHATS)
    assert parse_what("explore,canvas_template") == ["explore_categories", "canvas_templates"]
    with pytest.raises(ValueError):
        parse_what("nope")
    with pytest.raises(ValueError):
        build(explore_sources="x")
    with pytest.raises(ValueError):
        build(lang="fr")
    s = build(what="api_models", explore_pages="0", with_profiles="true")
    assert selection_from_dict(s.to_dict()) == s and s.with_profiles and s.explore_pages == 0
    assert default_label(build()) == "public" and default_label(build(what="all")) == "all"
    assert build(explore_sort="both").explore_sorts() == ["new", "trending"]


# ------------------------------------------------------------------ auth gating (no network)
def _requests(what, auth="auto", **kw):
    sp = ShowcaseSpider(selection=build(what=what, **kw), common=CommonOptions(auth=auth))
    return list(sp.build_requests()), sp


def test_public_requests_never_carry_auth():
    reqs, _ = _requests(None)
    assert reqs and all(r.meta.get("auth") is False for r in reqs)
    assert all("Authorization" not in r.headers for r in reqs)
    assert not any(r.meta["endpoint"] == "showcase_season" for r in reqs)        # login-only: off by default


def test_season_is_login_required_and_opt_in():
    reqs, _ = _requests("season")
    assert [r.meta["endpoint"] for r in reqs] == ["showcase_season"] and reqs[0].meta["auth"] == "required"
    reqs, sp = _requests("all")
    season = [r for r in reqs if r.meta["endpoint"] == "showcase_season"]
    assert len(season) == 1 and all(r.meta["auth"] is False for r in reqs if r not in season)
    reqs, sp = _requests("season", auth="off")
    assert reqs == [] and any("auth off" in x for x in sp.limits_hit)


def test_explore_page_caps():
    reqs, sp = _requests("explore_categories", explore_sort="both", explore_pages=1)
    feeds = [r for r in reqs if r.meta["endpoint"] == "showcase_explore_feed"]
    assert len(feeds) == 3            # higgsfield (trending only) + community new + community trending
    assert any("view=v2" in r.url for r in feeds) and not any("source=higgsfield&" in r.url and "sort=" in r.url
                                                               for r in feeds)
    assert sp._explore("community", "new", 2) is None and sp.limits_hit


def test_media_urls_modes(sel):
    e = validate_entity(parse_envelope(load("showcase_videoshop_examples.json"), sel)[0])
    assert media_urls(e, "full") and all(u.endswith(".mp4") for _, u in media_urls(e, "full"))
    assert all(u.endswith((".webp", ".jpg", ".png")) for _, u in media_urls(e, "thumbs"))
    assert len(media_urls(e, "all")) >= len(media_urls(e, "full")) + len(media_urls(e, "thumbs"))


# ------------------------------------------------------------------ dataset / CSV
def _csv(path: Path):
    with path.open(encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return set(r.fieldnames or []), rows


def test_dataset_and_csvs_complete(tmp_path, sel):
    from higgsfield_scraper.scrapers.showcase.dataset import CHILD_LISTS
    ds = SCRAPER.build_dataset(all_entities(sel), build(what="all"), RunMeta(totals={"api_models": 83}))
    assert ds["summary"]["counts"]["api_models"] >= 3 and ds["meta"]["totals_available"]["api_models"] == 83
    assert ds["summary"]["generation_keys"] > 10 and "season" in ds["summary"]["login"]
    SCRAPER.write_outputs(ds, tmp_path)
    assert (tmp_path / "schema" / "dataset.schema.json").exists() and (tmp_path / "summary.md").exists()
    for coll in COLLECTION_OF.values():
        children = CHILD_LISTS.get(coll, ())
        objs = [{k: v for k, v in e.items() if k not in children} for e in ds[coll]]
        cols, rows = _csv(tmp_path / "csv" / f"{coll}.csv")
        assert len(rows) == len(objs), coll
        missing = {k for o in objs for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{coll}.csv missing {sorted(missing)[:8]}"
        for f in children:
            kids = [c for e in ds[coll] for c in e.get(f) or []]
            cols, rows = _csv(tmp_path / "csv" / f"{coll}__{f}.csv")
            assert len(rows) == len(kids), f"{coll}__{f}"
            if kids and isinstance(kids[0], dict):
                missing = {k for o in kids for k in flatten(o)} - cols
                missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
                assert not missing, f"{coll}__{f}.csv missing {sorted(missing)[:8]}"


# ------------------------------------------------------------------ merge_generations.py
def _merge_module():
    spec = importlib.util.spec_from_file_location("merge_generations", ROOT / "scripts" / "merge_generations.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(tmp_path: Path, name: str, scraper: str, colls: dict) -> Path:
    d = tmp_path / name / "output"
    d.mkdir(parents=True)
    (d / "dataset.json").write_text(json.dumps({"meta": {"scraper": scraper, "run_id": name}, **colls}),
                                    encoding="utf-8")
    return d.parent


def test_merge_generations_dedupes_across_sources(tmp_path):
    m = _merge_module()
    job, pub = "d3a99a04-115c-0bae-3f1e-ce535b1e9850", "89f5f485-a602-4add-91de-4c7a21a540bc"
    out_uuid = "11831e74-9312-4129-bdd9-b475b371289a"
    out = f"https://d8j0ntlcm91z4.cloudfront.net/user_X/{out_uuid}.mp4"
    inp = "https://d2ol7oe51mr4n9.cloudfront.net/user_X/9f811c36-484f-43af-a40e-7f838be67064.mp4"
    community = _run(tmp_path, "c", "community", {"generations": [
        {"generation_id": job, "publication_id": pub, "prompt": "p", "model_id": "kling",
         "results": [{"name": "raw", "url": out}], "engagement": {"likes": 5, "views": 50}},
        {"generation_id": "aaaaaaaa-115c-0bae-3f1e-ce535b1e9850", "results": [{"url": inp}], "prompt": "q"}]})
    showcase = _run(tmp_path, "s", "showcase", {
        "effect_samples": [{"generation_key": f"job:{job}", "media_keys": [f"media:{out_uuid}"], "job_id": job,
                            "inputs": [{"url": inp}], "media": [{"role": "output", "url": out}]}],
        "explore_variants": [{"generation_key": f"media:{out_uuid}", "media_keys": [f"media:{out_uuid}"],
                              "publication_id": pub, "publication_engagement": {"likes": 7}}],
        "api_models": [{"endpoint_id": "x", "prompt": "never a generation"}]})
    recs = m.load_records([community, showcase])
    rows, per_source, pairs = m.merge(recs)
    merged = [r for r in rows if r["job_id"] == job]
    assert len(merged) == 1 and len(merged[0]["sources"]) == 3 and merged[0]["likes"] == 7
    assert merged[0]["prompt"] == "p" and merged[0]["model"] == "kling"
    # the input video shared by two records never merges them
    assert len(rows) == 2 and per_source["showcase:effect_samples"] == 1
    assert pairs["community:generations + showcase:effect_samples"] == 1
    m.write(rows, per_source, pairs, len(recs), tmp_path / "idx")
    assert (tmp_path / "idx" / "generations_index.csv").exists()
    rep = json.loads((tmp_path / "idx" / "duplicates.json").read_text(encoding="utf-8"))
    assert rep["unique_generations"] == 2 and rep["duplicates"] == 2


def test_merge_project_publication_id_is_not_a_generation_key(tmp_path):
    m = _merge_module()
    proj = _run(tmp_path, "p", "projects", {"assets": [
        {"asset_id": "a1", "publication_id": "P", "job_set_id": "j1", "url": "https://cdn.higgsfield.ai/u/" +
         "11111111-1111-1111-1111-111111111111.mp4"},
        {"asset_id": "a2", "publication_id": "P", "job_set_id": "j2", "url": "https://cdn.higgsfield.ai/u/" +
         "22222222-2222-2222-2222-222222222222.mp4"}]})
    rows, _, _ = m.merge(m.load_records([proj]))
    assert len(rows) == 2


# ------------------------------------------------------------------ Shorts Studio (AI Reels), opt-in
# Fixtures: trimmed copies of a live run (2026-11-26). showcase_reels_comments.json is SYNTHETIC (no live thread had
# comments yet) and follows the real fnf-community entity-comments shape (tests/fixtures/community).
REELS_HF = "showcase_reels_preset_detail_higgsfield.json"
REELS_COMMUNITY = "showcase_reels_preset_detail_community.json"


def test_reels_curated_preset(sel):
    env = load(REELS_HF)
    (e,) = parse_envelope(env, sel)
    detail = env.body["detail"]
    assert e["kind"] == "showcase_reels_preset" and e["preset_source"] == "higgsfield"
    assert e["source_url"] == f"https://higgsfield.ai/shorts-studio/{e['preset_id']}"
    assert e["prompt"] == detail["prompt"] and e["prompt"] and e["script"]
    assert e["job_set_type"] == "ai_reels_v1" and e["category_label"] == "Style transfer"
    assert e["reference_platform"] == "instagram" and e["reference_url"].startswith("https://www.instagram.com/")
    assert e["reference_engagement"]["views"] == detail["views"]           # the REFERENCE reel's stats
    assert e["engagement"]["uses"] == env.body["listed"]["recreates"] and e["engagement"]["likes"] is None
    assert e["reference_author_handle"] is None and "creator" not in e     # handle only with --with-profiles
    roles = [m["role"] for m in e["media"]]
    assert roles[:3] == ["output", "output_compressed", "output_thumbnail"]
    assert e["generation_key"] == f"media:{detail['generated_video_media']['media_id']}"
    assert {m["role"] for m in e["inputs"]} >= {"reference", "character"}
    assert not any(k.startswith("media:") and k[6:] in json.dumps(e["inputs"]) for k in e["media_keys"])
    validate_entity(e)


def test_reels_community_preset(sel):
    (e,) = parse_envelope(load(REELS_COMMUNITY), sel)
    assert e["preset_source"] == "community" and e["own_recording"] is True and e["instructions"]
    assert e["publication_id"] and f"pub:{e['publication_id']}" in e["media_keys"]
    assert e["creator_key"] and e["creator_key_basis"] in ("user_id", "username") and "creator" not in e
    assert any(m["role"].startswith("own_video_0") for m in e["inputs"])
    assert e["reference_engagement"] is None and e["source_url"].endswith("?source=community")
    validate_entity(e)


def _reels_env(listed: dict, detail=None) -> Envelope:
    env = load(REELS_COMMUNITY)
    env.body = {"listed": listed, "detail": detail, "detail_status": 404 if detail is None else 200,
                "categories": [], "lang": "en"}
    return env


def test_reels_profiles_and_missing_detail():
    listed = {"id": "00000000-0000-4000-8000-0000000000a1", "slug": "community-fake1", "source": "community",
              "title": "Fake", "generated_video_media": {"url": "https://d8j0ntlcm91z4.cloudfront.net/community-"
                                                                "presets/00000000-0000-4000-8000-0000000000a1/g.mp4"},
              "author_handle": "fake_handle",
              "author": {"username": "fake_creator",
                         "avatar_url": "https://d2ol7oe51mr4n9.cloudfront.net/user_FakeReelsAuthor1/a.png"}}
    (e,) = parse_envelope(_reels_env(listed), build())                  # detail 404: kept from the list item
    assert e["prompt"] is None and e["creator_key"] == creator_key("user_FakeReelsAuthor1")
    assert e["creator_key_basis"] == "user_id" and "fake_creator" not in json.dumps(e)
    assert "fake_handle" not in json.dumps(e)
    (p,) = parse_envelope(_reels_env(listed), build(with_profiles=True))
    assert p["creator"] == {"user_id": "user_FakeReelsAuthor1", "username": "fake_creator",
                            "avatar_url": listed["author"]["avatar_url"]}
    assert p["reference_author_handle"] == "fake_handle"
    no_avatar = {**listed, "author": {"username": "fake_creator", "avatar_url": None}}
    (n,) = parse_envelope(_reels_env(no_avatar), build())
    assert n["creator_key_basis"] == "username" and n["creator_key"] != e["creator_key"]
    other = {"id": "different", "prompt": "not mine"}                    # a detail for another id is ignored
    (o,) = parse_envelope(_reels_env(listed, other), build())
    assert o["prompt"] is None and o["preset_id"] == listed["id"]


def test_reels_comments(sel):
    (c,) = parse_envelope(load("showcase_reels_comments.json"), sel)
    assert c["kind"] == "showcase_reels_comment" and c["preset_id"] and c["publication_id"]
    assert c["creator_key"] == creator_key("user_FakeReelsCommenter1") and "creator" not in c
    assert c["likes"] == 2 and c["reply_count"] == 1 and c["reactions"] == [{"emoji": "🔥", "count": 1}]
    validate_entity(c)


def test_reels_are_opt_in():
    from higgsfield_scraper.scrapers.showcase.endpoints import OPT_IN_WHATS, PUBLIC_WHATS
    assert OPT_IN_WHATS == {"reels_presets", "reels_comments"}
    assert not OPT_IN_WHATS & set(DEFAULT_WHATS) and not OPT_IN_WHATS & set(PUBLIC_WHATS)
    assert OPT_IN_WHATS <= set(build(what="all").resolve())
    assert parse_what("reels") == ["reels_presets"] and parse_what("reels_comment") == ["reels_comments"]
    reqs, _ = _requests(None)
    assert not any("ai-reels" in r.url for r in reqs)
    reqs, _ = _requests("reels_presets")
    assert [r.url.split("?")[1] for r in reqs] == ["lang=en", "lang=en&source=community"]
    assert all(r.meta["auth"] is False and "Authorization" not in r.headers for r in reqs)
    reqs, _ = _requests("reels_comments")                               # curated presets have no threads
    assert [r.meta["params"]["list"] for r in reqs] == ["community"]
    reqs, sp = _requests("reels_comments", reels_sources="higgsfield")
    assert reqs == [] and sp.limits_hit
    with pytest.raises(ValueError):
        build(reels_sources="tiktok")
    s = build(what="reels_presets", reels_sources="community")
    assert selection_from_dict(s.to_dict()) == s


def test_reels_follow_up_caps():
    import scrapy
    from scrapy.http import TextResponse
    sp = ShowcaseSpider(selection=build(what="reels_presets,reels_comments"), common=CommonOptions(max_items=1))
    sp.whats = sp.selection.resolve()
    env = load("showcase_reels_presets_community.json")
    resp = TextResponse(url=env.url, body=b"{}", request=scrapy.Request(env.url, meta={"reels_source": "community"}))
    out = [r for r in sp.follow_up(env, [], resp) if isinstance(r, scrapy.Request)]
    eps = [r.meta["endpoint"] for r in out]
    assert eps.count("showcase_reels_preset_detail") == 1 and eps.count("showcase_reels_comments") == 1
    det = next(r for r in out if r.meta["endpoint"] == "showcase_reels_preset_detail")
    author = det.meta["reels"]["listed"].get("author")
    assert author is None or set(author) == {"id_hash", "id_basis", "badge"}   # archive: no username/avatar
    assert sp.totals["reels_presets_community"] == 3 and any("max_items=1" in x for x in sp.limits_hit)
    com = next(r for r in out if r.meta["endpoint"] == "showcase_reels_comments")
    assert "/entities/generation_publication/" in com.url and com.meta["auth"] is False


def test_reels_generation_keys_for_merge(sel):
    m = _merge_module()
    ds = SCRAPER.build_dataset(all_entities(sel), build(what="all"), RunMeta())
    for rec in ds["reels_presets"]:
        keys = m.record_keys("showcase", "reels_presets", rec)
        assert rec["generation_key"] in keys and any(k.startswith("media:") for k in keys)
    assert m.record_keys("showcase", "reels_comments", ds["reels_comments"][0]) == []


# ------------------------------------------------------------------ COMPLETENESS fixes (#2, #7, #8, #9, #10, #12, #13)
# showcase_effect_page_template.json: trimmed copy of a live effect page (2026-11-26) with fake user ids.
def test_explore_inputs_keep_source_role_and_type(sel):
    env = load("showcase_explore_feed_community.json")
    es = parse_envelope(env, sel)
    inputs = [i for v in kinds(es, "showcase_explore_variant") for i in v["inputs"]]
    assert inputs and all(i["role"] == "input" for i in inputs)                 # unchanged
    assert all(i["source_role"] and i["source_type"] for i in inputs)
    raw = [a for it in env.body["items"] for v in it["variants"] for a in v.get("input_assets") or []]
    assert [i["source_role"] for i in inputs] == [a["role"] for a in raw]


def test_effect_sample_settings_and_source_roles(sel):
    env = load("showcase_effect_page_template.json")
    samples = kinds(parse_envelope(env, sel), "showcase_effect_sample")
    raw = env.body["loader"]["initialSamples"]["items"]
    assert len(samples) == len(raw) == 2
    s, r = samples[0], raw[0]
    assert s["raw_params"] == r["job"]["rawParams"]                             # verbatim
    assert s["provider"] == r["job"]["params"]["provider"] and s["prompt_enhance"] is False
    assert s["is_reference"] is False
    assert s["preset_preview_url"] == r["presetPreview"]["source"]
    assert s["preset_poster_url"] == r["presetPreview"]["posterUrl"]
    assert s["inputs"][0]["role"] == "input" and s["inputs"][0]["source_role"] == "start_image"
    assert s["inputs"][0]["source_type"] == "media_input"
    assert s["creator_uid_key"] == s["creator_key"] == creator_key("user_FakeEffectUser1")
    assert all("url" not in json.dumps(v) for v in s["params"].values())        # params unchanged (cleaned)
    validate_entity(s)


def test_effect_preset_template(sel):
    env = load("showcase_effect_page_template.json")
    es = parse_envelope(env, sel)
    assert es[-1]["kind"] == "showcase_effect_preset" and es[0]["kind"] == "showcase_effect_sample"
    p = es[-1]
    raw = env.body["loader"]["preset"]
    assert p["preset_id"] == raw["id"] and p["slug"] == "cutout" and p["catalog_ref"].endswith(raw["id"])
    first = p["preset_inputs"][0]
    assert first["input_id"] == raw["inputs"][0]["id"] and first["min"] == 1 and first["required"] is True
    assert first["binds_to"] == raw["inputs"][0]["binds_to"]
    assert p["preset_inputs"][1]["binds_to"] == [raw["inputs"][1]["binds_to"]]  # single object -> list
    assert p["param_choices"] == raw["param_choices"] and p["pricing_type"] == "matrix"
    assert [x["credit_units"] for x in p["price_matrix"]] == [x["credit_units"] for x in raw["price_matrix"]]
    assert p["price_matrix"][0]["params"] == {} and p["price_matrix"][1]["params"]
    roles = {m["role"] for m in p["media"]}
    assert {"preview", "preview_full", "preview_thumbnail", "widescreen"} <= roles
    assert p["description"] and p["duration_s"] == raw["duration"]
    validate_entity(p)
    assert media_urls(p, "all") == []                    # previews duplicate the catalog preset: never downloaded
    # the minimal page fixture (no template data) still emits only its samples
    assert {e["kind"] for e in parse_envelope(load("showcase_effect_page.json"), sel)} == {"showcase_effect_sample"}


def test_intone_compressed_video(sel):
    env = load("showcase_intone_explore.json")
    es = parse_envelope(env, sel)
    e, raw = es[0], env.body["items"][0]["video"]["compressed_video"]
    (c,) = [m for m in e["media"] if m["role"] == "video_compressed"]
    assert (c["url"], c["width"], c["height"]) == (raw["url"], raw["width"], raw["height"])
    assert c["extra"]["size_bytes"] == raw["size_bytes"] and c["type"] == "video"
    assert e["media"][-1] is c and c["media_key"] not in json.dumps(e["media_keys"])   # appended; keys unchanged
    assert c["url"] not in [u for _, u in media_urls(validate_entity(e), "full")]


def test_editing_room_take_and_version_thumbnails(sel):
    env = load("showcase_videoshop_project_examples.json")
    es = parse_envelope(env, sel)
    proj, rends = es[0], kinds(es, "showcase_editing_room_render")
    take = env.body["items"][0]["project"]["take"]
    assert proj["take_poster_url"] == take["assets"]["poster"]["url"]
    assert proj["take_preview_url"] == take["assets"]["preview"]["url"]
    assert proj["take_storyboard_vtt_url"] == take["assets"]["storyboard"]["vtt_url"]
    assert proj["take_thumbnail_url"] == take["thumbnail_url"] and proj["take_filename"] == take["filename"]
    versions = env.body["items"][0]["timeline"]["versions"]
    assert [r["thumbnail_url"] for r in rends] == [v.get("thumbnailUrl") for v in versions]
    assert any(r["thumbnail_url"] for r in rends)


def test_reels_recreates_and_uid_key(sel):
    env = load(REELS_HF)
    (e,) = parse_envelope(env, sel)
    assert e["recreates"] == env.body["listed"]["recreates"] == e["engagement"]["uses"]
    (c,) = parse_envelope(load(REELS_COMMUNITY), sel)
    if c["creator_key_basis"] == "user_id":
        assert c["creator_uid_key"] == c["creator_key"]
    else:
        assert c["creator_uid_key"] is None
    (cm,) = parse_envelope(load("showcase_reels_comments.json"), sel)
    assert cm["creator_uid_key"] == cm["creator_key"] == creator_key("user_FakeReelsCommenter1")


def test_creator_uid_key_matches_core_helper():
    from higgsfield_scraper.core.privacy import creator_uid_key
    es = parse_envelope(load("showcase_main_feed.json"), build())
    gens = [v for v in kinds(es, "showcase_main_feed_variant") if v["variant_type"] == "generation"]
    assert gens
    for i, g in enumerate(gens):
        assert g["creator_uid_key"] == creator_uid_key(f"user_FakeMainFeedAuthor{i + 1}") == g["creator_key"]
    # a redacted archive id gives no shared key (the old creator_key stays as it was)
    red = [v for v in kinds(parse_envelope(load("showcase_explore_feed_community.json"), build()),
                            "showcase_explore_variant") if v["variant_type"] == "generation"]
    assert red[0]["creator_key"] and red[0]["creator_uid_key"] is None


# ------------------------------------------------------------------ CMS main feed (opt-in by name)
# showcase_main_feed.json: live page 1 (2026-11-26), cut to 2 genjutsu + 1 game rows, fake author ids.
def test_main_feed_items_and_variants(sel):
    env = load("showcase_main_feed.json")
    es = parse_envelope(env, sel)
    items, vars_ = kinds(es, "showcase_main_feed_item"), kinds(es, "showcase_main_feed_variant")
    assert es[0]["kind"] == "showcase_main_feed_item"                          # parent first (cap drops children)
    assert [i["item_type"] for i in items] == ["genjutsu", "genjutsu", "game"]
    g = items[0]
    raw = env.body["items"][0]["genjutsu"]
    assert g["item_id"] == raw["id"] and g["position"] == 1 and g["feed_session_id"] == env.body["feed_session_id"]
    assert g["engagement"] == {"likes": raw["likes_count"], "views": raw["views_count"],
                               "comments": raw["comments_count"], "uses": raw["times_made"]}
    assert g["job_set_type"] == raw["job_set_type"] and g["title"] and g["description"]
    assert g["original_video"]["url"] == raw["original_video"]["url"] and g["media"] == []
    assert g["variant_ids"] == [v["id"] for v in raw["variants"]]
    gen = next(v for v in vars_ if v["item_id"] == g["item_id"] and v["variant_type"] == "generation")
    assert gen["prompt"] and gen["params"] and gen["publication_id"] in g["publication_ids"]
    assert gen["generation_key"].startswith("media:") and f"pub:{gen['publication_id']}" in gen["media_keys"]
    assert gen["inputs"][0]["source_role"] == "image" and gen["inputs"][0]["role"] == "input"
    orig = next(v for v in vars_ if v["item_id"] == g["item_id"] and v["variant_type"] == "original")
    assert orig["generation_key"] is None and orig["media_keys"] == []
    game = items[2]
    assert game["source_url"].endswith("/playable-ads") and game["engagement"]["likes"] is None
    assert {"poster", "video", "game", "video_compressed"} <= {m["role"] for m in game["media"]}
    assert "data:image" not in json.dumps(game) and "recreate" in game["extra"]
    for e in es:
        validate_entity(e)


def test_main_feed_privacy(sel):
    env = load("showcase_main_feed.json")
    blob = json.dumps([validate_entity(e) for e in parse_envelope(env, sel)])
    assert '"username"' not in blob and "avatar" not in blob.replace("avatar_url", "") and "REDACTED" not in blob
    on = [v for v in kinds(parse_envelope(env, build(with_profiles=True)), "showcase_main_feed_variant")
          if v["variant_type"] == "generation"]
    assert on[0]["creator"]["user_id"] == "user_FakeMainFeedAuthor1"


def test_main_feed_is_opt_in_by_name_only():
    from higgsfield_scraper.scrapers.showcase.endpoints import ALL_SOURCE_NAMES, NAME_ONLY_WHATS, PUBLIC_WHATS
    assert NAME_ONLY_WHATS == {"main_feed"} and "main_feed" in ALL_SOURCE_NAMES
    assert "main_feed" not in DEFAULT_WHATS and "main_feed" not in PUBLIC_WHATS and "main_feed" not in WHATS
    assert "main_feed" not in build(what="all").resolve() and "main_feed" not in build(what="public").resolve()
    assert build(what="all,main_feed").resolve()[-1] == "main_feed"
    assert parse_what("main") == ["main_feed"]
    for what in (None, "public", "all"):
        reqs, _ = _requests(what)
        assert not any("/main-feed" in r.url for r in reqs)
    reqs, _ = _requests("main_feed")
    assert [r.url for r in reqs] == ["https://cms.higgsfield.ai/main-feed?lang=en&size=20"]
    assert reqs[0].meta["auth"] is False and "Authorization" not in reqs[0].headers and "user_id" not in reqs[0].url
    s = build(what="main_feed", main_feed_pages="2")
    assert s.main_feed_pages == 2 and selection_from_dict(s.to_dict()) == s
    assert selection_from_dict({"what": "api_models"}).main_feed_pages == 3     # old manifests: default
    with pytest.raises(ValueError):
        build(main_feed_pages=-1)


def _main_feed_follow(sp, cursor_sent=None, body_cursor="next-1"):
    import scrapy
    from scrapy.http import TextResponse
    env = load("showcase_main_feed.json")
    env.body = {**env.body, "cursor": body_cursor}
    env.params = {**env.params, **({"cursor": cursor_sent} if cursor_sent else {})}
    resp = TextResponse(url=env.url, body=b"{}", request=scrapy.Request(env.url))
    return [r for r in sp.follow_up(env, [], resp) if isinstance(r, scrapy.Request)]


def test_main_feed_cursor_paging_and_caps():
    sp = ShowcaseSpider(selection=build(what="main_feed", main_feed_pages=2), common=CommonOptions())
    first = list(sp.build_requests())
    nxt = _main_feed_follow(sp)
    assert len(first) == 1 and len(nxt) == 1 and nxt[0].url.endswith("&cursor=next-1")
    assert _main_feed_follow(sp, body_cursor="next-2") == [] and any("main_feed_pages=2" in x for x in sp.limits_hit)
    sp = ShowcaseSpider(selection=build(what="main_feed", main_feed_pages=0), common=CommonOptions())
    list(sp.build_requests())
    assert _main_feed_follow(sp, body_cursor=None) == []                       # end of feed
    assert _main_feed_follow(sp, cursor_sent="same", body_cursor="same") == []  # cursor not advancing
    assert len(_main_feed_follow(sp)) == 1                                      # 0 = until the cursor ends
    sp = ShowcaseSpider(selection=build(what="main_feed", main_feed_pages=0), common=CommonOptions(max_pages=1))
    assert len(list(sp.build_requests())) == 1 and _main_feed_follow(sp) == []  # --max-pages
    sp = ShowcaseSpider(selection=build(what="main_feed"), common=CommonOptions(max_items=1))
    list(sp.build_requests())
    sp._kept["showcase_main_feed_item"] = 1
    assert _main_feed_follow(sp) == [] and any("max_items=1" in x for x in sp.limits_hit)


def test_main_feed_generation_keys_merge_with_explore(tmp_path, sel):
    m = _merge_module()
    env = load("showcase_main_feed.json")
    gen = next(v for v in kinds(parse_envelope(env, sel), "showcase_main_feed_variant")
               if v["variant_type"] == "generation")
    keys = m.record_keys("showcase", "main_feed_variants", gen)
    assert gen["generation_key"] in keys and f"pub:{gen['publication_id']}" in keys
    other = "media:" + "11111111-1111-1111-1111-111111111111"
    explore = {"generation_key": other, "media_keys": [other], "publication_id": gen["publication_id"],
               "prompt": "p"}                                                   # same publication, other file key
    run = _run(tmp_path, "s", "showcase", {"main_feed_variants": [validate_entity(gen)],
                                           "explore_variants": [explore]})
    rows, _, pairs = m.merge(m.load_records([run]))
    assert len(rows) == 1 and pairs["showcase:explore_variants + showcase:main_feed_variants"] == 1
