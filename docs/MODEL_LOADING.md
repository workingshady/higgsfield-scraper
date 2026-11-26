# How Higgsfield loads and calls its AI models

How the Higgsfield web app (higgsfield.ai) decides which models a tool shows, which options each model has, what it
costs, and how a generation is uploaded, submitted, polled and returned. Covers the video generator (Seedance 2.5 in
depth), image models, apps, viral-hub effects, motions, mixed media, lipsync/speak, upscale, Cinema Studio and MCP.

**Date:** 2026-11-26. **Builds studied:** `548e0f3a` (current, commit `7b1a78f4…`, buildId
`45776133266-1-production`, saved to `samples/higgsfield/js2/`, 580 chunks) and `8a801a77` (2026-11-25,
`samples/higgsfield/js/`). Both folders are gitignored. Chunk names below are from `548e0f3a` unless marked *(old)*.

**Method:** static analysis of the public JS, plus GET-only probing at about 1 request/s with no login. No POST,
PUT, PATCH or DELETE was sent, no upload or generation was started, and no bot protection was bypassed. Endpoints
marked **(from JS, not called)** are known only from the bundle.

> Related: [`REVERSE_ENGINEERING.md`](REVERSE_ENGINEERING.md) (pricing endpoints, Clerk login),
> [`ENDPOINTS.md`](ENDPOINTS.md) (`/job-sets/costs` fields), [`HIGGSFIELD_DATA_INVENTORY.md`](HIGGSFIELD_DATA_INVENTORY.md)
> (all routes and API paths), [`scrapers/catalog.md`](scrapers/catalog.md) (motions, viral presets),
> [`scrapers/site.md`](scrapers/site.md) (app templates with credit costs).

---

## 1. TL;DR

```
 page HTML (TanStack Start SSR)
   │  window.__HF_FF = {flags:{f_24c5dcf4:true,…}}        ← feature flags, evaluated server-side, public
   ▼
 MODEL REGISTRY  (hard-coded in JS, per tool)
   • menu tree: id, title, badges, tags, availablePlans   (video-model menu, video-featured-model-ids)
   • gating:  flag → hidden | "coming soon";  pricedAs → must exist in /job-sets/costs;  hidden-set;  plan → upsell
   • modelVersion id (UI) ──map──► job_set_type (API)    e.g. seedance_2_5_edit → seedance_2_5 + model:"video_edit"
   ▼
 PARAMS SCHEMA  (hard-coded: defineJob({type, input:[prompt, media roles, settings schema], validate,
                 toProvider, fromProvider, credits?}) — ~100 job types, one shared "FNF SDK")
   ▼
 COST  = live GET /job-sets/costs (public) × formula in JS        e.g. ceil(duration × cost_per_second) × batch_size
   ▼
 UPLOAD  POST /media/batch | /video | /audio → PUT presigned URL → POST /{media|video|audio}/{id}/upload
   ▼
 CREATE  POST /jobs/{route}  e.g. /jobs/v2/seedance_2_5   body {params:{…}, use_unlim, …}    (Clerk Bearer JWT)
         special routes: /chains/viral-hub, /chains/mixed-media, /chains/reframe, /workflows (apps), …
   ▼
 POLL    POST /jobs/status-batch {ids:[…]} → GET /jobs/{id} | /job-sets/{id}   (polling, no websocket)
   ▼
 RESULT  job.results.raw/min {url, thumbnail_url}  → CloudFront / cdn.higgsfield.ai
```

The model list and every option schema are compiled into the JS bundle. The server controls four things without
a deploy: feature flags (`__HF_FF`), prices and model availability (`/job-sets/costs`), promotions and unlimited
windows (`/datetime-settings`, `/workspaces/settings`), and CMS-driven catalogs (viral presets, motions, apps, notices).
A model the bundle has no code for never shows up in the UI, even when `/job-sets/costs` already prices it. On
2026-11-26 `scene_switch` appeared in `/job-sets/costs` but in no JS chunk.

---

## 2. Where the model list comes from

### 2.1 It is hard-coded, then filtered at runtime

There is **no public "models" endpoint**. The tools build their pickers from constants in the bundle, then filter
them with live data.

**(a) Menu tree, display names and featured order.** `548e0f3a-VcyAEjmNb78tihFH.js`:

```js
// named module "video-featured-model-ids-VYfdslD1"
t = ["seedance_2_5","seedance_2_5_flash","seedance_2_5_draft","magi_2","hf-mult-motion-control",
     "kling4_0","kling_4_0_flash","gemini-omni-flash-1-2","wan4_0","wan3_0_prime","seedance_2_5_edit",
     "seedance_2_5_flash_edit","gemini_omni_flash_1_2_edit","seedance_2_0","seedance_2_0_fast",
     "seedance_2_0_mini","minimax_h3","minimax_h3_max","minimax_h3_highspeed","minimax_h3_lite",
     "flux_3_video","grok_video_v15_lite","grok_video_v15"]

ie = {id:"seedance_2_5", title:"Seedance 2.5"}, fe = {id:"seedance_2_5_flash", title:"Seedance 2.5 Flash"},
ae = {id:"seedance_2_5_draft", …}, ce = {id:"seedance_2_5_edit", …}, le = {id:"seedance_2_5_extend", …}
he = [ie, fe, ae, ce, pe]        // the Seedance 2.5 family group in the picker
```

The same chunk holds about 70 video entries (Kling 2.5 to 4.0, Veo 3/3.1, Sora 2, Wan 2.2 to 4.0, MiniMax, Grok
Imagine, Gemini Omni, HappyHorse, MAGI-2, Higgsfield Lite/Standard/Turbo…). The lipsync picker
(`548e0f3a-2KSneU3QfSjJ6MRp.js`) uses richer entries:

```js
{ id:"speak-wan-2.5-fast", badges:["Premium"], title:"Wan 2.5 Speak Fast", short_title:"Wan 2.5 Fast",
  availablePlans: plans["speak-wan-2.5"], tags:[tag["720p-1080p"], tag.Audio, tag["10s"]],
  footer:{ children:<CmsJobSetNoticeBadge jobSetType=…/>, isVisibleOnSelect:true } }
```

**(b) Gating table: flag, fallback, price check.** `548e0f3a-tCLaulKUdGQfxqgZ.js` (`8a801a77-0OtXTwNP7z5O3DfS.js`
in the old build):

