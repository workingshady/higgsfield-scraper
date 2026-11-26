"""Opt-in gallery / template sources of the community scraper (docs/COMMUNITY_COVERAGE.md §3b):
--feeds music-cards | job-showcase | collections | explore-cards. Offline, on trimmed + redacted fixtures.
Also proves the defaults (and --feeds all) never request them."""
from __future__ import annotations

import csv
import dataclasses
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.community import media_urls
from higgsfield_scraper.scrapers.community import dataset as cds
from higgsfield_scraper.scrapers.community.endpoints import GALLERY_FEEDS
from higgsfield_scraper.scrapers.community.options import Selection, default_label, selection_from_dict
from higgsfield_scraper.scrapers.community.parsers import keep, parse_envelope
from higgsfield_scraper.scrapers.community.schemas import CommunityDatasetExt, CommunityDatasetGallery
from higgsfield_scraper.scrapers.community.spider import CommunitySpider
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "community"
GALLERY_FX = ["community_music_cards.json", "community_music_card_styles.json", "community_music_card_occasions.json",
              "community_music_card_roles.json", "community_job_showcase.json", "community_collection.json",
              "community_explore_cards.json"]
ALL_GALLERY = ",".join(GALLERY_FEEDS)


class _Resp:
    pass


def env(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def rm() -> RunMeta:
    return RunMeta(run_id="t", label="t", scraped_at=datetime(2026, 11, 26, tzinfo=timezone.utc),
                   common=CommonOptions(max_items=100))


def collect(sel, names=GALLERY_FX) -> dict[str, list[dict]]:
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


# ------------------------------------------------------------------ defaults stay unchanged
def test_defaults_and_all_never_include_gallery_feeds():
    assert Selection().extra_feeds == [] and Selection(feeds="all").extra_feeds == []
    for sel in (Selection(), Selection(feeds="all"), Selection(feeds="all", with_comments=True),
                Selection(feeds="shots,posts,feed,creators,talents", with_comments=True)):
        sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off", max_items=5))
        eps = {r.meta["endpoint"] for r in sp.build_requests()}
        assert not eps & {"community_music_cards", "community_music_card_options", "community_job_showcase",
                          "community_collection", "community_explore_cards"}


def test_old_opt_in_runs_keep_their_dataset_model():
    from test_community_pages import EXTRA_FX, collect as collect_pages
    sel = Selection(feeds="shots,posts")
    ds = cds.build_dataset(collect_pages(sel, EXTRA_FX), sel, rm())
    assert "music_cards" not in ds and "gallery_stats" not in ds
    assert set(ds) == set(CommunityDatasetExt.model_fields)


# ------------------------------------------------------------------ options
def test_options_roundtrip_aliases_and_label():
    sel = Selection(feeds="music_cards,job-showcase,collection,explore_cards")
    assert sel.feeds == [] and sel.extra_feeds == list(GALLERY_FEEDS)
    assert selection_from_dict(sel.to_dict()) == sel
    assert default_label(sel) == "music-cards-job-showcase-collections-explore-cards"
    assert Selection(feeds="all,music-cards").feeds == ["trending", "approved", "top", "model-x"]
    with pytest.raises(ValueError):
        Selection(feeds="viral-effects")


# ------------------------------------------------------------------ parsers
def test_music_cards_and_options():
    ents = collect(Selection(feeds="music-cards"))
    cards = ents["community_music_card"]
    raw = env("community_music_cards.json").body
    assert [c["music_card_id"] for c in cards] == [i["id"] for i in raw["items"]]
    c = cards[0]
    assert c["lyrics"] and c["song_title"] and c["recipients"] and c["recipients"][0]["facts_wishes"]
    assert c["preview_video_url"].endswith(".mp4") and c["preview_video_compressed_bytes"] > 0
    assert c["length_seconds"] == raw["items"][0]["length"] and c["position"] == 0
    opts = ents["community_music_card_option"]
    groups = {o["group"] for o in opts}
    assert groups == {"category", "style", "occasion", "role"}
    assert len({o["option_id"] for o in opts}) == len(opts)
    occ = next(o for o in opts if o["group"] == "occasion")
    assert occ["categories"] and occ["thumbnail_url"]
    # music cards are templates, not generations: no merge markers at the top level
    mg = _merge_module()
    assert all(mg.record_keys("community", "music_cards", c) == [] for c in cards)


def _merge_module():
    path = Path(__file__).parents[1] / "scripts" / "merge_generations.py"
    spec = importlib.util.spec_from_file_location("merge_generations", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_showcase_jobs_are_generation_like_with_merge_keys_and_privacy():
    jobs = collect(Selection(feeds="job-showcase"))["community_showcase_job"]
    raw = env("community_job_showcase.json").body["data"]
    assert len(jobs) == sum(len(m["jobs"]) for m in raw)
    j = jobs[0]
    assert j["prompt"] and j["job_set_type"] == "seedance_2_0" and j["media_type"] == "video"
    raw_res = env("community_job_showcase.json").body["data"][0]["jobs"][0]["results"]
    assert {r["name"] for r in j["results"]} == {k for k, v in raw_res.items() if v}   # every non-null variant
    assert {"raw", "min"} <= {r["name"] for r in j["results"]} and all(r["thumbnail_url"] for r in j["results"])
    assert j["inputs"] and all(i["url"] for i in j["inputs"])                       # assets (input images)
    assert j["settings"]["resolution"] and j["settings"]["duration"]
    assert j["generation_key"] == f"job:{j['generation_id']}" and j["media_keys"][0].startswith("media:")
    assert (j["movie_index"], j["movie_position"]) == (0, 0) and j["movie_logo_url"]
    assert j["creator"]["user_id"].startswith("user_REDACTED")
    assert all(x["creator"][k] is None for x in jobs for k in ("username", "full_name", "avatar_url"))
    assert collect(Selection(feeds="job-showcase", with_profiles=True))["community_showcase_job"][0][
        "creator"]["username"] == "<redacted>"
    assert j["raw_params"] is None
    assert collect(Selection(feeds="job-showcase", with_raw_params=True))["community_showcase_job"][0]["raw_params"]
    keys = _merge_module().record_keys("community", "showcase_jobs", j)
    assert keys[0] == j["generation_key"] and j["media_keys"][0] in keys


def test_collection_and_explore_cards():
    col = collect(Selection(feeds="collections"))["community_collection"]
    assert len(col) == 1 and col[0]["slug"] == "catch-the-pulse" and col[0]["collection_id"] == "catch-the-pulse"
    assert col[0]["items_count"] == len(col[0]["items"]) == 3
    assert col[0]["items"][0]["motion_id"] and col[0]["items"][0]["params"]
    cards = collect(Selection(feeds="explore-cards"))["community_explore_card"]
    assert [c["position"] for c in cards] == [0, 1, 2] and all(c["href"] for c in cards)
    assert all(c["has_placeholder"] for c in cards)
    assert not any("placeholder" in k for c in cards for k in c["extra"])          # inline data URI not stored


# ------------------------------------------------------------------ spider
def test_requests_are_anonymous_and_capped():
    for auth in ("off", "auto", "required"):
        sp = CommunitySpider(selection=Selection(feeds=ALL_GALLERY), common=CommonOptions(auth=auth, max_items=7))
        reqs = list(sp.build_requests())
        assert [r.url for r in reqs] == [
            "https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-presets?lang=en",
            "https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-styles?lang=en",
            "https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-occasions?lang=en",
            "https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-roles?lang=en",
            "https://higgsfield.ai/seedance-2-community",
            "https://fnf-api-gw.higgsfield.ai/fnf/collections/catch-the-pulse",
            "https://cms.higgsfield.ai/cards?size=7"]
        assert all(r.meta["auth"] is False and "Authorization" not in r.headers for r in reqs)
        assert all(r.method == "GET" for r in reqs)


def test_explore_cards_pagination_and_stop():
    sel = Selection(feeds="explore-cards")
    sp = CommunitySpider(selection=sel, common=CommonOptions(auth="off"))
    first = list(sp.build_requests())
    assert first[0].url == "https://cms.higgsfield.ai/cards?size=100"
    e = env("community_explore_cards.json")
    ents = parse_envelope(e, sel)
    nxt = list(sp.follow_up(e, ents, _Resp()))
    assert len(nxt) == 1 and nxt[0].url.endswith("cards?size=100&cursor=2")
    assert nxt[0].meta["params"]["offset"] == str(len(ents)) and sp.totals["explore-cards"] == e.body["total"]
    last = dataclasses.replace(e, body={**e.body, "cursor": None})
    assert list(sp.follow_up(last, ents, _Resp())) == []
    assert sp.stop_reasons["explore-cards"] == "no next cursor"
    capped = CommunitySpider(selection=sel, common=CommonOptions(auth="off", max_items=3))
    list(capped.build_requests())
    capped._extra_kept["explore-cards"] = 3
    assert list(capped.follow_up(e, ents, _Resp())) == [] and capped.stop_reasons["explore-cards"] ==         "max_items reached"
    sp = CommunitySpider(selection=Selection(feeds="job-showcase"), common=CommonOptions(auth="off"))
    e = env("community_job_showcase.json")
    assert list(sp.follow_up(e, parse_envelope(e, sel), _Resp())) == []          # single response


def test_media_urls():
    ents = collect(Selection(feeds=ALL_GALLERY))
    job = {**ents["community_showcase_job"][0], "kind": "community_showcase_job"}
    assert [r for r, _ in media_urls(job, "thumbs")] == ["thumb"]
    full = media_urls(job, "full")
    assert {r for r, _ in full} == {"thumb", "raw"} and not any(".m3u8" in u for _, u in full)   # h264/hls null
    assert any(r.startswith("input") for r, _ in media_urls(job, "all"))
    card = {**ents["community_music_card"][0], "kind": "community_music_card"}
    assert {r for r, _ in media_urls(card, "full")} == {"thumb", "poster", "video"}
    col = {**ents["community_collection"][0], "kind": "community_collection"}
    assert len(media_urls(col, "thumbs")) == 3
    assert media_urls(job, "none") == []


# ------------------------------------------------------------------ dataset + complete CSVs
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


def test_gallery_dataset_and_complete_csvs(tmp_path):
    sel = Selection(feeds=ALL_GALLERY)
    ds = cds.build_dataset(collect(sel), sel, rm())
    CommunityDatasetGallery.model_validate(ds)
    c = ds["meta"]["counts"]
    assert c["music_cards"] == 3 and c["music_card_options"] == 13 and c["showcase_jobs"] == 4
    assert c["collections"] == 1 and c["explore_cards"] == 3
    assert ds["gallery_stats"]["collection_items"] == 3
    assert [(j["movie_index"], j["movie_position"]) for j in ds["showcase_jobs"]] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    eps = ds["meta"]["endpoints"]
    assert eps["job-showcase"].startswith("https://higgsfield.ai/seedance-2-community") and "music-cards-options" in eps
    cds.write_outputs(ds, tmp_path)
    csvd = tmp_path / "csv"
    _assert_complete(ds["music_cards"], csvd / "music_cards.csv", drop=("recipients",))
    _assert_complete([r for x in ds["music_cards"] for r in x["recipients"]], csvd / "music_card_recipients.csv")
    _assert_complete(ds["music_card_options"], csvd / "music_card_options.csv")
    _assert_complete(ds["showcase_jobs"], csvd / "showcase_jobs.csv", drop=("inputs", "results"))
    _assert_complete([i for j in ds["showcase_jobs"] for i in j["inputs"]], csvd / "showcase_job_inputs.csv")
    _assert_complete([r for j in ds["showcase_jobs"] for r in j["results"]], csvd / "showcase_job_results.csv")
    _assert_complete(ds["collections"], csvd / "collections.csv", drop=("items",))
    _assert_complete([i for x in ds["collections"] for i in x["items"]], csvd / "collection_items.csv")
    _assert_complete(ds["explore_cards"], csvd / "explore_cards.csv")
    assert "Opt-in galleries and templates" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    schema = json.loads((tmp_path / "schema" / "dataset.schema.json").read_text(encoding="utf-8"))
    assert {"music_cards", "showcase_jobs", "collections", "explore_cards"} <= set(schema["properties"])
    out = json.loads((tmp_path / "dataset.json").read_text(encoding="utf-8"))
    assert out["meta"]["scraped_at"] and out["schema_version"] and all(
        x["source"]["url"] for k in ("music_cards", "showcase_jobs", "collections", "explore_cards") for x in out[k])


def test_job_showcase_is_read_from_the_public_page_ssr_state():
    """The showcase JSON is server-rendered into the page's TanStack state (loaderData.seedanceMovies); the spider
    extracts it and hands {data: [...]} to the normal JSON path. A page without the key stays non-JSON."""
    from scrapy.http import HtmlResponse, Request
    movies = env("community_job_showcase.json").body["data"]
    state = json.dumps({"matches": [{"i": "__root__", "l": {}},
                                    {"i": "/(public)/(explore)/seedance-2-community",
                                     "l": {"seedanceMovies": movies, "publications": {"items": []}}}]})
    state = state.replace(": true", ": !0").replace(": false", ": !1")      # seroval booleans, as in real pages
    html = f"<html><script>$_TSR.router=($R=>$R[0]={state})($R)</script></html>"
    sp = CommunitySpider(selection=Selection(feeds="job-showcase"), common=CommonOptions(auth="off"))
    req = list(sp.build_requests())[0]
    assert req.headers.get("Accept", b"").startswith(b"text/html") and req.callback == sp.parse_ssr
    got = {}

    def fake_parse_api(response, **kw):
        got["text"] = response.text
        yield from ()

    sp.parse_api = fake_parse_api
    list(sp.parse_ssr(HtmlResponse(url=req.url, body=html.encode(), encoding="utf-8", request=req, status=200)))
    body = json.loads(got["text"])
    assert body["data"] == movies and body["ssr_route"].endswith("seedance-2-community")
    list(sp.parse_ssr(HtmlResponse(url=req.url, body=b"<html>no state</html>", request=req, status=200)))
    assert got["text"] == "<html>no state</html>"              # passed on untouched
