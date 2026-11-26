"""The assembled, nested output document (output/dataset.json)."""
from __future__ import annotations

from typing import Annotated, Any, Optional

from pydantic import AwareDatetime, Field

from .account import AccountSection
from .auth import AuthPayload, CreditPackage
from .benefits import BenefitCard
from .common import SCHEMA_VERSION, VISIBILITY_DESCRIPTION, LoginOnly, LoginOptional, Money, Strict, Visibility
from .comparison import Comparison
from .marketing import MarketingPlan
from .models import Model
from .plans import Plan, PlanSet


class PlanSetWithPlans(PlanSet):
    plans: list[Plan] = Field(default_factory=list)


class CreditValue(LoginOptional):
    __login_only__ = ("visibility",)

    plan_id: str
    plan_set_key: str
    plan_type: str
    billing_period: str
    credits_per_month: int
    usd_per_credit_before_offer: Optional[Money] = None
    usd_per_credit_after_offer: Optional[Money] = None
    credits_per_usd_after_offer: Optional[float] = None
    visibility: Annotated[Optional[Visibility], LoginOnly] = Field(None, description=VISIBILITY_DESCRIPTION)


class AuthSection(Strict):
    credit_packages: list[CreditPackage] = Field(default_factory=list)
    payloads: list[AuthPayload] = Field(default_factory=list)


class LoggedInPricesMeta(Strict):
    """meta.logged_in_prices — only present when the run used --logged-in-prices and got logged-in responses."""

    costs_version_anonymous: Optional[str] = Field(None, description="/job-sets/costs `version` without a session")
    costs_version_logged_in: Optional[str] = Field(None, description="/job-sets/costs `version` with a session")
    logged_in_only_plan_ids: list[str] = Field(default_factory=list, description="plans tagged visibility=logged_in")
    logged_in_only_model_ids: list[str] = Field(default_factory=list, description="models tagged visibility=logged_in")
    differing_rows: list[str] = Field(
        default_factory=list, description="rows present in both responses but with different content (the anonymous "
                                          "row is kept unchanged), e.g. 'plan:<plan_id>' or 'model:<model_id>'")


class DatasetMeta(LoginOptional):
    __login_only__ = ("logged_in_prices",)

    run_id: Optional[str] = None
    label: Optional[str] = None
    scraped_at: AwareDatetime
    source_page: str
    country_code: Optional[str] = None
    currency: Optional[str] = None
    locale: str
    sections: list[str]
    plan_set_keys: list[str]
    costs_version: Optional[str] = None
    marketing_versions: list[str] = Field(default_factory=list)
    marketing_latest_version: Optional[str] = None
    usd_reference: Optional[dict[str, Any]] = None
    filters: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    endpoints: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    logged_in_prices: Annotated[Optional[LoggedInPricesMeta], LoginOnly] = None


class Dataset(LoginOptional):
    __login_only__ = ("account",)

    schema_version: int = SCHEMA_VERSION
    meta: DatasetMeta
    plan_sets: list[PlanSetWithPlans] = Field(default_factory=list)
    credit_values: list[CreditValue] = Field(default_factory=list)
    models: list[Model] = Field(default_factory=list)
    benefit_cards: list[BenefitCard] = Field(default_factory=list)
    tab_badges: Optional[dict[str, Any]] = None
    comparisons: list[Comparison] = Field(default_factory=list)
    marketing: list[MarketingPlan] = Field(default_factory=list)
    auth: AuthSection = Field(default_factory=AuthSection)
    account: Annotated[Optional[AccountSection], LoginOnly] = Field(
        None, description="opt-in --sections account: the logged-in account's own balances/plan (whitelisted)")
