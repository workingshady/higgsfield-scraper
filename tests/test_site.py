"""site scraper: page extraction, parsers per page type, options, spider discovery + limits, dataset + complete CSVs."""
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
from higgsfield_scraper.scrapers.site import SCRAPER, media_urls
from higgsfield_scraper.scrapers.site.dataset import build_dataset, merge_by_slug, write_outputs
from higgsfield_scraper.scrapers.site.extract import extract_page, main_html, resolve_suspense
from higgsfield_scraper.scrapers.site.hast import to_html
from higgsfield_scraper.scrapers.site.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.site.parsers import is_landing_path, keep, parse_envelope
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "site"


def env(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def by_prefix(prefix: str) -> Envelope:
    return env(next(p.name for p in sorted(FIX.glob(prefix + "*"))))


def parse(prefix: str, sel: Selection | None = None) -> list[dict]:
    out = parse_envelope(by_prefix(prefix), sel or Selection())
    for e in out:
        validate_entity(e)
    return out


def kinds(ents: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in ents:
        out[e["kind"]] = out.get(e["kind"], 0) + 1
    return out


def _spider(sel=None, **common):
    from higgsfield_scraper.scrapers.site.spider import SiteSpider
    return SiteSpider(selection=sel or Selection(), common=CommonOptions(auth="off", **common))


# ------------------------------------------------------------------ registry / options

def test_registered_kinds_prefixed_and_in_cli():
    assert "site" in registry.available() and registry.get("site") is SCRAPER
    assert all(k.startswith("site_") for k in SCRAPER.model_by_kind)
    assert set(SCRAPER.id_field_by_kind) == set(SCRAPER.model_by_kind)
    assert SCRAPER.personal_data and SCRAPER.examples
    from higgsfield_scraper.cli import build_parser
    a = build_parser().parse_args(["scrape", "site", "--what", "apps,academy", "--no-content", "--max-items", "5"])
    s = SCRAPER.make_selection(a)
    assert s.what == ["apps", "academy"] and s.with_content is False and a.max_items == 5


def test_selection_defaults_aliases_and_roundtrip():
    s = Selection()
    assert "rooms" not in s.what and "landings" in s.what and s.with_content and not s.with_profiles
    s2 = Selection(what="all,room", only="Kling, /plugins/", with_profiles="true", with_content="false")
    assert "rooms" in s2.what and "apps" in s2.what and s2.only == ["kling", "/plugins/"]
    assert s2.with_profiles is True and s2.with_content is False
    assert selection_from_dict(s2.to_dict()) == s2
    assert s2.path_ok("/kling-3.0") and not s2.path_ok("/ai-image")
    with pytest.raises(ValueError):
        Selection(what="effects")


def test_menu_offers_site_options():
    from higgsfield_scraper.interactive import options as opt
    qs = {q.dest: q for q in opt.questions_for("site")}
    assert qs["with_content"].kind == "confirm" and qs["with_profiles"].kind == "confirm"
    assert qs["what"].kind == "text" and "max_items" in qs
    assert opt.build_argv("site", {"what": "apps"}) == ["scrape", "site", "--what", "apps"]


# ------------------------------------------------------------------ extraction

HTML = """<!DOCTYPE html><html lang="en"><head><title>T | Higgsfield</title>
<meta name="description" content="Desc"/><meta name="keywords" content="a, b"/>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
{"@type":"Question","name":"Is it free?","acceptedAnswer":{"@type":"Answer","text":"Yes, to start."}}]}</script>
<script type="application/ld+json">{"@type":"SoftwareApplication","name":"X Gen","applicationCategory":"MultimediaApplication",
"offers":{"@type":"Offer","price":"0","priceCurrency":"USD"}}</script></head>
<body><main class="a b"><h1 class="big">Make <b>things</b></h1><p style="x">Intro text.</p>
<template id="B:0"></template><h2>Explore more AI features</h2><p>nav</p><footer>foot</footer></main>
<div hidden id="S:0"><section><h2>Streamed section</h2><div><p>Late <a href="/ai-image" class="z">link</a></p></div></section></div>
<script>$_TSR.router=($R=>$R[0]={manifest:$R[1]={},matches:$R[2]=[$R[3]={i:"__root__#",l:$R[4]={x:1}},
$R[5]={i:"#ai-x#ai-x",s:"success",ssr:!0}],dehydratedData:$R[6]={}})($R["tsr"])</script></body></html>"""


def test_resolve_suspense_and_main_html():
    assert "Streamed section" in resolve_suspense(HTML)
    m = main_html(HTML)
    assert "Streamed section" in m and "class=" not in m and "style=" not in m and "foot" not in m
    assert '<a href="/ai-image">' in m


def test_landing_from_saved_html():
    e = Envelope(endpoint="landing_page", url="https://higgsfield.ai/ai-x", status=200, params={"path": "/ai-x"},
                 body={"html": HTML, "path": "/ai-x", "page_type": "landing"}, fetched_at=datetime.now(timezone.utc))
    [x] = parse_envelope(e, Selection())
    validate_entity(x)
    assert x["h1"] == "Make things" and x["sections"] == ["Streamed section"] and x["page_type"] == "landing"
    assert x["faq"][0]["question"] == "Is it free?" and x["offer_price"] == "0" and x["offer_currency"] == "USD"
    assert x["app_name"] == "X Gen" and x["seo"]["keywords"] == "a, b"
    assert "Intro text." in x["content_markdown"] and "Explore more" not in x["content_markdown"]
    assert "nav" not in x["content_text"]
    body = extract_page(HTML, "/ai-x", None, "landing")
    assert body["matches"] == [] and body["main_html"]


def test_hast_to_html():
    tree = {"type": "root", "children": [
        {"type": "element", "tagName": "h2", "properties": {"id": "a"}, "children": [{"type": "text", "value": "Hi & <you>"}]},
        {"type": "element", "tagName": "img", "properties": {"src": "https://x/y.png", "alt": "pic"}, "children": []},
        {"type": "mdxJsxFlowElement", "name": "Video", "attributes": [{"name": "src", "value": "https://x/v.mp4"}],
         "children": [{"type": "text", "value": "cap"}]}]}
    h = to_html(tree)
    assert '<h2 id="a">Hi &amp; &lt;you&gt;</h2>' in h and '<img src="https://x/y.png" alt="pic"/>' in h
    assert '<video src="https://x/v.mp4"></video>cap' in h


def test_is_landing_path():
    assert is_landing_path("/ai-image") and is_landing_path("/plugins/blender") and is_landing_path("/")
    assert is_landing_path("/seedance/2.5") and is_landing_path("/academy-webinar-290926") is True
    for p in ("/pricing", "/pricing.md", "/mcp", "/mcp/x", "/community/rooms/x", "/es", "/ja/blog", "/apps", "/blog"):
        assert not is_landing_path(p), p


# ------------------------------------------------------------------ parsers on captured pages

def test_apps_index_and_app_page():
    ents = parse("apps_index")
    k = kinds(ents)
    assert k["site_app_category"] >= 5 and k["site_app"] >= 50
    card = next(e for e in ents if e["kind"] == "site_app")
    assert card["record_source"] == "index" and card["record_key"].endswith("@index") and card["category_slugs"]
    [app] = parse("app_page__path-_apps_face-swap")
    assert app["record_source"] == "page" and app["slug"] == "face-swap"
    assert {(t["role"], t["preset"]) for t in app["templates"]} == {("image", "primary"), ("video", "secondary")}
    assert app["min_cost_credits"] == "2" and app["max_cost_credits"] == "25"
    assert app["author_name"] is None                                 # personal data is opt-in


def test_academy_index_course_and_lesson():
    k = kinds(parse("academy_index"))
    assert k["site_academy_category"] >= 2 and k["site_academy_course"] >= 10
    [c] = parse("course_page")
    assert c["lessons"] and c["objectives"] and c["lessons"][0]["url"].startswith(c["url"] + "/")
    [les] = parse("lesson_page")
    assert les["content_format"] == "hast" and les["word_count"] > 100 and les["content_markdown"].count("## ") >= 2
    assert les["course_slug"] and les["video_url"] and les["url"].endswith("/" + les["slug"])
    [nocontent] = parse("lesson_page", Selection(with_content=False))
    assert nocontent.get("content_markdown") is None and nocontent["title"] == les["title"]


def test_mcp_index_and_skill_page():
    k = kinds(ents := parse("mcp_index"))
    assert k["site_mcp_skill"] >= 5 and k["site_mcp_bundle"] >= 1
    sk = next(e for e in ents if e["kind"] == "site_mcp_skill")
    assert sk["agents"] and sk["skill_label"] and sk["record_key"] == sk["slug"] + "@index"
    [page] = parse("mcp_skill_page")
    assert page["record_source"] == "page" and page["overview_description"]


def test_originals_index_and_episode():
    series = parse("originals_index")
    assert len(series) >= 20 and all(s["kind"] == "site_original_series" for s in series)
    assert any(s["in_hero"] for s in series) and all(s["cast"] == [] for s in series)
    [ep] = parse("episode_page")
    assert ep["series_slug"] and ep["views"] is not None and ep["episodes"] and ep["uploader"] is None


def test_mixed_media_preset_redacts_creators():
    [p] = parse("mixed_media_page")
    assert p["name"] and p["sample_count"] == len(p["samples"]) > 0
    assert all(s["creator"] is None for s in p["samples"])
    e = by_prefix("mixed_media_page")
    item = next(m for m in e.body["matches"] if "preset" in m["l"])["l"]["initialItems"][0]
    item["profile"] = {"username": "someone"}
    [p2] = parse_envelope(e, Selection(with_profiles=True))
    assert p2["samples"][0]["creator"] == "someone"


def test_landing_and_room_pages():
    lands = [x for p in sorted(FIX.glob("landing_page*")) for x in parse_envelope(Envelope.load(p), Selection())]
    assert lands and all(x["kind"] == "site_landing" for x in lands)
    assert any(x["faq"] for x in lands) and any(x["content_markdown"] for x in lands)
    [room] = parse("room_page")
    assert room["page_type"] == "room" and room.get("content_markdown") is None and room["seo"]["page_title"]


def test_promo_apis():
    ev = parse("datetime_settings")
    assert len(ev) >= 5 and all(e["event_id"] for e in ev)
    assert any(e["params"] for e in ev) and all(None not in e["params"].values() for e in ev)
    offers = parse("business_unlim")
    assert {o["section"] for o in offers} == {"plan_card", "pricing_banner"}
    gifts = parse("game_gift")
    assert gifts and {g["network"] for g in gifts} >= {"playstation"} and len({g["gift_id"] for g in gifts}) == len(gifts)


def test_sitemaps_are_discovery_only():
    for p in FIX.glob("*_sitemap*"):
        assert parse_envelope(Envelope.load(p), Selection()) == []


def test_keep_only_filter():
    ents = parse("apps_index")
    sel = Selection(only="/apps/face-swap")
    kept = [e for e in ents if keep(e, sel)]
    assert {e["kind"] for e in kept} == {"site_app", "site_app_category"}
    assert all(e["slug"] == "face-swap" for e in kept if e["kind"] == "site_app")


def test_media_urls_modes():
    [app] = parse("app_page__path-_apps_face-swap")
    thumbs = media_urls(app, "thumbs")
    full = media_urls(app, "full")
    assert thumbs and all(not r.endswith(("media", "input_media")) for r, _ in thumbs)
    assert len(full) > len(thumbs)
    [ep] = parse("episode_page")
    assert not any(u.endswith(".m3u8") for _, u in media_urls(ep, "all"))


# ------------------------------------------------------------------ spider

def test_spider_first_requests():
    urls = [r.url for r in _spider().build_requests()]
    assert "https://higgsfield.ai/apps" in urls and "https://higgsfield.ai/academy/courses" in urls
    assert "https://higgsfield.ai/mcp" in urls and "https://higgsfield.ai/sitemap-marketing.xml" in urls
    assert any(u.endswith("/datetime-settings") for u in urls)
    urls2 = [r.url for r in _spider(Selection(what="originals", with_content=False)).build_requests()]
    assert urls2 == ["https://higgsfield.ai/original-series"]


def test_spider_discovery_and_max_items():
    sp = _spider(Selection(what="apps,academy,mcp,landings,rooms"), max_items=3)
    list(sp.build_requests())
    apps = list(sp.follow_up(by_prefix("apps_index"), [], None))
    eps = [r.meta["endpoint"] for r in apps]
    assert eps.count("app_page") == 3 and "apps_sitemap" in eps
    assert any("max_items=3" in x for x in sp.limits_hit)
    sm = list(sp.follow_up(by_prefix("apps_sitemap"), [], None))
    assert not sm                                                     # budget spent, categories skipped
    course = list(sp.follow_up(by_prefix("course_page"), [], None))
    assert len(course) == 3 and all(r.meta["page_type"] == "lesson" for r in course)
    mk = list(sp.follow_up(by_prefix("marketing_sitemap"), [], None))
    by = {}
    for r in mk:
        by.setdefault(r.meta["endpoint"], []).append(r.meta["path"])
    assert len(by["landing_page"]) == 3 and len(by["room_page"]) == 3
    assert not any(p.startswith(("/mcp", "/pricing")) for p in by["landing_page"])
    assert sp.totals["landing_urls"] > 100 and sp.totals["room_urls"] > 10


def test_spider_no_content_and_only():
    sp = _spider(Selection(what="apps,mcp", with_content=False))
    list(sp.build_requests())
    assert list(sp.follow_up(by_prefix("apps_index"), [], None)) == []
    assert list(sp.follow_up(by_prefix("mcp_index"), [], None)) == []
    sp2 = _spider(Selection(what="apps", only="/apps/face-swap"))
    list(sp2.build_requests())
    reqs = list(sp2.follow_up(by_prefix("apps_index"), [], None))
    assert [r.meta["path"] for r in reqs if r.meta["endpoint"] == "app_page"] == ["/apps/face-swap"]


# ------------------------------------------------------------------ dataset + outputs

def _all_entities(sel):
    ents: dict[str, list[dict]] = {}
    for p in sorted(FIX.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                ents.setdefault(v["kind"], []).append(v)
    return ents


def _csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return set(rows[0].keys()) if rows else set(), rows


def test_merge_by_slug():
    page = {"slug": "a", "record_key": "a@page", "record_source": "page", "name": "A", "tags": [], "category_slugs": ["x"],
            "extra": {"p": 1}, "upload_date": None}
    idx = {"slug": "a", "record_key": "a@index", "record_source": "index", "name": "old", "tags": ["PRO"],
           "category_slugs": ["y"], "extra": {"i": 2}, "upload_date": "2025-01-01T00:00:00+00:00"}
    [m] = merge_by_slug([idx, page])
    assert m["name"] == "A" and m["tags"] == ["PRO"] and m["category_slugs"] == ["x", "y"]
    assert m["upload_date"] and m["record_key"] == "a@page" and m["extra"] == {"i": 2, "p": 1}


def test_build_dataset_and_outputs(tmp_path):
    sel = Selection()
    ds = build_dataset(_all_entities(sel), sel, RunMeta(run_id="t", label="t", totals={"landing_urls": 165}))
    assert ds["meta"]["scraper"] == "site" and ds["meta"]["totals_available"]["landing_urls"] == 165
    for c in ("apps", "app_categories", "courses", "lessons", "mcp_skills", "mcp_bundles", "original_series",
              "original_episodes", "mixed_media_presets", "landings", "promo_events", "business_unlim_offers",
              "game_gifts"):
        assert ds[c], c
    slugs = [a["slug"] for a in ds["apps"]]
    assert len(slugs) == len(set(slugs))                                # index + page merged
    mug = next(a for a in ds["apps"] if a["slug"] == "face-swap")
    assert mug["record_source"] == "page" and mug["category_slugs"] and mug["templates"]
    assert any(s["bundle_slugs"] for s in ds["mcp_skills"])
    files = write_outputs(ds, tmp_path)
    assert (tmp_path / "dataset.json").exists() and (tmp_path / "summary.md").exists()
    assert list((tmp_path / "articles" / "lessons").glob("*.md")) and list((tmp_path / "articles" / "landings").glob("*.md"))
    assert "| face-swap |" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "json" / "apps.json").read_text(encoding="utf-8")) == ds["apps"]
    assert (tmp_path / "dataset.json").read_text(encoding="utf-8").startswith('{\n    "schema_version"')   # indent 4
    assert len(files) > 30


def test_csvs_contain_every_json_field(tmp_path):
    """Nothing may exist only in JSON: every leaf of every object is a column of some CSV, rows 1:1."""
    from higgsfield_scraper.scrapers.site.dataset import CHILDREN, COLLECTIONS, JOIN_LISTS
    sel = Selection()
    ds = build_dataset(_all_entities(sel), sel, RunMeta(run_id="t"))
    write_outputs(ds, tmp_path)
    for coll in COLLECTIONS:
        prefix, idf, kids = CHILDREN.get(coll, ("", None, []))
        objs = [{k: v for k, v in x.items() if k not in kids and k not in JOIN_LISTS} for x in ds[coll]]
        cols, rows = _csv(tmp_path / "csv" / f"{coll}.csv")
        assert len(rows) == len(objs), coll
        missing = {k for o in objs for k in flatten(o) if k not in cols and not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{coll}: {sorted(missing)[:10]}"
        assert all(k in cols for o in ds[coll] for k in JOIN_LISTS if k in o), coll
        for child in kids:
            items = [c for x in ds[coll] for c in (x.get(child) or [])]
            ccols, crows = _csv(tmp_path / "csv" / f"{prefix}_{child}.csv")
            assert len(crows) == len(items), f"{prefix}_{child}"
            miss = {k for o in items for k in flatten(o if isinstance(o, dict) else {"value": o})
                    if k not in ccols and not any(c.startswith(k + ".") for c in ccols)}
            assert not miss, f"{prefix}_{child}: {sorted(miss)[:10]}"
