# Higgsfield pricing endpoints: what each one returns

> **This page covers the pricing endpoints.** The other scrapers' endpoints (params, page sizes, cursors, every field)
> are documented in [`scrapers/community.md`](scrapers/community.md), [`scrapers/catalog.md`](scrapers/catalog.md),
> [`scrapers/projects.md`](scrapers/projects.md), [`scrapers/blog.md`](scrapers/blog.md),
> [`scrapers/site.md`](scrapers/site.md) (apps, academy, MCP, original series, landings, promo APIs) and
> [`scrapers/cost-estimate.md`](scrapers/cost-estimate.md). Every endpoint, including the Clerk login flow, is in
> [`higgsfield.postman_collection.json`](higgsfield.postman_collection.json) (96 requests). The full site map is in
> [`HIGGSFIELD_DATA_INVENTORY.md`](HIGGSFIELD_DATA_INVENTORY.md).
> **How pricing works end to end** (plan math, plan sets, offers, benefits, model credits, snapshot): [`PRICING.md`](PRICING.md).


This document covers each endpoint's URL and parameters, auth, response structure, the meaning of every field, and
which output entity it becomes. For the complete list of every JSON path with types and examples, see
[`ENDPOINT_FIELDS.md`](ENDPOINT_FIELDS.md). For how these endpoints were found, see
[`REVERSE_ENGINEERING.md`](REVERSE_ENGINEERING.md).

**Base URLs**
- `API = https://fnf-api-gw.higgsfield.ai/fnf`
- `CFG = https://pricing.higgsfield.ai`

**Minimal headers:** `Accept: application/json`. The scraper also sends a Chrome User-Agent,
`Origin: https://higgsfield.ai` and `Referer: https://higgsfield.ai/pricing`.

**Money:** every amount in the raw responses is in **integer cents**. The scraper outputs **USD decimal strings**.

| # | Section (`--sections`) | Endpoint | Auth | Output entities |
|---|---|---|---|---|
| 1 | `plans` | `GET {API}/subscriptions/v2/plans` | — | `plan_set`, `plan` |
| 2 | `compare` | `GET {API}/subscriptions/v2/compare` | — | `comparison` (+ `seats` merged into `plan`) |
| 3 | `benefits` | `GET {API}/subscriptions/v2/plan-benefits` | — | `benefit_card` (+ joined into `plan`, `model`) |
| 4 | `models` | `GET {API}/job-sets/costs` | — | `model` → `price_points` |
| 5 | `marketing` | `GET {CFG}/v2/pricing-config` | — | `marketing_plan` |
| 6 | `auth` | `GET {API}/subscriptions/v2/packages` | Bearer | `credit_package` |
| 7 | `auth` | `GET {API}/subscriptions/bundle/unlim-catalog` | Bearer | `auth_payload` (raw) |
| 8 | `auth` | `GET {API}/workspaces/credit-price` | Bearer | `auth_payload` (raw) |
| 9 | `auth` | `GET {API}/subscriptions/v2/adjustable-credits` | Bearer | `auth_payload` (raw) |

---

## 1. Plans: `GET {API}/subscriptions/v2/plans`

Subscription plans with Stripe prices before the offer, after the offer, and on renewal.

| Query param | Required | Values | Effect |
|---|---|---|---|
| `plan_set_key` | no (defaults to `default`) | 25 keys, see `python -m higgsfield_scraper plan-sets` | Which price list. `ps_a3` = US |
| `with_localization` | no | `true` / `false` | Localized plan names |
| `promo_link_code` | no | Code from a `/pricing?fpr=<code>` link | Promo prices (not used by the scraper) |

An invalid `plan_set_key` returns **422**, and the error message lists every valid key.

**Response**

```json
{
    "plans": [ { …plan… } ],
    "country_code": "EG",
    "special_offer": null
}
```

