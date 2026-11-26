# Login coverage audit: what a Higgsfield session unlocks

Audit date: **2026-11-26**, build `548e0f3a`. Account: a **free, personal (non-team) workspace**, owner role.
Every request was a GET at about 1 req/s with `Authorization: Bearer <Clerk JWT>` (minted by
`TokenProvider.from_env().get()`), `Origin: https://higgsfield.ai` and the project `USER_AGENT`. `hf-workspace-id`
was added where the frontend sends it; it never changed a response. No DataDome challenge appeared.

Out of scope (handled by another task): login-only catalog kinds (soul styles, mixed-media presets, veo3 styles,
`*-motions`, katana, youtube-faceless, marketing-studio-v2, color presets, camera settings) and
`/publications/{id}/comments`.

Redacted samples: [`samples/higgsfield/login_audit/`](../samples/higgsfield/login_audit/) (ids, authors and UUIDs
redacted, lists cut to 2 items; per-user endpoints saved as **types only** in `account_endpoint_shapes.json`).

Which recommendations are implemented (and with which flag) and which are still open:
[Implementation status](#implementation-status) at the end. The sections below are the audit as it was written.

---

## 1. TL;DR

**Logged-in vs anonymous differences (the important part):**

| What | Anonymous | Logged in | Same with `hf-workspace-id`? |
|---|---|---|---|
| `/subscriptions/v2/plans?plan_set_key=ps_a3` | 14 plans | **15 plans**: an extra **`lite` / annual** plan, 100 credits/month, **$12/year ($1/month)**, list $84/year, `discount {percent_off: 85, duration: "forever"}`, `offer: null`. All 14 shared rows are byte-identical | yes (identical) |
| `/job-sets/costs` | 87 rows, `version` `0cee3218…` | **88 rows**, `version` `9048fa70…`: extra row **`magi_2`** `{resolution: 1080p, base_credits: 0, cost_per_second: 2.5, original_cost_per_second: 2.5}`. The other 87 rows are identical. Re-checked 3× (anon/auth/anon): stable, not a timing effect | yes (identical) |
| `/user/features`, `/feature` | 3 flags, all false / `{"ZGV5a2hhbg": false}` | identical | — |
| `window.__HF_FF` (SSR flags on `/ai/video`) | 23 flags, 12 true, `userId: null` | **not verifiable with GET**: the SSR page ignores a bare `__session` cookie (still `userId: null`); per-user flags are refreshed through a TanStack server function (`POST /_serverFn/…`), which is out of bounds | — |

So the anonymous pricing scrape is **not complete**: a logged-in user sees one more plan and one more model price.
Whether `lite` is offered to every logged-in user or only to free / low-cohort accounts is **unknown** (one account
tested; `/user` and `/user/meta` expose a `cohort` label that is the likely selector — inferred).

**What logging in really unlocks (verified):**

1. **Pricing deltas** above (`lite` annual plan, `magi_2` cost row).
2. **The account's own money state**: `/user` (plan, credit balances by bucket), `/workspaces/wallet` (balances in
   cost units ×100, `expire_days`, `scoped_credits`), `/workspaces/subscription` (plan, seats, period, payment status),
   `/v2/auto-top-ups/settings` (`credits_per_dollar: 18`, refill options), `/user/free-gens/v2`,
   `/user/generation-seconds`, `/generation-seconds/packs`, bundle status endpoints, `/workspaces/notice`.
3. **The account's own library**: `/jobs/accessible` (each job carries the **actual charged `cost`** in cost units —
   e.g. one job cost `112` = 1.12 credits, matching the drop in `/user.package_credits`), `/assets`, `/folders*`,
   `/custom-references`, `/restyle/presets/custom`, `/mixed-media/configs`.

**Biggest surprise: most "login-only catalogs" are public on another service base.** The gateway answers 401 to
*anything* under `/fnf/` without a token (auth runs before routing), and with a token the same path is **404** — the
real endpoint lives on a different service prefix and is public:

