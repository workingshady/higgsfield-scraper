"""projects scraper: parsers, options, spider pagination/follow-ups, dataset assembly, CSV completeness.

Fixtures (tests/fixtures/projects/*.json) are real API responses (2026-11-25), trimmed, with user ids, usernames,
names, avatars, social links and judge names replaced by fake values.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pytest
from scrapy.http import Request, TextResponse

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.projects import SCRAPER
from higgsfield_scraper.scrapers.projects import endpoints as ep
from higgsfield_scraper.scrapers.projects.dataset import media_urls
from higgsfield_scraper.scrapers.projects.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.projects.parsers import author_key, iso, keep, parse_envelope
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "projects"


def load(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def kinds(ents):
    out = defaultdict(list)
    for e in ents:
        out[e["kind"]].append(e)
    return out


def all_entities(sel: Selection) -> dict[str, list[dict]]:
    """Parse every fixture, validate, keep and dedup like the pipelines do."""
    ids = registry.all_id_fields()
    out, seen = defaultdict(list), set()
    for p in sorted(FIX.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if not keep(e, sel):
                continue
            v = validate_entity(e)
            f = ids.get(v["kind"])
            if f and (v["kind"], v[f]) in seen:
                continue
            seen.add((v["kind"], v.get(f)))
            out[v["kind"]].append(v)
    return out


# ------------------------------------------------------------------ registry / options
def test_registered_and_kinds_prefixed():
    sdef = registry.get("projects")
    assert sdef is SCRAPER and sdef.name == "projects"
    assert all(k.startswith("projects_") for k in sdef.model_by_kind)
    assert set(sdef.id_field_by_kind) == set(sdef.model_by_kind)


def test_options_defaults_roundtrip_and_strings():
    sel = Selection.build()
    assert sel.what == ep.WHAT and sel.scopes == ep.RECOMMENDED_SCOPES and sel.contest_status == "all"
    assert not sel.with_profiles and not sel.with_details
    sel2 = Selection.build(what="contests,publications", scope="community", with_details=True,
                           contest_status="closed", contest_types="weekly", max_submissions=5, with_profiles=True)
    assert selection_from_dict(sel2.to_dict()) == sel2
    assert sel2.statuses == ("finished",)
    s3 = selection_from_dict({"what": "contests", "with_submissions": "true", "max_submissions": "3",
                              "contest_status": "open"})
    assert s3.what == ("contests",) and s3.with_submissions and s3.max_submissions == 3
    assert "judge" in s3.statuses and "finished" not in s3.statuses
    json.dumps(sel2.to_dict())


@pytest.mark.parametrize("kw", [{"what": "bogus"}, {"scope": "nope"}, {"contest_status": "x"},
                                {"contest_types": "monthly"}, {"entry_tab": "x"}, {"submission_ordering": "x"}])
def test_options_reject_bad_values(kw):
    with pytest.raises(ValueError):
        Selection.build(**kw)


# ------------------------------------------------------------------ parsers
def test_publications_page_parsing():
    sel = Selection.build()
    k = kinds(parse_envelope(load("publications_p1.json"), sel))
    pubs = k["projects_publication"]
    assert len(pubs) == 4 and len(k["projects_listing_entry"]) == 4
    series = next(p for p in pubs if p["type"] == "series")
    assert series["episode_count"] == 3 and series["media_count"] == 4          # cover + 3 gallery
    assert [m["role"] for m in series["media"]] == ["cover", "gallery", "gallery", "gallery"]
    assert series["cover_url"].startswith("https://")
    eps = [e for e in k["projects_episode"] if e["publication_id"] == series["publication_id"]]
    assert [e["number"] for e in eps] == [1, 2, 3] and all(e["episode_id"].startswith(series["publication_id"]) for e in eps)
    a = series["authors"][0]
    assert a["author_key"] and len(a["author_key"]) == 16
    assert a.get("username") is None and a.get("avatar_url") is None and a.get("user_id") is None   # no profiles by default
    assert "username" not in a["extra"] and "id" not in a["extra"]
    assert series["url"] is None
    assert series["created_at"].endswith("+00:00")
    assert "is_liked_by_user" in series["extra"]
    team_pub = next(p for p in pubs if p["team"])
    assert team_pub["team"]["role"] == "team" and team_pub["team"].get("username") is None
    fe = next(p for p in pubs if p["featured_episode_id"])
    assert fe["type"] == "film"
    le = k["projects_listing_entry"][0]
    assert le["listing"] == "publications" and le["position"] == 0 and le["page_cursor"] is None


def test_profiles_opt_in():
    sel = Selection.build(with_profiles=True)
    pubs = kinds(parse_envelope(load("publications_p1.json"), sel))["projects_publication"]
    a = pubs[0]["authors"][0]
    assert a["username"].startswith("creator") and a["user_id"].startswith("user_fake")
    assert a["profile_url"] == f"https://higgsfield.ai/profile/{a['username']}"
    assert pubs[0]["url"] == f"https://higgsfield.ai/@{a['username']}/projects/{pubs[0]['slug']}"
    subs = kinds(parse_envelope(load("submissions_p1.json"), sel))["projects_contest_submission"]
    assert subs[0]["post_urls"] and subs[0]["user"]["username"]


def test_second_page_offset_and_score_cursors():
    sel = Selection.build()
    k = kinds(parse_envelope(load("publications_p2.json"), sel))
    le = k["projects_listing_entry"]
    assert le[0]["position"] is None and le[0]["page_cursor"].startswith("39.83")   # score cursor: no rank
    rec = kinds(parse_envelope(load("recommended_ai_film_festival.json"), sel))
    entries = rec["projects_listing_entry"]
    assert [e["position"] for e in entries] == [50, 51] and entries[0]["listing"] == "recommended:ai_film_festival"
    p = rec["projects_publication"][0]
    assert p["trailer_url"] and p["contest_badges"][0]["list_key"] == "top_50" and p["contest_key"] == "ai_film_festival"
    assert p["media"][-1]["role"] == "trailer"


def test_entries_listing_name():
    k = kinds(parse_envelope(load("entries_ai_film_festival.json"), Selection.build()))
    assert k["projects_listing_entry"][0]["listing"] == "entries:ai_film_festival:latest"
    p = k["projects_publication"][0]
    assert p["root_folder_id"] and p["published_at"] and p["votes"] is not None


def test_publication_detail_stats():
    k = kinds(parse_envelope(load("publication_detail_series.json"), Selection.build()))
    d = k["projects_publication_detail"][0]
    assert d["detail_fetched"] and d["detail_source"]["endpoint"] == "projects_publication_detail"
    assert d["model_usage"] and {"job_set_type", "credits_spent", "count"} <= set(d["model_usage"][0])
    film = kinds(parse_envelope(load("publication_detail_film.json"), Selection.build()))["projects_publication_detail"][0]
    assert film["generations_count"] and film["featured_episode_slug"]
    assert film["featured_episode_url"] == f"https://higgsfield.ai/original-series/{film['featured_episode_slug']}"


def test_categories():
    cats = parse_envelope(load("categories.json"), Selection.build())
    assert {c["slug"] for c in cats} == {"spotlight", "open-sourced-by-higgsfield"}


def test_contests_list_and_status_filter():
    env = load("contests_global.json")
    allc = [e for e in parse_envelope(env, Selection.build()) if e["kind"] == "projects_contest"]
    assert len(allc) == 4
    fin = next(c for c in allc if c["status"] == "finished")
    assert fin["status_group"] == "closed" and fin["winner"]["author_key"] and fin["winner"].get("username") is None
    assert fin["some_contestants_count"] == 2 and fin["some_contestants"] == []       # names only with profiles
    assert fin["judge_count"] == 2 and fin["judges"][0]["display_name"] and fin["judges"][0].get("avatar_url") is None
    assert fin["url"] == "https://higgsfield.ai/contests/make-your-action-scene"
    closed = Selection.build(contest_status="closed")
    assert [c["slug"] for c in allc if keep(c, closed)] == ["make-your-action-scene"]
    assert not any(keep(c, Selection.build(contest_types="weekly")) for c in allc)


def test_contest_detail_weekly():
    k = kinds(parse_envelope(load("contest_detail_weekly.json"), Selection.build()))
    c = k["projects_contest_detail"][0]
    assert c["settings"]["max_submissions"] == 1 and c["rewards"]["first_place_credits"] == 50000
    assert c["prizes"][0]["label"] == "1st" and c["prize_pool_unit"] == "credits"
    assert c["faq"][0]["question"] and c["rules_effective_at"] == "2026-11-04"
    winners = k["projects_contest_submission"]
    assert len(winners) == 3 and all(w["listing"] == "winners" for w in winners)
    assert c["winner_submission_ids"] == [w["submission_id"] for w in winners]
    assert winners[0]["winner_place"] == "1st" and winners[0]["publication_id"]


def test_contest_detail_festival_timeline_and_usd():
    c = parse_envelope(load("contest_detail_festival.json"), Selection.build())[0]
    assert c["prize_pool_unit"] == "usd" and c["timeline"]["version"] == 2 and c["settings"] is None


def test_submissions_parsing():
    subs = parse_envelope(load("submissions_p1.json"), Selection.build())
    s = subs[0]
    assert s["kind"] == "projects_contest_submission" and s["contest_slug"] == "make-your-action-scene"
    assert s["post_url_count"] == 1 and s["post_urls"] == []
    assert s["user"]["author_key"] and s["user"].get("username") is None
    assert s["url"] == f"https://higgsfield.ai/contests/make-your-action-scene/submissions/{s['submission_id']}"
    assert set(s["social_media_metrics"]) >= {"youtube_views"}


def test_non_200_and_unknown_endpoints_yield_nothing():
    assert parse_envelope(load("series_unauthorized.json"), Selection.build()) == []
    env = Envelope(endpoint="other", url="x", status=200, body={"items": [{"id": 1}]})
    assert parse_envelope(env, Selection.build()) == []


def test_series_parser_from_js_shape():
    """/series is login-only: parser is written from the web app's JS; synthetic body in that shape."""
    body = {"items": [{"id": "s1", "slug": "arena-zero", "name": "Arena Zero", "short_description": "short",
                       "full_description": None, "author_type": "studio",
                       "author": {"id": "u1", "username": "studio", "display_name": "Studio", "avatar_url": "a"},
                       "is_series": True, "state": "released", "portrait": {"url": "https://x/p.webp"},
                       "landscape_url": "https://x/l.webp", "logo": {"original": {"url": "https://x/logo.png"}},
                       "trailer": {"url": "https://x/t.mp4", "hls": {"url": "https://x/t.m3u8"}},
                       "engagement": {"like_count": 3, "view_count": 10, "comment_count": 1},
                       "categories": [{"slug": "first-look"}], "tags": ["scifi"], "vote_count": 2,
                       "subscriber_count": 5, "project_banner_images": [{"url": "https://x/b.webp"}],
                       "new_field": 1,
                       "episodes": [{"id": "e1", "slug": "episode-1", "title": "Ep 1", "thumbnail_url": "https://x/e.webp",
                                     "video": {"url": "https://x/e1.mp4", "hls": {"url": "https://x/e1.m3u8"}},
                                     "duration_seconds": 61, "is_locked": False},
                                    {"id": "e2", "slug": "episode-2", "title": "Ep 2", "is_locked": True,
                                     "video_url": "https://x/e2.mp4"}]}]}
    env = Envelope(endpoint="projects_series", url=f"https://api{ep.SERIES}", status=200, body=body)
    k = kinds(parse_envelope(env, Selection.build()))
    s = k["projects_series"][0]
    assert s["title"] == "Arena Zero" and s["likes"] == 3 and s["logo_url"] == "https://x/logo.png"
    assert s["trailer_hls_url"] == "https://x/t.m3u8" and s["episode_count"] == 2 and s["extra"] == {"new_field": 1}
    assert s["author"].get("username") is None and s["url"] == "https://higgsfield.ai/original-series/arena-zero"
    e1, e2 = k["projects_episode"]
    assert e1["video_url"] == "https://x/e1.m3u8" and e1["url"].endswith("/arena-zero/episode-1")
    assert e2["video_url"] is None and e2["is_locked"]
    for e in k["projects_series"] + k["projects_episode"]:
        validate_entity(e)