```js
zx = "seedance_2_5"                     // default video model (also the redirect target for retired ids)
Vx = new Set(["veo3","sora-2","sora2_video","seedance_1_5", …])   // retired → hidden, URLs redirected
Hx = {
  kling_4_0_flash:           { flag: f_3a0922bf, fallback: "kling4_0" },
  seedance_2_5_flash:        { flag: f_24c5dcf4, fallback: "seedance_2_5",
                               pricedAs: "seedance_2_5_flash", cobaltComingSoon: true },
  seedance_2_5_flash_edit:   { flag: f_24c5dcf4, fallback: "seedance_2_5_edit",   pricedAs: "seedance_2_5_flash", … },
  seedance_2_5_flash_extend: { flag: f_24c5dcf4, fallback: "seedance_2_5_extend", pricedAs: "seedance_2_5_flash", … },
  wan4_0:                    { flag: f_6a87092e, fallback: "wan3_0" },
}
function status(id, flags, costs, cobalt) {             // de-minified Ix()
  if (!flagOn(id, flags)) return "hidden";               // flag missing or false
  if (cobalt && Hx[id]?.cobaltComingSoon) return "coming-soon";
  return pricedAs(id, costs) ? "available" : "hidden";   // costs.some(c => c.job_set_type === Hx[id].pricedAs)
}
// a hidden model's saved selection falls back to Hx[id].fallback
```

Flag names are hashed. The constants live in `548e0f3a-aXyXjC_KHBp09DNW.js`. On 2026-11-26 the anonymous values
were `f_24c5dcf4: true` (Seedance 2.5 Flash shown), `f_3a0922bf: true` (Kling 4.0 Flash shown) and
`f_6a87092e: false` (Wan 4.0 hidden). Wan 4.0 is also missing from `/job-sets/costs`.

**(c) Plan gating.** `548e0f3a-CIDvui7vUuNoedmf.js`, module `video-model-plans-lVGgpFL9`. A model a plan can't
use is still listed; it opens an upsell instead of being hidden:

```js
ALL     = ["free","basic","pro","lite","standby","ultimate","creator","starter","plus","ultra","max","secret"]
PAID    = ALL minus "free"
PREMIUM = ["pro","ultimate","creator","plus","ultra","max"]
plans = { seedance_2_5: PREMIUM, seedance_2_5_flash: PREMIUM, seedance_2_0_fast: PAID, kling3_0: PAID,
          kling4_0: PAID, magi_2: PAID, minimax_h3: ALL, wan3_0: PAID, cinematic_studio_video_4_0: PREMIUM, … }
// legacy basic/starter users with planVersion <= 30 keep veo-3-1-lite, seedance_2_0 and private-ui
```

**(d) "Unlimited" badges.** These come from `GET /workspaces/settings` (login only), which returns
`unlimited_settings[]` with `{job_set_type, models[], start_date, end_date, team_end_date, status}`, re-polled
around grant transitions. They also come from static marketplace bundles, such as `jobSetTypes:
["nano_banana_pro_unlimited","gpt_image_2_unlimited","kling_3_unlimited","seedance_2_5", …]` in
`548e0f3a-2B_Cs0zHIGw5q2ts.js`, and from public promo windows in `/datetime-settings` (e.g.
`freegens_seedance_2_5_1080p`).

### 2.2 UI ids and API ids are different

The picker works with **model-version ids**. The API works with **`job_set_type`**. Mapping tables, such as
`job-set-type-to-model-version-hocm4GAv` and `mapModelToPresetFamily`:

| UI model-version id | `job_set_type` sent | extra param |
|---|---|---|
| `seedance_2_5` / `seedance_2_5_draft` | `seedance_2_5` | `model:"default"` (+ `draft:true`) |
| `seedance_2_5_edit` | `seedance_2_5` | `model:"video_edit"` |
| `seedance_2_5_extend` | `seedance_2_5` | `model:"video_extension"`, `extension_mode:"forward"\|"backward"` |
| `seedance_2_5_flash(_edit/_extend)` | `seedance_2_5_flash` | same as above |
| `hf-mult-motion-control` / `genjutsu-flash` | `hf_mult_motion_control` / `…_flash` | |
| `gemini-omni-flash-1-2` | `gemini_omni_flash_1_2` | |
| `cinematic_studio_video_4_0` | `cinematic_studio_video_4_0` | |
| `lite` / `standard` / `turbo` (Higgsfield DoP) | `image2video` | `model:"lite"\|"standard"\|"turbo"` |

The tool page picks a **mode** from the path, in `tCLaulKUdGQfxqgZ` (`Qm()` in the old build): `/ai/video` →
`video`, `/ai/video/edit` → `video-edit`, `/ai/video/motion` → `motion-control`, `/ai/video/reframe` → `reframe`,
`/ai/video/agent` → `agent`. The model comes from `?model=`. A retired id (the `Vx` set) is rewritten to
`?model=seedance_2_5`.

### 2.3 Per-model preset (motion) config

The same chunk maps each model version to its preset family and default preset:

```js
seedance_2_0: { generalPresetId: "…", categoryIcon, categoryName:{id:"RSUgyJ"}, presets: [...] },
seedance_2_5: { generalPresetId: "seedance_2_5_general", presets: [{id:"seedance_2_5_general", name:"General", preview:{…}}] },
wan3_0:       { …, presets: kx, mergeDynamicPresets: false },   // false = don't merge /motions results
mapModelToPresetFamily = { seedance_2_5:"seedance_2_5", kling3_0:"kling3_0", "kling-v2-5-turbo":"kling",
                           wan2_5_video:"wan2_5_video", lite:"higgsfield", … }
```

Dynamic presets come from `GET /motions?preset_family=higgsfield` (public) and the per-family lists
`/kling-motions`, `/kling2-6-motions`, `/seedance-motions`, `/wan2-2-motions`, `/wan2-5-motions`, `/minimax-motions`
and `/veo3-styles` (login only). The `catalog` scraper already collects these; the public `/motions` list also
contains every family.

---

## 3. Per-model parameter schema: the `defineJob` registry

