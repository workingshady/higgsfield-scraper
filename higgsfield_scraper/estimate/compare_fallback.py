"""Fallback prices for models that have no /job-sets/costs entry, taken from the plan comparison table.

/subscriptions/v2/compare lists features like "Higgsfield Soul 2.0 · 0.12 credits/image" or
"Wan 2.5 720p · ~7 credits/5s". /subscriptions/v2/plan-benefits maps display labels to job_set_types
(e.g. "Nano Banana Pro" -> nano_banana_2). Joining the two prices generations of models that the costs table
lacks. Matching is conservative: a feature is used only when its name equals a known label for that
model (optionally followed by a resolution like 720p / 4K). Ambiguous names are never guessed.
Every fallback estimate is reported as "approximate" with the source feature in its notes.
"""
from __future__ import annotations

import re
from typing import Any, Optional

RES_RE = re.compile(r"^(\d{3,4}p|[1-8]k)$", re.I)
PER_RE = re.compile(r"^(\d+(?:\.\d+)?)s$")


def _norm(s: str) -> str:
    s = re.sub(r"^higgsfield\s+", "", (s or "").strip().lower())
    return re.sub(r"\s+", " ", s)


def labels_from_benefits(body: dict) -> dict[str, set[str]]:
    """model_id -> display labels, from plan-benefit rows that name exactly one job_set_type."""
    out: dict[str, set[str]] = {}
    for cards in (body or {}).get("cards", {}).values():
        for card in cards or []:
            for sec in card.get("sections") or []:
                for row in sec.get("rows") or []:
                    ids, label = row.get("job_set_types") or [], row.get("label")
                    if label and len(ids) == 1:
                        out.setdefault(ids[0], set()).add(_norm(label))
    return out


def rates_from_compare(body: dict) -> list[dict]:
    """[{name, resolution, credits, per_unit ('image'|'second'), per_seconds, approx, detail}]"""
    rows = []
    for cat in (body or {}).get("categories") or []:
        for f in cat.get("features") or []:
            m = re.match(r"^\s*(~)?\s*([\d.,]+)\s*credits?\s*/\s*(\S+)\s*$", f.get("detail") or "", re.I)
            if not m:
                continue
            name = _norm(f.get("name"))
            words = name.split(" ")
            res = words[-1] if words and RES_RE.match(words[-1]) else None
            base = " ".join(words[:-1]) if res else name
            per = m.group(3).lower()
            sec = PER_RE.match(per)
            rows.append({"name": base, "resolution": res.lower() if res else None,
                         "credits": float(m.group(2).replace(",", "")), "approx": bool(m.group(1)),
                         "per_unit": "second" if sec else "image" if per == "image" else per,
                         "per_seconds": float(sec.group(1)) if sec else None,
                         "detail": f"{f.get('name')} · {f.get('detail')}", "category": cat.get("slug")})
    return rows


# Explicit job_set_type -> comparison-table names, for unambiguous cases the benefit labels don't cover
# (benefits group "Soul V2 & Cinema" under two ids, so they can't be split automatically). Evidence: compare
# feature names (2026-11-25) "Higgsfield Soul 2.0", "Higgsfield Soul", "Wan 2.5 480p/720p/1080p".
EXTRA_LABELS: dict[str, set[str]] = {
    "text2image_soul_v2": {"soul 2.0"},
    "text2image_soul": {"soul"},
    "wan2_5_video": {"wan 2.5"},
}


def build_fallback(compare_body: dict, benefits_body: dict, priced: set[str]) -> dict[str, list[dict]]:
    """model_id -> candidate compare rates, only for models NOT in /job-sets/costs."""
    labels = labels_from_benefits(benefits_body)
    for mid, names in EXTRA_LABELS.items():
        labels.setdefault(mid, set()).update(names)
    rates = rates_from_compare(compare_body)
    table: dict[str, list[dict]] = {}
    for model_id, names in labels.items():
        if model_id in priced:
            continue
        hits = [r for r in rates if r["name"] in names]
        if hits:
            table[model_id] = hits
    return table


