# Export: run folders → browsable / dataset-ready folders

`python -m higgsfield_scraper export` turns one or more **finished run folders** (any scraper) into a new folder that
is easy to browse or to load as a dataset. It is opt-in and read-only:

* it only **reads** `runs/<id>/manifest.json`, `output/json/*.json` (or `output/dataset.json`), `output/briefs/*.md`
  and `media/index.jsonl` + the media files; it never writes into a run folder and never re-scrapes;
* it sends **no network requests** unless `--download-missing-media` is given (plain GETs, ≤ 1 request/second,
  capped, into `<export>/.media_cache/`);
* it exports only what is in the run output. Runs scraped without `--with-profiles` are already redacted; the export
  never re-adds usernames (comments are attributed to the pseudonymous `author_key`).

Code: `higgsfield_scraper/export/` · tests: `tests/test_export.py` · default output: `exports/<run>-<layout>/`
(`/exports/` is gitignored).

```bash
python -m higgsfield_scraper export --run runs/20261126-133628_nested-check                 # tree (default)
python -m higgsfield_scraper export --run runs/20261126-133628_nested-check --layout hf --out exports/nested-check-hf
python -m higgsfield_scraper export --run "runs/*nested-sea*" --layout jsonl                 # glob, deduped
python -m higgsfield_scraper export --run runs/A --run runs/B --layout webdataset --shard-mb 512
python -m higgsfield_scraper export --run runs/A --filter "has_prompt=true,media_type=video" --per-asset
python -m higgsfield_scraper export --run runs/A --only assets --download-missing-media thumbs --max-media-files 200
python -m higgsfield_scraper export --run runs/A --dry-run                                     # plan only
```

## Options

| option | default | meaning |
|---|---|---|
| `--run RUN` | (required, repeatable) | run folder, run id (looked up in `--runs-dir`) or glob (`runs/*sea*`) |
| `--out DIR` | `exports/<first run>-<layout>` | export folder; must be empty, absent, or a previous export |
| `--layout` | `tree` | `tree` · `hf` · `webdataset` · `jsonl` (below) |
| `--group-by FIELDS` | profile default | tree folders, e.g. `model,media_type`, `collection,feed,date`; `=name` = literal folder |
| `--per-asset` | off | tree: one folder per asset (`<stem>/<stem>.<ext|json|txt>`); warns above 500 assets |
| `--media` | `auto` | `auto`/`copy`: copy local media · `hardlink`: hardlink (copy across volumes) · `link`: URLs only + `urls.txt` · `none`: metadata only |
| `--download-missing-media` | off | `thumbs` or `full`: GET media not in the run's `media/` (1 req/s) |
| `--max-media-files`, `--max-media-mb` | the run's own caps (500 / 1024) | caps for **new** downloads per invocation (cached files are reused and not counted) |
| `--only COLLECTIONS` | all | comma list of collections (`assets,generations`) or `scraper:collection` |
| `--filter EXPR` | none | `field=value` terms joined by `,` (AND); `a|b` = OR; `!=` negates; `null`, `true`, `false` |
| `--shard-mb` | 1024 | webdataset shard size |
| `--dry-run` | off | plan + counts, writes nothing (not even the folder) |
| `--force` | off | allow a non-empty non-export `--out`, or replacing an export of another layout |
| `--runs-dir` | `runs` (`HF_RUNS_DIR`) | where bare run ids are looked up |

Filter/group fields: the normalized fields (`id`, `collection`, `scraper`, `prompt`, `has_prompt`, `has_media`,
`model`, `media_type`, `date`, `created_at`, `author_key`, `run_id` …), profile fields (projects: `contest`,
`project`, `folder`, `folder_path`), or any dotted path into the record (`engagement.likes`, `feed`, `group`).

## Profiles (dynamic per scraper)

The scraper comes from the run's `manifest.json` (fallback `output/json/meta.json`). Tables are discovered
generically: every `output/json/<name>.json` whose top level is an array (or every list in `dataset.json`).