Every generatable job type is declared once with a small schema DSL. The framework is in
`548e0f3a-IbXroQBX75V1ZnAd.js` and its error text names it: *"defineJob('…'): semantic mediaSchema requires both
toProvider and fromProvider"*. About 100 types are in `548e0f3a-Kxdpq5YjqY_JH5zf.js`, `seedance_2_5` is in
`548e0f3a-G6o1S1hf1S6r2WZX.js`, and the shared limits and cost helpers are in `548e0f3a-fmaPQSnk2K7UZee5.js`.
The same definitions back the video page, the image page, Canvas (`canvas-worker.higgsfield.ai`) and the "recreate
from a community post" feature (`fromProvider` turns stored `params` back into form state).

```js
defineJob({
  type: "seedance_2_5",                 // = job_set_type
  output: "video",
  business: { useUnlim:false, useFreeGens:false, useGenerationSeconds:false },
  input: [
    prompt({ policy:{ required:true, minLength:1, maxLength:60000 } }),
    media({ roles:["image","start_image","end_image","video","audio"] }),   // "wrapped" wire format
    settingsSchema,                     // see 4.1
  ],
  validate:     (e) => validateSeedance(e, LIMITS.seedance_2_5),
  toProvider:   semanticToWireParams,   // → the JSON "params" object
  fromProvider: (wire) => wireToSemantic(wire, LIMITS.seedance_2_5),
  credits?:     ({settings, media}) => number | null,   // present on many types (see 5)
})
```

The registry covers `kling3_0`, `kling4_0`, `kling_4_0_flash`, `kling_o3_*`, `kling2_6(_motion_control)`,
`seedance_2_0(_mini)`, `seedance_2_5(_flash)`, the `seedance_*unlimited` types, `wan2_2/2_5/2_6/2_7/3_0(_prime)`,
`minimax_h3*`, `grok_video*`, `gemini_omni*`, `magi_2`, `veo3`, `veo3_1(_lite)`, `sora2_video`, `happy_horse_video`,
`flux_2`, `flux_3_image/video`, `gpt_image_2*`, `nano_banana*`, `seedream*`, `ideogram_4_*`, `recraft_v4_*`,
`text2image_soul(_v2)`, `soul_cinematic`, `image2video(_mix)`, `topaz_image/video`, `bytedance_video_upscale`,
`video_background_remover`, `reframe`, `viral_hub_video`, `cinematic_studio_*`, `videoshop_*`, `hf_mult_*`,
`what_if_v1`, `z_image`, `music_cards_v1`, and more.

---

## 4. Seedance 2.5 deep dive

### 4.1 Options and allowed values

Sources: `G6o1S1hf1S6r2WZX.js` (schema, validate, wire format), `fmaPQSnk2K7UZee5.js` (limits, resolution table),
`tCLaulKUdGQfxqgZ.js` (UI presets).

| Setting (UI) | Wire key | Allowed | Default | Notes |
|---|---|---|---|---|
| prompt | `prompt` | 1–60 000 chars | — | Required. `<<<image_1>>>`-style element references count toward the image limit |
| duration | `duration` | integer 4–30 s | 5 (UI quick picks `[4,10,15,20,30]`) | Not sent for `video_edit` (the length comes from the source video) |
| resolution | `resolution` | `480p` `720p` `1080p` `4k` | `720p` | Flash: `480p` `720p` only |
| aspect ratio | `aspect_ratio` | `21:9` `16:9` `4:3` `1:1` `3:4` `9:16` | `16:9` | Only sent when `model:"default"` |
| — | `width`,`height` | derived from resolution × aspect | — | e.g. 1080p 16:9 → 1920×1080; 4k 9:16 → 2160×3840; 480p 21:9 → 896×384 |
| audio | `generate_audio` | bool | `true` | |
| bitrate | `bitrate_mode` | `standard` `high` | `high` | |
| batch | `batch_size` | 1–4 | 1 | Multiplies the cost |
| mode | `model` | `default` `video_edit` `video_extension` | `default` | `video_edit` needs exactly 1 video; `video_extension` needs at least 1 video plus `extension_mode` |
| extension | `extension_mode` | `forward` `backward` | — | Extend mode only |
| seed | `seed` | 0–2 147 483 647 | random | Optional |
| draft | `draft` | bool | `false` | The "Seedance 2.5 Draft" picker entry: a cheap low-res preview |
| upscale a draft | `draft_job_id`, `draft_upscale_model` | job id; `seedance_2_5` \| `kling4_0` | — | Can't be combined with `draft:true` |
| inputs | `medias[]` | roles `image` `start_image` `end_image` `video` `audio` | `[]` | `[{role, data:{id, type:"media_input", url}}]` |
| billing | `use_unlim`, `use_free_gens`, `use_generation_seconds` | bool | false | See 4.3 |

**Media limits** (`validate`):

| | Seedance 2.5 | Seedance 2.5 Flash |
|---|---|---|
| images (incl. start/end and element references) | 30 | 10 |
| videos | 10 | 5 |
| audios | 10 | 5 |
| total inputs | 50 | 20 |
| total reference-video seconds | 30 | unlimited |

Each reference video or audio must be 2–30 s, and the total audio is capped at 30 s. Error codes look like
`seedance-2-5-image-limit` or `seedance-2-5-video-duration-budget`.

**Text-to-video vs image-to-video.** Both use the same job type and endpoint. Text-to-video sends `medias: []`.
Image-to-video adds `role:"image"` (a reference, free placement) or `start_image`/`end_image` (first/last frame).
Adding a `video` reference switches the price to the `with_video` row, unless a start or end frame is present.

### 4.2 Cost formula

The UI reads the live table from `GET /job-sets/costs` (public, cached per workspace) and computes the price in
`fmaPQSnk2K7UZee5.js` (`Xw` in the old canvas chunk):

```js
function seedanceCredits(rows, {resolution, duration, batchSize, edit, hasVideoInput, original}) {
  const pick = edit
    ? r => r.video_edit?.[original ? "original_cost_per_second" : "cost_per_second"]
    : r => r.video?.[hasVideoInput ? "with_video" : "without_video"]?.[original ? "original_cost_per_second" : "cost_per_second"];
  const perSec = pick(rows.find(r => r.resolution === resolution && pick(r) != null));
  return perSec == null ? null : Math.ceil(duration * perSec) * Math.max(1, batchSize);
}
// hasVideoInput = medias has role "video" AND no start_image/end_image
// edit: duration = the source video's length
// "original_*" is the strike-through price shown during discounts
```

