"""Session tokens for login-only endpoints, refreshed automatically.

Two sources (never log either):
  * HF_TOKEN / --token        a Clerk session JWT (the `__session` cookie). Lives ~60 s; used until it expires.
  * HF_CLERK_CLIENT           the long-lived Clerk `__client` cookie (days/weeks). The provider mints a fresh session
                              JWT from it whenever the current one is <20 s from expiry — exactly what clerk-js does
                              in the browser. Login once in Chrome, copy `__client` into .env, done.

Clerk Frontend API is proxied at https://higgsfield.ai/_clerk (page config `clerkProxyUrl`):
  GET  /v1/client                         -> {response: {sessions: [...], last_active_session_id}}
  POST /v1/client/sessions/{sid}/tokens   -> {jwt}
No password is ever used or stored.

AuthMiddleware adds `Authorization: Bearer <jwt>` to requests whose meta has `auth=True` (or every API request when
the selection asks for it), and on a 401 refreshes the token once and retries the request.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

from scrapy.exceptions import IgnoreRequest

from ..constants import USER_AGENT
from ..run.logging_setup import emit

log = logging.getLogger(__name__)

CLERK_BASE = os.environ.get("HF_CLERK_URL", "https://higgsfield.ai/_clerk")
CLERK_JS_VERSION = "6.46.3"
CLERK_API_VERSION = "2026-11-18"          # verified against the live Clerk instance (clerk-js 6.46.3)
REFRESH_MARGIN_S = 20


class AuthError(Exception):
    pass


def jwt_exp(token: str) -> Optional[float]:
    """Expiry (unix seconds) from a JWT payload, without verifying the signature."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp"))
    except Exception:
        return None


class TokenProvider:
    def __init__(self, token: Optional[str] = None, client_cookie: Optional[str] = None,
                 clerk_base: str = CLERK_BASE, opener=None):
        self._token = token or None
        self._client = client_cookie or None
        self._base = clerk_base.rstrip("/")
        self._sid: Optional[str] = None
        self._lock = threading.Lock()
        self._open = opener or urllib.request.urlopen
        self.refreshes = 0
        self.last_error: Optional[str] = None

    @classmethod
    def from_env(cls, token: Optional[str] = None) -> "TokenProvider":
        """Sources, in order: --token/HF_TOKEN (static JWT), cached login (runs/.auth/clerk_client.json, written by
        `python -m higgsfield_scraper login`), HF_CLERK_CLIENT (cookie pasted from the browser)."""
        client = None
        try:
            from .auth_login import load_cached_client
            cached = load_cached_client()
            client = (cached or {}).get("client_cookie")
        except Exception:
            client = None
        return cls(token=token or os.environ.get("HF_TOKEN"), client_cookie=client or os.environ.get("HF_CLERK_CLIENT"))

    @property
    def configured(self) -> bool:
        return bool(self._token or self._client)

    @property
    def can_refresh(self) -> bool:
        return bool(self._client)

    def expires_in(self) -> Optional[float]:
        exp = jwt_exp(self._token) if self._token else None
        return None if exp is None else exp - time.time()

    # ------------------------------------------------------------ public
    def get(self, force_refresh: bool = False) -> Optional[str]:
        with self._lock:
            left = self.expires_in()
            fresh = self._token and (left is None or left > REFRESH_MARGIN_S)
            if fresh and not force_refresh:
                return self._token
            if self.can_refresh:
                self._token = self._mint()
                return self._token
            if self._token and left is not None and left <= 0:
                self.last_error = "session token expired and no HF_CLERK_CLIENT cookie to refresh it"
                emit(log, "warning", "auth.token.expired", self.last_error, auth__can_refresh=False)
                return None
            return self._token

    def status(self) -> dict:
        info = {"configured": self.configured, "source": "clerk_client_cookie" if self._client else
                ("static_token" if self._token else None), "refreshes": self.refreshes}
        try:
            tok = self.get()
            info.update(ok=bool(tok), expires_in_s=round(self.expires_in() or 0, 1) if tok else None,
                        session_id=self._sid, error=self.last_error)
        except AuthError as e:
            info.update(ok=False, error=str(e))
        return info

    # ----------------------------------------------------------- private
    def _req(self, method: str, path: str) -> dict:
        url = (f"{self._base}{path}{'&' if '?' in path else '?'}"
               f"__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}")
        req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None, headers={
            "Cookie": f"__client={self._client}", "Origin": "https://higgsfield.ai", "Referer": "https://higgsfield.ai/",
            "User-Agent": USER_AGENT, "Accept": "application/json",
            **({"Content-Type": "application/x-www-form-urlencoded"} if method == "POST" else {})})
        try:
            with self._open(req, timeout=20) as r:
                for h in (r.headers.get_all("Set-Cookie") if hasattr(r.headers, "get_all") else None) or []:
                    name, _, rest = h.partition("=")                 # follow server-side __client rotation
                    val = rest.split(";", 1)[0]
                    if name.strip() == "__client" and val and val != self._client:
                        self._client = val
                        self._persist_rotation()
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code in (401, 404):
                self._sid = None                                     # session ended/revoked: rediscover next time
            raise AuthError(f"Clerk {method} {path.split('?')[0]} -> HTTP {e.code} "
                            f"({'cookie expired or invalid — log in again and update HF_CLERK_CLIENT' if e.code in (401, 403, 404) else 'unexpected'})") from None
        except Exception as e:
            raise AuthError(f"Clerk {method} {path.split('?')[0]} failed: {e.__class__.__name__}") from None

    def _persist_rotation(self) -> None:
        try:
            from .auth_login import load_cached_client, save_cached_client
            cached = load_cached_client()
            if cached:
                save_cached_client({**cached, "client_cookie": self._client})
        except Exception:
            pass

    def _mint(self) -> str:
        if not self._sid:
            client = self._req("GET", "/v1/client")
            body = client.get("response") or client
            sessions = [s for s in body.get("sessions") or [] if s.get("status") in (None, "active")]
            self._sid = body.get("last_active_session_id") or (sessions[0]["id"] if sessions else None)
            if not self._sid:
                self.last_error = "no active Clerk session for this __client cookie (log in again)"
                raise AuthError(self.last_error)
        data = self._req("POST", f"/v1/client/sessions/{self._sid}/tokens")
        jwt = data.get("jwt") or (data.get("response") or {}).get("jwt")
        if not jwt:
            self.last_error = "Clerk returned no jwt"
            raise AuthError(self.last_error)
        self.refreshes += 1
        self.last_error = None
        expires_in = round((jwt_exp(jwt) or time.time()) - time.time())
        emit(log, "info", "auth.token.refreshed",
             f"auth: minted fresh session token (expires in {expires_in}s, refresh #{self.refreshes})",
             expires_in_s=expires_in, refresh__count=self.refreshes)
        return jwt