def test_iso_and_author_key():
    assert iso("2026-11-07T12:36:10.836080Z") == "2026-11-07T12:36:10.836080+00:00"
    assert iso("2026-09-14T03:37:11.816299+02:00") == "2026-09-14T01:37:11.816299+00:00"
    assert iso("2026-11-04") == "2026-11-04" and iso(None) is None
    assert author_key("user_x") == author_key("user_x") != author_key("user_y") and author_key(None) is None


# ------------------------------------------------------------------ spider
class _Stats:
    def __init__(self):
        self.d = {}

    def inc_value(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n


class _Crawler:
    def __init__(self):
        self.stats = _Stats()


def make_spider(common: CommonOptions | None = None, **sel):
    from higgsfield_scraper.scrapers.projects.spider import ProjectsSpider
    sp = ProjectsSpider(selection=Selection.build(**sel), common=common or CommonOptions(auth="off"))
    sp.crawler = _Crawler()
    return sp


def respond(sp, fixture: str):
    env = load(fixture)
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params})
    resp = TextResponse(env.url, body=json.dumps(env.body).encode(), encoding="utf-8", request=req, status=env.status)
    out = list(sp.parse_api(resp))
    items = [o for o in out if not isinstance(o, Request)]
    reqs = [o for o in out if isinstance(o, Request)]
    return items, reqs


