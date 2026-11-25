"""CLI flags shared by every `scrape <scraper>` subcommand."""
from __future__ import annotations

import argparse
import os

from .base import MEDIA_MODES, CommonOptions


def add_run_args(p: argparse.ArgumentParser) -> None:
    r = p.add_argument_group("run")
    r.add_argument("--label", default=None, help="run label (folder suffix)")
    r.add_argument("--runs-dir", default=os.environ.get("HF_RUNS_DIR", "runs"))
    add_log_args(p)


def add_log_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("logging")
    g.add_argument("-v", "--verbose", action="count", default=0,
                   help="-v: project DEBUG on the console, -vv: Scrapy DEBUG too")
    g.add_argument("-q", "--quiet", action="store_true", help="console shows warnings and errors only")
    g.add_argument("--log-level", default=None,
                   help="console level (DEBUG/INFO/WARNING/ERROR); wins over -v/-q (env HF_LOG_LEVEL, default INFO)")
    g.add_argument("--log-format", choices=["console", "json"], default=os.environ.get("HF_LOG_FORMAT", "console"),
                   help="console: Rich text on stderr (default) | json: one JSON object per line on stderr "
                        "(env HF_LOG_FORMAT)")
    g.add_argument("--no-color", action="store_true", default=bool(os.environ.get("NO_COLOR")),
                   help="plain console output (also honours the NO_COLOR environment variable)")
    g.add_argument("--heartbeat", type=float, default=None, metavar="SECONDS",
                   help="seconds between worker.heartbeat events / manifest progress updates (default 30, 0 = off)")
    g.add_argument("--file-log-level", default="DEBUG", help="level of logs/events.jsonl and logs/run.log")
    g.add_argument("--scrapy-log-level", default=None, help="Scrapy's own loggers (default INFO, -vv: DEBUG)")
    g.add_argument("--split-logs", action="store_true", help="also write logs/app.log and logs/scrapy.log")


def resolve_log_levels(a: argparse.Namespace) -> tuple[str, str, str]:
    """(console, file, scrapy) levels. Precedence: --log-level > -q > -v > HF_LOG_LEVEL > INFO."""
    verbose = getattr(a, "verbose", 0) or 0
    if getattr(a, "log_level", None):
        console = a.log_level
    elif getattr(a, "quiet", False):
        console = "WARNING"
    elif verbose >= 1:
        console = "DEBUG"
    else:
        console = os.environ.get("HF_LOG_LEVEL", "INFO")
    scrapy = getattr(a, "scrapy_log_level", None) or ("DEBUG" if verbose >= 2 else "INFO")
    return console.upper(), (getattr(a, "file_log_level", None) or "DEBUG").upper(), scrapy.upper()


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
