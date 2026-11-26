"""Pure extraction: tool-page HTML and JS chunks -> compact JSON (what the models scraper archives and parses).

The frontend has no "models" API: the model registry is static code in the bundle (docs/MODEL_LOADING.md §2-3).
Everything here is regex + bracket matching on minified JS (no JS execution):

* page (`/ai/video` …): build id + commit (`$_TSR`/env JSON), frontend build prefix (`548e0f3a`), anonymous feature
  flags (`window.__HF_FF`), the chunk list (modulepreload + module scripts);
* chunk: static / dynamic chunk references (crawl), named modules, and when present:
  - `defineJob` registry entries (`P({type:`x`,output:`y`,business,input:[prompt(), media({roles,counts,rules}),
    settingsSchema],credits,validate,toProvider,fromProvider})`) with the settings schema resolved in the chunk;
  - the adapter route table (`seedance_2_5:`v2/seedance_2_5``);
  - `video-featured-model-ids` (picker order);
  - the gating table (`{flag, fallback, pricedAs, cobaltComingSoon}`), default model and retired set;
  - `video-model-plans` (+ the `plans` tier lists);
  - picker menu entries (`{id:`x`,badges:[…],title:`X`, short_title…}`);
  - hashed feature-flag constants (`xx=`f_24c5dcf4``) and their export names (to resolve gating flags).
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from collections import Counter
from typing import Any, Optional

from .jsparse import (IDENT, array_items, find_assignment, literal_or_raw, match_bracket, object_props,
                      object_spreads, parse_literal, split_top)

EXTRACT_VERSION = 1
CHUNK_RE = re.compile(r"/tanstack/assets/([0-9a-f]{8}-[A-Za-z0-9_\-]+\.js)")
STATIC_REF_RE = re.compile(r"""(?:\bfrom|\bimport)\s*["'`]\./([A-Za-z0-9_\-]+\.js)["'`]""")
DYNAMIC_REF_RE = re.compile(r"""import\(\s*["'`]\./([A-Za-z0-9_\-]+\.js)["'`]""")
NAMED_MODULE_RE = re.compile(r"\be\(`([a-z0-9][a-z0-9\-]*-[A-Za-z0-9_\-]{8})`,")
DEF_RE = re.compile(r"\{type:`([a-z0-9_]+)`,output:`([a-z_]+)`")
ROUTE_PAIR_RE = re.compile(r"(?<![\w$])([a-z][a-z0-9_]*):`(v2/[a-z0-9_]+|[a-z0-9\-]+/v2|[a-z0-9\-]+)`")
ROUTE_HINT_RE = re.compile(r"[a-z0-9_]+:`v2/[a-z0-9_]+`")
GATE_RE = re.compile(r"(?<![\w$])([a-z0-9_\-]+):\{flag:(" + IDENT + r"),fallback:`([^`]+)`((?:,[A-Za-z]+:[^,{}]+)*)\}")
MENU_RE = re.compile(r"\{id:`([A-Za-z0-9_\-.]+)`,")
FLAG_CONST_RE = re.compile(r"(?<![\w$.])(" + IDENT + r")=`(f_[0-9a-f]{8})`")
EXPORT_RE = re.compile(r"export\{([^}]*)\}")
IMPORT_RE = re.compile(r"import\{([^}]*)\}from\s*[\"'`]\./([A-Za-z0-9_\-]+\.js)[\"'`]")
MARKERS = {
    "define_job": DEF_RE,
    "routes": ROUTE_HINT_RE,
    "featured": re.compile(r"`video-featured-model-ids-"),
    "gating": re.compile(r"\{flag:" + IDENT + r",fallback:`"),
    "plans": re.compile(r"`video-model-plans-[A-Za-z0-9_\-]{8}`,\(e=>"),
    "flags": FLAG_CONST_RE,
}
MAX_RAW = 400


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ================================================================== pages

def extract_page(html: str, url: str = "") -> dict:
    """Tool page -> {format: page, frontend_build, build_id, commit, environment, flags, chunks[]}."""
    builds = Counter(c.split("-", 1)[0] for c in CHUNK_RE.findall(html))
    chunks = list(dict.fromkeys(CHUNK_RE.findall(html)))
    plain = html_lib.unescape(html)
    env: dict[str, Any] = {}
    for key in ("buildId", "commit", "environment"):
        m = re.search(r'"' + key + r'":"([^"]+)"', plain)
        env[key] = m.group(1) if m else None
    flags: dict[str, Any] = {}
    ff_keys: list[str] = []
    i = plain.find("window.__HF_FF")
    if i >= 0:
        j = plain.find("{", i)
        end = match_bracket(plain, j)
        if end > 0:
            try:
                ff = json.loads(plain[j:end + 1])
            except ValueError:
                ff = None
            if isinstance(ff, dict):
                flags = ff.get("flags") if isinstance(ff.get("flags"), dict) else {}
                ff_keys = sorted(k for k in ff if k != "userId")
    return {"format": "page", "extract_version": EXTRACT_VERSION, "url": url,
            "frontend_build": builds.most_common(1)[0][0] if builds else None,
            "build_id": env["buildId"], "commit": env["commit"], "environment": env["environment"],
            "flags": flags, "ff_keys": ff_keys, "chunks": chunks, "size": len(html.encode("utf-8")),
            "sha256": sha256(html.encode("utf-8"))}


# ================================================================== chunks

def extract_chunk(name: str, text: str) -> dict:
    out: dict[str, Any] = {
        "format": "chunk", "extract_version": EXTRACT_VERSION, "chunk": name,
        "size": len(text.encode("utf-8")), "sha256": sha256(text.encode("utf-8")),
        "refs_static": list(dict.fromkeys(STATIC_REF_RE.findall(text))),
        "refs_dynamic": list(dict.fromkeys(DYNAMIC_REF_RE.findall(text))),
        "named_modules": list(dict.fromkeys(NAMED_MODULE_RE.findall(text))),
        "markers": [k for k, rx in MARKERS.items() if rx.search(text)],
    }
    if "define_job" in out["markers"]:
        out["jobs"] = extract_jobs(text)
    if "routes" in out["markers"]:
        out["routes"] = extract_routes(text)
    if "featured" in out["markers"]:
        out["featured"] = extract_featured(text)
    if "gating" in out["markers"]:
        out.update(extract_gating(text))
    if "plans" in out["markers"]:
        out.update(extract_plans(text))
    flag_consts = dict(FLAG_CONST_RE.findall(text))
    if flag_consts:
        out["flag_consts"] = flag_consts
        out["flag_exports"] = {exp: loc for loc, exp in _export_pairs(text) if loc in flag_consts}
    menus = extract_menus(text)
    if menus:
        out["menus"] = menus
    return out


def _export_pairs(text: str) -> list[tuple[str, str]]:
    pairs = []
    for m in EXPORT_RE.finditer(text):
        for p in m.group(1).split(","):
            p = p.strip()
            if not p:
                continue
            loc, _, exp = p.partition(" as ")
            pairs.append((loc.strip(), (exp or loc).strip()))
    return pairs


def import_aliases(text: str) -> dict[str, tuple[str, str]]:
    """{local alias: (chunk file, exported name)} for `import{X as y}from"./chunk.js"` statements."""
    out: dict[str, tuple[str, str]] = {}
    for m in IMPORT_RE.finditer(text):
        for p in m.group(1).split(","):
            p = p.strip()
            if not p:
                continue
            exp, _, loc = p.partition(" as ")
            out[(loc or exp).strip()] = (m.group(2), exp.strip())
    return out


# ------------------------------------------------------------------ defineJob registry
SCHEMA_CALL_RE = re.compile(r"^(?:[\w$]+\.)?([A-Za-z_]+)\((.*)\)$", re.S)


def _raw(s: Any, n: int = MAX_RAW) -> Optional[str]:
    return None if s is None else str(s)[:n]


def parse_field(expr: str, text: str, near: int, depth: int = 0) -> dict:
    """Settings-schema field expression (`j._default(j.enum(Qn),`1600p`)`, `j.duration({min:4,max:15})`, …)."""
    e = expr.strip()
    m = SCHEMA_CALL_RE.match(e)
    if not m or depth > 6:
        return {"type": None, "raw": _raw(e)}
    fn, args = m.group(1), split_top(m.group(2))
    if fn == "_default" and args:
        inner = parse_field(args[0], text, near, depth + 1)
        if len(args) > 1:
            d = literal_or_raw(args[1], text, near)
            inner["default"] = d
        return inner
    if fn in ("optional", "nullable", "nullish") and args:
        inner = parse_field(args[0], text, near, depth + 1)
        inner[fn] = True
        return inner
    out: dict[str, Any] = {"type": fn}
    if args:
        a0 = args[0].strip()
        if a0.startswith("{"):
            v = literal_or_raw(a0, text, near)
            if isinstance(v, dict) and "raw" not in v:
                out.update({k: x for k, x in v.items() if k not in ("type",)})
            else:
                out["args_raw"] = _raw(a0)
        else:
            v = literal_or_raw(a0, text, near)
            if isinstance(v, list):
                out["values"] = v
            elif isinstance(v, dict) and set(v) == {"raw"}:
                out["args_raw"] = _raw(a0)
            elif isinstance(v, dict):
                out["values"] = list(v.values())
            else:
                out["arg"] = v
        for extra in args[1:]:
            v = literal_or_raw(extra, text, near)
            if isinstance(v, dict) and "raw" not in v:
                out.update(v)
    return out


def _settings_schema(ident: str, text: str, near: int) -> Optional[dict]:
    rhs = find_assignment(text, ident, near)
    if not rhs:
        return None
    m = re.match(r"^" + IDENT + r"\((\{.*\})\)$", rhs, flags=re.S)
    obj = m.group(1) if m else (rhs if rhs.startswith("{") else None)
    if obj is None:
        return None
    props = object_props(obj)
    spreads = object_spreads(obj)
    if not props and not spreads:
        return None
    out = {name: parse_field(v, text, near) for name, v in props.items()}
    if spreads:                                    # shared settings from another module (not inlined)
        out["..."] = {"type": "spread", "raw": _raw(", ".join(spreads))}
    return out


def _media_input(expr: str, text: str, near: int) -> Optional[dict]:
    m = re.match(r"^" + IDENT + r"\((\{.*\})\)$", expr.strip(), flags=re.S)
    if not m:
        return None
    props = object_props(m.group(1))
    if "roles" not in props:
        return None
    roles = literal_or_raw(props["roles"], text, near)
    counts = literal_or_raw(props.get("counts", "{}"), text, near)
    return {"roles": roles if isinstance(roles, list) else [], "roles_raw": None if isinstance(roles, list)
            else _raw(props["roles"]), "counts": counts if isinstance(counts, dict) and "raw" not in counts else {},
            "rules_raw": _raw(props.get("rules"), 1500),
            "extra": {k: _raw(v) for k, v in props.items() if k not in ("roles", "counts", "rules")}}


def _prompt_input(expr: str, text: str, near: int) -> Optional[dict]:
    m = re.match(r"^" + IDENT + r"\((.*)\)$", expr.strip(), flags=re.S)
    if not m:
        return None
    arg = m.group(1).strip()
    if not arg:
        return {"policy": {}, "raw": _raw(expr)}
    if "policy:" not in arg:
        return None
    v = literal_or_raw(arg, text, near)
    pol = v.get("policy") if isinstance(v, dict) and isinstance(v.get("policy"), dict) else {}
    return {"policy": pol, "raw": _raw(expr)}


RANGE_RE = re.compile(r"\(`([A-Za-z_][\w]*)`,[\w$.]+,(-?[\d.e]+),(-?[\d.e]+)\)")
ENUM_CHECK_RE = re.compile(r"\(`([A-Za-z_][\w]*)`,[\w$.]+,(Object\.values\(" + IDENT + r"\)|" + IDENT + r"|\[[^\]]*\])\)")
WIRE_KEY_RE = re.compile(r"(?:[{,]|\?\{)([a-z][a-z0-9]*(?:_[a-z0-9]+)+|[a-z]{2,}):")


def _num(s: str) -> Any:
    try:
        v = float(s)
    except ValueError:
        return s
    return int(v) if v.is_integer() else v


def extract_job(text: str, obj_start: int) -> Optional[dict]:
    end = match_bracket(text, obj_start)
    if end < 0:
        return None
    obj = text[obj_start:end + 1]
    props = object_props(obj)
    jtype = literal_or_raw(props.get("type", ""))
    if not isinstance(jtype, str):
        return None
    near = obj_start
    job: dict[str, Any] = {"type": jtype, "output": literal_or_raw(props.get("output", "")),
                           "keys": list(props), "prompt": None, "media": None, "settings": None,
                           "settings_ref": None, "inputs_raw": []}
    if isinstance(job["output"], dict):
        job["output"] = None
    if "business" in props:
        b = literal_or_raw(props["business"], text, near)
        job["business"] = b if isinstance(b, dict) else {"raw": _raw(props["business"])}
    for item in array_items(props.get("input", "[]")):
        media = _media_input(item, text, near)
        if media is not None:
            job["media"] = media
            continue
        if re.fullmatch(IDENT, item.strip()):
            schema = _settings_schema(item.strip(), text, near)
            if schema is not None:
                job["settings"] = schema
                job["settings_ref"] = item.strip()
                continue
        pr = _prompt_input(item, text, near)
        if pr is not None and job["prompt"] is None:
            job["prompt"] = pr
            continue
        job["inputs_raw"].append(_raw(item))
    credits = props.get("credits")
    if credits is not None:
        job["credits_raw"] = _raw(credits, 1500)
        m = re.fullmatch(r"\(\)=>(.+)", credits.strip(), flags=re.S)
        if m:
            v = literal_or_raw(m.group(1), text, near)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                job["credits_static"] = v
    val = props.get("validate")
    if val:
        job["ranges"] = {k: [_num(a), _num(b)] for k, a, b in RANGE_RE.findall(val)}
        enums = {}
        for k, ref in ENUM_CHECK_RE.findall(val):
            v = literal_or_raw(ref, text, near)
            if isinstance(v, dict) and "raw" not in v:
                v = list(v.values())
            if isinstance(v, list):
                enums[k] = v
        job["enum_checks"] = enums
    tp = props.get("toProvider")
    if tp:
        r = tp.rfind("return{")
        if r >= 0:
            e2 = match_bracket(tp, r + 6)
            ret = tp[r + 6:e2 + 1] if e2 > 0 else tp[r + 6:]
            job["wire_keys"] = sorted(set(WIRE_KEY_RE.findall(ret)))
    job["has_to_provider"] = "toProvider" in props
    job["has_from_provider"] = "fromProvider" in props
    return job


def extract_jobs(text: str) -> list[dict]:
    out, seen = [], set()
    for m in DEF_RE.finditer(text):
        start = m.start()
        if (m.group(1), start) in seen:
            continue
        seen.add((m.group(1), start))
        try:
            j = extract_job(text, start)
        except RecursionError:
            j = None
        out.append(j or {"type": m.group(1), "output": m.group(2), "unparsed": True})
    return out


# ------------------------------------------------------------------ routes / featured / gating / plans / menus
def extract_routes(text: str) -> dict[str, str]:
    routes: dict[str, str] = {}
    covered_to = -1
    for m in ROUTE_HINT_RE.finditer(text):
        if m.start() < covered_to:
            continue
        start = text.rfind("{", 0, m.start())
        end = text.find("}", m.start())
        if start < 0 or end < 0:
            continue
        pairs = ROUTE_PAIR_RE.findall(text[start:end])
        covered_to = end
        if sum(1 for _, v in pairs if v.startswith("v2/")) >= 5:
            for k, v in pairs:
                routes.setdefault(k, "/jobs/" + v)
    return routes


def extract_featured(text: str) -> list[str]:
    i = text.find("`video-featured-model-ids-")
    j = text.find("=[", i)
    if i < 0 or j < 0 or j - i > 800:
        return []
    end = match_bracket(text, j + 1)
    v = literal_or_raw(text[j + 1:end + 1])
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def extract_gating(text: str) -> dict:
    """Gating tables (`{id: {flag, fallback, pricedAs?, cobaltComingSoon?}}`), merged into `gating`, plus one
    `gating_tables` row per table with the default model and retired set declared just before it (video picker:
    zx=`seedance_2_5`, Vx=new Set([...retired]), Hx={...}; the image picker has its own)."""
    gating: dict[str, dict] = {}
    tables: dict[int, list[str]] = {}
    aliases = import_aliases(text)
    for m in GATE_RE.finditer(text):
        tables.setdefault(text.rfind("={", 0, m.start()), []).append(m.group(1))
        rest = {}
        for part in split_top(m.group(4).lstrip(",")) if m.group(4) else []:
            k, _, v = part.partition(":")
            rest[k] = literal_or_raw(v, text, m.start())
        ident = m.group(2)
        local = find_assignment(text, ident, m.start())
        imp = aliases.get(ident)
        gating[m.group(1)] = {"flag_ident": ident,
                              "flag": local.strip("`") if local and re.fullmatch(r"`f_[0-9a-f]{8}`", local) else None,
                              "flag_import": list(imp) if imp else None, "fallback": m.group(3),
                              "priced_as": rest.pop("pricedAs", None),
                              "cobalt_coming_soon": rest.pop("cobaltComingSoon", None), "extra": rest}
    rows = []
    for start, ids in tables.items():
        block = text.rfind("t(()=>{", 0, start)
        win = text[block if block >= 0 and start - block < 6000 else max(0, start - 3000):start]
        retired: list[str] = []
        default = None
        s = win.rfind("new Set([")
        if s >= 0:
            end = match_bracket(win, s + 8)
            v = literal_or_raw(win[s + 8:end + 1]) if end > 0 else None
            retired = [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
            m = re.search(r"(?<![\w$])" + IDENT + r"=`([a-z0-9_\-.]+)`,", win[:s])
            default = m.group(1) if m else None
        rows.append({"ids": ids, "default_model": default, "retired": retired})
    return {"gating": gating, "gating_tables": rows}


def _module_body(text: str, name_prefix: str) -> tuple[int, str]:
    i = text.find("e(`" + name_prefix)
    if i < 0:
        return -1, ""
    j = text.find("(e=>", i)
    end = match_bracket(text, j) if j >= 0 else -1
    return i, text[i:end + 1] if end > 0 else text[i:i + 50000]


def _plan_tiers(text: str) -> dict[str, list[str]]:
    """`plans-XXXX` module: {export letter: [plan, …]} (r=[`free`,…],i=[…],a=[…],o=a; n(e,{t:()=>r,…}))."""
    _, body = _module_body(text, "plans-")
    if not body:
        return {}
    arrays: dict[str, Any] = {}
    for m in re.finditer(r"(?<![\w$.])(" + IDENT + r")=(\[[^\]]*\]|" + IDENT + r")(?=[,)}])", body):
        arrays[m.group(1)] = m.group(2)
    out: dict[str, list[str]] = {}
    em = re.search(r"\bn\(e,(\{[^}]*\})\)", body)
    for part in split_top(em.group(1)[1:-1]) if em else []:
        mm = re.fullmatch(r"(" + IDENT + r"):\(\)=>(" + IDENT + r")", part)
        if not mm:
            continue
        val, seen = arrays.get(mm.group(2)), 0
        while isinstance(val, str) and not val.startswith("[") and seen < 4:
            val, seen = arrays.get(val), seen + 1
        if isinstance(val, str):
            v = literal_or_raw(val)
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                out[mm.group(1)] = v
    return out


def tier_name(plans: list[str], all_plans: list[str]) -> str:
    if "free" in plans:
        return "all"
    if set(plans) == set(all_plans) - {"free"}:
        return "paid"
    return "premium"


def extract_plans(text: str) -> dict:
    tiers = _plan_tiers(text)
    start, body = _module_body(text, "video-model-plans-")
    ns = re.search(r"var (" + IDENT + r")=r\(`plans-", body)
    alias = ns.group(1) if ns else None
    plans: dict[str, Any] = {}
    if alias:
        rx = re.compile(r"(?:[{,])(\"[^\"]+\"|" + IDENT + r"):" + re.escape(alias) + r"\.(" + IDENT + r")(?=[,}])")
        for m in rx.finditer(body):
            key = m.group(1).strip('"')
            plans.setdefault(key, m.group(2))
    all_plans = max(tiers.values(), key=len) if tiers else []
    names = {k: tier_name(v, all_plans) for k, v in tiers.items()}
    return {"plans": {k: {"tier": names.get(letter), "tier_ref": letter, "plans": tiers.get(letter)}
                      for k, letter in plans.items()},
            "plan_tiers": {names[k]: v for k, v in tiers.items()}}


def extract_menus(text: str) -> list[dict]:
    """Picker entries `{id:`x`,…,title:`X`…}` (only objects whose title is a literal string)."""
    out = []
    for m in MENU_RE.finditer(text):
        end = match_bracket(text, m.start(), 4000)
        if end < 0:
            continue
        props = object_props(text[m.start():end + 1])
        title = props.get("title", "")
        if not (title.startswith("`") and "${" not in title):
            continue
        entry: dict[str, Any] = {"id": m.group(1), "title": title.strip("`")}
        st = props.get("short_title") or props.get("shortTitle")
        if st and st.startswith("`") and "${" not in st:
            entry["short_title"] = st.strip("`")
        if "badges" in props:
            v = literal_or_raw(props["badges"])
            entry["badges"] = [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
        for k in ("tags", "availablePlans", "description"):
            if k in props:
                v = literal_or_raw(props[k])
                entry[k] = v if not (isinstance(v, dict) and set(v) == {"raw"}) else {"raw": _raw(props[k], 200)}
        out.append(entry)
    return out


def resolve_flag(gate: dict, chunk_extracts: dict[str, dict]) -> Optional[str]:
    """Hashed flag name (`f_24c5dcf4`) of a gating entry: local constant, or import -> export -> constant."""
    if gate.get("flag"):
        return gate["flag"]
    imp = gate.get("flag_import")
    if not imp:
        return None
    src = chunk_extracts.get(imp[0]) or {}
    local = (src.get("flag_exports") or {}).get(imp[1])
    return (src.get("flag_consts") or {}).get(local) if local else None


__all__ = ["extract_page", "extract_chunk", "extract_jobs", "extract_routes", "extract_featured", "extract_gating",
           "extract_plans", "extract_menus", "resolve_flag", "import_aliases", "parse_literal"]
