"""Studios scraper: parsers per source, privacy, options, request planning (no network), pagination follow-ups,
dataset/CSV completeness, merge script (offline; fixtures in tests/fixtures/studios are trimmed copies of a live run
with fake user ids and redacted names)."""
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
from higgsfield_scraper.scrapers.studios import SCRAPER, media_urls
from higgsfield_scraper.scrapers.studios.endpoints import (DEFAULT_WHATS, KINDS, STUDIO_MODELS, STUDIOS, WHATS)
from higgsfield_scraper.scrapers.studios.options import build, default_label, parse_what, selection_from_dict
from higgsfield_scraper.scrapers.studios.parsers import author_key, media_key, parse_envelope, redact_author_names
from higgsfield_scraper.scrapers.studios.schemas import COLLECTION_OF, MODEL_BY_KIND
from higgsfield_scraper.scrapers.studios.spider import StudiosSpider
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "studios"
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
    assert "studios" in registry.available()
    models = registry.all_models()                  # raises if a kind is defined twice
    assert set(KINDS) == set(MODEL_BY_KIND) and all(k.startswith("studios_") for k in KINDS)
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
    a = parse_envelope(load("studios_apps.json"), sel)
    b = parse_envelope(load("studios_apps.json"), sel)
    assert [x["id"] for x in a] == [x["id"] for x in b]


# ------------------------------------------------------------------ per source
def test_apps_engagement_and_categories(sel):
    cats = parse_envelope(load("studios_app_categories.json"), sel)
    assert len(cats) >= 3 and all(c["slug"] and c["app_types"] is not None for c in cats)
    apps = parse_envelope(load("studios_apps.json"), sel)
    a = apps[0]
    assert a["listing_id"] and a["app_url"].endswith("higgsfield.app") and a["sort"] == "trending"
    eng = a["engagement"]
    assert isinstance(eng["views"], int) and isinstance(eng["likes"], int) and isinstance(eng["dislikes"], int)
    assert isinstance(eng["remixes"], int) and isinstance(eng["credits_usage"], float)
    assert [x["rank"] for x in apps] == [0, 1, 2]
    assert a["author_key"] and a["author"] is None                       # pseudonymous by default
    assert {m["role"] for m in a["media"]} >= {"logo", "cover"}


def test_games_skills_employees(sel):
    g = parse_envelope(load("studios_games.json"), sel)[0]
    assert g["plays"] > 0 and g["unique_players"] > 0 and g["game_url"] and g["source_zip_url"].endswith(".zip")
    s = parse_envelope(load("studios_skills.json"), sel)[0]
    assert s["usage"] is not None and s["installs"] is not None and s["content_url"].startswith("https://")
    emps = parse_envelope(load("studios_employees.json"), sel)
    builtin = next(e for e in emps if e["is_builtin"])
    assert builtin["canonical_slug"] == "shorts-maker" and builtin["source_url"].endswith("/shorts-maker")
    assert builtin["author_key"] is None                                 # built-ins have no author
    assert [m for m in builtin["media"] if m["role"] == "example"] and builtin["features"]
    community = next(e for e in emps if not e["is_builtin"])
    assert community["author_key"] and community["author"] is None


def test_playable_presets_and_influencer_options(sel):
    ps = parse_envelope(load("studios_playable_presets.json"), sel)
    p = ps[0]
    assert p["recreate_prompt"] and p["recreate_game_type"] and p["category"]
    roles = {m["role"] for m in p["media"]}
    assert {"poster", "video", "game"} <= roles and any(r.startswith("cover") for r in roles)
    assert all(m["type"] == "image" for m in p["media"] if m["role"].endswith("_thumbnail"))
    opts = parse_envelope(load("studios_influencer_config.json"), sel)
    assert len(opts) >= 6 and {o["subcategory_key"] for o in opts} >= {"character_type"}
    o = opts[0]
    assert o["position"] == 0 and o["media"] and o["lang"] == "en"
    assert len({x["id"] for x in opts}) == len(opts)


