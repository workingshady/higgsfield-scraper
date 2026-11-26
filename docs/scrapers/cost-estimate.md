# Generation cost estimate

`higgsfield_scraper/estimate/estimator.py` → `CostEstimator`. It turns one generation (`job_set_type` + `params`)
into an `EstimatedCost` (schema in `higgsfield_scraper/estimate/__init__.py`).

```python
from higgsfield_scraper.estimate import CostEstimator
est = CostEstimator.from_job_costs_body(job_costs_body, usd_per_credit=0.025, usd_reference="ps_a3 plus annual")
est.estimate("seedance_2_5", {"resolution": "720p", "duration": 5, "medias": []}, media_type="video")
# {"status": "exact", "credits": 35.0, "unit": "credits_per_second", "unit_credits": 7.0, "quantity": 5.0,
#  "quantity_basis": "duration=5s", "matched": {"resolution": "720p", "video_input": "without_video"}, "usd": 0.875, ...}
```

> **It is an estimate.** It uses the list price per credit from `/job-sets/costs`, after the price table's own
> discount. It does **not** know what the user actually paid. Unlimited plans, free generations, campaign grants,
> team pools, retries/refunds and server-side rounding can all make the real charge different, often 0.
> `meta.cost` on a publication is the upstream provider's token usage, **not** Higgsfield credits.

## Method

1. **Pricing index.** The body goes through `parsers.costs.parse_job_costs`. That is the same normalizer the
   pricing scraper uses, so all 55 cost shapes become `price_points` with `dimensions`, `component`, `unit`,
   `credits` and `original_credits`.
2. **Model lookup.** The estimator tries the exact `job_set_type`, then `ALIASES`, then a separator-insensitive
   key (`kling4_0_flash` ≈ `kling_4_0_flash`). A separator-insensitive hit is always reported as `approximate`, with a
   note. `ALIASES` is **empty**: every priced `job_set_type` in about 1,000 community generations used the same id as
   the pricing. Models with no cost entry are not mapped to a sibling, because `nano_banana_2` ≠ `nano_banana_2_1`.
3. **Wanted dimensions.** The estimator only reads params for dimensions that this model's price points use, and
   ignores everything else.
4. **Point selection.** The estimator selects among main-rate points of the selected component, which means every
   unit except `base_credits`, `credits_per_image` and `credits_per_frame`. A point qualifies when each of its
   dimensions that appears in params is equal after normalization. It then ranks the qualifying points by
   *most matched dimensions* → *fewest unresolved dimensions* → *lowest credits*. Unresolved dimensions go to
   `assumed`. The default policy is therefore **lowest-cost**, so an approximate estimate is a lower bound.
5. **Quantity.** It is computed from the unit (table below). Add-on points with the same dimensions as the chosen
   point are added on top.
6. **USD.** `usd = credits × usd_per_credit` when a rate was given. `usd_reference` is passed through.

### Status

| status | when |
|---|---|
| `exact` | Every dimension of the chosen point came from params, every quantity input was present, and there was no fuzzy model match |
| `approximate` | Some dimension or quantity was assumed, a param value is not a pricing option, the model matched fuzzily, equal-fit points had different prices, or the price row is flagged `is_estimate` / `unit_assumed` |
| `unpriced` | There is no `/job-sets/costs` entry, the unit can't be computed (`formula` unit, or a characters-based price with no text), or there is no usable point |
| `skipped` | Never returned by the estimator. Callers use `estimate.skipped()` |

## Mapping tables

### Params → price dimensions (`PARAM_DIMENSIONS`)

The first non-empty key wins. Values are compared with `_norm`: lower-case, spaces removed, `-` treated as `_`,
bare `480/720/1080/…` becoming `…p`, and booleans becoming `true/false`. So `2K` matches `2k` and `1080` matches
`1080p`.

