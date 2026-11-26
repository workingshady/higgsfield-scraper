# Higgsfield reverse-engineering playbook

**How** this project reverse-engineers higgsfield.ai: rules, tools, the staged process, facts and pitfalls.
**Where we are** (status, findings, open questions, backlog) is in the checkpoint:
[`higgsfield-re-checkpoint.md`](higgsfield-re-checkpoint.md). The generic, site-agnostic method is
[`reverse-engineering.md`](reverse-engineering.md). Skill: `continue-reverse-engineering`.

This file summarizes and links. The evidence lives in `docs/` (index: [`docs/README.md`](../../docs/README.md)).

---

## 1. Ground rules (non-negotiable)

| Rule | Detail |
|---|---|
| **GET only** | Never send POST/PUT/PATCH/DELETE to Higgsfield APIs. Never generate, upload, buy, like, comment, vote, follow, publish or claim. The only exception is the Clerk login flow (`python -m higgsfield_scraper login`), which signs in the user's own account. Server "quotes" (`dry_run`, `POST /job-sets/costs`, `/realtor-studio/quote`) are POSTs too: **not called** |
| **No bypass** | No captcha / DataDome / Cloudflare challenge / Clerk Protect evasion. A 403 with `geo.captcha-delivery.com` or an `x-dd-b` header means **stop** (`/jobs`, `/media`, `/v2/reference-elements/picker` are known DataDome paths) |
| **Whose data** | Public data, or the user's own login (Clerk session from `.env` / `runs/.auth/`). Never other people's credentials |
| **Personal data** | Usernames, avatars, socials only with `--with-profiles`; samples committed to git are redacted |
| **Secrets** | Never print or log tokens, cookies or JWTs (print lengths at most). Never read or echo `.env` values; use `TokenProvider.from_env()` |
| **Politeness** | ≈ 1 request/s, small page sizes when probing, stop on 429/403 |
| **No spoofing** | Country comes from the IP; don't fake `CF-IPCountry` etc. (tested: ignored anyway) |
| **Low RAM** | Bundles are ~10 MB / 580–750 chunks: `grep -o` with a bounded context, read one chunk at a time, never pretty-print a whole bundle or load all chunks in one Python process |
| **Windows** | `set PYTHONIOENCODING=utf-8` before running scripts; use `.venv\Scripts\python` |

## 2. Toolbox

