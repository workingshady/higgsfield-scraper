"""Opt-in logged-in pricing (`--logged-in-prices`) and the opt-in `account` section of the pricing scraper.

Fixtures: the anonymous envelopes in fixtures/raw + the logged-in-only rows captured in
samples/higgsfield/login_audit/ (2026-11-26, redacted) + synthetic account bodies in fixtures/login_pricing/.
The main guarantee tested here: without logged-in data, nothing in the output changes.
"""
import argparse
import copy
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from higgsfield_scraper.assemble import build_dataset
from higgsfield_scraper.constants import ACCOUNT_ENDPOINTS, AUTH_ENDPOINTS, SECTIONS
from higgsfield_scraper.exporters import write_outputs
from higgsfield_scraper.parsers import keep, parse_envelope
from higgsfield_scraper.parsers.account import parse_account, sanitize_account_body
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.schemas import Dataset
from higgsfield_scraper.scrapers import pricing
from higgsfield_scraper.selection import Selection
from higgsfield_scraper.spiders.higgsfield import HiggsfieldSpider
from higgsfield_scraper.validation import validate_entity

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(__file__).parent / "fixtures" / "raw"
AUDIT = ROOT / "samples" / "higgsfield" / "login_audit"
ACCOUNT_BODIES = json.loads((Path(__file__).parent / "fixtures" / "login_pricing" / "account_bodies.json")
                            .read_text("utf-8"))
FAKE_PERSONAL = ("ws_fake_123", "sub_fake_1", "user_fake_9", "sc_fake_1", "opt_fake", "someone@example.com",
                 "card ending 4242", "wallet_created_at", "email_type", "workspace_id", "subscription_id")


# ------------------------------------------------------------------ helpers
def _logged_in_envelopes() -> list[Envelope]:
    """Anonymous fixtures + the rows only a logged-in user gets, under the new endpoint names."""
    plans = Envelope.load(RAW / "plans__plan_set_key-ps_a3.json")
    costs = Envelope.load(RAW / "job_costs.json")
    extra_plans = json.loads((AUDIT / "plans_ps_a3_logged_in_extra_plans.json").read_text("utf-8"))["data"]
    extra_costs = json.loads((AUDIT / "job_costs_logged_in_extra_rows.json").read_text("utf-8"))["data"]
    lite = dict(extra_plans["logged_in_only_plans"][0], id="lite-uuid", product_id="prod_x", price_id="price_x")
    pbody = copy.deepcopy(plans.body)
    pbody["plans"].append(lite)
    cbody = copy.deepcopy(costs.body)
    cbody["data"].extend(extra_costs["logged_in_only_rows"])
    cbody["version"] = extra_costs["logged_in_version"]
    return [Envelope(endpoint="plans_logged_in", url=plans.url, status=200, body=pbody, params=dict(plans.params),
                     fetched_at=plans.fetched_at),
            Envelope(endpoint="job_costs_logged_in", url=costs.url, status=200, body=cbody, params={},
                     fetched_at=costs.fetched_at)]


def _entities(sel, extra: list[Envelope] = ()):
    ents = defaultdict(list)
    envs = [Envelope.load(p) for p in sorted(RAW.glob("*.json"))] + list(extra)
    for env in envs:
        for e in parse_envelope(env, sel):
            if keep(e, sel):
                v = validate_entity(e)
                ents[v["kind"]].append(v)
    return ents


def _plans(ds):
    return [p for ps in ds["plan_sets"] for p in ps["plans"]]


def _walk_keys(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, out)
    return out


SEL_ARGS = dict(sections="all", plan_sets="ps_a3,default")


# ------------------------------------------------------------------ merge rule
def test_fixtures_really_lack_the_logged_in_rows():
    anon = Envelope.load(RAW / "plans__plan_set_key-ps_a3.json").body["plans"]
    assert not any(p["plan_type"] == "lite" for p in anon)
    assert "magi_2" not in {r["job_set_type"] for r in Envelope.load(RAW / "job_costs.json").body["data"]}


