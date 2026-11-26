# `models` scraper — the model registry from the public JS bundle

Opt-in scraper (never part of the default `scrape`, which is `pricing`). It productionizes what
`scripts/gen_model_catalog.py` did offline: there is **no public "models" API** — the generators' model list, the
per-model parameter schema (`defineJob`), routes, plan tiers, feature-flag gating, featured order and picker menus
are static code in the frontend bundle ([`MODEL_LOADING.md`](../MODEL_LOADING.md) §2–3, §8 idea 1). The scraper
reads that code at runtime (regexes + bracket matching, **no JS execution**), joins it with `/job-sets/costs` and the
Shots `available_models` facet, and records the build it came from, so runs can be diffed build by build.
GET only, anonymous, ≥ 1 s between requests (shared `--delay`), no bot-protection bypass.

```bash
python -m higgsfield_scraper scrape models                          # 4 pages + ≤ 800 chunks + costs + facet (~10 min)
python -m higgsfield_scraper scrape models --max-chunks 300 --no-shots
python -m higgsfield_scraper scrape models --pages /ai/video,/ai/image --max-chunks 0   # 0 = no cap
python -m higgsfield_scraper scrape models --dry-run                # first requests (6)
python -m higgsfield_scraper normalize --run runs/<id> --scraper models    # re-join raw/ offline
```

Package: `higgsfield_scraper/scrapers/models/` (`endpoints.py`, `jsparse.py`, `extract.py`, `middleware.py`,
`options.py`, `parsers.py`, `schemas.py`, `dataset.py`, `spider.py`). Tests: `tests/test_models.py`, fixtures
`tests/fixtures/models/` (hand-written chunks in the exact minified shapes of build `548e0f3a`; one test also reads
the saved real bundle `samples/higgsfield/js2/` when present).

## 1. How it works

```
GET higgsfield.ai/{/ai/video,/ai/image,/lipsync-studio,/mixed-media}      (SSR HTML)
    -> buildId / commit / environment (env JSON), frontend build prefix (548e0f3a), window.__HF_FF flags,
       modulepreload + module-script chunk list
GET assets.higgsfield.ai/tanstack/assets/<chunk>.js   (priority heap, 4 in flight, --max-chunks)
    -> static imports (from"./x.js"), dynamic imports (import(`./x.js`)), named modules, registry data
GET fnf-api-gw.higgsfield.ai/fnf/job-sets/costs                            -> priced job types + version
GET fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=1       -> available_models facet
```

**Crawl order.** Chunks are queued in a priority heap and requested 4 at a time: the tool pages' preloaded chunks
first (priority 50, page order), then the imports of chunks that hold model data (parent − 1), then all other
imports (parent − 10). `--max-chunks` therefore cuts the least useful chunks. On the saved build 548e0f3a the four
default pages reach every registry part (131 `defineJob` types, route table, featured ids, gating, plans) within
≈ 540–670 chunks; `/ai/video` + `/ai/image` alone need more (≈ 770). Hitting the cap is recorded in
`meta.limits_hit` and `builds[].coverage` says which parts were found.