| Tool | Use it for | Example |
|---|---|---|
| `scripts/re_check_changes.py` | Has the site changed since the checkpoint? (frontend build id, `__HF_FF` flags, `/job-sets/costs` version + job types vs `.claude/re-state.json`). Exit 0 unchanged / 1 changed / 2 fetch failed | `python scripts/re_check_changes.py` · `--save` to store a new checkpoint |
| `scripts/recon_probe.py` | GET every API path found in the JS without auth; classify 200/401/404/422/403 | `python scripts/recon_probe.py samples/higgsfield/inventory/js_call_paths.json` → `inventory/probe_results.jsonl` + `bodies/` |
| `scripts/clerk_login_probe.py` | Check that the Clerk login works and a JWT is accepted (never prints secrets) | `python scripts/clerk_login_probe.py --env-only` · `--use-cache` |
| `python -m higgsfield_scraper login` / `auth-check` | Sign in (email code on a new device), cache `__client`, check the session | `... login --code 123456`, `... auth-check` |
| `core.auth.TokenProvider` | Mint a fresh JWT (≈ 60 s life) inside a one-off probe script; **don't print it** | `tok = TokenProvider.from_env().get()` then `headers={"Authorization": f"Bearer {tok}"}` |
| Scrapers (`scrape <name>`) | Capture real responses into `runs/<ts>_.../raw` + `http/` (request, response, curl, HAR) | `python -m higgsfield_scraper scrape community --max-items 50 --with-raw-params` |
| `scrape pricing --logged-in-prices` | Fetch plans + costs a second time **with** the session and append the rows only logged-in users see (`visibility="logged_in"`; both costs versions in `meta.logged_in_prices`). The quickest logged-in vs anonymous price diff | `python -m higgsfield_scraper scrape pricing --sections all --logged-in-prices` |
| `scrape pricing --sections account` | Whitelisted snapshot of the account's wallet, subscription, auto top-up, free gens, generation seconds + packs, bundle status (never part of `all`) | `python -m higgsfield_scraper scrape pricing --sections account --label my-balance` |
| `scrape account` | The user's own snapshot; `--with-jobs` own jobs with the real charged `cost`; `--compare-estimate` estimator vs real charge (login required; see `docs/scrapers/account.md`) | `python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20` |
| `normalize` | Re-parse an old run offline after changing a parser | `python -m higgsfield_scraper normalize --run runs/<id>` |
| `diff` / `crosscheck` | Pricing changes between runs; `pricing.md` vs `ps_a3` | `python -m higgsfield_scraper diff` |
| `scripts/check_pricing_identity.py` | Commit gate: pricing output must stay byte-identical to the baseline | `python scripts/check_pricing_identity.py` |
| `scripts/gen_*.py` | Regenerate generated doc blocks (see [`docs/README.md`](../../docs/README.md) §8) | `gen_cost_tables.py --write docs/COST_FORMULAS.md`, `gen_model_catalog.py --write`, `gen_pricing_snapshot.py --write docs/PRICING.md`, `gen_endpoint_fields.py`, `gen_cli_tables.py` |
| `scripts/make_postman.py` | Regenerate the Postman collection after endpoint changes | `python scripts/make_postman.py` |
| `scrape projects --with-project-*` | Nested traversal of a project page with budgets: publication detail → root folder → sub-folders → assets (`items/v2`) → brief → comments → related; `--max-items` counts projects, `--max-submissions` caps entries per contest/tab, `--max-pages` caps item pages per folder and comment pages per thread | `python -m higgsfield_scraper scrape projects --what user-projects --users <handle> --max-items 1 --with-project-assets --with-project-brief` |
| `scrapers/projects/yjs.py`, `scrapers/blog/yjs.py` | Decode Yjs v1 updates/snapshots (pure Python): project briefs (`dam-editor-worker …/brief/{folder}/snapshot`, binary) and blog post bodies. Reuse them for any other Yjs/Lexical document | `projects/brief.py` renders the decoded Lexical tree to Markdown |
| `export` | Turn runs into tree / HF / WebDataset / JSONL folders to inspect a capture quickly (read-only, offline) | `python -m higgsfield_scraper export --run runs/<id> --dry-run` |
| `scripts/merge_generations.py` | Count and dedupe generations across scrapers/runs; keys `job:<job id>`, `pub:<publication id>` (single-generation publications only), `media:<uuid>` (last UUID of an OUTPUT URL; input CDN never a key), `static:<path>`; the same keys drive `export`'s generation-level dedup (`export/keys.py` loads the script) | `python scripts/merge_generations.py --latest community,catalog,projects,site,showcase` · `--compare old/generations_index.json` |
| curl / `grep -o` | Fast one-off GETs and bundle searches | see §3 C |

## 3. The process

Each stage: **input → commands → output → where it is documented.**

### A. Freshness check (always first)

```bash
set PYTHONIOENCODING=utf-8
.venv\Scripts\python scripts\re_check_changes.py
```

