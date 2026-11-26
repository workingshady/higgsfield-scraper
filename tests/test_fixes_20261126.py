"""Regression tests for the 2026-11-26 fixes.

1. projects: `normalize` of a --max-items run failed with `contests.0.listing: Extra inputs are not permitted`.
   The normalize budget keeps list rows of the first primary kind only (publications), so a contest *detail* lost
   its list row and `_merge` added the publication-only `listing="detail"` fallback to it.
   Fixture: tests/fixtures/fixes/projects_contest_detail_20261125.json = the raw contest detail of
   runs/20261125-131446_projects-smoke (trimmed: rules markdown, prizes, timeline; studio handle redacted).
2. catalog: `schema` export documents the opt-in collections; the per-run schema of a default run is unchanged.
3. account: `scrape account --dry-run` lists the planned requests when a session is configured (offline check).
"""
from __future__ import annotations

import json
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.raw import Envelope

FIXES = Path(__file__).parent / "fixtures" / "fixes"
PROJECTS = Path(__file__).parent / "fixtures" / "projects"
OLD_DETAIL = "projects_contest_detail_20261125.json"
CONTEST_ID = "4263b5fb-fead-441d-aa37-62f8aa367aa1"


# ------------------------------------------------------------------ 1. projects normalize
def _parse(paths, sel):
    from higgsfield_scraper.scrapers.projects.parsers import keep, parse_envelope
    from higgsfield_scraper.validation import validate_entity
    out: dict[str, list[dict]] = {}
    for p in paths:
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                out.setdefault(v["kind"], []).append(v)
    return out


def test_contest_detail_without_list_row_builds():
    from higgsfield_scraper.scrapers.projects import SCRAPER
    from higgsfield_scraper.scrapers.projects.options import Selection
    sel = Selection.build()
    ents = _parse([FIXES / OLD_DETAIL], sel)
    assert set(ents) == {"projects_contest_detail"}
    ds = SCRAPER.build_dataset(ents, sel, RunMeta())          # raised ValidationError before the fix
    (c,) = ds["contests"]
    assert c["contest_id"] == CONTEST_ID and c["detail_fetched"] is True and "listing" not in c
    assert c["slug"] == "higgsfield-global-film-festival" and c["prize_pool_unit"] == "usd"


def test_publication_detail_without_list_row_keeps_listing_detail():
    """Unchanged behaviour: a publication detail without its list row still gets listing='detail'."""
    from higgsfield_scraper.scrapers.projects import SCRAPER
    from higgsfield_scraper.scrapers.projects.options import Selection
    sel = Selection.build()
    ents = _parse([PROJECTS / "publication_detail_film.json"], sel)
    ds = SCRAPER.build_dataset(ents, sel, RunMeta())
    assert ds["publications"] and all(p["listing"] == "detail" for p in ds["publications"])


def test_contest_list_plus_detail_merge_unchanged():
    from higgsfield_scraper.scrapers.projects import SCRAPER
    from higgsfield_scraper.scrapers.projects.options import Selection
    sel = Selection.build()
    ents = _parse([PROJECTS / "contests_global.json", FIXES / OLD_DETAIL], sel)
    ds = SCRAPER.build_dataset(ents, sel, RunMeta())
    c = next(c for c in ds["contests"] if c["contest_id"] == CONTEST_ID)
    assert c["detail_fetched"] is True and c["detail_source"]["endpoint"] == "projects_contest_detail"
    assert "listing" not in c


