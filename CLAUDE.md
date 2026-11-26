# higgsfield-scraper

Python **Scrapy** project that scrapes public Higgsfield.ai data by reverse-engineering its data sources and storing
validated, versioned records. Eight scrapers (`python -m higgsfield_scraper scrapers`): `pricing` (default), `community`,
`catalog`, `projects`, `blog`, `site`, `showcase`, and the opt-in, login-only `account` (the user's own balances and jobs;
never in a default run); plus `diff` / `crosscheck` for pricing, `export` (run folders → browsable / dataset folders,
`docs/EXPORT.md`), `scripts/merge_generations.py` (dedupe generations across runs) and an interactive menu (`menu`).

## Knowledge base (read the relevant one before working)

Project docs index (what every doc contains, by topic): `docs/README.md`. Add new docs to it.

| File | Covers |
|---|---|
| `.claude/docs/scrapy.md` | Scrapy setup/CLI, spiders, Items, ItemLoaders, pipelines, feed exports (CSV/JSON/JSONL/S3), SQLite/MySQL/Postgres pipelines, login, 6 pagination methods, headers/proxies, scrapy-redis |
| `.claude/docs/schema-design.md` | Entity/ID design, nested vs split items, pydantic v2 validation, JSON Schema, nested → JSONL/CSV/SQL mapping, reference pricing schema + DDL |
| `.claude/docs/reverse-engineering.md` | Recon workflow, DevTools Network, hidden APIs, `__NEXT_DATA__`/GraphQL/Algolia, replaying requests, endpoint docs, Playwright capture, ethics |
| `.claude/docs/higgsfield-re-playbook.md` | **How** we reverse-engineer Higgsfield: ground rules, toolbox, stages A–G (freshness check → JS bundle grep recipes → replay → document → scraper → commit gates, baseline versioning), facts cheat-sheet, lessons learned |
| `.claude/docs/higgsfield-re-checkpoint.md` | **Where** we are: state (build, costs version, baseline), status per area, key findings, open questions, prioritized backlog, how to continue, changelog. State file: `.claude/re-state.json` |

Skills: `reverse-engineer-site` (map a new site before scraping), `scrape-spider` (build/modify spiders & pipelines),
`continue-reverse-engineering` (resume Higgsfield RE: check for site changes, read the checkpoint, update findings).

## Workflow

1. New site → `reverse-engineer-site`: robots/ToS → raw vs rendered → find JSON source → minimal replay →
   document in `docs/endpoints/<site>.md` + raw samples in `samples/<site>/`.
2. Schema → pydantic models in `higgsfield_scraper/schemas/<entity>.py` (source of truth), registered in
   `schemas/__init__.py:MODEL_BY_KIND`; Scrapy items are generated from them (`items.py`). Export with
   `python -m higgsfield_scraper schema`.
3. Spider → `scrape-spider` checklist; verify with a capped crawl before declaring done.

## Conventions

- Data source preference: public/hidden JSON API > embedded JSON > HTML selectors > headless browser.
- Every item: stable hashed natural-key ID, `source_url`, `scraped_at` (UTC ISO 8601), `schema_version`.
- Money: `Decimal` (serialized as string) + ISO 4217 `currency` + `price_raw`. Never float. Don't map `$` → USD blindly.
- Missing: `None`; empty list: `[]`; never `""` sentinels.
- Pipelines order: clean → validate (pydantic, `DropItem`) → dedup → store. Always `return item`.
- Storage: JSONL raw archive + normalized SQL with upserts; price history is append-only.
- Secrets (DB URLs, API keys, AWS creds, logins) come from environment variables / `.env` (gitignored). Never hardcode.
- Politeness: robots.txt is NOT obeyed by default (owner decision; `--obey-robots` turns it on), AutoThrottle, `DOWNLOAD_DELAY ≥ 1`, retry on 429; HTTP cache on in dev.
- Never bypass auth/paywalls/anti-bot protections or use non-public credentials; public data only.

## Layout (see README.md for full detail)

