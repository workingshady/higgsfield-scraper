"""projects scraper, additive fixes of 2026-11-26 (docs/COMPLETENESS.md #6, #10, #15-#17) and the opt-in extras
(`--what trending`, `--what contest-participation`, `--with-user-works`).

Fixtures tests/fixtures/projects_extras/*.json are live anonymous GET responses of 2026-11-26, trimmed, with Clerk ids
replaced by `user_Fake…` ids of the same length and every username / avatar / headline redacted. The folder and
contest_submission items of user_works.json follow the JS schema of chunk 3On2TPGk30aH8MrG (no live example).
"""
from __future__ import annotations

import copy
import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import pytest
from scrapy.http import Request, TextResponse

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.dataset import make_id
from higgsfield_scraper.core.privacy import creator_uid_key
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.projects import SCRAPER
from higgsfield_scraper.scrapers.projects import endpoints as ep
from higgsfield_scraper.scrapers.projects.dataset import media_urls
from higgsfield_scraper.scrapers.projects.extras import media_keys, owner_user_ids
from higgsfield_scraper.scrapers.projects.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.projects.parsers import keep, parse_envelope
from higgsfield_scraper.validation import validate_entity

ROOT = Path(__file__).parent
FIX = ROOT / "fixtures" / "projects_extras"
NESTED = ROOT / "fixtures" / "projects_nested"
PROJ = ROOT / "fixtures" / "projects"
# owner of the user_works / user_stats fixtures (the fake Clerk id in their request URL)
UID = json.loads((FIX / "user_works.json").read_text(encoding="utf-8"))["meta"]["url"].split("/user/")[1].split("/")[0]


def load(path: Path) -> Envelope:
    return Envelope.load(path)


def kinds(ents):
    out = defaultdict(list)
    for e in ents:
        out[e["kind"]].append(e)
    return out


def parsed(path: Path, sel: Selection) -> dict[str, list[dict]]:
    return kinds(validate_entity(e) for e in parse_envelope(load(path), sel) if keep(e, sel))


# ------------------------------------------------------------------ options: opt-in, defaults unchanged
def test_default_selection_and_what_all_unchanged():
    d = Selection.build().to_dict()
    assert set(d) == {"what", "categories", "featured", "scopes", "with_details", "with_submissions",
                      "contest_status", "contest_types", "entry_keys", "entry_tab", "submission_ordering",
                      "max_submissions", "with_profiles"}
    assert Selection.build(what="all").what == ep.WHAT == Selection.build().what
    assert not Selection.build().extras and not Selection.build(what="all").extras


def test_extras_options_roundtrip():
    sel = Selection.build(what="all,trending,contest-participation", trending_sort="most_liked",
                          trending_filter="contest", with_user_works=True)
    assert sel.what == ep.WHAT + ("trending", "contest-participation") and sel.extras
    back = selection_from_dict(sel.to_dict())
    assert back.what == sel.what and back.trending_sort == "most_liked" and back.trending_filter == "contest"
    assert back.with_user_works
    assert Selection.build(what="trending", trending_sort="default").trending_sort is None
    assert "trending_sort" not in Selection.build(what="trending").to_dict()


@pytest.mark.parametrize("kw", [dict(what="trending", trending_sort="hot"), dict(what="trending", trending_filter="x"),
                                dict(what="bogus")])
def test_extras_options_reject_bad_values(kw):
    with pytest.raises(ValueError):
        Selection.build(**kw)


def test_new_kinds_registered():
    sdef = registry.get("projects")
    for k in ("projects_trending_row", "projects_participation_counters", "projects_participation_config",
              "projects_user_work", "projects_user_stats"):
        assert k in sdef.model_by_kind and k in sdef.id_field_by_kind


