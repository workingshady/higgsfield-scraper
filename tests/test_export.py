"""Offline tests for the export feature (higgsfield_scraper/export) on small synthetic run folders."""
from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tracemalloc
from pathlib import Path

import pytest

from higgsfield_scraper import cli
from higgsfield_scraper.export import ExportOptions, parse_filters, run_export
from higgsfield_scraper.export import stream
from higgsfield_scraper.export.paths import (RESERVED, WIN_PATH_LIMIT, NameRegistry, fit_parts, safe_component,
                                             slug)
from higgsfield_scraper.export.reader import expand_runs

CDN = "https://d8j0ntlcm91z4.cloudfront.net/user_x"
U = "{:08x}-0000-4000-8000-{:012x}"


def uid(n: int, salt: int = 0) -> str:
    return U.format(salt, n)


def make_run(root: Path, name: str, scraper: str, tables: dict[str, list], media: dict[str, bytes] | None = None,
             extra_files: dict[str, str] | None = None) -> Path:
    run = root / "runs" / name
    (run / "output" / "json").mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"scraper": scraper, "status": "success",
                                                   "args": {"max_media_files": 500, "max_media_mb": 1024}}),
                                       encoding="utf-8")
    meta = {"schema_version": 1, "meta": {"scraper": scraper, "run_id": name, "scraped_at": "2026-11-26T10:00:00Z"}}
    (run / "output" / "json" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    for t, rows in tables.items():
        (run / "output" / "json" / f"{t}.json").write_text(json.dumps(rows, indent=4), encoding="utf-8")
    (run / "output" / "dataset.json").write_text(json.dumps({**meta, **tables}), encoding="utf-8")
    for rel, text in (extra_files or {}).items():
        p = run / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if media:
        (run / "media" / "x").mkdir(parents=True)
        with (run / "media" / "index.jsonl").open("w", encoding="utf-8") as f:
            for i, (url, body) in enumerate(media.items()):
                rel = f"media/x/f{i}{os.path.splitext(url.split('?')[0])[1]}"
                (run / rel).write_bytes(body)
                f.write(json.dumps({"kind": "x", "owner": "o", "role": "r", "url": url, "file": rel,
                                    "bytes": len(body)}) + "\n")
    return run


def projects_tables(folder_names=("Cast", "Locations", "Scenes")) -> dict[str, list]:
    pub = uid(1, 9)
    root_f = uid(100, 9)
    folders = [{"folder_id": root_f, "parent_id": None, "is_root": True, "name": "The Sea", "publication_id": pub}]
    assets = []
    for i, fname in enumerate(folder_names):
        fid = uid(200 + i, 9)
        folders.append({"folder_id": fid, "parent_id": root_f, "is_root": False, "name": fname,
                        "publication_id": pub})
        for j in range(2):
            aid = uid(1000 + i * 10 + j, 9)
            assets.append({"placement_id": uid(5000 + i * 10 + j, 9), "asset_id": aid, "publication_id": pub,
                           "root_folder_id": root_f, "folder_id": fid, "folder_path": fname, "position": j,
                           "media_type": "image", "model_name": "Seedream 5.0", "job_set_type": "seedream_v5",
                           "prompt": f"prompt {fname} {j}" if j == 0 else None,
                           "url": f"{CDN}/hf_{aid}.png", "thumbnail_url": f"{CDN}/hf_{aid}_min.webp",
                           "source_url": "https://api.example/x", "scraped_at": "2026-11-26T10:00:00Z",
                           "schema_version": 1, "owner_key": "abc123"})
    return {
        "publications": [{"publication_id": pub, "slug": "the-sea-walks-out", "name": "The Sea Walks Out",
                          "contest_key": "talent_contest", "cover_url": f"{CDN}/{uid(7, 9)}.png"}],
        "folders": folders, "assets": assets,
        "briefs": [{"brief_id": root_f, "publication_id": pub, "markdown": "## Story\nA sea walks out."}],
        "comments": [{"comment_id": uid(1, 3), "publication_id": pub, "parent_id": None, "text": "Lovely",
                      "created_at": "2026-11-25T01:00:00Z", "likes": 2, "author": {"author_key": "k1",
                                                                                     "username": None}},
                     {"comment_id": uid(2, 3), "publication_id": pub, "parent_id": uid(1, 3), "text": "Thanks",
                      "created_at": "2026-11-25T02:00:00Z", "likes": 0, "author": {"author_key": "k2"}}],
        "project_stats": [{"publication_id": pub, "generations_count": 6, "credits_spent": 12.5}],
        "stack_items": [{"stack_item_id": "s1", "publication_id": pub, "position": 0, "display_name": "Seedream"}],
        "contests": [{"contest_id": uid(1, 4), "slug": "talent-contest"}],
    }


def tree_hash(root: Path) -> dict[str, tuple[str, int]]:
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def opts(runs, out, **kw) -> ExportOptions:
    return ExportOptions(runs=[Path(r) for r in runs], out=Path(out), log=lambda s: None, **kw)


@pytest.fixture
def proj_run(tmp_path):
    t = projects_tables()
    a0 = t["assets"][0]
    return make_run(tmp_path, "20261126-000001_proj", "projects", t,
                    media={a0["url"]: b"PNGDATA0", t["assets"][2]["thumbnail_url"]: b"WEBP2"})


# ------------------------------------------------------------------------------------------------ layouts
def test_tree_layout_projects(proj_run, tmp_path):
    before = tree_hash(proj_run)
    out = tmp_path / "exp"
    r = run_export(opts([proj_run], out))
    proj = out / "talent_contest" / "the-sea-walks-out"
    for f in ("project.json", "brief.md", "comments.md", "stats.json"):
        assert (proj / f).is_file(), f
    for folder in ("Cast", "Locations", "Scenes"):
        assert (proj / folder / "metadata.jsonl").is_file()
        assert (proj / folder / "prompts.csv").is_file()
    rows = [json.loads(x) for x in (proj / "Cast" / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and rows[0]["file_name"] and rows[0]["record"]["asset_id"]
    media = proj / "Cast" / rows[0]["file_name"]
    assert media.read_bytes() == b"PNGDATA0"
    assert media.with_suffix(".txt").read_text(encoding="utf-8").strip() == "prompt Cast 0"   # same-stem caption
    assert "**k1**" in (proj / "comments.md").read_text(encoding="utf-8")
    assert "  - **k2**" in (proj / "comments.md").read_text(encoding="utf-8")              # threaded reply
    assert (out / "_tables" / "contests.jsonl").is_file()
    man = json.loads((out / "export_manifest.json").read_text(encoding="utf-8"))
    assert man["layout"] == "tree" and man["runs"][0]["scraper"] == "projects"
    assert all(len(v["sha256"]) == 64 for v in man["files"].values())
    assert "## Licensing" in (out / "README.md").read_text(encoding="utf-8")
    assert (out / "errors.log").exists()
    assert r.counts["media_files"] == 2
    assert tree_hash(proj_run) == before                                    # run folder untouched


def test_hf_layout(proj_run, tmp_path):
    out = tmp_path / "hf"
    run_export(opts([proj_run], out, layout="hf"))
    md = out / "images" / "train" / "metadata.jsonl"
    rows = [json.loads(x) for x in md.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    for r in rows:
        assert (md.parent / r["file_name"]).is_file()                      # ImageFolder contract
        assert r["source_url"] and r["run_id"] and "record" not in r       # flat, Arrow-friendly
        assert isinstance(r["params_json"], (str, type(None)))
    allrows = (out / "urls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(allrows) == 7                                               # 6 assets + 1 publication


def test_webdataset_layout(proj_run, tmp_path):
    out = tmp_path / "wds"
    run_export(opts([proj_run], out, layout="webdataset", shard_mb=0.002))  # tiny shards -> several
    shards = sorted((out / "shards").glob("shard-*.tar"))
    assert len(shards) >= 2
    names = []
    for s in shards:
        with tarfile.open(s) as t:
            names += t.getnames()
    keys = {n.split(".")[0] for n in names}
    assert all(f"{k}.json" in names for k in keys)                         # every sample has metadata
    assert any(n.endswith(".png") for n in names) and any(n.endswith(".txt") for n in names)
    for k in keys:                                                          # members of a sample are adjacent
        idx = [i for i, n in enumerate(names) if n.split(".")[0] == k]
        assert idx == list(range(idx[0], idx[0] + len(idx)))
    assert (out / "index.jsonl").is_file()


def test_jsonl_layout_and_generation_dedup(tmp_path):
    vid = uid(42, 7)
    comm = make_run(tmp_path, "r1", "community", {"generations": [
        {"generation_id": vid, "publication_id": uid(1, 1), "prompt": "a cat", "media_type": "video",
         "model_id": "kling", "results": [{"name": "raw", "type": "video", "url": f"{CDN}/hf_{vid}.mp4"}]}]})
    show = make_run(tmp_path, "r2", "showcase", {"explore_variants": [
        {"id": "v1", "variant_id": "v1", "generation_key": f"job:{vid}", "media_keys": [f"media:{vid}"],
         "prompt": "a cat", "media": [{"role": "output", "url": f"{CDN}/hf_{vid}.mp4"}]},
        {"id": "v2", "variant_id": "v2", "generation_key": f"job:{uid(43, 7)}", "prompt": "a dog",
         "media": [{"role": "output", "url": f"{CDN}/hf_{uid(43, 7)}.mp4"}]}]})
    out = tmp_path / "j"
    r = run_export(opts([comm, show], out, layout="jsonl"))
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and r.counts["duplicates"] == 1
    cat = next(x for x in rows if x["prompt"] == "a cat")
    assert cat["dedup_records"] == 2 and set(cat["dedup_sources"]) == {"community:generations",
                                                                       "showcase:explore_variants"}


def test_record_dedup_across_runs(proj_run, tmp_path):
    t = projects_tables()
    run2 = make_run(tmp_path, "20261126-000002_proj", "projects", t)
    out = tmp_path / "tw"
    r = run_export(opts([proj_run, run2], out))
    assert r.counts["records_read"] == 14 and r.counts["unique"] == 7
    lines = (out / "talent_contest" / "the-sea-walks-out" / "Cast" / "metadata.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert sorted(json.loads(lines[0])["dedup"]["runs"]) == ["20261126-000001_proj", "20261126-000002_proj"]


# ------------------------------------------------------------------------------------------------ names / paths
@pytest.mark.parametrize("raw", ["CON", "nul", "Aux.txt", "COM1", "lpt9.md", "COM¹"])
def test_reserved_names(raw):
    s = safe_component(raw)
    assert s.split(".")[0].upper() not in RESERVED


@pytest.mark.parametrize("raw,bad", [('a<b>:c"d/e\\f|g?h*', '<>:"/\\|?*'), ("trailing. . ", None),
                                     ("tab\tnew\nline\x00", "\t\n\x00")])
def test_illegal_chars(raw, bad):
    s = safe_component(raw)
    assert s and not s.endswith((".", " "))
    if bad:
        assert not any(c in s for c in bad)


def test_unicode_nfc_and_length():
    nfd = "Café Ле́то"
    assert safe_component(nfd) == safe_component("Café Ле́то".encode().decode())
    import unicodedata
    assert unicodedata.is_normalized("NFC", safe_component(nfd))
    long = "x" * 500
    s = safe_component(long, max_chars=60)
    assert len(s) <= 60 and s != safe_component("x" * 499, max_chars=60)    # hash keeps them distinct
    assert len(safe_component("é" * 300, max_chars=300).encode("utf-8")) <= 255


def test_case_collisions_registry():
    reg = NameRegistry()
    assert reg.claim("p", "Cast", "a") == "Cast"
    assert reg.claim("p", "cast", "b") == "cast~2"
    assert reg.claim("p", "Cast", "a") == "Cast"                            # stable for the same owner
    assert reg.claim("p", "x.png", "c") == "x.png" and reg.claim("p", "X.PNG", "d") == "X~2.PNG"


def test_fit_parts_limits_path(tmp_path):
    parts = ["a" * 80, "b" * 80, "c" * 80, "d" * 80]
    fitted = fit_parts(tmp_path, parts, "metadata.jsonl")
    assert len(str(tmp_path)) + sum(len(p) + 1 for p in fitted) + 15 <= WIN_PATH_LIMIT or \
        all(len(p) <= 13 for p in fitted)
    assert len(set(fitted)) == 4


def test_unsafe_folder_names_end_to_end(tmp_path):
    names = ("CON", "a<b>:c?", "Cast", "cast", "x" * 200, "Scenes / Act 1", "aux.txt", "trailing.")
    run = make_run(tmp_path, "r", "projects", projects_tables(folder_names=names))
    out = tmp_path / "o"
    run_export(opts([run], out))
    proj = out / "talent_contest" / "the-sea-walks-out"
    dirs = [p.name for p in proj.iterdir() if p.is_dir()]
    assert len(dirs) == len(names)                                          # Cast and cast stay separate
    for d in dirs:
        assert d.split(".")[0].upper() not in RESERVED and not any(c in d for c in '<>:"/\\|?*')
        assert not d.endswith((".", " ")) and len(d) <= 60
    for p in out.rglob("*"):
        assert len(str(p.resolve())) <= WIN_PATH_LIMIT + len(".export-tmp")   # under Windows MAX_PATH (260)
    assert slug("Seedance 2.5 / Pro") == "seedance-2-5-pro"


# ------------------------------------------------------------------------------------------------ idempotency etc.
def test_idempotent_rerun(proj_run, tmp_path):
    out = tmp_path / "idem"
    run_export(opts([proj_run], out))
    first = tree_hash(out)
    r2 = run_export(opts([proj_run], out))
    assert r2.sink_stats["written"] == 0 and r2.sink_stats["removed"] == 0
    assert tree_hash(out) == first                                          # bytes AND mtimes unchanged


def test_webdataset_idempotent(proj_run, tmp_path):
    out = tmp_path / "w"
    run_export(opts([proj_run], out, layout="webdataset"))
    first = tree_hash(out)
    run_export(opts([proj_run], out, layout="webdataset"))
    assert tree_hash(out) == first


def test_stale_files_removed(proj_run, tmp_path):
    out = tmp_path / "st"
    run_export(opts([proj_run], out))
    assert (out / "talent_contest" / "the-sea-walks-out" / "Scenes").exists()
    r = run_export(opts([proj_run], out, filters=parse_filters("folder_path=Cast"), only={"assets"}))
    assert r.sink_stats["removed"] > 0
    assert not (out / "talent_contest" / "the-sea-walks-out" / "Scenes").exists()


def test_dry_run_writes_nothing(proj_run, tmp_path):
    out = tmp_path / "dry"
    for layout in ("tree", "hf", "webdataset", "jsonl"):
        r = run_export(opts([proj_run], out, layout=layout, dry_run=True))
        assert r.dry_run and r.files > 0
    assert not out.exists()


def test_refuses_foreign_or_run_dirs(proj_run, tmp_path):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("x")
    with pytest.raises(ValueError, match="not an export"):
        run_export(opts([proj_run], foreign))
    with pytest.raises(ValueError, match="inside the run folder"):
        run_export(opts([proj_run], proj_run / "export"))
    out = tmp_path / "lay"
    run_export(opts([proj_run], out))
    with pytest.raises(ValueError, match="--force"):
        run_export(opts([proj_run], out, layout="jsonl"))
    run_export(opts([proj_run], out, layout="jsonl", force=True))
    assert not (out / "talent_contest").exists()                            # old layout's files pruned


def test_generic_profile_unknown_scraper(tmp_path):
    run = make_run(tmp_path, "r", "brand_new_scraper", {
        "widgets": [{"widget_id": "w1", "name": "Widget", "image_url": f"{CDN}/w1.jpg", "category": "a"},
                    {"widget_id": "w2", "name": "CON", "description": "no media"}],
        "notes": [{"text": "hello"}]})
    out = tmp_path / "g"
    r = run_export(opts([run], out))
    rows = (out / "widgets" / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2 and json.loads(rows[0])["media_url"].endswith("w1.jpg")
    assert (out / "notes" / "metadata.jsonl").is_file()
    assert r.counts["by_collection"] == {"brand_new_scraper:notes": 1, "brand_new_scraper:widgets": 2}
    r2 = run_export(opts([run], tmp_path / "g2", group_by=["collection", "category"]))
    assert (tmp_path / "g2" / "widgets" / "a" / "metadata.jsonl").is_file() and r2.counts["rows"] == 3


def test_dataset_json_fallback_without_json_dir(tmp_path):
    run = make_run(tmp_path, "r", "community", {"generations": [{"generation_id": uid(1), "prompt": "p",
                                                                 "media_type": "image", "feed": "top"}]})
    for p in (run / "output" / "json").iterdir():
        p.unlink()
    (run / "output" / "json").rmdir()
    out = tmp_path / "o"
    r = run_export(opts([run], out, layout="jsonl"))
    assert r.counts["unique"] == 1


def test_filters_and_only(proj_run, tmp_path):
    f = parse_filters("has_prompt=true,media_type=image|video,model!=null")
    assert len(f) == 3 and f[1].values == {"image", "video"} and f[2].negate
    with pytest.raises(ValueError):
        parse_filters("nonsense")
    r = run_export(opts([proj_run], tmp_path / "f", layout="jsonl", only={"assets"},
                        filters=parse_filters("has_prompt=true")))
    assert r.counts["unique"] == 3


def test_download_missing_media_mocked(proj_run, tmp_path, monkeypatch):
    calls = []

    def fake_fetch(url, max_bytes):
        calls.append(url)
        return b"THUMB:" + url.encode(), "image/webp"

    monkeypatch.setattr("higgsfield_scraper.export.media.time.sleep", lambda s: calls.append(("sleep", s)))
    out = tmp_path / "dl"
    r = run_export(opts([proj_run], out, only={"assets"}, download_missing="thumbs", max_media_files=2,
                        fetch=fake_fetch))
    urls = [c for c in calls if isinstance(c, str)]
    assert len(urls) == 2 and all(u.endswith("_min.webp") for u in urls)
    assert r.media_stats["downloaded"] == 2 and r.media_stats["cap_reached"] > 0
    assert len(list((out / ".media_cache").iterdir())) == 2
    assert any(isinstance(c, tuple) for c in calls)                         # rate limited (>= 1 s between GETs)
    calls.clear()
    run_export(opts([proj_run], out, only={"assets"}, fetch=fake_fetch))   # no download flag -> no network
    assert calls == []


def test_no_network_by_default(proj_run, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    run_export(opts([proj_run], tmp_path / "n"))


# ------------------------------------------------------------------------------------------------ streaming / memory
def test_stream_reader_chunk_boundaries(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "CHUNK", 7)
    data = [{"a": i, "s": "x" * (i % 13), "u": "é😀", "n": 12345678901234567890, "f": -1.5e-3, "b": None}
            for i in range(200)] + [1, "str", True, [1, [2]]]
    p = tmp_path / "t.json"
    p.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    assert list(stream.iter_json_array(p)) == data
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"schema_version": 1, "meta": {"x": 1}, "a": [1, 2], "b": [], "c": [{"k": "v"}]}),
                 encoding="utf-8")
    got = list(stream.iter_dataset(d))
    assert got == [("schema_version", 1), ("meta", {"x": 1}), ("a", 1), ("a", 2), ("c", {"k": "v"})]
    assert list(stream.iter_dataset(d, only={"c"})) == [("c", {"k": "v"})]
    e = tmp_path / "e.json"
    e.write_text("[]", encoding="utf-8")
    assert list(stream.iter_json_array(e)) == []


def test_large_table_streams_in_modest_memory(tmp_path):
    n = 50_000
    run = tmp_path / "runs" / "big"
    (run / "output" / "json").mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({"scraper": "community"}), encoding="utf-8")
    with (run / "output" / "json" / "generations.json").open("w", encoding="utf-8") as f:
        f.write("[\n")
        for i in range(n):
            rec = {"generation_id": uid(i, 5), "feed": "top", "prompt": f"prompt number {i} " + "lorem " * 40,
                   "model_id": f"m{i % 7}", "media_type": "image", "created_at": "2026-11-26T00:00:00Z",
                   "results": [{"name": "raw", "type": "image", "url": f"{CDN}/hf_{uid(i, 5)}.png"}]}
            f.write(("," if i else "") + json.dumps(rec) + "\n")
        f.write("]\n")
    size = (run / "output" / "json" / "generations.json").stat().st_size
    assert size > 15_000_000
    tracemalloc.start()
    count = sum(1 for _ in stream.iter_json_array(run / "output" / "json" / "generations.json"))
    _, peak_read = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert count == n and peak_read < 2_000_000                             # one record + one chunk, not the file
    tracemalloc.start()
    r = run_export(opts([run], tmp_path / "big-jsonl", layout="jsonl", media="none"))
    _, peak_export = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert r.counts["unique"] == n
    print(f"file {size / 1e6:.1f} MB, read peak {peak_read / 1e6:.2f} MB, export peak {peak_export / 1e6:.1f} MB")
    assert peak_export < size * 2.5                                         # json.load alone needs ~5-10x the file
    lines = 0
    with open(tmp_path / "big-jsonl" / "manifest.jsonl", encoding="utf-8") as f:
        for _ in f:
            lines += 1
    assert lines == n


# ------------------------------------------------------------------------------------------------ CLI
def test_cli_export_and_run_glob(proj_run, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["export", "--run", "runs/*proj*", "--layout", "jsonl", "--out", "exports/x",
                   "--filter", "has_prompt=true", "--dry-run"])
    assert rc == 0 and "DRY RUN" in capsys.readouterr().out and not (tmp_path / "exports").exists()
    rc = cli.main(["export", "--run", proj_run.name, "--runs-dir", "runs"])
    assert rc == 0 and (tmp_path / "exports" / f"{proj_run.name}-tree" / "export_manifest.json").is_file()
    assert expand_runs([str(proj_run)]) == [proj_run]
    with pytest.raises(ValueError):
        expand_runs(["does-not-exist"], tmp_path / "runs")
