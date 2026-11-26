"""Static price tables from the Higgsfield JS bundle (build 548e0f3a) for job types WITHOUT a /job-sets/costs row.

Used only by the v2 estimator (``estimate/v2.py``, ``--estimate-version 2``), and only when the live table has no
entry for the job_set_type (the web app does the same: live rows first, the static table second). Every formula is
copied from docs/COST_FORMULAS.md §4 (which cites the chunk). Results are always reported as "approximate": these
models are retired or unlisted, and the server may charge differently from the stale client table.

``STATIC[job_set_type](params) -> dict | None`` returns the fields ``credits``, ``unit``, ``unit_credits``,
``quantity``, ``quantity_basis``, ``matched``, ``assumed``, ``notes`` (or None when a required option is unknown).
"""
from __future__ import annotations

import math
from typing import Any, Callable, Optional

from .estimator import BATCH_KEYS, DURATION_KEYS, _first, _norm, _num

SOURCE = "static JS price table (docs/COST_FORMULAS.md §4, build 548e0f3a)"


# --------------------------------------------------------------------------------------------- helpers
def _batch(params: dict, default: int = 1) -> tuple[int, str]:
    key, val = _first(params, BATCH_KEYS)
    n = _num(val)
    if n is None or n < 1:
        return default, f"batch {default} (default)"
    return int(n), f"{key}={int(n)}"


def _duration(params: dict, default: float) -> tuple[float, dict, str]:
    key, val = _first(params, DURATION_KEYS)
    d = _num(val)
    if d is None or d <= 0:
        return float(default), {"duration": float(default)}, f"duration={default:g}s (assumed)"
    return d, {}, f"{key}={d:g}s"


def _pick(params: dict, keys: tuple[str, ...], table: dict, default: str) -> tuple[Optional[str], dict]:
    """value of the first param in `keys` normalized against the table keys; missing -> (default, assumed)."""
    _, val = _first(params, keys)
    if val is None or isinstance(val, (dict, list)):
        return default, {keys[0]: default}
    n = _norm(val)
    for k in table:
        if _norm(k) == n:
            return k, {}
    return None, {}


def _res(params: dict, table: dict, default: str) -> tuple[Optional[str], dict]:
    return _pick(params, ("resolution", "output_resolution"), table, default)


def _r(credits: float, unit: str, unit_credits: Optional[float], quantity: float, basis: str,
       matched: Optional[dict] = None, assumed: Optional[dict] = None, notes: Optional[list] = None) -> dict:
    return {"credits": round(credits, 4), "unit": unit, "unit_credits": unit_credits, "quantity": quantity,
            "quantity_basis": basis, "matched": matched or {}, "assumed": assumed or {}, "notes": notes or []}


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------------------------- shapes
def per_image(rate: float, default_batch: int = 1) -> Callable[[dict], dict]:
    """b × rate"""
    def f(p: dict) -> dict:
        b, how = _batch(p, default_batch)
        return _r(b * rate, "credits_per_generation", rate, b, how)
    return f


def per_image_by(table: dict, default: str, keys: tuple[str, ...] = ("resolution",),
                 batch: bool = True) -> Callable[[dict], Optional[dict]]:
    """b × table[option]"""
    def f(p: dict) -> Optional[dict]:
        k, assumed = _pick(p, keys, table, default)
        if k is None:
            return None
        b, how = _batch(p) if batch else (1, "1 generation (no batch factor)")
        return _r(b * table[k], "credits_per_generation", table[k], b, how, {} if assumed else {keys[0]: k}, assumed)
    return f


def fixed(credits: float) -> Callable[[dict], dict]:
    return lambda p: _r(credits, "credits_per_generation", credits, 1, "fixed price per generation")


def flux_2(p: dict) -> Optional[dict]:
    t = {"pro": {"1k": 1, "2k": 1.5}, "flex": {"1k": 3, "2k": 5}, "max": {"1k": 4, "2k": 6}}
    model, a1 = _pick(p, ("model",), t, "pro")
    if model is None:
        return None
    res, a2 = _res(p, t[model], "1k")
    if res is None:
        return None
    b, how = _batch(p)
    matched = {**({} if a1 else {"model": model}), **({} if a2 else {"resolution": res})}
    return _r(b * t[model][res], "credits_per_generation", t[model][res], b, how, matched, {**a1, **a2})


