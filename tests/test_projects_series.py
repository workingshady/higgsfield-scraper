"""projects: opt-in public original series (--public-series, fnf-series service). The default run keeps the legacy
login-only fnf path. Fixture: tests/fixtures/projects_series/ (real response 2026-11-26, trimmed, user ids redacted)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.projects import SCRAPER
from higgsfield_scraper.scrapers.projects import endpoints as ep
from higgsfield_scraper.scrapers.projects.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.projects.parsers import parse_envelope
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "projects_series"
ENV = "projects_series_public__limit-2.json"


def spider(common=None, **sel):
    from higgsfield_scraper.scrapers.projects.spider import ProjectsSpider
    return ProjectsSpider(selection=Selection.build(**sel), common=common or CommonOptions(auth="off"))


def test_option_default_and_roundtrip():
    assert "public_series" not in Selection.build().to_dict()            # default meta.options unchanged
    s = Selection.build(what="series", public_series=True)
    assert s.to_dict()["public_series"] is True and selection_from_dict(s.to_dict()) == s
    assert set(ep.PUBLIC_SERIES_ENDPOINTS).isdisjoint(ep.ENDPOINTS)


def test_default_requests_unchanged_and_public_request():
    default = [r.url for r in spider().build_requests()]
    assert not any("series" in u for u in default)                      # no session: skipped, as before
    reqs = list(spider(what="series", public_series=True).build_requests())
    assert [r.url for r in reqs] == ["https://fnf-api-gw.higgsfield.ai/fnf-series/series?limit=100"]
    assert reqs[0].meta["endpoint"] == "projects_series_public" and not reqs[0].meta["auth"]
    capped = spider(CommonOptions(auth="off", max_items=10), what="series", public_series=True)
    assert [r.url for r in capped.build_requests()] == ["https://fnf-api-gw.higgsfield.ai/fnf-series/series?limit=10"]


def test_public_series_parse_same_entities_as_legacy():
    sel = Selection.build(what="series", public_series=True)
    env = Envelope.load(FX / ENV)
    ents = parse_envelope(env, sel)
    series = [e for e in ents if e["kind"] == "projects_series"]
    eps = [e for e in ents if e["kind"] == "projects_episode"]
    assert len(series) == 2 and len(eps) == 2 and series[0]["slug"] == "cully-hill-boys"
    assert series[0]["author"] is None and series[0]["views"] and series[0]["url"].endswith("/cully-hill-boys")
    for e in ents:
        validate_entity(e)
    legacy = Envelope(endpoint="projects_series", url=env.url, status=200, body=env.body, params=env.params,
                      fetched_at=env.fetched_at)
    strip = lambda xs: [{k: v for k, v in x.items() if k != "source"} for x in xs]  # noqa: E731
    assert strip(parse_envelope(legacy, sel)) == strip(ents)            # same fields, same ids


def test_details_follow_up_and_dataset():
    sp = spider(what="series", public_series=True, with_details=True)
    env = Envelope.load(FX / ENV)
    ents = parse_envelope(env, sp.selection)
    out = list(sp.follow_up(env, ents, SimpleNamespace(meta={})))
    assert [r.url for r in out] == ["https://fnf-api-gw.higgsfield.ai/fnf-series/series/cully-hill-boys",
                                    "https://fnf-api-gw.higgsfield.ai/fnf-series/series/"
                                    "behind-the-scenes-of-mork-the-tale-of-kael"]
    sel = Selection.build(what="series", public_series=True)
    g: dict = {}
    for e in ents:
        g.setdefault(e["kind"], []).append(validate_entity(e))
    ds = SCRAPER.build_dataset(g, sel, RunMeta())
    assert ds["meta"]["counts"]["series"] == 2 and not ds["meta"]["warnings"]
    assert ds["meta"]["endpoints"]["projects_series_public"] == "https://fnf-api-gw.higgsfield.ai/fnf-series/series"
    d0 = SCRAPER.build_dataset({}, Selection.build(what="series"), RunMeta())
    assert "projects_series_public" not in d0["meta"]["endpoints"]
    assert d0["meta"]["warnings"] == ["original series (/series) need a login session: none scraped"]
