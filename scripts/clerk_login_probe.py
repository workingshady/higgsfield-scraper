"""Log in to Higgsfield (Clerk) with HF_EMAIL/HF_PASSWORD from .env, cache the `__client` cookie, verify a JWT.

Usage:  python scripts/clerk_login_probe.py [--env-only] [--use-cache] [--refresh-test] [--code-prompt]
  --env-only      only print the Clerk environment summary (no credentials used)
  --use-cache     skip the password login when runs/.auth/clerk_client.json holds a valid cookie
  --refresh-test  after the first JWT, wait 65 s and mint a second one from the cookie alone
  --code-prompt   if Clerk asks for the emailed one-time code (new-device check), prompt for it on stdin

Steps: (a) Clerk environment summary, (b) one email+password sign-in (no retries), (c) cache `__client` to
runs/.auth/clerk_client.json, (d) mint a session JWT and call fnf-api-gw /user and /subscriptions/v2/packages.

Never prints the password, cookies or JWTs (only lengths). Exit codes: 0 ok, 2 login blocked (captcha / email code /
MFA / device trust / lockout), 3 login failed (credentials / unexpected), 4 JWT rejected by the API.
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from higgsfield_scraper.core.auth_login import (  # noqa: E402
    CACHE_PATH, ClerkClient, LoginBlocked, LoginFailed, load_cached_client, login_with_password, save_cached_client)

API = "https://fnf-api-gw.higgsfield.ai/fnf"


def load_env(path: Path = ROOT / ".env") -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def jwt_claims(tok: str) -> dict:
    p = tok.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def ts(t) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t else "?"


def env_summary(cc: ClerkClient) -> None:
    env = cc.environment()
    ac, dc, us = env.get("auth_config", {}), env.get("display_config", {}), env.get("user_settings", {})
    print("== Clerk environment ==")
    print("  first_factors      :", ac.get("first_factors"))
    print("  second_factors     :", ac.get("second_factors"), "| sign_in.second_factor:", us.get("sign_in"))
    print("  password enabled   :", ac.get("password"), "| single_session_mode:", ac.get("single_session_mode"))
    print("  captcha            :", dc.get("captcha_provider"), dc.get("captcha_widget_type"),
          "| sign_up.captcha_enabled:", (us.get("sign_up") or {}).get("captcha_enabled"))
    print("  attack_protection  :", json.dumps(us.get("attack_protection")))
    print("  clerk protect      :", bool(env.get("protect_config", {}).get("loaders")))
    print("  social             :", [k for k, v in (us.get("social") or {}).items() if v.get("enabled")])


def api_get(path: str, jwt: str) -> tuple[int, object]:
    req = urllib.request.Request(API + path, headers={
        "Authorization": f"Bearer {jwt}", "Accept": "application/json", "Origin": "https://higgsfield.ai",
        "Referer": "https://higgsfield.ai/", "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def check_jwt(jwt: str, label: str) -> bool:
    c = jwt_claims(jwt)
    print(f"  {label}: len={len(jwt)} lifetime={c.get('exp', 0) - c.get('iat', 0)}s exp={ts(c.get('exp'))}")
    ok = True
    for path in ("/user", "/subscriptions/v2/packages"):
        st, body = api_get(path, jwt)
        keys = sorted(body)[:15] if isinstance(body, dict) else type(body).__name__
        print(f"    GET {path} -> {st}  keys={keys}")
        ok &= st == 200
    return ok


def main(argv: list[str]) -> int:
    cc = ClerkClient()
    env_summary(cc)
    if "--env-only" in argv:
        return 0

    cached = load_cached_client() if "--use-cache" in argv else None
    if cached:
        print(f"== using cached __client from {CACHE_PATH} (expires {ts(cached.get('expires_at'))}) ==")
        login = cached
    else:
        env = load_env()
        print("== signing in (email+password, one attempt) ==")
        try:
            cb = (lambda hint: input(f"  enter the code Clerk emailed to {hint}: ")) if "--code-prompt" in argv else None
            login = login_with_password(env.get("HF_EMAIL", ""), env.get("HF_PASSWORD", ""), code_callback=cb)
        except LoginBlocked as e:
            print(f"LOGIN BLOCKED (needs human action): {e}", file=sys.stderr)
            return 2
        except LoginFailed as e:
            print(f"LOGIN FAILED: {e}", file=sys.stderr)
            return 3
        path = save_cached_client(login)
        print(f"  ok: session={login['session_id'][:8]}... __client len={len(login['client_cookie'])} "
              f"expires={ts(login['expires_at'])} -> cached at {path}")

    # Fresh client seeded only with the cookie: proves the cookie alone is enough to mint tokens.
    minter = ClerkClient(client_cookie=login["client_cookie"])
    sid = login.get("session_id") or minter.get_client().get("last_active_session_id")
    print("== minting session JWT from __client ==")
    try:
        jwt = minter.mint_jwt(sid)
    except LoginFailed as e:
        print(f"MINT FAILED: {e}", file=sys.stderr)
        return 4
    ok = check_jwt(jwt, "jwt#1")
    if "--refresh-test" in argv:
        print("  waiting 65 s to let jwt#1 expire ...")
        time.sleep(65)
        jwt2 = minter.mint_jwt(sid)
        st, _ = api_get("/user", jwt)
        print(f"  old jwt#1 now -> GET /user {st}")
        ok &= check_jwt(jwt2, "jwt#2") and jwt2 != jwt
    # The server may rotate __client on every call; persist the latest value.
    if minter.client_cookie_from_jar() and minter.client_cookie_from_jar() != login["client_cookie"]:
        print("  note: __client was rotated by the server; cache updated")
        save_cached_client({**login, "client_cookie": minter.client_cookie_from_jar()})
    print("RESULT:", "OK" if ok else "JWT rejected")
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
