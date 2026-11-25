"""blog scraper: parsers per page type, Yjs/Lexical decoding, options, spider pagination/discovery, dataset + CSVs."""
from __future__ import annotations

import base64
import csv
import json
from pathlib import Path

import pytest

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.blog import SCRAPER, media_urls
from higgsfield_scraper.scrapers.blog.content import convert_html, convert_lexical, markdown_to_text
from higgsfield_scraper.scrapers.blog.dataset import build_dataset, write_outputs
from higgsfield_scraper.scrapers.blog.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.blog.parsers import (extract_page, keep, parse_envelope, sitemap_urls)
from higgsfield_scraper.scrapers.blog.tsr import router_matches
from higgsfield_scraper.scrapers.blog.yjs import decode_lexical
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "blog"


def env(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def by_prefix(prefix: str) -> Envelope:
    return env(next(p.name for p in sorted(FIX.glob(prefix + "*"))))


def parse(prefix: str, sel: Selection | None = None) -> list[dict]:
    out = parse_envelope(by_prefix(prefix), sel or Selection())
    for e in out:
        validate_entity(e)                       # every entity must pass its pydantic model
    return out


@pytest.fixture
def sel():
    return Selection()


# ------------------------------------------------------------------ registry / options

def test_registered_and_kinds_prefixed():
    assert SCRAPER.name == "blog"
    assert all(k.startswith("blog_") for k in SCRAPER.model_by_kind)
    assert set(SCRAPER.id_field_by_kind) == set(SCRAPER.model_by_kind)


def test_selection_defaults_aliases_and_roundtrip():
    s = Selection()
    assert "community" not in s.what and s.with_content and s.locale == "en"
    s2 = Selection(what="all,community", tags="Guides, news", since="2026-10-01", with_content="false")
    assert "community" in s2.what and "blog" in s2.what
    assert s2.tags == ["guides", "news"] and s2.with_content is False
    assert selection_from_dict(s2.to_dict()) == s2
    assert Selection(what="help-center,enterprise").what == ["help", "enterprise-help"]
    with pytest.raises(ValueError):
        Selection(what="nope")
    with pytest.raises(ValueError):
        Selection(locale="xx")
    with pytest.raises(ValueError):
        Selection(since="10/01/2026")


# ------------------------------------------------------------------ TSR router state

def test_tsr_extraction_from_saved_html():
    e = env("html__enterprise_article__path-_enterprise-help-center_manage-account_limits.json")
    html = e.body["html"]
    matches = router_matches(html)
    assert any((m.get("l") or {}).get("article") for m in matches)
    body = extract_page(html, "/enterprise-help-center/manage-account/limits")
    assert body["format"] == "tsr" and body["head"]["title"]
    art = body["matches"][-1]["l"]["article"]
    assert art["slug"] == "limits" and art["markdown"]


def test_parse_enterprise_article_from_html(sel):
    [a] = parse("html__enterprise_article", sel)
    assert a["kind"] == "blog_help_article" and a["section"] == "enterprise"
    assert a["category_slug"] == "manage-account" and a["title"] == "User Groups"
    assert a["content_format"] == "markdown" and a["word_count"] > 50
    assert a["headings"] and a["headings"][0]["anchor"]
    assert a["previous_slug"] and a["next_slug"]
    assert a["url"] == "https://higgsfield.ai/enterprise-help-center/manage-account/limits"


# ------------------------------------------------------------------ per page type

def test_blog_post_page(sel):
    [p] = parse("blog_page__", sel)
    assert p["kind"] == "blog_post" and p["slug"] == "higgsfield-playable-ads-and-games"
    assert p["category"]["slug"] == "editorials" and p["tags"] == ["editorials"]
    assert p["author"]["name"] == "Higgsfield"
    assert p["published_at"].startswith("2026-10-25") and p["reading_time_minutes"] == 10
    assert p["content_html"].startswith("<") and "Playable" in p["content_text"]
    assert p["content_markdown"].count("## ") >= 3 and p["word_count"] > 500
    assert p["related_posts"] and p["related_posts"][0]["url"].startswith("https://higgsfield.ai/blog/")
    assert p["faq"] and p["faq"][0]["answer_text"]
    assert p["sitemap_lastmod"] is None or len(p["sitemap_lastmod"]) >= 10


def test_blog_post_page_without_content():
    [p] = parse("blog_page__", Selection(with_content=False))
    assert p["title"] and p.get("content_text") is None


def test_blog_index_is_discovery_only_with_content(sel):
    assert parse("blog_index", sel) == []
    posts = parse("blog_index", Selection(with_content=False))
    assert len(posts) >= 10 and all(p["record_source"] == "index" for p in posts)
    assert len({p["post_id"] for p in posts}) == len(posts)


def test_blog_author_page(sel):
    [a] = parse("blog_author", sel)
    assert a["kind"] == "blog_author" and a["name"] == "David Matamoros"
    assert a["post_count"] == len(a["post_slugs"]) > 0


def test_help_article_page(sel):
    [a] = parse("help_article", sel)
    assert a["section"] == "creator-hub" and a["category_slug"] == "getting-started"
    assert a["content_markdown"] and a["content_html"] and a["links"]
    assert a["breadcrumbs"][0] == "Help Center"
    assert all(r["url"].startswith("https://higgsfield.ai/creator-hub/help-center/") for r in a["related_articles"])


def test_help_and_enterprise_index_metadata_mode():
    assert parse("help_index", Selection()) == []
    rows = parse("help_index", Selection(with_content=False))
    assert rows and all(r["record_source"] == "index" and r["url"].count("/") == 6 for r in rows)
    ent = parse("enterprise_index", Selection(with_content=False))
    assert ent and all(r["section"] == "enterprise" for r in ent)


def test_case_study_page(sel):
    [c] = parse("case_study__", sel)
    assert c["kind"] == "blog_case_study" and c["category"]["slug"]
    assert c["hero_metrics"] and isinstance(c["tools_used"], list) and c["content_text"]
    assert len(parse("case_studies_index", Selection(with_content=False))) >= 20


def test_changelog(sel):
    rows = parse("changelog", sel)
    assert len(rows) == 8
    r = rows[0]
    assert r["kind"] == "blog_changelog_entry" and r["url"].startswith("https://higgsfield.ai/creator-hub/changelog#")
    assert r["released_at"] and r["category_slug"] and r["content_text"] and r["chips"]


def test_sitemaps_are_discovery_only(sel):
    assert parse("blog_sitemap", sel) == []
    urls = sitemap_urls(by_prefix("blog_sitemap").body)
    assert len(urls) > 300 and any("/blog/author/" in u["loc"] for u in urls)
    assert len(sitemap_urls(by_prefix("creator_hub_sitemap").body)) > 100


def test_talent_and_community_feeds(sel):
    rows = parse("talent_posts", sel)
    assert len(rows) == 3 and all(r["kind"] == "blog_talent_post" for r in rows)
    r = rows[0]
    assert r["url"].startswith("https://higgsfield.ai/@") and "/blogs/" in r["url"]
    assert r["author"]["avatar_url"] is None                       # personal data is opt-in
    assert parse("talent_posts", Selection(include_author_avatars=True))[0]["author"]["avatar_url"]
    assert r["content_url"].endswith(".bin") and r["published_at"].startswith("20")
    com = parse("recommended_posts", sel)
    assert com and all(c["kind"] == "blog_community_post" and c["feed"] == "community" for c in com)


# ------------------------------------------------------------------ Yjs / Lexical bodies

def test_yjs_lexical_decoding():
    e = by_prefix("post_content__post_id-3762a890")
    tree = decode_lexical(base64.b64decode(e.body["content_b64"]))
    types = [c["type"] for c in tree["children"]]
    assert types[0] == "heading" and "list" in types and "code" in types
    r = convert_lexical(tree)
    assert r["content_markdown"].startswith("# Pencil Knight")
    assert "1. **Create the character in GPT Image.**" in r["content_markdown"]
    assert "```" in r["content_markdown"] and r["word_count"] > 1000
    assert any(i["kind"] == "video" and i["ref_id"] for i in r["images"])


def test_post_content_parser_and_merge(sel):
    [c] = parse("post_content__post_id-01ba", sel)
    assert c["kind"] == "blog_post_content" and c["content_status"] == "ok"
    assert c["content_format"] == "lexical" and c["content_blocks"] and c["images"][0]["url"]
    posts = parse("talent_posts", sel)
    ds = build_dataset({"blog_talent_post": [validate_entity(p) for p in posts],
                        "blog_post_content": [validate_entity(c)]}, sel, RunMeta())
    merged = next(p for p in ds["talent_posts"] if p["post_id"] == c["post_id"])
    assert merged["content_status"] == "ok" and merged["content_text"] == c["content_text"]
    assert sum(p["content_status"] == "not_fetched" for p in ds["talent_posts"]) == 2


def test_corrupt_yjs_is_flagged_not_fatal(sel):
    e = Envelope(endpoint="post_content", url="https://cdn.higgsfield.ai/blog/x.bin", status=200,
                 body={"format": "yjs", "content_b64": base64.b64encode(b"\x01\x05garbage").decode()},
                 params={"post_id": "x"})
    [c] = parse_envelope(e, sel)
    assert c["content_status"].startswith("error") or c["content_status"] == "empty"
    validate_entity(c)


# ------------------------------------------------------------------ HTML conversion

def test_html_to_markdown_tables_links_headings():
    r = convert_html('<h2 id="a">Title <a href="/x">link</a></h2><p>Hello <strong>bold</strong> and '
                     '<a href="https://higgsfield.ai/pricing">pricing</a>.</p><ul><li>one</li><li>two</li></ul>'
                     '<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr>'
                     '</tbody></table><img src="https://cdn.example/x.png" alt="pic">')
    md = r["content_markdown"]
    assert "## Title [link](https://higgsfield.ai/x)" in md and "**bold**" in md
    assert "- one\n- two" in md and "| A | B |\n|---|---|\n| 1 | 2 |" in md
    assert r["headings"] == [{"level": 2, "text": "Title link", "anchor": "a"}]
    assert {lk["url"] for lk in r["links"]} == {"https://higgsfield.ai/x", "https://higgsfield.ai/pricing"}
    assert r["links"][1]["text"] == "pricing" and r["images"][0]["url"] == "https://cdn.example/x.png"
    assert "**" not in r["content_text"] and "Hello bold and pricing." in r["content_text"]
    assert markdown_to_text("**a** [b](c)") == "a b"


def test_cms_comment_blocks_become_media_prompts_and_code():
    h = ('<p>x</p><!--post-asset-block:%7B%22url%22%3A%22https%3A%2F%2Fcdn.sanity.io%2Fa.mp4%22%2C%22contentType'
         '%22%3A%22video%2Fmp4%22%2C%22description%22%3A%22demo%22%7D--><!--post-prompt-block:%7B%22prompt%22%3A%22'
         'a%20cat%22%2C%22url%22%3A%22https%3A%2F%2Fx%2Fb.png%22%2C%22contentType%22%3A%22image%2Fpng%22%7D-->'
         '<!--post-code-block:%7B%22text%22%3A%22npm%20i%22%7D-->')
    r = convert_html(h)
    assert [i["kind"] for i in r["images"]] == ["video", "image"]
    assert "[video: demo](https://cdn.sanity.io/a.mp4)" in r["content_markdown"]
    assert "**Prompt:**\n\n```\na cat\n```" in r["content_markdown"] and "```\nnpm i\n```" in r["content_markdown"]


def test_blog_fixture_post_has_media_from_asset_blocks(sel):
    [p] = parse("blog_page__", sel)
    if "post-asset-block" in (p["content_html"] or ""):
        assert p["images"] and all(i["url"].startswith("https://") for i in p["images"])


# ------------------------------------------------------------------ filters / media

def test_keep_tags_and_since():
    [p] = parse_envelope(by_prefix("blog_page__"), Selection())
    assert keep(p, Selection(tags="editorials"))
    assert not keep(p, Selection(tags="guides"))
    assert keep(p, Selection(since="2026-10-01")) and not keep(p, Selection(since="2026-11-01"))
    author = parse_envelope(by_prefix("blog_author"), Selection())[0]
    assert keep(author, Selection(tags="guides"))                   # filters apply to primary kinds only


def test_media_urls_modes(sel):
    [p] = parse("blog_page__", sel)
    thumbs = media_urls(p, "thumbs")
    assert thumbs and all(role in ("cover", "card") for role, _ in thumbs)
    [c] = parse("post_content__post_id-01ba", sel)
    post = parse("talent_posts", sel)[0] | {k: c[k] for k in ("images",)}
    assert len(media_urls(post, "full")) > len(media_urls(post, "thumbs"))


# ------------------------------------------------------------------ spider discovery / pagination

def _spider(sel=None, **common):
    from higgsfield_scraper.scrapers.blog.spider import BlogSpider
    return BlogSpider(selection=sel or Selection(), common=CommonOptions(auth="off", **common))


def test_spider_first_requests_and_dry_urls():
    sp = _spider()
    urls = [r.url for r in sp.build_requests()]
    assert "https://higgsfield.ai/blog" in urls and "https://higgsfield.ai/creator-hub/changelog" in urls
    assert any("talents/blog-posts?size=50" in u for u in urls)
    assert not any("recommended" in u for u in urls)               # community feed is opt-in
    sp2 = _spider(Selection(what="community", locale="es"), page_size=10)
    [r] = list(sp2.build_requests())
    assert "recommended?size=10" in r.url
    sp3 = _spider(Selection(what="help", locale="es"))
    assert any(r.url == "https://higgsfield.ai/es/creator-hub/help-center" for r in sp3.build_requests())


def test_spider_feed_pagination_and_content_requests():
    sp = _spider(Selection(what="talents"), max_pages=2)
    list(sp.build_requests())
    e = by_prefix("talent_posts")
    e.body = {**e.body, "next_cursor": "blog-recommended:abc"}
    ents = parse_envelope(e, sp.selection)
    sp._accepted |= {x["post_id"] for x in ents}
    reqs = list(sp.follow_up(e, ents, None))
    contents = [r for r in reqs if r.meta["endpoint"] == "post_content"]
    nxt = [r for r in reqs if r.meta["endpoint"] == "talent_posts"]
    assert len(contents) == 3 and contents[0].url.endswith(".bin")
    assert len(nxt) == 1 and "cursor=blog-recommended%3Aabc" in nxt[0].url
    assert nxt[0].meta["params"] == {"size": "50", "page": "2"}   # short raw/ file names
    assert list(sp.follow_up(e, ents, None))[-1].meta["endpoint"] == "post_content"   # max_pages=2 reached
    assert any("max_pages" in x for x in sp.limits_hit)
    e.body = {**e.body, "next_cursor": None}
    assert not [r for r in sp.follow_up(e, ents, None) if r.meta["endpoint"] == "talent_posts"]


def test_spider_blog_discovery_from_index_and_sitemap():
    sp = _spider(Selection(what="blog"), max_items=5)
    list(sp.build_requests())
    first = list(sp.follow_up(by_prefix("blog_index"), [], None))
    assert [r.meta["endpoint"] for r in first] == ["blog_sitemap"]
    reqs = list(sp.follow_up(by_prefix("blog_sitemap"), [], None))
    eps = [r.meta["endpoint"] for r in reqs]
    assert eps.count("blog_author") == 4 and eps.count("blog_page") == 5            # capped by --max-items
    paths = [r.meta["path"] for r in reqs]
    assert "/blog/guides" not in paths and len(set(paths)) == len(paths)
    assert any(r.meta.get("lastmod") for r in reqs if r.meta["endpoint"] == "blog_page")


def test_spider_help_case_enterprise_discovery():
    sp = _spider()
    list(sp.build_requests())
    help_reqs = list(sp.follow_up(by_prefix("help_index"), [], None))
    assert help_reqs and all(r.meta["endpoint"] == "help_article" for r in help_reqs)
    cs = list(sp.follow_up(by_prefix("case_studies_index"), [], None))
    assert len(cs) >= 20 and all(r.meta["endpoint"] == "case_study" for r in cs)
    hub = list(sp.follow_up(by_prefix("creator_hub_sitemap"), [], None))
    eps = {r.meta["endpoint"] for r in hub}
    assert eps <= {"help_article", "case_study"}
    assert not any(r.meta["path"].endswith(("/creators", "/customers")) for r in hub)
    ent = list(sp.follow_up(by_prefix("enterprise_index"), [], None))
    assert ent and all(r.meta["path"].count("/") == 3 for r in ent)


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


def test_build_dataset_and_outputs(tmp_path, sel):
    ds = build_dataset(_all_entities(sel), sel, RunMeta(run_id="t", label="t", totals={"blog_sitemap_urls": 352}))
    assert ds["meta"]["scraper"] == "blog" and ds["meta"]["totals_available"]["blog_sitemap_urls"] == 352
    assert ds["posts"] and ds["help_articles"] and ds["case_studies"] and ds["changelog"] and ds["talent_posts"]
    assert any(a["record_source"] == "post" and a["slug"] == "higgsfield" for a in ds["authors"])
    assert {h["section"] for h in ds["help_articles"]} == {"creator-hub", "enterprise"}
    files = write_outputs(ds, tmp_path)
    assert (tmp_path / "dataset.json").exists() and (tmp_path / "summary.md").exists()
    md = list((tmp_path / "articles" / "posts").glob("*.md"))
    assert md and md[0].read_text(encoding="utf-8").startswith("---\ntitle:")
    assert (tmp_path / "articles" / "help_articles").exists() and (tmp_path / "articles" / "changelog").exists()
    assert len(files) > 30
    assert json.loads((tmp_path / "json" / "posts.json").read_text(encoding="utf-8")) == ds["posts"]


def test_csvs_contain_every_json_field(tmp_path, sel):
    """Nothing may exist only in JSON: every leaf of every object is a column of some CSV, rows 1:1."""
    ds = build_dataset(_all_entities(sel), sel, RunMeta(run_id="t"))
    write_outputs(ds, tmp_path)
    nested = ("headings", "links", "images", "content_blocks", "faq", "related_posts", "related_articles",
              "hero_metrics", "tools_used", "chips")
    drop = lambda d, *ks: {k: v for k, v in d.items() if k not in ks}  # noqa: E731
    checks = {
        "posts": [drop(p, *nested) for p in ds["posts"]],
        "authors": ds["authors"],
        "talent_posts": [drop(p, *nested) for p in ds["talent_posts"]],
        "community_posts": [drop(p, *nested) for p in ds["community_posts"]],
        "help_articles": [drop(a, *nested) for a in ds["help_articles"]],
        "case_studies": [drop(c, *nested) for c in ds["case_studies"]],
        "changelog": [drop(c, *nested) for c in ds["changelog"]],
        "post_headings": [h for p in ds["posts"] for h in p["headings"]],
        "post_links": [x for p in ds["posts"] for x in p["links"]],
        "post_related": [x for p in ds["posts"] for x in p["related_posts"]],
        "post_faq": [x for p in ds["posts"] for x in p["faq"]],
        "talent_post_images": [x for p in ds["talent_posts"] for x in p["images"]],
        "help_article_links": [x for p in ds["help_articles"] for x in p["links"]],
        "help_article_related": [x for p in ds["help_articles"] for x in p["related_articles"]],
        "case_study_metrics": [x for c in ds["case_studies"] for x in c["hero_metrics"]],
        "case_study_tools": [x for c in ds["case_studies"] for x in c["tools_used"]],
        "case_study_faq": [x for c in ds["case_studies"] for x in c["faq"]],
        "changelog_chips": [x for c in ds["changelog"] for x in c["chips"]],
        "changelog_links": [x for c in ds["changelog"] for x in c["links"]],
        "user_post_blocks": [{"content_blocks": p["content_blocks"]} for c in ("talent_posts", "community_posts")
                             for p in ds[c] if p.get("content_blocks") is not None],
    }
    for table, objects in checks.items():
        cols, rows = _csv(tmp_path / "csv" / f"{table}.csv")
        assert len(rows) == len(objects), table
        missing = {k for o in objects for k in flatten(o)
                   if k not in cols and not any(c.startswith(k + ".") for c in cols)}   # null parent of dotted cols
        assert not missing, f"{table}: {sorted(missing)[:10]}"
    _, tags = _csv(tmp_path / "csv" / "post_tags.csv")
    assert len(tags) == sum(len(p["tags"]) for c in ("posts", "talent_posts", "community_posts") for p in ds[c])
