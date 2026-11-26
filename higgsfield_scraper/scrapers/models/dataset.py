"""Join the per-response extracts into the models dataset and write its outputs (JSON parts, CSVs, summary.md).

job_types: one record per job_set_type found in the registry (defineJob), the route table or /job-sets/costs.
menu_entries: picker model-version ids (UI ids) that belong to a model (seen in the plans / featured / gating
tables, retired sets, or equal to a job type after normalizing - and .). builds: one record (what build the data
came from + coverage). chunks: every chunk read. shot_facets: the Shots facet.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ...core.base import RunMeta
from ...core.dataset import make_id, make_meta
from ...core.exporting import row, without, write_standard_outputs
from .endpoints import COSTS_ENDPOINT, ENDPOINT_URLS, SHOTS_ENDPOINT
from .extract import resolve_flag
from .schemas import COLLECTIONS, ModelsDataset

PARAM_KEYS = {"type", "values", "default", "min", "max", "optional", "nullable", "raw"}


def _norm(x: str) -> str:
    return x.replace("-", "_").replace(".", "_").lower()


def _param(name: str, f: dict) -> dict:
    vals = f.get("values")
    raw = f.get("raw") or f.get("args_raw")
    mn, mx = f.get("min"), f.get("max")
    num = (int, float)
    d = f.get("default")
    return {"name": name, "type": f.get("type"), "values": vals if isinstance(vals, list) else None,
            "default": None if isinstance(d, dict) and set(d) == {"raw"} else d,
            "min": mn if isinstance(mn, num) and not isinstance(mn, bool) else None,
            "max": mx if isinstance(mx, num) and not isinstance(mx, bool) else None,
            "optional": bool(f.get("optional")), "nullable": bool(f.get("nullable") or f.get("nullish")),
            "extra": {k: v for k, v in f.items() if k not in PARAM_KEYS and k not in ("args_raw", "nullish")}
            | ({"default_raw": d["raw"]} if isinstance(d, dict) and set(d) == {"raw"} else {})
            | ({"min_raw": mn} if mn is not None and not isinstance(mn, num) else {})
            | ({"max_raw": mx} if mx is not None and not isinstance(mx, num) else {}),
            "raw": raw if isinstance(raw, str) else None}


def _gate(g: Optional[dict], flags: dict, priced: Optional[set], chunks: dict) -> Optional[dict]:
    if not g:
        return None
    flag = resolve_flag(g, chunks)
    value = flags.get(flag) if flag else None
    status: Optional[str] = None
    if flag is not None:
        if value is not True:
            status = "hidden"
        elif g.get("priced_as") and priced is not None and g["priced_as"] not in priced:
            status = "hidden"
        else:
            status = "available"
    cc = g.get("cobalt_coming_soon")
    return {"flag": flag, "flag_value": value, "fallback": g.get("fallback"), "priced_as": g.get("priced_as"),
            "cobalt_coming_soon": cc if isinstance(cc, bool) else None, "status": status,
            "extra": {k: v for k, v in (g.get("extra") or {}).items()}}


def _plan(p: Optional[dict]) -> Optional[dict]:
    if not p:
        return None
    return {"tier": p.get("tier"), "plans": [str(x) for x in p.get("plans") or []]}


def build_dataset(entities: dict[str, list[dict]], sel: Any, rm: RunMeta) -> dict:
    now = (rm.scraped_at or datetime.now(timezone.utc)).isoformat()
    pages = entities.get("models_page_extract", [])
    chunks = {c["chunk"]: c for c in entities.get("models_chunk_extract", [])}
    data = {n: c.get("data") or {} for n, c in chunks.items()}
    costs = (entities.get("models_costs_snapshot") or [None])[0]
    priced: Optional[set] = set(costs["job_set_types"]) if costs else None
    facets = sorted((_strip(f) for f in entities.get("model_shot_facet", [])), key=lambda f: f["position"])
    shot_models = {f["model"]: f for f in facets} if facets else None      # None = facet not fetched

    flags: dict[str, Any] = {}
    for p in pages:
        flags.update(p.get("flags") or {})
    build = next((p for p in pages if p.get("build_id") or p.get("frontend_build")), {})

    # ---- registry parts (first chunk wins, in chunk-name order for determinism)
    jobs: dict[str, dict] = {}
    defined_in: dict[str, list[str]] = {}
    routes: dict[str, str] = {}
    route_chunk: Optional[str] = None
    featured: list[str] = []
    gating: dict[str, dict] = {}
    tables: list[dict] = []
    plans: dict[str, dict] = {}
    plan_tiers: dict[str, list[str]] = {}
    menus: dict[str, dict] = {}
    for name in sorted(data):
        d = data[name]
        for j in d.get("jobs") or []:
            t = j.get("type")
            if not t:
                continue
            defined_in.setdefault(t, []).append(name)
            if t not in jobs or (jobs[t].get("unparsed") and not j.get("unparsed")):
                jobs[t] = {**j, "_chunk": name}
        for k, v in (d.get("routes") or {}).items():
            routes.setdefault(k, v)
            route_chunk = route_chunk or name
        if d.get("featured") and not featured:
            featured = list(d["featured"])
        for k, v in (d.get("gating") or {}).items():
            gating.setdefault(k, v)
        tables += d.get("gating_tables") or []
        for k, v in (d.get("plans") or {}).items():
            plans.setdefault(k, v)
        for k, v in (d.get("plan_tiers") or {}).items():
            plan_tiers.setdefault(k, v)
        for m in d.get("menus") or []:
            e = menus.setdefault(m["id"], {"entries": [], "chunks": []})
            e["entries"].append(m)
            if name not in e["chunks"]:
                e["chunks"].append(name)
    retired = sorted({x for t in tables for x in t.get("retired") or []})
    defaults = list(dict.fromkeys(t["default_model"] for t in tables if t.get("default_model")))
    feat_rank = {x: i for i, x in enumerate(featured)}
    chunk_url = {n: c["url"] for n, c in chunks.items()}

    # ---- job types
    types = set(jobs) | set(routes) | (priced or set())
    job_rows = []
    for t in sorted(types):
        j = jobs.get(t) or {}
        media = j.get("media") or {}
        settings = j.get("settings") or {}
        menu = menus.get(t)
        title = menu["entries"][0].get("title") if menu else None
        extra = {k: j[k] for k in ("keys", "inputs_raw", "settings_ref", "has_to_provider", "has_from_provider",
                                   "unparsed") if j.get(k) not in (None, [], {})}
        if media.get("roles_raw"):
            extra["media_roles_raw"] = media["roles_raw"]
        if media.get("extra"):
            extra["media_extra"] = media["extra"]
        job_rows.append({
            "id": make_id("model_job_type", t), "job_set_type": t,
            "output": j.get("output") if isinstance(j.get("output"), str) else None, "display_title": title,
            "in_registry": t in jobs, "in_routes": t in routes,
            "in_costs": None if priced is None else t in priced,
            "in_shots": None if shot_models is None else t in shot_models,
            "route": routes.get(t),
            "route_inferred": "/jobs/" + t.replace("_", "-") if t in jobs and t not in routes else None,
            "business": j.get("business") if isinstance(j.get("business"), dict) else {},
            "prompt": (j.get("prompt") or {}).get("policy") if j.get("prompt") else None,
            "media_roles": [str(r) for r in media.get("roles") or [] if isinstance(r, str)],
            "media_counts": media.get("counts") or {}, "media_rules_raw": media.get("rules_raw"),
            "params": [_param(k, v) for k, v in settings.items() if isinstance(v, dict)],
            "validate_ranges": j.get("ranges") or {}, "validate_enums": j.get("enum_checks") or {},
            "wire_keys": j.get("wire_keys") or [], "credits_static": j.get("credits_static"),
            "credits_formula_raw": j.get("credits_raw") if j.get("credits_static") is None else None,
            "featured_rank": feat_rank.get(t), "gate": _gate(gating.get(t), flags, priced, data),
            "plan": _plan(plans.get(t)), "retired": t in retired,
            "shots_media_type": (shot_models or {}).get(t, {}).get("media_type"),
            "defined_in": defined_in.get(t, []), "build_id": build.get("build_id"),
            "frontend_build": build.get("frontend_build"), "extra": extra,
            "source_url": chunk_url.get(j.get("_chunk")) or (chunk_url.get(route_chunk) if t in routes else None),
            "scraped_at": now, "schema_version": 1})

    # ---- menu entries (model-like ids only)
    known = set(types) | set(plans) | set(featured) | set(gating) | set(retired)
    known_norm = {_norm(x): x for x in types}
    menu_rows = []
    for mid in sorted(menus):
        if mid not in known and _norm(mid) not in known_norm:
            continue
        es = menus[mid]["entries"]
        first = es[0]
        titles = list(dict.fromkeys(e.get("title") for e in es if e.get("title")))
        badges = list(dict.fromkeys(b for e in es for b in e.get("badges") or []))
        jst = mid if mid in types else known_norm.get(_norm(mid))
        menu_rows.append({
            "id": make_id("model_menu_entry", mid), "model_version_id": mid, "title": first.get("title"),
            "short_title": next((e["short_title"] for e in es if e.get("short_title")), None), "titles": titles,
            "badges": badges, "tags": next((e["tags"] for e in es if e.get("tags") is not None), None),
            "job_set_type": jst, "featured_rank": feat_rank.get(mid),
            "gate": _gate(gating.get(mid), flags, priced, data), "plan": _plan(plans.get(mid)),
            "retired": mid in retired, "chunks": menus[mid]["chunks"],
            "extra": {k: v for k, v in first.items() if k not in ("id", "title", "short_title", "badges", "tags")},
            "scraped_at": now, "schema_version": 1})

    # ---- chunks + build
    chunk_rows = [{"chunk": n, "url": c["url"], "size": c.get("size"), "sha256": c.get("sha256"),
                   "markers": c.get("markers") or [], "named_modules": len(c.get("named_modules") or []),
                   "job_types": len((c.get("data") or {}).get("jobs") or []),
                   "menu_entries": len((c.get("data") or {}).get("menus") or [])} for n, c in sorted(chunks.items())]
    coverage = {"registry": bool(jobs), "routes": bool(routes), "featured": bool(featured), "gating": bool(gating),
                "plans": bool(plans), "flags_resolved": bool(gating) and all(resolve_flag(g, data)
                                                                              for g in gating.values()),
                "page_flags": bool(flags), "costs": priced is not None, "shots": bool(facets)}
    build_row = {
        "id": make_id("model_build", build.get("build_id"), build.get("commit"), build.get("frontend_build")),
        "frontend_build": build.get("frontend_build"), "build_id": build.get("build_id"),
        "commit": build.get("commit"), "environment": build.get("environment"),
        "pages": [p["page"] for p in pages], "flags": dict(sorted(flags.items())),
        "costs_version": costs.get("version") if costs else None, "default_models": defaults, "retired": retired,
        "plan_tiers": plan_tiers, "featured": featured, "chunks_fetched": len(chunks),
        "chunks_with_data": sum(1 for d in data.values() if d), "job_types": len(job_rows),
        "registry_types": len(jobs), "route_types": len(routes), "menu_entries": len(menu_rows),
        "coverage": coverage, "limits_hit": list(rm.limits_hit), "scraped_at": now, "schema_version": 1}
    builds = [build_row] if pages or chunks else []

    ds = {"job_types": job_rows, "menu_entries": menu_rows, "builds": builds, "chunks": chunk_rows,
          "shot_facets": facets}
    counts = {c: len(ds[c]) for c in COLLECTIONS}
    gated = {r["job_set_type"]: r["gate"]["status"] for r in job_rows if r["gate"]}
    gated.update({r["model_version_id"]: r["gate"]["status"] for r in menu_rows if r["gate"]})
    summary = {"counts": counts,
               "by_output": dict(Counter(r["output"] or "unknown" for r in job_rows).most_common()),
               "by_plan_tier": dict(Counter((r["plan"] or {}).get("tier") or "none"
                                            for r in job_rows + menu_rows).most_common()),
               "gated": gated,
               "costs_only": [r["job_set_type"] for r in job_rows if r["in_costs"] and not r["in_registry"]
                              and not r["in_routes"]],
               "registry_not_priced": [r["job_set_type"] for r in job_rows if r["in_registry"]
                                       and r["in_costs"] is False]}
    endpoints = {k: v for k, v in ENDPOINT_URLS.items()
                 if not (k == COSTS_ENDPOINT and not getattr(sel, "with_costs", True))
                 and not (k == SHOTS_ENDPOINT and not getattr(sel, "with_shots", True))}
    meta = make_meta("models", sel, rm, counts=counts, endpoints=endpoints, totals_available=dict(rm.totals))
    return ModelsDataset.model_validate({"schema_version": 1, "meta": meta, "summary": summary, **ds}) \
        .model_dump(mode="json")


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}



# ------------------------------------------------------------------ outputs
CHILD_LISTS = {"job_types": ("params",), "menu_entries": (), "builds": (), "chunks": (), "shot_facets": ()}


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    t: dict[str, tuple[list[dict], list[str]]] = {}
    firsts = {"job_types": ["job_set_type", "id", "output", "display_title"],
              "menu_entries": ["model_version_id", "id", "title", "job_set_type"],
              "builds": ["id", "frontend_build", "build_id", "commit"], "chunks": ["chunk"],
              "shot_facets": ["model", "media_type", "position"]}
    for coll in COLLECTIONS:
        kids = CHILD_LISTS.get(coll, ())
        t[coll] = ([row(without(x, *kids)) for x in ds[coll]], firsts[coll])
    t["job_type_params"] = ([row(p, job_set_type=j["job_set_type"], position=i) for j in ds["job_types"]
                             for i, p in enumerate(j["params"])], ["job_set_type", "position", "name"])
    return t


def summary_md(ds: dict) -> str:
    m, s = ds["meta"], ds["summary"]
    b = ds["builds"][0] if ds["builds"] else {}
    lines = [f"# Higgsfield model registry — {m['scraped_at'][:19]}Z", "",
             f"run `{m.get('run_id')}` · label `{m.get('label')}` · options `{m['options']}`", "",
             f"Build: frontend `{b.get('frontend_build')}` · buildId `{b.get('build_id')}` · commit `{b.get('commit')}`"
             f" · costs version `{b.get('costs_version')}`", "",
             "| collection | rows |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in s["counts"].items()]
    if b:
        lines += ["", f"Chunks read: {b.get('chunks_fetched')} ({b.get('chunks_with_data')} with model data). "
                      f"Registry types: {b.get('registry_types')} · route table: {b.get('route_types')}.",
                  "", "Coverage: " + ", ".join(f"{k}={'yes' if v else 'NO'}" for k, v in b.get("coverage", {}).items())]
    if s["by_output"]:
        lines += ["", "By output: " + ", ".join(f"{k} {v}" for k, v in s["by_output"].items())]
    if s["gated"]:
        lines += ["", "Gated (anonymous): " + ", ".join(f"`{k}` {v}" for k, v in sorted(s["gated"].items()))]
    if s["costs_only"]:
        lines += ["", "Priced but not in the JS registry: " + ", ".join(f"`{x}`" for x in s["costs_only"])]
    if m.get("limits_hit"):
        lines += ["", "## Limits hit", ""] + [f"- {x}" for x in m["limits_hit"]]
    return "\n".join(lines) + "\n"


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    parts: dict[str, Any] = {c: ds[c] for c in COLLECTIONS}
    parts["summary"] = ds["summary"]
    return write_standard_outputs(ds, Path(out_dir), json_parts=parts, csv_tables=csv_tables(ds),
                                  dataset_model=ModelsDataset, summary_md=summary_md(ds))
