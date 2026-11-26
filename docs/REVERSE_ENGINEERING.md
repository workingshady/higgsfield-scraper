# Reverse-engineering findings: higgsfield.ai/pricing

**Target:** https://higgsfield.ai/pricing
**Date:** 2026-11-25
**Frontend build:** `45572506390-1-production`, git `cce99ad26d8c9accc238cbcb3f35d6a4cd83e650`

**Method:** plain HTTP from Python/curl (no browser, no cookies, no login). This work extends an earlier
browser-based report (`higgsfield_reverse_engineering_report.md`, logged-in Chrome, country EG).

Related documents:

| Document | Contents |
|---|---|
| [`ENDPOINTS.md`](ENDPOINTS.md) | What each endpoint returns and what every field means |
| [`ENDPOINT_FIELDS.md`](ENDPOINT_FIELDS.md) | Auto-generated list of every JSON path |
| [`../CLI.md`](../CLI.md) | How to run the scraper |
| [`higgsfield.postman_collection.json`](higgsfield.postman_collection.json) | Ready-made requests |
| [`MODEL_LOADING.md`](MODEL_LOADING.md) | How tools load models: JS registry, flags, param schemas, cost formulas, create/poll flow (§15) |
| [`PRICING.md`](PRICING.md) | Standalone pricing & plans reference with current snapshot |
| [`COST_FORMULAS.md`](COST_FORMULAS.md) | Credit and cost formulas for every model, scenarios, variation tables |
| [`PRODUCTS.md`](PRODUCTS.md) | Products → model ids → providers, examples, model catalog |
| [`JOBS_AND_STORAGE.md`](JOBS_AND_STORAGE.md) | Job ids, lifecycle, storage, library, chains, workflows |
| [`products/EDITING_ROOM.md`](products/EDITING_ROOM.md), [`products/PROPERTY_STUDIO.md`](products/PROPERTY_STUDIO.md) | Editing Room and Property Studio deep dives |
| [`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md) | Login audit (2026-11-26): what a session unlocks, every probed login endpoint, logged-in vs anonymous differences, service prefixes (§16) |

---

## 1. Executive summary

1. **The HTML contains no prices.** The page is a TanStack Start (React SSR) app. Every price, plan, model cost and
   benefit is fetched as JSON from `fnf-api-gw.higgsfield.ai` and `pricing.higgsfield.ai`.
2. **5 public endpoints** give the complete picture, with no auth, no signing, no CSRF and no cookies:
   `plans`, `compare`, `plan-benefits`, `job-sets/costs`, `pricing-config`.
3. **4 login-only endpoints** (top-ups, unlimited bundles, credit price, adjustable credits) need a Clerk session JWT.
4. **Prices vary by plan set, not by currency.** Everything is in **USD**. The frontend picks one of
   **25 `plan_set_key` values** based on a pricing tier (T1/T2/T3, or mobile). **`ps_a3` = the US price list**, which
   matches `https://higgsfield.ai/pricing.md` exactly.
5. **The country is detected from the IP address and cannot be overridden.** Headers and query parameters are
   ignored. The scraper does not try to spoof it.
6. **Model costs:** 86 models (`job_set_type`) in **55 different JSON shapes**, normalized by the scraper into
   524 typed price points.
7. **9 models appear only in the plan benefits** (Nano Banana Pro, Soul V2, Flux.2 Pro, Seedream 4.5 and 5.0 Lite,
   Kling O1 Image, …). They have no entry in `/job-sets/costs`.

## 2. Allowed scope (robots.txt and terms)

| Host | robots.txt | Our use |
|---|---|---|
| `higgsfield.ai` | 761 lines. `/pricing` and `/<locale>/pricing` are **allowed**. `/auth/`, `/payment/`, `/me/`, `/flow/`, `/library/`, … are disallowed | Recon only: one GET of `/pricing`, `/pricing.md` and the JS bundles |
| `fnf-api-gw.higgsfield.ai` | 404 (no rules) | The 5 public GET endpoints |
| `pricing.higgsfield.ai` | 302 → **Cloudflare Access login** (`fnf-web-pages.cloudflareaccess.com/cdn-cgi/access/login/…`). The host is behind Zero-Trust except for the public `/v2/pricing-config` path. The redirect is offsite, so Scrapy treats robots.txt as missing (`http/002_robots.txt_redirect__…`) | `pricing-config` |

The scraper does **not** obey robots.txt by default (owner decision; `--obey-robots` enables it). It uses AutoThrottle with a delay of at least 1 s, and makes about 6–75 requests
per run. It only calls the read-only GET endpoints listed below. The bundle also contains purchase, checkout and
offer-mutation endpoints, and these must **never** be called (§8).

## 3. Tech-stack fingerprint

| Layer | Finding | Evidence |
|---|---|---|
| Framework | **TanStack Start / Router** (React SSR, streaming hydration) | `assets.higgsfield.ai/tanstack/assets/8a801a77-*.js`; inline `$_TSR` and `self.$R["tsr"]` stream scripts; `dehydratedData.queryStream` |
| Data layer | react-query (`queryKey`, `queryFn`, `useQuery`) | bundle |
| Bundling | Vite-style hashed chunks: **176 JS chunks** referenced from the pricing HTML (~10 MB) | `page.html` |
| Auth | **Clerk** `clerk-js@6.46.3`, proxied at `https://higgsfield.ai/_clerk` | `<script src=…/_clerk/npm/@clerk/clerk-js@6.46.3/…>` |
| Payments | **Stripe** (`prod_*`, `price_*` IDs in the plans API) | `/subscriptions/v2/plans` |
| CDN / edge | Cloudflare | 302 page body, headers |
| API base | `https://fnf-api-gw.higgsfield.ai/fnf` | `data-fnf-api-url` attribute on the one-tap bootstrap script |
| i18n | `window.__HF_I18N__` → `l10n.higgsfield.ai/l10n/production/r/<hash>/<locale>.<hash>.json` | inline script |
| Locales | `en de es fr ja ko pt-BR zh-CN` | i18n assets |
| Build info | `window.__HF_BUILD__={"id":"45572506390-1-production","time":1795593855026,"git":"cce99ad…"}` | inline script |
| Feature flags | `window.__HF_FF = {"userId":null,"flags":{},"payloads":{}}` (anonymous) | inline script |
| Markdown twin | `<link rel="alternate" type="text/markdown" href="https://higgsfield.ai/pricing.md">` | `<head>` |
| Embedded state | No `__NEXT_DATA__`, `__NUXT__`, `__APOLLO_STATE__` or `ld+json`. The TSR stream holds only router state, not prices | grep of `page.html` |

## 4. Method (what was done, in order)

1. **robots.txt** for all 3 hosts (§2).
2. **Raw vs rendered:** fetched `/pricing` (237 KB HTML) and searched it for known prices such as "$49" and "Seedance".
   There were no price values, so the prices must come from XHR calls.
3. **Stack fingerprint** (§3).
4. **Downloaded all 176 JS chunks** referenced by the page into `samples/higgsfield/js/` (gitignored).
5. **Bundle mining:** searched for host literals (`https://*.higgsfield.ai`) and API path fragments
   (`/subscriptions/…`, `/job-sets/…`, `/workspaces/…`, `/user/offers…`, `pricing-config`), then extracted
   ±900 characters of context around each hit. This recovered the fetch functions, their query parameters,
   and the response mappers (for example cents → dollars).
6. **Resolved minified constants** (for example ``dS=`promo_link_code` ``, ``w_={T1:`ps_a3`,T2:`default`,T3:`max_v1`}``).
7. **Live probing** of every candidate endpoint without credentials, sorting them into 200 (public) and 401 (auth).
8. **Enumerated `plan_set_key`** by sending an invalid value. FastAPI's 422 response lists the whole enum (§6).
9. **Tested geo overrides** (`CF-IPCountry`, `X-Country-Code`, `?country_code=US`). All were ignored.
10. **Mapped every response shape** (55 cost shapes) and checked the normalized numbers against the site's own
    text. For example: Seedance 2.5 720p is 7 credits/s × 5 s = **35**, and `/compare` says "35 credits/5s".
    Plus annual is 1,200 × 12 credits for $360, which is **$0.025 per credit**.
11. **Built parsers, schemas, and tests** on the captured fixtures (`tests/fixtures/raw/`), then ran the scraper live.

## 5. Endpoint inventory

### 5.1 Public (no auth), used by the scraper

| # | Endpoint | Key params | Contents | Size |
|---|---|---|---|---|
| 1 | `GET /fnf/subscriptions/v2/plans` | `plan_set_key`, `with_localization`, `promo_link_code` | Stripe plans: list price, offer price, renewal price, discount, credits | ~9 KB |
| 2 | `GET /fnf/subscriptions/v2/compare` *(new)* | `plan_set_key`, `billing_period`, `with_localization` | Feature matrix for 6 categories, plus the Free plan and seat counts | ~90 KB |
| 3 | `GET /fnf/subscriptions/v2/plan-benefits` | `locale` (+ `Accept-Language`) | Pricing cards: unlimited models, free generations, caps, campaigns | ~175 KB |
| 4 | `GET /fnf/job-sets/costs` | none | Credit cost for each of 86 models, plus a `version` hash | ~76 KB |
| 5 | `GET https://pricing.higgsfield.ai/v2/pricing-config` | `locale`, `planVersion` | Marketing copy for plan versions v1…v51 | ~96 KB per version, ~4–6 MB for all |

Also public but not scraped: `GET https://higgsfield.ai/pricing.md`, an official markdown snapshot of the US prices
(kept in `samples/higgsfield/pricing.md` as a cross-check).

### 5.2 Login only (`Authorization: Bearer <Clerk JWT>`). These return 401 `{"detail":"Invalid or expired token"}` without it

| Endpoint | Contents (from JS mappers) |
|---|---|
| `GET /fnf/subscriptions/v2/packages` | Credit top-up packs. `amount`, `original_amount`, `display_amount`, `credits` and `tax_amount` are **all divided by 100** in JS. `offer` is `{type:"bonus", bonus_credits}` or `{type:"discount", amount_without_offer, savings}`. Also `expire_days` |
| `GET /fnf/subscriptions/bundle/unlim-catalog` | Unlimited-model add-on bundles |
| `GET /fnf/workspaces/credit-price` | Per-credit price for the workspace |
| `GET /fnf/subscriptions/v2/adjustable-credits` | Credit-slider tiers |

The token is the `__session` cookie from higgsfield.ai while logged in (DevTools → Application → Cookies). Clerk
rotates it about every 60 s.

A 401 here is not proof that a path is login-only: the `fnf` gateway answers 401 for *any* path without a token
(see §16). The full list of what a session unlocks is in [`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md).

### 5.3 Other paths found in the bundle (not called)

- **Read-ish, user-scoped:** `/subscriptions/active`, `/subscriptions/invoices`, `/workspaces/subscription`,
  `/workspaces/wallet`, `/workspaces/capabilities`, `/workspaces/details`, `/workspaces/invoices`,
  `/workspaces/pending-charges`, `/workspaces/pending-invoices`, `/workspaces/projects/usage-stats`,
  `/workspaces/seat-bonus`, `/subscriptions/bundle/all-unlim/status`, `/subscriptions/bundle/unlim/${id}`,
  `/user/offers`, `/user/offers/debug/${code}`, `/user/personal-promo`, `/credits/top-up-credits-expire`.
- **⚠️ Mutating (never call):** `/subscriptions/update`, `/subscriptions/change`, `/subscriptions/packages/instant`,
  `/subscriptions/bundle/purchase/instant(/unlim)`, `/subscriptions/plans/setup/pair`,
  `/workspaces/wallet/purchase-credits`, `/workspaces/wallet/auto-top-up(/…)`, `/workspaces/create-checkout-session`,
  `/workspaces/payment-cards(/…)`, `/workspaces/subscription/portal-link`, `/user/offers/${id}/skip|expire`.
- `POST /fnf/job-sets/costs` with a job body returns a quote for one specific job. It is not used, because the GET
  already returns the full price table.

## 6. How the frontend picks prices (de-minified from the bundle)

> Prices quoted in this section are from 2026-11-25 and some have since changed (e.g. Ultra annual on 2026-11-26).
> The complete, current reference, including all 25 plan sets (`ps_a7`, `mob_v1`, the `*_q` quarterly sets), is
> [`PRICING.md`](PRICING.md).

```js
// plan-set selection
const TIERS = ["T1", "T2", "T3"];
const PLAN_SET_BY_TIER = { T1: "ps_a3", T2: "default", T3: "max_v1" };
const MOBILE_PLAN_SET = "max_v2";
const MAX_FAMILY = new Set(["default_ww", "max_v1", "max_v2", "max_v3", "max_v2_q"]);
planSetKey = pricingOffer?.planSetKey                     // from ?fpr=<code> promo link or user metadata
          ?? (tier ? (isMobile ? MOBILE_PLAN_SET : PLAN_SET_BY_TIER[tier]) : "default");
// promo links: /pricing?fpr=<code> or /offer/<code>, mapped via {d94luc: {code: "default"}}

// plans fetch
async function fetchPlans(planSetKey, withLocalization, { promoLinkCode, signal }) {
  const p = new URLSearchParams({ plan_set_key: planSetKey, with_localization: String(withLocalization) });
  if (promoLinkCode) p.set("promo_link_code", promoLinkCode);
  const s = await (await fetch(api(`/subscriptions/v2/plans?${p}`), { signal })).json();
  return { plans: s.plans.filter(e => !["free_trial", "trial"].includes(e.plan_type) && e.plan_type !== "secret"),
           country_code: s.country_code, special_offer: s.special_offer };
}

// comparison table
fetch(api(`/subscriptions/v2/compare?${new URLSearchParams({plan_set_key, billing_period, with_localization})}`))
// -> {plans, annualDiscount: max(discount.percent_off of annual plans), categories}

// plan benefits
fetch(api("/subscriptions/v2/plan-benefits") + `?locale=${locale}`, { headers: { "Accept-Language": locale } })

// model costs (GET = full table; POST = quote for a single job)
fetch(api("/job-sets/costs"))

// "unlimited" model aliases
{ nano_banana_2: "nano_banana_pro_unlimited", gpt_image_2: "gpt_image_2_unlimited", kling3_0: "kling_3_unlimited" }
```

**Plan types known to the frontend:** `free basic pro lite standby ultimate creator starter plus ultra max secret`.
Upgradable plans: `pro ultimate creator plus ultra max`.

### All 25 `plan_set_key` values (from the API's 422 error)

```
mcp  default  default_basic  default_q  default_ww  default_ww_q
max_v1  max_v1_q  max_v1_seedance_2_5  max_v1_ultra
max_v2  max_v2_seedance_2_5  max_v2_q  max_v2_ultra  max_v3
ps_a1  ps_a2  ps_a3  ps_a3_basic  ps_a3_q  ps_a4  ps_a5  ps_a6  ps_a7  mob_v1
```

Observed differences between them (2026-11-25, country EG):

| plan set | Entry plan | Plus | Notes |
|---|---|---|---|
| `ps_a3` (US, tier T1) | Starter 270 cr $19 | 1,200 cr $59 → $40 (monthly) / $30 (annual) | matches `pricing.md` |
| `default` (T2) | Starter 200 cr $15 | 1,000 cr $49 → $35 / $25 | |
| `max_v1` (T3) | Basic 120 cr $9 | 1,000 cr $49 → $35 / $25 | |
| `max_v2` (mobile), `default_ww` | Basic 70 cr $5 | same as default | |
| `max_v2_q` | Basic 70 cr $5 | + **quarterly** Max plans (1,800 / 3,600 / 5,400 cr) | `billing_period: quarterly` |
| `max_v3` | Basic + Starter | annual-only Plus and Ultra | 10 plans |
| `mcp` | — | Plus and Ultra only | 4 plans (for MCP/CLI checkout) |

Ultra (3k / 6k / 9k credits), Team and Scale cost the same in every plan set.
`python -m higgsfield_scraper scrape --sections plans --plan-sets all` captures every variant.

## 7. Geo pricing

- Every plans response includes `country_code` (for example `EG`). The currency was `usd` in every response.
- Overrides tested and **ignored**: headers `CF-IPCountry: US` and `X-Country-Code: US`, and query `country_code=US`.
- So the only way to see another country's pricing is a real request from that country. The scraper does **not**
  do this. It records `meta.country_code` and uses `ps_a3` for US list prices.

## 8. Anti-bot and access notes

- The public endpoints worked with plain curl, urllib and Scrapy, using only `Accept: application/json` plus a normal
  browser User-Agent. No 403s, challenges or rate limiting were seen in about 100 requests.
- The bundle loads a DataDome-style tag (`dd.higgsfield.ai/js`, listening on `fnf-api-gw`). If 403s start appearing,
  **slow down or stop**. Evasion tooling is out of scope for this project.
- `COOKIES_ENABLED = False`, because the public data needs no session.

## 9. Data-shape findings

### Plans
- All money values are **integer cents**: `original_*` is before the offer, `final_*` is after the offer, and
  `renew_*` is the next renewal.
- `discount.duration`: `once` means only the first payment is discounted, so renewal goes back to list price.
  `forever` means renewals stay discounted. The scraper also writes `applies_to`.
- `credits` is **per month**, including on annual plans.
- Annual `original_monthly_price` can be higher than the monthly list price. For example, Ultra 6k is $258/mo
  annual list against $250 monthly list.
- Ultra has 3 credit tiers that share `plan_type`. The plan ID is a hash of
  `(plan_set_key, plan_type, billing_period, credits)`.
- `/compare` adds `seats` (Team 2, Scale 5: this is the minimum seat count) and the Free plan.

### Model costs (`/job-sets/costs`)
- The response is `{data: [{job_set_type, cost: [...]}], version: <sha256>}`. `version` changes whenever any price
  changes.
- There are **55 distinct shapes**. The normalization rules are:

| Raw pattern | Normalized to |
|---|---|
| `{"resolution":"720p","credits":2}` | dimension `resolution`, unit `credits_per_generation` |
| `cost_per_second` / `credits_per_second` | unit `credits_per_second` (example given for 5 s) |
| `original_<key>` | `original_credits`, plus `discount_percent` and `is_discounted` |
| `{"audio":{"on":2.5,"off":1.75}}` | dimension `audio=on/off`, per second (checked: Kling 3.0 std, audio off, 1.5 × 5 = 7.5 ≈ "~7 credits/5s") |
| `{"video":{"with_video":{…},"without_video":{…}}}` | dimension `video_input` |
| `{"video_edit":{"model":"video_edit",…}}` | `component = "video_edit"` |
| `{"model":"seedance_2_0","resolutions":[…]}` | the child list inherits the `model` dimension |
| `image_credits`, `frame_credits`, `base_credits` | extra units on the same price point |
| `is_estimate`, `reference_fps`, `max_frames`, `image_count` | `attributes`, not dimensions |
| `formula: character_blocks` | `credits_per_50_characters` = `cost_units_per_block / cost_units_per_credit` |
| `formula: input_duration` | `credits_per_minute` or `credits_per_second` |
| `formula: estimated_duration` | `credits_per_second` of estimated speech (`cost_units_per_second / 100`) |
| `formula: duration_blocks` | `credits_per_10_seconds` |
| `formula: linear_units` (qwen TTS) | `credits_per_character` = numerator / denominator / 100 (**unit assumed**, flagged `unit_assumed`) |
| `formula: input_duration_by_fps` | one point per `fps` (25 / 30 / 60) |

- Discounted models on 2026-11-25 (17): Seedance 2.0 and 2.0 Mini, Wan 3.0 and 3.0 Prime, GPT Image 2.5,
  Seedream 5.0 Pro, Kling 4.0 Flash, Flux video upscale, Cinematic Studio 3.0 and 3.5, Marketing Studio video,
  Happy Horse, the HF Mult / AI Influencer *flash* apps, and 3D Jutsu Angles.

### Plan benefits
- Each card is identified by `billing_period × tab × plan_type`. Team appears on both the `individual` and
  `business` tabs.
- Cards include legacy plan types that are no longer sold (`basic`, `lite`, `standby`, `pro`, `max`) plus
  `enterprise`. **Correction (login audit 2026-11-26, §16):** `lite` is still **sold to logged-in users**, as an
  annual plan (100 credits/month, $12/year, 85 % off forever on ps_a3). The anonymous `/plans` response omits it.
- Entitlement types: `unlimited` (with `duration_days`, for example 7 or 365, and `null` meaning while subscribed),
  `free_gens` (with `count`), `included`, and `none`.
- `caps` contains `max_resolution`, `max_duration_s`, and `concurrency{count, per: member, pool}`.
- `hero` sections carry a campaign grant without `job_set_types`, for example "7-day unlimited Seedance 2.0" with
  `requirements: ["business_verification"]`. The scraper records these as `label:<model label>`.
- `seat_bonus` section: 400 credits per seat starting from seat 3, expiring after 30 days, no rollover.
- Campaign on 2026-11-25: `business_unlim_seedance_2_5` ("30-day unlimited Seedance 2.5", business plans only).

### Marketing config
- 51 versions (`v1.0.0` → `v51.0.0`). `planVersion` accepts `v51.0.0` and also the fuzzy `v51`.
- Plans in v51: `free basic pro ultimate creator team enterprise-plan starter ultra plus scale max two_day_offer`.
- The `billingPeriods.*.price` values are **0**, so this endpoint is copy only. Real prices come from `/plans`.
- v1–v17 also contain `billingOverrides` and `variantOverrides`, which are not exported.

### `pricing.md` (US) on 2026-11-25
- "Black Friday sale: up to 70% off, ends 2026-11-26 00:00 UTC".
- Its numbers match the `ps_a3` plans exactly. This is the check behind the "US = ps_a3" conclusion.

## 10. Verification table

| Claim | How it was checked | Result |
|---|---|---|
| `ps_a3` = US prices | `pricing.md` table vs `plans?plan_set_key=ps_a3` | ✅ all 14 rows match |
| Plus annual $/credit | 360 / (1200 × 12) | ✅ $0.0250 |
| Seedance 2.5 720p = 35 cr / 5 s | cost 7/s vs `/compare` detail "35 credits/5s" | ✅ |
| Kling audio unit is per second | 1.5/s × 5 vs "~7 credits/5s" | ✅ |
| Annual compare counts are per year | Plus 14,400 credits / 35 = 411 vs "411 videos" | ✅ |
| Country override impossible | 3 override attempts | ✅ always EG |
| Every model parses | 86/86 models with ≥ 1 price point, 524 points, 0 validation errors | ✅ |
| Every plan set parses | `--plan-sets all` live run | ✅ (see `runs/*_all-plan-sets/manifest.json`) |

## 11. Change monitoring

| Signal | Meaning |
|---|---|
| `meta.costs_version` changed | Some model price changed. Diff `models[].price_points` |
| `plans[].pricing.after_offer` / `discount` / `special_offer` changed | The offer changed |
| New key in the 422 enum (`--plan-sets bogus`) | New plan set (pricing experiment) |
| New `vNN.0.0` in `pricing-config` | New packaging or copy |
| `__HF_BUILD__.git` changed in the HTML | New frontend build. Re-check the endpoints |
| New `campaign` in plan-benefits | New promotion |
| Non-200 status in `manifest.json → responses` | An endpoint moved or broke |

## 12. Re-doing the recon

```bash
mkdir -p samples/higgsfield && cd samples/higgsfield
curl -s https://higgsfield.ai/robots.txt -o robots.txt
curl -s -A "Mozilla/5.0" https://higgsfield.ai/pricing -o page.html
curl -s https://higgsfield.ai/pricing.md -o pricing.md
grep -o 'https://assets.higgsfield.ai/tanstack/assets/[^"]*\.js' page.html | sort -u > js_urls.txt   # then download
grep -ohE '[`"/](subscriptions|job-sets|workspaces|pricing-config|bundle)/[a-zA-Z0-9_/${}.?=&-]*' js/*.js | sort | uniq -c
curl -s "https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?plan_set_key=bogus"   # 422 lists plan sets
python scripts/gen_endpoint_fields.py        # refresh ENDPOINT_FIELDS.md from the latest run
```

---

## 13. Second round (2026-11-25): community, catalogs, projects, content, login

These findings come from the agents that built each scraper. Full details are in `docs/scrapers/<name>.md`.

### Login (Clerk)
- Frontend API is proxied at `https://higgsfield.ai/_clerk`, and `https://clerk.higgsfield.ai` is the same instance.
  Every call carries `__clerk_api_version=2026-11-18&_clerk_js_version=6.46.3` and `Origin: https://higgsfield.ai`.
- **Sign-in methods enabled:** password, email code, Google, Apple, GitHub, Microsoft and ChatGPT OAuth, and SSO/SAML.
  There is no instance-level MFA.
- **Password sign-in from a new device** returns `status=needs_second_factor` with `email_code` only. This is
  Clerk's client-trust check. The flow:
  `POST /v1/client/sign_ins` → `…/{id}/prepare_second_factor` → `…/{id}/attempt_second_factor` (code) →
  `created_session_id`.
- **Session tokens:** `POST /v1/client/sessions/{sid}/tokens` mints a fresh JWT (about 60 s). Only the long-lived
  `__client` cookie is needed; the cookie lasts up to 400 days.
- **Bot protection:** Turnstile is configured, but it's only required for sign-up. Clerk Protect may return
  `needs_protect_check`; the scraper stops there and never tries to bypass it. After 20 failed attempts the account
  is locked for 60 minutes.

### Community (`/publications/community/*`)
- **Page sizes:** trending and model-x max 50 (422 above), top 100, approved has no server cap (we use 200).
- **Cursors:** trending uses a decreasing float score; approved and model-x use a unix timestamp; top has a single
  page. `total` counts the items remaining after the cursor.
- **Filters:** `type` accepts `image|video|speak|upscale` only. Approved ignores `type`, and `model` filtering
  works on trending and approved only. These are filtered client-side where the API ignores them.
- **Videos are almost all in approved** (≈99% `viral_hub_video`); trending has about 10 videos in total.
- Each item carries the full `params` (prompt and every setting), its inputs, and results (raw/min, plus
  `hls`/`h264` for videos).
- `meta.cost` is the upstream provider's token usage, **not** Higgsfield credits.
- `profile.*` holds personal data, which is redacted from the archives unless `--with-profiles` is set.

### Catalogs
- `/motions?size=1000` returns all 419 motions in one page. 190 of them have a placeholder preview in the list;
  only `/motions/{id}` gives their real media.
- `/motion-samples` needs both `motion_id` and `size`. `/avatars` returns 500 for size > 200. `/avatar-presets` is
  public.
- **The real viral endpoint is `/viral-hub/presets/all`** (87 presets, each with a price matrix in credit units ÷ 100).
  `/viral-hub/presets` always returns `[]`.
- 18 catalogs are login-only (401): soul styles, mixed-media presets, per-model motions, katana, color presets,
  camera settings, marketing studio and others.
- **Correction (2026-11-26, tested with a login):** most of those 401s were the fnf gateway rejecting an unknown
  path before routing. With a session the same `fnf/<path>` URLs return **404 `Not Found`**. The JS helpers
  (core chunk `aXyXjC_KHBp09DNW.js`) use other bases: `Ixe(path, lang)` = `https://cms.higgsfield.ai{path}?lang=`
  (soul/cinematic/keyframe styles, veo3 styles, the six per-model motion lists, mixed-media presets, YouTube
  faceless presets, `marketing-studio-v2/catalog` and `/categories/{slug}/presets`) and `_V(path)` =
  `https://fnf-api-gw.higgsfield.ai/fnf-cms-api{path}` (katana categories/presets). On those bases they are
  **public**. Only `fnf/color-presets` and `fnf/camera-settings` really need a session. Details:
  `docs/scrapers/catalog.md`.
- **Comments** use `Axe()` = `https://fnf-api-gw.higgsfield.ai/fnf-community` (the separate Community posts
  service, public): `GET /publications/{id}/comments?limit&offset&parent_id`. Gallery publication ids do not exist
  there (`/fnf-community/publications/{gallery id}` 404; comments always `[]`), so gallery generations have no
  comments. `fnf/publications/{id}/comments` is 404 with a login. Details: `docs/scrapers/community.md`.

### Projects and contests
- **Page sizes:** `/project-publications` max 50, with a score cursor and no total. Contests and submissions max 100.
- `/contests` lists global contests only; weekly ones need `contest_type=weekly`.
- `/contest-participations/publications` (by `tab`) is the full public entry list for the film festival
  (~4.5k) and the talent contest.
- `/project-publications/{username}/{slug}` is the same record as `/{id}`, not an episode endpoint.

### Written content
- Company blog posts, help articles, case studies and the changelog are **not in the API**. They come from a CMS
  (Sanity) and are embedded in each SSR page as TanStack Router state (`$_TSR`, seroval format), which is parsed
  directly.
- Images, prompts and code blocks are carried in HTML comments, e.g. `<!--post-asset-block:{json}-->`.
- Talent and community post bodies (`content_url`) are binary Yjs v1 documents from a Lexical editor; they're decoded
  with no extra dependencies.

### Cost estimation sources
1. `/job-sets/costs` price points (exact when every price dimension is matched).
2. The `/subscriptions/v2/compare` feature details ("Higgsfield Soul 2.0 · 0.12 credits/image"), joined to
   job_set_types through the plan-benefit labels (approximate).
3. The viral preset price matrices, keyed by aspect ratio and resolution. On a live sample this priced 79% of
   community generations.

## 14. Third round (2026-11-25): site pages and leftover public APIs (`site` scraper)

Gap analysis against Appendix B of [`HIGGSFIELD_DATA_INVENTORY.md`](HIGGSFIELD_DATA_INVENTORY.md) and the 12 sitemaps:
every public (200) API path was matched against `scrapers/*/endpoints.py` and `constants.py`, and every sitemap page
type against the existing scrapers. Probes were polite GETs (≈ 1 req/s, a few pages per type), samples in
`samples/higgsfield/recon2/` (gitignored). Details and fields: [`scrapers/site.md`](scrapers/site.md).

### Findings
- **Every content page is TanStack Start SSR** with its loader data in `$_TSR.router` (seroval), exactly like the
  blog. No JSON API is needed (and the academy/apps APIs are 401 without login): the loaders hold apps
  (`appPreset` with `imageTemplate/videoTemplate/animateTemplate.cost` = credits per generation), academy courses and
  lessons (lesson text as an `mdxTree` HAST tree), MCP skills/bundles (agent prompts, example conversations),
  original-series episodes (views, likes, HLS video) and mixed-media presets (name, description, 6 samples — the
  `/mixed-media-presets` API is login-only, so the pages are the only public source).
- **Loader quirks:** blurred `data:image/webp;base64` placeholders (≈ 20 KB each) are embedded in app media and are
  stripped before archiving; `/apps/<slug>` is shared by apps (`kind: custom|app`) and the 8 category tabs
  (`kind: category`); `/apps` lists 84 apps but the sitemap has 98 URLs (8 categories + 8 apps not on the index, e.g.
  `mugshot`, `gtai`); `/apps/click-to-ad` renders the Marketing Studio route (no appPreset). Every academy page repeats
  the 17-course list in a layout loader (dropped on course/lesson pages).
- **Landing pages** (`/ai-image`, `/kling-3.0`, `/seedance/2.5`, `/plugins/*`, …) have **no loader data**; the content
  is SSR HTML. React streaming puts some sections at the end of `<body>` as `<div hidden id="S:n">`, referenced by
  `<template id="B:n">` placeholders — the extractor moves them back before converting `<main>` to Markdown. JSON-LD
  on these pages is rich: `SoftwareApplication` (with `offers.price`/`priceCurrency`), `HowTo` steps, `FAQPage`,
  `BreadcrumbList`, `ItemList`.
- **Rooms** (`/community/rooms/<slug>`, 73 URLs) render only head tags server-side; the chat is client-side and
  per-user. Only title/description/JSON-LD are collected, and only with `--what rooms`.
- **Effects** (`/effects/examples/<preset>`, 87) embed the same preset objects as `catalog`'s
  `/viral-hub/presets/all` (incl. `price_matrix`) plus a page of community samples: no new data, not built.
- **Leftover public APIs:** `/datetime-settings` (17 scheduled promo windows, some with per-plan free-generation
  params), `/business-unlim/state` (unlimited-model trial cards per team plan and billing period) and
  `/game-gift/networks` (PlayStation/Xbox gift amounts per country) are now scraped (`--what promos`).
  `/feature`, `/user/meta` (your IP's country/cohort), `/user/features`, `/youtube-faceless/hot-right-now` (empty) and
  `/contests/trending` (204) carry no catalog data and are skipped.
- No DataDome/Cloudflare challenge on any page type at ≈ 1 req/s; the framework still stops on a captcha.

## 15. Fourth round (2026-11-26): how tools load and call models

Full write-up: [`MODEL_LOADING.md`](MODEL_LOADING.md). Static analysis of build `548e0f3a` (580 chunks crawled from
the tool pages into `samples/higgsfield/js2/`, gitignored) plus GET-only probes (`samples/higgsfield/model_loading/`).

- The model list is **hard-coded in JS** (menu entries, `video-featured-model-ids`, plan tiers) and filtered at
  runtime by hashed feature flags embedded in every page as `window.__HF_FF`, by presence in `/job-sets/costs`
  (`pricedAs`), and by a retired-model set. No public "models" endpoint exists.
- Each job type's options come from a shared `defineJob({type, input, validate, toProvider, fromProvider, credits})`
  registry (~100 types). Seedance 2.5: 4–30 s, 480p–4k, 6 aspect ratios, `bitrate_mode`, `generate_audio`,
  batch 1–4, `model` default/video_edit/video_extension, draft, seed, media roles image/start_image/end_image/video/audio.
- Cost = live `/job-sets/costs` × JS formula (Seedance: `ceil(duration × cost_per_second[with_video|without_video]) ×
  batch`, edit uses the `video_edit` row). Generation = `POST /jobs/v2/{type}` `{params, use_unlim, …}` (from JS, not
  called); chains use `/chains/*`, apps `POST /workflows`; status by polling `POST /jobs/status-batch`.
- `scene_switch` appeared in `/job-sets/costs` with no frontend code yet: prices and availability can change without
  a deploy, new base models can't.

## 16. Fifth round (2026-11-26): login audit

Full write-up: [`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md). Build `548e0f3a`, one **free personal (non-team)** account,
GET only at about 1 req/s with `Authorization: Bearer <Clerk JWT>` and `Origin: https://higgsfield.ai`;
`hf-workspace-id` was added where the frontend sends it and never changed a response. Redacted samples:
`samples/higgsfield/login_audit/` (per-user endpoints saved as types only in `account_endpoint_shapes.json`).

**The gateway rule: 401 ≠ login-only.** `fnf-api-gw.higgsfield.ai/fnf/…` checks auth **before** routing, so *any*
path answers 401 without a token; with a token, an unknown path answers **404**. Most of the "login-only catalogs"
of the first inventory were such paths: the frontend calls them through a base helper that puts them on another
service, where they are **public**:

| JS call | Wrong guess | Real, public endpoint |
|---|---|---|
| `/series` | `/fnf/series` (401 anon / 404 auth) | `/fnf-series/series?limit=100` (35 series), `/fnf-series/series/{slug}` |
| `/api/v1/courses` | `/fnf/api/v1/courses` | `/fnf-academy/api/v1/courses` (17 courses) |
| `/applications/explore` | `/fnf/applications/explore` | `/fnf-cms-api/applications/explore?apps_per_category=20` |
| `/job-set-chain-presets` | `/fnf/job-set-chain-presets` | `/fnf-cms-api/job-set-chain-presets` (48, 58 with `show_hidden=true`; with credit prices) |
| `/restyle/presets` | `/fnf/restyle/presets` | `/fnf-cms-api/restyle-presets` (21) |
| `/notices` | `/fnf/notices` | `https://cms.higgsfield.ai/notices` = `/fnf-cms-api/notices` (10 per-model notices) |
| soul styles, per-model motions, mixed media, katana, faceless, marketing presets | `/fnf/<path>` | `https://cms.higgsfield.ai/<path>` or `/fnf-cms-api/<path>` (found in the previous commit; see `scrapers/catalog.md`) |

Only `/color-presets` and `/camera-settings` (catalog) really need a session. To place a path, find the base helper
in the JS (e.g. `Ixe(path, lang)` = `https://cms.higgsfield.ai{path}?lang=…`, `_V(path)` = `…/fnf-cms-api{path}`)
instead of trusting a 401.

**Service prefixes** on `https://fnf-api-gw.higgsfield.ai/` found in the bundle: `fnf`, `fnf-academy`, `fnf-ai-cmo`,
`fnf-aitys`, `fnf-apps-marketplace`, `fnf-campaign-api`, `fnf-cms-api`, `fnf-community`, `fnf-higgsclaw-cron`,
`fnf-meet`, `fnf-notification`, `fnf-score`, `fnf-series`, `fnf-skills-marketplace`.

**Logged-in vs anonymous differences** (the anonymous pricing scrape is not complete):

| Endpoint | Anonymous | Logged in |
|---|---|---|
| `/subscriptions/v2/plans?plan_set_key=ps_a3` | 14 plans | 15: + `lite` / annual, 100 credits/month, $12/year ($1/month), list $84, `discount {percent_off: 85, duration: "forever"}`. The 14 shared rows are byte-identical |
| `/job-sets/costs` | 87 rows, `version` `0cee3218…` | 88 rows, `version` `9048fa70…`: + `magi_2` (1080p, `base_credits` 0, `cost_per_second` 2.5). Stable over anon → auth → anon re-checks |
| `/user/features`, `/feature` | 3 flags / 1 legacy flag | identical |
| `window.__HF_FF` | 23 flags, `userId: null` | not readable with GET: the SSR page ignores a bare `__session` cookie; per-user flags are refreshed by a POST server function (out of bounds) |

Whether `lite` is offered to every logged-in user or only some cohorts is **unknown** (one account; `/user` and
`/user/meta` expose a `cohort` label, the likely selector, **inferred**). The scraper keeps the anonymous output and
adds the logged-in-only rows on request: `scrape pricing --logged-in-prices` (`visibility: "logged_in"`,
`meta.logged_in_prices` with both costs versions).

**What the session adds** (verified): the pricing deltas above; the account's own money state (`/user` balances in
credits, `/workspaces/wallet` balances in cost units ×100, `/workspaces/subscription`, `/v2/auto-top-ups/settings`
with `credits_per_dollar: 18`, free gens, generation seconds and packs, bundle status, `/workspaces/notice`); and the
account's own library (`/jobs/accessible` with the **actual charged `cost`** per job in cost units, assets, folders,
custom references, custom restyle presets, own mixed-media configs). Team-only endpoints answer 409
`workspace_is_not_shared` (`/workspaces/admin-capabilities`, `/workspaces/wallet/auto-top-up`) or 500
(`/workspaces/credit-price`) on a personal workspace. Implemented as opt-in: `scrape pricing --sections account`
(whitelisted wallet / subscription / top-up / bundle fields) and the `account` scraper
([`scrapers/account.md`](scrapers/account.md)).

**Cloudflare challenge on `/jobs/accessible` (not evaded).** During the audit, and for a single plain GET, the
endpoint answered 200. Requests from the Scrapy crawl of the `account` scraper got `403` with
`cf-mitigated: challenge`. The scraper records this in `meta.limits_hit` (`bot protection (cloudflare challenge) on
account_jobs`), ends the run `partial` and makes no attempt to get past it, so the estimate-vs-actual comparison
(`--compare-estimate`) has not run live yet.

## 17. Sixth round (2026-11-26): projects nested data

Target: the project page `/@<handle>/projects/<slug>` (route `#_private#profile#$username#projects#$projectSlug`),
`/contests/$slug` and `/@<handle>/projects`. Build `548e0f3a` (72 missing route chunks fetched into
`samples/higgsfield/js2/`; page HTML and raw responses in `samples/higgsfield/projects_nested/`, gitignored because
they hold real handles). GET only, ~1 req/s, anonymous first, then compared with a session.

* The SSR loader embeds only the publication (`project`, `info.information`, `info.stack`); `assets`, `document`
  (brief), comments and recommendations load client-side. The page model is `z8()` in `548e0f3a-H2odSMT_fOKI1GMn.js`;
  the assets/brief folder is chosen by `Fi()` (`snapshotFolderId`, else for contest entries `sourceFolderId` /
  `rootFolderId`).
* All the data is **public**: `/folders/{id}`, `/folders/{id}/children`, `/folders/{id}/items/v2`
  (`include_subfolders=true`, `size ≤ 100`, epoch-float cursor) carry every asset with its prompt, params, model
  (`job_set_type`) and media variants. No `hf-access-realm` header is needed (it changes nothing here).
* The **brief** is a Yjs CRDT snapshot of a Lexical document on a separate worker:
  `https://dam-editor-worker.higgsfield.ai/brief/{folder_id}/snapshot` (binary; `X-Brief-Updated-At`). The scraper
  decodes it with a small pure-Python Yjs v1 reader (`scrapers/projects/yjs.py`, YATA ordering) and renders
  Markdown (`brief.py`).
* **Comments** are on `fnf-community`: `/entities/project_publication/{id}/comments` (`limit`, `cursor`,
  `parent_id`, `order`). **Related** = `/project-publications/recommended?scope=…&current_publication_id=…`.
  **User projects** = `/fnf/user/{handle}/v2/publications?publication_type=project`.
* Stats: the page computes the stack percentages itself (count share, largest-remainder rounding to 0.1) and shows
  the size in decimal MB; credits are not scaled. Verified on "The Sea Walks Out": 59 generations, 5 064 credits,
  739.4 MB, 7 stack rows, 8 folder counts and 60 assets all match the page.
* `/jobs/{id}` and `/assets/{id}/public` answer a Cloudflare challenge (not evaded, not needed).
* Logged in vs anonymous: identical public data; a session only adds viewer state and a per-viewer feed order.
* Implemented as opt-in flags of `scrape projects` (`--with-project-assets/-brief/-stats/-comments/-related`,
  `--contest`, `--contest-tabs`, `--users`). Full write-up, field map, ER model and the anonymous/logged-in table:
  [`scrapers/projects.md`](scrapers/projects.md#nested-data-model-opt-in-2026-11-26).
