# Higgsfield products: which model each one really calls

For every Higgsfield.ai product: which raw `job_set_type` (model id) it sends, which vendor is behind that
model, how the product works, and what it costs. Credit **formulas** are in
[`COST_FORMULAS.md`](COST_FORMULAS.md); this page gives per-product price summaries and worked examples only.

**Date:** 2026-11-26. **Build studied:** `548e0f3a` (`samples/higgsfield/js2/`, 580 chunks).

**Sources:**

- the `defineJob` registry, the adapter route table and the `JobSetType` enum in the JS bundle (see
  [`MODEL_LOADING.md`](MODEL_LOADING.md) for how these fit together);
- live `GET /job-sets/costs` (`samples/higgsfield/model_loading/job_sets_costs.json`, 87 types);
- the latest pricing run's `models.json`;
- 300 community generations with raw `params` (`runs/20261126-090321_re-products`);
- 92 apps, 174 landing pages and 33 mixed-media presets (`runs/20261126-090321_re-products-site`);
- 87 viral presets, 419 motions and 75 MCP skills.

**Rules followed:** GET only, public, no login. No POST, upload or generation was sent. Every create endpoint and
request body below is marked **(from JS, not called)**. User ids in URLs are replaced with `user_<redacted>` and
media ids with `<media-id>`.

**Evidence labels used throughout:**

| label | meaning |
|---|---|
| **API** | Seen in live API data: provider-style usage records (`upstream_usage`) or provider model ids stored in a job's `params` |
| **JS** | The vendor is named in the bundle (model descriptions such as "by xAI", vendor groups such as `vendor:"bytedance"`) or in a JS flag such as `use_alibaba` |
| **landing** | The vendor is named on a public higgsfield.ai landing page |
| **name** | Inferred from the model family name only. No vendor string was found |
| **price twin** | A Higgsfield product's `/job-sets/costs` table is identical to a vendor model's table. This hints at the backend but doesn't prove it |
| **in-house** | A Higgsfield product. The backend model isn't disclosed |

Base URL for every API path below: `https://fnf-api-gw.higgsfield.ai/fnf`.

---

## 1. TL;DR matrix

| Product | Route(s) | `job_set_type` (default first) | Provider | Create endpoint (from JS, not called) | Inputs → output | Price summary (live) |
|---|---|---|---|---|---|---|
| Video generator | `/ai/video?model=`, `/create/video` | `seedance_2_5` (default), `seedance_2_5_flash`, `seedance_2_0(_mini)`, `kling4_0`, `kling_4_0_flash`, `kling3_0(_turbo)`, `kling_o3_*`, `wan3_0(_prime)`, `wan2_7`, `minimax_h3*`, `grok_video_v15(_lite)`, `gemini_omni_flash_1_2`, `magi_2`, `happy_horse_video`, `flux_3_video`, `veo3_1_lite`, `image2video` (DoP) | ByteDance, Kuaishou, Alibaba, MiniMax, xAI, Google, Sand AI, BFL, Higgsfield | `POST /jobs/v2/{type}` (older: `/jobs/{kebab-type}`) | prompt + images/video/audio → video | Seedance 2.5: 3–34 cr/s; Kling 4.0: 2.5–12 cr/s; Wan 3.0: 0.75–6 cr/s; MiniMax H3 Lite: 1–1.25 cr/s |
| Video edit / extend | `/ai/video/edit` | `seedance_2_5` + `model:"video_edit"` or `"video_extension"`; `kling_o3_image_reference`, `gemini_omni_flash_1_2` (edit), `grok_video_edit`, `flux_3_video_edit` | same as above | same | 1 source video + prompt → video | Seedance 2.5 edit: 3.5/7.5/20/34 cr/s (480p/720p/1080p/4k) |
| Image generator | `/ai/image?model=`, `/image` | `gpt_image_2_6` (default), `gpt_image_2_6_flare`, `gpt_image_2(_5)`, `nano_banana_2_1`, `nano_banana_flash`, `nano_banana_2`, `seedream_v5_pro`, `seedream_5_5`, `seedream_5_0_flash`, `flux_2`, `flux_3_image`, `ideogram_4_6`, `recraft_v4_1`, `grok_image_2_0`, `kling_image_4_0`, `minimax_h3_image`, `z_image`, `image_auto` | OpenAI, Google, ByteDance, BFL, Ideogram, Recraft, xAI, Kuaishou, MiniMax, Alibaba | `POST /jobs/v2/{type}` | prompt + 0–16 refs → image | GPT Image 2.6: 0.75–12 cr/image; Nano Banana 2.1: 1.5/2/3; Seedream 5.0 Pro: 1.25–2.5 |
| Soul / Soul ID | `/soul`, `/soul/{styleId}`, `/character` | `text2image_soul_v2`, `soul_cinematic`, `text2image_soul` | Higgsfield in-house | `/jobs/v2/text2image_soul_v2`, `/jobs/v2/soul_cinematic` | prompt + style + Soul ID → image | Not in `/job-sets/costs`; client formula `batch × 0.125` (unit unclear) |
| Cinema Studio | `/cinema-studio` | `cinematic_studio_video_4_0` (also `_3_5`, `hf_fnf_video` = 3.0, `cinematic_studio_image`, `_soul_cast`, `_soul_location`) | Higgsfield over **Seedance** (landing + price twin of `seedance_2_5`) | `/jobs/v2/cinematic_studio_video_4_0` | prompt + camera/genre CMS ids + refs → video | 4.0: 3/7/16/28–34 cr/s, the same as Seedance 2.5 |
| Camera motions (DoP) | `/motion`, `/ai/video` (Higgsfield Lite/Standard/Turbo) | `image2video`, `image2video_mix` | Higgsfield in-house | `/jobs/image2video` | image + `motion_id` → video | Client formula: Lite 3/5 cr; Standard/Turbo depend on steps |
| Motion control / Genjutsu | `/ai/video/motion`, `/genjutsu` | `hf_mult_motion_control(_flash)`, `kling3_0_motion_control`, `kling2_6_motion_control`, `ai_influencer_motion_control*` | Higgsfield (has a `use_magi_2` switch) / Kuaishou | `/jobs/v2/kling3_0_motion_control`, `/chains/motion-control` | driving video + character image → video | Genjutsu 3/7/20 cr/s; Flash 1/2/4; Kling 3.0 MC 1.5 (std) / 2.5 (pro) |
| Effects / viral hub | `/effects`, `/viral-effects` | `viral_hub_video` (a chain preset) | Higgsfield chain; price twin of Seedance 2.0 / 2.0 Fast for most presets | `POST /chains/viral-hub` | 1–3 images (+ text) → video | `ceil(credit_units/100)`, e.g. `floating-fall` 84 cr (default) to 144 cr (1080p) |
| Apps | `/apps/{slug}` | per app: `nano_banana*` (63 of 92 apps), `keyframes_faceswap`, `character_swap_v2`, `wan2_2_animate_*`, `qwen_camera_control`, `kling_transition`, `outpaint`, … | mostly Google Nano Banana (image step); video step not disclosed | `POST /workflows` (some apps have their own route) | fixed template → image/video | Static `template.cost`: 1–2 cr image step, 6–26 cr video step |
| Mixed media | `/mixed-media` | `mixed_media`, `mixed_media_preview` | Higgsfield chain | `/chains/mixed-media` | video ≤10 s + preset → video | Not in `/job-sets/costs` (config needs a login) |
| Lipsync / Speak | `/lipsync-studio`, `/speak` | `kling-speak` (Kling Avatars 2.0), `speak-hf-v2`, `wan2_5_speak`, `kling2_6_lipsync`, `kling-lipsync`, `infinite_talk`, `sync_so`, `veo3_1_speak` | Kuaishou, Higgsfield, Alibaba, MeiGen, Sync Labs, Google | `/jobs/{kebab}` | image or video + audio/TTS → video | Not in `/job-sets/costs` (shown per model in the picker) |
| Audio / TTS / dubbing | `/audio`, `/text-to-speech`, `/ai-video-translator` | `elevenlabs_v4(_turbo)`, `text2speech_v2` (`model: minimax\|elevenlabs…`), `seed_audio`, `qwen_audio_tts`, `voice_change_merge`, `audio_dubbing`, `dubbing_lipsync`, `elevenlabs_video_to_music` | ElevenLabs, MiniMax, ByteDance Seed, Alibaba Qwen | `/jobs/v2/{type}`, `/chains/dubbing`, `/chains/voice-change` | text/audio/video → audio or video | ElevenLabs v4: 0.23 cr per 50 characters; dubbing 3 cr/s; lipsync dubbing 3–6 cr/s by fps |
| Upscale / enhance | `/upscale`, `/ai-video-upscaler` | `topaz_image(_generative)`, `topaz_video`, `topaz_hyperion_2_5`, `bytedance_video_upscale`, `flux_video_upscale`, `seedance_2_5_kling_upscale`, `nano_banana_2_upscale`, `fps_boost` | Topaz Labs, ByteDance, BFL, Google, Higgsfield | `/jobs/topaz-image`, `/jobs/topaz-video`, `/jobs/v2/bytedance_video_upscale`, `/jobs/nano-banana-2-upscale` | image/video → upscaled | Topaz is a server quote (`dry_run`); Hyperion 2.6/5.2 cr/s; Enhance 4 cr/s; FLUX upscale 0.5–11 cr/s |
| Reframe | `/ai/video/reframe` | `reframe` | Higgsfield chain; price twin of **Seedance 2.0** | `/chains/reframe` (`/chains/reframe/batch` when > 15.25 s) | video + new aspect → video | 3/4.5/12 cr/s + 3 images × 1.25 cr |
| AI Influencer | `/ai-influencer-studio` | `ai_influencer`, `ai_influencer_motion_control(_flash)`, `ai_influencer_replace_object(_flash)`, `ai_influencer_restyle` | Higgsfield in-house | `/jobs/v2/{type}`, `/jobs/v2/restyle` | trait config → image; image + video → video | MC/replace 3/7/20 cr/s; Flash 1/2/4 |
| Marketing / Ads studio | `/marketing-studio`, `/ads-studio`, `/ad-multiplier` | `marketing_studio_video`, `marketing_studio_image`, `marketing_studio_hook`, `marketing_storyboard`, `ad_multiplier(_v2/_replace)` | Higgsfield; avatars "powered by Soul 2.0" (landing); storyboard has a `use_seedream_bonus` flag | `/jobs/v2/marketing_studio_image` … | URL/brand/product → storyboard → video | Marketing video 3.5/5/13 cr/s; Ad Multiplier = Seedance 2.5 table |
| Canvas / Flow | `/canvas/{id}`, `/flow/*` | any registry type as a node, plus an `llm` node | node's vendor; LLM node via **OpenRouter** (JS) | `canvas-worker.higgsfield.ai/api/*` | node graph | "Same rate as that model elsewhere" (landing) |
| Popcorn / storyboard | `/storyboard-generator`, Popcorn | `text2keyframes` (`is_pop_corn`, `count`, `quality:"1600p"`) | Higgsfield in-house | not in the route table | prompt (+ref) → N keyframes | Not in `/job-sets/costs` |
| Videoshop / video edit tools | `/videoshop`, `/video-editor` | `videoshop_edit/relight/camera_move/genjutsu`, `cinematic_video_editor/relight/inpaint`, `swap_object`, `remove_object`, `draw_to_video` | Higgsfield; price twins of Seedance 2.5 / 2.0 | `/jobs/v2/videoshop_*` | video + instruction → video | 3–34 cr/s (Seedance 2.5 table); object edits 3/4.5/12 cr/s + 3.5 cr/frame |
| Faceless / AI Host / Shorts | `/faceless-studio`, `/ai-host`, `/shorts-studio` | `youtube_faceless_video`, `ai_host_video` | Higgsfield in-house | not in the route table | script → video | Faceless: 16 or 41 cr per 10 s block; AI Host 3.3/7.7/17.6 cr/s |
| MCP / agents / CLI | `/mcp`, `/cli`, `/ai/video/agent` | the same job types | as per model | `https://mcp.higgsfield.ai/mcp` (OAuth) | chat → jobs | "Same credit system" (landing) |
| Public API | `/higgsfield-api` → `open.higgsfield.ai`, `docs.higgsfield.ai` | catalog of "Seedance, Kling, Veo, GPT Image, Soul…" | as per model | "POST the model's endpoint → `request_id` + `status_url` (+ `cancel_url`), poll" (landing; not called) | | Separate per-model API price list (needs an API key; not checked) |

---

## 2. Provider map

How each family's vendor was established. "Confirmed" means the vendor is named in JS or API data (or both).

