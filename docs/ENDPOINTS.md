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

| Endpoint | Contents | Scraper handling |
|---|---|---|
| `/subscriptions/v2/packages` | `{data: [{id, amount, original_amount, display_amount, credits, tax_amount, offer}], expire_days}`. **amount and credits are ×100** | `credit_package` (÷100, offer normalized, unknown fields kept) |
| `/subscriptions/bundle/unlim-catalog` | Unlimited add-on bundles | `auth_payload` (raw `data`) |
| `/workspaces/credit-price` | Price per credit for the workspace | `auth_payload` |
| `/subscriptions/v2/adjustable-credits` | Credit-slider tiers | `auth_payload` |

These shapes were inferred from JS mappers and have not been observed live. Unknown fields are kept rather than
dropped.

## Bonus: `GET https://higgsfield.ai/pricing.md`

An official markdown version of the US pricing page, with tables for individual and business plans, "best prices
right now" (for example the Black Friday banner), and per-plan inclusions. The scraper doesn't fetch it. It is
useful for checking `ps_a3` by hand.