| Field | Type | Meaning |
|---|---|---|
| `country_code` | str | Country detected from the caller's IP. Cannot be overridden |
| `special_offer` | null / object / str | Site-wide offer. In the `*_ultra` sets it is the string `"ultra"` (the plan to highlight) |
| `plans[].id` | uuid | Plan UUID (→ `plan_uuid`) |
| `plans[].plan_type` | str | `starter basic plus ultra max team scale` (`free_trial`, `trial` and `secret` are hidden by the site) |
| `plans[].name` | str | Display name |
| `plans[].credits` | int | Credits **per month**, also on annual plans |
| `plans[].billing_period` | str | `monthly`, `annual` or `quarterly` |
| `plans[].product_id` / `price_id` | str | Stripe product and price IDs |
| `plans[].original_price` | int (cents) | **Before offer**: list price for the whole billing period |
| `plans[].original_monthly_price` | int (cents) | Before offer, per month |
| `plans[].final_price` | int (cents) | **After offer**: what you pay now for the period |
| `plans[].final_monthly_price` | int (cents) | After offer, per month |
| `plans[].renew_price` | int (cents) | Price of the next renewal |
| `plans[].renew_monthly_price` | int (cents) | Renewal price per month |
| `plans[].currency` | str | Always `usd` so far |
| `plans[].discount` | null / object | `{percent_off, duration: once\|forever\|repeating, duration_months}` |
| `plans[].offer` | null / object | Personal or promo offer, when one applies |

**Becomes** a `plan` entity (prices in USD). It also adds derived fields:
- `pricing.{before_offer, after_offer, renewal}.{total, per_month}`
- `has_offer`
- `discount.applies_to` (`first_payment`, `all_payments` or `first_N_months`)
- `savings`
- `price_per_credit`
- `audience`
- `credits_per_period`

## 2. Compare: `GET {API}/subscriptions/v2/compare`

The comparison table: what each plan includes, and how many videos or images its credits buy.

| Query param | Values |
|---|---|
| `plan_set_key` | as above |
| `billing_period` | `monthly` / `annual` |
| `with_localization` | `true` |

**Response**

```json
{
    "plan_set_key": "ps_a3",
    "plans": [ { …same fields as /plans…, "purchased": false, "seats": 2 } ],
    "categories": [
        {
            "slug": "video",
            "name": "Video",
            "description": "…",
            "features": [
                {
                    "name": "Seedance 2.5 720p",
                    "detail": "35 credits/5s",
                    "values": {
                        "free": {"type": "bool", "value": false},
                        "plus": {"type": "string", "value": "411 videos"}
                    }
                }
            ]
        }
    ]
}
```

| Field | Meaning |
|---|---|
| `plans[]` | Includes the **Free** plan, plus `seats`, which is the minimum seat count (Team 2, Scale 5), and `purchased` |
| `categories[].slug` | `video`, `image`, `lipsync-studio`, `character`, `credits-usage`, `access-features` |
| `features[].name` | Model plus resolution (for example "Kling 3.0 1080p"), or a feature ("Commercial use") |
| `features[].detail` | Cost per unit as text: "35 credits/5s", "~22 credits/5s" (≈ means approximate), "2 credit/image" |
| `features[].values.<plan_type>` | `{type: bool\|string, value}`. Strings such as "411 videos", "Unlimited concurrent generations" or "Up to 480 generations". **Annual counts are per year** |

**Becomes** a `comparison` entity. The parsed fields are `approx`, `credits`, `per` (from `detail`) and
`quantity` / `quantity_unit` / `available` (from each value). Seats are copied into the matching `plan` by Stripe
price ID.

## 3. Plan benefits: `GET {API}/subscriptions/v2/plan-benefits`

The pricing-card content: unlimited models, free generations, caps, and campaigns.

| Query param / header | Values |
|---|---|
| `locale` + `Accept-Language` | `en de es fr ja ko pt-BR zh-CN` |

The response is the same for every plan set.

