"""Pydantic v2 models — the single source of truth for every output shape.

`MODEL_BY_KIND` maps an item kind (what the spider yields) to the model that validates it.
"""
from __future__ import annotations

from pydantic import BaseModel

from .account import AccountRecord
from .auth import AuthPayload, CreditPackage
from .benefits import BenefitCard
from .common import SCHEMA_VERSION, Provenance, make_id
from .comparison import Comparison
from .dataset import Dataset
from .marketing import MarketingPlan
from .models import Model
from .plans import Plan, PlanSet

MODEL_BY_KIND: dict[str, type[BaseModel]] = {
    "plan_set": PlanSet,
    "plan": Plan,
    "model": Model,
    "benefit_card": BenefitCard,
    "comparison": Comparison,
    "marketing_plan": MarketingPlan,
    "credit_package": CreditPackage,
    "auth_payload": AuthPayload,
    "pricing_account": AccountRecord,          # opt-in `--sections account`
}

__all__ = [
    "SCHEMA_VERSION", "MODEL_BY_KIND", "Provenance", "make_id",
    "AccountRecord", "AuthPayload", "BenefitCard", "Comparison", "CreditPackage", "Dataset",
    "MarketingPlan", "Model", "Plan", "PlanSet",
]
