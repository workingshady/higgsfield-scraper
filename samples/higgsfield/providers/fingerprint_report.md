# Provider fingerprints

925 unique jobs, 34 job types, 74 raw envelopes from 63 run folders.

## URL hosts (all jobs)

| host | jobs |
|---|---|
| `d8j0ntlcm91z4.cloudfront.net` | 920 |
| `d2ol7oe51mr4n9.cloudfront.net` | 551 |
| `cdn.higgsfield.ai` | 542 |

## Third-party platform hosts

- none found

## Per job_set_type

| job_set_type | jobs | fingerprints (jobs) | meta.cost shapes | hosts |
|---|---|---|---|---|
| `viral_hub_video` | 225 | - | - | `cdn.higgsfield.ai`, `d2ol7oe51mr4n9.cloudfront.net`, `d8j0ntlcm91z4.cloudfront.net` |
| `z_image` | 70 | - | - | `d8j0ntlcm91z4.cloudfront.net` |
| `wan2_5_video` | 51 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net`, `cdn.higgsfield.ai` |
| `gpt_image_2_6` | 50 | meta.cost present (50); openai images usage (input_text_tokens/output_image_tokens) (50); openai req_ id (50) | `{cached_image_input_tokens,cached_text_input_tokens,input_image_tokens,input_text_tokens,output_image_tokens,output_text_tokens,request_id}` (50) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `flux_2` | 50 | trace_id != job id (8) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `topaz_image` | 50 | trace_id != job id (15) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net`, `cdn.higgsfield.ai` |
| `seedance_2_0` | 50 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai` |
| `sora2_video` | 50 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai`, `d2ol7oe51mr4n9.cloudfront.net` |
| `minimax_hailuo` | 41 | - | - | `cdn.higgsfield.ai`, `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `text2image_soul_v2` | 39 | flag use_green=True (39); flag use_green_aidar=False (39); flag use_refiner=False (39); flag use_relax=False (39); flag use_sage_attention=False (39) | - | `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai`, `d2ol7oe51mr4n9.cloudfront.net` |
| `seedance_2_5` | 34 | - | - | `cdn.higgsfield.ai`, `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `nano_banana_2` | 30 | trace_id != job id (10) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `kling3_0` | 29 | - | - | `cdn.higgsfield.ai`, `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `soul_cinematic` | 26 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai`, `d2ol7oe51mr4n9.cloudfront.net` |
| `magi_2` | 23 | - | - | `cdn.higgsfield.ai`, `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `nano_banana_2_1` | 22 | meta.cost scalar number (10); trace_id != job id (6) | scalar 0.039009–0.12042 (n=10) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `recraft_v4_1` | 19 | - | - | `d8j0ntlcm91z4.cloudfront.net` |
| `seedream_v5_pro` | 10 | trace_id != job id (5) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `gpt_image_2` | 10 | meta.cost present (10); openai images usage (input_text_tokens/output_image_tokens) (10); openai req_ id (10) | `{cached_image_input_tokens,cached_text_input_tokens,input_image_tokens,input_text_tokens,output_image_tokens,output_text_tokens,request_id}` (7); `{input_image,input_image_tokens,input_text,input_text_tokens,output_image,output_image_tokens,request_id}` (2); `{cached_image_input_tokens,cached_text_input_tokens,input_image,input_image_tokens,input_text,input_text_tokens,output_image,output_image_tokens,output_text,output_text_tokens,request_id}` (1) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `grok_image` | 7 | meta.cost scalar number (7) | scalar 0.022–0.1 (n=7) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `seedream_v4_5` | 6 | flag use_unlim=False (2); flag use_unlim=True (4) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `flux_3_image` | 6 | meta.cost scalar number (6) | scalar 4.1–60.7 (n=6) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `gpt_image_2_6_flare` | 5 | meta.cost present (5); openai images usage (input_text_tokens/output_image_tokens) (5); openai req_ id (5) | `{cached_image_input_tokens,cached_text_input_tokens,input_image_tokens,input_text_tokens,output_image_tokens,output_text_tokens,request_id}` (5) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `grok_image_2_0` | 5 | meta.cost scalar number (5) | scalar 0.06–0.08 (n=5) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `seedream_v5_lite` | 4 | trace_id != job id (1) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `nano_banana_flash` | 3 | gemini-style token buckets (thinking_tokens) (1); meta.cost present (1); trace_id != job id (1) | `{input,input_tokens,output,output_tokens,thinking,thinking_tokens,total,total_tokens}` (1) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `cinematic_studio_soul_location` | 2 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai` |
| `gpt_image_2_5` | 2 | meta.cost present (2); openai images usage (input_text_tokens/output_image_tokens) (2); openai req_ id (2) | `{cached_image_input_tokens,cached_text_input_tokens,input_image,input_image_tokens,input_text,input_text_tokens,output_image,output_image_tokens,output_text,output_text_tokens,request_id}` (2) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `outpaint` | 1 | gemini-style token buckets (thinking_tokens) (1); meta.cost present (1) | `{input,input_tokens,output,output_tokens,thinking,thinking_tokens,total,total_tokens}` (1) | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `text2image_soul` | 1 | flag use_relax=False (1); flag use_sage_attention=False (1) | - | `d2ol7oe51mr4n9.cloudfront.net`, `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai` |
| `ai_influencer` | 1 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `cdn.higgsfield.ai` |
| `topaz_image_generative` | 1 | - | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `image_auto` | 1 | trace_id != job id (1) | - | `d8j0ntlcm91z4.cloudfront.net`, `d2ol7oe51mr4n9.cloudfront.net` |
| `text2keyframes` | 1 | - | - | `d8j0ntlcm91z4.cloudfront.net` |