| JS call | Wrong guess (inventory §5) | Real, public endpoint |
|---|---|---|
| `/series` | `/fnf/series` (401 anon / 404 auth) | `GET /fnf-series/series?limit=100` (35 series) and `/fnf-series/series/{slug}` |
| `/api/v1/courses` | `/fnf/api/v1/courses` (404) | `GET /fnf-academy/api/v1/courses` (17 courses) |
| `/applications/explore` | `/fnf/applications/explore` (404) | `GET /fnf-cms-api/applications/explore?apps_per_category=20` (8 categories) |
| `/job-set-chain-presets` | `/fnf/job-set-chain-presets` (404) | `GET /fnf-cms-api/job-set-chain-presets[?show_hidden=true]` (48 / 58 presets **with credit prices**) |
| `/restyle/presets` | `/fnf/restyle/presets` (404) | `GET /fnf-cms-api/restyle-presets` (21 presets, cursor) |
| `/notices` | `/fnf/notices` (404) | `GET https://cms.higgsfield.ai/notices` = `/fnf-cms-api/notices` (10 per-model notices) |
| `/users/suggestions`, `/publications/{id}/related` | `/fnf/…` (404) | `/fnf-community/…` — **public** |
| `/academy/_catalog` | listed as an API | it is a **frontend route** (`P("/academy/_catalog")`), not an API |

Service prefixes found in the bundle: `fnf`, `fnf-academy`, `fnf-ai-cmo`, `fnf-aitys`, `fnf-apps-marketplace`,
`fnf-campaign-api`, `fnf-cms-api`, `fnf-community`, `fnf-higgsclaw-cron`, `fnf-meet`, `fnf-notification`,
`fnf-score`, `fnf-series`, `fnf-skills-marketplace` (all on `https://fnf-api-gw.higgsfield.ai/`).

**Most valuable things not yet scraped (in order):**

1. Logged-in plans + costs deltas (`lite` annual, `magi_2`) → `pricing` with a session.
2. **Chain presets with `cost_credits` / `discount_credits`** (public!) → `catalog --kinds chain_preset`.
3. Per-model **notices** (retirements, badges; public) → `catalog --kinds notice`.
4. Series via the public `fnf-series` base (the `projects` scraper currently marks it login-only).
5. Opt-in `account` scraper: wallet/subscription/free-gens/generation-seconds + own jobs with real `cost`
   (validates the cost formulas against what was actually charged).

---

## 2. Every probed endpoint

Base `GW = https://fnf-api-gw.higgsfield.ai`. "anon" = no `Authorization`. "per-user" = depends on the account.
Value: **H**igh / **M**edium / **L**ow.

### 2.1 Pricing-related

