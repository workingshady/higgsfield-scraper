"""Generate the model catalog table in docs/PRODUCTS.md (between the model-catalog markers).

One row per `job_set_type`, built from:
  * `/job-sets/costs` (samples/higgsfield/model_loading/job_sets_costs.json, or --costs),
  * the latest pricing run's `output/json/models.json` (display name, family, category, min/max credits),
  * optionally the saved JS bundle (samples/higgsfield/js2): `defineJob({type:`x`,output:`y`})` types and the
    adapter route table (`x:`v2/x``). Chunks are read one at a time (the bundle is large).
  * PROVIDERS / PRODUCTS below: small hand-maintained maps (first regex match wins).

Usage:
    python scripts/gen_model_catalog.py                    # print the table
    python scripts/gen_model_catalog.py --write            # replace the block in docs/PRODUCTS.md
    python scripts/gen_model_catalog.py --models runs/<id>/output/json/models.json --js none
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COSTS = ROOT / "samples" / "higgsfield" / "model_loading" / "job_sets_costs.json"
DEFAULT_JS = ROOT / "samples" / "higgsfield" / "js2"
DOC = ROOT / "docs" / "PRODUCTS.md"
BEGIN, END = "<!-- BEGIN model-catalog -->", "<!-- END model-catalog -->"

# (regex on job_set_type, provider, evidence)
#   evidence: "JS" = vendor named in the bundle; "API" = upstream usage / provider model ids seen in API data;
#             "name" = inferred from the model family name only; "in-house" = Higgsfield product, backend not disclosed.
PROVIDERS: list[tuple[str, str, str]] = [
    (r"^(seedance|seedream|bytedance_)", "ByteDance (Seed)", "JS"),
    (r"^seed_audio", "ByteDance (Seed)", "name"),
    (r"^depth_anything", "Depth Anything (ByteDance/HKU, open model)", "name"),
    (r"^kling", "Kuaishou (Kling)", "JS"),
    (r"^(veo|gemini_omni)", "Google (Veo / Gemini)", "JS"),
    (r"^nano_banana", "Google (Gemini image)", "JS+API"),
    (r"^(gpt_image|imagegen|text2image_gpt)", "OpenAI (GPT Image)", "API"),
    (r"^openai_", "OpenAI", "name"),
    (r"^sora", "OpenAI (Sora 2)", "JS"),
    (r"^happy_horse", "Alibaba (HappyHorse)", "JS"),
    (r"^wan", "Alibaba (Wan)", "JS"),
    (r"^qwen", "Alibaba (Qwen)", "name"),
    (r"^z_image", "Alibaba Tongyi (Z-Image)", "name"),
    (r"^minimax", "MiniMax (Hailuo)", "JS"),
    (r"^grok", "xAI (Grok Imagine)", "JS+API"),
    (r"^flux", "Black Forest Labs (FLUX)", "JS"),
    (r"^(ideogram|p_image_ideogram)", "Ideogram", "JS"),
    (r"^recraft", "Recraft", "JS"),
    (r"^elevenlabs", "ElevenLabs", "JS"),
    (r"^(topaz|fps_boost)", "Topaz Labs", "JS"),
    (r"^magi", "Sand AI (MAGI)", "JS"),
    (r"^sam_3", "Meta (SAM 3)", "name"),
    (r"^reve", "Reve", "name"),
    (r"^sync_so", "Sync Labs (sync.)", "name"),
    (r"^infinite_talk", "MeiGen InfiniteTalk (open model)", "name"),
    (r"^text2speech", "multi: MiniMax / ElevenLabs (costs `model` rows)", "API"),
]
IN_HOUSE = "Higgsfield (backend not disclosed)"

# (regex, product list) - first match wins.
PRODUCTS: list[tuple[str, str]] = [
    (r"^nano_banana_2_upscale", "Upscale"),
    (r"^seedance_2_5_kling_upscale", "Upscale (Higgsfield Enhance)"),
    (r"^(seedance|kling(?!_image|_omni_image)|veo|sora|wan(?!2_2_image)|minimax_h3(?!_image)|minimax_hailuo|grok_video|"
     r"gemini_omni|happy_horse|magi|flux_3_video|kling_3_unlimited)", "Video generator"),
    (r"^(gpt_image|imagegen|nano_banana|seedream|flux_(2|3_image|kontext)|ideogram|recraft|grok_image|kling_image|"
     r"kling_omni_image|minimax_h3_image|z_image|image_auto|openai_hazel|reve|wan2_2_image|p_image_ideogram|text2image_gpt|gif)",
     "Image generator"),
    (r"^(text2image_soul|soul_)", "Soul / Soul ID"),
    (r"^cinematic_studio|^soul_cinema_studio|^hf_fnf_video", "Cinema Studio"),
    (r"^cinematic_video_|^videoshop_", "Videoshop / video edit"),
    (r"^(image2video)", "DoP motions (camera presets)"),
    (r"^(hf_mult_|videoshop_genjutsu)", "Genjutsu (motion control / replace object)"),
    (r"^ai_influencer|^restyle", "AI Influencer"),
    (r"^(marketing_studio|ms_image|ad_multiplier)", "Marketing Studio / Ads"),
    (r"^(topaz|bytedance_video_upscale|flux_video_upscale|fps_boost|sam_3|depth_anything)", "Upscale / video tools"),
    (r"^reframe", "Reframe"),
    (r"^viral_hub", "Viral effects"),
    (r"^(elevenlabs|text2speech|qwen_audio|seed_audio|voice_change|audio_dubbing|dubbing_lipsync)", "Audio / TTS / dubbing"),
    (r"^(draw_to_video|swap_object|remove_object)", "Draw to video / object edit"),
    (r"^(youtube_faceless|ai_host)", "Faceless / AI Host studio"),
    (r"^(intone|video_character_asset|hf_evolution|scene_switch|3d_jutsu|what_if|music_cards|katana)", "Other Higgsfield tools"),
    (r"^(character_swap|keyframes_faceswap|video_background_remover)", "Apps"),
]

_DEF_RE = re.compile(r"type:`([a-z0-9_]+)`,output:`([a-z]+)`")
_TITLE_RE = re.compile(r"id:`([a-z0-9_]+)`,(?:badges:\[[^\]]*\],)?title:`([^`]+)`")
_ROUTE_RE = re.compile(r"\b([a-z0-9_]+):`(v2/[a-z0-9_]+|[a-z0-9\-]+/v2|[a-z0-9\-]+)`")


def provider_for(jst: str) -> tuple[str, str]:
    for rx, prov, ev in PROVIDERS:
        if re.search(rx, jst):
            return prov, ev
    return IN_HOUSE, "in-house"


def products_for(jst: str) -> str:
    for rx, prod in PRODUCTS:
        if re.search(rx, jst):
            return prod
    return ""


def version_of(jst: str) -> str:
    # digits glued to letters on the right (text2image, image2video, 3d_jutsu) are not versions
    m = re.search(r"(?<![0-9])(\d+)(?![a-z0-9])(?:_(\d+)(?![a-z]))?(?:_(\d+)(?![a-z]))?",
                  re.split(r"_v(?=\d)", jst, maxsplit=1)[-1])
    if not m:
        return ""
    return ".".join(g for g in m.groups() if g is not None)


def load_costs(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("data", data) if isinstance(data, dict) else data
    return {r["job_set_type"]: r for r in rows}


def latest_models(runs: Path) -> Path | None:
    cands = sorted(runs.glob("*/output/json/models.json"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def load_models(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    return {m["model_id"]: m for m in json.loads(path.read_text(encoding="utf-8"))}


def scan_js(js_dir: Path | None) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Return ({type: output}, {type: route}, {id: picker title}) from the saved bundle, one chunk at a time."""
    defs: dict[str, str] = {}
    routes: dict[str, str] = {}
    titles: dict[str, str] = {}
    if not js_dir or not js_dir.is_dir():
        return defs, routes, titles
    for f in sorted(js_dir.glob("*.js")):
        text = f.read_text(encoding="utf-8", errors="replace")
        for t, out in _DEF_RE.findall(text):
            defs.setdefault(t, out)
        for i_, title in _TITLE_RE.findall(text):
            titles.setdefault(i_, title)
        i = text.find("seedance_2_5:`v2/seedance_2_5`")
        if i != -1:
            start = text.rfind("={", 0, i)
            end = text.find("}", i)
            for k, v in _ROUTE_RE.findall(text[start:end]):
                routes[k] = "/jobs/" + v
        del text
    return defs, routes, titles


