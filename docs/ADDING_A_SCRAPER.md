# Adding a scraper (framework contract)

Every Higgsfield scraper is a package `higgsfield_scraper/scrapers/<name>/` whose `__init__.py` exposes
`SCRAPER: ScraperDef` (see `higgsfield_scraper/core/base.py`). It is already registered in
`higgsfield_scraper/core/registry.py` (`SCRAPER_MODULES`: `pricing`, `community`, `catalog`, `projects`, `blog`,
`site`, `account`, `showcase`, `studios`, `models`; a new scraper adds one line there). The framework provides everything
else, for free and identically for every scraper:

| Provided by the framework | Where |
|---|---|
| `scrape <name>` CLI subcommand + common flags (limits, media, auth, safety, run/log) | `cli.py`, `core/cli_common.py` |
| Run folder `runs/<ts>_<name>-<label>/` with manifest, split logs, `raw/`, `http/`, `media/`, `output/` | `run/` |
| Raw archive of every response; offline `normalize` (re-parse `raw/`) | `pipelines.py`, `run/manager.py` |
| Pydantic validation (drop + stats), dedup by `id_field_by_kind`, Scrapy JSONL feeds per kind | `pipelines.py`, `items.py` |
| Login tokens with auto refresh (requests with `meta["auth"]=True` or `"required"`) | `core/auth.py` |
| Limits: `--max-items`, `--max-pages`, `--page-size`, `--max-requests`, `--max-minutes`, `--delay`, `--concurrency` | `core/api_spider.py` |
| Stop on DataDome captcha (no evasion) | `core/api_spider.py` |
| Optional media download (`--download-media none|thumbs|full|all`, file/MB caps) via `ScraperDef.media_urls` | `core/api_spider.py` |
| Export helpers: indented JSON, complete flat CSVs, schema, summary | `core/exporting.py` |

## Files of a scraper package

```
higgsfield_scraper/scrapers/<name>/
  __init__.py      SCRAPER = ScraperDef(...)          (must NOT import spider.py — use the "module:Class" string)
  endpoints.py     URLs/paths, page-size maxima, enums found while reverse-engineering
  options.py       add_args(parser), Selection dataclass (.to_dict()), make_selection(args), selection_from_dict(d)
  parsers.py       pure: parse_envelope(env, sel) -> list[dict]  (each dict has "kind"); keep(entity, sel)
  schemas.py       pydantic v2 models, Strict (extra="forbid"), one per kind + <Name>Dataset with meta: CoreMeta
  dataset.py       build_dataset(entities, sel, run_meta) -> validated JSON-mode dict; write_outputs(ds, out_dir)
  spider.py        class XSpider(BaseApiSpider): scraper_name="<name>"; build_requests(); follow_up() for pagination
tests/test_<name>.py + tests/fixtures/<name>/*.json  (raw Envelope files: {"meta": {...}, "body": ...})
docs/scrapers/<name>.md   endpoints, params, every field, options, examples, limits, gaps
```

## Rules

- **Kinds are globally unique**: prefix them with the scraper name (`community_generation`, `catalog_motion`, …).
- **Selection** objects must have `to_dict()` and `selection_from_dict()` must accept both that dict (from a manifest)
  and string values (from `scrapy crawl <name> -a key=value`).
- **Parsers are pure** (no network, no Scrapy) so they are unit-testable on fixtures and reusable by `normalize`.
- **Provenance**: every entity carries `source: Provenance` (`env.provenance()`), plus stable ids.
- **Money** as Decimal strings; timestamps as ISO-8601 UTC strings; `None` = missing, `[]` = empty.
- **Dataset**: `{"schema_version": 1, "meta": CoreMeta(...), "<collection>": [...], ...}`; build `meta` with
  `core.dataset.make_meta(...)` (puts selection, limits, limits_hit, totals_available, counts, endpoints, warnings).
- **Outputs**: `write_outputs` must call `core.exporting.write_standard_outputs(ds, out_dir, json_parts=..., csv_tables=...,
  dataset_model=..., summary_md=...)`. CSVs must be **complete** (every JSON leaf has a column; child lists become their
  own table with parent keys) — add a completeness test like `tests/test_assemble_and_export.py::test_csvs_contain_every_json_field`.
- **Spider**: `primary_kinds` = kinds counted by `--max-items`; use `self.api_request(...)`, `self.page_allowed(listing)`,
  `self.page_size(default, maximum)`, `self.budget_left()`, `self.limit_hit(reason)`, `self.totals[key] = n`.
  Paginate in `follow_up(env, entities, response)` and stop when the API says no more, the budget is spent, or
  `page_allowed` is False. Login-only endpoints: `auth="required"` (skipped cleanly without a session).
- **Personal data**: never export users' social handles/avatars unless an explicit opt-in flag is given.
- **Never** call mutating endpoints (POST/PUT/DELETE, like/vote/report/purchase/generate…). GET only.
- **Do not edit shared files** (`core/`, `cli.py`, `pipelines.py`, `settings.py`, `registry.py`, pricing modules, README, CLI.md).
