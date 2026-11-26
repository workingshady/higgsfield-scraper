"""Catalog additions 2026-11-26 (all additive): katana preset archive redaction (COMPLETENESS #5), katana
author_key / creator_uid_key (#11), and the name-only `outfit_character` kind (CONTENT_MAP GAP) that stays out of
`--kinds all` so existing runs plan the same requests. Fixture: tests/fixtures/catalog_named/ (live 2026-11-26)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scrapy.http import Request, TextResponse

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.privacy import creator_uid_key
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.catalog import SCRAPER
from higgsfield_scraper.scrapers.catalog.endpoints import KINDS, NAMED_ONLY, SELECTABLE
from higgsfield_scraper.scrapers.catalog.options import build, default_label, parse_kinds
from higgsfield_scraper.scrapers.catalog.parsers import parse_envelope
from higgsfield_scraper.scrapers.catalog.privacy import CatalogPrivacyMiddleware, redact_body
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "catalog_named"
KATANA_FX = Path(__file__).parent / "fixtures" / "catalog" / "catalog_katana_presets__lang-en__limit-2.json"
FAKE_UID = "user_FakeKatanaAuthor0001"


def katana_body() -> dict:
    """The real fixture with a fake (unredacted-looking) author, as the API sends it."""
    body = Envelope.load(KATANA_FX).body
    for it in body["items"]:
        it["author"] = {"user_id": FAKE_UID, "username": "fake_katana_user",
                        "avatar_url": "https://example.invalid/avatar.png", "badge": None}
    return body


def katana_env(body) -> Envelope:
    return Envelope(endpoint="catalog_katana_presets", url="https://fnf-api-gw.higgsfield.ai/fnf-cms-api/katana-presets",
                    status=200, body=body, params={"limit": "2", "lang": "en"},
                    fetched_at=datetime(2026, 11, 26, tzinfo=timezone.utc))


# ------------------------------------------------------------------ #5 archive redaction
def test_katana_body_redacted_before_archiving():
    raw = json.dumps(katana_body()).encode("utf-8")
    req = Request("https://fnf-api-gw.higgsfield.ai/fnf-cms-api/katana-presets?limit=2&lang=en",
                  meta={"endpoint": "catalog_katana_presets"})
    resp = TextResponse(req.url, body=raw, encoding="utf-8", request=req)
    mw = CatalogPrivacyMiddleware()
    out = mw.process_response(req, resp, SimpleNamespace(scraper_name="catalog", selection=build()))
    text = out.body.decode("utf-8")
    assert "fake_katana_user" not in text and "example.invalid" not in text
    assert FAKE_UID in text                                   # opaque id kept: author_key still works
    a = json.loads(text)["items"][0]["author"]
    assert a["username"] == "[redacted]" and a["avatar_url"] == "[redacted]" and a["badge"] is None
    # --with-profiles, other endpoints / scrapers: byte-identical
    keep = mw.process_response(req, resp, SimpleNamespace(scraper_name="catalog",
                                                          selection=build(with_profiles=True)))
    assert keep.body == raw
    other = Request("https://fnf-api-gw.higgsfield.ai/fnf/motions?size=5", meta={"endpoint": "catalog_motions"})
    r2 = TextResponse(other.url, body=raw, encoding="utf-8", request=other)
    assert mw.process_response(other, r2, SimpleNamespace(scraper_name="catalog", selection=build())) is r2
    assert mw.process_response(req, resp, SimpleNamespace(scraper_name="studios", selection=build())) is resp
    assert redact_body(b"<html>not json</html>") == b"<html>not json</html>"


def test_catalog_spider_adds_privacy_middleware_before_http_archive():
    from scrapy.settings import Settings

    from higgsfield_scraper import settings as project_settings
    from higgsfield_scraper.scrapers.catalog.spider import CatalogSpider
    s = Settings()
    s.setmodule(project_settings)
    CatalogSpider.update_settings(s)
    mws = s.getdict("DOWNLOADER_MIDDLEWARES")
    assert mws[CatalogSpider.PRIVACY_MW] > mws["higgsfield_scraper.middlewares.HttpArchiveMiddleware"]
    assert mws["higgsfield_scraper.core.auth.AuthMiddleware"] == 560                  # project ones kept


# ------------------------------------------------------------------ #11 author keys
def test_katana_author_keys():
    sel = build(kinds="katana_preset", include_login_only="yes")
    body = json.loads(redact_body(json.dumps(katana_body()).encode("utf-8")))      # what the parser receives
    ps = [validate_entity(e) for e in parse_envelope(katana_env(body), sel) if e["kind"] == "catalog_katana_preset"]
    assert len(ps) == 2
    for p in ps:
        assert p["author_key"] == p["creator_uid_key"] == creator_uid_key(FAKE_UID) and p["author_key"]
        assert not {"user_id", "username", "avatar_url"} & set(p["extra"]["author"])
    # the stored fixture has redacted ids -> no key, never a hash of "<redacted>"
    old = [e for e in parse_envelope(Envelope.load(KATANA_FX), sel) if e["kind"] == "catalog_katana_preset"]
    assert all(e["author_key"] is None and e["creator_uid_key"] is None for e in old)
    # same hash as showcase / studios creator keys
    from higgsfield_scraper.schemas.common import make_id
    assert creator_uid_key(FAKE_UID) == make_id("creator", FAKE_UID)


# ------------------------------------------------------------------ outfit characters (name-only kind)
def test_outfit_character_is_name_only():
    assert NAMED_ONLY == ("outfit_character",) and "outfit_character" not in KINDS and "outfit_character" in SELECTABLE
    assert "outfit_character" not in parse_kinds("all") and "outfit_character" not in parse_kinds("public")
    assert parse_kinds("outfit_characters") == ["outfit_character"]
    assert build(kinds="all").resolve_kinds(True) == [k for k in KINDS]            # `all` unchanged
    assert default_label(build(kinds="all")) == "all-samples"
    assert default_label(build(kinds="all,outfit_character")).startswith("all-outfit_character")
    assert default_label(build(kinds="outfit_character")) == "outfit_character"


def test_outfit_character_requests_and_parse():
    from higgsfield_scraper.scrapers.catalog.spider import CatalogSpider
    sp = CatalogSpider(selection=build(kinds="outfit_character"), common=CommonOptions(auth="off"))
    reqs = list(sp.build_requests())
    assert [r.url for r in reqs] == ["https://fnf-api-gw.higgsfield.ai/fnf/outfits/characters"]
    assert not reqs[0].meta["auth"]
    all_urls = [r.url for r in CatalogSpider(selection=build(kinds="all", include_login_only="yes"),
                                             common=CommonOptions(auth="off")).build_requests()]
    assert not any("outfits" in u for u in all_urls)
    sel = build(kinds="outfit_character")
    ents = [validate_entity(e) for e in parse_envelope(Envelope.load(FX / "catalog_outfit_characters.json"), sel)]
    chars = [e for e in ents if e["kind"] == "catalog_outfit_character"]
    assert len(chars) == 2 and chars[0]["id"] == "d833d942-d8ff-478a-b3ce-fd13bebf9988"
    assert chars[0]["width"] == 1400 and chars[0]["api_type"] == "media_input" and chars[0]["schema_version"] == 1
    assert chars[0]["media"][0]["type"] == "image" and chars[0]["source_url"].endswith("/outfits/characters")
    page = next(e for e in ents if e["kind"] == "catalog_page")
    assert page["item_count"] == 2 and page["next_cursor"] is None


def test_outfit_dataset_only_when_selected(tmp_path):
    sel = build(kinds="outfit_character")
    ents: dict[str, list[dict]] = {}
    for e in parse_envelope(Envelope.load(FX / "catalog_outfit_characters.json"), sel):
        if SCRAPER.keep(e, sel):
            v = validate_entity(e)
            ents.setdefault(v["kind"], []).append(v)
    ds = SCRAPER.build_dataset(ents, sel, RunMeta())
    assert len(ds["outfit_characters"]) == 2 and ds["meta"]["counts"]["outfit_characters"] == 2
    assert "catalog_outfit_characters" in ds["meta"]["endpoints"]
    assert "chain_presets" not in ds and "notices" not in ds
    SCRAPER.write_outputs(ds, tmp_path)
    assert (tmp_path / "csv" / "outfit_characters.csv").exists()
    assert "outfit_character" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    plain = SCRAPER.build_dataset({}, build(), RunMeta())                 # default run: no trace of the new kind
    assert "outfit_characters" not in plain and "catalog_outfit_characters" not in plain["meta"]["endpoints"]
    assert "outfit_character" not in json.dumps(plain["summary"])
