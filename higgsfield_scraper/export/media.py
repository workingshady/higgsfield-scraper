"""Find a local file for a row's media: the runs' `media/index.jsonl` first, then the export's download cache.

`--download-missing-media thumbs|full` is the ONLY network access of the export command: plain GETs, at most one
request per `delay` seconds (>= 1 s), honouring max files / max MB caps (default: the run's own --max-media-* caps).
Downloads land in `<export>/.media_cache/` (content named by sha1(url)), never in the run folder.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .paths import long_path
from .reader import url_key
from .records import ExportRow, ext_of, media_kind

USER_AGENT = "higgsfield-scraper-export/1.0 (+offline dataset export)"
Fetch = Callable[[str, int], tuple[bytes, str]]       # (url, max_bytes) -> (body, content-type)


def default_fetch(url: str, max_bytes: int) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with urllib.request.urlopen(req, timeout=60) as r:          # noqa: S310 (http/https checked by caller)
        clen = r.headers.get("Content-Length")
        if clen and clen.isdigit() and int(clen) > max_bytes:
            raise ValueError(f"too large ({int(clen)} bytes > remaining cap {max_bytes})")
        body = r.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError(f"too large (> remaining cap {max_bytes} bytes)")
        return body, r.headers.get("Content-Type") or ""


class MediaResolver:
    def __init__(self, index: dict[str, Path], cache_dir: Path, *, download: Optional[str] = None,
                 max_files: int = 500, max_mb: float = 1024.0, delay: float = 1.0, dry_run: bool = False,
                 fetch: Optional[Fetch] = None, errors: Optional[list[str]] = None) -> None:
        self.index = index
        self.cache = cache_dir
        self.download = download
        self.max_files = max_files
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.delay = max(1.0, float(delay))
        self.dry_run = dry_run
        self.fetch = fetch or default_fetch
        self.errors = errors if errors is not None else []
        self.stats = {"local": 0, "cached": 0, "downloaded": 0, "would_download": 0, "download_failed": 0,
                      "missing": 0, "cap_reached": 0}
        self._dl_files = 0
        self._dl_bytes = 0
        self._last = 0.0
        self._failed: set[str] = set()
        self._cap_logged = False
        self._cache_names: dict[str, Path] = {}
        if cache_dir.is_dir():
            for q in cache_dir.iterdir():
                if q.is_file() and not q.name.endswith(".part"):
                    self._cache_names.setdefault(q.name.split(".")[0], q)

    def _cache_path(self, url: str, ext: str) -> Path:
        return self.cache / (hashlib.sha1(url_key(url).encode("utf-8")).hexdigest()[:20] + ext)

    def _cached(self, url: str) -> Optional[Path]:
        return self._cache_names.get(hashlib.sha1(url_key(url).encode("utf-8")).hexdigest()[:20])

    def _download_candidate(self, row: ExportRow) -> Optional[str]:
        if self.download == "thumbs":
            order = [row.thumb_url] + ([row.media_url] if media_kind(row.media_url) == "image" else [])
        else:
            order = [row.media_url, row.thumb_url]
        return next((u for u in order if u and u.startswith(("http://", "https://")) and ".m3u8" not in u), None)

    def resolve(self, row: ExportRow) -> Optional[Path]:
        for u in row.all_urls:
            p = self.index.get(u) or self.index.get(url_key(u))
            if p is not None:
                self.stats["local"] += 1
                return p
        for u in row.all_urls:
            p = self._cached(u)
            if p is not None:
                self.stats["cached"] += 1
                return p
        if not self.download:
            if row.all_urls:
                self.stats["missing"] += 1
            return None
        url = self._download_candidate(row)
        if not url:
            return None
        return self._download(url)

    def _download(self, url: str) -> Optional[Path]:
        if url in self._failed:
            return None
        if self._dl_files >= self.max_files or self._dl_bytes >= self.max_bytes:
            self.stats["cap_reached"] += 1
            if not self._cap_logged:
                self.errors.append(f"download cap reached (max files {self.max_files}, max MB "
                                   f"{self.max_bytes / 1048576:.0f}); remaining media stay as URLs")
                self._cap_logged = True
            return None
        if self.dry_run:
            self._dl_files += 1
            self.stats["would_download"] += 1
            return None
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        try:
            body, ctype = self.fetch(url, self.max_bytes - self._dl_bytes)
        except Exception as e:                                  # network errors are logged, never fatal
            self._failed.add(url)
            self.stats["download_failed"] += 1
            self.errors.append(f"download failed {url_key(url)}: {type(e).__name__}: {e}")
            return None
        ext = ext_of(url) or mimetypes.guess_extension((ctype or "").split(";")[0].strip()) or ".bin"
        p = self._cache_path(url, ext)
        os.makedirs(long_path(self.cache), exist_ok=True)
        tmp = Path(str(p) + ".part")
        with open(long_path(tmp), "wb") as f:
            f.write(body)
        os.replace(long_path(tmp), long_path(p))
        self._cache_names[p.name.split(".")[0]] = p
        self._dl_files += 1
        self._dl_bytes += len(body)
        self.stats["downloaded"] += 1
        return p