def test_build_requests_default_and_filters():
    urls = [r.url for r in make_spider().build_requests()]
    assert any("/contests?contest_type=global" in u for u in urls) and any("contest_type=weekly" in u for u in urls)
    assert any(u.endswith("/project-publications/categories") for u in urls)
    assert sum("/recommended?scope=" in u for u in urls) == len(ep.RECOMMENDED_SCOPES)
    assert sum("contest-participations" in u for u in urls) == 2
    assert not any("/series" in u for u in urls)                        # login-only, no session -> skipped
    urls = [r.url for r in make_spider(what="publications,contests", categories="spotlight,banner", featured=True,
                                       contest_status="open", contest_types="weekly").build_requests()]
    assert sum("category=" in u for u in urls) == 2 and all("featured=true" in u for u in urls if "category=" in u)
    c = next(u for u in urls if "/contests?" in u)
    assert "status=created" in c and "status=judge" in c and "status=finished" not in c
    assert not any("recommended" in u or "participations" in u for u in urls)


def test_series_requested_only_with_session(monkeypatch):
    from higgsfield_scraper.scrapers.projects.spider import ProjectsSpider
    monkeypatch.setattr(ProjectsSpider, "authed", property(lambda self: True))
    sp = make_spider(what="series")
    reqs = list(sp.build_requests())
    assert len(reqs) == 1 and reqs[0].meta["auth"] == "required" and "/series?limit=100" in reqs[0].url


