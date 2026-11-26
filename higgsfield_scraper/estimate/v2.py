"""CostEstimatorV2 (``--estimate-version 2``): the v1 estimator brought in line with the web app's JS formulas.

v1 (``estimator.py``) stays the default and is not changed. v2 subclasses it and fixes the differences listed in
docs/COST_FORMULAS.md §8, using the formulas of §4 (per family) and §5 (account rules). Every v2 estimate carries
``formula_version: 2``. Summary of what v2 does differently (the §8 item number in brackets):

* [1]  per-generation integer ceil: ``ceil(d × cps) × max(1, b)`` (Seedance 2.5/Flash/2.0/mini, Cinema 4.0,
       Happy Horse, Gemini Omni); ``ceil(total)`` for Kling 3.0 motion control (+2 for a chain), Higgsfield Enhance,
       Marketing Studio video.
* [2]  edit mode is ``params.model == "video_edit"`` too; it is charged on the SOURCE video length
       (``medias[].data.duration_sec`` / ``meta.durationSec`` …), clamped to 4–30 s for Seedance 2.5 / Flash.
* [3]  no batch factor for Kling 4.0 / 4.0 Flash / 3.0 / 3.0 Turbo / O3 / motion control, Wan 3.0 / Prime / 4.0,
       Grok v1.5 / Lite, Flux 3 video, Higgsfield Enhance.
* [4]  Genjutsu / AI Influencer motion control & replace object: ``ceil(d) × cps × b``.
* [5]  reframe: ``ceil(round(d) × cps + n_img × image_credits)``, n_img = 3 (``image_count``) or 2·segments+1.
* [7]  Qwen TTS: ``max(minimum_cost_units, ceil(chars × num/den)) / cost_units_per_credit``.
* [8]  Seed Audio: seconds = ``clamp(ceil(chars / 15), 1, 120)`` from the text.
* [9]  ``duration_rounding`` of formula rows (dubbing ``floor``, music ``ceil`` minutes) + integer ceil for dubbing.
* [10] per-model default durations (Seedance 2.0/mini, Cinema 3.x: 4 s; Gemini: 8 s; Kling 4.0: 10 s).
* [11] viral presets: ``ceil(credit_units / 100)``.
* [12] ``ceil₀.₀₁`` (JS ``Es``) for Wan 3.0 / Prime / 4.0, GPT Image, voice change, Flux video upscale.
* [14] Kling 3.0 / O3 multi-shot: ``Σ multi_prompt[].duration``.
* [15] Wan edit: ``d = ceil(Σ source seconds − 0.01)`` on the ``with_video`` row.
* [16] scene_switch-style numeric fields (``cost_per_run`` …) are add-on costs, not price dimensions.
* [17] static JS tables (``js_static.py``) for job types without a /job-sets/costs row (before the compare table).
* [18] ``use_unlim`` note follows the unlimited rules (batch ≤ 1; never for magi_2 / wan4_0 / Flash types).
* [19] GPT Image: ``quality: auto`` → high; a missing quality / resolution / combination falls back to high / 2k.

Kept as v1 on purpose: [6] (MiniMax TTS batch: the live row says linear, the UI ignores it), [13] (Kling sound
default off = the main page). See docs/scrapers/cost-estimate.md for the full table.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Optional

from ..parsers.costs import options_of
from .estimator import (ADDON_UNITS, BATCH_KEYS, BLOCK_RE, DEFAULT_DURATION_S, DEFAULT_MINUTES, DEFAULT_POLICY,
                        DURATION_KEYS, TEXT_KEYS, VIDEO_PARAM_KEYS, CostEstimator, _first, _is_video_media, _norm,
                        _num)
from .js_static import SOURCE as STATIC_SOURCE, STATIC

FORMULA_VERSION = 2

# ------------------------------------------------------------------------------------------- per-model rules
#: ceil(d × cps) × max(1, b)                                                                  [1]
CEIL_THEN_BATCH = {"seedance_2_5", "seedance_2_5_flash", "seedance_2_0", "seedance_2_0_mini",
                   "cinematic_studio_video_4_0", "happy_horse_video", "gemini_omni"}
#: ceil(whole amount)                                                                          [1] [9]
CEIL_TOTAL = {"kling3_0_motion_control", "seedance_2_5_kling_upscale", "marketing_studio_video", "audio_dubbing",
              "dubbing_lipsync"}
#: ceil to 0.01 credit (JS Es)                                                                 [12]
CENT_CEIL = {"wan3_0", "wan3_0_prime", "wan4_0", "voice_change_merge", "flux_video_upscale", "gpt_image_2",
             "gpt_image_2_5", "gpt_image_2_6", "gpt_image_2_6_flare", "gpt_image_2_unlimited"}
#: no batch factor in the JS formula (batch fixed at 1 or not part of the price)                [3]
NO_BATCH = {"kling4_0", "kling_4_0_flash", "kling3_0", "kling3_0_turbo", "kling_o3_flf", "kling_o3_image_reference",
            "kling3_0_motion_control", "wan3_0", "wan3_0_prime", "wan4_0", "grok_video_v15", "grok_video_v15_lite",
            "flux_3_video", "seedance_2_5_kling_upscale", "reframe"}
#: ceil(d) seconds                                                                             [4]
CEIL_SECONDS = {"hf_mult_motion_control", "hf_mult_motion_control_flash", "hf_mult_replace_object",
                "hf_mult_replace_object_flash", "ai_influencer_motion_control", "ai_influencer_motion_control_flash",
                "ai_influencer_replace_object", "ai_influencer_replace_object_flash"}
#: JS default duration when params have none (v1: 5 s for every model)                          [10]
DEFAULT_DURATIONS = {"seedance_2_0": 4.0, "seedance_2_0_mini": 4.0, "cinematic_studio_3_0": 4.0,
                     "cinematic_studio_video_3_5": 4.0, "gemini_omni": 8.0, "gemini_omni_flash_1_2": 8.0,
                     "kling4_0": 10.0, "kling_4_0_flash": 10.0}
#: edit mode charged on the source video length, clamped (min, max) or not clamped (None)       [2]
EDIT_CLAMP: dict[str, Optional[tuple[float, float]]] = {"seedance_2_5": (4.0, 30.0), "seedance_2_5_flash": (4.0, 30.0),
                                                         "cinematic_studio_video_4_0": None}
WAN_EDIT = {"wan3_0", "wan3_0_prime", "wan4_0"}                                                # [15]
MULTI_SHOT = {"kling3_0", "kling_o3_flf", "kling_o3_image_reference"}                          # [14]
GPT_IMAGE = {"gpt_image_2", "gpt_image_2_5", "gpt_image_2_6", "gpt_image_2_6_flare", "gpt_image_2_unlimited"}  # [19]
GPT_FALLBACK = {"quality": "high", "resolution": "2k"}
#: numeric row fields that are add-on costs, not price dimensions (scene_switch)                [16]
ADDON_SCALAR_KEYS = {"cost_per_run", "cost_per_piece", "piece", "masks_cost_per_frame", "picture_cost", "look_cost"}
#: use_unlim never applies (adapter forces false; Flash types get no unlimited)                 [18]
NEVER_UNLIMITED = {"magi_2", "wan4_0", "kling_4_0_flash", "grok_video_v15_lite", "hf_mult_motion_control_flash",
                   "hf_mult_replace_object_flash"}
#: source-video length keys (on the media object, its data / meta)
SOURCE_SECONDS_KEYS = ("duration_sec", "durationSec", "duration_seconds", "duration")
SOURCE_TOP_KEYS = ("source_duration", "source_video_duration", "input_video_duration")


def ceil_cents(x: float) -> float:
    """JS ``Es(x) = Math.ceil(Number((x*100).toFixed(6)))/100``."""
    return math.ceil(round(x * 100, 6)) / 100


def _ceil(x: float) -> float:
    return float(math.ceil(round(x, 9)))


def _js_round(x: float) -> float:
    """JS Math.round (half up)."""
    return float(math.floor(x + 0.5))


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def _prepare_model(model: dict) -> dict:
    """Move scene_switch-style numeric cost fields out of the price dimensions into point attributes [16]."""
    if not any(k in ADDON_SCALAR_KEYS for p in model["price_points"] for k in p["dimensions"]):
        return model
    m = copy.deepcopy(model)
    for p in m["price_points"]:
        for k in [k for k in p["dimensions"] if k in ADDON_SCALAR_KEYS]:
            p["attributes"][k] = p["dimensions"].pop(k)
    m["options"] = options_of(m["price_points"])
    return m


def _source_seconds(params: dict) -> list[float]:
    """Lengths of the input videos, in order (medias with a video role/type, input_video, …)."""
    out: list[float] = []
    for k in SOURCE_TOP_KEYS:
        n = _num(params.get(k))
        if n and n > 0:
            return [n]
    for k in ("medias",) + VIDEO_PARAM_KEYS:
        v = params.get(k)
        items = v if isinstance(v, list) else [v] if isinstance(v, dict) else []
        for m in items:
            if not isinstance(m, dict) or (k == "medias" and not _is_video_media(m)):
                continue
            data = m.get("data") if isinstance(m.get("data"), dict) else {}
            for d in (m, data, m.get("meta") if isinstance(m.get("meta"), dict) else {},
                      data.get("meta") if isinstance(data.get("meta"), dict) else {}):
                n = next((x for x in (_num(d.get(s)) for s in SOURCE_SECONDS_KEYS) if x and x > 0), None)
                if n:
                    out.append(n)
                    break
    return out


def _multi_shot_seconds(params: dict) -> Optional[float]:
    if not _truthy(params.get("multi_shots")) or str(params.get("multi_shot_mode") or "custom") != "custom":
        return None
    shots = params.get("multi_prompt")
    if not isinstance(shots, list) or not shots:
        return None
    ds = [_num(s.get("duration")) if isinstance(s, dict) else None for s in shots]
    return float(sum(ds)) if all(d is not None and d > 0 for d in ds) else None


# ------------------------------------------------------------------------------------------- estimator
class CostEstimatorV2(CostEstimator):
    formula_version = FORMULA_VERSION

    def __init__(self, models: dict[str, dict], usd_per_credit: Optional[float] = None,
                 usd_reference: Optional[str] = None, aliases: Optional[dict[str, str]] = None):
        super().__init__({k: _prepare_model(m) for k, m in models.items()}, usd_per_credit=usd_per_credit,
                         usd_reference=usd_reference, aliases=aliases)

    def _out(self, **kw: Any) -> dict:
        kw["formula_version"] = FORMULA_VERSION
        return super()._out(**kw)

    # ------------------------------------------------------------------ public
    def estimate(self, job_set_type: str, params: Optional[dict], media_type: Optional[str] = None) -> dict:
        params = params if isinstance(params, dict) else {}
        notes: list[str] = []
        model_id, fuzzy = self._resolve(job_set_type)
        if model_id is None:
            return self._estimate_unlisted(job_set_type, params, media_type, notes)
        if model_id != job_set_type:
            notes.append(f"priced as {model_id!r} ({'separator-insensitive match' if fuzzy else 'alias'})")
        model = self.models[model_id]
        self._sanity(model, media_type, notes)

        edit = _norm(params.get("model", "")) == "video_edit"
        comps = set(model.get("components") or [])
        component = "video_edit" if edit and "video_edit" in comps else self._component(params, model)
        points = [p for p in model["price_points"] if p["component"] == component]
        mains = [p for p in points if p["unit"] not in ADDON_UNITS]
        if not mains:
            mains = [p for p in points if p["unit"] == "base_credits"]
        if not mains:
            return self._out(status="unpriced", notes=notes + [f"{model_id}: no usable price point"])

        dims_used = {k for p in mains for k in p["dimensions"]}
        wanted, _sources, bad = self._wanted(params, dims_used, model)
        v2_assumed: dict = {}
        if model_id in WAN_EDIT and edit and "video_input" in dims_used:          # [15] edit is always with_video
            wanted["video_input"] = "with_video"
            notes.append("Wan edit (model=video_edit): priced on the with_video row")
        if model_id in GPT_IMAGE:                                                  # [19]
            if _norm(params.get("quality", "")) == "auto" and "quality" in dims_used:
                bad.pop("quality", None)
                wanted["quality"] = "high"
                notes.append("quality=auto is priced as high (JS)")
            if bad.keys() & GPT_FALLBACK.keys():
                for d, v in GPT_FALLBACK.items():
                    if d in dims_used:
                        wanted[d] = v
                        v2_assumed[d] = v
                notes.append("option not in the price rows: JS falls back to the high/2k row")
                bad = {k: v for k, v in bad.items() if k not in GPT_FALLBACK}
            for d, v in GPT_FALLBACK.items():
                if d in dims_used and d not in wanted:
                    wanted[d] = v
                    v2_assumed[d] = v
                    notes.append(f"no {d} in params: JS falls back to the high/2k row ({d}={v})")
        for d, v in bad.items():
            notes.append(f"param {d}={v!r} not in pricing options {model['options'].get(d)}; assumed instead")

        point, assumed, tie = self._choose(mains, wanted)
        if point is None and model_id in GPT_IMAGE:                                # [19] missing combination
            for d, v in GPT_FALLBACK.items():
                if d in dims_used:
                    wanted[d] = v
                    v2_assumed[d] = v
            notes.append("combination not in the price rows: JS falls back to the high/2k row")
            point, assumed, tie = self._choose(mains, wanted)
        if point is None or point["credits"] is None or point["unit"] == "formula":
            return self._out(status="unpriced",
                             notes=notes + [f"{model_id}: unit {point['unit'] if point else None!r} not computable"])
        if tie:
            notes.append(f"{tie} price points fit equally; chose lowest-cost ({DEFAULT_POLICY})")
        if assumed:
            notes.append(f"unresolved dimensions assumed ({DEFAULT_POLICY}): "
                         + ", ".join(f"{k}={v}" for k, v in assumed.items()))
        assumed.update(v2_assumed)
        matched = {k: point["dimensions"][k] for k in point["dimensions"] if k not in assumed}

        q = self._quantity_v2(model_id, point, params, component, edit, notes)
        if q is None:
            return self._out(status="unpriced", notes=notes + [f"cannot derive quantity for unit {point['unit']}"],
                             unit=point["unit"], unit_credits=point["credits"], price_point_id=point["point_id"],
                             matched=matched, assumed=assumed)
        units, batch, basis, q_assumed = q
        assumed.update(q_assumed)
        orig_rate = point["original_credits"] if point["original_credits"] is not None else point["credits"]

        inferred = False
        if model_id == "reframe":                                                  # [5]
            credits, original, basis = self._reframe(point, points, units, basis)
        elif point["formula"] and point["formula"]["name"] == "linear_units":      # [7]
            credits, original, basis = self._linear_units(point, params, batch, basis)
        else:
            extra = 0.0
            if model_id == "kling3_0_motion_control" and _truthy(params.get("is_chain") or params.get("isChain")):
                extra = 2.0
                basis += " + 2 (chain)"
            if model_id == "marketing_studio_video" and _truthy(params.get("web_product")):
                extra = 6.0 * batch
                basis += " + 6 x batch (web product)"
            credits = self._round(model_id, point["credits"] * units, batch, extra)
            original = self._round(model_id, orig_rate * units, batch, extra)
            for add in points:                                                     # v1 add-ons (same price row)
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
            run = self._run_cost(point)                                            # [16]
            if run:
                credits += run
                original += run
                basis += f" + cost_per_run {run:g}"
                inferred = True
                notes.append("cost_per_run added once per generation (inferred from the price row; "
                             "no client formula found)")

        status = "approximate" if (assumed or fuzzy or bad or tie or v2_assumed or inferred) else "exact"
        attrs = point["attributes"]
        if attrs.get("is_estimate") or (attrs.get("unit_assumed") and not (
                point["formula"] and point["formula"]["name"] == "linear_units")):
            status = "approximate"
            notes.append("pricing marks this rate as an estimate / assumed unit")
        self._unlimited_note(model_id, params, self._batch(params)[0], notes)      # [18] requested batch
        return self._out(status=status, credits=round(credits, 4), credits_before_discount=round(original, 4),
                         unit=point["unit"], unit_credits=point["credits"], quantity=units * batch,
                         quantity_basis=basis, price_point_id=point["point_id"], matched=matched, assumed=assumed,
                         notes=notes)

    # ------------------------------------------------------------------ unlisted job types
    def _estimate_unlisted(self, job_set_type: str, params: dict, media_type: Optional[str],
                           notes: list[str]) -> dict:
        pid = str(params.get("chain_preset_id") or params.get("preset_id") or "")
        if pid and pid in self.viral:                                              # [11]
            from .compare_fallback import estimate_viral
            r = estimate_viral(self.viral[pid], params)
            if r.get("credits") is not None:
                c = _ceil(r["credits"])
                return self._out(status=r["status"], credits=c, credits_before_discount=c,
                                 unit="credits_per_generation", unit_credits=c, quantity=1,
                                 quantity_basis="1 viral preset run, ceil(credit_units / 100)",
                                 price_point_id=f"viral:{pid}", matched=r["matched"], assumed=r["assumed"],
                                 notes=notes + r["notes"])
        if job_set_type in STATIC:                                                 # [17]
            r = STATIC[job_set_type](params)
            if r is not None:
                b = self._batch(params)[0]
                n = list(r["notes"])
                self._unlimited_note(job_set_type, params, b, n)
                return self._out(status="approximate", credits=r["credits"], credits_before_discount=r["credits"],
                                 unit=r["unit"], unit_credits=r["unit_credits"], quantity=r["quantity"],
                                 quantity_basis=r["quantity_basis"], price_point_id=f"js_static:{job_set_type}",
                                 matched=r["matched"], assumed=r["assumed"],
                                 notes=notes + [f"no /job-sets/costs entry — priced from the {STATIC_SOURCE}"] + n)
        if job_set_type in self.fallback:
            from .compare_fallback import estimate_from_rate, pick
            rate = pick(self.fallback[job_set_type], params)
            r = estimate_from_rate(rate, params, media_type) if rate else {"credits": None, "notes": []}
            if r.get("credits") is not None:
                return self._out(status="approximate", credits=r["credits"], credits_before_discount=r["credits"],
                                 unit=r["unit"], unit_credits=r["unit_credits"], quantity=r["quantity"],
                                 quantity_basis=r["quantity_basis"], price_point_id=f"compare:{rate['detail']}",
                                 matched={"resolution": rate["resolution"]} if rate["resolution"] else {},
                                 assumed=r["assumed"], notes=notes + r["notes"])
        return self._out(status="unpriced", notes=[f"no /job-sets/costs entry for job_set_type {job_set_type!r}"])

    # ------------------------------------------------------------------ quantity
    @staticmethod
    def _batch(params: dict) -> tuple[float, Optional[str]]:
        bkey, bval = _first(params, BATCH_KEYS)
        b = _num(bval) if bval is not None else None
        return (b if b and b > 0 else 1.0), (bkey if b and b > 0 else None)

    def _quantity_v2(self, model_id: str, point: dict, params: dict, component: Optional[str], edit: bool,
                     notes: list[str]) -> Optional[tuple[float, float, str, dict]]:
        """-> (units per generation, batch factor, basis, assumed); credits = round_rule(rate × units, batch)."""
        unit = point["unit"]
        assumed: dict = {}
        b, bkey = self._batch(params)
        if model_id in NO_BATCH:
            bnote = f" ({bkey}={b:g} ignored: no batch factor)" if bkey and b != 1 else ""
            b = 1.0
        else:
            bnote = f" x {bkey}={int(b) if b.is_integer() else b}" if bkey and b != 1 else ""

        if unit == "credits_per_generation":
            return 1.0, b, (f"{bkey}={int(b) if b.is_integer() else b}" if bkey else "1 generation (no batch_size)") \
                + (bnote if model_id in NO_BATCH else ""), assumed
        if unit == "base_credits":
            return 1.0, 1.0, "base credits once", assumed

        formula = point.get("formula") or {}
        fparams = formula.get("params") or {}
        if unit in ("credits_per_second", "credits_per_minute"):
            secs, basis = self._seconds(model_id, point, params, component, edit, assumed, notes)
            if model_id in CEIL_SECONDS:                                           # [4]
                secs, basis = float(math.ceil(round(secs, 9))), f"ceil({basis})"
            if model_id == "grok_video_v15":
                secs = max(secs, 1.0)
            if fparams.get("duration_rounding") == "floor":                         # [9]
                secs, basis = float(math.floor(secs)), f"floor({basis})"
            if unit == "credits_per_minute":
                mins = secs / 60.0
                if fparams.get("duration_rounding") == "ceil":                      # [9] ceil(minutes)
                    return float(math.ceil(round(mins, 9))), b, f"ceil({basis} / 60) min{bnote}", assumed
                return mins, b, basis + bnote, assumed
            return secs, b, basis + bnote, assumed

        blk = BLOCK_RE.match(unit)
        if blk:
            size, kind = int(blk.group(1)), blk.group(2)
            if kind == "seconds":
                dkey, dval = _first(params, DURATION_KEYS)
                secs = _num(dval)
                if secs is None:
                    secs = 60.0
                    assumed["duration"] = secs
                    notes.append("no duration in params; assumed 60 s")
                return float(math.ceil(secs / size)), b, f"ceil({secs:g}s/{size}) blocks{bnote}", assumed
            tkey, text = _first(params, TEXT_KEYS)
            if not isinstance(text, str) or not text:
                return None
            return float(math.ceil(len(text) / size)), b, f"ceil(len({tkey})={len(text)}/{size}) blocks{bnote}", assumed
        if unit == "credits_per_character":
            tkey, text = _first(params, TEXT_KEYS)
            if not isinstance(text, str) or not text:
                return None
            return float(len(text)), b, f"len({tkey})={len(text)} chars{bnote}", assumed
        return None

    def _seconds(self, model_id: str, point: dict, params: dict, component: Optional[str], edit: bool,
                 assumed: dict, notes: list[str]) -> tuple[float, str]:
        formula = point.get("formula") or {}
        fparams = formula.get("params") or {}
        # [8] Seed Audio: speech length estimated from the text
        if formula.get("name") == "estimated_duration" and fparams.get("characters_per_second"):
            tkey, text = _first(params, TEXT_KEYS)
            if isinstance(text, str) and text:
                cps = fparams["characters_per_second"]
                lo, hi = fparams.get("minimum_seconds") or 1, fparams.get("maximum_seconds") or 120
                secs = float(min(max(math.ceil(len(text) / cps), lo), hi))
                return secs, f"clamp(ceil(len({tkey})={len(text)}/{cps:g}), {lo:g}, {hi:g})={secs:g}s"
        # [2] / [15] edit mode: charged on the source video length
        is_edit = component == "video_edit" or (edit and model_id in WAN_EDIT)
        if is_edit:
            src = _source_seconds(params)
            if src:
                if model_id in WAN_EDIT:
                    total = sum(src)
                    return float(math.ceil(round(total - 0.01, 9))), f"ceil(source {total:g}s - 0.01)"
                s = src[0]
                clamp = EDIT_CLAMP.get(model_id)
                if clamp:
                    c = min(clamp[1], max(clamp[0], s))
                    return c, f"source video {s:g}s" + (f" clamped to {c:g}s" if c != s else "")
                return s, f"source video {s:g}s"
            notes.append("edit mode: source video length not in params; output duration used instead")
        # [14] multi-shot
        if model_id in MULTI_SHOT:
            ms = _multi_shot_seconds(params)
            if ms is not None:
                return ms, f"sum(multi_prompt[].duration)={ms:g}s"
        dkey, dval = _first(params, DURATION_KEYS)
        secs = _num(dval)
        if secs is None or secs <= 0:
            if point["unit"] == "credits_per_minute":
                secs = DEFAULT_MINUTES * 60
            else:
                secs = DEFAULT_DURATIONS.get(model_id, DEFAULT_DURATION_S)                  # [10]
            key = "source_duration" if is_edit else "duration"
            assumed[key] = secs
            notes.append(f"no duration in params; assumed {secs:g} s"
                         + (" (JS default for this model)" if model_id in DEFAULT_DURATIONS else ""))
            return secs, f"duration={secs:g}s (assumed)"
        if is_edit:
            assumed["source_duration"] = secs
            clamp = EDIT_CLAMP.get(model_id)
            if clamp:
                secs = min(clamp[1], max(clamp[0], secs))
        return secs, f"{dkey}={secs:g}s"

    # ------------------------------------------------------------------ credits
    @staticmethod
    def _round(model_id: str, amount: float, batch: float, extra: float = 0.0) -> float:
        """amount = rate × units of ONE generation; extra = add-on inside the JS rounding."""
        if model_id in CEIL_THEN_BATCH:                                            # [1]
            return _ceil(amount + extra) * max(1.0, batch)
        if model_id in CEIL_TOTAL:
            return _ceil(amount * batch + extra)
        if model_id in CENT_CEIL:                                                  # [12]
            return ceil_cents(amount * batch + extra)
        return amount * batch + extra

    @staticmethod
    def _reframe(point: dict, points: list[dict], secs: float, basis: str) -> tuple[float, float, str]:
        """[5] ceil(round(d) × cps + n_img × image_credits), n_img = segments > 1 ? 2·segments+1 : image_count."""
        img = next((p for p in points if p["unit"] == "credits_per_image" and p["dimensions"] == point["dimensions"]),
                   None)
        rate_img = (img or {}).get("credits") or 0.0
        orig_img = (img or {}).get("original_credits") if img and img.get("original_credits") is not None else rate_img
        segments = 1 if secs <= 15.25 else math.ceil((secs - 0.25) / 15)
        n_img = 2 * segments + 1 if segments > 1 else int((img or point)["attributes"].get("image_count") or 3)
        d = _js_round(secs)
        orig = point["original_credits"] if point["original_credits"] is not None else point["credits"]
        credits = _ceil(d * point["credits"] + n_img * rate_img)
        original = _ceil(d * orig + n_img * orig_img)
        return credits, original, f"ceil(round({basis}) x cps + {n_img} images x {rate_img:g})"

    @staticmethod
    def _linear_units(point: dict, params: dict, batch: float, basis: str) -> tuple[float, float, str]:
        """[7] Qwen: max(minimum_cost_units, ceil(chars × numerator / denominator)) / cost_units_per_credit."""
        fp = point["formula"]["params"]
        _, text = _first(params, TEXT_KEYS)
        n = len(text) if isinstance(text, str) else 0
        num, den = fp.get("cost_units_numerator") or 0, fp.get("cost_units_denominator") or 1
        units = max(fp.get("minimum_cost_units") or 0, math.ceil(round(n * num / den, 9)))
        per = units / (fp.get("cost_units_per_credit") or 100)
        return per * batch, per * batch, f"max({fp.get('minimum_cost_units') or 0}, ceil({n} x {num}/{den})) units" \
            + (f" x batch {batch:g}" if batch != 1 else "")

    @staticmethod
    def _run_cost(point: dict) -> float:
        a = point["attributes"]
        run = _num(a.get("cost_per_run"))
        if run is None and str(a.get("piece") or "") == "run":
            run = _num(a.get("cost_per_piece"))
        return run or 0.0

    @staticmethod
    def _unlimited_note(model_id: str, params: dict, batch: float, notes: list[str]) -> None:
        if params.get("use_unlim") is not True:
            return
        if model_id in NEVER_UNLIMITED:
            notes.append(f"params.use_unlim=true has no effect for {model_id} (never unlimited): charged")
        elif batch > 1:
            notes.append("params.use_unlim=true but batch_size > 1: unlimited grants require batch_size <= 1, "
                         "so this generation was charged")
        else:
            notes.append("params.use_unlim=true: generation may have been free on an unlimited plan")


__all__ = ["CostEstimatorV2", "FORMULA_VERSION", "ceil_cents"]
