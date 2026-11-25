"""HttpArchiveMiddleware: record every HTTP exchange of a run into <run>/http/.

<run>/http/
  index.jsonl                     one line per exchange (seq, endpoint, method, url, status, bytes, latency_ms, dir)
  session.har                     HAR 1.2 of the whole run (Chrome DevTools -> Network -> Import HAR)
  NNN_<endpoint>__<params>/
    request.json                  method, url, query params, headers actually sent (secrets masked), meta, sent time
    response.json                 status, headers, final url, bytes, latency, retry count, flags
    body.raw                      response body bytes exactly as received (after gzip/br decoding)
    curl.sh                       copy-paste replay command (secrets masked)

Sits at priority 580 — just *below* HttpCompressionMiddleware (590) — so it sees decompressed bodies and the final
request headers (User-Agent, Accept-Encoding, …). Disable with setting HIGGS_HTTP_ARCHIVE = False (CLI: --no-http-archive).
URLs, headers and query strings are redacted with core.redact (bodies are kept byte-exact).

Also here:
  AccessLogMiddleware (585)    one `http.request.finished` event per response / failed attempt -> logs/access.jsonl
                               (works with --no-http-archive). Assigns meta["request_id"] (kept across retries).
  RetryEventsMiddleware (550)  Scrapy's RetryMiddleware + `external.call.retried` / `external.call.failed` events.
"""
from __future__ import annotations

import itertools
import json
import logging
import re
import shlex
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlsplit

from scrapy import signals
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.exceptions import NotConfigured

from .core.redact import SECRET_PARAMS, is_secret_key, redact_text
from .run.logging_setup import emit

log = logging.getLogger(__name__)
access_log = logging.getLogger("higgsfield_scraper.access")

