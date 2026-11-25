"""Email + password login against Higgsfield's Clerk instance -> long-lived `__client` cookie.

Pure stdlib (urllib + http.cookiejar). Secrets (password, cookies, JWTs) are never logged or put in exception text.

Clerk Frontend API (FAPI) for higgsfield.ai is served through the first-party proxy https://higgsfield.ai/_clerk
(also directly at https://clerk.higgsfield.ai, same instance ins_2uom704qq93kpbzVLeQWP2lyRh7). Every FAPI call carries
the query params clerk-js 6.46.3 adds (`__clerk_api_version=2026-11-18&_clerk_js_version=6.46.3`), an
`Origin: https://higgsfield.ai` header, and form-encoded bodies for POST. No `Clerk-Proxy-Url` header is needed.

Sign-in sequence (mirrors clerk-js `SignIn.create({identifier, password})`):

  1. GET  /v1/client                       -> sets a fresh, anonymous `__client` cookie (rotating; Max-Age 10 y)
  2. POST /v1/client/sign_ins              body: identifier=<email>&strategy=password&password=<pw>
       response: {"response": <SignIn>, "client": <Client>}
       SignIn.status == "complete"  -> SignIn.created_session_id is the new session; Set-Cookie rotates `__client`
       other statuses (needs_first_factor / needs_second_factor / needs_client_trust / needs_protect_check / ...) or
       errors (captcha_*, form_password_incorrect, form_password_pwned, user_locked, strategy_for_user_invalid ...)
       are surfaced as LoginBlocked / LoginFailed.
       VERIFIED 2026-11-25 for the owner's account from a fresh (untrusted) client: password accepted, status
       "needs_second_factor" with supported_second_factors=[email_code] (Clerk client-trust / new-device check;
       the instance itself has no MFA). See login_with_password(code_callback=...) for the email-code step.
  3. POST /v1/client/sessions/{sid}/tokens  (empty form body)        -> {"object": "token", "jwt": "<session JWT>"}
       Repeat 3 whenever the JWT (≈60 s) is near expiry; only the `__client` cookie is needed (no password).

Bot protection: the instance has Turnstile configured (display_config.captcha_*), but clerk-js only requests a
captcha token for sign-in when `signUpIfMissing` is set; sign-up always needs one. Clerk "Protect" may still flag a
sign-in with `needs_protect_check`, which a script cannot answer -> LoginBlocked.

Cached cookie file: runs/.auth/clerk_client.json  {"client_cookie", "expires_at", "session_id", "saved_at"}.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

CLERK_BASE = os.environ.get("HF_CLERK_URL", "https://higgsfield.ai/_clerk")
CLERK_JS_VERSION = "6.46.3"
CLERK_API_VERSION = "2026-11-18"
ORIGIN = "https://higgsfield.ai"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CACHE_PATH = Path(__file__).resolve().parents[2] / "runs" / ".auth" / "clerk_client.json"

# SignIn statuses / error codes that need a human (captcha, emailed code, MFA, device trust, ...).
_BLOCKING_STATUSES = {"needs_first_factor", "needs_second_factor", "needs_client_trust", "needs_protect_check",
                      "needs_new_password", "needs_identifier"}
_BLOCKING_CODES = ("captcha", "protect_check", "client_trust", "verification", "strategy_for_user_invalid",
                   "form_password_pwned", "user_locked", "sign_in_not_allowed", "not_allowed_access")


class LoginError(Exception):
    """Base class. `.code` is Clerk's error code / SignIn status (no secrets)."""

    def __init__(self, message: str, code: Optional[str] = None, http_status: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class LoginBlocked(LoginError):
    """Login needs something a script must not do: captcha, email code, MFA, device trust, password reset, lockout."""


class LoginFailed(LoginError):
    """Wrong credentials, unexpected response, network error."""


class ClerkClient:
    """Minimal FAPI client with its own cookie jar (holds `__client`, `__client_uat*`, `__cf_bm`)."""

    def __init__(self, base: str = CLERK_BASE, client_cookie: Optional[str] = None, timeout: float = 20):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self._seed = client_cookie  # sent explicitly until the server rotates it into the jar

    # ------------------------------------------------------------------ http
    def request(self, method: str, path: str, form: Optional[dict] = None) -> tuple[int, dict]:
        """Return (status, json). HTTP errors are returned, not raised; network errors raise LoginFailed."""
        sep = "&" if "?" in path else "?"
        url = (f"{self.base}/v1{path}{sep}__clerk_api_version={CLERK_API_VERSION}"
               f"&_clerk_js_version={CLERK_JS_VERSION}")
        headers = {"Origin": ORIGIN, "Referer": ORIGIN + "/", "User-Agent": USER_AGENT, "Accept": "application/json"}
        data = None
        if method != "GET":
            data = urllib.parse.urlencode({k: v for k, v in (form or {}).items() if v is not None}).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self._seed and not self.client_cookie_from_jar():
            headers["Cookie"] = f"__client={self._seed}"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read())
        except Exception as e:  # noqa: BLE001
            raise LoginFailed(f"network error on {method} {path.split('?')[0]}: {e.__class__.__name__}") from None

    # --------------------------------------------------------------- cookies
    def _cookie(self) -> Optional[http.cookiejar.Cookie]:
        found = [c for c in self.jar if c.name == "__client" and c.value]
        return found[-1] if found else None

    def client_cookie_from_jar(self) -> Optional[str]:
        c = self._cookie()
        return c.value if c else None

    @property
    def client_cookie(self) -> Optional[str]:
        return self.client_cookie_from_jar() or self._seed

    @property
    def client_cookie_expires(self) -> Optional[float]:
        c = self._cookie()
        return float(c.expires) if c and c.expires else None

    # ------------------------------------------------------------------ api
    def environment(self) -> dict:
        return self.request("GET", "/environment")[1]

    def get_client(self) -> dict:
        status, body = self.request("GET", "/client")
        if status != 200:
            raise LoginFailed(f"GET /client -> HTTP {status}", _first_code(body), status)
        return body.get("response") or {}

    def mint_jwt(self, session_id: str) -> str:
        status, body = self.request("POST", f"/client/sessions/{session_id}/tokens", {})
        jwt = body.get("jwt") or (body.get("response") or {}).get("jwt")
        if status != 200 or not jwt:
            raise LoginFailed(f"POST /client/sessions/{{sid}}/tokens -> HTTP {status} ({_first_code(body)})",
                              _first_code(body), status)
        return jwt


