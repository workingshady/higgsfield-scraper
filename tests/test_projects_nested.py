"""projects scraper, nested project data (opt-in): --with-project-assets/-brief/-stats/-comments/-related,
--contest <slug>, --users <handle>.

Fixtures (tests/fixtures/projects_nested/*.json) are real API responses of 2026-11-26 ("The Sea Walks Out" and the
talent contest), trimmed, with Clerk user ids replaced by fake ids of the same length (also inside the binary brief
snapshot) and the handle / name replaced. Usernames and avatars were already blanked by the run's privacy redaction.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pytest
from scrapy.http import Request, Response, TextResponse

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.projects import SCRAPER
from higgsfield_scraper.scrapers.projects import endpoints as ep
from higgsfield_scraper.scrapers.projects.brief import brief_markdown
from higgsfield_scraper.scrapers.projects.dataset import media_urls
from higgsfield_scraper.scrapers.projects.nested import _largest_remainder_tenths
from higgsfield_scraper.scrapers.projects.options import Selection, selection_from_dict, user_key
from higgsfield_scraper.scrapers.projects.parsers import keep, parse_envelope
from higgsfield_scraper.scrapers.projects.yjs import YjsDecodeError, decode_doc
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "projects_nested"
PID = "d62acd40-d4da-40d5-9aeb-f09374bb362e"
ROOT = "96cfeed5-3ebb-4013-9de2-1ec377fca7b6"
ALL = dict(with_project_assets=True, with_project_brief=True, with_project_stats=True, with_project_comments=True,
           with_project_related=True)


def load(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def kinds(ents):
    out = defaultdict(list)
    for e in ents:
        out[e["kind"]].append(e)
    return out


def all_entities(sel: Selection) -> dict[str, list[dict]]:
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


# ------------------------------------------------------------------ options: opt-in, defaults unchanged
def test_default_selection_dict_is_unchanged():
    d = Selection.build().to_dict()
    assert set(d) == {"what", "categories", "featured", "scopes", "with_details", "with_submissions",
                      "contest_status", "contest_types", "entry_keys", "entry_tab", "submission_ordering",
                      "max_submissions", "with_profiles"}
    assert not Selection.build().nested


def test_nested_options_roundtrip_and_privacy_of_handles():
    sel = Selection.build(what="contests", contests="talent-contest,wcc-the-place-you-know", contest_tabs="all",
                          users="@creator_one", **ALL)
    assert sel.nested and sel.users == ("creator_one",) and "user-projects" in sel.what
    assert sel.contest_tabs == ep.CONTEST_TABS and sel.tabs_for_contest == ep.CONTEST_TABS
    d = sel.to_dict()
    assert d["users"] == [f"key:{user_key('creator_one')}"] and "creator_one" not in json.dumps(d)
    back = selection_from_dict(d)
    assert back.users == (f"key:{user_key('creator_one')}",) and user_key(back.users[0]) == user_key("creator_one")
    assert back.with_project_assets and back.contests == sel.contests
    prof = Selection.build(users="creator_one", with_profiles=True)
    assert prof.to_dict()["users"] == ["creator_one"]
    assert Selection.build(contests="x").tabs_for_contest == ("latest",)


@pytest.mark.parametrize("kw", [dict(contest_tabs="liked"), dict(what="user-projects")])
def test_nested_options_reject_bad_values(kw):
    with pytest.raises(ValueError):
        Selection.build(**kw)


def test_new_kinds_registered():
    sdef = registry.get("projects")
    for k in ("projects_folder", "projects_asset", "projects_brief", "projects_stats", "projects_stack_item",
              "projects_comment", "projects_related"):
        assert k in sdef.model_by_kind and k in sdef.id_field_by_kind


# ------------------------------------------------------------------ parsers
def test_folders_and_counts():
    sel = Selection.build(with_project_assets=True)
    root = parse_envelope(load("folder_root.json"), sel)[0]
    assert root["kind"] == "projects_folder" and root["folder_id"] == ROOT and root["is_root"]
    assert root["asset_count"] == 60 and root["subfolders_count"] == 8 and root["depth"] == 0
    assert root["publication_id"] == PID and root["owner_key"] and "owner_username" not in root
    kids = parse_envelope(load("folder_children_root.json"), sel)
    counts = {f["name"]: f["asset_count"] for f in kids}
    assert counts == {"Watermarks": 4, "Titles and Posters": 13, "Scenes": 22, "Props": 2, "Cast": 6,
                      "Locations": 16, "Music": 1}
    assert all(f["depth"] == 1 and f["parent_id"] == ROOT and f["root_folder_id"] == ROOT for f in kids)
    assert [f["position"] for f in kids] == list(range(len(kids)))
    for e in kids + [root]:
        assert e["source_url"].startswith("https://") and e["scraped_at"] and e["schema_version"] == 1
        validate_entity(e)


def test_assets_prompt_model_params_media():
    sel = Selection.build(with_project_assets=True)
    assets = parse_envelope(load("folder_items.json"), sel)
    assert assets and all(a["kind"] == "projects_asset" for a in assets)
    img = next(a for a in assets if a["media_type"] == "image" and a["item_type"] == "job")
    assert img["prompts_visible"] and img["prompt"] and img["has_prompt"] and "prompt" in img["params"]
    assert img["job_set_type"] and img["url"].startswith("https://") and img["min_url"]
    assert {v["variant"] for v in img["variants"]} >= {"raw", "min"}
    assert img["placement_id"] != img["asset_id"] and img["folder_id"] and img["created_at"].endswith("+00:00")
    vid = next(a for a in assets if a["media_type"] == "video")
    assert vid["duration_seconds"] and vid["thumbnail_url"] and vid["resolution"]
    audio = next(a for a in assets if a["item_type"] == "audio_input")
    assert audio["media_type"] == "audio" and audio["filename"] and audio["size_bytes"] and audio["waveform_url"]
    assert all(a["in_all_assets"] for a in assets)
    assert all("user" not in a["extra"] and "username" not in json.dumps(a["extra"]) for a in assets)
    for a in assets:
        validate_entity(a)
    wm = parse_envelope(load("folder_items_watermarks.json"), sel)
    assert wm and all(not a["in_all_assets"] and a["item_type"] == "file_input" for a in wm)


def test_prompts_hidden_when_author_disabled_them():
    env = load("folder_items.json")
    env.params["show_prompts"] = "false"
    assets = parse_envelope(env, Selection.build(with_project_assets=True))
    job = next(a for a in assets if a["item_type"] == "job")
    assert not job["prompts_visible"] and job["prompt"] is None and job["has_prompt"]
    assert not any(k in job["params"] for k in ("prompt", "negative_prompt"))
    del env.params["show_prompts"]                       # unknown -> hidden
    assert all(a["prompt"] is None for a in parse_envelope(env, Selection.build(with_project_assets=True)))


def test_stats_and_stack_match_the_page():
    """Page: Generations 59 · Credits spent 5 064 · Size 739.4 MB · Stack Seedream 5.0 Pro 32.2% (+6 more)."""
    ents = kinds(parse_envelope(load("publication_detail.json"), Selection.build(with_project_stats=True)))
    st = ents["projects_stats"][0]
    assert (st["generations_count"], st["credits_spent"], st["size_mb"]) == (59, 5064.0, 739.4)
    stack = ents["projects_stack_item"]
    assert [(s["label"], s["percent"]) for s in stack] == [
        ("Seedream 5.0 Pro", 32.2), ("Seedance 2.5", 30.5), ("Seedream 5.5", 27.1), ("Kling 4.0", 3.4),
        ("MAGI-2", 3.4), ("Ideogram 4.6 Precise Edit", 1.7), ("Soul Cinematic", 1.7)]
    assert sum(s["count"] for s in stack) == st["generations_count"] == st["stack_generations"]
    assert round(sum(s["percent"] for s in stack), 1) == 100.0
    assert "projects_stats" not in kinds(parse_envelope(load("publication_detail.json"), Selection.build()))


def test_stack_from_a_redacted_archive_falls_back_to_the_model_key():
    """raw/ archives blank `display_name` (core privacy keys): normalize then labels the stack by job_set_type."""
    env = load("publication_detail.json")
    for s in env.body["stats"]["stack"]:
        s["display_name"] = "[redacted]"
    stack = kinds(parse_envelope(env, Selection.build(with_project_stats=True)))["projects_stack_item"]
    assert stack[0]["display_name"] is None and stack[0]["label"] == "seedream_v5_pro" and stack[0]["percent"] == 32.2


def test_largest_remainder_rounding_like_the_page():
    assert _largest_remainder_tenths([50.0, 50.0]) == [50.0, 50.0]
    assert _largest_remainder_tenths([33.333, 33.333, 33.334]) == [33.3, 33.3, 33.4]
    assert _largest_remainder_tenths([]) == [] and _largest_remainder_tenths([0.0]) == [0.0]


def test_brief_markdown_from_yjs_snapshot():
    env = load("brief.json")
    b = parse_envelope(env, Selection.build(with_project_brief=True))[0]
    assert b["kind"] == "projects_brief" and b["has_content"] and b["markdown"].strip()
    assert b["snapshot_bytes"] == env.body["bytes"] and b["block_count"] > 0 and b["word_count"] > 0
    assert b["brief_id"] == b["folder_id"] and b["decode_error"] is None
    validate_entity(b)


def test_brief_renderer_handles_lexical_nodes():
    import base64
    md, info = brief_markdown(base64.b64decode(load("brief.json").body["snapshot_b64"]))
    assert md == brief_markdown(base64.b64decode(load("brief.json").body["snapshot_b64"]))[0]   # deterministic
    assert set(info["node_types"]) & {"paragraph", "heading", "text"}


def test_yjs_decoder_rejects_garbage_and_empty():
    with pytest.raises(YjsDecodeError):
        decode_doc(b"")
    with pytest.raises(YjsDecodeError):
        decode_doc(b"\x05\xff")
    empty = {"snapshot_b64": "", "bytes": 0, "updated_at_ms": None}
    env = Envelope(endpoint="projects_brief", url="https://x/brief/f/snapshot", status=200, body=empty,
                   params={"folder_id": "f", "publication_id": "p"}, fetched_at=load("brief.json").fetched_at)
    b = parse_envelope(env, Selection.build(with_project_brief=True))[0]
    assert not b["has_content"] and b["markdown"] is None and b["snapshot_bytes"] == 0


def test_comments_are_pseudonymous():
    sel = Selection.build(with_project_comments=True)
    cs = parse_envelope(load("comments.json"), sel)
    assert cs and all(c["kind"] == "projects_comment" and c["text"] and c["author"]["author_key"] for c in cs)
    assert all(validate_entity(c)["author"]["username"] is None and c["author"].get("user_id") is None for c in cs)
    assert all(c["thread_type"] == "project_publication" and c["publication_id"] == PID for c in cs)
    assert {c["likes"] for c in cs} <= {0, 1, 2, 3, 4, 5} and all(c["reply_count"] is not None for c in cs)
    prof = parse_envelope(load("comments.json"), Selection.build(with_project_comments=True, with_profiles=True))
    assert all(c["author"]["user_id"] for c in prof)
    for c in cs:
        validate_entity(c)


def test_related_projects():
    rel = parse_envelope(load("related.json"), Selection.build(with_project_related=True))
    assert rel and [r["position"] for r in rel] == list(range(len(rel)))
    assert all(r["publication_id"] == PID and r["related_publication_id"] != PID for r in rel)
    assert all(r["scope"] == "talent_contest" and r["name"] for r in rel)


def test_user_projects_listing_hides_the_handle():
    env = load("user_publications.json")
    sel = Selection.build(users="creator_one")
    ents = kinds(parse_envelope(env, sel))
    pubs = ents["projects_publication"]
    assert len(pubs) == 2 and pubs[0]["publication_id"] == PID
    listing = f"user:{user_key('creator_one')}"
    assert all(e["listing"] == listing for e in ents["projects_listing_entry"])
    blob = json.dumps(ents)
    assert "creator_one" not in blob and "/user/key:" in blob
    prof = parse_envelope(env, Selection.build(users="creator_one", with_profiles=True))
    assert "/user/creator_one/" in json.dumps(prof)


def test_contest_by_slug_is_a_contest_detail():
    c = parse_envelope(load("contest_by_slug_talent.json"), Selection.build(contests="talent-contest"))[0]
    assert c["kind"] == "projects_contest_detail" and c["slug"] == "talent-contest" and c["prize_pool"] == 1000000


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


def respond(sp, fixture: str, callback=None):
    env = load(fixture)
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params, "handle": "creator_one"})
    resp = TextResponse(env.url, body=json.dumps(env.body).encode(), encoding="utf-8", request=req, status=env.status)
    out = list((callback or sp.parse_api)(resp))
    return [o for o in out if not isinstance(o, Request)], [o for o in out if isinstance(o, Request)]


def test_build_requests_contest_slugs_and_users():
    urls = [r.url for r in make_spider(what="contests", contests="talent-contest,wcc-the-place-you-know")
            .build_requests()]
    assert urls == ["https://fnf-api-gw.higgsfield.ai/fnf/contests/talent-contest",
                    "https://fnf-api-gw.higgsfield.ai/fnf/contests/wcc-the-place-you-know"]
    reqs = list(make_spider(what="user-projects", users="creator_one").build_requests())
    assert len(reqs) == 1 and "/user/creator_one/v2/publications?publication_type=project&limit=50" in reqs[0].url
    assert reqs[0].meta["params"]["user_key"] == user_key("creator_one")
    assert not list(make_spider(what="user-projects", users="key:abc").build_requests())   # redacted manifest


def test_default_build_requests_unchanged_by_nested_code():
    from higgsfield_scraper.scrapers.projects.spider import ProjectsSpider  # noqa: F401
    urls = [r.url for r in make_spider().build_requests()]
    assert not any("/user/" in u or "/folders/" in u or "brief" in u or "/contests/talent" in u for u in urls)


def test_contest_by_slug_follows_submissions_and_tabs():
    sp = make_spider(what="contests", contests="talent-contest", with_submissions=True, max_submissions=5,
                     contest_tabs="latest,submissions")
    _, reqs = respond(sp, "contest_by_slug_talent.json")
    urls = [r.url for r in reqs]
    assert any("/submissions?limit=5" in u for u in urls)
    tabs = [u for u in urls if "contest-participations" in u]
    assert len(tabs) == 2 and all("contest_key=talent_contest" in u and "size=5" in u for u in tabs)
    assert not [r for r in respond(make_spider(what="contests", contests="talent-contest"),
                                   "contest_by_slug_talent.json")[1]]        # no --with-submissions: nothing


def test_entries_listing_in_contest_mode_is_capped_and_goes_nested():
    sp = make_spider(what="contests", contests="talent-contest", with_submissions=True, max_submissions=2,
                     with_project_assets=True)
    sp._contest_listings["entries:talent_contest:latest"] = 0
    items, reqs = respond(sp, "contest_entries_talent.json")
    assert sum(r.meta["endpoint"] == "projects_publication_detail" for r in reqs) == 2
    assert not any(r.meta["endpoint"] == "projects_contest_entries" for r in reqs)     # 2 >= max_submissions
    assert any("max_submissions=2" in x for x in sp.limits_hit)


def test_detail_fans_out_to_nested_requests():
    sp = make_spider(what="publications", **ALL)
    _, reqs = respond(sp, "publication_detail.json")
    eps = sorted(r.meta["endpoint"] for r in reqs)
    assert eps == ["projects_brief", "projects_comments", "projects_folder", "projects_folder_children",
                   "projects_folder_items", "projects_related"]
    by = {r.meta["endpoint"]: r for r in reqs}
    assert f"/folders/{ROOT}/items/v2?size=100&include_subfolders=true" in by["projects_folder_items"].url
    assert by["projects_folder_items"].meta["params"]["show_prompts"] == "true"
    assert by["projects_brief"].url == f"{ep.BRIEF_BASE}/brief/{ROOT}/snapshot"
    assert by["projects_comments"].url.startswith(f"{ep.COMMUNITY_BASE}/entities/project_publication/{PID}/comments")
    assert "scope=talent_contest" in by["projects_related"].url and f"current_publication_id={PID}" in \
        by["projects_related"].url
    assert not respond(sp, "publication_detail.json")[1]                       # once per publication
    assert not respond(make_spider(what="publications", with_details=True), "publication_detail.json")[1]


def test_children_recurse_and_watermarks_listed_separately():
    sp = make_spider(what="publications", with_project_assets=True)
    _, reqs = respond(sp, "folder_children_root.json", callback=None)
    eps = [(r.meta["endpoint"], r.meta["params"].get("parent") or r.meta["params"].get("items_folder")) for r in reqs]
    assert sum(e == "projects_folder_children" for e, _ in eps) == 2              # Cast and Titles and Posters
    wm = [r for r in reqs if r.meta["endpoint"] == "projects_folder_items"]
    assert len(wm) == 1 and "include_subfolders" not in wm[0].url and wm[0].meta["params"]["items_folder"]


def test_folder_response_blanks_owner_username_before_archiving():
    sp = make_spider(what="publications", with_project_assets=True)
    env = load("folder_root.json")
    body = dict(env.body, owner_username="creator_one")
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params})
    resp = TextResponse(env.url, body=json.dumps(body).encode(), encoding="utf-8", request=req, status=200)
    out = [o for o in sp.parse_folder_response(resp) if not isinstance(o, Request)]
    assert "creator_one" not in json.dumps([dict(o) for o in out], default=str)


def test_brief_binary_response_is_wrapped_and_parsed():
    import base64
    sp = make_spider(what="publications", with_project_brief=True)
    env = load("brief.json")
    data = base64.b64decode(env.body["snapshot_b64"])
    req = Request(env.url, meta={"endpoint": "projects_brief", "params": env.params})
    resp = Response(env.url, body=data, request=req, status=200, headers={"X-Brief-Updated-At": "1795699000000",
                                                                         "Content-Type": "application/octet-stream"})
    out = list(sp.parse_brief_response(resp))
    raw = next(o for o in out if o.get("kind") == "raw_response")
    assert raw["body"]["bytes"] == len(data) and raw["body"]["updated_at_ms"] == "1795699000000"
    brief = next(o for o in out if o.get("kind") == "projects_brief")
    assert brief["has_content"] and brief["updated_at"].startswith("2026-11-26")


def test_items_and_comments_pagination():
    sp = make_spider(what="publications", with_project_assets=True, with_project_comments=True)
    env = load("folder_items.json")
    body = dict(env.body, cursor=1795694452.5)
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params})
    resp = TextResponse(env.url, body=json.dumps(body).encode(), encoding="utf-8", request=req, status=200)
    reqs = [o for o in sp.parse_api(resp) if isinstance(o, Request)]
    assert len(reqs) == 1 and "cursor=1795694452.5" in reqs[0].url
    assert reqs[0].meta["params"]["offset"] == str(len(env.body["items"]))
    env = load("comments.json")
    items = [dict(env.body["items"][0], reply_count=2)] + env.body["items"][1:]
    body = dict(env.body, items=items, next_cursor="abc")
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params})
    resp = TextResponse(env.url, body=json.dumps(body).encode(), encoding="utf-8", request=req, status=200)
    reqs = [o for o in sp.parse_api(resp) if isinstance(o, Request)]
    assert any("parent_id=" in r.url and "order=asc" in r.url for r in reqs)
    assert any("cursor=abc" in r.url and "parent_id" not in r.url for r in reqs)


# ------------------------------------------------------------------ dataset / outputs
def test_build_dataset_nested_enrichment(tmp_path):
    sel = Selection.build(users="creator_one", **ALL)
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    assert {"folders", "assets", "briefs", "project_stats", "stack_items", "comments", "related",
            "nested_summary"} <= set(ds)
    a = next(x for x in ds["assets"] if x["item_type"] == "job")
    assert a["model_name"] and a["folder_name"]
    assert all(x["folder_path"] for x in ds["assets"] if x["folder_id"] != ROOT and x["in_all_assets"])
    root = next(f for f in ds["folders"] if f["is_root"])
    assert root["assets_scraped"] == sum(1 for x in ds["assets"] if x["in_all_assets"])
    wm = next(f for f in ds["folders"] if f["name"] == "Watermarks")
    assert wm["assets_scraped"] == sum(1 for x in ds["assets"] if not x["in_all_assets"])
    assert ds["meta"]["counts"]["assets"] == len(ds["assets"])
    assert "projects_folder_items" in ds["meta"]["endpoints"] and "projects_brief" in ds["meta"]["endpoints"]
    assert all(c["is_by_author"] is not None for c in ds["comments"] if c["publication_id"] == PID)


def test_default_dataset_has_no_nested_keys():
    sel = Selection.build()
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    assert not ({"folders", "assets", "briefs", "nested_summary"} & set(ds))
    assert set(ds["meta"]["counts"]) == {"publications", "episodes", "categories", "contests", "submissions",
                                         "series", "listing_entries"}


def _csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return set(r.fieldnames or []), rows


def test_nested_csvs_complete_and_brief_files(tmp_path):
    from higgsfield_scraper.core.exporting import without
    sel = Selection.build(users="creator_one", **ALL)
    ds = SCRAPER.build_dataset(all_entities(sel), sel, RunMeta())
    SCRAPER.write_outputs(ds, tmp_path)
    checks = {
        "project_folders": ds["folders"],
        "project_assets": [without(a, "variants", "input_media") for a in ds["assets"]],
        "project_asset_variants": [v for a in ds["assets"] for v in a["variants"]],
        "project_asset_inputs": [i for a in ds["assets"] for i in a["input_media"]],
        "project_briefs": ds["briefs"],
        "project_stats": ds["project_stats"],
        "project_stack": ds["stack_items"],
        "project_comments": ds["comments"],
        "project_related": ds["related"],
    }
    for table, objects in checks.items():
        cols, rows = _csv(tmp_path / "csv" / f"{table}.csv")
        assert objects, f"fixture gives no rows for {table}"
        assert len(rows) == len(objects), table
        missing = {k for o in objects for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{table}.csv is missing JSON fields: {sorted(missing)[:10]}"
    b = ds["briefs"][0]
    assert b["file"] and (tmp_path / b["file"]).read_text("utf-8") == b["markdown"]
    schema = json.loads((tmp_path / "schema" / "dataset.schema.json").read_text("utf-8"))
    assert "assets" in schema["properties"]
    assert "Nested project data" in (tmp_path / "summary.md").read_text("utf-8")


def test_nested_dataset_has_no_personal_data_without_profiles():
    sel = Selection.build(users="creator_one", **ALL)
    blob = json.dumps(SCRAPER.build_dataset(all_entities(sel), sel, RunMeta()))
    assert "creator_one" not in blob and "Creator One" not in blob


def test_media_urls_for_assets():
    sel = Selection.build(with_project_assets=True)
    assets = parse_envelope(load("folder_items.json"), sel)
    img = next(a for a in assets if a["media_type"] == "image")
    assert media_urls(img, "full") == [("original", img["url"])]
    assert media_urls(img, "thumbs") and media_urls(img, "none") == []
    vid = next(a for a in assets if a["media_type"] == "video")
    assert ("original", vid["url"]) in media_urls(vid, "all") and media_urls(vid, "thumbs")


def test_normalize_offline_nested(tmp_path):
    import logging
    import shutil

    from higgsfield_scraper.cli import main
    from higgsfield_scraper.run.context import latest_run
    from higgsfield_scraper.run.logging_setup import teardown_logging
    src = tmp_path / "runs" / "20260101-000000_projects-nested"
    shutil.copytree(FIX, src / "raw")
    sel = Selection.build(users="creator_one", **ALL)
    (src / "manifest.json").write_text(json.dumps({"scraper": "projects", "selection": sel.to_dict()}), "utf-8")
    rc = main(["normalize", "--run", str(src), "--runs-dir", str(tmp_path / "runs"), "--log-level", "ERROR"])
    teardown_logging([h for h in logging.getLogger().handlers if getattr(h, "_higgs", False)])
    assert rc == 0
    run = latest_run(tmp_path / "runs")
    m = json.loads((run / "manifest.json").read_text("utf-8"))
    assert m["status"] == "success" and m["counts"]["assets"] > 0 and m["counts"]["briefs"] == 1
    assert list((run / "output" / "briefs").glob("*.md"))


# ------------------------------------------------------------------ auth gating (anonymous vs logged in)
def test_nested_requests_are_anonymous_even_with_a_session(monkeypatch):
    """Logged in, the nested endpoints return the same public data (see docs "Anonymous vs logged in"): the scraper
    never attaches the session to them, so --auth auto with a cached session gives the same output."""
    from higgsfield_scraper.scrapers.projects.spider import ProjectsSpider
    monkeypatch.setattr(ProjectsSpider, "authed", property(lambda self: True))
    sp = make_spider(what="publications", **ALL)
    _, reqs = respond(sp, "publication_detail.json")
    assert reqs and all(not r.meta.get("auth") for r in reqs)
    sp = make_spider(what="contests", contests="talent-contest", with_submissions=True, contest_tabs="all", **ALL)
    _, reqs = respond(sp, "contest_by_slug_talent.json")
    assert reqs and all(not r.meta.get("auth") for r in reqs)
    assert all(not r.meta.get("auth") for r in make_spider(what="user-projects", users="creator_one").build_requests())


def test_auth_off_has_no_token_provider():
    assert make_spider(CommonOptions(auth="off"), what="publications", **ALL).token_provider is None


@pytest.mark.parametrize("tab", ["liked", "voted"])
def test_viewer_only_tabs_are_refused(tab):
    """liked / voted are the logged-in viewer's own likes and votes (401 anonymous): never scraped."""
    with pytest.raises(ValueError):
        Selection.build(contests="talent-contest", contest_tabs=tab)
