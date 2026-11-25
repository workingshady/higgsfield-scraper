"""What to scrape and what to keep — built from CLI args / spider args."""
from __future__ import annotations

import fnmatch
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from .constants import (
    DEFAULT_SECTIONS, PLAN_SET_KEYS, PLAN_SET_PRESETS, SECTIONS, US_PLAN_SET,
)


def split_csv(value: Optional[str | Iterable[str]]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    return [v.strip() for v in value if v and v.strip()]


def normalize_version(v: str) -> str:
    """'51' / 'v51' / 'v51.0' -> 'v51.0.0'; 'latest' and 'all' pass through."""
    if v in ("latest", "all"):
        return v
    parts = v.lstrip("vV").split(".")
    parts += ["0"] * (3 - len(parts))
    return "v" + ".".join(parts[:3])


@dataclass
class Selection:
    sections: list[str] = field(default_factory=lambda: list(DEFAULT_SECTIONS))
    plan_set_keys: list[str] = field(default_factory=lambda: [US_PLAN_SET])
    billing_periods: list[str] = field(default_factory=lambda: ["monthly", "annual"])
    plan_types: list[str] = field(default_factory=list)          # empty = all
    models: list[str] = field(default_factory=list)              # patterns on model_id/family/name
    categories: list[str] = field(default_factory=list)          # video|image|audio|other
    marketing_versions: list[str] = field(default_factory=lambda: ["latest"])
    locale: str = "en"
    include_hidden_plans: bool = False
    include_raw_cost: bool = False
    usd_reference: str = "plus:annual"                          # plan_type:billing_period
    has_token: bool = False

    # ---------------------------------------------------------------- build
    @classmethod
    def build(cls, *, sections=None, plan_sets=None, billing=None, plan_types=None, models=None,
              categories=None, marketing_versions=None, locale="en", include_hidden_plans=False,
              include_raw_cost=False, usd_reference="plus:annual", has_token=False) -> "Selection":
        secs = split_csv(sections) or list(DEFAULT_SECTIONS)
        if "all" in secs:
            secs = list(DEFAULT_SECTIONS) + (["auth"] if has_token else [])
        unknown = set(secs) - set(SECTIONS)
        if unknown:
            raise ValueError(f"unknown section(s): {sorted(unknown)}; choose from {sorted(SECTIONS)}")
        keys: list[str] = []
        for k in split_csv(plan_sets) or [US_PLAN_SET]:
            keys.extend(PLAN_SET_PRESETS.get(k, [k]))
        bad = [k for k in keys if k not in PLAN_SET_KEYS]
        if bad:
            raise ValueError(f"unknown plan_set_key(s): {bad}; run `python -m higgs_price plan-sets`")
        mv = [normalize_version(v) for v in split_csv(marketing_versions) or ["latest"]]
        return cls(
            sections=list(dict.fromkeys(secs)),
            plan_set_keys=list(dict.fromkeys(keys)),
            billing_periods=split_csv(billing) or ["monthly", "annual"],
            plan_types=[p.lower() for p in split_csv(plan_types)],
            models=[m.lower() for m in split_csv(models)],
            categories=[c.lower() for c in split_csv(categories)],
            marketing_versions=mv,
            locale=locale,
            include_hidden_plans=include_hidden_plans,
            include_raw_cost=include_raw_cost,
            usd_reference=usd_reference,
            has_token=has_token,
        )

    # ------------------------------------------------------------- endpoints
    def endpoints(self) -> list[str]:
        """Endpoints to hit. `models` also pulls plans + benefits to enrich names, entitlements and USD estimates."""
        eps: list[str] = []
        for s in self.sections:
            eps.extend(SECTIONS[s])
        if "models" in self.sections:
            eps.extend(["plan_benefits", "plans"])
        if "plans" in self.sections:
            eps.extend(["plan_benefits", "compare"])  # benefits -> plan.unlimited models, compare -> seats
        return list(dict.fromkeys(eps))

    # ---------------------------------------------------------------- filters
    def keep_plan_type(self, plan_type: Optional[str]) -> bool:
        return not self.plan_types or (plan_type or "").lower() in self.plan_types

    def keep_model(self, model_id: str, family: str, name: str, category: str) -> bool:
        if self.categories and category not in self.categories:
            return False
        if not self.models:
            return True
        hay = [model_id.lower(), family.lower(), name.lower()]
        for pat in self.models:
            if any(ch in pat for ch in "*?["):
                if any(fnmatch.fnmatch(h, pat) for h in hay):
                    return True
            elif any(pat in h for h in hay):
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
