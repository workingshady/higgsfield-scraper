"""Spider for Higgsfield pricing APIs (no HTML parsing — every section comes from a JSON endpoint).

Run through the CLI (recommended):  python -m higgsfield_scraper scrape --sections all --plan-sets us
Or plain Scrapy:                    scrapy crawl higgsfield -a sections=plans,models -a plan_sets=ps_a3
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Iterator, Optional
from urllib.parse import urlencode

import scrapy

from ..constants import ACCOUNT_ENDPOINTS, ENDPOINTS
from ..items import RawResponseItem, to_item
from ..parsers import keep, parse_envelope
from ..raw import Envelope
from ..run.logging_setup import emit
from ..selection import Selection

HANDLED_STATUSES = [400, 401, 403, 404, 422]


class HiggsfieldSpider(scrapy.Spider):
    name = "higgsfield"
    allowed_domains = ["fnf-api-gw.higgsfield.ai", "pricing.higgsfield.ai"]
    custom_settings: dict[str, Any] = {}

    def __init__(self, selection: Optional[Selection] = None, token: Optional[str] = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.token = token or kwargs.get("token") or os.environ.get("HF_TOKEN") or None
        if selection is None:   # plain `scrapy crawl higgsfield -a key=value`
            selection = Selection.build(
                sections=kwargs.get("sections"), plan_sets=kwargs.get("plan_sets"),
                billing=kwargs.get("billing"), plan_types=kwargs.get("plan_types"),
                models=kwargs.get("models"), categories=kwargs.get("categories"),
                marketing_versions=kwargs.get("marketing_versions"), locale=kwargs.get("locale", "en"),
                include_hidden_plans=str(kwargs.get("include_hidden_plans", "")).lower() in ("1", "true", "yes"),
                include_raw_cost=str(kwargs.get("include_raw_cost", "")).lower() in ("1", "true", "yes"),
                usd_reference=kwargs.get("usd_reference", "plus:annual"), has_token=bool(self.token),
                logged_in_prices=str(kwargs.get("logged_in_prices", "")).lower() in ("1", "true", "yes"),
            )
        self.selection = selection
        if "auth" in selection.sections and not self._login_configured():
            emit(self.logger, "warning", "auth.token.missing",
                 "section 'auth' requested but no login (run `login`, or set HF_CLERK_CLIENT / HF_TOKEN); "
                 "those endpoints will 401")
        # opt-in login-only extras: never sent without a session (skipped with one warning each, never anonymously)
        for what, wanted in (("--logged-in-prices", selection.logged_in_prices),
                             ("section 'account'", "account" in selection.sections)):
            if wanted and not self._login_usable():
                emit(self.logger, "warning", "auth.skipped",
                     f"{what} needs a usable login (run `login` or set HF_CLERK_CLIENT / HF_TOKEN; never with "
                     f"--auth off); skipped")

    def _auth_mode(self) -> str:
        return getattr(getattr(self, "common", None), "auth", "auto")

    def _login_usable(self) -> bool:
        """For the opt-in login-only requests: the selection says a login is usable (has_token is False under
        --auth off / without a session), --auth is not off and a session is really configured."""
        return bool(self.selection.has_token) and self._auth_mode() != "off" and self._login_configured()

    def _login_configured(self) -> bool:
        try:
            from ..core.auth import TokenProvider
            return TokenProvider.from_env(self.token).configured
        except Exception:
            return bool(self.token)

    # ------------------------------------------------------------ requests
    def _request(self, endpoint: str, params: Optional[dict[str, str]] = None, auth: bool = False,
                 extra_headers: Optional[dict[str, str]] = None) -> scrapy.Request:
        base, _ = ENDPOINTS[endpoint]
        params = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{base}?{urlencode(params)}" if params else base
        headers = dict(extra_headers or {})
        meta = {"endpoint": endpoint, "params": params, "handle_httpstatus_list": HANDLED_STATUSES}
        if auth:
            # core.auth.AuthMiddleware adds the Bearer token (--token / HF_TOKEN / cached `login` / HF_CLERK_CLIENT),
            # mints fresh ~60 s tokens and retries once on 401. --auth off: never send one; required: skip if none.
            mode = getattr(getattr(self, "common", None), "auth", "auto")
            if mode != "off":
                meta["auth"] = "required" if mode == "required" else True
        return scrapy.Request(url, headers=headers, callback=self.parse_api, errback=self.on_error, dont_filter=True,
                              meta=meta)

    def _login_only_request(self, endpoint: str, params: Optional[dict[str, str]] = None) -> scrapy.Request:
        """Opt-in login-only request: always `auth="required"` (AuthMiddleware skips it rather than sending it
        anonymously); account bodies are never stored in the dev HTTP cache (AccountPrivacyMiddleware whitelists them
        before the http/ and raw/ archives)."""
        req = self._request(endpoint, params)
        req.meta["auth"] = "required"
        if endpoint in ACCOUNT_ENDPOINTS:
            req.meta["dont_cache"] = True
        return req

    def build_requests(self) -> Iterator[scrapy.Request]:
        sel = self.selection
        eps = sel.endpoints()
        if "plans" in eps:
            for key in sel.plan_set_keys:
                yield self._request("plans", {"with_localization": "true", "plan_set_key": key})
        if "compare" in eps:
            for key in sel.plan_set_keys:
                for period in sel.billing_periods:
                    if period == "quarterly":
                        continue
                    yield self._request("compare", {"plan_set_key": key, "billing_period": period,
                                                    "with_localization": "true"})
        if "plan_benefits" in eps:
            yield self._request("plan_benefits", {"locale": sel.locale}, extra_headers={"Accept-Language": sel.locale})
        if "job_costs" in eps:
            yield self._request("job_costs")
        if "pricing_config" in eps:
            explicit = [v for v in sel.marketing_versions if v not in ("latest", "all")]
            if "latest" in sel.marketing_versions or "all" in sel.marketing_versions:
                yield self._request("pricing_config", {"locale": sel.locale})          # every version (~3.8 MB)
            else:
                for v in explicit:
                    yield self._request("pricing_config", {"locale": sel.locale, "planVersion": v})
        for ep in ("credit_packages", "unlim_catalog", "credit_price", "adjustable_credits"):
            if ep in eps:
                yield self._request(ep, auth=True)
        # ---- opt-in extras (after every existing request, so the default request list is unchanged)
        if not (sel.logged_in_prices or "account" in sel.sections) or not self._login_usable():
            return
        if sel.logged_in_prices:
            if "plans" in eps:
                for key in sel.plan_set_keys:
                    yield self._login_only_request("plans_logged_in", {"with_localization": "true", "plan_set_key": key})
            if "job_costs" in eps:
                yield self._login_only_request("job_costs_logged_in")
        if "account" in sel.sections:
            for ep in ACCOUNT_ENDPOINTS:
                yield self._login_only_request(ep)

    async def start(self):  # Scrapy >= 2.13
        for r in self.build_requests():
            yield r

    def start_requests(self):  # older Scrapy
        yield from self.build_requests()

    # ------------------------------------------------------------- parsing
    def parse_api(self, response: scrapy.http.Response):
        endpoint, params = response.meta["endpoint"], response.meta["params"]
        stats = self.crawler.stats
        stats.inc_value(f"higgs/responses/{endpoint}/{response.status}")
        try:
            body: Any = json.loads(response.text)
        except ValueError:
            body = {"_non_json": response.text[:2000]}
            stats.inc_value("higgs/non_json_responses")
            emit(self.logger, "error", "page.invalid", f"non-JSON response from {endpoint} (HTTP {response.status})",
                 endpoint__name=endpoint, http__response__status_code=response.status,
                 request_id=response.meta.get("request_id"))
        env = Envelope(endpoint=endpoint, url=response.url, status=response.status, body=body, params=params,
                       fetched_at=datetime.now(timezone.utc))
        yield RawResponseItem(kind="raw_response", endpoint=endpoint, url=response.url, params=params,
                              status=response.status, fetched_at=env.fetched_at.isoformat(), body=body)
        if response.status != 200:
            emit(self.logger, "info" if ENDPOINTS[endpoint][1] else "warning", "page.fetched",
                 f"{endpoint} -> HTTP {response.status} {str(body)[:200]}", endpoint__name=endpoint,
                 http__response__status_code=response.status, request_id=response.meta.get("request_id"),
                 outcome="http_error", optional=bool(ENDPOINTS[endpoint][1]))
            return
        entities = parse_envelope(env, self.selection)
        kept = [e for e in entities if keep(e, self.selection)]
        emit(self.logger, "debug", "page.fetched",
             f"{endpoint} {params or ''} -> {len(entities)} entities ({len(kept)} after filters)",
             endpoint__name=endpoint, http__response__status_code=response.status,
             request_id=response.meta.get("request_id"), entities__count=len(entities), kept__count=len(kept),
             outcome="success")
        for e in kept:
            stats.inc_value(f"higgs/parsed/{e['kind']}")
            yield to_item(e)

    def on_error(self, failure):
        req = failure.request
        endpoint = req.meta.get("endpoint")
        from scrapy.exceptions import IgnoreRequest
        from scrapy.spidermiddlewares.httperror import HttpError
        if req.meta.get("auth") and failure.check(HttpError):
            # optional login-only endpoint answered with a server error after retries (e.g. /workspaces/credit-price
            # returns 500 for accounts without a team workspace): visible warning + stat, main data unaffected
            status = failure.value.response.status
            self.crawler.stats.inc_value(f"higgs/auth/http_error/{endpoint}/{status}")
            emit(self.logger, "warning", "auth.endpoint.failed",
                 f"login-only endpoint {endpoint} returned HTTP {status} (optional; skipped)",
                 endpoint__name=endpoint, http__response__status_code=status)
            return
        if req.meta.get("auth") and failure.check(IgnoreRequest):
            # login-only endpoint skipped because no session is configured (--auth required): expected, not an error
            self.crawler.stats.inc_value(f"higgs/auth/skipped/{endpoint}")
            emit(self.logger, "warning", "auth.skipped", f"skipped {endpoint}: no login configured",
                 endpoint__name=endpoint)
            return
        self.crawler.stats.inc_value(f"higgs/request_errors/{endpoint}")
        emit(self.logger, "debug" if req.meta.get("_gave_up") else "error", "external.call.failed",
             f"request failed for {endpoint}: {failure.value!r}", endpoint__name=endpoint,
             request_id=req.meta.get("request_id"), error__type=type(failure.value).__name__, url__full=req.url)
