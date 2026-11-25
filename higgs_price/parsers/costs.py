"""/job-sets/costs -> Model entities with typed price points.

The `cost` field is heterogeneous (55 distinct shapes across 86 models on 2026-11-25). The walker turns every
shape into flat PricePoints:

  * scalar strings/bools/ints (resolution, quality, mode, model, creativity, input_fps, ...) -> `dimensions`
  * cost keys (credits, cost_per_second, image_credits, ...) -> one point each, `original_<key>` -> original_credits
  * {"audio": {"on": 2.5, "off": 1.75}}              -> dimension audio=on/off, unit credits_per_second
  * {"video": {"with_video": {...}, "without_video"}} -> dimension video_input=with_video/without_video
  * {"video_edit": {...cost keys}}                   -> component="video_edit"
  * lists of dicts (e.g. seedance_2_0 "resolutions") -> recurse with the parent's dimensions
  * {"formula": ...} entries (audio/TTS)              -> effective rate + Formula params
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..schemas.common import make_id

log = logging.getLogger(__name__)

COST_KEYS: dict[str, str] = {
    "credits": "credits_per_generation",
    "cost_per_second": "credits_per_second",
    "credits_per_second": "credits_per_second",
    "credits_per_minute": "credits_per_minute",
    "image_credits": "credits_per_image",
    "frame_credits": "credits_per_frame",
    "base_credits": "base_credits",
}
ATTRIBUTE_KEYS = {"is_estimate", "reference_fps", "max_frames", "image_count"}
NESTED_DIMENSION_NAMES = {"video": "video_input"}
FORMULA_META_KEYS = {"formula", "batch_size", "unlimited", "fps_multipliers"}
FORMULA_DIMENSION_KEYS = {"model", "model_id", "animation_mode"}
AUDIO_HINTS = ("elevenlabs", "speech", "tts", "audio", "voice", "dubbing", "music")
EXAMPLE_SIZE = {"credits_per_second": ("seconds", 5), "credits_per_minute": ("minutes", 1)}


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pct(original: Optional[float], cost: Optional[float]) -> float:
    if not original or cost is None:
        return 0.0
    return round((1 - cost / original) * 100, 2)


class _Walker:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.points: list[dict] = []

    # ------------------------------------------------------------------ emit
    def emit(self, dims: dict, component: Optional[str], unit: str, credits: Optional[float],
             original: Optional[float] = None, attrs: Optional[dict] = None, formula: Optional[dict] = None,
             example: Optional[dict] = None) -> None:
        original = credits if original is None else original
        if example is None and credits is not None and unit in EXAMPLE_SIZE:
            name, size = EXAMPLE_SIZE[unit]
            example = {name: size, "credits": round(credits * size, 4)}
        key = (self.model_id, component, tuple(sorted((k, str(v)) for k, v in dims.items())), unit)
        self.points.append({
            "point_id": make_id(*map(str, key)),
            "dimensions": dict(dims),
            "component": component,
            "unit": unit,
            "credits": credits,
            "original_credits": original,
            "discount_percent": _pct(original, credits),
            "is_discounted": credits is not None and original is not None and credits < original,
            "example": example,
            "attributes": dict(attrs or {}),
            "formula": formula,
        })

    # ------------------------------------------------------------------ walk
    def walk(self, node: Any, dims: dict, component: Optional[str]) -> None:
        if isinstance(node, list):
            for child in node:
                self.walk(child, dims, component)
            return
        if not isinstance(node, dict):
            return
        if "formula" in node:
            self.formula(node, dims, component)
            return

        local, attrs = dict(dims), {}
        for k, v in node.items():
            if k in COST_KEYS or k.startswith("original_") or isinstance(v, (dict, list)) or v is None:
                continue
            if k == "model" and component and v == component.rsplit(".", 1)[-1]:
                continue  # {"video_edit": {"model": "video_edit", ...}} — already the component
            (attrs if k in ATTRIBUTE_KEYS else local)[k] = v

        for k, unit in COST_KEYS.items():
            if _num(node.get(k)):
                orig = node.get(f"original_{k}")
                self.emit(local, component, unit, float(node[k]), float(orig) if _num(orig) else None, attrs)

        for k, v in node.items():
            if isinstance(v, dict) and v:
                values = list(v.values())
                if all(_num(x) for x in values):                      # {"audio": {"on": 2.5, "off": 1.75}}
                    for sub, val in v.items():
                        self.emit({**local, k: sub}, component, "credits_per_second", float(val), None, attrs)
                elif all(isinstance(x, dict) for x in values) and not any(c in v for c in COST_KEYS):
                    dim = NESTED_DIMENSION_NAMES.get(k, k)            # {"video": {"with_video": {...}}}
                    for sub, child in v.items():
                        self.walk(child, {**local, dim: sub}, component)
                else:                                                 # {"video_edit": {...cost keys}}
                    self.walk(v, local, f"{component}.{k}" if component else k)
            elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                self.walk(v, local, component)                        # e.g. seedance_2_0 "resolutions"

    # --------------------------------------------------------------- formula
    def formula(self, node: dict, dims: dict, component: Optional[str]) -> None:
        local = dict(dims)
        params = {}
        for k, v in node.items():
            if k in FORMULA_META_KEYS:
                continue
            if k in FORMULA_DIMENSION_KEYS and isinstance(v, str):
                local[k] = v
            else:
                params[k] = v
        f = {"name": node["formula"], "params": params, "batch_size": node.get("batch_size"),
             "unlimited": node.get("unlimited")}
        cpc = node.get("cost_units_per_credit") or 100
        name = node["formula"]

        if node.get("fps_multipliers"):                               # input_duration_by_fps
            for m in node["fps_multipliers"]:
                self.emit({**local, "fps": m.get("fps")}, component, "credits_per_second",
                          m.get("credits_per_second"), None, {}, f)
            return

        unit, credits, example = "formula", None, None
        if node.get("characters_per_block") and node.get("cost_units_per_block") is not None:
            n = node["characters_per_block"]
            unit, credits = f"credits_per_{n}_characters", round(node["cost_units_per_block"] / cpc, 6)
            example = {"characters": 1000, "credits": round(credits * 1000 / n, 4)}
        elif node.get("seconds_per_block") and node.get("cost_units_per_block") is not None:
            n = node["seconds_per_block"]
            unit, credits = f"credits_per_{n}_seconds", round(node["cost_units_per_block"] / cpc, 6)
            example = {"seconds": 60, "credits": round(credits * 60 / n, 4)}
        elif _num(node.get("credits_per_minute")):
            unit, credits = "credits_per_minute", float(node["credits_per_minute"])
        elif _num(node.get("credits_per_second")):
            unit, credits = "credits_per_second", float(node["credits_per_second"])
        elif _num(node.get("cost_units_per_second")):                 # estimated_duration (speech length)
            unit, credits = "credits_per_second", round(node["cost_units_per_second"] / cpc, 6)
        elif _num(node.get("cost_units_numerator")) and node.get("cost_units_denominator"):
            # linear_units: cost units = chars * numerator / denominator (unit assumed: per character)
            unit = "credits_per_character"
            credits = round(node["cost_units_numerator"] / node["cost_units_denominator"] / cpc, 8)
            example = {"characters": 1000, "credits": round(credits * 1000, 4)}
        else:
            log.warning("unrecognised cost formula %r for %s", name, self.model_id)
        attrs = {"unit_assumed": True} if unit == "credits_per_character" else {}
        self.emit(local, component, unit, credits, None, attrs, f, example)


# ------------------------------------------------------------------ naming
ACRONYMS = {"gpt": "GPT", "ai": "AI", "hf": "HF", "fps": "FPS", "sam": "SAM", "3d": "3D", "flf": "FLF",
            "tts": "TTS", "v15": "v1.5", "o3": "O3", "h3": "H3", "gif": "GIF"}


def humanize(model_id: str) -> str:
    """Fallback display name: 'kling3_0' -> 'Kling 3.0', 'gpt_image_2_6' -> 'GPT Image 2.6'."""
    s = re.sub(r"^p_image_", "", model_id)
    s = re.sub(r"(\d)_(?=\d)", r"\1.", s)                     # 2_6 -> 2.6
    words = []
    for tok in s.split("_"):
        m = re.match(r"^([a-z]{3,})(\d[\d.]*)$", tok)          # kling3.0 -> kling 3.0
        for w in (m.groups() if m else (tok,)):
            words.append(ACRONYMS.get(w.lower(), w[:1].upper() + w[1:]))
    return " ".join(words)


def family_of(model_id: str) -> str:
    """'seedance_2_5_flash' -> 'seedance', 'kling3_0' -> 'kling', 'gpt_image_2_6' -> 'gpt_image'."""
    toks = re.sub(r"^p_image_", "", model_id).split("_")
    kept: list[str] = []
    for t in toks:
        if kept and re.fullmatch(r"v?\d+", t):
            break
        kept.append(t)
    if len(kept) < len(toks) or len(kept) == 1:
        kept[-1] = re.sub(r"(?<=[a-z])\d+$", "", kept[-1])     # kling3 -> kling
    return "_".join(kept) or model_id


IMAGE_HINTS = ("image", "soul", "flux", "banana", "seedream", "hazel", "ideogram", "recraft", "gpt_image")


def category_of(model_id: str, units: set[str]) -> str:
    n = model_id.lower()
    if any(h in n for h in AUDIO_HINTS):
        return "audio"
    if "video" in n or any("second" in u or "minute" in u for u in units):
        return "video"
    if units and units <= {"credits_per_generation", "credits_per_image"}:
        return "image"
    if not units and any(h in n for h in IMAGE_HINTS):
        return "image"
    return "other"


def options_of(points: list[dict]) -> dict[str, list]:
    opts: dict[str, list] = {}
    for p in points:
        for k, v in p["dimensions"].items():
            vals = opts.setdefault(k, [])
            if v not in vals:
                vals.append(v)
    return opts


# ------------------------------------------------------------------ parse
def parse_job_costs(body: dict, provenance: dict, include_raw: bool = False) -> list[dict]:
    out = []
    for entry in body.get("data") or []:
        model_id = entry.get("job_set_type")
        if not model_id:
            continue
        w = _Walker(model_id)
        w.walk(entry.get("cost"), {}, None)
        if not w.points:
            log.warning("no price points extracted for %s (shape: %s)", model_id, str(entry.get("cost"))[:200])
        units = {p["unit"] for p in w.points}
        credits = [p["credits"] for p in w.points if p["credits"] is not None]
        out.append({
            "kind": "model",
            "model_id": model_id,
            "display_name": humanize(model_id),
            "family": family_of(model_id),
            "category": category_of(model_id, units),
            "units": sorted(units),
            "options": options_of(w.points),
            "components": sorted({p["component"] for p in w.points if p["component"]}),
            "price_point_count": len(w.points),
            "has_discount": any(p["is_discounted"] for p in w.points),
            "min_credits": min(credits) if credits else None,
            "max_credits": max(credits) if credits else None,
            "price_points": w.points,
            "costs_version": body.get("version"),
            "raw_cost": entry.get("cost") if include_raw else None,
            "source": provenance,
        })
    return out