# ------------------------------------------------------------------ #6 related project card media
def test_related_card_media_fields():
    env = load(NESTED / "related.json")
    body = copy.deepcopy(env.body)
    body["items"][1]["trailer"] = {"id": "t1", "url": "https://cdn.higgsfield.ai/1dd1302b.mp4", "type": "video",
                                   "width": 1080, "height": 608, "duration": 17.002,
                                   "thumbnail_url": "https://cdn.higgsfield.ai/5a59272f.webp"}
    body["items"][1]["tags"] = ["animation"]
    env = Envelope(endpoint=env.endpoint, url=env.url, status=200, body=body, params=env.params,
                   fetched_at=env.fetched_at)
    sel = Selection.build(with_project_related=True)
    rel = [validate_entity(e) for e in parse_envelope(env, sel)]
    raw = {i["publication_id"]: i for i in body["items"]}
    for r in rel:
        it = raw[r["related_publication_id"]]
        assert r["title"] == it["name"] and r["description"] == it["description"]
        assert r["duration_seconds"] == it["duration_seconds"] and r["show_prompts"] == it["show_prompts"]
        assert r["cover_width"] == it["cover"]["width"] and r["created_at"]
        g, m = it["gallery_media"][0], r["gallery_media"][0]
        for k in ("url", "original_url", "preview_url", "thumbnail_url", "download_url", "width", "height"):
            assert m[k] == g.get(k)
        assert m["duration"] == g["duration"]
        assert r["creator_uid_keys"] == [creator_uid_key(a["id"]) for a in it["authors"]]
        assert r["likes"] == it["likes"] and r["views"] == it["views"]      # existing columns unchanged
    t = next(r for r in rel if r["trailer_url"])
    assert t["trailer_url"].endswith(".mp4") and t["trailer_width"] == 1080 and t["trailer_duration_seconds"] == 17.002
    assert t["trailer_thumbnail_url"] and t["tags"] == ["animation"]
    assert "[redacted]" not in json.dumps([r["team"] for r in rel])


# ------------------------------------------------------------------ #15 public series media variants
def test_series_optimized_images_and_episode_video_variants():
    env = load(FIX / "series_shimmer.json")
    item = env.body["items"][0]
    ents = parsed(FIX / "series_shimmer.json", Selection.build(what="series", public_series=True))
    s = ents["projects_series"][0]
    for k in ("portrait", "landscape", "background", "logo"):
        opt = (item.get(k) or {}).get("optimized")
        assert s[f"{k}_optimized_url"] == (opt["url"] if opt else None)
    assert s["portrait_optimized_url"] and s["portrait_url"] == item["portrait"]["original"]["url"]
    assert s["trailer_width"] == item["trailer"]["original"]["width"]
    assert s["trailer_hls_job_id"] == item["trailer"]["hls"]["job_id"]
    eps = {e["media_id"]: e for e in ents["projects_episode"]}
    shim = next(e for e in item["episodes"] if (e.get("video") or {}).get("shimmer"))
    e = eps[shim["id"]]
    v = shim["video"]
    assert e["shimmer_url"] == v["shimmer"]["url"] and e["shimmer_width"] == v["shimmer"]["width"]
    assert e["hls_job_id"] == v["hls"]["job_id"] and e["hls_url"] == v["hls"]["url"]
    assert (e["video_original_width"], e["video_original_height"]) == (v["original"]["width"], v["original"]["height"])
    assert e["video_url"] == v["hls"]["url"]                                    # existing column unchanged


def test_publication_gallery_episodes_keep_new_fields_empty():
    ents = parsed(PROJ / "publication_detail_series.json", Selection.build())
    assert ents["projects_episode"] and all(e["shimmer_url"] is None and e["hls_job_id"] is None
                                            for e in ents["projects_episode"])


# ------------------------------------------------------------------ #16 credits of the profile listing
def test_user_publications_listing_credits_survive_the_detail_merge():
    sel = Selection.build(users="creator_one", with_details=True)
    env = load(NESTED / "user_publications.json")
    raw = env.body["publications"][0]
    pub = parsed(NESTED / "user_publications.json", sel)["projects_publication"][0]
    assert pub["listing_credits_spent"] == raw["stats"]["credits_spent"] == 506400
    assert [u["credits_spent"] for u in pub["listing_model_usage"]] == [s["credits_spent"]
                                                                       for s in raw["stats"]["stack"]]
    detail = parsed(NESTED / "publication_detail.json", sel)["projects_publication_detail"][0]
    assert detail["listing_credits_spent"] is None and detail["listing_model_usage"] == []
    ds = SCRAPER.build_dataset({"projects_publication": [pub], "projects_publication_detail": [detail]}, sel,
                               RunMeta())
    p = next(x for x in ds["publications"] if x["publication_id"] == pub["publication_id"])
    assert p["listing_credits_spent"] == 506400 and p["credits_spent"] == detail["credits_spent"]
    assert p["listing_model_usage"] and p["model_usage"] == detail["model_usage"]
    other = parsed(PROJ / "publications_p1.json", Selection.build())["projects_publication"]
    assert all(x["listing_credits_spent"] is None and x["listing_model_usage"] == [] for x in other)