def test_gallery_items(sel):
    items = parse_envelope(load("studios_gallery_approved.json"), sel)
    it = items[0]
    assert it["studio"] == "marketing_studio" and it["feed"] == "approved" and it["approved"] is True
    assert it["generation_key"] == f"job:{it['job_id']}" and it["media_keys"]
    assert it["prompt"] and it["preset"] and it["job_set_type"].startswith("marketing_studio")
    assert isinstance(it["engagement"]["views"], int) and isinstance(it["engagement"]["likes"], int)
    assert it["author_key"] and it["author"] is None
    assert "prompt" not in it["settings"] and "medias" not in it["settings"] and it["settings"]
    assert all(m["url"] for m in it["inputs"])
    # inputs never become generation keys
    assert not {f"media:{m['media_key']}" for x in items for m in x["inputs"] if m["media_key"]} & \
        {k for x in items for k in x["media_keys"]}
    tr = parse_envelope(load("studios_gallery_trending.json"), sel)
    assert tr and all(x["feed"] == "trending" and x["studio"] == "canvas" for x in tr)
    assert any(x["inputs"] for x in tr)                                   # canvas input_image / mask
    cine = parse_envelope(load("studios_gallery_trending_cinema.json"), sel)
    assert cine and all(x["studio"] == "cinema_studio" for x in cine) and all(x["preset"] for x in cine)


def test_comments(sel):
    cs = parse_envelope(load("studios_comments.json"), sel)
    assert len(cs) == 1 and cs[0]["content"] and cs[0]["entity_type"] == "generation_publication"
    assert cs[0]["author_key"] and cs[0]["author"] is None and cs[0]["publication_id"]


def test_with_profiles_keeps_author_ids_only_when_opted_in():
    s = build(with_profiles=True)
    a = parse_envelope(load("studios_apps.json"), s)[0]
    assert a["author"]["user_id"].startswith("user_Fake") and a["author_key"] == author_key(a["author"]["user_id"])
    assert a["author"]["name"] is None                                   # archive was redacted: never "[redacted]"
    g = parse_envelope(load("studios_gallery_approved.json"), s)[0]
    assert g["author"] and g["author"]["avatar_url"] is None


def test_redact_author_names():
    body = {"items": [{"author": {"name": "someone", "user_id": "user_x"}}, {"author": None}, {"name": "App"}]}
    out = redact_author_names(body)
    assert out["items"][0]["author"] == {"name": "[redacted]", "user_id": "user_x"} and out["items"][2]["name"] == "App"


def test_media_key_and_non_200(sel):
    assert media_key("https://x/hf_20260414_3474b08b-9dc4-49e6-b6e2-4af862eff61d.mp4") == \
        "3474b08b-9dc4-49e6-b6e2-4af862eff61d"
    env = load("studios_apps.json")
    env.status = 404
    assert parse_envelope(env, sel) == []
    env.status, env.endpoint = 200, "studios_unknown"
    assert parse_envelope(env, sel) == []


# ------------------------------------------------------------------ options
def test_options():
    assert build().resolve() == list(DEFAULT_WHATS) == list(WHATS)
    assert parse_what("app,gallery,playable_presets") == ["apps", "galleries", "playable_presets"]
    assert parse_what("all") == parse_what("public") == list(WHATS)
    for bad in ({"what": "nope"}, {"lang": "fr"}, {"apps_sort": "x"}, {"studios": "x"}, {"gallery_feeds": "x"},
                {"gallery_pages": -1}):
        with pytest.raises(ValueError):
            build(**bad)
    s = build(what="galleries", studios="canvas,cinema_studio", gallery_pages="0", with_comments="true",
              with_profiles="1")
    assert selection_from_dict(s.to_dict()) == s and s.with_comments and s.gallery_pages == 0
    assert s.resolve_studios() == ["cinema_studio", "canvas"]
    assert default_label(build()) == "all" and default_label(build(what="apps")) == "apps"


