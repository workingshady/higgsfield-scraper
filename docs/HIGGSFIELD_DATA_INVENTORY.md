# Higgsfield.ai: complete feature and data inventory

**What this is:** every product feature, page and API data source on higgsfield.ai, and what can be scraped from
each one.

**Checked:** 2026-11-25. Build `45572506390-1-production`. Requests were sent from country EG with **no login**.

**Sources:**
- the 176 frontend JS bundles: 589 routes and 728 API call paths extracted;
- all 12 sitemaps: 1,384 URLs;
- live GET tests: 361 API paths, plus 30 follow-ups with real parameters and IDs;
- the existing pricing work.

**Reproduce:**
- `python scripts/recon_probe.py` writes `samples/higgsfield/inventory/probe_results.jsonl`;
- `samples/higgsfield/inventory/routes.json` and `js_call_paths.json` hold the raw lists.

Related docs: [`REVERSE_ENGINEERING.md`](REVERSE_ENGINEERING.md) (how pricing was mapped) and [`ENDPOINTS.md`](ENDPOINTS.md)
(pricing endpoint fields).

---

## 1. Summary

| Bucket | Count | Scrapable? |
|---|---:|---|
| **Public JSON APIs** (HTTP 200 without login) | **37** | ✅ Yes. Clean JSON, paginated, listed in §3 |
| **Public website pages** (in sitemaps) | **1,384** | ✅ Yes. HTML pages listed in §4 (blog, academy, apps, effects, help center, …) |
| Frontend routes (screens/features) | 589 | Feature map (§2). Most screens are app UIs, not data |
| API paths in JS that need a login, or aren't API paths (401) | 283 | 🔒 Only with your session token, and only your own account's view (§5) |
| API paths blocked by bot protection (DataDome 403) | 3 | ⛔ Not scraped (§6) |
| API paths that change data (create, buy, vote, delete, generate, …) | 239 | ⛔ Never called (§7) |
| API paths needing an ID that wasn't available | 128 | Detail endpoints, some filled via list results (§3) |

**Biggest public datasets:**

| Dataset | Items |
|---|---:|
| Community generations | **78,595** (6,701 approved) |
| Soul samples | 1,263 |
| Motion presets | 419 (each with sample videos) |
| Blog posts | 351 |
| Academy pages | 199 |
| Avatars | 100 |
| Apps | 98 |
| Effects examples | 87 |
| Voices | 82 |
| Pricing | 86 models, 25 plan sets (already scraped) |

---

## 2. Feature catalog (what Higgsfield offers)

Sources: the frontend routes, the marketing sitemap (168 landing pages) and the app sitemaps. Login-only means the
feature's data is per-user.

