"""Shared schema building blocks."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Iterator, Literal, Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_serializer
from pydantic_core import PydanticOmit

SCHEMA_VERSION = 1

# Money in major units (USD), serialized as a decimal string in JSON (e.g. "35.00").
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
Scalar = str | int | float | bool


class Strict(BaseModel):
    """Our own output shapes: unknown fields are a bug, so forbid them."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Provenance(Strict):
    endpoint: str
    url: str
    params: dict[str, str] = Field(default_factory=dict)
    fetched_at: AwareDatetime


# ------------------------------------------------------------------ login-only optional fields
# Fields that only exist in runs with a session (`--logged-in-prices`, `--sections account`). Two rules keep every
# default output byte-identical to the pre-flag baseline (scripts/check_pricing_identity.py):
#   1. LoginOptional models drop these fields from their dump when they are None (old rows never gain a `null` key);
#   2. the JSON Schema omits them unless `login_fields_in_schema()` is active. The exporter turns it on only for a
#      dataset that actually contains login-only data, so that dataset's schema/dataset.schema.json still validates it.
_LOGIN_FIELDS_IN_SCHEMA: ContextVar[bool] = ContextVar("login_fields_in_schema", default=False)


class _LoginOnlyJsonSchema:
    """`Annotated[...]` marker: like pydantic's SkipJsonSchema, but only while login fields are hidden."""

    def __get_pydantic_json_schema__(self, core_schema, handler):
        if not _LOGIN_FIELDS_IN_SCHEMA.get():
            raise PydanticOmit
        return handler(core_schema)

    def __hash__(self) -> int:
        return hash(type(self))

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self)


LoginOnly = _LoginOnlyJsonSchema()
# set ONLY on rows that the anonymous response did not contain (absent on every other row)
Visibility = Literal["logged_in"]
VISIBILITY_DESCRIPTION = ("'logged_in' = this row is only returned to a logged-in user (opt-in --logged-in-prices); "
                          "absent on rows the anonymous API returns too")


@contextmanager
def login_fields_in_schema(enabled: bool = True) -> Iterator[None]:
    token = _LOGIN_FIELDS_IN_SCHEMA.set(enabled)
    try:
        yield
    finally:
        _LOGIN_FIELDS_IN_SCHEMA.reset(token)


class LoginOptional(Strict):
    """Strict model whose `__login_only__` fields are left out of the dump while None (see the rules above)."""

    __login_only__: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _drop_unset_login_fields(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for name in self.__login_only__:
                if data.get(name) is None:
                    data.pop(name, None)
        return data


def make_id(*parts: Any) -> str:
    """Stable 16-hex id from a natural key (never include volatile values like prices)."""
    key = "|".join("" if p is None else str(p).strip().lower() for p in parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def cents_to_money(value: Optional[int | float]) -> Optional[Decimal]:
    if value is None:
        return None
    return (Decimal(str(value)) / 100).quantize(Decimal("0.01"))


def percent(before: Optional[Decimal], after: Optional[Decimal]) -> Optional[Decimal]:
    if before in (None, 0) or after is None:
        return None
    return ((1 - after / before) * 100).quantize(Decimal("0.01"))
