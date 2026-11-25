"""Scrapy Items, generated from the pydantic schemas of every registered scraper so they never drift.

Each entity kind gets an Item class whose fields == the pydantic model's fields (+ `kind`).
`RawResponseItem` carries the untouched API response to the raw-archive pipeline.
"""
from __future__ import annotations

import scrapy


class RawResponseItem(scrapy.Item):
    kind = scrapy.Field()
    endpoint = scrapy.Field()
    url = scrapy.Field()
    params = scrapy.Field()
    status = scrapy.Field()
    fetched_at = scrapy.Field()
    body = scrapy.Field()


_CLASSES: dict[str, type[scrapy.Item]] = {}


def item_class(kind: str) -> type[scrapy.Item]:
    if kind not in _CLASSES:
        from .core.registry import all_models
        model = all_models()[kind]
        name = "".join(p.title() for p in kind.split("_")) + "Item"
        _CLASSES[kind] = type(name, (scrapy.Item,), {"kind": scrapy.Field(),
                                                     **{f: scrapy.Field() for f in model.model_fields}})
    return _CLASSES[kind]


def item_classes(kinds=None) -> dict[str, type[scrapy.Item]]:
    from .core.registry import all_models
    return {k: item_class(k) for k in (kinds or all_models())}


def __getattr__(name: str):          # backwards compatibility: ITEM_BY_KIND
    if name == "ITEM_BY_KIND":
        return item_classes()
    raise AttributeError(name)


def to_item(entity: dict) -> scrapy.Item:
    cls = item_class(entity["kind"])
    allowed = cls.fields
    return cls(**{k: v for k, v in entity.items() if k in allowed})