Live table for `seedance_2_5` on 2026-11-26, in credits per second:

| resolution | without video | with video | video edit |
|---|---:|---:|---:|
| 480p | 3 | 3 | 3.5 |
| 720p | 7 | 7 | 7.5 |
| 1080p | 16 | 16 | 20 |
| 4k | 28 | 34 | 34 |

`seedance_2_5_flash`: 480p 2 / 2.5 / 2.5; 720p 5 / 6 / 6.

Worked examples:

| request | math | credits |
|---|---|---:|
| 1080p, 5 s, text only | ceil(5 × 16) × 1 | **80** |
| 1080p, 15 s, one reference image (the community example below) | ceil(15 × 16) | **240** |
| 4k, 10 s, text only | ceil(10 × 28) | **280** |
| 4k, 10 s, with a reference video | ceil(10 × 34) | **340** |
| 720p, 15 s, batch 2 | ceil(15 × 7) × 2 | **210** |
| edit an 8 s clip at 1080p | ceil(8 × 20) | **160** |
| Flash 720p, 10 s, text only | ceil(10 × 5) | **50** |

The bundle also ships a **static fallback table** that is already stale (`seedance_2_5` 4k = 27/26 per second, the
live value is 34/28). It is used before the costs query resolves. The live endpoint wins. The SDK's own
`estimateCost()` in the adapter (`548e0f3a-j8lj58UEh2bbmHmn.js`) has special formulas for `seedance_2_0`
(per-`model` rows, `trunc(duration × cps × 100) × batch`), `kling3_0` (`duration × audio[sound]` per `mode`),
`wan3_0`/`wan4_0` (same as Seedance) and `magi_2`. For `topaz_*` it asks the server with
`POST /jobs/{route}?dry_run=true` **(from JS, not called)**.

### 4.3 Request (from JS, not called)

`POST https://fnf-api-gw.higgsfield.ai/fnf/jobs/v2/seedance_2_5`. The route comes from the adapter's route table:
`seedance_2_5: "v2/seedance_2_5"`. Types not in that table use `/jobs/<type with _ replaced by ->`, e.g.
`/jobs/topaz-video`.

```http
POST /fnf/jobs/v2/seedance_2_5
Authorization: Bearer <Clerk session JWT>
hf-workspace-id: <workspace uuid>          (when a team workspace is active)
Accept-Language: en
Content-Type: application/json
```

```json
{
  "params": {
    "prompt": "<<<image_1>>> walks through a neon market, handheld, rain",
    "width": 1920,
    "height": 1080,
    "medias": [
      { "role": "image", "data": { "id": "<media-uuid>", "type": "media_input", "url": "https://<cdn>/<user>/<media-uuid>.png" } }
    ],
    "resolution": "1080p",
    "generate_audio": true,
    "bitrate_mode": "high",
    "batch_size": 1,
    "model": "default",
    "duration": 15,
    "aspect_ratio": "16:9",
    "use_unlim": false,
    "seed": 123456
  },
  "use_unlim": false,
  "use_free_gens": true,
  "use_generation_seconds": true,
  "use_free_daily_credits": true,
  "client_meta": { "...": "surface/analytics info" },
  "is_first_gen": false,
  "parent_id": "<job-set id when re-running>",
  "remix_source": { "publication_id": "<id>", "job_id": "<id>" }
}
```

Fields after `"use_unlim": false` are optional and only sent when relevant. `remix_source` is added by the
"community remix" extension when the generation started from a community post.

- Edit mode: `"model": "video_edit"` with exactly one `{role:"video"}` and no `duration` or `aspect_ratio`.
- Extend mode: `"model": "video_extension", "duration": 10, "extension_mode": "forward"` plus a video.
- Draft: add `"draft": true`. Upscaling a draft sends `"draft_job_id"` and `"draft_upscale_model": "seedance_2_5"`.

The adapter moves the billing flags out of `params` for most types (`use_free_gens` and `use_generation_seconds`
are stripped from params; `use_unlim` is kept in params for `seedance_2_5` and also sent at the top level). Before
sending, guard extensions check plan access, the unlimited grant, free-gen eligibility, IP and consent dialogs.
Guests run `POST /jobs/v2/{type}/dry-run` **(from JS, not called)** to learn whether a model is
`available_to_guests`.

**Response:** `{ "job_sets": [ { "id", "type", "params", "parent_id", "created_at", "jobs": [ { "id", "status",
"results", "ip_check_finished", "cost", "meta": {"fail_reason"} } ] } ] }`. The adapter normalizes each job to
`{id, job_set_type, job_set_id, job_set_parent_id, status, result_url, min_result_url, thumbnail_url, params,
created_at, fail_reason, ip_check_finished, cost}`.

### 4.4 Status and result

| status | meaning |
|---|---|
| `waiting` | the client treats it as `queued` |
| `queued`, `in_progress` (the UI also uses `processing`) | running |
| `ip_detect` | `completed` but `ip_check_finished:false` (result held for an IP/likeness check) |
| `completed` | done |
| `failed`, `nsfw`, `ip_detected`, `canceled` | terminal; `meta.fail_reason` explains |
| `dna`, `script`, `visuals`, `vision`, `flow` | stage values used by agent/multi-step products |

Polling, not push: `POST /jobs/status-batch` with `{"ids":[…]}`, or `{"jobs":[{"id","realm"}]}` for shared folders.
Ids go in batches of 100 with a 15 s timeout. The response is `{items:[{id,status,ip_check_finished,…}], missing:[]}`.
For jobs whose status changed, the client fetches `GET /jobs/{id}` (optionally `?cluster=true&folder_id=…`) or
`GET /job-sets/{id}`, then refreshes the feed (`GET /jobs?job_set_type=…&status=…&cursor=…&size=…`,
`/jobs/accessible`). The batch poller I could pin down runs on a 3 s `setInterval`. Neither build contains a
WebSocket, Centrifugo or Pusher client for generations; the only `text/event-stream` code is an EventSource
polyfill used elsewhere. Cancel is `PUT /jobs/{id}/cancel` **(from JS, not called)**.

Result media, as stored on a public community item (user id redacted):

