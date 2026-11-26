"""AccountSpider: the logged-in user's own snapshot (balances, plan, subscription, …), optionally their jobs
(/jobs/accessible) and the public pricing needed to compare estimates with actual charges. GET only.

Without a login session the spider makes no request, logs an error and the run ends with status `failure`
(exit code 1): nothing about the account can be read anonymously. With a session that turns out to be unusable
(refresh failed / every core endpoint non-200) the run is also `failure`.
"""
from __future__ import annotations

import json
from typing import Any, Iterator, Optional

from ...core.api_spider import BaseApiSpider
from ...run.logging_setup import emit
from . import endpoints as ep
from .dataset import NO_SESSION_STAT
from .redaction import AccountRedactionMiddleware

NO_SESSION_MSG = ("the account scraper needs a login session: run `python -m higgsfield_scraper login` or set "
                  "HF_CLERK_CLIENT (or HF_EMAIL/HF_PASSWORD) in .env — nothing was fetched")


class AccountSpider(BaseApiSpider):
    name = "account"
    scraper_name = "account"
    primary_kinds = ("account_job",)
    REDACTION_MW = "higgsfield_scraper.scrapers.account.redaction.AccountRedactionMiddleware"

    @classmethod
    def update_settings(cls, settings) -> None:
        """Add the account redaction middleware to the project's DOWNLOADER_MIDDLEWARES (a plain custom_settings
        dict would REPLACE the project's middlewares — auth, http archive, access log — in this Scrapy version)."""
        super().update_settings(settings)
        mws = dict(settings.getdict("DOWNLOADER_MIDDLEWARES"))
        mws[cls.REDACTION_MW] = AccountRedactionMiddleware.PRIORITY
        settings.set("DOWNLOADER_MIDDLEWARES", mws, priority="spider")

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self.no_session = False
        self.ok_endpoints: set[str] = set()
        self._cursors: set[str] = set()

    # ------------------------------------------------------------ first requests
    def build_requests(self) -> Iterator:
        if not self.authed:
            self.no_session = True
            stats = getattr(getattr(self, "crawler", None), "stats", None)
            if stats is not None:
                stats.set_value(NO_SESSION_STAT, 1) if hasattr(stats, "set_value") else stats.inc_value(NO_SESSION_STAT)
            emit(self.logger, "error", "request.skipped", NO_SESSION_MSG, reason="no_session")
            return
        for key, (path, _part) in ep.SNAPSHOT_ENDPOINTS.items():
            yield self.api_request(key, path, auth="required", priority=10)
        if self.selection.with_jobs:
            yield self._jobs_page(None)
        if self.selection.compare_estimate:
            for key, (path, params) in ep.PRICING_ENDPOINTS.items():
                # public, but sent with the session: logged-in users see extra cost rows (e.g. magi_2)
                yield self.api_request(key, path, params, auth=True, priority=5)

    def _jobs_page(self, cursor: Optional[str]):
        size = self.page_size(ep.JOBS_DEFAULT_SIZE, ep.JOBS_MAX_SIZE)
        budget = self.budget_left()
        if budget is not None:
            size = max(1, min(size, budget))
        params = {"size": size, "cursor": cursor, "job_set_type": list(self.selection.job_types) or None}
        return self.api_request(ep.JOBS_ENDPOINT, ep.JOBS, params, auth="required", priority=1)

    def parse_api(self, response, **kw):
        """Base parsing + a clear limit when bot protection (e.g. a Cloudflare challenge) answers an account
        request: recorded in meta.limits_hit, never retried or evaded; the run ends `partial`."""
        if response.status != 200:
            try:
                blocked = json.loads(response.text).get("_blocked")
            except (ValueError, AttributeError):
                blocked = None
            if blocked and "datadome" not in blocked:
                self.crawler.stats.inc_value("higgs/account/bot_protection")
                self.limit_hit(f"bot protection ({blocked}) on {response.meta.get('endpoint')} — HTTP "
                               f"{response.status}, no evasion attempted")
        yield from super().parse_api(response, **kw)

    # ------------------------------------------------------------ follow-ups
    def follow_up(self, env, entities, response) -> Iterator:
        self.ok_endpoints.add(env.endpoint)
        if env.endpoint != ep.JOBS_ENDPOINT:
            return
        body = env.body if isinstance(env.body, dict) else {}
        jobs = body.get("jobs") or []
        if not jobs or not body.get("has_more", bool(body.get("cursor") or body.get("next_cursor"))):
            return
        if self.budget_left() == 0:
            self.limit_hit(f"max_items={self.common.max_items} reached")
            return
        # the API returns {jobs, has_more} without a cursor; the web app pages job lists by the last created_at
        nxt = body.get("next_cursor") or body.get("cursor") or jobs[-1].get("created_at")
        if nxt in (None, ""):
            return
        if str(nxt) in self._cursors:
            emit(self.logger, "warning", "listing.cursor_repeated", f"account_jobs: cursor repeated, stopping",
                 listing=ep.JOBS_ENDPOINT)
            return
        self._cursors.add(str(nxt))
        if not self.page_allowed(ep.JOBS_ENDPOINT):
            return
        yield self._jobs_page(str(nxt))

    # ------------------------------------------------------------ outcome
    def closed(self, reason: str) -> None:
        """Turn "nothing about the account was read" into a failed run (export_result.ok=False -> status failure)."""
        problem = None
        if self.no_session:
            problem = NO_SESSION_MSG
        elif not (self.ok_endpoints & ep.CORE_ENDPOINTS):
            problem = ("no account data: every core account endpoint (/user, /workspaces/wallet) failed — the "
                       "session is probably expired or invalid (run `python -m higgsfield_scraper login`)")
        if problem:
            prev = getattr(self, "export_result", None) or {}
            self.export_result = {**prev, "ok": False, "error": problem}
            emit(self.logger, "error", "run.account.failed", problem)
