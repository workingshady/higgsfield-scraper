# `account` scraper (opt-in, needs a login)

Records the **logged-in user's own** account state and, optionally, their own jobs with the credits that were
**actually charged**. The main research value is `--compare-estimate`: it runs the `CostEstimator` on each job's
params and compares the result with the real charge, which validates `docs/COST_FORMULAS.md` against live billing.

It is **never part of a default run**. It only runs when called by name: `scrape account …`.
Source of the endpoint shapes: `docs/LOGIN_COVERAGE.md` §2.1, §2.4 and §3.4, plus
`samples/higgsfield/login_audit/account_endpoint_shapes.json`.

## Usage

```bash
python -m higgsfield_scraper scrape account                                   # snapshot only
python -m higgsfield_scraper scrape account --with-jobs --max-items 100       # + own jobs
python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20
python -m higgsfield_scraper normalize --run runs/<id>                       # re-parse raw/ offline
```

Login: `python -m higgsfield_scraper login`, or `HF_CLERK_CLIENT` (or `HF_EMAIL`/`HF_PASSWORD`) in `.env`.
Check it with `python -m higgsfield_scraper auth-check`.

## Flags

| Flag | Meaning |
|---|---|
| *(none)* | Snapshot: the 11 account endpoints below |
| `--with-jobs` | Also read `/jobs/accessible`, paginated. `--max-items` caps the number of jobs, `--max-pages` the pages, `--page-size` the page size (default 20, clamped to 50) |
| `--compare-estimate` | Needs `--with-jobs`. Also fetches the public pricing (`/job-sets/costs`, `/viral-hub/presets/all`, `/subscriptions/v2/compare`, `/subscriptions/v2/plan-benefits`), builds the `CostEstimator` and compares each job |
| `--job-types a,b` | Needs `--with-jobs`. Server-side `job_set_type` filter |
| `--with-prompts` | **Opt-in: stores your own prompt text** (`prompt`, `negative_prompt`, `text`, …) in the dataset **and** in the `raw/` and `http/` archives. By default only the prompt length is kept |

The common flags (limits, `--delay`, `--auth`, `--dry-run`, …) work as for every scraper.
`--download-media` does nothing here: this scraper never downloads your media.

## Endpoints (GET only)

Base `https://fnf-api-gw.higgsfield.ai/fnf`. All account endpoints use `auth="required"`.

| Endpoint key | Path | Used for | A non-200 makes the run `partial`? |
|---|---|---|---|
| `account_user` | `/user` | plan state, balances in credits (floats) | yes (core) |
| `account_wallet` | `/workspaces/wallet` | balances in cost units (×100) | yes (core) |
| `account_subscription` | `/workspaces/subscription` | plan, status, billing cycle, period, payment status | yes |
| `account_user_meta` | `/user/meta` | `cohort` only | no |
| `account_workspace_settings` | `/workspaces/settings` | unlimited grants (`configs`; `status=locked` dropped like the web app) | no |
| `account_notice` | `/workspaces/notice` | discount offers shown to this user | no |
| `account_free_gens` | `/user/free-gens/v2` | free generations | no |
| `account_generation_seconds` | `/user/generation-seconds` | generation-seconds balances | no |
| `account_auto_top_up` | `/v2/auto-top-ups/settings` | auto top-up state, `credits_per_dollar`, options | no |
| `account_personal_promo` | `/user/personal-promo` | personal promo (scrubbed) | no |
| `account_all_unlim_status` | `/subscriptions/bundle/all-unlim/status` | eligibility flags | no |
| `account_jobs` | `/jobs/accessible?size=&cursor=&job_set_type=` | own jobs + `cost` (`--with-jobs`) | yes |
| `account_job_costs`, `account_viral_presets`, `account_compare`, `account_benefits` | public pricing | estimator (`--compare-estimate`); sent with the session so logged-in-only cost rows (e.g. `magi_2`) are included | no |

**Pagination of `/jobs/accessible`:** the response is `{jobs, has_more}` with no cursor. The web app pages job lists
by the last item's `created_at`, so the scraper sends `cursor=<created_at of the last job>` while `has_more` is true
(*inferred* from the JS; a `cursor` / `next_cursor` in the body would be used first). It stops on `has_more=false`,
an empty page, a repeated cursor, `--max-items` or `--max-pages`.

