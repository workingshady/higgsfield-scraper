# Where Higgsfield gets its models: vendors, inference platforms and evidence

**Question.** Where does Higgsfield get its AI models? Who makes each model, and where does Higgsfield **run** it:
on its own GPUs, through the vendor's own API, through a cloud model platform (Google Vertex AI, BytePlus ModelArk /
Volcengine, Alibaba Cloud Model Studio / DashScope, Azure OpenAI, AWS Bedrock), or through a hosted inference
platform (fal.ai, Replicate, Together, Fireworks, Modal, Baseten, RunPod, DeepInfra, Novita, WaveSpeed, PiAPI)?
And does Higgsfield publish any of this?

**Rules followed.** Public data only, GET only, about 1 request per second, no login. No prompts, usernames or user
ids are copied here. Request ids are cut to a prefix plus `…`. Evidence date: **2026-11-26** (frontend build
`548e0f3a`).

Related docs: [PRODUCTS.md](PRODUCTS.md) (product → `job_set_type` → vendor map),
[MODEL_LOADING.md](MODEL_LOADING.md) (`defineJob`), [JOBS_AND_STORAGE.md](JOBS_AND_STORAGE.md) (`meta.cost`,
`trace_id`), [COST_FORMULAS.md](COST_FORMULAS.md), [scrapers/community.md](scrapers/community.md) (`upstream_usage`),
[HIGGSFIELD_DATA_INVENTORY.md](HIGGSFIELD_DATA_INVENTORY.md), [LOGIN_COVERAGE.md](LOGIN_COVERAGE.md).
Evidence files: [fingerprints.json](../samples/higgsfield/providers/fingerprints.json),
[fingerprint_report.md](../samples/higgsfield/providers/fingerprint_report.md). Script:
[provider_evidence.py](../scripts/provider_evidence.py).

---

## 1. Direct answer

**Model makers: yes, published.** Higgsfield names the company behind almost every third-party model. You can see it
on landing pages, in UI strings ("Kling 3.0 is Kuaishou's first unified multimodal video model", "FLUX 3 by Black
Forest Labs", "High-resolution image generation by xAI"), and in the public developer API. That API uses vendor
labels ("ByteDanceVideo", "KlingVideo", "AlibabaVideo", "xAIImage" …) and vendor-prefixed endpoint ids such as
`bytedance/seedance-2.5/reference-to-video` and `alibaba/wan-3.0/text-to-video`.

**Where the models run: not published.** Nothing Higgsfield publishes says how it runs the models: no "powered by
fal", no Vertex, no BytePlus. Here is what the data shows:

1. **No fal, Replicate or other hosted-inference fingerprint anywhere.** I searched:
   - 925 public jobs across 34 `job_set_type`s from today's runs (1,199 jobs across 40 types counting every run on
     disk);
   - every URL host, id, key and cost record in those jobs;
   - 744 JS chunks.

   That found **0 fal fingerprints, 0 Replicate fingerprints, and 0 for Together, Fireworks, Modal, Baseten, RunPod,
   DeepInfra, Novita, WaveSpeed or PiAPI.** There were also 0 Vertex, Bedrock, Azure, BytePlus/Volcengine and
   DashScope endpoint strings in the JS. The only `byteplus` hit is an icon-label key in the LLM picker.
2. **All result media is re-hosted by Higgsfield.** Every URL in every job points to one of 3 hosts:
   - `d8j0ntlcm91z4.cloudfront.net` and `d2ol7oe51mr4n9.cloudfront.net`: CloudFront in front of Amazon S3,
     `eu-north-1`;
   - `cdn.higgsfield.ai`: Cloudflare.

   No vendor or platform media host leaks through: no `fal.media`, `replicate.delivery`, `*.volces.com`,
   `aliyuncs.com`, `klingai`, `oaidalleapi` or `googleapis`.
3. **Some jobs keep the upstream vendor's bill.** For a few vendors, `meta.cost` stores the upstream bill:
   - **OpenAI:** 67 of 67 GPT Image jobs carry Images-API token usage and an OpenAI-style `req_…` request id;
   - **Google Gemini:** token buckets with `thinking_tokens`;
   - **xAI:** a USD price per image;
   - **Black Forest Labs:** a numeric cost, probably in BFL credits (inferred).

   These records show Higgsfield is **billed per call by the vendor's API** for those models, not running the
   models on its own GPUs. They do **not** show a reseller such as fal in between.
4. **The browser itself calls one vendor directly.** Speech-to-text opens `wss://api.openai.com/v1/realtime` with a
   token minted by Higgsfield (`/audio/speech-to-text/openai-token`).
5. **Everything else is server-side and can't be seen.** That covers Seedance, Kling, Wan, MiniMax, Veo, Sora, Topaz,
   Recraft, Ideogram, ElevenLabs and MAGI. Jobs go to Higgsfield's own gateway, `fnf-api-gw.higgsfield.ai`
   (Cloudflare → Envoy), and come back as Higgsfield-hosted files. The client can't see how the backend routes a job.
   A fal or Replicate account behind the gateway **can't be ruled out**. There is simply **no evidence for it**.