def test_normalize_max_items_run_with_contest_detail(tmp_path):
    """End to end, like `normalize --run runs/20261125-131446_projects-smoke`: max_items spent on publications,
    so the contest list rows are cut to 0 while the contest detail stays."""
    from higgsfield_scraper.run.context import latest_run
    from higgsfield_scraper.run.manager import RunManager
    from higgsfield_scraper.scrapers.projects.options import Selection
    src = tmp_path / "runs" / "20261125-131446_fixture"
    (src / "raw").mkdir(parents=True)
    for p in (FIXES / OLD_DETAIL, PROJECTS / "contests_global.json", PROJECTS / "publications_p1.json"):
        shutil.copy(p, src / "raw" / p.name)
    mgr = RunManager(tmp_path / "runs", "norm", "ERROR")
    rc = mgr.normalize(src, Selection.build(), scraper="projects", common=CommonOptions(max_items=1))
    assert rc == 0
    ds = json.loads((latest_run(tmp_path / "runs") / "output" / "dataset.json").read_text("utf-8"))
    assert len(ds["publications"]) == 1
    assert [c["contest_id"] for c in ds["contests"]] == [CONTEST_ID] and "listing" not in ds["contests"][0]


# ------------------------------------------------------------------ 2. catalog schema export
def test_catalog_schema_export_includes_opt_in_collections(tmp_path):
    from higgsfield_scraper.cli import cmd_schema
    from higgsfield_scraper.scrapers.catalog import SCRAPER
    from higgsfield_scraper.scrapers.catalog.schemas import CatalogDataset, CatalogDatasetFull
    assert SCRAPER.dataset_model is CatalogDatasetFull
    assert cmd_schema(Namespace(out=str(tmp_path))) == 0
    exported = json.loads((tmp_path / "catalog.dataset.schema.json").read_text("utf-8"))
    for coll in ("chain_presets", "notices", "restyle_presets"):
        assert coll in exported["properties"]
    # superset: every CatalogDataset property is exported exactly as before
    base = CatalogDataset.model_json_schema(mode="serialization")
    assert {k: exported["properties"][k] for k in base["properties"]} == base["properties"]
    assert all(exported["$defs"][k] == v for k, v in base["$defs"].items())


def test_catalog_default_run_schema_still_catalog_dataset(tmp_path):
    from higgsfield_scraper.scrapers.catalog import SCRAPER
    from higgsfield_scraper.scrapers.catalog.options import build
    from higgsfield_scraper.scrapers.catalog.schemas import CatalogDataset
    sel = build()
    ds = SCRAPER.build_dataset({}, sel, RunMeta())
    SCRAPER.write_outputs(ds, tmp_path)
    per_run = json.loads((tmp_path / "schema" / "dataset.schema.json").read_text("utf-8"))
    assert per_run == CatalogDataset.model_json_schema(mode="serialization")


# ------------------------------------------------------------------ 3. account dry-run
def _dry(capsys, monkeypatch, configured: bool, *extra: str) -> tuple[str, str]:
    from higgsfield_scraper.cli import main
    from higgsfield_scraper.core import auth

    class FakeProvider:
        def __init__(self, *a, **k):
            pass

        configured = property(lambda self: True if CONF else False)

        def get(self, *a, **k):                                   # minting must never happen in a dry run
            raise AssertionError("token requested during dry-run")

    CONF = configured
    monkeypatch.setattr(auth.TokenProvider, "from_env", classmethod(lambda cls, token=None: FakeProvider()))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    rc = main(["scrape", "account", "--dry-run", *extra])
    assert rc in (0, None)
    out = capsys.readouterr()
    return out.out, out.err


def test_account_dry_run_with_session_lists_requests(capsys, monkeypatch):
    out, err = _dry(capsys, monkeypatch, True, "--with-jobs", "--max-items", "5")
    lines = out.splitlines()
    assert any(l.endswith("/fnf/user   [auth]") for l in lines)
    assert any("/fnf/jobs/accessible?size=5" in l for l in lines)
    assert all(l.startswith("GET ") for l in lines) and "needs a login session" not in out + err


@pytest.mark.parametrize("extra", [(), ("--auth", "off")])
def test_account_dry_run_without_session_keeps_message(capsys, caplog, monkeypatch, extra):
    configured = bool(extra)          # --auth off: no session even if one is configured
    out, err = _dry(capsys, monkeypatch, configured, *extra)
    assert "GET " not in out and "needs a login session" in out + err + caplog.text