# ------------------------------------------------------------------ request planning (no network)
def _spider(what=None, common=None, **kw):
    return StudiosSpider(selection=build(what=what, **kw), common=common or CommonOptions())


def test_requests_are_public_get_only():
    sp = _spider()
    reqs = list(sp.build_requests())
    assert reqs and all(r.meta.get("auth") is False and r.method == "GET" for r in reqs)
    assert all("Authorization" not in r.headers for r in reqs)
    eps = {r.meta["endpoint"] for r in reqs}
    assert eps == {"studios_app_categories", "studios_apps", "studios_games", "studios_skills", "studios_employees",
                   "studios_playable_presets", "studios_influencer_config", "studios_gallery"}
    assert not any("shorts-studio" in r.url or "ai-reels" in r.url for r in reqs)      # showcase reels_presets


def test_gallery_trending_is_per_model_approved_is_combined():
    reqs = list(_spider("galleries", studios="cinema_studio").build_requests())
    approved = [r for r in reqs if "/approved" in r.url]
    trending = [r for r in reqs if "/trending" in r.url]
    assert len(approved) == 1 and approved[0].url.count("model=") == len(STUDIO_MODELS["cinema_studio"])
    assert "approved=true" in approved[0].url
    assert len(trending) == len(STUDIO_MODELS["cinema_studio"]) and all(r.url.count("model=") == 1 for r in trending)
    only = list(_spider("galleries", gallery_feeds="approved").build_requests())
    assert len(only) == len(STUDIOS)


def test_gallery_pagination_and_page_cap():
    sp = _spider("galleries", studios="canvas", gallery_feeds="approved", gallery_pages=2)
    first = list(sp.build_requests())[0]
    env = Envelope(endpoint="studios_gallery", url=first.url, status=200,
                   body={"items": [{"id": "a"}], "has_more": True, "cursor": 1774989440.800913, "total": 41},
                   params=first.meta["params"], fetched_at=load("studios_apps.json").fetched_at)
    nxt = list(sp.follow_up(env, [], None))
    assert len(nxt) == 1 and "cursor=1774989440.800913" in nxt[0].url and nxt[0].meta["params"]["rank_base"] == "1"
    assert sp.totals["gallery_canvas_approved"] == 41
    env.params = nxt[0].meta["params"]
    assert list(sp.follow_up(env, [], None)) == [] and any("gallery_pages=2" in x for x in sp.limits_hit)


def test_offset_and_cursor_pagination():
    sp = _spider("apps,skills")
    fetched = load("studios_apps.json").fetched_at
    env = Envelope(endpoint="studios_apps", url="u", status=200, body={"items": [{}], "next_offset": 100},
                   params={"offset": "0", "limit": "100", "sort": "trending"}, fetched_at=fetched)
    r = list(sp.follow_up(env, [], None))
    assert len(r) == 1 and "offset=100" in r[0].url and "sort=trending" in r[0].url
    env = Envelope(endpoint="studios_skills", url="u", status=200, body={"items": [{}, {}], "next_cursor": None},
                   params={"rank_base": "100"}, fetched_at=fetched)
    assert list(sp.follow_up(env, [], None)) == [] and sp.totals["skills"] == 102


def test_comments_are_queued_only_with_flag_and_for_kept_items():
    sp = _spider("galleries", with_comments=True)
    fetched = load("studios_apps.json").fetched_at
    ent = {"kind": "studios_gallery_item", "id": "x1", "publication_id": "P1"}
    sp._seen.add(("studios_gallery_item", "x1"))
    env = Envelope(endpoint="studios_gallery", url="u", status=200, body={"items": [], "has_more": False},
                   params={"studio": "canvas", "feed": "approved"}, fetched_at=fetched)
    out = list(sp.follow_up(env, [ent, {**ent, "id": "x2", "publication_id": "P2"}], None))
    assert [r.meta["endpoint"] for r in out] == ["studios_comments"] and "/P1/comments" in out[0].url
    sp2 = _spider("galleries")
    sp2._seen.add(("studios_gallery_item", "x1"))
    assert list(sp2.follow_up(env, [ent], None)) == []