def login_with_password(email: str, password: str, base: str = CLERK_BASE,
                        code_callback: Optional[Callable[[str], str]] = None) -> dict:
    """Sign in with email+password. Returns {"client_cookie", "expires_at", "session_id"} (expires_at: unix s).

    Makes exactly one sign-in attempt (no retries). Raises LoginBlocked / LoginFailed with Clerk's reason.

    VERIFIED 2026-11-25: the password is accepted, but from a new client Clerk answers status=needs_second_factor
    (Clerk "client trust" / new-device check — the instance has no MFA configured, second_factors=[]), with
    supported_second_factors=[email_code]. Without `code_callback` this raises LoginBlocked(code=<status>).

    With `code_callback` (NOT yet verified end-to-end — needs the owner to read the emailed code):
      POST /v1/client/sign_ins/{id}/prepare_second_factor  strategy=email_code[&email_address_id=...]
      code = code_callback(masked_email)        # e.g. lambda hint: input(f"code sent to {hint}: ")
      POST /v1/client/sign_ins/{id}/attempt_second_factor  strategy=email_code&code=<6 digits>
    After that the client is trusted, so the cached `__client` can mint tokens for as long as the session lives.
    """
    if not email or not password:
        raise LoginFailed("email and password are required")
    cc = ClerkClient(base)
    cc.get_client()  # obtain an anonymous __client cookie first, as the browser does
    status, body = cc.request("POST", "/client/sign_ins",
                              {"identifier": email, "strategy": "password", "password": password})
    if status >= 400:
        code = _first_code(body) or ""
        msg = f"sign-in rejected: HTTP {status} {code}: {_first_msg(body)}"
        if status == 429 or any(k in code for k in _BLOCKING_CODES):
            raise LoginBlocked(msg, code, status)
        raise LoginFailed(msg, code, status)
    si = body.get("response") or {}
    st = si.get("status")
    if st in ("needs_second_factor", "needs_client_trust") and code_callback:
        si, body = _email_code_second_factor(cc, si, code_callback)
        st = si.get("status")
    if st != "complete":
        second = st in ("needs_second_factor", "needs_client_trust")
        factors = [f.get("strategy") for f in
                   (si.get("supported_second_factors" if second else "supported_first_factors") or [])]
        cls = LoginBlocked if st in _BLOCKING_STATUSES else LoginFailed
        hint = (" — Clerk wants a one-time code emailed to the account (new-device check); "
                "rerun with an email-code callback, e.g. `clerk_login_probe.py --code-prompt`") if second else ""
        raise cls(f"sign-in not complete: status={st} client_trust_state={si.get('client_trust_state')} "
                  f"factors={factors}{hint}", st, status)
    sid = si.get("created_session_id") or (body.get("client") or {}).get("last_active_session_id")
    cookie = cc.client_cookie_from_jar()
    if not sid or not cookie:
        raise LoginFailed("sign-in complete but no session id or __client cookie returned", st, status)
    client = body.get("client") or {}
    exp = cc.client_cookie_expires
    if client.get("cookie_expires_at"):
        exp = min(exp or 1e18, client["cookie_expires_at"] / 1000)
    return {"client_cookie": cookie, "expires_at": exp, "session_id": sid}