# ------------------------------------------------------------------ #17 folder path, #10 creator_uid_key
def test_folder_path_and_creator_uid_keys():
    sel = Selection.build(with_project_assets=True)
    env = load(NESTED / "folder_root.json")
    root = parsed(NESTED / "folder_root.json", sel)["projects_folder"][0]
    assert root["path"] == env.body["path"] and root["path"].strip("/") == root["folder_id"]
    assert root["creator_uid_key"] == creator_uid_key(env.body["user_id"])
    assert root["owner_key"] == make_id("user", env.body["user_id"])            # existing key unchanged
    kids = parsed(NESTED / "folder_children_root.json", sel)["projects_folder"]
    assert all(k["path"] and k["path"].count("/") == 3 and k["depth"] == 1 for k in kids)
    assets = parsed(NESTED / "folder_items.json", sel)["projects_asset"]
    assert all(a["creator_uid_key"] and a["creator_key"] for a in assets if a["item_type"] == "job")
    det = parsed(NESTED / "publication_detail.json", Selection.build())["projects_publication_detail"][0]
    raw = load(NESTED / "publication_detail.json").body
    assert det["creator_uid_keys"] == [creator_uid_key(a["id"]) for a in raw["authors"]]
    assert all(a["creator_uid_key"] == creator_uid_key(i["id"]) for a, i in zip(det["authors"], raw["authors"]))
    assert all(a["user_id"] is None and a["username"] is None for a in det["authors"])     # --with-profiles only


def test_creator_uid_key_on_comments_submissions_and_judges():
    c = parsed(NESTED / "comments.json", Selection.build())["projects_comment"]
    assert c and all(x["author"]["creator_uid_key"] for x in c)
    subs = parsed(PROJ / "submissions_p1.json", Selection.build())["projects_contest_submission"]
    assert subs and all(s["user"]["creator_uid_key"] == creator_uid_key(s_raw["user"]["id"])
                        for s, s_raw in zip(subs, load(PROJ / "submissions_p1.json").body["items"]))
    det = parsed(PROJ / "contest_detail_festival.json", Selection.build(with_details=True))
    judges = [j for c in det["projects_contest_detail"] for j in c["judges"]]
    raw_j = [j for j in load(PROJ / "contest_detail_festival.json").body.get("judges") or []]
    assert len(judges) == len(raw_j)
    for j, r in zip(judges, raw_j):
        assert j["creator_uid_key"] == (creator_uid_key(r["user_id"]) if r.get("user_id") else None)
        assert j["user_id"] is None                                               # still --with-profiles only


# ------------------------------------------------------------------ GAP: trending ranking
def test_trending_parse_rows_publications_and_total():
    env = load(FIX / "trending.json")
    ents = parsed(FIX / "trending.json", Selection.build(what="trending"))
    rows, pubs = ents["projects_trending_row"], ents["projects_publication"]
    assert len(rows) == len(pubs) == len(env.body["items"]) == 2
    assert all(r["total_reported"] == env.body["total"] and r["snapshot_id"] == env.body["feed"]["snapshot_id"]
               for r in rows)
    assert [r["position"] for r in rows] == [i["feed_position"] - 1 for i in env.body["items"]] == [0, 1]
    assert {r["listing"] for r in rows} == {"trending"} == {e["listing"] for e in ents["projects_listing_entry"]}
    assert rows[0]["feed_lane"] == env.body["items"][0]["feed_lane"]