```json
{
    "schema_version": 1,
    "locale": "en",
    "valid_until": null,
    "tab_badges": {"individual": {"label": "30-day unlimited Seedance 2.5", "icon": "infinity", "theme": "business"}},
    "cards": {
        "monthly": [ { …card… } ],
        "annual":  [ { …card… } ]
    }
}
```

| Field | Meaning |
|---|---|
| `cards.<period>[].plan_type` | `starter basic lite standby pro plus ultra max team scale enterprise` (includes legacy plans) |
| `.tab` | `individual` / `business` (Team appears on both) |
| `.campaign` | Active promotion, for example `{id: "business_unlim_seedance_2_5", ends_at, footnote}` |
| `.availability` | Note: "Unlimited & free gens work only on higgsfield.ai" (not in MCP/CLI, Canvas or Supercomputer) |
| `.sections[].kind` | `list` (rows), `hero` (campaign grant in `data.grant`), `banner` (promo with `data.action`), `seat_bonus` (`data.credits_per_seat`, `starts_from_seat`, `expires_in_days`, `credits_rollover`) |
| `.sections[].id` | `unlimited`, `free_gens`, `business_unlim_hero`, `business_unlim_promo`, `seat_bonus`, `enterprise_volume_hero` |
| `.rows[].label` | Model display name ("Nano Banana Pro") |
| `.rows[].job_set_types[]` | **Join key** to `/job-sets/costs` model IDs |
| `.rows[].entitlement.type` | `unlimited`, `free_gens`, `included` or `none` (`none` means not on this plan; `of` says what is missing) |
| `.entitlement.count` | Number of free generations |
| `.entitlement.duration_days` | Unlimited window (7, 30, 365, or null meaning while subscribed) |
| `.entitlement.caps` | `max_resolution`, `resolutions`, `max_duration_s`, `qualities`, `output_formats`, `options`, `concurrency{count, per, pool}` |
| `.entitlement.starts` / `available_until` / `requirements` | `on_purchase`; deadline; for example `["business_verification"]` |
| `.rows[].placement` / `emphasis` / `tags` / `tooltip` | UI hints |

**Becomes** a `benefit_card` entity (one per `period × tab × plan_type`, 24 in total). It is also joined into
`plan.benefit_card_ids` / `unlimited_model_ids` / `free_gens` and into `model.entitlements`. Models referenced
here but missing from `/job-sets/costs` become `model` entries with `has_cost_data: false`.

## 4. Model costs: `GET {API}/job-sets/costs`

The credit cost of every generation model or tool. There are no parameters.

```json
{
    "data": [ {"job_set_type": "seedance_2_5", "cost": [ … ]} ],
    "version": "362779fa…"
}
```

| Field | Meaning |
|---|---|
| `version` | sha256 of the price table. It changes whenever any price changes |
| `data[].job_set_type` | Model ID (→ `model_id`) |
| `data[].cost[]` | List of price entries in one of **55 shapes** (see below) |

**Cost vocabulary**

| Key | Meaning | Output unit |
|---|---|---|
| `credits` | Per generation or image | `credits_per_generation` |
| `cost_per_second`, `credits_per_second` | Per second of output (or input) | `credits_per_second` |
| `credits_per_minute` | Per minute of input | `credits_per_minute` |
| `image_credits` (+ `image_count`) | Per input image | `credits_per_image` |
| `frame_credits` | Per frame | `credits_per_frame` |
| `base_credits` | Flat cost per job | `base_credits` |
| `original_<key>` | Before discount | → `original_credits` |
| `resolution`, `source_resolution`, `quality`, `mode`, `model`, `model_type`, `model_id`, `operation`, `thinking`, `has_references`, `creativity`, `input_fps`, `output_fps`, `animation_mode` | Selectable options | → `dimensions` |
| `audio: {on, off}` | Price with or without generated audio, per second | dimension `audio` |
| `video: {with_video, without_video}` | Price with or without an input video | dimension `video_input` |
| `video_edit: {…}` | Separate "edit" operation | `component = "video_edit"` |
| `resolutions: [...]` | Nested list under a `model` | inherits `model` |
| `is_estimate`, `reference_fps`, `max_frames` | Metadata | → `attributes` |
| `formula` + `cost_units_*`, `characters_per_block`, `seconds_per_block`, `fps_multipliers`, `rounding`, `batch_size`, `unlimited` | Audio and TTS pricing formulas | → `formula` + computed unit |