def per_second(table: Optional[dict], rate: Optional[float] = None, *, default_d: float = 5, default_res: str = "",
               ceil: bool = True, batch: bool = False, minimum_d: float = 0) -> Callable[[dict], Optional[dict]]:
    """ceil(d × rate[res]) [× b]"""
    def f(p: dict) -> Optional[dict]:
        assumed, matched = {}, {}
        r = rate
        if table is not None:
            k, a = _res(p, table, default_res)
            if k is None:
                return None
            r = table[k]
            assumed.update(a)
            if not a:
                matched["resolution"] = k
        d, a, basis = _duration(p, default_d)
        assumed.update(a)
        d = max(d, minimum_d)
        b, how = _batch(p) if batch else (1, "")
        c = d * r
        c = math.ceil(round(c, 9)) if ceil else c
        return _r(c * b, "credits_per_second", r, d * b, basis + (f" x {how}" if batch and b != 1 else ""),
                  matched, assumed)
    return f


def veo3_1(p: dict) -> dict:
    ref = str(p.get("mode") or "") == "reference_images"
    model = "veo-3-1-preview" if ref else str(p.get("model") or "veo-3-1-preview")
    d, assumed, basis = (8.0, {}, "reference_images mode: 8 s") if ref else _duration(p, 8)
    fast = model == "veo-3-1-fast"
    ultra = str(p.get("quality") or "") == "ultra"
    if fast:
        c, how = (math.ceil(6 * d), "ceil(6 x d)") if ultra else (math.ceil(round(d / 8 * 22, 9)), "ceil(d/8 x 22)")
    else:
        c, how = (math.ceil(round(10.9 * d, 9)), "ceil(10.9 x d)") if ultra else \
            (math.ceil(round(d / 8 * 58, 9)), "ceil(d/8 x 58)")
    return _r(c, "credits_per_generation", None, 1, f"{basis}; {how}", {"model": model}, assumed)


def veo3_1_lite(p: dict) -> dict:
    res = str(p.get("resolution") or "720p").lower()
    audio_v = p.get("generate_audio", p.get("audio"))
    assumed = {} if audio_v is not None else {"generate_audio": False}
    audio = _truthy(audio_v) if audio_v is not None else False
    rate = (2 if audio else 1.5) if res == "1080p" else (1.5 if audio else 1)
    d, a, basis = _duration(p, 8)
    return _r(math.ceil(round(d * rate, 9)), "credits_per_second", rate, d, basis, {}, {**assumed, **a})


SORA = {"sora-2": {"720p": 2.4, "1080p": 7.4}, "sora-2-pro": {"720p": 7.4, "1080p": 12.4}}


def sora2_video(p: dict) -> Optional[dict]:
    model = str(p.get("model") or "sora-2").lower()
    base = "sora-2-pro" if model.startswith("sora-2-pro") else "sora-2"
    is_max = "max" in model or _truthy(p.get("max"))
    res, assumed = _res(p, SORA[base], "720p")
    if res is None:
        return None
    d, a, basis = _duration(p, 4)
    rate = SORA[base][res]
    c = math.ceil(round(rate * d, 9)) + (4 if is_max else 0)
    return _r(c, "credits_per_second", rate, d, basis + (" + 4 (max)" if is_max else ""),
              {"model": base, "resolution": res}, {**assumed, **a})


def kling2_6(p: dict) -> dict:
    d, a, basis = _duration(p, 5)
    sound = _truthy(p.get("sound", p.get("generate_audio")))
    return _r(d * 2 if sound else d, "credits_per_second", 2 if sound else 1, d, basis, {"audio": "on" if sound else "off"}, a)


def _chain(p: dict) -> bool:
    return _truthy(p.get("is_chain") or p.get("isChain"))


def kling2_6_motion_control(p: dict) -> dict:
    rate = 1.5 if str(p.get("mode") or "") == "pro" else 1
    d, a, basis = _duration(p, 5)
    return _r(math.ceil(round(rate * d + (2 if _chain(p) else 0), 9)), "credits_per_second", rate, d, basis, {}, a)


def kling_omni_video(p: dict) -> dict:
    rate = 2 if str(p.get("mode") or "") == "pro" else 1.5
    d, a, basis = _duration(p, 5)
    return _r(math.ceil(round(d * rate, 9)), "credits_per_second", rate, d, basis, {}, a)


def minimax_h3(p: dict) -> Optional[dict]:
    return per_second({"480p": 1.5, "768p": 2.5}, default_res="480p", ceil=False, batch=True)(p)


HAILUO = {"minimax-2.3": {6: {"768p": 6, "1080p": 10}, 10: {"768p": 11}},
          "minimax-2.3-fast": {6: {"768p": 4, "1080p": 7}, 10: {"768p": 7}}}