| Dimension | Param keys | Evidence (community params, 2026-11-25) |
|---|---|---|
| `resolution` | `resolution`, `output_resolution`, `target_resolution` | seedance_2_5/2_0, cinematic_studio_3_0, gpt_image_2*, nano_banana_2_1, seedream_v5_pro |
| `source_resolution` | `source_resolution`, `input_resolution` | upscalers (pricing only) |
| `quality` | `quality` | gpt_image_2 / 2_5 / 2_6 / 2_6_flare (`low…max`) |
| `mode` | `mode` | kling3_0 (`pro`) |
| `model` | `model`, `model_name` | seedance_2_0 (`seedance_2_0`), gpt_image_2_5 (`flare`/`sunburst`). Values that are not price options (for example gpt_image_2_6 `aurora-img-alpha`, seedance_2_5 `default`) are **ignored** silently, because they are internal engine names |
| `model_type`, `model_id`, `operation`, `creativity`, `animation_mode` | same name (`model_type` also `style_type`) | pricing only |
| `thinking` | `thinking`, `thinking_level` | p_image_ideogram (`very-low` = `very_low`) |
| `input_fps` / `output_fps` / `fps` | same name, plus `fps` | fps_boost, dubbing_lipsync |
| `audio` (on/off) | `sound`, `generate_audio`, `audio`, `with_audio`, `enable_audio`. A bool, `"true"` or `1` becomes `on` | kling3_0 `sound: "on"`. `generate_audio` (bool) appears on seedance_2_x and cinematic_studio_3_0, but those prices have no audio dimension |
| `video_input` | **derived**: `with_video` if `input_video`/`video`/`source_video`/`reference_video`/… is non-empty, or if any item in `medias`/`input_images`/`input_image`/`reference_elements` is a video (role, `data.type` or URL contains `video`/`.mp4`). Otherwise `without_video` when any media key exists. Not set when no media key exists | seedance_2_5 `medias[].role="image"`, kling3_0 `start_image`, all `data.type=media_input`/`*_job` |
| `video_hdr` (kling4_0) | the `video_input` value, but only when `hdr`/`video_hdr`/`is_hdr`/`enable_hdr` is truthy. In that case `video_input` is dropped | pricing only |
| `has_references` | `has_references`, or **derived**: true if `medias`/`input_images`/`reference_elements`/… is non-empty | ideogram_4_6 / ideogram_vector |

Component: the `video_edit` rows are used only when params has a truthy `video_edit`/`is_video_edit`/`is_edit`, or
`operation`/`mode` = `video_edit`/`edit`. Otherwise the main (component-less) rows are used.

### Unit → quantity

| Unit | Quantity | Missing input |
|---|---|---|
| `credits_per_generation` | `batch_size` / `num_images` / `n` / `num_outputs` / `count` (default 1) | 1, still `exact` (the API default) |
| `credits_per_second` | `duration` / `duration_seconds` / `video_duration` / … seconds × batch | **5 s assumed** → `approximate`, `assumed.duration=5`. This is the site's own reference length ("credits per 5 s") |
| `credits_per_minute` | duration / 60 | 60 s assumed |
| `credits_per_N_seconds` (duration_blocks) | `ceil(duration / N)` blocks | 60 s assumed |
| `credits_per_N_characters` (character_blocks) | `ceil(len(text) / N)` blocks, with text = `text`/`input_text`/`script`/`prompt` | `unpriced` |
| `credits_per_character` (linear_units, unit already flagged as assumed by the parser) | `len(text)` | `unpriced` |
| add-on `base_credits` | + once | — |
| add-on `credits_per_image` / `credits_per_frame` | × number of non-video items in `medias`/`input_images` plus `input_image`/`start_image`/`end_image` | 1 assumed |

## Validation on real data

On 2026-11-25 the estimator ran over 966 unique community generations: about 800 fetched from
`/publications/community/approved?model=…` and `/trending?model=…` (≈ 67 GET requests), plus the samples in
`samples/`.

| job_set_type | n | exact | approx | unpriced | credits min / median / max |
|---|---:|---:|---:|---:|---|
| viral_hub_video | 198 | 0 | 0 | 198 | – |
| text2image_soul_v2 | 79 | 0 | 0 | 79 | – |
| nano_banana_2 | 73 | 0 | 0 | 73 | – |
| soul_cinematic | 66 | 0 | 0 | 66 | – |
| wan2_5_video | 51 | 0 | 0 | 51 | – |
| image_auto | 50 | 0 | 0 | 50 | – |
| seedream_v4_5 | 50 | 0 | 0 | 50 | – |
| gpt_image_2_6 | 50 | 50 | 0 | 0 | 0.75 / 1.25 / 12 |
| nano_banana_2_1 | 50 | 50 | 0 | 0 | 1.5 / 2 / 12 |
| seedream_v5_pro | 50 | 50 | 0 | 0 | 1.25 / 2.5 / 10 |
| gpt_image_2_5 | 50 | 50 | 0 | 0 | 0.25 / 2 / 12 |
| seedance_2_0 | 50 | 50 | 0 | 0 | 67.5 (720p × 15 s) |
| cinematic_studio_3_0 | 44 | 44 | 0 | 0 | 75 (720p × 15 s) |
| seedance_2_5 | 35 | 35 | 0 | 0 | 49 / 210 / 480 |
| kling3_0 | 31 | 31 | 0 | 0 | 12.5 / 20 / 37.5 |
| gpt_image_2_6_flare | 28 | 28 | 0 | 0 | 1 / 1.75 / 3.5 |
| gpt_image_2 | 2 | 2 | 0 | 0 | 7 / 12 |
| nano_banana_flash, seedream_v5_lite, grok_image_2_0, text2image_soul | 9 | 0 | 0 | 9 | – |