def test_publications_pagination_and_details():
    sp = make_spider(what="publications", with_details=True)
    items, reqs = respond(sp, "publications_p1.json")
    nxt = [r for r in reqs if r.meta["endpoint"] == "projects_publications"]
    det = [r for r in reqs if r.meta["endpoint"] == "projects_publication_detail"]
    assert len(nxt) == 1 and "cursor=39.83" in nxt[0].url and len(det) == 4
    # path ids are recorded as envelope params so every detail gets its own raw/ file
    names = {Envelope(endpoint=r.meta["endpoint"], url=r.url, status=200, body={}, params=r.meta["params"]).filename
             for r in det}
    assert len(names) == 4 and all("?" not in r.url for r in det)
    items, reqs = respond(sp, "publications_p2.json")                 # next_cursor null -> stop
    assert not [r for r in reqs if r.meta["endpoint"] == "projects_publications"]


def test_pagination_stops_on_budget_and_max_pages():
    sp = make_spider(CommonOptions(auth="off", max_items=3), what="publications")
    items, reqs = respond(sp, "publications_p1.json")
    assert sum(i["kind"] == "projects_publication" for i in items) == 3 and not reqs
    assert any("max_items=3" in x for x in sp.limits_hit)
    sp = make_spider(CommonOptions(auth="off", max_pages=0), what="recommended")
    _, reqs = respond(sp, "recommended_ai_film_festival.json")
    assert not reqs and any("max_pages" in x for x in sp.limits_hit)


