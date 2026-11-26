"""Generate the cost appendices of docs/COST_FORMULAS.md from a pricing run.

Two outputs, each written between its own markers in the doc:

* rate tables (default): every model in ``output/json/models.json`` -> one Markdown table of its price points
  (dimensions -> credits per unit -> example credits -> ~USD at plus:annual).
  Markers: ``<!-- BEGIN cost-tables -->`` / ``<!-- END cost-tables -->``.
* ``--variations``: one row per realistic option combination per model, with the credit equation written out the
  way the web client computes it (see docs/COST_FORMULAS.md section 4), and ~USD at plus:annual and ultra:annual.
  Markers: ``<!-- BEGIN cost-variations -->`` / ``<!-- END cost-variations -->``.

Usage:
    python scripts/gen_cost_tables.py                       # latest run with output/json/models.json -> stdout
    python scripts/gen_cost_tables.py --run runs/<id>       # a specific run
    python scripts/gen_cost_tables.py --costs tests/fixtures/raw/job_costs.json   # raw /job-sets/costs body
    python scripts/gen_cost_tables.py --variations          # the variations tables instead
    python scripts/gen_cost_tables.py --write docs/COST_FORMULAS.md [--variations]   # replace between markers

Pure offline: reads files only, never calls the network.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from higgsfield_scraper.parsers.costs import parse_job_costs  # noqa: E402

TABLE_MARKERS = ("<!-- BEGIN cost-tables -->", "<!-- END cost-tables -->")
VARIATION_MARKERS = ("<!-- BEGIN cost-variations -->", "<!-- END cost-variations -->")
#: USD per credit used when the run has no credit_values.json (ps_a3, 2026-11-26, after-offer, lowest tier).
DEFAULT_USD = {"plus:annual": Decimal("0.0250"), "ultra:annual": Decimal("0.0150")}
RES_ORDER = ["360p", "480p", "512", "720p", "768p", "768", "1080p", "1080", "1k", "1.5k", "2k", "4k", "8k"]


# ============================================================================================ loading
def find_pricing_run(runs_root: Path = ROOT / "runs") -> Optional[Path]:
    """Newest run folder that has output/json/models.json (site/community runs are skipped)."""
    if not runs_root.exists():
        return None
    for d in sorted((p for p in runs_root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        if (d / "output" / "json" / "models.json").exists():
            return d
    return None


def models_from_costs_body(body: dict) -> list[dict]:
    """Raw /job-sets/costs JSON (bare body or the {meta, body} envelope) -> parsed model dicts."""
    if "body" in body and isinstance(body["body"], dict):
        body = body["body"]
    prov = {"endpoint": "job_costs", "url": "", "params": {}, "fetched_at": None}
    return parse_job_costs(body, prov)


def load_models(run: Optional[Path] = None, costs: Optional[Path] = None) -> list[dict]:
    if costs:
        return models_from_costs_body(json.loads(Path(costs).read_text(encoding="utf-8")))
    run = run or find_pricing_run()
    if run is None:
        raise SystemExit("no pricing run with output/json/models.json found; pass --run or --costs")
    return json.loads((Path(run) / "output" / "json" / "models.json").read_text(encoding="utf-8"))


def load_usd(run: Optional[Path] = None) -> dict[str, Decimal]:
    """{'plus:annual': rate, 'ultra:annual': rate} from the run's credit_values.json (lowest credit tier)."""
    usd = dict(DEFAULT_USD)
    path = Path(run) / "output" / "json" / "credit_values.json" if run else None
    if path and path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
        for key in list(usd):
            ptype, period = key.split(":")
            cands = sorted((r for r in rows if r["plan_type"] == ptype and r["billing_period"] == period),
                           key=lambda r: r["credits_per_month"])
            if cands and cands[0].get("usd_per_credit_after_offer"):
                usd[key] = Decimal(str(cands[0]["usd_per_credit_after_offer"]))
    return usd


