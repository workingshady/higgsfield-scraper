"""Logging: Rich console (or JSON on stderr) + per-run files, structured `entity.action` events, central redaction.

<run>/logs/
  events.jsonl   canonical: every record as one JSON object (envelope + dotted fields), DEBUG and up
  run.log        the same records as human text:  2026-11-25T14:30:05.120Z INFO  logger  event  message  k=v …
  errors.log     WARNING and up, with full (redacted) tracebacks
  access.jsonl   only `http.request.finished` lines (one per HTTP response / failed attempt)
  (app.log + scrapy.log only with --split-logs)

Emit events with `emit(log, "info", "run.started", "run started", run__dir="…")` (`__` -> `.` in field names).
Every line carries run.id / scraper.name (contextvars, see `bind_run`), service/process/host resource fields and is
redacted by `core.redact` (message, fields and exception text) before it reaches any handler.
"""
from __future__ import annotations

import contextvars
import copy
import json
import logging
import math
import os
import socket
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import __version__
from ..core.redact import REDACTED, is_secret_key, redact, redact_text

SERVICE_NAME = "higgsfield_scraper"
SCRAPY_PREFIXES = ("scrapy", "twisted", "py.warnings", "asyncio", "protego", "filelock")
ENVELOPE = ("timestamp", "level", "logger", "event", "message")
RESOURCE = ("run.id", "scraper.name", "service.name", "service.version", "process.pid", "host.name")
ACCESS_EVENT = "http.request.finished"
MAX_VALUE_LEN = 4000
DEFAULT_EVENT = "log"
_STD_ATTRS = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {"message", "asctime", "taskName"}
_SKIP_EXTRAS = {"spider", "crawler", "item", "response", "request", "failure", "_fields", "event",
                "_higgs_doc", "run_id"}
_HOST = socket.gethostname()

_RUN: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("higgs_run", default=None)
_RUN_FALLBACK: dict[str, Any] = {}          # same values, for threads/callbacks that don't inherit the context