def fingerprint(cost) -> tuple:
    """Numbers that make up a price table (ignoring strike-through `original_*`), used to spot identical tables."""
    out: list = []

    def walk(o, key=""):
        if isinstance(o, dict):
            for k in sorted(o):
                if not k.startswith("original"):
                    walk(o[k], k)
        elif isinstance(o, list):
            for x in o:
                walk(x, key)
        elif isinstance(o, (int, float)) and not isinstance(o, bool) and ("cost_per_second" in key or key == "credits"):
            out.append(o)

    walk(cost)
    return tuple(out)


def build_rows(costs: dict, models: dict, defs: dict, routes: dict, titles: dict | None = None) -> list[dict]:
    titles = titles or {}
    ids = sorted(set(costs) | set(models) | set(defs) | set(routes))
    fps: dict[tuple, list[str]] = {}
    for t, r in costs.items():
        fp = fingerprint(r.get("cost"))
        if len(fp) >= 3:
            fps.setdefault(fp, []).append(t)
    rows = []
    for t in ids:
        m = models.get(t, {})
        prov, ev = provider_for(t)
        twins = []
        if t in costs:
            twins = [x for x in fps.get(fingerprint(costs[t].get("cost")), []) if x != t]
        price = ""
        if m.get("has_cost_data"):
            unit = ",".join(m.get("units") or [])
            lo, hi = m.get("min_credits"), m.get("max_credits")
            price = f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"
            price += f" {unit.replace('credits_per_', 'cr/').replace('credits_', 'cr/')}"
        rows.append({
            "job_set_type": t,
            "display_name": m.get("display_name") or titles.get(t, ""),
            "family": m.get("family") or "",
            "version": version_of(t),
            "provider": prov,
            "evidence": ev,
            "media": m.get("category") or defs.get(t, ""),
            "products": products_for(t),
            "in_costs": t in costs,
            "in_js": t in defs or t in routes,
            # types missing from the adapter table fall back to /jobs/<kebab-type> (marked *)
            "route": routes.get(t) or (f"/jobs/{t.replace('_', '-')} *" if t in defs else ""),
            "price": price,
            "same_price_as": ", ".join(sorted(twins)[:4]),
        })
    return rows


