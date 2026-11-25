# Endpoint field reference (auto-generated)

Every JSON path seen in the raw responses of run `20261125-104415_tiers`, with observed types and one example.
Dynamic object keys are shown as `<placeholder>`; `[]` marks list items. Regenerate with
`python scripts/gen_endpoint_fields.py [RUN_DIR]`. Field meanings: see `ENDPOINTS.md`.

## `plans`

`GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?plan_set_key=…&with_localization=true` — 22 distinct paths from 4 response(s).

| path | types | example |
|---|---|---|
| `country_code` | str | "EG" |
| `plans[]` | list/object |  |
| `plans[].billing_period` | str | "monthly" |
| `plans[].credits` | int | 200 |
| `plans[].currency` | str | "usd" |
| `plans[].discount` | null/object |  |
| `plans[].discount.duration` | str | "once" |
| `plans[].discount.duration_months` | null |  |
| `plans[].discount.percent_off` | int | 30 |
| `plans[].final_monthly_price` | int | 1500 |
| `plans[].final_price` | int | 1500 |
| `plans[].id` | str | "8b52f333-0c16-4dd5-a7d6-eaa35865879f" |
| `plans[].name` | str | "Starter" |
| `plans[].offer` | null |  |
| `plans[].original_monthly_price` | int | 1500 |
| `plans[].original_price` | int | 1500 |
| `plans[].plan_type` | str | "starter" |
| `plans[].price_id` | str | "price_1TDRaKCmk0pn4HuHk3dzxwQj" |
| `plans[].product_id` | str | "prod_UBpEPiZy7OZggS" |
| `plans[].renew_monthly_price` | int | 1500 |
| `plans[].renew_price` | int | 1500 |
| `special_offer` | null |  |

## `compare`

`GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/compare?plan_set_key=…&billing_period=…` — 34 distinct paths from 8 response(s).

| path | types | example |
|---|---|---|
| `categories[]` | list/object |  |
| `categories[].description` | str | "Top-tier models to generate short videos from prompts, i… |
| `categories[].features[]` | list/object |  |
| `categories[].features[].detail` | str | "" |
| `categories[].features[].name` | str | "Concurrent Generations" |
| `categories[].features[].values` | object |  |
| `categories[].features[].values.<plan_type>` | object |  |
| `categories[].features[].values.<plan_type>.type` | str | "string" |
| `categories[].features[].values.<plan_type>.value` | bool/str | "1 concurrent generation" |
| `categories[].name` | str | "Video" |
| `categories[].slug` | str | "video" |
| `plan_set_key` | str | "default" |
| `plans[]` | list/object |  |
| `plans[].billing_period` | str | "annual" |
| `plans[].credits` | int | 0 |
| `plans[].currency` | str | "usd" |
| `plans[].discount` | null/object |  |
| `plans[].discount.duration` | str | "once" |
| `plans[].discount.duration_months` | null |  |
| `plans[].discount.percent_off` | int | 30 |
| `plans[].final_monthly_price` | int | 0 |
| `plans[].final_price` | int | 0 |
| `plans[].id` | str | "294f0023-0ece-4129-b2f6-1709f69be67c" |
| `plans[].name` | str | "Free" |
| `plans[].offer` | null |  |
| `plans[].original_monthly_price` | int | 0 |
| `plans[].original_price` | int | 0 |
| `plans[].plan_type` | str | "free" |
| `plans[].price_id` | str | "price_1R8rqbCmk0pn4HuHi0nab0I8" |
| `plans[].product_id` | str | "prod_S2xmRIOaWs973C" |
| `plans[].purchased` | bool | false |
| `plans[].renew_monthly_price` | int | 0 |
| `plans[].renew_price` | int | 0 |
| `plans[].seats` | int | 1 |

## `plan_benefits`

`GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plan-benefits?locale=en` — 105 distinct paths from 1 response(s).