def pick(rates: list[dict], params: dict) -> Optional[dict]:
    res = str(params.get("resolution") or "").lower() or None
    if res:
        exact = [r for r in rates if r["resolution"] == res]
        if exact:
            return exact[0]
    no_res = [r for r in rates if r["resolution"] is None]
    return (no_res or rates or [None])[0]


def estimate_from_rate(rate: dict, params: dict, media_type: Optional[str]) -> dict[str, Any]:
    """-> partial EstimatedCost fields (credits, unit, quantity, quantity_basis, notes, assumed)."""
    notes = [f"no /job-sets/costs entry — priced from the plan comparison table: {rate['detail']}"]
    assumed: dict[str, Any] = {}
    if rate["per_unit"] == "image":
        n = params.get("batch_size") or params.get("num_images") or 1
        try:
            n = max(1, int(n))
        except (TypeError, ValueError):
            n = 1
        return {"credits": round(rate["credits"] * n, 4), "unit": "credits_per_generation",
                "unit_credits": rate["credits"], "quantity": n, "quantity_basis": f"batch_size={n}",
                "notes": notes, "assumed": assumed}
    if rate["per_unit"] == "second" and rate["per_seconds"]:
        per_s = rate["credits"] / rate["per_seconds"]
        dur = params.get("duration")
        try:
            dur = float(dur) if dur is not None else None
        except (TypeError, ValueError):
            dur = None
        if dur is None:
            dur = rate["per_seconds"]
            assumed["duration"] = dur
            notes.append(f"duration missing — assumed {dur:g}s (the comparison table's reference length)")
        return {"credits": round(per_s * dur, 4), "unit": "credits_per_second", "unit_credits": round(per_s, 6),
                "quantity": dur, "quantity_basis": f"duration={dur:g}s", "notes": notes, "assumed": assumed}
    return {"credits": None, "notes": notes + [f"unsupported comparison unit {rate['per_unit']!r}"], "assumed": assumed}


# ---------------------------------------------------------------------------------------------------------------
# Viral-hub presets (/viral-hub/presets/all): each preset carries a price matrix in credit units keyed by its
# params ("<id>.aspect_ratio=16:9,<id>.resolution=1080p"; "" = default). credit_units / 100 = credits — verified:
# "Eyes in" 7 s = 4900 units and "Floating fall" 12 s = 8400 units both give 7 credits/s, the Seedance 2.5 720p
# list price. Community viral_hub_video generations reference the preset via params.chain_preset_id / preset_id.
CREDIT_UNITS_PER_CREDIT = 100


def viral_table(presets_body: Any) -> dict[str, dict]:
    if isinstance(presets_body, list):
        items = presets_body
    else:
        b = presets_body or {}
        items = b.get("presets") or b.get("items") or b.get("data") or []
    out = {}
    for p in items:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        rows = []
        for m in p.get("price_matrix") or []:
            conds = {}
            for part in str(m.get("key") or "").split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    conds[k.split(".")[-1]] = v
            if m.get("credit_units") is not None:
                rows.append({"conds": conds, "units": float(m["credit_units"])})
        if rows:
            out[str(p["id"])] = {"name": p.get("name"), "rows": rows, "duration": p.get("duration")}
    return out


def _n(v: Any) -> str:
    return str(v).strip().lower()


def estimate_viral(preset: dict, params: dict) -> dict[str, Any]:
    best, best_n, default = None, -1, None
    for r in preset["rows"]:
        if not r["conds"]:
            default = r
            continue
        if all(_n(params.get(k)) == _n(v) for k, v in r["conds"].items()) and len(r["conds"]) > best_n:
            best, best_n = r, len(r["conds"])
    row = best or default
    if row is None:
        return {"credits": None, "notes": [f"viral preset {preset['name']!r}: no matching price row"]}
    credits = round(row["units"] / CREDIT_UNITS_PER_CREDIT, 4)
    notes = [f"viral preset {preset['name']!r} price matrix ({row['units']:g} credit units / 100)"]
    if not best:
        notes.append("params did not match a matrix row — preset default price used")
    return {"credits": credits, "status": "exact" if best else "approximate",
            "matched": dict(row["conds"]) if best else {},
            "assumed": {} if best else {"price_row": "preset default"}, "notes": notes}
