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
(auth-check, log in with the emailed 6-digit code, log out = delete `runs/.auth/clerk_client.json`), **Pricing tools** (`diff` latest vs previous or two
picked runs, optional `.md`/`.json` report; `crosscheck` a run with pricing.md, optional `--save`), **Test request**
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

1. [`scrape` pricing](#1-scrape-pricing-the-default-scraper): all options
   [1b. Every scraper: complete option reference](#1b-every-scraper-complete-option-reference) (community, catalog, projects, blog, shared, limits, logging)
2. [Option details: every choice and when to use it](#2-option-details)
3. [Recipes: common combinations](#3-recipes)
4. [`normalize`](#4-normalize)
5. [`show`](#5-show)
6. [`scrapers`, `login`, `auth-check`, `runs`, `runs clean`, `show-config`, `diff`, `crosscheck`, `plan-sets`, `sections`, `schema`](#6-info-commands)
7. [Output: what a run produces](#7-output)
8. [Exit codes, environment variables, `.env`](#8-exit-codes-and-environment)
9. [Plain Scrapy (`scrapy crawl higgsfield -a …`)](#9-plain-scrapy)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. `scrape` (pricing, the default scraper)

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
| Access | `--auth` | `auto` | `auto` (use the saved login when there is one), `off`, `required`. Login: `login` (see §6) |
| | `--token` | env `HF_TOKEN` | deprecated one-off Clerk JWT; prefer `login` |
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

## 1b. Every scraper: complete option reference

`scrape` with no scraper name means `scrape pricing` (backward compatible). Every scraper takes the shared options;
community, catalog, projects and blog also take the limit/media options. Per-scraper guides: `docs/scrapers/`.

<!-- BEGIN scraper-options -->
<!-- generated from the argparse definitions; regenerate with scripts/gen_cli_tables.py -->

### Shared options (every scraper)

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--token` | — | TOKEN | Clerk session JWT (~60 s). Prefer HF_CLERK_CLIENT or HF_EMAIL/HF_PASSWORD in .env for auto refresh |
| `--auth` | `auto` | `auto` `off` `required` | auto: use login when configured (default) \| off: never send tokens \| required: skip login-only endpoints when no session |
| `--cache` | off | flag | enable Scrapy HTTP cache (dev) |
| `--no-http-archive` | off | flag | don't write &lt;run&gt;/http/ (per-request request.json, response.json, body.raw, curl.sh, session.har) |
| `--obey-robots` | off | flag | check and obey robots.txt (default: off — robots.txt is not obeyed) |
| `--delay` | `1.0` | DELAY | seconds between requests per domain (default 1.0) |
| `--concurrency` | `2` | CONCURRENCY | parallel requests per domain (default 2) |
| `--max-requests` | `5000` | MAX_REQUESTS | hard cap on HTTP responses (default 5000) |
| `--max-minutes` | — | MAX_MINUTES | stop the crawl after N minutes |
| `--no-stop-on-block` | off | flag | keep going after a bot-protection (captcha) response instead of stopping |
| `--dry-run` | off | flag | print the first requests that would be made and exit |
| `--label` | — | LABEL | run label (folder suffix) |
| `--runs-dir` | `runs` | RUNS_DIR |  |
| `-v` / `--verbose` | off | flag | -v: project DEBUG on the console, -vv: Scrapy DEBUG too |
| `-q` / `--quiet` | off | flag | console shows warnings and errors only |
| `--log-level` | — | LOG_LEVEL | console level (DEBUG/INFO/WARNING/ERROR); wins over -v/-q (env HF_LOG_LEVEL, default INFO) |
| `--log-format` | `console` | `console` `json` | console: Rich text on stderr (default) \| json: one JSON object per line on stderr (env HF_LOG_FORMAT) |
| `--no-color` | off | flag | plain console output (also honours the NO_COLOR environment variable) |
| `--heartbeat` | — | SECONDS | seconds between worker.heartbeat events / manifest progress updates (default 30, 0 = off) |
| `--file-log-level` | `DEBUG` | FILE_LOG_LEVEL | level of logs/events.jsonl and logs/run.log |
| `--scrapy-log-level` | — | SCRAPY_LOG_LEVEL | Scrapy's own loggers (default INFO, -vv: DEBUG) |
| `--split-logs` | off | flag | also write logs/app.log and logs/scrapy.log |

### Limits and media (community, catalog, projects, blog, site, account)

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--max-items` | — | MAX_ITEMS | stop after N primary items (default: no limit) |
| `--max-pages` | — | MAX_PAGES | max pages per paginated listing |
| `--page-size` | — | PAGE_SIZE | items per API page (clamped to the API maximum) |
| `--download-media` | `none` | `none` `thumbs` `full` `all` | none (links only, default) \| thumbs \| full \| all — files go to &lt;run&gt;/media/ |
| `--max-media-files` | `500` | MAX_MEDIA_FILES | cap on downloaded files (default 500) |
| `--max-media-mb` | `1024.0` | MAX_MEDIA_MB | cap on downloaded MB (default 1024) |

### `scrape pricing`

Plans, offers (before/after), renewal, discounts, per-model credit costs, benefits, comparison, marketing copy; optional logged-in top-ups/bundles

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--sections` | `plans,compare,benefits,models,marketing` | SECTIONS | comma list of ['account', 'auth', 'benefits', 'compare', 'marketing', 'models', 'plans'] or 'all' (default: plans,compare,benefits,models,marketing) |
| `--plan-sets` | `us` | PLAN_SETS | plan_set_keys or presets ['all', 'tiers', 'us'] (default: us = ps_a3) |
| `--billing` | `monthly,annual` | BILLING | billing periods for /compare (default: monthly,annual) |
| `--marketing-versions` | `latest` | MARKETING_VERSIONS | latest \| all \| comma list like v51,v50 (default: latest) |
| `--locale` | `en` | LOCALE | en, de, es, fr, ja, ko, pt-BR, zh-CN |
| `--plan-types` | — | PLAN_TYPES | e.g. plus,ultra,team (default: all) |
| `--models` | — | MODELS | model patterns, e.g. seedance,kling*,gpt_image_2_6 |
| `--categories` | — | CATEGORIES | video,image,audio,other |
| `--usd-reference` | `plus:annual` | USD_REFERENCE | plan_type:billing_period whose after-offer $/credit prices model USD estimates |
| `--include-hidden-plans` | off | flag | keep trial/secret plan types |
| `--include-raw-cost` | off | flag | embed each model's untouched cost JSON |
| `--logged-in-prices` | off | flag | also fetch plans + model costs WITH the session and add the rows only logged-in users see (e.g. the Lite annual plan, magi_2), tagged visibility=logged_in; anonymous rows unchanged. Needs a login (skipped with a warning otherwise); --auth off disables it. Use --sections account for the account's own balances |

### `scrape community`

Community generations: model (job_set_type), prompt, settings, inputs, results, engagement; optional creator profiles (opt-in), detail, Community-post comments and estimated credit cost

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--feeds` | `trending` | FEEDS | comma list of feeds: trending (main feed, ~78.6k), approved (curated, ~6.7k, mostly video), top (single page, &lt;=100), model-x (featured model showcase), 'all', or 'none' (only --publication-ids) (default: trending) |
| `--type` | `all` | `all` `image` `video` `speak` `upscale` | media type filter (API `type`). image\|video are also enforced client-side because the approved feed ignores it; speak\|upscale are server-side only (default: all) |
| `--models` | — | JOB_SET_TYPES | job_set_type filter, comma list and/or repeatable, e.g. --models seedance_2_5,nano_banana_2 (API `model`, trending/approved; enforced client-side for top/model-x) |
| `--preset-ids` | — | IDS | preset/motion id filter (API `preset_id`, repeatable). Passed through; server effect unverified |
| `--resolution` | — | RESOLUTION | API `resolution` filter (passed through; the trending feed ignores it, approved returned 0 items for 720p in tests — use with care) |
| `--publication-ids` | — | IDS | also fetch these publications by id (GET /publications/{id}); their feed is 'detail' |
| `--with-profiles` | off | flag | PERSONAL DATA: include creators' username, avatar, social handles and badges (creators table). Default: only the pseudonymous user_id |
| `--with-raw-params` | off | flag | keep each generation's untouched `params` dict (raw_params) next to the normalized fields |
| `--detail` | off | flag | fetch GET /publications/{id} for every listed item and use that (1 extra request per item) |
| `--with-comments` | off | flag | fetch comments (+ replies) from the Community posts service (fnf-community): reads the posts feed (limit = --max-items, max 50) and the threads of posts that have comments. Gallery generations have no comments. Public; commenter identities only with --with-profiles |
| `--estimate-cost` | `off` | `off` `images` `videos` `all` | attach an estimated credit cost per generation from /job-sets/costs: off (default) \| images \| videos \| all. An estimate, not what the creator actually paid |
| `--usd-reference` | `plus:annual` | USD_REFERENCE | plan_type:billing_period whose after-offer $/credit converts credits to USD (default: plus:annual) |
| `--usd-plan-set` | `ps_a3` | USD_PLAN_SET | plan_set_key used for the USD reference plan (default: ps_a3) |

```bash
python -m higgsfield_scraper scrape community --max-items 300
python -m higgsfield_scraper scrape community --feeds approved --type video --max-items 100
python -m higgsfield_scraper scrape community --feeds trending --models nano_banana_2,seedream_v4_5 --max-items 500
python -m higgsfield_scraper scrape community --max-items 200 --estimate-cost all
python -m higgsfield_scraper scrape community --max-items 50 --with-profiles --download-media thumbs
```

### `scrape catalog`

Preset & asset catalogs: motions (+samples/details), avatars, voices, sounds, styles, soul samples, viral-hub presets; opt-in (`--kinds login`) soul styles, per-model motions, mixed media, katana, ...

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--kinds` | — | KINDS | comma list of catalog kinds (short names like motion,voice or catalog_motion), or 'public' (default), 'login', 'all'. Opt-in extras (only by name or 'all'): chain_preset, notice, restyle_preset. Available: motion, motion_sample, avatar, avatar_preset, voice, reference_voice, sound, style, soul_sample, viral_type, viral_preset, soul_style, mixed_media_preset, model_motion, katana_category, katana_preset, color_preset, youtube_faceless_preset, camera_setting, marketing_category, marketing_preset, chain_preset, notice, restyle_preset |
| `--with-samples` | off | flag | also fetch the sample videos of every motion (1 request per motion, ~419; --max-pages caps the number of sample requests) |
| `--with-details` | off | flag | also fetch /motions/{id} per motion (adds description + real preview media for the kling/minimax/seedance/wan families; ~419 requests; --max-pages caps them) |
| `--lang` | `en` | LANG | language for viral-hub, soul styles, mixed media, katana (default: en) |
| `--include-login-only` | `auto` | `auto` `yes` `no` | the opt-in `login` group (soul/veo3 styles, per-model motions, mixed media, katana, faceless, marketing presets: public CMS lists; color presets + camera settings: need a login). Adds it to the default selection: auto = when logged in (default), yes = always (login-only ones skipped cleanly without a session), no = never. `--kinds all\|login` always includes it |
| `--keep-placeholders` | off | flag | keep the base64 blur placeholders (data: URIs) found in media objects (large) |
| `--include-hidden` | off | flag | chain_preset: also fetch the presets the app hides (show_hidden=true; 1 extra request, ~10 more presets). They are marked is_hidden=true; visible ones keep is_hidden=false |
| `--with-profiles` | off | flag | opt-in: keep creator credits of the opt-in extras (chain_preset `collaborator`) and the katana preset authors (default: dropped / redacted) |

```bash
python -m higgsfield_scraper scrape catalog
python -m higgsfield_scraper scrape catalog --kinds motion,voice,sound
python -m higgsfield_scraper scrape catalog --kinds motion --with-samples --with-details --max-pages 50
python -m higgsfield_scraper scrape catalog --kinds all --include-login-only yes
python -m higgsfield_scraper scrape catalog --kinds viral_preset --lang de --download-media thumbs
```

### `scrape projects`

Community projects (films/series/carousels), recommended feeds, contest entries, contests (rules, rewards, judges, winners) and contest submissions

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--what` | `all` | WHAT | comma list of ['publications', 'recommended', 'contests', 'entries', 'series'] or 'all' (default). 'series' needs a login session unless --public-series |
| `--categories` | — | CATEGORIES | publication category slugs (server-side filter), e.g. spotlight,open-sourced-by-higgsfield |
| `--featured` | off | flag | publications listing: only featured (featured=true) |
| `--scope` | `all` | SCOPE | recommended feed scopes: ['community', 'ai_film_festival', 'talent_contest', 'ad_contest', 'discord'] or 'all' (default) |
| `--with-details` | off | flag | fetch each publication's / contest's detail endpoint (stats, rules, rewards, prizes, winners…) |
| `--with-submissions` | off | flag | fetch every contest's submissions (paginated) |
| `--contest-status` | `all` | `open` `closed` `all` | open (created/open/shortlist/judge) \| closed (finished) \| all (default) |
| `--contest-types` | `all` | CONTEST_TYPES | global,weekly or 'all' (default) |
| `--entry-keys` | `all` | ENTRY_KEYS | contest entries (contest-participations) for ['ai_film_festival', 'talent_contest'] or 'all' |
| `--entry-tab` | `latest` | `latest` `trending` `most_watched` `all_entries` `submissions` `liked` `voted` | ordering/tab of the contest-entries listing (default latest = every entry) |
| `--submission-ordering` | `newest` | `newest` `most-liked` `most-viewed` `trending` |  |
| `--max-submissions` | — | MAX_SUBMISSIONS | cap submissions per contest (default: all) |
| `--public-series` | off | flag | series: use the public fnf-series service (no login; 35 series, --with-details adds /series/{slug}; --max-items caps the series). Without it series keep the legacy login-only fnf path (skipped without a session) |
| `--with-profiles` | off | flag | opt-in: include authors'/contestants' usernames, names, avatars, headlines, locations, judge links and profile-based page URLs (default: pseudonymous author keys only) |

```bash
python -m higgsfield_scraper scrape projects --max-items 200
python -m higgsfield_scraper scrape projects --what contests --with-details --with-submissions
python -m higgsfield_scraper scrape projects --what publications --categories spotlight --with-details
python -m higgsfield_scraper scrape projects --what recommended --scope ai_film_festival --max-pages 2
python -m higgsfield_scraper scrape projects --what contests --contest-status closed --contest-types weekly
python -m higgsfield_scraper scrape projects --what publications --max-items 50 --download-media thumbs
```

### `scrape blog`

Blog posts + authors, talent/community posts, Creator Hub help center, case studies, changelog, Enterprise help center — metadata and full article text (Markdown/plain text)

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--what` | `blog,talents,help,enterprise-help,case-studies,changelog` | WHAT | comma list of ['blog', 'talents', 'help', 'enterprise-help', 'case-studies', 'changelog', 'community'] or 'all' (default: blog,talents,help,enterprise-help,case-studies,changelog; 'community' = the large user blog feed /blog/posts/recommended, opt-in) |
| `--with-content` | off | flag | fetch the full article text (default: on) |
| `--no-content` | off | flag | metadata only from the index pages / feeds (~10 requests): no per-article pages, no post bodies; text fields stay empty |
| `--locale` | `en` | LOCALE | one of ['en', 'es', 'ja', 'ko', 'de'] (default: en; others fall back to English where no translation exists) |
| `--tags` | — | TAGS | keep posts whose category slug/title or tags match (comma list) |
| `--since` | — | SINCE | keep items published/updated on or after YYYY-MM-DD |
| `--include-author-avatars` | off | flag | keep community/talent authors' avatar URLs (personal data; off by default) |
| `--no-markdown` | off | flag | don't write output/articles/&lt;collection&gt;/&lt;slug&gt;.md |

```bash
python -m higgsfield_scraper scrape blog
python -m higgsfield_scraper scrape blog --what help,enterprise-help --label help-only
python -m higgsfield_scraper scrape blog --what blog --since 2026-10-01 --tags guides,comparisons
python -m higgsfield_scraper scrape blog --no-content --label metadata-only
python -m higgsfield_scraper scrape blog --what talents,community --max-pages 3
python -m higgsfield_scraper scrape blog --what blog --download-media thumbs
```

### `scrape site`

Site pages: apps (+ credit cost), academy courses & lessons (Markdown), MCP skills & bundles, original-series episodes, mixed-media presets, landing/plugin pages, rooms (opt-in), promo APIs

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--what` | `apps,academy,mcp,originals,mixed-media,landings,promos` | WHAT | comma list of ['apps', 'academy', 'mcp', 'originals', 'mixed-media', 'landings', 'rooms', 'promos'] or 'all' (default: apps,academy,mcp,originals,mixed-media,landings,promos; 'rooms' = community room pages, title/description only, opt-in) |
| `--with-content` | off | flag | fetch every detail page (apps, courses, lessons, MCP skills, episodes) and convert bodies to Markdown (default: on) |
| `--no-content` | off | flag | index pages only where an index exists (apps, academy, mcp, originals): fewer requests, no lesson/landing text |
| `--only` | — | ONLY | keep only detail pages whose URL path contains one of these strings (comma list), e.g. 'kling,/plugins/,blockbuster-4k' |
| `--with-profiles` | off | flag | keep creators' usernames/avatars (app authors, episode uploaders, mixed-media sample creators). Personal data: off by default |
| `--no-markdown` | off | flag | don't write output/articles/&lt;collection&gt;/&lt;slug&gt;.md |

```bash
python -m higgsfield_scraper scrape site
python -m higgsfield_scraper scrape site --what apps --label apps
python -m higgsfield_scraper scrape site --what academy --only blockbuster-4k
python -m higgsfield_scraper scrape site --what mcp,promos --no-content
python -m higgsfield_scraper scrape site --what landings --only /plugins/,kling --max-items 10
python -m higgsfield_scraper scrape site --what originals,mixed-media --download-media thumbs
python -m higgsfield_scraper scrape site --what all,rooms --max-items 20 --label smoke-site
```

### `scrape account`

OPT-IN, login required: your own balances/plan/subscription snapshot, your jobs with the credits actually charged (--with-jobs) and estimate-vs-actual checks (--compare-estimate)

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--with-jobs` | off | flag | also read your own jobs from /jobs/accessible (paginated; --max-items / --max-pages apply): job_set_type, status, created_at, pricing-relevant params and the actual credits charged |
| `--compare-estimate` | off | flag | needs --with-jobs: run the CostEstimator on each job's params and compare it with the credits actually charged (fetches the public /job-sets/costs etc.) |
| `--job-types` | — | JOB_TYPES | needs --with-jobs: comma list of job_set_type values to request (server-side filter) |
| `--with-prompts` | off | flag | opt-in: STORE YOUR OWN PROMPT TEXT (prompt, negative_prompt, text …) in the dataset and in the raw/ and http/ archives. Default: prompts are replaced by their length only |

```bash
python -m higgsfield_scraper scrape account
python -m higgsfield_scraper scrape account --with-jobs --max-items 100
python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20
```
<!-- END scraper-options -->

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
| `all` | every section above; `auth` is included when you are logged in (`login`, `HF_CLERK_CLIENT` or `--token`), or when you write `all,auth` | everything | Full snapshot |

Enrichment requests are fetched so the joins work, but their sections only appear in the output if you selected
them. For example, `--sections models` also calls `plans` (so it can compute USD estimates) but writes no
`plan_sets`.

```bash
$ python -m higgsfield_scraper scrape --sections auth --dry-run
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

### `--token` (deprecated; prefer `login`)

**Recommended instead:** put `HF_EMAIL`/`HF_PASSWORD` in `.env` and run `login` once (see
[§6](#6-info-commands)), or set `HF_CLERK_CLIENT`. The scraper then mints fresh tokens automatically and refreshes
on `401`. `--token` still works but logs a `cli.flag.deprecated` warning.

A Clerk session JWT. Get it from DevTools → Application → Cookies → `https://higgsfield.ai` → `__session` while
logged in. It **expires after about 60 s**, so paste it right before running. The token is never written to the
manifest or the logs (it shows as `***`).

```bash
python -m higgsfield_scraper scrape --sections auth,plans --token "eyJhbGciOi…"
HF_TOKEN=eyJ… python -m higgsfield_scraper scrape --sections all      # also picks up auth
```

### Logged-in pricing (`auth` section)

With a saved login (`login`), every pricing scrape adds the login-only endpoints automatically when you use
`--sections all` (or name `auth`). Tokens are minted and refreshed by the shared auth layer (refresh + one retry on
`401`), exactly like the other scrapers. Verified 2026-11-26:

| Endpoint | Logged in (personal account) | Output |
|---|---|---|
| `/subscriptions/v2/packages` | 200: 6 credit top-up packs (100 … 4,000 credits) | `auth.credit_packages[]`, `csv/auth_credit_packages.csv` |
| `/subscriptions/bundle/unlim-catalog` | 200: `{"bundles": []}` | `auth.payloads[]` |
| `/subscriptions/v2/adjustable-credits` | 200: 12 credit-slider tiers | `auth.payloads[]` |
| `/workspaces/credit-price` | **500** for accounts without a team workspace (the site only calls it from the team credit-purchase screen) | warning `auth.endpoint.failed`, stat `higgs/auth/http_error/credit_price/500`; the run stays `success` |

| `--auth` | Effect on pricing |
|---|---|
| `auto` (default) | Use the saved login when present; `--sections all` then includes `auth` |
| `required` | Same, but if there is no login the `auth` requests are skipped with a warning (`higgs/auth/skipped/…`) |
| `off` | Never send a token; `--sections all` excludes `auth` |

Without any login, `auth` endpoints return 401; the run is still `success` because they are optional, and the
manifest records `responses.credit_packages.401`.

`normalize` never looks at this machine's login: it re-parses `auth` only when the source run contains login
responses in `raw/` (or when you pass `--sections …,auth`).

#### `--logged-in-prices` (opt-in): the rows only logged-in users see

A session changes two **public** price lists (audit 2026-11-26, `docs/LOGIN_COVERAGE.md`): `/subscriptions/v2/plans`
returns one more plan (`lite` **annual**: 100 credits/month, $12/year, list $84, 85 % off forever) and
`/job-sets/costs` one more model (`magi_2`, 1080p, 2.5 credits/s) with a different `version` hash. The flag fetches
both lists a second time **with** the session (endpoints `plans_logged_in` (one per plan set) and
`job_costs_logged_in`, raw files `raw/plans_logged_in__plan_set_key-….json`, `raw/job_costs_logged_in.json`) and merges:

- every anonymous row stays exactly as it is (same content, same order, no new key);
- a row that exists **only** in the logged-in response is appended with `visibility: "logged_in"` (plans, their
  `credit_values` row, models). The field is absent on every other row. (`plan.audience` already means
  individual/business, hence the separate name);
- `meta.logged_in_prices` = `{costs_version_anonymous, costs_version_logged_in, logged_in_only_plan_ids,
  logged_in_only_model_ids, differing_rows}`. A row present in both responses with different content keeps the
  anonymous version and is listed in `differing_rows` + `meta.warnings`;
- `plan_sets[].plan_count` / `plan_types` keep describing the anonymous response; `summary.md` marks the extra rows
  "(logged in only)"; `schema/dataset.schema.json` documents `visibility` / `logged_in_prices` only in runs that have them.

Needs a usable login: without one (or with `--auth off`) the requests are not sent, one warning `auth.skipped` is
logged and the output is the normal anonymous output. Requests are sent with `auth="required"`, never anonymously.

#### `--sections account` (opt-in): the account's own pricing state

Never part of `all`; list it explicitly (`--sections all,account` or `--sections account`). Needs a login (skipped
with a warning otherwise, and with `--auth off`). One `pricing_account` record per endpoint:

| Endpoint name | Request (GET) | Kept (whitelist) |
|---|---|---|
| `account_wallet` | `/workspaces/wallet` | balances **converted to credits** (`credits_balance`, `subscription_balance`, `total_credits`, `on_demand_credits`, `bonus_credits`), `expire_days`, `credit_limit`, allocation dates, `scoped_credits[]` |
| `account_subscription` | `/workspaces/subscription` | plan name/type, status, billing cycle, seats, `credits_per_seat`, period start/end, pause/cancel flags, payment status, `plan_version` |
| `account_auto_top_up` | `/v2/auto-top-ups/settings` | `credits_per_dollar`, state, eligibility, threshold, refill amount, currency, `expire_days`, `options[]`, `refill_options[]` |
| `account_free_gens` | `/user/free-gens/v2` | `items[]` |
| `account_generation_seconds` | `/user/generation-seconds` | `items[]` |
| `account_generation_seconds_packs` | `/generation-seconds/packs` | `items[]` |
| `account_bundle_all_unlim_status` | `/subscriptions/bundle/all-unlim/status` | `is_eligible_to_purchase`, `has_all_unlims` |
| `account_bundle_seedance_unlimited` | `/subscriptions/bundle/seedance-unlimited` | `tiers[]` |

**Privacy:** only the whitelisted fields survive (`higgsfield_scraper/parsers/account.py`); list items keep scalars
only, without id / url / email / name / avatar / user / workspace / Stripe / customer / payment keys. The whitelist is
applied by `AccountPrivacyMiddleware` *before* the `http/` and `raw/` archives, and these requests bypass the dev HTTP
cache, so emails, names, user / workspace / subscription ids and Stripe ids are never written to disk.
**Units:** wallet balances arrive in cost units = credits × 100 (`888` → `8.88`); the record holds credits and names the
rule in `conversions` (`raw/` keeps the API value). Everything else is kept as returned.

Output: `account.records[]` in `dataset.json`, `json/account.json`, `csv/account.csv` (one row per field:
`endpoint, status, field, value, conversion`) and `csv/account_items.csv` (one row per list item). These files exist
only in runs with account data. `meta.counts.account_records` likewise.

```bash
python -m higgsfield_scraper scrape pricing --sections all --logged-in-prices --label with-logged-in-prices
python -m higgsfield_scraper scrape pricing --sections all,account --logged-in-prices --label logged-in-prices-check
python -m higgsfield_scraper scrape pricing --sections account --label my-balance          # account only
python -m higgsfield_scraper normalize --run runs/<id>      # re-parses plans_logged_in / job_costs_logged_in / account_*
```

`normalize` turns `--logged-in-prices` on by itself when the source run has `plans_logged_in*` / `job_costs_logged_in*`
raw files, and always re-parses `account_*` raw files that are present.

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

**`show plans`** (US). Example output from 2026-11-25; prices change (e.g. Ultra annual moved on 2026-11-26).
Current prices: [`docs/PRICING.md`](docs/PRICING.md) snapshot, or run the command yourself:

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

**`scrapers`**: list every scraper with its description and example commands (no network).

**`login`** / **`login --code N`**: sign in with `HF_EMAIL`/`HF_PASSWORD` from `.env`.

```bash
python -m higgsfield_scraper login                 # step 1: Clerk emails a 6-digit code to the account
python -m higgsfield_scraper login --code 123456   # step 2: session cached in runs/.auth/clerk_client.json (gitignored)
```

After that, every run mints ~60 s session tokens automatically for as long as the Clerk session lives (up to ~400
days). Google/Apple accounts have no password: set `HF_CLERK_CLIENT` (the browser's `__client` cookie) instead. The
interactive menu has the same flow under *Login / session*.

**`auth-check [--json]`**: checks which credential source is configured and whether a token can be minted. Never
prints secrets. `--json` gives a machine-readable result (`ok`, `source`, …). Exit 0 if OK, 1 otherwise.

**`runs [--limit N] [--json]`**: recent runs from `runs/index.jsonl` (status, seconds, counts). `--json` prints the
raw records.

**`runs clean --keep-last N --keep-days D [--yes] [--json]`**: delete old run folders. Without `--yes` it is a
**dry run** that only lists what would be deleted. A run is kept if it is among the newest N **or** younger than D
days. Never deleted: runs still running, the latest successful run, and any run folder containing a `KEEP` file.

```bash
python -m higgsfield_scraper runs clean --keep-last 20 --keep-days 14          # preview
python -m higgsfield_scraper runs clean --keep-last 20 --keep-days 14 --yes    # delete
```

**`show-config [--json]`**: the resolved configuration (flags, environment, `.env`, defaults) and where each value
came from. Secrets are shown as `set`/`unset`, never their value.

**`diff [--old RUN] [--new RUN] [--json] [--out FILE.md|.json] [--only plans,models,benefits,offers] [--min-change PCT]`**:
compare two pricing runs' `output/dataset.json`. No network. `RUN` is a run folder or a run id under `--runs-dir`.

- Defaults: `--new` = the latest successful pricing run (from `runs/index.jsonl` + manifests; other scrapers are
  ignored), `--old` = the previous successful pricing run with a **compatible selection**: same plan sets, billing
  periods, filters and `--include-hidden-plans`, and at least the new run's plans/benefits/models sections.
- **plans**: added/removed plans; `before_offer` / `after_offer` / `renewal` price changes (`per_month` and `total`,
  per billing period) with absolute and % change; `credits_per_month` changes (a plan whose credits changed is
  paired with its old self, not reported as removed + added); seats/name changes.
- **offers**: plan-set `special_offer`, per-plan `discount` (`percent_off`, `duration`, `applies_to`), raw `offer`
  objects and benefit-card campaigns (`ends_at`).
- **models**: added/removed models; credit changes per price point, keyed by `model_id` + component + dimensions +
  unit (`credits` and `original_credits`); price points and option values added/removed.
- **benefits**: unlimited models and free gens per benefit card (plan type / billing / tab), added/removed/changed.
- **meta**: `costs_version` and `country_code`. A country difference is a warning: prices come from the IP's country
  and are not comparable. Runs with different plan sets are compared on the plan sets they share (with a warning).
- `--min-change PCT` hides price/credit changes smaller than PCT % (changes from 0 are always shown).
- `--json` prints the structured diff (`changed: true|false`, `summary`, `warnings`, one block per category) to
  stdout; `--out` also writes it as Markdown (`.md`) or indent-4 JSON (`.json`).
- Exit `0` whether or not anything changed (read `changed`), `1` on errors (no runs, unreadable dataset),
  `2` on usage errors (unknown `--only` value, `--out` not `.md`/`.json`).

```bash
python -m higgsfield_scraper diff                                         # latest vs previous compatible run
python -m higgsfield_scraper diff --old 20261125-111348_everything --new 20261125-141237_verify-logging-live
python -m higgsfield_scraper diff --only plans,offers --min-change 5 --out reports/prices.md
python -m higgsfield_scraper diff --json | jq '.changed, .summary'
```

```
pricing diff 20261201-090000_old -> 20261202-090000_new
┌──────────┬───────────────────────┬──────────────────────────────────────────┬──────────┬────────────────┬────────────────┐
│ category │ change                │ item                                     │ old      │ new            │ Δ              │
├──────────┼───────────────────────┼──────────────────────────────────────────┼──────────┼────────────────┼────────────────┤
│ meta     │ costs_version         │                                          │ 362779fa │ a1b2c3fa       │                │
│ plans    │ after_offer.per_month │ ps_a3/plus/monthly/1200cr                │ $40.00   │ $45.00         │ 5.00 (+12.50%) │
│ plans    │ after_offer.total     │ ps_a3/plus/monthly/1200cr                │ $40.00   │ $45.00         │ 5.00 (+12.50%) │
│ offers   │ percent_off           │ ps_a3/plus/monthly/1200cr                │ 33.0     │ 24.0           │                │
│ models   │ credits               │ seedance_2_5 resolution=480p video_in... │ 3.0      │ 3.6            │ 0.6 (+20.00%)  │
│ benefits │ unlimited             │ plus/monthly/individual                  │          │ +nano_banana_2 │                │
└──────────┴───────────────────────┴──────────────────────────────────────────┴──────────┴────────────────┴────────────────┘
summary: plans.price_changes=2, models.credit_changes=1, benefits.unlimited_changes=1, offers.discount_changes=1
```

When the plan sets differ (e.g. a `--plan-sets all` run vs a `us` run):

```
pricing diff 20261125-111348_everything -> 20261125-141237_verify-logging-live
warning: selection differs: include_hidden_plans True -> False
warning: plan sets differ ([default, default_basic, default_q, … (25 keys)] vs [ps_a3]); plans and offers compared only for [ps_a3]
no changes
```

**`crosscheck [--run RUN] [--json] [--save]`**: fetch the official `https://higgsfield.ai/pricing.md` (one plain GET
with the project's User-Agent; not a Scrapy crawl) and compare it with the run's **`ps_a3`** (US) dataset. Default
run: the latest successful pricing run that includes `ps_a3`.

- **plans**: matched on plan type + billing + credits per month. Only values the text states are compared:
  `$19/mo` (all stages 19), `$40 first month, then $59/mo` (after offer 40, renewal and list 59),
  `$55/mo (list price $79/mo)`, `$30/mo, billed $360 yearly` (annual `per_month` and `total`). Business plans are per
  seat, as in the dataset. Enterprise ("custom pricing") and the Free row are listed as pricing.md-only.
- **models**: pricing.md currently lists **no per-model credit costs**, so this section is empty (`note` says so).
  If a table with a "Model" and a "Credits" column appears, rows are matched conservatively (exact display name,
  credits must equal one of the model's price-point values).
- **benefits**: the per-plan "Unlimited & free gens" / "Free generations" / "Unlimited models" bullets, matched by
  exact row label against the dataset's benefit cards: unlimited vs none, free-gen counts, N-day windows, max
  resolution.
- Reports matches, mismatches, items only in pricing.md and items only in the dataset. Warns when the run was fetched
  from a non-US IP (ps_a3 prices are still comparable).
- `--save` writes `<run>/crosscheck/pricing_<UTC ts>.md` (the fetched file) and `report_<UTC ts>.json` (indent 4).
  `<run>/output/` is never touched.
- Exit `0` when the comparison ran (mismatches or not: read `ok` / `mismatch_count`), `1` on errors (network, no run,
  no `ps_a3` plan set in the run).

```bash
python -m higgsfield_scraper crosscheck                       # latest ps_a3 run
python -m higgsfield_scraper crosscheck --run 20261125-141237_verify-logging-live --save
python -m higgsfield_scraper crosscheck --json | jq '.ok, .summary'
```

```
pricing.md crosscheck (2026-11-25) vs 20261125-142650_verify-menu-normalize3 / ps_a3
offer: Black Friday sale: up to 70% off, ends 2026-11-26 00:00 UTC.
warning: run fetched from country EG; ps_a3 is the US price list, so plan prices are comparable, but other
country-dependent fields may not be
┌──────────┬───────┬──────────┬─────────────────┬──────────────┐
│ section  │ match │ mismatch │ only pricing.md │ only dataset │
├──────────┼───────┼──────────┼─────────────────┼──────────────┤
│ plans    │ 57    │ 0        │ 3               │ 0            │
│ models   │ 0     │ 0        │ 0               │ 0            │
│ benefits │ 76    │ 0        │ 0               │ 0            │
└──────────┴───────┴──────────┴─────────────────┴──────────────┘
models: pricing.md lists no per-model credit costs
                                           differences
┌─────────┬─────────────────┬──────────────────┬───────┬───────────────────────────────┬─────────┐
│ section │ kind            │ item             │ field │ pricing.md                    │ dataset │
├─────────┼─────────────────┼──────────────────┼───────┼───────────────────────────────┼─────────┤
│ plans   │ only pricing.md │ free/monthly/0cr │       │ Free                          │         │
│ plans   │ only pricing.md │ free/annual/0cr  │       │ Free                          │         │
│ plans   │ only pricing.md │ enterprise       │       │ custom pricing (not compared) │         │
└─────────┴─────────────────┴──────────────────┴───────┴───────────────────────────────┴─────────┘
all compared values match
```

**`menu`** / **`-i`** / **`--interactive`**: interactive mode (see [Interactive mode](#interactive-mode)).

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
auth       (needs login)
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
  manifest.json      status (running/success/partial/failure/cancelled), exit_code, scraper, args (secrets redacted),
                     common options, selection, limits_hit, auth status, versions (python/scrapy/pydantic/git),
                     started/finished/duration, counts, responses {endpoint: {status: n}}, scrapy_stats, files[],
                     outputs[] (size + sha256), progress (refreshed on every heartbeat). Written atomically.
  _SUCCESS           empty marker, only when status = success
  logs/events.jsonl  structured JSON, one event per line: timestamp, level, logger, event, message, run.id,
                     scraper.name, + event fields. Events: app.started, config.loaded, run.started, page.fetched,
                     raw.saved, worker.heartbeat (items, rate, ETA, memory, queue), output.written, run.finished …
  logs/access.jsonl  one line per HTTP request: method, url, endpoint, status, duration_ms, size, retry attempt, outcome
  logs/run.log       everything, human-readable
  logs/errors.log    WARNING+ with full tracebacks
  logs/app.log, logs/scrapy.log   only with --split-logs
  media/             downloaded files + index.jsonl (only with --download-media; not pricing)
  (all logs, the manifest and http/ pass through one redaction layer: JWTs, cookies, Bearer tokens, passwords)
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
| 0 | `success` | Every required endpoint returned 200, and every item validated |
| 1 | `failure` | No dataset was produced (crash or assembly error). `raw/` is kept |
| 2 | — | Usage error: bad arguments (`error: unknown plan_set_key(s): ['bogus']; …`), or `menu` without a terminal |
| 3 | `partial` | Output was written, but there was a non-200 response, a request error, or a dropped (invalid) item. Check `logs/errors.log` and `manifest.json` |
| 4 | `partial` + `"blocked": true` | Stopped on a bot-protection (captcha) response (`--no-stop-on-block` to continue) |
| 130 | `cancelled` | Ctrl-C; the run is finalized with what was collected |

Older manifests that say `failed` are read as `failure`. Before the logging upgrade, `partial` exited with 2.

| Env var | Equivalent |
|---|---|
| `HF_EMAIL`, `HF_PASSWORD` | credentials for `login` (option A) |
| `HF_CLERK_CLIENT` | browser `__client` cookie (option B), auto-refreshing |
| `HF_TOKEN` | `--token` (one-off JWT, option C) |
| `HF_LOCALE` | `--locale` |
| `HF_RUNS_DIR` | `--runs-dir` |
| `HF_LOG_LEVEL` | `--log-level` |
| `HF_LOG_FORMAT` | `--log-format` (`console` \| `json`) |
| `NO_COLOR` | `--no-color` |
| `HF_PREFS` | interactive-mode prefs file (default `%APPDATA%\higgsfield_scraper\prefs.json`) |
| `HF_NO_MENU=1` / `CI` | never open the menu on a bare `python -m higgsfield_scraper` |
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
