"""Login-only endpoints. Mapping mirrors the site's JS (`use-credits-query`): amounts AND credits are /100."""
from __future__ import annotations

from ..schemas.common import cents_to_money, make_id


def _offer(o):
    if not isinstance(o, dict):
        return None
    if o.get("type") == "bonus":
        return {"type": "bonus", "bonus_credits": (o.get("bonus_credits") or 0) / 100}
    if o.get("type") == "discount":
        return {"type": "discount", "amount_without_offer": cents_to_money(o.get("amount_without_offer")),
                "savings": cents_to_money(o.get("savings"))}
    return o


def parse_credit_packages(body: dict, provenance: dict) -> list[dict]:
    out = []
    known = {"amount", "original_amount", "display_amount", "credits", "tax_amount", "offer", "id"}
    for e in body.get("data") or []:
        out.append({
            "kind": "credit_package",
            "package_id": str(e.get("id") or make_id(e.get("credits"), e.get("amount"))),
            "credits": None if e.get("credits") is None else e["credits"] / 100,
            "amount": cents_to_money(e.get("amount")),
            "original_amount": cents_to_money(e.get("original_amount")),
            "display_amount": cents_to_money(e.get("display_amount")),
            "tax_amount": cents_to_money(e.get("tax_amount")),
            "offer": _offer(e.get("offer")),
            "expire_days": body.get("expire_days"),
            "source": provenance,
            **{k: v for k, v in e.items() if k not in known},
        })
    return out


def parse_auth_payload(endpoint: str, status: int, body, provenance: dict) -> list[dict]:
    return [{"kind": "auth_payload", "endpoint": endpoint, "status": status, "data": body, "source": provenance}]
