"""account scraper: registry, privacy whitelist, x100 conversion, comparison math, behaviour without a session.
All fixtures in tests/fixtures/account/ are SYNTHETIC (no real account data)."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy.http import Request, TextResponse

from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.account import SCRAPER
from higgsfield_scraper.scrapers.account import endpoints as ep
from higgsfield_scraper.scrapers.account.compare import TOLERANCE, compare_job, estimator_params, summarize
from higgsfield_scraper.scrapers.account.dataset import NO_SESSION_STAT, build_dataset, write_outputs
from higgsfield_scraper.scrapers.account.options import Selection, selection_from_dict
from higgsfield_scraper.scrapers.account.parsers import parse_envelope, units_to_credits
from higgsfield_scraper.scrapers.account.redaction import (AccountRedactionMiddleware, media_stub, sanitize_body)
from higgsfield_scraper.validation import validate_entity

FIX = Path(__file__).parent / "fixtures" / "account"
JOB_COSTS = Path(__file__).parent / "fixtures" / "raw" / "job_costs.json"
SECRETS = ("someone@example.invalid", "user_SYNTHETIC123", "ws_SYNTHETIC", "sub_SYNTH", "job-SYNTHETIC-1",
           "set-SYNTHETIC-1", "Jane Synthetic", "jsyn", "example.invalid", "a secret synthetic prompt", "price_SYNTH",
           "sc_SYNTH", "ZZ-1", "tr\"")


def load(name: str) -> Envelope:
    return Envelope.load(FIX / name)


def entities(sel: Selection, with_costs: bool = False) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for p in sorted(FIX.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            out[e["kind"]].append(validate_entity(e))
    if with_costs:
        env = Envelope.load(JOB_COSTS)
        env = Envelope(endpoint="account_job_costs", url=env.url, status=200, body=env.body, fetched_at=env.fetched_at)
        for e in parse_envelope(env, sel):
            out[e["kind"]].append(validate_entity(e))
    return out


def no_secrets(obj) -> None:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    leaked = [s for s in SECRETS if s in text]
    assert not leaked, f"personal data leaked: {leaked}"


# ------------------------------------------------------------------ registry / options
def test_registered_opt_in_and_kinds_prefixed():
    assert registry.get("account") is SCRAPER and "account" in registry.available()
    assert registry.DEFAULT_SCRAPER == "pricing"
    assert all(k.startswith("account_") for k in SCRAPER.model_by_kind)
    assert SCRAPER.personal_data and SCRAPER.media_urls is None
    assert ep.CORE_ENDPOINTS.isdisjoint(SCRAPER.optional_endpoints)


def test_options_roundtrip_and_validation():
    sel = Selection.build(with_jobs=True, compare_estimate="true", job_types="a,b,a")
    assert sel.job_types == ("a", "b") and sel.with_prompts is False
    assert selection_from_dict(sel.to_dict()) == sel and "with_profiles" not in sel.to_dict()
    with pytest.raises(ValueError, match="needs --with-jobs"):
        Selection.build(compare_estimate=True)
    # the core --with-profiles opt-in can never switch the core archive redaction off
    assert Selection.build(with_jobs=True).with_profiles is False


# ------------------------------------------------------------------ privacy
def test_snapshot_whitelist_drops_identity():
    body = load("user.json").body
    clean = sanitize_body("account_user", body)
    assert "email" not in clean and "id" not in clean and "workspace_id" not in clean and "consents" not in clean
    assert clean["plan_type"] == "free" and clean["package_credits"] == 8.88
    meta = sanitize_body("account_user_meta", load("user_meta.json").body)
    assert meta == {"cohort": "c_synthetic"}                         # location dropped
    sub = sanitize_body("account_subscription", load("subscription.json").body)
    assert "subscription_id" not in sub and "email_type" not in sub and sub["status"] == "active"
    top = sanitize_body("account_auto_top_up", load("auto_top_up.json").body)
    assert top["options"] == [{"credits": 500, "price": 25}]           # Stripe price id scrubbed


def test_jobs_whitelist_hashes_ids_and_redacts_prompts_and_media():
    body = load("jobs_p1.json").body
    clean = sanitize_body("account_jobs", body)
    no_secrets(clean)
    j = clean["jobs"][0]
    assert set(j) <= {"job_id", "job_set_key", "job_set_type", "status", "created_at", "cost", "params"}
    assert len(j["job_id"]) == 16 and j["job_id"] != "job-SYNTHETIC-1"
    assert j["params"]["prompt"] == "<redacted:25 chars>" and "seed" not in j["params"]
    assert j["params"]["medias"] == [{"role": "start_image", "data": {"type": "image", "url": "<media>.png"}}]
    assert sanitize_body("account_jobs", clean) == clean                # idempotent (normalize re-parses raw/)
    kept = sanitize_body("account_jobs", body, with_prompts=True)
    assert kept["jobs"][0]["params"]["prompt"] == "a secret synthetic prompt"
    assert media_stub("https://x.invalid/v/clip.MP4?sig=1") == "<media>.mp4"


def test_redaction_middleware_rewrites_archived_bodies():
    class Sp:
        scraper_name = "account"
        selection = Selection.build(with_jobs=True)

    mw = AccountRedactionMiddleware()
    env = load("jobs_p1.json")
    req = Request(env.url, meta={"endpoint": "account_jobs"})
    assert mw.process_request(req, Sp()) is None and req.meta["dont_cache"] is True
    resp = TextResponse(env.url, body=json.dumps(env.body).encode(), encoding="utf-8", request=req, status=200)
    out = mw.process_response(req, resp, Sp())
    no_secrets(json.loads(out.body))
    err = TextResponse(env.url, body=b'{"detail": "x", "user_id": "user_SYNTHETIC123"}', request=req, status=401)
    assert json.loads(mw.process_response(req, err, Sp()).body) == {"detail": "x"}
    html = TextResponse(env.url, body=b"<html>someone@example.invalid</html>", request=req, status=200)
    assert b"example.invalid" not in mw.process_response(req, html, Sp()).body

    class Other:
        scraper_name = "community"
    assert mw.process_response(req, resp, Other()) is resp           # other scrapers untouched
    pub = Request(env.url, meta={"endpoint": "account_job_costs"})
    assert mw.process_response(pub, resp, Sp()) is resp               # public pricing untouched


def test_redaction_middleware_is_registered_for_the_account_spider_only():
    from scrapy.settings import Settings

    from higgsfield_scraper.scrapers.account.spider import AccountSpider
    s = Settings({"DOWNLOADER_MIDDLEWARES": {"a.B": 560, "c.D": 580}})
    AccountSpider.update_settings(s)
    mws = s.getdict("DOWNLOADER_MIDDLEWARES")
    assert mws["a.B"] == 560 and mws["c.D"] == 580                     # project middlewares kept
    assert mws[AccountSpider.REDACTION_MW] == 582


# ------------------------------------------------------------------ parsing / x100
def test_units_to_credits():
    assert units_to_credits(888) == Decimal("8.88") and units_to_credits(112) == Decimal("1.12")
    assert units_to_credits(0) == Decimal("0.00") and units_to_credits(None) is None
    assert units_to_credits(True) is None


def test_snapshot_dataset_and_wallet_conversion():
    sel = Selection.build()
    ds = build_dataset(entities(sel), sel, RunMeta(run_id="r", label="t", common=CommonOptions()))
    snap = ds["snapshot"]
    w = snap["wallet"]
    assert w["credits_balance_units"] == 888 and w["credits_balance"] == "8.88"
    assert w["total_credits"] == "10.38" and w["bonus_credits"] == "1.50" and w["expire_days"] == 90
    assert w["scoped_credits"] == [{"scope": "seedance", "balance": 500, "expires_at": "2026-12-31T00:00:00Z"}]
    assert snap["balances"]["package_credits"] == "8.88" and snap["plan"]["cohort"] == "c_synthetic"
    assert snap["subscription"]["renewal_date"] == "2026-12-01T00:00:00+00:00"
    assert snap["unlimited_grants"] == [{"job_set_type": "nano_banana_2", "status": "active"}]
    assert snap["auto_top_up"]["credits_per_dollar"] == 18
    assert "generation_seconds" in snap["parts_missing"]
    no_secrets(ds)


def test_jobs_parsed_with_actual_credits():
    sel = Selection.build(with_jobs=True)
    ents = entities(sel)
    jobs = {j["job_set_type"]: j for j in ents["account_job"]}
    j = jobs["seedance_2_0"]
    assert j["cost_units"] == 2250 and j["actual_credits"] == "22.50"
    assert j["resolution"] == "720p" and j["duration"] == 5 and j["model"] == "seedance_2_0"
    assert j["input_images"] == 1 and j["input_videos"] == 0
    assert j["prompt_chars"] == 25 and j["prompt"] is None
    assert j["created_at"].startswith("2025-11-26T09:40:00")
    no_secrets(ents)
    sel2 = Selection.build(with_jobs=True, with_prompts=True)
    j2 = {j["job_set_type"]: j for j in entities(sel2)["account_job"]}["seedance_2_0"]
    assert j2["prompt"] == "a secret synthetic prompt"


def test_non_200_yields_nothing():
    assert parse_envelope(load("unauthorized.json"), Selection.build()) == []


# ------------------------------------------------------------------ comparison math
def test_compare_job_math_and_comparability():
    job = {"job_id": "j", "job_set_type": "m", "status": "completed", "actual_credits": "22.50", "params": {}}
    r = compare_job(job, {"status": "exact", "credits": 22.5})
    assert r["comparable"] and r["match"] and r["diff"] == Decimal("0") and r["ratio"] == Decimal("1")
    r = compare_job(job, {"status": "approximate", "credits": 12.5})
    assert r["comparable"] and r["match"] is False and r["diff"] == Decimal("10.0000")
    assert r["ratio"] == Decimal("1.8000")
    r = compare_job(job, {"status": "exact", "credits": 22.5 - float(TOLERANCE)})
    assert r["match"] is True                                          # within one cost unit
    assert compare_job({**job, "status": "failed"}, {"status": "exact", "credits": 1})["comparable"] is False
    assert compare_job(job, {"status": "unpriced", "credits": None})["not_comparable_reason"].startswith("estimator")
    assert compare_job({**job, "params": {"use_unlim": True}}, {"status": "exact", "credits": 22.5})["match"] is None
    assert compare_job(job, None)["estimator_status"] == "skipped"
    groups = summarize([compare_job(job, {"status": "exact", "credits": 22.5}),
                        compare_job(job, {"status": "approximate", "credits": 12.5}),
                        compare_job({**job, "status": "failed"}, {"status": "exact", "credits": 1})])
    assert groups == [{"job_set_type": "m", "jobs": 3, "comparable": 2, "matches": 1, "match_rate": 0.5,
                       "exact_estimates": 2, "approximate_estimates": 1, "unpriced": 0,
                       "mean_diff": Decimal("5.0000"), "total_actual_credits": Decimal("45.0000"),
                       "total_estimated_credits": Decimal("35.0000")}]


def test_estimator_params_expand_redacted_prompt_length():
    assert estimator_params({"text": "<redacted:7 chars>", "a": 1}) == {"text": "xxxxxxx", "a": 1}


def test_full_comparison_with_real_estimator_and_csv_completeness(tmp_path):
    sel = Selection.build(with_jobs=True, compare_estimate=True)
    ds = build_dataset(entities(sel, with_costs=True), sel, RunMeta(run_id="r", label="t", common=CommonOptions()))
    rows = {c["job_set_type"]: c for c in ds["estimate_comparison"]}
    assert rows["seedance_2_0"]["estimated_credits"] == "22.5000" and rows["seedance_2_0"]["match"] is True
    assert rows["nano_banana_2_1"]["comparable"] is False                 # failed job (refunded)
    assert ds["summary"]["comparable"] == 1 and ds["summary"]["match_rate"] == 1.0
    assert ds["pricing_basis"]["priced_models"]
    write_outputs(ds, tmp_path)
    md = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "| seedance_2_0 | 1 | 1 | 1 | 100% |" in md
    checks = {"account_snapshot": [ds["snapshot"]], "account_jobs": ds["jobs"],
              "estimate_comparison": ds["estimate_comparison"], "comparison_summary": ds["comparison_summary"]}
    for table, objects in checks.items():
        with (tmp_path / "csv" / f"{table}.csv").open(encoding="utf-8-sig", newline="") as f:
            rdr = list(csv.DictReader(f))
        cols = set(rdr[0].keys()) if rdr else set()
        assert len(rdr) == len(objects), table
        missing = {k for o in objects for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{table}.csv misses {sorted(missing)[:10]}"
    for p in tmp_path.rglob("*.*"):
        assert not any(s in p.read_text(encoding="utf-8-sig") for s in SECRETS if s != "tr\""), p


# ------------------------------------------------------------------ spider / no session
class _Stats:
    def __init__(self):
        self.d = {}

    def inc_value(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n

    def set_value(self, k, v):
        self.d[k] = v


class _Crawler:
    def __init__(self):
        self.stats = _Stats()


def make_spider(common: CommonOptions | None = None, **sel):
    from higgsfield_scraper.scrapers.account.spider import AccountSpider
    sp = AccountSpider(selection=Selection.build(**sel), common=common or CommonOptions(auth="off"))
    sp.crawler = _Crawler()
    return sp


def test_no_session_makes_no_request_and_fails_cleanly():
    sp = make_spider(with_jobs=True, compare_estimate=True)
    assert list(sp.build_requests()) == []
    assert sp.no_session and sp.crawler.stats.d[NO_SESSION_STAT] == 1
    sp.closed("finished")
    assert sp.export_result["ok"] is False and "login session" in sp.export_result["error"]
    sel = Selection.build()
    ds = build_dataset({}, sel, RunMeta(run_id="r", common=CommonOptions(), stats={NO_SESSION_STAT: 1}))
    assert ds["snapshot"] is None and any("no login session" in w for w in ds["meta"]["warnings"])


def test_requests_with_session_are_get_and_login_only(monkeypatch):
    from higgsfield_scraper.scrapers.account.spider import AccountSpider
    monkeypatch.setattr(AccountSpider, "authed", property(lambda self: True))
    reqs = list(make_spider(CommonOptions(auth="auto", max_items=5), with_jobs=True, compare_estimate=True,
                            job_types="seedance_2_0").build_requests())
    assert all(r.method == "GET" for r in reqs)
    by = {r.meta["endpoint"]: r for r in reqs}
    assert set(ep.SNAPSHOT_ENDPOINTS) | {"account_jobs"} | set(ep.PRICING_ENDPOINTS) == set(by)
    assert all(by[k].meta["auth"] == "required" for k in list(ep.SNAPSHOT_ENDPOINTS) + ["account_jobs"])
    assert "size=5" in by["account_jobs"].url and "job_set_type=seedance_2_0" in by["account_jobs"].url
    reqs = list(make_spider(CommonOptions(auth="auto")).build_requests())
    assert {r.meta["endpoint"] for r in reqs} == set(ep.SNAPSHOT_ENDPOINTS)   # snapshot only by default


def respond(sp, fixture: str):
    env = load(fixture)
    req = Request(env.url, meta={"endpoint": env.endpoint, "params": env.params})
    resp = TextResponse(env.url, body=json.dumps(env.body).encode(), encoding="utf-8", request=req, status=env.status)
    out = list(sp.parse_api(resp))
    return [o for o in out if not isinstance(o, Request)], [o for o in out if isinstance(o, Request)]


def test_jobs_pagination_cursor_budget_and_core_failure():
    sp = make_spider(with_jobs=True)
    items, reqs = respond(sp, "jobs_p1.json")
    assert len(reqs) == 1 and "cursor=1764140000.0" in reqs[0].url
    _, reqs = respond(sp, "jobs_p2.json")
    assert not reqs
    sp.closed("finished")                                              # jobs only, no /user or wallet -> failure
    assert sp.export_result["ok"] is False
    sp = make_spider(CommonOptions(auth="off", max_items=2), with_jobs=True)
    items, reqs = respond(sp, "jobs_p1.json")
    assert not reqs and any("max_items=2" in x for x in sp.limits_hit)
    sp = make_spider()
    respond(sp, "user.json")
    sp.export_result = {"ok": True}
    sp.closed("finished")
    assert sp.export_result == {"ok": True}


def test_stale_period_end_is_not_a_renewal():
    from higgsfield_scraper.scrapers.account.parsers import subscription_section
    s = {"status": "active", "current_period_end": "2026-09-08T07:10:35Z"}
    assert subscription_section(s, "2026-11-26T10:00:00+00:00")["renewal_date"] is None
    assert subscription_section(s, "2026-09-01T00:00:00+00:00")["renewal_date"] == "2026-09-08T07:10:35+00:00"
    assert subscription_section({**s, "cancel_at": "2026-09-08"}, "2026-09-01T00:00:00+00:00")["renewal_date"] is None


def test_bot_protection_is_recorded_not_evaded():
    class Sp:
        scraper_name = "account"
        selection = Selection.build(with_jobs=True)

    mw = AccountRedactionMiddleware()
    url = "https://fnf-api-gw.higgsfield.ai/fnf/jobs/accessible?size=20"
    req = Request(url, meta={"endpoint": "account_jobs", "params": {"size": "20"}})
    cf = TextResponse(url, body=b"<html>challenge</html>", request=req, status=403,
                      headers={"cf-mitigated": "challenge", "Content-Type": "text/html"})
    out = mw.process_response(req, cf, Sp())
    assert json.loads(out.body)["_blocked"] == "cloudflare challenge" and b"<html>" not in out.body
    dd = TextResponse(url, body=b"<html>captcha-delivery.com</html>", request=req, status=403)
    assert "datadome" in json.loads(mw.process_response(req, dd, Sp()).body)["_blocked"]   # core stop still works
    sp = make_spider(with_jobs=True)
    list(sp.parse_api(out))
    assert any("cloudflare challenge" in x and "no evasion" in x for x in sp.limits_hit)
