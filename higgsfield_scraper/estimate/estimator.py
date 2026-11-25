"""CostEstimator: generation params -> estimated credits, from /job-sets/costs price points.

Method (see docs/scrapers/cost-estimate.md for the tables with evidence from real community generations):

1. The pricing body is normalized by ``parsers.costs.parse_job_costs`` (single source of truth for the 55 cost
   shapes) into ``model_id -> price points``.
2. ``job_set_type`` is looked up directly, then through ``ALIASES``, then by a separator-insensitive key
   (``kling4_0_flash`` ~ ``kling_4_0_flash``; such a fuzzy hit always makes the result "approximate").
3. Generation ``params`` are turned into *wanted* dimension values with ``PARAM_DIMENSIONS`` (param keys per
   dimension, first non-empty wins) and ``_derive_*`` helpers (input video presence, references). Only dimensions
   that the model's price points actually use are considered; anything else in params is ignored.
4. Main-rate points (every unit except the add-on units in ``ADDON_UNITS``) of the selected component are
   filtered: a point survives when each of its dimensions present in *wanted* is equal after ``_norm``. Among the
   survivors we take the most matched dimensions, then the fewest unresolved ones, then the lowest cost
   (``DEFAULT_POLICY`` = lowest-cost: the estimate is a lower bound for unknown options). Unresolved dimensions
   are reported in ``assumed``.
5. Quantity comes from the unit (``_quantity``): per generation x batch, per second x duration, per minute,
   per-N-seconds blocks, per-N-characters blocks over the prompt/text, per character. Add-on points with the
   same dimensions are added: ``base_credits`` once, ``credits_per_image`` x input-image count,
   ``credits_per_frame`` x input-frame count.

status: "exact" when every dimension of the chosen point came from params and every quantity input was present;
"approximate" when anything was assumed/defaulted; "unpriced" when the model has no cost entry or no usable unit.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable, Optional

from ..parsers.costs import parse_job_costs
from . import EstimatedCost

# --------------------------------------------------------------------------------------------- mapping tables
#: price-point dimension -> generation param keys that carry it (checked in order; first non-empty wins).
#: Evidence (community params, 2026-11-25): resolution on seedance_2_5/2_0, cinematic_studio_3_0, gpt_image_2_x,
#: nano_banana_2_1, seedream_v5_pro; quality on gpt_image_2_x; mode on kling3_0 ("pro"); model on seedance_2_0
#: ("seedance_2_0") and gpt_image_2_5 ("flare"/"sunburst"); sound on kling3_0 ("on"); generate_audio on
#: seedance_2_0 / seedance_2_5 / cinematic_studio_3_0 (bool).
PARAM_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "resolution": ("resolution", "output_resolution", "target_resolution"),
    "source_resolution": ("source_resolution", "input_resolution"),
    "quality": ("quality",),
    "mode": ("mode",),
    "model": ("model", "model_name"),
    "model_type": ("model_type", "style_type"),
    "model_id": ("model_id",),
    "operation": ("operation",),
    "thinking": ("thinking", "thinking_level"),
    "creativity": ("creativity",),
    "input_fps": ("input_fps",),
    "output_fps": ("output_fps", "fps"),
    "fps": ("fps", "input_fps"),
    "animation_mode": ("animation_mode",),
    "audio": ("sound", "generate_audio", "audio", "with_audio", "enable_audio"),
    "has_references": ("has_references",),
}
#: dimensions whose value is a boolean flag rendered as on/off in pricing ({"audio": {"on":…, "off":…}}).
ON_OFF_DIMENSIONS = {"audio"}
#: param keys holding an input video (non-empty => video_input=with_video).
VIDEO_PARAM_KEYS = ("input_video", "video", "source_video", "reference_video", "input_videos", "videos",
                    "video_url", "reference_videos")
#: param keys holding input media lists / references.
MEDIA_LIST_KEYS = ("medias", "input_images", "image_urls", "reference_images")
IMAGE_PARAM_KEYS = ("input_image", "image", "start_image", "end_image")
REFERENCE_KEYS = ("medias", "input_images", "reference_elements", "reference_images", "image_reference",
                  "custom_reference", "kling_elements")
#: quantity inputs
BATCH_KEYS = ("batch_size", "num_images", "n", "num_outputs", "count")
DURATION_KEYS = ("duration", "duration_seconds", "video_duration", "length_seconds", "seconds")
TEXT_KEYS = ("text", "input_text", "script", "prompt")
#: video/edit component switches -> component name
COMPONENT_FLAGS = {"video_edit": ("video_edit", "is_video_edit", "is_edit")}
HDR_KEYS = ("hdr", "video_hdr", "is_hdr", "enable_hdr")

#: job_set_type -> pricing model_id when they differ. Empty on 2026-11-25: every priced job_set_type seen in
#: ~1,000 community generations used the same id as /job-sets/costs. Unknown ids (nano_banana_2,
#: text2image_soul_v2, soul_cinematic, image_auto, viral_hub_video, wan2_5_video, seedream_v4_5 …) have NO cost
#: entry and are deliberately NOT aliased to a sibling (e.g. nano_banana_2 != nano_banana_2_1 — different price).
ALIASES: dict[str, str] = {}

ADDON_UNITS = {"base_credits", "credits_per_image", "credits_per_frame"}
DEFAULT_DURATION_S = 5.0          # same reference length the site uses ("credits per 5 s")
DEFAULT_MINUTES = 1.0
DEFAULT_POLICY = "lowest-cost"
BLOCK_RE = re.compile(r"^credits_per_(\d+)_(seconds|characters)$")


# --------------------------------------------------------------------------------------------- helpers
def _norm(v: Any) -> str:
    """Comparable form: case/space-insensitive, '-' == '_', '1080' -> '1080p', True -> 'true'."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip().lower().replace("-", "_").replace(" ", "")
    if re.fullmatch(r"(240|360|480|540|576|720|768|1080|1440|2160)", s):
        s += "p"
    return s


