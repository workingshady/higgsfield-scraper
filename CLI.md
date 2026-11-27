# CLI reference: `python -m higgsfield_scraper`

This file covers every command, option, choice, default and combination, with real example output (captured
2026-11-25) and when to use each one. With `pip install -e .`, `higgsfield-scraper …` can be used in place of
`python -m higgsfield_scraper …`.

```
python -m higgsfield_scraper <command> [options]

commands:
  scrape       fetch live data into a new run folder (`scrape <scraper> -h`)   (default if no command is given)
  normalize    re-parse a run's raw/ responses offline into a new run
  show         print tables from a pricing run's dataset
  scrapers     list available scrapers (pricing, community, catalog, projects, blog, site, account, showcase, studios, models)
  auth-check   check login/session configuration (never prints secrets)
  login        log in with HF_EMAIL/HF_PASSWORD from .env (step 1), then --code (step 2)
  plan-sets    list plan_set_keys, presets and the frontend tier mapping
  sections     list pricing sections and the endpoints they call
  runs         list recent runs (`runs clean -h`: delete old run folders)
  show-config  print the resolved configuration (flags/env/.env), secrets redacted
  schema       export JSON Schemas of every scraper
  diff         compare two pricing runs (plans, offers, model credits, benefits)
  crosscheck   compare a run's ps_a3 prices with the official higgsfield.ai/pricing.md
  export       turn finished run folder(s) into a browsable / dataset-ready folder (docs/EXPORT.md)
  menu         interactive menu (also -i / --interactive; default with no args on a terminal)
```