Evidence strength: vendor identity is **confirmed** for almost all families. The access path is **confirmed or
strong** for OpenAI, Google Gemini image, xAI image, OpenAI speech-to-text and the Canvas LLM node (OpenRouter). It
is **likely** for BFL, Topaz and Alibaba (one path). It is **unknown** for the rest.

---

## 2. Evidence types and confidence

| Code | Evidence type |
|---|---|
| **A** | API data. Provider usage or billing fingerprints, provider model ids or provider-specific params in real public jobs (`params`, `meta`, `results`, `job_set_client_meta`) |
| **B** | JS code. Vendor strings, provider model ids, provider flags (`use_alibaba`, `use_magi_2`), direct vendor endpoints |
| **C** | Official Higgsfield text. Landing pages, UI strings (`_l10n_en.json`), the public API docs (`docs.higgsfield.ai`) |
| **D** | Inferred from the model name only |

| Confidence | Meaning |
|---|---|
| **confirmed** | Directly evidenced (a vendor named by Higgsfield, or a vendor-specific fingerprint in data or code) |
| **strong** | Several independent signals agree; no direct statement |
| **likely** | One circumstantial signal |
| **unknown** | No evidence; server-side routing is invisible |

> Note: in Higgsfield's JS, `toProvider` / `fromProvider` (the `defineJob` helpers, see
> [MODEL_LOADING.md](MODEL_LOADING.md)) convert between the UI form and **Higgsfield's own** wire `params`. They do
> **not** refer to a third-party provider. They are not evidence of any inference platform.

---

## 3. Master table

"Inference platform (evidence)" answers *where it runs*. "Jobs" counts public community jobs from the
2026-11-26 runs, shown as jobs with the fingerprint / jobs seen. "0 seen" means the public feeds returned no job of
that type.

