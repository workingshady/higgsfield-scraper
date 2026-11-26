# How Higgsfield computes credits and cost

How the Higgsfield web app turns a model choice plus its options into a credit price, how the account (unlimited
grants, free gens, generation seconds, discounts, workspaces) changes what is actually charged, and what a credit is
worth in USD per plan.

**Date:** 2026-11-26. **Build studied:** `548e0f3a` (`samples/higgsfield/js2/`, 580 chunks; chunk names below drop
the `548e0f3a-` prefix). **Live data:** `GET /job-sets/costs` version `0cee3218…` (87 job types, identical to
`samples/higgsfield/model_loading/job_sets_costs.json`), pricing run `runs/20261126-090255_costs-ref` (plan set
`ps_a3`, US prices). **Method:** static reading of the public JS plus public GETs. No login, no POST, no generation,
no bot-protection bypass. Every formula cites a chunk and a short excerpt; anything not seen in code is marked
**inferred**.

> Related: [`MODEL_LOADING.md`](MODEL_LOADING.md) (model registry, `defineJob`, routes, gating),
> [`ENDPOINTS.md`](ENDPOINTS.md) (`/job-sets/costs` fields), [`scrapers/cost-estimate.md`](scrapers/cost-estimate.md)
> (our estimator). Regenerate the two appendices with `python scripts/gen_cost_tables.py --write docs/COST_FORMULAS.md`
> and `python scripts/gen_cost_tables.py --variations --write docs/COST_FORMULAS.md`.

---

## 1. TL;DR: the master equations

```
quote (UI)   = F_type( settings, media, rows )                  rows = GET /job-sets/costs[job_set_type].cost
                                                                       (static table in the bundle as fallback)
charged      = 0                         if use_unlim and an active unlimited grant covers the settings (batch ≤ 1)
             = 0 credits, −1 free gen    if use_free_gens and the model has free gens left (unlim wins over free gens)
             = 0 credits, −N seconds     if use_generation_seconds and a seconds grant covers model + resolution
             = server price (cost units / 100) otherwise   ← the UI number is a client-side copy of this
USD          = charged × plan_price / credits_per_period    (e.g. plus annual after offer: $0.025 / credit)
```

`F_type` comes in a handful of shapes (§3). The ones that cover >90 % of what users run:

| shape | formula (JS) | used by |
|---|---|---|
| per second, integer ceil, × batch | `Math.ceil(duration × cps) × max(1, batch)` | Seedance 2.5 / Flash, Cinema Studio 4.0, Seedance 2.0 / mini, Happy Horse, Gemini Omni |
| per second, no rounding | `duration × cps` (× batch for some) | Kling 4.0 / 4.0 Flash / 3.0 / O3 / 3.0 Turbo, Grok v1.5, MiniMax H3, Gemini Omni Flash 1.2, Flux 3 video |
| per second, rounded up to 0.01 credit | `ceil₀.₀₁(duration × cps)` (`Es()`) | Wan 3.0 / Prime, video upscale/processing tools, voice change |
| per image | `batch × credits[resolution][quality…]` (GPT Image: `ceil₀.₀₁`) | all image models |
| per text block | `ceil(chars / 50) × rate` | ElevenLabs v3/v4, MiniMax/Seed speech TTS |
| fixed | `template.cost`, `ceil(credit_units / 100)` | apps, viral-hub presets |
| server quote | `POST /job-sets/costs` or `POST /jobs/{route}?dry_run=true` | motion-control chains, Topaz image/video |

`cps` = `cost_per_second` of the matching row; the strike-through ("was") price uses `original_cost_per_second` /
`original_credits` with the **same** formula. Credits are fractional; the backend works in **cost units = credits ×
100** (`cost_units_per_credit: 100`), which is why the finest rounding anywhere is 0.01 credit.

---

## 2. Glossary

| term | meaning |
|---|---|
| `job_set_type` | API model id (`seedance_2_5`). The UI's model-version id (`seedance_2_5_edit`) maps onto it ([MODEL_LOADING §2.2](MODEL_LOADING.md)) |
| row | one element of `cost[]` in `/job-sets/costs` for a type (usually one per resolution) |
| `cps` | `cost_per_second` in credits; `original_cost_per_second` = list price before a discount |
| `credits` / `original_credits` | per-generation price for image models |
| `video.with_video` / `video.without_video` | per-second rate when the request does / does not carry a reference **video** |
| `video_edit` | per-second rate in edit mode (`model: "video_edit"`), charged on the **source** length |
| `video_hdr` | Kling 4.0 HDR rates (`dynamicRange: "hdr"`, 1080p/4k only) |
| `audio.on` / `audio.off` | Kling 3.0 family rate by `sound` |
| `base_credits` | fixed add-on per generation (0 on Gemini Omni today) |
| `image_credits`, `frame_credits` | add-on per generated image / input frame (reframe, videoshop relight, draw-to-video) |
| `formula` rows | server-side audio formulas: `character_blocks`, `estimated_duration`, `linear_units`, `input_duration`, `input_duration_by_fps`, `duration_blocks` |
| cost unit | 1/100 credit; quotes return `cost` in units and `credits` = units / 100 |
| `ceil₀.₀₁(x)` | JS `Es(x) = Math.ceil(Number((x*100).toFixed(6)))/100` (`fmaPQSnk2K7UZee5.js`) |
| batch | `batch_size` 1–4 (image/video models); multiplies the price unless noted |
| `use_unlim`, `use_free_gens`, `use_generation_seconds`, `use_free_daily_credits` | billing flags sent with the job (§5) |

---

## 3. Pricing primitives

The client never hard-codes a final price for a model that has live rows: every cost function receives the live rows
first and a static table second. `IbXroQBX75V1ZnAd.js` (the `defineJob` framework) wires it:

```js
credits: t(r.credits, r.fallbackCosts), costsJobSetType: r.costsJobSetType,
// fmaPQSnk2K7UZee5.js
function Ds(e,t=[]){return{find:(n,r=ks)=>{…Ts(e?.find(n),r) ?? Ts(t.find(n),r)}}}   // live rows, then static
function Os(e,t){return e&&((n,r)=>e(n,Ds(r,t)))}                                    // credits(input, rows)
ks = e=>e.credits
```

The live table is fetched once per user/workspace and cached 5 min (`DK8UQ04csYdLjiyx.js`, module
`use-credits-config`): `queryKey:["credits-config", userId, workspaceId], …fetch(D("/job-sets/costs"),{method:"GET"})
with workspaceId header, staleTime:3e5`. **Prices can therefore differ per workspace** (the header is sent; the anonymous
GET is what we scrape).

Row lookups (`7neBbGmjVy-OZO45.js`, module `credits-config-store-gymfaS5B`) — one accessor per row shape:

| accessor | row it finds | returns |
|---|---|---|
| `p(type, res)` | `resolution` + `cost_per_second` | `{costPerSecond, originalCostPerSecond}` (original defaults to cps) |
| `_(type, res, with/without_video)` | `video[...]` + `resolution` | `{costPerSecond, originalCostPerSecond, imageCredits}` |
| `y(type, res)` | `video_edit` | edit rate |
| `i(type, mode, sound)` | `mode` + `audio` | `{costPerSecond}` (Kling 3.0 family) |
| `d(type, mode)` | `mode` + `cost_per_second` | Kling 3.0 motion control |
| `f(type, res)` | `resolution` + `credits` | `{credits, originalCredits}` (images) |
| `v(type, model, res)` | `model` + `resolutions[]` | Seedance 2.0 |
| `c(type, {model,inputFps,outputFps,sourceResolution})` | fps rows; picks the **smallest** `input_fps ≥ asked`, then `output_fps ≥ asked` | fps boost |
| `_(rows, type, {creativity, sourceResolution, resolution})` | Flux video upscale | |
| `a(type)` | `max_frames` row | depth video; `c(type)` → `reference_fps` row (Topaz Hyperion, SAM 3) |
| `l(res)` | `reframe` row with `image_credits`, `image_count` | |
| `n(type)` | `cost_units_numerator` row | Qwen TTS |

Units seen in `/job-sets/costs` (87 types on 2026-11-26; `parsers/costs.py` flattens all 55 shapes):

| unit | quantity | rounding |
|---|---|---|
| credits per second | output seconds, or source seconds (edit/upscale/dub) | per type, §4 |
| credits per generation | images × batch | none, or `ceil₀.₀₁` (GPT Image) |
| credits per 50 characters | `ceil(chars/50)` blocks | block ceil, then `round₀.₀₁` |
| credits per 10 seconds | `ceil(seconds/10)` blocks (`youtube_faceless_video`) | block ceil |
| credits per minute | `ceil(minutes)` (`elevenlabs_video_to_music`, `duration_rounding: ceil`) | |
| cost units per character | `max(1, ceil(chars × 3/70)) / 100` (Qwen) | ceil in units |
| fixed | apps `template.cost`, viral `ceil(units/100)` | |

---

## 4. Per-family formulas

Notation: `d` = duration in seconds, `b` = batch size, `cps(row)` = live rate. "defineJob" = the job definition
in `Kxdpq5YjqY_JH5zf.js` (100+ types) used by Canvas, Flow and the SDK; "submit" = the product page's own
`credits:` function (`DK8UQ04…`, `Pj18vYIp…`, `v4Gfv5l1…`, `HlGaE28…`), which is what the main tool pages display.
Where they differ both are listed.

### 4.1 Seedance 2.5 and Seedance 2.5 Flash (`seedance_2_5`, `seedance_2_5_flash`)

Options (`G6o1S1hf1S6r2WZX.js`, `H2odSMT_fOKI1GMn.js`): `resolution` 480p/720p/1080p/4k (Flash 480p/720p), `duration`
4–30 s (quick picks 4/10/15/20/30), `aspect_ratio` 21:9…9:16, `generate_audio`, `bitrate_mode` standard/high, `batch_size`
1–4, `model` default/video_edit/video_extension, `extension_mode` forward/backward, `draft`, `draft_job_id`,
`draft_upscale_model` seedance_2_5/kling4_0, `seed`. **Price-relevant:** resolution, duration (or source length),
reference video yes/no, batch, mode. **Not price-relevant:** aspect ratio, audio, bitrate, seed, number of images.

```js
// fmaPQSnk2K7UZee5.js
function Jx(e,{resolution:t,duration:n,batchSize:r,edit:i,hasVideoInput:a=!1,original:o=!1}){
  let s=i?e=>qx(e.video_edit,o,!0):e=>qx(e.video?.[a?`with_video`:`without_video`],o,!1),
      c=e.find(e=>e.resolution===t&&s(e)!=null,s);
  return c==null?null:Math.ceil(n*c)*Math.max(1,r)}
function Yx(e){return Math.min(30,Math.max(4,e))}           // edit: clamp source length to 4..30 s
// Kxdpq5YjqY_JH5zf.js, defineJob seedance_2_5_flash
credits:({settings:e,media:t},n)=>{…c=e.model===`video_edit`,l=s[0]?.meta?.durationSec;
  return c&&!(l>0)?null:Bt(n,{resolution:e.resolution??`720p`,duration:c?ke(l):e.duration??5,
  batchSize:e.batchSize??1,edit:c,hasVideoInput:s.length>0})}
```

```
generate / extend:  credits = ceil(d × cps[res][with_video if any role:"video" media else without_video]) × max(1,b)
edit:               credits = ceil(clamp(source_seconds, 4, 30) × cps_edit[res]) × max(1,b)
draft:              resolution forced to 480p  (H2odSMT… `$k=fe`, fmaPQ… `Gc=\`480p\``; picker text "Fast 480p drafts")
draft → kling4_0 upscale:  ceil(d × cps[seedance_2_5_kling_upscale][1080p])   = ceil(d × 4)
strike-through:     same formula with original_cost_per_second (shown only when it is higher)
```

- The `with_video` switch is **any** video in `medias` (`s.length>0`); images, start/end frames and audio don't change
  the price. Extend mode (`video_extension`) carries a video, so it is priced at `with_video × added seconds`.
- Draft upscale with `draft_upscale_model:"kling4_0"` is priced by `credits-MunJpi9u.i()` =
  `Math.ceil(e*(n?r.originalCostPerSecond:r.costPerSecond))` on the `SEEDANCE_2_5_KLING_UPSCALE` 1080p row. Upscaling
  with `seedance_2_5` re-uses the job's duration (`e.draft_job_id?e.duration`) at the chosen resolution (**inferred**:
  the request is not visible in full).
- Live rates (credits/s): 480p 3/3/3.5, 720p 7/7/7.5, 1080p 16/16/20, 4k 28/34/34 (without/with video/edit). Flash
  480p 2/2.5/2.5, 720p 5/6/6. No discount today (`original = cost`).
- Static fallback in the bundle is stale (4k 27/26 per second); the live table wins once loaded.

### 4.2 Cinema Studio (`cinematic_studio_video_4_0`, `_3_5`, `_3_0`, `_v2`, images)

```js
// DK8UQ04csYdLjiyx.js, module credits-7Xj09Now (Cinema Studio 4.0)
let s=e.model===`video_edit`?(0,a.a)(o):e.duration; …
let c=e.model===`video_edit`?(0,t.m)(`cinematic_studio_video_4_0`,e.resolution):null,
    l=c==null?(0,t.p)(`cinematic_studio_video_4_0`,e.resolution,(0,a.c)(o)?`with_video`:`without_video`):c;
return Math.ceil(s*u)*Math.max(1,e.batch_size??1)
// cinematic_studio_video_3_5 / cinematic_studio_3_0 submit
credits:e=>…((r=a.batch_size)??1)*((i=a.duration)??1)*o.costPerSecond           // no rounding
// cinematic_studio_video_v2 (Kling-backed)
d=l===`pro`?o===`on`?2:1.5:o===`on`?1.75:1.25, f=costs(`cinematic_studio_video_v2`,mode,sound)?.costPerSecond??d;
return Math.ceil(u*f*p)                                    // u = d or Σ multi_prompt durations, p = batch
// WtcE77xtVkvsNEl6.js: cinematic_studio_image(_grid): batch × (Y[res] ?? 2); soul_cast / soul_location: batch × 0.125
```

| type | formula |
|---|---|
| `cinematic_studio_video_4_0` | Seedance 2.5 shape: `ceil(d × cps[res][with/without video]) × b`; edit: `ceil(src × cps_edit) × b` (src from the video's `durationSec`, no clamp in this module) |
| `cinematic_studio_video_3_5`, `cinematic_studio_3_0` | `b × d × cps[res]` (no rounding); 3.0's other module uses `ceil(d × cps)` |
| `cinematic_studio_video_v2` | `ceil(d_total × rate[mode][sound] × b)`; fallback pro 2/1.5, std 1.75/1.25 |
| `cinematic_studio_image(_grid)` | `b × table[res]` (default 2) |
| `cinematic_studio_soul_cast/location`, `soul_cinema_studio` | `b × 0.125` |
| `cinematic_video_relight`, `cinematic_video_inpaint`, `videoshop_*`, `cinematic_video_editor` | Seedance-shaped rows; no client formula found (**inferred** `ceil(d × cps) × b`); `videoshop_relight` image mode = `image_credits` 3.5 |

### 4.3 Kling

```js
// v4Gfv5l1d073Oxjh.js, kling3_0 submit
if(r===`4k`){let e=(0,I.i)(`kling3_0`,`4k`,i??`off`);return c*(e?.costPerSecond??6)}
let u=(0,I.i)(`kling3_0`,r??`std`,i??`off`);return u?c*u.costPerSecond:null       // c = d or Σ multi_prompt
// kling_o3_flf / kling_o3_image_reference submit
let a=(0,I.i)(`kling_o3_flf`,r??`std`,i??`off`);if(a)return Number((n*a.costPerSecond).toPrecision(12));
return Math.ceil(r===`4k`?n*6:r===`pro`?n*(o?2:1.5):n*(o?1.5:1.25))               // fallback only
// Kxdpq5… defineJob kling4_0 / kling_4_0_flash
credits:({settings:e,media:t})=>(e.duration??10)*Jh(res,ze(res,e.dynamicRange))[q(t,`video`)>0?`with_video`:`without_video`]
Wg={with_video:4,without_video:3}            // flash static fallback (live: 2 / 1.5, discounted from 4 / 3)
// kling3_0_motion_control defineJob
let i=e.mode===`pro`?2.5:1.5;return Math.ceil(i*r+(e.isChain?2:0))          // r = d or source video length
// kling3_0_turbo submit: e*(costs(`kling3_0_turbo`,t)?.costPerSecond ?? {720p:1.5,1080p:2}[t])
```

| type | options that change price | formula |
|---|---|---|
| `kling3_0` | `mode` std/pro/4k, `sound` on/off, `duration` 3–15, `multi_shots` + `multi_prompt[].duration` | `d_total × audio[sound]` of the `mode` row (no rounding). Live: pro 2.5/1.75, std 2/1.5, 4k 6/6 |
| `kling_o3_image_reference`, `kling_o3_flf` | same | `d × rate` (`toPrecision(12)`); defineJob/Canvas uses `ceil(d × rate)` and default `sound:"on"`, submit defaults `"off"` |
| `kling4_0` | `resolution` 720p/1080p/4k, `dynamicRange` sdr/hdr (1080p+), reference video | `d × rate[sdr|hdr][res][with/without video]`, no batch (batch fixed 1), no rounding |
| `kling_4_0_flash` | reference video | `d × rate` (720p only), batch fixed 1 (`E("batchSize",n.batchSize,1,1)`) |
| `kling3_0_turbo` | `resolution` | `d × rate` |
| `kling3_0_motion_control` | `mode`, driving-video length, chain | `ceil(rate × d + (isChain ? 2 : 0))`; the chain route also asks the server (`POST /job-sets/costs`, §5.6) |
| `kling2_6_motion_control` | `mode` | `ceil((pro?1.5:1) × d + (chain?2:0))` (no costs row) |
| `kling2_6` | `duration` 5/10, `sound` | `sound ? d×2 : d` (static) |
| `kling_video_edit` | `model`, `mode` | `ceil(rate × floor(source_s))`; rates kling-video-edit pro 3/std 2.2, o3 pro 2/std 1.5/4k 6 (static) |
| `kling_video_reference` | `model`, `mode` | `ceil(trunc(rate × d × 100)/100)` (static) |
| `kling_omni_flf/_image_reference` | `mode` | `ceil(d × (pro?2:1.5))` |
| `kling_omni_image` | — | `b × 0.5` |
| `kling_image_4_0` | `resolution` 2k/4k/8k, `resultType` series | `rows[res] × (series ? seriesAmount(default 4) : b)` |
| `kling_3_unlimited` | — | `0` (credits:()=>0) |

### 4.4 Wan (`wan3_0`, `wan3_0_prime`, `wan4_0`, older)

```js
// fmaPQSnk2K7UZee5.js
function eC(e,{resolution:t,duration:n,hasVideoInput:r,original:i=!1}){…return c==null?null:Es(n*c)}  // ceil₀.₀₁
function $S(e,t,n){return RS(e)?t:n>0?Math.ceil(n-sC):null}   // RS(e)= e!==`video_edit`; sC=Ic=.01
// Kxdpq5… wan3_0 factory: let a=Ge(yM(e),e.duration??5,bM(t)); …Ve(n,{resolution,duration:a,hasVideoInput:q(t,`video`)>0})
```

- `wan3_0`/`wan3_0_prime`/`wan4_0`: `ceil₀.₀₁(d × cps[res][with/without video])`, **no batch factor**. Edit mode:
  `d = ceil(Σ source video seconds − 0.01)`, always `with_video`. Durations 2–30 (Wan 4.0 2–45, hidden behind flag
  `f_6a87092e` and absent from `/job-sets/costs`).
- Wan 3.0 is discounted today: 720p 1.5 (was 2.5) without video, 3 (was 5) with video.
- Legacy: `wan2_6` `ceil(d × (1080p?4:2.5))`; `wan2_7` `ceil(d × (1080p?2.5:1.5))`; `wan2_5_video`
  `ceil(d × {regular:{480p:1.25,720p:2.5,1080p:4}, fast:{720p:1.8,1080p:2.5}})`; `wan2_2_video` like DoP
  (`ceil((24·steps+200)/100)` / `ceil((35·steps+300)/100)`, `wan_fast` = 5); `wan2_2_image` `b × {720p:50,1080p:100}/100`.

### 4.5 Veo and Sora (no `/job-sets/costs` rows; static JS)

```js
// veo3_1: let n=e.mode===`reference_images`,r=n?`veo-3-1-preview`:e.model,i=n||e.duration==null?8:e.duration;
return r===`veo-3-1-fast`?e.quality===`ultra`?Math.ceil(6*i):Math.ceil(i/8*22)
                         :e.quality===`ultra`?Math.ceil(10.9*i):Math.ceil(i/8*58)
// veo3_1_lite: n = 1080p ? (audio?2:1.5) : (audio?1.5:1); Math.ceil(d*n)
// veo3: Ok={"veo-3-preview":58,"veo-3-fast":22}
// sora2_video: Math.ceil(rO[base][res]*d)+(max?4:0)
rO={"sora-2":{"720p":2.4,"1080p":7.4},"sora-2-pro":{"720p":7.4,"1080p":12.4}}
```

Veo 3/3.1 and Sora 2 are in the retired set (`Vx`) and redirect to Seedance 2.5, so these only apply to old
re-runs and Canvas nodes.

### 4.6 MiniMax / Hailuo

| type | formula |
|---|---|
| `minimax_h3_highspeed`, `minimax_h3_lite` | `d × cps[res] × max(1,b)` (live; static fallback highspeed 480p 1.25/768p 2, lite 1/1.25) |
| `minimax_h3`, `minimax_h3_max` | `d × {480p:1.5, 768p:2.5}[res] × max(1,b)` (static; no costs row) |
| `minimax_hailuo` (2.3) | table `{minimax-2.3:{6:{768:6,1080:10},10:{768:11}}, -fast:{6:{768:4,1080:7},10:{768:7}}}`, 512p → `{6:3,10:5}` |
| `minimax_h3_image` | `rows[res] × b` (live 1k 3, 2k 3, 4k 4) |

### 4.7 Other video generators

| type | formula (JS) |
|---|---|
| `gemini_omni` | `ceil((d ?? 8) × 3) × max(1,b)` (`As=3`); live rows all 3/s + `base_credits` 0 |
| `gemini_omni_flash_1_2` | `d × cps[res] × max(1,b)` (edit mode → `null`, server-priced); live 360p .75, 720p 2.25, 1080p 3.25, 4k 6.75 |
| `gemini_omni_flash_1_1` | `ceil(d × {360p:1,720p:3,1080p:4.5,4k:9}) × b` |
| `grok_video_v15` | `max(d,1) × (1080p ? 8 : 720p ? 4.5 : 2.5)`; 1080p blocked with reference media |
| `grok_video_v15_lite` | `d × cps[res]` |
| `grok_video` / `grok_video_edit` | `ceil(d × 1.5)` / `ceil(min(src, 8) × 2)` |
| `happy_horse_video` | `ceil(d × cps[res]) × max(1,b)` |
| `magi_2` | `ceil₀.₀₁(ceil₀.₀₁(base_credits + d × cps[1080p]) × b)` (unlimited never applies). **Anonymously** `/job-sets/costs` has no `magi_2` row → `null`, server-priced. **Logged in** (audit 2026-11-26, [`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md) §1) the row exists: `1080p: base_credits 0, cost_per_second 2.5` → e.g. 5 s = 12.5 credits. `scrape pricing --logged-in-prices` adds it with `visibility: "logged_in"` |
| `flux_3_video` | `d × cps[res][with/without video]` (static fallback `{720p:{5.5,13},1080p:{9,17},2k:7,4k:13}` is stale; live 6/8/10/13) |
| `seedance_2_0`, `_fast` | `ceil(d × cps[model][res]) × b` (default `d=4`) |
| `seedance_2_0_mini`, `seedance_mini_unlimited` | `ceil(d × {480p:1,720p:2.5}) × b` (live mini .5/1, discounted) |
| `seedance_unlimited`, `seedance_2_unlimited` | `0` |
| `seedance1_5` | `ceil(d × {480p:{.3,.6},720p:{.6,1.2},1080p:{1.5,3}}[audio])` |
| `seedance` (1.0) | `floor(d × {pro:{480:.8,720:1.6,1080:3.6}, pro_fast:{.5,.9,1.8}})` — the only `floor` |
| `hf_fnf_video` | `ceil(d × 6)` (default 15 s) |
| `marketing_studio_video` | `ceil(d × cps[res] × b + (web_product ? 6 × b : 0))` |
| `marketing_studio_hook` | `20` |
| `what_if_v1` | `63 × seconds × episodes / 60` (seconds 15–300, episodes 1–4) |
| `music_cards_v1`, `video_character_asset`, `intone`, `ad_multiplier(_v2)`, `ai_host_video`, `hf_evolution`, `scene_switch` | rows only, no client formula found (**inferred** `ceil(d × cps)`; `scene_switch` also carries `cost_per_run` 8.87/12.46) |

### 4.8 Higgsfield DoP / motions (`image2video`, `image2video_mix`)

```js
// Kxdpq5… defineJob image2video
let r=e.model??`standard`,i=e.frames??49;if(i!==49&&i!==81)return null;
if(r===`lite`)return i===81?5:3;
let a=Kd(r,e.steps),o=r===`turbo`?i===81?10*a+400:7*a+280:i===81?35*a+300:24*a+200;return Math.ceil(o/100)
function Kd(e,t){return e===`lite`?30:t==null?e===`turbo`?30:20:t}       // default steps
```

`motion_id` (from `/motions`), `strength`, `seed`, `guideScale`, aspect ratio don't change the price; `frames` 49/81,
`model` lite/standard/turbo and `steps` (1–70) do. `image2video_mix` (two motions) uses the same function.

### 4.9 Motion control / replace object (Genjutsu, AI Influencer)

```js
// Pj18vYIpTWkz-NlF.js, module credits-aYbfBp9O
c = cost ?? (e===`1080p`&&type===HF_MULT_MOTION_CONTROL ? 20 : null); return Math.ceil(t)*c*r   // t = seconds, r = batch
// duration sent to the quote for AI Influencer: Math.max(4,Math.min(Math.floor(t+.5),30))
```

`hf_mult_motion_control(_flash)`, `hf_mult_replace_object(_flash)`, `ai_influencer_*`: `ceil(d) × cps[res] × b`, d = 3–30
(replace-object 4–30). The page also requests a **server quote** (`POST /job-sets/costs`, §5.6) and uses
its `credits`. Live: 480p 3, 720p 7, 1080p 20; Flash 1/2/4 (was 3/6/12).

### 4.10 Images

| type | formula (JS) | price-relevant options |
|---|---|---|
| `gpt_image_2`, `gpt_image_2_5`, `gpt_image_2_6`, `gpt_image_2_6_flare` | `ceil₀.₀₁(b × credits[model?][quality][res])`; `quality:"auto"` → `high`; a missing combination falls back to **high/2k**; strike-through only if `original_credits > credits` | quality low/medium/high/xhigh/max, resolution 1k/2k/4k, model flare/sunburst (2.5) |
| `gpt_image_2_unlimited` | same function (priced); the `_unlimited` route is meant for `use_unlim` | |
| `nano_banana_2_1` | `b × rows[res]` (1k 1.5, 2k 2, 4k 3) | resolution |
| `nano_banana_2` | `b × {1k:2,2k:2,4k:4}` (static, no costs row) | resolution |
| `nano_banana` / `_flash` / `_2_lite` / `_2_upscale` | `b × 1` / `b × {1k:1.5,2k:2,4k:3}` / `b × 1` / `{2k:2,4k:4}` | |
| `seedream_v5_pro` | `b × (2k ? 3 : 1.5)` static; live 1k/1.5k 1.25, 2k 2.5 (discounted) | resolution |
| `seedream_5_5`, `seedream_5_0_flash` | `b × rows[res]` / `b × 0.5` | |
| `seedream`, `seedream_v4_5`, `seedream_v5_lite` | `b × 1` | |
| `flux_2` | `b × {pro:{1k:1,2k:1.5}, flex:{3,5}, max:{4,6}}[model][res]` | model, resolution |
| `flux_3_image` | `b × {768sq:1, 1k:2, 1.5k:2, 2k:3, 4k:19}` | |
| `flux_kontext` | `b × 1.5` (default b = 2) | |
| `ideogram_4_6` | `b × row(quality, res, has_references)` | |
| `ideogram_4_5` | `b × {very_low:.25, low:1, medium:2, high:6.25}` | |
| `ideogram_4_5/4_6_precise_edit` | `b × row(quality)` / `b × row(quality, 2k if w×h ≤ 4,194,304 else 4k)` | |
| `ideogram_vector` | vectorize: flat row (3); generate: `max(1,b) × row(quality, has_refs)` | |
| `recraft_v4_1`, `recraft_v4_styles` | `b × JS[model_type][res]` / `b × (2k ? 3 : 1)` | |
| `kling_image_4_0`, `minimax_h3_image` | see §4.3, §4.6 | |
| `image_auto` | `b × {2k:2, 4k:4}` | |
| `grok_image` / `grok_image_2_0` | `b × (quality|pro ? 2 : 1)` / `b × table[res][quality]` | |
| `openai_hazel` / `_mini`, `text2image_gpt` | `b × {low:2,medium:4,high:6}` / `b` / `b × {low:1,medium:2,high:5}` | |
| `reve`, `z_image`, `marketing_studio_image` | `b × {std:1,fast:.25}` / `b × .15` / `b × {1k:2,2k:2,4k:4}` | |
| `text2image_soul_v2`, `soul_cinematic`, `text2image_soul` | `b × 0.125` | batch (Soul: unlimited only at batch 1, §5.1) |
| `keyframes_faceswap`, `character_swap_v2` | `2` | |
| `p_image_ideogram`, `3d_jutsu_angles`, `gif` | rows only (`gif` create 1 / recreate 3) | |

