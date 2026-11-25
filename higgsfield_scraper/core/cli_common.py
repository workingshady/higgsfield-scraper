"""CLI flags shared by every `scrape <scraper>` subcommand."""
from __future__ import annotations

import argparse
import os

from .base import MEDIA_MODES, CommonOptions


def add_run_args(p: argparse.ArgumentParser) -> None:
    r = p.add_argument_group("run")
    r.add_argument("--label", default=None, help="run label (folder suffix)")
    r.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    r.add_argument("--log-level", default=os.environ.get("HF_LOG_LEVEL", "INFO"), help="console level")
    r.add_argument("--file-log-level", default="DEBUG")
    r.add_argument("--scrapy-log-level", default="INFO")


def add_access_args(p: argparse.ArgumentParser) -> None:
    a = p.add_argument_group("access / safety")
    a.add_argument("--token", default=None,
                   help="Clerk session JWT (~60 s). Prefer HF_CLERK_CLIENT or HF_EMAIL/HF_PASSWORD in .env for auto refresh")
    a.add_argument("--auth", choices=["auto", "off", "required"], default="auto",
                   help="auto: use login when configured (default) | off: never send tokens | required: skip login-only "
                        "endpoints when no session")
    a.add_argument("--cache", action="store_true", help="enable Scrapy HTTP cache (dev)")
    a.add_argument("--no-http-archive", action="store_true",
                   help="don't write <run>/http/ (per-request request.json, response.json, body.raw, curl.sh, session.har)")
    a.add_argument("--obey-robots", action="store_true",
                   help="check and obey robots.txt (default: off — robots.txt is not obeyed)")
    a.add_argument("--delay", type=float, default=1.0, help="seconds between requests per domain (default 1.0)")
    a.add_argument("--concurrency", type=int, default=2, help="parallel requests per domain (default 2)")
    a.add_argument("--max-requests", type=int, default=5000, help="hard cap on HTTP responses (default 5000)")
    a.add_argument("--max-minutes", type=float, default=None, help="stop the crawl after N minutes")
    a.add_argument("--no-stop-on-block", action="store_true",
                   help="keep going after a bot-protection (captcha) response instead of stopping")
    a.add_argument("--dry-run", action="store_true", help="print the first requests that would be made and exit")


def add_limit_args(p: argparse.ArgumentParser) -> None:
    lim = p.add_argument_group("limits")
    lim.add_argument("--max-items", type=int, default=None, help="stop after N primary items (default: no limit)")
    lim.add_argument("--max-pages", type=int, default=None, help="max pages per paginated listing")
    lim.add_argument("--page-size", type=int, default=None, help="items per API page (clamped to the API maximum)")
    m = p.add_argument_group("media download (optional)")
    m.add_argument("--download-media", choices=MEDIA_MODES, default="none",
                   help="none (links only, default) | thumbs | full | all — files go to <run>/media/")
    m.add_argument("--max-media-files", type=int, default=500, help="cap on downloaded files (default 500)")
    m.add_argument("--max-media-mb", type=float, default=1024.0, help="cap on downloaded MB (default 1024)")


def common_from_args(a: argparse.Namespace) -> CommonOptions:
    return CommonOptions(
        max_items=getattr(a, "max_items", None), max_pages=getattr(a, "max_pages", None),
        page_size=getattr(a, "page_size", None), max_requests=a.max_requests, max_minutes=a.max_minutes,
        delay=a.delay, concurrency=a.concurrency, download_media=getattr(a, "download_media", "none"),
        max_media_files=getattr(a, "max_media_files", 500), max_media_mb=getattr(a, "max_media_mb", 1024.0),
        auth=a.auth, stop_on_block=not a.no_stop_on_block)
