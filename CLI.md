# CLI reference: `python -m higgsfield_scraper`

This file covers every command, option, choice, default and combination, with real example output (captured
2026-11-25) and when to use each one. With `pip install -e .`, `higgsfield-scraper …` can be used in place of
`python -m higgsfield_scraper …`.

```
python -m higgsfield_scraper <command> [options]

commands:
  scrape      fetch live data into a new run folder            (default if no command is given)
  normalize   re-parse a run's raw/ responses offline into a new run
  show        print tables from a run's dataset
  plan-sets   list plan_set_keys, presets and the frontend tier mapping
  sections    list sections and the endpoints they call
  runs        list recent runs
  schema      export JSON Schemas
  menu        interactive menu (also -i / --interactive; default with no args on a terminal)
```

`python -m higgsfield_scraper --sections plans` is the same as `python -m higgsfield_scraper scrape --sections plans`.
Every command accepts `-h / --help`.

## Interactive mode

A guided menu over the same commands. It needs the optional extra: `pip install -e ".[interactive]"`
(questionary + rich).

| How | Opens the menu? |
|---|---|
| `python -m higgsfield_scraper` with no arguments, stdin and stdout are a terminal, `CI` / `HF_NO_MENU` unset | yes |
| `python -m higgsfield_scraper menu` (aliases `-i`, `--interactive`) | yes |
| no arguments but piped / redirected / cron / CI | no: runs the pricing scrape exactly as before |

If the terminal can't run prompts (Git Bash/mintty without a console, no TTY, or questionary not installed),
`menu` prints a one-line hint and exits with code 2. On Git Bash, use Windows Terminal or `winpty python -m higgsfield_scraper`.