### 4.11 Audio, TTS, dubbing

```js
// DK8UQ04… TTS submit
let p=e.params?.model?l.u[e.params.model]:.15, m=isElevenV4(model)?Array.from(f).length:f.trim().length,
    h=Math.ceil(m/50)*p;
return isElevenV4(model)?Math.round(h*(batch??1)*100)/100:h
// --B96yNjC9WSkLGbx.js config-2kJXQY26
o={minimax:.15,elevenlabs:.15,elevenlabs_v4:.23,elevenlabs_v4_turbo:.15,vibe_voice:.1,seed_speech:.1,seed_audio:.04,qwen_audio:.05}
// config-xa7JEzuI (seed_audio): Math.min(Math.max(Math.ceil(t/15),1),120)*.1
// config-MWDOdAuz (qwen): Math.max(i.minimum_cost_units,ceil(len*num/den))/i.cost_units_per_credit
// built-LH9XCUI7: dubbing  n={25:3,30:3.6,60:6}; Math.ceil(Math.floor(d)*n[fps]??n[25])
//                 voice change  Math.ceil(t*.1*100)/100
```

| type | formula | live formula row agrees? |
|---|---|---|
| `elevenlabs_v4`, `_turbo` | `round₀.₀₁(ceil(codepoints/50) × .23 (.15) × b)` | yes: `character_blocks`, 23 / 15 units per block |
| `text2speech_v2` (`model` minimax / elevenlabs v3 / seed_speech / vibe_voice / cozy_voice) | `ceil(trim(text).length/50) × rate` — **the UI ignores batch**; the live row says `batch_size.pricing: linear` (server likely charges × b) | yes (15/15/10/10 units) |
| `seed_audio` | `clamp(ceil(chars/15), 1, 120) × 0.1` | yes (`estimated_duration`, 10 units/s) |
| `qwen_audio_tts` | `max(1, ceil(chars × 3/70)) / 100` | yes (`linear_units`) |
| `voice_change_merge` | `ceil₀.₀₁(d × 0.1)` | yes |
| `audio_dubbing` | `ceil(floor(d) × 3)` (inferred from the row: `duration_rounding: floor`, `rounding: ceil`) | row only |
| `dubbing_lipsync` | `ceil(floor(d) × {25:3, 30:3.6, 60:6}[fps])`, unknown fps → 25 | yes (`input_duration_by_fps`) |
| `elevenlabs_video_to_music` | `ceil(minutes) × 4` (music_v2_5: 9) | row only |
| `youtube_faceless_video` | `ceil(d/10) × 41` (fully animated) / `× 16` (scene based) | row only |

### 4.12 Lipsync / Speak (`2KSneU3QfSjJ6MRp.js`, `hi()`)

| model | credits |
|---|---|
| `speak-hf-v2` | mid `ceil(max(14, 2.8 × d))`, high `ceil(max(22, 4.4 × d))` |
| `speak-wan-2.5` | `ceil(d × {480p:1.25, 720p:2.5, 1080p:4})`; `-fast` `ceil(d × {720p:1.8, 1080p:2.5})` |
| `veo3-speak` / `veo3-1-speak` (`speak-veo*`) | fixed 58; `speak-veo-fast` 22 |
| `infinite_talk` | low/mid `ceil(3 × d)`, high `ceil(12 × d)` |
| `kling-speak` (`Rr.u`) | `ceil({mid:1, high:2}[quality] × max(d, 2))` |
| `kling2_6_lipsync` | `d === 5 ? 10 : 20` |
| `kling-lipsync` | `ceil(video_s / 5) × 5 × 0.25` |
| `sync-so` | `ceil(video_s × 3)`, flagged *inaccurate* (UI shows "≈") |
| `hummingbird` | 1 |
| chunked speak (fallback) | `{low:[20,35,50], mid:[25,45,70], high:[45,85,130]}[quality][min(chunks)−1]` |

None of these has a `/job-sets/costs` row; all prices are static in JS.

### 4.13 Upscale and video tools

