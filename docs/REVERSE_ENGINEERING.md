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

The scraper sets `ROBOTSTXT_OBEY = True`, uses AutoThrottle with a delay of at least 1 s, and makes about 6–75 requests
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
`python -m higgs_price scrape --sections plans --plan-sets all` captures every variant.

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
  `enterprise`.
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
