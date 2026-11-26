"""Community completeness fixes (docs/COMPLETENESS.md §11 #1, #3, #4, #10, #14; docs/CONTENT_MAP.md §16 feed
categories): creator / talent works in full, Feed post media + project card video, post-card counters, shot model
facets, creator_uid_key, and the opt-in --feeds feed-categories. Offline, on trimmed + redacted fixtures."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.core.privacy import creator_uid_key
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.community import SCRAPER, media_urls
from higgsfield_scraper.scrapers.community import dataset as cds
from higgsfield_scraper.scrapers.community.options import Selection, default_label, selection_from_dict
from higgsfield_scraper.scrapers.community.parsers import keep, parse_envelope, parse_generation
from higgsfield_scraper.scrapers.community.schemas import CommunityDatasetExt
from higgsfield_scraper.scrapers.community.spider import CommunitySpider
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "community"
PROFILE = ("username", "full_name", "avatar_url", "headline", "bio", "location")
VIEWER_KEYS = {"is_liked_by_user", "liked_by_me", "is_liked", "is_followed", "join_requested", "is_subscribed",
               "is_mine", "my_vote"}


def env(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def rm() -> RunMeta:
    return RunMeta(run_id="t", label="t", scraped_at=datetime(2026, 11, 26, tzinfo=timezone.utc),
                   common=CommonOptions(max_items=100))


def collect(sel, names) -> dict[str, list[dict]]:
    ids = registry.all_id_fields()
    out: dict[str, list[dict]] = {}
    seen: set = set()
    for n in names:
        for e in parse_envelope(env(n), sel):
            if not keep(e, sel):
                continue
            v = validate_entity(e)
            key = (v["kind"], v.get(ids.get(v["kind"], ""), id(v)))
            if key not in seen:
                seen.add(key)
                out.setdefault(v["kind"], []).append(v)
    return out


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


# ------------------------------------------------------------------ #1 creator / talent works
def test_creator_works_one_row_per_item_with_rank_and_join_keys():
    sel = Selection(feeds="talents")
    ents = collect(sel, ["community_talents_works.json"])
    cards, works = ents["community_creator_stats"], ents["community_creator_work"]
    raw_users = env("community_talents_works.json").body["users"]
    assert len(works) == sum(len(u["items"]) for u in raw_users) == sum(c["works_count"] for c in cards)
    for c in cards:
        mine = sorted((w for w in works if w["record_id"] == c["record_id"]), key=lambda w: w["rank"])
        assert [w["rank"] for w in mine] == list(range(c["works_count"]))
        assert [(w["item_type"], w["item_id"]) for w in mine] == [(x["type"], x["item_id"]) for x in c["works"]]
        assert all(w["creator_user_id"] == c["user_id"] and w["listing"] == "talents" for w in mine)
        assert all(w["creator_uid_key"] == creator_uid_key(c["user_id"]) == c["creator_uid_key"] for w in mine)
    assert {w["item_type"] for w in works} == {"shot", "project"}


def test_creator_work_shot_reuses_the_generation_parser():
    sel = Selection(feeds="talents")
    raw_users = env("community_talents_works.json").body["users"]
    raw = next(w["item"] for u in raw_users for w in u["items"] if w["type"] == "shot")
    works = collect(sel, ["community_talents_works.json"])["community_creator_work"]
    w = next(x for x in works if x["generation_id"] == raw["id"])
    g = validate_entity(parse_generation(raw, "trending", sel, env("community_talents_works.json").provenance()))
    for k in ("job_set_type", "prompt", "settings", "params_extra", "inputs", "results", "upstream_usage", "parent_id",
              "publication_id", "media_type", "status", "created_at", "published_at"):
        assert w[k] == g[k], k
    assert (w["likes"], w["views"], w["approved"]) == (g["engagement"]["likes"], g["engagement"]["views"],
                                                       g["engagement"]["approved"])
    assert w["prompt"] and w["results"] and w["settings"] is not None
    assert w["enhanced_prompt"] == raw["params"].get("enhanced_prompt")
    assert w["url"] == f"https://higgsfield.ai/community/generations?shot={raw['publication']['id']}"
    assert any(x["inputs"] for x in works if x["item_type"] == "shot")
    assert all(x["raw_params"] is None for x in works)                     # only with --with-raw-params
    with_raw = collect(Selection(feeds="talents", with_raw_params=True),
                       ["community_talents_works.json"])["community_creator_work"]
    assert next(x for x in with_raw if x["generation_id"] == raw["id"])["raw_params"] == raw["params"]


def test_creator_work_project_card_fields():
    raw_users = env("community_talents_works.json").body["users"]
    raw = next(w["item"] for u in raw_users for w in u["items"] if w["type"] == "project")
    works = collect(Selection(feeds="talents"), ["community_talents_works.json"])["community_creator_work"]
    w = next(x for x in works if x.get("project_publication_id") == raw["publication_id"])
    assert (w["title"], w["description"], w["likes"], w["views"], w["comments"]) == (
        raw["name"], raw["description"], raw["likes"], raw["views"], raw["comments"])
    assert w["duration_seconds"] == raw["duration_seconds"] and w["cover_url"] == raw["cover"]["url"]
    gallery = [m for m in w["gallery_media"] if m["role"] == "gallery"]
    assert [m["url"] for m in gallery] == [g["url"] for g in raw["gallery_media"]]
    assert all(m["width"] and m["height"] for m in gallery)
    assert w["author_user_ids"] == raw["author_user_ids"]
    assert w["author_uid_keys"] == [creator_uid_key(a) for a in raw["author_user_ids"]]
    assert w["prompt"] is None and w["generation_id"] is None


def test_creator_works_privacy_and_viewer_flags():
    sel = Selection(feeds="talents")
    e = env("community_talents_works.json")
    works = [x for x in parse_envelope(e, sel) if x["kind"] == "community_creator_work"]
    blob = json.dumps(works)
    assert "<redacted>" not in blob and '"authors"' not in blob and '"profile"' not in blob
    assert not (_keys(works) & VIEWER_KEYS)
    assert not (set(PROFILE) & _keys(works))

    def flag(o):
        if isinstance(o, dict):
            o = {k: flag(v) for k, v in o.items()}
            o.update({k: True for k in ("is_liked_by_user", "is_liked", "is_followed") if k in o})
            return o
        return [flag(x) for x in o] if isinstance(o, list) else o

    e.body = flag(e.body)
    assert [x for x in parse_envelope(e, sel) if x["kind"] == "community_creator_work"] == works


def test_creator_works_dataset_filters_dropped_cards_and_merges_csv(tmp_path):
    sel = Selection(feeds="creators,talents,shots,feed,posts")
    ents = collect(sel, ["community_talents_works.json", "community_shots.json", "community_feed.json",
                         "community_posts_list.json", "community_creators.json"])
    dropped = ents["community_creator_stats"].pop(0)                  # as if --max-items cut this card
    ds = cds.build_dataset(ents, sel, rm())
    CommunityDatasetExt.model_validate(ds)
    assert ds["creator_works"] and all(w["record_id"] != dropped["record_id"] for w in ds["creator_works"])
    assert ds["meta"]["counts"]["creator_works"] == len(ds["creator_works"]) == ds["extra_stats"]["creator_works"]
    cds.write_outputs(ds, tmp_path)
    with (tmp_path / "csv" / "creator_works.csv").open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        header, rows = set(r.fieldnames or []), list(r)
    assert len(rows) == sum(len(c["works"]) for c in ds["creator_stats"])
    assert {"record_id", "user_id", "listing", "position", "type", "item_id", "title", "is_pinned"} <= header
    leaves = {k for w in ds["creator_works"] for k in flatten({a: b for a, b in w.items()
                                                                if a not in ("inputs", "results", "gallery_media")})}
    assert not {k for k in leaves if k not in header and not any(c.startswith(k + ".") for c in header)}
    for name, n in (("creator_work_inputs", sum(len(w["inputs"]) for w in ds["creator_works"])),
                    ("creator_work_results", sum(len(w["results"]) for w in ds["creator_works"])),
                    ("creator_work_media", sum(len(w["gallery_media"]) for w in ds["creator_works"]))):
        with (tmp_path / "csv" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as f:
            assert len(list(csv.DictReader(f))) == n > 0, name
    assert (tmp_path / "json" / "creator_works.json").exists()


def test_creator_work_media_urls():
    works = collect(Selection(feeds="talents"), ["community_talents_works.json"])["community_creator_work"]
    shot = next(w for w in works if w["item_type"] == "shot")
    proj = next(w for w in works if w["item_type"] == "project")
    assert media_urls({**shot, "kind": "community_creator_work"}, "thumbs")
    assert media_urls({**proj, "kind": "community_creator_work"}, "thumbs") == [("thumb", proj["cover_url"])]
    full = media_urls({**proj, "kind": "community_creator_work"}, "full")
    assert all(".m3u8" not in u for _, u in full) and media_urls({**proj, "kind": "community_creator_work"},
                                                                 "none") == []


# ------------------------------------------------------------------ #3 Feed items: post media, project video, extra
def test_feed_post_items_keep_text_and_media():
    items = collect(Selection(feeds="feed"), ["community_feed.json"])["community_feed_item"]
    raw = {i["id"]: i for i in env("community_feed.json").body["items"]}
    post = next(i for i in items if i["item_type"] == "post")
    rp = raw[post["item_id"]]["post"]
    assert post["text"] == rp["content"]["text"]
    assert len(post["media"]) == len(rp["content"]["medias"])
    m, rm0 = post["media"][0], rp["content"]["medias"][0]
    assert m["job_id"] == rm0["job_id"] and m["url"] == rm0["job_result"]["url"]
    assert m["extra"]["min_result"]["url"] == rm0["min_result"]["url"] and m["extra"]["width"] == rm0["width"]
    assert post["extra"].get("post.dislike_count") == rp["dislike_count"]
    assert all(i["media"] == [] and i["text"] is None for i in items if i["item_type"] != "post")


def test_feed_project_card_video_fields_and_extra():
    items = collect(Selection(feeds="feed"), ["community_feed.json"])["community_feed_item"]
    raw = {i["id"]: i for i in env("community_feed.json").body["items"]}
    proj = next(i for i in items if i["item_type"] == "project_publication")
    v = raw[proj["item_id"]]["card"]["video"]
    assert (proj["video_url"], proj["video_hls_url"], proj["video_preview_url"], proj["width"], proj["height"],
            proj["duration_seconds"]) == (v["url"], v["hls_url"], v["preview_url"], v["width"], v["height"],
                                          v["duration"])
    tc = raw[proj["item_id"]].get("top_comment") or {}
    if tc.get("text"):
        assert proj["extra"]["top_comment.text"] == tc["text"]
    blob = json.dumps([i["extra"] for i in items])
    assert "<redacted>" not in blob and not (_keys([i["extra"] for i in items]) & VIEWER_KEYS)
    assert not any(k.endswith((".username", ".avatar_url", ".headline")) for i in items for k in i["extra"])


# ------------------------------------------------------------------ #4 post media card counters + thumbnails
def test_post_media_card_counters_and_thumbnails():
    posts = collect(Selection(feeds="posts"), ["community_posts_list.json"])["community_post"]
    raw = {p["id"]: p for p in env("community_posts_list.json").body["publications"]}
    p = posts[0]
    card = raw[p["post_id"]]["content"]["medias"][0]["card"]
    m = p["media"][0]
    assert (m["card_likes"], m["card_views"], m["card_comments"]) == (card["like_count"], card["views_count"],
                                                                       card["comment_count"])
    assert m["card_published_at"].startswith(card["published_at"][:19])
    e = env("community_posts_list.json")
    e.body = {"publications": [{"id": "p1", "user_id": "user_Fake001", "content": {"medias": [
        {"type": "job", "job_id": "j", "job_result": {"url": "https://x/a.mp4", "thumbnail_url": "https://x/a.webp"},
         "min_result": {"url": "https://x/a_min.mp4", "thumbnail_url": "https://x/a_min.webp"}}]}}]}
    m = parse_envelope(e, Selection(feeds="posts"))[0]["media"][0]
    assert (m["job_result_thumbnail_url"], m["min_result_thumbnail_url"]) == ("https://x/a.webp",
                                                                            "https://x/a_min.webp")
    assert m["extra"]["min_result"]["thumbnail_url"] == "https://x/a_min.webp"      # still kept as before


# ------------------------------------------------------------------ #14 shot model facets
def test_shot_model_facets_and_counts(tmp_path):
    sel = Selection(feeds="shots")
    ents = collect(sel, ["community_shots.json"])
    raw = env("community_shots.json").body["available_models"]
    facets = ents["community_shot_model_facet"]
    assert [(f["model"], f["media_type"]) for f in facets] == [(m["model"], m["media_type"]) for m in raw]
    ds = cds.build_dataset(ents, sel, rm())
    counts = {f["model"]: f["shots_in_run"] for f in ds["shot_model_facets"]}
    for s in ds["shots"]:
        if s["job_set_type"] in counts:
            assert counts[s["job_set_type"]] == sum(1 for x in ds["shots"] if x["job_set_type"] == s["job_set_type"])
    assert sum(counts.values()) <= len(ds["shots"])
    cds.write_outputs(ds, tmp_path)
    with (tmp_path / "csv" / "shot_model_facets.csv").open(encoding="utf-8-sig", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(raw)


# ------------------------------------------------------------------ #10 creator_uid_key
def test_creator_uid_key_on_every_record_with_an_author():
    assert creator_uid_key("user_REDACTED1") is None and creator_uid_key(None) is None
    sel = Selection(feeds="shots,posts,feed,creators,talents")
    ents = collect(sel, ["community_shots.json", "community_posts_list.json", "community_feed.json",
                         "community_talents_works.json", "community_entity_comments.json"])
    for kind, uid in (("community_shot", lambda x: x["author"]["user_id"]),
                      ("community_post", lambda x: x["author"]["user_id"]),
                      ("community_feed_item", lambda x: x["author"]["user_id"]),
                      ("community_creator_stats", lambda x: x["user_id"]),
                      ("community_creator_work", lambda x: x["creator_user_id"]),
                      ("community_comment", lambda x: x["user_id"])):
        assert ents[kind], kind
        assert all(x["creator_uid_key"] == creator_uid_key(uid(x)) for x in ents[kind]), kind
    fake = [x for x in ents["community_creator_stats"] if x["user_id"].startswith("user_Fake")]
    assert fake and all(x["creator_uid_key"] for x in fake)
    gen = parse_generation({"id": "j", "user_id": "user_Fake001", "params": {}}, "trending", Selection(), {})
    assert gen["creator_uid_key"] == creator_uid_key("user_Fake001") and gen["creator"]["user_id"] == "user_Fake001"


# ------------------------------------------------------------------ CONTENT_MAP gap: --feeds feed-categories
def test_feed_categories_is_opt_in_and_never_in_all():
    assert "feed-categories" not in Selection(feeds="all").extra_feeds + Selection(feeds="all").feeds
    sel = Selection(feeds="feed_categories")
    assert sel.feeds == [] and sel.extra_feeds == ["feed-categories"] and default_label(sel) == "feed-categories"
    assert selection_from_dict(sel.to_dict()) == sel
    assert Selection(feeds="all,feed-categories").feeds == ["trending", "approved", "top", "model-x"]
    sp = CommunitySpider(selection=Selection(feeds="feed-categories"), common=CommonOptions(auth="required"))
    reqs = list(sp.build_requests())
    assert [(r.meta["endpoint"], r.url) for r in reqs] == [
        ("community_feed_categories", "https://fnf-api-gw.higgsfield.ai/fnf-community/feed/categories"),
        ("community_feed_ongoing", "https://fnf-api-gw.higgsfield.ai/fnf-community/feed/ongoing")]
    assert all(r.meta["auth"] is False and r.method == "GET" for r in reqs)
    assert list(sp.follow_up(env("community_feed_categories.json"), [], None)) == []      # single response


def test_feed_categories_parse_dataset_and_csv(tmp_path):
    sel = Selection(feeds="feed-categories")
    ents = collect(sel, ["community_feed_categories.json"])
    cats = ents["community_feed_category"]
    raw = env("community_feed_categories.json").body["categories"]
    assert [c["slug"] for c in cats] == [r["slug"] for r in raw]
    assert [c["post_count"] for c in cats] == [r["post_count"] for r in raw]
    assert cats[0]["hashtag"] == raw[0].get("hashtag") and cats[0]["previews"] == raw[0]["previews"]
    assert all(c["source_list"] == "categories" for c in cats)
    e = env("community_feed_categories.json")
    e.endpoint, e.body = "community_feed_ongoing", {"items": []}
    assert parse_envelope(e, sel) == []
    assert media_urls({**cats[0], "kind": "community_feed_category"}, "thumbs")
    ds = cds.build_dataset(ents, sel, rm())
    CommunityDatasetExt.model_validate(ds)
    assert ds["meta"]["counts"]["feed_categories"] == len(raw)
    assert "feed-categories" in ds["meta"]["endpoints"] and "feed-ongoing" in ds["meta"]["endpoints"]
    cds.write_outputs(ds, tmp_path)
    with (tmp_path / "csv" / "feed_categories.csv").open(encoding="utf-8-sig", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(raw)


def test_new_kinds_registered():
    for kind, idf in (("community_creator_work", "work_id"), ("community_shot_model_facet", "facet_id"),
                      ("community_feed_category", "category_id")):
        assert kind in SCRAPER.model_by_kind and SCRAPER.id_field_by_kind[kind] == idf
