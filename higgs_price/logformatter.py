"""Scrapy LogFormatter that logs a one-line summary per item instead of dumping the whole item
(the raw pricing-config response alone is ~4 MB)."""
from __future__ import annotations

import logging

from scrapy.logformatter import LogFormatter

from .validation import ident_of


def _summary(item) -> dict:
    d = dict(item) if item is not None else {}
    return {"kind": d.get("kind", type(item).__name__), "ident": d.get("endpoint") if d.get("kind") == "raw_response"
            else ident_of(d)}


class QuietLogFormatter(LogFormatter):
    def scraped(self, item, response, spider):
        s = _summary(item)
        return {"level": logging.DEBUG, "msg": "Scraped %(kind)s %(ident)s from %(src)s",
                "args": {**s, "src": getattr(response, "url", response)}}

    def dropped(self, item, exception, response, spider):
        s = _summary(item)
        return {"level": logging.WARNING, "msg": "Dropped %(kind)s %(ident)s: %(exception)s",
                "args": {**s, "exception": exception}}

    def item_error(self, item, exception, response, spider):
        s = _summary(item)
        return {"level": logging.ERROR, "msg": "Error processing %(kind)s %(ident)s",
                "args": s}