## Run status

| Situation | Status | Why |
|---|---|---|
| No session (`--auth off`, nothing configured) | **`failure`** (exit 1) | No request is made; an error explains how to log in. Nothing about the account can be read anonymously, so this is not a partial result |
| Session configured but `/user` and `/workspaces/wallet` both failed (expired / refresh failed) | **`failure`** | same reason |
| Snapshot OK, but a core/job endpoint answered non-200, or bot protection answered | `partial` | some data is missing |
| Everything OK, including zero jobs | `success` | zero jobs is a valid result |

Bot protection is **never evaded**. A DataDome captcha stops the crawl (framework behaviour). A Cloudflare challenge
(`cf-mitigated` header) is recorded in `meta.limits_hit` as
`bot protection (cloudflare challenge) on account_jobs — HTTP 403, no evasion attempted`, and the run ends `partial`.

## Privacy

The account is personal, so the scraper keeps a **whitelist** of fields, not a blacklist.

- **Never stored:** email, names, username, avatar, user / workspace / subscription / Stripe / customer / price ids,
  trace ids, country / region, consents, block reasons, invoices, payment methods, result media URLs, input media
  URLs or ids, the `user{}` block of jobs, `seed`, and non-pricing params such as `selection` and `brief`.
- **Hashed:** job ids → `job_id = make_id("account_job", id)`; job-set ids → `job_set_key`.
- **Prompts:** replaced by `"<redacted:N chars>"`. The length is kept because per-character pricing needs it.
  `--with-prompts` keeps the text.
- **Input media:** reduced to stubs `{role, type, data: {type, url: "<media>.png"}}`. The estimator can still tell
  "1 input video, 2 images", but no one can see where the files are.
- **Unknown-shape lists** (free gens, grants, scoped credits, top-up options, personal promo) are scrubbed of every key
  matching id / url / email / avatar / stripe / customer / card / token / user / workspace / name keys.
- **Archives:** `AccountRedactionMiddleware` (`scrapers/account/redaction.py`) is a downloader middleware at priority
  582, added only for this spider through `AccountSpider.update_settings`. Its `process_response` runs before
  `HttpArchiveMiddleware` (580), so **`http/` (body.raw, HAR), `raw/`, the parser and the logs all see only the
  whitelisted body**. Non-JSON bodies (HTML challenge pages) are withheld. Account requests are marked `dont_cache`,
  so `--cache` never stores unredacted bodies. `personal_data=True` adds the core `redact_personal` pass on top.
  Request headers are masked by the framework (`Authorization: Bearer ***`). No `hf-workspace-id` header is sent.