def minimax_hailuo(p: dict) -> Optional[dict]:
    model = str(p.get("model") or "minimax-2.3").lower()
    model = model if model in HAILUO else ("minimax-2.3-fast" if "fast" in model else "minimax-2.3")
    d, a, _ = _duration(p, 6)
    res = _norm(p.get("resolution") or "768p")
    if res == "512p":
        t = {6: 3, 10: 5}
        if int(d) not in t:
            return None
        return _r(t[int(d)], "credits_per_generation", None, 1, f"512p table, {int(d)} s", {"model": model}, a)
    row = HAILUO[model].get(int(d), {})
    if res not in row:
        return None
    return _r(row[res], "credits_per_generation", None, 1, f"table[{model}][{int(d)} s][{res}]",
              {"model": model, "resolution": res}, a)


def wan2_5_video(p: dict) -> Optional[dict]:
    fast = "fast" in str(p.get("model") or p.get("mode") or "").lower()
    t = {"720p": 1.8, "1080p": 2.5} if fast else {"480p": 1.25, "720p": 2.5, "1080p": 4}
    return per_second(t, default_res="720p" if fast else "480p")(p)


def image2video(p: dict) -> Optional[dict]:
    """Higgsfield DoP: frames 49|81, model lite|standard|turbo, steps."""
    model = str(p.get("model") or "standard")
    frames = int(_num(p.get("frames")) or 49)
    if frames not in (49, 81):
        return None
    if model == "lite":
        return _r(5 if frames == 81 else 3, "credits_per_generation", None, 1, f"lite, {frames} frames")
    steps = _num(p.get("steps"))
    steps = int(steps) if steps is not None else (30 if model == "turbo" else 20)
    if model == "turbo":
        units = 10 * steps + 400 if frames == 81 else 7 * steps + 280
    else:
        units = 35 * steps + 300 if frames == 81 else 24 * steps + 200
    return _r(math.ceil(units / 100), "credits_per_generation", None, 1,
              f"ceil({units}/100) ({model}, {frames} frames, steps {steps})")


def seedance1_5(p: dict) -> Optional[dict]:
    t = {"480p": (0.3, 0.6), "720p": (0.6, 1.2), "1080p": (1.5, 3)}
    res, assumed = _res(p, t, "480p")
    if res is None:
        return None
    audio = _truthy(p.get("generate_audio", p.get("audio")))
    rate = t[res][1 if audio else 0]
    d, a, basis = _duration(p, 5)
    return _r(math.ceil(round(d * rate, 9)), "credits_per_second", rate, d, basis, {"resolution": res}, {**assumed, **a})


def seedance_1(p: dict) -> Optional[dict]:
    t = {"pro": {"480p": 0.8, "720p": 1.6, "1080p": 3.6}, "pro_fast": {"480p": 0.5, "720p": 0.9, "1080p": 1.8}}
    model = "pro_fast" if "fast" in str(p.get("model") or "") else "pro"
    res, assumed = _res(p, t[model], "480p")
    if res is None:
        return None
    d, a, basis = _duration(p, 5)
    return _r(math.floor(round(d * t[model][res], 9)), "credits_per_second", t[model][res], d, basis,
              {"resolution": res}, {**assumed, **a})


def what_if_v1(p: dict) -> Optional[dict]:
    s, e = _num(p.get("seconds")), _num(p.get("episodes"))
    if s is None or e is None:
        return None
    return _r(63 * s * e / 60, "credits_per_second", 63 / 60, s * e, f"seconds={s:g} x episodes={e:g}")


# lipsync / speak (§4.12)
def hf_speak_v2(p: dict) -> dict:
    d, a, basis = _duration(p, 5)
    high = str(p.get("quality") or "mid") == "high"
    c = math.ceil(round(max(22, 4.4 * d), 9)) if high else math.ceil(round(max(14, 2.8 * d), 9))
    return _r(c, "credits_per_second", 4.4 if high else 2.8, d, basis, {}, a)


def wan2_5_speak(p: dict) -> Optional[dict]:
    fast = "fast" in str(p.get("model") or "")
    return per_second({"720p": 1.8, "1080p": 2.5} if fast else {"480p": 1.25, "720p": 2.5, "1080p": 4},
                      default_res="720p" if fast else "480p")(p)


def infinite_talk(p: dict) -> dict:
    rate = 12 if str(p.get("quality") or "") == "high" else 3
    return per_second(None, rate)(p)


def kling_speak(p: dict) -> dict:
    rate = 2 if str(p.get("quality") or "mid") == "high" else 1
    return per_second(None, rate, minimum_d=2)(p)


def kling2_6_lipsync(p: dict) -> dict:
    d, a, basis = _duration(p, 5)
    return _r(10 if d == 5 else 20, "credits_per_generation", None, 1, basis, {}, a)