| scraper | tree grouping (default) | plain tables (`_tables/<name>.jsonl`) |
|---|---|---|
| projects | assets → `<contest>/<project-slug>/<Folder>/<Subfolder>/` (root-folder assets → `_root/`); publications → `<contest>/<project-slug>/`; submissions → `<contest>/submissions/`; + `project.json`, `brief.md`, `comments.md`, `stats.json` per project | contests, listing_entries, folders, briefs, comments, project_stats, stack_items, related, categories, series |
| community | `<collection>/<feed>/<model>/<date>/` | pages, stats, creator_stats, extra_stats, creators, comments |
| catalog | `<kind>/<group>/` (e.g. `marketing_presets/ads/`, `model_motions/kling2_6/`) | pages, summary, *_categories, viral_types |
| site | `<section>/` (rooms by `room_slug`, lessons by course) | summary |
| showcase | `<collection>/<model>/` (explore items by category, effect samples by preset) | explore_categories, seasons |
| blog | `<collection>/` | – |
| *anything else* | generic: `<collection>/` | – |

New scrapers need no code: the generic profile exports every list table. Add a class to
`export/profiles.py:PROFILES` only to change the grouping.

Every record becomes a row with generic fields pulled from it (`export/records.py`): prompt (`prompt`,
`raw_params.prompt`, `params.prompt`), caption (prompt, else description), model (`model_name`, `made_with_model`,
`model_id`, `job_set_type`, …), primary media URL (url/media_url/video_url, `results[]`/`media[]` entries whose role
is not an input/avatar, plus `scripts/merge_generations.py:output_urls`), thumbnail, size, duration, provenance
(`source_url` or `source.url`, `scraped_at` or `source.fetched_at`, run id, schema version) and `author_key`.

## Layouts

### `tree` (default) — website-like
```
exports/nested-check-tree/
  README.md  export_manifest.json  errors.log
  talent_contest/
    the-sea-walks-out/
      project.json  brief.md  comments.md  stats.json
      metadata.jsonl  prompts.csv                  # the publication row (cover)
      Cast/        metadata.jsonl  prompts.csv     (+ 0000_seedream-5-5_be8159e678ab.png + .txt with --download-media runs)
        Face Locks/  Outfits/  Sheets/
      Locations/  Scenes/  Props/  Music/  Titles and Posters/Posters/ …
  _tables/ contests.jsonl folders.jsonl comments.jsonl …
```
`metadata.jsonl` holds per row: `file_name` (relative to the folder or null), the normalized fields, `dedup`
(records/sources/runs merged into this row) and the full original `record`. `prompts.csv` is the flat view
(UTF-8 BOM for Excel). Media are named `<position>_<model-slug>_<id12>.<ext>` and the caption sits next to it with
the **same stem** (`.txt`), the convention used by kohya-ss sd-scripts and most captioning tools.

### `hf` — Hugging Face ImageFolder / VideoFolder / AudioFolder
```
images/train/metadata.jsonl   images/train/<stem>.png   images/train/<stem>.txt
videos/train/metadata.jsonl   videos/train/<stem>.mp4 …
urls.jsonl                    # every deduplicated row (also those without a local file; `file` null)
```
`file_name` is relative to the metadata file, as the builders require; columns are flat and typed consistently
(params as `params_json` string) so Arrow schema inference does not fail. Only rows with a local media file go into
`metadata.jsonl` (the builders need the file); all rows are in `urls.jsonl`.

### `webdataset` — tar shards
`shards/shard-000000.tar`, … (rolled over at `--shard-mb`): per sample `<key>.<ext>` (media, if local),
`<key>.json` (normalized + original record), `<key>.txt` (prompt), adjacent in the tar; keys contain no dots.
Tar headers are deterministic (mtime 0, uid/gid 0) so an unchanged re-export produces byte-identical shards.
`index.jsonl` maps `__key__` → shard.