def test_duplicates_are_not_counted_twice():
    sp = make_spider(CommonOptions(auth="off", max_items=100), what="publications")
    respond(sp, "publications_p1.json")
    items, _ = respond(sp, "publications_p1.json")                    # same items again (another listing)
    assert not [i for i in items if i["kind"] == "projects_publication"]
    assert len([i for i in items if i["kind"] == "projects_listing_entry"]) == 4
    assert sp.primary_count == 4


def test_contests_follow_ups_and_totals():
    sp = make_spider(what="contests", with_details=True, with_submissions=True)
    _, reqs = respond(sp, "contests_global.json")
    eps = [r.meta["endpoint"] for r in reqs]
    assert eps.count("projects_contest_detail") == 4 and eps.count("projects_contest_submissions") == 4
    sub = next(r for r in reqs if r.meta["endpoint"] == "projects_contest_submissions")
    assert "limit=100" in sub.url and "ordering=newest" in sub.url
    assert sub.meta["params"]["contest_id"] and "contest_id" not in sub.url
    assert sp.totals["contests:global"] == 4 and sp.totals["submissions:make-your-action-scene"] == 8752
    _, reqs = respond(sp, "submissions_p1.json")                     # has_more -> next offset
    assert len(reqs) == 1 and "offset=3" in reqs[0].url
    _, reqs = respond(sp, "submissions_weekly_last.json")            # has_more false -> stop
    assert not reqs


def test_max_submissions_per_contest():
    sp = make_spider(what="contests", with_submissions=True, max_submissions=3)
    _, reqs = respond(sp, "submissions_p1.json")
    assert not reqs and any("max_submissions=3" in x for x in sp.limits_hit)


def test_entries_totals():
    sp = make_spider(what="entries")
    _, reqs = respond(sp, "entries_ai_film_festival.json")
    assert sp.totals["entries:ai_film_festival:latest"] == 4518
    assert reqs and "cursor=2" in reqs[0].url and "contest_key=ai_film_festival" in reqs[0].url


# ------------------------------------------------------------------ dataset / outputs
def _csv(path: Path):
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        return set(rows[0].keys()) if rows else set(), rows


def test_build_dataset_merges_details_and_counts():
    sel = Selection.build(with_details=True, with_submissions=True)
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta(totals={"entries:ai_film_festival:latest": 4518}))
    pubs = {p["publication_id"]: p for p in ds["publications"]}
    merged = pubs["b93872c6-1aa3-4460-b311-4717233ef04c"]
    assert merged["detail_fetched"] and merged["model_usage"] and merged["comments"] is not None   # list-only kept
    assert merged["listing"] == "publications" and merged["detail_source"]["endpoint"] == "projects_publication_detail"
    contests = {c["slug"]: c for c in ds["contests"]}
    wk = contests["wcc-without-a-word"]
    assert wk["detail_fetched"] and wk["entries_count"] == 280 and wk["rewards"]["third_place_credits"] == 15000
    assert contests["make-your-action-scene"]["judge_count"] >= 2
    assert ds["meta"]["counts"]["publications"] == len(ds["publications"]) and ds["meta"]["scraper"] == "projects"
    assert ds["meta"]["totals_available"]["entries:ai_film_festival:latest"] == 4518
    assert ds["summary"]["publications_by_type"]["series"] >= 1
    assert all(e["publication_id"] in pubs for e in ds["listing_entries"])
    assert all(e["publication_id"] in pubs for e in ds["episodes"] if e["publication_id"])


