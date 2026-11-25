"""RunManager: create run folder -> configure logging -> run Scrapy (or offline normalize) -> manifest."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .. import __version__
from ..selection import Selection
from .context import RunContext
from .logging_setup import setup_logging, teardown_logging

log = logging.getLogger("higgsfield_scraper.run")


def _git_commit() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except Exception:
        return None


def _versions() -> dict[str, Any]:
    import pydantic
    import scrapy
    return {"higgsfield_scraper": __version__, "python": platform.python_version(), "scrapy": scrapy.__version__,
            "pydantic": pydantic.VERSION, "platform": platform.platform(), "git_commit": _git_commit()}


def _status(stats: dict, export: dict, sel: Selection) -> str:
    if not export.get("ok"):
        return "failed"
    bad = [k for k in stats if k.startswith(("higgs/request_errors/", "higgs/non_json"))]
    non200 = [k for k in stats if k.startswith("higgs/responses/") and not k.endswith("/200")
              and not any(a in k for a in ("credit_packages", "unlim_catalog", "credit_price", "adjustable_credits"))]
    dropped = stats.get("validation/dropped", 0)
    return "partial" if bad or non200 or dropped else "success"


class RunManager:
    def __init__(self, runs_dir: str | Path = "runs", label: str = "scrape", console_level: str = "INFO",
                 file_level: str = "DEBUG", scrapy_level: str = "INFO"):
        self.runs_dir, self.label = Path(runs_dir), label
        self.levels = (console_level, file_level, scrapy_level)

    def _start(self, sel: Selection, args: dict) -> tuple[RunContext, list]:
        ctx = RunContext.create(self.runs_dir, self.label)
        handlers = setup_logging(ctx.logs_dir, ctx.run_id, *self.levels)
        ctx.write_manifest({"status": "running", "args": args, "selection": sel.to_dict(), "versions": _versions(),
                            "paths": {"logs": "logs/", "raw": "raw/", "http": "http/", "output": "output/"}})
        log.info("run %s started -> %s", ctx.run_id, ctx.run_dir.resolve())
        log.info("sections=%s plan_sets=%s endpoints=%s", sel.sections, sel.plan_set_keys, sel.endpoints())
        return ctx, handlers

    def _finish(self, ctx: RunContext, handlers: list, status: str, t0: float, extra: dict) -> int:
        finished = datetime.now(timezone.utc)
        files = sorted(p for p in ctx.run_dir.rglob("*") if p.is_file() and p.name != "manifest.json")
        ctx.write_manifest({"status": status, "finished_at": finished.isoformat(),
                            "duration_s": round(time.monotonic() - t0, 2), **extra, "files": ctx.relpaths(files)})
        ctx.finalize()
        log.info("run %s finished: %s in %.1fs", ctx.run_id, status.upper(), time.monotonic() - t0)
        log.info("outputs: %s", (ctx.output_dir / "dataset.json").resolve())
        teardown_logging(handlers)
        print(f"\n[{status.upper()}] run folder: {ctx.run_dir.resolve()}", file=sys.stderr)
        return {"success": 0, "partial": 2}.get(status, 1)

    # ------------------------------------------------------------ scrape
    def scrape(self, sel: Selection, token: Optional[str] = None, cache: bool = False,
               settings_overrides: Optional[dict] = None, args: Optional[dict] = None) -> int:
        os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "higgsfield_scraper.settings")
        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings

        from ..items import ITEM_BY_KIND
        from ..spiders.higgsfield import HiggsfieldSpider

        t0 = time.monotonic()
        ctx, handlers = self._start(sel, args or {})
        settings = get_project_settings()
        items_dir = (ctx.output_dir / "items").resolve()
        items_dir.mkdir(parents=True, exist_ok=True)
        settings.set("FEEDS", {
            (items_dir / f"{kind}.jsonl").as_uri(): {"format": "jsonlines", "encoding": "utf8", "overwrite": True,
                                                    "store_empty": False, "item_classes": [cls]}
            for kind, cls in ITEM_BY_KIND.items()
        }, priority="cmdline")
        settings.set("LOG_LEVEL", self.levels[2], priority="cmdline")
        settings.set("HTTPCACHE_ENABLED", cache, priority="cmdline")
        settings.set("HTTPCACHE_DIR", str((self.runs_dir / ".httpcache").resolve()), priority="cmdline")
        settings.set("LOG_INSTALL_ROOT_HANDLER", False, priority="cmdline")   # our handlers own the root logger
        for k, v in (settings_overrides or {}).items():
            settings.set(k, v, priority="cmdline")

        process = CrawlerProcess(settings)
        crawler = process.create_crawler(HiggsfieldSpider)
        stats: dict = {}
        export: dict = {"ok": False, "error": "crawl did not finish"}
        try:
            process.crawl(crawler, selection=sel, token=token, run_ctx=ctx)
            process.start()
            stats = crawler.stats.get_stats() if crawler.stats else {}
            export = getattr(crawler.spider, "export_result", export)
        except KeyboardInterrupt:
            log.warning("interrupted by user")
            export = {"ok": False, "error": "interrupted"}
        except Exception:
            log.exception("crawl crashed")
        status = _status(stats, export, sel)
        responses = defaultdict(dict)
        for k, v in stats.items():
            if k.startswith("higgs/responses/"):
                ep, code = k.removeprefix("higgs/responses/").rsplit("/", 1)
                responses[ep][code] = v
        return self._finish(ctx, handlers, status, t0, {
            "counts": export.get("counts"), "country_code": export.get("country_code"),
            "error": export.get("error"), "responses": responses,
            "scrapy_stats": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in stats.items()},
        })

    # --------------------------------------------------------- normalize
    def normalize(self, source_run: Path, sel: Selection, args: Optional[dict] = None) -> int:
        """Re-parse a previous run's raw/ folder offline into a new run (no network)."""
        from ..assemble import build_dataset
        from ..exporters import write_outputs
        from ..parsers import keep, parse_envelope
        from ..raw import Envelope
        from ..validation import EntityInvalid, validate_entity

        t0 = time.monotonic()
        ctx, handlers = self._start(sel, {**(args or {}), "source_run": str(source_run)})
        entities: dict[str, list[dict]] = defaultdict(list)
        dropped = 0
        raws = sorted((Path(source_run) / "raw").glob("*.json"))
        log.info("normalizing %d raw responses from %s", len(raws), source_run)
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
                    dropped += 1
                    log.warning("invalid %s", err)
        try:
            ds = build_dataset(entities, sel, run_id=ctx.run_id, label=ctx.label, scraped_at=ctx.started_at)
            write_outputs(ds, ctx.output_dir)
            status = "partial" if dropped else "success"
            extra = {"counts": ds["meta"]["counts"], "country_code": ds["meta"]["country_code"], "dropped": dropped}
        except Exception as e:
            log.exception("normalize failed")
            status, extra = "failed", {"error": repr(e)}
        return self._finish(ctx, handlers, status, t0, extra)