```json
"results": [
  { "name": "raw", "type": "video",
    "url": "https://d8j0ntlcm91z4.cloudfront.net/user_<redacted>/hf_20260814_041459_<uuid>_wm3.mp4",
    "thumbnail_url": "https://cdn.higgsfield.ai/user_<redacted>/hf_20260814_041459_<uuid>_thumbnail.webp" },
  { "name": "min", "type": "video", "url": "…same…", "thumbnail_url": "…" }
]
```

Inputs live on `d2ol7oe51mr4n9.cloudfront.net/<user>/<media-id>.<ext>`.

### 4.5 A real `seedance_2_5` params object

This comes from `/publications/community/*`, captured with
`scrape community --models seedance_2_5 --with-raw-params`. The prompt is cut and the user id redacted.

```json
{
  "width": 1920, "height": 1080,
  "prompt": "<<<image_1>>> — Ines\n\nCamera Settings: shot on 35mm film, anamorphic 2x squeeze, 2.39:1, o...",
  "genre": "auto",
  "medias": [ { "role": "image", "data": { "id": "727d971e-…", "type": "media_input",
                "url": "https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/727d971e-….png" } } ],
  "duration": 15, "resolution": "1080p", "aspect_ratio": "16:9", "generate_audio": true,
  "multi_shots": false, "multi_shot_mode": "custom", "multi_prompt": [], "speedramp": "auto",
  "reference_elements": [], "prompt_language": "zh", "model": "default", "extension_mode": null,
  "bitrate_mode": "high", "draft": false, "seed": null, "draft_job_id": null
}
```

It matches the wire format above. The stored copy also carries keys the web client does not send for this type:
`genre`, `speedramp`, `multi_shots`, `multi_shot_mode`, `multi_prompt`, `reference_elements` and
`prompt_language`. These are backend defaults or come from Cinema Studio and API clients (inferred). In 11 sampled
posts, 9 had `prompt_language:"zh"`, all were `1080p`, durations were 9–30 s, and every one had
`generate_audio:true`.

---

## 5. How the tools differ

### 5.1 Summary table

| Tool | Route(s) | Model(s) / `job_set_type` | Create endpoint (from JS, not called) | What differs |
|---|---|---|---|---|
| Video generator | `/ai/video?model=…`, `/create/video`, `/mobile/video/{model}` | ~70 entries; default `seedance_2_5` | `POST /jobs/v2/{type}` for modern models, `/jobs/{kebab-type}` for older ones | Full option set per `defineJob`; cost from `/job-sets/costs` |
| Video edit / extend | `/ai/video/edit` | `seedance_2_5(_flash)` with `model:"video_edit"`, `kling4_0`, `kling_o3_*`, `gemini_omni_flash_*_edit`, `grok_video_edit` | same | One source video; cost uses the `video_edit` row × source length |
| Motion control | `/ai/video/motion`, `/motion/{id}` | `kling3_0_motion_control`, `kling2_6_motion_control`, `hf_mult_motion_control(_flash)` (Genjutsu), `ai_influencer_motion_control*` | `/jobs/v2/kling3_0_motion_control`, or `/chains/motion-control` (`isChain`, `model_name: kling-v3\|kling-v2-6`) | A driving video plus a character image; `mode`, `background_source` |
| Camera motions / presets (DoP) | `/ai/video` with Higgsfield Lite/Standard/Turbo | `image2video`, `image2video_mix` | `/jobs/image2video`, `/jobs/image2video-mix` | `motion_id` from `/motions?preset_family=higgsfield` (or a `.safetensors` reference), `strength`, `frames` 49/81, `steps`, `seed`; client formula: lite = 3 (49 frames) / 5 (81); standard = ceil((24·s+200)/100) / ceil((35·s+300)/100); turbo = ceil((7·s+280)/100) / ceil((10·s+400)/100), s = steps |
| Reframe | `/ai/video/reframe` | `reframe` | `/chains/reframe`, or `/chains/reframe/batch` when duration > 15.25 s | Chain job |
| Image generator | `/ai/image?model=…`, `/image/` | `gpt_image_2*`, `nano_banana*`, `seedream_*`, `flux_*`, `ideogram_*`, `recraft_*`, `grok_image*`, `kling_image_4_0`, `z_image`, `image_auto` | `/jobs/v2/{type}` (most), `/jobs/nano-banana-2`, `/jobs/seedream-v4-5`, … | `resolution` 1k/2k/4k, `aspect_ratio`, `input_images[]` or `medias[]`, `batch_size` |
| Soul (image) | `/soul`, `/soul/{styleId}`, `/ai/image?model=soul` | `text2image_soul_v2`, `soul_cinematic`, `text2image_soul` | `/jobs/v2/text2image_soul_v2`, `/jobs/v2/soul_cinematic` | `style_id` + `style_strength` (styles from `/soul-styles`, login), `quality` 720p/1080p, `seed`, `custom_reference`, internal flags (`use_green`, `use_refiner`); `credits = batchSize × 0.125` in the def (unit unclear) |
| Apps | `/apps`, `/apps/{slug}` | Per-app job types (`HEADSHOT`, `OUTPAINT`, `KEYFRAMES_FACESWAP`, `CHARACTER_SWAP_V2`, `NANO_BANANA_ANIMAL`, `STICKER_MATCHCUT`, `BEAT_FIT`, `AI_STYLIST`, …; table `app-slug-type-jobsets`) | `POST /workflows` `{width, height, params:[{id,value}], application_slug, application_template_slug}`; some apps use their own job (`/jobs/face-swap`, `/jobs/nano-banana-2-ai-stylist`, `/chains/beat-fit-nano-banana`, …) | Fixed template: page loader `appPreset.{image,video,animate}Template = {slug, inputs[{id,type,properties}], cost}`. The **credit cost is static in the template**, not computed |
| Viral hub / effects | `/viral-effects`, `/effects`, `/effects/use/{slug}` | `viral_hub_video` (preset = a node graph) | `POST /chains/viral-hub` `{params:{preset_id, medias, …}, use_free_gens}` | Presets from `/viral-hub/presets/all` (public): `inputs[]` bound to graph nodes, `param_choices` per node, `price_matrix[{key, credit_units}]`. **credits = ceil(credit_units / 100)**. E.g. `floating-fall`: default 8400 → 84 cr, 16:9 1080p 14400 → 144 cr |
| Mixed media | `/mixed-media`, `/mixed-media-presets/preset/{id}` | chain (stored as preset samples) | `POST /chains/mixed-media`, `/chains/mixed-media-preview`; config `GET /mixed-media/configs?preset_id=` (401) | Video input: mp4/mov, ≤ 10 s, ≤ 50 MB, ratio 1/3–3 |
| Lipsync / Speak | `/lipsync-studio`, `/speak`, `/kling-lipsync` | `wan2_5_speak` (`speak-wan-2.5(-fast)`), `kling-speak`, `kling2_6_lipsync`, `kling-lipsync`, `sync-so`, `infinite-talk`, `hf_speak_v2`, `veo3-speak`, `veo3-1-speak` | `/jobs/wan2-5-speak`, `/jobs/kling-speak`, `/jobs/kling2-6-lipsync`, `/jobs/sync-so`, `/jobs/infinite-talk`, `/jobs/veo3-speak` … | Image or video plus an audio upload (`POST /audio` wav/mp3/webm) or TTS voice; picker tags e.g. `720p-1080p · Audio · 10s` |
| Audio / TTS / dubbing | `/audio` | `elevenlabs_v4(_turbo)`, `text2speech_v2`, `qwen_audio_tts`, `seed_audio`, `voice_change_merge`, `dubbing_lipsync` | `/jobs/v2/{type}`; `/chains/dubbing`, `/chains/voice-change` | Separate audio runtime (`createAudioFnfSubmit`) |
| Upscale | `/upscale`, `/ai-video-upscaler` | image: `topaz_image`, `topaz_image_generative`, `nano_banana_2_upscale`; video: `topaz_video`, `bytedance_video_upscale`, `flux_video_upscale`, `seedance_2_5_kling_upscale` ("Higgsfield Enhance", 4 cr/s at 1080p) | `/jobs/topaz-image`, `/jobs/topaz-video`, `/jobs/v2/bytedance_video_upscale`, `/jobs/nano-banana-2-upscale` | `output_width/height`, Topaz `model` + enhancement (`focus_fix_level`, denoise/blur/grain), `frame_interpolation {model:"apo-8", fps 15–240, slowmo 1–16}`; Topaz price is a server quote (`?dry_run=true`) |
| Cinema Studio | `/cinema-studio`, `/cinematic-video-generator` (landing) | `cinematic_studio_video_4_0` (also `_3_5`, `_v2`, `cinematic_studio_3_0`, `_image`, `_soul_cast`, `_soul_location`) | `/jobs/v2/cinematic_studio_video_4_0`, … | Seedance-like schema plus CMS ids `genre_id`, `era_id`, `pacing_id`, `light_id`/`light`/`light_custom[]`, `camera_model_id`, `camera_lens_id`, `camera_aperture_id`, `color_palette`, `prompt_language` en/zh; batch 1–4; 30 images / 10 videos / 10 audios; priced from the `cinematic_studio_video_4_0` costs row |
| AI Influencer | `/ai-influencer`, `/ai-influencer-studio` | `ai_influencer` (image), `ai_influencer_motion_control(_flash)`, `ai_influencer_replace_object(_flash)`, `ai_influencer_restyle` | `/jobs/v2/{type}`; restyle → `/jobs/v2/restyle` | `config {age, gender, ethnicity_origin_base, hair, eye_color, skin_color, …}`; restyle presets `GET /restyle/presets` (401) |
| Canvas / Flow | `/canvas/{id}`, `/flow/*` | any registry type as a node | `canvas-worker.higgsfield.ai` (`/api/canvases`, `/api/templates/{id}/use`, node `/run`) | Same `defineJob` schemas; node fields such as `{nodeType:"seedance_2_5", fieldId:"bitrate_mode"}` |
| MCP / agents | `/mcp`, `/mcp/{skill}`, `/mcp/bundles/{id}` | "35+ models and tools" | Remote MCP server `https://mcp.higgsfield.ai/mcp` (needs a Higgsfield login via OAuth; not connected) | Skills are prompt bundles (site scraper: 75 skills, 3 bundles). The page says it uses the same credits and models; tool schemas weren't inspected (login needed) |