def _email_code_second_factor(cc: ClerkClient, si: dict, code_callback: Callable[[str], str]) -> tuple[dict, dict]:
    """prepare_second_factor(email_code) -> ask callback for the code -> attempt_second_factor. One attempt only."""
    factor = next((f for f in si.get("supported_second_factors") or [] if f.get("strategy") == "email_code"), None)
    if not factor:
        raise LoginBlocked("second factor required but email_code is not offered", si.get("status"))
    sid = si["id"]
    st, body = cc.request("POST", f"/client/sign_ins/{sid}/prepare_second_factor",
                          {"strategy": "email_code", "email_address_id": factor.get("email_address_id")})
    if st >= 400:
        raise LoginBlocked(f"prepare_second_factor -> HTTP {st} {_first_code(body)}: {_first_msg(body)}",
                           _first_code(body), st)
    code = (code_callback(factor.get("safe_identifier") or "the account email") or "").strip()
    if not code:
        raise LoginBlocked("no email code supplied", "needs_second_factor")
    st, body = cc.request("POST", f"/client/sign_ins/{sid}/attempt_second_factor",
                          {"strategy": "email_code", "code": code})
    if st >= 400:
        raise LoginFailed(f"attempt_second_factor -> HTTP {st} {_first_code(body)}: {_first_msg(body)}",
                          _first_code(body), st)
    return body.get("response") or {}, body


