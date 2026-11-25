"""RunManager: create run folder -> configure logging -> run Scrapy (or offline normalize) -> manifest.

Lifecycle events: run.started, config.loaded, (worker.heartbeat …), run.finished (one wide summary line).
Statuses: running -> success | partial | failure | cancelled. Exit codes: see EXIT_CODES.
The manifest is always finalized (in `finally`), also on crashes and Ctrl-C.
"""
from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from .. import __version__
from ..core import registry
from ..core.base import CommonOptions, RunMeta, ScraperDef, resolve
from ..core.redact import redact, redact_argv, redact_text
from .context import RunContext
from .logging_setup import DropReporter, emit, setup_logging, teardown_logging, utc_iso

if TYPE_CHECKING:  # pragma: no cover
    from scrapy.crawler import Crawler

log = logging.getLogger("higgsfield_scraper.run")

EXIT_OK, EXIT_FAILURE, EXIT_USAGE, EXIT_PARTIAL, EXIT_BLOCKED, EXIT_CANCELLED = 0, 1, 2, 3, 4, 130
EXIT_CODES = {"success": EXIT_OK, "failure": EXIT_FAILURE, "partial": EXIT_PARTIAL, "cancelled": EXIT_CANCELLED}
CANCEL_REASONS = ("shutdown", "cancelled", "interrupted")
_GIT_CACHE: Optional[dict] = None