# ---------------------------------------------------------------- helpers
def utc_iso(ts: Any = None) -> str:
    """ISO-8601 UTC with milliseconds and Z: 2026-11-25T14:30:05.120Z (accepts epoch seconds or datetime)."""
    if ts is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(ts, datetime):
        dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    else:
        dt = datetime.fromtimestamp(float(ts), timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(text: Optional[str]) -> Optional[datetime]:
    """Inverse of utc_iso (Python 3.10's fromisoformat does not accept 'Z')."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def bind_run(run_id: Optional[str], scraper: Optional[str] = None) -> None:
    """Attach run.id / scraper.name to every log line from now on (this context and threads without one)."""
    data = {"run.id": run_id, "scraper.name": scraper}
    _RUN.set(data)
    _RUN_FALLBACK.clear()
    _RUN_FALLBACK.update(data)


def unbind_run() -> None:
    _RUN.set(None)
    _RUN_FALLBACK.clear()


def current_run() -> dict:
    return _RUN.get() or dict(_RUN_FALLBACK)


def _level(level: Any) -> int:
    if isinstance(level, int):
        return level
    return logging.getLevelName(str(level).upper()) if not str(level).isdigit() else int(level)


def emit(log: logging.Logger | logging.LoggerAdapter, level: Any, event: str, msg: Optional[str] = None,
         exc_info: Any = None, **fields: Any) -> None:
    """Log a structured event. `fields` use `__` for dots: emit(log, "info", "x.y", "msg", http__status_code=200)."""
    lvl = _level(level)
    target = log.logger if isinstance(log, logging.LoggerAdapter) else log
    if not target.isEnabledFor(lvl):
        return
    dotted = {k.replace("__", "."): v for k, v in fields.items()}
    target.log(lvl, "%s", msg if msg is not None else event, exc_info=exc_info,
               extra={"event": event, "_fields": dotted}, stacklevel=2)


def _clean(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, str) and len(v) > MAX_VALUE_LEN:
        return f"{v[:MAX_VALUE_LEN]}...[+{len(v) - MAX_VALUE_LEN} chars]"
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, datetime):
        return utc_iso(v)
    if isinstance(v, (list, tuple, set, frozenset)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    return str(v)


def _exc_text(exc_info) -> Optional[str]:
    if not exc_info or exc_info is True or exc_info[0] is None:
        return None
    return "".join(traceback.format_exception(*exc_info)).rstrip()


def record_doc(record: logging.LogRecord) -> dict[str, Any]:
    """The redacted, ordered event dict of a record (computed once, cached on the record)."""
    doc = getattr(record, "_higgs_doc", None)
    if doc is not None:
        return doc
    try:
        message = record.getMessage()
    except Exception:
        message = str(record.msg)
    fields: dict[str, Any] = {}
    for k, v in record.__dict__.items():           # legacy `extra={...}` keys from our code and libraries
        if k not in _STD_ATTRS and k not in _SKIP_EXTRAS and not k.startswith("_"):
            fields[k] = v
    fields.update(getattr(record, "_fields", None) or {})
    run = current_run()
    head: dict[str, Any] = {
        "timestamp": utc_iso(record.created),
        "level": record.levelname,
        "logger": record.name,
        "event": getattr(record, "event", None) or DEFAULT_EVENT,
        "message": redact_text(message),
        "run.id": fields.pop("run.id", None) or run.get("run.id"),
        "scraper.name": fields.pop("scraper.name", None) or run.get("scraper.name"),
        "service.name": SERVICE_NAME,
        "service.version": __version__,
        "process.pid": record.process or os.getpid(),
        "host.name": _HOST,
    }
    if record.exc_info and record.exc_info[0] is not None:
        et, ev, _ = record.exc_info
        fields.setdefault("error.type", et.__name__)
        fields["exception.type"] = et.__name__
        fields["exception.message"] = redact_text(str(ev))
        fields["exception.stacktrace"] = redact_text(_exc_text(record.exc_info))
    elif record.exc_text:
        fields["exception.stacktrace"] = redact_text(record.exc_text)
    clean = {}
    for k, v in fields.items():
        if is_secret_key(k) and v not in (None, "", "***") and not isinstance(v, bool):
            clean[k] = REDACTED
        else:
            v = redact(_clean(v))
            if k == "exception.stacktrace" and isinstance(v, str):
                clean[k] = v
            else:
                clean[k] = _clean(v)
    doc = {**head, **dict(sorted(clean.items()))}
    record._higgs_doc = doc  # type: ignore[attr-defined]
    return doc


def _esc(v: Any) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s.replace("\r", "\\r").replace("\n", "\\n")          # no raw CR/LF: one record = one line


# ------------------------------------------------------------- formatters
class JsonFormatter(logging.Formatter):
    """One JSON object per line: envelope keys first, then sorted dotted fields."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_doc(record), ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """`2026-11-25T14:30:05.120Z INFO    logger  event  message  k=v …` — CR/LF escaped, tracebacks indented."""

    def __init__(self, tracebacks: bool = True):
        super().__init__()
        self.tracebacks = tracebacks

    def format(self, record: logging.LogRecord) -> str:
        d = record_doc(record)
        parts = [d["timestamp"], f"{d['level']:<7}", d["logger"], d["event"], _esc(d["message"])]
        extras = [f"{k}={_esc(v)}" for k, v in d.items()
                  if k not in ENVELOPE and k not in RESOURCE and not k.startswith("exception.") and v is not None]
        line = "  ".join(parts) + ("  " + " ".join(extras) if extras else "")
        st = d.get("exception.stacktrace")
        if st and self.tracebacks:
            line += "\n" + "\n".join("    | " + x.replace("\r", "\\r") for x in st.splitlines())
        return line


class ConsoleNoiseFilter(logging.Filter):
    """Keeps Scrapy's start-up banners and the final stats dump out of the console (they stay in the log files)."""
    QUIET = ("scrapy.statscollectors", "scrapy.middleware", "scrapy.addons", "scrapy.crawler", "scrapy.utils.log",
             "scrapy.extensions.remote_control", "scrapy.extensions.telnet")

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or not record.name.startswith(self.QUIET)


class EventFilter(logging.Filter):
    def __init__(self, event: str):
        super().__init__()
        self.event = event

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "event", None) == self.event


class PrefixFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...], include: bool = True):
        super().__init__()
        self.prefixes, self.include = prefixes, include

    def filter(self, record: logging.LogRecord) -> bool:
        hit = record.name.startswith(self.prefixes)
        return hit if self.include else not hit


class RunIdFilter(logging.Filter):
    """Backwards compatible: keeps `record.run_id` (old JsonFormatter field) for third-party formatters."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = current_run().get("run.id") or self.run_id
        return True


# ---------------------------------------------------------------- console
def _redacted_exc(exc: Optional[BaseException], depth: int = 0) -> Optional[BaseException]:
    """A stand-in exception with the same type name whose text is redacted (Rich tracebacks print str(exc))."""
    if exc is None or depth > 5:
        return None
    text = str(exc)
    red = redact_text(text)
    cause = _redacted_exc(exc.__cause__, depth + 1)
    ctx = _redacted_exc(exc.__context__, depth + 1) if exc.__context__ is not exc.__cause__ else cause
    if red == text and cause is exc.__cause__ and ctx is exc.__context__:
        return exc
    stand_in_cls = type(type(exc).__name__, (Exception,), {"__str__": lambda self: red,
                                                            "__module__": type(exc).__module__})
    new = stand_in_cls()
    new.__cause__, new.__context__ = cause, ctx
    new.__suppress_context__ = exc.__suppress_context__
    new.__traceback__ = exc.__traceback__
    return new


def make_console(no_color: bool = False) -> Any:
    from rich.console import Console
    return Console(stderr=True, no_color=no_color or bool(os.environ.get("NO_COLOR")) or None,
                   highlight=not no_color)


def _console_handler(console: Any, level: str) -> logging.Handler:
    from rich.logging import RichHandler
    from rich.text import Text

    def utc_time(dt: datetime) -> Text:
        return Text(dt.astimezone(timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z")

    class _Handler(RichHandler):
        def emit(self, record: logging.LogRecord) -> None:
            d = record_doc(record)
            r = copy.copy(record)
            shown = [f"{k}={v}" for k, v in d.items() if k not in ENVELOPE and k not in RESOURCE
                     and not k.startswith(("exception.", "error.")) and v is not None and not isinstance(v, (dict, list))]
            ev = "" if d["event"] == DEFAULT_EVENT else f"{d['event']}  "
            text = _esc(d["message"])
            if record.levelno < logging.WARNING:
                shown = []                         # INFO/DEBUG: the message says it; fields are in events.jsonl
            shown = [x for x in shown if len(x) <= 120][:8]
            r.msg, r.args = ev + text + (("  " + " ".join(shown)) if shown else ""), None
            if r.exc_info and r.exc_info[1] is not None:
                ex = _redacted_exc(r.exc_info[1])
                r.exc_info = (type(ex), ex, r.exc_info[2])
            r.exc_text = None
            super().emit(r)

    h = _Handler(console=console, rich_tracebacks=True, tracebacks_show_locals=False, markup=False,
                 show_path=False, log_time_format=utc_time, omit_repeated_times=False)
    h.setLevel(_level(level))
    return h


# ------------------------------------------------------------------ hooks
_HOOKS_INSTALLED = False


def install_excepthooks() -> None:
    """Uncaught exceptions (main thread and threads) -> one `app.crashed` critical line."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True
    log = logging.getLogger("higgsfield_scraper.app")
    prev_hook = sys.excepthook

    def on_crash(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return prev_hook(exc_type, exc, tb)
        emit(log, logging.CRITICAL, "app.crashed", f"uncaught {exc_type.__name__}", exc_info=(exc_type, exc, tb))

    def on_thread_crash(args):
        if args.exc_type is SystemExit:
            return
        emit(log, logging.CRITICAL, "app.crashed", f"uncaught {args.exc_type.__name__} in thread",
             exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
             thread__name=getattr(args.thread, "name", None))

    sys.excepthook = on_crash
    threading.excepthook = on_thread_crash


def _file(path: Path, level: Any, fmt: logging.Formatter, flt: Optional[logging.Filter] = None) -> logging.Handler:
    h = logging.FileHandler(path, encoding="utf-8")
    h.setLevel(_level(level))
    h.setFormatter(fmt)
    if flt:
        h.addFilter(flt)
    return h


def setup_logging(logs_dir: Optional[Path], run_id: str = "-", console_level: str = "INFO",
                  file_level: str = "DEBUG", scrapy_level: str = "INFO", *, console: Any = None,
                  log_format: str = "console", scraper: Optional[str] = None, split_logs: bool = False,
                  no_color: bool = False, announce: bool = True) -> list[logging.Handler]:
    """Configure the root logger. Returns the handlers so callers can remove them (tests / repeated runs).

    console:    a rich.console.Console to log through (share it with a rich Live display); default: a new stderr one.
    log_format: "console" (Rich) or "json" (one JSON object per line on stderr).
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_higgs", False):
            root.removeHandler(h)
            h.close()
    root.setLevel(logging.DEBUG)
    bind_run(None if run_id == "-" else run_id, scraper)
    rid = RunIdFilter(run_id)
    handlers: list[logging.Handler] = []

    log_format = (log_format or "console").lower()
    if log_format == "json":
        c = logging.StreamHandler(sys.stderr)
        c.setLevel(_level(console_level))
        c.setFormatter(JsonFormatter())
    else:
        c = _console_handler(console if console is not None else make_console(no_color), console_level)
    if _level(console_level) > logging.DEBUG:
        c.addFilter(ConsoleNoiseFilter())
    handlers.append(c)

    if logs_dir:
        logs_dir = Path(logs_dir)
        logs_dir.mkdir(parents=True, exist_ok=True)
        handlers += [
            _file(logs_dir / "events.jsonl", file_level, JsonFormatter()),
            _file(logs_dir / "run.log", file_level, TextFormatter()),
            _file(logs_dir / "errors.log", logging.WARNING, TextFormatter()),
            _file(logs_dir / "access.jsonl", logging.DEBUG, JsonFormatter(), EventFilter(ACCESS_EVENT)),
        ]
        if split_logs:
            handlers += [
                _file(logs_dir / "app.log", logging.DEBUG, TextFormatter(), PrefixFilter(("higgsfield_scraper",))),
                _file(logs_dir / "scrapy.log", logging.DEBUG, TextFormatter(), PrefixFilter(SCRAPY_PREFIXES)),
            ]
    for h in handlers:
        h.addFilter(rid)
        h._higgs = True  # type: ignore[attr-defined]
        root.addHandler(h)

    logging.getLogger("scrapy").setLevel(_level(scrapy_level))
    logging.getLogger("twisted").setLevel(_level(scrapy_level))
    logging.getLogger("higgsfield_scraper").setLevel(logging.DEBUG)
    for noisy in ("asyncio", "filelock", "urllib3", "protego"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.captureWarnings(True)
    install_excepthooks()
    if announce:
        emit(logging.getLogger("higgsfield_scraper.app"), "info", "app.started",
             f"{SERVICE_NAME} {__version__} started", log__format=log_format, log__level=str(console_level).upper(),
             python__version=sys.version.split()[0], logs__dir=str(logs_dir) if logs_dir else None)
    return handlers


def teardown_logging(handlers: list[logging.Handler]) -> None:
    root = logging.getLogger()
    for h in handlers:
        root.removeHandler(h)
        h.close()
    unbind_run()


class DropReporter:
    """`item.dropped` warnings for the first `cap` drops of a run; after that drops are only counted (+ one notice)."""

    def __init__(self, log: logging.Logger, cap: int = 100):
        self.log, self.cap, self.count, self.logged = log, cap, 0, 0

    def __call__(self, kind: Any, ident: Any, reason: Any, level: Any = "warning") -> None:
        self.count += 1
        if self.logged < self.cap:
            self.logged += 1
            emit(self.log, level, "item.dropped", f"dropped {kind} {ident}: {reason}", item__kind=kind,
                 item__id=ident, reason=str(reason)[:500], dropped__count=self.count)
        elif self.logged == self.cap:
            self.logged += 1
            emit(self.log, "warning", "item.dropped.suppressed",
                 f"more than {self.cap} items dropped; further drops are only counted (see run.finished)",
                 dropped__count=self.count)