def test_merge_adds_only_logged_in_rows_and_tags_only_them():
    base_sel = Selection.build(**SEL_ARGS)
    base = build_dataset(_entities(base_sel), base_sel, run_id="t", label="t")
    sel = Selection.build(**SEL_ARGS, has_token=True, logged_in_prices=True)
    ds = build_dataset(_entities(sel, _logged_in_envelopes()), sel, run_id="t", label="t")

    plans, base_plans = _plans(ds), _plans(base)
    lite = [p for p in plans if p["plan_type"] == "lite"]
    assert len(lite) == 1 and lite[0]["visibility"] == "logged_in" and lite[0]["billing_period"] == "annual"
    assert lite[0]["pricing"]["after_offer"]["total"] == "12.00" and lite[0]["discount"]["percent_off"] == 85
    assert lite[0]["source"]["endpoint"] == "plans_logged_in"
    # every anonymous plan is unchanged (same content, same order, no new key)
    assert [p for p in plans if not p.get("visibility")] == base_plans
    assert sum(1 for p in plans if "visibility" in p) == 1
    # plan_set rows are unchanged (plan_count = anonymous response)
    assert [{k: v for k, v in ps.items() if k != "plans"} for ps in ds["plan_sets"]] == \
           [{k: v for k, v in ps.items() if k != "plans"} for ps in base["plan_sets"]]

    magi = [m for m in ds["models"] if m["model_id"] == "magi_2"]
    assert len(magi) == 1 and magi[0]["visibility"] == "logged_in" and magi[0]["has_cost_data"]
    assert magi[0]["price_points"][0]["credits"] == 2.5
    assert [m for m in ds["models"] if not m.get("visibility") and m["model_id"] != "magi_2"] == \
           [m for m in base["models"] if m["model_id"] != "magi_2"]
    assert {m["model_id"] for m in ds["models"] if m.get("visibility")} == {"magi_2"}

    li = ds["meta"]["logged_in_prices"]
    assert li["costs_version_anonymous"] == base["meta"]["costs_version"] == ds["meta"]["costs_version"]
    assert li["costs_version_logged_in"].startswith("9048fa70")
    assert li["logged_in_only_plan_ids"] == [lite[0]["plan_id"]] and li["logged_in_only_model_ids"] == ["magi_2"]
    assert li["differing_rows"] == []
    cv = [c for c in ds["credit_values"] if c.get("visibility")]
    assert [c["plan_type"] for c in cv] == ["lite"]
    assert [c for c in ds["credit_values"] if not c.get("visibility")] == base["credit_values"]


def test_without_logged_in_data_nothing_new_appears(tmp_path):
    sel = Selection.build(**SEL_ARGS)
    ds = build_dataset(_entities(sel), sel)
    assert not {"visibility", "logged_in_prices", "account", "account_records"} & _walk_keys(ds)
    files = {f.relative_to(tmp_path).as_posix() for f in write_outputs(ds, tmp_path)}
    assert not any("account" in f for f in files)
    schema = json.loads((tmp_path / "schema" / "dataset.schema.json").read_text("utf-8"))
    assert schema == Dataset.model_json_schema(mode="serialization")
    assert "visibility" not in json.dumps(schema) and "AccountRecord" not in json.dumps(schema)


def test_flag_alone_without_logged_in_responses_changes_no_row():
    """Flag on, but the login failed: rows identical to a default run; only a warning + meta are added."""
    base_sel = Selection.build(**SEL_ARGS)
    base = build_dataset(_entities(base_sel), base_sel)
    sel = Selection.build(**SEL_ARGS, has_token=True, logged_in_prices=True)
    ds = build_dataset(_entities(sel), sel)
    assert _plans(ds) == _plans(base) and ds["models"] == base["models"]
    assert ds["meta"]["logged_in_prices"]["costs_version_logged_in"] is None
    assert any("--logged-in-prices" in w for w in ds["meta"]["warnings"])


def test_logged_in_outputs_and_schema_document_the_new_fields(tmp_path):
    sel = Selection.build(**SEL_ARGS, has_token=True, logged_in_prices=True)
    ds = build_dataset(_entities(sel, _logged_in_envelopes()), sel)
    write_outputs(ds, tmp_path)
    header = (tmp_path / "csv" / "plans.csv").read_text("utf-8-sig").splitlines()[0]
    assert "visibility" in header.split(",")
    assert "Lite (logged in only)" in (tmp_path / "summary.md").read_text("utf-8")
    schema = (tmp_path / "schema" / "dataset.schema.json").read_text("utf-8")
    assert "visibility" in schema and "LoggedInPricesMeta" in schema
    Dataset.model_validate(json.loads((tmp_path / "dataset.json").read_text("utf-8")))   # round-trips