def test_trending_requests_pagination_and_not_in_all():
    sp = make_spider(what="trending", trending_sort="most_viewed", trending_filter="contest")
    reqs = list(sp.build_requests())
    assert [r.url for r in reqs] == [f"{ep.SITE.replace('higgsfield.ai', 'fnf-api-gw.higgsfield.ai')}/fnf"
                                     "/project-publications/trending?limit=50&filter=contest&sort=most_viewed"]
    sp2 = make_spider(what="trending", trending_with_contest=True)
    assert list(sp2.build_requests())[0].url.endswith("/trending?limit=50&with_contest=true")
    _, follow = respond(make_spider(what="trending"), FIX / "trending.json")
    nxt = [r for r in follow if r.meta["endpoint"] == "projects_trending"]
    assert len(nxt) == 1 and "cursor=rc1" in nxt[0].url
    for what in (None, "all"):
        urls = [r.url for r in make_spider(**({"what": what} if what else {})).build_requests()]
        assert not any("/trending" in u or "/contest-participations/config" in u or "/counters" in u for u in urls)


# ------------------------------------------------------------------ GAP: contest participation counters + config
def test_participation_counters_config_and_merge():
    sel = Selection.build(what="contest-participation")
    cnt = parsed(FIX / "participation_counters.json", sel)["projects_participation_counters"][0]
    cfg = parsed(FIX / "participation_config.json", sel)["projects_participation_config"][0]
    assert (cnt["total"], cnt["public_total"], cnt["private_total"]) == (66645, 4516, 62129)
    assert cfg["contest_key"] == "ai_film_festival" and cfg["stage"] and cfg["votes_per_user"] == 5
    assert cfg["voting_opens_at"].startswith("2026-10-08") and cfg["max_team_size"] == 4
    ds = SCRAPER.build_dataset({"projects_participation_counters": [cnt], "projects_participation_config": [cfg]},
                               sel, RunMeta())
    row = ds["contest_participation"][0]
    assert row["contest_slug"] == "higgsfield-global-film-festival" and row["total"] == 66645
    assert row["stage"] == cfg["stage"] and row["counters_source_url"] and row["config_source_url"]
    assert ds["meta"]["counts"]["contest_participation"] == 1
    urls = [r.url for r in make_spider(what="contest-participation", entry_keys="talent_contest").build_requests()]
    assert urls == [f"https://fnf-api-gw.higgsfield.ai/fnf{ep.PARTICIPATION_COUNTERS}?contest_key=talent_contest",
                    f"https://fnf-api-gw.higgsfield.ai/fnf{ep.PARTICIPATION_CONFIG}?contest_key=talent_contest"]


# ------------------------------------------------------------------ GAP: user works + stats (--with-user-works)
def works_env(**labels) -> Envelope:
    env = load(FIX / "user_works.json")
    params = {"limit": "50", "creator_uid_key": creator_uid_key(UID), "creator_key": make_id("user", UID), **labels}
    return Envelope(endpoint=env.endpoint, url=env.url, status=200, body=env.body, params=params,
                    fetched_at=env.fetched_at)


def test_user_works_assets_are_generation_records():
    sel = Selection.build(with_user_works=True, users="creator_one")
    env = works_env()
    works = [validate_entity(e) for e in parse_envelope(env, sel)]
    by_type = defaultdict(list)
    for w in works:
        by_type[w["publication_type"]].append(w)
    assert set(by_type) == {"asset", "project_publication", "folder", "contest_submission"}      # blog_post skipped
    raw_assets = [p for p in env.body["publications"] if p["publication_type"] == "asset"]
    for w, r in zip(by_type["asset"], raw_assets):
        d = r["data"]
        assert w["generation_key"] == f"job:{d['id']}" and w["job_id"] == d["id"]
        assert w["prompt"] == (d["params"].get("prompt") or None) and w["params"] == d["params"]
        assert w["job_set_type"] == d["job_set_type"] and w["url"] == d["results"]["raw"]["url"]
        assert f"media:{d['id']}" in w["media_keys"]
        assert w["likes"] == d["publication"]["likes_count"] and w["views"] == d["publication"]["views_count"]
        assert w["clones"] == r["clones"] and w["publication_id"] == r["id_"]
        assert w["creator_uid_key"] == creator_uid_key(UID) and w["creator_key"] == make_id("user", UID)
    assert any(w["hls_url"] for w in by_type["asset"]) and any(w["input_media"] for w in by_type["asset"]) \
        or all(not w["input_media"] for w in by_type["asset"])
    assert all(p["name"] and p["generation_key"] is None for p in by_type["project_publication"])
    assert any(p["credits_spent_raw"] and p["generations_count"] for p in by_type["project_publication"])
    sub = by_type["contest_submission"][0]
    assert sub["contest_slug"] == "wcc-the-escape" and sub["video_url"]
    assert [w["position"] for w in works] == list(range(len(works))) or len(works) < len(env.body["publications"])