def _git(*args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def git_info() -> dict[str, Any]:
    global _GIT_CACHE
    if _GIT_CACHE is None:
        commit = _git("rev-parse", "HEAD")
        status = _git("status", "--porcelain") if commit else None
        _GIT_CACHE = {"commit": commit, "branch": _git("rev-parse", "--abbrev-ref", "HEAD") if commit else None,
                      "dirty": bool(status) if status is not None else None}
    return dict(_GIT_CACHE)


def _git_commit() -> Optional[str]:          # backwards compatible helper
    c = git_info().get("commit")
    return c[:7] if c else None


def _versions() -> dict[str, Any]:
    import pydantic
    import scrapy
    return {"higgsfield_scraper": __version__, "python": platform.python_version(), "scrapy": scrapy.__version__,
            "pydantic": pydantic.VERSION, "platform": platform.platform(), "git_commit": _git_commit()}


def _issues(stats: dict, sdef: ScraperDef) -> list[str]:
    bad = [k for k in stats if k.startswith(("higgs/request_errors/", "higgs/non_json", "higgs/blocked"))]
    non200 = [k for k in stats if k.startswith("higgs/responses/") and not k.endswith("/200")
              and k.removeprefix("higgs/responses/").rsplit("/", 1)[0] not in sdef.optional_endpoints
              and not k.startswith("higgs/responses/media/")]
    dropped = ["validation/dropped"] if stats.get("validation/dropped", 0) else []
    return bad + non200 + dropped


def classify(stats: dict, export: dict, sdef: ScraperDef, close_reason: Optional[str] = None,
             interrupted: bool = False, crashed: bool = False) -> tuple[str, bool]:
    """(status, blocked) from Scrapy stats, the export result and the close reason.

    finished -> success, or partial when some requests/items failed; shutdown / Ctrl-C -> cancelled;
    closespider_* (limits) / blocked_by_bot_protection -> partial; crash or failed export -> failure."""
    blocked = bool(stats.get("higgs/blocked")) or close_reason == "blocked_by_bot_protection"
    if interrupted or (close_reason or "") in CANCEL_REASONS:
        return "cancelled", blocked
    if crashed or not export.get("ok"):
        return "failure", blocked
    if blocked or (close_reason or "").startswith("closespider_"):
        return "partial", blocked
    if close_reason not in (None, "finished"):
        return "partial", blocked
    return ("partial" if _issues(stats, sdef) else "success"), blocked


def _status(stats: dict, export: dict, sdef: ScraperDef) -> str:      # backwards compatible
    return classify(stats, export, sdef)[0]


def exit_code_for(status: str, blocked: bool = False) -> int:
    if status == "partial" and blocked:
        return EXIT_BLOCKED
    return EXIT_CODES.get(status, EXIT_FAILURE)


def _err(e: BaseException) -> dict[str, str]:
    return {"type": type(e).__name__, "message": redact_text(str(e))[:2000]}


class RunManager:
    def __init__(self, runs_dir: str | Path = "runs", label: str = "scrape", console_level: str = "INFO",
                 file_level: str = "DEBUG", scrapy_level: str = "INFO", *, log_format: str = "console",
                 no_color: bool = False, console: Any = None, heartbeat: Optional[float] = None,
                 split_logs: bool = False):
        self.runs_dir, self.label = Path(runs_dir), label
        self.levels = (console_level, file_level, scrapy_level)
        self.log_format, self.no_color, self.console = log_format, no_color, console
        self.heartbeat, self.split_logs = heartbeat, split_logs

    def _start(self, sdef: ScraperDef, sel, args: dict, common: CommonOptions, *, command: str,
               invocation_mode: str) -> tuple[RunContext, list]:
        ctx = RunContext.create(self.runs_dir, self.label)
        handlers = setup_logging(ctx.logs_dir, ctx.run_id, *self.levels, console=self.console,
                                 log_format=self.log_format, scraper=sdef.name, split_logs=self.split_logs,
                                 no_color=self.no_color)
        ctx.write_manifest({
            "status": "running", "scraper": sdef.name, "command_name": command, "args": args,
            "selection": sel.to_dict(), "common": common.to_dict(), "versions": _versions(),
            "command": redact_argv([sys.executable, *sys.argv]), "cwd": os.getcwd(),
            "invocation": {"mode": invocation_mode},
            "host": {"name": socket.gethostname(), "pid": os.getpid(), "python": platform.python_version(),
                     "os": platform.platform()},
            "git": git_info(), "progress": {}, "close_reason": None, "error": None,
            "paths": {"logs": "logs/", "raw": "raw/", "http": "http/", "media": "media/", "output": "output/"}})
        emit(log, "info", "run.started", f"run {ctx.run_id} started -> {ctx.run_dir.resolve()}",
             run__dir=str(ctx.run_dir.resolve()), run__label=ctx.label, command=command,
             invocation__mode=invocation_mode)
        cfg = {"selection": sel.to_dict(), "common": common.to_dict()}
        if hasattr(sel, "endpoints"):
            cfg["endpoints"] = sel.endpoints()
        emit(log, "info", "config.loaded",
             f"scraper={sdef.name} " + (f"sections={sel.sections} plan_sets={sel.plan_set_keys}"
                                        if hasattr(sel, "endpoints") else f"selection={sel.to_dict()}"),
             config=redact(cfg))
        if args.get("token") == "***":
            emit(log, "warning", "cli.flag.deprecated",
                 "--token is deprecated: put HF_TOKEN in the environment/.env or run `login` (auto-refreshing session)",
                 flag="--token")
        return ctx, handlers

    def _finish(self, ctx: RunContext, handlers: list, status: str, t0: float, extra: dict,
                blocked: bool = False) -> int:
        code = exit_code_for(status, blocked)
        duration_ms = int((time.monotonic() - t0) * 1000)
        try:
            files = sorted(p for p in ctx.run_dir.rglob("*") if p.is_file() and p.name != "manifest.json"
                           and not p.name.startswith("."))
            ctx.write_manifest({"status": status, "finished_at": utc_iso(), "duration_ms": duration_ms,
                                "duration_s": round(duration_ms / 1000, 2), "exit_code": code, "blocked": blocked,
                                **extra, "outputs": ctx.outputs(), "files": ctx.relpaths(files)})
            ctx.finalize()
        except Exception:
            emit(log, "error", "run.manifest.failed", "writing the final manifest failed", exc_info=True)
        m = ctx.meta
        counts = m.get("counts") or {}
        summary = {f"counts.{k}": v for k, v in counts.items()} if isinstance(counts, dict) else {}
        emit(log, "error" if status == "failure" else "info", "run.finished",
             f"run {ctx.run_id} finished: {status.upper()} in {duration_ms / 1000:.1f}s (exit {code})",
             outcome=status, duration_ms=duration_ms, exit_code=code, close_reason=m.get("close_reason"),
             dropped__count=m.get("dropped") or 0, limits_hit=m.get("limits_hit") or [],
             requests__count=m.get("requests_count"), responses__count=m.get("responses_count"),
             items__count=m.get("items_count"), errors__count=m.get("errors_count"), blocked=blocked,
             error__type=(m.get("error") or {}).get("type") if isinstance(m.get("error"), dict) else None,
             output__path=str((ctx.output_dir / "dataset.json").resolve()),
             **{k.replace(".", "__"): v for k, v in summary.items()})
        teardown_logging(handlers)
        print(f"\n[{status.upper()}] run folder: {ctx.run_dir.resolve()}", file=sys.stderr)
        return code

    # ------------------------------------------------------------ scrape
    def scrape(self, sel, token: Optional[str] = None, cache: bool = False,
               settings_overrides: Optional[dict] = None, args: Optional[dict] = None,
               scraper: str = registry.DEFAULT_SCRAPER, common: Optional[CommonOptions] = None,
               on_crawler: Optional[Callable[["Crawler"], None]] = None, invocation_mode: str = "flags") -> int:
        """Run one crawl. `on_crawler(crawler)` is called right after the crawler is created, before the reactor
        starts (hook for live dashboards: connect signals, read crawler.stats)."""
        os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "higgsfield_scraper.settings")
        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings

        from ..items import item_classes

        sdef = registry.get(scraper)
        spider_cls = resolve(sdef.spider_cls)
        common = common or CommonOptions()
        t0 = time.monotonic()
        ctx, handlers = self._start(sdef, sel, args or {}, common, command="scrape", invocation_mode=invocation_mode)
        crawler = None
        stats: dict = {}
        export: dict = {"ok": False, "error": "crawl did not finish"}
        interrupted = crashed = False
        error: Optional[dict] = None
        code = EXIT_FAILURE
        try:
            settings = get_project_settings()
            items_dir = (ctx.output_dir / "items").resolve()
            items_dir.mkdir(parents=True, exist_ok=True)
            settings.set("FEEDS", {
                (items_dir / f"{kind}.jsonl").as_uri(): {"format": "jsonlines", "encoding": "utf8", "overwrite": True,
                                                        "store_empty": False, "item_classes": [cls]}
                for kind, cls in item_classes(sdef.model_by_kind).items()
            }, priority="cmdline")
            settings.set("LOG_LEVEL", self.levels[2], priority="cmdline")
            settings.set("HTTPCACHE_ENABLED", cache, priority="cmdline")
            settings.set("HTTPCACHE_DIR", str((self.runs_dir / ".httpcache").resolve()), priority="cmdline")
            settings.set("LOG_INSTALL_ROOT_HANDLER", False, priority="cmdline")   # our handlers own the root logger
            if self.heartbeat is not None:
                settings.set("HIGGS_HEARTBEAT", float(self.heartbeat), priority="cmdline")
            for k, v in common.settings_overrides().items():
                settings.set(k, v, priority="cmdline")
            for k, v in (settings_overrides or {}).items():
                settings.set(k, v, priority="cmdline")

            process = CrawlerProcess(settings)
            crawler = process.create_crawler(spider_cls)
            if on_crawler is not None:
                on_crawler(crawler)
            kw = dict(selection=sel, token=token, run_ctx=ctx)
            if sdef.name != "pricing":
                kw["common"] = common
            process.crawl(crawler, **kw)
            process.start()
            stats = crawler.stats.get_stats() if crawler.stats else {}
            export = getattr(crawler.spider, "export_result", export)
        except KeyboardInterrupt as e:
            interrupted = True
            error = _err(e) | {"message": "interrupted by user"}
            emit(log, "warning", "run.interrupted", "interrupted by user (Ctrl-C)")
            export = {"ok": False, "error": "interrupted"}
        except Exception as e:
            crashed = True
            error = _err(e)
            emit(log, "error", "run.crashed", "crawl crashed", exc_info=True)
        finally:
            try:
                if crawler is not None and crawler.stats and not stats:
                    stats = crawler.stats.get_stats()
                close_reason = stats.get("finish_reason")
                status, blocked = classify(stats, export, sdef, close_reason, interrupted, crashed)
                spider = getattr(crawler, "spider", None)
                limits = list(getattr(spider, "limits_hit", []) or [])
                if close_reason and str(close_reason).startswith("closespider_"):
                    emit(log, "warning", "limit.hit", f"safety cap reached: {close_reason}", limit=close_reason,
                         limit__kind="safety")
                    if close_reason not in limits:
                        limits.append(close_reason)
                if blocked:
                    emit(log, "error", "request.blocked", "run stopped by bot protection (no evasion attempted)",
                         close_reason=close_reason)
                if error is None and status == "failure":
                    error = {"type": "ExportFailed", "message": redact_text(str(export.get("error")))}
                responses: dict = defaultdict(dict)
                for k, v in stats.items():
                    if k.startswith("higgs/responses/"):
                        ep, c = k.removeprefix("higgs/responses/").rsplit("/", 1)
                        responses[ep][c] = v
                prov = getattr(spider, "token_provider", None)
                auth = None
                if prov is not None and getattr(prov, "configured", False):
                    try:
                        auth = {k: v for k, v in prov.status().items() if k != "session_id"}
                    except Exception:
                        auth = {"ok": False}
                dropped = int(stats.get("validation/dropped", 0) or 0)
                code = self._finish(ctx, handlers, status, t0, {
                    "counts": export.get("counts"), "country_code": export.get("country_code"),
                    "close_reason": close_reason, "error": error, "responses": responses, "limits_hit": limits,
                    "dropped": dropped,
                    "requests_count": stats.get("downloader/request_count", 0),
                    "responses_count": stats.get("downloader/response_count", 0),
                    "items_count": stats.get("item_scraped_count", 0),
                    "errors_count": int(stats.get("log_count/ERROR", 0) or 0),
                    "auth": auth,
                    "progress": {**(ctx.meta.get("progress") or {}), "final": True,
                                 "responses.count": stats.get("downloader/response_count", 0),
                                 "items.count": stats.get("item_scraped_count", 0),
                                 **({"percent": 100.0, "eta_s": 0} if status == "success" else {})},
                    "scrapy_stats": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in stats.items()},
                }, blocked=blocked)
            except Exception:
                emit(log, "critical", "run.finalize.failed", "finalizing the run failed", exc_info=True)
                teardown_logging(handlers)
                code = EXIT_FAILURE
        return code

    # --------------------------------------------------------- normalize
    def normalize(self, source_run: Path, sel, args: Optional[dict] = None, scraper: str = registry.DEFAULT_SCRAPER,
                  common: Optional[CommonOptions] = None, invocation_mode: str = "flags") -> int:
        """Re-parse a previous run's raw/ folder offline into a new run (no network)."""
        from ..raw import Envelope
        from ..validation import EntityInvalid, validate_entity

        sdef = registry.get(scraper)
        common = common or CommonOptions()
        parse_envelope, keep = sdef.parse_envelope, sdef.keep
        t0 = time.monotonic()
        ctx, handlers = self._start(sdef, sel, {**(args or {}), "source_run": str(source_run)}, common,
                                    command="normalize", invocation_mode=invocation_mode)
        drops = DropReporter(log)
        status, extra = "failure", {"error": {"type": "Unfinished", "message": "normalize did not finish"}}
        code = EXIT_FAILURE
        try:
            entities: dict[str, list[dict]] = defaultdict(list)
            raws = sorted((Path(source_run) / "raw").glob("*.json"))
            emit(log, "info", "normalize.started", f"normalizing {len(raws)} raw responses from {source_run}",
                 raw__count=len(raws), source_run=str(source_run))
            for path in raws:
                env = Envelope.load(path)
                env.save(ctx.raw_dir)
                for e in parse_envelope(env, sel):
                    if not keep(e, sel):
                        continue
                    try:
                        v = validate_entity(e)
                        entities[v["kind"]].append(v)
                    except EntityInvalid as err:
                        drops(err.kind, err.ident, err)
            ids = registry.all_id_fields()
            for kind, rows in list(entities.items()):                 # same dedup as the crawl pipeline
                f = ids.get(kind)
                if f:
                    seen, uniq = set(), []
                    for r in rows:
                        k = r.get(f)
                        if k in seen and k not in (None, ""):
                            continue
                        seen.add(k)
                        uniq.append(r)
                    entities[kind] = uniq
            limits: list[str] = []
            if common.max_items is not None and sdef.name != "pricing":   # same --max-items budget as the crawl
                budget = common.max_items
                for kind in getattr(resolve(sdef.spider_cls), "primary_kinds", ()):
                    rows = entities.get(kind, [])
                    if len(rows) > budget:
                        emit(log, "info", "limit.hit",
                             f"normalize: max_items={common.max_items} — keeping {budget} of {len(rows)} {kind}",
                             limit=f"max_items={common.max_items}", limit__kind="user", item__kind=kind)
                        limits.append(f"max_items={common.max_items} reached")
                    entities[kind] = rows[:budget]
                    budget = max(0, budget - len(entities[kind]))
            ds = sdef.build_dataset(entities, sel, RunMeta(run_id=ctx.run_id, label=ctx.label,
                                                           scraped_at=ctx.started_at, common=common))
            sdef.write_outputs(ds, ctx.output_dir)
            status = "partial" if drops.count else "success"
            extra = {"counts": ds["meta"].get(sdef.counts_key), "country_code": ds["meta"].get("country_code"),
                     "dropped": drops.count, "error": None, "close_reason": "finished", "limits_hit": limits,
                     "items_count": sum(len(v) for v in entities.values())}
        except KeyboardInterrupt as e:
            status, extra = "cancelled", {"error": _err(e) | {"message": "interrupted by user"},
                                          "close_reason": "interrupted", "dropped": drops.count}
            emit(log, "warning", "run.interrupted", "interrupted by user (Ctrl-C)")
        except Exception as e:
            emit(log, "error", "run.crashed", "normalize failed", exc_info=True)
            status, extra = "failure", {"error": _err(e), "dropped": drops.count}
        finally:
            code = self._finish(ctx, handlers, status, t0, extra)
        return code