| Request (GET) | Status | Shape (key fields) | Same for all? | Personal data? | Value | Recommendation |
|---|---|---|---|---|---|---|
| `GW/fnf/subscriptions/v2/plans?plan_set_key=ps_a3&with_localization=true` (auth; ± ws header) | 200 | `{plans[15]{id, plan_type, name, credits, billing_period, product_id, price_id, original_price, original_monthly_price, final_price, final_monthly_price, renew_price, renew_monthly_price, currency, discount{percent_off, duration_months, duration}, offer}, country_code, special_offer}` | **No**: +1 `lite`/annual vs anon | `country_code` (IP country) | **H** | `pricing`: when a session exists, also fetch plans logged in; emit the extra rows with a new field `audience = "logged_in"` (anon rows `"anonymous"`) |
| same, anon | 200 | 14 plans, same fields | baseline | `country_code` | — | (already scraped) |
| `…/plans?with_localization=true` (no key) | 200 | anon 14 / auth 15; prices differ from `ps_a3` (cheaper starter/plus = the IP's geo plan set) | per IP | `country_code` | L | skip: the scraper pins `ps_a3`; geo default is known behaviour |
| `GW/fnf/job-sets/costs` (auth; ± ws header) | 200 | `{data[88]{job_set_type, cost[{resolution, base_credits, cost_per_second, original_cost_per_second}]}, version}` | **No**: +`magi_2`, different `version` | none | **H** | `pricing`: fetch costs logged in too; union rows, new field `visibility = "logged_in_only"` on rows missing anonymously; store both `version` hashes |
| `GW/fnf/user/free-gens/v2` (± ws; JS adds `surfaces=`) | 200 | `{items: []}` | per-user | — | M | `account` scraper |
| `GW/fnf/user/free-gens` (legacy) | 200 | `{}` | per-user | — | L | skip (legacy) |
| `GW/fnf/user/offers` | 200 | `[]` | per-user | — | L | skip (not called by the current bundle) |
| `GW/fnf/user/personal-promo` (JS: `?offered=`) | 200 | `{}` (no promo) | per-user | — | M | `account` (personal discount when present) |
| `GW/fnf/user/personal-promo/tasks` | 200 | `null` (JS: 404 → none) | per-user | — | L | `account`, optional |
| `GW/fnf/user/generation-seconds` | 200 | `{items: []}` | per-user | — | M | `account` |
| `GW/fnf/generation-seconds/packs` | 200 (anon 401) | `{items: []}` for this account | probably per-eligibility | — | **M** | `pricing --sections auth`: store raw; packs are purchasable Seedance-seconds prices when offered (empty today) |
| `GW/fnf/subscriptions/bundle/all-unlim/status` | 200 | `{is_eligible_to_purchase, has_all_unlims}` | per-user | — | L | `account` |
| `GW/fnf/subscriptions/bundle/seedance-unlimited` | 200 | `{tiers: []}` | per-eligibility | — | M | `pricing --sections auth` raw (like `unlim-catalog`) |
| `GW/fnf/subscriptions/bundle/unlim-catalog` | 200 | `{bundles: []}` | per-eligibility | — | M | already in `pricing` auth |
| `GW/fnf/user` | 200 | `{id, plan_type, subscription_credits, package_credits, bonus_credits, bonus_credits_expire_at, daily_credits, soul_credits, wan2_5_video_credits, text2keyframes_credits, face_swap_credits, qwen_camera_control_credits, character_swap_credits, total_plan_credits, billing_period, plan_ends_at, next_credit_allocation_at, cohort, promo_state, has_unlim, workspace_id, workspace_type, workspace_role, is_paused, is_gift_subscription, subscription_downgrades_*, lang, …}` (41 keys; credits in **credits**, float) | per-user | ids | M | `account` (balances, plan state; drop ids) |
| `GW/fnf/user/profile` | 200 | `{username, avatar_url, full_name, bio, headline, *_handle, badges[], total_projects_views/likes, created_at, …}` | per-user | **yes** (name, handles) | L | skip (identity only) |
| `GW/fnf/user/meta` | 200 | `{country_code, region_code, cohort}` | per-user | location | L | `account`: keep `cohort` only (explains offers) |
| `GW/fnf/user/settings` | 200 | consents (`media_consent`, …), `unlimited_settings: null`, `has_image_auto` | per-user | consents | L | skip |
| `GW/fnf/user/features`, `GW/fnf/feature` | 200 | 3 bools / 1 legacy flag | **same** as anon | — | L | skip (identical) |
| `GW/fnf/workspaces` | 200 | `[{id, name, type, user_role, is_enterprise_sub_workspace, can_publish_assets, clerk_organization_id, avatar_url, username}]` | per-user | ids | L | `account` (to get the workspace id in memory only) |
| `GW/fnf/workspaces/details` | 200 | `{id, type, user_role, sso_status, grace_period_type, has_scheduled_monthly_credit_allocation, overdue_invoice_stage, …}` | per-user | id | L | skip |
| `GW/fnf/workspaces/capabilities` | 200 | `{id, 56 boolean permissions}` (`subscription_top_up`, `members_assign_unlims`, `usage_view_team_dashboard`, …); free personal: only `project_create` true | per-plan/role | id | L | skip (UI permissions) |
| `GW/fnf/workspaces/admin-capabilities` | **409** `{detail:{error_type:"workspace_is_not_shared"}}` | — | team only | — | L | skip |
| `GW/fnf/workspaces/wallet` (± ws) | 200 | `{workspace_id, credits_balance, subscription_balance, total_credits, on_demand_credits, bonus_credits, bonus_credits_expire_at, expire_days, credit_limit, group_credit_allocation, allocation_cycle, next_credit_allocation_date, wallet_created_at, scoped_credits[]}` — **all balances in cost units (×100)**: `credits_balance 888` = 8.88 credits | per-user | id | **M** | `account` |
| `GW/fnf/workspaces/settings` (± ws) | 200 | **`{configs: []}`** (wire format; the client maps `configs` → `unlimited_settings`, dropping `status == "locked"`) | per-workspace | — | M | `account` (unlimited grants when present) |
| `GW/fnf/workspaces/subscription` | 200 | `{subscription_id, plan_name, plan_type, status, billing_cycle, total/occupied/available_seats, seats_capacity, credits_per_seat, current_period_start/end, payment_status, plan_version, cancel_at, is_paused, email_type, …}` (34 keys) | per-user | ids | M | `account` |
| `GW/fnf/workspaces/seat-bonus` | 200 | `{seat_bonus: null}` | team only | — | L | `account` (team) |
| `GW/fnf/workspaces/credit-price` | **500** `An unexpected error occurred while retrieving credit price` | — | team only | — | L | already handled in `pricing` (warning) |
| `GW/fnf/workspaces/notice` | 200 | `{status, modal_data, payment_method_bonus_status, discount, discounted_price, subscription, unlims, currency, claim dates …}` | per-user | — | M | `account` (shows discount offers to this user when active) |
| `GW/fnf/workspaces/onboarding/triggers` | 200 | `[]` | per-user | — | L | skip |
| `GW/fnf/workspaces/wallet/auto-top-up` | **409** `workspace_is_not_shared` | — | team only | — | L | skip |
| `GW/fnf/v2/auto-top-ups/settings` | 200 | `{state, is_eligible, is_on_demand_only, threshold, refill_options[], options[], selected_option, default_option, credits_per_dollar: 18, current_refill_amount, on_demand_credits, modal_type, currency: "usd", expire_days: 90}` | mostly per-user; `credits_per_dollar` looks global | — | M | `pricing --sections auth`: record `credits_per_dollar` and `options[]` (top-up price ladder) when eligible |
| `GW/fnf/workspaces/invoices`, `GW/fnf/subscriptions/invoices` | 200 | `{items: [], cursor}` | per-user | **billing** | L | skip (private billing) |

### 2.2 Catalog-like (same for everyone)

| Request (GET) | Status | Shape | Same for all? | Personal? | Value | Recommendation |
|---|---|---|---|---|---|---|
| `GW/fnf-cms-api/job-set-chain-presets` (`?show_hidden=true`, `?product_key=`) | 200 **anon** | list[48] (58 with hidden) `{id, product_key, name, description, category, image_preview, previews[], duration, priority, cost_credits, discount_credits, pricing_mode (fixed 47 / dynamic_chain 1), pricing_schema, inputs[], preset_family, model (seedance_2_0_fast 27, seedance_2_0 14, kling3_0 7), runtime "preset_chain", runtime_params{chain_type, preset_id, endpoint, model}}`; all `product_key = game_character_creator`; 9 with `discount_credits ≠ cost_credits` | yes | — | **H** | `catalog --kinds chain_preset` (public, no login): per-preset credit price + discount + underlying model |
| `https://cms.higgsfield.ai/notices` (= `GW/fnf-cms-api/notices`) | 200 **anon** | `{header_notices[], job_set_notices[10]{job_set_types[], params, variant, badge{label, tooltip}, popup{title, description}}}` (e.g. "Seedance 1.5 Pro is being retired … after 11 November") | yes | — | **M** | `catalog --kinds notice` (or a `model_notice` item in `pricing` keyed by `job_set_type`): model lifecycle / retirement / promo badges |
| `GW/fnf-cms-api/restyle-presets` | 200 **anon** | `{total: 21, cursor: int, items[5]{id, name, title, description, source, job_set_type "restyle", variants[], image, images[], preview_video, video, priority}}` | yes | — | M | `catalog --kinds restyle_preset` (paginate by `cursor`) |
| `GW/fnf/restyle/presets/custom?size=20` | 200 | `{items: [], has_more, cursor}` | per-user | own uploads | L | skip (own content) |
| `GW/fnf/mixed-media/configs?preset_id=<id>` | 200 | `{total, cursor, items: []}` — the user's saved configs for that preset, not a catalog | per-user | own content | L | skip |
| `GW/fnf-series/series?limit=100` / `…/series/{slug}` | 200 **anon** | `{items[35]{id, slug, name, short_description, full_description, author_type, state, is_series, portrait/landscape/background/logo/trailer, is_hero, display_order, categories[], cast[], tags[], vote_count, subscriber_count, engagement_score, episodes[{23 keys}], duration_seconds, …}}` | yes (`is_vote_triggered`/`is_notify_triggered` per-user) | — | M | `projects`: switch `SERIES`/`SERIES_DETAIL` to the `fnf-series` base and drop `LOGIN_ONLY` |
| `GW/fnf-academy/api/v1/courses` | 200 **anon** | list[17] `{id, slug, title, description, lesson_count, test_count, has_certificate, difficulty, reading_minutes, duration_minutes, **free_generations**, categories[], preview_media, featured_position, published_at}` | yes | — | M | `site --what academy`: use this JSON for the course list (adds `free_generations` per course); `/api/v1/courses/{slug}` for detail |
| `GW/fnf-cms-api/applications/explore?apps_per_category=20` | 200 **anon** | list[8] categories `{id, slug, name, description, icon, priority, apps[{9 keys}], seo_*}` | yes | — | L | `site --what apps` already gets this from HTML; optional JSON source |
| `GW/fnf-apps-marketplace/api/v1/apps/community` | 200 **anon** | `{items[50]{id, app_id, user_id, author{3}, name, description, category, app_url, views/remixes/likes/dislikes_count, **credits_usage**, is_featured, is_higgsfield, type, published_at, …}, next_offset}` | yes | author (public creator) | M | new `site --what marketplace-apps` (or `catalog`): community-built apps with credit usage; redact authors like `community` |
| `GW/fnf-apps-marketplace/api/v1/apps/personal` | 200 | `{apps: []}` | per-user | — | L | skip |
| `GW/fnf-apps-marketplace/api/v1/categories` | 404 | — | — | — | — | path not on this base (unresolved) |
| `GW/fnf-score/v1/season` | 200 | `null` (no active season for this account) | per-user progress | — | L | skip until a season exists; `/v1/season/weekly-canvas` 404 |
| `GW/fnf/v2/quizzes/user` | 200 | `{quiz{usage_plan, experience, features[], creation_goals[], source, frustration, …}, enterprise_quiz_required}` | per-user | **yes** (onboarding answers) | L | skip. (`/v2/quizzes` itself is a POST) |

### 2.3 Social

| Request (GET) | Status | Shape | Same for all? | Personal? | Value | Recommendation |
|---|---|---|---|---|---|---|
| `GW/fnf-community/users/feed?limit=20&offset=0` | 200 (anon 401) | `{publications: [], has_more}` — posts from followed users | per-user | — | L | skip (empty; depends on follows) |
| `GW/fnf-community/users/suggestions?limit=10` (JS also `type=`) | 200 **anon** too | `{items[10]{type, profile{10 keys}}}` | ~yes | **other users' profiles** | L | skip (people data, no pricing value) |
| `GW/fnf-community/publications/{id}/related?limit=10` | 200 **anon** too | `{publications[10]{id, user_id, title, content{3}, like/dislike/comment/views/share_count, author{7}, is_subscribed, is_mine, created_at, updated_at}}` | yes | authors | L | `community` already defines `RELATED_PATH` (unused); keep unused. Note: the id must be a **community post** id (`/publications/feed`), a generation `publication_id` gives 404 |

### 2.4 The account's own content (shape only; counts for this account)

| Request (GET) | Status | Shape | Count | Value | Recommendation |
|---|---|---|---:|---|---|
| `GW/fnf/jobs/accessible?size=20` (JS: `status`, `job_set_type`, `cursor`, `ordering`, `workspace_id`, `liked_by`, date filters) | 200 | `{jobs[{id, job_set_id, job_set_type, params{…}, meta, status, results{raw, min, hls, h264}, created_at, workspace_id, user{4}, is_favourite, **cost** (cost units), ip_* flags, …}], has_more}` | 1 | **M** | `account --with-jobs`: emit `account_job{job_set_type, params, status, cost_units, credits=cost/100, created_at}` — lets us check `COST_FORMULAS` against real charges |
| `GW/fnf/assets?category=image&size=20` (`category` required) | 200 | `{items[{id, user_id, created_at, min_url, raw_url, thumbnail_url, job_set_type, published_at, folder_ids[], comments_count, deleted_at, duration_ms, is_favourite, …}], cursor}` | 1 (video 0) | L | skip (media URLs; nothing price-related) |
| `GW/fnf/assets/favourites?category=image&size=20` | 200 | `{items: [], cursor}` | 0 | L | skip |
| `GW/fnf/folders`, `/folders/accessible`, `/folders/shared`, `/folders/pinned` | 200 | `{items: [], cursor}` / `[]` | 0 | L | skip |
| `GW/fnf/custom-references` | 200 | `[]` | 0 | L | skip (trained characters; personal) |
| `GW/fnf/custom-references/soul-v2` | 422 | validation error (path param) | — | — | — |
| `GW/fnf/v2/reference-elements` | 405 | GET not allowed on the bare path | — | — | not explored further |

---

## 3. Proposed schema sketches (high/medium value)

All follow the project conventions (hashed natural-key id, `source_url`, `scraped_at`, `schema_version`, money as
`Decimal` strings + ISO 4217 `currency` + `price_raw`).

**3.1 `pricing`: audience on plans and visibility on costs (new fields on existing items)**

```text
plan_price (existing) + audience: "anonymous" | "logged_in"     # lite/annual only appears logged in
                      + discount_percent_off: int | None         # from plans[].discount.percent_off
                      + discount_duration: "forever"|"once"|"repeating"|None, discount_duration_months: int|None
job_cost (existing)   + visibility: "public" | "logged_in_only"  # magi_2 today
pricing_run meta      + job_costs_version_anon, job_costs_version_logged_in
```
Natural key stays `(plan_set_key, plan_type, billing_period, …)`; `audience` is a field, not part of the key,
unless a plan ever differs between audiences (then add it to the key).

**3.2 `catalog --kinds chain_preset` (new item, public)**

```text
catalog_chain_preset: id(hash of preset id), preset_id, product_key, name, description, category, priority,
  model, preset_family, runtime, chain_type, endpoint, pricing_mode, cost_credits: Decimal,
  discount_credits: Decimal, is_discounted: bool, pricing_schema: dict, inputs: list[{id, type, min, max}],
  duration: int|None, is_hidden: bool (seen only with show_hidden=true), image_preview_url, source_url, scraped_at
```

**3.3 `catalog --kinds notice` (new item, public)**

```text
catalog_model_notice: id(hash of sorted job_set_types + badge.label), job_set_types: list[str], variant,
  badge_label, badge_tooltip, popup_title, popup_description, params: dict, kind: "job_set"|"header",
  source_url, scraped_at
```

**3.4 `account` scraper (opt-in, needs `login`; never in default runs)**

```text
account_snapshot (one per run): plan_type, billing_period, cohort, promo_state, has_unlim, workspace_type,
  workspace_role, subscription_status, payment_status, plan_version, credits_per_seat,
  current_period_start/end, next_credit_allocation_at,
  balances: {subscription, package, bonus, daily, total_plan} (credits, Decimal),
  wallet: {credits_balance, subscription_balance, on_demand, bonus, total} (÷100 → credits), expire_days,
  scoped_credits: list[{scope, balance, expires_at}], free_gens: list, generation_seconds: list,
  unlimited_grants: list (from /workspaces/settings configs), auto_top_up: {state, is_eligible,
  credits_per_dollar, options}, personal_promo: dict|None, notice: {status, discount, discounted_price, currency}
account_job (--with-jobs): job_id_hash, job_set_type, status, params (as-is), cost_units: int,
  credits: Decimal (= cost_units/100), created_at
```
No ids, emails, names, usernames, media URLs, invoices or payment cards. Workspace id only in memory (header).

---

## 4. Doc corrections needed elsewhere (not edited here)

**`HIGGSFIELD_DATA_INVENTORY.md`**
- §5 "Catalogs that need any session": `/series`, `/applications/explore`, `/api/v1/courses` are **public** on
  `fnf-series`, `fnf-cms-api`, `fnf-academy`; `/academy/_catalog` is a frontend route, not an API. The 401s came from
  calling them under `/fnf/` (the §5 caveat applies).
- §5 "Social": `/users/suggestions` and `/publications/{id}/related` are **public** on `fnf-community`; `/users/feed`
  is login-only on `fnf-community` (not `/fnf`).
- §5 "Studios": `/v1/season` lives on `fnf-score` (200 `null` with a session); `/v2/quizzes` is a POST (only
  `/v2/quizzes/user` is a GET, personal).
- §5 "Your account and billing": confirmed 200 for `/user`, `/user/profile`, `/user/free-gens/v2`, `/user/offers` (`[]`,
  no longer called by the bundle), `/user/personal-promo`, `/workspaces`, `/workspaces/{details,capabilities,wallet,
  settings,subscription,seat-bonus,notice}`; `/workspaces/admin-capabilities` and `/workspaces/wallet/auto-top-up` are
  409 `workspace_is_not_shared` for personal workspaces. Add `/user/generation-seconds`, `/generation-seconds/packs`,
  `/v2/auto-top-ups/settings`, `/subscriptions/bundle/{all-unlim/status,seedance-unlimited}`, `/user/meta` (cohort).
- §8 table: add the service-prefix list (§1 above); "Original plan #7 `account`" is now specified in §3.4 here.

**`MODEL_LOADING.md`**
- §6: `/notices` is **public** at `https://cms.higgsfield.ai/notices` / `fnf-cms-api/notices` (not "login");
  `/job-set-chain-presets` and the restyle presets (`/fnf-cms-api/restyle-presets`) are **public** on `fnf-cms-api`;
  `/mixed-media/configs?preset_id=` returns the user's own saved configs (`{total, cursor, items}`), not a preset config.
- §6: `/workspaces/settings` returns `{configs: [...]}`; `unlimited_settings` is the client-side name after mapping.
- §6: `/jobs/accessible`, `/user`, `/workspaces`, `/workspaces/details`, `/workspaces/wallet` → confirmed (login, 200).
  `/jobs/accessible` items include `cost` in cost units.
- §6/§7: `/job-sets/costs` **differs when logged in** (extra `magi_2` row, different `version`).
- §7: per-user `__HF_FF` could not be read with GET (SSR ignores a bare `__session` cookie; refresh is a POST server fn).

**`COST_FORMULAS.md`**
- §4 table row `magi_2` (line ~279): "no costs row today → null" is only true **anonymously**; logged in the row is
  `1080p: base_credits 0, cost_per_second 2.5` → `ceil₀.₀₁(d × 2.5) × b` can be computed.
- §5.1: the wire format of `GET /workspaces/settings` is `{configs: []}`; the client maps it to `unlimited_settings`
  and drops `status == "locked"` grants (`548e0f3a-tCLaulKUdGQfxqgZ.js`, `Lj`/`eM`).
- §5.3: confirmed wallet fields, plus `expire_days`, `credit_limit`, `wallet_created_at`, `next_credit_allocation_date`;
  **all** wallet balances (not only `scoped_credits`) are in cost units (×100). `/user` reports the same balances in
  credits (floats) plus legacy per-model buckets (`soul_credits`, `wan2_5_video_credits`, `face_swap_credits`, …).
- §5.4: `GET /v2/auto-top-ups/settings` (personal accounts) exposes `credits_per_dollar` (18) and refill `options[]`;
  `/workspaces/wallet/auto-top-up` is team-only (409 on personal).

**`PRICING.md`**
- §10: add the logged-in plan difference (`lite` annual, $12/year, 85 % forever discount, ps_a3) and the logged-in
  `magi_2` cost row; add `/generation-seconds/packs`, `/subscriptions/bundle/seedance-unlimited`,
  `/v2/auto-top-ups/settings` to the login-only list. `/workspaces/credit-price` 500 on personal accounts: confirmed.
- §6 / any statement that `lite` is a legacy plan "no longer sold": wrong for logged-in users (it is sold, annual only).

**`REVERSE_ENGINEERING.md`**
- The "legacy plan types no longer sold (`basic`, `lite`, …)" note: `lite` is sold to logged-in users.

**`scrapers/projects` code comment** (`higgsfield_scraper/scrapers/projects/endpoints.py`): `SERIES` / `SERIES_DETAIL`
are marked "LOGIN ONLY"; they are public on `https://fnf-api-gw.higgsfield.ai/fnf-series`. (Code not changed.)

---

## 5. Confidence notes

- **Verified live** (2026-11-26): every status and shape in §2; the plans and costs differences (costs re-checked
  anon → auth → anon with stable versions); workspace header made no difference on plans, costs, wallet, settings.
- **One account only**: a free personal workspace. Team / paid accounts will return non-empty seat bonus, credit price,
  admin capabilities, auto top-up and unlimited grants. Whether `lite` is offered to everyone logged in or only to some
  cohorts/free users is **unknown** (inferred: cohort-driven).
- Empty lists (`generation-seconds/packs`, `seedance-unlimited` tiers, `unlim-catalog` bundles, free gens, personal
  promo) mean "nothing offered to this account today", not "endpoint unused". Their item shapes are only known from
  the JS (see `PRICING.md` §10 for packages).
- Flags: per-user `__HF_FF` was **not** observed (would need a POST server function). `/user/features` and `/feature`
  are identical logged in and anonymous.
- Service bases were found by probing likely prefixes; the minified wrapper functions that pick the base were not
  resolved for `/api/v1/categories` (404 on `fnf-apps-marketplace`).
- `country_code` (IP-derived) appears in plans and `/user/meta`; it is not recorded in any sample.

---

## Implementation status

As of commit `fc9eda3` (2026-11-26). Everything implemented is **opt-in**: default runs of every scraper are unchanged.
Field names sometimes differ from the §3 sketches; the scraper docs are authoritative.

| Recommendation (§1, §2, §3) | Status | How / where |
|---|---|---|
| Logged-in plans: extra `lite` / annual row (§2.1, §3.1) | **implemented** | `scrape pricing --logged-in-prices`: plans re-fetched with the session (`plans_logged_in`); rows only in the logged-in response appended with `visibility: "logged_in"` (not `audience`, which already means individual/business). [`PRICING.md`](PRICING.md) §10, [`../CLI.md`](../CLI.md) "Logged-in pricing" |
| Logged-in costs: extra `magi_2` row, both `version` hashes (§2.1, §3.1) | **implemented** | same flag (`job_costs_logged_in`); model tagged `visibility: "logged_in"`; `meta.logged_in_prices` = `{costs_version_anonymous, costs_version_logged_in, logged_in_only_plan_ids, logged_in_only_model_ids, differing_rows}` |
| Wallet, subscription, auto top-up (`credits_per_dollar`, `options[]`), free gens, generation seconds, generation-seconds packs, all-unlim status, seedance-unlimited tiers (§2.1) | **implemented** | `scrape pricing --sections account` (8 whitelisted endpoints, never part of `all`). The packs and seedance-unlimited tiers went here, not into the `auth` section as §2.1 suggested, so default logged-in `--sections all` output is unchanged |
| `account` scraper (§1 #5, §3.4): snapshot incl. `/user` balances, `/user/meta` cohort, `/workspaces/settings` grants, `/workspaces/notice`, personal promo | **implemented** | `scrape account` (11 snapshot endpoints, field whitelists, redaction before the archives). [`scrapers/account.md`](scrapers/account.md) |
| Own jobs with the real charged `cost` (§2.4) and estimate-vs-actual check | **implemented, blocked live** | `scrape account --with-jobs [--compare-estimate]`. `/jobs/accessible` answered `403 cf-mitigated: challenge` to the Scrapy crawl on 2026-11-26 (a single plain GET passed): recorded in `meta.limits_hit`, run `partial`, not evaded. The comparison is covered by offline tests only |
| Chain presets with credit prices (§2.2, §3.2) | **implemented** | `scrape catalog --kinds chain_preset` (+ `--include-hidden` for the `show_hidden=true` presets, `is_hidden`; `--with-profiles` keeps `collaborator`) |
| Per-model notices (§2.2, §3.3) | **implemented** | `scrape catalog --kinds notice` |
| Restyle presets (§2.2) | **implemented** | `scrape catalog --kinds restyle_preset` |
| Series via the public `fnf-series` base (§2.2, §4) | **implemented (opt-in)** | `scrape projects --what series --public-series` (+ `--with-details` for `/series/{slug}`). The default run keeps the legacy `/fnf/series` path so its output does not change; the `endpoints.py` comment now explains this (the §4 "code not changed" note is outdated) |
| Doc corrections listed in §4 | **done** | `HIGGSFIELD_DATA_INVENTORY.md` §5/§8, `MODEL_LOADING.md` §2.1/§5/§6–§9, `COST_FORMULAS.md` §4/§5.1/§5.3/§5.4/§8, `PRICING.md` §6.1/§10, `REVERSE_ENGINEERING.md` §5.2/§9/§16 |
| Academy course list from `fnf-academy/api/v1/courses` (adds `free_generations`) (§2.2) | open | `site --what academy` still reads the academy pages (SSR loader state) |
| Community-built apps from `fnf-apps-marketplace/api/v1/apps/community` (`credits_usage`) (§2.2) | open | not scraped |
| `applications/explore` as a JSON source for `site --what apps` (§2.2) | open (optional) | `site` keeps the HTML source |
| Discount fields `discount_percent_off` / `discount_duration*` flattened on plans (§3.1) | not done as sketched | plans keep the API's nested `discount` object |
| Team / paid-account shapes (seat bonus, credit price, admin capabilities, unlimited grants, scoped credits) | open | needs a team or paid account; kept as scrubbed generic objects in `account` |