### 5.2 Notes per tool

- **Plain generator.** Model picker (§2), then the `defineJob` schema, then the live cost, then `/jobs/v2/{type}`.
  Each model has its own persisted form store, e.g. `hf:video-kling-3-store:v2` and
  `hf:video-cinematic-studio-3-0-store:v1`. "Recreate" fills that store from a job's `params`.
- **Apps** are thin forms over fixed workflows. `POST /workflows` sends the template slug and a list of
  `{id, value}` field values. The server expands them into a job with a fixed model and params. The price shown is
  `template.cost` from the SSR page data, which the `site` scraper already captures (`site_app.templates[].cost_credits`).
- **Viral-hub presets** are graph workflows (`kind:"chain"`): every input has `binds_to:[{node, port}]`.
  `param_choices` exposes per-node enums such as `resolution` and `aspect_ratio`. The price is a lookup in
  `price_matrix` keyed by `"<node>.<param>=<value>,…"` (empty key = default), divided by 100. Community items store
  the result as `chain_preset_id` plus `chain_preset{id,name,slug,preview_media}`.
- **Motions** come in two kinds. (a) Higgsfield's own DoP model (`image2video`), which takes a `motion_id` from
  `/motions`. (b) Per-vendor preset families (`/kling-motions`, `/seedance-motions`…), which are applied as a
  preset or prompt to that vendor's job type. `mergeDynamicPresets:false` stops a model from merging the server list.
- **Kling 3.0** sends `mode` (`std`/`pro`/`4k`), `sound` (`on`/`off`), `duration` 3–15 s, `aspect_ratio`,
  `multi_shots` + `multi_shot_mode` (`auto`/`custom`) + `multi_prompt[{prompt,duration}]` and `kling_element_ids`.
  Cost: `duration × costs[mode].audio[sound]`. The client formula only covers `4k` (6 cr/s).

---

## 6. All related endpoints