| Model family | Vendor (company) | Inference platform / access path (evidence) | Ev. | Vendor conf. | Platform conf. | `job_set_type`s · public jobs |
|---|---|---|---|---|---|---|
| GPT Image 2 / 2.5 / 2.6 / 2.6 Flare | OpenAI | **OpenAI API, billed per call**: `meta.cost` = Images-API usage (`input_text_tokens`, `output_image_tokens`, `cached_*`) + `request_id` `req_<hex>`; 67/67 jobs | A C | confirmed | **strong** (OpenAI's own API; Azure OpenAI not strictly excluded) | `gpt_image_2_6` 50/50, `gpt_image_2` 10/10, `gpt_image_2_6_flare` 5/5, `gpt_image_2_5` 2/2; also `imagegen_2_0`, `openai_hazel*` |
| Sora 2 (retired) | OpenAI | OpenAI API naming in `params.model` (`sora-2`, `sora-2-pro`); no usage record | A B C | confirmed | likely (vendor API) | `sora2_video` 0/50 usage; model ids 50/50 |
| Speech-to-text (Realtime) | OpenAI | **Vendor API direct from the browser**: `wss://api.openai.com/v1/realtime`, token from `/audio/speech-to-text/openai-token` | B | confirmed | **confirmed** | (not a job type) |
| Nano Banana family (Gemini image) | Google | **Google Gemini API or Vertex AI** (can't tell which): Gemini-style token buckets incl. `thinking_tokens`; USD per job | A B C | confirmed | **strong** (Google-billed); AI Studio vs Vertex **unknown** | `nano_banana_flash` 1/3, `outpaint` 1/1, `nano_banana_2_1` 10/22 (scalar USD), `nano_banana_2` 0/30 |
| Veo 3 / 3.1, Gemini Omni | Google | none visible | B C | confirmed | unknown | `veo3*`, `gemini_omni*` · 0 seen |
| Grok Imagine image | xAI | **xAI API, billed per image**: `meta.cost` = bare USD string 0.022–0.10 | A B C | confirmed | **strong** | `grok_image` 7/7, `grok_image_2_0` 5/5 |
| Grok Imagine video | xAI | none visible | B C | confirmed | unknown | `grok_video*` · 0 seen |
| Seedance 2.0 / 2.5, Seedream, Seed Audio, ByteDance upscale | ByteDance | none visible: no `cgt-` task ids, no TOS/`volces` hosts, no `req_key` | B C | confirmed | unknown | `seedance_2_0` 0/50, `seedance_2_5` 0/34, `seedream_*` 0/20; `seed_audio`, `bytedance_*_upscale` 0 seen |
| Kling 2.x / 3.0 / O3 / Omni, Kling Avatars | Kuaishou | none visible; JS uses Kling-API-style ids `kling-v3`, `kling-v2-6`, `kling-v2-5-turbo` | B C | confirmed ("Kling 3.0 is Kuaishou's…") | unknown (vendor-API naming only, so likely at most) | `kling3_0` 0/29; others 0 seen |
| Wan 2.x / 3.0 | Alibaba | **two backends**: `client_meta.use_alibaba` (UI label "Use Alibaba") selects Alibaba's own service. Where the default path runs is unknown | B C | confirmed | likely: Alibaba Cloud for `use_alibaba=true`; unknown otherwise | `wan2_5_video` 51 seen, `client_meta` null 51/51 |
| HappyHorse, Qwen (TTS, camera, Image 3), Z-Image | Alibaba | none visible | B C (D for Qwen TTS) | confirmed (API docs: "AlibabaVideo/Image") | unknown | `z_image` 0/70; `happy_horse_video`, `qwen_*` 0 seen |
| MiniMax Hailuo 02/2.3, H3, speech | MiniMax | MiniMax-style `params.model` (`minimax-2.3`, `minimax-2.3-fast`, `minimax`); no usage record | A B C | confirmed | unknown | `minimax_hailuo` 41 seen (model ids 41/41) |
| FLUX.2, FLUX 3 | Black Forest Labs | likely **BFL API**: `flux_3_image` `meta.cost` 4.1–60.7, a scale consistent with BFL API credits (1 credit = $0.01; inferred) | A B C | confirmed | likely | `flux_3_image` 6/6, `flux_2` 0/50 |
| Ideogram 4.x | Ideogram | none visible | B C | confirmed | unknown | `ideogram_*` 0 seen |
| Recraft V4 / V4.1 | Recraft | none visible | B C | confirmed (name + API docs) | unknown | `recraft_v4_1` 0/19 |
| ElevenLabs v4, Music | ElevenLabs | none visible | B C | confirmed | unknown | `elevenlabs_*` 0 seen |
| Topaz image/video upscale | Topaz Labs | likely **Topaz API**: JS maps UI names to Topaz API model codes (`prob-4`, `ahq-12`, `iris-3`, `slp-2.5` …); params hold Topaz model names | A B C | confirmed | likely | `topaz_image` 50 seen (`Standard V2` 30, `High Fidelity V2` 18 …), `topaz_image_generative` 1 |
| MAGI-2 | Sand AI | none visible; `use_magi_2` switch for Genjutsu (feature flag `f_abd197c8`) | B C | confirmed | unknown | `magi_2` 0/23 |
| LTX-2.x | Lightricks | none visible | C (API docs) | confirmed | unknown | (not in community enum) |
| PixVerse V6 | PixVerse | none visible | C (API docs) | confirmed | unknown | (not in community enum) |
| SAM 3 (video, 3D) | Meta | none; open weights, so possibly self-hosted (inferred) | D | likely | unknown | `sam_3_*` 0 seen |
| 3D: Tripo, Meshy, Hunyuan3D | VAST (Tripo), Meshy, Tencent | none | D | likely | unknown | `tripo_*`, `meshy_*`, `hunyuan3d_*` (enum only) |
| Others: Sync, InfiniteTalk, Reve, Bria eraser, Inworld TTS, Mirelo, Sonilo, Depth Anything | Sync Labs, MeiGen, Reve, Bria, Inworld, Mirelo, Sonilo, open model | none | D (Inworld also C) | likely | unknown | enum / picker only |
| Soul / Soul 2 / Soul Cinema, DoP, Popcorn, Genjutsu, AI Influencer, mixed media … | **Higgsfield** | **in-house, probably self-hosted GPUs**: Soul params expose inference-engine switches `use_sage_attention`, `use_relax`, `use_refiner`, `use_green*` (inferred) | A C | confirmed (Higgsfield product) | likely (self-hosted) | `text2image_soul_v2` 39/39 flags, `text2image_soul` 1/1, `soul_cinematic` 26 |
| Cinema Studio 4.0, Videoshop, Reframe, viral presets, Ad Multiplier | Higgsfield wrappers over **Seedance** (landing + identical price tables) | same unknown path as Seedance | C + price twin | strong | unknown | `viral_hub_video` 225 seen (only `client_meta.source=viral_hub_web`) |
| Canvas `llm` node | Anthropic / OpenAI / Google models | **OpenRouter** ("Generate text via an LLM (OpenRouter).") | B | confirmed | **confirmed** | (Canvas node) |
| "Supercomputer" agent | Anthropic (Claude) | **the user's own linked Claude organization** ("It runs on Claude"; "Anthropic bills our organization") | B | confirmed | **confirmed** | (agent) |

---

## 4. Inference platform / source: is it fal, Replicate or similar?

### 4.1 What was searched

| Source | Size | What was looked for |
|---|---|---|
| Public community jobs, fresh (2026-11-26) | **925 unique jobs, 34 `job_set_type`s**, 74 raw envelopes. One run of 400 trending+approved items plus per-model filtered runs (trending and approved) for 44 job types | every URL host in `params` / `meta` / `meta.cost` / `results` / `result` / `job_set_client_meta`; id shapes; provider-ish keys; `meta.cost` shapes |
| All community runs on disk | 1,199 unique jobs, 40 types, 319 envelopes | same |
| Frontend JS (`samples/higgsfield/js2/`) | 744 chunks | platform domains and SDK names (list in §7) |
| Public API docs (`docs.higgsfield.ai`) | index, models catalog, video/image catalogs, request lifecycle, Seedance 2.5, Kling 3.0, Wan 3.0 pages | "powered by", vendor and platform names, queue API shape |
| Response headers | `fnf-api-gw`, `api.higgsfield.ai`, `cdn.higgsfield.ai`, both CloudFront result hosts | `server`, `via`, `x-*` |

### 4.2 Results

| Fingerprint searched | Where | Hits |
|---|---|---|
| fal: `fal.media`, `v3.fal.media`, `fal.run`, `falserverless`, `@fal-ai`, `fal.ai`, `fal_*` keys | jobs + JS | **0** |
| Replicate: `replicate.delivery` (`pbxt.`, `tjzk.`), `replicate.com`, `replicate_*` keys, 26-char base32 prediction ids, 64-hex `model_version` | jobs + JS | **0**. The one JS hit, `replicateAssets`, is an internal asset-copy method |
| Together, Fireworks, DeepInfra, Novita, WaveSpeed, PiAPI, Modal, Baseten, RunPod | jobs + JS | **0** |
| BytePlus / Volcengine: `volces.com`, `volcengine`, `ark.*`, TOS hosts, `cgt-` task ids, `req_key` | jobs + JS | **0**. JS has one `byteplus` key, a label in the LLM picker's icon map (`byteplus:{label:"ByteDance"}`) |
| Alibaba DashScope / OSS: `dashscope`, `*.aliyuncs.com`, DashScope `task_id`/`request_id` | jobs + JS | **0**. Only `use_alibaba` / `isAlibaba` / "Use Alibaba" |
| Google Vertex / AI Studio: `aiplatform.googleapis.com`, `generativelanguage.googleapis.com`, `storage.googleapis.com` | jobs + JS | **0** (JS `vertex` hits are WebGL `createVertexArray`) |
| AWS Bedrock, Azure (`blob.core.windows.net`, `openai.azure`) | jobs + JS | **0** |
| Kling: `klingai.com`, 18–19-digit task ids | jobs + JS | **0** |
| OpenAI: `req_<hex>` request id + Images-API usage | jobs | **67 / 67** GPT Image jobs |
| OpenAI: `api.openai.com` | JS | **1** (Realtime speech-to-text WebSocket) |
| Gemini token buckets (`input_tokens`, `output_tokens`, `thinking_tokens` + USD per bucket) | jobs | **2** (`nano_banana_flash`, `outpaint`) |
| Scalar USD cost (`meta.cost` = number string) | jobs | **22** (`grok_image` 7, `grok_image_2_0` 5, `nano_banana_2_1` 10); **6** numeric non-USD-scale (`flux_3_image`) |
| URL hosts in jobs | jobs | **3 hosts only**: `d8j0ntlcm91z4.cloudfront.net` (920 jobs), `d2ol7oe51mr4n9.cloudfront.net` (551), `cdn.higgsfield.ai` (542) |

> **Searched 925 jobs across 34 job types (1,199 / 40 counting older runs) and 744 JS chunks: 0 fal or Replicate
> fingerprints, and 0 for any other hosted-inference platform or cloud model platform endpoint.**

What this means, and its limits:

- Higgsfield **downloads every result into its own S3 bucket** before publishing. A fal or Replicate output URL would
  never reach the public data even if one was used. So "0 media-host hits" is weak evidence on its own.
- The **billing records are stronger evidence**. Where Higgsfield keeps the upstream bill, the bill has the
  **vendor's own format**: OpenAI `req_` ids and Images-API token fields, Gemini thinking-token buckets, xAI per-image
  USD. fal and Replicate bill in their own units (fal: per request, with a fal `request_id` UUID; Replicate:
  per-second or per-output, with prediction ids) and don't pass through OpenAI request ids. For **GPT Image, Nano
  Banana and Grok image**, the data therefore points to **direct vendor APIs** (strong, not proof).
- For **Seedance, Kling, Wan, MiniMax, Veo, Sora, Recraft, Ideogram, ElevenLabs, MAGI, Topaz video** there is
  **no fingerprint either way**. Platform: **unknown**.

### 4.3 The public API looks fal-like (circumstantial)

`docs.higgsfield.ai` (API host `https://api.higgsfield.ai`, keys from `console.higgsfield.ai`) documents a queue API:

| | Higgsfield public API (docs) | fal queue API (`queue.fal.run`, public docs) | Replicate predictions |
|---|---|---|---|
| Submit | `POST /{vendor}/{model}/{variant}` → `{status:"queued", request_id, status_url, cancel_url, expires_after}` | `POST /{owner}/{model}/{variant}` → `{request_id, status_url, response_url, cancel_url, queue_position}` | `POST /v1/predictions` → `{id, status:"starting", urls:{get, cancel}}` |
| Auth header | `Authorization: Key <id>:<secret>` | `Authorization: Key <key_id>:<key_secret>` | `Authorization: Bearer <token>` |
| Endpoint ids | `bytedance/seedance-2.5/reference-to-video`, `kling-video/v3.0/pro/text-to-video`, `alibaba/wan-3.0/text-to-video`, `higgsfield-ai/soul/v2/standard` | e.g. `fal-ai/kling-video/…/pro/text-to-video`, `fal-ai/bytedance/seedance/…` | `owner/model` + version |
| Statuses | `queued`, `in_progress`, `completed`, `failed`, `nsfw`, `canceled` | `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED` | `starting`, `processing`, `succeeded`, `failed`, `canceled` |
| Host | `api.higgsfield.ai`: Cloudflare (same IPs as `fnf-api-gw`) | `queue.fal.run` | `api.replicate.com` |

The `Key id:secret` scheme, the `vendor/model/variant` paths (`kling-video/…/pro/text-to-video` especially) and the
`request_id` + `status_url` + `cancel_url` trio closely **resemble fal's queue API**. This is **circumstantial
only**. It may just be the same industry convention, or an API designed to be familiar to fal users. The host is
Higgsfield's own, behind Cloudflare. The docs name no platform ("powered by", fal, Replicate: 0 mentions; SDK
`@higgsfield/client`). It **does not show** that Higgsfield runs models on fal.

---

## 5. Per-vendor notes

Counts are from the 2026-11-26 runs. Redacted examples are in
[fingerprints.json](../samples/higgsfield/providers/fingerprints.json).

### ByteDance: Seedance, Seedream, Seed Audio, upscale

- **Vendor:** confirmed. B: `{vendor:"bytedance", models:[…Seedance…, "Seedream 5.0 Pro"]}`, "ByteDance Upscale".
  C: "ByteDance's advanced image editing model", "Upscale images and videos with ByteDance and Topaz upscalers";
  API docs label "ByteDanceVideo"; API endpoint `bytedance/seedance-2.5/reference-to-video`.
- **Data:** `seedance_2_0` (50), `seedance_2_5` (34), `seedream_*` (20). **No** `meta.cost`, no task ids, no
  BytePlus fields. `seedance_2_5` params are Higgsfield-shaped (`model:"default"`, `speedramp`, `multi_shots`,
  `bitrate_mode`, `prompt_language`). `seedance_2_0` stores `model:"seedance_2_0"`, `mode:"std"`.
- **Unknown:** BytePlus ModelArk (international) vs Volcengine Ark (China) vs a reseller. The JS has a
  `video-seedance-2-5-cn` module and `prompt_language:"zh"` defaults (see [PRODUCTS.md](PRODUCTS.md)), but that is
  not a hosting fingerprint.

### Google: Veo, Gemini Omni, Nano Banana (Gemini image)

- **Vendor:** confirmed (B + C: "Google's next-gen flagship image model", "Google Veo 3.1").
- **Data (A):**
  - `nano_banana_flash` (1 of 3) and `outpaint` (1 of 1): `meta.cost` is a JSON string
    `{input, input_tokens, output, output_tokens, thinking, thinking_tokens, total, total_tokens}` with USD per bucket.
    In `outpaint`, $2 / $12 / $120 per 1M input / thinking / output tokens (example: 1,120 output tokens = $0.1344).
    That ratio is consistent with Gemini 3 Pro Image list pricing (inferred).
  - `nano_banana_2_1`: 10 of 22 jobs carry a bare USD string, 0.039–0.120.
  - `nano_banana_2`: 0 of 30.
- **Platform:** Google-billed per token, so **strong** for Google's API. Gemini API (AI Studio) and Vertex AI use
  the same prices, so **which one is unknown**. Veo / Gemini Omni: 0 public jobs, **unknown**.

### OpenAI: GPT Image, Sora, speech-to-text

- **GPT Image (A, 67 of 67 jobs):** `meta.cost` JSON string with `request_id` (`req_` + 32 hex, e.g. `req_a22f…`),
  `input_text_tokens`, `input_image_tokens`, `output_image_tokens`, `output_text_tokens`,
  `cached_text_input_tokens`, `cached_image_input_tokens`. Some `gpt_image_2` / `2_5` records also carry USD per
  bucket (`input_text`, `output_image` …).
  - `params.model` holds codenames: `aurora-img-alpha` (2.6, 50/50), `videotape-alpha` (2, 10/10),
    `star-swirl-alpha` (2.6 Flare, 5/5), `sunburst` / `flare` (2.5).
  - Codenames plus `alpha` suggest early or partner access to unreleased OpenAI models (inferred).
  - `req_<hex>` is the OpenAI platform's request id format, so this looks like **OpenAI's own API**. Azure OpenAI is
    not strictly ruled out.
- **Sora 2** (retired): `params.model` `sora-2-pro` (40), `sora-2` (10). These are OpenAI API model names. No usage
  record. Platform: likely OpenAI API.
- **UI text:** "OpenAI service disruption. Credits refunded." (C) shows a direct dependency on OpenAI's service.
- **Speech-to-text (B):** the browser connects to `wss://api.openai.com/v1/realtime` (24 kHz audio) using a
  short-lived token from Higgsfield's `/audio/speech-to-text/openai-token`. This is the **only direct client → AI
  vendor connection** in the frontend.

### xAI: Grok Imagine

- **Vendor:** confirmed (C: "High-resolution image generation by xAI", "Grok Imagine by xAI"; API docs "xAIImage",
  "xAIVideo").
- **Data (A):** `grok_image` 7 of 7, `grok_image_2_0` 5 of 5. `meta.cost` is a bare string such as `"0.08"`, range
  0.022–0.10. That is a USD-per-image price, so xAI bills per call.
- **Platform:** **strong**, xAI API. Grok video: 0 public jobs, **unknown**.

### Kuaishou: Kling

- **Vendor:** confirmed. C: "Kling 3.0 is Kuaishou's first unified multimodal video model" (UI strings); API docs
  "KlingVideo"; endpoints `kling-video/v3.0/{std|pro|4k}/…`. B: Kling-API-style ids `kling-v3`, `kling-v2-6`,
  `kling-v2-5-turbo`, `kling-v2-1-master`, `kling_element_ids`.
- **Data:** `kling3_0` 29 jobs, only `mode:"pro"`. No task ids, no `klingai` hosts.
- **Platform:** **unknown**. Kling-API model naming hints at the vendor API (likely at most).

### Alibaba: Wan, HappyHorse, Qwen, Z-Image

- **Vendor:** confirmed. C: "Alibaba's #1 ranked video and audio model" (HappyHorse), "Wan 2.6 … from Alibaba Cloud";
  API docs "AlibabaVideo" / "AlibabaImage"; endpoints `alibaba/wan-3.0/…`.
- **The switch (B):** Wan 2.5 video and Wan 2.5 Speak forms keep `isAlibaba` and send
  `client_meta.use_alibaba` (alongside `use_unlim`). The UI string is "Use Alibaba". So one backend is Alibaba's own
  service (Model Studio / DashScope; inferred, no endpoint string), and the default backend is something else.
  Wan 2.x has open weights, so the default could be self-hosted or a third party (unknown).
- **Data:** `wan2_5_video` 51 jobs, all with `job_set_client_meta: null`. The flag isn't stored, or community posts
  used the default path. `z_image` 70 jobs, no fingerprints.

### MiniMax: Hailuo, H3, speech

- Vendor confirmed (B + C: "Hailuo is MiniMax's video model family"; API docs "MiniMaxVideo").
- Data: `minimax_hailuo` 41 jobs, `params.model` `minimax-2.3` (28), `minimax-2.3-fast` (7), `minimax` (6). No
  `trace_id` / `base_resp` (MiniMax API response fields).
- `text2speech_v2` cost rows carry `model:"minimax"`.
- JS has `minimaxInstructCanvas` (`access-video-instruct-minimax`).
- Platform **unknown**.

### Black Forest Labs: FLUX

- Vendor confirmed (C: "FLUX 2 is an AI image model from Black Forest Labs", "FLUX 3 … by Black Forest Labs").
- Data: `flux_3_image` 6 of 6 `meta.cost` strings, 4.1–60.7. That isn't USD-per-image scale, and BFL's API prices
  in credits (1 credit = $0.01), so the values are probably BFL credits (**inferred**). `flux_2` 0 of 50
  (`model: pro` 49, `max` 1).
- Platform **likely** BFL API.

### Ideogram, Recraft, ElevenLabs

- Vendors named in B and C ("by Ideogram", "Expressive voiceovers from ElevenLabs", "Recraft V4.1"; API docs
  "IdeogramImage", "RecraftImage").
- `recraft_v4_1` has 19 jobs with no fingerprints. Ideogram and ElevenLabs had 0 public jobs.
- Platform **unknown**.

### Topaz Labs

- Vendor confirmed (C: "ByteDance and Topaz upscalers").
- B: JS maps UI names to **Topaz API model codes**: `proteus:"prob-4"`, `artemis:"ahq-12"`, `iris:"iris-3"`,
  `rhea:"rhea-1"`, `gaia:"ghq-5"`, `theia:"thd-3"`, Starlight `slc-1` / `slf-1` / `slp-2.5`, interpolation `apo-8`.
  `fps_boost` cost rows carry `model:"topaz"`.
- A: `topaz_image` 50 jobs with Topaz product model names (`Standard V2` 30, `High Fidelity V2` 18, `CGI`,
  `Text Refine`); `topaz_image_generative` `Redefine`.
- Platform **likely** Topaz's own API: these are its API model ids, and Topaz doesn't distribute Starlight weights
  (inferred).

### Sand AI: MAGI-2

- Vendor confirmed (B + C: "MAGI: Sand AI video from text, frames or references, with sound").
- B: Genjutsu motion control has a `use_magi_2` option behind feature flag `f_abd197c8`, with rules "MAGI-2 renders
  only 1080p" and "at most 10 reference images".
- Data: `magi_2` 23 jobs, `trace_id: null`, no fingerprints.
- Platform **unknown**.

### Meta (SAM 3), 3D vendors, others

These come from job-type names only (D):

- `sam_3_video` / `sam_3_3d*`: Meta SAM 3;
- `tripo_*`: VAST Tripo;
- `meshy_*`: Meshy;
- `hunyuan3d_*`: Tencent;
- `bria_eraser`: Bria;
- `sync_so`: Sync Labs;
- `infinite_talk`: MeiGen;
- `reve`: Reve;
- `inworld_text_to_speech`: Inworld;
- `mirelo_text_to_audio`: Mirelo;
- `sonilo_music`: Sonilo;
- `depth_anything_video`: Depth Anything.

The public API docs add **Lightricks (LTX-2.5)** and **PixVerse (V6)** (C). There were no public jobs and no
fingerprints. Platform **unknown**.

### Higgsfield in-house

- **Soul** (`text2image_soul_v2` 39 of 39, `text2image_soul` 1 of 1) stores inference-engine switches in `params`:
  `use_sage_attention`, `use_relax`, `use_refiner`, `use_green`, `use_green_aidar`, plus `seed`, `enhance_prompt` and
  `style_strength`. SageAttention is an open-source attention kernel for diffusion inference. Flags like this only
  make sense when you **run the model on your own GPUs**, so the platform is **likely self-hosted** (inferred). The
  base model is unknown.
- DoP (`image2video`), Popcorn (`text2keyframes`), Genjutsu (`hf_mult_*`, optionally MAGI-2), AI Influencer and
  mixed media are Higgsfield products. Their backends aren't disclosed.
- Wrappers: Cinema Studio 4.0, Videoshop, Reframe, Ad Multiplier and viral presets have price tables identical to
  Seedance (see [PRODUCTS.md](PRODUCTS.md)). They probably call Seedance through the same unknown path.
  `viral_hub_video` (225 jobs) stores only `client_meta.source = "viral_hub_web"`.

---

## 6. LLMs inside Higgsfield products

| Surface | Models | Access path | Evidence |
|---|---|---|---|
| Canvas `llm` node | default `anthropic/claude-sonnet-4.6`; `anthropic/claude-opus-4.7`, `claude-haiku-4.5`; `openai/gpt-5.5(-pro)`, `gpt-5.4-mini`, `gpt-5.2`, `gpt-5.1`, `gpt-5(-mini)`, `gpt-4.1-mini`, `gpt-4o-mini`; `google/gemini-3.1-pro-preview`, `gemini-3.1-flash-lite-preview` | **OpenRouter**, confirmed: "Generate text via an LLM (OpenRouter)." | B ([PRODUCTS.md](PRODUCTS.md) §3.17) |
| Agent / studio model picker | `higgsfield/best-orchestrator`, `higgsfield/efficient-orchestrator(-paid)`, `google/gemini-orchestrator`, `anthropic/claude-opus-5-5`; modes "Smart", "Efficient", "Orchestrator (Gemini)" | Higgsfield orchestrators. Model slugs use the OpenRouter-style `vendor/model` form. The label map knows `anthropic`, `openai`, `google`, `xai`, `deepseek`, `qwen`/`alibaba`, `moonshot`/`kimi`, `bytedance-seed`/`byteplus`, `z.ai`, `nvidia`, `minimax`. Routing **unknown** (OpenRouter likely, inferred) | B |
| "Supercomputer" | Claude | **The user's linked Claude organization**: "I'd like to use Supercomputer in Higgsfield. It runs on Claude, and an owner, admin, or billing admin of our Claude organization needs to approve the connection" … "we don't share an API key. Anthropic bills our organization for the usage" (`platform.claude.com/linked-platforms`). Confirmed | B |
| Prompt enhancement | not named | `enhance_prompt` boolean in job params (Soul, Cinema Studio 3). Done server-side; the model is **unknown** | B |
| MCP (`mcp.higgsfield.ai`) | n/a | An MCP **server** that external agents call. It isn't an LLM Higgsfield consumes | C |

---

## 7. Infrastructure: visible and invisible

**Visible:**

| Layer | Finding | Evidence |
|---|---|---|
| App API | `fnf-api-gw.higgsfield.ai/fnf`, Cloudflare in front (`server: cloudflare`, `CF-RAY`) with **Envoy** behind it (`x-envoy-upstream-service-time`) | response headers |
| Public developer API | `api.higgsfield.ai`, Cloudflare, **same IPs** as `fnf-api-gw` (104.18.14.164 / 104.18.15.164) | DNS + headers |
| Result storage | `d8j0ntlcm91z4.cloudfront.net` and `d2ol7oe51mr4n9.cloudfront.net`: CloudFront → **Amazon S3, `eu-north-1`** (`x-amz-bucket-region`) | headers; 920 / 551 jobs |
| CDN | `cdn.higgsfield.ai`: Cloudflare (thumbnails, min variants) | headers; 542 jobs |
| Other services | `canvas-worker.higgsfield.ai`, `3d-scene-builder.higgsfield.ai`. The JS reads config from `cloudflare.env`, which suggests some services run on Cloudflare Workers (inferred) | JS |
| Direct vendor call | `wss://api.openai.com/v1/realtime` (speech-to-text) | JS |
| Third-party inference hosts | **none** in 744 JS chunks or 1,199 jobs | §4 |

**Invisible:** what happens between the gateway and the GPU or vendor. Every generation job is created as
`POST /jobs/v2/{job_set_type}` (or `/jobs/{kebab}`, `/chains/*`) on Higgsfield's own gateway, polled on Higgsfield
endpoints, and returned as Higgsfield-hosted files. **Server-side routing can't be seen from the client.** One model
could be served by the vendor API on one day and by fal on the next with no visible change. The only leaks are the
`meta.cost` billing records (§4.2) and client flags such as `use_alibaba` and `use_magi_2`.

---

## 8. How to re-check

```bash
# 1. fresh public jobs with stored params and meta (GET only, ~1 req/s)
python -m higgsfield_scraper scrape community --feeds trending,approved --max-items 400 --with-raw-params --label provider-evidence -q
#    per model (trending is image-heavy; approved has more video):
python -m higgsfield_scraper scrape community --feeds approved --models seedance_2_5 --max-items 40 --with-raw-params --label pa-seedance_2_5 -q

# 2. fingerprint report: hosts, usage shapes, ids, provider keys per job_set_type (+ JS platform-string scan)
python scripts/provider_evidence.py --runs "runs/*_provider-evidence*" "runs/*_pa-*" --js samples/higgsfield/js2
python scripts/provider_evidence.py            # every run on disk
```

Note: a `--models` list with many types can return 0 items or a 422 when one name isn't in the feed's
`JobSetType` enum. The 422 body lists the valid names. Query one model per run.

**JS grep list** (case-insensitive) over `samples/higgsfield/js2/*.js` and `_l10n_en*.json`:
`fal.ai fal.run fal.media @fal-ai falserverless replicate.com replicate.delivery byteplus volcengine volces.com ark.
dashscope aliyuncs aiplatform.googleapis generativelanguage vertexai bedrock azure together.ai fireworks.ai deepinfra
novita wavespeed piapi modal.run baseten runpod openrouter api.openai.com api.x.ai klingai.com minimaxi
api.elevenlabs.io topazlabs use_alibaba use_magi isAlibaba upstream vendor: "by " "from "`.
Expect false positives: `vertex` (WebGL), `replicate` (`replicateAssets`), `aliyun` (an email-domain list), `xai`
inside identifiers.

**Reading the fingerprints:**

| You see | It means |
|---|---|
| `meta.cost` JSON with `request_id:"req_…"`, `input_text_tokens`, `output_image_tokens` | OpenAI Images API bill |
| `meta.cost` with `thinking_tokens` and USD per bucket; or `usageMetadata`, `thoughtsTokenCount`, `candidatesTokenCount` | Google Gemini bill |
| `meta.cost` bare number string < 1 on a vendor model | USD per call from the vendor API (xAI, Gemini image) |
| `meta.cost` bare number ≥ 1 on FLUX | probably BFL credits (inferred) |
| `fal.media` / `falserverless` / `replicate.delivery` URLs, `fal_*` / `replicate_*` keys, 64-hex `version` | a hosted-inference platform (not seen so far) |
| `cgt-…` ids, `*.volces.com` / TOS URLs, `req_key` | BytePlus / Volcengine Ark (not seen) |
| `dashscope` / `*.aliyuncs.com`, `task_status`, `output.task_id` | Alibaba Model Studio (not seen) |
| `base_resp`, MiniMax `trace_id` inside `meta` | MiniMax API (not seen; the top-level `trace_id` is Higgsfield's own UUIDv4) |
| `use_*` flags in `params` / `client_meta` | backend switches (`use_alibaba`, `use_magi_2`) or engine knobs (`use_sage_attention`) |

**Changes to watch:**

- A new `meta.cost` shape on a job type that had none, such as Seedance or Kling. This is the most likely leak.
- Any non-Higgsfield host in `results`.
- New `use_*` switches in `client_meta`.
- New "by X" / "powered by" lines in `_l10n_en.json` or on the public API docs.
- A `response_url` or `queue_position` field showing up in the public API (more fal-like).
- New vendor prefixes in `docs.higgsfield.ai` endpoint ids.

---

## 9. Confidence and limits

- **Public data only.** Community posts are a biased sample: popular models, published results. 30 of the 44 job
  types queried returned **no public jobs** (Kling 4.0, Kling 2.6, Wan 2.6–3.0, Veo, Grok video, Ideogram, ElevenLabs, Seed Audio, HappyHorse, Topaz video …).
  Their platform rows rest on JS and docs only.
- **Absence isn't proof.** Results are re-hosted, and server-side calls never reach the client. "0 fal or Replicate
  fingerprints" means *no evidence*, not *proven not used*.
- **Billing-shape evidence is strong but indirect.** A reseller could in theory pass a vendor's usage object through
  unchanged. Here that seems unlikely because OpenAI `req_` ids come from OpenAI's own API, but it isn't impossible.
- **Inferred items** are marked as such: Gemini 3 Pro Image pricing for `outpaint`, BFL credits, the Alibaba Cloud
  meaning of `use_alibaba`, Soul running self-hosted, the Seedance price twins, the OpenRouter routing of the agent
  picker, and every D-row vendor.
- **The public API's fal-like shape is circumstantial.** It is not evidence that fal hosts anything.
- Login-only data (own job history, `/jobs/{id}/trace`) might hold more upstream ids. It wasn't used (public only,
  see [LOGIN_COVERAGE.md](LOGIN_COVERAGE.md)).