def test_user_works_are_pseudonymous_unless_with_profiles():
    env = works_env()
    works = parse_envelope(env, Selection.build(with_user_works=True))
    for w in works:          # the Clerk id stays only inside CDN media paths (as for every project asset)
        assert UID not in w["source_url"] and UID not in w["source"]["url"] and "/user/key:" in w["source_url"]
        assert w.get("user_id") is None and w.get("username") is None and w.get("avatar_url") is None
        assert UID not in json.dumps(w.get("extra"))
    prof = parse_envelope(env, Selection.build(with_user_works=True, with_profiles=True))
    assert all(w.get("user_id") == UID and UID in w["source_url"] for w in prof)
    assert any("username" in w for w in prof if w["publication_type"] == "asset")


def test_user_works_merge_with_scripts_merge_generations():
    spec = importlib.util.spec_from_file_location("merge_generations", ROOT.parent / "scripts" /
                                                  "merge_generations.py")
    mg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mg)
    works = [validate_entity(e) for e in parse_envelope(works_env(), Selection.build(with_user_works=True))]
    asset = next(w for w in works if w["publication_type"] == "asset")
    keys = mg.record_keys("projects", "user_works", asset)
    assert keys[0] == asset["generation_key"] and set(asset["media_keys"]) <= set(keys)
    community_twin = {"generation_id": asset["job_id"], "prompt": "x"}
    merged, _, _ = mg.merge([{"scraper": "projects", "collection": "user_works", "run": "a", "keys": keys,
                              "rec": asset},
                             {"scraper": "community", "collection": "generations", "run": "b",
                              "keys": mg.record_keys("community", "generations", community_twin),
                              "rec": community_twin}])
    assert len(merged) == 1 and merged[0]["records"] == 2
    folder = next(w for w in works if w["publication_type"] == "folder")
    assert mg.record_keys("projects", "user_works", folder) == []
    assert media_keys("https://d2ol7oe51mr4n9.cloudfront.net/u/0e73480a-023f-4937-898e-06b14aeca73a.jpg") == []


def test_user_stats():
    env = load(FIX / "user_stats.json")
    env = Envelope(endpoint=env.endpoint, url=env.url, status=200, body=env.body, params={}, fetched_at=env.fetched_at)
    st = [validate_entity(e) for e in parse_envelope(env, Selection.build(with_user_works=True))][0]
    assert st["creator_uid_key"] == creator_uid_key(UID) and st["views_count"] == env.body["views_count"]
    assert UID not in json.dumps(st) and st["user_id"] is None


def test_user_discovery_only_from_users_entries_and_submissions():
    entries = load(NESTED / "contest_entries_talent.json")
    owners = owner_user_ids(entries)
    assert owners == list(dict.fromkeys(next(a["id"] for a in i["authors"] if a.get("is_owner"))
                                        for i in entries.body["items"]))
    subs = load(PROJ / "submissions_p1.json")
    assert owner_user_ids(subs) == list(dict.fromkeys(i["user"]["id"] for i in subs.body["items"]))
    sp = make_spider(what="contests", contests="talent-contest", with_submissions=True, with_user_works=True,
                     max_submissions=2)
    sp._contest_listings["entries:talent_contest:latest"] = 0
    _, reqs = respond(sp, NESTED / "contest_entries_talent.json")
    eps = [r.meta["endpoint"] for r in reqs]
    assert eps.count("projects_user_works") == eps.count("projects_user_stats") == len(owners)
    w = next(r for r in reqs if r.meta["endpoint"] == "projects_user_works")
    assert w.url.endswith(f"/user/{owners[0]}/v2/publications?limit=50") and "publication_type" not in w.url
    assert w.meta["params"]["creator_uid_key"] == creator_uid_key(owners[0])
    assert not [r for r in respond(sp, NESTED / "contest_entries_talent.json")[1]
                if r.meta["endpoint"] == "projects_user_works"]                        # each user once
    plain = make_spider(what="contests", contests="talent-contest", with_submissions=True, max_submissions=2)
    plain._contest_listings["entries:talent_contest:latest"] = 0
    assert not [r for r in respond(plain, NESTED / "contest_entries_talent.json")[1]
                if r.meta["endpoint"].startswith("projects_user_")]
    # broad listings never discover users
    _, reqs = respond(make_spider(what="trending", with_user_works=True), FIX / "trending.json")
    assert not [r for r in reqs if r.meta["endpoint"].startswith("projects_user_")]


