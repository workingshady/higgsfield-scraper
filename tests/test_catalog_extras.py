"""Catalog opt-in extras (chain_preset, notice, restyle_preset): parsers, options, spider, dataset/CSV, and the
guarantee that runs without them keep the pre-existing output. Fixtures: tests/fixtures/catalog_extras/ (real
responses 2026-11-26, trimmed; creator credit replaced, placeholders shortened)."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.core.exporting import flatten
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.catalog import SCRAPER
from higgsfield_scraper.scrapers.catalog.endpoints import (DEFAULT_PUBLIC, KINDS, LOGIN_ONLY, OPT_IN, PUBLIC,
                                                           SOURCE_BY_ENDPOINT)
from higgsfield_scraper.scrapers.catalog.options import build, default_label, parse_kinds, selection_from_dict
from higgsfield_scraper.scrapers.catalog.parsers import next_params, parse_envelope
from higgsfield_scraper.scrapers.catalog.schemas import CatalogDataset
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "catalog_extras"
BASE_FX = Path(__file__).parent / "fixtures" / "catalog"


def load(name: str) -> Envelope:
    return Envelope.load(FX / name)


def of(entities, kind):
    return [e for e in entities if e["kind"] == kind]


def collect(sel, *dirs) -> dict[str, list[dict]]:
    """Parse + validate + dedup (first wins, files in name order) like the pipelines / normalize."""
    out, seen = defaultdict(list), set()
    ids = SCRAPER.id_field_by_kind
    for d in dirs:
        for p in sorted(d.glob("*.json")):
            for e in parse_envelope(Envelope.load(p), sel):
                if not SCRAPER.keep(e, sel):
                    continue
                v = validate_entity(e)
                key = (v["kind"], v.get(ids.get(v["kind"], "")))
                if key in seen:
                    continue
                seen.add(key)
                out[v["kind"]].append(v)
    return out


# ------------------------------------------------------------------ kind groups / options
def test_opt_in_kinds_are_not_in_default_public_or_login():
    for k in OPT_IN:
        assert k in KINDS and k not in DEFAULT_PUBLIC and k not in PUBLIC and k not in LOGIN_ONLY
    assert build().resolve_kinds(False) == list(DEFAULT_PUBLIC)
    assert not set(build(include_login_only="yes").resolve_kinds(True)) & set(OPT_IN)
    assert not set(parse_kinds("public")) & set(OPT_IN) and not set(parse_kinds("login")) & set(OPT_IN)
    assert set(OPT_IN) <= set(build(kinds="all").resolve_kinds(False))
    assert build(kinds="chain_preset,notices,restyle-preset").resolve_kinds(False) == list(OPT_IN)


def test_late_options_hidden_from_to_dict_at_default():
    d = build().to_dict()
    assert "include_hidden" not in d and "with_profiles" not in d          # default meta.options unchanged
    s = build(kinds="chain_preset", include_hidden=True, with_profiles=True)
    assert s.to_dict()["include_hidden"] is True and selection_from_dict(s.to_dict()) == s
    assert default_label(s) == "chain_preset-hidden" and default_label(build()) == "public"


# ------------------------------------------------------------------ parsers
def test_chain_presets():
    sel = build(kinds="chain_preset")
    es = parse_envelope(load("catalog_chain_presets__lang-en.json"), sel)
    ps = {p["name"]: p for p in of(es, "catalog_chain_preset")}
    b = ps["BASEBALL GAME"]
    assert b["cost_credits"] == 10 and b["discount_credits"] == 14 and b["is_discounted"] is True
    assert isinstance(b["cost_credits"], int)                                 # credits, numeric (no ÷100)
    assert b["model"] and b["runtime"] == "preset_chain" and b["chain_type"] == "game_character_creator"
    assert b["runtime_endpoint"].startswith("/chains/") and b["inputs"][0]["type"] == "image"
    assert b["inputs"][0]["min"] == b["inputs"][0]["max"] == 1
    assert b["is_hidden"] is False and b["lang"] == "en" and b["extra"] == {}
    assert b["image_preview_url"] is None                                      # API image_preview = {} (36 of 58)
    assert {"preview", "preview_main"} <= {m["role"] for m in b["media"]}
    assert ps["MOONWALK"]["image_preview_url"] and "image_preview" in {m["role"] for m in ps["MOONWALK"]["media"]}
    assert b["source_url"].startswith("https://fnf-api-gw.higgsfield.ai/fnf-cms-api/job-set-chain-presets")
    assert b["scraped_at"] and b["schema_version"] == 1
    assert ps["MOONWALK"]["pricing_mode"] == "dynamic_chain"
    o = ps["ORBITAL PRESENCE"]
    assert o["has_collaborator"] is True and o["collaborator"] is None        # person redacted by default
    assert o["is_discounted"] is False
    v = validate_entity(b)
    assert v["cost_credits"] == 10
    prof = parse_envelope(load("catalog_chain_presets__lang-en.json"), build(kinds="chain_preset", with_profiles=True))
    assert {p["name"]: p for p in of(prof, "catalog_chain_preset")}["ORBITAL PRESENCE"]["collaborator"] == \
        "example_creator"


def test_chain_presets_hidden_marked_and_visible_rows_win():
    sel = build(kinds="chain_preset", include_hidden=True)
    ents = collect(sel, FX)["catalog_chain_preset"]
    hidden = {p["name"] for p in ents if p["is_hidden"]}
    visible = {p["name"] for p in ents if not p["is_hidden"]}
    assert visible == {"BASEBALL GAME", "ORBITAL PRESENCE", "MOONWALK"}
    assert hidden == {"CLOUD KEEPER", "MAGIC MAKEUP"} and len(ents) == 5


def test_notices():
    es = parse_envelope(load("catalog_notices__lang-en.json"), build(kinds="notice"))
    ns = of(es, "catalog_notice")
    assert len(ns) == 5 and {n["section"] for n in ns} == {"header", "job_set"}
    sd = next(n for n in ns if n["job_set_types"] == ["seedance1_5"])
    assert "retired" in sd["badge_label"] and sd["popup_title"] and sd["variant"] == "info" and sd["lang"] == "en"
    assert len(sd["id"]) == 16 and len({n["id"] for n in ns}) == 5            # hashed, unique
    again = of(parse_envelope(load("catalog_notices__lang-en.json"), build(kinds="notice")), "catalog_notice")
    assert [n["id"] for n in again] == [n["id"] for n in ns]                  # stable
    h = next(n for n in ns if n["section"] == "header")
    assert h["title"] == "Example header" and h["link"] == "/pricing" and h["extra"]["config"]
    page = of(es, "catalog_page")[0]
    assert page["item_count"] == 5
    for n in ns:
        validate_entity(n)


def test_restyle_presets_and_pagination():
    es = parse_envelope(load("catalog_restyle_presets__lang-en__size-2.json"), build(kinds="restyle_preset"))
    rs = of(es, "catalog_restyle_preset")
    assert [r["name"] for r in rs] == ["Mission", "Classic Cel"]
    c = rs[1]
    assert c["preset_source"] == "higgsfield" and c["job_set_type"] == "restyle" and c["variants"]
    assert any(m["role"].startswith("variant_") for m in c["media"]) and c["image_count"] >= 1
    assert all(m["placeholder"] is None for r in rs for m in r["media"] if "placeholder" in m)
    assert of(es, "catalog_page")[0]["total"] == 21
    src = SOURCE_BY_ENDPOINT["catalog_restyle_presets"]
    body = load("catalog_restyle_presets__lang-en__size-2.json").body
    assert next_params(src, body, {"size": "2", "lang": "en"}, 2) == {"size": "2", "lang": "en", "cursor": "2"}
    assert next_params(src, {"items": [1], "cursor": None, "total": 21}, {"size": "100"}, 1) is None


# ------------------------------------------------------------------ spider
def make_spider(sel, **common):
    from higgsfield_scraper.scrapers.catalog.spider import CatalogSpider
    return CatalogSpider(selection=sel, common=CommonOptions(**{"auth": "off", **common}))


def test_spider_requests():
    reqs = {r.meta["endpoint"]: r for r in make_spider(build(kinds="chain_preset,notice,restyle_preset")).build_requests()}
    assert set(reqs) == {"catalog_chain_presets", "catalog_notices", "catalog_restyle_presets"}
    assert reqs["catalog_chain_presets"].url == \
        "https://fnf-api-gw.higgsfield.ai/fnf-cms-api/job-set-chain-presets?lang=en"
    assert reqs["catalog_notices"].url == "https://cms.higgsfield.ai/notices?lang=en"
    assert reqs["catalog_restyle_presets"].url == \
        "https://fnf-api-gw.higgsfield.ai/fnf-cms-api/restyle-presets?size=100&lang=en"
    assert not any(r.meta["auth"] for r in reqs.values())
    de = [r.url for r in make_spider(build(kinds="notice", lang="de")).build_requests()]
    assert de == ["https://cms.higgsfield.ai/notices?lang=de"]
    small = [r.url for r in make_spider(build(kinds="restyle_preset"), page_size=5).build_requests()]
    assert "size=5" in small[0]
    # default run: none of them
    assert not {r.meta["endpoint"] for r in make_spider(build()).build_requests()} & set(reqs)


def test_spider_hidden_list_follows_visible_list():
    sp = make_spider(build(kinds="chain_preset", include_hidden=True))
    first = list(sp.build_requests())
    assert [r.meta["endpoint"] for r in first] == ["catalog_chain_presets"]   # hidden list never first
    env = load("catalog_chain_presets__lang-en.json")
    out = list(sp.follow_up(env, parse_envelope(env, sp.selection), SimpleNamespace(meta=first[0].meta)))
    assert [r.meta["endpoint"] for r in out] == ["catalog_chain_presets_hidden"]
    assert "show_hidden=true" in out[0].url and "lang=en" in out[0].url
    sp2 = make_spider(build(kinds="chain_preset"))
    r0 = next(iter(sp2.build_requests()))
    assert list(sp2.follow_up(env, parse_envelope(env, sp2.selection), SimpleNamespace(meta=r0.meta))) == []


def test_spider_max_pages_stops_restyle_paging():
    sp = make_spider(build(kinds="restyle_preset"), max_pages=1)
    first = next(iter(sp.build_requests()))
    sp.pages["catalog_restyle_presets"] = 1
    env = load("catalog_restyle_presets__lang-en__size-2.json")
    out = list(sp.follow_up(env, parse_envelope(env, sp.selection), SimpleNamespace(meta=first.meta)))
    assert out == [] and any("max_pages=1" in x for x in sp.limits_hit)


# ------------------------------------------------------------------ dataset / outputs
def _csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return set(rows[0].keys()) if rows else set(), rows


def test_default_dataset_has_no_opt_in_traces(tmp_path):
    sel = build(with_samples=True, with_details=True)
    ds = SCRAPER.build_dataset(collect(sel, BASE_FX), sel, RunMeta())
    for coll in ("chain_presets", "notices", "restyle_presets"):
        assert coll not in ds and coll not in ds["meta"]["counts"]
    assert not any(e in ds["meta"]["endpoints"] for e in ("catalog_chain_presets", "catalog_notices"))
    assert set(ds) == set(CatalogDataset.model_fields)
    SCRAPER.write_outputs(ds, tmp_path)
    kinds = {r["kind"] for r in _csv(tmp_path / "csv" / "summary_counts.csv")[1]}
    assert not kinds & set(OPT_IN)
    md = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "chain_preset" not in md and "restyle_preset" not in md
    assert '"chain_presets"' not in (tmp_path / "schema" / "dataset.schema.json").read_text(encoding="utf-8")


def test_opt_in_dataset_and_csvs(tmp_path):
    sel = build(kinds="chain_preset,notice,restyle_preset", include_hidden=True)
    ds = SCRAPER.build_dataset(collect(sel, FX), sel, RunMeta(scraped_at=datetime(2026, 11, 26, tzinfo=timezone.utc)))
    assert len(ds["chain_presets"]) == 5 and len(ds["notices"]) == 5 and len(ds["restyle_presets"]) == 2
    assert ds["summary"]["counts"] == {"chain_preset": 5, "notice": 5, "restyle_preset": 2}
    assert ds["meta"]["endpoints"]["catalog_chain_presets_hidden"].endswith("/job-set-chain-presets")
    only_notice = build(kinds="notice")
    ds2 = SCRAPER.build_dataset(collect(only_notice, FX), only_notice, RunMeta())
    assert "notices" in ds2 and "chain_presets" not in ds2 and "restyle_presets" not in ds2
    SCRAPER.write_outputs(ds, tmp_path)
    drop = lambda d, *ks: {k: v for k, v in d.items() if k not in ks}  # noqa: E731
    checks = {"chain_presets": [drop(e, "media", "inputs") for e in ds["chain_presets"]],
              "notices": [drop(e, "media") for e in ds["notices"]],
              "restyle_presets": [drop(e, "media") for e in ds["restyle_presets"]],
              "chain_presets_media": [m for e in ds["chain_presets"] for m in e["media"]],
              "restyle_presets_media": [m for e in ds["restyle_presets"] for m in e["media"]],
              "chain_preset_inputs": [i for e in ds["chain_presets"] for i in e["inputs"]]}
    for table, objects in checks.items():
        cols, rows = _csv(tmp_path / "csv" / f"{table}.csv")
        assert len(rows) == len(objects), table
        missing = {k for o in objects for k in flatten(o)} - cols
        missing = {k for k in missing if not any(c.startswith(k + ".") for c in cols)}
        assert not missing, f"{table}.csv is missing JSON fields: {sorted(missing)[:10]}"
    kinds = {r["kind"] for r in _csv(tmp_path / "csv" / "summary_counts.csv")[1]}
    assert set(OPT_IN) <= kinds
    assert '"chain_presets"' in (tmp_path / "schema" / "dataset.schema.json").read_text(encoding="utf-8")


def test_max_items_caps_opt_in_kind():
    sp = make_spider(build(kinds="chain_preset"), max_items=2)
    first = next(iter(sp.build_requests()))
    from scrapy.http import TextResponse, Request
    env = load("catalog_chain_presets__lang-en.json")
    import json
    resp = TextResponse(url=first.url, body=json.dumps(env.body).encode(), encoding="utf-8",
                        request=Request(first.url, meta=first.meta))
    sp.crawler = SimpleNamespace(stats=SimpleNamespace(inc_value=lambda *a, **k: None))
    items = [x for x in sp.parse_api(resp) if hasattr(x, "get") and x.get("kind") == "catalog_chain_preset"]
    assert len(items) == 2 and any("max_items=2" in x for x in sp.limits_hit)