### 2.1 Generation: image
| Feature | Routes / pages | Notes |
|---|---|---|
| Image generator (all image models) | `/image`, `/ai/image`, `/ai/custom-image`, `/flow/image`, `/ai-image` | GPT Image 2/2.5/2.6, Nano Banana (2, 2.1, Pro), Seedream 4.5/5.0, Flux 2, Ideogram 4.5/4.6, Recraft v4, Kling image, Minimax image, Grok image… |
| Soul (Higgsfield's own photo model) | `/soul`, `/soul/$styleId`, `/soul-intro`, `/soul-cinema`, `/soul-cast-intro` | Styles: soul, cinematic, keyframe |
| Character / Soul ID (consistent person) | `/character`, `/character-sheet`, `/characters`, `/upload/$characterId`, `/cast` | Custom references and training |
| Image editing / Canvas | `/canvas`, `/canvas/templates/$templateId`, `/edit-image`, `/image-editing`, `/layers` | Canvas templates, layers |
| Photo apps | `/photodump`, `/photoset`, `/moodboard`, `/fashion`, `/clothing` | |
| Upscale / enhance / translate | `/upscale`, `/ai-image-upscaler`, `/image-translations`, `/seedream-layer-separation` | |

### 2.2 Generation: video
| Feature | Routes / pages | Notes |
|---|---|---|
| Video generator (all video models) | `/video`, `/ai/video`, `/ai/custom-video`, `/flow/video`, `/ai-video` | Seedance 2.0/2.5/4K, Kling 2.5–4.0, Veo 3.1, Wan 2.2–3.0, Minimax Hailuo, Grok Imagine, Sora 2, Gemini Omni… |
| Motion presets (camera/VFX moves) | `/motion`, `/motion/$motionId`, `/motion/$motionId/$sampleId` | **419 public presets** |
| Effects (viral effects) | `/effects`, `/effects/examples/$presetSlug`, `/viral-effects`, `/viral-presets` | 87 public example pages |
| Cinema Studio | `/cinema-studio`, `/cinematic-video-generator` | Camera settings, creative controls |
| Video edit / reframe / upscale | `/video-edit`, `/video-editor`, `/ai/video/edit`, `/ai/video/reframe`, `/ai-video-upscaler`, `/videoshop` | |
| Mixed media | `/mixed-media`, `/mixed-media-presets/preset/$id` | 33 public presets |
| Genjutsu / Katana / What-If / 3D Jutsu | `/genjutsu`, `/genjutsu-for-reels`, `/katana`, `/what-if`, `/3d-jutsu` | Higgsfield apps (shareable `/shared/$code` links) |
| Draw-to-video / sketch | `/draw`, `/sketch-to-video-ai` | |

### 2.3 Generation: audio and lipsync
| Feature | Routes | Notes |
|---|---|---|
| Speech / TTS | `/speech`, `/text-to-speech`, `/ai-voice-generator` | **82 public voices** |
| Voice change / cloning / dubbing | `/ai-voice-changer`, `/voice-cloning`, `/ai-video-translator` | |
| Lipsync Studio | `/lipsync-studio`, `/kling-lipsync`, `/infinite-talk`, `/sync-so` | Kling, Infinite Talk, Sync |
| Music / sounds | `/music-cards`, `/audio` | **11 public sounds** |

### 2.4 Studios and agents (multi-step products)
| Feature | Routes |
|---|---|
| Marketing Studio / Ads Studio / Ad Multiplier | `/marketing-studio`, `/ads-studio`, `/ad-multiplier`, `/multiplier`, `/playable-ads`, `/brand-research`, `/b/$brandId` |
| Short Drama / Micro-dramas / Mangaka (comics) | `/short-drama`, `/micro-dramas`, `/mangaka`, `/production`, `/episodes`, `/welcome-to-drama` |
| Shorts Studio / Faceless Studio / AI Host | `/shorts-studio`, `/shorts`, `/faceless-studio`, `/faceless-channel`, `/ai-host` |
| AI Influencer Studio / Avatars | `/ai-influencer`, `/ai-influencer-studio`, `/avatar/*`, `/avatars` (**100 public avatars**) |
| Realtor / Property Studio | `/property-studio`, realtor-studio API |
| Agent / Imagine / Supercomputer / Higgsfield Assembly | `/agent`, `/new/agent`, `/imagine`, `/supercomputer`, `/higgsfield-assembly`, `/content-factory` |
| Editing Room / Projects | `/editing-room`, `/projects`, `/p/$projectId` |
| Games / playable | `/playable`, `/games/$gameId`, `/gaming`, `/arena` |
| Websites / app builder | `/websites`, `/app-builder-intro`, `/$appId/edit` |

### 2.5 Community and social
| Feature | Routes | Public data? |
|---|---|---|
| Community feed / generations | `/community`, `/community/generations`, `/community/feed`, `/explore`, `/feed` | ✅ **78,595 generations** |
| Model communities | `/soul-community`, `/soul-cinema-community`, `/seedance-2-community`, `/seedance-2-5-community`, `/seedance-4k-community`, `/kling-30-community`, `/gpt-image-2-community`, `/marketing-studio-community`, `/mixed-media-community`, `/nano-banana-pro-preview`, `/sora-video`, `/wan-video` | ✅ via the same API, filtered by `model` |
| Projects / series showcase | `/community/projects`, `/community/originals`, `/original-series` | ✅ project publications, 41 original-series pages |
| Contests / weekly challenge / Adathon | `/contests`, `/contests/$slug`, `/community/contests`, `/talent-contest` | ✅ contests + full detail (rules, rewards, judges) |
| Creators / talents / talent hub | `/community/creators`, `/talents`, `/talents-hub/*`, `/earn` | Partly (talent blog posts public) |
| Rooms (group chats) | `/community/rooms/$roomSlug` | 73 room pages in the sitemap |
| Community blog / magazine | `/community/blogs`, `/community/magazine/$issue` | ✅ |
| Profiles | `/profile/$username`, `/@user/projects` | Public profile data comes embedded in each generation |
| Comments, likes, related, user search | — | 🔒 login |

### 2.6 Learning and content
| Feature | Routes | Public? |
|---|---|---|
| Blog | `/blog/$slug` (351) | ✅ API + pages |
| Academy (courses, lessons, certificates) | `/academy/courses/$course/$lesson` (199) | ✅ pages; JSON API needs login |
| Creator Hub: help center, case studies, changelog | `/creator-hub/*` (116) | ✅ pages |
| Enterprise help center | `/enterprise-help-center/*` (35) | ✅ pages |
| Guides, prompt guides | `/guides/$guideId`, `/nano-banana-pro-prompt-guide` | ✅ pages |

### 2.7 Integrations and developer
| Feature | Routes |
|---|---|
| MCP server + skills marketplace | `/mcp`, `/mcp/$slug` (76 pages), `/skills/$bundle/$skill`, `/mcp-pricing`, `/mcp-credits` |
| CLI / API | `/cli`, `/higgsfield-api` |
| AI assistants | `/claude`, `/cursor`, `/manus`, `/gpt-astra` |
| Plugins | `/plugins/{after-effects, blender, davinci, figma, minecraft, photoshop, premiere-pro}` |
| Connectors / marketplace | `/connectors/$connector`, `/marketplace/{apps, skills, employees, games, connectors}` |
| AI employees | `/employees`, `/create-employees`, `/marketplace/employees` |
| Telegram bot, desktop app, mobile | `/higgsfield-telegram-intro`, `/desktop`, `/mobile/*` |

### 2.8 Plans, billing and account
| Feature | Routes | Public? |
|---|---|---|
| Pricing, plans, offers, comparison | `/pricing`, `/pricing/offer`, `/special-offer`, `/team-plan`, `/enterprise` | ✅ **already scraped** (`--sections all`) |
| Credits, top-ups, unlimited bundles, auto top-up | `/credits-usage`, `/unlimited-access-history`, `/billing`, `/subscription` | 🔒 login (`--sections auth`) |
| Workspaces / teams / members / SSO | `/organization`, `/members`, `/sub-workspaces`, `/sso`, `/enter-team` | 🔒 login |
| Library / assets / folders / favourites / trash | `/library`, `/asset`, `/folders/$id`, `/favorites`, `/trash`, `/files` | 🔒 login (your own content) |
| Referrals / affiliate / achievements / quizzes | `/referrals`, `/affiliate`, `/achievements`, `/quiz` | 🔒 login |

---

## 3. Public JSON APIs (no login): exact endpoints, parameters and fields

Base: `https://fnf-api-gw.higgsfield.ai/fnf`. Header: `Accept: application/json`. Totals are live values from 2026-11-25.

### 3.1 Community generations ⭐ largest dataset

| Endpoint | Params | Total | Notes |
|---|---|---:|---|
| `GET /publications/community/trending` | `size`, `cursor` (float), `type` = `all\|image\|video`, `model` (repeatable job_set_type), `preset_id` (repeatable motion ID), `resolution`, `approved=true\|false` | **78,595** | Main community feed |
| `GET /publications/community/approved` | same | **6,701** | Curated (approved) only |
| `GET /publications/community/trending/top` | `size`, `cursor`, `type` | 50 | Top picks |
| `GET /publications/community/model-x` | `size`, `cursor` | 64 | Showcase for one featured model |
| `GET /publications/{publication_id}` | — | detail | Same fields as the list |
| `/publications/{id}/comments`, `/related`, `/users/search` | — | 🔒 | Login |

**Fields per generation** (all public):

| Group | Fields |
|---|---|
| Model | `job_set_type` (joins to the pricing `model_id`), `job_set_id`, `job_set_parent_id` |
| **Prompt and settings** (`params.*`) | `prompt`, `width`, `height`, `aspect_ratio`, `quality`, `resolution`, `model` (internal model name, e.g. `aurora-img-alpha`), `medias[]` (input images), `reference_elements[]`, `remove_bg`, `background`, `output_format`, and per-model extras such as `duration` |
| Results | `results.raw.url`, `results.min.url` (CDN media), `status`, `can_upgrade_to_4k`, `expires_at` |
| Engagement | `publication.views_count`, `likes_count`, `approved`, `pinned_at` |
| Timing | `created_at`, `published_at` (unix) |
| Moderation flags | `ip_check_finished`, `ip_detected`, `deepfake_consent_required`, `can_bypass_ip` |
| Upstream usage | `meta.cost`: the **provider's** token usage (e.g. `input_text_tokens`, `output_image_tokens` for GPT Image). This is **not** Higgsfield credits, and it's null for most models |
| ⚠️ Personal data | `user_id`, `profile.username`, `avatar_url`, `instagram/twitter/youtube/tiktok_handle`, `badges` |

**What it's useful for:**
- real prompts per model;
- which models and settings people actually use;
- popularity (views and likes);
- prompt examples for each pricing model;
- per-generation cost, by joining `job_set_type` + `params` to the pricing price points.

**Personal data:** usernames and social handles are personal data, so by default a scraper should keep `user_id`
pseudonymous or drop the `profile.*` fields.

### 3.2 Presets, styles and assets catalog

| Endpoint | Params | Total | Fields |
|---|---|---:|---|
| `GET /motions` | `size` (required), `cursor`, `category`, `hide_collection` | **419** | `id, name, preset_family` (kling/veo/…), `categories, tags, media` (preview), `params, priority, cms_id` |
| `GET /motions/{id}` | — | detail | + `description` |
| `GET /motion-samples` | `motion_id` (required), `size` | per preset | sample videos (`media`, `preset_family`) |
| `GET /styles` | `size` | 5 | style presets |
| `GET /avatars` | `size` | **100** | `id, name, media, params` |
| `GET /voices` | `size` | **82** | `name, gender, age, categories, voice_url, waveform_url, image_url, is_gpt` |
| `GET /reference-elements/voices` | `cursor` | paginated | voice reference elements: `supported_models, source, type` |
| `GET /sounds` | `size` | 11 | `name, description, sound_url, waveform_url` |
| `GET /soul-samples` | `size` | **1,263** | Soul model sample generations (same shape as community generations, without profile) |
| `GET /viral-hub/types` | — | 6 | viral effect categories (`id, name, slug, priority`). `/viral-hub/presets?lang=` returned empty without `category` |
| 🔒 `/soul-styles`, `/mixed-media-presets`, `/veo3-styles`, `/kling-motions`, `/seedance-motions`, `/wan2-*-motions`, `/minimax-motions`, `/series`, `/katana-categories` | | | Login |

### 3.3 Projects, series and contests

| Endpoint | Params | Total | Fields |
|---|---|---:|---|
| `GET /project-publications` | `limit`, `cursor` | paginated | `name, slug, description, type` (series/…), `duration_seconds, cover, gallery_media, trailer, tags, categories, authors, team, views, likes, comments, awards, contest_badges, show_prompts, is_featured, created_at` |
| `GET /project-publications/recommended` | `scope`, `cursor`, `limit`, `current_publication_id` | paginated | same + `feed` |
| `GET /project-publications/categories` | — | 2 | `label, slug` |
| `GET /project-publications/{id}` | — | detail | full project |
| `GET /contests` | — | 4 active | `title, slug, contest_type, status, start_at, end_at, prize_pool` (e.g. $1,000,000), `submissions_count, judges, some_contestants, winner, preview media` |
| `GET /contests/by-id/{id}` | — | detail (50 KB) | + `settings, rewards, rules_effective_at, results_published` |
| `GET /contests/{id}/submissions` | — | list | contest entries |
| `GET /contests/trending` | — | 204 (empty right now) | |

### 3.4 Blog and talent content

| Endpoint | Params | Fields |
|---|---|---|
| `GET /blog/posts/recommended` | `cursor`, `size` | `title, slug, subtitle, tags, cover, author, content_url, reading_time_minutes, likes_count, views_count, related_posts, published_at` |
| `GET /community/discovery/talents/blog-posts` | `cursor` | talent/creator blog posts (same shape) |
| 🔒 `/blog/posts` (full list) | | Login. Use the sitemap (351 posts) instead |

### 3.5 Pricing (✅ already implemented: `python -m higgsfield_scraper scrape`)
`/subscriptions/v2/plans`, `/subscriptions/v2/compare`, `/subscriptions/v2/plan-benefits`, `/job-sets/costs`,
`pricing.higgsfield.ai/v2/pricing-config`. See [`ENDPOINTS.md`](ENDPOINTS.md).

### 3.6 Small public config endpoints
| Endpoint | Contents |
|---|---|
| `GET /business-unlim/state` | Business-plan unlimited promo: `plan_cards` (monthly/annual), `pricing_banner`, `promo`, `window` |
| `GET /datetime-settings` | 17 scheduled UI events (`source`, `datetimes`): sale start/end times |
| `GET /game-gift/networks` | Game-gift promo networks |
| `GET /feature`, `/user/features`, `/user/meta` | Anonymous feature flags |
| `GET /youtube-faceless/hot-right-now` | Trending faceless-channel topics (empty today) |

---

## 4. Public website pages (from the 12 sitemaps, 1,384 URLs)

These are HTML pages. A scraper would use Scrapy's `SitemapSpider` plus HTML or embedded-data parsing.

| Sitemap | URLs | URL patterns | Contents |
|---|---:|---|---|
| `sitemap-marketing.xml` | 396 | 168 landing pages (`/ai-image`, `/kling-3.0`, `/seedance`, `/veo3.1`, …), `/mcp/*` (76), `/community/rooms/*` (73), `/plugins/*` (7), localized blog (`/es|ja|ko|de/blog`) | Feature and model descriptions, MCP skills and how-tos, rooms |
| `blog/sitemap.xml` | 351 | `/blog/$slug`, `/blog/author/*` (4) | Articles: model guides, comparisons, announcements |
| `academy/sitemap.xml` | 199 | `/academy/courses/$course/$lesson` | Courses and lessons (e.g. "seedance-25-ai-filmmaking", "claude-higgsfield-ai-ad-agency") |
| `creator-hub/sitemap.xml` | 116 | help center: ai-models, credits, plans, refunds, tools, getting-started; case studies (26) | **Official FAQ: credits, refunds, plans** |
| `apps/sitemap.xml` | 98 | `/apps/$slug` | App catalog (Face Swap, Shots, Skin Enhancer, Zooms, …) |
| `effects/sitemap.xml` | 87 | `/effects/examples/$preset` | Effect preset examples |
| `original-series/sitemap.xml` | 41 | `/original-series/$series/$episode` | Higgsfield original films |
| `enterprise-help-center/sitemap.xml` | 35 | manage-account, platform, support | Enterprise docs |
| `mixed-media-presets/sitemap.xml` | 33 | `/mixed-media-presets/preset/{uuid}` | Mixed-media presets |
| `sitemap-projects.xml` | 28 | `/@user/projects/$slug` | Featured community projects |
| `sitemap-es.xml`, `sitemap-ko.xml` | — | localized marketing | |

Also: `https://higgsfield.ai/pricing.md` is a markdown snapshot of the US prices.

---

## 5. Needs a login (🔒 401 `Invalid or expired token`)

> **Correction 2026-11-26 (verified with a real login):** the soul/veo3 styles, per-model motion lists, mixed-media,
> katana, faceless and marketing catalogs below are **public** on other bases (`cms.higgsfield.ai`, `/fnf-cms-api`),
> and comments are public on `/fnf-community`. The `fnf/<path>` guesses return 404 even when logged in. Only
> `/color-presets` and `/camera-settings` need a session. The rest of this list is re-checked in
> `LOGIN_COVERAGE.md` (login audit, in progress).

**Caveat:** the gateway checks auth **before** routing, so unknown paths and website routes (e.g. `/about`, `/pricing`)
also return 401. The 283 paths below are a mix of real login-only APIs and non-API strings found in the JS.

With your own session token (`--token`), these would return **your account's** data only:

| Area | Examples |
|---|---|
| Your content | `/assets`, `/assets/favourites`, `/folders`, `/library/`, `/jobs/accessible`, `/media/accessible`, `/video/accessible`, `/file/accessible`, `/custom-references` (your trained characters), `/reference-elements` |
| Your account and billing | `/user`, `/user/profile`, `/user/free-gens/v2`, `/user/offers`, `/user/personal-promo`, `/workspaces/*` (details, capabilities, subscription, usage stats, seat bonus), `/subscriptions/v2/packages`, `/subscriptions/bundle/unlim-catalog` |
| Catalogs that need any session | `/soul-styles`, `/soul-cinematic-styles`, `/soul-keyframe-styles`, `/mixed-media-presets`, `/veo3-styles`, per-model motion lists (`/kling-motions`, `/kling2-6-motions`, `/seedance-motions`, `/wan2-2-motions`, `/wan2-5-motions`, `/minimax-motions`), `/series`, `/katana-categories`, `/camera-settings`, `/applications/explore`, `/academy/_catalog`, `/api/v1/courses` |
| Social | `/users/search`, `/users/feed`, `/users/suggestions`, `/publications/{id}/comments`, `/publications/{id}/related` |
| Studios | `/mangaka/*`, `/realtor-studio/*`, `/youtube-faceless/channels`, `/chains/*`, `/lipsync/*`, `/v1/season`, `/v2/quizzes` |

Catalogs such as soul styles and per-model motions are probably the same for every user, so one logged-in run
would capture them.

## 6. Blocked by bot protection (⛔ do not scrape)
`/jobs`, `/media` and `/v2/reference-elements/picker` returned **403 with a DataDome captcha**
(`geo.captcha-delivery.com`). This is active bot protection. These paths are excluded, and no evasion is attempted.

## 7. Never called (could change data)
239 paths matched action words and were **not** requested. Examples: purchase, checkout, subscribe, change plan,
top-up, generate (`/jobs/v2/*`), upload, publish, like, vote, comment, report, follow, delete, share, claim reward,
redeem, invite. The full rule is the `MUTATION` regex in `scripts/recon_probe.py`.

---

## 8. Scraper status

**Update 2026-11-25:** six scrapers are built (`python -m higgsfield_scraper scrapers`); `site` covers the sitemap page types that were left (§4).

| Scraper | Status | Docs |
|---|---|---|
| `pricing` | ✅ built | [`ENDPOINTS.md`](ENDPOINTS.md) |
| `community` | ✅ built, with an optional cost estimate | [`scrapers/community.md`](scrapers/community.md), [`scrapers/cost-estimate.md`](scrapers/cost-estimate.md) |
| `catalog` | ✅ built: public catalogs, plus the opt-in group (mostly public CMS lists; color/camera need a login) | [`scrapers/catalog.md`](scrapers/catalog.md) |
| `projects` | ✅ built | [`scrapers/projects.md`](scrapers/projects.md) |
| `blog` | ✅ built: blog, help centers, case studies, changelog, talent posts | [`scrapers/blog.md`](scrapers/blog.md) |
| `site` | ✅ built: apps (+ credit cost per template), academy courses + lessons (Markdown), MCP skills + bundles, original-series series + episodes, mixed-media presets, landing/plugin pages (Markdown, FAQ, HowTo), rooms (opt-in, title only), promo APIs (`/datetime-settings`, `/business-unlim/state`, `/game-gift/networks`) | [`scrapers/site.md`](scrapers/site.md) |
| effects pages | ➖ not built: same presets as `catalog` viral presets; samples = community generations | [`scrapers/site.md`](scrapers/site.md) |
| `/feature`, `/user/meta`, `/user/features`, `/youtube-faceless/hot-right-now`, `/contests/trending` | ➖ not built: flags / empty | [`REVERSE_ENGINEERING.md`](REVERSE_ENGINEERING.md) §14 |

The original plan follows.

### Original plan: what could be built next

All of these would reuse the existing run system: run folders, logs, the `http/` archive, validation, JSON + complete
CSVs, and `normalize`.

| # | Scraper / option | Data | Size | Effort | Notes |
|---|---|---|---:|---|---|
| 1 | **`community`** | generations: model, prompt, settings, results, engagement (+ optional profile) | 78,595 | Medium | Options: `--type image/video`, `--model`, `--approved`, `--max-items`, `--with-profiles` (off by default). Join to pricing for estimated credits per generation |
| 2 | **`presets`** | motions + samples, avatars, voices, sounds, styles, soul samples, viral types | ~1,900 | Easy | Options: `--kinds motions,voices,…`, `--with-samples` |
| 3 | **`projects`** | project publications + categories, contests + detail + submissions | hundreds | Easy | |
| 4 | **`blog`** | blog + talent posts (API), full list via sitemap | 351 | Easy | Optional article text from `content_url` |
| 5 | **`helpcenter`** | creator-hub help center + enterprise help (HTML) | 151 | Medium | Official credits, refunds and plan rules |
| 6 | **`site`** | sitemap crawler: marketing, apps, effects, academy, original series, MCP pages | 1,384 | Medium–hard | Per-page-type parsers |
| 7 | **`account`** (token) | your library, usage, credits, offers + login-only catalogs | your account | Medium | Token expires about every 60 s |
| — | pricing: `diff` command | compare two runs (prices, offers, new models) | — | Easy | Daily monitoring |
| — | pricing: `--locales all` | benefits and marketing text in 8 languages | — | Easy | |
| — | pricing: `pricing.md` cross-check | official US markdown vs `ps_a3` | — | Easy | |

**Suggested order:** community → presets → projects/contests → blog → help center → site crawler.

## 9. robots.txt status (for reference; the scraper doesn't obey it by default)
- `fnf-api-gw.higgsfield.ai` (all APIs above): **no robots.txt**.
- `higgsfield.ai` disallows `/me/`, `/library/`, `/asset/`, `/share/`, `/auth/`, `/payment/`, `/flow/`,
  `/mixed-media-community/`, `/sora-video/`, `/wan-video/`, `/nano-banana-pro*/`, `/effects/use/`, `/academy/saved`,
  `/quiz/`, …
- Every sitemap above is listed in robots.txt as crawlable.

---

## Appendix A: all frontend routes (589), by area

Generated from the JS route manifest. `$param` marks a dynamic segment.

- **$**: `/$`
- **$appId**: `/$appId/`, `/$appId/edit`, `/$appId/view`
- **$category**: `/$category`
- **$chatId**: `/$chatId`
- **$id**: `/$id`
- **$jobSetId**: `/$jobSetId`
- **$lesson**: `/$lesson`
- **$mode**: `/$mode/`, `/$mode/$modelVersion`
- **$projectId**: `/$projectId`, `/$projectId/read`
- **$projectSlug**: `/$projectSlug`
- **$publicationId**: `/$publicationId`
- **$sampleId**: `/$sampleId`
- **$slug**: `/$slug`
- **$subject**: `/$subject`
- **$versionId**: `/$versionId`
- **/**: `/`
- **3d-jutsu**: `/3d-jutsu`
- **about**: `/about`
- **academy**: `/academy`
- **accept-invitation**: `/accept-invitation/`, `/accept-invitation/logout`
- **achievements**: `/achievements`
- **activate**: `/activate/access`
- **activation**: `/activation`
- **ad-multiplier**: `/ad-multiplier`
- **ads-studio**: `/ads-studio`, `/ads-studio/google-ads`
- **affiliate**: `/affiliate`
- **agent**: `/agent`
- **agent-test**: `/agent-test`
- **ai**: `/ai`, `/ai/custom-image`, `/ai/custom-video`, `/ai/image`, `/ai/video`, `/ai/video/edit`, `/ai/video/motion`, `/ai/video/reframe`
- **ai-assist**: `/ai-assist`
- **ai-host**: `/ai-host`, `/ai-host/channel/$channelId`, `/ai-host/channels`, `/ai-host/new`
- **ai-influencer**: `/ai-influencer`, `/ai-influencer/shared/$code`
- **ai-influencer-studio**: `/ai-influencer-studio`
- **ai-reels**: `/ai-reels/shared/$code`
- **ai-video-upscaler**: `/ai-video-upscaler`
- **all**: `/all`
- **analysis**: `/analysis`
- **analyze**: `/analyze`
- **apps**: `/apps`, `/apps/`, `/apps/$slug`, `/apps/$slug/view`, `/apps/link-to-video-ad`, `/apps/shots`, `/apps/skin-enhancer`, `/apps/whats-next`, `/apps/zooms`
- **arena**: `/arena/`, `/arena/$category`
- **asset**: `/asset`
- **audio**: `/audio`
- **auth**: `/auth`, `/auth/email/`, `/auth/email/sign-in`, `/auth/email/sign-up`, `/auth/email/verify`, `/auth/forgot-password`, `/auth/login`, `/auth/logout`, `/auth/sign-in`, `/auth/sign-up`, `/auth/sso`, `/auth/sso-callback`, `/auth/token`
- **avatar**: `/avatar/$category`, `/avatar/$view/$category`, `/avatar/history`, `/avatar/preset`, `/avatar/prompt`, `/avatar/select`
- **avatars**: `/avatars`
- **b**: `/b/$brandId`
- **billing**: `/billing`
- **blocked**: `/blocked`
- **blog**: `/blog`, `/blog/5-Best-AI-Video-Models-2026-Tested-Compared`, `/blog/9-best-ai-video-generators-social-media`, `/blog/A-Guide-to-Kling-Turbo-Start-End-Frame`, `/blog/AI-Tool-That-Allows-You-to-Replace-Faces-in-a-Movie-Scene`, `/blog/Higgsfield-Earn-Talent-And-Collaboration-Monetization`, `/blog/Higgsfield-Upscale-Phone-vs-Camera`, `/blog/How-to-Use-Google-Veo-3.1-Complete-Guide-for-the-New-Model`, `/blog/Kling-3.0-is-on-Higgsfield-User-Guide-AI-Video-Generation`, `/blog/Nano-Banana-2-Gemini-3.1-Flash-AI-Image-Generation`, `/blog/Nano-Banana-Pro-Expert-Use-Cases`, `/blog/Soul-ID-AI-Character-Consistency`, `/blog/Visual-Consistency-of-AI-Generated-Photo-and-Video`, `/blog/WAN-2.6-by-Alibaba-User-Guide-on-Higgsfield`, `/blog/ai-motion-designer-after-effects-gpt`, `/blog/ai-product-videos-no-studio`, `/blog/ai-vs-vfx`, `/blog/best-affordable-ai-video-generators`, `/blog/best-ai-ad-generators-2026`, `/blog/best-ai-image-generators-2026`, `/blog/best-ai-video-generators-2026`, `/blog/best-sora-alternatives-2026`, `/blog/cinema-studio-3.0`, `/blog/cinema-studio-4-0`, `/blog/creator-partnership-program`, `/blog/higgsfield-ads-studio`, `/blog/higgsfield-global-film-festival`, `/blog/higgsfield-series-b-extension-tcv-nvidia`, `/blog/how-to-create-ai-influencer`, `/blog/how-to-make-ai-videos-beginners-guide`, `/blog/how-we-built-cinema-studio`, `/blog/photo-to-ai-video`, `/blog/seedance-2-on-higgsfield`, `/blog/seedance-unlimited`, `/blog/soul-2-vs-nano-banana-pro`, `/blog/why-ai-video-generations-fail`
- **blogs**: `/blogs`, `/blogs/$slug`
- **brand-research**: `/brand-research/`, `/brand-research/$brandId`
- **brands**: `/brands`
- **business-domain-verification**: `/business-domain-verification`
- **callback**: `/callback`
- **cancel**: `/cancel`
- **canvas**: `/canvas/`, `/canvas/$id`, `/canvas/$imageId`, `/canvas/templates/$templateId`
- **cast**: `/cast`, `/cast/$entityFolderId`
- **certificate**: `/certificate`
- **character**: `/character`
- **character-sheet**: `/character-sheet`
- **characters**: `/characters`
- **checkout-first** (10): checkout flows (UUID ids)
- **cinematic-video-generator**: `/cinematic-video-generator`
- **claude**: `/claude`, `/claude/billing/callback`, `/claude/billing/link`
- **client**: `/client`
- **clothing**: `/clothing`
- **collection**: `/collection/catch-the-pulse`, `/collection/effects`
- **community**: `/community`, `/community/`, `/community/blogs`, `/community/contests`, `/community/creators`, `/community/creators-2`, `/community/feed`, `/community/feed/$kind/$itemId`, `/community/feed/$postId`, `/community/generations`, `/community/magazine/$issue`, `/community/originals`, `/community/posts`, `/community/posts/$publicationId`, `/community/projects`, `/community/rooms`, `/community/rooms/$roomSlug`, `/community/talents-hub`
- **conditions**: `/conditions`
- **configuration**: `/configuration`
- **connected**: `/connected`
- **connectors**: `/connectors`, `/connectors/`, `/connectors/$connector`, `/connectors/$connector/`, `/connectors/$connector/$account`
- **consent**: `/consent/`, `/consent/mock-checkout`
- **contact**: `/contact`
- **content-factory**: `/content-factory`
- **contests**: `/contests`, `/contests/`, `/contests/$contestSlug`, `/contests/$contestSlug/`, `/contests/$contestSlug/submissions/`, `/contests/$contestSlug/submissions/$submissionId`, `/contests/adathon/`, `/contests/app/`, `/contests/apps/`, `/contests/weekly-challenge`, `/contests/weekly-challenge/`, `/contests/weekly-challenge/latest`
- **cookie-notice**: `/cookie-notice`
- **courses**: `/courses`, `/courses/$course`
- **create-employees**: `/create-employees`
- **create-model**: `/create-model`
- **creator-hub**: `/creator-hub`, `/creator-hub/case-studies`, `/creator-hub/case-studies/boxel-studio-higgsfield-case-study`, `/creator-hub/case-studies/one-of-one-studio-interview`, `/creator-hub/case-studies/vertexcgi-higgsfield-nba-finals-case-study`, `/creator-hub/changelog`, `/creator-hub/help-center`, `/creator-hub/help-center/credits/top-up-credits-expire`, `/creator-hub/help-center/troubleshooting/generation-is-stuck-or-failed`
- **creators**: `/creators`
- **creators-2**: `/creators-2`
- **credits-usage**: `/credits-usage`
- **debug**: `/debug/bf-week3-hero`, `/debug/card-playground`, `/debug/enterprise-onboarding`, `/debug/games-gift-ui`, `/debug/library-feed-states`, `/debug/mcp-plan-cards`, `/debug/seedance-2-5-modals`, `/debug/sso-domains-field`, `/debug/supercomputer/$folderId`, `/debug/upsell`
- **desktop**: `/desktop`, `/desktop/sign-in`
- **device**: `/device`
- **discord-verify**: `/discord-verify`
- **downloads**: `/downloads`
- **draw**: `/draw`
- **early-access**: `/early-access/higgsline/$accessId`
- **edit**: `/edit`
- **edit-image**: `/edit-image`
- **editing-room**: `/editing-room`, `/editing-room/$projectId`, `/editing-room/examples/$slug`
- **effects**: `/effects`, `/effects/$invalidSegment/$`, `/effects/examples/$presetSlug`, `/effects/examples/$presetSlug/$sampleId`, `/effects/tests`, `/effects/tests/effects`, `/effects/use`, `/effects/use/$slug`
- **effects-home**: `/effects-home`
- **elements**: `/elements`
- **email**: `/email/`, `/email/sign-in`, `/email/sign-up`, `/email/verify`
- **email-verification**: `/email-verification`
- **embed**: `/embed`
- **employees**: `/employees/`, `/employees/$employeeId/`, `/employees/$employeeId/edit`
- **enter-team**: `/enter-team`
- **enterprise-help-center**: `/enterprise-help-center/manage-account/usage-analytics`
- **enterprise-studio**: `/enterprise-studio`
- **episodes**: `/episodes`, `/episodes/$episodeId`
- **examples**: `/examples/$slug`
- **explainer**: `/explainer`
- **explore**: `/explore`
- **faceless-channel**: `/faceless-channel`
- **faceless-studio**: `/faceless-studio`, `/faceless-studio/`, `/faceless-studio/channel/$channelId/`, `/faceless-studio/channels`, `/faceless-studio/new`
- **fashion**: `/fashion`
- **favorites**: `/favorites`
- **feed**: `/feed`, `/feed/$kind/$itemId`, `/feed/$postId`
- **feedback**: `/feedback`
- **files**: `/files`
- **flow**: `/flow`, `/flow/avatar/preset/wan`, `/flow/image`, `/flow/video`
- **folders**: `/folders/$folderId`
- **forgot-password**: `/forgot-password`
- **gallery**: `/gallery`, `/gallery/$`
- **games**: `/games/$gameId`
- **gaming**: `/gaming`
- **gemini-omni-flash**: `/gemini-omni-flash`
- **generate**: `/generate`
- **generation**: `/generation`
- **generations**: `/generations`
- **genjutsu**: `/genjutsu`, `/genjutsu/shared/$code`
- **genjutsu-create**: `/genjutsu-create`
- **genjutsu-for-reels**: `/genjutsu-for-reels`, `/genjutsu-for-reels/$id`
- **gift**: `/gift`
- **go**: `/go/$code`
- **gpt-2**: `/gpt-2`
- **gpt-astra**: `/gpt-astra`, `/gpt-astra/$slug`, `/gpt-astra/bundles/$id`
- **gpt-image-2-community**: `/gpt-image-2-community`
- **gpu**: `/gpu`
- **guides**: `/guides/`, `/guides/$guideId`
- **higgsfield-assembly**: `/higgsfield-assembly`
- **higgsfield-genjutsu-presets**: `/higgsfield-genjutsu-presets`
- **home**: `/home`
- **horizontal**: `/horizontal/$category`
- **image**: `/image/`, `/image/avatar/$category`, `/image/character`
- **image-editing**: `/image-editing`
- **image-translations**: `/image-translations`
- **imagine**: `/imagine`
- **incognito**: `/incognito`
- **infinite-talk**: `/infinite-talk`
- **katana**: `/katana`, `/katana/shared/$code`
- **kion**: `/kion`
- **kling**: `/kling`
- **kling-3.0**: `/kling-3.0`
- **kling-30-community**: `/kling-30-community`
- **kling-lipsync**: `/kling-lipsync`
- **layers**: `/layers`
- **library**: `/library`
- **licences**: `/licences/owl-nc-1.0`, `/licences/owl-p-1.0`, `/licences/owl-p-nl-1.0`
- **lipsync-studio**: `/lipsync-studio`
- **locales**: `/locales/$locale`
- **login**: `/login`
- **logout**: `/logout`
- **mangaka**: `/mangaka`
- **market**: `/market`
- **marketing-studio**: `/marketing-studio`, `/marketing-studio/preset/$slug`
- **marketing-studio-community**: `/marketing-studio-community`
- **marketplace**: `/marketplace/`, `/marketplace/$`, `/marketplace/apps/`, `/marketplace/apps/$appId`, `/marketplace/connectors`, `/marketplace/employees/`, `/marketplace/employees/$employeeId`, `/marketplace/employees/shared/$shareSlug`, `/marketplace/employees/shorts-maker`, `/marketplace/games/`, `/marketplace/games/$gameId`, `/marketplace/published`, `/marketplace/skills/`, `/marketplace/skills/$skillId`, `/marketplace/skills/higgsfield-explainer`
- **mcp**: `/mcp`, `/mcp/$slug`, `/mcp/bundles/$id`
- **mcp-credits**: `/mcp-credits`, `/mcp-credits/`, `/mcp-credits/$id`
- **mcp-pricing**: `/mcp-pricing`, `/mcp-pricing/`, `/mcp-pricing/$id`
- **me**: `/me/settings`
- **media**: `/media`
- **members**: `/members`
- **memory**: `/memory`
- **micro-dramas**: `/micro-dramas`
- **miracle**: `/miracle`
- **mixed-media**: `/mixed-media`
- **mixed-media-community**: `/mixed-media-community/`, `/mixed-media-community/$publicationId`
- **mixed-media-presets**: `/mixed-media-presets/preset/$presetId`, `/mixed-media-presets/publication/$publicationId`
- **mob-explore**: `/mob-explore`
- **mobile**: `/mobile`, `/mobile/audio`, `/mobile/image`, `/mobile/marketing-studio`, `/mobile/video`, `/mobile/video/`, `/mobile/video/reframe`
- **moodboard**: `/moodboard`
- **motion**: `/motion/`, `/motion/$motionId`, `/motion/$motionId/`, `/motion/$motionId/$sampleId`, `/motion/$motionId/publication/$publicationId`
- **multiplier**: `/multiplier/`
- **music-cards**: `/music-cards`
- **nano-banana-intro**: `/nano-banana-intro`
- **nano-banana-pro-preview**: `/nano-banana-pro-preview/`, `/nano-banana-pro-preview/$publicationId`
- **new**: `/new`, `/new/agent`, `/new/imagine`
- **newsletter**: `/newsletter`
- **oauth**: `/oauth`, `/oauth/consent/`, `/oauth/consent/mock-checkout`
- **offer**: `/offer/$ref`
- **onboarding**: `/onboarding`
- **organization**: `/organization`
- **original-series**: `/original-series/`, `/original-series/$serialSlug/$episodeSlug`
- **originals**: `/originals`
- **p**: `/p/$id`, `/p/$projectId`
- **payment**: `/payment`, `/payment/free-trial`
- **photodump**: `/photodump`, `/photodump/mobile`
- **photoset**: `/photoset`
- **playable**: `/playable`
- **playable-ads**: `/playable-ads`
- **playable-intro**: `/playable-intro`
- **plugin**: `/plugin`
- **plugins**: `/plugins/photoshop`, `/plugins/premiere-pro`
- **popcorn**: `/popcorn`
- **post**: `/post/$postId`
- **posts**: `/posts`
- **preset**: `/preset/$slug`
- **presets**: `/presets/$slug`
- **pricing**: `/pricing`, `/pricing/`, `/pricing/checkout/$plan`, `/pricing/offer/`
- **privacy-policy**: `/privacy-policy`
- **production**: `/production`, `/production/$episodeId`
- **products**: `/products`
- **profile**: `/profile/`, `/profile/$username`
- **progress**: `/progress`
- **projects**: `/projects`, `/projects/$projectId`, `/projects/$projectId/`, `/projects/$threadId`
- **promo**: `/promo`
- **property-studio**: `/property-studio`
- **publication**: `/publication/$publicationId`
- **publications**: `/publications/$publicationId`
- **quanta-demo**: `/quanta-demo`
- **quiz**: `/quiz`
- **ranking**: `/ranking`
- **reactivate**: `/reactivate`
- **referrals**: `/referrals`
- **remote-quiz**: `/remote-quiz/$quizId`
- **renew**: `/renew`
- **requests**: `/requests/`, `/requests/$threadId`
- **review**: `/review`
- **rooms**: `/rooms`
- **scheduled**: `/scheduled/`, `/scheduled/$taskId`
- **search**: `/search`
- **seedance**: `/seedance/2.0`, `/seedance/2.5`
- **seedance-2-5-community**: `/seedance-2-5-community`
- **seedance-2-community**: `/seedance-2-community`
- **seedance-4k**: `/seedance-4k`
- **seedance-4k-community**: `/seedance-4k-community`
- **seedream-layer-separation**: `/seedream-layer-separation`
- **select-template**: `/select-template`
- **sessions**: `/sessions`
- **settings**: `/settings`
- **share**: `/share/$id`, `/share/folder`
- **shared**: `/shared/$code`
- **short-drama**: `/short-drama/`, `/short-drama/$projectId`, `/short-drama/mock/agent`, `/short-drama/mock/cast`, `/short-drama/mock/production`
- **shorts**: `/shorts`, `/shorts/$id`
- **shorts-studio**: `/shorts-studio`, `/shorts-studio/$id`
- **shorts-studio-intro**: `/shorts-studio-intro`
- **sign-in**: `/sign-in`
- **sign-up**: `/sign-up`
- **skills**: `/skills/`, `/skills/$bundle/`, `/skills/$bundle/$skill`, `/skills/$skillId`
- **sora-2**: `/sora-2`
- **sora-trends**: `/sora-trends`
- **sora-video**: `/sora-video/`, `/sora-video/$publicationId`
- **soul**: `/soul/`, `/soul/$styleId`, `/soul/job/$jobId`
- **soul-cinema-community**: `/soul-cinema-community`
- **soul-community**: `/soul-community`
- **special-offer**: `/special-offer`
- **speech**: `/speech/`, `/speech/prompt`
- **sso**: `/sso`
- **sso-callback**: `/sso-callback`
- **start**: `/start`, `/start/agent`, `/start/agent-test`, `/start/edit-image`, `/start/genjutsu`, `/start/genjutsu-for-reels`, `/start/imagine`, `/start/katana`, `/start/katana/$slug`, `/start/mangaka`, `/start/micro-dramas`, `/start/playable`, `/start/playable-ads`, `/start/shorts`, `/start/shorts-studio`
- **sub-workspaces**: `/sub-workspaces`
- **subscription**: `/subscription`
- **supercomputer**: `/supercomputer`, `/supercomputer/debug/chat`, `/supercomputer/embed`, `/supercomputer/gaming`
- **sync-so**: `/sync-so`
- **talents**: `/talents`, `/talents/`, `/talents/$userId`
- **talents-hub**: `/talents-hub`, `/talents-hub/`, `/talents-hub/blogs`, `/talents-hub/conditions`, `/talents-hub/downloads`, `/talents-hub/edits`, `/talents-hub/guides/`, `/talents-hub/guides/$guideId`, `/talents-hub/projects/$projectId`, `/talents-hub/requests/$threadId`, `/talents-hub/review`, `/talents-hub/review/`, `/talents-hub/review/projects/$threadId`, `/talents-hub/review/requests/`, `/talents-hub/review/requests/$threadId`, `/talents-hub/review/talents/`, `/talents-hub/review/talents/$userId`, `/talents-hub/search`, `/talents-hub/talents`
- **template**: `/template`
- **terms-of-use-agreement**: `/terms-of-use-agreement`
- **token**: `/token`
- **touring-banner-probe**: `/touring-banner-probe`
- **touring-results-probe**: `/touring-results-probe`
- **trash**: `/trash`
- **trust**: `/trust`
- **tube**: `/tube`
- **unlimited-access-history**: `/unlimited-access-history`
- **upload**: `/upload`, `/upload/`, `/upload/$characterId`
- **upscale**: `/upscale`
- **usage**: `/usage`
- **v2**: `/v2`
- **veo**: `/veo`
- **verify**: `/verify/$serial`
- **verify-card**: `/verify-card`
- **vertical**: `/vertical/$category`
- **video**: `/video/`, `/video/prompt`
- **video-edit**: `/video-edit`
- **video-editor**: `/video-editor`
- **videoshop**: `/videoshop/`, `/videoshop/$projectId`, `/videoshop/examples/$slug`
- **view**: `/view`
- **viral-effects**: `/viral-effects`
- **viral-presets**: `/viral-presets`
- **wan**: `/wan`
- **wan-ai-video**: `/wan-ai-video`
- **wan-video**: `/wan-video/`, `/wan-video/$publicationId`
- **websites**: `/websites`
- **welcome-quiz**: `/welcome-quiz`
- **welcome-to-drama**: `/welcome-to-drama/$accessId`
- **what-if**: `/what-if`, `/what-if/shared/$code`

## Appendix B: all API call paths found in the JS (728) and their probe result

Legend: ✅ 200 public · 🔒 401 login (or not an API path) · ❓ 404 · ⚠️ 422 needs params · ⛔ 403 bot protection · 🚫 not called (would change data) · 🆔 needs an ID

| Path | Result |
|---|---|
| `/about` | 🔒 |
| `/academy` | 🔒 |
| `/academy/` | 🔒 |
| `/academy/_catalog` | 🔒 |
| `/academy/_catalog/` | 🔒 |
| `/academy/_catalog/$category` | 🔒 |
| `/academy/_catalog/courses` | 🔒 |
| `/academy/_catalog/progress` | 🔒 |
| `/academy/courses/` | 🔒 |
| `/academy/courses/$course` | 🔒 |
| `/academy/courses/$course/` | 🔒 |
| `/academy/courses/$course/$lesson` | 🔒 |
| `/academy/courses/$course/certificate` | 🔒 |
| `/access` | 🔒 |
| `/access/{id}` | 🆔 |
| `/activate/access` | 🚫 |
| `/ai-image` | 🔒 |
| `/ai-influencer_/shared_/$code` | 🔒 |
| `/ai-reels_/shared_/$code` | 🔒 |
| `/ai-video` | 🔒 |
| `/ai/image` | 🔒 |
| `/ai/video` | 🔒 |
| `/ai/video/` | 🔒 |
| `/ai/video/agent` | 🔒 |
| `/ai/video/edit` | 🚫 |
| `/ai/video/motion` | 🔒 |
| `/ai/video/reframe` | 🔒 |
| `/api/app-image` | 🔒 |
| `/api/canvases` | 🔒 |
| `/api/server-time` | 🔒 |
| `/api/templates/{id}` | 🆔 |
| `/api/templates/{id}/auth` | 🚫 |
| `/api/templates/{id}/preview` | 🚫 |
| `/api/templates/{id}/use` | 🆔 |
| `/api/v1/apps/{id}/og-meta` | 🆔 |
| `/api/v1/categories` | 🔒 |
| `/api/v1/certificates/{id}` | 🆔 |
| `/api/v1/courses` | 🔒 |
| `/api/v1/courses/{id}` | 🆔 |
| `/api/v1/lessons/{id}` | 🆔 |
| `/api/v1/user/certificates` | 🔒 |
| `/api/v1/user/certificates/{id}/status` | 🆔 |
| `/app/` | 🔒 |
| `/applications` | 🔒 |
| `/applications/explore` | 🔒 |
| `/apps` | 🔒 |
| `/apps/` | 🔒 |
| `/apps/shots` | 🔒 |
| `/apps/skin-enhancer` | 🔒 |
| `/apps/whats-next` | 🔒 |
| `/apps/zooms` | 🔒 |
| `/apps/{id}` | 🆔 |
| `/asset` | 🔒 |
| `/asset/` | 🔒 |
| `/assets` | 🔒 |
| `/assets/count` | 🔒 |
| `/assets/favourites` | 🔒 |
| `/assets/favourites/feed` | 🔒 |
| `/assets/favourites/job-sets` | 🔒 |
| `/assets/members/{id}/detail` | 🆔 |
| `/assets/publish` | 🚫 |
| `/assets/{id}/detail` | 🆔 |
| `/assets/{id}/public` | 🆔 |
| `/audio` | 🔒 |
| `/audio/{id}/hide` | 🚫 |
| `/audio/{id}/upload` | 🚫 |
| `/auth` | 🚫 |
| `/auth/` | 🚫 |
| `/auth/logout` | 🚫 |
| `/auth/sign-in` | 🚫 |
| `/auth/sign-up` | 🚫 |
| `/auth/sso-callback` | 🚫 |
| `/auth/token` | 🚫 |
| `/auto-top-ups/invoices` | 🚫 |
| `/auto-top-ups/retry-payment` | 🚫 |
| `/avatar-presets` | 🚫 |
| `/avatar-presets/{id}` | 🚫 |
| `/avatars` | ⚠️ |
| `/avatars/{id}` | 🆔 |
| `/banner/settings/v2` | 🚫 |
| `/banner/settings/{id}` | 🚫 |
| `/blocked` | 🚫 |
| `/blocks/apps/items/{id}` | 🚫 |
| `/blocks/{id}` | 🚫 |
| `/blocks/{id}/items` | 🚫 |
| `/blog/posts` | 🔒 |
| `/blog/posts/pinned-order` | 🚫 |
| `/blog/posts/recommended` | ✅ |
| `/blog/posts/{id}` | 🆔 |
| `/blog/posts/{id}/like` | 🚫 |
| `/blog/posts/{id}/publish` | 🚫 |
| `/blog/posts/{id}/review/cancel` | 🚫 |
| `/blog/posts/{id}/unpublish` | 🚫 |
| `/blog/posts/{id}/view` | 🆔 |
| `/blog/public/posts/{id}` | 🆔 |
| `/blog/{id}/posts` | 🆔 |
| `/blog/{id}/posts/{id}` | 🆔 |
| `/boards/{id}/jobs` | 🆔 |
| `/business-unlim/state` | ✅ |
| `/business-unlim/verification/confirm` | 🚫 |
| `/business-unlim/verification/submit` | 🚫 |
| `/camera-movements` | 🚫 |
| `/camera-settings` | 🔒 |
| `/camera-settings/recommended` | 🔒 |
| `/camera-settings/{id}` | 🆔 |
| `/canvas/` | 🔒 |
| `/cards` | 🚫 |
| `/chains/` | 🔒 |
| `/chains/dubbing` | 🔒 |
| `/chains/voice-change` | 🔒 |
| `/character` | 🔒 |
| `/checkout-first` | 🚫 |
| `/cinema-studio` | 🔒 |
| `/cinema-studio-3-5/camera-settings` | 🔒 |
| `/cinema-studio-4-0/creative-controls` | 🔒 |
| `/cinema-studio-4-og` | 🔒 |
| `/collection/catch-the-pulse` | 🔒 |
| `/collections/{id}` | 🆔 |
| `/color-presets` | 🚫 |
| `/color-presets/manual` | 🚫 |
| `/color-presets/name` | 🚫 |
| `/color-presets/pinned` | 🚫 |
| `/color-presets/with-presets` | 🚫 |
| `/color-presets/{id}` | 🚫 |
| `/color-presets/{id}/{id}` | 🚫 |
| `/comments/{id}/reaction` | 🆔 |
| `/community` | ❓ |
| `/community/` | ❓ |
| `/community/@` | ❓ |
| `/community/contests` | ❓ |
| `/community/discovery/talents/blog-posts` | ✅ |
| `/community/originals` | ❓ |
| `/contact` | 🔒 |
| `/contest-participations/publications/{id}` | 🆔 |
| `/contests` | ✅ |
| `/contests-legacy/` | 🔒 |
| `/contests/adathon/` | ❓ |
| `/contests/app/` | ❓ |
| `/contests/apps/` | ❓ |
| `/contests/by-id/{id}` | 🆔 |
| `/contests/submissions/{id}/reaction` | 🆔 |
| `/contests/submissions/{id}/report` | 🚫 |
| `/contests/trending` | ✅ (empty) |
| `/contests/weekly-challenge/` | ❓ |
| `/contests/weekly-challenge/latest` | ❓ |
| `/contests/{id}` | 🆔 |
| `/contests/{id}/projects` | 🆔 |
| `/contests/{id}/projects/me` | 🚫 |
| `/contests/{id}/submissions` | 🆔 |
| `/contests/{id}/submissions/me` | 🚫 |
| `/contests/{id}/submissions/{id}` | 🆔 |
| `/cookie-notice` | 🔒 |
| `/create/video/` | 🚫 |
| `/custom-references` | 🔒 |
| `/custom-references/details/{id}` | 🆔 |
| `/custom-references/name` | 🔒 |
| `/custom-references/photo-dump` | 🔒 |
| `/custom-references/retrain` | 🔒 |
| `/custom-references/v2` | 🔒 |
| `/custom-references/{id}` | 🆔 |
| `/custom-references/{id}/move` | 🚫 |
| `/datetime-settings` | ✅ |
| `/debug/bf-week3-hero` | 🚫 |
| `/debug/enterprise-onboarding` | 🚫 |
| `/debug/mcp-plan-cards` | 🚫 |
| `/debug/supercomputer/$folderId` | 🚫 |
| `/effects_/$invalidSegment_/$` | 🔒 |
| `/effects_/examples_/$presetSlug` | 🚫 |
| `/effects_/examples_/$presetSlug_/$sampleId` | 🚫 |
| `/effects_/tests` | 🔒 |
| `/effects_/tests_/effects` | 🔒 |
| `/effects_/use` | 🔒 |
| `/effects_/use_/$slug` | 🔒 |
| `/email-verification` | 🚫 |
| `/enter-team` | 🔒 |
| `/entities/user_profile/{id}/view` | 🆔 |
| `/episodes/{id}/reaction` | 🆔 |
| `/explore` | 🔒 |
| `/fashion-factory` | 🔒 |
| `/favourites/like` | 🚫 |
| `/favourites/unlike` | 🚫 |
| `/feature` | ✅ |
| `/file` | 🔒 |
| `/file/accessible` | 🔒 |
| `/file/{id}/upload` | 🚫 |
| `/flow/avatar/preset/kling` | 🚫 |
| `/flow/image` | 🔒 |
| `/flow/video/prompt` | 🔒 |
| `/folder-items/{id}` | 🆔 |
| `/folder-items/{id}/folders` | 🆔 |
| `/folder/{id}/preview` | 🚫 |
| `/folders` | 🔒 |
| `/folders/accessible` | 🔒 |
| `/folders/pinned` | 🚫 |
| `/folders/reorder` | ⚠️ |
| `/folders/reorder/v2` | 🔒 |
| `/folders/shared` | 🔒 |
| `/folders/{id}` | 🆔 |
| `/folders/{id}/add` | 🆔 |
| `/folders/{id}/assets` | 🆔 |
| `/folders/{id}/children` | 🆔 |
| `/folders/{id}/compose-view` | 🆔 |
| `/folders/{id}/credit-limit` | 🚫 |
| `/folders/{id}/delete-preview` | 🚫 |
| `/folders/{id}/duplicate` | 🚫 |
| `/folders/{id}/info` | 🆔 |
| `/folders/{id}/items` | 🆔 |
| `/folders/{id}/items/gallery` | 🆔 |
| `/folders/{id}/items/locate` | 🆔 |
| `/folders/{id}/items/v2` | 🆔 |
| `/folders/{id}/jobs` | 🆔 |
| `/folders/{id}/members/v2` | 🆔 |
| `/folders/{id}/members/{id}` | 🆔 |
| `/folders/{id}/migrate` | 🚫 |
| `/folders/{id}/move` | 🚫 |
| `/folders/{id}/permission-requests` | 🚫 |
| `/folders/{id}/public-assets` | 🆔 |
| `/folders/{id}/relocate` | 🆔 |
| `/folders/{id}/remove` | 🚫 |
| `/folders/{id}/stats` | 🆔 |
| `/folders/{id}/transfer` | 🚫 |
| `/folders/{id}/trash` | 🆔 |
| `/folders/{id}/trash/count` | 🆔 |
| `/folders/{id}/trash/empty` | 🆔 |
| `/folders/{id}/usage/breakdown` | 🆔 |
| `/folders/{id}{id}` | 🆔 |
| `/free-trial/v2/offers/{id}/start` | 🚫 |
| `/gallery/` | 🔒 |
| `/gallery/{id}` | 🆔 |
| `/game-gift` | 🔒 |
| `/game-gift/action` | 🔒 |
| `/game-gift/claim` | 🚫 |
| `/game-gift/networks` | ✅ |
| `/gemini-omni-flash-1-1/general/uk` | 🔒 |
| `/gemini-omni-flash-1-1/general/uk-poster` | 🔒 |
| `/generate` | 🚫 |
| `/generate/` | 🚫 |
| `/generate/community` | 🚫 |
| `/generate/community/` | 🚫 |
| `/generate/community/post` | 🚫 |
| `/generate/community/post/` | 🚫 |
| `/generate/pricing/` | 🚫 |
| `/generate/{id}/{id}` | 🚫 |
| `/generate/{id}/{id}/folders/{id}` | 🚫 |
| `/generate/{id}/{id}/info` | 🚫 |
| `/genjutsu-create` | 🚫 |
| `/genjutsu_/shared_/$code` | 🔒 |
| `/gifts/status` | 🔒 |
| `/google-omni-preset-mini` | 🚫 |
| `/gpt-image-2-community` | 🔒 |
| `/gpu` | 🔒 |
| `/gratification/grand-prize-banana-figma` | 🔒 |
| `/gratification/grand-prize-nano-figma` | 🔒 |
| `/gratification/grand-prize-pro-figma` | 🔒 |
| `/gratification/grand-prize-texture-figma` | 🔒 |
| `/gratification/grand-prize-texture-grey` | 🔒 |
| `/gratification/grand-prize-wordmark-sticker-figma` | 🚫 |
| `/gratification/nano-banana-pro-wordmark-figma` | 🚫 |
| `/gratification/non-eligible-10-off-sticker` | 🔒 |
| `/gratification/non-eligible-clapperboard` | 🔒 |
| `/gratification/non-eligible-seedance-logo` | 🔒 |
| `/gratification/non-eligible-seedance-rays` | 🔒 |
| `/gratification/non-eligible-snake-icon-dotted` | 🔒 |
| `/gratification/non-eligible-snake-icon-metal` | 🔒 |
| `/gratification/non-eligible-streak-texture` | 🔒 |
| `/gratification/non-eligible-tile-credits-icon` | 🚫 |
| `/gratification/non-eligible-tile-dot-pattern` | 🔒 |
| `/gratification/non-eligible-tile-nano-banana-logo` | 🔒 |
| `/gratification/notification-gift-icon-figma` | 🔒 |
| `/gratification/notification-hanger-notch-figma` | 🔒 |
| `/gratification/reward-card-bottom-mark` | 🚫 |
| `/gratification/reward-card-bottom-mark-figma` | 🚫 |
| `/gratification/reward-claim-rays-figma` | 🚫 |
| `/gratification/reward-ticket-brand-logo-figma` | 🔒 |
| `/gratification/reward-ticket-logo-50-figma` | 🔒 |
| `/gratification/reward-unlocked-pill-figma` | 🚫 |
| `/gratification/reward-unlocked-spark-figma` | 🚫 |
| `/gratification/reward-unlocked-wordmark-figma` | 🚫 |
| `/gratification/rewards-modal-hero-glow-figma` | 🔒 |
| `/gratification/ticket-art-floppy-disk` | 🔒 |
| `/gratification/ticket-art-floppy-sleeve-mask` | 🔒 |
| `/gratification/ticket-art-seedance-noise-tile` | 🔒 |
| `/gratification/ticket-art-unlimited-gpt-image-sticker` | 🔒 |
| `/halloween` | 🔒 |
| `/home` | 🔒 |
| `/image-translations` | 🔒 |
| `/image/` | 🔒 |
| `/input-images/{id}` | 🆔 |
| `/input-videos/{id}` | 🆔 |
| `/job-sets/costs` | ✅ |
| `/job-sets/{id}` | 🆔 |
| `/job-sets/{id}/hide` | 🚫 |
| `/jobs` | ⛔ |
| `/jobs/accessible` | 🔒 |
| `/jobs/seedance/confirm-rights/batch` | 🚫 |
| `/jobs/status-batch` | ⚠️ |
| `/jobs/text2speech` | ⚠️ |
| `/jobs/v2/cinematic_studio_2_5` | 🔒 |
| `/jobs/v2/cinematic_studio_3_0` | 🔒 |
| `/jobs/v2/cinematic_studio_image` | 🔒 |
| `/jobs/v2/cinematic_studio_image_grid` | 🔒 |
| `/jobs/v2/cinematic_studio_video_3_5` | 🔒 |
| `/jobs/v2/cinematic_studio_video_v2` | 🔒 |
| `/jobs/v2/soul_location` | 🔒 |
| `/jobs/v2/youtube_faceless_video` | 🔒 |
| `/jobs/v2/{id}` | 🆔 |
| `/jobs/{id}` | 🆔 |
| `/jobs/{id}/ip-detect` | 🆔 |
| `/jobs/{id}/status` | 🆔 |
| `/jobs/{id}/trace` | 🆔 |
| `/jobs/{id}/track` | 🚫 |
| `/jobs/{id}/view` | 🆔 |
| `/jobs/{id}/viewed` | 🚫 |
| `/jobs/{id}/{id}` | 🆔 |
| `/katana-categories` | 🔒 |
| `/katana-presets` | 🚫 |
| `/katana-presets/{id}` | 🚫 |
| `/katana_/shared_/$code` | 🔒 |
| `/kling-2.5-turbo` | 🔒 |
| `/kling-3.0` | 🔒 |
| `/kling-30-community` | 🔒 |
| `/kling-motions` | 🔒 |
| `/kling-motions/{id}` | 🆔 |
| `/kling2-6-motions` | 🔒 |
| `/kling2-6-motions/{id}` | 🆔 |
| `/kling_speak/general` | 🔒 |
| `/library/` | 🔒 |
| `/lipsync/infinite_talk` | 🔒 |
| `/lipsync/kling_lipsync` | 🔒 |
| `/lipsync/sync_so` | 🔒 |
| `/locales/` | 🔒 |
| `/mangaka` | 🔒 |
| `/mangaka/` | 🔒 |
| `/mangaka/$projectId` | 🔒 |
| `/mangaka/$projectId/` | 🔒 |
| `/mangaka/$projectId/analyze` | 🔒 |
| `/mangaka/$projectId/cast` | 🔒 |
| `/mangaka/$projectId/production` | 🔒 |
| `/mangaka/$projectId_/read` | 🚫 |
| `/market` | 🚫 |
| `/marketing-studio` | 🚫 |
| `/marketing-studio-community` | 🚫 |
| `/marketing-studio-v2/catalog` | 🚫 |
| `/marketing-studio-v2/categories/{id}/presets` | 🚫 |
| `/marketing-studio/` | 🚫 |
| `/marketing-studio/generations` | 🚫 |
| `/marketplace/cart` | 🚫 |
| `/marketplace/cart/lines/{id}` | 🚫 |
| `/marketplace/catalog` | 🚫 |
| `/marketplace/orders/{id}` | 🚫 |
| `/marketplace/purchase` | 🚫 |
| `/mcp-landing/skills/localization` | 🔒 |
| `/mcp-landing/skills/localization-thumbnail` | 🔒 |
| `/mcp-landing/skills/motion-design` | 🔒 |
| `/mcp-landing/skills/motion-design-thumbnail` | 🔒 |
| `/mcp-landing/skills/product-review-ugc` | 🚫 |
| `/mcp-landing/skills/product-review-ugc-thumbnail` | 🚫 |
| `/mcp/bundles/{id}` | 🆔 |
| `/mcp/higgsfield-logo` | ❓ |
| `/mcp/mcp-og-chatgpt-claude-20260925` | ❓ |
| `/mcp/v2/cinematic` | ❓ |
| `/mcp/v2/cinematic-orig` | ❓ |
| `/mcp/v2/clipper` | ❓ |
| `/mcp/v2/explainer` | ❓ |
| `/mcp/v2/info` | ❓ |
| `/mcp/v2/info-orig` | ❓ |
| `/mcp/v2/personal-clipper-orig` | ❓ |
| `/mcp/v2/product_showcase_9x16-1mb` | ❓ |
| `/mcp/v2/short-drama` | ❓ |
| `/mcp/v2/short-drama-orig` | ❓ |
| `/mcp/v2/short-maker` | ❓ |
| `/mcp/v2/shorts-maker-orig` | ❓ |
| `/mcp/v2/tv-com` | ❓ |
| `/mcp/v2/tv-com-input` | ❓ |
| `/mcp/v2/tv-com-orig` | ❓ |
| `/mcp/v2/ugc-content` | ❓ |
| `/mcp/v2/ugc-flow-orig` | ❓ |
| `/mcp/v2/ugc-localization` | ❓ |
| `/mcp/v2/ugc-localization-orig` | ❓ |
| `/mcp/v2/ugc-variations` | ❓ |
| `/mcp/v2/ugc-variations-orig` | ❓ |
| `/mcp/v2/youtube-cover` | ❓ |
| `/mcp/v2/youtube-cover-input-char` | ❓ |
| `/mcp/v2/youtube-cover-input-product` | ❓ |
| `/media` | ⛔ |
| `/media/accessible` | 🔒 |
| `/media/batch` | 🔒 |
| `/media/status` | 🔒 |
| `/media/{id}` | 🆔 |
| `/media/{id}/detail` | 🆔 |
| `/media/{id}/ip-check` | 🆔 |
| `/media/{id}/upload` | 🚫 |
| `/minimax-motions` | 🔒 |
| `/minimax-motions/{id}` | 🆔 |
| `/mixed-media` | 🔒 |
| `/mixed-media-community/{id}` | 🆔 |
| `/mixed-media-presets` | 🚫 |
| `/mo` | 🔒 |
| `/mobile` | 🔒 |
| `/mobile-tanstack/assets/` | 🔒 |
| `/mobile/` | 🔒 |
| `/mobile/image/` | 🔒 |
| `/mobile/marketing-studio` | 🚫 |
| `/mobile/marketing-studio/` | 🚫 |
| `/mobile/video` | 🔒 |
| `/mobile/video/reframe` | 🔒 |
| `/motion` | 🔒 |
| `/motion-samples` | ⚠️ |
| `/motion-samples/{id}` | 🆔 |
| `/motion/{id}` | 🆔 |
| `/motion/{id}/{id}` | 🆔 |
| `/motions` | ⚠️ |
| `/motions/{id}` | 🆔 |
| `/nano-banana-pro-preview/{id}` | 🚫 |
| `/new/agent` | 🔒 |
| `/new/imagine` | 🔒 |
| `/newsletter` | 🔒 |
| `/notices` | 🔒 |
| `/oauth/authorize` | 🚫 |
| `/oauth/authorize/` | 🚫 |
| `/oauth/consent/` | 🚫 |
| `/og/seedance_4k_unlim_og` | 🔒 |
| `/onboarding/` | 🔒 |
| `/payment` | 🚫 |
| `/playable/og/landscape-light` | 🔒 |
| `/posts` | 🔒 |
| `/posts/` | 🔒 |
| `/presence` | 🔒 |
| `/pricing` | 🔒 |
| `/profile/` | 🔒 |
| `/profile/avatar` | 🔒 |
| `/profile/banner` | 🔒 |
| `/profiles/{id}/subscribe` | 🚫 |
| `/profiles/{id}/subscriptions-info` | 🆔 |
| `/project` | 🔒 |
| `/project-publications` | ✅ |
| `/project-publications/categories` | ✅ |
| `/project-publications/recommended` | ✅ |
| `/project-publications/{id}` | 🆔 |
| `/project-publications/{id}/report` | 🚫 |
| `/project-publications/{id}/{id}` | 🆔 |
| `/project/` | 🔒 |
| `/promotions/hf_20260730_184530_df6bd713-d174-491a-ba41-12b861657d3e` | 🔒 |
| `/promotions/higgs-snake` | 🔒 |
| `/promotions/{id}` | 🆔 |
| `/public/thumbnail/{id}.{id}` | 🆔 |
| `/publications` | 🔒 |
| `/publications/check-likes` | 🚫 |
| `/publications/comments/{id}/report` | 🚫 |
| `/publications/community/model-x` | ✅ |
| `/publications/community/trending/top` | ✅ |
| `/publications/feed` | ⚠️ |
| `/publications/{id}` | 🆔 |
| `/publications/{id}/comments` | 🆔 |
| `/publications/{id}/comments/{id}` | 🆔 |
| `/publications/{id}/comments/{id}/vote` | 🚫 |
| `/publications/{id}/like` | 🚫 |
| `/publications/{id}/related` | 🆔 |
| `/publications/{id}/report` | 🚫 |
| `/publications/{id}/share` | 🆔 |
| `/publications/{id}/vote` | 🚫 |
| `/quiz` | 🔒 |
| `/reactivate` | 🚫 |
| `/realtor-studio/plan-check` | 🔒 |
| `/realtor-studio/projects` | 🔒 |
| `/realtor-studio/projects/{id}` | 🆔 |
| `/realtor-studio/projects/{id}/edits` | 🚫 |
| `/realtor-studio/projects/{id}/runs` | 🚫 |
| `/realtor-studio/projects/{id}/runs/{id}/screens/{id}/answer` | 🚫 |
| `/realtor-studio/projects/{id}/runs/{id}{id}` | 🚫 |
| `/reference-elements` | 🔒 |
| `/reference-elements/job/{id}` | 🆔 |
| `/reference-elements/voice` | ⚠️ |
| `/reference-elements/voices` | ✅ |
| `/reference-elements/{id}` | 🆔 |
| `/reference-elements/{id}/enable-audio` | 🚫 |
| `/reference-elements/{id}/folders` | 🆔 |
| `/reference-elements/{id}/folders/{id}` | 🆔 |
| `/reference-elements/{id}/ip-detect` | 🆔 |
| `/reference-elements/{id}/move` | 🚫 |
| `/reference-elements/{id}/workspaces` | 🆔 |
| `/reference-elements/{id}/workspaces/{id}` | 🆔 |
| `/reframe` | 🔒 |
| `/run` | 🚫 |
| `/s/{id}` | 🆔 |
| `/sandbox/re-light` | 🔒 |
| `/sandbox/relight` | 🔒 |
| `/sc-videos-thumbnails/cinematic-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/cinematic-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/clipper-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/explainer-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/info-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/info-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/personal-clipper-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/product_showcase_9x16-1mb-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/short-drama-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/short-drama-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/short-maker-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/shorts-maker-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/tv-com-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/tv-com-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/ugc-localization-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/ugc-localization-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/ugc-variations-orig-thumbnail` | 🔒 |
| `/sc-videos-thumbnails/ugc-variations-thumbnail` | 🔒 |
| `/seedance` | 🔒 |
| `/seedance-2.5/main/unlim-bg` | 🔒 |
| `/seedance-motions` | 🔒 |
| `/seedance-motions/{id}` | 🆔 |
| `/selling-page/selling-page-hero-new` | 🔒 |
| `/series` | 🔒 |
| `/series/{id}` | 🆔 |
| `/series/{id}/subscribe` | 🚫 |
| `/series/{id}/unsubscribe` | 🚫 |
| `/series/{id}/vote` | 🚫 |
| `/share` | 🔒 |
| `/short-drama/` | 🔒 |
| `/shorts-studio/og` | 🔒 |
| `/soul` | 🔒 |
| `/soul-cinema-community` | 🔒 |
| `/soul-cinematic-styles` | 🔒 |
| `/soul-community` | 🔒 |
| `/soul-keyframe-styles` | 🔒 |
| `/soul-samples` | ✅ |
| `/soul-styles` | 🔒 |
| `/soul-styles/{id}` | 🆔 |
| `/soul-v2/presets/{id}` | 🚫 |
| `/soul/{id}` | 🆔 |
| `/sounds` | ⚠️ |
| `/sounds/{id}` | 🆔 |
| `/speak_v2/general_speak_2` | 🔒 |
| `/special-offer` | 🔒 |
| `/sso/check` | ⚠️ |
| `/start` | 🚫 |
| `/start/katana/` | 🚫 |
| `/styles` | ⚠️ |
| `/subscriptions/adjustable-credits` | 🚫 |
| `/subscriptions/bundle/purchase/instant` | 🚫 |
| `/subscriptions/bundle/purchase/instant/unlim` | 🚫 |
| `/subscriptions/bundle/unlim-catalog` | 🔒 |
| `/subscriptions/bundle/unlim/{id}` | 🆔 |
| `/subscriptions/change` | 🔒 |
| `/subscriptions/invoices` | 🚫 |
| `/subscriptions/packages/instant` | 🚫 |
| `/subscriptions/plans/setup/pair` | 🚫 |
| `/subscriptions/update` | 🚫 |
| `/subscriptions/v2/adjustable-credits` | 🚫 |
| `/subscriptions/v2/compare` | ✅ |
| `/subscriptions/v2/packages` | 🔒 |
| `/subscriptions/v2/plan-benefits` | ✅ |
| `/subscriptions/v2/plans` | ✅ |
| `/supercomputer/` | 🔒 |
| `/supercomputer/embed/` | 🔒 |
| `/supercomputer_/debug/chat` | 🚫 |
| `/test-presets` | 🚫 |
| `/thumbnail/SEEDAUDIO_OG_COVER_1` | 🔒 |
| `/thumbnail/upscale` | 🔒 |
| `/touring-banner-probe` | 🔒 |
| `/touring-results-probe` | 🔒 |
| `/trash/delete-forever` | 🚫 |
| `/trash/entries/{id}` | 🆔 |
| `/trash/entries/{id}/contents` | 🆔 |
| `/trash/entries/{id}/delete-forever` | 🚫 |
| `/trash/entries/{id}/items/{id}` | 🆔 |
| `/trash/entries/{id}/restore` | 🚫 |
| `/trash/restore` | 🚫 |
| `/trust` | 🔒 |
| `/unlim-bundle-modal` | 🔒 |
| `/unlim-bundle-modal/shown` | 🔒 |
| `/unlim-marketplace/{id}` | 🚫 |
| `/upgrade-nudges` | 🚫 |
| `/upgrade-nudges/signals` | 🚫 |
| `/uploads/multipart/abort` | 🚫 |
| `/uploads/multipart/complete` | 🚫 |
| `/uploads/multipart/init` | 🚫 |
| `/uploads/multipart/part-urls` | 🚫 |
| `/upscale` | 🔒 |
| `/user` | 🔒 |
| `/user/credit-package-chase` | 🚫 |
| `/user/credit-package-discount` | 🚫 |
| `/user/features` | ✅ |
| `/user/fingerprint-evaluation` | 🔒 |
| `/user/free-gens/v2` | 🔒 |
| `/user/meta` | ✅ |
| `/user/offers` | 🔒 |
| `/user/offers/debug/{id}` | 🚫 |
| `/user/offers/{id}/expire` | 🚫 |
| `/user/offers/{id}/skip` | 🚫 |
| `/user/personal-promo` | 🔒 |
| `/user/personal-promo/chase` | 🚫 |
| `/user/personal-promo/restore` | 🚫 |
| `/user/personal-promo/tasks` | 🔒 |
| `/user/personal-promo/tasks/{id}/complete` | 🚫 |
| `/user/personal-promo/viewed` | 🚫 |
| `/user/pricing-page-view` | ❓ |
| `/user/profile` | 🔒 |
| `/user/profile/avatar` | 🔒 |
| `/user/profile/avatar/randomize` | 🔒 |
| `/user/secret-plan/notify` | 🚫 |
| `/user/session-evaluation{id}` | 🚫 |
| `/user/settings` | 🚫 |
| `/user/settings/audio-consent` | 🚫 |
| `/user/settings/character-sheets-consent` | 🚫 |
| `/user/settings/media-consent` | 🚫 |
| `/user/settings/supercomputer-llm-consent` | 🚫 |
| `/user/upsell-experiment/debug` | 🚫 |
| `/user/{id}` | 🆔 |
| `/user/{id}/stats` | 🆔 |
| `/users/feed` | 🔒 |
| `/users/search` | 🔒 |
| `/users/suggestions` | 🔒 |
| `/users/{id}/subscribe` | 🚫 |
| `/users/{id}/subscribers` | 🚫 |
| `/users/{id}/subscriptions` | 🆔 |
| `/users/{id}/subscriptions/active` | 🆔 |
| `/v1/activation` | 🔒 |
| `/v1/activation/form` | 🔒 |
| `/v1/activation/presets` | 🚫 |
| `/v1/activation/{id}/skip` | 🚫 |
| `/v1/season` | 🔒 |
| `/v1/season/animations/{id}/seen` | 🚫 |
| `/v1/season/rewards/{id}/claim` | 🚫 |
| `/v1/season/tasks/{id}/claim` | 🚫 |
| `/v1/season/weekly-canvas` | 🔒 |
| `/v2/auto-top-ups/disable` | 🚫 |
| `/v2/auto-top-ups/dry-run` | 🚫 |
| `/v2/auto-top-ups/retry-payment` | 🚫 |
| `/v2/auto-top-ups/settings` | 🚫 |
| `/v2/auto-top-ups/viewed` | 🚫 |
| `/v2/quizzes` | 🔒 |
| `/v2/quizzes/user` | 🔒 |
| `/v2/quizzes/{id}` | 🆔 |
| `/v2/quizzes/{id}/complete` | 🚫 |
| `/v2/reference-elements` | 🔒 |
| `/v2/reference-elements/bulk/delete` | 🚫 |
| `/v2/reference-elements/bulk/duplicate` | 🚫 |
| `/v2/reference-elements/bulk/move` | 🚫 |
| `/v2/reference-elements/bulk/remove` | 🚫 |
| `/v2/reference-elements/bulk/review-status` | 🚫 |
| `/v2/reference-elements/picker` | ⛔ |
| `/v2/reference-elements/picker/groups` | 🔒 |
| `/v2/reference-elements/pinned` | 🚫 |
| `/v2/reference-elements/properties/keys` | 🔒 |
| `/v2/reference-elements/share` | ⚠️ |
| `/v2/reference-elements/shared/{id}` | 🆔 |
| `/v2/reference-elements/shared/{id}/save` | 🚫 |
| `/v2/reference-elements/{id}` | 🆔 |
| `/v2/reference-elements/{id}/duplicate` | 🚫 |
| `/v2/reference-elements/{id}/folders/{id}` | 🆔 |
| `/v2/reference-elements/{id}/force-duplicate` | 🚫 |
| `/v2/reference-elements/{id}/move` | 🚫 |
| `/v2/reference-elements/{id}/pin` | 🚫 |
| `/v2/reference-elements/{id}/properties` | 🆔 |
| `/v2/reference-elements/{id}/review-status` | 🚫 |
| `/veo3-styles` | 🔒 |
| `/veo3-styles/{id}` | 🆔 |
| `/verify-card` | 🚫 |
| `/vibe-motion/` | 🔒 |
| `/video` | 🔒 |
| `/video-edit` | 🚫 |
| `/video/accessible` | 🔒 |
| `/video/batch` | 🔒 |
| `/video/{id}` | 🆔 |
| `/video/{id}/ip-check` | 🆔 |
| `/video/{id}/meta` | 🆔 |
| `/video/{id}/upload` | 🚫 |
| `/video/{id}/upload{id}` | 🚫 |
| `/views/track` | 🚫 |
| `/viral-effects` | 🔒 |
| `/viral-hub/chain-presets/{id}` | 🚫 |
| `/viral-hub/presets` | 🚫 |
| `/viral-hub/presets/by-slug/{id}` | 🚫 |
| `/viral-hub/presets/{id}` | 🚫 |
| `/viral-hub/presets/{id}/how-it-works` | 🚫 |
| `/viral-hub/types` | ✅ |
| `/viral-hub/{id}` | 🆔 |
| `/voices` | ⚠️ |
| `/voices/{id}` | 🆔 |
| `/wan-ai-video` | 🔒 |
| `/wan-video` | 🔒 |
| `/wan-video/{id}` | 🆔 |
| `/wan2-2-motions` | 🔒 |
| `/wan2-2-motions/{id}` | 🆔 |
| `/wan2-5-motions` | 🔒 |
| `/wan2-5-motions/{id}` | 🆔 |
| `/watchwood/check` | 🔒 |
| `/welcome-quiz` | 🔒 |
| `/what-if_/shared_/$code` | 🔒 |
| `/workspaces` | 🔒 |
| `/workspaces/admin-capabilities` | 🚫 |
| `/workspaces/capabilities` | 🔒 |
| `/workspaces/contact-sales` | 405 |
| `/workspaces/contact-sales/email/validate` | 🚫 |
| `/workspaces/context` | 405 |
| `/workspaces/create-checkout-session` | 🚫 |
| `/workspaces/credit-price` | 🚫 |
| `/workspaces/details` | 🔒 |
| `/workspaces/invoices` | 🚫 |
| `/workspaces/notice` | 🔒 |
| `/workspaces/notice/close` | 🚫 |
| `/workspaces/payment-cards` | 🚫 |
| `/workspaces/payment-cards/backup` | 🚫 |
| `/workspaces/payment-cards/default` | 🚫 |
| `/workspaces/payment-cards/delete` | 🚫 |
| `/workspaces/pending-charges` | 🚫 |
| `/workspaces/pending-invoices` | 🚫 |
| `/workspaces/projects/usage-stats` | 🔒 |
| `/workspaces/seat-bonus` | 🔒 |
| `/workspaces/subscription` | 🔒 |
| `/workspaces/subscription/billing-info-link` | 🔒 |
| `/workspaces/subscription/grace-charge-preview` | 🚫 |
| `/workspaces/subscription/portal-link` | 🚫 |
| `/workspaces/subscription/try-charge-then-portal-link` | 🚫 |
| `/workspaces/verify-payment-method` | 🚫 |
| `/workspaces/wallet` | 🚫 |
| `/workspaces/wallet/auto-top-up` | 🚫 |
| `/workspaces/wallet/auto-top-up/disable` | 🚫 |
| `/workspaces/wallet/auto-top-up/dry-run` | 🚫 |
| `/workspaces/wallet/auto-top-up/invoices` | 🚫 |
| `/workspaces/wallet/auto-top-up/retry-payment` | 🚫 |
| `/workspaces/wallet/purchase-credits` | 🚫 |
| `/youtube-faceless-presets` | 🚫 |
| `/youtube-faceless-showcases` | 🔒 |
| `/youtube-faceless/channels` | 🔒 |
| `/youtube-faceless/channels/{id}` | 🆔 |
| `/youtube-faceless/episodes/{id}/upscale` | 🆔 |
| `/youtube-faceless/episodes/{id}/upscale/estimate` | 🆔 |
| `/youtube-faceless/hot-right-now` | ✅ |
