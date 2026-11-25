"""/subscriptions/v2/plan-benefits -> BenefitCard entities (one per billing_period x tab x plan_type)."""
from __future__ import annotations

from typing import Any

from ..schemas.common import make_id

CAP_KEYS = ("max_resolution", "resolutions", "max_duration_s", "qualities", "output_formats", "options", "concurrency")


def _caps(c: Any) -> Any:
    if not isinstance(c, dict):
        return None
    out = {k: c.get(k) for k in CAP_KEYS}
    if isinstance(out["concurrency"], dict):
        out["concurrency"] = {k: out["concurrency"].get(k) for k in ("count", "per", "pool")}
    return out


def _entitlement(e: dict) -> dict:
    e = e or {}
    return {
        "type": e.get("type") or "none",
        "of": e.get("of"),
        "reason": e.get("reason"),
        "count": e.get("count"),
        "duration_days": e.get("duration_days"),
        "starts": e.get("starts"),
        "available_until": e.get("available_until"),
        "requirements": e.get("requirements") or [],
        "caps": _caps(e.get("caps")),
    }


def _row(r: dict) -> dict:
    return {
        "row_id": r.get("id") or "",
        "label": r.get("label"),
        "description": r.get("description"),
        "model_ids": r.get("job_set_types") or [],
        "entitlement": _entitlement(r.get("entitlement")),
        "placement": r.get("placement"),
        "emphasis": r.get("emphasis"),
        "tags": r.get("tags") or [],
        "tooltip": r.get("tooltip"),
    }


def _section(s: dict) -> dict:
    info = s.get("info")
    return {
        "section_id": s.get("id") or "",
        "kind": s.get("kind") or "",
        "slot": s.get("slot"),
        "title": s.get("title"),
        "subtitle": s.get("subtitle"),
        "theme": s.get("theme"),
        "info": info.get("text") if isinstance(info, dict) else info,
        "data": s.get("data"),
        "rows": [_row(r) for r in s.get("rows") or []],
    }


def parse_plan_benefits(body: dict, provenance: dict) -> list[dict]:
    badges = body.get("tab_badges") or {}
    out = []
    for period, cards in (body.get("cards") or {}).items():
        for c in cards or []:
            sections = [_section(s) for s in c.get("sections") or []]
            rows = [r for s in sections for r in s["rows"]]
            unlimited = list(dict.fromkeys(m for r in rows if r["entitlement"]["type"] == "unlimited"
                                           for m in r["model_ids"]))
            free_gens = [
                {"model_id": m, "label": r["label"], "count": r["entitlement"]["count"],
                 "max_resolution": (r["entitlement"]["caps"] or {}).get("max_resolution")}
                for r in rows if r["entitlement"]["type"] == "free_gens" for m in r["model_ids"]
            ]
            # hero sections carry a grant (e.g. "7-day unlimited Seedance 2.0") instead of rows
            for s in sections:
                grant = (s.get("data") or {}).get("grant") if s["kind"] == "hero" else None
                if grant and grant.get("type") == "unlimited" and (s.get("data") or {}).get("model_label"):
                    unlimited.append(f"label:{s['data']['model_label']}")
            out.append({
                "kind": "benefit_card",
                "card_id": make_id(period, c.get("tab"), c.get("plan_type")),
                "plan_type": c.get("plan_type") or "unknown",
                "billing_period": period,
                "tab": c.get("tab"),
                "campaign": c.get("campaign"),
                "experiment": c.get("experiment"),
                "availability": c.get("availability"),
                "sections": sections,
                "unlimited_model_ids": list(dict.fromkeys(unlimited)),
                "free_gens": free_gens,
                "tab_badge": badges.get(c.get("tab")),
                "source": provenance,
            })
    return out
