"""Registry adapter for the pricing scraper.

The pricing implementation is unchanged and lives where it always did (constants, selection, parsers/, schemas/,
assemble.py, exporters.py, spiders/higgsfield.py). This module only describes it to the framework, so its output
layout and quality stay exactly as before.
"""
from __future__ import annotations

import argparse
import os

from ..constants import AUTH_ENDPOINTS, DEFAULT_SECTIONS, PLAN_SET_PRESETS, SECTIONS, US_PLAN_SET
from ..core.base import RunMeta, ScraperDef
from ..schemas import MODEL_BY_KIND
from ..selection import Selection


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("pricing: what to scrape")
    g.add_argument("--sections", default=",".join(DEFAULT_SECTIONS),
                   help=f"comma list of {sorted(SECTIONS)} or 'all' (default: %(default)s)")
    g.add_argument("--plan-sets", default="us",
                   help=f"plan_set_keys or presets {sorted(PLAN_SET_PRESETS)} (default: us = {US_PLAN_SET})")
    g.add_argument("--billing", default="monthly,annual", help="billing periods for /compare (default: %(default)s)")
    g.add_argument("--marketing-versions", default="latest",
                   help="latest | all | comma list like v51,v50 (default: %(default)s)")
    g.add_argument("--locale", default=os.environ.get("HF_LOCALE", "en"), help="en, de, es, fr, ja, ko, pt-BR, zh-CN")
    f = p.add_argument_group("pricing: filters (applied to output)")
    f.add_argument("--plan-types", default=None, help="e.g. plus,ultra,team (default: all)")
    f.add_argument("--models", default=None, help="model patterns, e.g. seedance,kling*,gpt_image_2_6")
    f.add_argument("--categories", default=None, help="video,image,audio,other")
    o = p.add_argument_group("pricing: output options")
    o.add_argument("--usd-reference", default="plus:annual",
                   help="plan_type:billing_period whose after-offer $/credit prices model USD estimates")
    o.add_argument("--include-hidden-plans", action="store_true", help="keep trial/secret plan types")
    o.add_argument("--include-raw-cost", action="store_true", help="embed each model's untouched cost JSON")


def _login_available(a: argparse.Namespace) -> bool:
    """Live scrape: any configured session counts (--token, HF_TOKEN, the cached `login`, HF_CLERK_CLIENT), unless
    --auth off. `normalize` keeps the original env-only rule so offline re-parses don't depend on this machine's login."""
    legacy = bool(getattr(a, "token", None) or os.environ.get("HF_TOKEN") or os.environ.get("HF_CLERK_CLIENT"))
    if getattr(a, "command", None) == "normalize":
        # depends on the data, not this machine: include auth if the source run captured login-only responses
        from pathlib import Path
        raw = Path(getattr(a, "run", "") or ".") / "raw"
        has_auth_raw = any(next(raw.glob(p), None) is not None
                           for p in ("credit_packages*.json", "unlim_catalog*.json",
                                     "adjustable_credits*.json", "credit_price*.json"))
        return legacy or has_auth_raw
    if getattr(a, "command", None) != "scrape":
        return legacy
    if getattr(a, "auth", "auto") == "off":
        return False
    try:
        from ..core.auth import TokenProvider
        return legacy or TokenProvider.from_env(getattr(a, "token", None)).configured   # offline check, no network
    except Exception:
        return legacy


def make_selection(a: argparse.Namespace) -> Selection:
    has_token = _login_available(a)
    return Selection.build(
        sections=a.sections, plan_sets=a.plan_sets, billing=a.billing, plan_types=a.plan_types,
        models=a.models, categories=a.categories, marketing_versions=a.marketing_versions, locale=a.locale,
        include_hidden_plans=a.include_hidden_plans, include_raw_cost=a.include_raw_cost,
        usd_reference=a.usd_reference, has_token=has_token,
    )


def selection_from_dict(d: dict) -> Selection:
    if "plan_set_keys" in d:                        # a Selection.to_dict() from a manifest
        return Selection(**{k: v for k, v in d.items() if k in Selection.__dataclass_fields__})
    truthy = lambda v: str(v).lower() in ("1", "true", "yes")  # noqa: E731  (spider -a kwargs are strings)
    return Selection.build(
        sections=d.get("sections"), plan_sets=d.get("plan_sets"), billing=d.get("billing"),
        plan_types=d.get("plan_types"), models=d.get("models"), categories=d.get("categories"),
        marketing_versions=d.get("marketing_versions"), locale=d.get("locale", "en"),
        include_hidden_plans=truthy(d.get("include_hidden_plans")), include_raw_cost=truthy(d.get("include_raw_cost")),
        usd_reference=d.get("usd_reference", "plus:annual"), has_token=bool(d.get("token")))


def _parse(env, sel):
    from ..parsers import parse_envelope
    return parse_envelope(env, sel)


def _keep(e, sel):
    from ..parsers import keep
    return keep(e, sel)


def _build(entities, sel, rm: RunMeta) -> dict:
    from ..assemble import build_dataset
    return build_dataset(entities, sel, run_id=rm.run_id, label=rm.label, scraped_at=rm.scraped_at,
                         warnings=rm.warnings)


def _write(ds, out_dir):
    from ..exporters import write_outputs
    return write_outputs(ds, out_dir)


def default_label(sel: Selection) -> str:
    return ("-".join(sel.sections) if len(sel.sections) < 3 else "full") + f"-{'-'.join(sel.plan_set_keys[:2])}"


SCRAPER = ScraperDef(
    name="pricing",
    description="Plans, offers (before/after), renewal, discounts, per-model credit costs, benefits, comparison, "
                "marketing copy; optional logged-in top-ups/bundles",
    spider_cls="higgsfield_scraper.spiders.higgsfield:HiggsfieldSpider",
    model_by_kind=MODEL_BY_KIND,
    id_field_by_kind={},                 # pricing ids are unique by construction; no dedup (output unchanged)
    add_args=add_args,
    make_selection=make_selection,
    selection_from_dict=selection_from_dict,
    parse_envelope=_parse,
    keep=_keep,
    build_dataset=_build,
    write_outputs=_write,
    default_label=default_label,
    optional_endpoints=frozenset(AUTH_ENDPOINTS),
)
