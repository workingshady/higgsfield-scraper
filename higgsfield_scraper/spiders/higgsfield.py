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

from ..constants import ENDPOINTS
from ..items import RawResponseItem, to_item
from ..parsers import keep, parse_envelope
from ..raw import Envelope
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
            )
        self.selection = selection
        if "auth" in selection.sections and not self.token:
            self.logger.warning("section 'auth' requested but no token (--token / HF_TOKEN); those endpoints will 401")

    # ------------------------------------------------------------ requests
    def _request(self, endpoint: str, params: Optional[dict[str, str]] = None, auth: bool = False,
                 extra_headers: Optional[dict[str, str]] = None) -> scrapy.Request:
        base, _ = ENDPOINTS[endpoint]
        params = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{base}?{urlencode(params)}" if params else base
        headers = dict(extra_headers or {})
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return scrapy.Request(
            url, headers=headers, callback=self.parse_api, errback=self.on_error, dont_filter=True,
            meta={"endpoint": endpoint, "params": params, "handle_httpstatus_list": HANDLED_STATUSES},
        )

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
            self.logger.error("non-JSON response from %s (HTTP %s)", endpoint, response.status,
                              extra={"endpoint": endpoint, "status": response.status})
        env = Envelope(endpoint=endpoint, url=response.url, status=response.status, body=body, params=params,
                       fetched_at=datetime.now(timezone.utc))
        yield RawResponseItem(kind="raw_response", endpoint=endpoint, url=response.url, params=params,
                              status=response.status, fetched_at=env.fetched_at.isoformat(), body=body)
        if response.status != 200:
            level = self.logger.info if ENDPOINTS[endpoint][1] else self.logger.warning
            level("%s -> HTTP %s %s", endpoint, response.status, str(body)[:200],
                  extra={"endpoint": endpoint, "status": response.status})
            return
        entities = parse_envelope(env, self.selection)
        kept = [e for e in entities if keep(e, self.selection)]
        self.logger.info("%s %s -> %d entities (%d after filters)", endpoint, params or "", len(entities), len(kept),
                         extra={"endpoint": endpoint, "status": response.status})
        for e in kept:
            stats.inc_value(f"higgs/parsed/{e['kind']}")
            yield to_item(e)

    def on_error(self, failure):
        req = failure.request
        endpoint = req.meta.get("endpoint")
        self.crawler.stats.inc_value(f"higgs/request_errors/{endpoint}")
        self.logger.error("request failed for %s: %r", endpoint, failure.value, extra={"endpoint": endpoint})