def save_cached_client(data: dict, path: Path = CACHE_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {"client_cookie": data["client_cookie"], "expires_at": data.get("expires_at"),
           "session_id": data.get("session_id"), "saved_at": time.time()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out), encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_cached_client(path: Path = CACHE_PATH) -> Optional[dict]:
    """Cached login, or None if missing/unreadable/expired."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not data.get("client_cookie"):
        return None
    if data.get("expires_at") and data["expires_at"] < time.time() + 60:
        return None
    return data


def _json(raw: bytes) -> dict:
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {}


def _first_code(body: dict) -> Optional[str]:
    errs = body.get("errors") or []
    return errs[0].get("code") if errs else None


def _first_msg(body: dict) -> str:
    errs = body.get("errors") or []
    return (errs[0].get("long_message") or errs[0].get("message") or "") if errs else ""


# ----------------------------------------------------------------------------------------------------------------
# Two-step login for non-interactive terminals (CLI `login` / `login --code NNNNNN`)
PENDING_PATH = CACHE_PATH.with_name("pending_login.json")


def start_login(email: str, password: str, base: str = CLERK_BASE) -> dict:
    """Step 1: password sign-in. If Clerk completes immediately -> cache session, return {"status": "complete"}.
    If it asks for the emailed code -> trigger the email, persist the pending sign-in, return
    {"status": "code_sent", "sent_to": <masked email>}. One attempt, no retries."""
    if not email or not password:
        raise LoginFailed("HF_EMAIL and HF_PASSWORD must be set in .env")
    cc = ClerkClient(base)
    cc.get_client()
    status, body = cc.request("POST", "/client/sign_ins",
                              {"identifier": email, "strategy": "password", "password": password})
    if status >= 400:
        code = _first_code(body) or ""
        cls = LoginBlocked if status == 429 or any(k in code for k in _BLOCKING_CODES) else LoginFailed
        raise cls(f"sign-in rejected: HTTP {status} {code}: {_first_msg(body)}", code, status)
    si = body.get("response") or {}
    if si.get("status") == "complete":
        return _complete(cc, si, body)
    if si.get("status") not in ("needs_second_factor", "needs_client_trust"):
        raise LoginBlocked(f"sign-in not complete: status={si.get('status')}", si.get("status"), status)
    factor = next((f for f in si.get("supported_second_factors") or [] if f.get("strategy") == "email_code"), None)
    if not factor:
        raise LoginBlocked("second factor required but email_code is not offered", si.get("status"))
    st, b2 = cc.request("POST", f"/client/sign_ins/{si['id']}/prepare_second_factor",
                        {"strategy": "email_code", "email_address_id": factor.get("email_address_id")})
    if st >= 400:
        raise LoginBlocked(f"prepare_second_factor -> HTTP {st} {_first_code(b2)}: {_first_msg(b2)}", _first_code(b2), st)
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps({"client_cookie": cc.client_cookie, "sign_in_id": si["id"],
                                        "created": time.time()}), encoding="utf-8")
    return {"status": "code_sent", "sent_to": factor.get("safe_identifier") or "the account email"}


def finish_login(code: str, base: str = CLERK_BASE) -> dict:
    """Step 2: submit the emailed code for the pending sign-in; cache the trusted session."""
    try:
        pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise LoginFailed("no pending login — run `login` first") from None
    if time.time() - pending.get("created", 0) > 15 * 60:
        raise LoginFailed("pending login expired (>15 min) — run `login` again")
    cc = ClerkClient(base, client_cookie=pending["client_cookie"])
    st, body = cc.request("POST", f"/client/sign_ins/{pending['sign_in_id']}/attempt_second_factor",
                          {"strategy": "email_code", "code": (code or "").strip()})
    if st >= 400:
        raise LoginFailed(f"attempt_second_factor -> HTTP {st} {_first_code(body)}: {_first_msg(body)}",
                          _first_code(body), st)
    si = body.get("response") or {}
    if si.get("status") != "complete":
        raise LoginBlocked(f"sign-in not complete after code: status={si.get('status')}", si.get("status"), st)
    out = _complete(cc, si, body)
    try:
        PENDING_PATH.unlink()
    except OSError:
        pass
    return out


def _complete(cc: "ClerkClient", si: dict, body: dict) -> dict:
    sid = si.get("created_session_id") or (body.get("client") or {}).get("last_active_session_id")
    cookie = cc.client_cookie
    if not sid or not cookie:
        raise LoginFailed("sign-in complete but no session id or __client cookie returned")
    exp = cc.client_cookie_expires
    client = body.get("client") or {}
    if client.get("cookie_expires_at"):
        exp = min(exp or 1e18, client["cookie_expires_at"] / 1000)
    save_cached_client({"client_cookie": cookie, "expires_at": exp, "session_id": sid})
    return {"status": "complete", "expires_at": exp}
