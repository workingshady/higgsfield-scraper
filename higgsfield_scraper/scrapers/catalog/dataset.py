"""Assemble the validated CatalogDataset and write its outputs (JSON parts, complete CSVs, summary.md)."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import row, without, write_standard_outputs
from .endpoints import (COLLECTION_OF, ENDPOINT_URLS, KIND_OF, KINDS, LOGIN_ONLY, MOTION_DETAIL_KIND, OPT_IN,
                        OPT_IN_COLLECTIONS, OPT_IN_ENDPOINTS, PAGE_KIND, SHORT_OF, SOURCE_BY_ENDPOINT)
from .schemas import CatalogDataset, CatalogDatasetFull

CHILD_LISTS = ("media", "mix", "price_matrix", "inputs")


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def _merge_details(motions: list[dict], details: list[dict]) -> None:
    by_id = {d["id"]: d for d in details}
    for m in motions:
        d = by_id.get(m["id"])
        if not d:
            continue
        m["detail_fetched"] = True
        for k in ("name", "description", "preset_family", "priority", "cms_id", "params"):
            if d.get(k) not in (None, {}, ""):
                m[k] = d[k]
        for k in ("categories", "tags"):
            if d.get(k):
                m[k] = d[k]
        if d.get("media"):
            m["media"] = d["media"]
            m["has_preview"] = True
        m["extra"] = {**m.get("extra", {}), **d.get("extra", {})}


def _totals(pages: list[dict], spider_totals: dict[str, Optional[int]]) -> dict[str, Optional[int]]:
    out: dict[str, Optional[int]] = {}
    per_kind: dict[str, list[Optional[int]]] = defaultdict(list)
    for p in pages:
        if p["first_page"]:
            per_kind[SHORT_OF.get(p["catalog"], p["catalog"])].append(p.get("total"))
    for k, ts in per_kind.items():
        out[k] = None if any(t is None for t in ts) else sum(ts)
    for k, v in spider_totals.items():
        out.setdefault(k, v)
    return out


def _summary(ds: dict, sel: Any, pages: list[dict], totals: dict) -> dict:
    counts = {s: len(ds[COLLECTION_OF[k]]) for s, k in KIND_OF.items() if ds.get(COLLECTION_OF[k])}
    by_cat: dict[str, dict[str, int]] = {}

    def cat(name: str, values) -> None:
        c = Counter(str(v) for v in values)
        if c:
            by_cat[name] = dict(c.most_common())

    cat("motion", [c for m in ds["motions"] for c in m["categories"]] or [])
    cat("motion_tag", [t for m in ds["motions"] for t in m["tags"]])
    cat("style", [c for m in ds["styles"] for c in m["categories"]])
    cat("voice", [c for v in ds["voices"] for c in v["categories"]])
    cat("reference_voice_model", [x for v in ds["reference_voices"] for x in v["supported_models"]])
    cat("viral_preset_type", [s for p in ds["viral_presets"] for s in (p["type_slugs"] or p["type_ids"])])
    cat("soul_sample_quality", [s["quality"] for s in ds["soul_samples"] if s["quality"]])
    cat("soul_style_set", [x["style_set"] for x in ds["soul_styles"]])
    for coll in ("soul_styles", "mixed_media_presets", "model_motions", "katana_presets", "marketing_presets",
                 "youtube_faceless_presets", "color_presets"):
        cat(coll[:-1], [c for x in ds[coll] for c in x["categories"]])
    fam: dict[str, dict[str, int]] = {}
    for name, rows, key in (("motion", ds["motions"], "preset_family"), ("style", ds["styles"], "preset_family"),
                            ("motion_sample", ds["motion_samples"], "preset_family"),
                            ("model_motion", ds["model_motions"], "model_family")):
        c = Counter(str(r[key]) for r in rows if r.get(key))
        if c:
            fam[name] = dict(c.most_common())
    fetched = {SHORT_OF.get(p["catalog"]) for p in pages}
    would_fetch = set(sel.resolve_kinds(bool(getattr(sel, "has_session", False))))
    login = {}
    for k in LOGIN_ONLY:
        if k in fetched:
            login[k] = "fetched"
        elif k in would_fetch:
            login[k] = "skipped (no session or HTTP 401)"
        elif getattr(sel, "include_login_only", "auto") == "auto" and not getattr(sel, "has_session", False):
            login[k] = "not selected (no session configured)"
        else:
            login[k] = "not selected"
    styles: dict[str, dict] = {}
    for s in ds["soul_samples"]:
        if s.get("style_id"):
            st = styles.setdefault(s["style_id"], {"style_id": s["style_id"], "name": s.get("style_name"),
                                                   "url": s.get("style_url"), "samples": 0})
            st["samples"] += 1
    return {"counts": counts, "totals_available": totals, "by_category": by_cat, "by_model_family": fam,
            "login_only": login,
            "motions_without_preview": sum(1 for m in ds["motions"] if not m["has_preview"]),
            "motions_with_details": sum(1 for m in ds["motions"] if m["detail_fetched"]),
            "soul_sample_styles": sorted(styles.values(), key=lambda x: (-x["samples"], x["name"] or ""))}


def _active_opt_in(entities: dict[str, list[dict]], sel: Any) -> set[str]:
    """Opt-in short kinds that belong in this run's output: selected or with rows. The others are left out of the
    dataset entirely (no empty collections / counts / endpoints / summary rows), so runs that do not use them keep
    exactly the pre-opt-in output."""
    try:
        selected = set(sel.resolve_kinds(bool(getattr(sel, "has_session", False))))
    except Exception:
        selected = set()
    return {k for k in OPT_IN if k in selected or entities.get(KIND_OF[k])}


def _is_opt_in_collection_active(ds: dict, coll: str) -> bool:
    return coll not in OPT_IN_COLLECTIONS or coll in ds


def build_dataset(entities: dict[str, list[dict]], sel: Any, rm: RunMeta) -> dict:
    active = _active_opt_in(entities, sel)
    inactive_colls = {COLLECTION_OF[KIND_OF[k]] for k in OPT_IN if k not in active}
    ds: dict[str, Any] = {COLLECTION_OF[k]: [_strip(e) for e in entities.get(k, [])] for k in KIND_OF.values()
                          if COLLECTION_OF[k] not in inactive_colls}
    pages = [_strip(p) for p in entities.get(PAGE_KIND, [])]
    details = [_strip(d) for d in entities.get(MOTION_DETAIL_KIND, [])]
    _merge_details(ds["motions"], details)
    slugs = {t["id"]: t["slug"] for t in ds["viral_types"] if t.get("slug")}
    for p in ds["viral_presets"]:
        p["type_slugs"] = [slugs[i] for i in p["type_ids"] if i in slugs]
    for coll in ds.values():
        coll.sort(key=lambda e: (e.get("priority") if isinstance(e.get("priority"), (int, float)) else 0,
                                 str(e.get("uid") or e.get("sample_uid") or e.get("id"))))
    ds["soul_samples"].sort(key=lambda s: s.get("created_at") or "", reverse=True)
    pages.sort(key=lambda p: (p["endpoint"], p.get("group") or "", not p["first_page"], p["page_id"]))
    totals = _totals(pages, rm.totals)
    counts = {c: len(ds[c]) for c in COLLECTION_OF.values() if c in ds}
    counts["pages"] = len(pages)
    counts["motion_details"] = len(details)
    endpoints = {e: u for e, u in ENDPOINT_URLS.items()
                 if e not in OPT_IN_ENDPOINTS or SHORT_OF[SOURCE_BY_ENDPOINT[e].kind] in active}
    meta = make_meta("catalog", sel, rm, counts=counts, endpoints=endpoints, totals_available=totals)
    out = {"schema_version": 1, "meta": meta, "summary": _summary(ds, sel, pages, totals), **ds, "pages": pages}
    if not active:
        return CatalogDataset.model_validate(out).model_dump(mode="json")
    return CatalogDatasetFull.model_validate(out).model_dump(mode="json", exclude=inactive_colls)


# ------------------------------------------------------------------ outputs
def _id_of(e: dict) -> dict:
    return {k: e[k] for k in ("uid", "sample_uid", "id") if k in e}


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    tables: dict[str, tuple[list[dict], list[str]]] = {}
    for kind, coll in COLLECTION_OF.items():
        rows = ds.get(coll) or []
        if not rows:
            continue
        first = ["uid", "sample_uid", "id", "motion_id", "name", "slug", "section"]
        tables[coll] = ([row(without(e, *CHILD_LISTS)) for e in rows], first)
        media = [row(m, **{f"parent_{k}": v for k, v in _id_of(e).items()}, position=i)
                 for e in rows for i, m in enumerate(e.get("media") or [])]
        if media:
            tables[f"{coll}_media"] = (media, ["parent_uid", "parent_sample_uid", "parent_id", "position", "role"])
    if ds.get("motions"):
        mix = [row(x, motion_id=m["id"], position=i) for m in ds["motions"] for i, x in enumerate(m.get("mix") or [])]
        if mix:
            tables["motion_mix"] = (mix, ["motion_id", "position", "id", "name"])
    if ds.get("viral_presets"):
        prices = [row(p, preset_id=v["id"], preset_slug=v["slug"]) for v in ds["viral_presets"]
                  for p in v["price_matrix"]]
        inputs = [row(i, preset_id=v["id"], preset_slug=v["slug"], position=n) for v in ds["viral_presets"]
                  for n, i in enumerate(v["inputs"])]
        if prices:
            tables["viral_preset_prices"] = (prices, ["preset_id", "preset_slug", "key", "credit_units"])
        if inputs:
            tables["viral_preset_inputs"] = (inputs, ["preset_id", "preset_slug", "position", "id"])
    if ds.get("chain_presets"):
        inputs = [row(i, preset_id=v["id"], preset_name=v["name"], position=n) for v in ds["chain_presets"]
                  for n, i in enumerate(v["inputs"])]
        if inputs:
            tables["chain_preset_inputs"] = (inputs, ["preset_id", "preset_name", "position", "id"])
    s = ds["summary"]
    if s["soul_sample_styles"]:
        tables["soul_sample_styles"] = ([row(x) for x in s["soul_sample_styles"]], ["style_id", "name"])
    tables["summary_counts"] = ([{"kind": k, "count": s["counts"].get(k, 0),
                                  "total_available": s["totals_available"].get(k),
                                  "login_only": KINDS[k][2], "status": s["login_only"].get(k, "")}
                                 for k in KINDS if _is_opt_in_collection_active(ds, COLLECTION_OF[KIND_OF[k]])],
                                ["kind"])
    tables["summary_by_category"] = ([{"kind": k, "category": c, "count": n} for k, d in s["by_category"].items()
                                      for c, n in d.items()], ["kind"])
    tables["summary_by_model_family"] = ([{"kind": k, "model_family": f, "count": n}
                                          for k, d in s["by_model_family"].items() for f, n in d.items()], ["kind"])
    if ds.get("pages"):
        tables["pages"] = ([row(p) for p in ds["pages"]], ["page_id", "endpoint", "catalog", "group"])
    return tables


def summary_md(ds: dict) -> str:
    m, s = ds["meta"], ds["summary"]
    lines = [f"# Higgsfield catalog — {m['scraped_at'][:19]}Z", "",
             f"run `{m.get('run_id')}` · label `{m.get('label')}` · options `{m['options']}`", "",
             "| kind | items | API total | login-only | status |", "|---|---:|---:|---|---|"]
    for k, (kind, coll, login, desc) in KINDS.items():
        if not _is_opt_in_collection_active(ds, coll):
            continue
        t = s["totals_available"].get(k)
        lines.append(f"| {k} | {s['counts'].get(k, 0)} | {'' if t is None else t} | {'yes' if login else ''} | "
                     f"{s['login_only'].get(k, '')} |")
    lines += ["", f"motions without a preview URL (list placeholders): {s['motions_without_preview']} · "
                  f"motions with details merged: {s['motions_with_details']}", ""]
    if s["by_model_family"]:
        lines += ["## Model families", ""]
        for k, d in s["by_model_family"].items():
            lines.append(f"- **{k}**: " + ", ".join(f"{f} {n}" for f, n in d.items()))
        lines.append("")
    if s["by_category"]:
        lines += ["## Categories", ""]
        for k, d in s["by_category"].items():
            lines.append(f"- **{k}**: " + ", ".join(f"{c} {n}" for c, n in list(d.items())[:25])
                         + (" …" if len(d) > 25 else ""))
        lines.append("")
    if s["soul_sample_styles"]:
        lines += [f"## Soul styles referenced by samples ({len(s['soul_sample_styles'])})", ""]
        lines += [f"- {x['name']} ({x['samples']})" for x in s["soul_sample_styles"][:20]]
        lines.append("")
    if m["limits_hit"]:
        lines += ["## Limits hit", ""] + [f"- {x}" for x in m["limits_hit"]] + [""]
    if m["warnings"]:
        lines += ["## Warnings", ""] + [f"- {x}" for x in m["warnings"]] + [""]
    return "\n".join(lines) + "\n"


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    parts: dict[str, Any] = {c: ds[c] for c in COLLECTION_OF.values() if ds.get(c)}
    model = CatalogDatasetFull if any(c in ds for c in OPT_IN_COLLECTIONS) else CatalogDataset
    parts["summary"] = ds["summary"]
    parts["pages"] = ds["pages"]
    return write_standard_outputs(ds, Path(out_dir), json_parts=parts, csv_tables=csv_tables(ds),
                                  dataset_model=model, summary_md=summary_md(ds))
