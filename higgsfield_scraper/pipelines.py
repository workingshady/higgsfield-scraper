"""Item pipelines: raw archive (50) -> pydantic validation (300) -> collect + assemble + export (800).

Pipelines receive the crawler via `from_crawler` (Scrapy >= 2.13 style); the optional `spider` parameters keep
them working on older Scrapy versions that still pass it.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scrapy.exceptions import DropItem

from .assemble import build_dataset
from .exporters import write_outputs
from .items import RawResponseItem, to_item
from .raw import Envelope
from .run.context import RunContext
from .validation import EntityInvalid, validate_entity

log = logging.getLogger(__name__)


def run_ctx_for(crawler) -> RunContext:
    """RunManager attaches `spider.run_ctx`; for plain `scrapy crawl` create one from settings."""
    spider = crawler.spider
    ctx = getattr(spider, "run_ctx", None)
    if ctx is None:
        s = crawler.settings
        ctx = RunContext.create(s.get("HIGGS_RUNS_DIR", "runs"), s.get("HIGGS_RUN_LABEL", "scrapy-crawl"))
        spider.run_ctx = ctx
        log.info("created run folder %s", ctx.run_dir)
    return ctx


class _Base:
    def __init__(self, crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    @property
    def stats(self):
        return self.crawler.stats


class RawArchivePipeline(_Base):
    """Save every API response untouched to <run>/raw/<endpoint>__<params>.json."""

    def open_spider(self, spider=None):
        self.ctx = run_ctx_for(self.crawler)

    def process_item(self, item, spider=None):
        if isinstance(item, RawResponseItem):
            env = Envelope(endpoint=item["endpoint"], url=item["url"], status=item["status"], body=item["body"],
                           params=item["params"] or {}, fetched_at=datetime.fromisoformat(item["fetched_at"]))
            path: Path = env.save(self.ctx.raw_dir)
            self.stats.inc_value("higgs/raw_saved")
            log.debug("raw saved %s (%d bytes)", path.name, path.stat().st_size)
        return item


class ValidationPipeline(_Base):
    """Validate entities with pydantic; drop invalid ones with per-field error stats."""

    def process_item(self, item, spider=None):
        if isinstance(item, RawResponseItem):
            return item
        try:
            clean = validate_entity(dict(item))
        except EntityInvalid as e:
            self.stats.inc_value("validation/dropped")
            self.stats.inc_value(f"validation/dropped/{e.kind}")
            for err in e.errors:
                self.stats.inc_value(f"validation/error/{e.kind}/{'.'.join(map(str, err['loc']))}")
            log.warning("invalid %s", e, extra={"kind": e.kind, "ident": e.ident})
            raise DropItem(str(e)) from None
        self.stats.inc_value(f"validation/ok/{clean['kind']}")
        return to_item(clean)


class CollectAndExportPipeline(_Base):
    """Collect validated entities; on close build the nested dataset and write every output file."""

    def open_spider(self, spider=None):
        self.ctx = run_ctx_for(self.crawler)
        self.entities: dict[str, list[dict]] = defaultdict(list)

    def process_item(self, item, spider=None):
        if not isinstance(item, RawResponseItem):
            d = dict(item)
            self.entities[d["kind"]].append(d)
        return item

    def close_spider(self, spider=None):
        spider = self.crawler.spider
        warnings = [f"{k.removeprefix('higgs/responses/')} x{v}" for k, v in self.stats.get_stats().items()
                    if k.startswith("higgs/responses/") and not k.endswith("/200")]
        try:
            ds = build_dataset(self.entities, spider.selection, run_id=self.ctx.run_id, label=self.ctx.label,
                               scraped_at=self.ctx.started_at, warnings=warnings)
            files = write_outputs(ds, self.ctx.output_dir)
            spider.export_result = {"ok": True, "counts": ds["meta"]["counts"], "files": files,
                                    "country_code": ds["meta"]["country_code"]}
            for k, v in ds["meta"]["counts"].items():
                self.stats.set_value(f"higgs/output/{k}", v)
            log.info("dataset: %s", ", ".join(f"{k}={v}" for k, v in ds["meta"]["counts"].items()))
        except Exception as e:  # raw data is already on disk; record and keep going
            self.stats.set_value("higgs/assemble_failed", repr(e))
            spider.export_result = {"ok": False, "error": repr(e)}
            log.exception("assembling/exporting the dataset failed")
