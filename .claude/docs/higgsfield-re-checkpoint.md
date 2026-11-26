# Higgsfield reverse-engineering checkpoint

**Where we are.** Read this after running `python scripts/re_check_changes.py`. **How** to do the work:
[`higgsfield-re-playbook.md`](higgsfield-re-playbook.md). Skill: `continue-reverse-engineering`.

| | |
|---|---|
| Last updated | **2026-11-26** |
| Machine state file | [`.claude/re-state.json`](../re-state.json) (written by `re_check_changes.py --save`) |
| Frontend build | `548e0f3a` (buildId `45776133266-1-production`, commit `7b1a78f4…`); previous `8a801a77` (2026-11-25) |
| `/job-sets/costs` version | `0cee321863e207292a9facc5db75a99be4f292b03865ace9c025bd229f9b8f77` (anonymous); logged in `9048fa70…` (88 types, + `magi_2`) |
| Job set types priced | **87** (incl. `scene_switch`, priced but no frontend code) |
| Public `__HF_FF` flags | **empty** for the anonymous request on 2026-11-26 (an earlier crawl of `/ai/video` got 23; `f_24c5dcf4` Seedance 2.5 Flash on, `f_3a0922bf` Kling 4.0 Flash on, `f_6a87092e` Wan 4.0 off) |
| Pricing baseline | `runs/20261126-100141_pricing-baseline-v3` (31 files; `scripts/check_pricing_identity.py`) |
| Tests | **692 passed, 1 skipped** (`.venv\Scripts\python -m pytest -q`, 2026-11-26, after commit `d994459`) |
| Scrapers | **10**: `pricing`, `community`, `catalog`, `projects`, `blog`, `site`, `showcase`, `studios` (opt-in), `models` (opt-in), `account` (opt-in, login required); plus `export` and `scripts/merge_generations.py` |
| Content coverage | [`docs/CONTENT_MAP.md`](../../docs/CONTENT_MAP.md): 105 rows, **82 covered, 0 GAP, 0 in progress**, 23 not scraped by design; [`docs/COMPLETENESS.md`](../../docs/COMPLETENESS.md) §11: fixes #1–#17 done, #18 open |

---

## 1. Status per area

