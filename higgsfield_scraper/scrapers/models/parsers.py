"""Pure parsers: Envelope -> entity dicts (each with "kind"). No network, no Scrapy.

Envelope bodies are already compact JSON: middleware.py replaces the page HTML / JS chunk bodies with their
extract (extract.py) before anything is archived, and the Shots feed body with its facet whitelist. A raw HTML / JS
body (`{"_non_json": …}` from a run without the middleware) yields nothing.
"""
from __future__ import annotations

from typing import Any

from ...core.dataset import make_id
from ...raw import Envelope
from .endpoints import CHUNK_ENDPOINT, COSTS_ENDPOINT, PAGE_ENDPOINT, SHOTS_ENDPOINT

DATA_KEYS = ("jobs", "routes", "featured", "gating", "gating_tables", "plans", "plan_tiers", "flag_consts",
             "flag_exports", "menus")


def _prov_flat(env: Envelope) -> dict:
    return {"source_url": env.url, "scraped_at": env.fetched_at.isoformat(), "schema_version": 1}


def parse_page(env: Envelope, sel: Any) -> list[dict]:
    b = env.body
    if not isinstance(b, dict) or b.get("format") != "page":
        return []
    return [{"kind": "models_page_extract", "page": env.params.get("page") or b.get("url") or env.url,
             "url": env.url, "frontend_build": b.get("frontend_build"), "build_id": b.get("build_id"),
             "commit": b.get("commit"), "environment": b.get("environment"),
             "flags": b.get("flags") if isinstance(b.get("flags"), dict) else {},
             "ff_keys": [str(x) for x in b.get("ff_keys") or []], "chunks": [str(x) for x in b.get("chunks") or []],
             "size": b.get("size"), "sha256": b.get("sha256"), "source": env.provenance()}]


def parse_chunk(env: Envelope, sel: Any) -> list[dict]:
    b = env.body
    if not isinstance(b, dict) or b.get("format") != "chunk":
        return []
    return [{"kind": "models_chunk_extract", "chunk": str(b.get("chunk") or env.params.get("chunk")),
             "url": env.url, "size": b.get("size"), "sha256": b.get("sha256"),
             "markers": [str(x) for x in b.get("markers") or []],
             "named_modules": [str(x) for x in b.get("named_modules") or []],
             "refs_static": len(b.get("refs_static") or []), "refs_dynamic": len(b.get("refs_dynamic") or []),
             "data": {k: b[k] for k in DATA_KEYS if b.get(k)}, "source": env.provenance()}]


def parse_costs(env: Envelope, sel: Any) -> list[dict]:
    b = env.body
    rows = b.get("data") if isinstance(b, dict) else b
    if not isinstance(rows, list):
        return []
    types = sorted({str(r["job_set_type"]) for r in rows if isinstance(r, dict) and r.get("job_set_type")})
    return [{"kind": "models_costs_snapshot", "snapshot_id": "costs",
             "version": b.get("version") if isinstance(b, dict) else None, "job_set_types": types,
             "source": env.provenance()}]


def parse_shots(env: Envelope, sel: Any) -> list[dict]:
    b = env.body if isinstance(env.body, dict) else {}
    am = b.get("available_models") if isinstance(b.get("available_models"), list) else []
    out = []
    for n, m in enumerate(x for x in am if isinstance(x, dict)):
        model = m.get("model")
        if model in (None, ""):
            continue
        mt = m.get("media_type")
        out.append({"kind": "model_shot_facet", "facet_id": make_id("model_shot_facet", model, mt or ""),
                    "model": str(model), "media_type": None if mt in (None, "") else str(mt), "position": n,
                    "snapshot_id": b.get("snapshot_id"), "snapshot_at": b.get("snapshot_at"),
                    "extra": {k: v for k, v in m.items() if k not in ("model", "media_type") and v is not None},
                    **_prov_flat(env)})
    return out


PARSERS = {PAGE_ENDPOINT: parse_page, CHUNK_ENDPOINT: parse_chunk, COSTS_ENDPOINT: parse_costs,
           SHOTS_ENDPOINT: parse_shots}


def parse_envelope(env: Envelope, sel: Any) -> list[dict]:
    if env.status != 200:
        return []
    fn = PARSERS.get(env.endpoint)
    return fn(env, sel) if fn else []


def keep(entity: dict, sel: Any) -> bool:
    return True
