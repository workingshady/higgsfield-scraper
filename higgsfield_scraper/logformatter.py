"""Scrapy LogFormatter that logs a one-line summary per item instead of dumping the whole item
(the raw pricing-config response alone is ~4 MB). Dropped items become `item.dropped` events: the first 100 per run
are logged (validation drops as warnings, duplicates as debug), after that they are only counted."""
from __future__ import annotations

import logging

from scrapy.logformatter import LogFormatter

from .run.logging_setup import DropReporter
from .validation import ident_of

log = logging.getLogger("higgsfield_scraper.items")


def _summary(item) -> dict:
    d = dict(item) if item is not None else {}
    return {"kind": d.get("kind", type(item).__name__), "ident": d.get("endpoint") if d.get("kind") == "raw_response"
            else ident_of(d)}


class QuietLogFormatter(LogFormatter):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.drops = DropReporter(log)

    def scraped(self, item, response, spider):
        s = _summary(item)
        return {"level": logging.DEBUG, "msg": "Scraped %(kind)s %(ident)s from %(src)s",
                "args": {**s, "src": getattr(response, "url", response)}}

    def dropped(self, item, exception, response, spider):
        s = _summary(item)
        reason = str(exception)
        self.drops(s["kind"], s["ident"], reason, level="debug" if reason.startswith("duplicate ") else "warning")
        return None

    def item_error(self, item, exception, response, spider):
        s = _summary(item)                     # Scrapy logs this with exc_info (traceback kept)
        return {"level": logging.ERROR, "msg": "Error processing %(kind)s %(ident)s", "args": s}