def test_user_works_pagination():
    sp = make_spider(what="user-projects", users="creator_one", with_user_works=True)
    env = works_env()
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params, "uid": UID})
    resp = TextResponse(env.url, body=json.dumps(env.body).encode(), encoding="utf-8", request=req, status=200)
    reqs = [o for o in sp.parse_api(resp) if isinstance(o, Request)]
    assert len(reqs) == 1 and f"cursor={env.body['cursor']}" in reqs[0].url
    assert reqs[0].meta["params"]["offset"] == str(len(env.body["publications"]))
    assert sp.totals[f"user_works:{creator_uid_key(UID)}"] == env.body["total"]


# ------------------------------------------------------------------ dataset / outputs
def test_extras_dataset_outputs(tmp_path):
    sel = Selection.build(what="trending,contest-participation", with_user_works=True)
    ents = defaultdict(list)
    for p, e in [(FIX / "trending.json", None), (FIX / "participation_counters.json", None),
                 (FIX / "participation_config.json", None)]:
        for x in parse_envelope(load(p), sel):
            ents[x["kind"]].append(validate_entity(x))
    for x in parse_envelope(works_env(), sel):
        ents[x["kind"]].append(validate_entity(x))
    env = load(FIX / "user_stats.json")
    for x in parse_envelope(Envelope(endpoint=env.endpoint, url=env.url, status=200, body=env.body, params={},
                                     fetched_at=env.fetched_at), sel):
        ents[x["kind"]].append(validate_entity(x))
    rm = RunMeta()
    rm.totals = {f"user_works:{creator_uid_key(UID)}": 191}
    ds = SCRAPER.build_dataset(ents, sel, rm)
    assert len(ds["trending"]) == 2 and len(ds["contest_participation"]) == 1 and ds["user_stats"][0]["works_total"] == 191
    assert {"projects_trending", "projects_user_works", "projects_participation_config"} <= set(ds["meta"]["endpoints"])
    assert "assets" not in ds                                                  # no nested flag: no nested keys
    files = SCRAPER.write_outputs(ds, tmp_path)
    names = {f.name for f in files}
    assert {"trending.csv", "user_works.csv", "user_work_variants.csv", "contest_participation.csv",
            "user_stats.csv", "user_works.json"} <= names
    with (tmp_path / "csv" / "user_works.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows and any(r["generation_key"].startswith("job:") for r in rows) and "params" in rows[0]
    assert "User works" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    asset = next(w for w in ds["user_works"] if w["publication_type"] == "asset")
    assert media_urls({**asset, "kind": "projects_user_work"}, "full")


def test_default_dataset_has_no_extras_keys():
    sel = Selection.build()
    ents = parsed(PROJ / "publications_p1.json", sel)
    ds = SCRAPER.build_dataset(ents, sel, RunMeta())
    assert not ({"trending", "user_works", "user_stats", "contest_participation"} & set(ds))
    assert set(ds["meta"]["counts"]) == {"publications", "episodes", "categories", "contests", "submissions",
                                         "series", "listing_entries"}


# ------------------------------------------------------------------ spider helpers
class _Stats:
    def inc_value(self, *a, **k):
        pass


class _Crawler:
    stats = _Stats()


def make_spider(**sel):
    from higgsfield_scraper.scrapers.projects.spider import ProjectsSpider
    sp = ProjectsSpider(selection=Selection.build(**sel), common=CommonOptions(auth="off"))
    sp.crawler = _Crawler()
    return sp


def respond(sp, path: Path):
    env = load(path)
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params, "handle": "creator_one"})
    resp = TextResponse(env.url, body=json.dumps(env.body).encode(), encoding="utf-8", request=req, status=env.status)
    out = list(sp.parse_api(resp))
    return [o for o in out if not isinstance(o, Request)], [o for o in out if isinstance(o, Request)]
