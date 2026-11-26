"""Pydantic models of the models scraper: per-response extracts (entity kinds) and the joined dataset.

Kinds emitted by the parser (one per response, joined by `dataset.build_dataset`):
  models_page_extract   tool page: build id, commit, frontend build, anonymous feature flags, chunk list
  models_chunk_extract  one JS chunk: size, sha256, markers + the registry data found in it (`data`)
  models_costs_snapshot `/job-sets/costs`: version + priced job types (no prices: `pricing` has them)
  model_shot_facet      Shots feed `available_models[]` (models with published shots)

Dataset collections: job_types (one per job_set_type), menu_entries (picker model-version ids), builds (one per
run: what build the data came from), chunks (what was read), shot_facets.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta, Provenance, Strict

SCHEMA_VERSION = 1
Number = Union[int, float]


# ------------------------------------------------------------------ per-response kinds
class PageExtract(Strict):
    """kind=models_page_extract"""
    page: str = Field(description="tool page path, e.g. /ai/video")
    url: str
    frontend_build: Optional[str] = Field(None, description="chunk file prefix, e.g. 548e0f3a")
    build_id: Optional[str] = Field(None, description="buildId from the page env JSON")
    commit: Optional[str] = None
    environment: Optional[str] = None
    flags: dict[str, Any] = Field(default_factory=dict, description="window.__HF_FF.flags (anonymous values)")
    ff_keys: list[str] = Field(default_factory=list, description="other top-level __HF_FF keys")
    chunks: list[str] = Field(default_factory=list, description="modulepreload + module script chunk files")
    size: Optional[int] = None
    sha256: Optional[str] = None
    source: Provenance


class ChunkExtract(Strict):
    """kind=models_chunk_extract"""
    chunk: str
    url: str
    size: Optional[int] = None
    sha256: Optional[str] = None
    markers: list[str] = Field(default_factory=list)
    named_modules: list[str] = Field(default_factory=list)
    refs_static: int = 0
    refs_dynamic: int = 0
    data: dict[str, Any] = Field(default_factory=dict, description="jobs, routes, featured, gating, plans, menus, "
                                                                   "flag constants (extract.py)")
    source: Provenance


class CostsSnapshot(Strict):
    """kind=models_costs_snapshot"""
    snapshot_id: str = "costs"
    version: Optional[Any] = None
    job_set_types: list[str] = Field(default_factory=list)
    source: Provenance


class ShotFacet(Strict):
    """kind=model_shot_facet — one `available_models[]` entry of the Shots feed (fnf-community /generations/feed)."""
    facet_id: str = Field(description="make_id('model_shot_facet', model, media_type)")
    model: str = Field(description="job_set_type (or model id) with published shots")
    media_type: Optional[str] = None
    position: int
    snapshot_id: Optional[str] = None
    snapshot_at: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    source_url: str
    scraped_at: AwareDatetime
    schema_version: int = SCHEMA_VERSION


# ------------------------------------------------------------------ dataset records
class ModelParam(Strict):
    """One settings-schema field of a defineJob (form state; `wire_keys` on the job type are the API names)."""
    name: str = Field(description="settings key (camelCase, as in the form), or '...' for a shared spread")
    type: Optional[str] = Field(None, description="schema builder: enum, aspectRatio, duration, boolean, number, "
                                                  "string, int, … (None = unreadable, see raw)")
    values: Optional[list[Any]] = Field(None, description="allowed values (enums / aspect ratios)")
    default: Optional[Any] = None
    min: Optional[Number] = None
    max: Optional[Number] = None
    optional: bool = False
    nullable: bool = False
    extra: dict[str, Any] = Field(default_factory=dict, description="other builder options (step, unit, …)")
    raw: Optional[str] = Field(None, description="source text when (part of) the field could not be read")


class Gate(Strict):
    flag: Optional[str] = Field(None, description="hashed feature flag (f_xxxxxxxx)")
    flag_value: Optional[Any] = Field(None, description="value in the anonymous __HF_FF (None = flag absent)")
    fallback: Optional[str] = Field(None, description="model shown instead when hidden")
    priced_as: Optional[str] = Field(None, description="job type that must be in /job-sets/costs to show it")
    cobalt_coming_soon: Optional[bool] = None
    status: Optional[Literal["available", "hidden"]] = Field(
        None, description="anonymous status per the JS rule: flag off -> hidden; priced_as missing from costs -> "
                          "hidden; else available")
    extra: dict[str, Any] = Field(default_factory=dict)


class PlanGate(Strict):
    tier: Optional[str] = Field(None, description="all | paid | premium (named from the plan lists)")
    plans: list[str] = Field(default_factory=list)


class JobType(Strict):
    """One generatable job type (`job_set_type`): defineJob schema + route + gating + plans + availability."""
    id: str = Field(description="make_id('model_job_type', job_set_type): stable across builds")
    job_set_type: str
    output: Optional[str] = Field(None, description="defineJob output: video | image | audio | …")
    display_title: Optional[str] = Field(None, description="picker title of the menu entry with the same id")
    in_registry: bool = Field(description="has a defineJob in the bundle")
    in_routes: bool = Field(description="listed in the adapter route table")
    in_costs: Optional[bool] = Field(None, description="listed in /job-sets/costs (None = costs not fetched)")
    in_shots: Optional[bool] = Field(None, description="in the Shots available_models facet (None = not fetched)")
    route: Optional[str] = Field(None, description="create endpoint from the route table, e.g. /jobs/v2/seedance_2_5")
    route_inferred: Optional[str] = Field(None, description="registry types missing from the table: the default "
                                                            "/jobs/<kebab-type> rule (inferred, not called)")
    business: dict[str, Any] = Field(default_factory=dict, description="useUnlim / useFreeGens / … flags")
    prompt: Optional[dict[str, Any]] = Field(None, description="prompt input policy (required, min/maxLength)")
    media_roles: list[str] = Field(default_factory=list, description="media input roles (image, start_image, …)")
    media_counts: dict[str, Any] = Field(default_factory=dict, description="per-role {min, max}")
    media_rules_raw: Optional[str] = Field(None, description="media rules (sizes, ratios, durations) as source text")
    params: list[ModelParam] = Field(default_factory=list)
    validate_ranges: dict[str, list[Any]] = Field(default_factory=dict, description="numeric ranges checked by "
                                                                                    "validate(): name -> [min, max]")
    validate_enums: dict[str, list[Any]] = Field(default_factory=dict)
    wire_keys: list[str] = Field(default_factory=list, description="snake_case keys of the toProvider params")
    credits_static: Optional[Number] = Field(None, description="fixed client-side credit price (credits: () => N)")
    credits_formula_raw: Optional[str] = Field(None, description="client-side credits() source when not fixed")
    featured_rank: Optional[int] = Field(None, description="position in video-featured-model-ids (0 = first)")
    gate: Optional[Gate] = None
    plan: Optional[PlanGate] = None
    retired: bool = Field(False, description="in a retired set (hidden, URLs redirected to the default model)")
    shots_media_type: Optional[str] = None
    defined_in: list[str] = Field(default_factory=list, description="chunk files with a defineJob for the type")
    build_id: Optional[str] = None
    frontend_build: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict, description="unread defineJob parts (keys, raw inputs, …)")
    source_url: Optional[str] = Field(None, description="chunk URL of the defineJob (else the route table chunk)")
    scraped_at: AwareDatetime
    schema_version: int = SCHEMA_VERSION


class MenuEntry(Strict):
    """A model-version id offered by a picker (UI id; maps to a job type + extra params, MODEL_LOADING §2.2)."""
    id: str = Field(description="make_id('model_menu_entry', model_version_id)")
    model_version_id: str
    title: Optional[str] = None
    short_title: Optional[str] = None
    titles: list[str] = Field(default_factory=list, description="every distinct title seen for the id")
    badges: list[str] = Field(default_factory=list)
    tags: Optional[Any] = None
    job_set_type: Optional[str] = Field(None, description="job type with the same normalized id, when one exists")
    featured_rank: Optional[int] = None
    gate: Optional[Gate] = None
    plan: Optional[PlanGate] = None
    retired: bool = False
    chunks: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
    scraped_at: AwareDatetime
    schema_version: int = SCHEMA_VERSION


class Build(Strict):
    """The frontend build the registry was read from (one per run) + crawl coverage."""
    id: str = Field(description="make_id('model_build', build_id, commit, frontend_build)")
    frontend_build: Optional[str] = None
    build_id: Optional[str] = None
    commit: Optional[str] = None
    environment: Optional[str] = None
    pages: list[str] = Field(default_factory=list)
    flags: dict[str, Any] = Field(default_factory=dict, description="anonymous __HF_FF flags (union of pages)")
    costs_version: Optional[Any] = None
    default_models: list[str] = Field(default_factory=list, description="picker default per gating table")
    retired: list[str] = Field(default_factory=list)
    plan_tiers: dict[str, list[str]] = Field(default_factory=dict)
    featured: list[str] = Field(default_factory=list, description="video-featured-model-ids, in order")
    chunks_fetched: int = 0
    chunks_with_data: int = 0
    job_types: int = 0
    registry_types: int = 0
    route_types: int = 0
    menu_entries: int = 0
    coverage: dict[str, bool] = Field(default_factory=dict, description="registry parts found in this run")
    limits_hit: list[str] = Field(default_factory=list)
    scraped_at: AwareDatetime
    schema_version: int = SCHEMA_VERSION


class Chunk(Strict):
    """One JS chunk read in the run (to diff builds: names change, sha256 shows content changes)."""
    chunk: str
    url: str
    size: Optional[int] = None
    sha256: Optional[str] = None
    markers: list[str] = Field(default_factory=list)
    named_modules: int = 0
    job_types: int = 0
    menu_entries: int = 0


MODEL_BY_KIND = {
    "models_page_extract": PageExtract,
    "models_chunk_extract": ChunkExtract,
    "models_costs_snapshot": CostsSnapshot,
    "model_shot_facet": ShotFacet,
}
ID_FIELD_BY_KIND = {
    "models_page_extract": "page",
    "models_chunk_extract": "chunk",
    "models_costs_snapshot": "snapshot_id",
    "model_shot_facet": "facet_id",
}
COLLECTIONS = ("job_types", "menu_entries", "builds", "chunks", "shot_facets")


class Summary(Strict):
    counts: dict[str, int] = Field(default_factory=dict)
    by_output: dict[str, int] = Field(default_factory=dict)
    by_plan_tier: dict[str, int] = Field(default_factory=dict)
    gated: dict[str, Optional[str]] = Field(default_factory=dict, description="job type / UI id -> gate status")
    costs_only: list[str] = Field(default_factory=list, description="priced job types with no defineJob/route")
    registry_not_priced: list[str] = Field(default_factory=list)


class ModelsDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    summary: Summary
    job_types: list[JobType] = Field(default_factory=list)
    menu_entries: list[MenuEntry] = Field(default_factory=list)
    builds: list[Build] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    shot_facets: list[ShotFacet] = Field(default_factory=list)