**Bodies are converted before archiving.** `ModelsExtractMiddleware` (downloader middleware 582, added by
`ModelsSpider.update_settings`, like the account scraper's) replaces each page / chunk body with its compact JSON
extract **before** the http/ (580) and raw/ archives and the parser see it. A run reads ~20 MB of minified JS;
archiving it verbatim would bloat every run folder, while the extract keeps `size` + `sha256` of the original (a
content change stays visible) and lets `normalize` re-join `raw/` offline. The Shots feed body is reduced to
`{available_models, snapshot_id, snapshot_at}`: the one feed item that comes with it is another user's publication
and is never stored. Other endpoints / scrapers pass through untouched.

## 2. What is extracted (`extract.py`)

| Part | JS shape (build 548e0f3a) | Output |
|---|---|---|
| `defineJob` registry | `P({type:`x`,output:`y`,business:{…},input:[prompt({policy}), media({roles,counts,rules}), settingsVar],credits,validate,toProvider,fromProvider})` in `Kxdpq5YjqY_JH5zf` (111 types) + 7 smaller chunks | per type: output, business flags, prompt policy, media roles / counts / rules (source text), settings schema resolved in the chunk (`j._default(j.enum(X),d)`, `j.duration({min,max})`, `j.aspectRatio(X)`, `j.optional/nullable(...)`; identifiers resolved to the nearest assignment), `validate` ranges (`W(`seed`,e.seed,1,1e6)`) and enum checks, `toProvider` wire keys, fixed `credits` |
| Route table | `{seedance_2_5:`v2/seedance_2_5`,character_swap_v2:`character-swap/v2`,…}` (`j8lj58UEh2bbmHmn`) | `job_set_type -> /jobs/...` |
| Featured | named module `video-featured-model-ids-*` (`t=[…]`) | ordered list |
| Gating | `Hx={kling_4_0_flash:{flag:lc,fallback:`kling4_0`},seedance_2_5_flash:{flag:Gn,…,pricedAs,cobaltComingSoon:!0},…}` (`tCLaulKUdGQfxqgZ`) + the default model and retired `new Set([…])` declared before each table | per id: hashed flag (alias → `import{xF as lc}` → `export{sC as xF}` → `sC=`f_3a0922bf``), fallback, priced_as; per table: default model, retired ids |
| Plans | `video-model-plans-*`: `o={seedance_2_5:i.i,…}` with `i=r(`plans-*`)` whose module declares the tier arrays | per id: tier (`all` = has `free`, `paid` = all − free, else `premium`) + plan list |
| Menus | `{id:`seedance_2_5`,badges:[…],title:`Seedance 2.5`,short_title:…}` | UI model-version ids with title / badges / tags |
| Flags | `xx=`f_xxxxxxxx`` constants + export names (core chunk `aXyXjC_KHBp09DNW`) | used to resolve gating flags |
| Page | `"buildId":…,"commit":…` (HTML-escaped env JSON), `window.__HF_FF = {…}` | build record, anonymous flag values |

Anything that cannot be read is kept as source text (`raw`, `*_raw`, `extra`), never guessed. Known limits: shared
settings spread into a schema from another module (`...y(j)`, e.g. `seedance_2_5`) are recorded as a `...` param
with the spread source, not inlined; identifiers imported from other chunks (e.g. a prompt `maxLength`) stay `raw`.

## 3. Records

| Collection (kind) | Id | Fields |
|---|---|---|
| `job_types` | `id = make_id("model_job_type", job_set_type)` (stable across builds) | `job_set_type, output, display_title, in_registry, in_routes, in_costs, in_shots, route, route_inferred (/jobs/<kebab-type> for registry types missing from the table: inferred, not called), business, prompt, media_roles, media_counts, media_rules_raw, params[] (name, type, values, default, min, max, optional, nullable, extra, raw), validate_ranges, validate_enums, wire_keys, credits_static, credits_formula_raw, featured_rank, gate{flag, flag_value, fallback, priced_as, cobalt_coming_soon, status, extra}, plan{tier, plans}, retired, shots_media_type, defined_in[], build_id, frontend_build, extra, source_url, scraped_at, schema_version` |
| `menu_entries` | `make_id("model_menu_entry", model_version_id)` | `model_version_id, title, short_title, titles[], badges, tags, job_set_type (same normalized id), featured_rank, gate, plan, retired, chunks[], extra, scraped_at, schema_version` — only ids that belong to a model (in plans / featured / gating / retired, or a job type after normalizing `-`/`.`) |
| `builds` | `make_id("model_build", build_id, commit, frontend_build)` | `frontend_build, build_id, commit, environment, pages, flags (anonymous __HF_FF), costs_version, default_models, retired, plan_tiers, featured, chunks_fetched, chunks_with_data, job_types, registry_types, route_types, menu_entries, coverage{registry, routes, featured, gating, plans, flags_resolved, page_flags, costs, shots}, limits_hit, scraped_at, schema_version` |
| `chunks` | `chunk` | `url, size, sha256, markers, named_modules, job_types, menu_entries` |
| `shot_facets` (`model_shot_facet`) | `facet_id = make_id("model_shot_facet", model, media_type)` | `model, media_type, position, snapshot_id, snapshot_at, extra, source_url, scraped_at, schema_version` |

`job_types` is the union of registry types, route-table keys and `/job-sets/costs` types (so priced types with no
`defineJob`, e.g. `scene_switch`, still get a row: `in_registry=false`). Gate `status` follows the JS rule for an
anonymous visitor: flag missing / false → `hidden`; `priced_as` not in `/job-sets/costs` → `hidden`; else
`available` (`cobaltComingSoon` depends on the user and is only reported). Intermediate kinds (validated, archived,
not dataset collections): `models_page_extract`, `models_chunk_extract`, `models_costs_snapshot`.

Summary: counts, `by_output`, `by_plan_tier`, `gated` (id → status), `costs_only` (priced, no JS), 
`registry_not_priced`. Outputs: `dataset.json`, `json/<collection>.json`, CSVs per collection + `job_type_params`
(one row per param), `schema/dataset.schema.json`, `summary.md`.

## 4. Options

| Option | Default | Meaning |
|---|---|---|
| `--pages` | `/ai/video,/ai/image,/lipsync-studio,/mixed-media` | tool pages whose bundle is crawled (site paths only) |
| `--max-chunks` | 800 | max JS chunks fetched; 0 = no cap |
| `--no-costs` | off | skip `/job-sets/costs` (`in_costs` = null, no `costs_version`) |
| `--no-shots` | off | skip the Shots facet (`in_shots` = null, no `shot_facets`) |

Shared options apply (`--delay`, `--max-requests`, `--max-minutes`, …). `--max-items` / `--max-pages` /
`--download-media` have no effect.

## 5. Live checks

2026-11-26, anonymous, build `548e0f3a` (buildId `45857404800-1-production`, commit `bcc95938`):

* `--max-chunks 40`: 46 requests, 52 s, success; gating + flags + costs + facet found, registry not yet reached
  (coverage says so); `normalize` of its `raw/` reproduces the dataset exactly.
* default (`--max-chunks 800`): 806 requests, 16.4 min, success, 0 errors; **coverage complete** (registry, routes,
  featured, gating, plans, flags resolved, page flags, costs, shots). 164 job types (119 with a `defineJob`, 111 with
  a resolved params schema; 84 in the route table; 125 with published shots), 96 menu entries, 167 shot facets,
  32 chunks with model data. Gated (anonymous): `kling_4_0_flash`, `seedance_2_5_flash(_edit/_extend)` available;
  `wan4_0`, `minimax_h3_image` hidden. Run folder ≈ 19 MB `http/` + 4.5 MB `raw/` (extracts, not JS).
  The cap was hit with 1 chunk left unrequested; use `--max-chunks 0` for an uncapped crawl.

## 6. Privacy / ethics

Public, anonymous GETs of the same static files and public APIs the website loads; no session is ever sent
(`--auth off` is not needed: no request asks for auth). The Shots body is whitelisted to the facet before anything is
written. Bundle code is Higgsfield's; only extracted facts (ids, enums, limits, routes) are stored.
