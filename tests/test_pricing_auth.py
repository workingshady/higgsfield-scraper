"""The pricing scraper uses the shared login (AuthMiddleware) and classifies login-only failures correctly."""
import argparse
from types import SimpleNamespace

import pytest
from scrapy import Request
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Response
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.python.failure import Failure

from higgsfield_scraper.scrapers import pricing
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.spiders.higgsfield import HiggsfieldSpider


class _Stats:
    def __init__(self):
        self.d = {}

    def inc_value(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n


def _spider(auth_mode="auto"):
    sel = Selection.build(sections="auth,plans")
    sp = HiggsfieldSpider(selection=sel, common=SimpleNamespace(auth=auth_mode))
    sp.crawler = SimpleNamespace(stats=_Stats())
    return sp


@pytest.mark.parametrize("mode,expected", [("auto", True), ("required", "required"), ("off", None)])
def test_login_only_requests_are_flagged_for_the_auth_middleware(mode, expected):
    req = _spider(mode)._request("credit_packages", auth=True)
    assert req.meta.get("auth") == expected
    assert b"Authorization" not in req.headers            # the middleware adds a fresh token, not the spider
    assert "auth" not in _spider(mode)._request("plans").meta


def _fail(exc, req):
    try:
        raise exc
    except type(exc):
        f = Failure()
    f.request = req                                       # Scrapy attaches the request to errback failures
    return f


def test_server_error_on_login_endpoint_is_a_warning_not_no_login():
    sp = _spider()
    req = sp._request("credit_price", auth=True)
    sp.on_error(_fail(HttpError(Response(req.url, status=500, request=req)), req))
    assert sp.crawler.stats.d == {"higgs/auth/http_error/credit_price/500": 1}


def test_missing_login_is_a_skip_not_an_error():
    sp = _spider("required")
    req = sp._request("credit_packages", auth=True)
    sp.on_error(_fail(IgnoreRequest("login required"), req))
    assert sp.crawler.stats.d == {"higgs/auth/skipped/credit_packages": 1}


def test_public_request_failure_is_still_an_error():
    sp = _spider()
    req = sp._request("plans")
    sp.on_error(_fail(HttpError(Response(req.url, status=500, request=req)), req))
    assert sp.crawler.stats.d == {"higgs/request_errors/plans": 1}


def _args(command, auth="auto"):
    return argparse.Namespace(command=command, auth=auth, token=None, sections="all", plan_sets=None, billing=None,
                              plan_types=None, models=None, categories=None, marketing_versions=None, locale="en",
                              include_hidden_plans=False, include_raw_cost=False, usd_reference="plus:annual")


def test_sections_all_includes_auth_when_logged_in_via_cached_login(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_CLERK_CLIENT", raising=False)
    monkeypatch.setattr("higgsfield_scraper.core.auth_login.load_cached_client", lambda: {"client_cookie": "x"})
    assert "auth" in pricing.make_selection(_args("scrape")).sections
    assert "auth" not in pricing.make_selection(_args("scrape", auth="off")).sections
    # normalize must not depend on this machine's login (offline re-parse stays reproducible)
    assert "auth" not in pricing.make_selection(_args("normalize")).sections


def test_normalize_includes_auth_only_when_the_source_run_has_login_data(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_CLERK_CLIENT", raising=False)
    a = _args("normalize"); a.run = str(tmp_path)
    (tmp_path / "raw").mkdir()
    assert "auth" not in pricing.make_selection(a).sections
    (tmp_path / "raw" / "credit_packages.json").write_text("{}")
    assert "auth" in pricing.make_selection(a).sections


def test_all_plus_explicit_auth_keeps_auth():
    assert "auth" in Selection.build(sections="all,auth").sections
    assert "auth" not in Selection.build(sections="all").sections


def test_sections_all_without_any_login(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_CLERK_CLIENT", raising=False)
    monkeypatch.setattr("higgsfield_scraper.core.auth_login.load_cached_client", lambda: None)
    assert "auth" not in pricing.make_selection(_args("scrape")).sections


def test_credit_packages_keep_every_observed_field_through_items():
    """Regression: Scrapy items only carry declared schema fields; the live shape's extra fields were dropped."""
    from pathlib import Path
    from higgsfield_scraper.items import to_item
    from higgsfield_scraper.parsers import parse_envelope
    from higgsfield_scraper.raw import Envelope
    from higgsfield_scraper.validation import validate_entity
    env = Envelope.load(Path(__file__).parent / "fixtures" / "auth" / "credit_packages.json")
    ent = validate_entity(parse_envelope(env, Selection.build(sections="auth"))[0])
    item = dict(to_item(ent))
    assert item["credits"] == 100.0 and item["amount"] == "6.25" and item["original_amount"] == "8.50"
    for f in ("price_id", "currency", "discount", "credits_per_dollar", "features", "is_highlighted", "expire_days"):
        assert f in item, f
    assert item["features"][0]["text"].startswith("Up to")