def test_media_urls_modes(sel):
    e = validate_entity(parse_envelope(load("studios_playable_presets.json"), sel)[0])
    assert media_urls(e, "full") and all(t == "video" for t in
                                         (next(m["type"] for m in e["media"] if m["url"] == u)
                                          for _, u in media_urls(e, "full")))
    assert media_urls(e, "thumbs") and len(media_urls(e, "all")) == len(e["media"])


# ------------------------------------------------------------------ dataset / CSV
def _csv(path: Path):
    with path.open(encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return set(r.fieldnames or []), rows


def test_dataset_and_csvs_complete(tmp_path, sel):
    from higgsfield_scraper.scrapers.studios.dataset import CHILD_LISTS
    ds = SCRAPER.build_dataset(all_entities(sel), build(), RunMeta(totals={"playable_presets": 112}))
    assert ds["meta"]["totals_available"]["playable_presets"] == 112 and ds["meta"]["scraper"] == "studios"
    assert ds["summary"]["generation_keys"] >= 6 and ds["summary"]["engagement"]["apps"]["views"] > 0
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


def test_merge_generations_dedupes_gallery_items_with_community(tmp_path, sel):
    m = _merge_module()
    ds = SCRAPER.build_dataset(all_entities(sel), build(), RunMeta())
    item = ds["gallery_items"][0]
    d = tmp_path / "s" / "output"
    d.mkdir(parents=True)
    (d / "dataset.json").write_text(json.dumps(ds), encoding="utf-8")
    c = tmp_path / "c" / "output"
    c.mkdir(parents=True)
    (c / "dataset.json").write_text(json.dumps({"meta": {"scraper": "community", "run_id": "c"}, "generations": [
        {"generation_id": item["job_id"], "prompt": "p", "model_id": item["job_set_type"]}]}), encoding="utf-8")
    recs = m.load_records([d.parent, c.parent])
    colls = {r["collection"] for r in recs}
    assert "gallery_items" in colls
    assert not colls & {"apps", "games", "skills", "employees", "playable_presets", "influencer_options",
                        "comments", "app_categories"}                    # never generation-like
    rows, per_source, pairs = m.merge(recs)
    merged = [r for r in rows if r["job_id"] == item["job_id"]]
    assert len(merged) == 1 and merged[0]["sources"] == ["community:generations", "studios:gallery_items"]


# ------------------------------------------------------------------ COMPLETENESS #10: shared creator_uid_key
def test_creator_uid_key_is_the_shared_author_hash(sel):
    from higgsfield_scraper.core.privacy import creator_uid_key
    ents = all_entities(sel)
    checked = 0
    for kind in ("studios_app", "studios_game", "studios_skill", "studios_employee", "studios_gallery_item",
                 "studios_comment"):
        for e in ents.get(kind, []):
            assert "creator_uid_key" in e and "author_key" in e, kind          # additive: both columns
            if e["creator_uid_key"] is not None:
                assert e["creator_uid_key"] == e["author_key"], kind           # same hash, shared name
                checked += 1
    assert checked > 0
    env = load("studios_comments.json")
    c = env.body["items"][0]
    (first, *_) = parse_envelope(env, sel)
    assert first["creator_uid_key"] == creator_uid_key(c.get("user_id") or (c.get("author") or {}).get("id"))


def test_creator_uid_key_is_null_for_username_fallback(sel):
    env = load("studios_gallery_approved.json")
    it = dict(env.body["items"][0])
    it["user_id"] = None
    it["profile"] = {"username": "fake_name_only"}
    env.body = {**env.body, "items": [it]}
    (e,) = parse_envelope(env, sel)
    assert e["author_key"] == author_key("fake_name_only") and e["creator_uid_key"] is None
