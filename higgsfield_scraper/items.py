"""Scrapy Items, generated from the pydantic schemas so the two never drift.

Each entity kind gets an Item class whose fields == the pydantic model's fields (+ `kind`).
`RawResponseItem` carries the untouched API response to the raw-archive pipeline.
"""
from __future__ import annotations

import scrapy

from .schemas import MODEL_BY_KIND


class RawResponseItem(scrapy.Item):
    kind = scrapy.Field()
    endpoint = scrapy.Field()
    url = scrapy.Field()
    params = scrapy.Field()
    status = scrapy.Field()
    fetched_at = scrapy.Field()
    body = scrapy.Field()


def _item_class(kind: str) -> type[scrapy.Item]:
    model = MODEL_BY_KIND[kind]
    name = "".join(p.title() for p in kind.split("_")) + "Item"
    fields = {"kind": scrapy.Field(), **{f: scrapy.Field() for f in model.model_fields}}
    return type(name, (scrapy.Item,), fields)


ITEM_BY_KIND: dict[str, type[scrapy.Item]] = {kind: _item_class(kind) for kind in MODEL_BY_KIND}

PlanSetItem = ITEM_BY_KIND["plan_set"]
PlanItem = ITEM_BY_KIND["plan"]
ModelItem = ITEM_BY_KIND["model"]
BenefitCardItem = ITEM_BY_KIND["benefit_card"]
ComparisonItem = ITEM_BY_KIND["comparison"]
MarketingPlanItem = ITEM_BY_KIND["marketing_plan"]
CreditPackageItem = ITEM_BY_KIND["credit_package"]
AuthPayloadItem = ITEM_BY_KIND["auth_payload"]


def to_item(entity: dict) -> scrapy.Item:
    cls = ITEM_BY_KIND[entity["kind"]]
    allowed = cls.fields
    return cls(**{k: v for k, v in entity.items() if k in allowed})