Base: `https://fnf-api-gw.higgsfield.ai/fnf`. "public" = verified 200 without auth on 2026-11-26.
"login" = verified 401 `{"detail":"Invalid or expired token"}`. "JS" = seen only in the bundle, **not called**.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/job-sets/costs` | public | Cost table for 87 job types (`version` hash changes on every price change) |
| GET | `/feature` | public | `{"ZGV5a2hhbg":false}` (one legacy flag; base64 name) |
| GET | `/user/features` | public (anon defaults) | `generate_persisted_cache`, `has_nb_bonus_seedream_free_gens`, `has_seedream_batch_gens` |
| GET | `/datetime-settings` | public | Promo / free-gen / unlimited windows (`freegens_seedance_2_5_1080p`, …) |
| GET | `/viral-hub/presets/all`, `/viral-hub/types` | public | Viral presets with graph inputs, `param_choices`, `price_matrix` |
| GET | `/motions?size=…`, `/motion-samples?motion_id=…&size=…` | public (422 without the required params) | Motion catalog of all families (`catalog` scraper) |
| GET | `/kling-motions`, `/kling2-6-motions`, `/seedance-motions`, `/minimax-motions`, `/wan2-2-motions`, `/wan2-5-motions`, `/veo3-styles` | login | Per-vendor preset lists (`catalog --kinds login`) |
| GET | `/soul-styles`, `/soul-cinematic-styles`, `/soul-keyframe-styles` | login | Soul styles (`style_id`); public alternative: `/soul-samples` |
| GET | `/publications/community/{trending,approved,model-x}` | public | Real `params`/`results` per `job_set_type` |
| GET | `https://cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2/categories` | public | CMS trend categories (also `/video-explore/v2`, `/v2/{id}`) |
| GET | `/notices` | login | CMS `job_set_notices[]` and `header_notices[]` (per-model banners and badges) |
| GET | `/job-set-chain-presets?product_key=&show_hidden=` | login | Chain presets per product |
| GET | `/workspaces/settings` | login | `unlimited_settings[]` (unlimited grants per `job_set_type`/model) |
| GET | `/mixed-media/configs?preset_id=` | login | Mixed-media preset config |
| GET | `/restyle/presets` (+ `/restyle/presets/custom`) | login | AI Influencer restyle presets |
| GET | `/jobs`, `/jobs/accessible`, `/jobs/{id}`, `/job-sets/{id}` | JS (login) | Feed, job and job-set details |
| GET | `/input-{image,video,audio}s/{id}`, `/media/status` | JS (login) | Uploaded media and IP/NSFW status |
| GET | `/user`, `/workspaces`, `/workspaces/details`, `/workspaces/wallet` | JS (login) | User, workspace and credit balance |
| POST | `/jobs/v2/{type}`, `/jobs/{kebab-type}` | JS, mutation | **Create a generation** |
| POST | `/jobs/v2/{type}/dry-run`, `/jobs/{route}?dry_run=true` | JS, mutation-shaped | Guest availability / server cost quote |
| POST | `/chains/{viral-hub,mixed-media,mixed-media-preview,motion-control,reframe,reframe/batch,dubbing,voice-change,draw-to-video,beat-fit-nano-banana,sticker-matchcut,game-character-creator,seedance-eye-mask-sam}` | JS, mutation | Multi-step (chain) jobs |
| POST | `/workflows` | JS, mutation | App templates |
| POST | `/jobs/status-batch` | JS (login) | Poll many job statuses |
| PUT | `/jobs/{id}/cancel` | JS, mutation | Cancel |
| POST | `/jobs/seedance/confirm-rights/batch` | JS, mutation | Rights confirmation for Seedance inputs |
| POST | `/media/batch` `{mimetypes[], source:"user_upload", surface, force_ip_check}` | JS, mutation | Get presigned upload slots for images |
| POST | `/video` `{mimetype, is_hidden?, force_ip_check?}`, `/audio` `{extension, name}` | JS, mutation | Video/audio upload slot |
| PUT | `<upload_url>` (presigned, `Content-Type` from the slot) | JS, mutation | Upload bytes |
| POST | `/media/{id}/upload` `{job_id?, filename, force_nsfw_check, force_ip_check}`; `/video/{id}/upload?start_seconds&end_seconds`; `/audio/{id}/upload` | JS, mutation | Confirm upload (triggers NSFW/IP checks) |
| POST | `/media/anon` | JS, mutation | Guest upload slot |
| POST | `/uploads/multipart/{init,part-urls,complete,abort}` | JS, mutation | Large-file multipart upload |
| POST | `/workspaces/context` `{workspace_id}` | JS, mutation | Switch workspace |
| — | `https://mcp.higgsfield.ai/mcp` | OAuth | MCP server for agents |
| — | `https://canvas-worker.higgsfield.ai/api/*` | JS | Canvas / templates backend |

**Auth on these calls (described, not bypassed).** `Authorization: Bearer <Clerk JWT>` (Clerk frontend API is
proxied at `higgsfield.ai/_clerk`, publishable key in the HTML). Other headers:

- `hf-workspace-id` for team workspaces.
- `hf-access-realm` (JSON realm) on `/jobs/`, `/job-sets/`, `/assets/` and `/favourites/` for shared folders.
- `hf-surface` on uploads.
- `Accept-Language`.
- Analytics headers `hf-platform`/`hf-device`.

DataDome loads from `dd.higgsfield.ai/js`. The client spots a DataDome block by the `x-dd-b` response header and
clears `ddChallengeContainer`. Public GETs at about 1 req/s never hit a challenge.

---

## 7. The dynamic parts

| Mechanism | Where | What it can change without a deploy |
|---|---|---|
| `window.__HF_FF = {userId, flags:{f_<hash>:bool}, payloads:{}}` | Inline `<script>` in every SSR page. Refreshed per signed-in user via a TanStack server function (`POST`, id `c06cd72b…`) and cached in react-query `["feature-flags", userId]` | Show/hide flagged models (Seedance 2.5 Flash, Kling 4.0 Flash, Wan 4.0), features and A/B variants. 23 flags on `/ai/video`; names are hashed (`f_3a0922bf`) |
| `/job-sets/costs` | Fetched by the web adapter and the UI | Prices, discounts (`original_cost_per_second`), and **availability** of `pricedAs` models. A new `job_set_type` can appear here first (`scene_switch` on 2026-11-26) |
| `/datetime-settings` | Public | Free-gen, unlimited and promo windows per model |
| `/workspaces/settings` | Login | Unlimited grants per model and time window (badges, `use_unlim`) |
| `/user/features`, `/feature` | Public / per user | A few per-user switches |
| `/notices` | Login | CMS banners and badges per `job_set_type` (`cms-job-set-notice-*` components) |
| CMS catalogs | `/viral-hub/presets/all`, `/motions`, `/apps/{slug}` loaders, `/mixed-media-presets`, `cms.higgsfield.ai` | New effects, motions, apps and their prices: **these are new "models" from the user's point of view, with no deploy** |
| A/B cookies | `hf_ab_id`, `hf_es_ab*`, `hf_mob_vp_ab*` (cookie-consent list) | Layout experiments |
| PostHog | `phc_nAcCHDBUspNpjMXoEt7RUffSwfjsVsYAPVwEeHAfsWEd` at `e.higgsfield.ai` | Analytics; the flags above are evaluated server-side (likely PostHog-backed, given the `payloads` key; inferred) |