HAR_MAX_BODY = 256 * 1024        # bodies above this are left out of session.har (full bytes stay in body.raw)
SECRET_HEADERS ={"authorization", "cookie", "set-cookie", "x-api-key"}
HTTP_REASONS = {200: "OK", 301: "Moved Permanently", 302: "Found", 304: "Not Modified", 400: "Bad Request",
                401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 422: "Unprocessable Entity",
                429: "Too Many Requests", 500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable"}


def _headers(h) -> list[dict[str, str]]:
    out = []
    for k, vs in h.items():
        name = k.decode("latin-1") if isinstance(k, bytes) else str(k)
        for v in vs if isinstance(vs, (list, tuple)) else [vs]:
            val = v.decode("latin-1") if isinstance(v, bytes) else str(v)
            if name.lower() in SECRET_HEADERS or is_secret_key(name):
                val = (val.split(" ", 1)[0] + " ***") if " " in val else "***"
            else:
                val = redact_text(val)
            out.append({"name": name, "value": val})
    return out


def _safe_params(params: dict) -> dict:
    secret = {p.lower() for p in SECRET_PARAMS}
    return {k: ("[REDACTED]" if (str(k).lower() in secret or is_secret_key(k)) and v not in (None, "") else
                redact_text(v) if isinstance(v, str) else v) for k, v in params.items()}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")[:90] or "request"


class HttpArchiveMiddleware:
    def __init__(self, crawler):
        if not crawler.settings.getbool("HIGGS_HTTP_ARCHIVE", True):
            raise NotConfigured
        self.crawler = crawler
        self.seq = 0
        self.entries: list[dict[str, Any]] = []
        self._dir: Optional[Path] = None
        crawler.signals.connect(self.spider_closed, signal=signals.spider_closed)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    @property
    def dir(self) -> Path:
        if self._dir is None:
            from .pipelines import run_ctx_for
            self._dir = run_ctx_for(self.crawler).run_dir / "http"
            self._dir.mkdir(parents=True, exist_ok=True)
        return self._dir

    # -------------------------------------------------------------- hooks
    def process_request(self, request, spider=None):
        request.meta.setdefault("_http_sent_at", datetime.now(timezone.utc))
        return None

    def process_response(self, request, response, spider=None):
        try:
            self._record(request, response=response)
        except Exception:  # never break the crawl because of archiving
            emit(log, "error", "http.archive.failed", "http archive failed", exc_info=True,
                 url__full=redact_text(request.url))
        return response

    def process_exception(self, request, exception, spider=None):
        try:
            self._record(request, error=repr(exception))
        except Exception:
            emit(log, "error", "http.archive.failed", "http archive failed", exc_info=True,
                 url__full=redact_text(request.url))
        return None

    # ------------------------------------------------------------- record
    def _record(self, request, response=None, error: Optional[str] = None) -> None:
        if request.meta.get("media"):               # media downloads: index line only (files live in <run>/media/)
            with (self.dir / "index.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"seq": None, "endpoint": "media", "method": request.method,
                                    "url": redact_text(request.url),
                                    "status": response.status if response is not None else None,
                                    "bytes": len(response.body or b"") if response is not None else 0,
                                    "error": redact_text(error), "dir": None}, ensure_ascii=False) + "\n")
            return
        self.seq += 1
        sent = request.meta.get("_http_sent_at") or datetime.now(timezone.utc)
        latency = request.meta.get("download_latency")
        endpoint, name_parts = self._label(request)
        params = _safe_params(request.meta.get("params") or dict(parse_qsl(urlsplit(request.url).query)))
        url = redact_text(request.url)
        name = f"{self.seq:03d}_" + _slug("__".join(name_parts))
        d = self.dir / name
        d.mkdir(parents=True, exist_ok=True)

        req_headers = _headers(request.headers)
        req_doc = {
            "seq": self.seq, "endpoint": endpoint, "method": request.method, "url": url,
            "request_id": request.meta.get("request_id"), "query": params, "headers": req_headers,
            "body": redact_text(request.body.decode("utf-8", "replace")) if request.body else None,
            "sent_at": sent.isoformat(),
            "retry_times": request.meta.get("retry_times", 0),
            "meta": {k: (redact_text(v) if isinstance(v, str) else v) for k, v in request.meta.items()
                     if isinstance(v, (str, int, float, bool)) and not k.startswith("_") and not is_secret_key(k)},
        }
        (d / "request.json").write_text(json.dumps(req_doc, ensure_ascii=False, indent=4), encoding="utf-8")
        (d / "curl.sh").write_text(self._curl(request, req_headers) + "\n", encoding="utf-8")

        status, size, resp_headers, mime = None, 0, [], ""
        if response is not None:
            body: bytes = self._privacy(response.body or b"")
            size = len(body)
            status = response.status
            resp_headers = _headers(response.headers)
            mime = (response.headers.get("Content-Type") or b"").decode("latin-1")
            (d / "body.raw").write_bytes(body)
            resp_doc = {
                "seq": self.seq, "status": status, "reason": HTTP_REASONS.get(status, ""),
                "url": redact_text(response.url),
                "headers": resp_headers, "content_type": mime, "bytes": size,
                "latency_ms": round(latency * 1000, 1) if latency is not None else None,
                "received_at": (sent + timedelta(seconds=latency or 0)).isoformat(),
                "flags": list(response.flags), "protocol": getattr(response, "protocol", None),
                "ip_address": str(response.ip_address) if getattr(response, "ip_address", None) else None,
            }
        else:
            resp_doc = {"seq": self.seq, "error": redact_text(error)}
        (d / "response.json").write_text(json.dumps(resp_doc, ensure_ascii=False, indent=4), encoding="utf-8")

        line = {"seq": self.seq, "request_id": request.meta.get("request_id"), "endpoint": endpoint,
                "method": request.method, "url": url, "status": status, "bytes": size,
                "latency_ms": resp_doc.get("latency_ms"), "error": redact_text(error), "dir": f"http/{name}"}
        with (self.dir / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.crawler.stats.inc_value("higgs/http_archived")

        self.entries.append(self._har_entry(request, response, sent, latency, req_headers, resp_headers, mime,
                                            size, params, error,
                                            body=self._privacy(response.body or b"") if response is not None else b""))

    def _privacy(self, body: bytes) -> bytes:
        """Redact other users' personal data from archived bodies unless the run opted in (--with-profiles)."""
        sp = getattr(self.crawler, "spider", None)
        try:
            from .core.privacy import profiles_opt_in, redact_json_bytes
            from .pipelines import scraper_of
            if sp is not None and scraper_of(sp).personal_data and not profiles_opt_in(getattr(sp, "selection", None)):
                return redact_json_bytes(body)
        except Exception:
            pass
        return body

    @staticmethod
    def _label(request) -> tuple[str, list[str]]:
        """(endpoint, folder-name parts). Redirect hops are named after the request that started them; unknown URLs
        use only the host (their query strings can hold tokens, e.g. Cloudflare Access `meta=` JWTs)."""
        origin = (request.meta.get("redirect_urls") or [request.url])[0]
        hop = "_redirect" if request.meta.get("redirect_urls") else ""
        endpoint = request.meta.get("endpoint")
        if endpoint:
            params = request.meta.get("params") or {}
            return endpoint + hop, [endpoint + hop] + [f"{k}-{v}" for k, v in sorted(params.items())
                                                       if k != "with_localization"]
        host = urlsplit(origin).hostname or "unknown"
        if urlsplit(origin).path.endswith("/robots.txt"):
            return "robots.txt" + hop, ["robots.txt" + hop, host]
        return "other" + hop, ["other" + hop, urlsplit(request.url).hostname or "unknown"]

    @staticmethod
    def _curl(request, headers: list[dict[str, str]]) -> str:
        parts = ["curl", "-sS", "-X", request.method, shlex.quote(redact_text(request.url))]
        for h in headers:
            if h["name"].lower() in ("accept-encoding",):
                continue
            parts += ["-H", shlex.quote(f"{h['name']}: {h['value']}")]
        if request.body:
            parts += ["--data-raw", shlex.quote(redact_text(request.body.decode("utf-8", "replace")))]
        return " \\\n  ".join([" ".join(parts[:5])] + [" ".join(parts[i:i + 2]) for i in range(5, len(parts), 2)])

    @staticmethod
    def _har_entry(request, response, sent, latency, req_h, resp_h, mime, size, params, error, body=b"") -> dict:
        ms = round((latency or 0) * 1000, 1)
        text = None
        if body and len(body) <= HAR_MAX_BODY:
            text = body.decode("utf-8", "replace")     # large bodies: see http/NNN_*/body.raw (no MemoryError)
        return {
            "startedDateTime": sent.isoformat(),
            "time": ms,
            "request": {"method": request.method, "url": redact_text(request.url), "httpVersion": "HTTP/1.1",
                        "cookies": [],
                        "headers": req_h, "queryString": [{"name": k, "value": str(v)} for k, v in params.items()],
                        "headersSize": -1, "bodySize": len(request.body or b"")},
            "response": {"status": response.status if response is not None else 0,
                         "statusText": HTTP_REASONS.get(response.status, "") if response is not None
                         else redact_text(error or ""),
                         "httpVersion": "HTTP/1.1", "cookies": [], "headers": resp_h,
                         "content": {"size": size, "mimeType": mime or "x-unknown", **({"text": text} if text else {})},
                         "redirectURL": "", "headersSize": -1, "bodySize": size},
            "cache": {},
            "timings": {"send": 0, "wait": ms, "receive": 0},
            "_endpoint": request.meta.get("endpoint"),
        }

    def spider_closed(self, spider, reason=None):
        if not self.entries:
            return
        from . import __version__
        har = {"log": {"version": "1.2", "creator": {"name": "higgsfield_scraper", "version": __version__},
                       "pages": [], "entries": self.entries}}
        path = self.dir / "session.har"
        path.write_text(json.dumps(har, ensure_ascii=False, indent=4), encoding="utf-8")
        emit(log, "info", "http.archive.written", f"http archive: {len(self.entries)} exchanges",
             exchanges__count=len(self.entries), path=str(self.dir))


# ------------------------------------------------------------------ access log
_REQUEST_IDS = itertools.count(1)
BLOCK_MARKERS = (b"captcha-delivery.com", b"datadome")


def _optional_endpoint(crawler, request) -> bool:
    if request.meta.get("auth") or request.meta.get("media"):
        return True
    try:
        from .pipelines import scraper_of
        sp = getattr(crawler, "spider", None)
        return sp is not None and request.meta.get("endpoint") in scraper_of(sp).optional_endpoints
    except Exception:
        return False


class AccessLogMiddleware:
    """Downloader middleware (585): one `http.request.finished` event per response or failed attempt."""

    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_request(self, request, spider=None):
        request.meta.setdefault("request_id", next(_REQUEST_IDS))   # request.copy() on retry keeps it
        request.meta["_access_t0"] = time.monotonic()
        return None

    def _fields(self, request) -> dict[str, Any]:
        t0 = request.meta.get("_access_t0")
        lat = request.meta.get("download_latency")
        dur = lat * 1000 if lat is not None else ((time.monotonic() - t0) * 1000 if t0 else None)
        return {"request_id": request.meta.get("request_id"), "http.request.method": request.method,
                "url.full": redact_text(request.url), "server.address": urlsplit(request.url).hostname,
                "duration_ms": round(dur, 1) if dur is not None else None,
                "retry.attempt": request.meta.get("retry_times", 0),
                "endpoint.name": request.meta.get("endpoint")}

    def process_response(self, request, response, spider=None):
        try:
            f = self._fields(request)
            status = response.status
            body = response.body or b""
            blocked = status == 403 and any(m in body[:20000] for m in BLOCK_MARKERS)
            outcome = "blocked" if blocked else "success" if status < 400 else "http_error"
            f.update({"http.response.status_code": status, "size_bytes": len(body), "outcome": outcome})
            level = "info" if status < 400 or _optional_endpoint(self.crawler, request) else "warning"
            emit(access_log, level, "http.request.finished",
                 f"{request.method} {f['endpoint.name'] or f['server.address']} -> {status}",
                 **{k.replace(".", "__"): v for k, v in f.items()})
        except Exception:
            log.debug("access log failed", exc_info=True)
        return response

    def process_exception(self, request, exception, spider=None):
        try:
            f = self._fields(request)
            f.update({"http.response.status_code": None, "size_bytes": 0, "outcome": "error",
                      "error.type": type(exception).__name__})
            emit(access_log, "warning", "http.request.finished",
                 f"{request.method} {f['endpoint.name'] or f['server.address']} -> {type(exception).__name__}",
                 **{k.replace(".", "__"): v for k, v in f.items()})
        except Exception:
            log.debug("access log failed", exc_info=True)
        return None


class RetryEventsMiddleware(RetryMiddleware):
    """Scrapy's RetryMiddleware, plus `external.call.retried` (warn) / `external.call.failed` (error) events."""

    def _retry(self, request, reason, *args, **kwargs):
        new = super()._retry(request, reason, *args, **kwargs)
        reason_s = redact_text(reason if isinstance(reason, str) else
                               getattr(reason, "__name__", None) or f"{type(reason).__name__}: {reason}")
        f = {"request_id": request.meta.get("request_id"), "endpoint__name": request.meta.get("endpoint"),
             "url__full": redact_text(request.url), "error__type": reason_s}
        if new is not None:
            emit(log, "warning", "external.call.retried",
                 f"retrying {request.meta.get('endpoint') or urlsplit(request.url).hostname}: {reason_s}",
                 retry__attempt=new.meta.get("retry_times"), **f)
        else:
            request.meta["_gave_up"] = True          # the spider errback then logs at debug only (log once)
            emit(log, "error", "external.call.failed",
                 f"gave up on {request.meta.get('endpoint') or urlsplit(request.url).hostname}: {reason_s}",
                 retry__attempt=request.meta.get("retry_times", 0), **f)
        return new