def test_logged_in_plan_set_rows_and_failed_responses_are_ignored():
    env = _logged_in_envelopes()[0]
    kinds = {e["kind"] for e in parse_envelope(env, Selection.build(**SEL_ARGS))}
    assert kinds == {"plan"}
    bad = Envelope(endpoint="plans_logged_in", url=env.url, status=401, body={"detail": "x"}, params=env.params)
    assert parse_envelope(bad, Selection.build(**SEL_ARGS)) == []


# ------------------------------------------------------------------ section / flag selection rules
def test_account_is_opt_in_and_never_implied_by_all():
    assert "account" not in Selection.build(sections="all").sections
    assert "account" not in Selection.build(sections="all", has_token=True).sections
    s = Selection.build(sections="all,account", has_token=True)
    assert s.sections[-1] == "account" and "auth" in s.sections
    assert Selection.build(sections="account").sections == ["account"]
    assert SECTIONS["auth"] == AUTH_ENDPOINTS == ["credit_packages", "unlim_catalog", "credit_price",
                                                  "adjustable_credits"]   # auth section unchanged


def test_logged_in_endpoints_need_flag_and_login():
    eps = lambda **kw: Selection.build(sections="plans,models", **kw).endpoints()   # noqa: E731
    assert "plans_logged_in" not in eps(has_token=True)
    assert "plans_logged_in" not in eps(logged_in_prices=True)            # no usable login
    assert {"plans_logged_in", "job_costs_logged_in"} <= set(eps(has_token=True, logged_in_prices=True))
    assert "job_costs_logged_in" not in Selection.build(sections="plans", has_token=True,
                                                        logged_in_prices=True).endpoints()
    assert "logged_in_prices" not in Selection.build().to_dict()          # default manifests unchanged
    assert Selection.build(logged_in_prices=True).to_dict()["logged_in_prices"] is True


def _args(command, auth="auto", flag=False, sections="all"):
    return argparse.Namespace(command=command, auth=auth, token=None, sections=sections, plan_sets=None,
                              billing=None, plan_types=None, models=None, categories=None, marketing_versions=None,
                              locale="en", include_hidden_plans=False, include_raw_cost=False,
                              usd_reference="plus:annual", logged_in_prices=flag)


def test_auth_off_disables_logged_in_prices(monkeypatch):
    monkeypatch.setattr("higgsfield_scraper.core.auth_login.load_cached_client", lambda: {"client_cookie": "x"})
    on = pricing.make_selection(_args("scrape", flag=True))
    assert "plans_logged_in" in on.endpoints()
    off = pricing.make_selection(_args("scrape", auth="off", flag=True))
    assert "plans_logged_in" not in off.endpoints()
    assert "plans_logged_in" not in pricing.make_selection(_args("scrape")).endpoints()   # flag not given