| type | formula |
|---|---|
| `seedance_2_5_kling_upscale` ("Higgsfield Enhance") | `ceil(d × 4)` (1080p row) |
| `flux_video_upscale` | `ceil(cps[creativity][source][target] × d × 100 − 1e−9) / 100` |
| `bytedance_video_upscale` | `ceil(src_s × (fps > 30 ? {1080p:.4, 2k:.8, 4k:1.5} : {1080p:.2, 2k:.4, 4k:.8})[res])` (`n63Pne9P6uzSs9nC.js` `Ze`) |
| `topaz_hyperion_2_5`, `sam_3_video` | `ceil(frames × cps × 100 / reference_fps − 1e−9) / 100` (rows `is_estimate: true`, `reference_fps` 24) |
| `depth_anything_video` | `ceil₀.₀₁(min(frames, max_frames=1800) / frame_rate × cps)` (`m34lwUXf…` `Do`) |
| `fps_boost` | rate of the smallest `input_fps ≥ source fps` / `output_fps ≥ target` row × seconds (rounding **inferred** `ceil₀.₀₁`) |
| `topaz_image`, `topaz_image_generative`, `topaz_video` | **server quote** `POST /jobs/{route}?dry_run=true` (from JS, not called); no client formula |
| `video_background_remover` / video upscale form | `1` / `2` (defineJob) |
| `reframe` | `ceil(round(d) × cps[res] + n_img × image_credits)`, `n_img = segments > 1 ? 2·segments+1 : 3`, `segments = d ≤ 15.25 ? 1 : ceil((d − 0.25)/15)`; d 4–60 s. defineJob uses static `{480p:3, 720p:4.5, 1080p:9}` and 2 credits/image; live rows are 3/4.5/**12** and 1.25 × 3 images |
| `draw_to_video`, `swap_object`, `remove_object` | rows `cps` + `frame_credits` 3.5; no client formula (**inferred** `ceil(d × cps) + frames × 3.5`) |

### 4.14 Viral-hub presets, apps, mixed media

- **Viral presets** (`viral_hub_video`): `credits = ceil(creditUnits / 100)` (`Kxdpq5…`: `Math.ceil(t/oj)`, `oj=100`).
  `creditUnits` is the `price_matrix` row whose key matches the chosen `param_choices`
  (`"<node>.aspect_ratio=16:9,<node>.resolution=1080p"`; empty key = default). Example `floating-fall`: default 8400
  → **84**, 1080p 14400 → **144**, 480p 3600 → **36**. Of 87 presets, defaults range 1500–12000 units; non-multiples of
  100 exist (1750, 2250, 3150, 3350, 4050 …) so the ceil matters (1750 → 18). `use_free_gens` is sent for presets.
- **Apps** (`/apps/{slug}`): the price is `template.cost` from the page loader, shown as is. Seen 2026-11-25:
  headshot 1, angles 1, behind-the-scenes 2 (image) / 6 (video), character/face/style swap 2, video face swap 25,
  expand 2, glitter sticker 2, outfit shot 1 / 19 (video), relight 0, transitions 10, color grading 15. (The 2026-11-26
  `site --what apps --no-content` run returns apps without templates, so costs come from the 11-25 run.)
- **Mixed media** (`/chains/mixed-media`): no client formula and no costs row (config needs login) — unknown.
- **Community "recreate" of a Seedance 2.0 preset** (`VGa9OELr-Bpz2hSH.js`): `costCredits = ceil(d × cps)` at 720p,
  `discountCredits = ceil(d × original)` — the strike-through on preset cards.

### 4.15 Discounts and the strike-through

Every row may carry `original_*`. The UI computes the price twice with the same function (`original:true`) and shows
the original struck through when it is larger (`p=({credits:e,original_credits:t})=>…t>e?t:void 0` in
`gpt-image-costs`; `credits-config-store` `m(e,t,n)` returns `n × original/cps` only if it is bigger). On
2026-11-26 discounted types: `wan3_0`, `wan3_0_prime` (−40 %/−29 %), `kling_4_0_flash` (−50 %), `seedance_2_0`
(480p −50 %, 720p −25 %, 4k −15 %), `seedance_2_0_mini`, `cinematic_studio_3_0`/`_3_5` (480p/720p/4k),
`marketing_studio_video`, `happy_horse_video` (−38 %/−44 %), `flux_video_upscale` (−50 %), all `*_flash` motion
types (−67 %), `gpt_image_2_5` (many rows), `seedream_v5_pro` and `3d_jutsu_angles` (−17 %).

---

## 5. Account-level rules

### 5.1 Unlimited

- **Flag:** the UI sends `use_unlim` (top level, and inside `params` for some types). Seedance 2.5 page
  (`HlGaE28…`): `h({modelVersion,isUnlimited,isUseFreeGens,isUseGenerationSeconds})` → Flash-type models
  (`tY`: Wan Flash ids, `grok_video_v15_lite`, `genjutsu-flash`, `kling_4_0_flash`) get **no** unlimited, free gens or
  generation seconds; `seedance_2_5_flash` (`XJ`) gets unlimited only.
- **Grant source:** `GET /workspaces/settings` (login) returns `{configs: [...]}` on the wire (`{configs: []}` for
  the audited free personal account). The client maps `configs` → `unlimited_settings` and drops grants with
  `status == "locked"` (`548e0f3a-tCLaulKUdGQfxqgZ.js`, `Lj`/`eM`; [`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md) §2.1).
  The `account` scraper does the same (`unlimited_grants`).
- **Coverage check** (`Bu6Xbu7ZDQajrDWS.js`): a grant from `unlimited_settings[]` covers a generation iff the type matches, the time window is active (`start_date`, `end_date`,
  `team_end_date` for shared workspaces), every requested option is in the grant's lists (`models`, `modes`,
  `resolutions`, `qualities`, `output_formats`, `dynamic_ranges`, `durations`), `duration ≤ max_duration`, **and
  `batch_size ≤ 1`**:
  ```js
  …||u!=null&&e.max_duration!=null&&u>e.max_duration||d!=null&&d>1)
  ```
  Soul submits `use_unlim = batch_size > 1 ? false : use_unlim` (`DK8UQ04…`, `built-Bfz5umHL`). The audio rows say
  the same: `unlimited: {eligible: true, maximum_batch_size: 1}` (`text2speech_v2`, `seed_audio`); ElevenLabs v4,
  Qwen, dubbing are `eligible: false`.
- **Never unlimited:** `magi_2`, `wan4_0` — the adapter forces `use_unlim:false` (`j8lj58UEh2bbmHmn.js`:
  `R=new Set([\`magi_2\`,\`wan4_0\`])`, `ue(e,t)=>R.has(e)?{...t,use_unlim:!1,…}`).
- **Dedicated unlimited job types** price at 0: `kling_3_unlimited`, `seedance_unlimited`, `seedance_2_unlimited`
  (`credits:()=>0`); `nano_banana_pro_unlimited` has no credits function.
- **Per plan (ps_a3, from `plans.json` `unlimited_model_ids`):** starter: seedream_v5_lite, flux_2; plus monthly:
  seedream_v5_pro, gpt_image_2_6, gpt_image_2_6_flare, nano_banana, kling_omni_image, seedream_v4_5, seedream_v5_lite,
  flux_2; plus annual and all ultra: the same **plus nano_banana_2**; team: nano_banana_2, seedream_v5_pro,
  Seedance 2.0; scale: nano_banana_2, seedream_v5_pro, Seedance 2.5 (+ kling3_0 annual). Promotional windows
  (`/datetime-settings`: `plan_all_unlims`, `unlim_seedance_4k`, `unlim_marketplace_bundles` …) and purchasable
  bundles (`GET /subscriptions/bundle/unlim-catalog`, `POST …/purchase/instant/unlim` with `dry_run`) add more.
- **Concurrency** (pricing-config feature text, legacy plan names): basic 2 videos/2 images/1 character, pro 3/4/2,
  ultimate 4/8/3, creator 8/8/6, team 16 tasks per seat. It limits parallel jobs, not price.

### 5.2 Free gens

- `use_free_gens` is sent only when the model allows it; `defineJob` `business:{useFreeGens:false}` disables it
  (Seedance 2.5/Flash, Kling 3.0, Kling 2.6, Seedance 2.0, Gemini Flash 1.2, motion control, videoshop). Unlimited wins:
  `a = i===!0 ? !1 : useFreeGens` (`8P1KqccrkPDjF19Z.js`).
- Plan counts (`plans.json` `free_gens`): Soul V2 & Cinema 300 (starter) / 3,000 (plus monthly) / 5,000 (plus annual,
  ultra monthly) / 10,000 (ultra annual); Higgsfield Genjutsu 1–3 per period at max 720p. A free gen costs 0 credits.
- Windows from `/datetime-settings` (public): `freegens_seedance_2_5_1080p`, `freegens_seedance_4k(_new_users)`,
  `plan_free_gens`, `freegen_card_bonus` (`use-seedance-2-5-1080p-campaign` hook in `ZGItCEvS…`).

### 5.3 Generation seconds, daily credits, other balances

- Rewards/grants schema (`RjL0wZNqpe3iHpMW.js`): kinds `credits {amount, expires_at}`, `free_gens {model, amount}`,
  `model_unlim {model, duration_days}`, **`generation_seconds {model, amount, resolution, expires_at}`**,
  `rating_points`, `badge`. `use_generation_seconds: true` spends those seconds instead of credits (Seedance 2.5 only;
  a `generation_seconds_sale` window exists). How partial seconds are deducted is not visible (**inferred**: seconds of
  output).
- `use_free_daily_credits` (free plan "limited daily credits") is sent for Wan 2.5, Veo 3.1 and the legacy envelopes.
- Wallet (`2B_Cs0zHIGw5q2ts.js`): `subscription_balance`, `total_credits`, `credits_balance`, `on_demand_credits`
  (top-ups), `bonus_credits` + `bonus_credits_expire_at`, `scoped_credits[{scope: mcp|supercomputer|playable_ads|
  micro_drama_ads, balance/100, expires_at}]`, `group_credit_allocation` (team seats), `allocation_cycle`. Which
  balance is spent first is server-side (unknown).
- **Confirmed live** (`GET /workspaces/wallet`, login audit 2026-11-26, [`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md)
  §2.1): the fields above plus `workspace_id`, `expire_days`, `credit_limit`, `next_credit_allocation_date` and
  `wallet_created_at`. **All** wallet balances are in cost units (credits × 100), not only `scoped_credits`:
  `credits_balance 888` = 8.88 credits. `GET /user` reports the same balances in **credits** (floats:
  `subscription_credits`, `package_credits`, `bonus_credits`, `daily_credits`, `total_plan_credits`) plus legacy
  per-model buckets (`soul_credits`, `wan2_5_video_credits`, `text2keyframes_credits`, `face_swap_credits`,
  `qwen_camera_control_credits`, `character_swap_credits`). A job's charged `cost` in `/jobs/accessible` is in cost
  units too (`112` = 1.12 credits, matching the drop in `/user.package_credits`).
- Workspaces: costs are fetched with the workspace id; team plans allocate credits per seat; `hf-workspace-id` is
  sent on jobs; shared workspaces handle `not_enough_credits` by notifying the owner.

### 5.4 Not enough credits

There is no client-side balance comparison in the generation path. The server rejects the job with error code
`not_enough_credits` (enum in `0Oc7kBnNHrwTIkVv.js` next to `rate_limit_reached`, `ultimate_plan_required`,
`minimum_pro_plan_required`, …), and the error handler opens the top-up/upgrade modal; in a shared workspace it
shows the owner/credits dialog instead (`if(v===\`not_enough_credits\`){…return C===\`shared\`?(Ao(e),…):((0,c.p)(),…)}`).
Auto top-up exists (`/workspaces/wallet/auto-top-up`, `…/dry-run`); package sizes and prices are server-driven
(slider "boost credits" in `ZGItCEvS…`) and not public. Login audit 2026-11-26 ([`LOGIN_COVERAGE.md`](LOGIN_COVERAGE.md)
§2.1): `/workspaces/wallet/auto-top-up` is **team-only** (409 `workspace_is_not_shared` on a personal workspace);
personal accounts read `GET /v2/auto-top-ups/settings` instead: `{state, is_eligible, is_on_demand_only, threshold,
refill_options[], options[], selected_option, default_option, credits_per_dollar: 18, current_refill_amount,
on_demand_credits, modal_type, currency: "usd", expire_days: 90}`. `credits_per_dollar` (18) looks global
(**inferred**: one account seen). Recorded by `scrape pricing --sections account` and `scrape account`.

### 5.5 Refunds

No refund logic is in the client. Failed/NSFW/IP-detected jobs (`meta.fail_reason`) show their status; whether credits
come back is server-side (**unknown**).

### 5.6 Server quotes

- `POST /job-sets/costs` with `{job_set_type, params:{duration, resolution, batch_size}}` → `{job_set_type, credits,
  cost}` (`api-gbKNODQ6`; used for motion control: `invalid_motion_control_quote` unless `credits ≥ 0` and `cost` is an
  integer — `cost` is in units). **From JS, not called.**
- `POST /jobs/{route}?dry_run=true` for Topaz (`requiresQuote`, `isCalculating`, `retryQuote` in `Pj18vYIp…`).
- `POST /jobs/v2/{type}/dry-run` for guests (availability, not price).

---

## 6. Credits → USD

`price_per_credit = price for the period / credits for the period`, computed by `parsers/plans.py` and exported as
`credit_values.json`; `assemble.py` sets `usd_estimate = example credits × after-offer rate of --usd-reference`
(default `plus:annual`, lowest credit tier). ps_a3 (US), 2026-11-26:

| plan | period | credits / month | list $/mo | after offer $/mo | renewal $/mo | offer | $/credit list | $/credit after offer | $/credit renewal |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| starter | monthly | 270 | 19.00 | 19.00 | 19.00 | — | 0.0704 | 0.0704 | 0.0704 |
| starter | annual | 270 | 19.00 | 19.00 | 19.00 | — | 0.0704 | 0.0704 | 0.0704 |
| plus | monthly | 1,200 | 59.00 | 40.00 | 59.00 | −33 % first payment | 0.0492 | 0.0333 | 0.0492 |
| plus | annual | 1,200 | 59.00 | 30.00 | 30.00 | −50 % forever | 0.0492 | **0.0250** | 0.0250 |
| ultra | monthly | 3,000 | 129.00 | 75.00 | 129.00 | −42 % first payment | 0.0430 | 0.0250 | 0.0430 |
| ultra | monthly | 6,000 | 250.00 | 140.00 | 250.00 | −45 % first payment | 0.0417 | 0.0233 | 0.0417 |
| ultra | monthly | 9,000 | 375.00 | 199.00 | 375.00 | −47 % first payment | 0.0417 | 0.0221 | 0.0417 |
| ultra | annual | 3,000 | 129.00 | 45.00 | 45.00 | −65 % forever | 0.0430 | **0.0150** | 0.0150 |
| ultra | annual | 6,000 | 258.00 | 83.00 | 83.00 | −68 % forever | 0.0430 | 0.0138 | 0.0138 |
| ultra | annual | 9,000 | 387.00 | 117.00 | 117.00 | −69 % forever | 0.0430 | 0.0130 | 0.0130 |
| team (2 seats) | monthly | 1,000 | 79.00 | 55.00 | 55.00 | −30 % forever | 0.0790 | 0.0550 | 0.0550 |
| team (2 seats) | annual | 1,000 | 79.00 | 45.00 | 45.00 | −43 % forever | 0.0790 | 0.0450 | 0.0450 |
| scale (5 seats) | monthly | 2,500 | 215.00 | 119.99 | 119.99 | −45 % forever | 0.0860 | 0.0480 | 0.0480 |
| scale (5 seats) | annual | 2,500 | 215.00 | 80.00 | 80.00 | −63 % forever | 0.0860 | 0.0320 | 0.0320 |

Notes: annual prices are billed as 12 × per-month; $/credit is per month either way. Unused monthly credits,
top-ups and bonus credits have their own value (top-up packages are not public; creator plans advertised "15 % off
extra credits"). Effective cost per generation on an unlimited model is $0. The provider's own cost is sometimes
visible in community items (`upstream_usage`, e.g. `gpt_image_2` output image $0.53, `grok_image_2_0` $0.08) — this is
Higgsfield's COGS, not the user's price.

---

## 7. Scenarios

All use the live table of 2026-11-26 and USD at plus annual ($0.025) unless noted. More combinations, generated from
the live table, are in the [variations appendix](#11-generated-appendix-option-variations-per-model).

### Seedance 2.5 / Flash

1. **1080p, 5 s, text only.** `cps = video.without_video(1080p) = 16` → `ceil(5 × 16) × 1 = 80` credits → $2.00.
2. **4K, 10 s, with a reference video, batch 4.** `cps = video.with_video(4k) = 34` → `ceil(10 × 34) × 4 = 1,360` →
   $34.00 (ultra annual $20.40). Without the video it would be `ceil(10 × 28) × 4 = 1,120`.
3. **Edit a 12 s clip at 1080p.** `d = clamp(12, 4, 30) = 12`, `cps = video_edit(1080p) = 20` → `ceil(12 × 20) = 240`.
   A 2.5 s clip is clamped up: `ceil(4 × 20) = 80`.
4. **Extend forward by 10 s at 720p.** source video present → `with_video(720p) = 7` → `ceil(10 × 7) = 70`.
5. **Draft then upscale with Kling.** draft 10 s → 480p `ceil(10 × 3) = 30`; `draft_upscale_model:"kling4_0"` →
   `ceil(10 × 4) = 40`; total 70 vs 160 for a direct 1080p render.
6. **Flash 480p, 5 s, reference video.** `ceil(5 × 2.5) = ceil(12.5) = 13` (our estimator says 12.5).

### Kling 3.0 / 4.0

1. **Kling 3.0 std, sound off, 5 s.** `5 × 1.5 = 7.5`.
2. **Kling 3.0 pro, sound on, multi-shot custom 3 + 4 + 5 s.** `d = 12`, `12 × 2.5 = 30`.
3. **Kling 3.0 4K, 15 s.** `15 × 6 = 90` (sound does not matter).
4. **Kling 4.0 1080p HDR, with reference video, 10 s.** `10 × video_hdr.with_video(1080p) = 10 × 5.25 = 52.5`.
5. **Kling 4.0 Flash 720p, 5 s, with video (discount active).** `5 × 2 = 10`, strike-through `5 × 4 = 20`.
6. **Kling 3.0 motion control pro, 7.3 s driving video, chain.** `ceil(2.5 × 7.3 + 2) = ceil(20.25) = 21`.

### Veo / Sora (static, retired models)

1. Veo 3.1 8 s: `ceil(8/8 × 58) = 58`; Veo 3.1 Fast 8 s: `22`; Veo 3.1 ultra 8 s: `ceil(10.9 × 8) = 88`.
2. Veo 3.1 Lite 1080p with audio 8 s: `ceil(8 × 2) = 16`; 720p silent 4 s: `ceil(4 × 1) = 4`.
3. Sora 2 720p 8 s: `ceil(2.4 × 8) = 20`; Sora 2 Pro 1080p 12 s: `ceil(12.4 × 12) = 149`; Sora 2 Max 720p 4 s:
   `ceil(9.6) + 4 = 14`.

### Wan

1. **Wan 3.0 720p, 5 s, text only (discount).** `ceil₀.₀₁(5 × 1.5) = 7.5`, strike-through `5 × 2.5 = 12.5`.
2. **Wan 3.0 1080p, 10 s, with video.** `10 × 6 = 60`.
3. **Wan 3.0 edit of a 7.3 s clip at 720p.** `d = ceil(7.3 − 0.01) = 8`, `with_video(720p) = 3` → `24`.
4. **Wan 3.0 Prime 480p 2 s.** `ceil₀.₀₁(2 × 1.25) = 2.5`.

### MiniMax / Hailuo

1. H3 Highspeed 768p 10 s: `10 × 2 = 20`. 2. H3 Lite 480p 5 s, batch 2: `5 × 1 × 2 = 10`.
3. Hailuo 2.3 Fast 6 s 1080p: table `7`. 4. H3 image 4k batch 2: `4 × 2 = 8`.

### Higgsfield DoP motions

1. Lite, 49 frames: `3`; 81 frames: `5`.
2. Standard, 81 frames, default steps (20): `ceil((35 × 20 + 300)/100) = ceil(10) = 10`.
3. Turbo, 49 frames, steps 30: `ceil((7 × 30 + 280)/100) = ceil(4.9) = 5`.

### Soul

1. Soul V2, batch 4: `4 × 0.125 = 0.5` credits; with free gens left: 0 credits, 4 free gens.
2. Soul V2 batch 1 on an unlimited grant: `use_unlim` true → 0. Batch 2: `use_unlim` forced false → `0.25`.
3. Soul Cinema 1 image: `0.125` (≈ $0.003).

### Nano Banana / Seedream / Flux

1. Nano Banana 2.1, 4k, batch 4: `4 × 3 = 12` ($0.30). On plus annual and above `nano_banana_2` is unlimited (0).
2. Seedream v5 Pro 2k batch 4 (discount): `4 × 2.5 = 10`, strike-through `4 × 3 = 12`.
3. Flux 2 Max 2k batch 2: `2 × 6 = 12`; Flux 3 image 4k: `19`.

### GPT Image

1. `gpt_image_2_6` high 2k, batch 4: `ceil₀.₀₁(4 × 2) = 8`. 2. `gpt_image_2` high 4k batch 4: `ceil₀.₀₁(4 × 12) = 48` ($1.20).
3. `gpt_image_2_5` flare low 1k batch 4: `ceil₀.₀₁(4 × 0.25) = 1`, was `4 × 1 = 4`.
4. Missing combination (e.g. a quality not in the rows): JS falls back to the **high/2k** row.

### ElevenLabs / TTS

1. ElevenLabs v4, 400 characters: `ceil(400/50) × 0.23 = 8 × 0.23 = 1.84`; batch 2 → `3.68`.
2. ElevenLabs v4 Turbo, 1,001 characters: `ceil(1001/50) = 21 × 0.15 = 3.15`.
3. MiniMax speech 400 chars, batch 2: UI shows `1.2`; the live formula says linear batch → 2.4 (**discrepancy**).
4. Seed Audio 400 chars: `clamp(ceil(400/15), 1, 120) × 0.1 = 27 × 0.1 = 2.7`. Qwen 60 chars: `max(1, ceil(60 × 3/70))/100 = 0.03`.

### Lipsync / Speak

1. Speak HF v2 mid, 4 s audio: `ceil(max(14, 2.8 × 4)) = 14`; 10 s: `ceil(28) = 28`; high 10 s: `44`.
2. Wan 2.5 Speak 1080p, 10 s: `ceil(10 × 4) = 40`; Fast 720p: `ceil(10 × 1.8) = 18`.
3. Infinite Talk high 12 s: `ceil(12 × 12) = 144`; Kling lipsync 7 s video: `ceil(7/5) × 5 × 0.25 = 2.5`.

### Upscale / Topaz

1. Higgsfield Enhance (`seedance_2_5_kling_upscale`) 12 s: `ceil(12 × 4) = 48`.
2. Flux video upscale 720p → 1080p, creativity 0, 10 s: `ceil₀.₀₁(1.75 × 10) = 17.5` (was 35).
3. ByteDance upscale to 4k, 20 s at 60 fps: `ceil(20 × 1.5) = 30`; at 24 fps: `ceil(20 × 0.8) = 16`.
4. Topaz Hyperion 2.5, 10 s at 30 fps, 1080p: `ceil₀.₀₁(300 × 2.6 / 24) = 32.5`. Topaz image/video: server quote only.

### Viral presets / apps / mixed media

1. `floating-fall` default: `ceil(8400/100) = 84`; 1080p 16:9 row: `144`; a preset with 1750 units: `ceil(17.5) = 18`.
2. App "Video face swap": `template.cost = 25`; "AI headshot": `1`.
3. Mixed media: unknown (server-side chain, config behind login).

### Cinema Studio

1. 4.0 1080p 15 s with a reference image, batch 2: `ceil(15 × 16) × 2 = 480`.
2. 4.0 edit, 9 s source, 720p: `ceil(9 × 7) = 63`.
3. 3.5 720p 10 s batch 2: `2 × 10 × 5 = 100` (was `2 × 10 × 6 = 120`).

### Edge cases

| case | result |
|---|---|
| batch 4 on an unlimited model | grant requires `batch_size ≤ 1` → paid: e.g. GPT Image 2.6 high 2k → `8`, not 0 |
| 4K + reference video (Seedance 2.5) | `with_video` 34/s vs 28/s → +21 % |
| edit mode with source 45 s (Seedance) | clamped to 30 s for the price (`ceil(30 × 20) = 600` at 1080p); validation limits reference videos to 2–30 s anyway |
| discount active | charged at `cost_per_second`; UI strike-through at `original_cost_per_second` |
| unlimited plan model (e.g. `nano_banana_2` on plus annual, batch 1) | 0 credits, 0 USD |
| free gens (Soul, Genjutsu ≤ 720p, Seedance 1080p campaign) | 0 credits, one free gen consumed; unlimited takes precedence |
| `magi_2` / `wan4_0` with `use_unlim` | adapter forces `use_unlim:false` → always paid |
| Kling 4.0 batch 2 | not possible (batch 1); our estimator multiplies by 2 |

---

## 8. Our estimator vs the JS formulas

`higgsfield_scraper/estimate/estimator.py` + `compare_fallback.py` (see `docs/scrapers/cost-estimate.md`) was checked
against the formulas above by feeding the same params to `CostEstimator.estimate` with the live table
(the "estimator" column is v1, the default). `--estimate-version 2` (`estimate/v2.py`, `CostEstimatorV2`) is an opt-in
estimator that implements these formulas; the last column says what it does with each row. v1 is unchanged. Every
implemented row is a test case in `tests/test_estimate_v2.py` with the numbers of this table.

| # | case | estimator | JS | cause | `--estimate-version 2` |
|---|---|---:|---:|---|---|
| 1 | Seedance Flash 480p 5 s + video | 12.5 | 13 | estimator never applies `Math.ceil` per generation (all `ceil_batch` types: Seedance 2.5/Flash/2.0/mini, Cinema 4.0, Happy Horse, Gemini Omni, Kling motion control) | fixed in v2 |
| 2 | Seedance 2.5 edit (`model:"video_edit"`, 12 s source) | 80 (5 s assumed, generate row) | 240 | `_component` only looks at `video_edit`/`is_edit`/`operation`/`mode`, not `params.model == "video_edit"`; source length is not read from `medias[].data.duration_sec`; no 4–30 clamp | fixed in v2 (no source length → output `duration`, approximate) |
| 3 | Kling 4.0 1080p 10 s, `batch_size: 2` | 75 | 37.5 | estimator multiplies batch for every per-second unit; Kling 4.0/Flash, Wan 3.0, Grok, Kling 3.0 Turbo, Flux 3 video have no batch factor | fixed in v2 (also Kling 3.0 / O3 / motion control, Enhance, reframe) |
| 4 | Genjutsu 720p 5.4 s | 37.8 | 42 | JS uses `ceil(d) × cps` | fixed in v2 |
| 5 | Reframe 720p 10 s | 45 | 49 | estimator adds `image_credits` per *input* image (0); JS adds `3 × 1.25` (`image_count`) | fixed in v2 |
| 6 | MiniMax TTS 400 chars, batch 2 | 2.4 | 1.2 (UI) | UI ignores batch for non-ElevenLabs TTS; the live formula says linear — estimator probably matches the server | kept (the live row says linear batch) |
| 7 | Qwen TTS 60 chars | 0.0257 | 0.03 | estimator uses `len × 3/70/100` without `ceil` in units and without the 1-unit minimum | fixed in v2 |
| 8 | Seed Audio 400 chars | 0.5 (5 s assumed) | 2.7 | estimator needs `duration`; JS derives seconds = `clamp(ceil(chars/15), 1, 120)` | fixed in v2 |
| 9 | Audio dubbing 8.5 s | 25.5 | 24 | `duration_rounding: floor` and `rounding: ceil` not applied | fixed in v2 (also dubbing lipsync; music `ceil` minutes) |
| 10 | Seedance 2.0 720p, no duration | 22.5 (5 s) | 18 (4 s) | default duration 5 s vs JS default 4 s (Seedance 2.0, mini, Cinema 3.x) / 8 s (Veo, Gemini) / 10 s (Kling 4.0) | fixed in v2 |
| 11 | Viral preset with 1750 units | 17.5 | 18 | `estimate_viral` uses `round(units/100, 4)`; JS `Math.ceil(units/100)` | fixed in v2 |
| 12 | Wan 3.0 non-round rates | exact product | `ceil₀.₀₁` | no 0.01 rounding (no visible difference with today's rates) | fixed in v2 (Wan, GPT Image, voice change, Flux video upscale); not implemented for Topaz Hyperion / SAM 3 / depth: need the frame count |
| 13 | Kling 3.0 / O3 without `sound` | assumes `off` (lowest cost) | submit default `off`, defineJob `on` | agrees with the main page only | kept (= main page) |
| 14 | Kling 3.0 multi-shot | uses `params.duration` | Σ `multi_prompt[].duration` when `multi_shots` and mode custom | | fixed in v2 |
| 15 | Wan edit | generate row with `duration` | `ceil(Σ source s − 0.01)` with `with_video` | | fixed in v2 |
| 16 | `scene_switch` | `cost_per_run`, `cost_per_piece`, `masks_cost_per_frame` … parsed as **dimensions** | — | `parsers/costs.py` treats unknown numeric scalars as dimensions; they should be add-on costs | fixed in v2 (`cost_per_run` added once, inferred → approximate) |
| 17 | Models with static JS prices (Veo, Sora, Nano Banana 2, Soul, lipsync, Kling 2.6, MiniMax H3/Hailuo, Flux 2, Seedream v4.5 …) | `unpriced` or compare-table fallback | static tables (§4) | no JS-table fallback in the estimator | fixed in v2 for the tables listed in [cost-estimate.md](scrapers/cost-estimate.md#version-2-the-js-formulas---estimate-version-2); not implemented: Veo 3 (unit unclear), Cinema image (`Y` table unknown), Grok image, Reve, Kling video edit/reference (param names unknown), magi_2 (no static table) |
| 18 | Unlimited with `batch_size > 1` | note only | never unlimited | `use_unlim` note ignores the batch rule | fixed in v2 (notes; credits stay the list price) |
| 19 | GPT Image missing combination | `unpriced`/`approximate` | high/2k row | JS fallback row | fixed in v2 |

**Validation against real charges.** `scrape account --with-jobs --compare-estimate` (login required,
[`scrapers/account.md`](scrapers/account.md)) runs this estimator on the params of the account's own jobs and
compares the result with the `cost` the server actually charged (`match` = |diff| ≤ 0.01 credits). It could not be
run live yet: as of 2026-11-26 Cloudflare challenges `/jobs/accessible` for the Scrapy crawl (`403 cf-mitigated:
challenge`; recorded, not evaded), so it is covered only by offline tests on synthetic fixtures.
Add `--estimate-version 2` to compare the v2 formulas with the actual charges instead.

Agreements: Seedance 2.5 generate/extend at integer products, `with_video` detection, Kling 3.0 mode × sound,
GPT Image / Nano Banana 2.1 / Seedream / Recraft / Ideogram per-image prices, ElevenLabs block pricing, `original_*`
strike-through, `seedance_2_0` per-model rows.

---

## 9. Confidence

| claim | status |
|---|---|
| Live rates, discounts, formula rows, `unlimited.eligible` flags | **verified live** (`GET /job-sets/costs`, 2026-11-26) |
| Plan prices, credits, offers, unlimited/free-gen lists per plan | **verified live** (plans/compare/benefits endpoints) |
| Viral `price_matrix` values, app template costs | **verified live** (public presets; app pages 2026-11-25) |
| `Math.ceil(d × cps) × batch` (Seedance 2.5/Flash/Cinema 4.0), edit clamp 4–30, Kling/Wan/GPT/TTS/lipsync/DoP formulas, static tables | **from JS** (`548e0f3a`), cited above |
| Unlimited coverage rule incl. `batch ≤ 1`, magi_2/wan4_0 never unlimited, unlim > free gens | **from JS** |
| `POST /job-sets/costs` quote, Topaz `dry_run`, `not_enough_credits` handling | **from JS, not called** |
| Credits charged = client formula | **inferred**: the client mirrors the server table; no real charge was observed (community items carry no cost) |
| Draft upscale with `seedance_2_5`, videoshop/relight/inpaint/draw-to-video/scene_switch/audio_dubbing/music formulas | **inferred** from row shapes |
| Generation-seconds deduction, balance order, refunds, top-up package prices | **unknown** (server-side or login) |

---

## 10. Generated appendix: rate tables per model

<!-- BEGIN cost-tables -->
_Generated by `scripts/gen_cost_tables.py` from `/job-sets/costs` (version `0cee321863e2`). USD = example credits × $0.0250/credit (plus:annual after offer)._

#### `audio_dubbing` — Audio Dubbing (audio, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |

#### `dubbing_lipsync` — Dubbing Lipsync (audio, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| fps=25 |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| fps=30 |  | credits_per_second | 3.6 |  | seconds=5.0 → 18 | $0.4500 |
| fps=60 |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |

#### `elevenlabs_v4` — Elevenlabs V4 (audio, credits_per_50_characters)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_50_characters | 0.23 |  | characters=1000.0 → 4.6 | $0.1150 |

#### `elevenlabs_v4_turbo` — Elevenlabs V4 Turbo (audio, credits_per_50_characters)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_50_characters | 0.15 |  | characters=1000.0 → 3 | $0.0750 |

#### `elevenlabs_video_to_music` — Elevenlabs Video To Music (audio, credits_per_minute)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| model_id=music_v1 |  | credits_per_minute | 4 |  | minutes=1.0 → 4 | $0.1000 |
| model_id=music_v2 |  | credits_per_minute | 4 |  | minutes=1.0 → 4 | $0.1000 |
| model_id=music_v2_5 |  | credits_per_minute | 9 |  | minutes=1.0 → 9 | $0.2250 |

#### `qwen_audio_tts` — Qwen Audio TTS (audio, credits_per_character)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_character | 0.00042857 |  | characters=1000.0 → 0.4286 | $0.0107 |

#### `seed_audio` — Seed Audio (audio, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_second | 0.1 |  | seconds=5.0 → 0.5 | $0.0125 |

#### `text2speech_v2` — Text2speech V2 (audio, credits_per_50_characters)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| model=cozy_voice |  | credits_per_50_characters | 0.05 |  | characters=1000.0 → 1 | $0.0250 |
| model=elevenlabs |  | credits_per_50_characters | 0.15 |  | characters=1000.0 → 3 | $0.0750 |
| model=minimax |  | credits_per_50_characters | 0.15 |  | characters=1000.0 → 3 | $0.0750 |
| model=seed_speech |  | credits_per_50_characters | 0.1 |  | characters=1000.0 → 2 | $0.0500 |
| model=vibe_voice |  | credits_per_50_characters | 0.1 |  | characters=1000.0 → 2 | $0.0500 |

#### `voice_change_merge` — Voice Change Merge (audio, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_second | 0.1 |  | seconds=5.0 → 0.5 | $0.0125 |

#### `3d_jutsu_angles` — 3D Jutsu Angles (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1k |  | credits_per_generation | 1.25 | 1.5 | 1 → 1.25 | $0.0312 |
| resolution=1.5k |  | credits_per_generation | 1.25 | 1.5 | 1 → 1.25 | $0.0312 |
| resolution=2k |  | credits_per_generation | 2.5 | 3 | 1 → 2.5 | $0.0625 |

#### `gif` — GIF (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| mode=create |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| mode=recreate |  | credits_per_generation | 3 |  | 1 → 3 | $0.0750 |

#### `gpt_image_2` — GPT Image 2 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high, resolution=1k |  | credits_per_generation | 3.5 |  | 1 → 3.5 | $0.0875 |
| quality=low, resolution=1k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |
| quality=medium, resolution=1k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| quality=high, resolution=2k |  | credits_per_generation | 7 |  | 1 → 7 | $0.1750 |
| quality=low, resolution=2k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |
| quality=medium, resolution=2k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=high, resolution=4k |  | credits_per_generation | 12 |  | 1 → 12 | $0.3000 |
| quality=low, resolution=4k |  | credits_per_generation | 0.75 |  | 1 → 0.75 | $0.0188 |
| quality=medium, resolution=4k |  | credits_per_generation | 3.5 |  | 1 → 3.5 | $0.0875 |

#### `gpt_image_2_5` — GPT Image 2.5 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| model=flare, quality=high, resolution=1k |  | credits_per_generation | 1.25 | 2 | 1 → 1.25 | $0.0312 |
| model=flare, quality=low, resolution=1k |  | credits_per_generation | 0.25 | 1 | 1 → 0.25 | $0.0062 |
| model=flare, quality=max, resolution=1k |  | credits_per_generation | 4.5 | 5 | 1 → 4.5 | $0.1125 |
| model=flare, quality=medium, resolution=1k |  | credits_per_generation | 0.5 | 1 | 1 → 0.5 | $0.0125 |
| model=flare, quality=xhigh, resolution=1k |  | credits_per_generation | 2 | 3 | 1 → 2 | $0.0500 |
| model=sunburst, quality=high, resolution=1k |  | credits_per_generation | 1.25 | 2 | 1 → 1.25 | $0.0312 |
| model=sunburst, quality=low, resolution=1k |  | credits_per_generation | 0.5 | 1 | 1 → 0.5 | $0.0125 |
| model=sunburst, quality=max, resolution=1k |  | credits_per_generation | 3.5 | 5 | 1 → 3.5 | $0.0875 |
| model=sunburst, quality=medium, resolution=1k |  | credits_per_generation | 0.75 | 1 | 1 → 0.75 | $0.0188 |
| model=sunburst, quality=xhigh, resolution=1k |  | credits_per_generation | 2 | 3 | 1 → 2 | $0.0500 |
| model=flare, quality=high, resolution=2k |  | credits_per_generation | 2.25 | 3 | 1 → 2.25 | $0.0562 |
| model=flare, quality=low, resolution=2k |  | credits_per_generation | 0.5 | 1 | 1 → 0.5 | $0.0125 |
| model=flare, quality=max, resolution=2k |  | credits_per_generation | 7 | 10 | 1 → 7 | $0.1750 |
| model=flare, quality=medium, resolution=2k |  | credits_per_generation | 0.75 | 1.5 | 1 → 0.75 | $0.0188 |
| model=flare, quality=xhigh, resolution=2k |  | credits_per_generation | 3.5 | 5 | 1 → 3.5 | $0.0875 |
| model=sunburst, quality=high, resolution=2k |  | credits_per_generation | 2.25 | 3 | 1 → 2.25 | $0.0562 |
| model=sunburst, quality=low, resolution=2k |  | credits_per_generation | 0.75 | 1 | 1 → 0.75 | $0.0188 |
| model=sunburst, quality=max, resolution=2k |  | credits_per_generation | 7 | 10 | 1 → 7 | $0.1750 |
| model=sunburst, quality=medium, resolution=2k |  | credits_per_generation | 1.25 | 1.5 | 1 → 1.25 | $0.0312 |
| model=sunburst, quality=xhigh, resolution=2k |  | credits_per_generation | 3.5 | 5 | 1 → 3.5 | $0.0875 |
| model=flare, quality=high, resolution=4k |  | credits_per_generation | 3.25 | 4.5 | 1 → 3.25 | $0.0812 |
| model=flare, quality=low, resolution=4k |  | credits_per_generation | 0.75 | 1.5 | 1 → 0.75 | $0.0188 |
| model=flare, quality=max, resolution=4k |  | credits_per_generation | 12 | 16 | 1 → 12 | $0.3000 |
| model=flare, quality=medium, resolution=4k |  | credits_per_generation | 1.25 | 2 | 1 → 1.25 | $0.0312 |
| model=flare, quality=xhigh, resolution=4k |  | credits_per_generation | 5.75 | 8 | 1 → 5.75 | $0.1438 |
| model=sunburst, quality=high, resolution=4k |  | credits_per_generation | 3.25 | 4.5 | 1 → 3.25 | $0.0812 |
| model=sunburst, quality=low, resolution=4k |  | credits_per_generation | 0.75 | 1.5 | 1 → 0.75 | $0.0188 |
| model=sunburst, quality=max, resolution=4k |  | credits_per_generation | 12 | 16 | 1 → 12 | $0.3000 |
| model=sunburst, quality=medium, resolution=4k |  | credits_per_generation | 1.25 | 2 | 1 → 1.25 | $0.0312 |
| model=sunburst, quality=xhigh, resolution=4k |  | credits_per_generation | 5.75 | 8 | 1 → 5.75 | $0.1438 |

#### `gpt_image_2_6` — GPT Image 2.6 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high, resolution=1k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| quality=low, resolution=1k |  | credits_per_generation | 0.75 |  | 1 → 0.75 | $0.0188 |
| quality=max, resolution=1k |  | credits_per_generation | 4.5 |  | 1 → 4.5 | $0.1125 |
| quality=medium, resolution=1k |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=xhigh, resolution=1k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=high, resolution=2k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=low, resolution=2k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| quality=max, resolution=2k |  | credits_per_generation | 7 |  | 1 → 7 | $0.1750 |
| quality=medium, resolution=2k |  | credits_per_generation | 1.75 |  | 1 → 1.75 | $0.0438 |
| quality=xhigh, resolution=2k |  | credits_per_generation | 3.5 |  | 1 → 3.5 | $0.0875 |
| quality=high, resolution=4k |  | credits_per_generation | 3.25 |  | 1 → 3.25 | $0.0812 |
| quality=low, resolution=4k |  | credits_per_generation | 1.75 |  | 1 → 1.75 | $0.0438 |
| quality=max, resolution=4k |  | credits_per_generation | 12 |  | 1 → 12 | $0.3000 |
| quality=medium, resolution=4k |  | credits_per_generation | 2.75 |  | 1 → 2.75 | $0.0688 |
| quality=xhigh, resolution=4k |  | credits_per_generation | 5.5 |  | 1 → 5.5 | $0.1375 |

#### `gpt_image_2_6_flare` — GPT Image 2.6 Flare (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high, resolution=1k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| quality=low, resolution=1k |  | credits_per_generation | 0.75 |  | 1 → 0.75 | $0.0188 |
| quality=max, resolution=1k |  | credits_per_generation | 6.5 |  | 1 → 6.5 | $0.1625 |
| quality=medium, resolution=1k |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=xhigh, resolution=1k |  | credits_per_generation | 2.25 |  | 1 → 2.25 | $0.0562 |
| quality=high, resolution=2k |  | credits_per_generation | 2.25 |  | 1 → 2.25 | $0.0562 |
| quality=low, resolution=2k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| quality=max, resolution=2k |  | credits_per_generation | 6.75 |  | 1 → 6.75 | $0.1688 |
| quality=medium, resolution=2k |  | credits_per_generation | 1.75 |  | 1 → 1.75 | $0.0438 |
| quality=xhigh, resolution=2k |  | credits_per_generation | 3.25 |  | 1 → 3.25 | $0.0812 |
| quality=high, resolution=4k |  | credits_per_generation | 3.5 |  | 1 → 3.5 | $0.0875 |
| quality=low, resolution=4k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=max, resolution=4k |  | credits_per_generation | 12 |  | 1 → 12 | $0.3000 |
| quality=medium, resolution=4k |  | credits_per_generation | 2.75 |  | 1 → 2.75 | $0.0688 |
| quality=xhigh, resolution=4k |  | credits_per_generation | 5.5 |  | 1 → 5.5 | $0.1375 |

#### `ideogram_4_5` — Ideogram 4.5 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high |  | credits_per_generation | 6.25 |  | 1 → 6.25 | $0.1562 |
| quality=low |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=medium |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=very_low |  | credits_per_generation | 0.25 |  | 1 → 0.25 | $0.0062 |

#### `ideogram_4_5_precise_edit` — Ideogram 4.5 Precise Edit (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high |  | credits_per_generation | 7 |  | 1 → 7 | $0.1750 |
| quality=low |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=medium |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=very_low |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |

#### `ideogram_4_6` — Ideogram 4.6 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high, resolution=2k, has_references=False |  | credits_per_generation | 3.25 |  | 1 → 3.25 | $0.0812 |
| quality=low, resolution=2k, has_references=False |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=medium, resolution=2k, has_references=False |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=high, resolution=2k, has_references=True |  | credits_per_generation | 7 |  | 1 → 7 | $0.1750 |
| quality=low, resolution=2k, has_references=True |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=medium, resolution=2k, has_references=True |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=high, resolution=4k, has_references=False |  | credits_per_generation | 6.25 |  | 1 → 6.25 | $0.1562 |
| quality=low, resolution=4k, has_references=False |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=medium, resolution=4k, has_references=False |  | credits_per_generation | 3.75 |  | 1 → 3.75 | $0.0938 |
| quality=high, resolution=4k, has_references=True |  | credits_per_generation | 19 |  | 1 → 19 | $0.4750 |
| quality=low, resolution=4k, has_references=True |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=medium, resolution=4k, has_references=True |  | credits_per_generation | 6.25 |  | 1 → 6.25 | $0.1562 |

#### `ideogram_4_6_precise_edit` — Ideogram 4.6 Precise Edit (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| quality=high, resolution=2k |  | credits_per_generation | 7 |  | 1 → 7 | $0.1750 |
| quality=low, resolution=2k |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| quality=medium, resolution=2k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=high, resolution=4k |  | credits_per_generation | 19 |  | 1 → 19 | $0.4750 |
| quality=low, resolution=4k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| quality=medium, resolution=4k |  | credits_per_generation | 6.25 |  | 1 → 6.25 | $0.1562 |

#### `ideogram_vector` — Ideogram Vector (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| operation=generate, quality=high, has_references=False |  | credits_per_generation | 6.5 |  | 1 → 6.5 | $0.1625 |
| operation=generate, quality=low, has_references=False |  | credits_per_generation | 4 |  | 1 → 4 | $0.1000 |
| operation=generate, quality=medium, has_references=False |  | credits_per_generation | 5 |  | 1 → 5 | $0.1250 |
| operation=generate, quality=high, has_references=True |  | credits_per_generation | 10 |  | 1 → 10 | $0.2500 |
| operation=generate, quality=low, has_references=True |  | credits_per_generation | 4 |  | 1 → 4 | $0.1000 |
| operation=generate, quality=medium, has_references=True |  | credits_per_generation | 5 |  | 1 → 5 | $0.1250 |
| operation=vectorize |  | credits_per_generation | 3 |  | 1 → 3 | $0.0750 |

#### `kling_image_4_0` — Kling Image 4.0 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=2k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| resolution=4k |  | credits_per_generation | 3 |  | 1 → 3 | $0.0750 |
| resolution=8k |  | credits_per_generation | 5 |  | 1 → 5 | $0.1250 |

#### `minimax_h3_image` — Minimax H3 Image (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1k |  | credits_per_generation | 3 |  | 1 → 3 | $0.0750 |
| resolution=2k |  | credits_per_generation | 3 |  | 1 → 3 | $0.0750 |
| resolution=4k |  | credits_per_generation | 4 |  | 1 → 4 | $0.1000 |

#### `nano_banana_2_1` — Nano Banana 2.1 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1k |  | credits_per_generation | 1.5 |  | 1 → 1.5 | $0.0375 |
| resolution=2k |  | credits_per_generation | 2 |  | 1 → 2 | $0.0500 |
| resolution=4k |  | credits_per_generation | 3 |  | 1 → 3 | $0.0750 |

#### `p_image_ideogram` — Ideogram (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| thinking=high, resolution=1k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |
| thinking=low, resolution=1k |  | credits_per_generation | 0.25 |  | 1 → 0.25 | $0.0062 |
| thinking=medium, resolution=1k |  | credits_per_generation | 0.3 |  | 1 → 0.3 | $0.0075 |
| thinking=very-low, resolution=1k |  | credits_per_generation | 0.1 |  | 1 → 0.1 | $0.0025 |
| thinking=high, resolution=2k |  | credits_per_generation | 1 |  | 1 → 1 | $0.0250 |
| thinking=low, resolution=2k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |
| thinking=medium, resolution=2k |  | credits_per_generation | 0.6 |  | 1 → 0.6 | $0.0150 |
| thinking=very-low, resolution=2k |  | credits_per_generation | 0.2 |  | 1 → 0.2 | $0.0050 |

#### `recraft_v4_1` — Recraft V4.1 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| model_type=standard, resolution=1k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| model_type=utility, resolution=1k |  | credits_per_generation | 1.25 |  | 1 → 1.25 | $0.0312 |
| model_type=utility_vector, resolution=1k |  | credits_per_generation | 2.5 |  | 1 → 2.5 | $0.0625 |
| model_type=vector, resolution=1k |  | credits_per_generation | 2.5 |  | 1 → 2.5 | $0.0625 |
| model_type=standard, resolution=2k |  | credits_per_generation | 8 |  | 1 → 8 | $0.2000 |
| model_type=utility, resolution=2k |  | credits_per_generation | 8 |  | 1 → 8 | $0.2000 |
| model_type=utility_vector, resolution=2k |  | credits_per_generation | 10 |  | 1 → 10 | $0.2500 |
| model_type=vector, resolution=2k |  | credits_per_generation | 10 |  | 1 → 10 | $0.2500 |

#### `seedream_5_0_flash` — Seedream 5.0 Flash (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |
| resolution=1.5k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |
| resolution=2k |  | credits_per_generation | 0.5 |  | 1 → 0.5 | $0.0125 |

#### `seedream_5_5` — Seedream 5.5 (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1k |  | credits_per_generation | 2.5 |  | 1 → 2.5 | $0.0625 |
| resolution=1.5k |  | credits_per_generation | 2.5 |  | 1 → 2.5 | $0.0625 |
| resolution=2k |  | credits_per_generation | 3.5 |  | 1 → 3.5 | $0.0875 |

#### `seedream_v5_pro` — Seedream 5.0 Pro (image, credits_per_generation)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1k |  | credits_per_generation | 1.25 | 1.5 | 1 → 1.25 | $0.0312 |
| resolution=1.5k |  | credits_per_generation | 1.25 | 1.5 | 1 → 1.25 | $0.0312 |
| resolution=2k |  | credits_per_generation | 2.5 | 3 | 1 → 2.5 | $0.0625 |

#### `ad_multiplier` — Ad Multiplier (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `ad_multiplier_replace` — Ad Multiplier Replace (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |

#### `ad_multiplier_v2` — Ad Multiplier V2 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `ai_host_video` — AI Host Video (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| resolution=720p |  | credits_per_second | 7.7 |  | seconds=5.0 → 38.5 | $0.9625 |
| resolution=1080p |  | credits_per_second | 17.6 |  | seconds=5.0 → 88 | $2.2000 |

#### `ai_influencer_motion_control` — AI Influencer Motion Control (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |

#### `ai_influencer_motion_control_flash` — AI Influencer Motion Control Flash (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 1 | 3 | seconds=5.0 → 5 | $0.1250 |
| resolution=720p |  | credits_per_second | 2 | 6 | seconds=5.0 → 10 | $0.2500 |
| resolution=1080p |  | credits_per_second | 4 | 12 | seconds=5.0 → 20 | $0.5000 |

#### `ai_influencer_replace_object` — AI Influencer Replace Object (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |

#### `ai_influencer_replace_object_flash` — AI Influencer Replace Object Flash (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 1 | 3 | seconds=5.0 → 5 | $0.1250 |
| resolution=720p |  | credits_per_second | 2 | 6 | seconds=5.0 → 10 | $0.2500 |
| resolution=1080p |  | credits_per_second | 4 | 12 | seconds=5.0 → 20 | $0.5000 |

#### `cinematic_studio_3_0` — Cinematic Studio 3.0 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3.5 | 6 | seconds=5.0 → 17.5 | $0.4375 |
| resolution=720p |  | credits_per_second | 5 | 6 | seconds=5.0 → 25 | $0.6250 |
| resolution=1080p |  | credits_per_second | 13 |  | seconds=5.0 → 65 | $1.6250 |
| resolution=4k |  | credits_per_second | 24 | 26 | seconds=5.0 → 120 | $3.0000 |

#### `cinematic_studio_video_3_5` — Cinematic Studio Video 3.5 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3.5 | 6 | seconds=5.0 → 17.5 | $0.4375 |
| resolution=720p |  | credits_per_second | 5 | 6 | seconds=5.0 → 25 | $0.6250 |
| resolution=1080p |  | credits_per_second | 13 |  | seconds=5.0 → 65 | $1.6250 |
| resolution=4k |  | credits_per_second | 24 | 26 | seconds=5.0 → 120 | $3.0000 |

#### `cinematic_studio_video_4_0` — Cinematic Studio Video 4.0 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |
| resolution=480p | video_edit | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p | video_edit | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p | video_edit | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k | video_edit | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |

#### `cinematic_video_editor` — Cinematic Video Editor (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=480p | video_edit | credits_per_second | 3.5 |  | seconds=5.0 → 17.5 | $0.4375 |
| resolution=720p | video_edit | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| resolution=1080p | video_edit | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |

#### `cinematic_video_inpaint` — Cinematic Video Inpaint (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `cinematic_video_relight` — Cinematic Video Relight (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `depth_anything_video` — Depth Anything Video (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_second | 1.5 |  | seconds=5.0 → 7.5 | $0.1875 |

#### `draw_to_video` — Draw To Video (video, credits_per_frame, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=720p |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=720p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=1080p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| resolution=1080p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |

#### `flux_3_video` — Flux 3 Video (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p, video_input=with_video |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| resolution=720p, video_input=without_video |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 8 |  | seconds=5.0 → 40 | $1.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 8 |  | seconds=5.0 → 40 | $1.0000 |
| resolution=2k, video_input=with_video |  | credits_per_second | 10 |  | seconds=5.0 → 50 | $1.2500 |
| resolution=2k, video_input=without_video |  | credits_per_second | 10 |  | seconds=5.0 → 50 | $1.2500 |
| resolution=4k, video_input=with_video |  | credits_per_second | 13 |  | seconds=5.0 → 65 | $1.6250 |
| resolution=4k, video_input=without_video |  | credits_per_second | 13 |  | seconds=5.0 → 65 | $1.6250 |

#### `flux_video_upscale` — Flux Video Upscale (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| creativity=0, source_resolution=480p, resolution=720p |  | credits_per_second | 0.5 | 1 | seconds=5.0 → 2.5 | $0.0625 |
| creativity=1, source_resolution=480p, resolution=720p |  | credits_per_second | 0.75 | 1.5 | seconds=5.0 → 3.75 | $0.0938 |
| creativity=0, source_resolution=480p, resolution=1080p |  | credits_per_second | 1.75 | 3.5 | seconds=5.0 → 8.75 | $0.2188 |
| creativity=0, source_resolution=720p, resolution=1080p |  | credits_per_second | 1.75 | 3.5 | seconds=5.0 → 8.75 | $0.2188 |
| creativity=1, source_resolution=480p, resolution=1080p |  | credits_per_second | 2.5 | 5 | seconds=5.0 → 12.5 | $0.3125 |
| creativity=1, source_resolution=720p, resolution=1080p |  | credits_per_second | 1.75 | 3.5 | seconds=5.0 → 8.75 | $0.2188 |
| creativity=0, source_resolution=1080p, resolution=2k |  | credits_per_second | 1.75 | 3.5 | seconds=5.0 → 8.75 | $0.2188 |
| creativity=0, source_resolution=480p, resolution=2k |  | credits_per_second | 3.5 | 7 | seconds=5.0 → 17.5 | $0.4375 |
| creativity=0, source_resolution=720p, resolution=2k |  | credits_per_second | 3 | 6 | seconds=5.0 → 15 | $0.3750 |
| creativity=1, source_resolution=1080p, resolution=2k |  | credits_per_second | 2.5 | 5 | seconds=5.0 → 12.5 | $0.3125 |
| creativity=1, source_resolution=480p, resolution=2k |  | credits_per_second | 5 | 10 | seconds=5.0 → 25 | $0.6250 |
| creativity=1, source_resolution=720p, resolution=2k |  | credits_per_second | 4 | 8 | seconds=5.0 → 20 | $0.5000 |
| creativity=0, source_resolution=1080p, resolution=4k |  | credits_per_second | 6.5 | 13 | seconds=5.0 → 32.5 | $0.8125 |
| creativity=0, source_resolution=2k, resolution=4k |  | credits_per_second | 5 | 10 | seconds=5.0 → 25 | $0.6250 |
| creativity=0, source_resolution=720p, resolution=4k |  | credits_per_second | 8 | 16 | seconds=5.0 → 40 | $1.0000 |
| creativity=1, source_resolution=1080p, resolution=4k |  | credits_per_second | 9 | 18 | seconds=5.0 → 45 | $1.1250 |
| creativity=1, source_resolution=2k, resolution=4k |  | credits_per_second | 7 | 14 | seconds=5.0 → 35 | $0.8750 |
| creativity=1, source_resolution=720p, resolution=4k |  | credits_per_second | 11 | 22 | seconds=5.0 → 55 | $1.3750 |

#### `fps_boost` — FPS Boost (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| model=topaz, input_fps=24, output_fps=120, source_resolution=1080p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=120, source_resolution=2k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=120, source_resolution=480p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=120, source_resolution=4k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=120, source_resolution=720p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=30, source_resolution=1080p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=30, source_resolution=2k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=30, source_resolution=480p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=30, source_resolution=4k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=30, source_resolution=720p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=60, source_resolution=1080p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=60, source_resolution=2k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=60, source_resolution=480p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=60, source_resolution=4k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=60, source_resolution=720p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=90, source_resolution=1080p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=90, source_resolution=2k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=90, source_resolution=480p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=24, output_fps=90, source_resolution=4k |  | credits_per_second | 5.5 |  | seconds=5.0 → 27.5 | $0.6875 |
| model=topaz, input_fps=24, output_fps=90, source_resolution=720p |  | credits_per_second | 3.3 |  | seconds=5.0 → 16.5 | $0.4125 |
| model=topaz, input_fps=30, output_fps=120, source_resolution=1080p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=120, source_resolution=2k |  | credits_per_second | 6.9 |  | seconds=5.0 → 34.5 | $0.8625 |
| model=topaz, input_fps=30, output_fps=120, source_resolution=480p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=120, source_resolution=4k |  | credits_per_second | 6.9 |  | seconds=5.0 → 34.5 | $0.8625 |
| model=topaz, input_fps=30, output_fps=120, source_resolution=720p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=60, source_resolution=1080p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=60, source_resolution=2k |  | credits_per_second | 6.9 |  | seconds=5.0 → 34.5 | $0.8625 |
| model=topaz, input_fps=30, output_fps=60, source_resolution=480p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=60, source_resolution=4k |  | credits_per_second | 6.9 |  | seconds=5.0 → 34.5 | $0.8625 |
| model=topaz, input_fps=30, output_fps=60, source_resolution=720p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=90, source_resolution=1080p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=90, source_resolution=2k |  | credits_per_second | 6.9 |  | seconds=5.0 → 34.5 | $0.8625 |
| model=topaz, input_fps=30, output_fps=90, source_resolution=480p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=30, output_fps=90, source_resolution=4k |  | credits_per_second | 6.9 |  | seconds=5.0 → 34.5 | $0.8625 |
| model=topaz, input_fps=30, output_fps=90, source_resolution=720p |  | credits_per_second | 4.1 |  | seconds=5.0 → 20.5 | $0.5125 |
| model=topaz, input_fps=60, output_fps=120, source_resolution=1080p |  | credits_per_second | 8.1 |  | seconds=5.0 → 40.5 | $1.0125 |
| model=topaz, input_fps=60, output_fps=120, source_resolution=2k |  | credits_per_second | 13.7 |  | seconds=5.0 → 68.5 | $1.7125 |
| model=topaz, input_fps=60, output_fps=120, source_resolution=480p |  | credits_per_second | 8.1 |  | seconds=5.0 → 40.5 | $1.0125 |
| model=topaz, input_fps=60, output_fps=120, source_resolution=4k |  | credits_per_second | 13.7 |  | seconds=5.0 → 68.5 | $1.7125 |
| model=topaz, input_fps=60, output_fps=120, source_resolution=720p |  | credits_per_second | 8.1 |  | seconds=5.0 → 40.5 | $1.0125 |
| model=topaz, input_fps=60, output_fps=90, source_resolution=1080p |  | credits_per_second | 8.1 |  | seconds=5.0 → 40.5 | $1.0125 |
| model=topaz, input_fps=60, output_fps=90, source_resolution=2k |  | credits_per_second | 13.7 |  | seconds=5.0 → 68.5 | $1.7125 |
| model=topaz, input_fps=60, output_fps=90, source_resolution=480p |  | credits_per_second | 8.1 |  | seconds=5.0 → 40.5 | $1.0125 |
| model=topaz, input_fps=60, output_fps=90, source_resolution=4k |  | credits_per_second | 13.7 |  | seconds=5.0 → 68.5 | $1.7125 |
| model=topaz, input_fps=60, output_fps=90, source_resolution=720p |  | credits_per_second | 8.1 |  | seconds=5.0 → 40.5 | $1.0125 |
| model=topaz, input_fps=90, output_fps=120, source_resolution=1080p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| model=topaz, input_fps=90, output_fps=120, source_resolution=2k |  | credits_per_second | 20.5 |  | seconds=5.0 → 102.5 | $2.5625 |
| model=topaz, input_fps=90, output_fps=120, source_resolution=480p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| model=topaz, input_fps=90, output_fps=120, source_resolution=4k |  | credits_per_second | 20.5 |  | seconds=5.0 → 102.5 | $2.5625 |
| model=topaz, input_fps=90, output_fps=120, source_resolution=720p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| model=bytedance, source_resolution=1080p, min_fps=61, max_fps=120 |  | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| model=bytedance, source_resolution=2k, min_fps=61, max_fps=120 |  | credits_per_second | 15 |  | seconds=5.0 → 75 | $1.8750 |
| model=bytedance, source_resolution=4k, min_fps=61, max_fps=120 |  | credits_per_second | 30 |  | seconds=5.0 → 150 | $3.7500 |
| model=bytedance, source_resolution=8k, min_fps=61, max_fps=120 |  | credits_per_second | 120 |  | seconds=5.0 → 600 | $15.0000 |
| model=bytedance, source_resolution=1080p, min_fps=24, max_fps=30 |  | credits_per_second | 2 |  | seconds=5.0 → 10 | $0.2500 |
| model=bytedance, source_resolution=2k, min_fps=24, max_fps=30 |  | credits_per_second | 4 |  | seconds=5.0 → 20 | $0.5000 |
| model=bytedance, source_resolution=4k, min_fps=24, max_fps=30 |  | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| model=bytedance, source_resolution=8k, min_fps=24, max_fps=30 |  | credits_per_second | 30 |  | seconds=5.0 → 150 | $3.7500 |
| model=bytedance, source_resolution=1080p, min_fps=31, max_fps=60 |  | credits_per_second | 4 |  | seconds=5.0 → 20 | $0.5000 |
| model=bytedance, source_resolution=2k, min_fps=31, max_fps=60 |  | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| model=bytedance, source_resolution=4k, min_fps=31, max_fps=60 |  | credits_per_second | 15 |  | seconds=5.0 → 75 | $1.8750 |
| model=bytedance, source_resolution=8k, min_fps=31, max_fps=60 |  | credits_per_second | 60 |  | seconds=5.0 → 300 | $7.5000 |

#### `gemini_omni` — Gemini Omni (video, base_credits, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | base_credits | 0 |  | 1 → 0 | $0.0000 |
| resolution=1080p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=1080p |  | base_credits | 0 |  | 1 → 0 | $0.0000 |
| resolution=4k |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=4k |  | base_credits | 0 |  | 1 → 0 | $0.0000 |

#### `gemini_omni_flash_1_2` — Gemini Omni Flash 1.2 (video, base_credits, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=360p |  | credits_per_second | 0.75 |  | seconds=5.0 → 3.75 | $0.0938 |
| resolution=360p |  | base_credits | 0 |  | 1 → 0 | $0.0000 |
| resolution=720p |  | credits_per_second | 2.25 |  | seconds=5.0 → 11.25 | $0.2812 |
| resolution=720p |  | base_credits | 0 |  | 1 → 0 | $0.0000 |
| resolution=1080p |  | credits_per_second | 3.25 |  | seconds=5.0 → 16.25 | $0.4062 |
| resolution=1080p |  | base_credits | 0 |  | 1 → 0 | $0.0000 |
| resolution=4k |  | credits_per_second | 6.75 |  | seconds=5.0 → 33.75 | $0.8438 |
| resolution=4k |  | base_credits | 0 |  | 1 → 0 | $0.0000 |

#### `grok_video_v15` — Grok Video v1.5 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 2.5 |  | seconds=5.0 → 12.5 | $0.3125 |
| resolution=720p |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=1080p |  | credits_per_second | 8 |  | seconds=5.0 → 40 | $1.0000 |

#### `grok_video_v15_lite` — Grok Video v1.5 Lite (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 1 |  | seconds=5.0 → 5 | $0.1250 |
| resolution=720p |  | credits_per_second | 1 |  | seconds=5.0 → 5 | $0.1250 |
| resolution=1080p |  | credits_per_second | 4 |  | seconds=5.0 → 20 | $0.5000 |

#### `happy_horse_video` — Happy Horse Video (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p |  | credits_per_second | 2.5 | 4 | seconds=5.0 → 12.5 | $0.3125 |
| resolution=1080p |  | credits_per_second | 4.5 | 8 | seconds=5.0 → 22.5 | $0.5625 |

#### `hf_evolution` — HF Evolution (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p, model=hf_evolution |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |

#### `hf_mult_motion_control` — Higgsfield Genjutsu (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |

#### `hf_mult_motion_control_flash` — HF Mult Motion Control Flash (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 1 | 3 | seconds=5.0 → 5 | $0.1250 |
| resolution=720p |  | credits_per_second | 2 | 6 | seconds=5.0 → 10 | $0.2500 |
| resolution=1080p |  | credits_per_second | 4 | 12 | seconds=5.0 → 20 | $0.5000 |

#### `hf_mult_replace_object` — HF Mult Replace Object (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |

#### `hf_mult_replace_object_flash` — HF Mult Replace Object Flash (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p |  | credits_per_second | 2 | 6 | seconds=5.0 → 10 | $0.2500 |
| resolution=1080p |  | credits_per_second | 4 | 12 | seconds=5.0 → 20 | $0.5000 |

#### `intone` — Intone (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `kling3_0` — Kling 3.0 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| mode=4k, audio=off |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| mode=pro, audio=off |  | credits_per_second | 1.75 |  | seconds=5.0 → 8.75 | $0.2188 |
| mode=std, audio=off |  | credits_per_second | 1.5 |  | seconds=5.0 → 7.5 | $0.1875 |
| mode=4k, audio=on |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| mode=pro, audio=on |  | credits_per_second | 2.5 |  | seconds=5.0 → 12.5 | $0.3125 |
| mode=std, audio=on |  | credits_per_second | 2 |  | seconds=5.0 → 10 | $0.2500 |

#### `kling3_0_motion_control` — Kling 3.0 Motion Control (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| mode=pro |  | credits_per_second | 2.5 |  | seconds=5.0 → 12.5 | $0.3125 |
| mode=std |  | credits_per_second | 1.5 |  | seconds=5.0 → 7.5 | $0.1875 |

#### `kling3_0_turbo` — Kling 3.0 Turbo (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p |  | credits_per_second | 1.5 |  | seconds=5.0 → 7.5 | $0.1875 |
| resolution=1080p |  | credits_per_second | 2 |  | seconds=5.0 → 10 | $0.2500 |

#### `kling4_0` — Kling 4.0 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 2.5 |  | seconds=5.0 → 12.5 | $0.3125 |
| resolution=1080p, video_hdr=with_video |  | credits_per_second | 5.25 |  | seconds=5.0 → 26.25 | $0.6562 |
| resolution=1080p, video_hdr=without_video |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 3.75 |  | seconds=5.0 → 18.75 | $0.4688 |
| resolution=4k, video_hdr=with_video |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| resolution=4k, video_hdr=without_video |  | credits_per_second | 10 |  | seconds=5.0 → 50 | $1.2500 |
| resolution=4k, video_input=with_video |  | credits_per_second | 10.5 |  | seconds=5.0 → 52.5 | $1.3125 |
| resolution=4k, video_input=without_video |  | credits_per_second | 9 |  | seconds=5.0 → 45 | $1.1250 |

#### `kling_4_0_flash` — Kling 4.0 Flash (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=720p, video_input=with_video |  | credits_per_second | 2 | 4 | seconds=5.0 → 10 | $0.2500 |
| resolution=720p, video_input=without_video |  | credits_per_second | 1.5 | 3 | seconds=5.0 → 7.5 | $0.1875 |

#### `kling_o3_flf` — Kling O3 FLF (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| mode=4k, audio=off |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| mode=pro, audio=off |  | credits_per_second | 1.25 |  | seconds=5.0 → 6.25 | $0.1562 |
| mode=std, audio=off |  | credits_per_second | 1 |  | seconds=5.0 → 5 | $0.1250 |
| mode=4k, audio=on |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| mode=pro, audio=on |  | credits_per_second | 1.8 |  | seconds=5.0 → 9 | $0.2250 |
| mode=std, audio=on |  | credits_per_second | 1.25 |  | seconds=5.0 → 6.25 | $0.1562 |

#### `kling_o3_image_reference` — Kling O3 Image Reference (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| mode=4k, audio=off |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| mode=pro, audio=off |  | credits_per_second | 1.5 |  | seconds=5.0 → 7.5 | $0.1875 |
| mode=std, audio=off |  | credits_per_second | 1 |  | seconds=5.0 → 5 | $0.1250 |
| mode=4k, audio=on |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| mode=pro, audio=on |  | credits_per_second | 2 |  | seconds=5.0 → 10 | $0.2500 |
| mode=std, audio=on |  | credits_per_second | 1.25 |  | seconds=5.0 → 6.25 | $0.1562 |

#### `marketing_studio_video` — Marketing Studio Video (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3.5 | 4 | seconds=5.0 → 17.5 | $0.4375 |
| resolution=720p |  | credits_per_second | 5 | 6 | seconds=5.0 → 25 | $0.6250 |
| resolution=1080p |  | credits_per_second | 13 |  | seconds=5.0 → 65 | $1.6250 |

#### `minimax_h3_highspeed` — Minimax H3 Highspeed (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 1.25 |  | seconds=5.0 → 6.25 | $0.1562 |
| resolution=768p |  | credits_per_second | 2 |  | seconds=5.0 → 10 | $0.2500 |

#### `minimax_h3_lite` — Minimax H3 Lite (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 1 |  | seconds=5.0 → 5 | $0.1250 |
| resolution=768p |  | credits_per_second | 1.25 |  | seconds=5.0 → 6.25 | $0.1562 |

#### `reframe` — Reframe (video, credits_per_image, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p |  | credits_per_image | 1.25 |  | 1 → 1.25 | $0.0312 |
| resolution=720p |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=720p |  | credits_per_image | 1.25 |  | 1 → 1.25 | $0.0312 |
| resolution=1080p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| resolution=1080p |  | credits_per_image | 1.25 |  | 1 → 1.25 | $0.0312 |

#### `remove_object` — Remove Object (video, credits_per_frame, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=720p |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=720p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=1080p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| resolution=1080p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |

#### `sam_3_video` — SAM 3 Video (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| — |  | credits_per_second | 0.225 |  | seconds=5.0 → 1.125 | $0.0281 |

#### `scene_switch` — Scene Switch (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| tier=pro, resolution=720p, cost_per_run=12.46, cost_per_piece=12.46, piece=run, masks_cost_per_frame=0, picture_cost=0, look_cost=0 |  | credits_per_second | 9.28 |  | seconds=5.0 → 46.4 | $1.1600 |
| tier=pro, resolution=1080p, cost_per_run=12.46, cost_per_piece=12.46, piece=run, masks_cost_per_frame=0, picture_cost=0, look_cost=0 |  | credits_per_second | 22.53 |  | seconds=5.0 → 112.65 | $2.8162 |
| tier=basic, resolution=1080p, cost_per_run=8.87, cost_per_piece=8.87, piece=run, masks_cost_per_frame=0, picture_cost=0, look_cost=0 |  | credits_per_second | 4.03 |  | seconds=5.0 → 20.15 | $0.5038 |
| tier=pro, resolution=4k, cost_per_run=12.46, cost_per_piece=12.46, piece=run, masks_cost_per_frame=0, picture_cost=0, look_cost=0 |  | credits_per_second | 37.58 |  | seconds=5.0 → 187.9 | $4.6975 |

#### `seedance_2_0` — Seedance 2.0 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| model=seedance_2_0, resolution=480p |  | credits_per_second | 3 | 6 | seconds=5.0 → 15 | $0.3750 |
| model=seedance_2_0_fast, resolution=480p |  | credits_per_second | 1 | 1.5 | seconds=5.0 → 5 | $0.1250 |
| model=seedance_2_0, resolution=720p |  | credits_per_second | 4.5 | 6 | seconds=5.0 → 22.5 | $0.5625 |
| model=seedance_2_0_fast, resolution=720p |  | credits_per_second | 2.5 | 3.5 | seconds=5.0 → 12.5 | $0.3125 |
| model=seedance_2_0, resolution=1080p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| model=seedance_2_0_fast, resolution=1080p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| model=seedance_2_0, resolution=4k |  | credits_per_second | 22 | 26 | seconds=5.0 → 110 | $2.7500 |
| model=seedance_2_0_fast, resolution=4k |  | credits_per_second | 14 |  | seconds=5.0 → 70 | $1.7500 |

#### `seedance_2_0_mini` — Seedance 2.0 Mini (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 0.5 | 1 | seconds=5.0 → 2.5 | $0.0625 |
| resolution=720p |  | credits_per_second | 1 | 2.5 | seconds=5.0 → 5 | $0.1250 |

#### `seedance_2_5` — Seedance 2.5 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |
| resolution=480p | video_edit | credits_per_second | 3.5 |  | seconds=5.0 → 17.5 | $0.4375 |
| resolution=720p | video_edit | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| resolution=1080p | video_edit | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=4k | video_edit | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |

#### `seedance_2_5_flash` — Seedance 2.5 Flash (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 2.5 |  | seconds=5.0 → 12.5 | $0.3125 |
| resolution=480p, video_input=without_video |  | credits_per_second | 2 |  | seconds=5.0 → 10 | $0.2500 |
| resolution=720p, video_input=with_video |  | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |
| resolution=720p, video_input=without_video |  | credits_per_second | 5 |  | seconds=5.0 → 25 | $0.6250 |
| resolution=480p | video_edit | credits_per_second | 2.5 |  | seconds=5.0 → 12.5 | $0.3125 |
| resolution=720p | video_edit | credits_per_second | 6 |  | seconds=5.0 → 30 | $0.7500 |

#### `seedance_2_5_kling_upscale` — Seedance 2.5 Kling Upscale (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=1080p |  | credits_per_second | 4 |  | seconds=5.0 → 20 | $0.5000 |

#### `swap_object` — Swap Object (video, credits_per_frame, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=720p |  | credits_per_second | 4.5 |  | seconds=5.0 → 22.5 | $0.5625 |
| resolution=720p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=1080p |  | credits_per_second | 12 |  | seconds=5.0 → 60 | $1.5000 |
| resolution=1080p |  | credits_per_frame | 3.5 |  | 1 → 3.5 | $0.0875 |

#### `topaz_hyperion_2_5` — Topaz Hyperion 2.5 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 2.6 |  | seconds=5.0 → 13 | $0.3250 |
| resolution=720p |  | credits_per_second | 2.6 |  | seconds=5.0 → 13 | $0.3250 |
| resolution=1080p |  | credits_per_second | 2.6 |  | seconds=5.0 → 13 | $0.3250 |
| resolution=2k |  | credits_per_second | 5.2 |  | seconds=5.0 → 26 | $0.6500 |
| resolution=4k |  | credits_per_second | 5.2 |  | seconds=5.0 → 26 | $0.6500 |

#### `video_character_asset` — Video Character Asset (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `videoshop_camera_move` — Videoshop Camera Move (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |

#### `videoshop_edit` — Videoshop Edit (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3.5 |  | seconds=5.0 → 17.5 | $0.4375 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3.5 |  | seconds=5.0 → 17.5 | $0.4375 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7.5 |  | seconds=5.0 → 37.5 | $0.9375 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |

#### `videoshop_genjutsu` — Videoshop Genjutsu (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=720p |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=1080p |  | credits_per_second | 20 |  | seconds=5.0 → 100 | $2.5000 |

#### `videoshop_relight` — Videoshop Relight (video, credits_per_image, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p, video_input=without_video |  | credits_per_second | 3 |  | seconds=5.0 → 15 | $0.3750 |
| resolution=480p |  | credits_per_image | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=720p, video_input=with_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 7 |  | seconds=5.0 → 35 | $0.8750 |
| resolution=720p |  | credits_per_image | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 16 |  | seconds=5.0 → 80 | $2.0000 |
| resolution=1080p |  | credits_per_image | 3.5 |  | 1 → 3.5 | $0.0875 |
| resolution=4k, video_input=with_video |  | credits_per_second | 34 |  | seconds=5.0 → 170 | $4.2500 |
| resolution=4k, video_input=without_video |  | credits_per_second | 28 |  | seconds=5.0 → 140 | $3.5000 |
| resolution=4k |  | credits_per_image | 3.5 |  | 1 → 3.5 | $0.0875 |

#### `wan3_0` — Wan 3.0 (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 1.5 | 2.5 | seconds=5.0 → 7.5 | $0.1875 |
| resolution=480p, video_input=without_video |  | credits_per_second | 0.75 | 1.25 | seconds=5.0 → 3.75 | $0.0938 |
| resolution=480p |  | credits_per_second | 0.75 | 1.25 | seconds=5.0 → 3.75 | $0.0938 |
| resolution=720p, video_input=with_video |  | credits_per_second | 3 | 5 | seconds=5.0 → 15 | $0.3750 |
| resolution=720p, video_input=without_video |  | credits_per_second | 1.5 | 2.5 | seconds=5.0 → 7.5 | $0.1875 |
| resolution=720p |  | credits_per_second | 1.5 | 2.5 | seconds=5.0 → 7.5 | $0.1875 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 6 | 10 | seconds=5.0 → 30 | $0.7500 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 3 | 5.5 | seconds=5.0 → 15 | $0.3750 |
| resolution=1080p |  | credits_per_second | 3 | 5.5 | seconds=5.0 → 15 | $0.3750 |

#### `wan3_0_prime` — Wan 3.0 Prime (video, credits_per_second)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| resolution=480p, video_input=with_video |  | credits_per_second | 2.5 | 3.5 | seconds=5.0 → 12.5 | $0.3125 |
| resolution=480p, video_input=without_video |  | credits_per_second | 1.25 | 1.75 | seconds=5.0 → 6.25 | $0.1562 |
| resolution=480p |  | credits_per_second | 1.25 | 1.75 | seconds=5.0 → 6.25 | $0.1562 |
| resolution=720p, video_input=with_video |  | credits_per_second | 5.5 | 7 | seconds=5.0 → 27.5 | $0.6875 |
| resolution=720p, video_input=without_video |  | credits_per_second | 2.75 | 3.5 | seconds=5.0 → 13.75 | $0.3438 |
| resolution=720p |  | credits_per_second | 2.75 | 3.5 | seconds=5.0 → 13.75 | $0.3438 |
| resolution=1080p, video_input=with_video |  | credits_per_second | 11 | 15 | seconds=5.0 → 55 | $1.3750 |
| resolution=1080p, video_input=without_video |  | credits_per_second | 5.5 | 7.5 | seconds=5.0 → 27.5 | $0.6875 |
| resolution=1080p |  | credits_per_second | 5.5 | 7.5 | seconds=5.0 → 27.5 | $0.6875 |

#### `youtube_faceless_video` — Youtube Faceless Video (video, credits_per_10_seconds)

| dimensions | component | unit | credits/unit | original | example | ≈USD plus:annual |
|---|---|---|---:|---:|---|---:|
| animation_mode=fully_animated |  | credits_per_10_seconds | 41 |  | seconds=60.0 → 246 | $6.1500 |
| animation_mode=scene_based |  | credits_per_10_seconds | 16 |  | seconds=60.0 → 96 | $2.4000 |

**In plans but not in `/job-sets/costs`** (priced in JS or covered by unlimited): `flux_2`, `kling_omni_image`, `nano_banana`, `nano_banana_2`, `openai_hazel_mini`, `seedream_v4_5`, `seedream_v5_lite`, `soul_cinematic`, `text2image_soul_v2`

<!-- END cost-tables -->

## 11. Generated appendix: option variations per model

<!-- BEGIN cost-variations -->
_Generated by `scripts/gen_cost_tables.py --variations` from `/job-sets/costs`. USD = credits × $0.0250 (plus:annual) and × $0.0150 (ultra:annual, 3,000-credit tier), after-offer rates. `ceil₀.₀₁` = round up to 0.01 credit (JS `Es()`). Aspect ratio never changes the price. Unlimited/free-gen runs cost 0 and are not shown._

#### Seedance 2.5 / Flash

**`seedance_2_5`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | on/off (same price) | no | 1 | generate | `ceil(4 × 3) = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 5 s | any | – | on/off (same price) | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | on/off (same price) | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | on/off (same price) | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 30 s | any | – | on/off (same price) | no | 1 | generate | `ceil(30 × 3) = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 4 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(4 × 3) = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 5 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 30 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(30 × 3) = 90` | 90 | $2.2500 | $1.3500 |
| 720p | 4 s | any | – | on/off (same price) | no | 1 | generate | `ceil(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 5 s | any | – | on/off (same price) | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | on/off (same price) | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | on/off (same price) | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 30 s | any | – | on/off (same price) | no | 1 | generate | `ceil(30 × 7) = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 4 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 5 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 30 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(30 × 7) = 210` | 210 | $5.2500 | $3.1500 |
| 1080p | 4 s | any | – | on/off (same price) | no | 1 | generate | `ceil(4 × 16) = 64` | 64 | $1.6000 | $0.9600 |
| 1080p | 5 s | any | – | on/off (same price) | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | on/off (same price) | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | on/off (same price) | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 30 s | any | – | on/off (same price) | no | 1 | generate | `ceil(30 × 16) = 480` | 480 | $12.0000 | $7.2000 |
| 1080p | 4 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(4 × 16) = 64` | 64 | $1.6000 | $0.9600 |
| 1080p | 5 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 30 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(30 × 16) = 480` | 480 | $12.0000 | $7.2000 |
| 4k | 4 s | any | – | on/off (same price) | no | 1 | generate | `ceil(4 × 28) = 112` | 112 | $2.8000 | $1.6800 |
| 4k | 5 s | any | – | on/off (same price) | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | on/off (same price) | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | on/off (same price) | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 30 s | any | – | on/off (same price) | no | 1 | generate | `ceil(30 × 28) = 840` | 840 | $21.0000 | $12.6000 |
| 4k | 4 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(4 × 34) = 136` | 136 | $3.4000 | $2.0400 |
| 4k | 5 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |
| 4k | 30 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(30 × 34) = 1020` | 1020 | $25.5000 | $15.3000 |
| 480p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 3) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 720p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 7) × 4 = 280` | 280 | $7.0000 | $4.2000 |
| 1080p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 16) × 4 = 640` | 640 | $16.0000 | $9.6000 |
| 4k | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 28) × 4 = 1120` | 1120 | $28.0000 | $16.8000 |
| 480p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 3.5) = 42` | 42 | $1.0500 | $0.6300 |
| 720p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 7.5) = 90` | 90 | $2.2500 | $1.3500 |
| 1080p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 20) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 34) = 408` | 408 | $10.2000 | $6.1200 |
| 480p | 10 s added | any | – | – | yes (source) | 1 | extend forward | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 10 s added | any | – | – | yes (source) | 1 | extend forward | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 480p (forced) | 5 s | any | – | – | no | 1 | draft | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p (forced) | 10 s | any | – | – | no | 1 | draft | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p (forced) | 15 s | any | – | – | no | 1 | draft | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |

**`seedance_2_5_flash`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | on/off (same price) | no | 1 | generate | `ceil(4 × 2) = 8` | 8 | $0.2000 | $0.1200 |
| 480p | 5 s | any | – | on/off (same price) | no | 1 | generate | `ceil(5 × 2) = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 10 s | any | – | on/off (same price) | no | 1 | generate | `ceil(10 × 2) = 20` | 20 | $0.5000 | $0.3000 |
| 480p | 15 s | any | – | on/off (same price) | no | 1 | generate | `ceil(15 × 2) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | on/off (same price) | no | 1 | generate | `ceil(30 × 2) = 60` | 60 | $1.5000 | $0.9000 |
| 480p | 4 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(4 × 2.5) = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 5 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(5 × 2.5) = 13` | 13 | $0.3250 | $0.1950 |
| 480p | 10 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(10 × 2.5) = 25` | 25 | $0.6250 | $0.3750 |
| 480p | 15 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(15 × 2.5) = 38` | 38 | $0.9500 | $0.5700 |
| 480p | 30 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(30 × 2.5) = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 4 s | any | – | on/off (same price) | no | 1 | generate | `ceil(4 × 5) = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 5 s | any | – | on/off (same price) | no | 1 | generate | `ceil(5 × 5) = 25` | 25 | $0.6250 | $0.3750 |
| 720p | 10 s | any | – | on/off (same price) | no | 1 | generate | `ceil(10 × 5) = 50` | 50 | $1.2500 | $0.7500 |
| 720p | 15 s | any | – | on/off (same price) | no | 1 | generate | `ceil(15 × 5) = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 30 s | any | – | on/off (same price) | no | 1 | generate | `ceil(30 × 5) = 150` | 150 | $3.7500 | $2.2500 |
| 720p | 4 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(4 × 6) = 24` | 24 | $0.6000 | $0.3600 |
| 720p | 5 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(5 × 6) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 10 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(10 × 6) = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 15 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(15 × 6) = 90` | 90 | $2.2500 | $1.3500 |
| 720p | 30 s | any | – | on/off (same price) | yes | 1 | generate | `ceil(30 × 6) = 180` | 180 | $4.5000 | $2.7000 |
| 480p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 2) × 4 = 80` | 80 | $2.0000 | $1.2000 |
| 720p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 5) × 4 = 200` | 200 | $5.0000 | $3.0000 |
| 480p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 2.5) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 6) = 72` | 72 | $1.8000 | $1.0800 |
| 480p | 10 s added | any | – | – | yes (source) | 1 | extend forward | `ceil(10 × 2.5) = 25` | 25 | $0.6250 | $0.3750 |
| 720p | 10 s added | any | – | – | yes (source) | 1 | extend forward | `ceil(10 × 6) = 60` | 60 | $1.5000 | $0.9000 |

**`seedance_2_5_kling_upscale`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 4) = 20` | 20 | $0.5000 | $0.3000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 4) = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 4) = 60` | 60 | $1.5000 | $0.9000 |

#### Seedance 2.0

**`seedance_2_0`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(4 × 3) = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 10 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 15 s | any | seedance_2_0 | – | no | 4 | generate | `ceil(15 × 3) × 4 = 180` | 180 | $4.5000 | $2.7000 |
| 720p | 4 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(4 × 4.5) = 18` | 18 | $0.4500 | $0.2700 |
| 720p | 10 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(10 × 4.5) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 15 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(15 × 4.5) = 68` | 68 | $1.7000 | $1.0200 |
| 720p | 15 s | any | seedance_2_0 | – | no | 4 | generate | `ceil(15 × 4.5) × 4 = 272` | 272 | $6.8000 | $4.0800 |
| 1080p | 4 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(4 × 12) = 48` | 48 | $1.2000 | $0.7200 |
| 1080p | 10 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(10 × 12) = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 15 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(15 × 12) = 180` | 180 | $4.5000 | $2.7000 |
| 1080p | 15 s | any | seedance_2_0 | – | no | 4 | generate | `ceil(15 × 12) × 4 = 720` | 720 | $18.0000 | $10.8000 |
| 4k | 4 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(4 × 22) = 88` | 88 | $2.2000 | $1.3200 |
| 4k | 10 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(10 × 22) = 220` | 220 | $5.5000 | $3.3000 |
| 4k | 15 s | any | seedance_2_0 | – | no | 1 | generate | `ceil(15 × 22) = 330` | 330 | $8.2500 | $4.9500 |
| 4k | 15 s | any | seedance_2_0 | – | no | 4 | generate | `ceil(15 × 22) × 4 = 1320` | 1320 | $33.0000 | $19.8000 |
| 480p | 4 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(4 × 1) = 4` | 4 | $0.1000 | $0.0600 |
| 480p | 10 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(10 × 1) = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 15 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(15 × 1) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 15 s | any | seedance_2_0_fast | – | no | 4 | generate | `ceil(15 × 1) × 4 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 4 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(4 × 2.5) = 10` | 10 | $0.2500 | $0.1500 |
| 720p | 10 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(10 × 2.5) = 25` | 25 | $0.6250 | $0.3750 |
| 720p | 15 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(15 × 2.5) = 38` | 38 | $0.9500 | $0.5700 |
| 720p | 15 s | any | seedance_2_0_fast | – | no | 4 | generate | `ceil(15 × 2.5) × 4 = 152` | 152 | $3.8000 | $2.2800 |
| 1080p | 4 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 1080p | 10 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 1080p | 15 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 15 s | any | seedance_2_0_fast | – | no | 4 | generate | `ceil(15 × 7) × 4 = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 4 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(4 × 14) = 56` | 56 | $1.4000 | $0.8400 |
| 4k | 10 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(10 × 14) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 15 s | any | seedance_2_0_fast | – | no | 1 | generate | `ceil(15 × 14) = 210` | 210 | $5.2500 | $3.1500 |
| 4k | 15 s | any | seedance_2_0_fast | – | no | 4 | generate | `ceil(15 × 14) × 4 = 840` | 840 | $21.0000 | $12.6000 |

**`seedance_2_0_mini`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 0.5) = 2` | 2 | $0.0500 | $0.0300 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 0.5) = 5` | 5 | $0.1250 | $0.0750 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 0.5) = 8` | 8 | $0.2000 | $0.1200 |
| 480p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 0.5) × 4 = 32` | 32 | $0.8000 | $0.4800 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 1) = 4` | 4 | $0.1000 | $0.0600 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 1) = 10` | 10 | $0.2500 | $0.1500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 1) = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 1) × 4 = 60` | 60 | $1.5000 | $0.9000 |

#### Cinema Studio / Videoshop

**`cinematic_studio_video_4_0`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 3) = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 3) = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 4 s | any | – | – | yes | 1 | generate | `ceil(4 × 3) = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 30 s | any | – | – | yes | 1 | generate | `ceil(30 × 3) = 90` | 90 | $2.2500 | $1.3500 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 7) = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 4 s | any | – | – | yes | 1 | generate | `ceil(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 30 s | any | – | – | yes | 1 | generate | `ceil(30 × 7) = 210` | 210 | $5.2500 | $3.1500 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 16) = 64` | 64 | $1.6000 | $0.9600 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 16) = 480` | 480 | $12.0000 | $7.2000 |
| 1080p | 4 s | any | – | – | yes | 1 | generate | `ceil(4 × 16) = 64` | 64 | $1.6000 | $0.9600 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 30 s | any | – | – | yes | 1 | generate | `ceil(30 × 16) = 480` | 480 | $12.0000 | $7.2000 |
| 4k | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 28) = 112` | 112 | $2.8000 | $1.6800 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 28) = 840` | 840 | $21.0000 | $12.6000 |
| 4k | 4 s | any | – | – | yes | 1 | generate | `ceil(4 × 34) = 136` | 136 | $3.4000 | $2.0400 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |
| 4k | 30 s | any | – | – | yes | 1 | generate | `ceil(30 × 34) = 1020` | 1020 | $25.5000 | $15.3000 |
| 480p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 3) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 720p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 7) × 4 = 280` | 280 | $7.0000 | $4.2000 |
| 1080p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 16) × 4 = 640` | 640 | $16.0000 | $9.6000 |
| 4k | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 28) × 4 = 1120` | 1120 | $28.0000 | $16.8000 |
| 480p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 3) = 36` | 36 | $0.9000 | $0.5400 |
| 720p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 7) = 84` | 84 | $2.1000 | $1.2600 |
| 1080p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 16) = 192` | 192 | $4.8000 | $2.8800 |
| 4k | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 34) = 408` | 408 | $10.2000 | $6.1200 |

**`cinematic_studio_3_0`** — formula: JS: plain_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `4 × 3.5 = 14` | 14 | $0.3500 | $0.2100 |
| 480p | 10 s | any | – | – | no | 1 | generate | `10 × 3.5 = 35` | 35 | $0.8750 | $0.5250 |
| 480p | 15 s | any | – | – | no | 1 | generate | `15 × 3.5 = 52.5` | 52.5 | $1.3125 | $0.7875 |
| 480p | 15 s | any | – | – | no | 4 | generate | `15 × 3.5 × 4 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 4 s | any | – | – | no | 1 | generate | `4 × 5 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 5 = 50` | 50 | $1.2500 | $0.7500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 5 = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 15 s | any | – | – | no | 4 | generate | `15 × 5 × 4 = 300` | 300 | $7.5000 | $4.5000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `4 × 13 = 52` | 52 | $1.3000 | $0.7800 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `10 × 13 = 130` | 130 | $3.2500 | $1.9500 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 13 = 195` | 195 | $4.8750 | $2.9250 |
| 1080p | 15 s | any | – | – | no | 4 | generate | `15 × 13 × 4 = 780` | 780 | $19.5000 | $11.7000 |
| 4k | 4 s | any | – | – | no | 1 | generate | `4 × 24 = 96` | 96 | $2.4000 | $1.4400 |
| 4k | 10 s | any | – | – | no | 1 | generate | `10 × 24 = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `15 × 24 = 360` | 360 | $9.0000 | $5.4000 |
| 4k | 15 s | any | – | – | no | 4 | generate | `15 × 24 × 4 = 1440` | 1440 | $36.0000 | $21.6000 |

**`cinematic_studio_video_3_5`** — formula: JS: plain_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `4 × 3.5 = 14` | 14 | $0.3500 | $0.2100 |
| 480p | 10 s | any | – | – | no | 1 | generate | `10 × 3.5 = 35` | 35 | $0.8750 | $0.5250 |
| 480p | 15 s | any | – | – | no | 1 | generate | `15 × 3.5 = 52.5` | 52.5 | $1.3125 | $0.7875 |
| 480p | 15 s | any | – | – | no | 4 | generate | `15 × 3.5 × 4 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 4 s | any | – | – | no | 1 | generate | `4 × 5 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 5 = 50` | 50 | $1.2500 | $0.7500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 5 = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 15 s | any | – | – | no | 4 | generate | `15 × 5 × 4 = 300` | 300 | $7.5000 | $4.5000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `4 × 13 = 52` | 52 | $1.3000 | $0.7800 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `10 × 13 = 130` | 130 | $3.2500 | $1.9500 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 13 = 195` | 195 | $4.8750 | $2.9250 |
| 1080p | 15 s | any | – | – | no | 4 | generate | `15 × 13 × 4 = 780` | 780 | $19.5000 | $11.7000 |
| 4k | 4 s | any | – | – | no | 1 | generate | `4 × 24 = 96` | 96 | $2.4000 | $1.4400 |
| 4k | 10 s | any | – | – | no | 1 | generate | `10 × 24 = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `15 × 24 = 360` | 360 | $9.0000 | $5.4000 |
| 4k | 15 s | any | – | – | no | 4 | generate | `15 × 24 × 4 = 1440` | 1440 | $36.0000 | $21.6000 |

**`cinematic_video_editor`** — formula: inferred: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 480p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 3.5) = 42` | 42 | $1.0500 | $0.6300 |
| 720p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 7.5) = 90` | 90 | $2.2500 | $1.3500 |
| 1080p | 12 s source | any | – | – | yes (source) | 1 | edit | `ceil(12 × 20) = 240` | 240 | $6.0000 | $3.6000 |

**`cinematic_video_relight`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 20) = 100` | 100 | $2.5000 | $1.5000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 20) = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 20) = 300` | 300 | $7.5000 | $4.5000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 20) = 100` | 100 | $2.5000 | $1.5000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 20) = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 20) = 300` | 300 | $7.5000 | $4.5000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`cinematic_video_inpaint`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 20) = 100` | 100 | $2.5000 | $1.5000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 20) = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 20) = 300` | 300 | $7.5000 | $4.5000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 20) = 100` | 100 | $2.5000 | $1.5000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 20) = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 20) = 300` | 300 | $7.5000 | $4.5000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`videoshop_edit`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3.5) = 18` | 18 | $0.4500 | $0.2700 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3.5) = 35` | 35 | $0.8750 | $0.5250 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3.5) = 53` | 53 | $1.3250 | $0.7950 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3.5) = 18` | 18 | $0.4500 | $0.2700 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3.5) = 35` | 35 | $0.8750 | $0.5250 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3.5) = 53` | 53 | $1.3250 | $0.7950 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7.5) = 38` | 38 | $0.9500 | $0.5700 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7.5) = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7.5) = 113` | 113 | $2.8250 | $1.6950 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7.5) = 38` | 38 | $0.9500 | $0.5700 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7.5) = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7.5) = 113` | 113 | $2.8250 | $1.6950 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 20) = 100` | 100 | $2.5000 | $1.5000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 20) = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 20) = 300` | 300 | $7.5000 | $4.5000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 20) = 100` | 100 | $2.5000 | $1.5000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 20) = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 20) = 300` | 300 | $7.5000 | $4.5000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`videoshop_relight`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |
| – | – | any | – | – | no | 1 | image relight | `image_credits = 3.5` | 3.5 | $0.0875 | $0.0525 |

**`videoshop_camera_move`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`videoshop_genjutsu`** — formula: inferred: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 3 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 3 = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 3 × 4 = 360` | 360 | $9.0000 | $5.4000 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 7 = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 7 = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 7 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 7 × 4 = 840` | 840 | $21.0000 | $12.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 20 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 20 = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 20 = 600` | 600 | $15.0000 | $9.0000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 20 × 4 = 2400` | 2400 | $60.0000 | $36.0000 |

#### Kling

**`kling4_0`** — formula: JS: plain

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 3 s | any | SDR | – | no | 1 | generate | `3 × 2.5 = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 720p | 5 s | any | SDR | – | no | 1 | generate | `5 × 2.5 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| 720p | 10 s | any | SDR | – | no | 1 | generate | `10 × 2.5 = 25` | 25 | $0.6250 | $0.3750 |
| 720p | 15 s | any | SDR | – | no | 1 | generate | `15 × 2.5 = 37.5` | 37.5 | $0.9375 | $0.5625 |
| 720p | 3 s | any | SDR | – | yes | 1 | generate | `3 × 3 = 9` | 9 | $0.2250 | $0.1350 |
| 720p | 5 s | any | SDR | – | yes | 1 | generate | `5 × 3 = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 10 s | any | SDR | – | yes | 1 | generate | `10 × 3 = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 15 s | any | SDR | – | yes | 1 | generate | `15 × 3 = 45` | 45 | $1.1250 | $0.6750 |
| 1080p | 3 s | any | SDR | – | no | 1 | generate | `3 × 3.75 = 11.25` | 11.25 | $0.2812 | $0.1688 |
| 1080p | 5 s | any | SDR | – | no | 1 | generate | `5 × 3.75 = 18.75` | 18.75 | $0.4688 | $0.2812 |
| 1080p | 10 s | any | SDR | – | no | 1 | generate | `10 × 3.75 = 37.5` | 37.5 | $0.9375 | $0.5625 |
| 1080p | 15 s | any | SDR | – | no | 1 | generate | `15 × 3.75 = 56.25` | 56.25 | $1.4062 | $0.8438 |
| 1080p | 10 s | any | HDR | – | no | 1 | generate | `10 × 4.5 = 45` | 45 | $1.1250 | $0.6750 |
| 1080p | 3 s | any | SDR | – | yes | 1 | generate | `3 × 4.5 = 13.5` | 13.5 | $0.3375 | $0.2025 |
| 1080p | 5 s | any | SDR | – | yes | 1 | generate | `5 × 4.5 = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 1080p | 10 s | any | SDR | – | yes | 1 | generate | `10 × 4.5 = 45` | 45 | $1.1250 | $0.6750 |
| 1080p | 15 s | any | SDR | – | yes | 1 | generate | `15 × 4.5 = 67.5` | 67.5 | $1.6875 | $1.0125 |
| 1080p | 10 s | any | HDR | – | yes | 1 | generate | `10 × 5.25 = 52.5` | 52.5 | $1.3125 | $0.7875 |
| 4k | 3 s | any | SDR | – | no | 1 | generate | `3 × 9 = 27` | 27 | $0.6750 | $0.4050 |
| 4k | 5 s | any | SDR | – | no | 1 | generate | `5 × 9 = 45` | 45 | $1.1250 | $0.6750 |
| 4k | 10 s | any | SDR | – | no | 1 | generate | `10 × 9 = 90` | 90 | $2.2500 | $1.3500 |
| 4k | 15 s | any | SDR | – | no | 1 | generate | `15 × 9 = 135` | 135 | $3.3750 | $2.0250 |
| 4k | 10 s | any | HDR | – | no | 1 | generate | `10 × 10 = 100` | 100 | $2.5000 | $1.5000 |
| 4k | 3 s | any | SDR | – | yes | 1 | generate | `3 × 10.5 = 31.5` | 31.5 | $0.7875 | $0.4725 |
| 4k | 5 s | any | SDR | – | yes | 1 | generate | `5 × 10.5 = 52.5` | 52.5 | $1.3125 | $0.7875 |
| 4k | 10 s | any | SDR | – | yes | 1 | generate | `10 × 10.5 = 105` | 105 | $2.6250 | $1.5750 |
| 4k | 15 s | any | SDR | – | yes | 1 | generate | `15 × 10.5 = 157.5` | 157.5 | $3.9375 | $2.3625 |
| 4k | 10 s | any | HDR | – | yes | 1 | generate | `10 × 12 = 120` | 120 | $3.0000 | $1.8000 |

**`kling_4_0_flash`** — formula: JS: plain

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 3 s | any | – | – | no | 1 | generate | `3 × 1.5 = 4.5` | 4.5 | $0.1125 | $0.0675 |
| 720p | 5 s | any | – | – | no | 1 | generate | `5 × 1.5 = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 1.5 = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 1.5 = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 720p | 3 s | any | – | – | yes | 1 | generate | `3 × 2 = 6` | 6 | $0.1500 | $0.0900 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `5 × 2 = 10` | 10 | $0.2500 | $0.1500 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `10 × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `15 × 2 = 30` | 30 | $0.7500 | $0.4500 |

**`kling3_0`** — formula: JS: d × rate[mode][sound]

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 3 s | any | mode=pro | on | no | 1 | generate | `3 × 2.5 = 7.5` | 7.5 | $0.1875 | $0.1125 |
| – | 5 s | any | mode=pro | on | no | 1 | generate | `5 × 2.5 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| – | 10 s | any | mode=pro | on | no | 1 | generate | `10 × 2.5 = 25` | 25 | $0.6250 | $0.3750 |
| – | 15 s | any | mode=pro | on | no | 1 | generate | `15 × 2.5 = 37.5` | 37.5 | $0.9375 | $0.5625 |
| – | 3 s | any | mode=pro | off | no | 1 | generate | `3 × 1.75 = 5.25` | 5.25 | $0.1312 | $0.0788 |
| – | 5 s | any | mode=pro | off | no | 1 | generate | `5 × 1.75 = 8.75` | 8.75 | $0.2188 | $0.1312 |
| – | 10 s | any | mode=pro | off | no | 1 | generate | `10 × 1.75 = 17.5` | 17.5 | $0.4375 | $0.2625 |
| – | 15 s | any | mode=pro | off | no | 1 | generate | `15 × 1.75 = 26.25` | 26.25 | $0.6562 | $0.3938 |
| – | 3 s | any | mode=std | on | no | 1 | generate | `3 × 2 = 6` | 6 | $0.1500 | $0.0900 |
| – | 5 s | any | mode=std | on | no | 1 | generate | `5 × 2 = 10` | 10 | $0.2500 | $0.1500 |
| – | 10 s | any | mode=std | on | no | 1 | generate | `10 × 2 = 20` | 20 | $0.5000 | $0.3000 |
| – | 15 s | any | mode=std | on | no | 1 | generate | `15 × 2 = 30` | 30 | $0.7500 | $0.4500 |
| – | 3 s | any | mode=std | off | no | 1 | generate | `3 × 1.5 = 4.5` | 4.5 | $0.1125 | $0.0675 |
| – | 5 s | any | mode=std | off | no | 1 | generate | `5 × 1.5 = 7.5` | 7.5 | $0.1875 | $0.1125 |
| – | 10 s | any | mode=std | off | no | 1 | generate | `10 × 1.5 = 15` | 15 | $0.3750 | $0.2250 |
| – | 15 s | any | mode=std | off | no | 1 | generate | `15 × 1.5 = 22.5` | 22.5 | $0.5625 | $0.3375 |
| – | 3 s | any | mode=4k | on | no | 1 | generate | `3 × 6 = 18` | 18 | $0.4500 | $0.2700 |
| – | 5 s | any | mode=4k | on | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| – | 10 s | any | mode=4k | on | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| – | 15 s | any | mode=4k | on | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |
| – | 3 s | any | mode=4k | off | no | 1 | generate | `3 × 6 = 18` | 18 | $0.4500 | $0.2700 |
| – | 5 s | any | mode=4k | off | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| – | 10 s | any | mode=4k | off | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| – | 15 s | any | mode=4k | off | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |

**`kling3_0_turbo`** — formula: JS: plain

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 3 s | any | – | – | no | 1 | generate | `3 × 1.5 = 4.5` | 4.5 | $0.1125 | $0.0675 |
| 720p | 5 s | any | – | – | no | 1 | generate | `5 × 1.5 = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 1.5 = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 1.5 = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 1080p | 3 s | any | – | – | no | 1 | generate | `3 × 2 = 6` | 6 | $0.1500 | $0.0900 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `5 × 2 = 10` | 10 | $0.2500 | $0.1500 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `10 × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 2 = 30` | 30 | $0.7500 | $0.4500 |

**`kling_o3_image_reference`** — formula: JS: d × rate[mode][sound]

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 3 s | any | mode=pro | on | no | 1 | generate | `3 × 2 = 6` | 6 | $0.1500 | $0.0900 |
| – | 5 s | any | mode=pro | on | no | 1 | generate | `5 × 2 = 10` | 10 | $0.2500 | $0.1500 |
| – | 10 s | any | mode=pro | on | no | 1 | generate | `10 × 2 = 20` | 20 | $0.5000 | $0.3000 |
| – | 15 s | any | mode=pro | on | no | 1 | generate | `15 × 2 = 30` | 30 | $0.7500 | $0.4500 |
| – | 3 s | any | mode=pro | off | no | 1 | generate | `3 × 1.5 = 4.5` | 4.5 | $0.1125 | $0.0675 |
| – | 5 s | any | mode=pro | off | no | 1 | generate | `5 × 1.5 = 7.5` | 7.5 | $0.1875 | $0.1125 |
| – | 10 s | any | mode=pro | off | no | 1 | generate | `10 × 1.5 = 15` | 15 | $0.3750 | $0.2250 |
| – | 15 s | any | mode=pro | off | no | 1 | generate | `15 × 1.5 = 22.5` | 22.5 | $0.5625 | $0.3375 |
| – | 3 s | any | mode=std | on | no | 1 | generate | `3 × 1.25 = 3.75` | 3.75 | $0.0938 | $0.0562 |
| – | 5 s | any | mode=std | on | no | 1 | generate | `5 × 1.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| – | 10 s | any | mode=std | on | no | 1 | generate | `10 × 1.25 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| – | 15 s | any | mode=std | on | no | 1 | generate | `15 × 1.25 = 18.75` | 18.75 | $0.4688 | $0.2812 |
| – | 3 s | any | mode=std | off | no | 1 | generate | `3 × 1 = 3` | 3 | $0.0750 | $0.0450 |
| – | 5 s | any | mode=std | off | no | 1 | generate | `5 × 1 = 5` | 5 | $0.1250 | $0.0750 |
| – | 10 s | any | mode=std | off | no | 1 | generate | `10 × 1 = 10` | 10 | $0.2500 | $0.1500 |
| – | 15 s | any | mode=std | off | no | 1 | generate | `15 × 1 = 15` | 15 | $0.3750 | $0.2250 |
| – | 3 s | any | mode=4k | on | no | 1 | generate | `3 × 6 = 18` | 18 | $0.4500 | $0.2700 |
| – | 5 s | any | mode=4k | on | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| – | 10 s | any | mode=4k | on | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| – | 15 s | any | mode=4k | on | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |
| – | 3 s | any | mode=4k | off | no | 1 | generate | `3 × 6 = 18` | 18 | $0.4500 | $0.2700 |
| – | 5 s | any | mode=4k | off | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| – | 10 s | any | mode=4k | off | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| – | 15 s | any | mode=4k | off | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |

**`kling_o3_flf`** — formula: JS: d × rate[mode][sound]

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 3 s | any | mode=pro | on | no | 1 | generate | `3 × 1.8 = 5.4` | 5.4 | $0.1350 | $0.0810 |
| – | 5 s | any | mode=pro | on | no | 1 | generate | `5 × 1.8 = 9` | 9 | $0.2250 | $0.1350 |
| – | 10 s | any | mode=pro | on | no | 1 | generate | `10 × 1.8 = 18` | 18 | $0.4500 | $0.2700 |
| – | 15 s | any | mode=pro | on | no | 1 | generate | `15 × 1.8 = 27` | 27 | $0.6750 | $0.4050 |
| – | 3 s | any | mode=pro | off | no | 1 | generate | `3 × 1.25 = 3.75` | 3.75 | $0.0938 | $0.0562 |
| – | 5 s | any | mode=pro | off | no | 1 | generate | `5 × 1.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| – | 10 s | any | mode=pro | off | no | 1 | generate | `10 × 1.25 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| – | 15 s | any | mode=pro | off | no | 1 | generate | `15 × 1.25 = 18.75` | 18.75 | $0.4688 | $0.2812 |
| – | 3 s | any | mode=std | on | no | 1 | generate | `3 × 1.25 = 3.75` | 3.75 | $0.0938 | $0.0562 |
| – | 5 s | any | mode=std | on | no | 1 | generate | `5 × 1.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| – | 10 s | any | mode=std | on | no | 1 | generate | `10 × 1.25 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| – | 15 s | any | mode=std | on | no | 1 | generate | `15 × 1.25 = 18.75` | 18.75 | $0.4688 | $0.2812 |
| – | 3 s | any | mode=std | off | no | 1 | generate | `3 × 1 = 3` | 3 | $0.0750 | $0.0450 |
| – | 5 s | any | mode=std | off | no | 1 | generate | `5 × 1 = 5` | 5 | $0.1250 | $0.0750 |
| – | 10 s | any | mode=std | off | no | 1 | generate | `10 × 1 = 10` | 10 | $0.2500 | $0.1500 |
| – | 15 s | any | mode=std | off | no | 1 | generate | `15 × 1 = 15` | 15 | $0.3750 | $0.2250 |
| – | 3 s | any | mode=4k | on | no | 1 | generate | `3 × 6 = 18` | 18 | $0.4500 | $0.2700 |
| – | 5 s | any | mode=4k | on | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| – | 10 s | any | mode=4k | on | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| – | 15 s | any | mode=4k | on | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |
| – | 3 s | any | mode=4k | off | no | 1 | generate | `3 × 6 = 18` | 18 | $0.4500 | $0.2700 |
| – | 5 s | any | mode=4k | off | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| – | 10 s | any | mode=4k | off | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| – | 15 s | any | mode=4k | off | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |

**`kling3_0_motion_control`** — formula: JS: ceil(rate × d [+2 chain])

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 3 s (driving video) | any | mode=std | – | yes | 1 | generate | `ceil(1.5 × 3) = 5` | 5 | $0.1250 | $0.0750 |
| – | 5.5 s (driving video) | any | mode=std | – | yes | 1 | generate | `ceil(1.5 × 5.5) = 9` | 9 | $0.2250 | $0.1350 |
| – | 10 s (driving video) | any | mode=std | – | yes | 1 | generate | `ceil(1.5 × 10) = 15` | 15 | $0.3750 | $0.2250 |
| – | 30 s (driving video) | any | mode=std | – | yes | 1 | generate | `ceil(1.5 × 30) = 45` | 45 | $1.1250 | $0.6750 |
| – | 10 s (driving video) | any | mode=std | – | yes | 1 | chain | `ceil(1.5 × 10 + 2) = 17` | 17 | $0.4250 | $0.2550 |
| – | 3 s (driving video) | any | mode=pro | – | yes | 1 | generate | `ceil(2.5 × 3) = 8` | 8 | $0.2000 | $0.1200 |
| – | 5.5 s (driving video) | any | mode=pro | – | yes | 1 | generate | `ceil(2.5 × 5.5) = 14` | 14 | $0.3500 | $0.2100 |
| – | 10 s (driving video) | any | mode=pro | – | yes | 1 | generate | `ceil(2.5 × 10) = 25` | 25 | $0.6250 | $0.3750 |
| – | 30 s (driving video) | any | mode=pro | – | yes | 1 | generate | `ceil(2.5 × 30) = 75` | 75 | $1.8750 | $1.1250 |
| – | 10 s (driving video) | any | mode=pro | – | yes | 1 | chain | `ceil(2.5 × 10 + 2) = 27` | 27 | $0.6750 | $0.4050 |

**`kling_image_4_0`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 2k | – | any | – | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | – | – | no | 1 | generate | `1 × 3 = 3` | 3 | $0.0750 | $0.0450 |
| 4k | – | any | – | – | no | 4 | generate | `4 × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 8k | – | any | – | – | no | 1 | generate | `1 × 5 = 5` | 5 | $0.1250 | $0.0750 |
| 8k | – | any | – | – | no | 4 | generate | `4 × 5 = 20` | 20 | $0.5000 | $0.3000 |

#### Wan

**`wan3_0`** — formula: JS: cent

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 2 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(2 × 0.75) = 1.5` | 1.5 | $0.0375 | $0.0225 |
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(5 × 0.75) = 3.75` | 3.75 | $0.0938 | $0.0562 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(10 × 0.75) = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(15 × 0.75) = 11.25` | 11.25 | $0.2812 | $0.1688 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(30 × 0.75) = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 480p | 2 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(2 × 1.5) = 3` | 3 | $0.0750 | $0.0450 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(5 × 1.5) = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(10 × 1.5) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(15 × 1.5) = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 480p | 30 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(30 × 1.5) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 2 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(2 × 1.5) = 3` | 3 | $0.0750 | $0.0450 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(5 × 1.5) = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(10 × 1.5) = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(15 × 1.5) = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(30 × 1.5) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 2 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(2 × 3) = 6` | 6 | $0.1500 | $0.0900 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 30 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(30 × 3) = 90` | 90 | $2.2500 | $1.3500 |
| 1080p | 2 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(2 × 3) = 6` | 6 | $0.1500 | $0.0900 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(30 × 3) = 90` | 90 | $2.2500 | $1.3500 |
| 1080p | 2 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(2 × 6) = 12` | 12 | $0.3000 | $0.1800 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(5 × 6) = 30` | 30 | $0.7500 | $0.4500 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(10 × 6) = 60` | 60 | $1.5000 | $0.9000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(15 × 6) = 90` | 90 | $2.2500 | $1.3500 |
| 1080p | 30 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(30 × 6) = 180` | 180 | $4.5000 | $2.7000 |

**`wan3_0_prime`** — formula: JS: cent

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 2 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(2 × 1.25) = 2.5` | 2.5 | $0.0625 | $0.0375 |
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(5 × 1.25) = 6.25` | 6.25 | $0.1562 | $0.0938 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(10 × 1.25) = 12.5` | 12.5 | $0.3125 | $0.1875 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(15 × 1.25) = 18.75` | 18.75 | $0.4688 | $0.2812 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(30 × 1.25) = 37.5` | 37.5 | $0.9375 | $0.5625 |
| 480p | 2 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(2 × 2.5) = 5` | 5 | $0.1250 | $0.0750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(5 × 2.5) = 12.5` | 12.5 | $0.3125 | $0.1875 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(10 × 2.5) = 25` | 25 | $0.6250 | $0.3750 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(15 × 2.5) = 37.5` | 37.5 | $0.9375 | $0.5625 |
| 480p | 30 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(30 × 2.5) = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 2 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(2 × 2.75) = 5.5` | 5.5 | $0.1375 | $0.0825 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(5 × 2.75) = 13.75` | 13.75 | $0.3438 | $0.2062 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(10 × 2.75) = 27.5` | 27.5 | $0.6875 | $0.4125 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(15 × 2.75) = 41.25` | 41.25 | $1.0312 | $0.6188 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(30 × 2.75) = 82.5` | 82.5 | $2.0625 | $1.2375 |
| 720p | 2 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(2 × 5.5) = 11` | 11 | $0.2750 | $0.1650 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(5 × 5.5) = 27.5` | 27.5 | $0.6875 | $0.4125 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(10 × 5.5) = 55` | 55 | $1.3750 | $0.8250 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(15 × 5.5) = 82.5` | 82.5 | $2.0625 | $1.2375 |
| 720p | 30 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(30 × 5.5) = 165` | 165 | $4.1250 | $2.4750 |
| 1080p | 2 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(2 × 5.5) = 11` | 11 | $0.2750 | $0.1650 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(5 × 5.5) = 27.5` | 27.5 | $0.6875 | $0.4125 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(10 × 5.5) = 55` | 55 | $1.3750 | $0.8250 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(15 × 5.5) = 82.5` | 82.5 | $2.0625 | $1.2375 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil₀.₀₁(30 × 5.5) = 165` | 165 | $4.1250 | $2.4750 |
| 1080p | 2 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(2 × 11) = 22` | 22 | $0.5500 | $0.3300 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(5 × 11) = 55` | 55 | $1.3750 | $0.8250 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(10 × 11) = 110` | 110 | $2.7500 | $1.6500 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(15 × 11) = 165` | 165 | $4.1250 | $2.4750 |
| 1080p | 30 s | any | – | – | yes | 1 | generate | `ceil₀.₀₁(30 × 11) = 330` | 330 | $8.2500 | $4.9500 |

#### MiniMax / Hailuo

**`minimax_h3_highspeed`** — formula: JS: plain_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `5 × 1.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| 480p | 10 s | any | – | – | no | 1 | generate | `10 × 1.25 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| 480p | 15 s | any | – | – | no | 1 | generate | `15 × 1.25 = 18.75` | 18.75 | $0.4688 | $0.2812 |
| 480p | 15 s | any | – | – | no | 4 | generate | `15 × 1.25 × 4 = 75` | 75 | $1.8750 | $1.1250 |
| 768p | 5 s | any | – | – | no | 1 | generate | `5 × 2 = 10` | 10 | $0.2500 | $0.1500 |
| 768p | 10 s | any | – | – | no | 1 | generate | `10 × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 768p | 15 s | any | – | – | no | 1 | generate | `15 × 2 = 30` | 30 | $0.7500 | $0.4500 |
| 768p | 15 s | any | – | – | no | 4 | generate | `15 × 2 × 4 = 120` | 120 | $3.0000 | $1.8000 |

**`minimax_h3_lite`** — formula: JS: plain_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `5 × 1 = 5` | 5 | $0.1250 | $0.0750 |
| 480p | 10 s | any | – | – | no | 1 | generate | `10 × 1 = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `15 × 1 = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 15 s | any | – | – | no | 4 | generate | `15 × 1 × 4 = 60` | 60 | $1.5000 | $0.9000 |
| 768p | 5 s | any | – | – | no | 1 | generate | `5 × 1.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| 768p | 10 s | any | – | – | no | 1 | generate | `10 × 1.25 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| 768p | 15 s | any | – | – | no | 1 | generate | `15 × 1.25 = 18.75` | 18.75 | $0.4688 | $0.2812 |
| 768p | 15 s | any | – | – | no | 4 | generate | `15 × 1.25 × 4 = 75` | 75 | $1.8750 | $1.1250 |

**`minimax_h3_image`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | – | – | no | 1 | generate | `1 × 3 = 3` | 3 | $0.0750 | $0.0450 |
| 1k | – | any | – | – | no | 4 | generate | `4 × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 2k | – | any | – | – | no | 1 | generate | `1 × 3 = 3` | 3 | $0.0750 | $0.0450 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 4k | – | any | – | – | no | 1 | generate | `1 × 4 = 4` | 4 | $0.1000 | $0.0600 |
| 4k | – | any | – | – | no | 4 | generate | `4 × 4 = 16` | 16 | $0.4000 | $0.2400 |

#### Gemini Omni / Grok / Happy Horse / Flux video

**`gemini_omni`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 3 s | any | – | – | no | 1 | generate | `ceil(3 × 3) = 9` | 9 | $0.2250 | $0.1350 |
| 720p | 8 s | any | – | – | no | 1 | generate | `ceil(8 × 3) = 24` | 24 | $0.6000 | $0.3600 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 3) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 3 s | any | – | – | no | 1 | generate | `ceil(3 × 3) = 9` | 9 | $0.2250 | $0.1350 |
| 1080p | 8 s | any | – | – | no | 1 | generate | `ceil(8 × 3) = 24` | 24 | $0.6000 | $0.3600 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 1080p | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 3) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 4k | 3 s | any | – | – | no | 1 | generate | `ceil(3 × 3) = 9` | 9 | $0.2250 | $0.1350 |
| 4k | 8 s | any | – | – | no | 1 | generate | `ceil(8 × 3) = 24` | 24 | $0.6000 | $0.3600 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 4k | 10 s | any | – | – | no | 4 | generate | `ceil(10 × 3) × 4 = 120` | 120 | $3.0000 | $1.8000 |

**`gemini_omni_flash_1_2`** — formula: JS: plain_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 360p | 3 s | any | – | – | no | 1 | generate | `3 × 0.75 = 2.25` | 2.25 | $0.0562 | $0.0338 |
| 360p | 8 s | any | – | – | no | 1 | generate | `8 × 0.75 = 6` | 6 | $0.1500 | $0.0900 |
| 360p | 15 s | any | – | – | no | 1 | generate | `15 × 0.75 = 11.25` | 11.25 | $0.2812 | $0.1688 |
| 360p | 15 s | any | – | – | no | 4 | generate | `15 × 0.75 × 4 = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 3 s | any | – | – | no | 1 | generate | `3 × 2.25 = 6.75` | 6.75 | $0.1688 | $0.1012 |
| 720p | 8 s | any | – | – | no | 1 | generate | `8 × 2.25 = 18` | 18 | $0.4500 | $0.2700 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 2.25 = 33.75` | 33.75 | $0.8438 | $0.5062 |
| 720p | 15 s | any | – | – | no | 4 | generate | `15 × 2.25 × 4 = 135` | 135 | $3.3750 | $2.0250 |
| 1080p | 3 s | any | – | – | no | 1 | generate | `3 × 3.25 = 9.75` | 9.75 | $0.2438 | $0.1462 |
| 1080p | 8 s | any | – | – | no | 1 | generate | `8 × 3.25 = 26` | 26 | $0.6500 | $0.3900 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 3.25 = 48.75` | 48.75 | $1.2188 | $0.7312 |
| 1080p | 15 s | any | – | – | no | 4 | generate | `15 × 3.25 × 4 = 195` | 195 | $4.8750 | $2.9250 |
| 4k | 3 s | any | – | – | no | 1 | generate | `3 × 6.75 = 20.25` | 20.25 | $0.5062 | $0.3038 |
| 4k | 8 s | any | – | – | no | 1 | generate | `8 × 6.75 = 54` | 54 | $1.3500 | $0.8100 |
| 4k | 15 s | any | – | – | no | 1 | generate | `15 × 6.75 = 101.25` | 101.25 | $2.5312 | $1.5188 |
| 4k | 15 s | any | – | – | no | 4 | generate | `15 × 6.75 × 4 = 405` | 405 | $10.1250 | $6.0750 |

**`grok_video_v15`** — formula: JS: plain

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 1 s | any | – | – | no | 1 | generate | `1 × 2.5 = 2.5` | 2.5 | $0.0625 | $0.0375 |
| 480p | 5 s | any | – | – | no | 1 | generate | `5 × 2.5 = 12.5` | 12.5 | $0.3125 | $0.1875 |
| 480p | 10 s | any | – | – | no | 1 | generate | `10 × 2.5 = 25` | 25 | $0.6250 | $0.3750 |
| 480p | 15 s | any | – | – | no | 1 | generate | `15 × 2.5 = 37.5` | 37.5 | $0.9375 | $0.5625 |
| 720p | 1 s | any | – | – | no | 1 | generate | `1 × 4.5 = 4.5` | 4.5 | $0.1125 | $0.0675 |
| 720p | 5 s | any | – | – | no | 1 | generate | `5 × 4.5 = 22.5` | 22.5 | $0.5625 | $0.3375 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 4.5 = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 4.5 = 67.5` | 67.5 | $1.6875 | $1.0125 |
| 1080p | 1 s | any | – | – | no | 1 | generate | `1 × 8 = 8` | 8 | $0.2000 | $0.1200 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `5 × 8 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `10 × 8 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 8 = 120` | 120 | $3.0000 | $1.8000 |

**`grok_video_v15_lite`** — formula: JS: plain

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 1 s | any | – | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| 480p | 5 s | any | – | – | no | 1 | generate | `5 × 1 = 5` | 5 | $0.1250 | $0.0750 |
| 480p | 10 s | any | – | – | no | 1 | generate | `10 × 1 = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `15 × 1 = 15` | 15 | $0.3750 | $0.2250 |
| 720p | 1 s | any | – | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| 720p | 5 s | any | – | – | no | 1 | generate | `5 × 1 = 5` | 5 | $0.1250 | $0.0750 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 1 = 10` | 10 | $0.2500 | $0.1500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 1 = 15` | 15 | $0.3750 | $0.2250 |
| 1080p | 1 s | any | – | – | no | 1 | generate | `1 × 4 = 4` | 4 | $0.1000 | $0.0600 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `5 × 4 = 20` | 20 | $0.5000 | $0.3000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `10 × 4 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 4 = 60` | 60 | $1.5000 | $0.9000 |

**`happy_horse_video`** — formula: JS: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 2.5) = 13` | 13 | $0.3250 | $0.1950 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 2.5) = 25` | 25 | $0.6250 | $0.3750 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 2.5) = 38` | 38 | $0.9500 | $0.5700 |
| 720p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 2.5) × 4 = 152` | 152 | $3.8000 | $2.2800 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 4.5) = 23` | 23 | $0.5750 | $0.3450 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 4.5) = 45` | 45 | $1.1250 | $0.6750 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 4.5) = 68` | 68 | $1.7000 | $1.0200 |
| 1080p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 4.5) × 4 = 272` | 272 | $6.8000 | $4.0800 |

**`flux_3_video`** — formula: JS: plain

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 5 s | any | – | – | no | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 10 s | any | – | – | no | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 15 s | any | – | – | no | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `5 × 6 = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `10 × 6 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `15 × 6 = 90` | 90 | $2.2500 | $1.3500 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `5 × 8 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `10 × 8 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `15 × 8 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `5 × 8 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `10 × 8 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `15 × 8 = 120` | 120 | $3.0000 | $1.8000 |
| 2k | 5 s | any | – | – | no | 1 | generate | `5 × 10 = 50` | 50 | $1.2500 | $0.7500 |
| 2k | 10 s | any | – | – | no | 1 | generate | `10 × 10 = 100` | 100 | $2.5000 | $1.5000 |
| 2k | 15 s | any | – | – | no | 1 | generate | `15 × 10 = 150` | 150 | $3.7500 | $2.2500 |
| 2k | 5 s | any | – | – | yes | 1 | generate | `5 × 10 = 50` | 50 | $1.2500 | $0.7500 |
| 2k | 10 s | any | – | – | yes | 1 | generate | `10 × 10 = 100` | 100 | $2.5000 | $1.5000 |
| 2k | 15 s | any | – | – | yes | 1 | generate | `15 × 10 = 150` | 150 | $3.7500 | $2.2500 |
| 4k | 5 s | any | – | – | no | 1 | generate | `5 × 13 = 65` | 65 | $1.6250 | $0.9750 |
| 4k | 10 s | any | – | – | no | 1 | generate | `10 × 13 = 130` | 130 | $3.2500 | $1.9500 |
| 4k | 15 s | any | – | – | no | 1 | generate | `15 × 13 = 195` | 195 | $4.8750 | $2.9250 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `5 × 13 = 65` | 65 | $1.6250 | $0.9750 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `10 × 13 = 130` | 130 | $3.2500 | $1.9500 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `15 × 13 = 195` | 195 | $4.8750 | $2.9250 |

#### Higgsfield Genjutsu / AI Influencer (motion control, replace object)

**`hf_mult_motion_control`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 3 s | any | – | – | no | 1 | generate | `ceil(3) × 3 = 9` | 9 | $0.2250 | $0.1350 |
| 480p | 5.4 s | any | – | – | no | 1 | generate | `ceil(5.4) × 3 = 18` | 18 | $0.4500 | $0.2700 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 3 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 3 = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 3 × 4 = 360` | 360 | $9.0000 | $5.4000 |
| 720p | 3 s | any | – | – | no | 1 | generate | `ceil(3) × 7 = 21` | 21 | $0.5250 | $0.3150 |
| 720p | 5.4 s | any | – | – | no | 1 | generate | `ceil(5.4) × 7 = 42` | 42 | $1.0500 | $0.6300 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 7 = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 7 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 7 × 4 = 840` | 840 | $21.0000 | $12.6000 |
| 1080p | 3 s | any | – | – | no | 1 | generate | `ceil(3) × 20 = 60` | 60 | $1.5000 | $0.9000 |
| 1080p | 5.4 s | any | – | – | no | 1 | generate | `ceil(5.4) × 20 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 20 = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 20 = 600` | 600 | $15.0000 | $9.0000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 20 × 4 = 2400` | 2400 | $60.0000 | $36.0000 |

**`hf_mult_motion_control_flash`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 3 s | any | – | – | no | 1 | generate | `ceil(3) × 1 = 3` | 3 | $0.0750 | $0.0450 |
| 480p | 5.4 s | any | – | – | no | 1 | generate | `ceil(5.4) × 1 = 6` | 6 | $0.1500 | $0.0900 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 1 = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 1 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 1 × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 720p | 3 s | any | – | – | no | 1 | generate | `ceil(3) × 2 = 6` | 6 | $0.1500 | $0.0900 |
| 720p | 5.4 s | any | – | – | no | 1 | generate | `ceil(5.4) × 2 = 12` | 12 | $0.3000 | $0.1800 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 2 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 2 × 4 = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 3 s | any | – | – | no | 1 | generate | `ceil(3) × 4 = 12` | 12 | $0.3000 | $0.1800 |
| 1080p | 5.4 s | any | – | – | no | 1 | generate | `ceil(5.4) × 4 = 24` | 24 | $0.6000 | $0.3600 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 4 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 4 × 4 = 480` | 480 | $12.0000 | $7.2000 |

**`hf_mult_replace_object`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 3 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 3 = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 3 × 4 = 360` | 360 | $9.0000 | $5.4000 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 7 = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 7 = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 7 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 7 × 4 = 840` | 840 | $21.0000 | $12.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 20 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 20 = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 20 = 600` | 600 | $15.0000 | $9.0000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 20 × 4 = 2400` | 2400 | $60.0000 | $36.0000 |

**`hf_mult_replace_object_flash`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 2 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 2 × 4 = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 4 = 16` | 16 | $0.4000 | $0.2400 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 4 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 4 × 4 = 480` | 480 | $12.0000 | $7.2000 |

**`ai_influencer_motion_control`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 3 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 3 = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 3 × 4 = 360` | 360 | $9.0000 | $5.4000 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 7 = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 7 = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 7 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 7 × 4 = 840` | 840 | $21.0000 | $12.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 20 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 20 = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 20 = 600` | 600 | $15.0000 | $9.0000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 20 × 4 = 2400` | 2400 | $60.0000 | $36.0000 |

**`ai_influencer_motion_control_flash`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 1 = 4` | 4 | $0.1000 | $0.0600 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 1 = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 1 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 1 × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 2 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 2 × 4 = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 4 = 16` | 16 | $0.4000 | $0.2400 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 4 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 4 × 4 = 480` | 480 | $12.0000 | $7.2000 |

**`ai_influencer_replace_object`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 3 = 12` | 12 | $0.3000 | $0.1800 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 3 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 3 = 90` | 90 | $2.2500 | $1.3500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 3 × 4 = 360` | 360 | $9.0000 | $5.4000 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 7 = 28` | 28 | $0.7000 | $0.4200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 7 = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 7 = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 7 × 4 = 840` | 840 | $21.0000 | $12.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 20 = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 20 = 200` | 200 | $5.0000 | $3.0000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 20 = 600` | 600 | $15.0000 | $9.0000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 20 × 4 = 2400` | 2400 | $60.0000 | $36.0000 |

**`ai_influencer_replace_object_flash`** — formula: JS: ceil_dur

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 1 = 4` | 4 | $0.1000 | $0.0600 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 1 = 10` | 10 | $0.2500 | $0.1500 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 1 = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 1 × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 2 = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 2 = 60` | 60 | $1.5000 | $0.9000 |
| 720p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 2 × 4 = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4) × 4 = 16` | 16 | $0.4000 | $0.2400 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10) × 4 = 40` | 40 | $1.0000 | $0.6000 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30) × 4 = 120` | 120 | $3.0000 | $1.8000 |
| 1080p | 30 s | any | – | – | no | 4 | generate | `ceil(30) × 4 × 4 = 480` | 480 | $12.0000 | $7.2000 |

**`hf_evolution`** — formula: inferred: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 720p | 5 s | any | model=hf_evolution | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | model=hf_evolution | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |

#### GPT Image

**`gpt_image_2`** — formula: JS: ceil₀.₀₁(batch × credits)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5` | 3.5 | $0.0875 | $0.0525 |
| 1k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14` | 14 | $0.3500 | $0.2100 |
| 1k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.5) = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 1k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.5) = 2` | 2 | $0.0500 | $0.0300 |
| 1k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5` | 5 | $0.1250 | $0.0750 |
| 2k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 7) = 7` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 2k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.5) = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 2k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.5) = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 2) = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 2) = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 12) = 12` | 12 | $0.3000 | $0.1800 |
| 4k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 12) = 48` | 48 | $1.2000 | $0.7200 |
| 4k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75` | 0.75 | $0.0188 | $0.0112 |
| 4k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3` | 3 | $0.0750 | $0.0450 |
| 4k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5` | 3.5 | $0.0875 | $0.0525 |
| 4k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14` | 14 | $0.3500 | $0.2100 |

**`gpt_image_2_5`** — formula: JS: ceil₀.₀₁(batch × credits)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | model=flare, quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25 (was 2)` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | model=flare, quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5 (was 8)` | 5 | $0.1250 | $0.0750 |
| 1k | – | any | model=flare, quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.25) = 0.25 (was 1)` | 0.25 | $0.0062 | $0.0038 |
| 1k | – | any | model=flare, quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.25) = 1 (was 4)` | 1 | $0.0250 | $0.0150 |
| 1k | – | any | model=flare, quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 4.5) = 4.5 (was 5)` | 4.5 | $0.1125 | $0.0675 |
| 1k | – | any | model=flare, quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 4.5) = 18 (was 20)` | 18 | $0.4500 | $0.2700 |
| 1k | – | any | model=flare, quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.5) = 0.5 (was 1)` | 0.5 | $0.0125 | $0.0075 |
| 1k | – | any | model=flare, quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.5) = 2 (was 4)` | 2 | $0.0500 | $0.0300 |
| 1k | – | any | model=flare, quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 2) = 2 (was 3)` | 2 | $0.0500 | $0.0300 |
| 1k | – | any | model=flare, quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 2) = 8 (was 12)` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | model=flare, quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 2.25) = 2.25 (was 3)` | 2.25 | $0.0562 | $0.0338 |
| 2k | – | any | model=flare, quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 2.25) = 9 (was 12)` | 9 | $0.2250 | $0.1350 |
| 2k | – | any | model=flare, quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.5) = 0.5 (was 1)` | 0.5 | $0.0125 | $0.0075 |
| 2k | – | any | model=flare, quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.5) = 2 (was 4)` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | model=flare, quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 7) = 7 (was 10)` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | model=flare, quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 7) = 28 (was 40)` | 28 | $0.7000 | $0.4200 |
| 2k | – | any | model=flare, quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75 (was 1.5)` | 0.75 | $0.0188 | $0.0112 |
| 2k | – | any | model=flare, quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3 (was 6)` | 3 | $0.0750 | $0.0450 |
| 2k | – | any | model=flare, quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5 (was 5)` | 3.5 | $0.0875 | $0.0525 |
| 2k | – | any | model=flare, quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14 (was 20)` | 14 | $0.3500 | $0.2100 |
| 4k | – | any | model=flare, quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.25) = 3.25 (was 4.5)` | 3.25 | $0.0812 | $0.0488 |
| 4k | – | any | model=flare, quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.25) = 13 (was 18)` | 13 | $0.3250 | $0.1950 |
| 4k | – | any | model=flare, quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75 (was 1.5)` | 0.75 | $0.0188 | $0.0112 |
| 4k | – | any | model=flare, quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3 (was 6)` | 3 | $0.0750 | $0.0450 |
| 4k | – | any | model=flare, quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 12) = 12 (was 16)` | 12 | $0.3000 | $0.1800 |
| 4k | – | any | model=flare, quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 12) = 48 (was 64)` | 48 | $1.2000 | $0.7200 |
| 4k | – | any | model=flare, quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25 (was 2)` | 1.25 | $0.0312 | $0.0188 |
| 4k | – | any | model=flare, quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5 (was 8)` | 5 | $0.1250 | $0.0750 |
| 4k | – | any | model=flare, quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 5.75) = 5.75 (was 8)` | 5.75 | $0.1438 | $0.0862 |
| 4k | – | any | model=flare, quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 5.75) = 23 (was 32)` | 23 | $0.5750 | $0.3450 |
| 1k | – | any | model=sunburst, quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25 (was 2)` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | model=sunburst, quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5 (was 8)` | 5 | $0.1250 | $0.0750 |
| 1k | – | any | model=sunburst, quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.5) = 0.5 (was 1)` | 0.5 | $0.0125 | $0.0075 |
| 1k | – | any | model=sunburst, quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.5) = 2 (was 4)` | 2 | $0.0500 | $0.0300 |
| 1k | – | any | model=sunburst, quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5 (was 5)` | 3.5 | $0.0875 | $0.0525 |
| 1k | – | any | model=sunburst, quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14 (was 20)` | 14 | $0.3500 | $0.2100 |
| 1k | – | any | model=sunburst, quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75 (was 1)` | 0.75 | $0.0188 | $0.0112 |
| 1k | – | any | model=sunburst, quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3 (was 4)` | 3 | $0.0750 | $0.0450 |
| 1k | – | any | model=sunburst, quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 2) = 2 (was 3)` | 2 | $0.0500 | $0.0300 |
| 1k | – | any | model=sunburst, quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 2) = 8 (was 12)` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | model=sunburst, quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 2.25) = 2.25 (was 3)` | 2.25 | $0.0562 | $0.0338 |
| 2k | – | any | model=sunburst, quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 2.25) = 9 (was 12)` | 9 | $0.2250 | $0.1350 |
| 2k | – | any | model=sunburst, quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75 (was 1)` | 0.75 | $0.0188 | $0.0112 |
| 2k | – | any | model=sunburst, quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3 (was 4)` | 3 | $0.0750 | $0.0450 |
| 2k | – | any | model=sunburst, quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 7) = 7 (was 10)` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | model=sunburst, quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 7) = 28 (was 40)` | 28 | $0.7000 | $0.4200 |
| 2k | – | any | model=sunburst, quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25 (was 1.5)` | 1.25 | $0.0312 | $0.0188 |
| 2k | – | any | model=sunburst, quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5 (was 6)` | 5 | $0.1250 | $0.0750 |
| 2k | – | any | model=sunburst, quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5 (was 5)` | 3.5 | $0.0875 | $0.0525 |
| 2k | – | any | model=sunburst, quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14 (was 20)` | 14 | $0.3500 | $0.2100 |
| 4k | – | any | model=sunburst, quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.25) = 3.25 (was 4.5)` | 3.25 | $0.0812 | $0.0488 |
| 4k | – | any | model=sunburst, quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.25) = 13 (was 18)` | 13 | $0.3250 | $0.1950 |
| 4k | – | any | model=sunburst, quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75 (was 1.5)` | 0.75 | $0.0188 | $0.0112 |
| 4k | – | any | model=sunburst, quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3 (was 6)` | 3 | $0.0750 | $0.0450 |
| 4k | – | any | model=sunburst, quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 12) = 12 (was 16)` | 12 | $0.3000 | $0.1800 |
| 4k | – | any | model=sunburst, quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 12) = 48 (was 64)` | 48 | $1.2000 | $0.7200 |
| 4k | – | any | model=sunburst, quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25 (was 2)` | 1.25 | $0.0312 | $0.0188 |
| 4k | – | any | model=sunburst, quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5 (was 8)` | 5 | $0.1250 | $0.0750 |
| 4k | – | any | model=sunburst, quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 5.75) = 5.75 (was 8)` | 5.75 | $0.1438 | $0.0862 |
| 4k | – | any | model=sunburst, quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 5.75) = 23 (was 32)` | 23 | $0.5750 | $0.3450 |

**`gpt_image_2_6`** — formula: JS: ceil₀.₀₁(batch × credits)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5` | 5 | $0.1250 | $0.0750 |
| 1k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75` | 0.75 | $0.0188 | $0.0112 |
| 1k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3` | 3 | $0.0750 | $0.0450 |
| 1k | – | any | quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 4.5) = 4.5` | 4.5 | $0.1125 | $0.0675 |
| 1k | – | any | quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 4.5) = 18` | 18 | $0.4500 | $0.2700 |
| 1k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1) = 1` | 1 | $0.0250 | $0.0150 |
| 1k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1) = 4` | 4 | $0.1000 | $0.0600 |
| 1k | – | any | quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 2) = 2` | 2 | $0.0500 | $0.0300 |
| 1k | – | any | quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 2) = 8` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 2) = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 2) = 8` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 2k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5` | 5 | $0.1250 | $0.0750 |
| 2k | – | any | quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 7) = 7` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 7) = 28` | 28 | $0.7000 | $0.4200 |
| 2k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.75) = 1.75` | 1.75 | $0.0438 | $0.0262 |
| 2k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.75) = 7` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5` | 3.5 | $0.0875 | $0.0525 |
| 2k | – | any | quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14` | 14 | $0.3500 | $0.2100 |
| 4k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.25) = 3.25` | 3.25 | $0.0812 | $0.0488 |
| 4k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.25) = 13` | 13 | $0.3250 | $0.1950 |
| 4k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.75) = 1.75` | 1.75 | $0.0438 | $0.0262 |
| 4k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.75) = 7` | 7 | $0.1750 | $0.1050 |
| 4k | – | any | quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 12) = 12` | 12 | $0.3000 | $0.1800 |
| 4k | – | any | quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 12) = 48` | 48 | $1.2000 | $0.7200 |
| 4k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 2.75) = 2.75` | 2.75 | $0.0688 | $0.0412 |
| 4k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 2.75) = 11` | 11 | $0.2750 | $0.1650 |
| 4k | – | any | quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 5.5) = 5.5` | 5.5 | $0.1375 | $0.0825 |
| 4k | – | any | quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 5.5) = 22` | 22 | $0.5500 | $0.3300 |

**`gpt_image_2_6_flare`** — formula: JS: ceil₀.₀₁(batch × credits)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5` | 5 | $0.1250 | $0.0750 |
| 1k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 0.75) = 0.75` | 0.75 | $0.0188 | $0.0112 |
| 1k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 0.75) = 3` | 3 | $0.0750 | $0.0450 |
| 1k | – | any | quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 6.5) = 6.5` | 6.5 | $0.1625 | $0.0975 |
| 1k | – | any | quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 6.5) = 26` | 26 | $0.6500 | $0.3900 |
| 1k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1) = 1` | 1 | $0.0250 | $0.0150 |
| 1k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1) = 4` | 4 | $0.1000 | $0.0600 |
| 1k | – | any | quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 2.25) = 2.25` | 2.25 | $0.0562 | $0.0338 |
| 1k | – | any | quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 2.25) = 9` | 9 | $0.2250 | $0.1350 |
| 2k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 2.25) = 2.25` | 2.25 | $0.0562 | $0.0338 |
| 2k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 2.25) = 9` | 9 | $0.2250 | $0.1350 |
| 2k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.25) = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 2k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.25) = 5` | 5 | $0.1250 | $0.0750 |
| 2k | – | any | quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 6.75) = 6.75` | 6.75 | $0.1688 | $0.1012 |
| 2k | – | any | quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 6.75) = 27` | 27 | $0.6750 | $0.4050 |
| 2k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 1.75) = 1.75` | 1.75 | $0.0438 | $0.0262 |
| 2k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 1.75) = 7` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.25) = 3.25` | 3.25 | $0.0812 | $0.0488 |
| 2k | – | any | quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.25) = 13` | 13 | $0.3250 | $0.1950 |
| 4k | – | any | quality=high | – | no | 1 | generate | `ceil₀.₀₁(1 × 3.5) = 3.5` | 3.5 | $0.0875 | $0.0525 |
| 4k | – | any | quality=high | – | no | 4 | generate | `ceil₀.₀₁(4 × 3.5) = 14` | 14 | $0.3500 | $0.2100 |
| 4k | – | any | quality=low | – | no | 1 | generate | `ceil₀.₀₁(1 × 2) = 2` | 2 | $0.0500 | $0.0300 |
| 4k | – | any | quality=low | – | no | 4 | generate | `ceil₀.₀₁(4 × 2) = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=max | – | no | 1 | generate | `ceil₀.₀₁(1 × 12) = 12` | 12 | $0.3000 | $0.1800 |
| 4k | – | any | quality=max | – | no | 4 | generate | `ceil₀.₀₁(4 × 12) = 48` | 48 | $1.2000 | $0.7200 |
| 4k | – | any | quality=medium | – | no | 1 | generate | `ceil₀.₀₁(1 × 2.75) = 2.75` | 2.75 | $0.0688 | $0.0412 |
| 4k | – | any | quality=medium | – | no | 4 | generate | `ceil₀.₀₁(4 × 2.75) = 11` | 11 | $0.2750 | $0.1650 |
| 4k | – | any | quality=xhigh | – | no | 1 | generate | `ceil₀.₀₁(1 × 5.5) = 5.5` | 5.5 | $0.1375 | $0.0825 |
| 4k | – | any | quality=xhigh | – | no | 4 | generate | `ceil₀.₀₁(4 × 5.5) = 22` | 22 | $0.5500 | $0.3300 |

#### Nano Banana / Seedream / other image

**`nano_banana_2_1`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | – | – | no | 1 | generate | `1 × 1.5 = 1.5` | 1.5 | $0.0375 | $0.0225 |
| 1k | – | any | – | – | no | 4 | generate | `4 × 1.5 = 6` | 6 | $0.1500 | $0.0900 |
| 2k | – | any | – | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | – | – | no | 1 | generate | `1 × 3 = 3` | 3 | $0.0750 | $0.0450 |
| 4k | – | any | – | – | no | 4 | generate | `4 × 3 = 12` | 12 | $0.3000 | $0.1800 |

**`seedream_v5_pro`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | – | – | no | 1 | generate | `1 × 1.25 = 1.25 (was 1.5)` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | – | – | no | 4 | generate | `4 × 1.25 = 5 (was 6)` | 5 | $0.1250 | $0.0750 |
| 1.5k | – | any | – | – | no | 1 | generate | `1 × 1.25 = 1.25 (was 1.5)` | 1.25 | $0.0312 | $0.0188 |
| 1.5k | – | any | – | – | no | 4 | generate | `4 × 1.25 = 5 (was 6)` | 5 | $0.1250 | $0.0750 |
| 2k | – | any | – | – | no | 1 | generate | `1 × 2.5 = 2.5 (was 3)` | 2.5 | $0.0625 | $0.0375 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 2.5 = 10 (was 12)` | 10 | $0.2500 | $0.1500 |

**`seedream_5_5`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | – | – | no | 1 | generate | `1 × 2.5 = 2.5` | 2.5 | $0.0625 | $0.0375 |
| 1k | – | any | – | – | no | 4 | generate | `4 × 2.5 = 10` | 10 | $0.2500 | $0.1500 |
| 1.5k | – | any | – | – | no | 1 | generate | `1 × 2.5 = 2.5` | 2.5 | $0.0625 | $0.0375 |
| 1.5k | – | any | – | – | no | 4 | generate | `4 × 2.5 = 10` | 10 | $0.2500 | $0.1500 |
| 2k | – | any | – | – | no | 1 | generate | `1 × 3.5 = 3.5` | 3.5 | $0.0875 | $0.0525 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 3.5 = 14` | 14 | $0.3500 | $0.2100 |

**`seedream_5_0_flash`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | – | – | no | 1 | generate | `1 × 0.5 = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 1k | – | any | – | – | no | 4 | generate | `4 × 0.5 = 2` | 2 | $0.0500 | $0.0300 |
| 1.5k | – | any | – | – | no | 1 | generate | `1 × 0.5 = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 1.5k | – | any | – | – | no | 4 | generate | `4 × 0.5 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | – | – | no | 1 | generate | `1 × 0.5 = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 0.5 = 2` | 2 | $0.0500 | $0.0300 |

**`3d_jutsu_angles`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | – | – | no | 1 | generate | `1 × 1.25 = 1.25 (was 1.5)` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | – | – | no | 4 | generate | `4 × 1.25 = 5 (was 6)` | 5 | $0.1250 | $0.0750 |
| 1.5k | – | any | – | – | no | 1 | generate | `1 × 1.25 = 1.25 (was 1.5)` | 1.25 | $0.0312 | $0.0188 |
| 1.5k | – | any | – | – | no | 4 | generate | `4 × 1.25 = 5 (was 6)` | 5 | $0.1250 | $0.0750 |
| 2k | – | any | – | – | no | 1 | generate | `1 × 2.5 = 2.5 (was 3)` | 2.5 | $0.0625 | $0.0375 |
| 2k | – | any | – | – | no | 4 | generate | `4 × 2.5 = 10 (was 12)` | 10 | $0.2500 | $0.1500 |

**`recraft_v4_1`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | model_type=standard | – | no | 1 | generate | `1 × 1.25 = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | model_type=standard | – | no | 4 | generate | `4 × 1.25 = 5` | 5 | $0.1250 | $0.0750 |
| 1k | – | any | model_type=utility | – | no | 1 | generate | `1 × 1.25 = 1.25` | 1.25 | $0.0312 | $0.0188 |
| 1k | – | any | model_type=utility | – | no | 4 | generate | `4 × 1.25 = 5` | 5 | $0.1250 | $0.0750 |
| 1k | – | any | model_type=vector | – | no | 1 | generate | `1 × 2.5 = 2.5` | 2.5 | $0.0625 | $0.0375 |
| 1k | – | any | model_type=vector | – | no | 4 | generate | `4 × 2.5 = 10` | 10 | $0.2500 | $0.1500 |
| 1k | – | any | model_type=utility_vector | – | no | 1 | generate | `1 × 2.5 = 2.5` | 2.5 | $0.0625 | $0.0375 |
| 1k | – | any | model_type=utility_vector | – | no | 4 | generate | `4 × 2.5 = 10` | 10 | $0.2500 | $0.1500 |
| 2k | – | any | model_type=standard | – | no | 1 | generate | `1 × 8 = 8` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | model_type=standard | – | no | 4 | generate | `4 × 8 = 32` | 32 | $0.8000 | $0.4800 |
| 2k | – | any | model_type=utility | – | no | 1 | generate | `1 × 8 = 8` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | model_type=utility | – | no | 4 | generate | `4 × 8 = 32` | 32 | $0.8000 | $0.4800 |
| 2k | – | any | model_type=vector | – | no | 1 | generate | `1 × 10 = 10` | 10 | $0.2500 | $0.1500 |
| 2k | – | any | model_type=vector | – | no | 4 | generate | `4 × 10 = 40` | 40 | $1.0000 | $0.6000 |
| 2k | – | any | model_type=utility_vector | – | no | 1 | generate | `1 × 10 = 10` | 10 | $0.2500 | $0.1500 |
| 2k | – | any | model_type=utility_vector | – | no | 4 | generate | `4 × 10 = 40` | 40 | $1.0000 | $0.6000 |

**`ideogram_4_6`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 2k | – | any | quality=high, has_references=False | – | no | 1 | generate | `1 × 3.25 = 3.25` | 3.25 | $0.0812 | $0.0488 |
| 2k | – | any | quality=high, has_references=False | – | no | 4 | generate | `4 × 3.25 = 13` | 13 | $0.3250 | $0.1950 |
| 2k | – | any | quality=high, has_references=True | – | no | 1 | generate | `1 × 7 = 7` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | quality=high, has_references=True | – | no | 4 | generate | `4 × 7 = 28` | 28 | $0.7000 | $0.4200 |
| 2k | – | any | quality=low, has_references=False | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| 2k | – | any | quality=low, has_references=False | – | no | 4 | generate | `4 × 1 = 4` | 4 | $0.1000 | $0.0600 |
| 2k | – | any | quality=low, has_references=True | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| 2k | – | any | quality=low, has_references=True | – | no | 4 | generate | `4 × 1 = 4` | 4 | $0.1000 | $0.0600 |
| 2k | – | any | quality=medium, has_references=False | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | quality=medium, has_references=False | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 2k | – | any | quality=medium, has_references=True | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | quality=medium, has_references=True | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=high, has_references=False | – | no | 1 | generate | `1 × 6.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| 4k | – | any | quality=high, has_references=False | – | no | 4 | generate | `4 × 6.25 = 25` | 25 | $0.6250 | $0.3750 |
| 4k | – | any | quality=high, has_references=True | – | no | 1 | generate | `1 × 19 = 19` | 19 | $0.4750 | $0.2850 |
| 4k | – | any | quality=high, has_references=True | – | no | 4 | generate | `4 × 19 = 76` | 76 | $1.9000 | $1.1400 |
| 4k | – | any | quality=low, has_references=False | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 4k | – | any | quality=low, has_references=False | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=low, has_references=True | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 4k | – | any | quality=low, has_references=True | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=medium, has_references=False | – | no | 1 | generate | `1 × 3.75 = 3.75` | 3.75 | $0.0938 | $0.0562 |
| 4k | – | any | quality=medium, has_references=False | – | no | 4 | generate | `4 × 3.75 = 15` | 15 | $0.3750 | $0.2250 |
| 4k | – | any | quality=medium, has_references=True | – | no | 1 | generate | `1 × 6.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| 4k | – | any | quality=medium, has_references=True | – | no | 4 | generate | `4 × 6.25 = 25` | 25 | $0.6250 | $0.3750 |

**`ideogram_4_6_precise_edit`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 2k | – | any | quality=high | – | no | 1 | generate | `1 × 7 = 7` | 7 | $0.1750 | $0.1050 |
| 2k | – | any | quality=high | – | no | 4 | generate | `4 × 7 = 28` | 28 | $0.7000 | $0.4200 |
| 2k | – | any | quality=low | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| 2k | – | any | quality=low | – | no | 4 | generate | `4 × 1 = 4` | 4 | $0.1000 | $0.0600 |
| 2k | – | any | quality=medium | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | quality=medium | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=high | – | no | 1 | generate | `1 × 19 = 19` | 19 | $0.4750 | $0.2850 |
| 4k | – | any | quality=high | – | no | 4 | generate | `4 × 19 = 76` | 76 | $1.9000 | $1.1400 |
| 4k | – | any | quality=low | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| 4k | – | any | quality=low | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| 4k | – | any | quality=medium | – | no | 1 | generate | `1 × 6.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| 4k | – | any | quality=medium | – | no | 4 | generate | `4 × 6.25 = 25` | 25 | $0.6250 | $0.3750 |

**`ideogram_4_5`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | – | any | quality=high | – | no | 1 | generate | `1 × 6.25 = 6.25` | 6.25 | $0.1562 | $0.0938 |
| – | – | any | quality=high | – | no | 4 | generate | `4 × 6.25 = 25` | 25 | $0.6250 | $0.3750 |
| – | – | any | quality=low | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| – | – | any | quality=low | – | no | 4 | generate | `4 × 1 = 4` | 4 | $0.1000 | $0.0600 |
| – | – | any | quality=medium | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| – | – | any | quality=medium | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| – | – | any | quality=very_low | – | no | 1 | generate | `1 × 0.25 = 0.25` | 0.25 | $0.0062 | $0.0038 |
| – | – | any | quality=very_low | – | no | 4 | generate | `4 × 0.25 = 1` | 1 | $0.0250 | $0.0150 |

**`ideogram_4_5_precise_edit`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | – | any | quality=high | – | no | 1 | generate | `1 × 7 = 7` | 7 | $0.1750 | $0.1050 |
| – | – | any | quality=high | – | no | 4 | generate | `4 × 7 = 28` | 28 | $0.7000 | $0.4200 |
| – | – | any | quality=low | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| – | – | any | quality=low | – | no | 4 | generate | `4 × 1 = 4` | 4 | $0.1000 | $0.0600 |
| – | – | any | quality=medium | – | no | 1 | generate | `1 × 2 = 2` | 2 | $0.0500 | $0.0300 |
| – | – | any | quality=medium | – | no | 4 | generate | `4 × 2 = 8` | 8 | $0.2000 | $0.1200 |
| – | – | any | quality=very_low | – | no | 1 | generate | `1 × 0.5 = 0.5` | 0.5 | $0.0125 | $0.0075 |
| – | – | any | quality=very_low | – | no | 4 | generate | `4 × 0.5 = 2` | 2 | $0.0500 | $0.0300 |

**`ideogram_vector`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | – | any | operation=vectorize | – | no | 1 | generate | `1 × 3 = 3` | 3 | $0.0750 | $0.0450 |
| – | – | any | operation=generate, quality=high, has_references=False | – | no | 1 | generate | `1 × 6.5 = 6.5` | 6.5 | $0.1625 | $0.0975 |
| – | – | any | operation=generate, quality=high, has_references=False | – | no | 4 | generate | `4 × 6.5 = 26` | 26 | $0.6500 | $0.3900 |
| – | – | any | operation=generate, quality=high, has_references=True | – | no | 1 | generate | `1 × 10 = 10` | 10 | $0.2500 | $0.1500 |
| – | – | any | operation=generate, quality=high, has_references=True | – | no | 4 | generate | `4 × 10 = 40` | 40 | $1.0000 | $0.6000 |
| – | – | any | operation=generate, quality=low, has_references=False | – | no | 1 | generate | `1 × 4 = 4` | 4 | $0.1000 | $0.0600 |
| – | – | any | operation=generate, quality=low, has_references=False | – | no | 4 | generate | `4 × 4 = 16` | 16 | $0.4000 | $0.2400 |
| – | – | any | operation=generate, quality=low, has_references=True | – | no | 1 | generate | `1 × 4 = 4` | 4 | $0.1000 | $0.0600 |
| – | – | any | operation=generate, quality=low, has_references=True | – | no | 4 | generate | `4 × 4 = 16` | 16 | $0.4000 | $0.2400 |
| – | – | any | operation=generate, quality=medium, has_references=False | – | no | 1 | generate | `1 × 5 = 5` | 5 | $0.1250 | $0.0750 |
| – | – | any | operation=generate, quality=medium, has_references=False | – | no | 4 | generate | `4 × 5 = 20` | 20 | $0.5000 | $0.3000 |
| – | – | any | operation=generate, quality=medium, has_references=True | – | no | 1 | generate | `1 × 5 = 5` | 5 | $0.1250 | $0.0750 |
| – | – | any | operation=generate, quality=medium, has_references=True | – | no | 4 | generate | `4 × 5 = 20` | 20 | $0.5000 | $0.3000 |

**`p_image_ideogram`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1k | – | any | thinking=very-low | – | no | 1 | generate | `1 × 0.1 = 0.1` | 0.1 | $0.0025 | $0.0015 |
| 1k | – | any | thinking=very-low | – | no | 4 | generate | `4 × 0.1 = 0.4` | 0.4 | $0.0100 | $0.0060 |
| 1k | – | any | thinking=low | – | no | 1 | generate | `1 × 0.25 = 0.25` | 0.25 | $0.0062 | $0.0038 |
| 1k | – | any | thinking=low | – | no | 4 | generate | `4 × 0.25 = 1` | 1 | $0.0250 | $0.0150 |
| 1k | – | any | thinking=medium | – | no | 1 | generate | `1 × 0.3 = 0.3` | 0.3 | $0.0075 | $0.0045 |
| 1k | – | any | thinking=medium | – | no | 4 | generate | `4 × 0.3 = 1.2` | 1.2 | $0.0300 | $0.0180 |
| 1k | – | any | thinking=high | – | no | 1 | generate | `1 × 0.5 = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 1k | – | any | thinking=high | – | no | 4 | generate | `4 × 0.5 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | thinking=very-low | – | no | 1 | generate | `1 × 0.2 = 0.2` | 0.2 | $0.0050 | $0.0030 |
| 2k | – | any | thinking=very-low | – | no | 4 | generate | `4 × 0.2 = 0.8` | 0.8 | $0.0200 | $0.0120 |
| 2k | – | any | thinking=low | – | no | 1 | generate | `1 × 0.5 = 0.5` | 0.5 | $0.0125 | $0.0075 |
| 2k | – | any | thinking=low | – | no | 4 | generate | `4 × 0.5 = 2` | 2 | $0.0500 | $0.0300 |
| 2k | – | any | thinking=medium | – | no | 1 | generate | `1 × 0.6 = 0.6` | 0.6 | $0.0150 | $0.0090 |
| 2k | – | any | thinking=medium | – | no | 4 | generate | `4 × 0.6 = 2.4` | 2.4 | $0.0600 | $0.0360 |
| 2k | – | any | thinking=high | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| 2k | – | any | thinking=high | – | no | 4 | generate | `4 × 1 = 4` | 4 | $0.1000 | $0.0600 |

**`gif`** — formula: JS: batch × credits

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | – | any | mode=create | – | no | 1 | generate | `1 × 1 = 1` | 1 | $0.0250 | $0.0150 |
| – | – | any | mode=recreate | – | no | 1 | generate | `1 × 3 = 3` | 3 | $0.0750 | $0.0450 |

#### Upscale / video tools

**`flux_video_upscale`** — formula: JS: ceil₀.₀₁

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p → 720p | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(0.5 × 10) = 5` | 5 | $0.1250 | $0.0750 |
| 480p → 1080p | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(1.75 × 10) = 17.5` | 17.5 | $0.4375 | $0.2625 |
| 480p → 2k | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(3.5 × 10) = 35` | 35 | $0.8750 | $0.5250 |
| 720p → 1080p | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(1.75 × 10) = 17.5` | 17.5 | $0.4375 | $0.2625 |
| 720p → 2k | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(3 × 10) = 30` | 30 | $0.7500 | $0.4500 |
| 720p → 4k | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(8 × 10) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p → 2k | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(1.75 × 10) = 17.5` | 17.5 | $0.4375 | $0.2625 |
| 1080p → 4k | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(6.5 × 10) = 65` | 65 | $1.6250 | $0.9750 |
| 2k → 4k | 10 s source | any | creativity=0 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(5 × 10) = 50` | 50 | $1.2500 | $0.7500 |
| 480p → 720p | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(0.75 × 10) = 7.5` | 7.5 | $0.1875 | $0.1125 |
| 480p → 1080p | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(2.5 × 10) = 25` | 25 | $0.6250 | $0.3750 |
| 480p → 2k | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(5 × 10) = 50` | 50 | $1.2500 | $0.7500 |
| 720p → 1080p | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(1.75 × 10) = 17.5` | 17.5 | $0.4375 | $0.2625 |
| 720p → 2k | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(4 × 10) = 40` | 40 | $1.0000 | $0.6000 |
| 720p → 4k | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(11 × 10) = 110` | 110 | $2.7500 | $1.6500 |
| 1080p → 2k | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(2.5 × 10) = 25` | 25 | $0.6250 | $0.3750 |
| 1080p → 4k | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(9 × 10) = 90` | 90 | $2.2500 | $1.3500 |
| 2k → 4k | 10 s source | any | creativity=1 | – | yes (source) | 1 | upscale | `ceil₀.₀₁(7 × 10) = 70` | 70 | $1.7500 | $1.0500 |

**`fps_boost`** — formula: inferred

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 10 s source | any | topaz 24→30 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 720p | 10 s source | any | topaz 24→30 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 1080p | 10 s source | any | topaz 24→30 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 2k | 10 s source | any | topaz 24→30 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 4k | 10 s source | any | topaz 24→30 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 480p | 10 s source | any | topaz 24→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 720p | 10 s source | any | topaz 24→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 1080p | 10 s source | any | topaz 24→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 2k | 10 s source | any | topaz 24→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 4k | 10 s source | any | topaz 24→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 480p | 10 s source | any | topaz 24→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 720p | 10 s source | any | topaz 24→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 1080p | 10 s source | any | topaz 24→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 2k | 10 s source | any | topaz 24→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 4k | 10 s source | any | topaz 24→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 480p | 10 s source | any | topaz 24→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 720p | 10 s source | any | topaz 24→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 1080p | 10 s source | any | topaz 24→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(3.3 × 10) = 33 (rounding inferred)` | 33 | $0.8250 | $0.4950 |
| 2k | 10 s source | any | topaz 24→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 4k | 10 s source | any | topaz 24→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(5.5 × 10) = 55 (rounding inferred)` | 55 | $1.3750 | $0.8250 |
| 480p | 10 s source | any | topaz 30→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 720p | 10 s source | any | topaz 30→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 1080p | 10 s source | any | topaz 30→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 2k | 10 s source | any | topaz 30→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(6.9 × 10) = 69 (rounding inferred)` | 69 | $1.7250 | $1.0350 |
| 4k | 10 s source | any | topaz 30→60 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(6.9 × 10) = 69 (rounding inferred)` | 69 | $1.7250 | $1.0350 |
| 480p | 10 s source | any | topaz 30→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 720p | 10 s source | any | topaz 30→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 1080p | 10 s source | any | topaz 30→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 2k | 10 s source | any | topaz 30→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(6.9 × 10) = 69 (rounding inferred)` | 69 | $1.7250 | $1.0350 |
| 4k | 10 s source | any | topaz 30→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(6.9 × 10) = 69 (rounding inferred)` | 69 | $1.7250 | $1.0350 |
| 480p | 10 s source | any | topaz 30→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 720p | 10 s source | any | topaz 30→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 1080p | 10 s source | any | topaz 30→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4.1 × 10) = 41 (rounding inferred)` | 41 | $1.0250 | $0.6150 |
| 2k | 10 s source | any | topaz 30→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(6.9 × 10) = 69 (rounding inferred)` | 69 | $1.7250 | $1.0350 |
| 4k | 10 s source | any | topaz 30→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(6.9 × 10) = 69 (rounding inferred)` | 69 | $1.7250 | $1.0350 |
| 480p | 10 s source | any | topaz 60→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(8.1 × 10) = 81 (rounding inferred)` | 81 | $2.0250 | $1.2150 |
| 720p | 10 s source | any | topaz 60→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(8.1 × 10) = 81 (rounding inferred)` | 81 | $2.0250 | $1.2150 |
| 1080p | 10 s source | any | topaz 60→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(8.1 × 10) = 81 (rounding inferred)` | 81 | $2.0250 | $1.2150 |
| 2k | 10 s source | any | topaz 60→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(13.7 × 10) = 137 (rounding inferred)` | 137 | $3.4250 | $2.0550 |
| 4k | 10 s source | any | topaz 60→90 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(13.7 × 10) = 137 (rounding inferred)` | 137 | $3.4250 | $2.0550 |
| 480p | 10 s source | any | topaz 60→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(8.1 × 10) = 81 (rounding inferred)` | 81 | $2.0250 | $1.2150 |
| 720p | 10 s source | any | topaz 60→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(8.1 × 10) = 81 (rounding inferred)` | 81 | $2.0250 | $1.2150 |
| 1080p | 10 s source | any | topaz 60→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(8.1 × 10) = 81 (rounding inferred)` | 81 | $2.0250 | $1.2150 |
| 2k | 10 s source | any | topaz 60→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(13.7 × 10) = 137 (rounding inferred)` | 137 | $3.4250 | $2.0550 |
| 4k | 10 s source | any | topaz 60→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(13.7 × 10) = 137 (rounding inferred)` | 137 | $3.4250 | $2.0550 |
| 480p | 10 s source | any | topaz 90→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(12 × 10) = 120 (rounding inferred)` | 120 | $3.0000 | $1.8000 |
| 720p | 10 s source | any | topaz 90→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(12 × 10) = 120 (rounding inferred)` | 120 | $3.0000 | $1.8000 |
| 1080p | 10 s source | any | topaz 90→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(12 × 10) = 120 (rounding inferred)` | 120 | $3.0000 | $1.8000 |
| 2k | 10 s source | any | topaz 90→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(20.5 × 10) = 205 (rounding inferred)` | 205 | $5.1250 | $3.0750 |
| 4k | 10 s source | any | topaz 90→120 fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(20.5 × 10) = 205 (rounding inferred)` | 205 | $5.1250 | $3.0750 |
| 1080p | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(2 × 10) = 20 (rounding inferred)` | 20 | $0.5000 | $0.3000 |
| 2k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4 × 10) = 40 (rounding inferred)` | 40 | $1.0000 | $0.6000 |
| 4k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(7.5 × 10) = 75 (rounding inferred)` | 75 | $1.8750 | $1.1250 |
| 8k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(30 × 10) = 300 (rounding inferred)` | 300 | $7.5000 | $4.5000 |
| 1080p | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(4 × 10) = 40 (rounding inferred)` | 40 | $1.0000 | $0.6000 |
| 2k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(7.5 × 10) = 75 (rounding inferred)` | 75 | $1.8750 | $1.1250 |
| 4k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(15 × 10) = 150 (rounding inferred)` | 150 | $3.7500 | $2.2500 |
| 8k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(60 × 10) = 600 (rounding inferred)` | 600 | $15.0000 | $9.0000 |
| 1080p | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(7.5 × 10) = 75 (rounding inferred)` | 75 | $1.8750 | $1.1250 |
| 2k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(15 × 10) = 150 (rounding inferred)` | 150 | $3.7500 | $2.2500 |
| 4k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(30 × 10) = 300 (rounding inferred)` | 300 | $7.5000 | $4.5000 |
| 8k | 10 s source | any | bytedance None→None fps | – | yes (source) | 1 | fps boost | `ceil₀.₀₁(120 × 10) = 1200 (rounding inferred)` | 1200 | $30.0000 | $18.0000 |

**`topaz_hyperion_2_5`** — formula: JS: frames

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames × 2.6 / 24) = 26` | 26 | $0.6500 | $0.3900 |
| 480p | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames × 2.6 / 24) = 32.5` | 32.5 | $0.8125 | $0.4875 |
| 480p | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames × 2.6 / 24) = 65` | 65 | $1.6250 | $0.9750 |
| 720p | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames × 2.6 / 24) = 26` | 26 | $0.6500 | $0.3900 |
| 720p | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames × 2.6 / 24) = 32.5` | 32.5 | $0.8125 | $0.4875 |
| 720p | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames × 2.6 / 24) = 65` | 65 | $1.6250 | $0.9750 |
| 1080p | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames × 2.6 / 24) = 26` | 26 | $0.6500 | $0.3900 |
| 1080p | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames × 2.6 / 24) = 32.5` | 32.5 | $0.8125 | $0.4875 |
| 1080p | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames × 2.6 / 24) = 65` | 65 | $1.6250 | $0.9750 |
| 2k | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames × 5.2 / 24) = 52` | 52 | $1.3000 | $0.7800 |
| 2k | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames × 5.2 / 24) = 65` | 65 | $1.6250 | $0.9750 |
| 2k | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames × 5.2 / 24) = 130` | 130 | $3.2500 | $1.9500 |
| 4k | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames × 5.2 / 24) = 52` | 52 | $1.3000 | $0.7800 |
| 4k | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames × 5.2 / 24) = 65` | 65 | $1.6250 | $0.9750 |
| 4k | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames × 5.2 / 24) = 130` | 130 | $3.2500 | $1.9500 |

**`sam_3_video`** — formula: JS: frames

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames × 0.225 / 24) = 2.25` | 2.25 | $0.0562 | $0.0338 |
| – | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames × 0.225 / 24) = 2.82` | 2.82 | $0.0705 | $0.0423 |
| – | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames × 0.225 / 24) = 5.63` | 5.63 | $0.1408 | $0.0844 |

**`depth_anything_video`** — formula: JS: frames

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 10 s @ 24 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(240 frames / 24 fps × 1.5) = 15` | 15 | $0.3750 | $0.2250 |
| – | 10 s @ 30 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(300 frames / 30 fps × 1.5) = 15` | 15 | $0.3750 | $0.2250 |
| – | 10 s @ 60 fps | any | – | – | yes (source) | 1 | process video | `ceil₀.₀₁(600 frames / 60 fps × 1.5) = 15` | 15 | $0.3750 | $0.2250 |

**`reframe`** — formula: JS: reframe

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s source | any | – | – | yes (source) | 1 | reframe | `ceil(5 × 3 + 3 × 1.25) = 19` | 19 | $0.4750 | $0.2850 |
| 480p | 10 s source | any | – | – | yes (source) | 1 | reframe | `ceil(10 × 3 + 3 × 1.25) = 34` | 34 | $0.8500 | $0.5100 |
| 480p | 15 s source | any | – | – | yes (source) | 1 | reframe | `ceil(15 × 3 + 3 × 1.25) = 49` | 49 | $1.2250 | $0.7350 |
| 480p | 30 s source | any | – | – | yes (source) | 1 | reframe | `ceil(30 × 3 + 5 × 1.25) = 97` | 97 | $2.4250 | $1.4550 |
| 480p | 60 s source | any | – | – | yes (source) | 1 | reframe | `ceil(60 × 3 + 9 × 1.25) = 192` | 192 | $4.8000 | $2.8800 |
| 720p | 5 s source | any | – | – | yes (source) | 1 | reframe | `ceil(5 × 4.5 + 3 × 1.25) = 27` | 27 | $0.6750 | $0.4050 |
| 720p | 10 s source | any | – | – | yes (source) | 1 | reframe | `ceil(10 × 4.5 + 3 × 1.25) = 49` | 49 | $1.2250 | $0.7350 |
| 720p | 15 s source | any | – | – | yes (source) | 1 | reframe | `ceil(15 × 4.5 + 3 × 1.25) = 72` | 72 | $1.8000 | $1.0800 |
| 720p | 30 s source | any | – | – | yes (source) | 1 | reframe | `ceil(30 × 4.5 + 5 × 1.25) = 142` | 142 | $3.5500 | $2.1300 |
| 720p | 60 s source | any | – | – | yes (source) | 1 | reframe | `ceil(60 × 4.5 + 9 × 1.25) = 282` | 282 | $7.0500 | $4.2300 |
| 1080p | 5 s source | any | – | – | yes (source) | 1 | reframe | `ceil(5 × 12 + 3 × 1.25) = 64` | 64 | $1.6000 | $0.9600 |
| 1080p | 10 s source | any | – | – | yes (source) | 1 | reframe | `ceil(10 × 12 + 3 × 1.25) = 124` | 124 | $3.1000 | $1.8600 |
| 1080p | 15 s source | any | – | – | yes (source) | 1 | reframe | `ceil(15 × 12 + 3 × 1.25) = 184` | 184 | $4.6000 | $2.7600 |
| 1080p | 30 s source | any | – | – | yes (source) | 1 | reframe | `ceil(30 × 12 + 5 × 1.25) = 367` | 367 | $9.1750 | $5.5050 |
| 1080p | 60 s source | any | – | – | yes (source) | 1 | reframe | `ceil(60 × 12 + 9 × 1.25) = 732` | 732 | $18.3000 | $10.9800 |

**`draw_to_video`** — formula: inferred

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 3) + 1 × 3.5 = 18.5 (inferred)` | 18.5 | $0.4625 | $0.2775 |
| 480p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 3) + 1 × 3.5 = 33.5 (inferred)` | 33.5 | $0.8375 | $0.5025 |
| 720p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 4.5) + 1 × 3.5 = 26.5 (inferred)` | 26.5 | $0.6625 | $0.3975 |
| 720p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 4.5) + 1 × 3.5 = 48.5 (inferred)` | 48.5 | $1.2125 | $0.7275 |
| 1080p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 12) + 1 × 3.5 = 63.5 (inferred)` | 63.5 | $1.5875 | $0.9525 |
| 1080p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 12) + 1 × 3.5 = 123.5 (inferred)` | 123.5 | $3.0875 | $1.8525 |

**`swap_object`** — formula: inferred

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 3) + 1 × 3.5 = 18.5 (inferred)` | 18.5 | $0.4625 | $0.2775 |
| 480p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 3) + 1 × 3.5 = 33.5 (inferred)` | 33.5 | $0.8375 | $0.5025 |
| 720p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 4.5) + 1 × 3.5 = 26.5 (inferred)` | 26.5 | $0.6625 | $0.3975 |
| 720p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 4.5) + 1 × 3.5 = 48.5 (inferred)` | 48.5 | $1.2125 | $0.7275 |
| 1080p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 12) + 1 × 3.5 = 63.5 (inferred)` | 63.5 | $1.5875 | $0.9525 |
| 1080p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 12) + 1 × 3.5 = 123.5 (inferred)` | 123.5 | $3.0875 | $1.8525 |

**`remove_object`** — formula: inferred

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 3) + 1 × 3.5 = 18.5 (inferred)` | 18.5 | $0.4625 | $0.2775 |
| 480p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 3) + 1 × 3.5 = 33.5 (inferred)` | 33.5 | $0.8375 | $0.5025 |
| 720p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 4.5) + 1 × 3.5 = 26.5 (inferred)` | 26.5 | $0.6625 | $0.3975 |
| 720p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 4.5) + 1 × 3.5 = 48.5 (inferred)` | 48.5 | $1.2125 | $0.7275 |
| 1080p | 5 s | any | – | – | yes (source) | 1 | generate | `ceil(5 × 12) + 1 × 3.5 = 63.5 (inferred)` | 63.5 | $1.5875 | $0.9525 |
| 1080p | 10 s | any | – | – | yes (source) | 1 | generate | `ceil(10 × 12) + 1 × 3.5 = 123.5 (inferred)` | 123.5 | $3.0875 | $1.8525 |

#### Audio / TTS / dubbing

**`elevenlabs_v4`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | short line (60 chars) | any | model=elevenlabs_v4 | – | no | 1 | TTS | `ceil(60/50) × 0.23 = 0.46` | 0.46 | $0.0115 | $0.0069 |
| – | short line (60 chars) | any | model=elevenlabs_v4 | – | no | 4 | TTS | `ceil(60/50) × 0.23 × 4 = 1.84` | 1.84 | $0.0460 | $0.0276 |
| – | paragraph (400 chars) | any | model=elevenlabs_v4 | – | no | 1 | TTS | `ceil(400/50) × 0.23 = 1.84` | 1.84 | $0.0460 | $0.0276 |
| – | paragraph (400 chars) | any | model=elevenlabs_v4 | – | no | 4 | TTS | `ceil(400/50) × 0.23 × 4 = 7.36` | 7.36 | $0.1840 | $0.1104 |
| – | page (2,000 chars) | any | model=elevenlabs_v4 | – | no | 1 | TTS | `ceil(2000/50) × 0.23 = 9.2` | 9.2 | $0.2300 | $0.1380 |
| – | page (2,000 chars) | any | model=elevenlabs_v4 | – | no | 4 | TTS | `ceil(2000/50) × 0.23 × 4 = 36.8` | 36.8 | $0.9200 | $0.5520 |

**`elevenlabs_v4_turbo`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | short line (60 chars) | any | model=elevenlabs_v4_turbo | – | no | 1 | TTS | `ceil(60/50) × 0.15 = 0.3` | 0.3 | $0.0075 | $0.0045 |
| – | short line (60 chars) | any | model=elevenlabs_v4_turbo | – | no | 4 | TTS | `ceil(60/50) × 0.15 × 4 = 1.2` | 1.2 | $0.0300 | $0.0180 |
| – | paragraph (400 chars) | any | model=elevenlabs_v4_turbo | – | no | 1 | TTS | `ceil(400/50) × 0.15 = 1.2` | 1.2 | $0.0300 | $0.0180 |
| – | paragraph (400 chars) | any | model=elevenlabs_v4_turbo | – | no | 4 | TTS | `ceil(400/50) × 0.15 × 4 = 4.8` | 4.8 | $0.1200 | $0.0720 |
| – | page (2,000 chars) | any | model=elevenlabs_v4_turbo | – | no | 1 | TTS | `ceil(2000/50) × 0.15 = 6` | 6 | $0.1500 | $0.0900 |
| – | page (2,000 chars) | any | model=elevenlabs_v4_turbo | – | no | 4 | TTS | `ceil(2000/50) × 0.15 × 4 = 24` | 24 | $0.6000 | $0.3600 |

**`text2speech_v2`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | short line (60 chars) | any | model=minimax | – | no | 1 | TTS | `ceil(60/50) × 0.15 = 0.3` | 0.3 | $0.0075 | $0.0045 |
| – | paragraph (400 chars) | any | model=minimax | – | no | 1 | TTS | `ceil(400/50) × 0.15 = 1.2` | 1.2 | $0.0300 | $0.0180 |
| – | page (2,000 chars) | any | model=minimax | – | no | 1 | TTS | `ceil(2000/50) × 0.15 = 6` | 6 | $0.1500 | $0.0900 |
| – | short line (60 chars) | any | model=elevenlabs | – | no | 1 | TTS | `ceil(60/50) × 0.15 = 0.3` | 0.3 | $0.0075 | $0.0045 |
| – | paragraph (400 chars) | any | model=elevenlabs | – | no | 1 | TTS | `ceil(400/50) × 0.15 = 1.2` | 1.2 | $0.0300 | $0.0180 |
| – | page (2,000 chars) | any | model=elevenlabs | – | no | 1 | TTS | `ceil(2000/50) × 0.15 = 6` | 6 | $0.1500 | $0.0900 |
| – | short line (60 chars) | any | model=seed_speech | – | no | 1 | TTS | `ceil(60/50) × 0.1 = 0.2` | 0.2 | $0.0050 | $0.0030 |
| – | paragraph (400 chars) | any | model=seed_speech | – | no | 1 | TTS | `ceil(400/50) × 0.1 = 0.8` | 0.8 | $0.0200 | $0.0120 |
| – | page (2,000 chars) | any | model=seed_speech | – | no | 1 | TTS | `ceil(2000/50) × 0.1 = 4` | 4 | $0.1000 | $0.0600 |
| – | short line (60 chars) | any | model=vibe_voice | – | no | 1 | TTS | `ceil(60/50) × 0.1 = 0.2` | 0.2 | $0.0050 | $0.0030 |
| – | paragraph (400 chars) | any | model=vibe_voice | – | no | 1 | TTS | `ceil(400/50) × 0.1 = 0.8` | 0.8 | $0.0200 | $0.0120 |
| – | page (2,000 chars) | any | model=vibe_voice | – | no | 1 | TTS | `ceil(2000/50) × 0.1 = 4` | 4 | $0.1000 | $0.0600 |
| – | short line (60 chars) | any | model=cozy_voice | – | no | 1 | TTS | `ceil(60/50) × 0.05 = 0.1` | 0.1 | $0.0025 | $0.0015 |
| – | paragraph (400 chars) | any | model=cozy_voice | – | no | 1 | TTS | `ceil(400/50) × 0.05 = 0.4` | 0.4 | $0.0100 | $0.0060 |
| – | page (2,000 chars) | any | model=cozy_voice | – | no | 1 | TTS | `ceil(2000/50) × 0.05 = 2` | 2 | $0.0500 | $0.0300 |

**`seed_audio`** — formula: JS

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | short line (60 chars) | any | – | – | no | 1 | TTS | `clamp(ceil(60/15), 1, 120) × 0.1 = 0.4` | 0.4 | $0.0100 | $0.0060 |
| – | paragraph (400 chars) | any | – | – | no | 1 | TTS | `clamp(ceil(400/15), 1, 120) × 0.1 = 2.7` | 2.7 | $0.0675 | $0.0405 |
| – | page (2,000 chars) | any | – | – | no | 1 | TTS | `clamp(ceil(2000/15), 1, 120) × 0.1 = 12` | 12 | $0.3000 | $0.1800 |

**`qwen_audio_tts`** — formula: JS

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | short line (60 chars) | any | – | – | no | 1 | TTS | `max(1, ceil(60 × 3/70)) / 100 = 0.03` | 0.03 | $0.0008 | $0.0004 |
| – | paragraph (400 chars) | any | – | – | no | 1 | TTS | `max(1, ceil(400 × 3/70)) / 100 = 0.18` | 0.18 | $0.0045 | $0.0027 |
| – | page (2,000 chars) | any | – | – | no | 1 | TTS | `max(1, ceil(2000 × 3/70)) / 100 = 0.86` | 0.86 | $0.0215 | $0.0129 |

**`voice_change_merge`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 8.5 s input | any | – | – | audio/video input | 1 | voice_change_merge | `ceil₀.₀₁(8.5 × 0.1) = 0.85` | 0.85 | $0.0212 | $0.0128 |
| – | 30 s input | any | – | – | audio/video input | 1 | voice_change_merge | `ceil₀.₀₁(30 × 0.1) = 3` | 3 | $0.0750 | $0.0450 |
| – | 90 s input | any | – | – | audio/video input | 1 | voice_change_merge | `ceil₀.₀₁(90 × 0.1) = 9` | 9 | $0.2250 | $0.1350 |

**`audio_dubbing`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 8.5 s input | any | – | – | audio/video input | 1 | audio_dubbing | `ceil(floor(8.5) × 3) = 24` | 24 | $0.6000 | $0.3600 |
| – | 30 s input | any | – | – | audio/video input | 1 | audio_dubbing | `ceil(floor(30) × 3) = 90` | 90 | $2.2500 | $1.3500 |
| – | 90 s input | any | – | – | audio/video input | 1 | audio_dubbing | `ceil(floor(90) × 3) = 270` | 270 | $6.7500 | $4.0500 |

**`dubbing_lipsync`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 8.5 s input | any | fps=25 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(8.5) × 3) = 24` | 24 | $0.6000 | $0.3600 |
| – | 30 s input | any | fps=25 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(30) × 3) = 90` | 90 | $2.2500 | $1.3500 |
| – | 90 s input | any | fps=25 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(90) × 3) = 270` | 270 | $6.7500 | $4.0500 |
| – | 8.5 s input | any | fps=30 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(8.5) × 3.6) = 29` | 29 | $0.7250 | $0.4350 |
| – | 30 s input | any | fps=30 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(30) × 3.6) = 108` | 108 | $2.7000 | $1.6200 |
| – | 90 s input | any | fps=30 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(90) × 3.6) = 324` | 324 | $8.1000 | $4.8600 |
| – | 8.5 s input | any | fps=60 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(8.5) × 6) = 48` | 48 | $1.2000 | $0.7200 |
| – | 30 s input | any | fps=60 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(30) × 6) = 180` | 180 | $4.5000 | $2.7000 |
| – | 90 s input | any | fps=60 | – | audio/video input | 1 | dubbing_lipsync | `ceil(floor(90) × 6) = 540` | 540 | $13.5000 | $8.1000 |

**`elevenlabs_video_to_music`** — formula: JS + live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 8.5 s input | any | model_id=music_v1 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(8.5/60) × 4 = 4` | 4 | $0.1000 | $0.0600 |
| – | 30 s input | any | model_id=music_v1 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(30/60) × 4 = 4` | 4 | $0.1000 | $0.0600 |
| – | 90 s input | any | model_id=music_v1 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(90/60) × 4 = 8` | 8 | $0.2000 | $0.1200 |
| – | 8.5 s input | any | model_id=music_v2 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(8.5/60) × 4 = 4` | 4 | $0.1000 | $0.0600 |
| – | 30 s input | any | model_id=music_v2 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(30/60) × 4 = 4` | 4 | $0.1000 | $0.0600 |
| – | 90 s input | any | model_id=music_v2 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(90/60) × 4 = 8` | 8 | $0.2000 | $0.1200 |
| – | 8.5 s input | any | model_id=music_v2_5 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(8.5/60) × 9 = 9` | 9 | $0.2250 | $0.1350 |
| – | 30 s input | any | model_id=music_v2_5 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(30/60) × 9 = 9` | 9 | $0.2250 | $0.1350 |
| – | 90 s input | any | model_id=music_v2_5 | – | audio/video input | 1 | elevenlabs_video_to_music | `ceil(90/60) × 9 = 18` | 18 | $0.4500 | $0.2700 |

#### Other job types

**`ad_multiplier`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`ad_multiplier_replace`** — formula: inferred: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |

**`ad_multiplier_v2`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`ai_host_video`** — formula: inferred: ceil_batch

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3.3) = 17` | 17 | $0.4250 | $0.2550 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3.3) = 33` | 33 | $0.8250 | $0.4950 |
| 480p | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 3.3) = 99` | 99 | $2.4750 | $1.4850 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7.7) = 39` | 39 | $0.9750 | $0.5850 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7.7) = 77` | 77 | $1.9250 | $1.1550 |
| 720p | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 7.7) = 231` | 231 | $5.7750 | $3.4650 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 17.6) = 88` | 88 | $2.2000 | $1.3200 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 17.6) = 176` | 176 | $4.4000 | $2.6400 |
| 1080p | 30 s | any | – | – | no | 1 | generate | `ceil(30 × 17.6) = 528` | 528 | $13.2000 | $7.9200 |

**`intone`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`marketing_studio_video`** — formula: JS: ceil_total

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 3.5) = 14` | 14 | $0.3500 | $0.2100 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3.5) = 35` | 35 | $0.8750 | $0.5250 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3.5) = 53` | 53 | $1.3250 | $0.7950 |
| 480p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 3.5 × 4) = 210` | 210 | $5.2500 | $3.1500 |
| 720p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 5) = 20` | 20 | $0.5000 | $0.3000 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 5) = 50` | 50 | $1.2500 | $0.7500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 5) = 75` | 75 | $1.8750 | $1.1250 |
| 720p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 5 × 4) = 300` | 300 | $7.5000 | $4.5000 |
| 1080p | 4 s | any | – | – | no | 1 | generate | `ceil(4 × 13) = 52` | 52 | $1.3000 | $0.7800 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 13) = 130` | 130 | $3.2500 | $1.9500 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 13) = 195` | 195 | $4.8750 | $2.9250 |
| 1080p | 15 s | any | – | – | no | 4 | generate | `ceil(15 × 13 × 4) = 780` | 780 | $19.5000 | $11.7000 |

**`scene_switch`** — formula: inferred (no JS)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 1080p | 5 s | any | tier=basic | – | no | 1 | generate | `5 × 4.03 + 8.87 per run = 29.02 (no JS; inferred)` | 29.02 | $0.7255 | $0.4353 |
| 1080p | 10 s | any | tier=basic | – | no | 1 | generate | `10 × 4.03 + 8.87 per run = 49.17 (no JS; inferred)` | 49.17 | $1.2292 | $0.7376 |
| 720p | 5 s | any | tier=pro | – | no | 1 | generate | `5 × 9.28 + 12.46 per run = 58.86 (no JS; inferred)` | 58.86 | $1.4715 | $0.8829 |
| 720p | 10 s | any | tier=pro | – | no | 1 | generate | `10 × 9.28 + 12.46 per run = 105.26 (no JS; inferred)` | 105.26 | $2.6315 | $1.5789 |
| 1080p | 5 s | any | tier=pro | – | no | 1 | generate | `5 × 22.53 + 12.46 per run = 125.11 (no JS; inferred)` | 125.11 | $3.1278 | $1.8766 |
| 1080p | 10 s | any | tier=pro | – | no | 1 | generate | `10 × 22.53 + 12.46 per run = 237.76 (no JS; inferred)` | 237.76 | $5.9440 | $3.5664 |
| 4k | 5 s | any | tier=pro | – | no | 1 | generate | `5 × 37.58 + 12.46 per run = 200.36 (no JS; inferred)` | 200.36 | $5.0090 | $3.0054 |
| 4k | 10 s | any | tier=pro | – | no | 1 | generate | `10 × 37.58 + 12.46 per run = 388.26 (no JS; inferred)` | 388.26 | $9.7065 | $5.8239 |

**`video_character_asset`** — formula: inferred: Seedance-style ceil(d × cps)

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| 480p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 480p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 3) = 15` | 15 | $0.3750 | $0.2250 |
| 480p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 3) = 30` | 30 | $0.7500 | $0.4500 |
| 480p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 3) = 45` | 45 | $1.1250 | $0.6750 |
| 720p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 720p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 7) = 35` | 35 | $0.8750 | $0.5250 |
| 720p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 7) = 70` | 70 | $1.7500 | $1.0500 |
| 720p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 7) = 105` | 105 | $2.6250 | $1.5750 |
| 1080p | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 1080p | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 16) = 80` | 80 | $2.0000 | $1.2000 |
| 1080p | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 16) = 160` | 160 | $4.0000 | $2.4000 |
| 1080p | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 16) = 240` | 240 | $6.0000 | $3.6000 |
| 4k | 5 s | any | – | – | no | 1 | generate | `ceil(5 × 28) = 140` | 140 | $3.5000 | $2.1000 |
| 4k | 10 s | any | – | – | no | 1 | generate | `ceil(10 × 28) = 280` | 280 | $7.0000 | $4.2000 |
| 4k | 15 s | any | – | – | no | 1 | generate | `ceil(15 × 28) = 420` | 420 | $10.5000 | $6.3000 |
| 4k | 5 s | any | – | – | yes | 1 | generate | `ceil(5 × 34) = 170` | 170 | $4.2500 | $2.5500 |
| 4k | 10 s | any | – | – | yes | 1 | generate | `ceil(10 × 34) = 340` | 340 | $8.5000 | $5.1000 |
| 4k | 15 s | any | – | – | yes | 1 | generate | `ceil(15 × 34) = 510` | 510 | $12.7500 | $7.6500 |

**`youtube_faceless_video`** — formula: live formula

| resolution | duration | aspect | quality/mode | audio | ref video | batch | edit/extend/draft | equation | credits | ≈USD plus:annual | ≈USD ultra:annual |
|---|---|---|---|---|---|---:|---|---|---:|---:|---:|
| – | 30 s | any | animation_mode=fully_animated | – | no | 1 | generate | `ceil(30/10) × 41 = 123` | 123 | $3.0750 | $1.8450 |
| – | 60 s | any | animation_mode=fully_animated | – | no | 1 | generate | `ceil(60/10) × 41 = 246` | 246 | $6.1500 | $3.6900 |
| – | 95 s | any | animation_mode=fully_animated | – | no | 1 | generate | `ceil(95/10) × 41 = 410` | 410 | $10.2500 | $6.1500 |
| – | 30 s | any | animation_mode=scene_based | – | no | 1 | generate | `ceil(30/10) × 16 = 48` | 48 | $1.2000 | $0.7200 |
| – | 60 s | any | animation_mode=scene_based | – | no | 1 | generate | `ceil(60/10) × 16 = 96` | 96 | $2.4000 | $1.4400 |
| – | 95 s | any | animation_mode=scene_based | – | no | 1 | generate | `ceil(95/10) × 16 = 160` | 160 | $4.0000 | $2.4000 |

<!-- END cost-variations -->