Outside the CLI, `python scripts/merge_generations.py` counts and dedupes the generations of several runs
([§6c](#6c-count-and-dedupe-generations-scriptsmerge_generationspy)).

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
   [1b. Every scraper: complete option reference](#1b-every-scraper-complete-option-reference) (shared, limits, pricing, community, catalog, projects, blog, site, account, showcase, studios, models)
   [1c. Examples: opt-in kinds, flags and the `account` scraper](#1c-examples-opt-in-kinds-flags-and-the-account-scraper)
   [1d. Projects: nested project data, contests by slug, user projects](#1d-projects-nested-project-data-contests-by-slug-user-projects)
   [1e. Community pages: shots, posts, Feed, creators, talents, comment threads](#1e-community-pages-shots-posts-feed-creators-talents-comment-threads)
   [1f. Site: community rooms (`room-list`, `room-content`)](#1f-site-community-rooms-room-list-room-content)
   [1g. `scrape showcase`: every source and option](#1g-scrape-showcase-every-source-and-option)
   [1h. Opt-in extras of the content-map round](#1h-opt-in-extras-of-the-content-map-round-2026-11-26) (feeds, main feed, trending projects, user works, outfits, academy API, `creator_uid_key`)
   [1i. `scrape studios`](#1i-scrape-studios-marketplaces-studio-presets-and-galleries)
   [1j. `scrape models`](#1j-scrape-models-the-model-registry-from-the-public-js-bundle)
2. [Option details: every choice and when to use it](#2-option-details), incl.
   [Logged-in pricing](#logged-in-pricing-auth-section) (`auth`, [`--logged-in-prices`](#--logged-in-prices-opt-in-the-rows-only-logged-in-users-see),
   [`--sections account`](#--sections-account-opt-in-the-accounts-own-pricing-state))
3. [Recipes: common combinations](#3-recipes), incl. [scrape everything](#scrape-everything-all-10-scrapers)
4. [`normalize`](#4-normalize)
5. [`show`](#5-show)
6. [`scrapers`, `login`, `auth-check`, `runs`, `runs clean`, `show-config`, `diff`, `crosscheck`, `plan-sets`, `sections`, `schema`](#6-info-commands)
   [6b. `export`: run folders → browsable / dataset folders](#6b-export-run-folders--browsable--dataset-folders)
   [6c. Count and dedupe generations: `scripts/merge_generations.py`](#6c-count-and-dedupe-generations-scriptsmerge_generationspy)
   [6d. Top trending ideas and templates: `scripts/trending_ideas.py`](#6d-top-trending-ideas-and-templates-scriptstrending_ideaspy)
7. [Output: what a run produces](#7-output), incl. [the other scrapers' files](#output-of-the-other-scrapers)
8. [Exit codes, environment variables, `.env`](#8-exit-codes-and-environment)
9. [Plain Scrapy (`scrapy crawl higgsfield -a …`)](#9-plain-scrapy)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. `scrape` (pricing, the default scraper)

```
python -m higgsfield_scraper scrape [--sections S] [--plan-sets P] [--billing B] [--marketing-versions V] [--locale L]
                             [--plan-types T] [--models M] [--categories C]
                             [--usd-reference R] [--include-hidden-plans] [--include-raw-cost] [--logged-in-prices]
                             [--label X] [--runs-dir D] [--log-level LVL] [--file-log-level LVL] [--scrapy-log-level LVL]
                             [--token JWT] [--cache] [--dry-run]
```

| Group | Option | Default | Accepts |
|---|---|---|---|
| What to fetch | `--sections` | `plans,compare,benefits,models,marketing` | comma list of `plans compare benefits models marketing auth account`, or `all` (`all` never includes `account`) |
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
| | `--logged-in-prices` | off | flag: also add the plan / model rows only logged-in users see, tagged `visibility="logged_in"` (needs a login; see [below](#--logged-in-prices-opt-in-the-rows-only-logged-in-users-see)) |
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

`scrape` with no scraper name means `scrape pricing` (backward compatible). There are **10 scrapers**
(`python -m higgsfield_scraper scrapers`). Every scraper takes the shared options; community, catalog, projects, blog,
site, account, showcase, studios and models also take the limit/media options (`models` ignores them). Per-scraper
guides: `docs/scrapers/` ([`community`](docs/scrapers/community.md), [`catalog`](docs/scrapers/catalog.md),
[`projects`](docs/scrapers/projects.md), [`blog`](docs/scrapers/blog.md), [`site`](docs/scrapers/site.md),
[`account`](docs/scrapers/account.md), [`showcase`](docs/scrapers/showcase.md), [`studios`](docs/scrapers/studios.md),
[`models`](docs/scrapers/models.md)). The tables below are generated (`python scripts/gen_cli_tables.py`); examples
for the opt-in flags are in [§1c](#1c-examples-opt-in-kinds-flags-and-the-account-scraper) to
[§1j](#1j-scrape-models-the-model-registry-from-the-public-js-bundle).

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

### Limits and media (community, catalog, projects, blog, site, account, showcase, studios, models)

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
| `--feeds` | `trending` | FEEDS | comma list of feeds: trending (main feed, ~78.6k), approved (curated, ~6.7k, mostly video), top (single page, &lt;=100), model-x (featured model showcase), 'all', or 'none' (only --publication-ids) (default: trending). Opt-in Community pages, never part of 'all': shots (/community/generations, fnf-community generations feed), posts (Community posts, ~24k), feed (the /community/feed mix of shots, projects, blogs and posts), creators (/community/creators, ~650, aggregate stats; names only with --with-profiles), talents (Talents hub, ~80), music-cards (Music Cards templates: lyrics, recipients, preview videos, ~111 + option lists), job-showcase (Seedance 2 community 'movies': 54 jobs with prompt, inputs, all result variants), collections (motion collection Catch the Pulse), explore-cards (explore/home cards, ~192), feed-categories (Feed hashtag contest categories with post counts and previews, + /feed/ongoing). --max-items caps each opt-in feed separately |
| `--type` | `all` | `all` `image` `video` `speak` `upscale` | media type filter (API `type`). image\|video are also enforced client-side because the approved feed ignores it; speak\|upscale are server-side only (default: all) |
| `--models` | — | JOB_SET_TYPES | job_set_type filter, comma list and/or repeatable, e.g. --models seedance_2_5,nano_banana_2 (API `model`, trending/approved; enforced client-side for top/model-x) |
| `--preset-ids` | — | IDS | preset/motion id filter (API `preset_id`, repeatable). Passed through; server effect unverified |
| `--resolution` | — | RESOLUTION | API `resolution` filter (passed through; the trending feed ignores it, approved returned 0 items for 720p in tests — use with care) |
| `--publication-ids` | — | IDS | also fetch these publications by id (GET /publications/{id}); their feed is 'detail' |
| `--with-profiles` | off | flag | PERSONAL DATA: include creators' username, avatar, social handles and badges (creators table). Default: only the pseudonymous user_id |
| `--with-raw-params` | off | flag | keep each generation's untouched `params` dict (raw_params) next to the normalized fields |
| `--detail` | off | flag | fetch GET /publications/{id} for every listed item and use that (1 extra request per item) |
| `--with-comments` | off | flag | fetch comments (+ replies) from the Community posts service (fnf-community): reads the posts feed (limit = --max-items, max 50) and the threads of posts that have comments. With the opt-in feeds shots/feed/posts it instead reads the comment threads of those items (fnf-community /entities/{type}/{id}/comments for shots, projects and blogs). Public; commenter identities only with --with-profiles |
| `--estimate-cost` | `off` | `off` `images` `videos` `all` | attach an estimated credit cost per generation from /job-sets/costs: off (default) \| images \| videos \| all. An estimate, not what the creator actually paid |
| `--usd-reference` | `plus:annual` | USD_REFERENCE | plan_type:billing_period whose after-offer $/credit converts credits to USD (default: plus:annual) |
| `--usd-plan-set` | `ps_a3` | USD_PLAN_SET | plan_set_key used for the USD reference plan (default: ps_a3) |
| `--estimate-version` | `1` | `1` `2` | cost formulas used by --estimate-cost: 1 (default, unchanged) or 2 (matches the web app's JS formulas, docs/COST_FORMULAS.md §8; v2 estimates carry formula_version: 2) |

```bash
python -m higgsfield_scraper scrape community --max-items 300
python -m higgsfield_scraper scrape community --feeds approved --type video --max-items 100
python -m higgsfield_scraper scrape community --feeds trending --models nano_banana_2,seedream_v4_5 --max-items 500
python -m higgsfield_scraper scrape community --max-items 200 --estimate-cost all
python -m higgsfield_scraper scrape community --max-items 50 --with-profiles --download-media thumbs
python -m higgsfield_scraper scrape community --feeds shots,posts,feed --max-items 100 --with-comments
python -m higgsfield_scraper scrape community --feeds creators,talents
python -m higgsfield_scraper scrape community --feeds feed-categories
```

### `scrape catalog`

Preset & asset catalogs: motions (+samples/details), avatars, voices, sounds, styles, soul samples, viral-hub presets; opt-in (`--kinds login`) soul styles, per-model motions, mixed media, katana, ...

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--kinds` | — | KINDS | comma list of catalog kinds (short names like motion,voice or catalog_motion), or 'public' (default), 'login', 'all'. Opt-in extras (only by name or 'all'): chain_preset, notice, restyle_preset. Name-only (not even in 'all'): outfit_character. Available: motion, motion_sample, avatar, avatar_preset, voice, reference_voice, sound, style, soul_sample, viral_type, viral_preset, soul_style, mixed_media_preset, model_motion, katana_category, katana_preset, color_preset, youtube_faceless_preset, camera_setting, marketing_category, marketing_preset, chain_preset, notice, restyle_preset, outfit_character |
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
| `--what` | `all` | WHAT | comma list of ['publications', 'recommended', 'contests', 'entries', 'series'] or 'all' (default). 'series' needs a login session unless --public-series. Opt-in (not in 'all'): ['trending', 'contest-participation'] |
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
| `--with-project-assets` | off | flag | folders (+ counts) and every asset of each project: prompt (only when the author enabled show_prompts), model/job_set_type, params, media URLs/variants, folder, created_at |
| `--with-project-brief` | off | flag | the project brief as Markdown (field + output/briefs/&lt;slug&gt;.md) |
| `--with-project-stats` | off | flag | generations, credits spent, size and the model stack with the page's percentages |
| `--with-project-comments` | off | flag | comments and replies of each project |
| `--with-project-related` | off | flag | the page's related-projects list |
| `--users` | — | USERS | comma list of handles: list their public projects (adds 'user-projects' to --what). Handles are inputs only; outputs stay pseudonymous unless --with-profiles |
| `--contest` | — | CONTESTS | comma list of contest slugs (e.g. talent-contest,wcc-the-place-you-know): fetch these contests by slug instead of listing all contests |
| `--contest-tabs` | — | CONTEST_TABS | entry tabs of a --contest that has an entries listing (talent-contest, festival): ['latest', 'trending', 'most_watched', 'all_entries', 'submissions'] or 'all' (default: --entry-tab). Needs --with-submissions |
| `--trending-sort` | — | `default` `most_viewed` `most_liked` `newest` `oldest` | --what trending: ranking order (default: the site's default ranking; not sent) |
| `--trending-filter` | — | `all` `non_contest` `contest` `talents_hub` | --what trending: filter (default: not sent = every project) |
| `--trending-with-contest` | off | flag | --what trending: with_contest=true (ignored when --trending-filter is given, like the site) |
| `--with-user-works` | off | flag | published works (generations with prompt/params/results, projects, folders, contest submissions) + stats of users ALREADY found in this run (owners of --users projects, contest entrants and submitters); never enumerates users. Pseudonymous (creator_uid_key) unless --with-profiles |
| `--with-profiles` | off | flag | opt-in: include authors'/contestants' usernames, names, avatars, headlines, locations, judge links and profile-based page URLs (default: pseudonymous author keys only) |

```bash
python -m higgsfield_scraper scrape projects --max-items 200
python -m higgsfield_scraper scrape projects --what contests --with-details --with-submissions
python -m higgsfield_scraper scrape projects --what publications --categories spotlight --with-details
python -m higgsfield_scraper scrape projects --what recommended --scope ai_film_festival --max-pages 2
python -m higgsfield_scraper scrape projects --what contests --contest-status closed --contest-types weekly
python -m higgsfield_scraper scrape projects --what publications --max-items 50 --download-media thumbs
python -m higgsfield_scraper scrape projects --what trending,contest-participation --max-pages 2
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
| `--what` | `apps,academy,mcp,originals,mixed-media,landings,promos` | WHAT | comma list of ['apps', 'academy', 'mcp', 'originals', 'mixed-media', 'landings', 'rooms', 'promos', 'room-list', 'room-content', 'academy-api'] or 'all' (default: apps,academy,mcp,originals,mixed-media,landings,promos; 'rooms' = community room pages, title/description only, opt-in; 'room-list' = every room from the public rooms API with member/works counts and room-stats (posts, discussions); 'room-content' = room-list + each room's works (shots, projects, blog posts) and discussion posts. All three are opt-in, not part of 'all'; --max-items caps rooms, room items and discussions separately; 'academy-api' = the academy JSON API (fnf-academy: categories, courses with free_generations / test_count, lessons with MDX source, xp, subtitles), opt-in, not in 'all'; --no-content = categories + course list only) |
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
python -m higgsfield_scraper scrape site --what room-content --max-items 50 --label rooms
```

### `scrape account`

OPT-IN, login required: your own balances/plan/subscription snapshot, your jobs with the credits actually charged (--with-jobs) and estimate-vs-actual checks (--compare-estimate)

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--with-jobs` | off | flag | also read your own jobs from /jobs/accessible (paginated; --max-items / --max-pages apply): job_set_type, status, created_at, pricing-relevant params and the actual credits charged |
| `--compare-estimate` | off | flag | needs --with-jobs: run the CostEstimator on each job's params and compare it with the credits actually charged (fetches the public /job-sets/costs etc.) |
| `--job-types` | — | JOB_TYPES | needs --with-jobs: comma list of job_set_type values to request (server-side filter) |
| `--estimate-version` | `1` | `1` `2` | needs --compare-estimate: estimator formulas, 1 (default, unchanged) or 2 (the web app's JS formulas, docs/COST_FORMULAS.md §8) |
| `--with-prompts` | off | flag | opt-in: STORE YOUR OWN PROMPT TEXT (prompt, negative_prompt, text …) in the dataset and in the raw/ and http/ archives. Default: prompts are replaced by their length only |

```bash
python -m higgsfield_scraper scrape account
python -m higgsfield_scraper scrape account --with-jobs --max-items 100
python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20
```

### `scrape showcase`

Showcase/example content: Canvas templates, Editing Room examples, Property Studio presets, video-explore feeds (+likes), effect sample generations, public API models, Cinema Studio controls, faceless/Intone/Seedance/motion-control showcases; opt-in Shorts Studio reels presets/comments, the home main feed (`--what main_feed`, by name only) and login `season`

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--what` | — | WHAT | comma list of sources, 'public' (default: every public source except the opt-in ones) or 'all' (+ opt-in reels_comments, reels_presets and login-only `season`; by name only, never in 'all': main_feed). Available: canvas_templates, editing_room_examples, property_studio_examples, explore_categories, effect_examples, api_models, cinema_controls, faceless_showcases, intone_examples, seedance_presets, motion_control_presets, season, reels_presets, reels_comments, main_feed |
| `--lang` | `en` | LANG | language for CMS lists and Property Studio titles (en, es, de, ja, ko; zh titles only) |
| `--explore-sources` | `higgsfield,community` | EXPLORE_SOURCES | video explore feeds: higgsfield (curated, ~35), community (~49k) (default: both) |
| `--explore-sort` | `new` | `new` `trending` `both` | community explore sort: new (page-numbered, has `total`), trending (opaque cursor), both |
| `--explore-pages` | `3` | EXPLORE_PAGES | pages (20 items) per explore feed (default 3; 0 = until the end; --max-pages also applies) |
| `--explore-categories` | — | EXPLORE_CATEGORIES | also crawl the community feed per category: comma list or 'all' (from /categories) |
| `--effects` | — | EFFECTS | only these /effects/examples slugs (comma list); default: every slug in the sitemap |
| `--reels-sources` | `higgsfield,community` | REELS_SOURCES | Shorts Studio preset lists for reels_presets/reels_comments: higgsfield (curated, ~40), community (user-published, ~75) (default: both) |
| `--main-feed-pages` | `3` | MAIN_FEED_PAGES | main_feed (home Explore feed, opt-in by name): pages of 20 items (default 3; 0 = until the cursor ends; --max-pages / --max-items also apply) |
| `--with-profiles` | off | flag | opt-in: keep creator user_id/username/avatar on explore / main-feed variants, effect samples and reels presets/comments, and the reference reel's author handle (default: only a pseudonymous creator_key hash) |

```bash
python -m higgsfield_scraper scrape showcase
python -m higgsfield_scraper scrape showcase --what api_models,canvas_templates
python -m higgsfield_scraper scrape showcase --what explore --explore-sort both --explore-pages 10
python -m higgsfield_scraper scrape showcase --what effect_examples --effects acid,vanish
python -m higgsfield_scraper scrape showcase --what property_studio_examples --lang de --download-media thumbs
python -m higgsfield_scraper scrape showcase --what reels_presets,reels_comments --max-items 20
python -m higgsfield_scraper scrape showcase --what all --max-items 30   # + opt-in reels, login season
python -m higgsfield_scraper scrape showcase --what main_feed --main-feed-pages 2   # home feed, by name
```

### `scrape studios`

Studio & marketplace content: community apps (+views/likes/dislikes/remixes/credits), games (+plays), skills & AI employees (+usage), Playable Ads presets, AI Influencer options, published outputs of every studio (+likes/views, optional comments)

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--what` | — | WHAT | comma list of sources, 'public' or 'all' (same: every source is public; default: all). Available: apps, games, skills, employees, playable_presets, influencer_options, galleries |
| `--lang` | `en` | LANG | language of the CMS lists (playable presets, AI influencer options): en es de ja ko |
| `--apps-sort` | `trending` | `trending` `most_viewed` `popular` `newest` | community apps order (JS default `trending`; unknown values fall back to it) |
| `--studios` | — | STUDIOS | galleries: only these studios (comma list; default all): marketing_studio, ads_studio, cinema_studio, ai_influencer, canvas, shorts_drama, ai_host, property_studio, editing_room |
| `--gallery-feeds` | `approved,trending` | GALLERY_FEEDS | galleries: approved (curated) and/or trending (default: both) |
| `--gallery-pages` | `3` | GALLERY_PAGES | galleries: pages (50 items) per studio and feed (default 3; 0 = until the end; --max-pages also applies) |
| `--with-comments` | off | flag | galleries: also fetch the public comments of every gallery item (1+ request per item) |
| `--with-profiles` | off | flag | opt-in: keep author user_id/name/avatar (apps, games, skills, employees, gallery items, comments) (default: only a pseudonymous author_key hash) |

```bash
python -m higgsfield_scraper scrape studios
python -m higgsfield_scraper scrape studios --what apps --apps-sort most_viewed --max-items 500
python -m higgsfield_scraper scrape studios --what games,skills,employees
python -m higgsfield_scraper scrape studios --what galleries --studios marketing_studio,cinema_studio --gallery-pages 0 --with-comments
python -m higgsfield_scraper scrape studios --what playable_presets --download-media thumbs
python -m higgsfield_scraper scrape studios --what playable_presets,influencer_options --lang de
```

### `scrape models`

Model registry from the public JS bundle: ~130 job types with params schema (enums, ranges, defaults), media roles/limits, routes, plan tiers, flag gating, featured order, picker menus; + /job-sets/costs and the Shots available_models facet; build id recorded

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--pages` | `/ai/video,/ai/image,/lipsync-studio,/mixed-media` | PAGES | comma list of tool pages whose JS bundle is crawled (default: /ai/video,/ai/image,/lipsync-studio,/mixed-media) |
| `--max-chunks` | `800` | MAX_CHUNKS | max JS chunks fetched (default 800; 0 = no cap). Preloaded chunks of the pages come first, then imports of chunks holding model data, then everything else; ~540 reach the whole registry |
| `--no-costs` | off | flag | skip /job-sets/costs (in_costs, costs version) |
| `--no-shots` | off | flag | skip the Shots feed facet (available_models -&gt; shot_facets, in_shots) |

```bash
python -m higgsfield_scraper scrape models
python -m higgsfield_scraper scrape models --max-chunks 300 --no-shots
python -m higgsfield_scraper scrape models --pages /ai/video,/ai/image --max-chunks 0
```
<!-- END scraper-options -->

## 1c. Examples: opt-in kinds, flags and the `account` scraper

Everything here is **opt-in** (added 2026-11-26): without these flags every scraper's output is unchanged.

**Pricing with a login** (details: [Logged-in pricing](#logged-in-pricing-auth-section)):

```bash
python -m higgsfield_scraper scrape pricing --sections all --logged-in-prices        # + rows only logged-in users see (lite annual, magi_2)
python -m higgsfield_scraper scrape pricing --sections all,account --logged-in-prices # + the account's own wallet, subscription, top-up settings
python -m higgsfield_scraper scrape pricing --sections account --label my-balance     # account records only
```

With a login, `--sections all --logged-in-prices --dry-run` adds two requests after the `auth` ones:

```
GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?with_localization=true&plan_set_key=ps_a3   [auth]
GET https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs   [auth]
```

**Catalog: chain presets (credit prices), notices, restyle presets** (public, no login; never in the default run,
`--kinds public` or the `login` group; included by `--kinds all`). Guide: [`docs/scrapers/catalog.md`](docs/scrapers/catalog.md).

```bash
python -m higgsfield_scraper scrape catalog --kinds chain_preset,notice,restyle_preset
python -m higgsfield_scraper scrape catalog --kinds chain_preset --include-hidden      # + presets the app hides (is_hidden=true)
python -m higgsfield_scraper scrape catalog --kinds chain_preset --with-profiles       # keep the `collaborator` credit
python -m higgsfield_scraper scrape catalog --kinds notice --lang de                   # notices are translated
```

```
$ python -m higgsfield_scraper scrape catalog --kinds chain_preset,notice,restyle_preset --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-cms-api/job-set-chain-presets?lang=en
GET https://cms.higgsfield.ai/notices?lang=en
GET https://fnf-api-gw.higgsfield.ai/fnf-cms-api/restyle-presets?size=100&lang=en
```

**Projects: original series from the public `fnf-series` service** (no login). Guide:
[`docs/scrapers/projects.md`](docs/scrapers/projects.md).

```bash
python -m higgsfield_scraper scrape projects --what series --public-series                  # 35 series + episodes
python -m higgsfield_scraper scrape projects --what series --public-series --with-details   # + /series/{slug}
```

```
$ python -m higgsfield_scraper scrape projects --what series --public-series --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-series/series?limit=100
```

**`scrape account`** (login required; your own data; never part of a default run). Guide:
[`docs/scrapers/account.md`](docs/scrapers/account.md).

```bash
python -m higgsfield_scraper scrape account                                             # snapshot (11 endpoints)
python -m higgsfield_scraper scrape account --with-jobs --max-items 100                 # + your jobs with the credits charged
python -m higgsfield_scraper scrape account --with-jobs --job-types seedance_2_5 --max-items 50
python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20   # estimator vs real charge
python -m higgsfield_scraper scrape account --with-jobs --with-prompts --max-items 20   # opt-in: STORES your prompt text
```

- Without a session the run makes no request and ends `failure` (exit 1) with a message on how to log in.
- `/jobs/accessible` was Cloudflare-challenged for the crawl on 2026-11-26 (`403 cf-mitigated: challenge`): the
  run records it in `meta.limits_hit`, ends `partial` and does not try to get past it.
- `scrape account --dry-run` prints the "needs a login session" message and no requests even with a working login
  (the session is resolved when the crawl starts).

## 1d. Projects: nested project data, contests by slug, user projects

A project page (`https://higgsfield.ai/@<handle>/projects/<slug>`) shows more than the publication record: stats and
model stack, folders, every asset with its prompt, the brief, comments and related projects. These **opt-in** flags
of `scrape projects` collect them (added 2026-11-26). Without them the requests and every output file are unchanged.
Every nested request is a public GET; none needs a login (a session adds no public data here, so nested requests are
always sent without one, whatever `--auth` says). Guide with the field map, ER diagram and evidence:
[`docs/scrapers/projects.md`](docs/scrapers/projects.md#nested-data-model-opt-in-2026-11-26).

| Flag | Fetches (per project) | Output |
|---|---|---|
| `--with-project-assets` | root folder `GET /folders/{id}`, sub-folders recursively (`/folders/{id}/children`), every asset (`/folders/{id}/items/v2?include_subfolders=true&size=100`), plus the Watermarks folder listed apart | `folders`, `assets` (prompt only when the author enabled `show_prompts`, model / `job_set_type`, params, media URLs and variants, folder path, dates); CSV `project_folders`, `project_assets`, `project_asset_variants`, `project_asset_inputs` |
| `--with-project-brief` | `GET https://dam-editor-worker.higgsfield.ai/brief/{folder}/snapshot` (binary Yjs snapshot, decoded to Markdown) | `briefs` (field `markdown`) + `output/briefs/<slug>.md`; CSV `project_briefs` |
| `--with-project-stats` | nothing extra: parsed from the publication detail | `project_stats` (generations, credits spent, size), `stack_items` (model stack with the page's percentages); CSV `project_stats`, `project_stack` |
| `--with-project-comments` | `GET fnf-community /entities/project_publication/{id}/comments` (+ replies) | `comments`; CSV `project_comments` |
| `--with-project-related` | `GET /project-publications/recommended?scope=…&current_publication_id={id}` | `related`; CSV `project_related` |
| `--contest a,b` | `GET /contests/{slug}` instead of the contest listing; with `--with-submissions` its submissions and, for `talent-contest` / `higgsfield-global-film-festival`, its entries tabs | `contests`, `submissions`, `listing_entries` |
| `--contest-tabs` | entries tabs of a `--contest` that has an entries listing: `latest`, `trending`, `most_watched`, `all_entries`, `submissions` or `all` (default: `--entry-tab`). Needs `--with-submissions`. The per-viewer tabs `liked` / `voted` are refused | `listing_entries` |
| `--users a,b` | `GET /user/{handle}/v2/publications?publication_type=project` (adds `user-projects` to `--what`; use `--what user-projects --users a` for only that) | `publications`; handles are inputs only, outputs stay pseudonymous unless `--with-profiles` |

Each `--with-project-*` flag fetches the publication detail of every publication seen (listings, entries, user
projects, contest submissions), with or without `--with-details`. `dataset.json` then uses `ProjectsNestedDataset`
with the extra collections `folders`, `assets`, `briefs`, `project_stats`, `stack_items`, `comments`, `related` and
`nested_summary`.

How the limits apply:

- `--max-items` counts publications and contests as before; nested rows (folders, assets, comments …) are not counted.
- `--max-submissions` caps each contest's submissions **and** each `--contest` entries tab.
- `--max-pages` also caps the item pages of each folder and the comment pages of each thread.
- `--download-media` saves assets under `<run>/media/projects_asset/`: `thumbs` = thumbnail / preview image,
  `full` = the original file (png, mp4, wav, mov), `all` = both + the `min` preview. A project's Watermarks folder can
  hold 1.5 GB `.mov` packshots, so `--max-media-mb` (default 1024) matters.

```bash
# one project with everything, found through its author's handle
python -m higgsfield_scraper scrape projects --what user-projects --users <handle> --max-items 1 --with-project-assets --with-project-brief --with-project-stats --with-project-comments --with-project-related
# the talent contest: 5 entries (entries tab `latest`) and all their nested data
python -m higgsfield_scraper scrape projects --what contests --contest talent-contest --with-submissions --max-submissions 5 --with-project-assets --with-project-brief --with-project-stats --with-project-comments --with-project-related
# a weekly contest: 5 submissions, their folders and assets
python -m higgsfield_scraper scrape projects --what contests --contest wcc-the-place-you-know --with-submissions --max-submissions 5 --with-project-assets
# two entries tabs, up to 10 entries each, stats + model stack only
python -m higgsfield_scraper scrape projects --what contests --contest talent-contest --with-submissions --contest-tabs latest,trending --max-submissions 10 --with-project-stats
# nested data for the public publications listing
python -m higgsfield_scraper scrape projects --what publications --max-items 20 --with-project-stats --with-project-comments
# + the asset files themselves
python -m higgsfield_scraper scrape projects --what user-projects --users <handle> --max-items 1 --with-project-assets --download-media full --max-media-mb 2048
```

Dry runs print only the first request; the nested requests follow at runtime:

```
$ python -m higgsfield_scraper scrape projects --what contests --contest talent-contest --with-submissions --max-submissions 5 --with-project-assets --with-project-brief --with-project-stats --with-project-comments --with-project-related --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/contests/talent-contest

$ python -m higgsfield_scraper scrape projects --what publications,user-projects --users a,b --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/project-publications/categories
GET https://fnf-api-gw.higgsfield.ai/fnf/project-publications?limit=50
GET https://fnf-api-gw.higgsfield.ai/fnf/user/a/v2/publications?publication_type=project&limit=50
GET https://fnf-api-gw.higgsfield.ai/fnf/user/b/v2/publications?publication_type=project&limit=50

$ python -m higgsfield_scraper scrape projects --contest talent-contest --contest-tabs liked --with-submissions --dry-run
error: --contest-tabs: unknown ['liked']; choose from ['latest', 'trending', 'most_watched', 'all_entries', 'submissions'] or 'all'
```

Live runs (2026-11-26, all five `--with-project-*` flags): one project via `--users` → 13 folders, 64 assets (60 +
4 Watermarks), 1 brief, 7 stack rows, 6 comments, 20 related, 11 requests; `--contest talent-contest
--max-submissions 5` → 5 projects, 102 folders, 4,745 assets, 100 requests. The talent contest's own
`/contests/{id}/submissions` is empty: its entries come from the entries tab.

## 1e. Community pages: shots, posts, Feed, creators, talents, comment threads

Opt-in values of `scrape community --feeds` (added 2026-11-26), **never part of `--feeds all`**. They can be combined
with the gallery feeds. Every request is public and sent without a session; the parsers drop per-viewer flags.
Evidence, data model and totals: [`docs/COMMUNITY_COVERAGE.md`](docs/COMMUNITY_COVERAGE.md).

| `--feeds` value | Page | Endpoint (GET) | Kind → CSV |
|---|---|---|---|
| `shots` | `/community/generations` | `fnf-community /generations/feed?limit≤50&cursor` (+ `type`, `models`) | `community_shot` → `shots.csv` (joins `community_generation` by `publication_id` / `generation_id`) |
| `posts` | Community posts | `fnf-community /publications/feed?limit&offset` (~24k posts) | `community_post` → `posts.csv`, `post_media.csv` |
| `feed` | `/community/feed` | `fnf-community /feed?limit≤50&cursor` (shots, projects, blog posts, posts) | `community_feed_item` → `feed_items.csv` |
| `creators` | `/community/creators` | `fnf /community/discovery/v2/creators?all=true&sort=default` (~650) | `community_creator_stats` → `creator_stats.csv`, `creator_works.csv` |
| `talents` | Talents hub | `fnf /community/discovery/talents?sort=rating&offset` (~80) | same kind, `listing = talents` |
| `music-cards` | `/music-cards` | `fnf-cms-api /music-cards-presets` + `/music-cards-{styles,occasions,roles}` (111 templates) | `community_music_card`, `community_music_card_option` → `music_cards.csv`, `music_card_options.csv` |
| `job-showcase` | `/seedance-2-community` (movies) | the page's SSR state (`loaderData.seedanceMovies`; 5 movies, 54 jobs) | `community_showcase_job` → `showcase_jobs.csv` |
| `collections` | `/collection/catch-the-pulse` | `fnf /collections/catch-the-pulse` (15 motions) | `community_collection` → `collections.csv`, `collection_items.csv` |
| `explore-cards` | explore / home cards | `cms /cards?size&cursor` (192) | `community_explore_card` → `explore_cards.csv` |
| `feed-categories` | Feed hashtag contests | `fnf-community /feed/categories` + `/feed/ongoing` | `community_feed_category` → `feed_categories.csv` |

Since 2026-11-26, `creators` / `talents` also emit every showcased work in full (`community_creator_work` →
`creator_works.csv` + inputs / results / media CSVs) and `shots` emits the model facet (`community_shot_model_facet`
→ `shot_model_facets.csv`); the requests are unchanged. Details: [§1h](#1h-opt-in-extras-of-the-content-map-round-2026-11-26).

- `--max-items` caps **each** opt-in feed separately (gallery feeds share one budget). `--max-pages` caps pages per
  feed and per comment thread. `--type image|video` and `--models` are passed to the shots feed.
- `--with-comments` with `shots`, `feed` or `posts` reads the comment threads (+ one level of replies) of those
  items: shots, projects and blog posts on `fnf-community /entities/{generation_publication|project_publication|blog_post}/{id}/comments`
  (cursor), posts on `/publications/{id}/comments` (offset). Rows are `community_comment` with `thread_type` = the
  entity type. Without an opt-in feed, `--with-comments` behaves as before (Community posts' comments only).
- Gallery generations **do** have comments (on the `/entities/generation_publication/…` path); the default
  `trending`/`approved` crawl does not request them (1 request per generation). Use `--feeds shots --with-comments`.
- Creator names, bios, locations and avatars only with `--with-profiles` (also blanked in the `raw/` and `http/`
  archives without it).

```bash
python -m higgsfield_scraper scrape community --feeds shots,posts,feed --max-items 20 --with-comments
python -m higgsfield_scraper scrape community --feeds creators,talents --max-items 20
python -m higgsfield_scraper scrape community --feeds shots --type video --models seedance_2_5 --max-items 50
python -m higgsfield_scraper scrape community --feeds all,shots,posts,feed,creators,talents --with-comments --max-items 100
```

```
$ python -m higgsfield_scraper scrape community --feeds shots,posts,feed --max-items 20 --with-comments --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=20
GET https://fnf-api-gw.higgsfield.ai/fnf-community/publications/feed?limit=20
GET https://fnf-api-gw.higgsfield.ai/fnf-community/feed?limit=20

$ python -m higgsfield_scraper scrape community --feeds creators,talents --max-items 20 --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/community/discovery/v2/creators?all=true&sort=default&limit=20
GET https://fnf-api-gw.higgsfield.ai/fnf/community/discovery/talents?sort=rating&limit=20&offset=0

$ python -m higgsfield_scraper scrape community --feeds shots --type video --models seedance_2_5 --max-items 50 --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=50&type=video&models=seedance_2_5
```

Live check (2026-11-26): `--feeds shots,posts,feed --with-comments --max-items 20` → 20 + 20 + 20 items and 409
comments (project 222, blog 109, shot 66, post 12) from 68 thread requests.

## 1f. Site: community rooms (`room-list`, `room-content`)

Two opt-in values of `scrape site --what` (added 2026-11-26), **not part of `--what all`** (like `rooms`, which keeps
only each room page's title/description). Public, no login; data model in
[`docs/COMMUNITY_COVERAGE.md`](docs/COMMUNITY_COVERAGE.md#site_room-csvroomscsv--key-room_id).

| `--what` | Endpoints (GET, `fnf-community`) | Kinds → CSV |
|---|---|---|
| `room-list` | `/rooms?limit=50&cursor` + `/publications/room-stats?room_id` per room | `site_room` → `rooms.csv` (works per type, followers, posts / discussions counts, call status) |
| `room-content` | `room-list` + `/rooms/{id}/items` (works: shots with prompts, projects, blog posts) + `/publications/feed?room_id&kind=discussion` | + `site_room_item` → `room_items.csv`, `site_room_discussion` → `room_discussions.csv`, `room_discussion_media.csv` |

`--max-items` caps rooms, room items and room discussions **separately**. Room chat does not exist as a public
stream, and room followers (people only) are not collected.

```bash
python -m higgsfield_scraper scrape site --what room-list                          # all 88 rooms (~90 requests)
python -m higgsfield_scraper scrape site --what room-content --max-items 50 --label rooms
python -m higgsfield_scraper scrape site --what all,room-content                   # every site page + rooms
```

```
$ python -m higgsfield_scraper scrape site --what room-list --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-community/rooms?limit=50
```

Live check (2026-11-26): `--what room-list` → 88 rooms in 90 requests (2 list pages + 88 room-stats);
`--what room-content --max-items 20` → 20 rooms, 20 room items, 1 discussion, 61 requests.

## 1g. `scrape showcase`: every source and option

New scraper (2026-11-26) for public example / showcase content no other scraper covers. GET only, about 1 request/s.
Public sources never carry a token, even with `--auth auto`; only `season` needs a login. Guide with evidence, HTTP
flow, field tables and gaps: [`docs/scrapers/showcase.md`](docs/scrapers/showcase.md).

| `--what` | Source (GET) | Kinds → collection | Size (2026-11-26) |
|---|---|---|---|
| `canvas_templates` | `canvas-worker.higgsfield.ai/api/templates` | `showcase_canvas_template` → `canvas_templates` | 5 |
| `editing_room_examples` | `cms /videoshop-examples` + `fnf /videoshop/project-examples` | `showcase_editing_room_example`, `…_project`, `…_render` | 11 examples, 6 projects, 41 renders |
| `property_studio_examples` | `/property-studio` page → JS preset table + l10n titles | `showcase_property_studio_example` | 69 |
| `explore_categories` (alias `explore`) | `cms /higgsfield-multiplier/video-explore/v2` (+ `/categories`) | `showcase_explore_category`, `…_item`, `…_variant` (likes, prompt, params, publication id) | 6 categories, 35 curated, 49,322 community |
| `effect_examples` | `/effects/sitemap.xml` → `/effects/examples/{slug}` (SSR) | `showcase_effect_sample` | 87 pages × first page of samples |
| `api_models` | `docs.higgsfield.ai/docs/openapi.json` + `/llms-full.txt` | `showcase_api_model` (parameters, listed prices) | 83 endpoints |
| `cinema_controls` | `cms /cinema-studio-4-0/creative-controls` | `showcase_cinema_control` | 78 |
| `faceless_showcases` | `cms /youtube-faceless-showcases` | `showcase_faceless_showcase` | 9 |
| `intone_examples` | `cms /intone/explore` | `showcase_intone_example` | 18 |
| `seedance_presets` | `cms /seedance-2-0` | `showcase_seedance_preset` | 14 |
| `motion_control_presets` | `cms /kling-motion-control-presets` | `showcase_motion_control_preset` | 36 |
| `season` | `fnf-api-gw /fnf-score/v1/season` | `showcase_season` | **login only**; `null` (no active season) |
| `reels_presets` (alias `reels`; **opt-in**) | `fnf-cms-api /ai-reels-presets?lang=[&source=community]` + `/ai-reels-presets/{slug}` | `showcase_reels_preset` → `reels_presets` (Shorts Studio example reels: output video, prompt, script, inputs, reference reel stats, recreates) | 40 curated + 75 community |
| `reels_comments` (**opt-in**) | `fnf-community /entities/generation_publication/{id}/comments` | `showcase_reels_comment` → `reels_comments` | 73 threads, 0 comments |
| `main_feed` (**by name only**, not in `all`) | `cms /main-feed?lang&size=20[&cursor]` | `showcase_main_feed_item`, `showcase_main_feed_variant` → `main_feed_items`, `main_feed_variants` (Genjutsu presets with likes / views / comments / `times_made`, variants with prompt and params; playable-ad game rows) | no total; page 1 = 17 genjutsu + 3 game rows |

`effect_examples` also emits `showcase_effect_preset` → `effect_presets` since 2026-11-26 (the page's template: inputs,
param choices, credit price matrix), and input media carry `source_role` / `source_type` (the raw role) next to
`role = input`. `explore` is accepted as an alias of `explore_categories` (it is not listed in `--help`).

`--what` default = every public source except the opt-in reels sources (`public`, unchanged); `all` = public +
`reels_presets` + `reels_comments` + `season`; `main_feed` is selected **only by name** (`--what main_feed` or
`--what all,main_feed`), so `--what all` plans the same requests as before it was added. `season` is skipped cleanly
without a session and not scheduled with `--auth off`.

| Option | Default | Effect |
|---|---|---|
| `--lang` | `en` | CMS `lang` (en, es, de, ja, ko) and Property Studio titles (+ zh titles) |
| `--explore-sources` | both | `higgsfield` (curated, ~35), `community` (~49k) |
| `--explore-sort` | `new` | community sort: `new` (page numbers, has `total`), `trending` (opaque cursor), `both`; the curated feed is always `trending` |
| `--explore-pages N` | 3 | pages of 20 per explore feed; `0` = to the end (≈2,467 pages for community/new); `--max-pages` also applies |
| `--explore-categories LIST\|all` | off | also crawl the community feed per category (names from `/categories`) |
| `--effects LIST` | every sitemap slug | only these `/effects/examples` slugs |
| `--reels-sources` | both | Shorts Studio lists: `higgsfield` (curated, ~40), `community` (~75); comments exist only on community presets |
| `--main-feed-pages N` | 3 | `main_feed` only: pages of 20 rows; `0` = until the cursor ends; `--max-pages` and `--max-items` (per kind) also stop paging |
| `--with-profiles` | off | keep creator `user_id` / `username` / avatar on explore variants, effect samples and reels presets/comments, plus the reference reel's author handle (default: only a pseudonymous `creator_key`) |
| `--max-items` | no limit | **per kind** (reels presets: per list, curated and community; reels comments: per thread count) |
| `--max-pages` | — | per explore feed, per JS-chunk discovery, per effect page sequence |
| `--download-media` | `none` | `thumbs` / `full` / `all` into `<run>/media/` |

```bash
python -m higgsfield_scraper scrape showcase                                                  # every public source
python -m higgsfield_scraper scrape showcase --what api_models,canvas_templates
python -m higgsfield_scraper scrape showcase --what explore --explore-sort both --explore-pages 10
python -m higgsfield_scraper scrape showcase --what explore --explore-sources community --explore-pages 0   # all ~49k, with likes
python -m higgsfield_scraper scrape showcase --what explore_categories --explore-sources community --explore-categories all --explore-pages 1
python -m higgsfield_scraper scrape showcase --what effect_examples --effects acid,vanish
python -m higgsfield_scraper scrape showcase --what property_studio_examples --lang de --download-media thumbs
python -m higgsfield_scraper scrape showcase --what editing_room_examples,cinema_controls,faceless_showcases,intone_examples,seedance_presets,motion_control_presets
python -m higgsfield_scraper scrape showcase --what reels_presets,reels_comments --max-items 20   # opt-in Shorts Studio reels + comments
python -m higgsfield_scraper scrape showcase --what all --max-items 30                         # + login-only season
python -m higgsfield_scraper scrape showcase --what main_feed --main-feed-pages 2              # home feed (by name only)
```

```
$ python -m higgsfield_scraper scrape showcase --dry-run
GET https://canvas-worker.higgsfield.ai/api/templates
GET https://cms.higgsfield.ai/videoshop-examples?lang=en
GET https://fnf-api-gw.higgsfield.ai/fnf/videoshop/project-examples
GET https://higgsfield.ai/property-studio
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2/categories?lang=en
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2?lang=en&source=higgsfield&size=20&cursor=1
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2?lang=en&source=community&size=20&cursor=1&sort=new
GET https://higgsfield.ai/effects/sitemap.xml
GET https://docs.higgsfield.ai/docs/openapi.json
GET https://cms.higgsfield.ai/cinema-studio-4-0/creative-controls?lang=en
GET https://cms.higgsfield.ai/youtube-faceless-showcases?lang=en&size=20
GET https://cms.higgsfield.ai/intone/explore?lang=en&size=20&cursor=1
GET https://cms.higgsfield.ai/seedance-2-0?lang=en
GET https://cms.higgsfield.ai/kling-motion-control-presets?lang=en

$ python -m higgsfield_scraper scrape showcase --what explore --explore-sort both --explore-pages 2 --dry-run
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2/categories?lang=en
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2?lang=en&source=higgsfield&size=20&cursor=1
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2?lang=en&source=community&size=20&cursor=1&sort=new
GET https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2?lang=en&source=community&size=20&cursor=1&sort=trending&view=v2

$ python -m higgsfield_scraper scrape showcase --what effect_examples --effects acid,vanish --dry-run
GET https://higgsfield.ai/effects/examples/acid
GET https://higgsfield.ai/effects/examples/vanish
```

The dry run never lists the `season` request (the session is resolved when the crawl starts), nor the per-page
follow-ups (Property Studio JS chunks and l10n files, `llms-full.txt`, category feeds, effect pages from the
sitemap). Outputs: `dataset.json`, `json/<collection>.json` and complete CSVs (one per collection plus child tables
such as `explore_variants__media.csv`, `api_models__parameters.csv`); see [§7](#output-of-the-other-scrapers).


## 1h. Opt-in extras of the content-map round (2026-11-26)

These options close the gaps of [`docs/CONTENT_MAP.md`](docs/CONTENT_MAP.md) §16 and the fixes of
[`docs/COMPLETENESS.md`](docs/COMPLETENESS.md) §11. **All are opt-in and selected by name only**: the default run and
every existing `all` selection (`--what all`, `--feeds all`, `--kinds all`) plan exactly the same requests as before
(dry-runs compared byte for byte against the previous commit). Every request is a public, anonymous GET.

| Scraper | Option | Endpoint(s) (GET) | Output (kind → collection / CSV) | Guide |
|---|---|---|---|---|
| `community` | `--feeds feed-categories` (aliases `feed_categories`, `feed-category`) | `fnf-community /feed/categories` + `/feed/ongoing` | `community_feed_category` → `feed_categories`, `feed_categories.csv` (slug, title, hashtag, `post_count`, previews) | [community.md](docs/scrapers/community.md) |
| `community` | `--feeds music-cards` | `fnf-cms-api /music-cards-presets` + `/music-cards-{styles,occasions,roles}` | `community_music_card`, `community_music_card_option` → `music_cards.csv`, `music_card_recipients.csv`, `music_card_options.csv` | [community.md](docs/scrapers/community.md) |
| `community` | `--feeds job-showcase` | page `/seedance-2-community` (SSR state = fnf `/jobs/showcase/seedance-2-0`, which challenges the crawler) | `community_showcase_job` → `showcase_jobs.csv` (+ `_inputs`, `_results`) | [community.md](docs/scrapers/community.md) |
| `community` | `--feeds collections` | fnf `/collections/catch-the-pulse` | `community_collection` → `collections.csv`, `collection_items.csv` | [community.md](docs/scrapers/community.md) |
| `community` | `--feeds explore-cards` | cms `/cards?size&cursor` | `community_explore_card` → `explore_cards.csv` | [community.md](docs/scrapers/community.md) |
| `community` | `--feeds creators,talents` (new output, same requests) | same as before | + `community_creator_work` → `creator_works.csv` + `creator_work_{inputs,results,media}.csv`: every work of every creator card in full (shots parsed like gallery generations; project cards with media) | [COMMUNITY_COVERAGE.md](docs/COMMUNITY_COVERAGE.md) |
| `community` | `--feeds shots` (new output, same requests) | same as before | + `community_shot_model_facet` → `shot_model_facets.csv` (the feed's `available_models[]`) | [community.md](docs/scrapers/community.md) |
| `showcase` | `--what main_feed` (+ `--main-feed-pages N`, default 3, `0` = to the end) | cms `/main-feed?lang&size=20[&cursor]` | `showcase_main_feed_item`, `showcase_main_feed_variant` → `main_feed_items`, `main_feed_variants` (+ `__media`, `__inputs`) | [showcase.md §11](docs/scrapers/showcase.md) |
| `showcase` | `--what reels_presets,reels_comments` (+ `--reels-sources higgsfield,community`) | `fnf-cms-api /ai-reels-presets[?source=community]`, `/ai-reels-presets/{slug}`; `fnf-community /entities/generation_publication/{id}/comments` | `showcase_reels_preset`, `showcase_reels_comment` | [showcase.md §10](docs/scrapers/showcase.md) |
| `showcase` | `--what effect_examples` (new output, same requests) | same pages | + `showcase_effect_preset` → `effect_presets` (inputs, param choices, credit price matrix) | [showcase.md](docs/scrapers/showcase.md) |
| `projects` | `--what trending` (+ `--trending-sort`, `--trending-filter`, `--trending-with-contest`) | fnf `/project-publications/trending?limit≤50&cursor[&sort&filter&with_contest]` | publications + `projects_trending_row` → `trending`, `trending.csv` (position, `total_reported`, snapshot) | [projects.md](docs/scrapers/projects.md) |
| `projects` | `--what contest-participation` (per `--entry-keys`, default both) | fnf `/contest-participations/publications/counters`, `/config` (`contest_key`) | `contest_participation`, `contest_participation.csv` (total / public / private + stage, windows, limits) | [projects.md](docs/scrapers/projects.md) |
| `projects` | `--with-user-works` | fnf `/user/{user_id}/v2/publications`, `/user/{user_id}/stats` | `projects_user_work` → `user_works` (+ `user_work_variants.csv`, `user_work_inputs.csv`), `projects_user_stats` → `user_stats` | [projects.md](docs/scrapers/projects.md) |
| `catalog` | `--kinds outfit_character` (**not** even in `--kinds all`) | fnf `/outfits/characters` | `catalog_outfit_character` → `outfit_characters` | [catalog.md](docs/scrapers/catalog.md) |
| `site` | `--what academy-api` (not in `--what all`) | `fnf-academy /api/v1/categories`, `/courses`, `/courses/{slug}`, `/lessons/{id}` | `site_academy_api_{category,course,lesson}` → `academy_api_*` (+ child CSVs) | [site.md](docs/scrapers/site.md) |

Option details:

- **`--trending-sort`** `default|most_viewed|most_liked|newest|oldest`: the ranking of `--what trending`. `default`
  (or no flag) sends no `sort`, like the web app. **`--trending-filter`** `all|non_contest|contest|talents_hub`: sent as
  `filter`; without it no filter is sent (every project). **`--trending-with-contest`**: sends `with_contest=true`;
  ignored when `--trending-filter` is given (the site does the same). The label of each listing row records the
  combination (`trending[:filter=…][:sort=…][:with_contest]`). Trending publications count against `--max-items` and
  are followed by `--with-details` / `--with-project-*` like any other listing.
- **`--with-user-works`**: reads the published works (assets = full generations with prompt, params, results;
  projects; folders; contest submissions) and the stats of users **already found in this run**: the owner of each
  project in a `--users` listing or in the contest entries listing, and every contest submitter. Broad listings
  (publications, recommended, trending) never add users, and users are never enumerated. Rows carry
  `creator_uid_key` (+ `creator_key`); ids, names and avatars only with `--with-profiles`. `--max-pages` caps each
  user's pages. Works with `generation_key = job:<id>` merge with community generations in
  `scripts/merge_generations.py`.
- **`--main-feed-pages N`**: pages of 20 rows of the home feed (default 3; `0` = until the cursor ends). Paging also
  stops at `--max-pages`, `--max-items` (per kind) or an unchanged/empty cursor. The feed is personalised per anonymous
  session and has no total.
- **`--reels-sources`**: `higgsfield` (curated, ~40) and/or `community` (~75); comments exist only on community presets.
- `--max-items` caps each opt-in feed / kind separately; `--download-media` covers the new media (previews, posters,
  outputs) like any other kind.

```bash
python -m higgsfield_scraper scrape community --feeds feed-categories,music-cards,job-showcase,collections,explore-cards
python -m higgsfield_scraper scrape community --feeds creators,talents --with-raw-params        # every work in full
python -m higgsfield_scraper scrape showcase --what main_feed --main-feed-pages 0                 # whole home feed
python -m higgsfield_scraper scrape showcase --what all,main_feed --max-items 30                  # `all` + the main feed
python -m higgsfield_scraper scrape projects --what trending --trending-sort most_viewed --trending-filter contest --max-pages 2
python -m higgsfield_scraper scrape projects --what all,trending,contest-participation           # all + the two extras
python -m higgsfield_scraper scrape projects --what contests --contest talent-contest --with-submissions --max-submissions 5 --with-user-works
python -m higgsfield_scraper scrape catalog --kinds outfit_character
python -m higgsfield_scraper scrape site --what academy-api                                      # 2 + 17 + ~180 requests
python -m higgsfield_scraper scrape site --what academy-api --no-content                         # categories + course list
```

```
$ python -m higgsfield_scraper scrape projects --what trending,contest-participation --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/project-publications/trending?limit=50
GET https://fnf-api-gw.higgsfield.ai/fnf/contest-participations/publications/counters?contest_key=ai_film_festival
GET https://fnf-api-gw.higgsfield.ai/fnf/contest-participations/config?contest_key=ai_film_festival
GET https://fnf-api-gw.higgsfield.ai/fnf/contest-participations/publications/counters?contest_key=talent_contest
GET https://fnf-api-gw.higgsfield.ai/fnf/contest-participations/config?contest_key=talent_contest

$ python -m higgsfield_scraper scrape projects --what trending --trending-sort most_viewed --trending-filter contest --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/project-publications/trending?limit=50&filter=contest&sort=most_viewed

$ python -m higgsfield_scraper scrape community --feeds feed-categories,music-cards,job-showcase,collections,explore-cards --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-community/feed/categories
GET https://fnf-api-gw.higgsfield.ai/fnf-community/feed/ongoing
GET https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-presets?lang=en
GET https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-styles?lang=en
GET https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-occasions?lang=en
GET https://fnf-api-gw.higgsfield.ai/fnf-cms-api/music-cards-roles?lang=en
GET https://higgsfield.ai/seedance-2-community
GET https://fnf-api-gw.higgsfield.ai/fnf/collections/catch-the-pulse
GET https://cms.higgsfield.ai/cards?size=100

$ python -m higgsfield_scraper scrape showcase --what main_feed --dry-run
GET https://cms.higgsfield.ai/main-feed?lang=en&size=20

$ python -m higgsfield_scraper scrape catalog --kinds outfit_character --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/outfits/characters

$ python -m higgsfield_scraper scrape site --what academy-api --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-academy/api/v1/categories
GET https://fnf-api-gw.higgsfield.ai/fnf-academy/api/v1/courses
```

`--with-user-works` adds nothing to a dry run: its users are only known once the listings have been read.

**New field everywhere: `creator_uid_key`.** Every record with an author, creator or owner (community, projects,
showcase, studios, catalog katana presets) now also carries `creator_uid_key` = `core/privacy.py:creator_uid_key(<Clerk
user id>)` = `make_id("creator", id)`: one pseudonymous key per user, the same in every scraper (it equals the
showcase/studios `creator_key` / `author_key`). It is `null` when the id is missing or redacted. Existing keys
(`author_key`, `creator_key`, `user_id`) are unchanged.

## 1i. `scrape studios`: marketplaces, studio presets and galleries

Opt-in scraper (2026-11-26) for the public content of Higgsfield's studio products and marketplaces. GET only,
~1 request/s, never with a token (every source answers anonymously and identically with a session). Guide with JS
evidence, schema, HTTP flow and limits: [`docs/scrapers/studios.md`](docs/scrapers/studios.md).

| `--what` | Source (GET) | Kinds → collection | Size (2026-11-26) |
|---|---|---|---|
| `apps` | `fnf-apps-marketplace /api/v1/apps/categories` + `/api/v1/apps/community?limit=100&offset&sort` | `studios_app_category` → `app_categories`, `studios_app` → `apps` (views, likes, dislikes, remixes, `credits_usage`, author key, cover media) | 8 categories, ≈ 59,560 apps (no total) |
| `games` | `fnf-skills-marketplace /api/v1/games/community?limit=100&offset` | `studios_game` → `games` (plays, unique players, remixes, game URL, source zip) | 1,299 |
| `skills` | `fnf-skills-marketplace /api/v1/skills/community?limit=100&cursor` | `studios_skill` → `skills` (installs, unique users, usage, `example_prompt`, `content_url`) | 632 |
| `employees` | `fnf-skills-marketplace /api/v1/ai-agents/community?limit=100&cursor` | `studios_employee` → `employees` (public instructions, features, example videos, connectors, installs/usage) | 296 |
| `playable_presets` | `cms /playable-ads-presets?size=100&cursor=<page>&lang` | `studios_playable_preset` → `playable_presets` (HTML builds, videos, posters, recreate prompt/settings) | 112 |
| `influencer_options` | `cms /ai-influencer-config?lang` | `studios_influencer_option` → `influencer_options` (category → subcategory → option, with media) | 143 options |
| `galleries` | `fnf /publications/community/{approved,trending}?size=50&model=…` per studio; with `--with-comments` `fnf-community /entities/generation_publication/{id}/comments` | `studios_gallery_item` → `gallery_items` (job, prompt, settings, inputs, outputs, likes/views, `generation_key`), `studios_comment` → `comments` | 2,112 published outputs (approved 74 + trending 2,038) |

Default and `all` = `public` = every source (there is no login-only source). `--max-items` caps each kind separately
(child kinds `studios_app_category` and `studios_comment` are not counted); for galleries it caps all studios together,
in `--studios` order.

| Option | Default | Effect |
|---|---|---|
| `--what LIST` | all | comma list of the sources above, `all` or `public` |
| `--lang` | `en` | language of the CMS lists (`playable_presets`, `influencer_options`): `en es de ja ko` (labels and titles translated) |
| `--apps-sort` | `trending` | community apps order: `trending` (the app's default), `most_viewed`, `popular`, `newest` (unknown values fall back to `trending`) |
| `--studios LIST` | all | galleries only: `marketing_studio`, `ads_studio`, `cinema_studio`, `ai_influencer`, `canvas`, `shorts_drama`, `ai_host`, `property_studio`, `editing_room` (each maps to its job types, `endpoints.STUDIO_MODELS`) |
| `--gallery-feeds` | `approved,trending` | galleries only: which community feed(s) |
| `--gallery-pages N` | 3 | galleries only: pages of 50 per studio × feed (× model for trending); `0` = until `has_more` is false; `--max-pages` also applies |
| `--with-comments` | off | galleries only: also read the public top-level comments of every kept gallery item (1+ request per item, sequential) |
| `--with-profiles` | off | keep author `user_id` / name / avatar on apps, games, skills, employees, gallery items and comments (default: only the pseudonymous `author_key` + `creator_uid_key`) |
| `--max-items`, `--max-pages`, `--page-size` | — | shared limits (see the table in §1b) |
| `--download-media` | `none` | `thumbs` = images, `full` = videos, `all` = every media URL incl. gallery inputs and HTML / zip builds |

Notes: trending honours only the **last** `model` value (approved sums them), so trending is requested once per model
of each studio (the default run plans 64 first requests). A job in both feeds is kept once. Apps, games, skills and
employees have no comment API. Ads Studio, AI Host, Short Drama, Production and Popcorn have no public content (the
user's own workspace); their published outputs, if any, come through `--what galleries`.

```bash
python -m higgsfield_scraper scrape studios                                                   # every source
python -m higgsfield_scraper scrape studios --what apps --apps-sort most_viewed --max-items 500
python -m higgsfield_scraper scrape studios --what games,skills,employees
python -m higgsfield_scraper scrape studios --what galleries --studios marketing_studio,cinema_studio --gallery-pages 0 --with-comments
python -m higgsfield_scraper scrape studios --what galleries --gallery-feeds approved             # curated outputs only
python -m higgsfield_scraper scrape studios --what playable_presets --download-media thumbs
python -m higgsfield_scraper scrape studios --what playable_presets,influencer_options --lang de
python -m higgsfield_scraper scrape studios --what apps --max-requests 2000 --label all-apps   # all ≈ 59.6k apps (≈ 600 pages)
```

```
$ python -m higgsfield_scraper scrape studios --what apps,games,skills,employees,playable_presets,influencer_options --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf-apps-marketplace/api/v1/apps/categories
GET https://fnf-api-gw.higgsfield.ai/fnf-apps-marketplace/api/v1/apps/community?limit=100&offset=0&sort=trending
GET https://fnf-api-gw.higgsfield.ai/fnf-skills-marketplace/api/v1/games/community?limit=100&offset=0
GET https://fnf-api-gw.higgsfield.ai/fnf-skills-marketplace/api/v1/skills/community?limit=100
GET https://fnf-api-gw.higgsfield.ai/fnf-skills-marketplace/api/v1/ai-agents/community?limit=100
GET https://cms.higgsfield.ai/playable-ads-presets?size=100&cursor=1&lang=en
GET https://cms.higgsfield.ai/ai-influencer-config?lang=en

$ python -m higgsfield_scraper scrape studios --what galleries --studios marketing_studio --dry-run
GET https://fnf-api-gw.higgsfield.ai/fnf/publications/community/approved?size=50&model=marketing_studio_video&model=marketing_studio_image&model=marketing_studio_2_image&model=marketing_studio_v2_video&model=marketing_studio_v2_reference2video&model=marketing_storyboard&model=marketing_studio_hook&approved=true
GET https://fnf-api-gw.higgsfield.ai/fnf/publications/community/trending?size=50&model=marketing_studio_video
GET https://fnf-api-gw.higgsfield.ai/fnf/publications/community/trending?size=50&model=marketing_studio_image
…                                                     (one trending request per Marketing Studio model)
```

Live run (2026-11-26, `scrape studios --max-items 20 --with-comments`): 4.5 min, 0 errors; 8 app categories, 20 of
each kind, 1 comment.

## 1j. `scrape models`: the model registry from the public JS bundle

Opt-in scraper (2026-11-26). There is no public "models" API: the model list, each model's parameter schema
(`defineJob`), routes, plan tiers, feature-flag gating, featured order and picker menus are static code in the website's
JavaScript. `scrape models` downloads the tool pages and their JS chunks, extracts those facts **without executing any
JS** (regexes + bracket matching), joins them with `/job-sets/costs` and the Shots `available_models` facet, and
records the frontend build, so runs can be diffed build by build. GET only, anonymous. Guide:
[`docs/scrapers/models.md`](docs/scrapers/models.md).

| Option | Default | Effect |
|---|---|---|
| `--pages LIST` | `/ai/video,/ai/image,/lipsync-studio,/mixed-media` | tool pages (site paths) whose JS bundle is crawled; their preloaded chunks are fetched first |
| `--max-chunks N` | 800 | max JS chunks fetched; `0` = no cap. Chunks are queued by priority (page preloads, then imports of chunks with model data, then the rest), so the cap cuts the least useful ones; ≈ 540–670 chunks reach the whole registry with the default pages. Hitting the cap is recorded in `meta.limits_hit` and `builds[].coverage` |
| `--no-costs` | off | skip `/job-sets/costs` (`in_costs` = null, no `costs_version`) |
| `--no-shots` | off | skip the Shots feed facet (`in_shots` = null, no `shot_facets`) |
| shared options | | `--delay`, `--max-requests`, `--max-minutes`, `--auth`, logging … apply; `--max-items`, `--max-pages`, `--download-media` have **no effect** |

Output collections: `job_types` (one row per `job_set_type`: output, business flags, prompt policy, media roles /
counts, params schema with enums / ranges / defaults, validate ranges, wire keys, route, featured rank, gate status,
plan tier, `in_registry` / `in_routes` / `in_costs` / `in_shots`), `menu_entries` (picker entries with titles and
badges), `builds` (build id, commit, flags, costs version, coverage), `chunks` (url, size, sha256, markers) and
`shot_facets`; CSVs per collection + `job_type_params.csv`. Bodies are reduced to compact JSON extracts **before**
they reach `http/` and `raw/` (a run reads ~20 MB of JS; the extract keeps `size` + `sha256`), so
`normalize --run <id> --scraper models` re-joins `raw/` offline.

```bash
python -m higgsfield_scraper scrape models                                          # 4 pages, ≤ 800 chunks, costs + facet (~10–16 min)
python -m higgsfield_scraper scrape models --max-chunks 300 --no-shots              # quicker, may not reach the whole registry
python -m higgsfield_scraper scrape models --pages /ai/video,/ai/image --max-chunks 0   # no cap
python -m higgsfield_scraper normalize --run runs/<id> --scraper models             # re-join raw/ offline
```

```
$ python -m higgsfield_scraper scrape models --dry-run
GET https://higgsfield.ai/ai/video
GET https://higgsfield.ai/ai/image
GET https://higgsfield.ai/lipsync-studio
GET https://higgsfield.ai/mixed-media
GET https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs
GET https://fnf-api-gw.higgsfield.ai/fnf-community/generations/feed?limit=1
```

The JS chunks (`assets.higgsfield.ai/tanstack/assets/<chunk>.js`) follow at runtime. Live (2026-11-26, build
`548e0f3a`, default options): 806 requests, 16.4 min, coverage complete; 164 job types (119 with a `defineJob`),
96 menu entries, 167 shot facets. Known limits: settings spread from another module (`...y(j)`, e.g. `seedance_2_5`)
are kept as a `...` param with the spread source, not inlined; `--max-chunks 0` (no cap) has not been run live yet.

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
| `auth` | 4 login-only endpoints | `auth.credit_packages[]`, `auth.payloads[]` | Top-up packs, unlimited bundles, credit price. **Needs a login** (`login`, `HF_CLERK_CLIENT` or `--token`) |
| `account` | 8 login-only account endpoints (wallet, subscription, auto top-up, free gens, generation seconds + packs, bundle status) | `account.records[]` | The account's own pricing state, whitelisted. **Opt-in, needs a login, never part of `all`** (see [below](#--sections-account-opt-in-the-accounts-own-pricing-state)) |
| `all` | every section above except `account`; `auth` is included when you are logged in (`login`, `HF_CLERK_CLIENT` or `--token`), or when you write `all,auth` | everything | Full snapshot |

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
| + rows only logged-in users see (lite, magi_2) | `python -m higgsfield_scraper scrape --sections all --logged-in-prices` (saved login) | 12 | — |
| The account's own balances / top-up settings | `python -m higgsfield_scraper scrape --sections account --label my-balance` (saved login) | 8 | — |
| Your jobs vs the estimator | `python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20` (saved login) | — | — |
| Chain-preset credit prices, notices, restyle presets | `python -m higgsfield_scraper scrape catalog --kinds chain_preset,notice,restyle_preset --include-hidden` | 4 | — |
| Original series without a login | `python -m higgsfield_scraper scrape projects --what series --public-series` | 1 | — |
| Everything possible | `python -m higgsfield_scraper scrape --sections all --plan-sets all --marketing-versions all --include-raw-cost --include-hidden-plans` | 78 | ~2 min |
| Quiet, for cron/CI | `python -m higgsfield_scraper scrape --label cron --log-level WARNING --scrapy-log-level WARNING` | 6 | ~10 s |
| Re-parse after a code change | `python -m higgsfield_scraper normalize --run runs/<id>` | 0 | ~3 s |
| One project page with everything (assets, brief, stats, comments, related) | `python -m higgsfield_scraper scrape projects --what user-projects --users <handle> --max-items 1 --with-project-assets --with-project-brief --with-project-stats --with-project-comments --with-project-related` | 11 (live) | — |
| A contest's entries with their assets | `python -m higgsfield_scraper scrape projects --what contests --contest talent-contest --with-submissions --max-submissions 5 --with-project-assets` | — | — |
| Shots, posts, Feed + their comment threads | `python -m higgsfield_scraper scrape community --feeds shots,posts,feed --max-items 20 --with-comments` | ~70 (live) | — |
| Creator / talent stats (no names) | `python -m higgsfield_scraper scrape community --feeds creators,talents` | — | — |
| Every community room with its works | `python -m higgsfield_scraper scrape site --what room-content` | — | — |
| Showcase / example content | `python -m higgsfield_scraper scrape showcase` | — | — |
| Video-explore community feed with likes, to the end | `python -m higgsfield_scraper scrape showcase --what explore --explore-sources community --explore-pages 0` | ~2,470 | — |
| Browsable / dataset folder from a run | `python -m higgsfield_scraper export --run runs/<id> --layout tree` ([§6b](#6b-export-run-folders--browsable--dataset-folders)) | 0 | seconds |
| Apps / games / skills / AI-employees marketplaces | `python -m higgsfield_scraper scrape studios --what apps,games,skills,employees` ([§1i](#1i-scrape-studios-marketplaces-studio-presets-and-galleries)) | apps ≈ 600 pages | — |
| Every studio's published outputs + comments | `python -m higgsfield_scraper scrape studios --what galleries --gallery-pages 0 --with-comments` | — | — |
| Model registry of the current frontend build | `python -m higgsfield_scraper scrape models` ([§1j](#1j-scrape-models-the-model-registry-from-the-public-js-bundle)) | ≈ 806 | ~16 min |
| Trending projects ranking + contest counters | `python -m higgsfield_scraper scrape projects --what trending,contest-participation` | 5+ | — |
| Home main feed | `python -m higgsfield_scraper scrape showcase --what main_feed --main-feed-pages 0` | — | — |
| Academy JSON (free generations, MDX lessons) | `python -m higgsfield_scraper scrape site --what academy-api` | ≈ 200 | — |
| Count and dedupe every video / image across runs | `python scripts/merge_generations.py --latest community,catalog,projects,site,showcase,studios` ([§6c](#6c-count-and-dedupe-generations-scriptsmerge_generationspy)) | 0 | seconds |

### Scrape everything (all 10 scrapers)

One run folder per scraper; nothing is shared between runs. Without `--max-items` some feeds are large (community
trending ≈ 75k generations, explore ≈ 49k items, apps ≈ 59.6k, contest entries thousands), so start with a cap and
raise it. **The default `--max-requests 5000` stops large runs**: raise it (e.g. `--max-requests 200000`) and use
`--max-minutes` as a time box. Full sizes and times: [`docs/CONTENT_MAP.md`](docs/CONTENT_MAP.md) §18.

```bash
# 1. every public scraper with its default selection (studios and models have no "default run" elsewhere: they run here)
for s in pricing community catalog projects blog site showcase studios models; do python -m higgsfield_scraper scrape $s --label all-$s; done

# 2. + every public opt-in extra (each scraper's `all` and the options that are selected by name only)
python -m higgsfield_scraper scrape pricing --sections all --plan-sets all --marketing-versions all --include-hidden-plans --include-raw-cost --label all-prices
python -m higgsfield_scraper scrape community --feeds all,shots,posts,feed,creators,talents,music-cards,job-showcase,collections,explore-cards,feed-categories --with-comments --with-raw-params --max-items 5000 --max-requests 100000 --label all-community
python -m higgsfield_scraper scrape catalog --kinds all,outfit_character --include-hidden --with-samples --with-details --label all-catalog
python -m higgsfield_scraper scrape projects --what all,trending,contest-participation --with-details --with-submissions --public-series --max-requests 50000 --label all-projects
python -m higgsfield_scraper scrape projects --what contests --contest talent-contest --with-submissions --max-submissions 50 --with-project-assets --with-project-brief --with-project-stats --with-project-comments --with-project-related --with-user-works --label talent-nested
python -m higgsfield_scraper scrape blog --what all,community --label all-blog
python -m higgsfield_scraper scrape site --what all,room-content,academy-api --label all-site
python -m higgsfield_scraper scrape showcase --what all,main_feed --explore-sort both --explore-pages 0 --explore-categories all --main-feed-pages 0 --max-requests 20000 --label all-showcase
python -m higgsfield_scraper scrape studios --gallery-pages 0 --with-comments --max-requests 50000 --label all-studios
python -m higgsfield_scraper scrape models --max-chunks 0 --label all-models

# 3. with a login only: your own account (never part of a default run)
python -m higgsfield_scraper scrape pricing --sections all,account --logged-in-prices --label logged-in-prices
python -m higgsfield_scraper scrape account --with-jobs --max-items 200

# 4. turn runs into datasets, count/dedupe all videos and images
python -m higgsfield_scraper export --run "runs/*all-community*" --layout hf
python scripts/merge_generations.py --latest community,catalog,projects,site,showcase,studios
```

The opt-in extras in step 2, by scraper (none of them is in a default run; ★ = selected **by name only**, not even
by that scraper's `all`):

| Scraper | Opt-in extras |
|---|---|
| `pricing` | `--sections all` (adds `auth` with a login), `--plan-sets all`, `--marketing-versions all`, `--include-hidden-plans`, `--include-raw-cost`; login: `--logged-in-prices`, `--sections account` ★ |
| `community` | `--feeds shots,posts,feed,creators,talents,music-cards,job-showcase,collections,explore-cards,feed-categories` ★ (none of them is in `--feeds all`), `--with-comments`, `--with-raw-params`, `--detail`, `--estimate-cost all`, `--with-profiles` (personal data) |
| `catalog` | `--kinds all` (public + login group + `chain_preset`, `notice`, `restyle_preset`), `outfit_character` ★, `--with-samples`, `--with-details`, `--include-hidden` |
| `projects` | `--public-series`, `--with-details`, `--with-submissions`, `--with-project-assets/-brief/-stats/-comments/-related`, `--contest`, `--contest-tabs`, `--users`, `trending` ★, `contest-participation` ★, `--with-user-works` |
| `blog` | `--what all,community` |
| `site` | `--what rooms`, `room-list`, `room-content`, `academy-api` ★ (none of them is in `--what all`) |
| `showcase` | `--what all` (+ reels presets / comments, login `season`), `main_feed` ★, `--explore-pages 0`, `--explore-sort both`, `--explore-categories all`, `--main-feed-pages 0` |
| `studios` | the whole scraper; `--gallery-pages 0`, `--with-comments` |
| `models` | the whole scraper; `--max-chunks 0` |
| `account` | the whole scraper (login); `--with-jobs`, `--compare-estimate`, `--with-prompts` |

Windows (PowerShell): `foreach ($s in 'pricing','community','catalog','projects','blog','site','showcase','studios','models') { python -m higgsfield_scraper scrape $s --label all-$s }`.

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

**`schema [--out DIR]`** (default `schemas/`) writes the JSON Schemas of every scraper: the pricing
`dataset.schema.json`, one `<scraper>.dataset.schema.json` per other scraper (community, catalog, projects, blog,
site, account) and one `<entity>.schema.json` per entity kind (`plan`, `model`, `catalog_chain_preset`,
`account_job`, …).

```
wrote 81 schemas to schemas          (2026-11-26)
```

Note: `catalog.dataset.schema.json` is the plain `CatalogDataset` (without the opt-in `chain_presets` / `notices` /
`restyle_presets` collections); a run that selects one of them writes the full schema to its own
`output/schema/dataset.schema.json`.

## 6b. `export`: run folders → browsable / dataset folders

```
python -m higgsfield_scraper export --run RUN [--run RUN …] [--out DIR] [--layout tree|hf|webdataset|jsonl]
                                    [--group-by FIELDS] [--per-asset] [--media auto|link|copy|hardlink|none]
                                    [--download-missing-media thumbs|full] [--max-media-files N] [--max-media-mb MB]
                                    [--only COLLECTIONS] [--filter EXPR] [--shard-mb MB] [--dry-run] [--force]
                                    [--runs-dir DIR]
```

Turns one or more **finished run folders of any scraper** into a new folder that is easy to browse or to load as a
dataset (added 2026-11-26). Read-only: it never writes into a run folder, never re-scrapes, and sends no request
unless `--download-missing-media` is given. It exports only what the run output contains (no usernames unless the
run used `--with-profiles`). Full guide: [`docs/EXPORT.md`](docs/EXPORT.md).

| Option | Default | Accepts | Meaning |
|---|---|---|---|
| `--run RUN` | required, repeatable | run folder, run id (looked up in `--runs-dir`) or glob (`"runs/*sea*"`) | runs are read in order; the first occurrence of a record wins |
| `--out DIR` | `exports/<first run>-<layout>` | path | must be empty, absent or a previous export (`--force` otherwise); a folder inside a run is refused |
| `--layout` | `tree` | `tree` `hf` `webdataset` `jsonl` | see below |
| `--group-by FIELDS` | the scraper's profile default | comma list, e.g. `model,media_type`, `collection,feed,date`; `=name` = a literal folder | tree folders |
| `--per-asset` | off | flag | tree: one folder per asset (warns above 500 assets) |
| `--media` | `auto` | `auto` `link` `copy` `hardlink` `none` | `auto`/`copy`: copy the run's local media · `hardlink`: hardlink (copy across volumes) · `link`: URLs only + `urls.txt` · `none`: metadata only |
| `--download-missing-media` | off | `thumbs` `full` | GET media that is not in the run's `media/` (1 request/s, capped) into `<out>/.media_cache/` |
| `--max-media-files` | the run's cap (500) | int | cap on **new** downloads per invocation (cached files are reused, not counted) |
| `--max-media-mb` | the run's cap (1024) | float | same, in MB |
| `--only COLLECTIONS` | all | comma list (`assets,generations`) or `scraper:collection` | collections to export |
| `--filter EXPR` | none | `field=value` terms joined by `,` (AND); `a\|b` = OR; `!=` negates; `null`, `true`, `false` | e.g. `"has_prompt=true,media_type=video"` |
| `--shard-mb` | `1024` | float | webdataset shard size |
| `--dry-run` | off | flag | plan and print counts; writes nothing (not even the folder) |
| `--force` | off | flag | allow a non-empty non-export `--out`, or replacing an export of another layout |
| `--runs-dir` | `runs` (env `HF_RUNS_DIR`) | path | where bare run ids are looked up |

Filter / group fields: the normalized fields (`id`, `collection`, `scraper`, `prompt`, `has_prompt`, `has_media`,
`model`, `media_type`, `date`, `created_at`, `author_key`, `run_id` …), profile fields (projects: `contest`,
`project`, `folder`, `folder_path`) or any dotted path into the record (`engagement.likes`, `feed`).

**Layouts**

| `--layout` | Produces | Dedup |
|---|---|---|
| `tree` | website-like folders (projects: `<contest>/<project-slug>/<Folder>/<Subfolder>/` with `project.json`, `brief.md`, `comments.md`, `stats.json`; community: `<collection>/<feed>/<model>/<date>/`; …), a `metadata.jsonl` + `prompts.csv` per folder, media named `<position>_<model-slug>_<id12>.<ext>` with a same-stem `.txt` caption, `_tables/<name>.jsonl` for plain tables | per record (`rec:<scraper>:<collection>:<id>`): the same video in two folders stays in both |
| `hf` | Hugging Face ImageFolder / VideoFolder / AudioFolder: `images/train/metadata.jsonl` + files, `videos/train/…`, `urls.jsonl` (every row, also those without a local file) | per generation |
| `webdataset` | `shards/shard-000000.tar` … (rolled over at `--shard-mb`), per sample `<key>.<ext>` + `<key>.json` + `<key>.txt`; `index.jsonl`; deterministic tar headers | per generation |
| `jsonl` | one flat `manifest.jsonl`, one line per unique asset / generation | per generation |

Every export also writes `README.md` (data card with the licensing caveat), `export_manifest.json` (options, runs,
counts, every file with size and sha256) and `errors.log`. Generation-level dedup uses the keys of
`scripts/merge_generations.py` (`job:<id>`, `pub:<id>`, `media:<uuid>` of output URLs, `static:`) plus
`asset:<asset_id>` for project assets. Re-running with the same inputs changes nothing (files are replaced only when
their sha256 differs); files the previous export wrote and the new one does not are removed.

```bash
python -m higgsfield_scraper export --run runs/20261126-133628_nested-check                       # tree (default)
python -m higgsfield_scraper export --run runs/20261126-133628_nested-check --layout hf --out exports/nested-check-hf
python -m higgsfield_scraper export --run "runs/*nested-sea*" --layout jsonl                       # glob, deduped
python -m higgsfield_scraper export --run runs/A --run runs/B --layout webdataset --shard-mb 512
python -m higgsfield_scraper export --run runs/A --filter "has_prompt=true,media_type=video" --per-asset
python -m higgsfield_scraper export --run runs/A --only assets --download-missing-media thumbs --max-media-files 200
python -m higgsfield_scraper export --run runs/A --group-by model,media_type
python -m higgsfield_scraper export --run runs/A --dry-run                                           # plan only
```

Example output (run id looked up in `runs/`; no media had been downloaded in that run, so every row is URL-only):

```
$ python -m higgsfield_scraper export --run 20261126-133532_nested-sea2 --layout hf --dry-run
export: 65 rows -> 65 unique (generation-level dedup) from 1 run(s)
DRY RUN: would export 65 unique of 65 records -> exports\20261126-133532_nested-sea2-hf (hf)
  files 3  bytes 3,786  media files 0  url-only 65  time 0.1s
  media: {'missing': 65}

$ python -m higgsfield_scraper export --run "runs/*showcase-check*" --run runs/20261126-133046_cov-community-extras --layout jsonl --dry-run
export: 1072 rows -> 668 unique (generation-level dedup) from 3 run(s)
DRY RUN: would export 668 unique of 1072 records -> exports\20261126-140538_showcase-check-jsonl (jsonl)
  files 3  bytes 4,301  media files 0  url-only 502  time 0.6s
  media: {'missing': 502}
```

A real run prints the same lines with `exported …` plus `written N  unchanged N  removed N`. Exit code 0.

## 6c. Count and dedupe generations: `scripts/merge_generations.py`

```
python scripts/merge_generations.py [runs ...] [--latest SCRAPERS] [--runs-dir DIR] [--out DIR] [--compare OLD_INDEX]
```

Merges the generation-like records (anything with an output media URL on a Higgsfield CDN or a job id) of several run
folders (`output/dataset.json` of any scraper) into one deduplicated index. Records sharing a key are merged
(union-find): `job:<job id>`, `pub:<publication id>` (only for single-generation publications: community
generations / feed items / shots, showcase explore variants), `media:<file id>` (last UUID of an **output** URL; inputs
on `d2ol7oe51mr4n9.cloudfront.net` are never keys) and `static:<path>` (Property Studio files). Offline, no requests.

| Option | Default | Meaning |
|---|---|---|
| `runs` | — | run folders (each with `output/dataset.json`) |
| `--latest LIST` | — | add the latest run of each scraper in the comma list from `--runs-dir` |
| `--runs-dir` | `runs` | where `--latest` looks |
| `--out` | `runs/generations_index` | output folder |
| `--compare OLD` | — | a previous `generations_index.json`: adds `likes_delta` / `views_delta` per key |

Output: `<out>/generations_index.csv` + `.json` (one row per unique generation: `key`, `keys[]`, `sources[]`
(`scraper:collection`), `records`, best prompt / model / media URL / likes / views / comments) and
`<out>/duplicates.json` (duplicate counts per source pair). It prints a report:

```
$ python scripts/merge_generations.py --latest community,projects,site,showcase --out <dir>
runs: 20261126-133558_cov-community-comments, 20261126-135153_nested-check-wcc2, 20261126-134145_cov-site-room-list-full, 20261126-141401_showcase-check-normalized
records 974 -> unique 934 (duplicates 40, seen in >1 source 6)
  community:feed_items: 16 records -> 16 unique
  community:shots: 20 records -> 20 unique
  projects:assets: 576 records -> 562 unique
  …
  showcase:explore_variants: 117 records -> 97 unique
  dup pair community:feed_items + community:shots: 6
```

Likes over time: merge two snapshots and diff them:

```bash
python scripts/merge_generations.py <runs of day N>   --out runs/gi_dayN
python scripts/merge_generations.py <runs of day N+1> --out runs/gi_dayN1 --compare runs/gi_dayN/generations_index.json
```

More in [`docs/ENGAGEMENT.md`](docs/ENGAGEMENT.md#14-how-to-track-likes-over-time) and
[`docs/scrapers/showcase.md`](docs/scrapers/showcase.md#8-dedupe-scriptsmerge_generationspy).

---

## 6d. Top trending ideas and templates: `scripts/trending_ideas.py`

One command that scrapes Higgsfield's own trending-sorted lists (one run per feed, capped, GET only), ranks every
template / reel / ad / video / film by how fast it is trending, and packages the best ones with prompts, settings,
reference inputs and example videos, one folder per idea, organized by category.

```bash
python scripts/trending_ideas.py                         # scrape + rank + top 100 overall + top 20 per category
python scripts/trending_ideas.py --no-scrape --top 50    # re-rank the latest trend-* runs
python scripts/trending_ideas.py --no-scrape --compare exports/trending/<older>/ideas.json   # + "rising" score
```

| Step | What |
|---|---|
| scrape (labels `trend-*`) | `showcase --what main_feed,explore_categories,reels_presets --explore-sort trending` (15 pages), `community --feeds trending --type video` (1000), one `--feeds trending --models <m>` run per video model (`--video-models`; the trending feed is ~97 % images and honours one `model=` per request) and, as a separate run, `--feeds approved` (300), `studios --what galleries --gallery-feeds trending,approved`, `projects --what trending` (200), `catalog --kinds viral_preset,viral_type,marketing_preset,marketing_category` |
| categories | `reels_shorts` (Shorts Studio presets: remakes + the original social reel's views/likes), `ads` (Marketing/Ads Studio outputs, ad-model videos), `templates` (home-feed + Explore presets: times made), `videos` (community + Cinema Studio + other studios), `films` (trending projects) |
| dedupe | publication id, job id, output media key, title |
| score | 40 % rank inside its source (Higgsfield trending position 30 %, usage = times made / remakes 25 %, views/day 15 %, likes/day 10 %, likes 10 %, views 10 %; missing signals re-weighted, sources under 10 items damped) + 60 % the same reach signals ranked across all sources (usage only within its category). With `--compare`: 50 % popularity + 50 % growth |
| pick | overall top N (at most `--max-per-source` per source) + top K of every category |
| featured | catalog viral effects (main-page picks first) and ad templates in site order: no public popularity numbers, so they are listed separately, not scored |

| Option | Default | Meaning |
|---|---|---|
| `--top` | 100 | overall top ideas to package |
| `--per-category` | 20 | also package the top K of every category |
| `--featured` | 30 | featured viral effects / ad templates to package (each) |
| `--pages` | 15 | pages of the main feed and Explore trending |
| `--videos` / `--approved` | 1000 / 300 | community trending / approved videos |
| `--video-models` / `--per-model` | 12 video models / 100 | video models whose trending list is scraped separately, and items per model |
| `--gallery-pages` | 3 | studio gallery pages (50) per studio and feed |
| `--films` | 200 | trending projects |
| `--no-scrape` / `--runs DIR…` | – | reuse the latest `trend-*` runs / read these run folders |
| `--compare FILE` | – | a previous `ideas.json`: adds `score_rising` and per-idea growth |
| `--max-per-source` | 25 | diversity cap inside the overall top |
| `--no-download` | off | links only |
| `--max-outputs` / `--max-inputs` | 2 / 4 | example outputs / reference inputs per idea |
| `--max-mb` / `--delay` | 80 / 0.3 | skip larger files / seconds between downloads |
| `--out` | `exports/trending/<timestamp>` | output folder |

Output:

```
index.md                 overall top N, top K per category, featured templates
top.csv / top.json       the packaged ideas;  ideas.json = every candidate's metrics (for --compare)
categories/<cat>.md|csv  EVERY candidate of that category, ranked, with links and metrics
ideas/<cat>/NNN_<slug>/  README.md (what it is, prompt, model, settings, user inputs, trend metrics, source),
                         contest_brief.md (idea-submission draft: facts filled in, your hook/twist left blank),
                         prompt.txt, idea.json, assets/ (example outputs + thumbnails), inputs/ (reference inputs)
featured/<viral_effects|ad_templates>/NN_<slug>/   the same for Higgsfield-featured templates
```

`NNN` is the overall rank. Note: Higgsfield's live community *video* trending list is a short recent window
(29 videos on 2026-11-27: `seedance_2_5` 9, `magi_2` 19, `wan2_5_video` 1); the larger trend pools are the home feed,
Explore trending, Shorts/Reels presets and the studio galleries, which the script reads too. Downloads are cached once per URL in `exports/trending/_cache/` and hard-linked into the
idea folders.

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
  output/dataset.json              everything, nested (see README §7)
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
    auth_credit_packages.csv / auth_payloads.csv   (with a login: `auth` section)
    account.csv / account_items.csv    (only with --sections account; json/account.json too)
  output/items/<kind>.jsonl            Scrapy feeds written live during the crawl (one item per line, before joins)
  output/schema/dataset.schema.json
runs/LATEST          newest run id      runs/index.jsonl   one summary line per run
```

All `.json` files use **4-space indentation**. The `.jsonl` files hold one object per line, as that format requires.

### Output of the other scrapers

Every other scraper writes the same run-folder frame (`manifest.json`, `logs/`, `raw/`, `http/`, `media/`) and
`output/dataset.json`, `output/json/<collection>.json`, `output/csv/<collection>.csv` (complete; child lists get their
own CSV with the parent key), `output/items/<kind>.jsonl`, `output/schema/dataset.schema.json` and
`output/summary.md`. Per-scraper files are listed in each guide (`docs/scrapers/<name>.md`). Files added by the
opt-in features of 2026-11-26:

| Scraper / option | Extra collections and files |
|---|---|
| `projects --with-project-assets` | `folders`, `assets`; `csv/project_folders.csv`, `project_assets.csv`, `project_asset_variants.csv`, `project_asset_inputs.csv` |
| `projects --with-project-brief` | `briefs`; `csv/project_briefs.csv`; **`output/briefs/<slug>.md`** (one Markdown brief per project) |
| `projects --with-project-stats` | `project_stats`, `stack_items`; `csv/project_stats.csv`, `project_stack.csv` |
| `projects --with-project-comments` / `--with-project-related` | `comments` / `related`; `csv/project_comments.csv` / `project_related.csv` |
| `projects` (any `--with-project-*`) | `nested_summary` in `dataset.json` (counts, asset-count mismatches) |
| `community --feeds shots / posts / feed / creators,talents` | `csv/shots.csv` / `posts.csv` + `post_media.csv` / `feed_items.csv` / `creator_stats.csv` + `creator_works.csv` |
| `community --with-comments` | `csv/comments.csv` (`thread_type` = `publication`, `generation_publication`, `project_publication`, `blog_post`) |
| `site --what room-list / room-content` | `csv/rooms.csv` / + `room_items.csv`, `room_discussions.csv`, `room_discussion_media.csv` |
| `site --what academy-api` | `academy_api_categories`, `academy_api_courses` (+ `_objectives`, `_authors`, `_examples`, `_lessons`), `academy_api_lessons` (+ `_video_subtitles`, `_video_cues`, `_resources`) |
| `community --feeds creators,talents` / `shots` / `feed-categories` | + `creator_works.csv`, `creator_work_inputs.csv`, `creator_work_results.csv`, `creator_work_media.csv` / + `shot_model_facets.csv` / `feed_categories.csv` |
| `community --feeds music-cards / job-showcase / collections / explore-cards` | `music_cards.csv` + `music_card_recipients.csv`, `music_card_options.csv` / `showcase_jobs.csv` + `_inputs`, `_results` / `collections.csv` + `collection_items.csv` / `explore_cards.csv`; `gallery_stats.csv` |
| `projects --what trending / contest-participation / --with-user-works` | `trending.csv` / `contest_participation.csv` / `user_works` (+ `user_work_variants.csv`, `user_work_inputs.csv`), `user_stats` |
| `catalog --kinds outfit_character` | `outfit_characters` |
| `studios` | `app_categories`, `apps`, `games`, `skills`, `employees`, `playable_presets`, `influencer_options`, `gallery_items`, `comments` + child CSVs `<collection>__media.csv`, `employees__features.csv`, `gallery_items__inputs.csv` |
| `models` | `job_types`, `menu_entries`, `builds`, `chunks`, `shot_facets` + `job_type_params.csv` (one row per parameter) |
| `showcase` | one collection + CSV per kind (`canvas_templates`, `editing_room_examples`, `editing_room_projects`, `editing_room_renders`, `property_studio_examples`, `explore_categories`, `explore_items`, `explore_variants`, `effect_samples`, `api_models`, `cinema_controls`, `faceless_showcases`, `intone_examples`, `seedance_presets`, `motion_control_presets`, `seasons`; opt-in `reels_presets`, `reels_comments`, `main_feed_items`, `main_feed_variants`; `effect_presets` with `effect_examples`) + child CSVs `<collection>__media.csv`, `__inputs`, `__edits`, `__scenes`, `__segments`, `api_models__parameters.csv`, `api_models__prices.csv` |
| `export` (not a run) | `exports/<run>-<layout>/` (gitignored): `README.md`, `export_manifest.json`, `errors.log` + the layout's files ([§6b](#6b-export-run-folders--browsable--dataset-folders)) |
| `scripts/merge_generations.py` | `runs/generations_index/generations_index.csv`, `.json`, `duplicates.json` ([§6c](#6c-count-and-dedupe-generations-scriptsmerge_generationspy)) |

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