### `jsonl` — one flat deduplicated manifest
`manifest.jsonl`: one line per unique asset/generation (prompt, model, media URL, local `file` under
`media/<kind>/` when available, provenance, `dedup_records`, `dedup_sources`, `dedup_runs`).

## Loading

```python
import pandas as pd                                              # any layout
df = pd.read_json("exports/x-jsonl/manifest.jsonl", lines=True)
df = pd.read_json("exports/x-tree/talent_contest/the-sea-walks-out/Scenes/metadata.jsonl", lines=True)
df = pd.read_csv("exports/x-tree/talent_contest/the-sea-walks-out/Scenes/prompts.csv", encoding="utf-8-sig")
# Parquet (pyarrow is NOT a dependency of this project): df.to_parquet("manifest.parquet")

from datasets import load_dataset                                # pip install datasets
ds = load_dataset("imagefolder", data_dir="exports/x-hf/images") # columns: image + metadata fields
vs = load_dataset("videofolder", data_dir="exports/x-hf/videos")
rows = load_dataset("json", data_files="exports/x-hf/urls.jsonl")

import webdataset as wds                                         # pip install webdataset
ds = wds.WebDataset("exports/x-wds/shards/shard-{000000..000003}.tar").decode("pil")
for s in ds: s["__key__"], s.get("png"), s["json"]["prompt"], s.get("txt")
```

## Dedup, ids and multiple runs

* `--run` is repeatable and takes globs; runs are read in the given order and the **first** occurrence wins.
* **tree** dedups by record identity `rec:<scraper>:<collection>:<id>` (profile id field, else `<singular>_id`,
  `placement_id`, `uid`, `id`, first `*_id`, else a content hash). The same video placed in two project folders
  stays in both folders (website view).
* **hf / webdataset / jsonl** dedup at generation level with union-find over the record key plus the generation keys
  of `scripts/merge_generations.py` (`job:<id>`, `pub:<id>`, `media:<uuid>` of output URLs, `static:` …) and, for
  project assets, `asset:<asset_id>`. The key logic is **reused** from that script (loaded by path in
  `export/keys.py`, with a minimal fallback if the script is absent), not duplicated.

## Idempotent, resumable, safe

* Every file is written to `<name>.export-tmp` and `os.replace`d in, only if its sha256 differs from the existing
  file; unchanged files keep their mtime. Group files are streamed to `.export-staging/` first.
* `export_manifest.json` (export version, options, runs with output fingerprints, counts, every file with
  bytes/sha256/mtime) is rewritten only when something changed; its `exported_at` is the time of the last change.
* Re-running an export with the same inputs changes nothing (tested); files the previous export wrote that the new
  one does not produce are removed (e.g. after narrowing `--filter`); nothing else in `--out` is touched.
* `--dry-run` writes nothing. `--out` inside a run folder is refused.
* Media copies keep mtime (`copy2`) so later runs skip them by size+mtime; downloads are cached by `sha1(url)` and
  reused, so an interrupted `--download-missing-media` resumes where it stopped.

## Best-practice decisions (and sources)

