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
"""
from __future__ import annotations

import json
import logging
import re
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlsplit

from scrapy import signals
from scrapy.exceptions import NotConfigured

log = logging.getLogger(__name__)

SECRET_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}
HTTP_REASONS = {200: "OK", 301: "Moved Permanently", 302: "Found", 304: "Not Modified", 400: "Bad Request",
                401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 422: "Unprocessable Entity",
                429: "Too Many Requests", 500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable"}


def _headers(h) -> list[dict[str, str]]:
    out = []
    for k, vs in h.items():
        name = k.decode("latin-1") if isinstance(k, bytes) else str(k)
        for v in vs if isinstance(vs, (list, tuple)) else [vs]:
            val = v.decode("latin-1") if isinstance(v, bytes) else str(v)
            if name.lower() in SECRET_HEADERS:
                val = (val.split(" ", 1)[0] + " ***") if " " in val else "***"
            out.append({"name": name, "value": val})
    return out


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
            log.exception("http archive failed for %s", request.url)
        return response

    def process_exception(self, request, exception, spider=None):
        try:
            self._record(request, error=repr(exception))
        except Exception:
            log.exception("http archive failed for %s", request.url)
        return None

    # ------------------------------------------------------------- record
    def _record(self, request, response=None, error: Optional[str] = None) -> None:
        self.seq += 1
        sent = request.meta.get("_http_sent_at") or datetime.now(timezone.utc)
        latency = request.meta.get("download_latency")
        endpoint, name_parts = self._label(request)
        params = request.meta.get("params") or dict(parse_qsl(urlsplit(request.url).query))
        name = f"{self.seq:03d}_" + _slug("__".join(name_parts))
        d = self.dir / name
        d.mkdir(parents=True, exist_ok=True)

        req_headers = _headers(request.headers)
        req_doc = {
            "seq": self.seq, "endpoint": endpoint, "method": request.method, "url": request.url,
            "query": params, "headers": req_headers,
            "body": request.body.decode("utf-8", "replace") if request.body else None,
            "sent_at": sent.isoformat(),
            "retry_times": request.meta.get("retry_times", 0),
            "meta": {k: v for k, v in request.meta.items() if isinstance(v, (str, int, float, bool)) and not k.startswith("_")},
        }
        (d / "request.json").write_text(json.dumps(req_doc, ensure_ascii=False, indent=4), encoding="utf-8")
        (d / "curl.sh").write_text(self._curl(request, req_headers) + "\n", encoding="utf-8")

        status, size, resp_headers, mime = None, 0, [], ""
        if response is not None:
            body: bytes = response.body or b""
            size = len(body)
            status = response.status
            resp_headers = _headers(response.headers)
            mime = (response.headers.get("Content-Type") or b"").decode("latin-1")
            (d / "body.raw").write_bytes(body)
            resp_doc = {
                "seq": self.seq, "status": status, "reason": HTTP_REASONS.get(status, ""), "url": response.url,
                "headers": resp_headers, "content_type": mime, "bytes": size,
                "latency_ms": round(latency * 1000, 1) if latency is not None else None,
                "received_at": (sent + timedelta(seconds=latency or 0)).isoformat(),
                "flags": list(response.flags), "protocol": getattr(response, "protocol", None),
                "ip_address": str(response.ip_address) if getattr(response, "ip_address", None) else None,
            }
        else:
            resp_doc = {"seq": self.seq, "error": error}
        (d / "response.json").write_text(json.dumps(resp_doc, ensure_ascii=False, indent=4), encoding="utf-8")

        line = {"seq": self.seq, "endpoint": endpoint, "method": request.method, "url": request.url,
                "status": status, "bytes": size, "latency_ms": resp_doc.get("latency_ms"), "error": error,
                "dir": f"http/{name}"}
        with (self.dir / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.crawler.stats.inc_value("higgs/http_archived")

        self.entries.append(self._har_entry(request, response, sent, latency, req_headers, resp_headers, mime,
                                            size, params, error))

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
        parts = ["curl", "-sS", "-X", request.method, shlex.quote(request.url)]
        for h in headers:
            if h["name"].lower() in ("accept-encoding",):
                continue
            parts += ["-H", shlex.quote(f"{h['name']}: {h['value']}")]
        if request.body:
            parts += ["--data-raw", shlex.quote(request.body.decode("utf-8", "replace"))]
        return " \\\n  ".join([" ".join(parts[:5])] + [" ".join(parts[i:i + 2]) for i in range(5, len(parts), 2)])

    @staticmethod
    def _har_entry(request, response, sent, latency, req_h, resp_h, mime, size, params, error) -> dict:
        ms = round((latency or 0) * 1000, 1)
        text = None
        if response is not None and response.body:
            text = response.body.decode("utf-8", "replace")
        return {
            "startedDateTime": sent.isoformat(),
            "time": ms,
            "request": {"method": request.method, "url": request.url, "httpVersion": "HTTP/1.1", "cookies": [],
                        "headers": req_h, "queryString": [{"name": k, "value": str(v)} for k, v in params.items()],
                        "headersSize": -1, "bodySize": len(request.body or b"")},
            "response": {"status": response.status if response is not None else 0,
                         "statusText": HTTP_REASONS.get(response.status, "") if response is not None else (error or ""),
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
        har = {"log": {"version": "1.2", "creator": {"name": "higgs_price", "version": __version__},
                       "pages": [], "entries": self.entries}}
        path = self.dir / "session.har"
        path.write_text(json.dumps(har, ensure_ascii=False, indent=4), encoding="utf-8")
        log.info("http archive: %d exchanges -> %s", len(self.entries), self.dir)