| path | types | example |
|---|---|---|
| `cards` | object |  |
| `cards.<billing_period>[]` | list/object |  |
| `cards.<billing_period>[].availability` | null/object |  |
| `cards.<billing_period>[].availability.chip_label` | str | "Availability" |
| `cards.<billing_period>[].availability.note` | null/str | "Unlimited & free gens work only on higgsfield.ai" |
| `cards.<billing_period>[].availability.tooltip` | str | "Unlimited access and free generations are not available … |
| `cards.<billing_period>[].campaign` | null/object |  |
| `cards.<billing_period>[].campaign.ends_at` | null |  |
| `cards.<billing_period>[].campaign.footnote` | null |  |
| `cards.<billing_period>[].campaign.id` | str | "business_unlim_seedance_2_5" |
| `cards.<billing_period>[].campaign.show_availability` | bool | true |
| `cards.<billing_period>[].campaign.theme` | str | "business" |
| `cards.<billing_period>[].experiment` | null |  |
| `cards.<billing_period>[].plan_type` | str | "starter" |
| `cards.<billing_period>[].sections[]` | list/object |  |
| `cards.<billing_period>[].sections[].collapsed` | null/object |  |
| `cards.<billing_period>[].sections[].collapsed.count_override` | null |  |
| `cards.<billing_period>[].sections[].collapsed.dialog_title` | null |  |
| `cards.<billing_period>[].sections[].data` | null/object |  |
| `cards.<billing_period>[].sections[].data.action` | object |  |
| `cards.<billing_period>[].sections[].data.action.tab` | str | "business" |
| `cards.<billing_period>[].sections[].data.action.type` | str | "switch_tab" |
| `cards.<billing_period>[].sections[].data.credits_per_seat` | int | 400 |
| `cards.<billing_period>[].sections[].data.credits_rollover` | bool | false |
| `cards.<billing_period>[].sections[].data.cta` | null/object |  |
| `cards.<billing_period>[].sections[].data.cta.action` | object |  |
| `cards.<billing_period>[].sections[].data.cta.action.type` | str | "contact_sales" |
| `cards.<billing_period>[].sections[].data.cta.label` | str | "Contact sales" |
| `cards.<billing_period>[].sections[].data.expires_in_days` | int | 30 |
| `cards.<billing_period>[].sections[].data.grant` | null/object |  |
| `cards.<billing_period>[].sections[].data.grant.available_until` | null |  |
| `cards.<billing_period>[].sections[].data.grant.caps` | object |  |
| `cards.<billing_period>[].sections[].data.grant.caps.concurrency` | object |  |
| `cards.<billing_period>[].sections[].data.grant.caps.concurrency.count` | int | 1 |
| `cards.<billing_period>[].sections[].data.grant.caps.concurrency.per` | str | "member" |
| `cards.<billing_period>[].sections[].data.grant.caps.concurrency.pool` | null |  |
| `cards.<billing_period>[].sections[].data.grant.caps.max_duration_s` | int | 15 |
| `cards.<billing_period>[].sections[].data.grant.caps.max_resolution` | str | "720p" |
| `cards.<billing_period>[].sections[].data.grant.caps.options` | null |  |
| `cards.<billing_period>[].sections[].data.grant.caps.output_formats` | null |  |
| `cards.<billing_period>[].sections[].data.grant.caps.qualities` | null |  |
| `cards.<billing_period>[].sections[].data.grant.caps.resolutions` | null |  |
| `cards.<billing_period>[].sections[].data.grant.duration_days` | int | 7 |
| `cards.<billing_period>[].sections[].data.grant.requirements[]` | list/str | "business_verification" |
| `cards.<billing_period>[].sections[].data.grant.starts` | str | "on_purchase" |
| `cards.<billing_period>[].sections[].data.grant.type` | str | "unlimited" |
| `cards.<billing_period>[].sections[].data.model_label` | null/str | "Seedance 2.0" |
| `cards.<billing_period>[].sections[].data.starts_from_seat` | int | 3 |
| `cards.<billing_period>[].sections[].data.state` | str | "active" |
| `cards.<billing_period>[].sections[].fallback` | str | "generic" |
| `cards.<billing_period>[].sections[].icon` | null/str | "gift" |
| `cards.<billing_period>[].sections[].id` | str | "free_gens" |
| `cards.<billing_period>[].sections[].info` | null/object |  |
| `cards.<billing_period>[].sections[].info.text` | str | "Included free generations vary by model and plan. See ea… |
| `cards.<billing_period>[].sections[].kind` | str | "list" |
| `cards.<billing_period>[].sections[].rows[]` | list/object |  |
| `cards.<billing_period>[].sections[].rows[].description` | null |  |
| `cards.<billing_period>[].sections[].rows[].emphasis` | str | "none" |
| `cards.<billing_period>[].sections[].rows[].entitlement` | object |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.available_until` | null |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps` | object |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.concurrency` | null/object |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.concurrency.count` | int | 2 |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.concurrency.per` | str | "member" |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.concurrency.pool` | null/str | "image" |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.max_duration_s` | null |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.max_resolution` | null/str | "720p" |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.options` | null |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.options[]` | list/object |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.options[].max_duration_s` | int | 15 |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.options[].resolution` | str | "720p" |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.output_formats` | null |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.output_formats[]` | list/str | "png" |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.qualities` | null |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.qualities[]` | list/str | "low" |
| `cards.<billing_period>[].sections[].rows[].entitlement.caps.resolutions` | null |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.count` | int | 1 |
| `cards.<billing_period>[].sections[].rows[].entitlement.duration_days` | int/null | 7 |
| `cards.<billing_period>[].sections[].rows[].entitlement.of` | str | "unlimited" |
| `cards.<billing_period>[].sections[].rows[].entitlement.reason` | null/str | "annual_only" |
| `cards.<billing_period>[].sections[].rows[].entitlement.requirements[]` | list |  |
| `cards.<billing_period>[].sections[].rows[].entitlement.starts` | str | "on_purchase" |
| `cards.<billing_period>[].sections[].rows[].entitlement.type` | str | "free_gens" |
| `cards.<billing_period>[].sections[].rows[].icon` | null |  |
| `cards.<billing_period>[].sections[].rows[].id` | str | "genjutsu" |
| `cards.<billing_period>[].sections[].rows[].job_set_types[]` | list/str | "hf_mult_motion_control" |
| `cards.<billing_period>[].sections[].rows[].label` | str | "Higgsfield Genjutsu" |
| `cards.<billing_period>[].sections[].rows[].placement` | str | "primary" |
| `cards.<billing_period>[].sections[].rows[].tags[]` | list |  |
| `cards.<billing_period>[].sections[].rows[].tooltip` | null/str | "Unlimited on web while your subscription is active" |
| `cards.<billing_period>[].sections[].rows[].tooltip_links[]` | list |  |
| `cards.<billing_period>[].sections[].show_availability` | bool | false |
| `cards.<billing_period>[].sections[].slot` | str | "after_cta" |
| `cards.<billing_period>[].sections[].subtitle` | null/str | "Available on business plans only" |
| `cards.<billing_period>[].sections[].theme` | str | "exclusive" |
| `cards.<billing_period>[].sections[].title` | str | "Free generations" |
| `cards.<billing_period>[].tab` | str | "individual" |
| `locale` | str | "en" |
| `schema_version` | int | 1 |
| `tab_badges` | object |  |
| `tab_badges.<tab>` | object |  |
| `tab_badges.<tab>.icon` | str | "infinity" |
| `tab_badges.<tab>.label` | str | "30-day unlimited Seedance 2.5" |
| `tab_badges.<tab>.theme` | str | "business" |
| `valid_until` | null |  |

## `job_costs`

`GET https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs` — 85 distinct paths from 1 response(s).

| path | types | example |
|---|---|---|
| `data[]` | list/object |  |
| `data[].cost[]` | list/object |  |
| `data[].cost[].animation_mode` | str | "fully_animated" |
| `data[].cost[].audio` | object |  |
| `data[].cost[].audio.off` | float/int | 1.75 |
| `data[].cost[].audio.on` | float/int | 2.5 |
| `data[].cost[].base_credits` | int | 0 |
| `data[].cost[].batch_size` | object |  |
| `data[].cost[].batch_size.maximum` | int | 4 |
| `data[].cost[].batch_size.minimum` | int | 1 |
| `data[].cost[].batch_size.pricing` | str | "linear" |
| `data[].cost[].characters_per_block` | int | 50 |
| `data[].cost[].characters_per_second` | int | 15 |
| `data[].cost[].cost_per_second` | float/int | 0.75 |
| `data[].cost[].cost_units_denominator` | int | 70 |
| `data[].cost[].cost_units_numerator` | int | 3 |
| `data[].cost[].cost_units_per_block` | int | 23 |
| `data[].cost[].cost_units_per_credit` | int | 100 |
| `data[].cost[].cost_units_per_minute` | int | 400 |
| `data[].cost[].cost_units_per_second` | int | 10 |
| `data[].cost[].creativity` | int | 0 |
| `data[].cost[].credits` | float/int | 1.25 |
| `data[].cost[].credits_per_minute` | float | 4.0 |
| `data[].cost[].credits_per_second` | float | 0.1 |
| `data[].cost[].duration_rounding` | str | "ceil" |
| `data[].cost[].fallback_fps` | float | 25.0 |
| `data[].cost[].formula` | str | "character_blocks" |
| `data[].cost[].fps_matching` | str | "exact" |
| `data[].cost[].fps_multipliers[]` | list/object |  |
| `data[].cost[].fps_multipliers[].credits_per_second` | float | 3.0 |
| `data[].cost[].fps_multipliers[].fps` | int | 25 |
| `data[].cost[].frame_credits` | float | 3.5 |
| `data[].cost[].has_references` | bool | false |
| `data[].cost[].image_count` | int | 3 |
| `data[].cost[].image_credits` | float | 3.5 |
| `data[].cost[].input_fps` | int | 24 |
| `data[].cost[].is_estimate` | bool | false |
| `data[].cost[].max_fps` | int | 30 |
| `data[].cost[].max_frames` | int | 1800 |
| `data[].cost[].maximum_seconds` | int | 120 |
| `data[].cost[].min_fps` | int | 24 |
| `data[].cost[].minimum_cost_units` | int | 1 |
| `data[].cost[].minimum_seconds` | int | 1 |
| `data[].cost[].mode` | str | "pro" |
| `data[].cost[].model` | str | "topaz" |
| `data[].cost[].model_id` | str | "music_v1" |
| `data[].cost[].model_type` | str | "standard" |
| `data[].cost[].operation` | str | "generate" |
| `data[].cost[].original_cost_per_second` | float/int | 1.25 |
| `data[].cost[].original_credits` | float/int | 1.0 |
| `data[].cost[].output_fps` | int | 30 |
| `data[].cost[].quality` | str | "low" |
| `data[].cost[].reference_fps` | int | 24 |
| `data[].cost[].resolution` | str | "480p" |
| `data[].cost[].resolutions[]` | list/object |  |
| `data[].cost[].resolutions[].cost_per_second` | float/int | 3 |
| `data[].cost[].resolutions[].original_cost_per_second` | float/int | 6 |
| `data[].cost[].resolutions[].resolution` | str | "480p" |
| `data[].cost[].rounding` | str | "ceil" |
| `data[].cost[].seconds_per_block` | int | 10 |
| `data[].cost[].source_resolution` | str | "480p" |
| `data[].cost[].thinking` | str | "very-low" |
| `data[].cost[].unlimited` | object |  |
| `data[].cost[].unlimited.eligible` | bool | false |
| `data[].cost[].unlimited.maximum_batch_size` | int/null | 1 |
| `data[].cost[].video` | object |  |
| `data[].cost[].video.with_video` | object |  |
| `data[].cost[].video.with_video.cost_per_second` | float/int | 1.5 |
| `data[].cost[].video.with_video.original_cost_per_second` | float/int | 2.5 |
| `data[].cost[].video.without_video` | object |  |
| `data[].cost[].video.without_video.cost_per_second` | float/int | 0.75 |
| `data[].cost[].video.without_video.original_cost_per_second` | float/int | 1.25 |
| `data[].cost[].video_edit` | object |  |
| `data[].cost[].video_edit.cost_per_second` | float/int | 3.5 |
| `data[].cost[].video_edit.model` | str | "video_edit" |
| `data[].cost[].video_edit.original_cost_per_second` | float/int | 3.5 |
| `data[].cost[].video_hdr` | object |  |
| `data[].cost[].video_hdr.with_video` | object |  |
| `data[].cost[].video_hdr.with_video.cost_per_second` | float/int | 5.25 |
| `data[].cost[].video_hdr.with_video.original_cost_per_second` | float/int | 5.25 |
| `data[].cost[].video_hdr.without_video` | object |  |
| `data[].cost[].video_hdr.without_video.cost_per_second` | float/int | 4.5 |
| `data[].cost[].video_hdr.without_video.original_cost_per_second` | float/int | 4.5 |
| `data[].job_set_type` | str | "wan3_0" |
| `version` | str | "362779fa834b2dd181fc95ebeb66935c8fa117d96a62617b421439d4… |

## `pricing_config`

`GET https://pricing.higgsfield.ai/v2/pricing-config?locale=en[&planVersion=…]` — 172 distinct paths from 1 response(s).