# ============================================================================================ number helpers
def D(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def fmt(x: Any) -> str:
    if x is None:
        return "–"
    d = D(x)
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def ceil_int(x: Decimal) -> Decimal:
    return x.to_integral_value(rounding=ROUND_CEILING)


def floor_int(x: Decimal) -> Decimal:
    return x.to_integral_value(rounding=ROUND_FLOOR)


def ceil_cent(x: Decimal) -> Decimal:
    """JS Es(): Math.ceil(Number((x*100).toFixed(6)))/100 — round UP to 0.01 credit (= 1 cost unit)."""
    return (x * 100).to_integral_value(rounding=ROUND_CEILING) / 100


def usd(credits: Optional[Decimal], rate: Decimal) -> str:
    if credits is None:
        return "–"
    v = (D(credits) * rate).quantize(Decimal("0.0001"))
    return f"${v}"


def res_key(r: Any) -> tuple:
    s = str(r)
    return (RES_ORDER.index(s) if s in RES_ORDER else 99, s)


def esc(s: Any) -> str:
    return str(s).replace("|", "\\|")


# ============================================================================================ rate tables
def rate_tables(models: list[dict], usd_rates: dict[str, Decimal]) -> str:
    """Markdown: one table per model with every price point."""
    rate = usd_rates.get("plus:annual", DEFAULT_USD["plus:annual"])
    out = [f"_Generated by `scripts/gen_cost_tables.py` from `/job-sets/costs` "
           f"(version `{(models[0].get('costs_version') or '?')[:12] if models else '?'}`). "
           f"USD = example credits × ${rate}/credit (plus:annual after offer)._", ""]
    priced = [m for m in models if m.get("price_points")]
    unpriced = sorted(m["model_id"] for m in models if not m.get("price_points"))
    for m in sorted(priced, key=lambda m: (m.get("category") or "", m["model_id"])):
        out.append(f"#### `{m['model_id']}` — {m.get('display_name', '')} ({m.get('category')}, "
                   f"{', '.join(m.get('units') or [])})")
        out.append("")
        out.append("| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |")
        out.append("|---|---|---|---:|---:|---|---:|")
        pts = sorted(m["price_points"], key=lambda p: (p.get("component") or "",
                                                       res_key(p["dimensions"].get("resolution", "")),
                                                       json.dumps(p["dimensions"], sort_keys=True, default=str)))
        for p in pts:
            dims = ", ".join(f"{k}={v}" for k, v in p["dimensions"].items()) or "—"
            ex = p.get("example")
            if ex:
                qty = ", ".join(f"{k}={v}" for k, v in ex.items() if k != "credits")
                ex_s = f"{qty} → {fmt(ex['credits'])}"
                ex_c = D(ex["credits"])
            elif p.get("credits") is not None:
                ex_s, ex_c = f"1 → {fmt(p['credits'])}", D(p["credits"])
            else:
                ex_s, ex_c = "formula", None
            orig = p.get("original_credits")
            orig_s = fmt(orig) if orig is not None and orig != p.get("credits") else ""
            out.append(f"| {esc(dims)} | {p.get('component') or ''} | {p['unit']} | {fmt(p.get('credits'))} | "
                       f"{orig_s} | {esc(ex_s)} | {usd(ex_c, rate)} |")
        out.append("")
    if unpriced:
        out.append("**In plans but not in `/job-sets/costs`** (priced in JS or covered by unlimited): "
                   + ", ".join(f"`{u}`" for u in unpriced))
        out.append("")
    return "\n".join(out)


# ============================================================================================ variations
class Row(dict):
    """resolution, duration, aspect, quality, audio, ref_video, batch, mode, equation, credits"""


def _pts(m: dict, component: Optional[str] = None, unit: Optional[str] = None) -> list[dict]:
    return [p for p in m["price_points"] if p.get("component") == component
            and (unit is None or p["unit"] == unit) and p.get("credits") is not None]


def _find(m: dict, component: Optional[str] = None, unit: Optional[str] = None, **dims: Any) -> Optional[dict]:
    for p in _pts(m, component, unit):
        if all(str(p["dimensions"].get(k)) == str(v) for k, v in dims.items()):
            return p
    return None


def _opts(m: dict, dim: str, component: Optional[str] = None) -> list:
    vals = []
    for p in _pts(m, component):
        v = p["dimensions"].get(dim)
        if v is not None and v not in vals:
            vals.append(v)
    return sorted(vals, key=res_key) if dim == "resolution" else vals


def row(**kw: Any) -> Row:
    base = dict(resolution="–", duration="–", aspect="any", quality="–", audio="–", ref_video="no",
                batch=1, mode="generate", equation="", credits=None)
    base.update(kw)
    return Row(base)


#: how a per-second price becomes credits, keyed by style (see doc §4)
def per_second(style: str, dur: Decimal, cps: Decimal, batch: int) -> tuple[str, Decimal]:
    d, c, b = fmt(dur), fmt(cps), batch
    if style == "ceil_batch":          # Math.ceil(d × cps) × max(1, batch)
        v = ceil_int(dur * cps) * b
        return (f"ceil({d} × {c}) × {b} = {fmt(v)}" if b != 1 else f"ceil({d} × {c}) = {fmt(v)}"), v
    if style == "ceil_total":          # Math.ceil(d × cps × batch)
        v = ceil_int(dur * cps * b)
        return (f"ceil({d} × {c} × {b}) = {fmt(v)}" if b != 1 else f"ceil({d} × {c}) = {fmt(v)}"), v
    if style == "ceil_dur":            # Math.ceil(d) × cps × batch
        v = ceil_int(dur) * cps * b
        return f"ceil({d}) × {c}" + (f" × {b}" if b != 1 else "") + f" = {fmt(v)}", v
    if style == "plain_batch":         # d × cps × batch
        v = dur * cps * b
        return f"{d} × {c}" + (f" × {b}" if b != 1 else "") + f" = {fmt(v)}", v
    if style == "plain":               # d × cps (no batch in the client formula)
        v = dur * cps
        return f"{d} × {c} = {fmt(v)}", v
    if style == "cent":                # Es(d × cps): ceil to 0.01
        v = ceil_cent(dur * cps)
        return f"ceil₀.₀₁({d} × {c}) = {fmt(v)}", v
    raise ValueError(style)


#: video_input-split models (Seedance-shaped rows): style, durations, has batch, JS evidence level
VIDEO_INPUT_STYLE: dict[str, tuple[str, list[int], bool, str]] = {
    "seedance_2_5": ("ceil_batch", [4, 5, 10, 15, 30], True, "JS"),
    "seedance_2_5_flash": ("ceil_batch", [4, 5, 10, 15, 30], True, "JS"),
    "cinematic_studio_video_4_0": ("ceil_batch", [4, 5, 10, 15, 30], True, "JS"),
    "wan3_0": ("cent", [2, 5, 10, 15, 30], False, "JS"),
    "wan3_0_prime": ("cent", [2, 5, 10, 15, 30], False, "JS"),
    "kling4_0": ("plain", [3, 5, 10, 15], False, "JS"),
    "kling_4_0_flash": ("plain", [3, 5, 10, 15], False, "JS"),
    "flux_3_video": ("plain", [5, 10, 15], False, "JS"),
}
#: resolution-only per-second models: style, durations, has batch, evidence
PER_SECOND_STYLE: dict[str, tuple[str, list[int], bool, str]] = {
    "happy_horse_video": ("ceil_batch", [5, 10, 15], True, "JS"),
    "gemini_omni": ("ceil_batch", [3, 8, 10], True, "JS"),
    "gemini_omni_flash_1_2": ("plain_batch", [3, 8, 15], True, "JS"),
    "minimax_h3_highspeed": ("plain_batch", [5, 10, 15], True, "JS"),
    "minimax_h3_lite": ("plain_batch", [5, 10, 15], True, "JS"),
    "grok_video_v15": ("plain", [1, 5, 10, 15], False, "JS"),
    "grok_video_v15_lite": ("plain", [1, 5, 10, 15], False, "JS"),
    "kling3_0_turbo": ("plain", [3, 5, 10, 15], False, "JS"),
    "hf_mult_motion_control": ("ceil_dur", [3, 5.4, 10, 30], True, "JS"),
    "hf_mult_motion_control_flash": ("ceil_dur", [3, 5.4, 10, 30], True, "JS"),
    "hf_mult_replace_object": ("ceil_dur", [4, 10, 30], True, "JS"),
    "hf_mult_replace_object_flash": ("ceil_dur", [4, 10, 30], True, "JS"),
    "ai_influencer_motion_control": ("ceil_dur", [4, 10, 30], True, "JS"),
    "ai_influencer_motion_control_flash": ("ceil_dur", [4, 10, 30], True, "JS"),
    "ai_influencer_replace_object": ("ceil_dur", [4, 10, 30], True, "JS"),
    "ai_influencer_replace_object_flash": ("ceil_dur", [4, 10, 30], True, "JS"),
    "videoshop_genjutsu": ("ceil_dur", [4, 10, 30], True, "inferred"),
    "cinematic_studio_3_0": ("plain_batch", [4, 10, 15], True, "JS"),
    "cinematic_studio_video_3_5": ("plain_batch", [4, 10, 15], True, "JS"),
    "marketing_studio_video": ("ceil_total", [4, 10, 15], True, "JS"),
    "seedance_2_0_mini": ("ceil_batch", [4, 10, 15], True, "JS"),
    "seedance_2_5_kling_upscale": ("ceil_batch", [5, 10, 15], False, "JS"),
    "hf_evolution": ("ceil_batch", [5, 10], False, "inferred"),
    "ai_host_video": ("ceil_batch", [5, 10, 30], False, "inferred"),
    "ad_multiplier_replace": ("ceil_batch", [5, 10], False, "inferred"),
    "cinematic_video_editor": ("ceil_batch", [5, 10], False, "inferred"),
}


def gen_video_input(m: dict, style: str, durations: list, batch_ok: bool, ev: str) -> list[Row]:
    mid, rows = m["model_id"], []
    hdr = "video_hdr" in (m.get("options") or {})
    for res in _opts(m, "resolution"):
        for ref in ("without_video", "with_video"):
            p = _find(m, None, "credits_per_second", resolution=res, video_input=ref)
            if p is None:
                continue
            for dur in durations:
                eq, v = per_second(style, D(dur), D(p["credits"]), 1)
                rows.append(row(resolution=res, duration=f"{dur} s", ref_video="yes" if ref == "with_video" else "no",
                                audio="on/off (same price)" if mid.startswith("seedance") else "–",
                                quality="SDR" if hdr else "–", equation=eq, credits=v))
            if hdr:
                ph = _find(m, None, "credits_per_second", resolution=res, video_hdr=ref)
                if ph is not None:
                    eq, v = per_second(style, D(10), D(ph["credits"]), 1)
                    rows.append(row(resolution=res, duration="10 s", ref_video="yes" if ref == "with_video" else "no",
                                    quality="HDR", equation=eq, credits=v))
    if batch_ok:
        for res in _opts(m, "resolution"):
            p = _find(m, None, "credits_per_second", resolution=res, video_input="without_video")
            if p:
                eq, v = per_second(style, D(10), D(p["credits"]), 4)
                rows.append(row(resolution=res, duration="10 s", batch=4, equation=eq, credits=v))
    for res in _opts(m, "resolution", "video_edit"):
        p = _find(m, "video_edit", None, resolution=res)
        if p:
            src = 12
            dur = min(30, max(4, src)) if mid.startswith("seedance") else src
            eq, v = per_second(style, D(dur), D(p["credits"]), 1)
            rows.append(row(resolution=res, duration=f"{src} s source", ref_video="yes (source)", mode="edit",
                            equation=eq.replace(f"ceil({dur} ", f"ceil(clamp4..30({src}) ") if dur != src else eq,
                            credits=v))
    if mid in ("seedance_2_5", "seedance_2_5_flash"):
        for res in _opts(m, "resolution")[:2]:
            p = _find(m, None, "credits_per_second", resolution=res, video_input="with_video")
            if p:
                eq, v = per_second(style, D(10), D(p["credits"]), 1)
                rows.append(row(resolution=res, duration="10 s added", ref_video="yes (source)",
                                mode="extend forward", equation=eq, credits=v))
    if mid == "seedance_2_5":
        p = _find(m, None, "credits_per_second", resolution="480p", video_input="without_video")
        if p:
            for dur in (5, 10, 15):
                eq, v = per_second(style, D(dur), D(p["credits"]), 1)
                rows.append(row(resolution="480p (forced)", duration=f"{dur} s", mode="draft", equation=eq, credits=v))
    if mid == "videoshop_relight":
        p = _find(m, None, "credits_per_generation") or _find(m, None, "credits_per_image")
        if p:
            rows.append(row(mode="image relight", equation=f"image_credits = {fmt(p['credits'])}",
                            credits=D(p["credits"])))
    return rows


def gen_per_second(m: dict, style: str, durations: list, batch_ok: bool, ev: str) -> list[Row]:
    rows = []
    dims = [k for k in (m.get("options") or {}) if k not in ("resolution",)]
    for p in sorted(_pts(m, None, "credits_per_second"), key=lambda p: (res_key(p["dimensions"].get("resolution", "")),
                                                                        json.dumps(p["dimensions"], default=str))):
        res = p["dimensions"].get("resolution", "–")
        qual = ", ".join(f"{k}={p['dimensions'][k]}" for k in dims if k in p["dimensions"]) or "–"
        for dur in durations:
            eq, v = per_second(style, D(dur), D(p["credits"]), 1)
            rows.append(row(resolution=res, duration=f"{dur} s", quality=qual, equation=eq, credits=v))
        if batch_ok:
            eq, v = per_second(style, D(durations[-1]), D(p["credits"]), 4)
            rows.append(row(resolution=res, duration=f"{durations[-1]} s", quality=qual, batch=4, equation=eq,
                            credits=v))
    for p in _pts(m, "video_edit", "credits_per_second"):
        eq, v = per_second(style, D(12), D(p["credits"]), 1)
        rows.append(row(resolution=p["dimensions"].get("resolution", "–"), duration="12 s source",
                        ref_video="yes (source)", mode="edit", equation=eq, credits=v))
    return rows


def gen_seedance_2_0(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        res, model = p["dimensions"].get("resolution"), p["dimensions"].get("model")
        for dur in (4, 10, 15):
            eq, v = per_second("ceil_batch", D(dur), D(p["credits"]), 1)
            rows.append(row(resolution=res, duration=f"{dur} s", quality=model, equation=eq, credits=v))
        eq, v = per_second("ceil_batch", D(15), D(p["credits"]), 4)
        rows.append(row(resolution=res, duration="15 s", quality=model, batch=4, equation=eq, credits=v))
    return rows


def gen_mode_audio(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        mode, audio = p["dimensions"].get("mode"), p["dimensions"].get("audio")
        for dur in (3, 5, 10, 15):
            eq, v = per_second("plain", D(dur), D(p["credits"]), 1)
            rows.append(row(duration=f"{dur} s", quality=f"mode={mode}", audio=audio, equation=eq, credits=v))
    return rows


def gen_mode_cps(m: dict) -> list[Row]:      # kling3_0_motion_control: ceil(rate × d + (chain ? 2 : 0))
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        mode = p["dimensions"].get("mode")
        for dur in (3, 5.5, 10, 30):
            v = ceil_int(D(p["credits"]) * D(dur))
            rows.append(row(duration=f"{fmt(dur)} s (driving video)", quality=f"mode={mode}", ref_video="yes",
                            equation=f"ceil({fmt(p['credits'])} × {fmt(dur)}) = {fmt(v)}", credits=v))
        v = ceil_int(D(p["credits"]) * 10 + 2)
        rows.append(row(duration="10 s (driving video)", quality=f"mode={mode}", ref_video="yes", mode="chain",
                        equation=f"ceil({fmt(p['credits'])} × 10 + 2) = {fmt(v)}", credits=v))
    return rows


def gen_images(m: dict) -> list[Row]:
    mid, rows = m["model_id"], []
    gpt = mid.startswith("gpt_image")
    for p in sorted(_pts(m, None, "credits_per_generation"),
                    key=lambda p: (str(p["dimensions"].get("model", "")), res_key(p["dimensions"].get("resolution", "")),
                                   str(p["dimensions"].get("quality", "")))):
        dims = dict(p["dimensions"])
        res = dims.pop("resolution", "–")
        qual = ", ".join(f"{k}={v}" for k, v in dims.items()) or "–"
        c = D(p["credits"])
        batches = (1,) if (mid in ("gif",) or dims.get("operation") == "vectorize") else (1, 4)
        for b in batches:
            if gpt:
                v = ceil_cent(c * b)
                eq = f"ceil₀.₀₁({b} × {fmt(c)}) = {fmt(v)}"
            else:
                v = c * b
                eq = f"{b} × {fmt(c)} = {fmt(v)}"
            orig = p.get("original_credits")
            if orig is not None and D(orig) > c:
                eq += f" (was {fmt(D(orig) * b)})"
            rows.append(row(resolution=res, quality=qual, batch=b, equation=eq, credits=v))
    return rows


def gen_flux_upscale(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        d = p["dimensions"]
        v = ceil_cent(D(p["credits"]) * 10)
        rows.append(row(resolution=f"{d.get('source_resolution')} → {d.get('resolution')}", duration="10 s source",
                        quality=f"creativity={d.get('creativity')}", ref_video="yes (source)", mode="upscale",
                        equation=f"ceil₀.₀₁({fmt(p['credits'])} × 10) = {fmt(v)}", credits=v))
    return rows


def gen_fps_boost(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        d = p["dimensions"]
        v = ceil_cent(D(p["credits"]) * 10)
        rows.append(row(resolution=f"{d.get('source_resolution')}", duration="10 s source",
                        quality=f"{d.get('model')} {d.get('input_fps')}→{d.get('output_fps')} fps",
                        ref_video="yes (source)", mode="fps boost",
                        equation=f"ceil₀.₀₁({fmt(p['credits'])} × 10) = {fmt(v)} (rounding inferred)", credits=v))
    return rows


def gen_frames(m: dict) -> list[Row]:     # topaz_hyperion_2_5, sam_3_video, depth_anything_video
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        ref_fps = p["attributes"].get("reference_fps") or 24
        res = p["dimensions"].get("resolution", "–")
        for secs, fps in ((10, 24), (10, 30), (10, 60)):
            frames = secs * fps
            if p["attributes"].get("max_frames"):
                frames = min(frames, int(p["attributes"]["max_frames"]))
                v = ceil_cent(D(frames) / D(fps) * D(p["credits"]))
                eq = f"ceil₀.₀₁({frames} frames / {fps} fps × {fmt(p['credits'])}) = {fmt(v)}"
            else:
                v = ceil_cent(D(frames) * D(p["credits"]) / D(ref_fps))
                eq = f"ceil₀.₀₁({frames} frames × {fmt(p['credits'])} / {ref_fps}) = {fmt(v)}"
            rows.append(row(resolution=res, duration=f"{secs} s @ {fps} fps", ref_video="yes (source)",
                            mode="process video", equation=eq, credits=v))
    return rows


def gen_reframe(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        res = p["dimensions"].get("resolution")
        img = _find(m, None, "credits_per_image", resolution=res)
        ic = D(img["credits"]) if img else D(2)
        for dur in (5, 10, 15, 30, 60):
            segs = 1 if dur <= 15.25 else math.ceil((dur - 0.25) / 15)
            n_img = 2 * segs + 1 if segs > 1 else 3
            v = ceil_int(floor_int(D(dur) + D("0.5")) * D(p["credits"]) + n_img * ic)
            rows.append(row(resolution=res, duration=f"{dur} s source", ref_video="yes (source)", mode="reframe",
                            equation=f"ceil({dur} × {fmt(p['credits'])} + {n_img} × {fmt(ic)}) = {fmt(v)}", credits=v))
    return rows


def gen_frame_addon(m: dict) -> list[Row]:  # draw_to_video / swap_object / remove_object
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        res = p["dimensions"].get("resolution")
        fr = _find(m, None, "credits_per_frame", resolution=res)
        fc = D(fr["credits"]) if fr else D(0)
        for dur in (5, 10):
            v = ceil_int(D(dur) * D(p["credits"])) + fc
            rows.append(row(resolution=res, duration=f"{dur} s", ref_video="yes (source)",
                            equation=f"ceil({dur} × {fmt(p['credits'])}) + 1 × {fmt(fc)} = {fmt(v)} (inferred)",
                            credits=v))
    return rows


def gen_scene_switch(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None, "credits_per_second"):
        d = p["dimensions"]
        run = D(d.get("cost_per_run") or 0)
        for dur in (5, 10):
            v = D(dur) * D(p["credits"]) + run
            rows.append(row(resolution=d.get("resolution"), duration=f"{dur} s", quality=f"tier={d.get('tier')}",
                            equation=f"{dur} × {fmt(p['credits'])} + {fmt(run)} per run = {fmt(v)} (no JS; inferred)",
                            credits=v))
    return rows


TEXTS = (("short line (60 chars)", 60), ("paragraph (400 chars)", 400), ("page (2,000 chars)", 2000))


def gen_char_blocks(m: dict) -> list[Row]:
    rows = []
    mid = m["model_id"]
    for p in _pts(m, None):
        if not p["unit"].startswith("credits_per_") or not p["unit"].endswith("_characters"):
            continue
        n = int(p["unit"].split("_")[2])
        c = D(p["credits"])
        model = p["dimensions"].get("model", mid)
        for label, chars in TEXTS:
            blocks = math.ceil(chars / n)
            for b in ((1, 4) if mid.startswith("elevenlabs") else (1,)):
                v = (D(blocks) * c * b).quantize(Decimal("0.01"))
                eq = f"ceil({chars}/{n}) × {fmt(c)}" + (f" × {b}" if b != 1 else "") + f" = {fmt(v)}"
                rows.append(row(quality=f"model={model}", duration=label, batch=b, mode="TTS", equation=eq, credits=v))
    return rows


def gen_seed_audio(m: dict) -> list[Row]:
    p = (_pts(m, None) or [None])[0]
    if not p:
        return []
    f = (p.get("formula") or {}).get("params", {})
    cps = int(f.get("characters_per_second", 15))
    lo, hi = int(f.get("minimum_seconds", 1)), int(f.get("maximum_seconds", 120))
    rows = []
    for label, chars in TEXTS:
        secs = min(max(math.ceil(chars / cps), lo), hi)
        v = D(secs) * D(p["credits"])
        rows.append(row(duration=label, mode="TTS", equation=f"clamp(ceil({chars}/{cps}), {lo}, {hi}) × "
                                                                  f"{fmt(p['credits'])} = {fmt(v)}", credits=v))
    return rows


def gen_qwen(m: dict) -> list[Row]:
    p = (_pts(m, None) or [None])[0]
    if not p:
        return []
    f = (p.get("formula") or {}).get("params", {})
    num, den = int(f.get("cost_units_numerator", 3)), int(f.get("cost_units_denominator", 70))
    mn, cpc = int(f.get("minimum_cost_units", 1)), int(f.get("cost_units_per_credit", 100))
    rows = []
    for label, chars in TEXTS:
        units = max(mn, math.ceil(chars * num / den))
        v = D(units) / cpc
        rows.append(row(duration=label, mode="TTS", equation=f"max({mn}, ceil({chars} × {num}/{den})) / {cpc} = {fmt(v)}",
                        credits=v))
    return rows


def gen_input_duration(m: dict) -> list[Row]:   # voice_change_merge, audio_dubbing, dubbing_lipsync, video_to_music
    rows = []
    mid = m["model_id"]
    for p in _pts(m, None):
        f = (p.get("formula") or {}).get("params", {})
        c = D(p["credits"])
        dims = ", ".join(f"{k}={v}" for k, v in p["dimensions"].items()) or "–"
        for secs in (8.5, 30, 90):
            if p["unit"] == "credits_per_minute":
                mins = math.ceil(secs / 60)
                v = D(mins) * c
                eq = f"ceil({secs}/60) × {fmt(c)} = {fmt(v)}"
            elif f.get("duration_rounding") == "floor":
                v = ceil_int(floor_int(D(secs)) * c)
                eq = f"ceil(floor({secs}) × {fmt(c)}) = {fmt(v)}"
            else:
                v = ceil_cent(D(secs) * c)
                eq = f"ceil₀.₀₁({secs} × {fmt(c)}) = {fmt(v)}"
            rows.append(row(duration=f"{secs} s input", quality=dims, ref_video="audio/video input", mode=mid,
                            equation=eq, credits=v))
    return rows


def gen_blocks_seconds(m: dict) -> list[Row]:   # youtube_faceless_video
    rows = []
    for p in _pts(m, None):
        if not p["unit"].endswith("_seconds"):
            continue
        n = int(p["unit"].split("_")[2])
        for secs in (30, 60, 95):
            v = D(math.ceil(secs / n)) * D(p["credits"])
            rows.append(row(duration=f"{secs} s", quality=", ".join(f"{k}={v2}" for k, v2 in p["dimensions"].items()),
                            equation=f"ceil({secs}/{n}) × {fmt(p['credits'])} = {fmt(v)}", credits=v))
    return rows


def gen_default(m: dict) -> list[Row]:
    rows = []
    for p in _pts(m, None) + [p for c in (m.get("components") or []) for p in _pts(m, c)]:
        ex = p.get("example") or {}
        v = D(ex["credits"]) if ex.get("credits") is not None else D(p["credits"])
        qty = ", ".join(f"{k}={x}" for k, x in ex.items() if k != "credits") or "1"
        rows.append(row(resolution=p["dimensions"].get("resolution", "–"),
                        quality=", ".join(f"{k}={x}" for k, x in p["dimensions"].items() if k != "resolution") or "–",
                        mode=p.get("component") or "generate",
                        equation=f"{fmt(p['credits'])} {p['unit']} × {qty} = {fmt(v)} (generic)", credits=v))
    return rows


def generator_for(m: dict) -> tuple[Callable[[dict], list[Row]], str]:
    mid, units = m["model_id"], set(m.get("units") or [])
    opts = m.get("options") or {}
    if mid in VIDEO_INPUT_STYLE:
        s, durs, b, ev = VIDEO_INPUT_STYLE[mid]
        return (lambda mm: gen_video_input(mm, s, durs, b, ev)), f"{ev}: {s}"
    if "video_input" in opts:
        return (lambda mm: gen_video_input(mm, "ceil_batch", [5, 10, 15], False, "inferred")), \
            "inferred: Seedance-style ceil(d × cps)"
    if mid in PER_SECOND_STYLE:
        s, durs, b, ev = PER_SECOND_STYLE[mid]
        return (lambda mm: gen_per_second(mm, s, durs, b, ev)), f"{ev}: {s}"
    if mid == "seedance_2_0":
        return gen_seedance_2_0, "JS: ceil_batch"
    if "audio" in opts and "mode" in opts:
        return gen_mode_audio, "JS: d × rate[mode][sound]"
    if mid == "kling3_0_motion_control":
        return gen_mode_cps, "JS: ceil(rate × d [+2 chain])"
    if mid == "flux_video_upscale":
        return gen_flux_upscale, "JS: ceil₀.₀₁"
    if mid == "fps_boost":
        return gen_fps_boost, "inferred"
    if mid in ("topaz_hyperion_2_5", "sam_3_video", "depth_anything_video"):
        return gen_frames, "JS: frames"
    if mid == "reframe":
        return gen_reframe, "JS: reframe"
    if mid in ("draw_to_video", "swap_object", "remove_object"):
        return gen_frame_addon, "inferred"
    if mid == "scene_switch":
        return gen_scene_switch, "inferred (no JS)"
    if mid == "seed_audio":
        return gen_seed_audio, "JS"
    if mid == "qwen_audio_tts":
        return gen_qwen, "JS"
    if any(u.endswith("_characters") for u in units):
        return gen_char_blocks, "JS + live formula"
    if any(u.endswith("_seconds") and u.startswith("credits_per_") and u != "credits_per_second" for u in units):
        return gen_blocks_seconds, "live formula"
    if any((p.get("formula") or {}).get("name", "").startswith("input_duration") for p in m["price_points"]):
        return gen_input_duration, "JS + live formula"
    if units and units <= {"credits_per_generation", "base_credits"}:
        return gen_images, "JS: batch × credits" if not mid.startswith("gpt_image") else "JS: ceil₀.₀₁(batch × credits)"
    return gen_default, "generic"


#: families -> model ids, in doc order (anything not listed goes to "Other")
FAMILIES: list[tuple[str, Iterable[str]]] = [
    ("Seedance 2.5 / Flash", ["seedance_2_5", "seedance_2_5_flash", "seedance_2_5_kling_upscale"]),
    ("Seedance 2.0", ["seedance_2_0", "seedance_2_0_mini"]),
    ("Cinema Studio / Videoshop", ["cinematic_studio_video_4_0", "cinematic_studio_3_0", "cinematic_studio_video_3_5",
                                   "cinematic_video_editor", "cinematic_video_relight", "cinematic_video_inpaint",
                                   "videoshop_edit", "videoshop_relight", "videoshop_camera_move", "videoshop_genjutsu"]),
    ("Kling", ["kling4_0", "kling_4_0_flash", "kling3_0", "kling3_0_turbo", "kling_o3_image_reference", "kling_o3_flf",
               "kling3_0_motion_control", "kling_image_4_0"]),
    ("Wan", ["wan3_0", "wan3_0_prime"]),
    ("MiniMax / Hailuo", ["minimax_h3_highspeed", "minimax_h3_lite", "minimax_h3_image"]),
    ("Gemini Omni / Grok / Happy Horse / Flux video", ["gemini_omni", "gemini_omni_flash_1_2", "grok_video_v15",
                                                       "grok_video_v15_lite", "happy_horse_video", "flux_3_video"]),
    ("Higgsfield Genjutsu / AI Influencer (motion control, replace object)",
     ["hf_mult_motion_control", "hf_mult_motion_control_flash", "hf_mult_replace_object", "hf_mult_replace_object_flash",
      "ai_influencer_motion_control", "ai_influencer_motion_control_flash", "ai_influencer_replace_object",
      "ai_influencer_replace_object_flash", "hf_evolution"]),
    ("GPT Image", ["gpt_image_2", "gpt_image_2_5", "gpt_image_2_6", "gpt_image_2_6_flare"]),
    ("Nano Banana / Seedream / other image", ["nano_banana_2_1", "seedream_v5_pro", "seedream_5_5", "seedream_5_0_flash",
                                              "3d_jutsu_angles", "recraft_v4_1", "ideogram_4_6", "ideogram_4_6_precise_edit",
                                              "ideogram_4_5", "ideogram_4_5_precise_edit", "ideogram_vector",
                                              "p_image_ideogram", "gif"]),
    ("Upscale / video tools", ["flux_video_upscale", "fps_boost", "topaz_hyperion_2_5", "sam_3_video",
                               "depth_anything_video", "reframe", "draw_to_video", "swap_object", "remove_object"]),
    ("Audio / TTS / dubbing", ["elevenlabs_v4", "elevenlabs_v4_turbo", "text2speech_v2", "seed_audio", "qwen_audio_tts",
                               "voice_change_merge", "audio_dubbing", "dubbing_lipsync", "elevenlabs_video_to_music"]),
]


def variations(models: list[dict], usd_rates: dict[str, Decimal], only: Optional[set[str]] = None) -> str:
    plus = usd_rates.get("plus:annual", DEFAULT_USD["plus:annual"])
    ultra = usd_rates.get("ultra:annual", DEFAULT_USD["ultra:annual"])
    by_id = {m["model_id"]: m for m in models if m.get("price_points")}
    out = [f"_Generated by `scripts/gen_cost_tables.py --variations` from `/job-sets/costs`. USD = credits × "
           f"${plus} (plus:annual) and × ${ultra} (ultra:annual, 3,000-credit tier), after-offer rates. "
           f"`ceil₀.₀₁` = round up to 0.01 credit (JS `Es()`). Aspect ratio never changes the price. "
           f"Unlimited/free-gen runs cost 0 and are not shown._", ""]
    seen: set[str] = set()
    fams = [(name, [i for i in ids if i in by_id]) for name, ids in FAMILIES]
    rest = sorted(set(by_id) - {i for _, ids in FAMILIES for i in ids})
    fams.append(("Other job types", rest))
    for fam, ids in fams:
        ids = [i for i in ids if (only is None or i in only)]
        if not ids:
            continue
        out += [f"#### {fam}", ""]
        for mid in ids:
            if mid in seen:
                continue
            seen.add(mid)
            m = by_id[mid]
            gen, how = generator_for(m)
            rows = gen(m)
            if not rows:
                continue
            out.append(f"**`{mid}`** — formula: {how}")
            out.append("")
            out.append("| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft "
                       "| equation | credits | ≈USD plus:annual | ≈USD ultra:annual |")
            out.append("|---|---|---|---|---|---|---:|---|---|---:|---:|---:|")
            for r in rows:
                out.append(f"| {esc(r['resolution'])} | {esc(r['duration'])} | {r['aspect']} | {esc(r['quality'])} | "
                           f"{esc(r['audio'])} | {esc(r['ref_video'])} | {r['batch']} | {esc(r['mode'])} | "
                           f"`{esc(r['equation'])}` | {fmt(r['credits'])} | {usd(r['credits'], plus)} | "
                           f"{usd(r['credits'], ultra)} |")
            out.append("")
    return "\n".join(out)


# ============================================================================================ doc writing
def replace_between(text: str, markers: tuple[str, str], body: str) -> str:
    begin, end = markers
    if begin not in text or end not in text:
        return text.rstrip() + f"\n\n{begin}\n{body}\n{end}\n"
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{begin}\n{body}\n{end}{tail}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", type=Path, help="run folder (default: newest run with output/json/models.json)")
    ap.add_argument("--costs", type=Path, help="raw /job-sets/costs JSON instead of a run's models.json")
    ap.add_argument("--variations", action="store_true", help="print the per-model option-variation tables")
    ap.add_argument("--model", action="append", help="limit --variations to these job_set_types")
    ap.add_argument("--write", type=Path, help="replace the marked section of this Markdown file")
    a = ap.parse_args(argv)
    run = None if a.costs else (a.run or find_pricing_run())
    models = load_models(run, a.costs)
    rates = load_usd(run)
    if a.variations:
        body, markers = variations(models, rates, set(a.model) if a.model else None), VARIATION_MARKERS
    else:
        body, markers = rate_tables(models, rates), TABLE_MARKERS
    if a.write:
        a.write.write_text(replace_between(a.write.read_text(encoding="utf-8"), markers, body), encoding="utf-8")
        print(f"wrote {markers[0]} section of {a.write} ({len(body.splitlines())} lines)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
