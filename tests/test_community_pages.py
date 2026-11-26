"""Opt-in Community pages (docs/COMMUNITY_COVERAGE.md): community --feeds shots|posts|feed|creators|talents and
site --what room-list|room-content. Offline, on trimmed + redacted fixtures. Also proves the defaults are unchanged."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.community import SCRAPER as COMMUNITY, media_urls
from higgsfield_scraper.scrapers.community import dataset as cds
from higgsfield_scraper.scrapers.community.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.community.parsers import keep, parse_envelope
from higgsfield_scraper.scrapers.community.privacy import REDACTED, CreatorsPrivacyMiddleware, sanitize_users
from higgsfield_scraper.scrapers.community.schemas import CommunityDataset, CommunityDatasetExt
from higgsfield_scraper.scrapers.community.spider import CommunitySpider
from higgsfield_scraper.scrapers.site import dataset as sds
from higgsfield_scraper.scrapers.site.options import Selection as SiteSelection
from higgsfield_scraper.scrapers.site.parsers import keep as site_keep, parse_envelope as site_parse
from higgsfield_scraper.scrapers.site.schemas import SiteDataset, SiteDatasetExt
from higgsfield_scraper.validation import validate_entity

FIX_C = Path(__file__).parent / "fixtures" / "community"
FIX_S = Path(__file__).parent / "fixtures" / "site"
EXTRA_FX = ["community_shots.json", "community_posts_list.json", "community_feed.json", "community_creators.json",
            "community_talents.json", "community_entity_comments.json"]
ROOM_FX = ["rooms_api.json", "room_stats.json", "room_items.json", "room_discussions.json"]
PROFILE_KEYS = ("username", "full_name", "avatar_url", "headline")


def env_c(name: str) -> Envelope:
    return Envelope.load(FIX_C / name)


def env_s(name: str) -> Envelope:
    return Envelope.load(FIX_S / name)


def rm() -> RunMeta:
    return RunMeta(run_id="t", label="t", scraped_at=datetime(2026, 11, 26, tzinfo=timezone.utc),
                   common=CommonOptions(max_items=100))


def collect(sel, names, parse=parse_envelope, keep_fn=keep, loader=env_c) -> dict[str, list[dict]]:
    ids = registry.all_id_fields()
    out: dict[str, list[dict]] = {}
    seen: set = set()
    for n in names:
        for e in parse(loader(n), sel):
            if not keep_fn(e, sel):
                continue
            v = validate_entity(e)
            key = (v["kind"], v.get(ids.get(v["kind"], ""), id(v)))
            if key not in seen:
                seen.add(key)
                out.setdefault(v["kind"], []).append(v)
    return out


class _Resp:
    pass


# ------------------------------------------------------------------ defaults stay unchanged
def test_default_selection_and_manifest_unchanged():
    sel = Selection()
    assert sel.feeds == ["trending"] and sel.extra_feeds == []
    assert "extra_feeds" not in sel.to_dict()                       # default manifest/meta options identical
    assert Selection(feeds="all").feeds == ["trending", "approved", "top", "model-x"]   # 'all' never adds opt-ins
    s = SiteSelection()
    assert not s.rooms_api and "room-list" not in s.what and "room-content" not in s.what
    assert not SiteSelection(what="all").rooms_api


def test_default_requests_unchanged():
    sp = CommunitySpider(selection=Selection(), common=CommonOptions(auth="off"))
    assert [r.url for r in sp.build_requests()] == [
        "https://fnf-api-gw.higgsfield.ai/fnf/publications/community/trending?size=50"]
    sp = CommunitySpider(selection=Selection(with_comments=True), common=CommonOptions(auth="off", max_items=5))
    assert [r.meta["endpoint"] for r in sp.build_requests()] == ["community_posts", "community_trending"]


def test_default_datasets_keep_their_models(tmp_path):
    ents = collect(Selection(), EXTRA_FX)                            # even if such entities were present
    ds = cds.build_dataset(ents, Selection(), rm())
    assert "shots" not in ds and "extra_stats" not in ds
    assert set(ds["meta"]["counts"]) == {"generations", "creators", "comments", "pages"}
    cds.write_outputs(ds, tmp_path)
    assert {p.stem for p in (tmp_path / "csv").glob("*.csv")} == {
        "run_meta", "generations", "generation_inputs", "generation_results", "creators", "comments", "pages", "stats"}
    schema = json.loads((tmp_path / "schema" / "dataset.schema.json").read_text(encoding="utf-8"))
    assert schema == CommunityDataset.model_json_schema(mode="serialization")
    sel = SiteSelection()
    ds = sds.build_dataset(collect(sel, ROOM_FX, site_parse, site_keep, env_s), sel, rm())
    assert "rooms" not in ds and "rooms" not in ds["meta"]["counts"]
    assert set(ds) == set(SiteDataset.model_fields)


# ------------------------------------------------------------------ options
def test_options_opt_in_feeds_roundtrip_and_label():
    from higgsfield_scraper.scrapers.community.options import default_label
    sel = Selection(feeds="shots,posts")
    assert sel.feeds == [] and sel.extra_feeds == ["shots", "posts"] and sel.wants("shots")
    assert selection_from_dict(sel.to_dict()) == sel and default_label(sel) == "shots-posts"
    sel = Selection(feeds="all,creators")
    assert sel.feeds == ["trending", "approved", "top", "model-x"] and sel.extra_feeds == ["creators"]
    assert Selection(feeds="none", extra_feeds=["talents"]).feeds == []
    with pytest.raises(ValueError):
        Selection(feeds="bogus")
    assert SiteSelection(what="rooms-api").what == ["room-list"] and SiteSelection(what="room-items").rooms_api


# ------------------------------------------------------------------ parsers
def test_shots_join_keys_and_privacy():
    shots = collect(Selection(), ["community_shots.json"])["community_shot"]
    s = shots[0]
    assert s["url"] == f"https://higgsfield.ai/community/generations?shot={s['shot_id']}"
    assert s["generation_id"] and s["job_set_type"] and s["media_type"] in ("image", "video")
    assert all(x["author"]["user_id"].startswith("user_REDACTED") for x in shots)
    assert all(x["author"][k] is None for x in shots for k in PROFILE_KEYS)
    with_p = collect(Selection(with_profiles=True), ["community_shots.json"])["community_shot"]
    assert with_p[0]["author"]["username"] is not None
    raw = env_c("community_shots.json").body["items"][0]
    assert (s["likes"], s["views"], s["comments"]) == (raw["like_count"], raw["view_count"], raw["comment_count"])


def test_posts_and_media():
    posts = collect(Selection(), ["community_posts_list.json"])["community_post"]
    p = posts[0]
    assert p["url"].endswith(p["post_id"]) and p["text"] and p["media"]
    m = p["media"][0]
    assert m["type"] == "project_publication" and m["project_publication_id"] and m["card_stats"]
    assert m["url"] is None                                         # job_result.url "" -> None, never ""
    assert p["author"]["username"] is None and p["views"] is not None


def test_feed_items_types():
    items = collect(Selection(), ["community_feed.json"])["community_feed_item"]
    types = {i["item_type"] for i in items}
    assert {"generation", "project_publication", "blog_post"} <= types
    gen = next(i for i in items if i["item_type"] == "generation")
    assert gen["generation_id"] and gen["job_set_type"] and gen["views"] is not None and gen["url"]
    assert [i["position"] for i in items] == sorted(i["position"] for i in items)
    assert all(i["author"]["username"] is None for i in items)


def test_creators_and_talents_aggregate_only():
    ents = collect(Selection(), ["community_creators.json", "community_talents.json"])["community_creator_stats"]
    assert {e["listing"] for e in ents} == {"creators", "talents"}
    c = ents[0]
    assert c["record_id"] and c["user_id"].startswith("user_REDACTED") and c["followers_count"] is not None
    assert c["works_count"] == len(c["works"])
    assert all(e[k] is None for e in ents for k in ("username", "full_name", "bio", "headline", "location",
                                                    "avatar_url"))


def test_entity_comments_parse():
    e = env_c("community_entity_comments.json")
    ents = collect(Selection(), ["community_entity_comments.json"])["community_comment"]
    assert ents and all(c["thread_type"] == e.params["entity_type"] for c in ents)
    assert all(c["publication_id"] == e.params["entity_id"] for c in ents)
    assert all(c["username"] is None for c in ents)


def test_creators_privacy_middleware():
    body = {"users": [{"id": "u", "username": "x", "bio": "b", "location": "l", "headline": "", "rating_points": 3}],
            "total": 1}
    out = sanitize_users(body)
    assert out["users"][0]["username"] == REDACTED and out["users"][0]["bio"] == REDACTED
    assert out["users"][0]["headline"] == "" and out["users"][0]["rating_points"] == 3
    assert sanitize_users(out) == out                               # idempotent

    class R:
        def __init__(self, ep):
            self.meta = {"endpoint": ep}

    raw_body = json.dumps(body).encode()

    class Resp:
        body = raw_body

        def replace(self, body):
            r = Resp()
            r.body = body
            return r

    class Sp:
        selection = Selection()

    mw = CreatorsPrivacyMiddleware()
    resp = Resp()
    assert mw.process_response(R("community_trending"), resp, Sp()) is resp          # other endpoints untouched
    got = json.loads(mw.process_response(R("community_creators"), resp, Sp()).body)
    assert got["users"][0]["bio"] == REDACTED
    Sp.selection = Selection(with_profiles=True)
    assert mw.process_response(R("community_talents"), resp, Sp()) is resp


# ------------------------------------------------------------------ spider
def test_opt_in_requests_and_page_size_capped_by_max_items():
    sel = Selection(feeds="shots,posts,feed,creators,talents", type="video", models="seedance_2_5")
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off", max_items=7))
    urls = {r.meta["endpoint"]: r.url for r in sp.build_requests()}
    assert urls["community_shots"] == ("https://fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=7"
                                       "&type=video&models=seedance_2_5")
    assert urls["community_posts_list"].endswith("/fnf-community/publications/feed?limit=7")
    assert urls["community_feed"].endswith("/fnf-community/feed?limit=7")
    assert "/fnf/community/discovery/v2/creators?all=true&sort=default&limit=7" in urls["community_creators"]
    assert urls["community_talents"].endswith("/fnf/community/discovery/talents?sort=rating&limit=7&offset=0")
    assert "community_posts" not in urls and "community_trending" not in urls


def test_extra_follow_up_paginates_and_requests_comment_threads():
    sel = Selection(feeds="shots,feed,talents", with_comments=True)
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off", max_items=500))
    list(sp.build_requests())
    for name in ("community_shots.json", "community_feed.json"):
        e = env_c(name)
        ents = parse_envelope(e, sel)
        sp._extra_ids |= {str(x.get("shot_id") or x.get("feed_item_id")) for x in ents}
        reqs = list(sp.follow_up(e, ents, _Resp()))
        nxt = [r for r in reqs if r.meta["endpoint"] in ("community_shots", "community_feed")]
        assert len(nxt) == 1 and "cursor=" in nxt[0].url
        threads = [r for r in reqs if r.meta["endpoint"] in ("community_entity_comments", "community_comments")]
        assert len(threads) == sum(1 for x in ents if (x.get("comments") or 0) > 0)
    e = env_c("community_talents.json")
    ents = parse_envelope(e, sel)
    sp._extra_ids |= {x["record_id"] for x in ents}
    reqs = list(sp.follow_up(e, ents, _Resp()))
    assert sp.totals["talents"] == e.body["total"]
    assert [r.meta["params"]["offset"] for r in reqs] == [str(e.body["next_offset"])]


def test_entity_comments_follow_up_replies():
    sel = Selection(feeds="shots", with_comments=True)
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off"))
    e = env_c("community_entity_comments.json")
    ents = parse_envelope(e, sel)
    reqs = list(sp.follow_up(e, ents, _Resp()))
    replies = [r for r in reqs if "parent_id=" in r.url]
    assert {r.meta["params"]["parent_id"] for r in replies} == {c["comment_id"] for c in ents if c["reply_count"]}
    assert all(f"/entities/{e.params['entity_type']}/{e.params['entity_id']}/comments" in r.url for r in reqs)


def test_media_urls_for_opt_in_kinds():
    s = collect(Selection(), ["community_shots.json"])["community_shot"][0]
    assert media_urls({**s, "kind": "community_shot"}, "thumbs")
    assert media_urls({**s, "kind": "community_shot"}, "none") == []


# ------------------------------------------------------------------ dataset + CSVs
def _cols(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return set(r.fieldnames or []), list(r)


def _assert_complete(records, path: Path, drop=()):
    header, rows = _cols(path)
    assert len(rows) == len(records), path.name
    leaves = {k for rec in records for k in flatten({a: b for a, b in rec.items() if a not in drop})}
    missing = {k for k in leaves if k not in header and not any(c.startswith(k + ".") for c in header)}
    assert not missing, (path.name, sorted(missing)[:10])


def test_community_ext_dataset_and_complete_csvs(tmp_path):
    sel = Selection(feeds="shots,posts,feed,creators,talents", with_comments=True)
    ents = collect(sel, EXTRA_FX)
    # the comments fixture belongs to another shot: add that shot so its thread is kept (others are dropped)
    entity_id = env_c("community_entity_comments.json").params["entity_id"]
    ents["community_shot"].append({**ents["community_shot"][0], "shot_id": entity_id})
    ds = cds.build_dataset(ents, sel, rm())
    CommunityDatasetExt.model_validate(ds)
    c = ds["meta"]["counts"]
    assert c["shots"] == len(ds["shots"]) > 0 and c["posts"] and c["feed_items"] and c["creator_stats"]
    assert ds["comments"] and ds["extra_stats"]["comments_by_thread_type"]
    assert "entity_comments" in ds["meta"]["endpoints"]
    cds.write_outputs(ds, tmp_path)
    _assert_complete(ds["shots"], tmp_path / "csv" / "shots.csv")
    _assert_complete(ds["posts"], tmp_path / "csv" / "posts.csv", drop=("media",))
    _assert_complete([m for p in ds["posts"] for m in p["media"]], tmp_path / "csv" / "post_media.csv")
    _assert_complete(ds["feed_items"], tmp_path / "csv" / "feed_items.csv")
    _assert_complete(ds["creator_stats"], tmp_path / "csv" / "creator_stats.csv", drop=("works",))
    _assert_complete([w for x in ds["creator_stats"] for w in x["works"]], tmp_path / "csv" / "creator_works.csv")
    assert "Opt-in Community pages" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    schema = json.loads((tmp_path / "schema" / "dataset.schema.json").read_text(encoding="utf-8"))
    assert "shots" in schema["properties"]


# ------------------------------------------------------------------ site rooms
def test_room_parsers_and_privacy():
    sel = SiteSelection(what="room-content")
    ents = collect(sel, ROOM_FX, site_parse, site_keep, env_s)
    rooms = ents["site_room"]
    assert rooms[0]["url"] == f"https://higgsfield.ai/community/rooms/{rooms[0]['slug']}"
    assert rooms[0]["followers_count"] is not None and rooms[0]["owner_username"] is None
    assert rooms[0]["owner_user_id"].startswith("user_REDACTED")
    items = ents["site_room_item"]
    assert {"shot", "project_publication", "blog_post"} <= {i["item_type"] for i in items}
    shot = next(i for i in items if i["item_type"] == "shot")
    assert shot["generation_id"] and shot["item_id"] and shot["prompt"] and shot["url"].endswith(shot["item_id"])
    blog = next(i for i in items if i["item_type"] == "blog_post")
    assert blog["created_at"] and blog["views"] is not None
    disc = ents["site_room_discussion"]
    assert disc and disc[0]["room_id"] and disc[0]["author"]["username"] is None
    assert ents["site_room_stats"][0]["posts"] is not None
    with_p = collect(SiteSelection(what="room-list", with_profiles=True), ["rooms_api.json"], site_parse, site_keep,
                     env_s)["site_room"]
    assert with_p[0]["owner_username"] is not None
    only = SiteSelection(what="room-content", only="no-such-room")
    assert not any(site_keep(i, only) for i in items)


def test_site_rooms_requests_and_follow_up():
    from higgsfield_scraper.scrapers.site.spider import SiteSpider
    sel = SiteSelection(what="room-content")
    sp = SiteSpider(selection=sel, common=CommonOptions(auth="off", max_items=1))
    assert [r.url for r in sp.build_requests()] == ["https://fnf-api-gw.higgsfield.ai/fnf-community/rooms?limit=50"]
    e = env_s("rooms_api.json")
    reqs = [r for r in sp.follow_up(e, [], _Resp()) if r is not None]
    eps = [r.meta["endpoint"] for r in reqs]
    assert eps == ["room_stats", "room_items", "room_discussions"]      # max_items=1: one room, no next list page
    assert "kind=discussion" in reqs[2].url and "room_id=" in reqs[2].url
    assert sp.totals["rooms_api_total"] == e.body["total"]
    sp = SiteSpider(selection=SiteSelection(what="room-list"), common=CommonOptions(auth="off"))
    list(sp.build_requests())
    eps = [r.meta["endpoint"] for r in sp.follow_up(e, [], _Resp()) if r is not None]
    assert set(eps) == {"room_stats", "rooms_api"} and eps.count("room_stats") == len(e.body["items"])


def test_site_rooms_dataset_and_complete_csvs(tmp_path):
    sel = SiteSelection(what="room-content")
    ds = sds.build_dataset(collect(sel, ROOM_FX, site_parse, site_keep, env_s), sel, rm())
    SiteDatasetExt.model_validate(ds)
    assert ds["meta"]["counts"]["rooms"] == len(ds["rooms"]) > 0 and ds["room_items"] and ds["room_discussions"]
    stats_room = env_s("room_stats.json").params["room_id"]
    merged = [r for r in ds["rooms"] if r["room_id"] == stats_room]
    if merged:
        assert merged[0]["posts_count"] == env_s("room_stats.json").body["posts"]
    assert "rooms_api" in ds["meta"]["endpoints"]
    sds.write_outputs(ds, tmp_path)
    _assert_complete(ds["rooms"], tmp_path / "csv" / "rooms.csv", drop=("works_preview_ids",))
    _assert_complete(ds["room_items"], tmp_path / "csv" / "room_items.csv", drop=("tags", "author_user_ids"))
    _assert_complete(ds["room_discussions"], tmp_path / "csv" / "room_discussions.csv", drop=("media",))
    assert "Community rooms" in (tmp_path / "summary.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ auth gating (logged-in adds only viewer flags)
VIEWER_KEYS = {"is_liked_by_user", "liked_by_me", "is_liked", "is_followed", "join_requested", "is_subscribed",
               "is_mine", "my_vote"}


def _keys(o, out=None):
    out = set() if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(o, list):
        for x in o:
            _keys(x, out)
    return out


def test_opt_in_requests_never_send_a_session_even_with_auth_required():
    """The opt-in pages are public; a login only adds the viewer's own flags (docs: 'Anonymous vs logged in'),
    so every new request is anonymous (meta auth False) whatever --auth says."""
    from higgsfield_scraper.scrapers.site.spider import SiteSpider
    sel = Selection(feeds="shots,posts,feed,creators,talents", with_comments=True)
    for auth in ("off", "auto", "required"):
        sp = CommunitySpider(selection=sel, common=CommonOptions(auth=auth, max_items=5))
        reqs = list(sp.build_requests())
        reqs.append(sp._entity_comments("generation_publication", "x"))
        assert reqs and all(r.meta["auth"] is False for r in reqs) and all(
            "Authorization" not in r.headers for r in reqs)
        sp = SiteSpider(selection=SiteSelection(what="room-content"), common=CommonOptions(auth=auth))
        reqs = list(sp.build_requests()) + [r for r in sp.follow_up(env_s("rooms_api.json"), [], _Resp()) if r]
        assert all(r.meta["auth"] is False for r in reqs)


def test_viewer_flags_never_reach_the_outputs():
    """Logged-in bodies carry is_liked_by_user / liked_by_me / is_followed / join_requested (personal to the
    viewer): parsers drop them, so a run with a session gives the same records as an anonymous one."""
    def flag(o):
        if isinstance(o, dict):
            o = {k: flag(v) for k, v in o.items()}
            o.update({k: True for k in ("is_liked_by_user", "liked_by_me", "is_liked", "is_followed",
                                        "join_requested") if k in o})
            return o
        return [flag(x) for x in o] if isinstance(o, list) else o

    sel = Selection(feeds="shots,posts,feed,creators,talents")
    for name in EXTRA_FX:
        e = env_c(name)
        anon = parse_envelope(e, sel)
        e.body = flag(e.body)
        authed = parse_envelope(e, sel)
        assert [x for x in authed if x["kind"] != "community_comment"] == \
               [x for x in anon if x["kind"] != "community_comment"], name
        assert not (_keys([x for x in authed if x["kind"] != "community_comment"]) & VIEWER_KEYS), name
    for name in ROOM_FX:
        e = env_s(name)
        anon = site_parse(e, SiteSelection(what="room-content"))
        e.body = flag(e.body)
        assert site_parse(e, SiteSelection(what="room-content")) == anon, name