def render(rows: list[dict], sources: str) -> str:
    head = ("| job_set_type | display name | family | ver | provider | evidence | media | product(s) | costs | JS | "
            "route | price (live) | same price table as |\n|---|---|---|---|---|---|---|---|:-:|:-:|---|---|---|\n")
    lines = []
    for r in rows:
        lines.append("| `{job_set_type}` | {display_name} | {family} | {version} | {provider} | {evidence} | {media} | "
                     "{products} | {c} | {j} | {route} | {price} | {same_price_as} |".format(
                         c="✔" if r["in_costs"] else "", j="✔" if r["in_js"] else "",
                         **{k: (f"`{v}`" if k == "route" and v else v) for k, v in r.items()}))
    n_c = sum(r["in_costs"] for r in rows)
    n_j = sum(r["in_js"] for r in rows)
    costs_only = [r["job_set_type"] for r in rows if r["in_costs"] and not r["in_js"]]
    foot = (f"\n{len(rows)} job types; {n_c} in `/job-sets/costs`, {n_j} in the JS bundle. "
            "Route `*` = not in the adapter route table, default `/jobs/<kebab-type>` rule (from JS, not called). "
            f"Costs-only (no `defineJob`/route in JS): {', '.join(f'`{x}`' for x in costs_only) or 'none'}.\n\n"
            f"_Generated by `python scripts/gen_model_catalog.py --write` from {sources}._\n")
    return head + "\n".join(lines) + "\n" + foot


def replace_block(doc: str, block: str) -> str:
    if BEGIN not in doc or END not in doc:
        raise SystemExit(f"markers {BEGIN} / {END} not found")
    pre, rest = doc.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    return f"{pre}{BEGIN}\n{block}{END}{post}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--costs", type=Path, default=DEFAULT_COSTS)
    ap.add_argument("--models", type=Path, default=None, help="models.json (default: newest under runs/)")
    ap.add_argument("--js", default=str(DEFAULT_JS), help="saved JS chunk folder, or 'none'")
    ap.add_argument("--write", action="store_true", help=f"replace the block in {DOC.relative_to(ROOT)}")
    a = ap.parse_args(argv)
    models_path = a.models or latest_models(ROOT / "runs")
    js_dir = None if a.js == "none" else Path(a.js)
    defs, routes, titles = scan_js(js_dir)
    rows = build_rows(load_costs(a.costs), load_models(models_path), defs, routes, titles)

    def rel(p):
        try:
            return Path(p).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return str(p)

    sources = f"`{rel(a.costs)}`, `{rel(models_path) if models_path else 'no models.json'}`" + (
        f", `{rel(js_dir)}`" if defs else "")
    block = render(rows, sources)
    if a.write:
        DOC.write_text(replace_block(DOC.read_text(encoding="utf-8"), block), encoding="utf-8")
        print(f"wrote {len(rows)} rows to {DOC}")
    else:
        sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