class AuthMiddleware:
    """Downloader middleware (priority 560): attach bearer tokens, refresh+retry once on 401."""

    def __init__(self, crawler):
        self.crawler = crawler
        self.provider: Optional[TokenProvider] = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _prov(self) -> Optional[TokenProvider]:
        if self.provider is None:
            sp = self.crawler.spider
            self.provider = getattr(sp, "token_provider", None) or TokenProvider.from_env(getattr(sp, "token", None))
        return self.provider

    def process_request(self, request, spider=None):
        if not request.meta.get("auth"):
            return None
        prov = self._prov()
        if not prov or not prov.configured:
            if request.meta.get("auth") == "required":
                self.crawler.stats.inc_value("higgs/auth/skipped_no_token")
                raise IgnoreRequest(f"login required for {request.meta.get('endpoint')} (set HF_CLERK_CLIENT or --token)")
            return None
        try:
            tok = prov.get()
        except AuthError as e:
            self.crawler.stats.inc_value("higgs/auth/errors")
            emit(log, "error", "auth.refresh.failed", f"auth: {e}", endpoint__name=request.meta.get("endpoint"),
                 error__type=type(e).__name__)
            if request.meta.get("auth") == "required":
                raise IgnoreRequest(str(e)) from None
            return None
        if tok:
            request.headers["Authorization"] = f"Bearer {tok}"
            self.crawler.stats.inc_value("higgs/auth/requests")
        return None

    def process_response(self, request, response, spider=None):
        if response.status == 401 and request.meta.get("auth") and not request.meta.get("auth_retried"):
            prov = self._prov()
            if prov and prov.can_refresh:
                try:
                    tok = prov.get(force_refresh=True)
                    self.crawler.stats.inc_value("higgs/auth/retried_401")
                    emit(log, "warning", "auth.token.expired",
                         f"auth: 401 on {request.meta.get('endpoint')} — refreshed token, retrying once",
                         endpoint__name=request.meta.get("endpoint"), request_id=request.meta.get("request_id"),
                         auth__can_refresh=True)
                    new = request.replace(dont_filter=True)
                    new.meta["auth_retried"] = True
                    new.headers["Authorization"] = f"Bearer {tok}"
                    return new
                except AuthError as e:
                    emit(log, "error", "auth.refresh.failed", f"auth: refresh after 401 failed: {e}",
                         endpoint__name=request.meta.get("endpoint"), error__type=type(e).__name__)
            elif prov and prov.configured:
                emit(log, "error", "auth.token.expired",
                     f"auth: 401 on {request.meta.get('endpoint')} — token expired; run `login` or set HF_CLERK_CLIENT "
                     "for automatic refresh", endpoint__name=request.meta.get("endpoint"), auth__can_refresh=False)
        return response
