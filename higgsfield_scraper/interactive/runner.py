"""Child process that runs ONE scrape/normalize for the menu:

    python -m higgsfield_scraper.interactive.runner scrape community --max-items 10 --label x

It takes exactly the flag CLI's argv (same parser, same `cmd_*` functions) and adds the interactive extras:
one shared Rich console (stderr) for logs + the live progress panel, and `invocation_mode="interactive"`.

Why a subprocess: Scrapy's Twisted reactor can start only once per process, so the menu (which may run several
scrapes in a row) never starts a reactor itself — every crawl gets a fresh process. Ctrl-C reaches the child (same
console), Scrapy shuts down gracefully and the run is finalized as `cancelled` (exit 130).
"""
from __future__ import annotations

import sys
from typing import Optional

INVOCATION_MODE = "interactive"


def main(argv: Optional[list[str]] = None) -> int:
    from .. import cli
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    cli._load_dotenv()
    argv = cli._normalize_argv(list(sys.argv[1:] if argv is None else argv))
    a = cli.build_parser().parse_args(argv)
    if getattr(a, "command", None) not in ("scrape", "normalize"):
        return a.func(a)
    from ..run.logging_setup import make_console
    console = make_console(getattr(a, "no_color", False))
    try:
        if a.command == "normalize":
            return cli.cmd_normalize(a, console=console, invocation_mode=INVOCATION_MODE)
        if a.dry_run or a.log_format == "json":
            return cli.cmd_scrape(a, console=console, invocation_mode=INVOCATION_MODE)
        from .live import LiveProgress
        live = LiveProgress(console, title=f"scrape {a.scraper}")
        try:
            return cli.cmd_scrape(a, console=console, on_crawler=live.attach, invocation_mode=INVOCATION_MODE)
        finally:
            live.stop()
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
