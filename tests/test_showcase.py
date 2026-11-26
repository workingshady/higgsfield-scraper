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