| path | types | example |
|---|---|---|
| `versions` | object |  |
| `versions.<version>` | object |  |
| `versions.<version>.annual` | object |  |
| `versions.<version>.annual.billingOverrides` | object |  |
| `versions.<version>.annual.billingOverrides.monthly` | object |  |
| `versions.<version>.annual.billingOverrides.monthly.hiddenFeatureIds[]` | list/str | "one-more-unlimited" |
| `versions.<version>.annual.plans` | object |  |
| `versions.<version>.annual.plans.<plan_type>` | object |  |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods` | object |  |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>` | object |  |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits` | object |  |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.amount` | int | 6000 |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.label` | str | "credits per month" |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[].isBold` | bool | true |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[].prefix` | str | "+ 365 UNLIMITED" |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[].text` | str | "Nano Banana Pro" |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.credits.tooltip` | str | "~24000 images or ~1200 videos or ~200 character generati… |
| `versions.<version>.annual.plans.<plan_type>.billingPeriods.<billing_period>.price` | int | 0 |
| `versions.<version>.annual.plans.<plan_type>.credits` | object |  |
| `versions.<version>.annual.plans.<plan_type>.credits.amount` | int | 0 |
| `versions.<version>.annual.plans.<plan_type>.credits.label` | str | "Limited daily credits" |
| `versions.<version>.annual.plans.<plan_type>.credits.promoItems[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.credits.promoItems[].isBold` | bool | true |
| `versions.<version>.annual.plans.<plan_type>.credits.promoItems[].prefix` | str | "= 75" |
| `versions.<version>.annual.plans.<plan_type>.credits.promoItems[].text` | str | " Nano Banana Pro" |
| `versions.<version>.annual.plans.<plan_type>.credits.tooltip` | str | "~600 images or ~30 videos or ~5 character generations" |
| `versions.<version>.annual.plans.<plan_type>.customSections` | object |  |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>` | object |  |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].badges[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].badges[].color` | str | "#a3e635" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].badges[].label` | str | "UNLIMITED" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].icon` | str | "✕" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].id` | str | "kling-2.6" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].status` | str | "excluded" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].text` | str | "Unlimited Kling 2.6" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].textColor` | str | "#D1FE17" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.features[].tooltip` | str | "Get unlimited access for Kling 2.6 with audio, 5 s.\nBuy… |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.icon` | str | "cinematic" |
| `versions.<version>.annual.plans.<plan_type>.customSections.<section_id>.title` | str | "KLING BUNDLE" |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection` | object |  |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.features[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.features[].description` | str | "Share assets, folders, and presets instantly" |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.features[].icon` | str | "folder" |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.features[].id` | str | "workspace" |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.features[].status` | str | "included" |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.features[].text` | str | "Unified team workspace" |
| `versions.<version>.annual.plans.<plan_type>.everythingOnSection.title` | str | "EVERYTHING ON CREATOR AND..." |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].badges[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].badges[].color` | str | "primary" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].badges[].label` | str | "Extra" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].description` | str | "Flexible seat options under one team" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].icon` | str | "check" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].id` | str | "access-models" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].isHighlighted` | bool | true |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].status` | str | "limited" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].text` | str | "Access to selected models only" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].textColor` | str | "#ED1572" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].tooltip` | str | "Access to selected video and image models" |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].tooltipsByBillingPeriod` | object |  |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].tooltipsByBillingPeriod.eighteen_month` | str | "18-month plan: Models available: Seedance 1.0 Pro Fast 7… |
| `versions.<version>.annual.plans.<plan_type>.mainFeatures[].tooltipsByBillingPeriod.two_year` | str | "2-year plan: Models available: Seedance 1.0 Pro Fast 720… |
| `versions.<version>.annual.plans.<plan_type>.specialDeal` | str | "SPECIAL" |
| `versions.<version>.annual.plans.<plan_type>.tagline` | str | "Get started with AI content creation" |
| `versions.<version>.annual.plans.<plan_type>.ui` | object |  |
| `versions.<version>.annual.plans.<plan_type>.ui.ctaHelperText` | str | "Get one time offer, non-recurring" |
| `versions.<version>.annual.plans.<plan_type>.ui.ctaText` | str | "Get 2-day access" |
| `versions.<version>.annual.plans.<plan_type>.ui.fixedCreditsText` | str | "Fixed amount of 40 credits for 2 days" |
| `versions.<version>.annual.plans.<plan_type>.ui.priceSuffix` | str | "pay once, non-recurring" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess` | object |  |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].badges[]` | list/object |  |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].badges[].color` | str | "primary" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].badges[].label` | str | "365 UNLIMITED" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].icon` | str | "banana" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].id` | str | "image-gen" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].isHighlighted` | bool | true |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].status` | str | "excluded" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].text` | str | "Unlimited Image generations" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].textColor` | str | "#FFE500" |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.features[].tooltip` | str | "Unlimited Image Generation\n\nIncludes: Kling 01 Image, … |
| `versions.<version>.annual.plans.<plan_type>.unlimitedAccess.title` | str | "UNLIMITED ACCESS" |
| `versions.<version>.annual.variantOverrides` | object |  |
| `versions.<version>.annual.variantOverrides.pricing_v1` | object |  |
| `versions.<version>.annual.variantOverrides.pricing_v1.hiddenFeaturePatterns[]` | list/str | "one more" |
| `versions.<version>.monthly` | object |  |
| `versions.<version>.monthly.billingOverrides` | object |  |
| `versions.<version>.monthly.billingOverrides.monthly` | object |  |
| `versions.<version>.monthly.billingOverrides.monthly.hiddenFeatureIds[]` | list/str | "one-more-unlimited" |
| `versions.<version>.monthly.plans` | object |  |
| `versions.<version>.monthly.plans.<plan_type>` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.amount` | int | 6000 |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.label` | str | "credits per month" |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[].isBold` | bool | true |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[].prefix` | str | "+ 365 UNLIMITED" |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.promoItems[].text` | str | "Nano Banana Pro" |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.credits.tooltip` | str | "~24000 images or ~1200 videos or ~200 character generati… |
| `versions.<version>.monthly.plans.<plan_type>.billingPeriods.<billing_period>.price` | int | 0 |
| `versions.<version>.monthly.plans.<plan_type>.credits` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.credits.amount` | int | 0 |
| `versions.<version>.monthly.plans.<plan_type>.credits.label` | str | "Limited daily credits" |
| `versions.<version>.monthly.plans.<plan_type>.credits.promoItems[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.credits.promoItems[].isBold` | bool | true |
| `versions.<version>.monthly.plans.<plan_type>.credits.promoItems[].prefix` | str | "= 75" |
| `versions.<version>.monthly.plans.<plan_type>.credits.promoItems[].text` | str | " Nano Banana Pro" |
| `versions.<version>.monthly.plans.<plan_type>.credits.tooltip` | str | "~600 images or ~30 videos or ~5 character generations" |
| `versions.<version>.monthly.plans.<plan_type>.customSections` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].badges[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].badges[].color` | str | "#a3e635" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].badges[].label` | str | "5 Free gens" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].icon` | str | "kling" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].id` | str | "cinema-studio-video" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].status` | str | "excluded" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].text` | str | "Cinema Studio Video" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].textColor` | str | "#D1FE17" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.features[].tooltip` | str | "Get 5 free generations for Cinema Studio Video feature.\… |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.icon` | str | "cinematic" |
| `versions.<version>.monthly.plans.<plan_type>.customSections.<section_id>.title` | str | "Cinematic bundle" |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.features[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.features[].description` | str | "Share assets, folders, and presets instantly" |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.features[].icon` | str | "folder" |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.features[].id` | str | "workspace" |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.features[].status` | str | "included" |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.features[].text` | str | "Unified team workspace" |
| `versions.<version>.monthly.plans.<plan_type>.everythingOnSection.title` | str | "EVERYTHING ON CREATOR AND..." |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].badges[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].badges[].color` | str | "primary" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].badges[].label` | str | "Extra" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].description` | str | "Flexible seat options under one team" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].icon` | str | "check" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].id` | str | "access-models" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].isHighlighted` | bool | true |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].status` | str | "limited" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].text` | str | "Access to selected models only" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].textColor` | str | "#ED1572" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].tooltip` | str | "Access to selected video and image models" |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].tooltipsByBillingPeriod` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].tooltipsByBillingPeriod.eighteen_month` | str | "18-month plan: Models available: Seedance 1.0 Pro Fast 7… |
| `versions.<version>.monthly.plans.<plan_type>.mainFeatures[].tooltipsByBillingPeriod.two_year` | str | "2-year plan: Models available: Seedance 1.0 Pro Fast 720… |
| `versions.<version>.monthly.plans.<plan_type>.specialDeal` | str | "SPECIAL" |
| `versions.<version>.monthly.plans.<plan_type>.tagline` | str | "Get started with AI content creation" |
| `versions.<version>.monthly.plans.<plan_type>.ui` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.ui.ctaHelperText` | str | "Get one time offer, non-recurring" |
| `versions.<version>.monthly.plans.<plan_type>.ui.ctaText` | str | "Get 2-day access" |
| `versions.<version>.monthly.plans.<plan_type>.ui.fixedCreditsText` | str | "Fixed amount of 40 credits for 2 days" |
| `versions.<version>.monthly.plans.<plan_type>.ui.priceSuffix` | str | "pay once, non-recurring" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess` | object |  |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].badges[]` | list/object |  |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].badges[].color` | str | "primary" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].badges[].label` | str | "365 UNLIMITED" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].icon` | str | "banana" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].id` | str | "image-gen" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].isHighlighted` | bool | true |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].status` | str | "excluded" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].text` | str | "Unlimited Image generations" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].textColor` | str | "#FFE500" |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.features[].tooltip` | str | "Unlimited Image Generation\n\nIncludes: Kling 01 Image, … |
| `versions.<version>.monthly.plans.<plan_type>.unlimitedAccess.title` | str | "UNLIMITED ACCESS" |
| `versions.<version>.monthly.variantOverrides` | object |  |
| `versions.<version>.monthly.variantOverrides.pricing_v1` | object |  |
| `versions.<version>.monthly.variantOverrides.pricing_v1.hiddenFeaturePatterns[]` | list/str | "one more" |