def kling_lipsync(p: dict) -> dict:
    d, a, basis = _duration(p, 5)
    return _r(math.ceil(d / 5) * 5 * 0.25, "credits_per_second", 0.25, math.ceil(d / 5) * 5, basis, {}, a)


def veo_speak(p: dict) -> dict:
    fast = "fast" in str(p.get("model") or "")
    return _r(22 if fast else 58, "credits_per_generation", None, 1, "fixed (veo speak)")


SOUL = per_image(0.125)
STATIC: dict[str, Callable[[dict], Optional[dict]]] = {
    # images (§4.10)
    "text2image_soul_v2": SOUL, "soul_cinematic": SOUL, "text2image_soul": SOUL,
    "cinematic_studio_soul_cast": SOUL, "cinematic_studio_soul_location": SOUL, "soul_cinema_studio": SOUL,
    "nano_banana_2": per_image_by({"1k": 2, "2k": 2, "4k": 4}, "1k"),
    "nano_banana": per_image(1), "nano_banana_2_lite": per_image(1),
    "nano_banana_flash": per_image_by({"1k": 1.5, "2k": 2, "4k": 3}, "1k"),
    "nano_banana_2_upscale": per_image_by({"2k": 2, "4k": 4}, "2k", batch=False),
    "seedream": per_image(1), "seedream_v4_5": per_image(1), "seedream_v5_lite": per_image(1),
    "flux_2": flux_2,
    "flux_3_image": per_image_by({"768sq": 1, "1k": 2, "1.5k": 2, "2k": 3, "4k": 19}, "768sq"),
    "flux_kontext": per_image(1.5, default_batch=2),
    "image_auto": per_image_by({"2k": 2, "4k": 4}, "2k"),
    "kling_omni_image": per_image(0.5),
    "openai_hazel": per_image_by({"low": 2, "medium": 4, "high": 6}, "low", ("quality",)),
    "openai_hazel_mini": per_image(1),
    "text2image_gpt": per_image_by({"low": 1, "medium": 2, "high": 5}, "low", ("quality",)),
    "z_image": per_image(0.15),
    "marketing_studio_image": per_image_by({"1k": 2, "2k": 2, "4k": 4}, "1k"),
    "keyframes_faceswap": fixed(2), "character_swap_v2": fixed(2),
    "wan2_2_image": per_image_by({"720p": 0.5, "1080p": 1}, "720p"),
    "recraft_v4_styles": lambda p: per_image(3 if _norm(p.get("resolution") or "") == "2k" else 1)(p),
    # video (§4.3–§4.8)
    "veo3_1": veo3_1, "veo3_1_lite": veo3_1_lite, "sora2_video": sora2_video,
    "kling2_6": kling2_6, "kling2_6_motion_control": kling2_6_motion_control,
    "kling_omni_flf": kling_omni_video, "kling_omni_image_reference": kling_omni_video,
    "kling_3_unlimited": fixed(0), "seedance_unlimited": fixed(0), "seedance_2_unlimited": fixed(0),
    "seedance_mini_unlimited": per_second({"480p": 1, "720p": 2.5}, default_d=4, default_res="480p", batch=True),
    "minimax_h3": minimax_h3, "minimax_h3_max": minimax_h3, "minimax_hailuo": minimax_hailuo,
    "wan2_6": lambda p: per_second(None, 4 if _norm(p.get("resolution") or "") == "1080p" else 2.5)(p),
    "wan2_7": lambda p: per_second(None, 2.5 if _norm(p.get("resolution") or "") == "1080p" else 1.5)(p),
    "wan2_5_video": wan2_5_video,
    "gemini_omni_flash_1_1": per_second({"360p": 1, "720p": 3, "1080p": 4.5, "4k": 9}, default_d=8,
                                        default_res="360p", batch=True),
    "grok_video": per_second(None, 1.5),
    "seedance1_5": seedance1_5, "seedance": seedance_1,
    "hf_fnf_video": per_second(None, 6, default_d=15),
    "marketing_studio_hook": fixed(20),
    "what_if_v1": what_if_v1,
    "image2video": image2video, "image2video_mix": image2video,
    # lipsync / speak (§4.12)
    "hf_speak_v2": hf_speak_v2, "wan2_5_speak": wan2_5_speak, "infinite_talk": infinite_talk,
    "kling_speak": kling_speak, "kling2_6_lipsync": kling2_6_lipsync, "kling_lipsync": kling_lipsync,
    "sync_so": per_second(None, 3), "hummingbird": fixed(1),
    "veo3_speak": veo_speak, "veo3_1_speak": veo_speak,
}

__all__ = ["STATIC", "SOURCE"]