def test_normalize_reparses_logged_in_raw(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_CLERK_CLIENT", raising=False)
    a = _args("normalize"); a.run = str(tmp_path)
    (tmp_path / "raw").mkdir()
    assert not pricing.make_selection(a).logged_in_prices
    (tmp_path / "raw" / "plans_logged_in__plan_set_key-ps_a3.json").write_text("{}")
    sel = pricing.make_selection(a)
    assert sel.logged_in_prices and "plans_logged_in" in sel.endpoints()


# ------------------------------------------------------------------ spider
def _spider(sections, auth="auto", flag=True, configured=True, monkeypatch=None):
    sel = Selection.build(sections=sections, has_token=auth != "off", logged_in_prices=flag)
    monkeypatch.setattr(HiggsfieldSpider, "_login_configured", lambda self: configured)
    sp = HiggsfieldSpider(selection=sel, common=SimpleNamespace(auth=auth))
    return sp, {(r.meta["endpoint"], r.meta.get("auth"), r.meta.get("dont_cache")) for r in sp.build_requests()}


def test_spider_sends_opt_in_requests_only_with_a_usable_login(monkeypatch):
    _, reqs = _spider("plans,models,account", monkeypatch=monkeypatch)
    assert ("plans_logged_in", "required", None) in reqs and ("job_costs_logged_in", "required", None) in reqs
    assert {e for e, a, c in reqs if e in ACCOUNT_ENDPOINTS} == set(ACCOUNT_ENDPOINTS)
    assert all(a == "required" and c is True for e, a, c in reqs if e in ACCOUNT_ENDPOINTS)
    for auth, configured in (("off", True), ("auto", False)):
        _, reqs = _spider("plans,models,account", auth=auth, configured=configured, monkeypatch=monkeypatch)
        assert not {e for e, _, _ in reqs} & {"plans_logged_in", "job_costs_logged_in", *ACCOUNT_ENDPOINTS}
        assert {e for e, _, _ in reqs} >= {"plans", "job_costs"}       # public requests unaffected


def test_spider_default_requests_unchanged_by_the_new_code(monkeypatch):
    _, with_login = _spider("all", flag=False, monkeypatch=monkeypatch)
    assert not {e for e, _, _ in with_login} & {"plans_logged_in", "job_costs_logged_in", *ACCOUNT_ENDPOINTS}


# ------------------------------------------------------------------ account privacy
def _prov(ep):
    return {"endpoint": ep, "url": f"https://fnf-api-gw.higgsfield.ai/fnf/{ep}", "params": {},
            "fetched_at": "2026-11-26T00:00:00+00:00"}


@pytest.mark.parametrize("endpoint", ACCOUNT_ENDPOINTS)
def test_account_whitelist_never_keeps_personal_data(endpoint):
    body = ACCOUNT_BODIES[endpoint]
    clean = sanitize_account_body(endpoint, body)
    assert sanitize_account_body(endpoint, clean) == clean                       # idempotent (normalize)
    rec = validate_entity(parse_account(endpoint, 200, body, _prov(endpoint))[0])
    dumped = json.dumps([clean, rec])
    for secret in FAKE_PERSONAL:
        assert secret not in dumped, (endpoint, secret)


def test_account_wallet_balances_converted_from_cost_units():
    rec = parse_account("account_wallet", 200, ACCOUNT_BODIES["account_wallet"], _prov("w"))[0]
    assert rec["fields"]["credits_balance"] == 8.88 and rec["fields"]["total_credits"] == 8.88
    assert rec["fields"]["expire_days"] == 90                                     # not a balance: as returned
    assert rec["conversions"]["credits_balance"].startswith("credits = api_value / 100")
    assert rec["lists"]["scoped_credits"] == [{"scope": "seedance_2_0", "balance": 2.5,
                                                "expires_at": "2026-12-01T00:00:00Z"}]
    top = parse_account("account_auto_top_up", 200, ACCOUNT_BODIES["account_auto_top_up"], _prov("t"))[0]
    assert top["fields"]["credits_per_dollar"] == 18
    assert top["lists"]["options"] == [{"credits": 1000, "amount": 5556}]


def test_account_privacy_middleware_rewrites_only_account_bodies():
    from scrapy import Request
    from scrapy.http import TextResponse
    from higgsfield_scraper.middlewares import AccountPrivacyMiddleware
    mw = AccountPrivacyMiddleware()
    body = json.dumps(ACCOUNT_BODIES["account_subscription"]).encode()
    req = Request("https://fnf-api-gw.higgsfield.ai/fnf/workspaces/subscription", meta={"endpoint": "account_subscription"})
    out = mw.process_response(req, TextResponse(req.url, body=body, request=req), SimpleNamespace())
    assert b"sub_fake_1" not in out.body and json.loads(out.body)["plan_type"] == "free"
    pub = Request("https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans", meta={"endpoint": "plans"})
    resp = TextResponse(pub.url, body=body, request=pub)
    assert mw.process_response(pub, resp, SimpleNamespace()) is resp           # everything else untouched


def test_account_section_outputs(tmp_path):
    sel = Selection.build(sections="plans,account", has_token=True)
    ents = _entities(sel, [Envelope(endpoint=ep, url=_prov(ep)["url"], status=200, body=ACCOUNT_BODIES[ep])
                           for ep in ACCOUNT_ENDPOINTS])
    ds = build_dataset(ents, sel)
    assert len(ds["account"]["records"]) == len(ACCOUNT_ENDPOINTS) and ds["meta"]["counts"]["account_records"] == 8
    names = {f.relative_to(tmp_path).as_posix() for f in write_outputs(ds, tmp_path)}
    assert {"csv/account.csv", "csv/account_items.csv", "json/account.json"} <= names
    rows = (tmp_path / "csv" / "account.csv").read_text("utf-8-sig")
    assert "account_wallet,200,credits_balance,8.88" in rows and "credits_per_dollar,18" in rows
    for secret in FAKE_PERSONAL:
        assert secret not in (tmp_path / "dataset.json").read_text("utf-8")
