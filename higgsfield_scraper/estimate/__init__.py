"""Estimated credit (and optional USD) cost of a generation, from the pricing data (/job-sets/costs).

Interface (stable — the community scraper codes against it; implementation in estimator.py):

    est = CostEstimator.from_job_costs_body(body, usd_per_credit=0.025, usd_reference="ps_a3 plus annual")
    est.estimate(job_set_type="seedance_2_5", params={...generation params...}, media_type="video") -> dict
        # JSON-mode dict matching EstimatedCost below

`media_type` is "image" | "video" | "audio" | None. Estimation is always OPTIONAL: callers decide per media type
(e.g. community `--estimate-cost images|videos|all`) and pass status "skipped" otherwise.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated, Iterator, Literal, Optional

from pydantic import Field, model_serializer
from pydantic_core import PydanticOmit

from ..schemas.common import Scalar, Strict

EstimateStatus = Literal["exact", "approximate", "unpriced", "skipped"]

#: estimator versions selectable with --estimate-version (1 = default, unchanged; 2 = JS formulas, estimate/v2.py)
ESTIMATE_VERSIONS = (1, 2)
DEFAULT_ESTIMATE_VERSION = 1

# `formula_version` exists only on v2 estimates. Same two rules as LoginOptional (schemas/common.py) so that every
# default (v1) output stays byte-identical: the key is dropped from the dump while None, and the JSON Schema omits
# it unless `formula_version_in_schema()` is active (community/account writers enable it only for v2 datasets).
_FORMULA_VERSION_IN_SCHEMA: ContextVar[bool] = ContextVar("formula_version_in_schema", default=False)


class _V2OnlyJsonSchema:
    def __get_pydantic_json_schema__(self, core_schema, handler):
        if not _FORMULA_VERSION_IN_SCHEMA.get():
            raise PydanticOmit
        return handler(core_schema)

    def __hash__(self) -> int:
        return hash(type(self))

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self)


@contextmanager
def formula_version_in_schema(enabled: bool = True) -> Iterator[None]:
    token = _FORMULA_VERSION_IN_SCHEMA.set(enabled)
    try:
        yield
    finally:
        _FORMULA_VERSION_IN_SCHEMA.reset(token)


class EstimatedCost(Strict):
    status: EstimateStatus = Field(description="exact: every price dimension matched; approximate: some assumed; "
                                               "unpriced: model/params not in pricing; skipped: estimation off")
    credits: Optional[float] = Field(None, description="estimated total credits for this generation")
    credits_before_discount: Optional[float] = None
    unit: Optional[str] = Field(None, description="price-point unit, e.g. credits_per_second")
    unit_credits: Optional[float] = Field(None, description="credits per unit after discount")
    quantity: Optional[float] = Field(None, description="units charged, e.g. 5 (seconds) or 4 (images)")
    quantity_basis: Optional[str] = Field(None, description="how quantity was derived, e.g. 'duration=5s', 'batch_size=4'")
    price_point_id: Optional[str] = None
    matched: dict[str, Scalar] = Field(default_factory=dict, description="price dimensions matched from params")
    assumed: dict[str, Scalar] = Field(default_factory=dict, description="dimensions not in params -> assumed value")
    usd: Optional[float] = None
    usd_per_credit: Optional[float] = None
    usd_reference: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    formula_version: Annotated[Optional[int], _V2OnlyJsonSchema()] = Field(
        None, description="2 = estimated with the JS-formula estimator (--estimate-version 2); absent on v1 estimates")

    @model_serializer(mode="wrap")
    def _drop_unset_formula_version(self, handler):
        data = handler(self)
        if isinstance(data, dict) and data.get("formula_version") is None:
            data.pop("formula_version", None)
        return data


def skipped(reason: str = "estimation disabled") -> dict:
    return EstimatedCost(status="skipped", notes=[reason]).model_dump(mode="json")


try:  # implementation provided by estimator.py
    from .estimator import CostEstimator  # noqa: F401
except ImportError:  # pragma: no cover - until implemented
    CostEstimator = None  # type: ignore[assignment]


def estimator_class(version: int = DEFAULT_ESTIMATE_VERSION):
    """1 -> CostEstimator (default, unchanged); 2 -> CostEstimatorV2 (JS formulas, docs/COST_FORMULAS.md §8)."""
    version = int(version)
    if version == 1:
        return CostEstimator
    if version == 2:
        from .v2 import CostEstimatorV2
        return CostEstimatorV2
    raise ValueError(f"estimate version must be one of {list(ESTIMATE_VERSIONS)}, got {version!r}")


__all__ = ["EstimatedCost", "EstimateStatus", "CostEstimator", "skipped", "estimator_class", "ESTIMATE_VERSIONS",
           "DEFAULT_ESTIMATE_VERSION", "formula_version_in_schema"]