- The public pricing bodies (`--compare-estimate`) are stored unchanged, like in `pricing` and `community`. They
  contain public catalog data only (preset authors' public ids, preview URLs), nothing about this account.
- `core/privacy.py` was **not** changed. Its key set does not cover ids, prompts or media URLs, which is why the
  redaction lives in this package.

## Outputs (`runs/<ts>_<label>/output/`)

| File | Content |
|---|---|
| `dataset.json` | `{schema_version, meta, snapshot, jobs, estimate_comparison, comparison_summary, pricing_basis, summary}` (indent 4) |
| `json/account_snapshot.json` | `plan`, `balances` (credits from `/user`), `wallet` (`<x>_units` raw ×100 **and** `<x>` in credits), `subscription` (+ `renewal_date`), `auto_top_up`, `notice`, `all_unlim`, `free_gens`, `generation_seconds`, `unlimited_grants`, `personal_promo`, `parts_fetched`, `parts_missing` |
| `json/account_jobs.json` | per job: `job_id` (hash), `job_set_key`, `job_set_type`, `status`, `created_at` (ISO UTC), `cost_units`, `actual_credits` (= cost/100), `resolution`, `duration`, `quality`, `batch_size`, `mode`, `aspect_ratio`, `model`, `use_unlim`, `input_images`, `input_videos`, `prompt_chars`, `prompt` (only with `--with-prompts`), `params` (pricing subset), `source` |
| `json/estimate_comparison.json` | per job: `actual_credits`, `estimated_credits`, `diff`, `abs_diff`, `ratio`, `match`, `comparable`, `not_comparable_reason`, `estimator_status`, `price_point_id`, `unit`, `quantity`, `quantity_basis`, `matched`, `assumed`, `notes` |
| `json/comparison_summary.json` | per `job_set_type`: jobs, comparable, matches, match_rate, exact / approximate / unpriced counts, mean_diff, totals |
| `csv/account_snapshot.csv`, `csv/account_jobs.csv`, `csv/estimate_comparison.csv`, `csv/comparison_summary.csv`, `csv/run_meta.csv` | complete flat tables (every JSON leaf is a column; lists are JSON text) |
| `summary.md` | snapshot summary, jobs by type and status, match rate per `job_set_type`, the first 20 mismatches |
| `items/*.jsonl` | validated entities (`account_snapshot_part`, `account_job`, `account_cost_basis`) |

Credits are `Decimal` values, serialized as strings. **Wallet balances and `jobs[].cost` are cost units (credits × 100):**
`credits_balance 888` → `8.88`, `cost 112` → `1.12`. `/user` balances are already in credits.

## Comparison method

1. The estimator is built exactly as in `community --estimate-cost`:
   `CostEstimator.from_job_costs_body(/job-sets/costs)`, then `with_viral_presets(...)` and
   `with_compare_fallback(compare, plan-benefits)`.
2. For each job, `est.estimate(job_set_type, params)` runs on the whitelisted params. A redacted prompt is expanded
   to an N-character placeholder, so per-character pricing still works.
3. `diff = actual − estimated`, `ratio = actual / estimated`.
   **`match` = |diff| ≤ 0.01 credits**, which is one cost unit, the API's resolution.
4. **`comparable`** requires all of the following:
   - `status == "completed"` (failed jobs are refunded, `cost = 0`);
   - an actual cost is present;
   - the estimator returned credits;
   - `params.use_unlim` is not true (such jobs may be free on an unlimited plan).
   Other jobs are listed with a `not_comparable_reason`.
5. `summary.md` and `comparison_summary` give the match rate per `job_set_type`.
   `estimator_status` (`exact` / `approximate`) shows whether a mismatch can come from assumed dimensions; the
   estimator's policy is lowest-cost for unknown options.

## Limits and gaps

- **Tested on one free personal workspace.** Team or paid accounts will fill more fields: seats, scoped credits,
  unlimited grants and auto top-up options. Their item shapes are unknown, so they are kept scrubbed as generic
  objects.
- **Cloudflare challenge on `/jobs/accessible` (2026-11-26).** Requests from the Scrapy crawl got
  `403 cf-mitigated: challenge`, while the earlier audit and a single plain GET got 200. The scraper does not try to
  get past it. The run is `partial` and records the block in `meta.limits_hit`. The estimate-vs-actual comparison
  could therefore not be run live; it is covered by offline tests on synthetic fixtures.
- **Job pagination** by `created_at` is inferred. Page size above 50 is not verified.
- Only the pricing-relevant params subset is kept, so an estimator dimension that reads a param outside the whitelist
  is not seen. The whitelist is built from the estimator's own key tables (`PARAM_DIMENSIONS`, `BATCH_KEYS`,
  `DURATION_KEYS`, media/reference keys, …), so it stays in sync automatically.
- `wallet.credit_limit` is assumed to be ×100, like the other wallet balances. It is stored raw as
  `credit_limit_units`.
- `renewal_date` is set only when the subscription is active, not cancelled, and the period end lies after the
  snapshot time. Free plans keep a stale period end from the past, so they get no renewal date.

## Files

`higgsfield_scraper/scrapers/account/`:
- `__init__.py` (ScraperDef)
- `endpoints.py`
- `options.py`
- `redaction.py` (whitelists + middleware)
- `parsers.py`
- `compare.py` (pure comparison math)
- `schemas.py`
- `dataset.py`
- `spider.py`

Tests: `tests/test_account.py`. Fixtures: `tests/fixtures/account/*.json` (synthetic; no real account data).