def _on_off(v: Any) -> Optional[str]:
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, (int, float)):
        return "on" if v else "off"
    s = str(v).strip().lower()
    if s in ("on", "true", "yes", "1", "enabled"):
        return "on"
    if s in ("off", "false", "no", "0", "disabled", "none"):
        return "off"
    return None


def _present(v: Any) -> bool:
    return v not in (None, "", [], {}) and v is not False


def _media_type(m: Any) -> str:
    if not isinstance(m, dict):
        return str(m).lower()
    data = m.get("data") if isinstance(m.get("data"), dict) else {}
    return f"{m.get('role', '')} {m.get('type', '')} {data.get('type', '')} {data.get('url', '')}".lower()


def _is_video_media(m: Any) -> bool:
    t = _media_type(m)
    return "video" in t or bool(re.search(r"\.(mp4|mov|webm|m4v)\b", t))


def _first(params: dict, keys: Iterable[str]) -> tuple[Optional[str], Any]:
    for k in keys:
        if k in params and params[k] not in (None, ""):
            return k, params[k]
    return None, None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        m = re.match(r"^\s*(\d+(?:\.\d+)?)", str(v))
        return float(m.group(1)) if m else None


def _loose_key(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]", "", model_id.lower())


# --------------------------------------------------------------------------------------------- estimator
class CostEstimator:
    def __init__(self, models: dict[str, dict], usd_per_credit: Optional[float] = None,
                 usd_reference: Optional[str] = None, aliases: Optional[dict[str, str]] = None):
        self.models = models
        self.usd_per_credit = usd_per_credit
        self.usd_reference = usd_reference
        self.aliases = {**ALIASES, **(aliases or {})}
        self._loose = {_loose_key(k): k for k in models}
        self.fallback: dict[str, list[dict]] = {}        # model_id -> comparison-table rates (compare_fallback.py)
        self.viral: dict[str, dict] = {}                  # viral preset id -> price matrix (compare_fallback.py)

    def with_viral_presets(self, presets_body) -> "CostEstimator":
        """Price viral_hub_* generations from /viral-hub/presets/all price matrices (preset id in params)."""
        from .compare_fallback import viral_table
        self.viral = viral_table(presets_body)
        return self

    def with_compare_fallback(self, compare_body: dict, benefits_body: dict) -> "CostEstimator":
        """Price models missing from /job-sets/costs from the plan comparison table (always 'approximate')."""
        from .compare_fallback import build_fallback
        self.fallback = build_fallback(compare_body or {}, benefits_body or {}, set(self.models))
        return self

    @classmethod
    def from_job_costs_body(cls, body: dict, usd_per_credit: Optional[float] = None,
                            usd_reference: Optional[str] = None) -> "CostEstimator":
        prov = {"endpoint": "job_costs", "url": "", "params": {}, "fetched_at": None}
        models = {m["model_id"]: m for m in parse_job_costs(body or {}, prov)}
        return cls(models, usd_per_credit=usd_per_credit, usd_reference=usd_reference)

    # ------------------------------------------------------------------ public
    def estimate(self, job_set_type: str, params: Optional[dict], media_type: Optional[str] = None) -> dict:
        params = params if isinstance(params, dict) else {}
        notes: list[str] = []
        model_id, fuzzy = self._resolve(job_set_type)
        pid = str(params.get("chain_preset_id") or params.get("preset_id") or "")
        if model_id is None and pid and pid in self.viral:
            from .compare_fallback import estimate_viral
            r = estimate_viral(self.viral[pid], params)
            if r.get("credits") is not None:
                return self._out(status=r["status"], credits=r["credits"], credits_before_discount=r["credits"],
                                 unit="credits_per_generation", unit_credits=r["credits"], quantity=1,
                                 quantity_basis="1 viral preset run", price_point_id=f"viral:{pid}",
                                 matched=r["matched"], assumed=r["assumed"], notes=notes + r["notes"])
        if model_id is None and job_set_type in self.fallback:
            from .compare_fallback import estimate_from_rate, pick
            rate = pick(self.fallback[job_set_type], params)
            r = estimate_from_rate(rate, params, media_type) if rate else {"credits": None, "notes": []}
            if r.get("credits") is not None:
                return self._out(status="approximate", credits=r["credits"], credits_before_discount=r["credits"],
                                 unit=r["unit"], unit_credits=r["unit_credits"], quantity=r["quantity"],
                                 quantity_basis=r["quantity_basis"], price_point_id=f"compare:{rate['detail']}",
                                 matched={"resolution": rate["resolution"]} if rate["resolution"] else {},
                                 assumed=r["assumed"], notes=notes + r["notes"])
        if model_id is None:
            return self._out(status="unpriced",
                             notes=[f"no /job-sets/costs entry for job_set_type {job_set_type!r}"])
        if model_id != job_set_type:
            notes.append(f"priced as {model_id!r} ({'separator-insensitive match' if fuzzy else 'alias'})")
        model = self.models[model_id]
        self._sanity(model, media_type, notes)

        component = self._component(params, model)
        points = [p for p in model["price_points"] if p["component"] == component]
        mains = [p for p in points if p["unit"] not in ADDON_UNITS]
        if not mains:  # e.g. a model priced only with base_credits
            mains = [p for p in points if p["unit"] == "base_credits"]
        if not mains:
            return self._out(status="unpriced", notes=notes + [f"{model_id}: no usable price point"])

        dims_used = {k for p in mains for k in p["dimensions"]}
        wanted, sources, bad = self._wanted(params, dims_used, model)
        for d, v in bad.items():
            notes.append(f"param {d}={v!r} not in pricing options {model['options'].get(d)}; assumed instead")

        point, assumed, tie = self._choose(mains, wanted)
        if point is None or point["credits"] is None or point["unit"] == "formula":
            return self._out(status="unpriced",
                             notes=notes + [f"{model_id}: unit {point['unit'] if point else None!r} not computable"])
        if tie:
            notes.append(f"{tie} price points fit equally; chose lowest-cost ({DEFAULT_POLICY})")
        if assumed:
            notes.append(f"unresolved dimensions assumed ({DEFAULT_POLICY}): "
                         + ", ".join(f"{k}={v}" for k, v in assumed.items()))
        matched = {k: point["dimensions"][k] for k in point["dimensions"] if k not in assumed}

        qty, basis, q_assumed = self._quantity(point, params, media_type, notes)
        if qty is None:
            return self._out(status="unpriced", notes=notes + [f"cannot derive quantity for unit {point['unit']}"],
                             unit=point["unit"], unit_credits=point["credits"], price_point_id=point["point_id"],
                             matched=matched, assumed=assumed)
        assumed.update(q_assumed)
        credits = point["credits"] * qty
        original = (point["original_credits"] if point["original_credits"] is not None else point["credits"]) * qty

        # add-ons that share the chosen point's dimensions (same price row in the raw cost entry)
        for add in points:
            if add["unit"] not in ADDON_UNITS or add is point or add["credits"] is None:
                continue
            if add["dimensions"] != point["dimensions"]:
                continue
            n, how, a_assumed = self._addon_quantity(add, params)
            orig = add["original_credits"] if add["original_credits"] is not None else add["credits"]
            credits += add["credits"] * n
            original += orig * n
            assumed.update(a_assumed)
            basis += f" + {add['unit']} x {how}"

        status = "approximate" if (assumed or fuzzy or bad or tie) else "exact"
        if point["attributes"].get("is_estimate") or point["attributes"].get("unit_assumed"):
            status = "approximate"
            notes.append("pricing marks this rate as an estimate / assumed unit")
        if params.get("use_unlim") is True:
            notes.append("params.use_unlim=true: generation may have been free on an unlimited plan")
        return self._out(status=status, credits=round(credits, 4), credits_before_discount=round(original, 4),
                         unit=point["unit"], unit_credits=point["credits"], quantity=qty, quantity_basis=basis,
                         price_point_id=point["point_id"], matched=matched, assumed=assumed, notes=notes)

    # ------------------------------------------------------------------ steps
    def _resolve(self, job_set_type: str) -> tuple[Optional[str], bool]:
        if not job_set_type:
            return None, False
        if job_set_type in self.models:
            return job_set_type, False
        alias = self.aliases.get(job_set_type)
        if alias in self.models:
            return alias, False
        loose = self._loose.get(_loose_key(job_set_type))
        return (loose, True) if loose else (None, False)

    @staticmethod
    def _sanity(model: dict, media_type: Optional[str], notes: list[str]) -> None:
        cat = model.get("category")
        if media_type and cat in ("video", "image", "audio") and media_type != cat:
            notes.append(f"media_type={media_type!r} but pricing category is {cat!r}")

    @staticmethod
    def _component(params: dict, model: dict) -> Optional[str]:
        comps = set(model.get("components") or [])
        for comp, keys in COMPONENT_FLAGS.items():
            if comp in comps and (any(_present(params.get(k)) for k in keys)
                                  or _norm(params.get("operation", "")) == comp
                                  or _norm(params.get("mode", "")) in ("edit", comp)):
                return comp
        return None

    def _wanted(self, params: dict, dims: set[str], model: dict) -> tuple[dict, dict, dict]:
        wanted, sources, bad = {}, {}, {}
        options = model.get("options") or {}
        for dim in dims:
            val: Any = None
            key: Optional[str] = None
            if dim in ("video_input", "video_hdr"):
                val, key = self._derive_video_input(params)
                if dim == "video_hdr" and not any(_present(params.get(k)) for k in HDR_KEYS):
                    val, key = None, None   # HDR rows only when an HDR flag is on
            elif dim == "has_references" and "has_references" not in params:
                val, key = self._derive_references(params)
            else:
                key, val = _first(params, PARAM_DIMENSIONS.get(dim, (dim,)))
                if val is not None and dim in ON_OFF_DIMENSIONS:
                    val = _on_off(val)
            if val is None or isinstance(val, (dict, list)):
                continue
            allowed = {_norm(o) for o in options.get(dim, [])}
            if allowed and _norm(val) not in allowed:
                # e.g. gpt_image_2_6 params.model="aurora-img-alpha" is an internal engine name, not a price option
                if dim == "model":
                    continue
                bad[dim] = val
                continue
            wanted[dim], sources[dim] = val, key
        if "video_hdr" in wanted:  # kling4_0: HDR rows carry the input-video split under `video_hdr` instead
            wanted.pop("video_input", None)
        return wanted, sources, bad

    @staticmethod
    def _derive_video_input(params: dict) -> tuple[Optional[str], Optional[str]]:
        """with_video if any input video is present; without_video if media inputs are known and none is video."""
        for k in VIDEO_PARAM_KEYS:
            if _present(params.get(k)):
                return "with_video", k
        known = False
        for k in MEDIA_LIST_KEYS + IMAGE_PARAM_KEYS + ("reference_elements",):
            if k in params:
                known = True
                v = params[k]
                items = v if isinstance(v, list) else [v] if v else []
                if any(_is_video_media(m) for m in items):
                    return "with_video", k
        return ("without_video", "medias") if known else (None, None)

    @staticmethod
    def _derive_references(params: dict) -> tuple[Optional[bool], Optional[str]]:
        known = False
        for k in REFERENCE_KEYS:
            if k in params:
                known = True
                if _present(params[k]):
                    return True, k
        return (False, "medias") if known else (None, None)

    @staticmethod
    def _choose(mains: list[dict], wanted: dict) -> tuple[Optional[dict], dict, int]:
        nwanted = {k: _norm(v) for k, v in wanted.items()}
        scored = []
        for p in mains:
            ok, matched, unresolved = True, 0, []
            for d, v in p["dimensions"].items():
                if d in nwanted:
                    if _norm(v) != nwanted[d]:
                        ok = False
                        break
                    matched += 1
                else:
                    unresolved.append(d)
            if ok:
                cost = p["credits"] if p["credits"] is not None else math.inf
                scored.append((-matched, len(unresolved), cost, p, unresolved))
        if not scored:
            return None, {}, 0
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        best = scored[0]
        same = [s for s in scored if s[:2] == best[:2]]
        tie = len({s[2] for s in same}) if len({s[2] for s in same}) > 1 and not best[4] else 0
        p = best[3]
        return p, {d: p["dimensions"][d] for d in best[4]}, tie

    def _quantity(self, point: dict, params: dict, media_type: Optional[str],
                  notes: list[str]) -> tuple[Optional[float], str, dict]:
        unit = point["unit"]
        assumed: dict = {}
        bkey, bval = _first(params, BATCH_KEYS)
        batch = _num(bval) if bval is not None else None
        batch = batch if batch and batch > 0 else None
        bnote = f" x {bkey}={int(batch) if batch.is_integer() else batch}" if batch and batch != 1 else ""
        mult = batch or 1.0

        if unit == "credits_per_generation":
            return mult, (f"{bkey}={int(mult) if mult.is_integer() else mult}" if batch else "1 generation (no batch_size)"), assumed
        if unit == "base_credits":
            return 1.0, "base credits once", assumed

        if unit in ("credits_per_second", "credits_per_minute"):
            dkey, dval = _first(params, DURATION_KEYS)
            secs = _num(dval)
            if secs is None or secs <= 0:
                secs = DEFAULT_DURATION_S if unit == "credits_per_second" else DEFAULT_MINUTES * 60
                assumed["duration"] = secs
                notes.append(f"no duration in params; assumed {secs:g} s")
                basis = f"duration={secs:g}s (assumed)"
            else:
                basis = f"{dkey}={secs:g}s"
            qty = secs if unit == "credits_per_second" else secs / 60.0
            return qty * mult, basis + bnote, assumed

        b = BLOCK_RE.match(unit)
        if b:
            size, kind = int(b.group(1)), b.group(2)
            if kind == "seconds":
                dkey, dval = _first(params, DURATION_KEYS)
                secs = _num(dval)
                if secs is None:
                    secs = 60.0
                    assumed["duration"] = secs
                    notes.append("no duration in params; assumed 60 s")
                return math.ceil(secs / size) * mult, f"ceil({secs:g}s/{size}) blocks{bnote}", assumed
            tkey, text = _first(params, TEXT_KEYS)
            if not isinstance(text, str) or not text:
                return None, "", assumed
            return math.ceil(len(text) / size) * mult, f"ceil(len({tkey})={len(text)}/{size}) blocks{bnote}", assumed
        if unit == "credits_per_character":
            tkey, text = _first(params, TEXT_KEYS)
            if not isinstance(text, str) or not text:
                return None, "", assumed
            return float(len(text)) * mult, f"len({tkey})={len(text)} chars{bnote}", assumed
        return None, "", assumed

    @staticmethod
    def _addon_quantity(add: dict, params: dict) -> tuple[float, str, dict]:
        if add["unit"] == "base_credits":
            return 1.0, "1", {}
        images = 0
        found = False
        for k in MEDIA_LIST_KEYS:
            if isinstance(params.get(k), list):
                found = True
                images += sum(1 for m in params[k] if not _is_video_media(m))
        for k in IMAGE_PARAM_KEYS:
            if k in params:
                found = True
                images += 1 if _present(params[k]) else 0
        if not found:
            return 1.0, "1 (assumed)", {f"{add['unit']}_count": 1}
        return float(images), f"{images} input image(s)", {}

    def _out(self, **kw: Any) -> dict:
        credits = kw.get("credits")
        if self.usd_per_credit is not None:
            kw["usd_per_credit"] = self.usd_per_credit
            kw["usd_reference"] = self.usd_reference
            if credits is not None:
                kw["usd"] = round(credits * self.usd_per_credit, 6)
        return EstimatedCost(**kw).model_dump(mode="json")


__all__ = ["CostEstimator", "PARAM_DIMENSIONS", "ALIASES", "DEFAULT_DURATION_S"]