**Totals:** 390 exact (40 %), 0 approximate, 576 unpriced (60 %). Every generation from a priced model resolved
exactly: community params always carry resolution/quality/mode/duration. All unpriced rows are models that have
no `/job-sets/costs` entry, such as Soul, Nano Banana 2, image_auto, the viral-hub app and Wan 2.5. Those models are
priced elsewhere, or covered by unlimited plans.

Sanity checks against the site's text:
- Seedance 2.5, 720p, 5 s → 7 × 5 = **35 credits** ✓ ("35 credits per 5 s").
- Kling 3.0 std, audio off, 5 s → 1.5 × 5 = **7.5** ✓ ("~7 credits/5s", REVERSE_ENGINEERING §9).
- Seedance 2.0 720p, 15 s → 4.5 × 15 = 67.5 (list price 90 before the 25 % discount).

## Limitations

- **List-price estimate only.** It ignores unlimited plans (`params.use_unlim=true` adds a note), free gens,
  campaign grants and refunds. `credits_before_discount` uses the price table's `original_*`.
- **Hidden surcharges.** seedance_2_5 `bitrate_mode="high"` (11 of 35 samples) and `generate_audio` on
  seedance/cinematic have no pricing dimension, so they are not priced. If the backend charges extra for them,
  the estimate is low.
- **Lowest-cost defaults.** When options are missing, the estimate is a lower bound.
- **Missing video duration** defaults to 5 s (`approximate`). Input-duration tools (upscale, dubbing, lip-sync) need
  the *input* duration, which community params usually do not carry.
- **Image add-ons** count input images in `medias`. For `reframe`, the price's `image_count: 3` attribute (likely
  output images) is not used.
- **Price drift.** Prices change: `costs_version` (sha256) identifies the table used. Old generations priced with
  today's table may not match what was charged at the time.
- Audio formula rounding (`rounding: ceil` on cost units) is approximated by block ceiling only.

## Version 2: the JS formulas (`--estimate-version 2`)

