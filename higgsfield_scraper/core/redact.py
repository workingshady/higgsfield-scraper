"""Central secret redaction, shared by every log formatter, the http archive, the HAR and the run manifest.

    redact_text("GET https://u:p@x/?token=abc Bearer eyJhbGciOi.eyJzdWIi.sig")
      -> "GET https://[REDACTED]@x/?token=[REDACTED] Bearer [REDACTED]"
    redact({"cookie": "__client=abc", "url": "https://x/?sig=1"})
      -> {"cookie": "[REDACTED]", "url": "https://x/?sig=[REDACTED]"}

Covers secret keys (dict keys / `key=value` / `key: value` in text), credentials in URLs (`user:pass@`), secret query
parameters, `Bearer …` values and bare JWTs (`eyJ…` -> [REDACTED_JWT]). Redaction never raises.
"""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"
REDACTED_JWT = "[REDACTED_JWT]"

# dict keys / field names whose value is always a secret (compared lower-case, last dotted segment, '-' == '_')
SECRET_KEYS = frozenset({
    "authorization", "proxy_authorization", "cookie", "set_cookie", "x_api_key", "api_key", "apikey",
    "token", "access_token", "refresh_token", "id_token", "jwt", "password", "passwd", "secret", "client_secret",
    "private_key", "__session", "__client", "__clerk_db_jwt", "client_cookie", "session_id",
    "hf_token", "hf_clerk_client", "hf_password", "hf_email",
})
# URL query parameters whose value is a secret
SECRET_PARAMS = ("token", "access_token", "refresh_token", "api_key", "apikey", "key", "signature", "sig",
                 "password", "meta", "__clerk_db_jwt", "x-amz-signature", "x-amz-credential", "x-amz-security-token",
                 "code")

_KEY_ALT = "|".join(sorted({k.replace("_", "[_-]") if k.startswith(("x_", "set_", "proxy_")) else k
                            for k in SECRET_KEYS}, key=len, reverse=True))
_URL_CREDS = re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s:@'\"]+:[^/\s@'\"]+@")
_QUERY = re.compile(r"([?&;])(" + "|".join(re.escape(p) for p in sorted(SECRET_PARAMS, key=len, reverse=True))
                    + r")=([^&#\s\"'<>]*)", re.I)
_BEARER = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.I)
_KV = re.compile(r"(?<![\w.-])([\"']?)(" + _KEY_ALT + r")\1(\s*[:=]\s*)([\"']?)(?!\[REDACTED|\*\*\*|(?:Bearer|Basic)\s)([^\"'\s,;&}\]]+)", re.I)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*")


def is_secret_key(key: Any) -> bool:
    k = str(key).lower().rsplit(".", 1)[-1].replace("-", "_")
    return k in SECRET_KEYS


def redact_text(text: Any) -> Any:
    """Scrub secrets out of free text (messages, URLs, exception text, tracebacks). Non-strings pass through."""
    if not isinstance(text, str) or not text:
        return text
    try:
        t = _URL_CREDS.sub(r"\1" + REDACTED + "@", text)
        t = _JWT.sub(REDACTED_JWT, t)
        t = _QUERY.sub(lambda m: f"{m.group(1)}{m.group(2)}={REDACTED}" if m.group(3) else m.group(0), t)
        t = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", t)
        t = _KV.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(1)}{m.group(3)}{m.group(4)}{REDACTED}", t)
        return t
    except Exception:  # pragma: no cover - never break logging
        return text


def redact_url(url: Any) -> Any:
    return redact_text(url)


def redact(obj: Any, _depth: int = 0) -> Any:
    """Deep copy of `obj` with secret-keyed values replaced and every string scrubbed."""
    if _depth > 20:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if is_secret_key(k) and v not in (None, "", "***") and not isinstance(v, bool):
                out[k] = REDACTED
            else:
                out[k] = redact(v, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return type(obj)(redact(v, _depth + 1) for v in obj) if isinstance(obj, list) else \
            tuple(redact(v, _depth + 1) for v in obj)
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def redact_argv(argv: list[str]) -> list[str]:
    """Command line for the manifest: values of secret flags (`--token X`, `--password=X`) are replaced."""
    out: list[str] = []
    hide_next = False
    for a in argv:
        if hide_next:
            out.append(REDACTED)
            hide_next = False
            continue
        if a.startswith("--"):
            name, eq, _ = a[2:].partition("=")
            if is_secret_key(name):
                if eq:
                    out.append(f"--{name}={REDACTED}")
                else:
                    out.append(a)
                    hide_next = True
                continue
        out.append(redact_text(a))
    return out
