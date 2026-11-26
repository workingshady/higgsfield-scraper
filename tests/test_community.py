"""community scraper: parsers, pagination decisions, options, dataset/CSV completeness, dedup, estimates (offline)."""
from __future__ import annotations

import argparse
import csv
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.community import SCRAPER, media_urls
from higgsfield_scraper.scrapers.community import dataset as cds
from higgsfield_scraper.scrapers.community.options import Selection, add_args, make_selection, selection_from_dict
from higgsfield_scraper.scrapers.community.parsers import (iso_ts, keep, media_type_of, parse_envelope,
                                                           parse_upstream_usage, split_params)
from higgsfield_scraper.scrapers.community.spider import CommunitySpider, next_page
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "community"
RAW = Path(__file__).parent / "fixtures" / "raw"
ALL = ["trending_p1.json", "trending_p2.json", "approved_last.json", "top.json", "model_x_last.json", "detail.json",
       "trending_empty.json"]


def load(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def collect(sel: Selection, names=ALL) -> dict[str, list[dict]]:
    """Parse + keep + validate + dedup exactly like the pipeline / normalize."""
    ids = registry.all_id_fields()
    out: dict[str, list[dict]] = {}
    seen: set = set()
    for n in names:
        for e in parse_envelope(load(n), sel):
            if not keep(e, sel):
                continue
            v = validate_entity(e)
            key = (v["kind"], v.get(ids.get(v["kind"], ""), id(v)))
            if key in seen:
                continue
            seen.add(key)
            out.setdefault(v["kind"], []).append(v)
    return out


def rm() -> RunMeta:
    return RunMeta(run_id="test", label="t", scraped_at=datetime(2026, 11, 25, tzinfo=timezone.utc),
                   common=CommonOptions(max_items=100))


# ------------------------------------------------------------------ registry / options
def test_registered():
    assert registry.get("community") is SCRAPER
    assert SCRAPER.id_field_by_kind["community_generation"] == "generation_id"
    assert SCRAPER.id_field_by_kind["community_creator"] == "user_id"


def _args(*argv):
    p = argparse.ArgumentParser()
    add_args(p)
    return p.parse_args(list(argv))


def test_options_parsing_and_roundtrip():
    sel = make_selection(_args("--feeds", "trending,approved", "--type", "video", "--models", "seedance_2_5",
                               "--models", "kling3_0,seedance_2_5", "--estimate-cost", "videos", "--with-profiles"))
    assert sel.feeds == ["trending", "approved"]
    assert sel.models == ["seedance_2_5", "kling3_0"]
    assert sel.estimate_for("video") and not sel.estimate_for("image")
    assert selection_from_dict(sel.to_dict()) == sel                        # manifest round trip
    s2 = selection_from_dict({"feeds": "all", "type": "image", "with_profiles": "true", "detail": "0",
                              "models": "a,b"})                              # `scrapy crawl -a` strings
    assert s2.feeds == ["trending", "approved", "top", "model-x"] and s2.with_profiles and not s2.detail
    assert s2.models == ["a", "b"]
    assert selection_from_dict({"feeds": "model_x"}).feeds == ["model-x"]
    assert selection_from_dict({}).feeds == ["trending"] and selection_from_dict({}).estimate_cost == "off"
    assert selection_from_dict({"feeds": "none", "publication_ids": "x,y"}).feeds == []


@pytest.mark.parametrize("bad", [{"feeds": "nope"}, {"type": "gif"}, {"estimate_cost": "maybe"},
                                 {"usd_reference": "plus"}, {"feeds": "none"}])
def test_options_reject_bad_values(bad):
    with pytest.raises(ValueError):
        selection_from_dict(bad)


def test_feed_params_and_dry_run_requests():
    sel = Selection(feeds=["trending", "top", "model-x", "approved"], type="video", models=["seedance_2_5"],
                    resolution="1080p", estimate_cost="all")
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off", page_size=500))
    urls = [r.url for r in sp.build_requests()]
    assert urls[0].endswith("/job-sets/costs") and "plan_set_key=ps_a3" in urls[1]
    assert any("/trending?size=50&type=video&model=seedance_2_5&resolution=1080p" in u for u in urls)
    assert any(u.endswith("/trending/top?size=100&type=video") for u in urls)          # top: size<=100, no model
    assert any(u.endswith("/model-x?size=50") for u in urls)                           # model-x: size+cursor only
    assert any("/approved?size=200&type=video" in u for u in urls)                     # approved capped at 200


# ------------------------------------------------------------------ pagination decisions
def test_next_page_decisions():
    body = {"items": [{"id": "a"}], "cursor": 0.0499870126, "has_more": True, "total": 10}
    assert next_page(body, None, 1) == (repr(0.0499870126), "next")
    assert next_page({**body, "has_more": False}, None, 1)[0] is None
    assert next_page({"items": [{"id": "a"}], "cursor": 0.1, "total": 1}, None, 1) == \
        (None, "no has_more (single-page feed)")                                       # trending/top
    assert next_page({**body, "items": []}, None, 0) == (None, "empty page")
    assert next_page({**body, "cursor": None}, None, 1) == (None, "cursor null")
    assert next_page(body, repr(0.0499870126), 1) == (None, "cursor repeated")
    assert next_page(body, "0.9", 0) == (None, "no new items on page")
    assert next_page("oops", None, 0)[0] is None


class _Resp:
    pass


def test_follow_up_paginates_then_stops_on_budget():
    sel = Selection()
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off", max_items=60))
    list(sp.build_requests())
    env = load("trending_p1.json")
    sp.count_primary(8)
    reqs = list(sp.follow_up(env, [], _Resp()))
    assert len(reqs) == 1 and "cursor=" in reqs[0].url and sp.totals["trending"] == 78595
    sp.count_primary(52)                                     # budget now spent
    reqs = list(sp.follow_up(load("trending_p2.json"), [], _Resp()))
    assert reqs == [] and sp.stop_reasons["trending"] == "max_items reached"


def test_follow_up_max_pages_and_detail_requests():
    sel = Selection(detail=True)
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off", max_items=3, max_pages=1))
    list(sp.build_requests())
    reqs = list(sp.follow_up(load("trending_p1.json"), [], _Resp()))
    details = [r for r in reqs if r.meta["endpoint"] == "community_detail"]
    assert len(details) == 3 and all(r.meta["params"]["feed"] == "trending" for r in details)
    assert len(reqs) == 3                                    # no next page: detail budget spent


POST_ID = "085b9664-5c1e-4d63-a9bb-cf4df65c0977"
PARENT_ID = "a24bd70f-7293-40ce-bdbc-f38df4cb9e66"
COMMENTS_FX = f"community_comments__limit-50__publication_id-{POST_ID}.json"
REPLIES_FX = f"community_comments__limit-50__parent_id-{PARENT_ID}__publication_id-{POST_ID}.json"


def test_with_comments_reads_community_posts_without_session():
    """Comments are public and live in fnf-community (gallery publications have none): --with-comments
    requests the posts feed, no session needed, and never the old fnf/publications/{id}/comments path."""
    sp = CommunitySpider(selection=Selection(with_comments=True), common=CommonOptions(auth="off", max_items=5))
    reqs = list(sp.build_requests())
    posts = [r for r in reqs if r.meta["endpoint"] == "community_posts"]
    assert len(posts) == 1 and posts[0].url == "https://fnf-api-gw.higgsfield.ai/fnf-community/publications/feed?limit=5"
    assert not posts[0].meta["auth"] and not sp.limits_hit
    # gallery feed pages no longer schedule per-publication comment requests
    out = list(sp.follow_up(load("trending_p1.json"), parse_envelope(load("trending_p1.json"), sp.selection), _Resp()))
    assert not any(r.meta["endpoint"] == "community_comments" for r in out)


def test_with_comments_follow_up_posts_comments_replies():
    sp = CommunitySpider(selection=Selection(with_comments=True), common=CommonOptions(auth="off"))
    env = load("community_posts__limit-3.json")
    reqs = list(sp.follow_up(env, parse_envelope(env, sp.selection), _Resp()))
    with_comments = [p for p in env.body["publications"] if p["comment_count"] > 0]
    assert len(reqs) == len(with_comments) >= 1
    assert reqs[0].url.startswith("https://fnf-api-gw.higgsfield.ai/fnf-community/publications/")
    assert reqs[0].url.endswith("/comments?limit=50") and not reqs[0].meta["auth"]
    env = load(COMMENTS_FX)
    ents = parse_envelope(env, sp.selection)
    reqs = list(sp.follow_up(env, ents, _Resp()))
    replies = [r for r in reqs if "parent_id=" in r.url]
    assert {r.meta["params"]["parent_id"] for r in replies} == {e["comment_id"] for e in ents if e["reply_count"]}
    assert all(r.meta["params"]["publication_id"] == POST_ID for r in reqs)
    # has_more -> next offset; replies of replies are not requested
    more = Envelope(endpoint="community_comments", url="u", status=200, body={**env.body, "has_more": True},
                    params={"publication_id": POST_ID, "limit": "50", "parent_id": PARENT_ID})
    nxt = list(sp.follow_up(more, parse_envelope(more, sp.selection), _Resp()))
    assert len(nxt) == 1 and "offset=2" in nxt[0].url and f"parent_id={PARENT_ID}" in nxt[0].url


# ------------------------------------------------------------------ parsers
def test_parse_image_item_fields():
    es = parse_envelope(load("trending_p1.json"), Selection())
    pages = [e for e in es if e["kind"] == "community_page"]
    gens = [e for e in es if e["kind"] == "community_generation"]
    assert len(pages) == 1 and pages[0]["has_more"] is True and pages[0]["total"] == 78595 and pages[0]["cursor"] is None
    assert not [e for e in es if e["kind"] == "community_creator"]                      # profiles are opt-in
    g = gens[0]
    assert g["job_set_type"] == g["model_id"] == "gpt_image_2_6" and g["media_type"] == "image"
    assert g["settings"]["width"] and g["settings"]["model"] == "aurora-img-alpha"
    assert g["upstream_usage"]["output_image_tokens"] > 0                                # meta.cost parsed
    assert g["created_at"].endswith("+00:00") and g["engagement"]["views"] is not None
    assert set(g["creator"]) == {"user_id"}                                              # pseudonymous only
    assert {r["name"] for r in g["results"]} == {"raw", "min"}
    params = [i["param"] for g in gens for i in g["inputs"]]
    assert {"medias", "reference_elements"} <= set(params)


def test_split_params_loses_nothing():
    for name in ALL:
        env = load(name)
        items = env.body.get("items") if isinstance(env.body, dict) and "items" in env.body else [env.body]
        for item in items:
            params = item.get("params") or {}
            text, settings, extra, inputs = split_params(params)
            covered = set(settings) | set(extra) | {i["param"] for i in inputs} | {k for k, v in text.items()
                                                                                    if v is not None}
            empty_inputs = {k for k, v in params.items() if v in ([], None)}
            assert set(params) - covered <= empty_inputs | {"prompt", "negative_prompt"}, name
            assert not (set(settings) & set(extra))


def test_video_items_and_results():
    gens = [e for e in parse_envelope(load("approved_last.json"), Selection()) if e["kind"] == "community_generation"]
    assert gens and all(g["media_type"] == "video" for g in gens)
    viral = [g for g in gens if g["job_set_type"] == "viral_hub_video"][0]
    assert "hls" in {r["name"] for r in viral["results"]} and viral["can_upgrade_to_4k"] is False
    assert viral["client_meta"] == {"source": "viral_hub_web"}
    seed = [g for g in gens if g["job_set_type"] == "seedance_2_5"][0]
    assert seed["settings"]["duration"] and seed["settings"]["resolution"]
    assert seed["inputs"][0]["param"] == "medias" and seed["inputs"][0]["role"]


def test_nsfw_item_without_results_and_helpers():
    gens = [e for e in parse_envelope(load("model_x_last.json"), Selection()) if e["kind"] == "community_generation"]
    nsfw = [g for g in gens if g["status"] == "nsfw"][0]
    assert nsfw["media_type"] == "unknown" and nsfw["results"] == []
    assert media_type_of({"results": {"h264": {"type": "video", "url": "u"}}}) == "video"
    assert media_type_of({"result": {"type": "audio", "url": "u"}}) == "audio"
    assert iso_ts(1795587493.078455).startswith("2026-11-25T") and iso_ts(None) is None
    assert iso_ts("2026-01-01T00:00:00Z") == "2026-01-01T00:00:00+00:00"
    assert parse_upstream_usage('{"a": 1}') == {"a": 1} and parse_upstream_usage("x") == {"raw": "x"}


def test_detail_envelope_and_profiles_opt_in():
    es = parse_envelope(load("detail.json"), Selection(with_profiles=True))
    g = [e for e in es if e["kind"] == "community_generation"][0]
    c = [e for e in es if e["kind"] == "community_creator"][0]
    assert g["detail_fetched"] and g["feed"] == "trending"
    assert c["username"].startswith("creator_") and g["creator"]["username"] == c["username"]
    # listing envelopes emit no generations with --detail (the detail responses carry them)
    assert {e["kind"] for e in parse_envelope(load("trending_p1.json"), Selection(detail=True))} == {"community_page"}


def test_keep_client_side_filters():
    sel = Selection(type="image", models=["gpt_image_2_6"])
    assert keep({"kind": "community_generation", "job_set_type": "gpt_image_2_6", "media_type": "image"}, sel)
    assert not keep({"kind": "community_generation", "job_set_type": "gpt_image_2_6", "media_type": "video"}, sel)
    assert not keep({"kind": "community_generation", "job_set_type": "x", "media_type": "image"}, sel)
    assert keep({"kind": "community_generation", "job_set_type": "x", "media_type": "video", "feed": "detail"}, sel)
    assert keep({"kind": "community_page"}, sel)


def test_raw_params_opt_in():
    g = parse_envelope(load("top.json"), Selection(with_raw_params=True))[1]
    assert g["raw_params"]["prompt"] == g["prompt"]
    assert parse_envelope(load("top.json"), Selection())[1]["raw_params"] is None


# ------------------------------------------------------------------ dataset / dedup / csv
def test_dedup_across_pages():
    ents = collect(Selection())
    ids = [g["generation_id"] for g in ents["community_generation"]]
    assert len(ids) == len(set(ids))
    p1 = {i["id"] for i in load("trending_p1.json").body["items"]}
    p2 = {i["id"] for i in load("trending_p2.json").body["items"]}
    assert p1 & p2                                         # fixture really contains a duplicate


def test_build_dataset_and_csv_completeness(tmp_path):
    sel = Selection(feeds=["trending", "approved", "top", "model-x"], with_profiles=True)
    ds = cds.build_dataset(collect(sel), sel, rm())
    assert ds["meta"]["counts"]["generations"] == len(ds["generations"]) > 15
    assert ds["meta"]["totals_available"]["trending"] == 78595
    assert ds["stats"]["by_media_type"]["video"] >= 4 and ds["creators"]
    assert all(c["generations_in_dataset"] >= 1 for c in ds["creators"])
    files = cds.write_outputs(ds, tmp_path)
    assert (tmp_path / "summary.md").read_text(encoding="utf-8").count("|") > 20
    assert (tmp_path / "schema" / "dataset.schema.json").exists() and files

    def cols(name):
        with (tmp_path / "csv" / f"{name}.csv").open(encoding="utf-8-sig") as f:
            r = csv.DictReader(f)
            return set(r.fieldnames or []), list(r)

    for table, records in (("generations", ds["generations"]), ("creators", ds["creators"]), ("pages", ds["pages"])):
        header, rows = cols(table)
        assert len(rows) == len(records)
        leaves = {k for rec in records for k, v in flatten(rec).items()}
        nullparents = {k for k in leaves if any(o.startswith(k + ".") for o in leaves)}
        missing = leaves - header - nullparents
        assert not missing, (table, sorted(missing)[:10])
    header, rows = cols("generation_inputs")
    assert len(rows) == sum(len(g["inputs"]) for g in ds["generations"])
    assert {"generation_id", "param", "role", "url"} <= header
    header, rows = cols("generation_results")
    assert len(rows) == sum(len(g["results"]) for g in ds["generations"])
    inp_header, _ = cols("generation_inputs")
    leaves = {k for g in ds["generations"] for i in g["inputs"] for k in flatten(i)}
    assert not {k for k in leaves if not any(o.startswith(k + ".") for o in leaves)} - inp_header
    res_header, _ = cols("generation_results")
    leaves = {k for g in ds["generations"] for r in g["results"] for k in flatten(r)}
    assert not {k for k in leaves if not any(o.startswith(k + ".") for o in leaves)} - res_header


def test_creators_absent_without_profiles():
    sel = Selection()
    ds = cds.build_dataset(collect(sel), sel, rm())
    assert ds["creators"] == []
    assert all(set(g["creator"]) >= {"user_id"} and g["creator"]["username"] is None for g in ds["generations"])
    blob = json.dumps(ds)
    assert not re.search(r"creator_\d", blob) and "example.invalid/avatar" not in blob and "ig_fake" not in blob


class FakeEstimator:
    calls: list = []

    @classmethod
    def from_job_costs_body(cls, body, usd_per_credit=None, usd_reference=None):
        inst = cls()
        inst.rate, inst.ref = usd_per_credit, usd_reference
        return inst

    def estimate(self, job_set_type, params, media_type=None):
        FakeEstimator.calls.append((job_set_type, params, media_type))
        if job_set_type == "kling3_0":
            return {"status": "unpriced", "notes": ["no price"]}
        cr = 10.0 if media_type == "video" else 2.0
        return {"status": "exact", "credits": cr, "usd": cr * (self.rate or 0), "usd_per_credit": self.rate,
                "usd_reference": self.ref}


def _cost_envs():
    jc = Envelope.load(RAW / "job_costs.json")
    jc.endpoint = "community_job_costs"
    pl = Envelope.load(RAW / "plans__plan_set_key-ps_a3.json")
    pl.endpoint = "community_plans"
    return [jc, pl]


def test_cost_estimates_with_fake_estimator(monkeypatch):
    from higgsfield_scraper import estimate
    monkeypatch.setattr(estimate, "CostEstimator", FakeEstimator)
    sel = Selection(feeds=["trending", "approved"], estimate_cost="videos")
    ents = collect(sel)
    for env in _cost_envs():
        for e in parse_envelope(env, sel):
            ents.setdefault(e["kind"], []).append(validate_entity(e))
    basis = {b["basis_id"]: b for b in ents["community_cost_basis"]}
    assert basis["usd_reference"]["usd_per_credit"] and basis["job_costs"]["job_costs"]["data"]
    ds = cds.build_dataset(ents, sel, rm())
    st = {g["media_type"]: [] for g in ds["generations"]}
    for g in ds["generations"]:
        st[g["media_type"]].append(g["estimated_cost"]["status"])
    assert set(st["image"]) == {"skipped"}                                   # --estimate-cost videos
    assert "exact" in st["video"] and "unpriced" in st["video"]              # kling3_0 unpriced in the fake
    assert ds["stats"]["estimated_credits_total"] == 10.0 * st["video"].count("exact")
    assert ds["stats"]["cost_basis"]["usd_per_credit"] == basis["usd_reference"]["usd_per_credit"]
    assert ds["stats"]["estimated_usd_total"] > 0
    assert all(isinstance(c[1], dict) and "prompt" in c[1] for c in FakeEstimator.calls)


def test_estimates_off_and_unavailable(monkeypatch):
    sel = Selection()
    ds = cds.build_dataset(collect(sel), sel, rm())
    assert all(g["estimated_cost"] is None for g in ds["generations"])
    assert ds["stats"]["estimated_credits_total"] is None
    from higgsfield_scraper import estimate
    monkeypatch.setattr(estimate, "CostEstimator", None)
    sel = Selection(estimate_cost="all")
    ds = cds.build_dataset(collect(sel), sel, rm())
    assert {g["estimated_cost"]["status"] for g in ds["generations"]} == {"skipped"}
    assert any("not available" in w for w in ds["meta"]["warnings"])


def test_reconstruct_params_matches_raw_for_estimator():
    raw = parse_envelope(load("approved_last.json"), Selection(with_raw_params=True))
    plain = parse_envelope(load("approved_last.json"), Selection())
    for a, b in zip(raw, plain):
        if a["kind"] != "community_generation":
            continue
        rebuilt = cds.reconstruct_params(validate_entity(b))
        orig = {k: v for k, v in a["raw_params"].items() if v not in ([], None)}
        assert {k for k in orig} <= set(rebuilt)
        if "medias" in orig:
            assert rebuilt["medias"][0]["data"]["url"] == orig["medias"][0]["data"]["url"]


def test_media_urls_modes():
    gens = [validate_entity(e) for e in parse_envelope(load("approved_last.json"), Selection())
            if e["kind"] == "community_generation"]
    v = gens[0]
    v["results"].append({"name": "h264", "type": "video", "url": "https://x/h.mp4", "thumbnail_url": None, "extra": {}})
    thumbs = media_urls(v, "thumbs")
    assert len(thumbs) == 1 and thumbs[0][1].endswith(".webp")               # video -> thumbnail image
    full = dict(media_urls(v, "full"))
    assert full["raw"].endswith(".mp4") and full["h264"] == "https://x/h.mp4"
    allm = media_urls(v, "all")
    assert any(r.startswith("input") for r, _ in allm) and not any(u.endswith(".m3u8") for _, u in allm)
    img = [validate_entity(e) for e in parse_envelope(load("top.json"), Selection())
           if e["kind"] == "community_generation"][0]
    assert media_urls(img, "thumbs")[0][0] == "thumb" and media_urls(img, "none") == []


def test_comments_parser_real_shape_and_privacy():
    env = load(COMMENTS_FX)
    out = [validate_entity(e) for e in parse_envelope(env, Selection())]
    assert len(out) == 2 and all(c["publication_id"] == POST_ID and c["thread_type"] == "publication" for c in out)
    c = next(x for x in out if x["comment_id"] == PARENT_ID)
    assert c["text"] and c["likes"] == 1 and c["reply_count"] == 1 and c["dislikes"] == 0
    assert c["reactions"] and c["reactions"][0]["count"] == 1 and c["created_at"] and c["updated_at"]
    assert c["username"] is None and set(c["author"]) <= {"badge", "rating_points"}     # redacted by default
    assert c["extra"] == {}
    prof = parse_envelope(env, Selection(with_profiles=True))[0]
    assert prof["username"] == "<redacted>" and "full_name" in prof["author"]            # fixture is redacted
    assert iso_ts("2026-11-24T11:03:50.21733Z") == "2026-11-24T11:03:50.217330+00:00"     # 5 fraction digits
    assert iso_ts("2026-11-24T11:03:50.1234567Z") == "2026-11-24T11:03:50.123456+00:00"
    rep = [validate_entity(e) for e in parse_envelope(load(REPLIES_FX), Selection())]
    assert len(rep) == 1 and rep[0]["parent_id"] == PARENT_ID


def test_comments_parser_is_defensive():
    env = Envelope(endpoint="community_comments", url="u", status=200, params={"publication_id": "p1"},
                   body={"items": [{"id": "c1", "text": "nice", "created_at": 1795587493.0, "likes_count": 2,
                                    "user_id": "user_x", "profile": {"username": "someone"}, "foo": 1},
                                   {"no_id": True}]})
    out = parse_envelope(env, Selection())
    assert len(out) == 1 and out[0]["username"] is None and out[0]["extra"] == {"foo": 1}
    validate_entity(out[0])
    assert parse_envelope(env, Selection(with_profiles=True))[0]["username"] == "someone"
    assert parse_envelope(Envelope(endpoint="community_comments", url="u", status=401, body={}), Selection()) == []
