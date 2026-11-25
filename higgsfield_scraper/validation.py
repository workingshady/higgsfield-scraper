"""Validate entity dicts against the pydantic schemas (shared by the Scrapy pipeline and `normalize`)."""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .schemas import MODEL_BY_KIND


class EntityInvalid(Exception):
    def __init__(self, kind: str, ident: str, errors: list[dict[str, Any]]):
        self.kind, self.ident, self.errors = kind, ident, errors
        super().__init__(f"{kind} {ident}: " + "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in errors[:5]))


def ident_of(entity: dict) -> str:
    for k in ("plan_id", "model_id", "card_id", "comparison_id", "marketing_id", "package_id",
              "plan_set_key", "endpoint"):
        if entity.get(k):
            return str(entity[k])
    return "?"


def validate_entity(entity: dict) -> dict:
    """Return the JSON-mode dump (Decimal -> str, datetime -> ISO) with `kind` kept; raise EntityInvalid."""
    kind = entity["kind"]
    data = {k: v for k, v in entity.items() if k != "kind"}
    try:
        obj = MODEL_BY_KIND[kind].model_validate(data)
    except ValidationError as e:
        raise EntityInvalid(kind, ident_of(entity), e.errors(include_url=False)) from None
    return {"kind": kind, **obj.model_dump(mode="json")}