```
higgsfield_scraper/
  cli.py  constants.py  selection.py       # entry point, endpoint registry, run selection/filters
  spiders/higgsfield.py                    # JSON-API spider (no HTML parsing)
  parsers/                                 # pure raw-JSON -> entity dicts (unit-tested on fixtures)
  schemas/                                 # pydantic v2 models = source of truth; items.py is generated from them
  pipelines.py  validation.py  assemble.py  exporters.py  logformatter.py
  middlewares.py                           # HttpArchiveMiddleware -> <run>/http/ (request/response/body/curl/HAR)
  run/ (context.py, logging_setup.py, manager.py, retention.py)   # run folders, logs, manifest, `runs clean`
  core/                                    # ScraperDef/registry, BaseApiSpider, auth (Clerk), privacy, redact, exporting
  scrapers/<name>/                         # community, catalog, projects, blog, site, account, showcase (pricing = scrapers/pricing.py + the modules above)
  scrapers/showcase/                       # Canvas, Editing Room, Property Studio, explore, effects, API models, CMS showcases
  export/                                  # `export` command: runs -> tree / hf / webdataset / jsonl (read-only on runs/)
  estimate/                                # per-generation cost estimator
  interactive/                             # menu mode (Rich + questionary), built dynamically from the registry
  extensions.py                            # heartbeat
docs/REVERSE_ENGINEERING.md, ENDPOINTS.md  # findings + field meanings — update when endpoints change
docs/ENDPOINT_FIELDS.md                    # generated by scripts/gen_endpoint_fields.py
CLI.md                                     # every CLI option — update when flags change
tests/fixtures/raw/                        # captured API envelopes used by tests
scripts/merge_generations.py               # count + dedupe generations across runs (--compare: likes/views deltas)
runs/  exports/                            # run output, export output (gitignored)
```

## Higgsfield specifics

- Pricing data comes from 5 public JSON endpoints + 4 login-only ones (`auth` section); opt-in extras with a login:
  `--logged-in-prices` (plans + costs re-fetched with the session, rows only logged-in users see tagged
  `visibility="logged_in"`) and `--sections account` (8 whitelisted account endpoints, never part of `all`). What a
  session unlocks: `docs/LOGIN_COVERAGE.md`. The other scrapers are documented in `docs/scrapers/<name>.md`. Docs: `docs/REVERSE_ENGINEERING.md` (findings),
  `docs/ENDPOINTS.md` (field meanings), `docs/ENDPOINT_FIELDS.md` (generated: `python scripts/gen_endpoint_fields.py`),
  `CLI.md` (every option — update it when adding/changing a CLI flag; regenerate its scraper option tables with
  `python scripts/gen_cli_tables.py`), Postman collection (`python scripts/make_postman.py`).
- Continuing the reverse engineering: run `python scripts/re_check_changes.py` first (build id, costs version, job
  types vs `.claude/re-state.json`), then follow `.claude/docs/higgsfield-re-checkpoint.md` + `higgsfield-re-playbook.md`;
  update the checkpoint and `--save` the state when done.
- Full site inventory (features, 589 routes, 728 API paths, public vs login, next scrapers): `docs/HIGGSFIELD_DATA_INVENTORY.md`;
  re-probe with `python scripts/recon_probe.py`.
- All JSON output is written with `indent=4`; JSONL stays one object per line.
- `.gitignore` output-folder patterns must be root-anchored (`/schemas/`, `/runs/`, `/data/`): an unanchored
  `schemas/` once silently excluded the `higgsfield_scraper/schemas/` package from git.
- Repo: https://github.com/workingshady/higgsfield-scraper (branch `main`). Names: repo/dist `higgsfield-scraper`,
  package `higgsfield_scraper`. New Higgsfield scrapers go in this repo (see README "Adding a scraper").
- Default plan set `ps_a3` = US prices (matches https://higgsfield.ai/pricing.md). Country comes from the IP and
  cannot be overridden — do not try to spoof it.
- `/job-sets/costs` has many cost shapes; new shapes go in `parsers/costs.py` + a test in `tests/test_parsers.py`.
- After changing a parser, re-parse old data offline: `python -m higgsfield_scraper normalize --run runs/<id>`.
- Before every commit: `python -m pytest -q` + `python scripts/check_pricing_identity.py` (pricing output must stay
  31/31 identical to the baseline `runs/20261126-100141_pricing-baseline-v3`), and check `git diff --name-status HEAD` for unintended deletions.

## Commands

```bash
.venv\Scripts\activate
python -m pytest -q                                   # offline tests
python -m higgsfield_scraper scrape --dry-run                # planned requests
python -m higgsfield_scraper scrape --sections all           # live run -> runs/<ts>_<label>/
python -m higgsfield_scraper show model seedance_2_5         # inspect latest run
python -m higgsfield_scraper scrape site --what apps --max-items 20   # any scraper: scrape <name> -h
python -m higgsfield_scraper diff                            # pricing changes vs previous run
python -m higgsfield_scraper menu                            # interactive mode
python scripts/re_check_changes.py                    # has Higgsfield changed since the RE checkpoint? (--save to update)
```