`higgsfield_scraper/estimate/v2.py` → `CostEstimatorV2` (+ `estimate/js_static.py`) is an **opt-in** second
estimator that follows the web app's own formulas ([`COST_FORMULAS.md`](../COST_FORMULAS.md) §4–§5) and fixes the
differences listed in [`COST_FORMULAS.md` §8](../COST_FORMULAS.md#8-our-estimator-vs-the-js-formulas). Everything
above this section describes v1, which stays the default and is unchanged: without the flag every output is
byte-identical to before (manifest, `meta.options`, CSV columns and `schema/dataset.schema.json` included).

```bash
python -m higgsfield_scraper scrape community --estimate-cost all --estimate-version 2
python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --estimate-version 2
```

```python
from higgsfield_scraper.estimate import estimator_class
est = estimator_class(2).from_job_costs_body(job_costs_body)          # estimator_class(1) is CostEstimator
est.estimate("seedance_2_5_flash", {"resolution": "480p", "duration": 5, "medias": [video]})["credits"]   # 13.0 (v1: 12.5)
```

**Output.** Same `EstimatedCost` shape plus `formula_version: 2` on every v2 estimate. v1 estimates have no such key,
and the field is only in the JSON Schema of datasets that contain it. Community runs record
`options.estimate_version: 2` (absent for v1), a `cost_basis` note and a "Formula version" line in `summary.md`.
Account runs record `options.estimate_version: 2` and a `pricing_basis.notes` entry (the comparison rows keep their
schema). `normalize` re-uses the run's manifest selection, so a run scraped with `--estimate-version 2` is
re-normalized with v2.

**Lookup order for job types without a `/job-sets/costs` row:** viral preset price matrix → static JS table
(`js_static.STATIC`, always `approximate`, `price_point_id: "js_static:<type>"`) → plan comparison table → `unpriced`.
v1 has no static step.

| §8 | rule in v2 | status |
|---|---|---|
| 1 | `ceil(d × cps) × max(1,b)` for Seedance 2.5/Flash/2.0/mini, Cinema 4.0, Happy Horse, Gemini Omni; `ceil(total)` for Kling 3.0 motion control (+2 with `is_chain`), Higgsfield Enhance, Marketing Studio video (+6·b with `web_product`) | fixed |
| 2 | edit = `params.model == "video_edit"` too; quantity = first input video's length (`duration_sec` / `durationSec` / `duration` on the media, its `data` or `meta`, or top-level `source_duration`), clamped 4–30 s for Seedance 2.5 / Flash. Without a source length the output `duration` is used (`assumed.source_duration`, approximate) — JS would show no price | fixed |
| 3 | no batch factor for Kling 4.0 / 4.0 Flash / 3.0 / Turbo / O3 / motion control, Wan 3.0 / Prime / 4.0, Grok v1.5 / Lite, Flux 3 video, Enhance, reframe (basis says "batch_size=N ignored") | fixed |
| 4 | Genjutsu / AI Influencer: `ceil(d) × cps × b` | fixed |
| 5 | reframe: `ceil(round(d) × cps + n_img × image_credits)`, `n_img` = row `image_count` (3) or `2·segments+1` | fixed |
| 6 | MiniMax TTS × batch (live row: `pricing: linear`; the UI ignores batch) | kept |
| 7 | Qwen: `max(minimum_cost_units, ceil(chars × 3/70)) / 100` | fixed |
| 8 | Seed Audio: seconds = `clamp(ceil(chars/15), 1, 120)` from the text (falls back to `duration` without text) | fixed |
| 9 | formula rows: `duration_rounding: floor` (dubbing, dubbing lipsync) then integer ceil; `ceil` minutes for video-to-music | fixed |
| 10 | default duration 4 s (Seedance 2.0 / mini, Cinema 3.0 / 3.5), 8 s (Gemini Omni / Flash 1.2), 10 s (Kling 4.0 / Flash), else 5 s | fixed |
| 11 | viral presets `ceil(units / 100)` | fixed |
| 12 | `ceil₀.₀₁` for Wan 3.0 / Prime / 4.0, GPT Image, voice change, Flux video upscale | fixed |
| 13 | Kling 3.0 / O3 without `sound` → `off` (main page default) | kept |
| 14 | Kling 3.0 / O3: `Σ multi_prompt[].duration` when `multi_shots` and `multi_shot_mode` is `custom` (or absent) | fixed |
| 15 | Wan edit: `ceil(Σ source s − 0.01)` on the `with_video` row | fixed |
| 16 | `cost_per_run`, `cost_per_piece`, `piece`, `masks_cost_per_frame`, `picture_cost`, `look_cost` are moved from dimensions to attributes; `cost_per_run` is added once (inferred → approximate) | fixed |
| 17 | static tables for Soul, Nano Banana 2 / 1 / Flash / Lite / upscale, Seedream / v4.5 / v5 Lite, Flux 2 / 3 image / Kontext, image_auto, Kling Omni, OpenAI Hazel, GPT text2image, Z-image, Marketing Studio image, faceswaps, Wan 2.2 image, Recraft styles, Veo 3.1 / Lite, Sora 2, Kling 2.6 / motion control / Omni video, MiniMax H3 / Max / Hailuo, Wan 2.5 / 2.6 / 2.7, Gemini Flash 1.1, Grok video, Seedance 1.0 / 1.5, FNF, Marketing hook, What-if, DoP, lipsync/speak, `*_unlimited` (0) | fixed (partly, see below) |
| 18 | `use_unlim` note: "batch_size > 1 → charged", "never unlimited" for magi_2 / wan4_0 / Flash types; credits stay the list price | fixed |
| 19 | GPT Image: `quality: auto` → high; missing quality/resolution or a missing combination → the high/2k row | fixed |

**Not implemented in v2 (left as v1):** Veo 3 (`Ok` table: unit unclear), Cinema Studio image (`Y` table not in the
doc), Grok image (`quality|pro` condition ambiguous), Reve (option key unknown), Kling video edit / reference (param
names unknown), Cinema Studio video v2, chunked-speak fallback, magi_2 (no anonymous row and no static table),
Topaz Hyperion / SAM 3 / depth video (need the frame count), and the "inferred" rounding of rows without a client
formula (videoshop, relight, inpaint, draw-to-video, scene_switch, ad multiplier …) — they keep the v1 product.
Lipsync job_set_type ids (`hf_speak_v2`, `wan2_5_speak`, `infinite_talk`, …) come from MODEL_LOADING.md and were not
seen in community data.

**Effect on real data** (3 community runs re-normalized with `--estimate-cost all`, 900 generations): 156 estimates
changed, all on job types without a costs row that the static tables now price (Soul, Nano Banana Flash, Seedream v4.5,
Flux 2, image_auto…); unpriced 244 → 167 (coverage 73 % → 81 %). Priced types in these runs (GPT Image, Nano Banana
2.1, Seedream v5 Pro, Seedance 2.5 generate, viral presets) gave the same numbers in v1 and v2.