A new *base model*, such as a new Kling version, needs a frontend deploy: menu entry, `defineJob` schema, route,
plan table and cost formula all live in the bundle. Deploys are frequent: the build changed from `8a801a77` to
`548e0f3a` within one day, and `wan4_0` and `kling_4_0_flash` were added behind flags.

---

## 8. What we can and can't scrape

**Can (public, GET):**

- Live prices and model availability: `/job-sets/costs` (already the `models` section).
- Feature-flag states for anonymous users: parse `__HF_FF` from any page (one GET).
- Viral presets with their full price matrix (`catalog`), the `/motions` catalog (`catalog`; per-vendor lists and
  Soul styles need a login), and app templates with static costs (`site`).
- Promo windows: `/datetime-settings` (`site --what promos`).
- Real per-model `params` and results from the community feeds (`community --with-raw-params`).
- **The whole model registry from the JS bundle**: menu entries, `defineJob` schemas (enums, defaults, ranges,
  media roles and limits), routes, plan tiers, flag gating. These are static strings in a handful of chunks.

**Can't (without login, or never):**

- `/notices`, `/workspaces/settings` (unlimited), `/job-set-chain-presets`, `/mixed-media/configs`,
  `/restyle/presets`, `/seedance-motions`: login only.
- Per-user flag values (`__HF_FF` for a signed-in user).
- MCP tool schemas (OAuth).
- Anything that creates jobs, uploads or quotes prices server-side (`dry_run`): mutations, out of scope.

**New scraper ideas:**

1. **`models` registry scraper (new, high value).** Fetch the `/ai/video` and `/ai/image` HTML, follow the chunk
   graph like `samples/higgsfield/js2` does, and extract the following, joined on `job_set_type` with
   `/job-sets/costs`:
   - menu entries (`{id,title,badges,tags}`);
   - `video-featured-model-ids`;
   - the gating table (`flag`/`fallback`/`pricedAs`) plus the current `__HF_FF` values;
   - `video-model-plans`;
   - the adapter route table (`job_set_type → /jobs/v2/...`);
   - per-type schemas from `defineJob({type:…})` (`_default(enum([...]), x)`, `duration({min,max})`, `roles`,
     `counts`, limits).

   Output one row per model: `model_version_id, job_set_type, title, family, route, plan_tier, flag, flag_value,
   available, resolutions, durations, aspect_ratios, media_roles, limits, cost_rows`. Pure regex on minified JS
   works because every `defineJob` starts with `type:\`<job_set_type>\`,output:\``. Store the build id
   (`548e0f3a`, commit) so changes can be diffed.
2. **Flag / availability monitor.** A daily diff of `__HF_FF` and of `/job-sets/costs` job types catches new models
   (like `scene_switch`) and flag flips before launch.
3. **Cost calculator.** Implement the formulas in §4.2 and §5 (Seedance/Wan `with_video`/`video_edit`, Kling
   mode×sound, viral `credit_units/100`, app `template.cost`) in `estimate/` so `--estimate-cost` covers chain
   presets and edit/extend modes.
4. **Viral-preset price matrix expansion.** Flatten `price_matrix` keys into `(preset, node, param, value) →
   credits` rows.

---

## 9. Confidence

| Claim | Status |
|---|---|
| `__HF_FF` is in the SSR HTML with the flag values listed | **Verified live** (anon, `/ai/video`) |
| `/job-sets/costs` content, Seedance 2.5 rows, new `scene_switch` | **Verified live** |
| `/feature`, `/user/features`, `/datetime-settings`, `/viral-hub/presets/all`, `/viral-hub/types`, CMS categories public | **Verified live** |
| `/notices`, `/job-set-chain-presets`, `/workspaces/settings`, `/mixed-media/configs`, `/restyle/presets`, `/seedance-motions` need login | **Verified live** (401) |
| Community `params`/`results` shapes for `seedance_2_5` | **Verified live** (public feed) |
| Model menu, gating, plan tiers, `defineJob` schemas, limits, route table | **From JS**, read in two builds (stable between them) |
| Create endpoints, request bodies, billing flags, upload flow, status-batch, cancel | **From JS, not called** |
| Cost formulas | **From JS**. Example numbers apply them to the live table; not checked against a real charge |
| 3 s polling interval | **From JS** for the batch eligibility poller. The feed's own refetch interval wasn't pinned down |
| Extra stored keys (`genre`, `speedramp`, `prompt_language` …) come from backend defaults or other clients | **Inferred** |
| Flags evaluated by PostHog | **Inferred** (PostHog key and `payloads` shape) |
| App submission via `POST /workflows`, its server-side model choice | **From JS**; the model behind each app template is not visible |
| MCP tools use the same job types and credits | **Inferred** from the MCP page copy; not connected |

### Reproduce

```bash
# fetch tool pages + chunk graph (static imports), then grep:
grep -o 'type:`seedance_2_5`' samples/higgsfield/js2/*.js                  # job definition chunk
grep -o 'e(`video-featured-model-ids-[^`]*`' samples/higgsfield/js2/*.js   # named modules survive minification
grep -o 'window.__HF_FF = [^<]*' samples/higgsfield/js2/_pages/ai_video.html
# probe samples (GET only): samples/higgsfield/model_loading/*.json
python -m higgsfield_scraper scrape community --models seedance_2_5 --with-raw-params --max-items 300
```

Named modules are kept in the minified output, which makes chunks easy to grep:
`e(\`job-status-batch-api-MlNgvtE-\`, …)`, `use-seedance-2-5-submit-mutation-…`, `video-model-plans-…`,
`app-slug-type-jobsets-…`, `upscale-media-model-mapping-…`.
