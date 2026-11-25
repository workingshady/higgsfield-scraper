"""pricing.higgsfield.ai/v2/pricing-config -> MarketingPlan entities (copy, features, unlimited lists)."""
from __future__ import annotations

import re
from typing import Iterable

from ..schemas.common import make_id

FEATURE_KEYS = ("id", "text", "status", "tooltip", "description", "icon", "badges")


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def _feature(f: dict) -> dict:
    return {
        "feature_id": str(f.get("id") or ""),
        "text": f.get("text") or "",
        "status": f.get("status"),
        "tooltip": f.get("tooltip"),
        "description": f.get("description"),
        "icon": f.get("icon"),
        "badges": f.get("badges") or [],
    }


def _group(group_id: str, g: dict) -> dict:
    return {"group_id": group_id, "title": g.get("title"), "features": [_feature(f) for f in g.get("features") or []]}


def select_versions(available: Iterable[str], wanted: list[str]) -> list[str]:
    ordered = sorted(available, key=version_key)
    if not ordered:
        return []
    if "all" in wanted:
        return ordered
    out = [ordered[-1]] if "latest" in wanted else []
    out += [v for v in wanted if v in ordered]
    return list(dict.fromkeys(out))


def parse_pricing_config(body: dict, provenance: dict, wanted: list[str]) -> list[dict]:
    versions = body.get("versions") or {}
    latest = max(versions, key=version_key) if versions else None
    out = []
    for v in select_versions(versions, wanted):
        for period, block in (versions[v] or {}).items():
            for plan_type, p in ((block or {}).get("plans") or {}).items():
                credits = p.get("credits") or {}
                groups = []
                if p.get("unlimitedAccess"):
                    groups.append(_group("unlimitedAccess", p["unlimitedAccess"]))
                for gid, g in (p.get("customSections") or {}).items():
                    if isinstance(g, dict):
                        groups.append(_group(gid, g))
                if p.get("everythingOnSection"):
                    groups.append(_group("everythingOnSection", p["everythingOnSection"]))
                out.append({
                    "kind": "marketing_plan",
                    "marketing_id": make_id(v, period, plan_type),
                    "config_version": v,
                    "is_latest": v == latest,
                    "billing_period": period,
                    "plan_type": plan_type,
                    "tagline": p.get("tagline"),
                    "credits_amount": credits.get("amount"),
                    "credits_label": credits.get("label"),
                    "credits_tooltip": credits.get("tooltip"),
                    "promo_items": credits.get("promoItems") or [],
                    "main_features": [_feature(f) for f in p.get("mainFeatures") or []],
                    "feature_groups": groups,
                    "special_deal": p.get("specialDeal"),
                    "billing_periods": p.get("billingPeriods"),
                    "ui": p.get("ui"),
                    "source": provenance,
                })
    return out