| Change reported | What it means | Do |
|---|---|---|
| none (exit 0) | Same build, same price table | Pick a backlog item in the checkpoint |
| **frontend build** `old → new` | New deploy; chunk file names change, new base models / flags / schemas possible | Re-crawl the chunks (stage C) into `samples/higgsfield/js2/` (or a new folder per build), re-run the grep recipes, check `defineJob` types and the route table against `/job-sets/costs`, re-verify chunk names cited in `MODEL_LOADING.md` / `PRODUCTS.md` / `COST_FORMULAS.md`; `python scripts/gen_model_catalog.py --write` |
| **costs version** changed | Some price, discount or formula row changed | `scrape --sections all` → `diff`; regenerate `COST_FORMULAS.md` tables (rate + `--variations`), `PRODUCTS.md` catalog, `PRICING.md` snapshot. New cost shape → `parsers/costs.py` + test |
| **NEW job_set_types** | A model is being priced before (or without) launch, e.g. `scene_switch` | Search the bundle for `type:\`<name>\`` and a `/jobs/v2/<name>` route; document in `PRODUCTS.md` §5 (costs-only) and `COST_FORMULAS.md`; check the parser handled its shape |
| **REMOVED job_set_types** | A model was retired or hidden | Check the retired set (`Vx`) and the gating table; note it in `PRODUCTS.md` §5 |
| **flags** changed | A gated model / feature flipped | Map `f_<hash>` to the model via the gating table (`MODEL_LOADING.md` §2.1). An **empty** flag list is not a change (anonymous pages sometimes serve `{}`) |
| exit 2 | Network error, DataDome, or the page/JSON shape changed | Retry once later; if it persists, inspect the HTML manually (don't hammer) |

After the work is done and documented: `re_check_changes.py --save` and add a row to the checkpoint changelog.

### B. Map the surface

| Source | How | Output |
|---|---|---|
| robots.txt + 12 sitemaps | `curl -s https://higgsfield.ai/robots.txt`; sitemaps listed there | `samples/higgsfield/sitemaps/`, 1,384 URLs |
| Frontend routes (589) | Grep the TanStack route tree in the bundle | `samples/higgsfield/inventory/routes.json` |
| API call paths (728) | Grep path literals passed to the api helpers | `samples/higgsfield/inventory/js_call_paths.json` |
| Public vs login | `python scripts/recon_probe.py` (GET, no auth, mutation words skipped) | `probe_results.jsonl`; summary in [`HIGGSFIELD_DATA_INVENTORY.md`](../../docs/HIGGSFIELD_DATA_INVENTORY.md) §1, §5–§8 and appendices A/B |

Caveat: the gateway checks auth **before** routing, so a 401 does not prove the path exists. Only a call with a
real session tells 404 from a real endpoint (pitfall 9).

### C. JS bundle analysis

**Getting the chunks.** Fetch a tool page (`/ai/video`, `/ai/image`, `/apps/...`, `/edit`, `/property-studio`) →
collect `https://assets.higgsfield.ai/tanstack/assets/<build>-<hash>.js` from `<link rel="modulepreload">` and
`<script>` → in each chunk follow static `import` and dynamic `import("./<build>-<hash>.js")` strings → repeat until no new
names. Build `548e0f3a` gave 580 chunks from the tool pages (746 files today in `js2/`).

**Storage (gitignored):** `samples/higgsfield/js2/` (chunks of build `548e0f3a`) and `js2/_pages/` (the tool-page
HTML, e.g. `ai_video.html`); `samples/higgsfield/js/` (old build `8a801a77`). The l10n message catalog
(`window.__HF_I18N__` → `l10n.higgsfield.ai/l10n/production/r/<hash>/<locale>.<hash>.json`) maps the UI's message ids
to English text: use it to name features found by id.

**Grep recipes that worked** (run from `samples/higgsfield/js2/`):

```bash
grep -o 'type:`[a-z0-9_]*`,output:`[a-z]*`' *.js | sort -u          # defineJob registry (~100 job types)
grep -o '[a-z0-9_]*:`v2/[a-z0-9_]*`' *.js | sort -u                  # adapter route table -> POST /jobs/v2/<type>
grep -o 'window.__HF_FF = [^<]*' _pages/ai_video.html                # flags served to this request
grep -o '[a-z0-9_]*:{flag:[^}]*pricedAs[^}]*}' *.js                  # gating: flag / fallback / pricedAs
grep -o 'e(`video-featured-model-ids-[^`]*`' *.js                    # named modules survive minification
grep -o 'e(`[a-z0-9-]*-[A-Za-z0-9_-]\{8\}`' *.js | sort -u           # ALL module names: reveal each chunk's purpose
grep -o 'fnf-api-gw.higgsfield.ai/[a-z-]*' *.js | sort | uniq -c    # gateway sub-bases (/fnf, /fnf-cms-api, ...)
grep -o 'cms.higgsfield.ai[^`"]*' *.js | sort -u                     # CMS base helper
grep -o 'queryKey:\[`[^`]*`' *.js | sort | uniq -c                    # react-query keys = data the UI loads
grep -o 'fnf-notification[^`]*`' *.js                                # SSE stream base
grep -o 'subscribe(`job:status_changed`' *.js                        # SSE event names
grep -o '.\{200\}z.object({.\{400\}' <chunk>.js                       # zod schemas (request/response shapes)
```

Then read **one chunk at a time** with a bounded window around a hit (`grep -o '.\{0,600\}<needle>.\{0,600\}'`).
Resolve minified constants by grepping their definition (`w_={T1:`ps_a3`,...}`). Important: an API path is only
meaningful together with its **helper** (base URL + prefix); the catalog paths were first tried on the wrong base
(`/fnf`) and 404'd. Find the helper that wraps each path before probing it.

### D. Replay minimal GETs

- **Public:** `curl -s -A "Mozilla/5.0" -H "Accept: application/json" "https://fnf-api-gw.higgsfield.ai/fnf/<path>"`.
  Strip headers until it breaks; record the minimal set, page-size maxima (422 above the max), cursor style and
  stop condition. Save 1–3 small, redacted samples under `samples/higgsfield/<topic>/` (own folder per task).
- **Login:** in a throwaway script, `from higgsfield_scraper.core.auth import TokenProvider;
  tok = TokenProvider.from_env().get()`; send `Authorization: Bearer <tok>`; print status + byte count + top-level
  keys only. Compare bytes with and without the token: identical = actually public.
- **Record headers** the web client sends (from JS, add only when needed): `hf-workspace-id` (team workspace),
  `hf-access-realm` (JSON realm for shared folders on `/jobs/`, `/job-sets/`, `/assets/`, `/favourites/`),
  `hf-surface` (uploads), `Accept-Language`, analytics `hf-platform`/`hf-device`.
- **DataDome signal:** response header `x-dd-b` or a `geo.captcha-delivery.com` body → stop, mark the path ⛔.
- **Clerk FAPI** is at `https://higgsfield.ai/_clerk` (`?__clerk_api_version=...&_clerk_js_version=...`,
  `Origin: https://higgsfield.ai`). Only the project's login command uses it.

### E. Document

| Finding | Goes into |
|---|---|
| Discovery log, method, evidence (dated round) | [`docs/REVERSE_ENGINEERING.md`](../../docs/REVERSE_ENGINEERING.md) (new § per round) |
| New route / API path / public-vs-login status | [`docs/HIGGSFIELD_DATA_INVENTORY.md`](../../docs/HIGGSFIELD_DATA_INVENTORY.md) |
| Pricing endpoint fields | [`docs/ENDPOINTS.md`](../../docs/ENDPOINTS.md), [`docs/PRICING.md`](../../docs/PRICING.md), regenerate `ENDPOINT_FIELDS.md` |
| Credit formula | [`docs/COST_FORMULAS.md`](../../docs/COST_FORMULAS.md) (+ §8 if the estimator disagrees) |
| Model → provider → endpoint | [`docs/PRODUCTS.md`](../../docs/PRODUCTS.md) |
| Model registry, gating, flags, params | [`docs/MODEL_LOADING.md`](../../docs/MODEL_LOADING.md) |
| Job / storage / lifecycle | [`docs/JOBS_AND_STORAGE.md`](../../docs/JOBS_AND_STORAGE.md) |
| A product deep dive | `docs/products/<PRODUCT>.md` (TL;DR, features, data model, endpoints, public vs login, confidence) |
| A scraper's endpoints and fields | `docs/scrapers/<name>.md` |
| Status, open questions, backlog | [`higgsfield-re-checkpoint.md`](higgsfield-re-checkpoint.md) |

Every claim gets a **confidence label** ([`docs/README.md`](../../docs/README.md) §9): **verified live** (seen in a
real response; say whether logged in) · **from JS, not called** · **inferred**. Keep "unknowns" lists. When a claim is
corrected, grep **all** docs for the old wording (pitfall 10). New docs go into `docs/README.md`.

### F. Turn it into a scraper

Follow [`docs/ADDING_A_SCRAPER.md`](../../docs/ADDING_A_SCRAPER.md) and the `scrape-spider` skill: package
`higgsfield_scraper/scrapers/<name>/` (endpoints, options, pure parsers, strict pydantic schemas, dataset, spider),
raw envelopes in `tests/fixtures/<name>/`, `tests/test_<name>.py` (incl. the CSV-completeness test),
`docs/scrapers/<name>.md`, CLI.md tables (`gen_cli_tables.py`), Postman (`make_postman.py`). Login-only endpoints use
`auth="required"`. Verify with a capped live crawl (`--max-items 20 --max-pages 1`).

### G. Verify and commit gates

1. `git status --short` and `git diff --name-status HEAD`: no unintended **D**eletions, no files of another agent.
2. `.venv\Scripts\python -m pytest -q` passes.
3. `.venv\Scripts\python scripts\check_pricing_identity.py` → exit 0 (31/31 identical to the baseline).
4. Secrets / personal-data scan of the staged diff: `git diff --cached | grep -iE 'eyJ[a-zA-Z0-9_-]{20,}|__client|sess_|password|@gmail|user_[A-Za-z0-9]{27}'`
   plus any real usernames from samples. Nothing from `.env` and `runs/.auth/`.
5. Stage **explicit paths** (`git add <file> ...`), never `git add -A` / `.` (parallel agents share the tree).
6. New or renamed docs listed in [`docs/README.md`](../../docs/README.md); generated blocks regenerated, not hand-edited.
7. Commit only when the user asks.

**Baseline versioning** (when an intended change alters pricing output):
1. Run the identity check and confirm **every** differing line is explained by the intended change (nothing else).
2. Create the new baseline: `python -m higgsfield_scraper normalize --run <SOURCE run in the script> --label pricing-baseline-vN` with the
   script's `NORMALIZE_ARGS`, so the output lands in `runs/<ts>_pricing-baseline-vN/`.
3. Update `BASELINE` and the version comment in `scripts/check_pricing_identity.py`, the baseline path in
   `CLAUDE.md` ("Before every commit"), the checkpoint header, and the user's memory notes if they keep one.
4. Re-run the check: exit 0 against vN.

## 4. Higgsfield facts cheat-sheet

| Fact | Value / note | Source |
|---|---|---|
| Main API | `https://fnf-api-gw.higgsfield.ai/fnf` (FastAPI; 422 lists enums) | REVERSE_ENGINEERING §3 |
| Other gateway bases | `/fnf-cms-api` (katana, chain presets, restyle presets, notices, applications), `/fnf-community` (community posts, comments incl. `/entities/{type}/{id}/comments`, shots `/generations/feed`, `/feed`, rooms, suggestions, related), `/fnf-series` (original series), `/fnf-academy` (courses), `/fnf-score` (season), `/fnf-notification/notifications/stream` (SSE); 14 prefixes in all | `docs/scrapers/catalog.md`, `community.md`, LOGIN_COVERAGE §1, JOBS_AND_STORAGE §3.5 |
| Gateway auth rule | `/fnf/<anything>` → 401 without a token (auth before routing), 404 for unknown paths with one | REVERSE_ENGINEERING §16 |
| Logged-in deltas | ps_a3 plans 15 vs 14 (+ `lite` annual); costs 88 vs 87 rows (+ `magi_2`), `version` `9048fa70…` vs `0cee3218…` | LOGIN_COVERAGE §1 |
| CMS | `https://cms.higgsfield.ai{path}?lang=` (soul styles, model motions, mixed-media, marketing studio, videoshop examples) | `docs/scrapers/catalog.md` |
| Pricing config | `https://pricing.higgsfield.ai/v2/pricing-config` (rest of the host is behind Cloudflare Access) | PRICING §2.5 |
| Canvas | `https://canvas-worker.higgsfield.ai/api/*`; `/api/templates` public; the node graph only over a login WebSocket (`/connect?ticket=`, ticket from `/auth`) | JOBS_AND_STORAGE §6.3, `scrapers/showcase.md` §9 |
| Project assets / briefs | `/fnf/folders/{id}`, `/children`, `/items/v2` (public); briefs = Yjs snapshot on `dam-editor-worker.higgsfield.ai` | `scrapers/projects.md`, REVERSE_ENGINEERING §17 |
| CDNs | uploads `d2ol7oe51mr4n9.cloudfront.net`, outputs `d8j0ntlcm91z4.cloudfront.net` (S3, unsigned, 1-year immutable), derivatives/HLS `cdn.higgsfield.ai`; `static.`/`assets.`/`static-public-media.higgsfield.ai` | JOBS_AND_STORAGE §4 |
| Frontend | TanStack Start (React SSR), chunks `assets.higgsfield.ai/tanstack/assets/<build8>-<hash>.js`; loader data in `$_TSR` (seroval) | REVERSE_ENGINEERING §3, §13–14 |
| Login | Clerk, FAPI proxied at `higgsfield.ai/_clerk`; JWT ≈ 60 s, `__client` cookie ≤ 400 days; new device → emailed code | REVERSE_ENGINEERING §13 |
| Money | Plan prices in **integer cents**; top-up `amount`/`credits` ÷ 100 in JS; viral/app "credit units" ÷ 100 (`ceil(units/100)`); all USD | PRICING §2–3, §10; COST_FORMULAS §1 |
| Plan sets | 25 `plan_set_key`s (422 on a bogus key lists them); `ps_a3` = US = `pricing.md` | PRICING §4 |
| Country | From the IP only; headers/query overrides ignored | PRICING §4.3 |
| Models | No public "models" endpoint: registry hard-coded in JS + `__HF_FF` flags + `pricedAs` presence in `/job-sets/costs` | MODEL_LOADING §2 |
| Costs | `/job-sets/costs` = 87 job types, many shapes, `version` hash changes on any price change | COST_FORMULAS, ENDPOINTS |
| Ids | All UUIDs except Clerk user ids (`user_` + 27 chars). **Job id = asset id** = id in result filenames; publication id is different | JOBS_AND_STORAGE §2 |
| Job tracking | SSE `job:status_changed` + `POST /jobs/status-batch` fallback (5 s / 30 s) | JOBS_AND_STORAGE §3.5 |
| Bot protection | DataDome (`dd.higgsfield.ai`, `x-dd-b`); 3 API paths blocked | DATA_INVENTORY §6 |
| Written content | Sanity CMS via SSR loader state; post bodies are Yjs v1 docs | REVERSE_ENGINEERING §13 |

## 5. Lessons learned / pitfalls (all happened here)

| # | What went wrong | Fix / rule |
|---|---|---|
| 1 | An unanchored `.gitignore` rule `schemas/` silently dropped the `higgsfield_scraper/schemas/` package from git | Root-anchor output folders (`/schemas/`, `/runs/`, `/data/`); check `git status` for missing package files |
| 2 | Parallel agents wrote to the same `samples/` folder and overwrote committed files | One sample folder per task/agent; stage explicit paths; check `git diff --name-status HEAD` before committing |
| 3 | The pricing spider only used `--token`, so login-only endpoints got 401 while a login was cached; `--sections all` ignored the cached login | Use the shared `TokenProvider.from_env()` everywhere (fixed in `86d5613`); test with a cached session, not only `--token` |
| 4 | Scrapy `HttpError` subclasses `IgnoreRequest`, so 5xx errors were reported as "no login" | Check `HttpError` **before** `IgnoreRequest` in errbacks and log the real status (e.g. `credit-price` 500) |
| 5 | Scrapy items silently dropped fields not declared in the pydantic schema, even with `extra="allow"` (credit packages lost `discount`, `features`, …) | Declare every live-observed field in the schema; compare raw vs output key sets |
| 6 | `any(path.glob(...))` treated as "folder is non-empty" | `glob` returns a generator; materialize or use `next(iter(...), None)` deliberately and test both cases |
| 7 | A script without argparse took `-h` as a run dir and overwrote `ENDPOINT_FIELDS.md` with nothing | Every script uses argparse (handles `-h`) and refuses to write empty output (fixed in `e7ea6bb`) |
| 8 | The identity-check mask regex hard-coded a date → false differences on another day | Mask with generic patterns (run id, ISO timestamps), never literal dates |
| 9 | Login-only paths inferred from JS (`/fnf/soul-styles`, `/fnf/publications/{id}/comments`) returned **404 with a valid login** | Find the real base helper in JS (CMS / `fnf-cms-api` / `fnf-community`), verify live with a session, mark untested paths as "from JS, not called" |
| 10 | `MODEL_LOADING.md` said "no websocket/push"; the SSE stream exists | When a claim is corrected, grep all docs for it and fix every copy |
| 11 | A loop variable named `label` overwrote the outer `label`, corrupting `meta.label` (fixed in `0dd152d`, baseline v2) | Don't reuse outer names in loops; the identity check catches this class of bug |
| 12 | `window.__HF_FF` came back `{}` for an anonymous request (an earlier crawl got 23 flags) | Treat an empty flag list as "unknown", not "all off"; `re_check_changes.py` ignores it |
| 13 | Windows cp1252 console crashed on `→`/`✅`; mintty (Git Bash) can't run the interactive menu | `PYTHONIOENCODING=utf-8`; run `menu` in PowerShell / Windows Terminal |
| 14 | The first inventory marked many paths "login-only" because they answered 401 under `/fnf/`. The fnf gateway answers 401 for **any** unknown path without a token (404 with one), so 401 ≠ "login-only" | Find the base helper in the JS (`Ixe` → `cms.higgsfield.ai`, `_V` → `/fnf-cms-api`, `ho` → `/fnf-series`, …) and probe the path on that base, anonymous **and** logged in |
| 15 | In this Scrapy version (2.19), a spider's `custom_settings` dict **replaces** the project's `DOWNLOADER_MIDDLEWARES` dict, which would silently drop auth, the HTTP archive and the access log | Merge in a `update_settings` classmethod (`dict(settings.getdict(...))` + the new entry, `priority="spider"`), as `AccountSpider` does |
| 16 | Cloudflare challenged `/jobs/accessible` (`403 cf-mitigated: challenge`) for the Scrapy crawl while a single plain request passed | Record it (`meta.limits_hit`, run `partial`) and stop; never try to evade a challenge (no header/TLS tricks, no browser automation to pass it) |
| 17 | Logged-in responses of "public" endpoints contained extra rows (`lite` plan, `magi_2` cost row, another costs `version`) | Before assuming a session changes nothing, compare logged-in vs anonymous bodies (row counts, ids, `version`), re-check anon → auth → anon |
| 18 | Real Clerk user ids (`user_…`) were hidden inside CDN media URL paths of samples and fixtures, not only in `user_id` fields | Redaction must scan URL paths and every string value, not just known keys; grep samples for `user_[A-Za-z0-9]{27}` before committing. (In scraper **output** the CDN URLs are kept unredacted: owner decision 2026-11-26) |
| 19 | The docs said "gallery generations have no comments" because `fnf-community /publications/{gallery id}/comments` is always empty; they do have comments on `/entities/generation_publication/{id}/comments` | Before concluding "no data", check the CMS paths (`cms.higgsfield.ai`, `/fnf-cms-api`) and the `/entities/{type}/{id}/…` pattern for every entity type the UI shows (generation, project, blog) |
| 20 | TanStack SSR server functions (`/_serverFn/<hash>`, e.g. effect-sample pages after the first) have a **per-build hash** | Don't hard-code them in a scraper; prefer the SSR loader state of the page or a real JSON endpoint, and record what the first page reports (`samples_total`) |
| 21 | Nested traversals (contest → entries → project → folders → assets → comments) can explode in requests and media size (1.5 GB `.mov` watermarks) | Give every level a budget (`--max-items`, `--max-submissions`, `--max-pages` per folder/thread, `--max-media-mb`), count only top-level items against `--max-items`, warn on API counts that exceed what a listing returns |
| 22 | The same generation appears in several scrapers (community, showcase explore, effect samples, project assets) and inputs are shared between generations | Dedupe with stable keys (`job:`, `media:` of OUTPUT URLs only, `pub:` only for single-generation publications, `asset:`), never with input URLs; one key logic shared by `merge_generations.py` and `export` |
| 23 | Faked ids in fixtures must not look real (a same-length random `user_…` id can be mistaken for a leak, or collide with one) | Prefix fakes clearly (`user_Fake…`; the fixtures use `user_fake…` / `user_REDACTED…`) and keep the same length when a parser checks it, also inside binary fixtures such as Yjs briefs |