def test_csvs_contain_every_json_field(tmp_path):
    from higgsfield_scraper.core.exporting import without
    sel = Selection.build(with_details=True, with_submissions=True, with_profiles=True)
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    files = SCRAPER.write_outputs(ds, tmp_path)
    assert (tmp_path / "dataset.json").exists() and (tmp_path / "summary.md").exists()
    assert (tmp_path / "schema" / "dataset.schema.json").exists() and len(files) > 15
    pubs, contests = ds["publications"], ds["contests"]
    checks = {
        "publications": [without(p, "media", "authors", "team", "model_usage") for p in pubs],
        "publication_media": [m for p in pubs for m in p["media"]],
        "publication_authors": [a for p in pubs for a in p["authors"] + ([p["team"]] if p["team"] else [])],
        "publication_model_usage": [u for p in pubs for u in p["model_usage"]],
        "episodes": ds["episodes"],
        "categories": ds["categories"],
        "contests": [without(c, "judges", "prizes", "faq", "some_contestants") for c in contests],
        "contest_judges": [j for c in contests for j in c["judges"]],
        "contest_rewards": [p for c in contests for p in c["prizes"]],
        "contest_faq": [f for c in contests for f in c["faq"]],
        "contest_contestants": [p for c in contests for p in c["some_contestants"]],
        "submissions": ds["submissions"],
        "listing_entries": ds["listing_entries"],
    }
    for table, objects in checks.items():
        cols, rows = _csv(tmp_path / "csv" / f"{table}.csv")
        assert len(rows) == len(objects), table
        assert objects, f"fixture gives no rows for {table}"
        missing = {k for o in objects for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{table}.csv is missing JSON fields: {sorted(missing)[:10]}"
    meta_keys = {r["key"] for r in _csv(tmp_path / "csv" / "run_meta.csv")[1]}
    assert {"meta.counts.publications", "schema_version", "meta.options.with_profiles"} <= meta_keys


def test_no_personal_data_without_profiles(tmp_path):
    sel = Selection.build(with_details=True, with_submissions=True)
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    blob = json.dumps(ds)
    assert "creator1" not in blob and "avatar.webp" not in blob and "video.example.test" not in blob
    assert "example.test/judge" not in blob


def test_media_urls_modes():
    sel = Selection.build()
    ents = parse_envelope(load("publications_p1.json"), sel) + parse_envelope(load("recommended_ai_film_festival.json"), sel)
    rec = next(e for e in ents if e["kind"] == "projects_publication" and e["trailer_url"])
    thumbs, full = media_urls(rec, "thumbs"), media_urls(rec, "full")
    assert thumbs and full and all(not u.endswith(".m3u8") for _, u in full)
    assert media_urls(rec, "none") == [] and set(media_urls(rec, "all")) >= set(thumbs) | set(full)
    sub = parse_envelope(load("submissions_p1.json"), sel)[0]
    assert media_urls(sub, "full") == [("video", sub["video_url"])]
    c = parse_envelope(load("contests_global.json"), sel)[0]
    assert ("preview_image", c["preview_image"]) in media_urls(c, "thumbs")


def test_normalize_offline_end_to_end(tmp_path):
    import logging
    import shutil

    from higgsfield_scraper.cli import main
    from higgsfield_scraper.run.context import latest_run
    from higgsfield_scraper.run.logging_setup import teardown_logging
    src = tmp_path / "runs" / "20260101-000000_projects-fixture"
    shutil.copytree(FIX, src / "raw")
    (src / "manifest.json").write_text(json.dumps({"scraper": "projects", "selection": Selection.build(
        with_details=True, with_submissions=True).to_dict()}), "utf-8")
    rc = main(["normalize", "--run", str(src), "--runs-dir", str(tmp_path / "runs"), "--log-level", "ERROR"])
    teardown_logging([h for h in logging.getLogger().handlers if getattr(h, "_higgs", False)])
    assert rc == 0
    run = latest_run(tmp_path / "runs")
    m = json.loads((run / "manifest.json").read_text("utf-8"))
    assert m["status"] == "success" and m["counts"]["contests"] == 6 and m["counts"]["publications"] == 10
