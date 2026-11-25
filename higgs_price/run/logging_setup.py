"""Logging: console + per-run files (run/app/scrapy/errors logs + structured events.jsonl)."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

FILE_FMT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(name)s] %(message)s"
CONSOLE_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"
SCRAPY_PREFIXES = ("scrapy", "twisted", "py.warnings", "asyncio", "protego", "filelock")


class PrefixFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...], include: bool = True):
        super().__init__()
        self.prefixes, self.include = prefixes, include

    def filter(self, record: logging.LogRecord) -> bool:
        hit = record.name.startswith(self.prefixes)
        return hit if self.include else not hit


class RunIdFilter(logging.Filter):
    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", None),
            "msg": record.getMessage(),
        }
        for k in ("endpoint", "url", "status", "kind", "ident", "event"):
            if hasattr(record, k):
                d[k] = getattr(record, k)
        if record.exc_info:
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, ensure_ascii=False, default=str)


def _file(path: Path, level: int, fmt: logging.Formatter, flt: Optional[logging.Filter] = None) -> logging.Handler:
    h = logging.FileHandler(path, encoding="utf-8")
    h.setLevel(level)
    h.setFormatter(fmt)
    if flt:
        h.addFilter(flt)
    return h


def setup_logging(logs_dir: Optional[Path], run_id: str = "-", console_level: str = "INFO",
                  file_level: str = "DEBUG", scrapy_level: str = "INFO") -> list[logging.Handler]:
    """Configure the root logger. Returns the handlers so callers can remove them (tests / repeated runs)."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_higgs", False):
            root.removeHandler(h)
            h.close()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(FILE_FMT, DATE_FMT)
    rid = RunIdFilter(run_id)
    handlers: list[logging.Handler] = []

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level.upper())
    console.setFormatter(logging.Formatter(CONSOLE_FMT, "%H:%M:%S"))
    handlers.append(console)

    if logs_dir:
        logs_dir.mkdir(parents=True, exist_ok=True)
        handlers += [
            _file(logs_dir / "run.log", file_level.upper(), fmt),
            _file(logs_dir / "app.log", logging.DEBUG, fmt, PrefixFilter(("higgs_price",))),
            _file(logs_dir / "scrapy.log", logging.DEBUG, fmt, PrefixFilter(SCRAPY_PREFIXES)),
            _file(logs_dir / "errors.log", logging.WARNING, fmt),
            _file(logs_dir / "events.jsonl", file_level.upper(), JsonFormatter()),
        ]
    for h in handlers:
        h.addFilter(rid)
        h._higgs = True  # type: ignore[attr-defined]
        root.addHandler(h)

    logging.getLogger("scrapy").setLevel(scrapy_level.upper())
    logging.getLogger("twisted").setLevel(scrapy_level.upper())
    logging.getLogger("higgs_price").setLevel(logging.DEBUG)
    for noisy in ("asyncio", "filelock", "urllib3", "protego"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.captureWarnings(True)
    return handlers


def teardown_logging(handlers: list[logging.Handler]) -> None:
    root = logging.getLogger()
    for h in handlers:
        root.removeHandler(h)
        h.close()