Menu items: **Scrape** (pick one or more scrapers, then for each one "quick (defaults)", "last used options" or
"customize". The customize step asks every option of `scrape <scraper> -h`, grouped as in `--help`. Then you set a
run label, review a summary showing the **equivalent flag command**, and choose Run / Dry run / Edit / Cancel),
**Normalize a past run**, **Browse runs** (table, summary.md, errors.log, open folder), **Login / session**
(auth-check, log in with the emailed 6-digit code, log out = delete `runs/.auth/clerk_client.json`), **Test request**
(one GET of a scraper's first public request: status, latency, size, JSON keys), **Show config**, **Clean old runs**
(dry run, then confirm), **Settings / prefs**, **Quit**.

- Every choice maps to a flag. The menu builds the same argv the flag CLI takes and parses it with the same parser.
  Answers that equal the default add no flag. Scrapers and their options are read from the registry and argparse,
  so a new scraper appears in the menu without menu code.
- Each scrape runs in its own child process (`python -m higgsfield_scraper.interactive.runner <same argv>`),
  because Scrapy's reactor can start only once per process. Several scrapers therefore run one after another,
  each in its own run folder. The child shows a live progress panel and records `"invocation": {"mode": "interactive"}`
  in the manifest.
- Ctrl-C in a prompt goes back; at the main menu it quits (exit 130). Ctrl-C during a crawl stops it gracefully,
  and the run is finalized as `cancelled` (exit 130). The menu then asks whether to run the remaining scrapers.
- Remembered choices (last scrapers, labels and options; never secrets) are stored in
  `%APPDATA%\higgsfield_scraper\prefs.json` (`~/.config/higgsfield_scraper/prefs.json` elsewhere). Set `HF_PREFS`
  to use another file.
- Passwords and codes are typed masked and are never printed or logged. If `HF_PASSWORD` is set, the menu offers to
  use it without showing it.

---

## Contents

1. [`scrape`](#1-scrape): all options
2. [Option details: every choice and when to use it](#2-option-details)
3. [Recipes: common combinations](#3-recipes)
4. [`normalize`](#4-normalize)
5. [`show`](#5-show)
6. [`plan-sets`, `sections`, `runs`, `schema`](#6-info-commands)
7. [Output: what a run produces](#7-output)
8. [Exit codes, environment variables, `.env`](#8-exit-codes-and-environment)
9. [Plain Scrapy (`scrapy crawl higgsfield -a …`)](#9-plain-scrapy)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. `scrape`

```
python -m higgsfield_scraper scrape [--sections S] [--plan-sets P] [--billing B] [--marketing-versions V] [--locale L]
                             [--plan-types T] [--models M] [--categories C]
                             [--usd-reference R] [--include-hidden-plans] [--include-raw-cost]
                             [--label X] [--runs-dir D] [--log-level LVL] [--file-log-level LVL] [--scrapy-log-level LVL]
                             [--token JWT] [--cache] [--dry-run]
```

| Group | Option | Default | Accepts |
|---|---|---|---|
| What to fetch | `--sections` | `plans,compare,benefits,models,marketing` | comma list of `plans compare benefits models marketing auth`, or `all` |
| | `--plan-sets` | `us` | comma list of any of the 25 `plan_set_key`s and/or presets `us`, `tiers`, `all` |
| | `--billing` | `monthly,annual` | `monthly`, `annual` (for `/compare`) |
| | `--marketing-versions` | `latest` | `latest`, `all`, or versions such as `v51,v50` / `51` / `v51.0.0` |
| | `--locale` | `en` (env `HF_LOCALE`) | `en de es fr ja ko pt-BR zh-CN` |
| Filters | `--plan-types` | all | comma list, for example `starter,plus,ultra,team,scale,basic,max` |
| | `--models` | all | comma list of substrings or globs (`*`, `?`, `[]`) matched against model id, family and name |
| | `--categories` | all | `video,image,audio,other` |
| Output | `--usd-reference` | `plus:annual` | `<plan_type>:<billing_period>`, for example `ultra:annual`, `plus:monthly` |
| | `--include-hidden-plans` | off | flag |
| | `--include-raw-cost` | off | flag |
| Run | `--label` | auto (`full-ps_a3`, `models-ps_a3`, …) | any text (slugified) |
| | `--runs-dir` | `runs` (env `HF_RUNS_DIR`) | path |
| | `--log-level` | `INFO` (env `HF_LOG_LEVEL`) | `DEBUG INFO WARNING ERROR` (console) |
| | `--file-log-level` | `DEBUG` | level for `run.log` and `events.jsonl` |
| | `--scrapy-log-level` | `INFO` | level for Scrapy's own loggers |
| Access | `--token` | env `HF_TOKEN` | Clerk session JWT (only for `auth`) |
| Dev | `--cache` | off | flag: Scrapy HTTP cache in `runs/.httpcache` (1 h) |
| | `--no-http-archive` | off (the archive is on) | flag: don't write `<run>/http/` |
| Robots | `--obey-robots` | off (robots.txt **not** obeyed) | flag: fetch robots.txt and skip disallowed URLs. Plain Scrapy: `-s ROBOTSTXT_OBEY=True` |
| | `--dry-run` | off | flag: print requests and exit, no network |

**Default run** (`python -m higgsfield_scraper scrape`). Console output, trimmed:

```
12:43:28 INFO    higgsfield_scraper.run: run 20261125-104328_first-live started -> D:\higgsfield-scraper\runs\20261125-104328_first-live
12:43:28 INFO    higgsfield_scraper.run: sections=['plans','compare','benefits','models','marketing'] plan_sets=['ps_a3'] endpoints=[…]
12:43:30 INFO    higgsfield_scraper.spiders.higgsfield: plans {'with_localization': 'true', 'plan_set_key': 'ps_a3'} -> 15 entities (15 after filters)
12:43:31 INFO    higgsfield_scraper.spiders.higgsfield: job_costs  -> 86 entities (86 after filters)
…
12:43:37 INFO    higgsfield_scraper.pipelines: dataset: plan_sets=1, plans=14, models=95, price_points=524, benefit_cards=24, comparisons=2, marketing_plans=26, …
12:43:37 INFO    higgsfield_scraper.run: run 20261125-104328_first-live finished: SUCCESS in 9.4s

[SUCCESS] run folder: D:\higgsfield-scraper\runs\20261125-104328_first-live
```

It takes about 10 s, makes 6 requests and downloads about 4 MB (most of that is the marketing config).

---

## 2. Option details

### `--sections`: what to fetch

| Value | Endpoint(s) called | Adds to the dataset | When to use |
|---|---|---|---|
| `plans` | `/subscriptions/v2/plans` (one per plan set) **+ `plan-benefits` + `compare`** for enrichment | `plan_sets[].plans[]`, `credit_values[]` | Prices before and after the offer, discounts, $/credit |
| `compare` | `/subscriptions/v2/compare` (per plan set × billing) | `comparisons[]` | Feature matrix, "how many videos per plan", Free plan, seats |
| `benefits` | `/subscriptions/v2/plan-benefits` | `benefit_cards[]`, `tab_badges` | Unlimited models, free generations, caps, campaigns per plan |
| `models` | `/job-sets/costs` **+ `plan-benefits` + `plans`** for names, entitlements and USD | `models[]` | Credit cost of every model and option |
| `marketing` | `pricing.higgsfield.ai/v2/pricing-config` | `marketing[]` | Card copy, taglines, feature lists, version history |
| `auth` | 4 login-only endpoints | `auth.credit_packages[]`, `auth.payloads[]` | Top-up packs, unlimited bundles, credit price. **Needs `--token`** |
| `all` | every section above (`auth` only if a token is set) | everything | Full snapshot |

Enrichment requests are fetched so the joins work, but their sections only appear in the output if you selected
them. For example, `--sections models` also calls `plans` (so it can compute USD estimates) but writes no
`plan_sets`.

```bash
$ python -m higgsfield_scraper scrape --sections auth --token x --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/packages   [auth]
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/bundle/unlim-catalog   [auth]
GET https://fnf-api-gw.higgsfield.ai/fnf/workspaces/credit-price   [auth]
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/adjustable-credits   [auth]
```

### `--plan-sets`: which price list

The site serves different price lists ("plan sets") to different visitors. All of them are in **USD**.

| Value | Expands to | Requests | When to use |
|---|---|---|---|
| `us` (default) | `ps_a3` | 1 plans + 2 compare | **US prices**, matching `higgsfield.ai/pricing.md` |
| `tiers` | `ps_a3, default, max_v1, max_v2` | 4 + 8 | What the frontend actually shows to tiers T1, T2, T3 and mobile |
| `all` | all 25 keys | 25 + 50 (~2 min) | Full catalogue of pricing experiments |
| `<key>[,<key>…]` | as given | | One specific variant, for example `max_v2_q` (quarterly plans) or `mcp` |

The 25 keys are: `mcp default default_basic default_q default_ww default_ww_q max_v1 max_v1_q max_v1_seedance_2_5
max_v1_ultra max_v2 max_v2_seedance_2_5 max_v2_q max_v2_ultra max_v3 ps_a1 ps_a2 ps_a3 ps_a3_basic ps_a3_q ps_a4
ps_a5 ps_a6 ps_a7 mob_v1`. You can mix presets and keys: `--plan-sets us,max_v2_q`.

```bash
$ python -m higgsfield_scraper scrape --dry-run --sections plans,compare --plan-sets tiers --billing annual
GET …/subscriptions/v2/plans?with_localization=true&plan_set_key=ps_a3
GET …/subscriptions/v2/plans?with_localization=true&plan_set_key=default
GET …/subscriptions/v2/plans?with_localization=true&plan_set_key=max_v1
GET …/subscriptions/v2/plans?with_localization=true&plan_set_key=max_v2
GET …/subscriptions/v2/compare?plan_set_key=ps_a3&billing_period=annual&with_localization=true
GET …/subscriptions/v2/compare?plan_set_key=default&billing_period=annual&with_localization=true
GET …/subscriptions/v2/compare?plan_set_key=max_v1&billing_period=annual&with_localization=true
GET …/subscriptions/v2/compare?plan_set_key=max_v2&billing_period=annual&with_localization=true
GET …/subscriptions/v2/plan-benefits?locale=en
```

The first plan set listed is the one used for `--usd-reference`.

### `--billing`

| Value | Effect |
|---|---|
| `monthly,annual` (default) | Two `/compare` tables per plan set |
| `monthly` or `annual` | Only that table (fewer requests) |

`/plans` always returns every billing period, including `quarterly` where a set has it. `--billing` only affects
`/compare`, which has no quarterly table.

### `--marketing-versions`

| Value | Requests | Output |
|---|---|---|
| `latest` (default) | 1 request for all versions (~4–6 MB), keeps the newest | 26 entries (13 plans × 2 periods) |
| `all` | same single request | all 51 versions (~1,000 entries) |
| `v51,v40` / `51` / `v51.0.0` | 1 small request **per version** (`planVersion=`) | only those versions |
| `latest,v40` | the all-versions request | newest + v40 |

```bash
$ python -m higgsfield_scraper scrape --dry-run --sections marketing --marketing-versions v51,v40
GET https://pricing.higgsfield.ai/v2/pricing-config?locale=en&planVersion=v51.0.0
GET https://pricing.higgsfield.ai/v2/pricing-config?locale=en&planVersion=v40.0.0
```

### `--locale`

`en` (default), `de`, `es`, `fr`, `ja`, `ko`, `pt-BR`, `zh-CN`. This changes the language of the plan-benefit labels
and the marketing copy. Prices, IDs and model costs stay the same.

### Filters: `--plan-types`, `--models`, `--categories`

Filters change only what is **written**. The same endpoints are still fetched, and `raw/` always holds the
complete responses.

| Option | Applies to | Matching |
|---|---|---|
| `--plan-types plus,ultra` | `plans`, `benefit_cards`, `marketing` | exact `plan_type` (case-insensitive) |
| `--models seedance,kling*` | `models` | without wildcards: **substring** of model_id, family or display name; with `* ? []`: **glob** |
| `--categories video,audio` | `models` | exact: `video`, `image`, `audio`, `other` |

When you combine filters, a model must match **both** `--models` and `--categories`.

| Example | Keeps |
|---|---|
| `--models seedance` | `seedance_2_0`, `seedance_2_0_mini`, `seedance_2_5`, `seedance_2_5_flash`, `seedance_2_5_kling_upscale` |
| `--models kling3_0` | `kling3_0`, `kling3_0_turbo`, `kling3_0_motion_control` (substring) |
| `--models "kling3_[0]"` | **only** `kling3_0` (a glob must match the whole id, so a `[]` class gives an exact match) |
| `--models "kling*"` | every Kling model, including `kling_o3_flf` and `kling_image_4_0` |
| `--models "gpt_image_*"` | the 4 GPT Image models |
| `--models nano --categories image` | Nano Banana models |
| `--categories audio` | 9 audio and TTS models |
| `--plan-types team,scale` | business plans only |

### `--usd-reference`

This chooses the plan whose **after-offer** price per credit converts model credits into `usd_estimate`.

| Value | $/credit (US, 2026-11-25) | Meaning |
|---|---|---|
| `plus:annual` (default) | $0.0250 | the plan most people buy |
| `ultra:annual` | $0.0150 (when a plan has several credit tiers, the **smallest** tier, 3k, is used) | heavy users |
| `plus:monthly` | $0.0333 | first month only |
| `starter:monthly` | $0.0704 | entry plan |
| `team:annual` | $0.0450 | per seat |

If the plan isn't in the first selected plan set, the run adds a warning to `meta.warnings` and leaves
`usd_estimate` empty.

### `--include-hidden-plans`

This keeps `free_trial`, `trial` and `secret` plan types, which the website hides. None appeared on 2026-11-25.
Use it to watch for secret or trial plans.

### `--include-raw-cost`

This embeds the untouched `cost` JSON in every `models[].raw_cost`, which adds about 75 KB. Use it when debugging
the cost normalizer or when you need a field the normalizer doesn't map. The full raw response is in
`raw/job_costs.json` either way.

### Run options

| Option | Use |
|---|---|
| `--label weekly` | The folder becomes `runs/<UTC yyyymmdd-HHMMSS>_weekly/`. Two runs in the same second get a `-2` suffix |
| `--runs-dir D:/data/hf` | Keep runs elsewhere |
| `--log-level WARNING` | Quiet console. The files still get everything |
| `--log-level DEBUG` | Show each item, raw save and Scrapy detail on the console |
| `--file-log-level INFO` | Smaller `run.log` and `events.jsonl` |
| `--scrapy-log-level WARNING` | Hide Scrapy's INFO lines (stats dump, middleware lists) |

### `--token`

A Clerk session JWT. Get it from DevTools → Application → Cookies → `https://higgsfield.ai` → `__session` while
logged in. It **expires after about 60 s**, so paste it right before running. The token is never written to the
manifest or the logs (it shows as `***`).

```bash
python -m higgsfield_scraper scrape --sections auth,plans --token "eyJhbGciOi…"
HF_TOKEN=eyJ… python -m higgsfield_scraper scrape --sections all      # also picks up auth
```

Without a token, `auth` endpoints return 401. The run is still `success` because these are optional, and the
manifest records `responses.credit_packages.401`.

### `--no-http-archive`

By default every run writes `<run>/http/`, a wire-level record of **every** HTTP exchange: API calls, robots.txt
checks, redirect hops, retries and failed requests. Each exchange gets a numbered folder:

```
http/
  index.jsonl                                   {"seq": 4, "endpoint": "plans", "status": 200, "bytes": 6270, "latency_ms": 313.0, "dir": "http/004_plans__plan_set_key-ps_a3", …}
  session.har                                   all exchanges, HAR 1.2. Open it in Chrome DevTools → Network → Import
  001_robots.txt__fnf-api-gw.higgsfield.ai/
  002_robots.txt_redirect__pricing.higgsfield.ai/   (pricing host's robots.txt redirects to Cloudflare Access; offsite → not followed)
  003_pricing_config__locale-en/
  004_plans__plan_set_key-ps_a3/
      request.json    {"method": "GET", "url": "…", "query": {…}, "headers": [{"name": "User-Agent", "value": "…"}, …], "sent_at": "…", "retry_times": 0}
      response.json   {"status": 200, "reason": "OK", "headers": [{"name": "Server", "value": "cloudflare"}, …], "bytes": 6270, "latency_ms": 313.0, …}
      body.raw        the exact bytes received
      curl.sh         curl -sS -X GET 'https://…/plans?…' -H 'Accept: …' -H 'User-Agent: …'
  …
```

Secrets are masked everywhere: `Authorization: Bearer ***`, `Cookie: ***` and `Set-Cookie: ***`.
How `raw/` and `http/` differ:
- `raw/` holds one pretty-printed JSON envelope per API response, used as input to `normalize`.
- `http/` holds the byte-exact traffic with headers and timings, used for debugging, auditing and replaying.

Use `--no-http-archive` to save disk space. It saves about 4 MB per run, mostly the duplicate body of the marketing
config. It also saves a few milliseconds per request on large `--plan-sets all` runs. Plain Scrapy:
`-s HIGGS_HTTP_ARCHIVE=False`.

### `--cache`

Development only. It stores responses in `runs/.httpcache` for 1 hour, so you can rerun parsers without hitting
the API. Never use it for real snapshots, because the data would be stale.

### `--dry-run`

Prints the exact GET requests and exits with no network and no run folder. Use it to check a combination before
running it.

```bash
$ python -m higgsfield_scraper scrape --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?with_localization=true&plan_set_key=ps_a3
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/compare?plan_set_key=ps_a3&billing_period=monthly&with_localization=true
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/compare?plan_set_key=ps_a3&billing_period=annual&with_localization=true
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plan-benefits?locale=en
GET https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs
GET https://pricing.higgsfield.ai/v2/pricing-config?locale=en
```

---

## 3. Recipes

| Goal | Command | Requests | Time |
|---|---|---|---|
| Daily US snapshot (everything public) | `python -m higgsfield_scraper scrape --label daily` | 6 | ~10 s |
| Only plan prices (before/after offer) | `python -m higgsfield_scraper scrape --sections plans --label prices` | 4 | ~5 s |
| Only model credit costs | `python -m higgsfield_scraper scrape --sections models --label costs` | 3 | ~5 s |
| Seedance and Kling video costs only | `python -m higgsfield_scraper scrape --sections models --models "seedance,kling" --categories video` | 3 | ~5 s |
| All image models with USD at the Ultra rate | `python -m higgsfield_scraper scrape --sections models --categories image --usd-reference ultra:annual` | 3 | ~5 s |
| Every pricing experiment | `python -m higgsfield_scraper scrape --sections plans --plan-sets all --label experiments` | 75 | ~2 min |
| What the frontend shows each tier | `python -m higgsfield_scraper scrape --sections plans,compare --plan-sets tiers` | 13 | ~25 s |
| Quarterly / Max plans | `python -m higgsfield_scraper scrape --sections plans --plan-sets max_v2_q,max_v1_q` | 6 | ~8 s |
| Business plans only | `python -m higgsfield_scraper scrape --sections plans,benefits --plan-types team,scale,enterprise` | 4 | ~5 s |
| Comparison matrix, annual only | `python -m higgsfield_scraper scrape --sections compare --billing annual` | 1 | ~3 s |
| Full marketing history | `python -m higgsfield_scraper scrape --sections marketing --marketing-versions all` | 1 | ~5 s |
| Compare copy v40 and v51 | `python -m higgsfield_scraper scrape --sections marketing --marketing-versions v40,v51` | 2 | ~4 s |
| German copy | `python -m higgsfield_scraper scrape --sections benefits,marketing --locale de` | 2 | ~5 s |
| Logged-in extras | `python -m higgsfield_scraper scrape --sections all --token "$HF_TOKEN"` | 10 | ~12 s |
| Everything possible | `python -m higgsfield_scraper scrape --sections all --plan-sets all --marketing-versions all --include-raw-cost --include-hidden-plans` | 78 | ~2 min |
| Quiet, for cron/CI | `python -m higgsfield_scraper scrape --label cron --log-level WARNING --scrapy-log-level WARNING` | 6 | ~10 s |
| Re-parse after a code change | `python -m higgsfield_scraper normalize --run runs/<id>` | 0 | ~3 s |

Windows Task Scheduler / cron example:

```bat
cd /d D:\higgsfield-scraper && .venv\Scripts\python -m higgsfield_scraper scrape --label daily --log-level WARNING
```

---

## 4. `normalize`

```
python -m higgsfield_scraper normalize [--run DIR] [all scrape selection/filter/output/run options]
```

This re-parses `DIR/raw/*.json` **offline** (no network) into a **new** run folder labelled `normalize` by default,
and copies the raw files into it.

| Option | Default | Notes |
|---|---|---|
| `--run` | latest run (`runs/LATEST`) | Source run folder |
| `--sections`, `--plan-sets` | taken from the source run's manifest when left at the defaults | Pass them explicitly when the source run used `all` |
| filters / `--usd-reference` / `--include-*` / `--locale` | as in `scrape` | Applied to the old data |
| `--label`, `--runs-dir`, log levels | as in `scrape` | |

When to use it:
- you changed a parser or schema (for example the `special_offer` fix) and want to rebuild old snapshots;
- you want a different filter or USD reference without re-fetching;
- you want to rebuild CSVs from an archived `raw/` folder.

```bash
$ python -m higgsfield_scraper normalize --run runs/20261125-104932_all-plan-sets --sections all --plan-sets all --label all-plan-sets-reparsed
[SUCCESS] run folder: D:\higgsfield-scraper\runs\20261125-105241_all-plan-sets-reparsed
```

---

## 5. `show`

```
python -m higgsfield_scraper show {plans|models|model|plan-sets|benefits|compare} [FILTER] [--run DIR] [--runs-dir D]
```

This reads `output/dataset.json` from the latest run, or from `--run`. It prints the dataset path to stderr and a
table to stdout.

| Subcommand | FILTER | Shows |
|---|---|---|
| `plans` | substring of `plan_type` | set, plan, billing, credits/mo, seats, before/after/renewal per month, off %, applies-to, $/credit |
| `models` | substring of id or name, **or** a category | one row per model: cheapest option, unit, discount flag, options |
| `model <model_id>` | exact model id (required) | every price point (component, dimensions, unit, credits, original, discount, example, ≈USD) + entitlements |
| `plan-sets` | — | plan set, country, number of plans, plan types |
| `benefits` | substring of `plan_type` | plan × billing × tab: unlimited models, free gens |
| `compare` | substring of a feature name | the matrix per plan set and billing (one column per plan type) |

**`show plans`** (US):

```
set    plan     billing  credits/mo  seats  before/mo $  after/mo $  renew/mo $  off %  applies        $/credit
-----  -------  -------  ----------  -----  -----------  ----------  ----------  -----  -------------  --------
ps_a3  Starter  monthly  270         1      19.00        19.00       19.00                             0.0704
ps_a3  Plus     monthly  1200        1      59.00        40.00       59.00       33.0   first_payment  0.0333
ps_a3  Plus     annual   1200        1      59.00        30.00       30.00       50.0   all_payments   0.0250
ps_a3  Ultra    monthly  3000        1      129.00       75.00       129.00      42.0   first_payment  0.0250
ps_a3  Ultra    annual   9000        1      387.00       115.00      115.00      70.0   all_payments   0.0128
ps_a3  Team     monthly  1000        2      79.00        55.00       55.00       30.0   all_payments   0.0550
ps_a3  Scale    annual   2500        5      215.00       80.00       80.00       63.0   all_payments   0.0320
…
```

Reading it: **before** is the list price, **after** is what you pay now, and **renew** is what you pay next period.
`first_payment` means the discount applies only to the first payment. `all_payments` means it continues on renewal.

**`show models audio`**:

```
model_id                   name                       cat    points  min credits  unit                       disc  options
-------------------------  -------------------------  -----  ------  -----------  -------------------------  ----  ---------------------------------
dubbing_lipsync            Dubbing Lipsync            audio  3       3.0          credits_per_second               fps=25/30/60
elevenlabs_v4              Elevenlabs V4              audio  1       0.23         credits_per_50_characters
elevenlabs_video_to_music  Elevenlabs Video To Music  audio  3       4.0          credits_per_minute               model_id=music_v1/music_v2/music_v2_5
text2speech_v2             Text2speech V2             audio  5       0.05         credits_per_50_characters        model=minimax/elevenlabs/seed_speech/vibe_voice/cozy_voice
…
```

**`show model gpt_image_2_6`**:

```
GPT Image 2.6 (gpt_image_2_6) — image, family gpt_image
options: {"quality": ["low", "medium", "high", "xhigh", "max"], "resolution": ["1k", "2k", "4k"]}
component  dimensions                    unit                    credits  orig  disc  example  ≈USD
---------  ----------------------------  ----------------------  -------  ----  ----  -------  ------
           quality=low resolution=1k     credits_per_generation  0.75     0.75                 0.0188
           quality=max resolution=4k     credits_per_generation  12.0     12.0                 0.3
…
entitlements:
plan   billing  type       count  days  max res
pro    monthly  unlimited         7     2K
plus   annual   unlimited         7     2K
…
```

**`show model seedance_2_5`** (video, per second, with an input-video option and an edit component):

```
component   dimensions                                  unit                credits  example                            ≈USD
            resolution=720p video_input=without_video   credits_per_second  7.0      {"seconds": 5, "credits": 35.0}    0.875
video_edit  resolution=720p                             credits_per_second  7.5      {"seconds": 5, "credits": 37.5}    0.9375
            resolution=4k video_input=with_video        credits_per_second  34.0     {"seconds": 5, "credits": 170.0}   4.25
```

**`show compare concurrent`**:

```
## ps_a3 / annual
category        feature                 detail  free                     starter                   plus                              ultra                             team                       scale
video           Concurrent Generations          1 concurrent generation  2 concurrent generations  Unlimited concurrent generations  Unlimited concurrent generations  16 concurrent generations  32 concurrent generations
```

**`show benefits plus`**:

```
plan  billing  tab         unlimited                                                         free gens
plus  monthly  individual  seedream_v5_pro,gpt_image_2_6,gpt_image_2_6_flare,nano_banana,…   hf_mult_motion_controlx2,soul_cinematicx3000,…
plus  annual   individual  nano_banana_2,seedream_v5_pro,gpt_image_2_6,…                     hf_mult_motion_controlx3,soul_cinematicx5000,…
```

**`show plan-sets`** (after `--plan-sets all`):

```
plan_set_key         country  plans  plan types
default              EG       14     starter,plus,ultra,team,scale
max_v2_q             EG       13     basic,plus,ultra,max,team,scale
mcp                  EG       4      plus,ultra
mob_v1               EG       2      plus
ps_a3                EG       14     starter,plus,ultra,team,scale
…                                    (25 rows)
```

Errors: `show model nope` prints `model 'nope' not found` and exits 1. With no runs, it prints
`no dataset found; run ``python -m higgsfield_scraper scrape`` first` and exits 1.

---

## 6. Info commands

**`plan-sets`**: static knowledge, no network.

```
Presets:
  us     -> ps_a3
  tiers  -> ps_a3, default, max_v1, max_v2
  all    -> 25 keys

Frontend tier mapping (from JS): T1->ps_a3, T2->default, T3->max_v1, mobile->max_v2
US prices (pricing.md) = ps_a3

All plan_set_keys accepted by the API:
  mcp
  default
  …
```

**`sections`**

```
plans      (default)
    https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans
compare    (default)
    https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/compare
benefits   (default)
    https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plan-benefits
models     (default)
    https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs
marketing  (default)
    https://pricing.higgsfield.ai/v2/pricing-config
auth       (needs --token)
    https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/packages   [auth]
    …
```

**`runs [--limit N] [--runs-dir D]`** (default 20), read from `runs/index.jsonl`:

```
run_id                                  status   secs    country  counts
20261125-104932_all-plan-sets           partial  123.74  EG       plan_sets=23, plans=340, models=95, …
20261125-105241_all-plan-sets-reparsed  success  4.75    EG       plan_sets=25, plans=340, models=95, …
```

**`schema [--out DIR]`** (default `schemas/`) writes `dataset.schema.json` plus one schema per entity:
`plan_set plan model benefit_card comparison marketing_plan credit_package auth_payload`.

```
wrote 9 schemas to schemas
```

---

## 7. Output

```
runs/<yyyymmdd-HHMMSS>_<label>/
  manifest.json      status, args (token masked), selection, versions (python/scrapy/pydantic/git),
                     started/finished/duration, counts, responses {endpoint: {status: n}}, scrapy_stats, files[]
  logs/run.log       all loggers          logs/app.log     higgsfield_scraper.* only
  logs/scrapy.log    scrapy/twisted       logs/errors.log  WARNING+
  logs/events.jsonl  one JSON object per log line (ts, level, logger, run_id, msg, endpoint, status…)
  raw/<endpoint>__<params>.json    {"meta": {endpoint,url,params,status,fetched_at}, "body": <untouched>}
  http/index.jsonl                 one line per HTTP exchange (incl. robots.txt, redirects, retries, errors)
  http/session.har                 HAR 1.2 of the whole run (import into Chrome DevTools)
  http/NNN_<endpoint>__<params>/   request.json, response.json (all headers, status, latency), body.raw (exact bytes), curl.sh
  output/dataset.json              everything, nested (see README §5)
  output/summary.md                plans table + cheapest option per model
  output/json/{plans,plan_sets,credit_values,models,benefit_cards,comparisons,marketing,auth,meta}.json
  output/csv/                          COMPLETE: every JSON field is a column (nested -> dotted, lists -> JSON text)
    run_meta.csv                       key/value: meta (counts, versions, usd_reference, warnings…) + tab_badges
    plan_sets.csv                      one row per plan set (special_offer, country, plan types)
    plans.csv                          one row per plan: pricing.*, discount.*, savings.*, price_per_credit.*, …
    credit_values.csv                  $/credit per plan
    models.csv                         one row per model (options.*, units, components, raw_cost…)
    model_price_points.csv             one row per price point: dimensions.*, example.*, attributes.*, formula.*
    model_entitlements.csv             model × plan unlimited/free-gens (concurrency.*)
    benefit_cards.csv                  card: campaign.*, availability.*, tab_badge.*, unlimited_model_ids, free_gens
    benefit_sections.csv               section: kind, title, data.* (hero grants, seat bonus, banners)
    benefit_rows.csv                   row: entitlement.* incl. caps.*
    comparisons.csv / comparison_plans.csv / comparison_categories.csv
    comparison_matrix.csv              plan set × billing × feature × plan
    marketing_plans.csv                tagline, credits_*, billing_periods.*, ui.*, special_deal
    marketing_promo_items.csv          promo lines per plan
    marketing_features.csv             version × plan × group × feature
    auth_credit_packages.csv / auth_payloads.csv   (with --token)
  output/items/<kind>.jsonl            Scrapy feeds written live during the crawl (one item per line, before joins)
  output/schema/dataset.schema.json
runs/LATEST          newest run id      runs/index.jsonl   one summary line per run
```

All `.json` files use **4-space indentation**. The `.jsonl` files hold one object per line, as that format requires.

---

## 8. Exit codes and environment

| Exit code | Status | Meaning |
|---|---|---|
| 0 | `success` | Every public endpoint returned 200, and every item validated |
| 2 | `partial` | Output was written, but there was a non-200 public response, a request error, or a dropped (invalid) item. Check `logs/errors.log` and `manifest.json` |
| 1 | `failed` | No dataset was produced (crash, interrupted, or assembly error). `raw/` is kept |
| 2 | — | Bad arguments (`error: unknown plan_set_key(s): ['bogus']; run python -m higgsfield_scraper plan-sets`) |

| Env var | Equivalent |
|---|---|
| `HF_TOKEN` | `--token` |
| `HF_LOCALE` | `--locale` |
| `HF_RUNS_DIR` | `--runs-dir` |
| `HF_LOG_LEVEL` | `--log-level` |
| `HF_LIVE=1` | enables live tests in pytest |

A `.env` file in the working directory is loaded automatically. Variables already set in the environment take
precedence. See `.env.example`.

---

## 9. Plain Scrapy

The spider also works with `scrapy crawl`. Every option becomes `-a name=value`, using underscores:

```bash
scrapy crawl higgsfield
scrapy crawl higgsfield -a sections=models -a models=seedance
scrapy crawl higgsfield -a sections=all -a plan_sets=tiers -a billing=annual -a locale=de
scrapy crawl higgsfield -a sections=plans -a plan_types=plus,ultra -a usd_reference=ultra:annual
scrapy crawl higgsfield -a sections=auth -a token=eyJ…
scrapy crawl higgsfield -a include_hidden_plans=true -a include_raw_cost=true -a marketing_versions=all
scrapy crawl higgsfield -s HIGGS_RUNS_DIR=D:/data -s HIGGS_RUN_LABEL=nightly -L WARNING
```

Spider args: `sections plan_sets billing plan_types models categories marketing_versions locale
include_hidden_plans include_raw_cost usd_reference token`.

This still creates `runs/<ts>_scrapy-crawl/` with `raw/` and `output/`, but **no manifest and no log files**
(Scrapy's own logging goes to the console). Use the CLI for fully managed runs.

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `[PARTIAL]` + `invalid plan_set …` in errors.log | The API returned a shape the schema doesn't allow yet. Fix `higgsfield_scraper/schemas/`, then `normalize --run <that run>` |
| `responses.plans.403` or `429` in the manifest | Blocked or rate-limited. Wait and run less often. Don't add evasion |
| `responses.credit_packages.401` | No or expired token. This is normal without `--token` |
| `usd_reference … not found` warning | That plan type or billing doesn't exist in the first selected plan set. Pick another `--usd-reference` or reorder `--plan-sets` |
| Prices differ from the website | You're seeing a different plan set (tier) or country. Check `meta.country_code` and use `--plan-sets tiers` |
| `model 'x' not found` in `show model` | Use the exact `model_id` (`show models x` lists matches) |
| `no dataset found` | No run yet, or `--run` points to a folder without `output/dataset.json` |
| Garbled `≈` / `—` in the console | The CLI forces UTF-8. In old consoles run `chcp 65001` |