| topic | decision | sources |
|---|---|---|
| HF ImageFolder/VideoFolder | `metadata.jsonl` per split folder with a `file_name` column relative to it; one folder per media kind; flat, consistently typed columns | [HF: create an image dataset](https://huggingface.co/docs/datasets/en/image_dataset), [HF: create a video dataset](https://huggingface.co/docs/datasets/en/video_dataset), [HF Hub: image datasets](https://huggingface.co/docs/hub/datasets-image) |
| WebDataset | samples = files sharing a basename (up to the first dot), adjacent in the tar; numbered shards `shard-{000000..N}.tar`; ~1 GB shards | [webdataset (PyPI)](https://pypi.org/project/webdataset/), [Megatron-Energon data prep](https://nvidia.github.io/Megatron-Energon/basic/data_prep.html), [NVIDIA AIStore ishard](https://aistore.nvidia.com/blog/2024/08/16/ishard) |
| JSONL | UTF-8, one JSON value per line, `\n` terminator, no blank lines | [jsonlines.org](https://jsonlines.org/) |
| Parquet | not produced (pyarrow is not installed / not a dependency); load JSONL with pandas/pyarrow and `to_parquet` when needed; the HF Hub auto-converts public datasets to Parquet | [HF Hub: PyArrow](https://huggingface.co/docs/hub/datasets-pyarrow), [HF dataset viewer Parquet](https://huggingface.co/docs/dataset-viewer/parquet_process) |
| captions | `.txt` with the same stem next to the media | [kohya-ss sd-scripts dataset config](https://github.com/kohya-ss/sd-scripts/blob/main/docs/config_README-en.md) |
| Windows names | strip `< > : " / \ | ? *` and control chars; no trailing dot/space; reserved names CON, PRN, AUX, NUL, COM0-9, LPT0-9 (incl. ¹²³), also with an extension | [Microsoft: Naming files, paths, and namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file) |
| path length | keep paths < 260 (MAX_PATH) by shortening the longest folder names with a hash suffix; `\\?\` prefix as fallback for long absolute paths | [Microsoft: Maximum path length limitation](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation) |
| Unicode | NFC-normalize names (macOS tools may produce NFD; APFS does not normalize itself) | [Eclectic Light: Unicode, normalization and APFS](https://eclecticlight.co/2021/05/08/explainer-unicode-normalization-and-apfs/), [Unicode normalization FAQ](https://www.unicode.org/faq/normalization.html) |
| case collisions | NTFS/APFS are case-insensitive by default → second name differing only by case gets `~2` | same as above |
| hardlinks | only on the same volume, files only (no directories); symlinks need admin or Developer Mode on Windows → not used; hardlinks fall back to copies; default is copy because editing a hardlinked export file would edit the run's media file too | [Microsoft: CreateHardLink](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw), [Microsoft: Hard links and junctions](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions), [Rush Stack: createHardLink](https://api.rushstack.io/pages/node-core-library.filesystem.createhardlink/) |
| atomic writes | temp file in the **same directory** + `os.replace` (atomic on POSIX, best effort on Windows); skip when hash unchanged | [Python discuss: atomic writes](https://discuss.python.org/t/adding-atomicwrite-in-stdlib/11899), [bugs.python.org #8828](https://bugs.python.org/issue8828) |
| content addressing | media named by asset id; download cache by `sha1(url)`; every file's sha256 in `export_manifest.json` | – |
| data card | README.md per export: motivation, composition, collection/provenance, privacy, licensing, limitations | [Gebru et al., Datasheets for Datasets](https://arxiv.org/abs/1803.09010), [HF dataset cards](https://huggingface.co/docs/hub/datasets-cards) |

## Privacy and licensing

* Exports contain exactly what the run output contains. Runs without `--with-profiles` hold no usernames/handles
  (authors are pseudonymous `author_key`s); the README states when a source run used `--with-profiles`.
* `comments.md` names authors only by `author_key`.
* Prompts, comments and briefs are user-written and can mention people: review before sharing.
* **Licensing caveat** (also in every export's README): the content belongs to its creators and is subject to the
  Higgsfield Terms of Service; the export grants no licence to redistribute or train on it.

## Performance (measured on this machine, offline)

| export | records → unique | files | size | time | peak RAM |
|---|---|---|---|---|---|
| nested-check (54 MB assets.json) tree | 4750 → 4750 | 234 | 121.5 MB | 9.5 s | 94 MB (process) |
| nested-check hf | 4750 → 4685 | 3 | 47.0 MB | 5.9 s | – |
| synthetic 50k generations (28.6 MB) jsonl | 50 000 → 50 000 | – | – | – | read 0.4 MB, export 62 MB (tracemalloc; dedup key sets) |