## Provider-ish keys (where: job count)

- `job_set_client_meta…source`: 225
- `meta_cost…request_id`: 67
- `params…use_sage_attention`: 40
- `params…use_relax`: 40
- `params…use_green`: 39
- `params…use_refiner`: 39
- `params…use_green_aidar`: 39
- `params…use_unlim`: 6

## Id-shape examples (truncated)

- `gpt_image_2` openai req_ id: `request_id=req_958a…`
- `gpt_image_2_5` openai req_ id: `request_id=req_34ef…`
- `gpt_image_2_6` openai req_ id: `request_id=req_a22f…`
- `gpt_image_2_6_flare` openai req_ id: `request_id=req_164d…`

## JS platform strings (744 chunks)

| term | chunks |
|---|---|
| `fal.ai` | 0 |
| `fal.run` | 0 |
| `fal.media` | 0 |
| `@fal-ai` | 0 |
| `falserverless` | 0 |
| `replicate.com` | 0 |
| `replicate.delivery` | 0 |
| `byteplus` | 1 |
| `volcengine` | 0 |
| `volces.com` | 0 |
| `ark.cn-beijing` | 0 |
| `ark.ap-southeast` | 0 |
| `dashscope` | 0 |
| `aliyuncs` | 0 |
| `aiplatform.googleapis` | 0 |
| `generativelanguage` | 0 |
| `vertexai` | 0 |
| `bedrock` | 0 |
| `azure` | 0 |
| `openai.azure` | 0 |
| `together.ai` | 0 |
| `together.xyz` | 0 |
| `fireworks.ai` | 0 |
| `deepinfra` | 0 |
| `novita` | 0 |
| `wavespeed` | 0 |
| `piapi` | 0 |
| `modal.run` | 0 |
| `baseten` | 0 |
| `runpod` | 0 |
| `openrouter` | 1 |
| `api.openai.com` | 1 |
| `api.x.ai` | 0 |
| `klingai.com` | 0 |
| `minimaxi` | 6 |
| `api.elevenlabs.io` | 0 |
| `topazlabs` | 0 |