| Family / `job_set_type` prefix | Vendor | Status | Evidence |
|---|---|---|---|
| `seedance_*`, `seedream_*`, `bytedance_video_upscale` | **ByteDance** (Seed team) | **Confirmed (JS + landing)** | JS: `{vendor:"bytedance", models:["Seedance 2.0","Seedance 2.0 Fast & Mini","Seedream 5.0 Pro"]}`; "Seedream 4.5: ByteDance's next-gen 4K image-editing model"; "ByteDance Upscale". Landing: "Seedance 2.5 is an AI video model by ByteDance". JS also has a `video-seedance-2-5-cn` module and `prompt_language:"zh"` defaults (9 of 11 community posts) |
| `seed_audio` | ByteDance | **Confirmed (landing)** | "Use Seed Audio from ByteDance"; JS audio group lists "Seed Audio 1.0", "Seed Speech" |
| `kling*`, `kling_o3_*`, `kling_omni_*`, `kling_image_4_0` | **Kuaishou** (Kling) | Brand confirmed (JS `vendor:"kling"`, "Kling's Photorealistic Image Model"). **Kuaishou is inferred from the name**: neither the JS nor the landings say "Kuaishou" | Provider-style ids in JS: `model_name:"kling-v3"`/`"kling-v2-6"` (motion-control chain), `kling-v2-5-turbo`, `kling-v2-1-master`, `kling_element_ids` |
| `veo3*` | **Google** | **Confirmed (JS + landing)** | "Google Veo 3.1 … Google's advanced AI video model"; provider-style ids `veo-3-1-fast`, `veo-3-1-preview`, `veo-3-fast` |
| `gemini_omni*` | **Google** | **Confirmed (JS + landing)** | "Gemini Omni Flash: Multi-image video generation by Google"; vendor group `google` |
| `nano_banana*` | **Google** (Gemini image) | **Confirmed (JS + landing + API)** | "Nano Banana Pro: Google's flagship generation model"; landing "multimodal model developed by Google". **API:** `nano_banana_flash` jobs store `upstream_usage {input_tokens, output_tokens, thinking_tokens, input, output, thinking, total}` priced at $0.50 per 1M input tokens and $60 per 1M output tokens. The app job `outpaint` stores $2 / $120 / $12 per 1M (input / output / thinking). Both are Gemini-style token billing. `nano_banana_2_1` stores `{"value": 0.0597}` (USD per job) |
| `gpt_image_*`, `imagegen_2_0`, `openai_hazel*`, `text2image_gpt` | **OpenAI** | **Confirmed (API + landing)** | Every `gpt_image_2/2_5/2_6/2_6_flare` community job carries `upstream_usage {request_id:"req_<32 hex>", input_text_tokens, input_image_tokens, cached_*, output_image_tokens}`. That is the OpenAI Images API usage shape. `gpt_image_2_5` adds USD: 254 text tokens = $0.0013 ($5 per 1M). Landing: "Introducing GPT Image 2 by OpenAI", "Powered by OpenAI". Stored `params.model` holds internal codenames: `videotape-alpha` (GPT Image 2), `aurora-img-alpha` (2.6), `star-swirl-alpha` (2.6 Flare), and `flare`/`sunburst` (2.5). One 2.6 Flare input is typed `openai_hazel_job`. JS route alias: `imagegen_2_0 → /jobs/v2/gpt_image_2` |
| `sora2_video*` | **OpenAI** | **Confirmed (JS)**, but retired | `params.model` values `sora-2`, `sora-2-pro`, `sora-2-max`, `sora-2-pro-max` (OpenAI's API model naming). In the retired set |
| `wan*` | **Alibaba** (Tongyi Wan) | **Confirmed (JS + landing)** | Blog route `WAN-2.6-by-Alibaba`; landing "Wan 2.6 … from Alibaba Cloud". **Hosting hint (JS):** Wan 2.5 video and Wan 2.5 Speak forms keep `isAlibaba` and send `client_meta.use_alibaba`, so there are two backends, one of them Alibaba Cloud (Model Studio / DashScope; inferred). `wan2_2_animate_v2` model values `Wan2.2-animate-v2-mix` / `wan2.2-animate-v2-move` |
| `happy_horse_video` | **Alibaba** | **Confirmed (JS)** | "HappyHorse: Alibaba's #1 ranked video and audio model" |
| `qwen_audio_tts`, `qwen_camera_control` | Alibaba (Qwen) | **Name** ("Qwen Audio 3.0 TTS", "Qwen Camera Control") | Qwen is Alibaba's model family |
| `z_image` | Alibaba Tongyi (Z-Image) | **Name** | "Z-Image: Instant lifelike portraits" |
| `minimax_*` | **MiniMax** (Hailuo) | **Confirmed (JS + landing)** | "MiniMax H3", "Minimax Hailuo 02/2.3"; landing "Hailuo is MiniMax's video model family". `text2speech_v2` cost rows carry `model:"minimax"` / `"elevenlabs"` |
| `grok_*` | **xAI** | **Confirmed (JS + landing + API)** | "Grok Imagine 2.0: High-resolution image generation by xAI"; `grok_image_2_0` job `upstream_usage {"value":0.08}` (USD) |
| `flux_*` | **Black Forest Labs** | **Confirmed (JS + landing)** | "FLUX 3 Image: … by Black Forest Labs"; FLUX.2 Pro/Flex/MAX, Flux Kontext Max; "FLUX.3 Upscale" |
| `ideogram_*`, `p_image_ideogram` | **Ideogram** | **Confirmed (JS)** | "Ideogram 4.6: High-resolution image generation by Ideogram" |
| `recraft_*` | **Recraft** | **Confirmed (JS name)** | "Recraft V4.1", "Recraft V4.1 Utility", "Recraft V4 Styles" |
| `elevenlabs_*` | **ElevenLabs** | **Confirmed (JS + landing)** | "ElevenLabs v4", "Eleven v3"; `elevenlabs_video_to_music` cost rows `model_id: music_v1/music_v2` |
| `topaz_*`, `fps_boost` | **Topaz Labs** | **Confirmed (JS + API)** | JS maps UI names to Topaz model codes: `proteus:"prob-4"`, `artemis:"ahq-12"`, `iris:"iris-3"`, `rhea:"rhea-1"`, `gaia:"ghq-5"`, `theia:"thd-3"`, Starlight `slc-1`/`slf-1`/`slp-2.5`, frame interpolation `apo-8`. Community `topaz_image` params `model:"High Fidelity V2"`, `"Redefine"`. `fps_boost` cost rows `model:"topaz"` |
| `magi_2` | **Sand AI** | **Confirmed (JS)** | "MAGI: Sand AI video from text, frames or references, with sound" |
| `sam_3_video` | Meta (SAM 3) | **Name** | |
| `depth_anything_video` | Depth Anything (open model from ByteDance/HKU researchers) | **Name** | |
| `reve` | Reve | **Name** | |
| `sync_so` | Sync Labs | **Name** | Lipsync picker |
| `infinite_talk` | MeiGen InfiniteTalk (open model) | **Name** | |
| `mirelo_text_to_audio`, `sonilo_music`, `inworld_text_to_speech` | Mirelo, Sonilo, Inworld | **Name** (enum only) | |
| Canvas `llm` node | **OpenRouter** (Anthropic / OpenAI / Google models) | **Confirmed (JS)** | "Generate text via an LLM (OpenRouter)."; model list `anthropic/claude-sonnet-4.6` (default), `anthropic/claude-opus-4.7`, `openai/gpt-5.5`, `google/gemini-3.1-pro-preview` … |
| `text2image_soul*`, `soul_*`, `image2video` (DoP), `hf_*`, `cinematic_studio_*`, `videoshop_*`, `marketing_studio_*`, `ai_influencer*`, `reframe`, `viral_hub_video`, … | **Higgsfield** | **in-house** | See the price-twin notes per product |

**Hosting / inference layer.** The bundle has no fal.ai, Replicate, BytePlus/ModelArk, Volcengine or Vertex
endpoints. Every job goes through Higgsfield's own `fnf-api-gw`. The only explicit hosting switch is
`use_alibaba` (Wan 2.5). Usage records show direct vendor billing shapes for OpenAI (request ids `req_…`), Google
Gemini (token buckets with thinking tokens) and xAI (`value` in USD). Seedance, Kling and Soul jobs store no
`upstream_usage`.

---

## 3. Products

Each product section lists the UI flow, the job types, the models, gating, cost and worked examples. Every endpoint
and body is **(from JS, not called)**. Credits are computed with the live 2026-11-26 table and the formulas in
[`COST_FORMULAS.md`](COST_FORMULAS.md).

### 3.1 Video generator (`/ai/video`)

**What it does and how the UI flows.** The model picker comes from a hard-coded menu tree in the JS. The page
picks a mode from its path:

- `/ai/video` → create;
- `/ai/video/edit` → edit/extend;
- `/ai/video/motion` → motion control;
- `/ai/video/reframe` → reframe;
- `/ai/video/agent` → agent.

The flow is: prompt and media, then settings, then the live credit estimate from `/job-sets/costs` × the JS
formula, then upload (`POST /media/batch` + PUT), then `POST /jobs/v2/{type}`, then poll with
`POST /jobs/status-batch`.

**Models.** The default is `seedance_2_5` (`zx` in `tCLaulKUdGQfxqgZ.js`). Featured order:

- Seedance 2.5 / Flash / Draft;
- MAGI-2;
- Genjutsu;
- Kling 4.0 / 4.0 Flash;
- Gemini Omni Flash 1.2;
- Wan 4.0 / 3.0 Prime;
- Seedance edit variants;
- Seedance 2.0 / Fast / Mini;
- MiniMax H3 / Max / Highspeed / Lite;
- FLUX 3 Video;
- Grok Imagine 1.5 Lite / 1.5.

Picker ids map to job types like this:

| Picker id | `job_set_type` + extra param | Provider |
|---|---|---|
| `seedance_2_5`, `seedance_2_5_draft`, `seedance_2_5_edit`, `seedance_2_5_extend` | `seedance_2_5` + `model: default / video_edit / video_extension` (+ `draft:true`) | ByteDance |
| `seedance_2_5_flash(_edit/_extend)` | `seedance_2_5_flash` | ByteDance |
| `seedance_2_0`, `seedance_2_0_fast` | `seedance_2_0` + `model: seedance_2_0 / seedance_2_0_fast` | ByteDance |
| `seedance_2_0_mini`; `seedance_unlimited`, `seedance_mini_unlimited`, `seedance_2_unlimited` | own types (unlimited-plan variants) | ByteDance |
| `kling4_0`, `kling_4_0_flash`, `kling3_0`, `kling3_0_turbo`, `kling_o3_flf` / `kling_o3_image_reference` ("Kling 3.0 Omni"), `kling2_6` | same id | Kuaishou |
| `wan3_0`, `wan3_0_prime`, `wan4_0` (flag off), `wan2_7`, `wan2_6`, `wan2_5_video` (`mode: regular / fast`) | same id | Alibaba |
| `minimax_h3(_max/_highspeed/_lite)`; legacy `minimax` (Hailuo 02/2.3) → `minimax_hailuo` | same id | MiniMax |
| `grok_video_v15(_lite)`, `grok_video`, `grok-video-edit` | `grok_video*` | xAI |
| `gemini-omni-flash-1-2` (+ `_edit`, `_extend`) | `gemini_omni_flash_1_2` | Google |
| `veo-3-1-lite` (legacy plans only), `veo-3-1-fast`, `veo-3-1-preview` | `veo3_1_lite`, `veo3_1` + `model` | Google |
| `magi_2` | `magi_2` | Sand AI |
| `happy-horse` | `happy_horse_video` | Alibaba |
| `flux_3_video` | `flux_3_video` | BFL |
| `lite`, `standard`, `turbo` ("Higgsfield DoP") | `image2video` + `model: lite / standard / turbo` | Higgsfield |

**Gating.** Hashed feature flags in `__HF_FF` control three models: Seedance 2.5 Flash `f_24c5dcf4` (on),
Kling 4.0 Flash `f_3a0922bf` (on) and Wan 4.0 `f_6a87092e` (off). The plan table `video-model-plans` sets:

- `seedance_2_5` and `seedance_2_5_flash`: PREMIUM (pro, ultimate, creator, plus, ultra, max);
- `kling3_0`, `kling4_0`, `magi_2`, `wan3_0`, `seedance_2_0_fast`: PAID;
- `minimax_h3`: ALL.

A plan that can't use a model still sees it and gets an upsell. Retired ids redirect to `seedance_2_5` (see §5).

**Model-specific params (wire).**

- **Seedance 2.5:** `duration` 4–30, `resolution` 480p/720p/1080p/4k, `aspect_ratio`, `generate_audio`,
  `bitrate_mode`, `batch_size` 1–4, `seed`, `model`, `extension_mode`, `draft`, `draft_job_id`,
  `draft_upscale_model` (`seedance_2_5` or `kling4_0`), and `medias[]` with roles `image` / `start_image` /
  `end_image` / `video` / `audio`. Limits: 30 images, 10 videos, 10 audios (Flash: 10/5/5).
- **Kling 3.0:** `mode` std/pro/4k, `sound` on/off, `duration` 3–15, `multi_shots`, `multi_prompt[]`,
  `kling_element_ids`.
- **Wan 2.5:** `mode` regular/fast, `client_meta.use_alibaba`.
- **MAGI-2:** `enhance_prompt`, `generate_audio`, `duration`, `resolution`.

#### Examples: Seedance 2.5 (`seedance_2_5`, ByteDance; endpoint `POST /jobs/v2/seedance_2_5`)

| # | UI choice | Key params | Credits |
|---|---|---|---:|
| 1 | Text-to-video, 1080p, 5 s, 16:9 | `model:"default"`, `medias:[]` | ceil(5×16) = **80** |
| 2 | Image-to-video, start + end frame, 720p, 10 s | `medias:[start_image, end_image]` (a start/end frame forces the `without_video` row) | ceil(10×7) = **70** |
| 3 | Reference video + prompt, 4k, 10 s | `medias:[{role:"video"}]` (`with_video` row) | ceil(10×34) = **340** |
| 4 | Edit an 8 s clip at 1080p | `model:"video_edit"`, 1 video, no `duration`/`aspect_ratio` | ceil(8×20) = **160** |
| 5 | Extend forward 10 s at 1080p | `model:"video_extension"`, `extension_mode:"forward"`, 1 video | ceil(10×16) = **160** (`with_video` row; at 1080p it equals `without_video`) |
| 6 | Draft (cheap preview), 720p, 10 s | `draft:true` | `/job-sets/costs` has no draft row. The client formula gives ceil(10×7) = 70; whether the server discounts drafts is **unknown** |
| 7 | Upscale a draft | `draft_job_id:"<job-id>"`, `draft_upscale_model:"seedance_2_5"` (or `"kling4_0"`) | Not determinable offline |
| 8 | Seedance 2.5 **Flash**, 720p, 10 s, text only (`/jobs/v2/seedance_2_5_flash`) | as #1 | ceil(10×5) = **50** |

Example 1 as a request body (from JS, not called):

```json
POST /jobs/v2/seedance_2_5
{"params": {"prompt": "a lighthouse in a storm, slow push-in", "medias": [], "model": "default",
  "duration": 5, "resolution": "1080p", "aspect_ratio": "16:9", "width": 1920, "height": 1080,
  "generate_audio": true, "bitrate_mode": "high", "batch_size": 1, "use_unlim": false},
 "use_unlim": false}
```

Example 2, the `medias` part:

```json
"medias": [{"role": "start_image", "data": {"id": "<media-id>", "type": "media_input", "url": "https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/<media-id>.png"}},
           {"role": "end_image",   "data": {"id": "<media-id>", "type": "media_input", "url": "https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/<media-id>.png"}}]
```

Example 4, edit: `{"model": "video_edit", "medias": [{"role": "video", "data": {"id": "<media-id>", "type": "media_input", "url": "…mp4"}}], "resolution": "1080p", "prompt": "make it night"}`

Example 5, extend: `{"model": "video_extension", "extension_mode": "forward", "duration": 10, "medias": [{"role": "video", …}]}`

Example 6, draft: `{"model": "default", "draft": true, …}`. Example 7, upscale a draft: `{"draft_job_id": "<job-id>", "draft_upscale_model": "seedance_2_5", …}`

**A real community `params` object** (image reference, 1080p, 15 s; prompt cut):

```json
{"width": 1920, "height": 1080, "prompt": "<<<image_1>>> … Camera Settings: shot on 35mm film, anamorphic …",
 "genre": "auto", "medias": [{"data": {"id": "<media-id>", "url": "https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/<media-id>.png", "type": "media_input"}, "role": "image"}],
 "duration": 15, "resolution": "1080p", "aspect_ratio": "16:9", "generate_audio": true, "multi_shots": false,
 "multi_shot_mode": "custom", "multi_prompt": [], "speedramp": "auto", "reference_elements": [], "prompt_language": "zh",
 "model": "default", "extension_mode": null, "bitrate_mode": "high", "draft": false, "seed": null, "draft_job_id": null}
```

Cost: ceil(15×16) = **240** credits.

#### Examples: other video models

| UI choice | `job_set_type` / endpoint | Params (key) | Credits | Provider |
|---|---|---|---:|---|
| Kling 3.0 Pro, sound on, 10 s | `kling3_0` → `/jobs/v2/kling3_0` | `{"mode":"pro","sound":"on","duration":10,"aspect_ratio":"16:9","multi_shots":false}` | 10 × 2.5 = **25** | Kuaishou |
| Kling 3.0 4K, 5 s | same | `{"mode":"4k","sound":"off","duration":5}` | 5 × 6 = **30** | Kuaishou |
| Kling 4.0, 1080p, 10 s, text only | `kling4_0` → `/jobs/v2/kling4_0` | `{"resolution":"1080p","duration":10}` | ceil(10 × 3.75) = **38** (HDR row 4.5/s → 45) | Kuaishou |
| Kling 4.0 Flash, 720p, 5 s | `kling_4_0_flash` | `{"resolution":"720p","duration":5}` | ceil(5 × 1.5) = **8** | Kuaishou |
| Wan 3.0, 1080p, 10 s, no video input | `wan3_0` → `/jobs/v2/wan3_0` | `{"resolution":"1080p","duration":10}` | 10 × 3 = **30** (with a video input: 60) | Alibaba |
| MiniMax H3 Lite, 768p, 6 s | `minimax_h3_lite` | `{"resolution":"768p","duration":6}` | ceil(6 × 1.25) = **8** | MiniMax |
| Grok Imagine 1.5, 720p, 8 s | `grok_video_v15` | `{"resolution":"720p","duration":8}` | 8 × 4.5 = **36** | xAI |
| Gemini Omni Flash 1.2, 1080p, 8 s | `gemini_omni_flash_1_2` | `{"resolution":"1080p","duration":8}` | 0 + 8 × 3.25 = **26** | Google |
| MAGI-2, 1080p, 15 s, 9:16, 2 reference images (real community params) | `magi_2` → `/jobs/v2/magi_2` | `{"duration":15,"resolution":"1080p","aspect_ratio":"9:16","generate_audio":true,"enhance_prompt":false,"batch_size":1,"medias":[{"role":"image",…},{"role":"image",…}]}` | Not in `/job-sets/costs`; JS `estimateCost` has its own `magi_2` formula ([`COST_FORMULAS.md`](COST_FORMULAS.md)) | Sand AI |
| HappyHorse, 1080p, 5 s | `happy_horse_video` | `{"resolution":"1080p","duration":5}` | ceil(5 × 4.5) = **23** | Alibaba |

### 3.2 Image generator (`/ai/image`)

**What it does.** A model picker with per-model forms. The default is GPT Image 2.6 (the `gpt-image-2-6-*`
modules). Common params are `prompt`, `aspect_ratio`, `resolution` (1k/2k/4k), `batch_size` 1–4 and
`medias[]` (role `image`). Older types use `input_images[]` instead. `reference_elements[]` holds saved
"elements" such as a character face. The price is per image: `credits(quality, resolution) × batch`.

| Picker title | `job_set_type` | Route | Provider | Notes |
|---|---|---|---|---|
| GPT Image 2.6 (Sunburst) | `gpt_image_2_6` | `/jobs/v2/gpt_image_2_6` | OpenAI (API) | quality low/medium/high/xhigh/max; backend `model:"aurora-img-alpha"` |
| GPT Image 2.6 Flare | `gpt_image_2_6_flare` | `/jobs/v2/gpt_image_2_6_flare` | OpenAI | `model:"star-swirl-alpha"` |
| GPT Image 2.5 | `gpt_image_2_5` | `/jobs/v2/gpt_image_2_5` | OpenAI | `model: flare / sunburst`; up to 16 refs, min side 300 px, aspect 0.4–2.5 |
| GPT Image 2 | `gpt_image_2` (alias `imagegen_2_0`) | `/jobs/v2/gpt_image_2` | OpenAI | quality low/medium/high; `model:"videotape-alpha"` |
| Nano Banana 2.1 | `nano_banana_2_1` | `/jobs/v2/nano_banana_2_1` | Google | `thinking_level`, `enable_web_search`, `enable_image_search` |
| Nano Banana 2 | `nano_banana_flash` | `/jobs/v2/nano_banana_flash` | Google | |
| Nano Banana Pro | `nano_banana_2` | `/jobs/nano-banana-2` | Google | `input_images[]`, `application`, `surface` |
| Nano Banana 2 Lite / Nano Banana | `nano_banana_2_lite` / `nano_banana` | v2 / legacy | Google | |
| Seedream 5.0 Pro / 5.5 / 5.0 Flash / 5.0 lite / 4.5 | `seedream_v5_pro`, `seedream_5_5`, `seedream_5_0_flash`, `seedream_v5_lite`, `seedream_v4_5` | `/jobs/v2/…`; 4.5 → `/jobs/seedream-v4-5` | ByteDance | 4.5/lite: `quality` basic/high/ultra |
| FLUX.2 Pro / Flex / MAX, FLUX 3 Image, Flux Kontext Max | `flux_2` (`model: pro / flex / max`), `flux_3_image`, `flux_kontext` | | BFL | `steps`, `cfg` |
| Ideogram 4.6 / 4.5 (+ Precise Edit), Vector | `ideogram_4_6`, `ideogram_4_5(_precise_edit)`, `ideogram_vector` | | Ideogram | |
| Recraft V4.1 / Utility / Styles | `recraft_v4_1` (`model_type`), `recraft_v4_styles` | | Recraft | |
| Grok Imagine 2.0 | `grok_image_2_0` | `/jobs/v2/grok_image_2_0` | xAI | `mode`, `quality` |
| Kling Image 4.0 / Kling O1 | `kling_image_4_0`, `kling_omni_image` | | Kuaishou | up to 8k |
| MiniMax H3 Image | `minimax_h3_image` | | MiniMax | |
| Z-Image | `z_image` | | Alibaba Tongyi (name) | |
| Auto | `image_auto` | `/jobs/v2/image_auto` | Server picks the model; which one is **unknown** (one community post reused a previous `nano_banana_2_job` output as input, which proves nothing) | |

**Gating.** Per-model access flags (`access-image-seedream-v5-pro` etc.) and plan tables. The "unlimited"
variants `gpt_image_2_unlimited` and `nano_banana_pro_unlimited` come with unlimited bundles.

#### Examples: GPT Image (OpenAI; credits per image from `/job-sets/costs`)

**GPT Image 2.6** (`gpt_image_2_6`) by quality and resolution:

| quality | 1k | 2k | 4k |
|---|---:|---:|---:|
| low (default) | 0.75 | 1.25 | 1.75 |
| medium | 1 | 1.75 | 2.75 |
| high | 1.25 | 2 | 3.25 |
| xhigh | 2 | 3.5 | 5.5 |
| max | 4.5 | 7 | 12 |

**GPT Image 2** (`gpt_image_2`):

| quality | 1k | 2k | 4k |
|---|---:|---:|---:|
| low | 0.5 | 0.5 | 0.75 |
| medium | 1.25 | 2 | 3.5 |
| high | 3.5 | 7 | 12 |

**GPT Image 2.5** (`gpt_image_2_5`): Flare is 0.25 (low 1k) to 12 (max 4k), Sunburst 0.5 to 12. The live table
is discounted from `original_credits` (Flare low 1k: 0.25 instead of 1).

| UI choice | Body (from JS, not called) | Credits |
|---|---|---:|
| **Text-to-image**, GPT Image 2.6, high, 2k, 9:16, batch 1 | `POST /jobs/v2/gpt_image_2_6` `{"params":{"prompt":"…","aspect_ratio":"9:16","quality":"high","resolution":"2k","background":"auto","batch_size":1,"medias":[],"width":1520,"height":2688}}` | **2** |
| Same at **max** quality (a real community post: `quality:"max"`, `resolution:"2k"`, `model:"aurora-img-alpha"`) | as above with `"quality":"max"` | **7** |
| **Edit with 3 reference images**, 2.6, high, 2k (real community post) | `"medias":[{"role":"image","data":{"id":"<media-id>","type":"media_input","url":"…/user_<redacted>/<media-id>_resize.jpg"}} ×3]` | **2** (refs don't change the price) |
| GPT Image 2.6 **Flare**, medium, 1k, 2 refs | `/jobs/v2/gpt_image_2_6_flare` `{"quality":"medium","resolution":"1k","aspect_ratio":"27:16",…}` | **1** |
| GPT Image 2.5 Flare, **low**, 1k (default, community) | `/jobs/v2/gpt_image_2_5` `{"model":"flare","quality":"low","resolution":"1k","aspect_ratio":"1:1"}` | **0.25**; upstream was $0.0072 (254 text + 196 image tokens) |
| GPT Image 2.5 Sunburst, high, 1k, 1 ref, `aspect_ratio:"auto"` (community) | `{"model":"sunburst","quality":"high","resolution":"1k","medias":[{"role":"image",…}]}` | **1.25** |
| GPT Image 2, **low**, 2k, 16:9 (community) | `/jobs/v2/gpt_image_2` `{"quality":"low","resolution":"2k"}` | **0.5** |
| GPT Image 2, **medium**, 1k | `{"quality":"medium","resolution":"1k"}` | **1.25** |
| GPT Image 2, **high**, 4k, edit with 2 refs (community) | `{"quality":"high","resolution":"4k","aspect_ratio":"auto","medias":[2 images]}` | **12** |

A stored GPT Image 2.6 job, redacted:

```json
{"width": 1520, "height": 2688, "prompt": "…", "medias": [], "aspect_ratio": "9:16", "quality": "max", "resolution": "2k",
 "model": "aurora-img-alpha", "remove_bg": false, "reference_elements": [], "background": "auto", "output_format": "png"}
// upstream_usage: {"request_id": "req_…", "input_text_tokens": 236, "input_image_tokens": 1505, "output_image_tokens": 2743, …}
```

#### Examples: other image models

| UI choice | `job_set_type` | Key params | Credits | Provider |
|---|---|---|---:|---|
| Nano Banana 2.1, 4k, edit with 2 refs, `thinking_level:"medium"` (community) | `nano_banana_2_1` | `{"resolution":"4k","aspect_ratio":"16:9","medias":[2],"thinking_level":"medium","enable_web_search":false}` | **3** (upstream ≈ $0.06) | Google |
| Nano Banana 2.1, 1k, batch 2 | same | `{"resolution":"1k","batch_size":2}` | 1.5 × 2 = **3** | Google |
| Seedream 5.0 Pro, 2k, text only (community) | `seedream_v5_pro` | `{"resolution":"2k","aspect_ratio":"3:4","seed":296119,"is_inpaint":false}` | **2.5** | ByteDance |
| Seedream 5.5, 1k | `seedream_5_5` | `{"resolution":"1k"}` | **2.5** | ByteDance |
| Ideogram 4.6, high, 2k, no refs | `ideogram_4_6` | `{"quality":"high","resolution":"2k"}` | **3.25** | Ideogram |
| Recraft V4.1 vector, 2k | `recraft_v4_1` | `{"model_type":"vector","resolution":"2k"}` | **10** | Recraft |
| Kling Image 4.0, 8k | `kling_image_4_0` | `{"resolution":"8k"}` | **5** | Kuaishou |
| FLUX.2 Pro, 2k, 1 ref (community) | `flux_2` | `{"model":"pro","resolution":"2k","steps":30,"cfg":5.0,"input_images":[1]}` | Not in `/job-sets/costs` (client fallback table) | BFL |
| Grok Imagine 2.0, 2k, medium (community) | `grok_image_2_0` | `{"mode":"std","quality":"medium","resolution":"2k"}` | Not in costs; upstream $0.08 | xAI |

### 3.3 Soul, Soul ID and characters

**What it does.** Higgsfield's own photo model. Soul 2.0 (`text2image_soul_v2`) is the default. Soul Cinema
(`soul_cinematic`) has camera-model and lens controls. Legacy Soul is `text2image_soul`. Styles come from
`/soul-styles` (login); the public preview list is `/soul-samples`. **Soul ID** trains a consistent person from
uploads (about 3 minutes, per the landing). The result is passed as `custom_reference {name, url, strength}`.
Characters, Cast and Location (`soul_cast`, `soul_location`, `cinematic_studio_soul_cast`,
`cinematic_studio_soul_location`) build reusable people and places for Cinema Studio.

**Provider: Higgsfield in-house.** The Soul params expose a diffusion-style backend:

- `steps`, `sample_shift`, `sample_guide_scale`;
- `use_sage_attention` (SageAttention, an attention kernel used with video/DiT models);
- `use_refiner`, `use_relax`;
- `use_green` / `use_green_aidar`;
- dev variants "Soul Cinematic Aidar/Olzhas/Sultan".

The base model isn't named anywhere. Soul jobs store no `upstream_usage`.

**Cost.** Not in `/job-sets/costs`. The `defineJob` has `credits = batchSize × 0.125` (unit unclear; see
[`COST_FORMULAS.md`](COST_FORMULAS.md)).

| UI choice | Endpoint | Real community params (redacted) |
|---|---|---|
| Soul 2.0, General style, 720p, batch 2, Soul ID reference | `/jobs/v2/text2image_soul_v2` | `{"width":1152,"height":1536,"batch_size":2,"quality":"720p","enhance_prompt":false,"use_sage_attention":false,"use_relax":false,"use_refiner":false,"use_green":true,"style_id":"<style-id>","style_strength":1.0,"custom_reference":{"id":null,"name":"<soul-id name>","url":"…/user_<redacted>/<media-id>.png","strength":1.0}}` |
| Soul Cinema, "Modern" camera, 1080p, batch 2 | `/jobs/v2/soul_cinematic` | `{"width":2048,"height":1152,"batch_size":2,"quality":"1080p","enhance_prompt":true,"style":{"name":"General"},"camera_model":{"name":"Modern","type":"camera_model"}}` |
| Legacy Soul, 50 steps, batch 4 | `text2image_soul` | `{"steps":50,"sample_shift":4.0,"sample_guide_scale":4.0,"quality":"1080p","batch_size":4,…}` |
| Soul Location (Cinema Studio), 35mm Film + Vintage Anamorphic | `cinematic_studio_soul_location` | `{"full_name":"<location name>","camera_model":{"name":"35mm Film"},"camera_lens":{"name":"Vintage Anamorphic"},"batch_size":1}` |

### 3.4 Cinema Studio (`/cinema-studio`)

**What it does.** A director-style UI with these controls:

- Genre, era, pacing and lighting presets;
- camera body, lens and aperture;
- color palette;
- multi-shot prompts.

It produces video (4.0, 3.5, 3.0 = `hf_fnf_video`, and v2 = "Cinema Studio 2.5") and images
(`cinematic_studio_image`, `_image_grid`, `_2_5`, 3D recomposition, Soul Cast/Location). Version 4.0 supports
edit and extend through the same `model:"video_edit"` / `"video_extension"` switch as Seedance 2.5.

**Model.** Higgsfield product **over Seedance**. The landing says "Seedance and other leading video models run
natively inside Cinema Studio 4". The `cinematic_studio_video_4_0` cost table is identical to `seedance_2_5`'s
(3/7/16/28, 34 with video). The JS schema is Seedance-like: same media limits (30/10/10), `prompt_language`
en/zh, and batch 1–4. Inferred: 4.0 runs on Seedance 2.5. Cinema Studio 3.0/3.5 (3.5/5/13/24 cr/s) sit close
to Seedance 2.0 (3/4.5/12/22) with a markup (inferred).

**Gating.** `cinematic_studio_video_4_0`: PREMIUM plans.

| UI choice | Endpoint | Params | Credits |
|---|---|---|---:|
| 4.0, 1080p, 10 s, genre + camera + lens | `/jobs/v2/cinematic_studio_video_4_0` | `{"prompt":"…","duration":10,"resolution":"1080p","aspect_ratio":"21:9","genre_id":"<cms-id>","camera_model_id":"<cms-id>","camera_lens_id":"<cms-id>","light_id":"<cms-id>","color_palette":null,"prompt_language":"en","medias":[]}` | 10 × 16 = **160** |
| 4.0 edit of a 6 s clip, 720p | same, `"model":"video_edit"` | | 6 × 7 = **42** |
| 3.0 video, 1080p, 5 s | `/jobs/v2/cinematic_studio_3_0` | | 5 × 13 = **65**. The enum also maps `CINEMATIC_STUDIO_3_0 = hf_fnf_video` (labelled "Cinema Studio 3.0 Video"), which has no cost row |

### 3.5 Camera motions and DoP (`/motion`)

**What it does.** 419 public motion presets: higgsfield 229, minimax 77, kling 56, seedance 25, wan2_2 17,
wan2_5 15. They come in two kinds:

- **(a) Higgsfield DoP.** `image2video` with `model: lite / standard / turbo` and a `motion_id` from
  `/motions?preset_family=higgsfield`. Picker titles: "Higgsfield Lite/Standard/Turbo". `.safetensors` LoRA
  presets show as "Higgsfield Canary". `image2video_mix` blends two motions (`mix`).
- **(b) Vendor preset families.** The preset is applied to that vendor's own job type, e.g. a Kling motion runs
  on `kling*` and a MiniMax motion on `minimax_hailuo` (motion assets live under `kling_motion/…` and
  `minimax_hailuo_motion/…`).

**Provider.** (a) Higgsfield in-house (inferred from `steps` and `frames` 49/81). (b) The vendor of the target
model.

**Cost (client formula, JS).**

- Lite: 3 credits (49 frames) or 5 credits (81 frames).
- Standard: ceil((24·s + 200)/100) or ceil((35·s + 300)/100).
- Turbo: ceil((7·s + 280)/100) or ceil((10·s + 400)/100).

`s` is the step count. Full formulas: [`COST_FORMULAS.md`](COST_FORMULAS.md).

| UI choice | Body | Credits |
|---|---|---:|
| Higgsfield Lite, any public motion, 81 frames | `POST /jobs/image2video` `{"params":{"model":"lite","motion_id":"<motion-id>","frames":81,"strength":1,"seed":…,"input_image":{…}}}` | **5** |
| Higgsfield Standard, 30 steps, 49 frames | `{"model":"standard","steps":30,"frames":49,…}` | ceil(920/100) = **10** |
| Kling motion preset on Kling 2.5 Turbo | `kling` job with the preset's motion/prompt | Kling price |

### 3.6 Motion control and Genjutsu (`/ai/video/motion`, `/genjutsu`)

**What it does.** Takes a driving video plus a character image (plus an optional location) and transfers the
motion, or replaces an object. There are two UI modes:

- `motion-control`: roles `image`, `location`, `video`;
- `replace-object`: roles `video`, `image`.

Settings: `resolution`, `batch_size`, `aspect_ratio`, `scene_mode`, `location_character_media_id`.

| Picker | `job_set_type` | Provider |
|---|---|---|
| Higgsfield Genjutsu | `hf_mult_motion_control`, `hf_mult_replace_object` | Higgsfield. JS has an optional `use_magi_2` flag, so the backend can be **Sand AI MAGI-2** (confirmed switch; default backend unknown) |
| Genjutsu Lite / Flash (up to 10 reference images) | `hf_mult_motion_control_flash`, `hf_mult_replace_object_flash` | Higgsfield |
| Kling 3.0 Motion Control | `kling3_0_motion_control` (also `/chains/motion-control` with `model_name:"kling-v3"`) | Kuaishou |
| Kling Motion Control (2.6) | `kling2_6_motion_control` (`model_name:"kling-v2-6"`) | Kuaishou |
| AI Influencer variants | `ai_influencer_motion_control(_flash)`, `ai_influencer_replace_object(_flash)` | Higgsfield (price twins of Genjutsu) |

| UI choice | Endpoint | Credits |
|---|---|---:|
| Genjutsu motion transfer, 720p, 8 s source | `POST /jobs/v2/hf_mult_motion_control` `{"prompt":"","medias":[{"role":"video",…},{"role":"image",…}],"resolution":"720p","batch_size":1}` | 8 × 7 = **56** |
| Genjutsu Flash, 1080p, 10 s | `hf_mult_motion_control_flash` | 10 × 4 = **40** |
| Kling 3.0 Motion Control pro, 10 s | `/jobs/v2/kling3_0_motion_control` `{"mode":"pro",…}` | 10 × 2.5 = **25** |

### 3.7 Effects and the viral hub (`/effects`, `/viral-effects`)

**What it does.** 87 public presets (`GET /viral-hub/presets/all`). Each preset is a **node graph**
(`kind:"chain"`):

- `inputs[]` are bound to node ports (`input_images` 60×, `image_references` 25×);
- `param_choices` exposes the video node's `resolution` / `aspect_ratio`;
- `price_matrix` is keyed by `"<node>.<param>=<value>,…"`.

The job type is always `viral_hub_video`, sent to `POST /chains/viral-hub {params:{preset_id, medias, …}}`.

**Models.** The node model ids are opaque UUIDs. The implied per-second rates (`credit_units/100/duration`)
cluster as follows:

- 10 presets: 1 / 2.5 cr/s (480p/720p). Exactly **Seedance 2.0 Fast** (`seedance_2_0_fast` row).
- 16 presets: 3 / 4.5 / 9 / 22 cr/s. Close to **Seedance 2.0** (3/4.5/12/22).
- 13 presets: 3 / 7 / 12 cr/s.

These are price fingerprints only (inferred).

| UI choice | Body | Credits |
|---|---|---:|
| `floating-fall`, default (720p 9:16, 12 s) | `POST /chains/viral-hub` `{"params":{"preset_id":"<preset-id>","medias":[…one per preset input…]},"use_free_gens":false}` (exact media item shape not pinned down) | 8400/100 = **84** |
| `floating-fall`, 16:9 1080p | `+ param choices {node.resolution:"1080p", node.aspect_ratio:"16:9"}` | **144** |
| `floating-fall`, 16:9 480p | | **36** |

### 3.8 Apps (`/apps/{slug}`)

**What it does.** 92 apps. Each app is a thin form over a fixed template:
`POST /workflows {width, height, params:[{id,value}], application_slug, application_template_slug}`. The price
is the template's static `cost`.

**Models.** The site scraper's `slug_type` gives the family per app:

- **63 apps are `nano_banana`** (Google). Their image template costs 1–2 cr. The video template (6–26 cr) runs
  an undisclosed video model.
- The JS table `app-slug-type-jobsets` maps the special apps to job types:

| App slug | `job_set_type` | Provider | Template cost (cr) |
|---|---|---|---:|
| `ai-headshot-generator` | `headshot` | not disclosed | 1 |
| `expand-image` | `outpaint` | **Google Gemini image (API):** stored usage has input / output / **thinking** token prices of $2 / $120 / $12 per 1M, matching Gemini 3 Pro Image published rates (inferred). Separately, `flux_2_pro_outpaint` exists in the enum | 2 |
| `face-swap`, `commercial-faces`, `style-snap`, `animal-clone`, `recast` | `keyframes_faceswap` (route `/jobs/face-swap`), `nano_banana_animal` | Higgsfield / Google | 2 |
| `video-face-swap`, `fans-studio` | `wan2_2_animate_faceswap`, `wan2_2_animate_v3` | **Alibaba Wan 2.2 Animate** (job type name; the `wan-animate-ai-video` landing says "Powered by the revolutionary Wan 2.2 Animate model") | 25 |
| `character-swap` | `character_swap_v2` (`/jobs/character-swap/v2`) | Higgsfield | 2 |
| `angles` (`qwen-camera-control`) | `qwen_camera_control` | Alibaba Qwen (name) | 1 |
| `transitions` | `kling_transition` | Kuaishou | 10 |
| `relight` | `nano_banana_2_relight` | Google | 0 |
| `ai-stylist` | `nano_banana_2_ai_stylist` (`/jobs/nano-banana-2-ai-stylist`) | Google | — |
| `sticker-matchcut`, `beatfit` (`urban-cuts`), `outfit-matchcut` (`clipcut`) | `sticker_matchcut`, `beat_fit` (`/chains/beat-fit-nano-banana`), `outfit_matchcut` | Google (image steps) + chain | 15–25 |
| `plushies` | `viral_transform_video/_image` | not disclosed | 25 |
| `game-dump` | `game_dump` | not disclosed | 2 |
| `image-background-remover`, `video-background-remover` | `image_background_remover`, `video_background_remover` | not disclosed | 1 |
| `skin-enhancer`, `shots`, `zooms` | `nano_banana_2_skin_enhancer`, `nano_banana_2_shots`, `nano_banana_2_zooms` (enum) | Google | — |

| UI choice | Body (from JS, not called) | Credits |
|---|---|---:|
| `3d-figure`, image template | `POST /workflows {"application_slug":"3d-figure","application_template_slug":"3d-figure-image","params":[{"id":"<input-id>","value":"<media-id>"}],"width":…,"height":…}` | **1** |
| `3d-figure`, video template | `…"application_template_slug":"3d-figure-video"` | **15** |
| `face-swap` → `video-face-swap` template | | **25** |

### 3.9 Mixed media (`/mixed-media`)

33 public presets (colour and texture overlays such as "Ocean: Liquid sea color overlay"). All 142 samples are
`job_set_type: "mixed_media"`. Preview: `mixed_media_preview` via `POST /chains/mixed-media-preview`; final:
`POST /chains/mixed-media`. The preset config (`/mixed-media/configs?preset_id=`) needs a login. Input video:
mp4/mov, ≤ 10 s, ≤ 50 MB, aspect ratio 1/3 to 3. **Provider:** Higgsfield chain; the underlying models are
unknown. **Cost:** not in `/job-sets/costs`.

Example: `POST /chains/mixed-media {"params":{"preset_id":"<preset-id>","medias":[{"role":"video","data":{"id":"<media-id>",…}}]}}`.
The credits are unknown.

### 3.10 Lipsync, Speak and talking avatars (`/lipsync-studio`, `/speak`)

The picker (`speak-group-select-items`) has two groups:

| Group | Picker title | id / `job_set_type` | Tags | Provider |
|---|---|---|---|---|
| image-to-video | Kling 2.6 Lipsync | `kling-2-6-lipsync` / `kling2_6_lipsync` | 1080p · Audio · 10s | Kuaishou |
| | Wan 2.5 Speak / Wan 2.5 Speak Fast | `speak-wan-2.5(-fast)` / `wan2_5_speak` (`mode: regular / fast`, `client_meta.use_alibaba`) | 480p–1080p · 10s | Alibaba |
| | Kling Avatars 2.0 | `kling-speak` | 720p–1080p · 5m | Kuaishou |
| | Higgsfield Speak 2.0 | `speak-hf-v2` | 720p · 15s | Higgsfield |
| | Infinite Talk | `infinite_talk` | 480p–720p · 15s | MeiGen InfiniteTalk (name) |
| video-to-video | Kling Lipsync | `kling-lipsync` | | Kuaishou |
| | Sync | `sync_so` | | Sync Labs (name) |
| (legacy) | Veo 3 / 3.1 Speak | `veo3_speak`, `veo3_1_speak` (retired) | | Google |

Inputs are an image or video plus an audio upload (`POST /audio`, wav/mp3/webm) or a TTS voice. Prices are not in
`/job-sets/costs`: they come from the per-model CMS notice badges and server quotes (unknown offline).

Example (from JS, not called):
`POST /jobs/wan2-5-speak` with `params {mode:"fast", resolution:"720p", duration:10, <image + audio media>}` and `client_meta.use_alibaba` (field names for the media not pinned down).

### 3.11 Audio, TTS, voice change and dubbing

| Product | `job_set_type` | Provider | Live cost |
|---|---|---|---|
| TTS (VoiceLab) | `text2speech_v2` (`model`: `minimax`, `elevenlabs`, …) | MiniMax / ElevenLabs (API cost rows) | 15 units per 50 characters → 0.15 cr |
| ElevenLabs v4 / v4 Turbo | `elevenlabs_v4`, `elevenlabs_v4_turbo` | ElevenLabs | 0.23 / 0.15 cr per 50 characters |
| Seed Audio | `seed_audio` | ByteDance | 0.1 cr per estimated second (15 characters/s) |
| Qwen Audio 3.0 TTS | `qwen_audio_tts` | Alibaba Qwen | 3/70 units per character |
| Voice change | `voice_change_merge` (`/chains/voice-change`) | not disclosed | 0.1 cr/s |
| Dubbing (audio only) | `audio_dubbing` | not disclosed | 3 cr/s |
| Video translation with lipsync | `dubbing_lipsync` (`/chains/dubbing`) | not disclosed | 3 / 3.6 / 6 cr/s at 25 / 30 / 60 fps |
| Video to music | `elevenlabs_video_to_music` (`music_v1` / `music_v2`) | ElevenLabs | 4–9 cr/min |
| Others (enum only) | `mirelo_text_to_audio`, `sonilo_music`, `inworld_text_to_speech` | Mirelo, Sonilo, Inworld (name) | — |

Landings name "ElevenLabs, MiniMax, Seed Speech and Vibe Voice" plus Qwen Audio 3.

Examples:

- ElevenLabs v4, 500 characters: 10 blocks × 23 units / 100 ≈ **2.3** credits (rounding per [`COST_FORMULAS.md`](COST_FORMULAS.md)).
- Dub a 20 s clip with lipsync at 30 fps: 20 × 3.6 = **72**.
- Full formulas: [`COST_FORMULAS.md`](COST_FORMULAS.md).

### 3.12 Upscale and enhance (`/upscale`, `/ai-video-upscaler`)

| Picker | `job_set_type` / route | Provider | Cost |
|---|---|---|---|
| Topaz Upscale (image) | `topaz_image` → `/jobs/topaz-image` | Topaz (models "High Fidelity V2", Standard…) | Server quote (`dry_run`) |
| Topaz Redefine (generative) | `topaz_image_generative` | Topaz | Server quote |
| Topaz Video Upscale | `topaz_video` → `/jobs/topaz-video` (Proteus `prob-4`, Iris `iris-3`, Starlight `slp-2.5`…; interpolation `apo-8`) | Topaz | Server quote |
| Topaz Hyperion 2.5 | `topaz_hyperion_2_5` | Topaz | 2.6 cr/s (≤1080p), 5.2 (2k/4k), estimate |
| Topaz FPS boost | `fps_boost` | Topaz (`model:"topaz"`) | 2–120 cr/s by fps and resolution |
| ByteDance Upscale | `bytedance_video_upscale` → `/jobs/v2/…` | ByteDance (landing: presets, up to 8K, 30/60 fps) | not in costs |
| FLUX.3 Upscale | `flux_video_upscale` | BFL | 0.5–11 cr/s (`creativity`, source → target) |
| Higgsfield Enhance | `seedance_2_5_kling_upscale` | Higgsfield (the name suggests Seedance 2.5 output upscaled with Kling, matching `draft_upscale_model: kling4_0`; inferred) | 4 cr/s at 1080p |
| Nano Banana upscale | `nano_banana_2_upscale` → `/jobs/nano-banana-2-upscale` | Google | not in costs |
| Depth map / SAM 3 | `depth_anything_video`, `sam_3_video` | Depth Anything / Meta (name) | 1.5 / 0.225 cr/s |

Example (community, redacted): `topaz_image {"model":"High Fidelity V2","output_width":3072,"output_height":5440,"sharpen":0.3,"denoise":0.1,"face_enhancement":false,"input_image":{…}}`.

Credit examples:

- Enhance a 10 s clip: 10 × 4 = **40**.
- Hyperion 4k, 10 s: **52**.

### 3.13 Reframe (`/ai/video/reframe`)

`reframe` chain: `POST /chains/reframe`, or `/chains/reframe/batch` when the source is over 15.25 s. Costs
3 / 4.5 / 12 cr/s (480p/720p/1080p) plus `image_credits` 1.25 × `image_count` 3. That table is identical to
`draw_to_video`, `swap_object`, `remove_object` and to **Seedance 2.0** (3/4.5/12), so the generation step is
likely Seedance 2.0 (price twin, inferred).

Example: reframe a 10 s clip to 9:16 at 720p = 10 × 4.5 + 3 × 1.25 = **48.75** (rounding per
[`COST_FORMULAS.md`](COST_FORMULAS.md)).

### 3.14 AI Influencer (`/ai-influencer-studio`)

- `ai_influencer` (image) takes a trait `config`: age, gender, `ethnicity_origin_base`, hair, eye_color,
  skin_color, ears, mouth…
- Video variants: `ai_influencer_motion_control(_flash)`, `ai_influencer_replace_object(_flash)`.
- Restyle: `ai_influencer_restyle`, `restyle` → `/jobs/v2/restyle`; presets at `/restyle/presets` (login).

**Provider:** Higgsfield. The video variants have the same price tables as Genjutsu.

Real community example (image):

```json
{"aspect_ratio":"9:16","resolution":"2k","batch_size":1,"input_images":[],"prompt":"",
 "config":{"age":[{"value":"senior"}],"gender":[{"value":"female"}],"hair":[{"value":"hair_long"}],
 "eye_color":[{"value":"eye_grey"}],"skin_color":[{"value":"C1876B"}],"ethnicity_origin_base":[{"value":"Scandinavian Supermodel"}]}}
```

Cost not in `/job-sets/costs`. Motion control at 720p for 10 s: 10 × 7 = **70**.

### 3.15 Marketing Studio, Ads Studio and Ad Multiplier

**What it does.** From a URL, brand kit or product, it scrapes the brand (`marketing_studio_brand_kit_scrape` /
`_preview`), writes a storyboard (`marketing_storyboard`, `marketing_studio_image`, `ms_image`) and then renders
hooks and videos (`marketing_studio_hook`, `marketing_studio_video`, v2: `marketing_studio_v2_video`,
`_reference2video`). The params include `mode` / `specific_mode` (e.g. product demo), `is_storyboard`,
`is_zoom_control`, `use_seedream_bonus` and `parent_job`.

**Models.**

- Avatars are "powered by Soul 2.0" (landing).
- The storyboard image step has a `use_seedream_bonus` flag, so it is likely Seedream (ByteDance; inferred).
- `ad_multiplier`, `ad_multiplier_v2`, `intone` and `video_character_asset` have the **Seedance 2.5** price table
  (price twin).
- Another landing says UGC avatars get "lifelike lip-sync powered by Seedance 2.0's native audio generation".

| UI choice | `job_set_type` | Credits |
|---|---|---:|
| Marketing video, 720p, 15 s | `marketing_studio_video` | 15 × 5 = **75** |
| Ad Multiplier variant, 1080p, 10 s | `ad_multiplier_v2` | 10 × 16 = **160** |
| Ad replace, 720p, 10 s | `ad_multiplier_replace` (3/7/16 table) | **70** |

### 3.16 Videoshop and video editing tools

`videoshop_edit`, `videoshop_relight`, `videoshop_camera_move` and `videoshop_genjutsu` route to
`/jobs/v2/videoshop_*`. `cinematic_video_editor`, `cinematic_video_relight` and `cinematic_video_inpaint` are the
Cinema Studio counterparts. `draw_to_video`, `swap_object` and `remove_object` charge 3/4.5/12 cr/s plus 3.5 cr
per frame.

**Price twins:** `videoshop_edit` = Seedance 2.5 `video_edit` (3.5/7.5/20/34). `cinematic_video_editor` = Seedance
2.5 including the edit row. Relight, camera move, character asset and intone = Seedance 2.5 `video` rows. Inferred:
Seedance 2.5 does the generation.

Example: relight a 6 s clip at 1080p (`videoshop_relight`) = 6 × 16 = **96**.

### 3.17 Canvas and Flow (`/canvas/{id}`, `/flow/*`)

A node graph on `canvas-worker.higgsfield.ai` (`/api/canvases`, `/api/templates/{id}/use`, node `/run`). Every
`defineJob` type can be a node, configured with fields such as `{nodeType:"seedance_2_5", fieldId:"bitrate_mode"}`.
There is also an **`llm` node: "Generate text via an LLM (OpenRouter)"** with these models:

- default `anthropic/claude-sonnet-4.6`;
- `anthropic/claude-opus-4.7`, `anthropic/claude-haiku-4.5`;
- `openai/gpt-5.5`, `openai/gpt-5.5-pro`, `openai/gpt-5.4-mini`, `openai/gpt-5.2`, `openai/gpt-5.1`, `openai/gpt-5`,
  `openai/gpt-5-mini`, `openai/gpt-4.1-mini`, `openai/gpt-4o-mini`;
- `google/gemini-3.1-pro-preview`, `google/gemini-3.1-flash-lite-preview`;
- reasoning off/low/medium/high.

**Cost:** "credits are deducted when a node generates … at the same rate as that model elsewhere" (landing).
Example: a Soul → Kling 3.0 → Topaz graph costs the sum of the three jobs.

### 3.18 Popcorn and storyboards

`text2keyframes` generates N keyframes from one prompt. Popcorn mode sets `is_pop_corn:true` (the "Instadump"
surface when `is_pop_corn` is set). Real community params: `{"count":4,"quality":"1600p","aspect_ratio":"3:4","preset":{"name":"Default"},"is_pop_corn":false,"seed":…}`.
**Provider:** Higgsfield (not disclosed). **Cost:** not in `/job-sets/costs`.

### 3.19 Original series, Short Drama, Mangaka, Shorts, Faceless and AI Host

These multi-step studios (`/short-drama`, `/mangaka`, `/shorts-studio`, `/faceless-studio`, `/ai-host`) use
agent stage statuses (`dna`, `script`, `visuals`, `vision`, `flow`) and the job types `youtube_faceless_video`
(`animation_mode`: `scene_based` 16 cr / `fully_animated` 41 cr per 10 s block) and `ai_host_video`
(3.3/7.7/17.6 cr/s). Enum-only: `reels_studio`, `video_explainer`, `vibe_motion`, `bd_studio_kling`,
`bd_studio_sora2`, `bd_studio_soul_cast`.

The underlying models aren't disclosed. The `bd_studio_*` names say the "BD studio" chained Kling, Sora 2 and Soul
Cast.

Example: a 60 s fully animated faceless video = 6 blocks × 41 = **246** credits.

### 3.20 MCP, agents and CLI

- The remote MCP server is `https://mcp.higgsfield.ai/mcp` (OAuth; not connected).
- 75 skills and 3 bundles are prompt packages for Telegram, Slack, ChatGPT, Claude and Cursor. They name no models.
- The CLI landing: "Your agent automatically selects the best model … or you can specify one yourself" and
  "same credit system".
- `/ai/video/agent` is an in-app video agent mode.

Tool schemas and model routing for MCP are **unknown** (they need a login).

### 3.21 Public API (open.higgsfield.ai)

The `/higgsfield-api` landing links to `open.higgsfield.ai` (create an API key), `docs.higgsfield.ai` and
`api.higgsfield.ai`. The flow it describes is "POST the model's endpoint with your prompt, get back a request_id
with a status_url, poll it", plus `cancel_url`. The catalog covers "Seedance, Kling, Veo, GPT Image, Soul,
VoiceLab and more". The offer is up to 75 % off 3 chosen models, a $15 starter balance and 20 concurrent requests.
These are separate API products; no endpoints were called.

---

## 4. Model catalog (generated)

One row per `job_set_type` that appears in `/job-sets/costs`, the latest `models.json`, a JS `defineJob` or the
adapter route table. Provider and evidence come from the hand-maintained map in
`scripts/gen_model_catalog.py`. "same price table as" lists other types whose live price table is numerically
identical (a backend hint, not proof). Regenerate with `python scripts/gen_model_catalog.py --write`.

<!-- BEGIN model-catalog -->
| job_set_type | display name | family | ver | provider | evidence | media | product(s) | costs | JS | route | price (live) | same price table as |
|---|---|---|---|---|---|---|---|:-:|:-:|---|---|---|
| `3d_jutsu_angles` | 3D Jutsu Angles | 3d_jutsu_angles |  | Higgsfield (backend not disclosed) | in-house | image | Other Higgsfield tools | ✔ |  |  | 1.25–2.5 cr/generation | seedream_v5_pro |
| `ad_multiplier` | Ad Multiplier | ad_multiplier |  | Higgsfield (backend not disclosed) | in-house | video | Marketing Studio / Ads | ✔ |  |  | 3–34 cr/second | ad_multiplier_v2, intone, video_character_asset, videoshop_camera_move |
| `ad_multiplier_replace` | Ad Multiplier Replace | ad_multiplier_replace |  | Higgsfield (backend not disclosed) | in-house | video | Marketing Studio / Ads | ✔ |  |  | 3–16 cr/second |  |
| `ad_multiplier_v2` | Ad Multiplier V2 | ad_multiplier | 2 | Higgsfield (backend not disclosed) | in-house | video | Marketing Studio / Ads | ✔ |  |  | 3–34 cr/second | ad_multiplier, intone, video_character_asset, videoshop_camera_move |
| `ai_host_video` | AI Host Video | ai_host_video |  | Higgsfield (backend not disclosed) | in-house | video | Faceless / AI Host studio | ✔ |  |  | 3.3–17.6 cr/second |  |
| `ai_influencer_motion_control` | AI Influencer Motion Control | ai_influencer_motion_control |  | Higgsfield (backend not disclosed) | in-house | video | AI Influencer | ✔ |  |  | 3–20 cr/second | ai_influencer_replace_object, hf_mult_motion_control, hf_mult_replace_object, videoshop_genjutsu |
| `ai_influencer_motion_control_flash` | AI Influencer Motion Control Flash | ai_influencer_motion_control_flash |  | Higgsfield (backend not disclosed) | in-house | video | AI Influencer | ✔ |  |  | 1–4 cr/second | ai_influencer_replace_object_flash, hf_mult_motion_control_flash |
| `ai_influencer_replace_object` | AI Influencer Replace Object | ai_influencer_replace_object |  | Higgsfield (backend not disclosed) | in-house | video | AI Influencer | ✔ |  |  | 3–20 cr/second | ai_influencer_motion_control, hf_mult_motion_control, hf_mult_replace_object, videoshop_genjutsu |
| `ai_influencer_replace_object_flash` | AI Influencer Replace Object Flash | ai_influencer_replace_object_flash |  | Higgsfield (backend not disclosed) | in-house | video | AI Influencer | ✔ |  |  | 1–4 cr/second | ai_influencer_motion_control_flash, hf_mult_motion_control_flash |
| `audio_dubbing` | Audio Dubbing | audio_dubbing |  | Higgsfield (backend not disclosed) | in-house | audio | Audio / TTS / dubbing | ✔ |  |  | 3 cr/second |  |
| `bytedance_video_upscale` |  |  |  | ByteDance (Seed) | JS | video | Upscale / video tools |  | ✔ | `/jobs/v2/bytedance_video_upscale` |  |  |
| `character_swap_v2` |  |  | 2 | Higgsfield (backend not disclosed) | in-house | image | Apps |  | ✔ | `/jobs/character-swap/v2` |  |  |
| `cinematic_studio_3_0` | Cinematic Studio 3.0 | cinematic_studio | 3.0 | Higgsfield (backend not disclosed) | in-house | video | Cinema Studio | ✔ | ✔ | `/jobs/v2/cinematic_studio_3_0` | 3.5–24 cr/second | cinematic_studio_video_3_5 |
| `cinematic_studio_image` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Cinema Studio |  | ✔ | `/jobs/cinematic-studio-image *` |  |  |
| `cinematic_studio_image_grid` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Cinema Studio |  | ✔ | `/jobs/cinematic-studio-image-grid *` |  |  |
| `cinematic_studio_soul_cast` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Cinema Studio |  | ✔ | `/jobs/cinematic-studio-soul-cast *` |  |  |
| `cinematic_studio_soul_location` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Cinema Studio |  | ✔ | `/jobs/cinematic-studio-soul-location *` |  |  |
| `cinematic_studio_video_3_5` | Cinematic Studio Video 3.5 | cinematic_studio_video | 3.5 | Higgsfield (backend not disclosed) | in-house | video | Cinema Studio | ✔ | ✔ | `/jobs/v2/cinematic_studio_video_3_5` | 3.5–24 cr/second | cinematic_studio_3_0 |
| `cinematic_studio_video_4_0` | Cinematic Studio Video 4.0 | cinematic_studio_video | 4.0 | Higgsfield (backend not disclosed) | in-house | video | Cinema Studio | ✔ | ✔ | `/jobs/v2/cinematic_studio_video_4_0` | 3–34 cr/second |  |
| `cinematic_studio_video_v2` |  |  | 2 | Higgsfield (backend not disclosed) | in-house | video | Cinema Studio |  | ✔ | `/jobs/v2/cinematic_studio_video_v2` |  |  |
| `cinematic_video_editor` | Cinematic Video Editor | cinematic_video_editor |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ |  |  | 3–20 cr/second |  |
| `cinematic_video_inpaint` | Cinematic Video Inpaint | cinematic_video_inpaint |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ | ✔ | `/jobs/v2/cinematic_video_inpaint` | 3–34 cr/second | cinematic_video_relight |
| `cinematic_video_relight` | Cinematic Video Relight | cinematic_video_relight |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ | ✔ | `/jobs/v2/cinematic_video_relight` | 3–34 cr/second | cinematic_video_inpaint |
| `depth_anything_video` | Depth Anything Video | depth_anything_video |  | Depth Anything (ByteDance/HKU, open model) | name | video | Upscale / video tools | ✔ |  |  | 1.5 cr/second |  |
| `draw_to_video` | Draw To Video | draw_to_video |  | Higgsfield (backend not disclosed) | in-house | video | Draw to video / object edit | ✔ |  |  | 3–12 cr/frame,cr/second | reframe, remove_object, swap_object |
| `dubbing_lipsync` | Dubbing Lipsync | dubbing_lipsync |  | Higgsfield (backend not disclosed) | in-house | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/dubbing-lipsync *` | 3–6 cr/second |  |
| `elevenlabs_v4` | Elevenlabs V4 | elevenlabs | 4 | ElevenLabs | JS | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/v2/elevenlabs_v4` | 0.23 cr/50_characters |  |
| `elevenlabs_v4_turbo` | Elevenlabs V4 Turbo | elevenlabs | 4 | ElevenLabs | JS | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/v2/elevenlabs_v4_turbo` | 0.15 cr/50_characters |  |
| `elevenlabs_video_to_music` | Elevenlabs Video To Music | elevenlabs_video_to_music |  | ElevenLabs | JS | audio | Audio / TTS / dubbing | ✔ |  |  | 4–9 cr/minute |  |
| `flux_2` | Flux.2 Pro | flux | 2 | Black Forest Labs (FLUX) | JS | image | Image generator |  | ✔ | `/jobs/flux-2 *` |  |  |
| `flux_3_image` |  |  | 3 | Black Forest Labs (FLUX) | JS | image | Image generator |  | ✔ | `/jobs/v2/flux_3_image` |  |  |
| `flux_3_video` | Flux 3 Video | flux | 3 | Black Forest Labs (FLUX) | JS | video | Video generator | ✔ | ✔ | `/jobs/flux-3-video *` | 6–13 cr/second |  |
| `flux_3_video_edit` |  |  | 3 | Black Forest Labs (FLUX) | JS | video | Video generator |  | ✔ | `/jobs/flux-3-video-edit *` |  |  |
| `flux_kontext` | Flux Kontext Max |  |  | Black Forest Labs (FLUX) | JS | image | Image generator |  | ✔ | `/jobs/flux-kontext *` |  |  |
| `flux_video_upscale` | Flux Video Upscale | flux_video_upscale |  | Black Forest Labs (FLUX) | JS | video | Upscale / video tools | ✔ |  |  | 0.5–11 cr/second |  |
| `fps_boost` | FPS Boost | fps_boost |  | Topaz Labs | JS | video | Upscale / video tools | ✔ |  |  | 2–120 cr/second |  |
| `gemini_omni` | Gemini Omni | gemini_omni |  | Google (Veo / Gemini) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/gemini_omni` | 0–3 base_credits,cr/second |  |
| `gemini_omni_flash_1_1` |  |  | 1.1 | Google (Veo / Gemini) | JS | video | Video generator |  | ✔ | `/jobs/v2/gemini_omni_flash_1_1` |  |  |
| `gemini_omni_flash_1_2` | Gemini Omni Flash 1.2 | gemini_omni_flash | 1.2 | Google (Veo / Gemini) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/gemini_omni_flash_1_2` | 0–6.75 base_credits,cr/second |  |
| `gif` | GIF | gif |  | Higgsfield (backend not disclosed) | in-house | image | Image generator | ✔ |  |  | 1–3 cr/generation |  |
| `gpt_image_2` | GPT Image 2 | gpt_image | 2 | OpenAI (GPT Image) | API | image | Image generator | ✔ | ✔ | `/jobs/v2/gpt_image_2` | 0.5–12 cr/generation |  |
| `gpt_image_2_5` | GPT Image 2.5 | gpt_image | 2.5 | OpenAI (GPT Image) | API | image | Image generator | ✔ | ✔ | `/jobs/v2/gpt_image_2_5` | 0.25–12 cr/generation |  |
| `gpt_image_2_6` | GPT Image 2.6 | gpt_image | 2.6 | OpenAI (GPT Image) | API | image | Image generator | ✔ | ✔ | `/jobs/v2/gpt_image_2_6` | 0.75–12 cr/generation |  |
| `gpt_image_2_6_flare` | GPT Image 2.6 Flare | gpt_image | 2.6 | OpenAI (GPT Image) | API | image | Image generator | ✔ | ✔ | `/jobs/v2/gpt_image_2_6_flare` | 0.75–12 cr/generation |  |
| `gpt_image_2_unlimited` |  |  | 2 | OpenAI (GPT Image) | API | image | Image generator |  | ✔ | `/jobs/v2/gpt_image_2_unlimited` |  |  |
| `grok_image` |  |  |  | xAI (Grok Imagine) | JS+API | image | Image generator |  | ✔ | `/jobs/v2/grok_image` |  |  |
| `grok_image_2_0` |  |  | 2.0 | xAI (Grok Imagine) | JS+API | image | Image generator |  | ✔ | `/jobs/v2/grok_image_2_0` |  |  |
| `grok_video` | Grok Imagine |  |  | xAI (Grok Imagine) | JS+API | video | Video generator |  | ✔ | `/jobs/v2/grok_video` |  |  |
| `grok_video_edit` |  |  |  | xAI (Grok Imagine) | JS+API | video | Video generator |  | ✔ | `/jobs/v2/grok_video_edit` |  |  |
| `grok_video_v15` | Grok Video v1.5 | grok_video | 15 | xAI (Grok Imagine) | JS+API | video | Video generator | ✔ | ✔ | `/jobs/v2/grok_video_v15` | 2.5–8 cr/second |  |
| `grok_video_v15_lite` | Grok Video v1.5 Lite | grok_video | 15 | xAI (Grok Imagine) | JS+API | video | Video generator | ✔ | ✔ | `/jobs/v2/grok_video_v15_lite` | 1–4 cr/second |  |
| `happy_horse_video` | Happy Horse Video | happy_horse_video |  | Alibaba (HappyHorse) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/happy_horse_video` | 2.5–4.5 cr/second |  |
| `hf_evolution` | HF Evolution | hf_evolution |  | Higgsfield (backend not disclosed) | in-house | video | Other Higgsfield tools | ✔ |  |  | 7 cr/second |  |
| `hf_fnf_video` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | Cinema Studio |  | ✔ | `/jobs/v2/hf_fnf_video` |  |  |
| `hf_mult_motion_control` | Higgsfield Genjutsu | hf_mult_motion_control |  | Higgsfield (backend not disclosed) | in-house | video | Genjutsu (motion control / replace object) | ✔ | ✔ | `/jobs/hf-mult-motion-control *` | 3–20 cr/second | ai_influencer_motion_control, ai_influencer_replace_object, hf_mult_replace_object, videoshop_genjutsu |
| `hf_mult_motion_control_flash` | HF Mult Motion Control Flash | hf_mult_motion_control_flash |  | Higgsfield (backend not disclosed) | in-house | video | Genjutsu (motion control / replace object) | ✔ |  |  | 1–4 cr/second | ai_influencer_motion_control_flash, ai_influencer_replace_object_flash |
| `hf_mult_replace_object` | HF Mult Replace Object | hf_mult_replace_object |  | Higgsfield (backend not disclosed) | in-house | video | Genjutsu (motion control / replace object) | ✔ | ✔ | `/jobs/hf-mult-replace-object *` | 3–20 cr/second | ai_influencer_motion_control, ai_influencer_replace_object, hf_mult_motion_control, videoshop_genjutsu |
| `hf_mult_replace_object_flash` | HF Mult Replace Object Flash | hf_mult_replace_object_flash |  | Higgsfield (backend not disclosed) | in-house | video | Genjutsu (motion control / replace object) | ✔ |  |  | 2–4 cr/second |  |
| `ideogram_4_5` | Ideogram 4.5 | ideogram | 4.5 | Ideogram | JS | image | Image generator | ✔ | ✔ | `/jobs/ideogram-4-5 *` | 0.25–6.25 cr/generation |  |
| `ideogram_4_5_precise_edit` | Ideogram 4.5 Precise Edit | ideogram | 4.5 | Ideogram | JS | image | Image generator | ✔ | ✔ | `/jobs/ideogram-4-5-precise-edit *` | 0.5–7 cr/generation |  |
| `ideogram_4_6` | Ideogram 4.6 | ideogram | 4.6 | Ideogram | JS | image | Image generator | ✔ | ✔ | `/jobs/ideogram-4-6 *` | 1–19 cr/generation |  |
| `ideogram_4_6_precise_edit` | Ideogram 4.6 Precise Edit | ideogram | 4.6 | Ideogram | JS | image | Image generator | ✔ | ✔ | `/jobs/ideogram-4-6-precise-edit *` | 1–19 cr/generation |  |
| `ideogram_vector` | Ideogram Vector | ideogram_vector |  | Ideogram | JS | image | Image generator | ✔ | ✔ | `/jobs/ideogram-vector *` | 3–10 cr/generation |  |
| `image2video` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | DoP motions (camera presets) |  | ✔ | `/jobs/image2video *` |  |  |
| `image2video_mix` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | DoP motions (camera presets) |  | ✔ | `/jobs/image2video-mix *` |  |  |
| `image_auto` | Auto |  |  | Higgsfield (backend not disclosed) | in-house | image | Image generator |  | ✔ | `/jobs/v2/image_auto` |  |  |
| `imagegen_2_0` |  |  | 2.0 | OpenAI (GPT Image) | API |  | Image generator |  | ✔ | `/jobs/v2/gpt_image_2` |  |  |
| `intone` | Intone | intone |  | Higgsfield (backend not disclosed) | in-house | video | Other Higgsfield tools | ✔ |  |  | 3–34 cr/second | ad_multiplier, ad_multiplier_v2, video_character_asset, videoshop_camera_move |
| `keyframes_faceswap` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Apps |  | ✔ | `/jobs/face-swap` |  |  |
| `kling` |  |  |  | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/kling *` |  |  |
| `kling2_6` | Kling 2.6 |  | 2.6 | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/kling2-6 *` |  |  |
| `kling2_6_motion_control` |  |  | 2.6 | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/v2/kling2_6_motion_control` |  |  |
| `kling3_0` | Kling 3.0 | kling | 3.0 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling3_0` | 1.5–6 cr/second |  |
| `kling3_0_motion_control` | Kling 3.0 Motion Control | kling | 3.0 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling3_0_motion_control` | 1.5–2.5 cr/second |  |
| `kling3_0_turbo` | Kling 3.0 Turbo | kling | 3.0 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling3_0_turbo` | 1.5–2 cr/second |  |
| `kling4_0` | Kling 4.0 | kling | 4.0 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling4_0` | 2.5–12 cr/second |  |
| `kling_3_unlimited` |  |  | 3 | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/v2/kling_3_unlimited` |  |  |
| `kling_4_0_flash` | Kling 4.0 Flash | kling | 4.0 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling_4_0_flash` | 1.5–2 cr/second |  |
| `kling_image_4_0` | Kling Image 4.0 | kling_image | 4.0 | Kuaishou (Kling) | JS | image | Image generator | ✔ | ✔ | `/jobs/v2/kling_image_4_0` | 2–5 cr/generation |  |
| `kling_o3_flf` | Kling O3 FLF | kling_o3_flf | 3 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling_o3_flf` | 1–6 cr/second |  |
| `kling_o3_image_reference` | Kling O3 Image Reference | kling_o3_image_reference | 3 | Kuaishou (Kling) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/kling_o3_image_reference` | 1–6 cr/second |  |
| `kling_omni_flf` |  |  |  | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/kling-omni-flf *` |  |  |
| `kling_omni_image` | Kling O1 Image | kling_omni_image |  | Kuaishou (Kling) | JS | image | Image generator |  | ✔ | `/jobs/kling-omni-image *` |  |  |
| `kling_omni_image_reference` |  |  |  | Kuaishou (Kling) | JS | video | Image generator |  | ✔ | `/jobs/kling-omni-image-reference *` |  |  |
| `kling_video_edit` |  |  |  | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/kling-video-edit *` |  |  |
| `kling_video_reference` |  |  |  | Kuaishou (Kling) | JS | video | Video generator |  | ✔ | `/jobs/kling-video-reference *` |  |  |
| `layer_project_generate` |  |  |  | Higgsfield (backend not disclosed) | in-house | image |  |  | ✔ | `/jobs/layer-project-generate *` |  |  |
| `layer_project_regenerate` |  |  |  | Higgsfield (backend not disclosed) | in-house | image |  |  | ✔ | `/jobs/layer-project-regenerate *` |  |  |
| `magi_2` | MAGI-2 |  | 2 | Sand AI (MAGI) | JS | video | Video generator |  | ✔ | `/jobs/v2/magi_2` |  |  |
| `marketing_storyboard` |  |  |  | Higgsfield (backend not disclosed) | in-house | image |  |  | ✔ | `/jobs/marketing-storyboard *` |  |  |
| `marketing_studio_brand_kit_preview` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Marketing Studio / Ads |  | ✔ | `/jobs/marketing-studio-brand-kit-preview *` |  |  |
| `marketing_studio_brand_kit_scrape` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Marketing Studio / Ads |  | ✔ | `/jobs/marketing-studio-brand-kit-scrape *` |  |  |
| `marketing_studio_hook` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | Marketing Studio / Ads |  | ✔ | `/jobs/marketing-studio-hook *` |  |  |
| `marketing_studio_image` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Marketing Studio / Ads |  | ✔ | `/jobs/v2/marketing_studio_image` |  |  |
| `marketing_studio_video` | Marketing Studio Video | marketing_studio_video |  | Higgsfield (backend not disclosed) | in-house | video | Marketing Studio / Ads | ✔ | ✔ | `/jobs/marketing-studio-video *` | 3.5–13 cr/second |  |
| `minimax_h3` | MiniMax H3 |  | 3 | MiniMax (Hailuo) | JS | video | Video generator |  | ✔ | `/jobs/v2/minimax_h3` |  |  |
| `minimax_h3_highspeed` | Minimax H3 Highspeed | minimax_h3_highspeed | 3 | MiniMax (Hailuo) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/minimax_h3_highspeed` | 1.25–2 cr/second |  |
| `minimax_h3_image` | Minimax H3 Image | minimax_h3_image | 3 | MiniMax (Hailuo) | JS | image | Image generator | ✔ | ✔ | `/jobs/v2/minimax_h3_image` | 3–4 cr/generation |  |
| `minimax_h3_lite` | Minimax H3 Lite | minimax_h3_lite | 3 | MiniMax (Hailuo) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/minimax_h3_lite` | 1–1.25 cr/second |  |
| `minimax_h3_max` | MiniMax H3 Max |  | 3 | MiniMax (Hailuo) | JS | video | Video generator |  | ✔ | `/jobs/v2/minimax_h3_max` |  |  |
| `minimax_hailuo` |  |  |  | MiniMax (Hailuo) | JS | video | Video generator |  | ✔ | `/jobs/minimax-hailuo *` |  |  |
| `ms_image` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Marketing Studio / Ads |  | ✔ | `/jobs/ms-image *` |  |  |
| `music_cards_v1` |  |  | 1 | Higgsfield (backend not disclosed) | in-house | video | Other Higgsfield tools |  | ✔ | `/jobs/v2/music_cards_v1` |  |  |
| `nano_banana` | Nano Banana | nano_banana |  | Google (Gemini image) | JS+API | image | Image generator |  | ✔ | `/jobs/nano-banana *` |  |  |
| `nano_banana_2` | Nano Banana Pro | nano_banana | 2 | Google (Gemini image) | JS+API | image | Image generator |  | ✔ | `/jobs/nano-banana-2 *` |  |  |
| `nano_banana_2_1` | Nano Banana 2.1 | nano_banana | 2.1 | Google (Gemini image) | JS+API | image | Image generator | ✔ | ✔ | `/jobs/v2/nano_banana_2_1` | 1.5–3 cr/generation |  |
| `nano_banana_2_lite` | Nano Banana 2 Lite |  | 2 | Google (Gemini image) | JS+API | image | Image generator |  | ✔ | `/jobs/v2/nano_banana_2_lite` |  |  |
| `nano_banana_2_upscale` |  |  | 2 | Google (Gemini image) | JS+API | image | Upscale |  | ✔ | `/jobs/nano-banana-2-upscale` |  |  |
| `nano_banana_flash` | Nano Banana 2 |  |  | Google (Gemini image) | JS+API | image | Image generator |  | ✔ | `/jobs/v2/nano_banana_flash` |  |  |
| `nano_banana_pro_unlimited` |  |  |  | Google (Gemini image) | JS+API | image | Image generator |  | ✔ | `/jobs/v2/nano_banana_pro_unlimited` |  |  |
| `openai_hazel` |  |  |  | OpenAI | name | image | Image generator |  | ✔ | `/jobs/openai-hazel *` |  |  |
| `openai_hazel_mini` | OpenAI Hazel Mini | openai_hazel_mini |  | OpenAI | name | image | Image generator |  | ✔ | `/jobs/openai-hazel-mini *` |  |  |
| `p_image_ideogram` | Ideogram | ideogram |  | Ideogram | JS | image | Image generator | ✔ |  |  | 0.1–1 cr/generation |  |
| `qwen_audio_tts` | Qwen Audio TTS | qwen_audio_tts |  | Alibaba (Qwen) | name | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/v2/qwen_audio_tts` | 0.00042857 cr/character |  |
| `recraft_v4_1` | Recraft V4.1 | recraft | 4.1 | Recraft | JS | image | Image generator | ✔ | ✔ | `/jobs/v2/recraft_v4_1` | 1.25–10 cr/generation |  |
| `recraft_v4_styles` |  |  | 4 | Recraft | JS | image | Image generator |  | ✔ | `/jobs/v2/recraft_v4_styles` |  |  |
| `reframe` | Reframe | reframe |  | Higgsfield (backend not disclosed) | in-house | video | Reframe | ✔ | ✔ | `/jobs/reframe *` | 1.25–12 cr/image,cr/second | draw_to_video, remove_object, swap_object |
| `remove_object` | Remove Object | remove_object |  | Higgsfield (backend not disclosed) | in-house | video | Draw to video / object edit | ✔ |  |  | 3–12 cr/frame,cr/second | draw_to_video, reframe, swap_object |
| `restyle` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | AI Influencer |  | ✔ | `/jobs/restyle *` |  |  |
| `reve` |  |  |  | Reve | name | image | Image generator |  | ✔ | `/jobs/reve *` |  |  |
| `sam_3_video` | SAM 3 Video | sam | 3 | Meta (SAM 3) | name | video | Upscale / video tools | ✔ |  |  | 0.225 cr/second |  |
| `scene_switch` | Scene Switch | scene_switch |  | Higgsfield (backend not disclosed) | in-house | video | Other Higgsfield tools | ✔ |  |  | 4.03–37.58 cr/second |  |
| `seed_audio` | Seed Audio | seed_audio |  | ByteDance (Seed) | name | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/v2/seed_audio` | 0.1 cr/second |  |
| `seedance` |  |  |  | ByteDance (Seed) | JS | video | Video generator |  | ✔ | `/jobs/seedance *` |  |  |
| `seedance1_5` |  |  | 1.5 | ByteDance (Seed) | JS | video | Video generator |  | ✔ | `/jobs/v2/seedance1_5` |  |  |
| `seedance_2_0` | Seedance 2.0 | seedance | 2.0 | ByteDance (Seed) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/seedance_2_0` | 1–22 cr/second |  |
| `seedance_2_0_mini` | Seedance 2.0 Mini | seedance | 2.0 | ByteDance (Seed) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/seedance_2_0_mini` | 0.5–1 cr/second |  |
| `seedance_2_5` | Seedance 2.5 | seedance | 2.5 | ByteDance (Seed) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/seedance_2_5` | 3–34 cr/second |  |
| `seedance_2_5_flash` | Seedance 2.5 Flash | seedance | 2.5 | ByteDance (Seed) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/seedance_2_5_flash` | 2–6 cr/second |  |
| `seedance_2_5_kling_upscale` | Seedance 2.5 Kling Upscale | seedance | 2.5 | ByteDance (Seed) | JS | video | Upscale (Higgsfield Enhance) | ✔ |  |  | 4 cr/second |  |
| `seedance_2_unlimited` | Seedance 2.0 |  | 2 | ByteDance (Seed) | JS | video | Video generator |  | ✔ | `/jobs/v2/seedance_2_unlimited` |  |  |
| `seedance_mini_unlimited` | Seedance 2.0 Mini |  |  | ByteDance (Seed) | JS | video | Video generator |  | ✔ | `/jobs/v2/seedance_mini_unlimited` |  |  |
| `seedance_unlimited` | Enhanced Seedance 2.0 Fast |  |  | ByteDance (Seed) | JS | video | Video generator |  | ✔ | `/jobs/v2/seedance_unlimited` |  |  |
| `seedream` | Seedream 4.0 |  |  | ByteDance (Seed) | JS | image | Image generator |  | ✔ | `/jobs/seedream *` |  |  |
| `seedream_5_0_flash` | Seedream 5.0 Flash | seedream | 5.0 | ByteDance (Seed) | JS | image | Image generator | ✔ | ✔ | `/jobs/v2/seedream_5_0_flash` | 0.5 cr/generation |  |
| `seedream_5_5` | Seedream 5.5 | seedream | 5.5 | ByteDance (Seed) | JS | image | Image generator | ✔ | ✔ | `/jobs/v2/seedream_5_5` | 2.5–3.5 cr/generation |  |
| `seedream_v4_5` | Seedream 4.5 | seedream | 4.5 | ByteDance (Seed) | JS | image | Image generator |  | ✔ | `/jobs/seedream-v4-5 *` |  |  |
| `seedream_v5_lite` | Seedream 5.0 Lite | seedream | 5 | ByteDance (Seed) | JS | image | Image generator |  | ✔ | `/jobs/v2/seedream_v5_lite` |  |  |
| `seedream_v5_pro` | Seedream 5.0 Pro | seedream | 5 | ByteDance (Seed) | JS | image | Image generator | ✔ | ✔ | `/jobs/v2/seedream_v5_pro` | 1.25–2.5 cr/generation | 3d_jutsu_angles |
| `sora2_video` |  |  | 2 | OpenAI (Sora 2) | JS | video | Video generator |  | ✔ | `/jobs/sora2-video *` |  |  |
| `soul_cinema_1_5` |  |  | 1.5 | Higgsfield (backend not disclosed) | in-house |  | Soul / Soul ID |  | ✔ | `/jobs/v2/soul_cinema_1_5` |  |  |
| `soul_cinema_1_5_serega` |  |  | 1.5 | Higgsfield (backend not disclosed) | in-house |  | Soul / Soul ID |  | ✔ | `/jobs/v2/soul_cinema_1_5_serega` |  |  |
| `soul_cinema_studio` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Soul / Soul ID |  | ✔ | `/jobs/soul-cinema-studio *` |  |  |
| `soul_cinematic` | Soul V2 & Cinema | soul_cinematic |  | Higgsfield (backend not disclosed) | in-house | image | Soul / Soul ID |  | ✔ | `/jobs/v2/soul_cinematic` |  |  |
| `swap_object` | Swap Object | swap_object |  | Higgsfield (backend not disclosed) | in-house | video | Draw to video / object edit | ✔ |  |  | 3–12 cr/frame,cr/second | draw_to_video, reframe, remove_object |
| `text2image_gpt` |  |  |  | OpenAI (GPT Image) | API | image | Image generator |  | ✔ | `/jobs/text2image-gpt *` |  |  |
| `text2image_soul` |  |  |  | Higgsfield (backend not disclosed) | in-house | image | Soul / Soul ID |  | ✔ | `/jobs/text2image-soul *` |  |  |
| `text2image_soul_v2` | Soul V2 & Cinema | text2image_soul | 2 | Higgsfield (backend not disclosed) | in-house | image | Soul / Soul ID |  | ✔ | `/jobs/v2/text2image_soul_v2` |  |  |
| `text2speech_v2` | Text2speech V2 | text2speech | 2 | multi: MiniMax / ElevenLabs (costs `model` rows) | API | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/v2/text2speech_v2` | 0.05–0.15 cr/50_characters |  |
| `topaz_hyperion_2_5` | Topaz Hyperion 2.5 | topaz_hyperion | 2.5 | Topaz Labs | JS | video | Upscale / video tools | ✔ |  |  | 2.6–5.2 cr/second |  |
| `topaz_image` |  |  |  | Topaz Labs | JS | image | Upscale / video tools |  | ✔ | `/jobs/topaz-image *` |  |  |
| `topaz_image_generative` |  |  |  | Topaz Labs | JS | image | Upscale / video tools |  | ✔ | `/jobs/topaz-image-generative *` |  |  |
| `topaz_video` |  |  |  | Topaz Labs | JS | video | Upscale / video tools |  | ✔ | `/jobs/topaz-video *` |  |  |
| `veo3` |  |  | 3 | Google (Veo / Gemini) | JS | video | Video generator |  | ✔ | `/jobs/veo3 *` |  |  |
| `veo3_1` |  |  | 3.1 | Google (Veo / Gemini) | JS | video | Video generator |  | ✔ | `/jobs/veo3-1 *` |  |  |
| `veo3_1_lite` |  |  | 3.1 | Google (Veo / Gemini) | JS | video | Video generator |  | ✔ | `/jobs/v2/veo3_1_lite` |  |  |
| `video_background_remover` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | Apps |  | ✔ | `/jobs/video-background-remover *` |  |  |
| `video_character_asset` | Video Character Asset | video_character_asset |  | Higgsfield (backend not disclosed) | in-house | video | Other Higgsfield tools | ✔ |  |  | 3–34 cr/second | ad_multiplier, ad_multiplier_v2, intone, videoshop_camera_move |
| `videoshop_camera_move` | Videoshop Camera Move | videoshop_camera_move |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ | ✔ | `/jobs/v2/videoshop_camera_move` | 3–34 cr/second | ad_multiplier, ad_multiplier_v2, intone, video_character_asset |
| `videoshop_edit` | Videoshop Edit | videoshop_edit |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ | ✔ | `/jobs/v2/videoshop_edit` | 3.5–34 cr/second |  |
| `videoshop_genjutsu` | Videoshop Genjutsu | videoshop_genjutsu |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ | ✔ | `/jobs/v2/videoshop_genjutsu` | 3–20 cr/second | ai_influencer_motion_control, ai_influencer_replace_object, hf_mult_motion_control, hf_mult_replace_object |
| `videoshop_relight` | Videoshop Relight | videoshop_relight |  | Higgsfield (backend not disclosed) | in-house | video | Videoshop / video edit | ✔ | ✔ | `/jobs/v2/videoshop_relight` | 3–34 cr/image,cr/second | ad_multiplier, ad_multiplier_v2, intone, video_character_asset |
| `viral_hub_video` |  |  |  | Higgsfield (backend not disclosed) | in-house | video | Viral effects |  | ✔ | `/jobs/viral-hub-video *` |  |  |
| `voice_change_merge` | Voice Change Merge | voice_change_merge |  | Higgsfield (backend not disclosed) | in-house | audio | Audio / TTS / dubbing | ✔ | ✔ | `/jobs/voice-change-merge *` | 0.1 cr/second |  |
| `wan2_2_image` |  |  | 2.2 | Alibaba (Wan) | JS | image | Image generator |  | ✔ | `/jobs/wan2-2-image *` |  |  |
| `wan2_2_video` |  |  | 2.2 | Alibaba (Wan) | JS | video | Video generator |  | ✔ | `/jobs/wan2-2-video *` |  |  |
| `wan2_5_video` | Wan 2.5 |  | 2.5 | Alibaba (Wan) | JS | video | Video generator |  | ✔ | `/jobs/wan2-5-video *` |  |  |
| `wan2_6` |  |  | 2.6 | Alibaba (Wan) | JS | video | Video generator |  | ✔ | `/jobs/wan2-6 *` |  |  |
| `wan2_7` |  |  | 2.7 | Alibaba (Wan) | JS | video | Video generator |  | ✔ | `/jobs/v2/wan2_7` |  |  |
| `wan3_0` | Wan 3.0 | wan | 3.0 | Alibaba (Wan) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/wan3_0` | 0.75–6 cr/second |  |
| `wan3_0_prime` | Wan 3.0 Prime | wan | 3.0 | Alibaba (Wan) | JS | video | Video generator | ✔ | ✔ | `/jobs/v2/wan3_0_prime` | 1.25–11 cr/second |  |
| `wan4_0` | Wan 4.0 |  | 4.0 | Alibaba (Wan) | JS |  | Video generator |  | ✔ | `/jobs/v2/wan4_0` |  |  |
| `what_if_v1` |  |  | 1 | Higgsfield (backend not disclosed) | in-house | video | Other Higgsfield tools |  | ✔ | `/jobs/v2/what_if_v1` |  |  |
| `youtube_faceless_video` | Youtube Faceless Video | youtube_faceless_video |  | Higgsfield (backend not disclosed) | in-house | video | Faceless / AI Host studio | ✔ |  |  | 16–41 cr/10_seconds |  |
| `z_image` | Z-Image |  |  | Alibaba Tongyi (Z-Image) | name | image | Image generator |  | ✔ | `/jobs/z-image *` |  |  |

175 job types; 87 in `/job-sets/costs`, 145 in the JS bundle. Route `*` = not in the adapter route table, default `/jobs/<kebab-type>` rule (from JS, not called). Costs-only (no `defineJob`/route in JS): `3d_jutsu_angles`, `ad_multiplier`, `ad_multiplier_replace`, `ad_multiplier_v2`, `ai_host_video`, `ai_influencer_motion_control`, `ai_influencer_motion_control_flash`, `ai_influencer_replace_object`, `ai_influencer_replace_object_flash`, `audio_dubbing`, `cinematic_video_editor`, `depth_anything_video`, `draw_to_video`, `elevenlabs_video_to_music`, `flux_video_upscale`, `fps_boost`, `gif`, `hf_evolution`, `hf_mult_motion_control_flash`, `hf_mult_replace_object_flash`, `intone`, `p_image_ideogram`, `remove_object`, `sam_3_video`, `scene_switch`, `seedance_2_5_kling_upscale`, `swap_object`, `topaz_hyperion_2_5`, `video_character_asset`, `youtube_faceless_video`.

_Generated by `python scripts/gen_model_catalog.py --write` from `samples/higgsfield/model_loading/job_sets_costs.json`, `runs/20261126-090255_costs-ref/output/json/models.json`, `samples/higgsfield/js2`._
<!-- END model-catalog -->

---

## 5. Retired, redirected, JS-only and costs-only models

**Retired.** The `Vx` set in `tCLaulKUdGQfxqgZ.js` hides these and redirects their URLs to
`?model=seedance_2_5`:

- `veo-3-preview`, `veo-3-fast`, `veo3`, `speak-veo-preview`, `speak-veo-fast`, `veo3_speak`;
- `gemini-omni`, `gemini_omni`;
- `open_sora_video`, `sora-pro`, `sora-2`, `sora-2-pro`, `sora-2-max`, `sora-2-pro-max`, `sora2_video`,
  `sora2_video_upscale`, `sora2_video_deflicker`, `bd_studio_sora2`;
- `seedance-1-5`, `seedance1_5`, `seedance_1_5`.

`gemini_omni` is still priced in `/job-sets/costs` (3 cr/s) even though it is retired in the UI.

**Behind flags or fallbacks:**

- `wan4_0` (flag off, no cost row, falls back to `wan3_0`);
- `kling_4_0_flash` (flag on, falls back to `kling4_0`);
- `seedance_2_5_flash(_edit/_extend)` (flag on, `pricedAs: seedance_2_5_flash`, "coming soon" on the cobalt surface).

Legacy basic/starter plans (`planVersion ≤ 30`) keep `veo-3-1-lite`, `seedance_2_0` and `private-ui` (labelled
"Seedance 2.5").

**Costs-only** (priced in `/job-sets/costs`, but no `defineJob` or route in this build): see the list under the
generated table. Notable ones:

- `scene_switch`: tiers basic/pro × resolution, with `cost_per_run`, `masks_cost_per_frame`, `picture_cost` and
  `look_cost`. A per-run plus per-second product, not shipped in the UI yet.
- `hf_evolution` (7 cr/s at 720p) and `intone`.
- `video_character_asset`, `youtube_faceless_video`, `ai_host_video`, `elevenlabs_video_to_music`, `fps_boost`,
  `topaz_hyperion_2_5`, `sam_3_video`, `depth_anything_video`, `p_image_ideogram` (Ideogram with a `thinking`
  level) and `gif` (create 1 / recreate 3).

Most of these are server-side steps of chains or apps (e.g. object edit, faceless, Genjutsu Flash), so the client
never declares them.

**JS-only (no cost row):**

- video: `veo3_1`, `veo3_1_lite`, `sora2_video`, `magi_2`, `minimax_h3`, `minimax_h3_max`, `kling2_6`, `wan2_x`,
  `grok_video`, `flux_3_video_edit`;
- image: all Soul types, `nano_banana*` except 2.1, `seedream_v4_5` / `v5_lite`, `flux_2` / `kontext` / `3_image`,
  `z_image`, `reve`;
- upscale: `topaz_*`, `bytedance_video_upscale`.

These are priced by client fallback tables, `credits()` functions or a server quote (`dry_run`). See
[`COST_FORMULAS.md`](COST_FORMULAS.md).

**Enum-only** (in the `JobSetType` enum, with no schema): `claudesfield_image`, `image_to_3d`, `autosprite`,
`character_sheet(_vibe)`, `katana`, `next_shots`, `video_scene_edit`, `concat_videos`, `ip_detection`, `soul_cast`,
`soul_location`, `mirelo_text_to_audio`, `sonilo_music`, `inworld_text_to_speech`.

---

## 6. Confidence and unknowns

| Claim | Status |
|---|---|
| Job types per product, routes, picker ids → `job_set_type` | **From JS** (build `548e0f3a`) |
| OpenAI behind GPT Image; Google behind Nano Banana; xAI behind Grok image | **Confirmed by API data** (`upstream_usage` shapes and USD values on public community jobs) and by JS/landing text |
| ByteDance (Seedance/Seedream), Google (Veo/Gemini Omni), Alibaba (Wan/HappyHorse), MiniMax, BFL, Ideogram, Recraft, ElevenLabs, Topaz, Sand AI | **Confirmed by JS/landing vendor strings** |
| Kling = Kuaishou | Brand confirmed; **company inferred from the name** (no "Kuaishou" string anywhere) |
| Qwen, Z-Image (Alibaba), SAM 3 (Meta), Depth Anything, Sync Labs, InfiniteTalk, Reve, Mirelo, Sonilo, Inworld | **Inferred from the name** |
| Wan 2.5 can run on Alibaba Cloud (`use_alibaba`) | **JS flag** confirmed; which host runs the other path is unknown |
| Genjutsu can run on MAGI-2 (`use_magi_2`) | **JS flag** confirmed; default backend unknown |
| Cinema Studio 4.0 runs Seedance 2.5 | **Landing + identical price table** (strong inference) |
| Reframe, object edit and draw-to-video run Seedance 2.0; Videoshop / Ad Multiplier / Intone run Seedance 2.5; viral presets run Seedance 2.0 (Fast) | **Price twins only** (inferred) |
| Soul is Higgsfield's own model | Landing ("Higgsfield's proprietary photorealistic avatar model"); base architecture unknown |
| `outpaint` uses Gemini 3 Pro Image | **Inferred** from token price ratios in `upstream_usage` |
| GPT Image codenames (`videotape-alpha`, `aurora-img-alpha`, `star-swirl-alpha`) | **Verified in stored params**; what they map to at OpenAI is unknown |
| No third-party inference host (fal, Replicate, BytePlus) in the client | **Verified by absence** in 580 chunks; server-side hosting is invisible |

**Unknowns:**

- Video-step models in the 63 Nano Banana apps and in viral presets (opaque node UUIDs).
- Soul's base model.
- Mixed-media, Popcorn, Faceless and AI Host backends.
- Lipsync and Topaz prices (server-side).
- Seedance draft pricing.
- MCP tool schemas.
- The public API's model ids and prices (`open.higgsfield.ai` needs a key).

### Reproduce

```bash
python scripts/gen_model_catalog.py --write                                           # refresh §4
python -m higgsfield_scraper scrape community --max-items 300 --with-raw-params -q   # params + upstream_usage
python -m higgsfield_scraper scrape site --what apps,landings,mixed-media -q          # app slug_type, vendor text
grep -o 'type:`[a-z0-9_]*`,output:`[a-z]*`' samples/higgsfield/js2/*.js | sort -u     # defineJob registry
```