| Area | Status | Scraper | Docs | Last verified |
|---|---|---|---|---|
| Pricing (plans, compare, benefits, costs, marketing, `pricing.md`) | done | `pricing` | [`PRICING.md`](../../docs/PRICING.md), [`ENDPOINTS.md`](../../docs/ENDPOINTS.md), [`ENDPOINT_FIELDS.md`](../../docs/ENDPOINT_FIELDS.md) | 2026-11-26 |
| Login-only pricing (packages, unlim-catalog, adjustable credits, credit-price) | done for a personal account; `credit-price` 500 without a team | `pricing --sections all,auth` | [`PRICING.md`](../../docs/PRICING.md) §10 | 2026-11-26 |
| Logged-in price rows (`lite` annual plan, `magi_2` cost row) | done (opt-in; anonymous rows unchanged, extra rows `visibility="logged_in"`, both costs versions in `meta.logged_in_prices`) | `pricing --logged-in-prices` | [`PRICING.md`](../../docs/PRICING.md) §10, [`CLI.md`](../../CLI.md) | 2026-11-26 |
| Account pricing state (wallet, subscription, auto top-up, free gens, generation seconds + packs, bundle status) | done (opt-in, whitelisted, never in `all`) | `pricing --sections account` | [`CLI.md`](../../CLI.md), [`ENDPOINTS.md`](../../docs/ENDPOINTS.md) | 2026-11-26 |
| Account scraper (snapshot, own jobs with real `cost`, estimate vs actual) | done; `/jobs/accessible` Cloudflare-challenged for the crawler (recorded, not evaded), so `--compare-estimate` not run live | `account` | [`scrapers/account.md`](../../docs/scrapers/account.md) | 2026-11-26 |
| Login audit (what a session unlocks) | **done** | — | [`LOGIN_COVERAGE.md`](../../docs/LOGIN_COVERAGE.md), [`REVERSE_ENGINEERING.md`](../../docs/REVERSE_ENGINEERING.md) §16 | 2026-11-26 |
| Community generations | done | `community` | [`scrapers/community.md`](../../docs/scrapers/community.md), [`cost-estimate.md`](../../docs/scrapers/cost-estimate.md) | 2026-11-26 |
| Community comments | done (public on `/fnf-community`): Community posts (`/publications/{id}/comments`) and, with the opt-in feeds, shots / projects / blog posts (`/entities/{type}/{id}/comments`). Gallery generations **do** have comments (correction of the earlier note) | `community --with-comments` (+ `--feeds shots,posts,feed`) | `scrapers/community.md`, [`COMMUNITY_COVERAGE.md`](../../docs/COMMUNITY_COVERAGE.md) | 2026-11-26 |
| Community pages (Shots, Posts, Feed, Creators, Talents) | done (opt-in, public, never in `--feeds all`; requests always anonymous); creators/talents emit every work in full (`community_creator_work`), shots the model facet | `community --feeds shots,posts,feed,creators,talents` | [`COMMUNITY_COVERAGE.md`](../../docs/COMMUNITY_COVERAGE.md) | 2026-11-26 |
| Community galleries / templates (music cards, Seedance job showcase, collections, explore cards, Feed hashtag categories) | done (opt-in, not in `--feeds all`; job showcase read from the page's SSR state because the API is Cloudflare-challenged for the crawler) | `community --feeds music-cards,job-showcase,collections,explore-cards,feed-categories` | `COMMUNITY_COVERAGE.md`, `scrapers/community.md` | 2026-11-26 |
| Community rooms (list, works, discussions) | done (opt-in, public; no public chat stream) | `site --what room-list` / `room-content` | `COMMUNITY_COVERAGE.md`, [`scrapers/site.md`](../../docs/scrapers/site.md) | 2026-11-26 |
| Engagement audit (likes, views, comments, votes; anon vs login; old vs new) | **done**; the apps-marketplace gap is closed by `studios` | — | [`ENGAGEMENT.md`](../../docs/ENGAGEMENT.md) | 2026-11-26 |
| Catalogs (public) | done | `catalog` | [`scrapers/catalog.md`](../../docs/scrapers/catalog.md) | 2026-11-25 |
| Catalogs opt-in `login` group | done (public on CMS / `fnf-cms-api`; color + camera need a login) | `catalog --kinds login` | `scrapers/catalog.md` | 2026-11-26 |
| Catalog kinds `chain_preset` (credit prices), `notice`, `restyle_preset` | done (opt-in, public; `--include-hidden`, `--with-profiles`) | `catalog --kinds chain_preset,notice,restyle_preset` | `scrapers/catalog.md` | 2026-11-26 |
| Catalog `outfit_character`; katana author redaction in archives | done (name-only kind, not in `--kinds all`; `CatalogPrivacyMiddleware`) | `catalog --kinds outfit_character` | `scrapers/catalog.md` | 2026-11-26 |
| Projects, series, contests | done | `projects` | [`scrapers/projects.md`](../../docs/scrapers/projects.md) | 2026-11-25 |
| Projects nested data (folders, assets with prompt/model/params/media, brief, stats + stack, comments, related; contests by slug, contest tabs, user projects) | done (opt-in, public; nested requests always anonymous) | `projects --with-project-assets/-brief/-stats/-comments/-related`, `--contest`, `--contest-tabs`, `--users` | [`scrapers/projects.md`](../../docs/scrapers/projects.md#nested-data-model-opt-in-2026-11-26), REVERSE_ENGINEERING §17 | 2026-11-26 |
| Trending projects, contest participation counters, user works / stats | done (opt-in, by name only; user works only for users already found in a run, pseudonymous) | `projects --what trending,contest-participation`, `--with-user-works` | `scrapers/projects.md`, REVERSE_ENGINEERING §18 | 2026-11-26 |
| Showcase / examples (Canvas templates, Editing Room, Property Studio, video explore, effect samples, API models, Cinema controls, CMS showcases) | done (public; `season` login-only, opt-in) | `showcase` | [`scrapers/showcase.md`](../../docs/scrapers/showcase.md) | 2026-11-26 |
| Shorts Studio reels presets + comments, effect presets, CMS main feed | done (opt-in; `main_feed` by name only, not in `--what all`) | `showcase --what reels_presets,reels_comments,main_feed` | `scrapers/showcase.md` §10–11 | 2026-11-26 |
| Studios & marketplaces (apps, games, skills, AI employees, Playable Ads, AI Influencer options, per-studio galleries + comments) | done (opt-in scraper, all public; studio workspaces are login-only personal data, not collected) | `studios` | [`scrapers/studios.md`](../../docs/scrapers/studios.md) | 2026-11-26 |
| Export (tree / Hugging Face / WebDataset / JSONL) | done (read-only on runs, deduped, idempotent) | `export` | [`EXPORT.md`](../../docs/EXPORT.md) | 2026-11-26 |
| Cross-run dedupe / counting of generations | done (`job:` / `pub:` / `media:` / `static:` keys, `--compare` deltas) | `scripts/merge_generations.py` | `scrapers/showcase.md` §8, `ENGAGEMENT.md` §14 | 2026-11-26 |
| Original series (public `fnf-series`) | done (opt-in; the default run keeps the legacy login-only path) | `projects --what series --public-series` | `scrapers/projects.md` | 2026-11-26 |
| Blog, help centers, case studies, changelog, talent posts | done | `blog` | [`scrapers/blog.md`](../../docs/scrapers/blog.md) | 2026-11-25 |
| Site pages (apps, academy, MCP, series, landings, promos) | done | `site` | [`scrapers/site.md`](../../docs/scrapers/site.md) | 2026-11-25 |
| Academy JSON API (`fnf-academy`: categories, courses with `free_generations`, lessons with MDX) | done (opt-in, not in `--what all`) | `site --what academy-api` | `scrapers/site.md` | 2026-11-26 |
| Model loading (registry, flags, `defineJob`, gating) | documented; **live scraper** (registry, routes, gating, plans, menus + costs + shots facet; coverage complete with default options) | `models` | [`MODEL_LOADING.md`](../../docs/MODEL_LOADING.md), [`scrapers/models.md`](../../docs/scrapers/models.md) | 2026-11-26 (build `548e0f3a`) |
| Cross-scraper identity | done: `creator_uid_key` = `core/privacy.py:creator_uid_key()` = `make_id("creator", id)` on every record with an author | all | `COMPLETENESS.md` #10 | 2026-11-26 |
| Content map / completeness audits | done: every content source classified; every GAP and in-progress row resolved; fixes #1–#17 done | `scripts/content_map.py`, `scripts/completeness_audit.py` | [`CONTENT_MAP.md`](../../docs/CONTENT_MAP.md), [`COMPLETENESS.md`](../../docs/COMPLETENESS.md) | 2026-11-26 |
| Products → models → providers | documented | — | [`PRODUCTS.md`](../../docs/PRODUCTS.md) | 2026-11-26 |
| Cost formulas | documented; estimator has 19 known differences | `estimate/` (partial) | [`COST_FORMULAS.md`](../../docs/COST_FORMULAS.md) | 2026-11-26 |
| Jobs, ids, storage, lifecycle | documented | — | [`JOBS_AND_STORAGE.md`](../../docs/JOBS_AND_STORAGE.md) | 2026-11-26 |
| Editing Room (videoshop) | documented | — | [`products/EDITING_ROOM.md`](../../docs/products/EDITING_ROOM.md) | 2026-11-26 |
| Property Studio (realtor studio) | documented | — | [`products/PROPERTY_STUDIO.md`](../../docs/products/PROPERTY_STUDIO.md) | 2026-11-26 |
| Login (Clerk) | done | `login`, `auth-check`, `core/auth.py` | [`REVERSE_ENGINEERING.md`](../../docs/REVERSE_ENGINEERING.md) §13 | 2026-11-26 |
| Site inventory (routes, API paths, probes) | done for build `45572506390` (2026-11-25) | `scripts/recon_probe.py` | [`HIGGSFIELD_DATA_INVENTORY.md`](../../docs/HIGGSFIELD_DATA_INVENTORY.md) | 2026-11-25 |

**DONE (2026-11-26, committed):** the catalog "login" group and community comments. With a valid login, the paths
guessed from the JS (`fnf/soul-styles`, `fnf/<model>-motions`, `fnf/publications/{id}/comments`, …) returned **404**.
The real paths (documented in `docs/scrapers/catalog.md` and `community.md`) live on other bases: CMS `https://cms.higgsfield.ai{path}?lang=`, `fnf-api-gw…/fnf-cms-api{path}`
(katana), and `fnf-api-gw…/fnf-community` (posts + comments). Most of them turn out to be **public**. Only
`/color-presets` and `/camera-settings` really need a session. `HIGGSFIELD_DATA_INVENTORY.md` §5, `MODEL_LOADING.md`
§6–§8 and `REVERSE_ENGINEERING.md` §16 were updated after the login audit (`LOGIN_COVERAGE.md` §4 corrections).

## 2. Key findings

1. Prices are not in the HTML; 5 public JSON endpoints + 4 login-only give the full pricing picture. → [REVERSE_ENGINEERING §1](../../docs/REVERSE_ENGINEERING.md#1-executive-summary)
2. 25 `plan_set_key` price lists; `ps_a3` = US = `pricing.md`; the 422 on a bogus key lists them all. → [PRICING §4](../../docs/PRICING.md#4-plan-sets-25-price-lists-and-geo-pricing)
3. Country comes from the IP and can't be overridden; everything is USD. → [PRICING §4.3](../../docs/PRICING.md#43-country-detection-why-it-cant-be-overridden)
4. Plan money is integer cents; `percent_off` is a label, not the formula; `discount.duration` drives renewal. → [PRICING §3](../../docs/PRICING.md#3-plan-pricing-math-with-worked-examples)
5. `/job-sets/costs`: 87 job types, many shapes, `version` hash changes on every price change. → [ENDPOINTS.md](../../docs/ENDPOINTS.md), [COST_FORMULAS §3](../../docs/COST_FORMULAS.md#3-pricing-primitives)
6. Cost = live table × formula in JS (Seedance: `ceil(duration × cps) × batch`; edit clamps 4–30 s). → [COST_FORMULAS §1](../../docs/COST_FORMULAS.md#1-tldr-the-master-equations)
7. Viral presets and apps price in credit units ÷ 100 (`ceil`). → [COST_FORMULAS §4.14](../../docs/COST_FORMULAS.md#414-viral-hub-presets-apps-mixed-media)
8. Credit top-ups: 100–4,000 credits, $6.25–$210.53 (US, 2026-11-26), 90-day expiry; 12 adjustable-credit tiers. → [PRICING §10](../../docs/PRICING.md#10-login-only-pricing)
9. No public "models" endpoint: the registry is hard-coded in JS and filtered by `__HF_FF` flags, `pricedAs` presence in costs, a retired set and plan tiers. → [MODEL_LOADING §2.1](../../docs/MODEL_LOADING.md#21-it-is-hard-coded-then-filtered-at-runtime)
10. ~100 job types declared with `defineJob({type, input, validate, toProvider, fromProvider, credits})`, shared by the tools, Canvas and "recreate". → [MODEL_LOADING §3](../../docs/MODEL_LOADING.md#3-per-model-parameter-schema-the-definejob-registry)
11. A new base model needs a deploy; prices, flags, promos and CMS catalogs change without one. → [MODEL_LOADING §7](../../docs/MODEL_LOADING.md#7-the-dynamic-parts)
12. `scene_switch` is priced in `/job-sets/costs` with no frontend code: costs can lead launches. → [MODEL_LOADING §1](../../docs/MODEL_LOADING.md#1-tldr)
13. Generation = `POST /jobs/v2/<type>` (or kebab routes, `/chains/*`, `/workflows`): known from JS only, never called. → [MODEL_LOADING §4.3](../../docs/MODEL_LOADING.md#43-request-from-js-not-called)
14. Product → provider map (ByteDance, Google, OpenAI, xAI, Alibaba, Kling, MiniMax, BFL, ElevenLabs, Topaz …); no third-party inference host visible in the client. → [PRODUCTS §2](../../docs/PRODUCTS.md#2-provider-map), [§6](../../docs/PRODUCTS.md#6-confidence-and-unknowns)
15. All ids are UUIDs except Clerk user ids; job id = asset id = id in the result filename; publication id differs. → [JOBS_AND_STORAGE §2](../../docs/JOBS_AND_STORAGE.md#2-identifiers)
16. Job tracking = SSE `job:status_changed` on `fnf-notification` + `/jobs/status-batch` fallback (5 s / 30 s). → [JOBS_AND_STORAGE §3.5](../../docs/JOBS_AND_STORAGE.md#35-tracking-sse-push-plus-batch-polling)
17. Results are public, unsigned, immutable S3/CloudFront objects; buckets can't be listed. → [JOBS_AND_STORAGE §4](../../docs/JOBS_AND_STORAGE.md#4-storage)
18. Canvas templates are public at `canvas-worker.higgsfield.ai/api/templates`; graphs sync over a WebSocket. → [JOBS_AND_STORAGE §6.3](../../docs/JOBS_AND_STORAGE.md#63-canvas-and-flow-canvas-workerhiggsfieldai)
19. 37 public JSON APIs, 1,384 sitemap pages, 589 routes, 728 API paths; 3 DataDome-blocked paths. → [DATA_INVENTORY §1](../../docs/HIGGSFIELD_DATA_INVENTORY.md#1-summary)
20. The gateway checks auth before routing: 401 doesn't prove a path exists. → [DATA_INVENTORY §5](../../docs/HIGGSFIELD_DATA_INVENTORY.md#5-needs-a-login--401-invalid-or-expired-token)
21. The "login-only" catalogs are on CMS / `fnf-cms-api` bases and public there; comments on `/fnf-community`. The `fnf` gateway answers 401 for *any* unknown path without a token and 404 with one. → [scrapers/catalog.md](../../docs/scrapers/catalog.md)
22. Community: page-size caps per feed, score vs timestamp cursors; `meta.cost` is provider token usage, not credits. → [REVERSE_ENGINEERING §13](../../docs/REVERSE_ENGINEERING.md#13-second-round-2026-11-25-community-catalogs-projects-content-login)
23. Written content (blog, help, changelog) and site pages come from SSR `$_TSR` loader state (seroval); post bodies are Yjs. → [REVERSE_ENGINEERING §13–14](../../docs/REVERSE_ENGINEERING.md#14-third-round-2026-11-25-site-pages-and-leftover-public-apis-site-scraper)
24. Clerk: new-device logins need an emailed code; JWT ≈ 60 s, minted from the long-lived `__client` cookie. → [REVERSE_ENGINEERING §13](../../docs/REVERSE_ENGINEERING.md#login-clerk)
25. Editing Room is an AI re-shoot editor (4 `videoshop_*` types, server-side render, FCP7 export); public examples give real preset ids. → [EDITING_ROOM §1](../../docs/products/EDITING_ROOM.md#1-tldr)
26. Property Studio is a server-side agent pipeline with review gates; no cost rows, 1500–2000 credit UI estimate. → [PROPERTY_STUDIO §1](../../docs/products/PROPERTY_STUDIO.md#1-tldr)
27. Our estimator disagrees with the JS formulas in 19 documented cases. → [COST_FORMULAS §8](../../docs/COST_FORMULAS.md#8-our-estimator-vs-the-js-formulas)
28. **Logged in sees more prices:** `/subscriptions/v2/plans` (ps_a3) has 15 plans instead of 14 (+ `lite` annual,
    $12/year, 85 % off forever) and `/job-sets/costs` 88 rows instead of 87 (+ `magi_2`, 1080p 2.5 credits/s) with
    another `version` (`9048fa70…` vs `0cee3218…`). The shared rows are identical; `hf-workspace-id` changes nothing.
    → [LOGIN_COVERAGE §1](../../docs/LOGIN_COVERAGE.md#1-tldr)
29. **Gateway rule:** `fnf-api-gw…/fnf/` answers 401 for *any* path without a token (auth before routing) and 404 for
    unknown paths with one, so 401 ≠ login-only. 14 service prefixes (`fnf-cms-api`, `fnf-series`, `fnf-academy`,
    `fnf-community`, `fnf-score`, …) host the real paths; most "login-only" catalogs are public there.
    → [REVERSE_ENGINEERING §16](../../docs/REVERSE_ENGINEERING.md#16-fifth-round-2026-11-26-login-audit)
30. What a session really adds: those price rows, the account's own money state (wallet balances in cost units ×100,
    `credits_per_dollar` 18) and its own library (`/jobs/accessible` with the actual charged `cost`).
    → [LOGIN_COVERAGE §1](../../docs/LOGIN_COVERAGE.md#1-tldr), [scrapers/account.md](../../docs/scrapers/account.md)
31. **Gallery generations do have comments**, on `fnf-community /entities/generation_publication/{publication_id}/comments`
    (cursor, 20/page); `/publications/{id}/comments` is always empty for them (the earlier "no comments" note was wrong).
    Projects and blog posts use the same `/entities/{type}/{id}/comments` pattern.
    → [COMMUNITY_COVERAGE §3](../../docs/COMMUNITY_COVERAGE.md#comments-of-shots-projects-and-blog-posts-new-finding)
32. **Project assets are public via folders**: `/folders/{id}`, `/children`, `/folders/{id}/items/v2`
    (`include_subfolders=true`, `size ≤ 100`, epoch-float cursor) carry every asset with prompt, params, model and media;
    the folder comes from the publication's `snapshot_folder_id` (web app `Fi()`). `/jobs/{id}` and `/assets/{id}/public`
    are Cloudflare-challenged (not needed, not evaded). → [scrapers/projects.md](../../docs/scrapers/projects.md#nested-data-model-opt-in-2026-11-26)
33. **Project briefs are a Yjs snapshot** of a Lexical document on `https://dam-editor-worker.higgsfield.ai/brief/{folder}/snapshot`
    (binary, `X-Brief-Updated-At`); decoded in pure Python (`scrapers/projects/yjs.py`) and rendered to Markdown
    (`brief.py`). → [REVERSE_ENGINEERING §17](../../docs/REVERSE_ENGINEERING.md#17-sixth-round-2026-11-26-projects-nested-data)
34. **Video explore** (`cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2`) has ~49k community items with likes
    (49,322 on 2026-11-26; page-number cursor with `total` for `sort=new`, opaque cursor for `trending`).
    → [scrapers/showcase.md](../../docs/scrapers/showcase.md), [ENGAGEMENT §12](../../docs/ENGAGEMENT.md#12-showcase-items-scrape-showcase)
35. **Logging in adds no public data** on community pages, projects (incl. nested) or showcase: same items, totals and
    fields; only viewer state (`is_liked_by_user`, `liked_by_me`, `is_followed` …) and a personalised feed order. So
    those requests are always sent anonymously. → COMMUNITY_COVERAGE §7a, projects.md "Anonymous vs logged in", showcase.md §4
36. **The Canvas node graph exists only over a login WebSocket** (`wss://canvas-worker…/api/templates/{id}/connect?ticket=`,
    ticket from `/auth` with a session; a Yjs-style sync protocol where the client must send messages). Template
    metadata is public; the graph is not scraped. → [scrapers/showcase.md §9](../../docs/scrapers/showcase.md#9-skipped-sources-and-gaps)
37. **Two marketplace services:** apps on `fnf-apps-marketplace` (`/api/v1/apps/community`, `/api/v1/apps/categories`;
    the earlier 404 was the wrong path `/api/v1/categories`), games / skills / AI employees on `fnf-skills-marketplace`.
    Studio galleries are the ordinary community feeds filtered by model; trending honours only the **last** `model`.
    → [scrapers/studios.md](../../docs/scrapers/studios.md), REVERSE_ENGINEERING §18
38. **Academy is public JSON on `fnf-academy`** (the earlier 401 was the `fnf` gateway path); the home main feed is
    `cms /main-feed` (opaque cursor, personalised, no total); trending projects have a `total`; user works are public
    on `/user/{id}/v2/publications`. `fnf /jobs/showcase/seedance-2-0` is Cloudflare-challenged for the crawler, so the
    job showcase is read from the public page's SSR state. → REVERSE_ENGINEERING §18
39. **The model registry can be scraped without running JS**: regexes + bracket matching over ~540–670 chunks reach
    every `defineJob`, the route table, featured ids, gating and plan tiers; bodies are reduced to extracts before
    archiving. → [scrapers/models.md](../../docs/scrapers/models.md)

## 3. Open questions / unknowns

**Pricing and credits**
- Real charged credits vs the client formula: the `account --with-jobs --compare-estimate` tooling exists, but
  Cloudflare challenges `/jobs/accessible` for the Scrapy crawl (`403 cf-mitigated: challenge`, 2026-11-26) while a
  single plain GET passed. Not evaded; wait and retry later, or check whether the challenge persists. → COST_FORMULAS §8, `scrapers/account.md`
- Generation-seconds deduction, balance order across wallets, refund rules. → COST_FORMULAS §5, §9
- `/workspaces/credit-price` on a team workspace (500 on a personal account). → PRICING §10
- Prices for other countries (needs a real request from that country; not spoofed).
- Seedance draft pricing; lipsync and Topaz prices (server-side). → PRODUCTS §6
- `qwen` TTS unit (flagged `unit_assumed`). → REVERSE_ENGINEERING §9

**Models and providers**
- Video-step models behind the 63 Nano Banana apps and viral presets (opaque node UUIDs); model behind each app template. → PRODUCTS §6, MODEL_LOADING §9
- Soul's base model; mixed-media, Popcorn, Faceless, AI Host backends; vendors behind `videoshop_*`. → PRODUCTS §6, EDITING_ROOM §11
- GPT Image codenames (`videotape-alpha` …) → which OpenAI model. → PRODUCTS §6
- What the 23 hashed flags mean beyond the 3 mapped; whether flags are PostHog-backed (inferred). → MODEL_LOADING §2.1, §9
- `scene_switch`: what product it is; its cost row is parsed as dimensions instead of add-ons. → COST_FORMULAS §8 #16
- MCP tool schemas (OAuth) and public API (`open.higgsfield.ai`, key) model ids and prices. → PRODUCTS §6

**Jobs and storage**
- `POST /publications` body, `hf-job-id` / `hf-media-links`, `/jobs/{id}/ip-detect`, ultra-batch lifecycle. → JOBS_AND_STORAGE §10
- Retention policy of result files; whether `/assets/{id}/public` is meant to be anonymous (Cloudflare challenge). → JOBS_AND_STORAGE §10
- The 3 s poller in MODEL_LOADING §4.4 vs the 5 s job tracker. → JOBS_AND_STORAGE §3.5

**Products**
- Exact jobs route for `videoshop_*` (`/jobs/v2/{type}` vs kebab). → EDITING_ROOM §11
- Property Studio LLM, image/video models and prompts (server-side); `exploded_view` unreleased (inferred). → PROPERTY_STUDIO §11

**Login-only data**
- Login-only endpoints (account, workspaces, notices, presets, social): **audited** in `docs/LOGIN_COVERAGE.md`
  (`/notices`, chain presets, restyle presets are public on `fnf-cms-api`; `/workspaces/settings` = `{configs: []}`;
  `/mixed-media/configs` = the user's own configs).
- Is the `lite` annual plan offered to every logged-in user or only to a cohort (free / low-cohort accounts)? One
  account tested; `/user` and `/user/meta` expose a `cohort` label (likely selector, inferred). → LOGIN_COVERAGE §1, §5
- Per-user `__HF_FF` flags: not readable with GET (SSR ignores a bare `__session` cookie); the refresh is a POST
  TanStack server function, which is out of bounds. → MODEL_LOADING §7
- Team / paid accounts: seat bonus, credit price, admin capabilities, auto top-up, unlimited grants, scoped credits
  (only a free personal workspace was tested). → LOGIN_COVERAGE §5

## 4. Prioritized backlog

| # | Item | Next steps | Docs to update |
|---|---|---|---|
| 1 | ~~Verify and finish the login catalogs and comments~~ **done 2026-11-26**. ~~Login audit and its recommendations as opt-in options~~ **done 2026-11-26** (`--logged-in-prices`, `--sections account`, `scrape account`, `catalog --kinds chain_preset,notice,restyle_preset`, `projects --public-series`; see [LOGIN_COVERAGE "Implementation status"](../../docs/LOGIN_COVERAGE.md#implementation-status)). ~~Still open from the audit: academy JSON, marketplace community apps~~ **done 2026-11-26** (`site --what academy-api`, `studios --what apps`) | — | `LOGIN_COVERAGE.md`, `scrapers/site.md` |
| 1a | **Estimator vs actual charges** (blocked) | `scrape account --with-jobs --compare-estimate --max-items 20` once `/jobs/accessible` is no longer Cloudflare-challenged for the crawler; never evade the challenge. Then feed mismatches into backlog 2 | COST_FORMULAS §8, `scrapers/account.md` |
| 1b | ~~**`normalize` of `runs/20261125-131446_projects-smoke` fails**~~ **done (`0e2f57d`)** with a `listing` validation error (pre-existing, not caused by the 2026-11-26 changes) | Reproduce with `normalize --run runs/20261125-131446_projects-smoke`; fix the projects schema/parser so old raw data re-parses; add a test | `scrapers/projects.md` |
| 1c | ~~**Schema export of `catalog` uses the old `CatalogDataset`**~~ **done (`0e2f57d`)** | `ScraperDef.dataset_model` in `scrapers/catalog/__init__.py` is `CatalogDataset`, so `python -m higgsfield_scraper schema` omits the opt-in collections; the per-run schema already switches to `CatalogDatasetFull` when one is selected | `scrapers/catalog.md` |
| 2 | **Fix the cost estimator's 19 differences** from the JS formulas | Work through [COST_FORMULAS §8](../../docs/COST_FORMULAS.md#8-our-estimator-vs-the-js-formulas): `ceil` per generation, `params.model == "video_edit"` + source length, per-family batch rules, JS default durations, viral `ceil(units/100)`, `scene_switch` add-on costs in `parsers/costs.py`; one test per case. Pricing output may change → baseline procedure | COST_FORMULAS §8, `scrapers/cost-estimate.md`, baseline |
| 3 | ~~**`models` registry scraper** (JS registry + costs + flags)~~ **done (`d994459`)**: `scrape models` | Design in [MODEL_LOADING §8](../../docs/MODEL_LOADING.md#8-what-we-can-and-cant-scrape): fetch tool pages → chunk graph → regex `defineJob`, routes, gating, featured ids, plan tiers → join on `job_set_type` with `/job-sets/costs` + `__HF_FF`; store the build id; fixtures = a few saved chunks | new `docs/scrapers/models.md`, ADDING_A_SCRAPER flow |
| 4 | **Monitor costs version / new job types** (e.g. `scene_switch`) | Schedule `re_check_changes.py` daily (or wrap it in a `monitor` command); on change run `pricing` + `diff`; document new types | this checkpoint changelog, PRODUCTS §5 |
| 5 | **Team-account checks** | With a team workspace: `/workspaces/credit-price`, seat pricing, `hf-workspace-id` effects on costs | PRICING §10, COST_FORMULAS §5.3 |
| 6 | ~~**Canvas templates scraper**~~ **done (`de0f5b8`)**: `showcase --what canvas_templates` (metadata; the node graph is login + WebSocket only) | — | `scrapers/showcase.md` |
| 7 | ~~**Property Studio public example media**~~ **done (`de0f5b8`)**: `showcase --what property_studio_examples` (69 presets, l10n titles); voices are `catalog --kinds reference_voice` | — | `scrapers/showcase.md` |
| 11 | ~~**Community apps marketplace**~~ **done (`9039a3f`)**: `scrape studios --what apps` (+ games, skills, AI employees) | — | `ENGAGEMENT.md` §11, DATA_INVENTORY §8 |
| 12 | **`display_name` redaction removes model names after `normalize`** — **still true** (checked 2026-11-26): `PERSONAL_KEYS` contains `display_name` and `redact_personal` blanks it everywhere, not only inside person containers (`redact_personal({"model": {"display_name": "Seedance"}})` → `[redacted]`); the studios fixtures show skills' / employees' `display_name` as `[redacted]` in archived bodies too | `core/privacy.PERSONAL_KEYS` blanks every `display_name`, incl. `stats.stack[]` model names and studios skill / employee names: live runs are fine, `normalize` gets `[redacted]` (stack label falls back to `job_set_type`, assets lose `model_name`; `publication_model_usage.display_name` too). Fix carefully per scraper: redact `display_name` only inside person containers, then check every scraper's normalize output | `scrapers/projects.md` Gaps, `scrapers/studios.md`, core privacy |
| 13 | **Talent-contest `/contests/{id}/submissions` is empty** (`submissions_count: 0`); its entries come from the contest-participations tabs | Either map those entries into `submissions` (with a `listing`/source marker) or document it more prominently in the contest output (`nested_summary`, summary.md) | `scrapers/projects.md` |
| 14 | **`--max-items` truncation with several kinds / feeds** (COMPLETENESS #18) | `--max-items N` stops item emission while further pages of other kinds are still fetched into `raw/` (e.g. `catalog --kinds all --max-items 30` emitted motions only). Add an additive option (e.g. `--max-items-per-kind`) or a `limit.items_not_emitted` count in the manifest; default behaviour unchanged | `COMPLETENESS.md` §4.3, §11, CLI.md |
| 15 | **The interactive menu has no Export item** | `export` is CLI-only (`higgsfield_scraper/interactive/` has no export flow). Add a menu item that builds the same argv as `export` | CLI.md "Interactive mode", README §4 |
| 16 | **`showcase --what explore` alias is missing from `--help`** | The alias works (`--what explore` plans the explore requests) but the help's "Available:" list shows only `explore_categories`. Add it to the help text | `scrapers/showcase.md`, CLI.md tables (regenerate) |
| 17 | **`models`: spread params not inlined; `--max-chunks 0` unverified** | Settings spread from another module (`...y(j)`, e.g. `seedance_2_5`) are kept as a `...` param with the spread source; resolve them across chunks. The uncapped crawl (`--max-chunks 0`) has not been run live (default 800 hit the cap with 1 chunk left) | `scrapers/models.md` §2, §5 |
| 8 | **Re-verify after a frontend build change** | When `re_check_changes.py` reports a new build: re-crawl chunks, re-run grep recipes, re-check every chunk name cited in MODEL_LOADING / PRODUCTS / COST_FORMULAS / EDITING_ROOM / PROPERTY_STUDIO, regenerate the catalog | those docs |
| 10 | ~~Estimator matches the JS formulas~~ **done (v2, opt-in)**; remaining: Veo 3 units, Cinema image table, Grok image condition, Reve key, Kling edit/reference params, magi_2, frame-count models | `--estimate-version 2` | COST_FORMULAS §8 |
| 9 | **Cloudflare scheduled deployment** (pending the user's decision) | Don't start until the user decides: scheduled runs of `re_check_changes.py` / pricing diff | — |

**DECIDED:** 2026-11-26: owner decided to keep CDN media URLs unredacted (they contain the uploader's Clerk user id in
the path); all other personal fields stay redacted unless --with-profiles.

Smaller ideas: viral-preset price-matrix flattening (MODEL_LOADING §8 #4); ~~Editing Room examples catalog~~ done
(`showcase --what editing_room_examples`); effect samples beyond the first SSR page (TanStack server function with a
per-build hash; showcase.md §9); refresh the inventory
(`recon_probe.py`) on the current build; `pricing --locales all`.

## 5. How to continue (new session)

1. `set PYTHONIOENCODING=utf-8` and `.venv\Scripts\python scripts\re_check_changes.py`. If something changed, handle it
   first (playbook stage A).
2. Read this checkpoint (status, in-progress rows, backlog) and the playbook's rules and pitfalls.
3. `git log --oneline -20` and `git status --short`: see what landed since the date above and what another agent may
   be editing. Don't touch files that are mid-change by someone else.
4. Pick the top backlog item that is not in progress (or what the user asked for).
5. Follow the playbook stages B → G that apply (map → JS → replay → document → scraper → gates).
6. Update this checkpoint: header values, status table, findings, unknowns, backlog, and a changelog row.
7. `.venv\Scripts\python scripts\re_check_changes.py --save` to store the new state in `.claude/re-state.json`.
8. Run the gates (playbook §3 G). Commit only when the user asks, with explicit paths.

## 6. Changelog of checkpoints

| Date | Build | Costs version | What changed |
|---|---|---|---|
| 2026-11-26 | `548e0f3a` | unchanged | Commits `9039a3f`, `b5d6909`, `d994459` + docs (all additive and opt-in; default and existing-option dry-runs identical; pricing 31/31): new **`studios`** scraper (apps / games / skills / AI-employees marketplaces, Playable Ads presets, AI Influencer options, per-studio galleries + comments) and **`models`** scraper (JS model registry + costs + shots facet) → **10 scrapers**; community `--feeds music-cards,job-showcase,collections,explore-cards,feed-categories`, creator works, shot facets; showcase `reels_presets`, `reels_comments`, `main_feed`, effect presets; projects `--what trending,contest-participation`, `--with-user-works`; catalog `outfit_character`; site `academy-api`; `creator_uid_key` everywhere. New docs `CONTENT_MAP.md` (every GAP / in-progress row now covered: 82 covered, 0 GAP) and `COMPLETENESS.md` (fixes #1–#17 done, #18 open), `scrapers/studios.md`, `scrapers/models.md`, REVERSE_ENGINEERING §18 (+ terms-of-use note in §2). Backlog: #12 still true, new #14–#17. Tests 692 passed, 1 skipped |
| 2026-11-26 | `548e0f3a` | unchanged | Commit `de0f5b8` (all opt-in, default dry-runs unchanged, pricing 31/31): projects nested data (`--with-project-assets/-brief/-stats/-comments/-related`, `--contest`, `--contest-tabs`, `--users`; Yjs briefs → Markdown); Community pages (`--feeds shots,posts,feed,creators,talents`, entity comment threads); `site --what room-list/room-content`; new **`showcase`** scraper (8 scrapers); `export` command; `scripts/merge_generations.py`; docs COMMUNITY_COVERAGE, ENGAGEMENT, EXPORT, scrapers/showcase, REVERSE_ENGINEERING §17; `core/privacy` redacts `owner_username`. Owner decision: CDN media URLs stay unredacted. Tests 578 passed, 1 skipped |
| 2026-11-26 | `548e0f3a` | unchanged | Commits `0e2f57d`, `2a4deb7` + docs: fixed projects normalize (contest detail without list row), catalog schema export (`CatalogDatasetFull`), `account --dry-run`; **estimator v2** (`--estimate-version 2`: 17/19 COST_FORMULAS §8 differences fixed, ~60 static JS tables, community coverage 73% → 81%; v1 default byte-identical); **`docs/PROVIDERS.md`**: makers are published, inference platforms are not; 0 fal/Replicate fingerprints in 925 jobs + 744 JS chunks; OpenAI/Gemini/xAI/BFL upstream billing records point to direct vendor APIs. Tests 465 passed, 1 skipped |
| 2026-11-26 | `548e0f3a` | anonymous `0cee3218…` (87 types) / logged in `9048fa70…` (88, + `magi_2`) | Login audit (`LOGIN_COVERAGE.md`, REVERSE_ENGINEERING §16). Commit `d0429ec`: `pricing --logged-in-prices` and `--sections account`, new `account` scraper (7 scrapers), `catalog --kinds chain_preset,notice,restyle_preset` (+ `--include-hidden`, `--with-profiles`), `projects --public-series`. `/jobs/accessible` Cloudflare-challenged for the crawler (not evaded). Docs updated for the audit corrections. Tests 370 passed, 1 skipped |
| 2026-11-26 | `548e0f3a` | `0cee3218…` (87 types) | First checkpoint. Pricing (incl. login-only, baseline v3), 6 scrapers, model loading, products, cost formulas, jobs/storage, Editing Room, Property Studio documented. Catalog/community login endpoints fixed (public bases). Anonymous `__HF_FF` empty |

## History rewrite (2026-11-26)

At the owner's request the whole Git history was rewritten with `git-filter-repo` and force-pushed: the 9 real Clerk
user ids that older commits contained were replaced with `user_REDACTEDHnn`, and the `Co-Authored-By` trailer was
removed from every commit message (no trailers from now on). Every commit id changed (e.g. `fc9eda3` -> `d0429ec`);
ids quoted in these docs were updated. The final tree was verified byte-identical (same tree hash), with the same 24
subjects, bodies, authors and dates. A local pre-rewrite mirror backup is at `D:/higgsfield-scraper-backup-20261126-130804.git` (not on GitHub).