The full normalization table is in `REVERSE_ENGINEERING.md` §9.

**Becomes** a `model` entity with these fields:
- `options`: every selectable value for each dimension
- `price_points[]`: one entry per combination
- `units`, `components`, `has_discount`, `min_credits`, `max_credits`, `entitlements`
- `example`: for example the credits for 5 s
- `usd_estimate`: priced at the `--usd-reference` plan's after-offer $/credit

## 5. Marketing config: `GET {CFG}/v2/pricing-config`

Marketing copy for the plan cards, for every historic version.

| Query param | Values |
|---|---|
| `locale` | `en` … |
| `planVersion` | `v51.0.0` (fuzzy `v51` also works). **Omit it to get all 51 versions** (~4–6 MB) |

```json
{
    "versions": {
        "v51.0.0": {
            "monthly": {"plans": { "<plan>": { …plan copy… } }},
            "annual":  {"plans": { … }}
        }
    }
}
```

| Plan-copy field | Meaning |
|---|---|
| `tagline` | One-line pitch |
| `credits.{amount, label, tooltip, promoItems[]}` | Credits headline, for example "~600 images or ~30 videos"; promo lines `{prefix, text, isBold}` |
| `mainFeatures[]` | `{id, text, status: included\|excluded\|limited, tooltip}` |
| `unlimitedAccess.{title, features[]}` | Unlimited or free-gens list |
| `customSections.<id>.{title, features[]}` | Extra blocks, for example "7-Day Unlimited" |
| `everythingOnSection` | Team-workspace feature list (`description`, `icon`) |
| `billingPeriods.<period>.{price, credits}` | **price is always 0**. Real prices come from `/plans` |
| `specialDeal`, `ui` | Badge text ("SPECIAL"); CTA texts for `two_day_offer` |

Plans in v51: `free basic pro ultimate creator team enterprise-plan starter ultra plus scale max two_day_offer`.

**Becomes** a `marketing_plan` entity (one per `version × period × plan`).

## 6–9. Login-only endpoints

Send `Authorization: Bearer <Clerk JWT>` (the `__session` cookie). Without it they return
`401 {"detail":"Invalid or expired token"}`.

| Endpoint | Observed live 2026-11-26 (logged in, personal account) | Scraper handling |
|---|---|---|
| `/subscriptions/v2/packages` | 200 `{data: [{id, price_id, amount, original_amount, display_amount, credits, currency, credits_per_dollar, discount, features[{display_number, text, type, is_available}], is_highlighted, tax_amount, tax_rate, offer}], expire_days: 90}`. **amount (cents) and credits are ×100.** 6 packs: 100 / 200 / 500 / 1,000 / 2,000 / 4,000 credits; e.g. 100 credits = $6.25 (list $8.50, `discount` 26, `credits_per_dollar` 16) | `credit_package` (÷100, every field declared) → `auth.credit_packages[]`, `csv/auth_credit_packages.csv` |
| `/subscriptions/bundle/unlim-catalog` | 200 `{"bundles": []}` (no bundles offered to this account) | `auth_payload` (raw) |
| `/subscriptions/v2/adjustable-credits` | 200 `{data: [12 tiers with the same fields as packages, + is_default], expire_days, iteration: 2000}`, e.g. 5,000 credits = $250.75 (list $425, 41 % off) | `auth_payload` (raw) |
| `/workspaces/credit-price` | **500** for an account without a team workspace. The site calls it only from the team "buy credits" screen | warning + stat `higgs/auth/http_error/credit_price/500`; run stays `success` |

How to log in and scrape them: `PRICING.md` §10 and `CLI.md` (Logged-in pricing).

### Logged-in differences on the public endpoints (opt-in `--logged-in-prices`)

Audited 2026-11-26 (`docs/LOGIN_COVERAGE.md`); `hf-workspace-id` changes nothing.

| Endpoint name | Request | Logged in vs anonymous | Scraper handling |
|---|---|---|---|
| `plans_logged_in` | `/subscriptions/v2/plans?plan_set_key=…&with_localization=true` + Bearer | ps_a3: **15** plans vs 14. Extra `lite` / `annual`: `credits` 100, `final_price` 1200 (=$12/yr, $1/mo), `original_price` 8400, `discount {percent_off: 85, duration: "forever"}`, `offer: null`. The 14 shared rows are byte-identical | logged-in-only plans appended with `visibility: "logged_in"`; anonymous rows unchanged |
| `job_costs_logged_in` | `/job-sets/costs` + Bearer | **88** rows vs 87, `version` `9048fa70…` vs `0cee3218…`. Extra `magi_2`: `[{resolution: "1080p", base_credits: 0, cost_per_second: 2.5, original_cost_per_second: 2.5}]` | `magi_2` model appended with `visibility: "logged_in"`; both versions in `meta.logged_in_prices` |

### Account endpoints (opt-in `--sections account`, login only)

| Endpoint name | Request (GET) | Shape (wire) | Kept by the scraper |
|---|---|---|---|
| `account_wallet` | `/workspaces/wallet` | `{workspace_id, credits_balance, subscription_balance, total_credits, on_demand_credits, bonus_credits, bonus_credits_expire_at, expire_days, credit_limit, group_credit_allocation, allocation_cycle, next_credit_allocation_date, wallet_created_at, scoped_credits[]}`; **balances in cost units (×100)**: `888` = 8.88 credits | balances ÷100 → credits, dates, `expire_days`, `credit_limit`, `scoped_credits[]` (balance ÷100); no ids |
| `account_subscription` | `/workspaces/subscription` | 34 keys: `subscription_id, workspace_id, plan_name, plan_type, status, billing_cycle, *_seats, credits_per_seat, current_period_start/end, payment_status, plan_version, email_type, …` | plan/seat/period/status fields; no ids, no `email_type`, no payment message |
| `account_auto_top_up` | `/v2/auto-top-ups/settings` | `{state, is_eligible, is_on_demand_only, threshold, refill_options[], options[], selected_option, default_option, credits_per_dollar (18), current_refill_amount, on_demand_credits, modal_type, currency, expire_days, outstanding_amount}` | all but `outstanding_amount` / `modal_data` |
| `account_free_gens` | `/user/free-gens/v2` | `{items: []}` | `items[]` (scrubbed) |
| `account_generation_seconds` | `/user/generation-seconds` | `{items: []}` | `items[]` |
| `account_generation_seconds_packs` | `/generation-seconds/packs` | `{items: []}` (401 anonymous) | `items[]` |
| `account_bundle_all_unlim_status` | `/subscriptions/bundle/all-unlim/status` | `{is_eligible_to_purchase, has_all_unlims}` | both |
| `account_bundle_seedance_unlimited` | `/subscriptions/bundle/seedance-unlimited` | `{tiers: []}` | `tiers[]` |

Not scraped on purpose: `/user`, `/user/profile`, `/user/meta`, `/workspaces*` ids/details (personal data or UI
permissions), invoices (private billing). List items keep scalars only, without id / url / personal keys.

## Bonus: `GET https://higgsfield.ai/pricing.md`

An official markdown version of the US pricing page, with tables for individual and business plans, "best prices
right now" (for example the Black Friday banner), and per-plan inclusions. The scraper doesn't fetch it. It is
useful for checking `ps_a3` by hand.
