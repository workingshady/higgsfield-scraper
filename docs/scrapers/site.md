# `site` scraper

`python -m higgsfield_scraper scrape site [options]` collects the public **higgsfield.ai pages that no other scraper
covers**, plus three small public JSON APIs that were not used anywhere:

| Collection (dataset key) | Kind | `--what` | Source | Live count (2026-11-25) |
|---|---|---|---|---:|
| `apps` | `site_app` | `apps` | `/apps` (index cards) + `/apps/<slug>` (appPreset) + `/apps/sitemap.xml` | 84 on the index, ~92 pages |
| `app_categories` | `site_app_category` | `apps` | `/apps` loader `categories[]` | 8 |
| `courses` | `site_academy_course` | `academy` | `/academy/courses` (allCourses) + `/academy/courses/<course>` | 17 |
| `academy_categories` | `site_academy_category` | `academy` | `/academy/courses` loader `categories[]` | 3 |
| `lessons` | `site_academy_lesson` | `academy` | `/academy/courses/<course>/<lesson>` (lesson + `mdxTree` → Markdown) | 179 |
| `mcp_skills` | `site_mcp_skill` | `mcp` | `/mcp` loader `items[]` + `/mcp/<slug>` | 75 |
| `mcp_bundles` | `site_mcp_bundle` | `mcp` | `/mcp` loader `bundles[]` + `/mcp/bundles/<slug>` | 3 |
| `original_series` | `site_original_series` | `originals` | `/original-series` loader `snapshot.originals.data` (+ hero) | 35 |
| `original_episodes` | `site_original_episode` | `originals` | `/original-series/<series>/<episode>` from `/original-series/sitemap.xml` | 40 |
| `mixed_media_presets` | `site_mixed_media_preset` | `mixed-media` | `/mixed-media-presets/preset/<uuid>` from its sitemap (the API list is login-only) | 33 |
| `landings` | `site_landing` | `landings` / `rooms` | `/sitemap-marketing.xml`: model/feature landings, `/plugins/*`, home; rooms opt-in | ~165 (+73 rooms) |
| `promo_events` | `site_promo_event` | `promos` | API `GET /datetime-settings` | 17 |
| `business_unlim_offers` | `site_business_unlim_offer` | `promos` | API `GET /business-unlim/state` (plan cards + pricing banner) | 8 |
| `game_gifts` | `site_game_gift` | `promos` | API `GET /game-gift/networks` (one row per network × country) | 37 |

Default `--what`: everything except `rooms`. A full run is ≈ 650 requests (≈ 12 minutes at the default 1 s delay).

## Sources (reverse-engineered, GET only, no login)

### SSR pages: TanStack Start loader state
Same technique as the `blog` scraper: every page embeds the router state as a seroval literal
(`$_TSR.router=…`) and `matches[i].l` is the route's loader data. `scrapers/blog/tsr.py` decodes it;
`scrapers/site/extract.py` keeps only the non-root loaders, drops base64 `data:` placeholders (blurred previews,
≈ 20 KB each) and duplicated `head`/`schemas`, and archives that compact JSON in `raw/`.

| Page | Route id (suffix) | Loader data |
|---|---|---|
| `/apps` | `#_private#apps##apps#` | `categories[{id, name, slug, icon, priority, description, apps[{id, slug, name[], tags[{text}], preview, mediaDescription, uploadDate}]}]`, `activeCategory` |
| `/apps/<slug>` (an app) | `#_private#apps#$slug#…` | `kind` (`custom`\|`app`), `slugType`, `appPreset{id, title, name, description, shortDescription, media, inputMedia, type, isOnlyVideoAllowed, imageTemplate/videoTemplate/animateTemplate{slug, inputs[], cost}, author{name, media}, landing*}`, `secondaryAppPreset` |
| `/apps/<slug>` (a category) | same | `kind: "category"`, `initialCategoryData.items[]` (cards) — not fetched: the index carries the same cards |
| `/academy/courses` | `#academy#_catalog#courses#…` | `allCourses[{id, slug, title, description, lesson_count, reading_minutes, duration_minutes, difficulty, thumbnail, has_certificate, has_examples, categories[], preview_media, published_at, updated_at, featured_position}]`, `categories[{id, slug, title, description, artwork}]` |
| `/academy/courses/<course>` | `#academy#courses#$course##…` | `course{…, objectives[{title, description}], authors[{name, role, bio, avatar_url}], metadata{skills, models, languages, tools}, examples[], lessons[{id, slug, title, position, reading_minutes, thumbnail, video, homework_required, access}]}` |
| `/academy/courses/<course>/<lesson>` | `#academy#courses#$course#$lesson#…` | `lesson{id, slug, title, xp_reward, thumbnail, video, video_subtitles[], video_cues[], resources[{type, name, download_url, page_count}]}`, `summary{position, reading_minutes, homework_required}`, `nextLessonTarget`, **`mdxTree`** (HAST: `element`/`text` nodes) |
| `/mcp` | `#mcp#mcp` | `items[]` (75 skills, each with `agents[]` prompts per agent, `main_conversation{messages[], result}`, `card_example.prompt`, `cover_media`, `tags[]`, `apps[]`, `installations[]`), `bundles[]` (3), `settings.agents` |
| `/mcp/<slug>` | `#mcp_#$slug#…` | `skill{…, overview_description, detail_title, medias[], tutorial_title/description/media, breadcrumb_label}` |
| `/mcp/bundles/<slug>` | `#mcp_#bundles#$id#…` | `bundle{…, skill_slugs[], prompt, download_url, chatgpt_url, seo_*}`, `skills[]` |
| `/original-series` | `#(public)#community#_tabs#originals#…` | `snapshot{hero.data[], originals{data{items[], total}, limit}}` — 35 series with engagement, trailer/HLS, artwork |
| `/original-series/<series>/<episode>` | `#(public)#original-series#$serialSlug#$episodeSlug#…` | `episode{id, slug, title, description, likesCount, dislikesCount, viewsCount, totalViews, videoSrc (HLS), thumbnailSrc, allEpisodes[], user, createdAt}`, `project{…}`, `recommended[]`, `seriesId/Title/Slug` |
| `/mixed-media-presets/preset/<id>` | `#(public)#mixed-media-presets#preset#$presetId#…` | `preset{id, name, description}`, `initialItems[]` (6 community samples: media, likes, job, profile), `initialCursor` |
| `/community/rooms/<slug>` | `#(public)#community#rooms#$roomSlug#…` | only the page's head tags — the room chat is client-side; only title/description/JSON-LD are kept |

### Landing pages (no loader data)
Marketing/model/feature pages (`/ai-image`, `/kling-3.0`, `/seedance/2.5`, `/plugins/blender`, …) have no route
loader: their content is the SSR HTML. The spider keeps `<main>` with React streaming chunks resolved
(`<div hidden id="S:n">` moved into `<template id="B:n">`), footer/scripts/styles/svg/buttons removed and only
`href/src/alt/poster/title` attributes kept (≈ 40 KB per page). The parser converts it to Markdown with the blog
converter and cuts the shared "Explore more AI features" / footer navigation. JSON-LD gives structured fields:
`SoftwareApplication` (name, category, `offers.price` + `priceCurrency`), `HowTo` (steps), `FAQPage` (Q&A),
`BreadcrumbList`.

Excluded from `landings`: `/pricing` and `/pricing.md` (the `pricing` scraper), `/blog`, `/apps`, `/academy`,
`/effects`, `/mcp*` and `/community*` (own collections) and the localized `/es|ja|ko|de/*` copies.

### Public JSON APIs (`https://fnf-api-gw.higgsfield.ai/fnf`)
| Endpoint | Shape | Kind |
|---|---|---|
| `GET /datetime-settings` | `[{source, datetimes{starts_at, ends_at}, params{…}}]` | `site_promo_event` (non-null params kept, e.g. per-plan free generations) |
| `GET /business-unlim/state` | `{plan_cards{monthly[], annual[]}, pricing_banner{offers[]}, held_offer, verification, window, promo}` | `site_business_unlim_offer` (`section` = plan_card \| pricing_banner) |
| `GET /game-gift/networks` | `{networks[{id, countries[{code, fulfillment_mode, amount_label}]}]}` | `site_game_gift` |

### Sitemaps
`/apps/sitemap.xml` (98: apps + the 8 category pages), `/academy/sitemap.xml` (199: 17 courses + 179 lessons +
`/academy`, `/academy/courses`, `/filmmaker-grant`), `/original-series/sitemap.xml` (41), `/mixed-media-presets/sitemap.xml`
(33), `/sitemap-marketing.xml` (396). The spider takes the union of index pages and sitemaps, deduplicated by path.

## Fields

Every record carries `url` (the public page) and `source` (endpoint, request URL, params, `fetched_at`); the dataset
carries `schema_version` and `meta.scraped_at`. Ids: the site's UUID where there is one, otherwise
`make_id(<natural key>)` (16 hex chars of SHA-256). `apps`, `courses` and `mcp_skills` are built from an index record
and a page record of the same slug (`record_key = <slug>@index|page`); `build_dataset` merges them (page wins, empty
fields are filled from the index, `category_slugs`/`tags` unioned) and sets `record_source`.

| Kind | Key fields |
|---|---|
| `site_app` | `app_id, slug, title, name, description, short_description, media_description, page_kind, slug_type, preset_type, category_slugs[], tags[], upload_date, media, input_media, card_preview, templates[{role, preset (primary\|secondary), preset_slug, slug, cost_credits, input_types[]}], min_cost_credits, max_cost_credits, has_author, author_name (opt-in), landing_* (how-to, showcase, info items, FAQ, CTA), seo` |
| `site_academy_course` | `course_id, slug, title, description, difficulty, duration_minutes, reading_minutes, lesson_count, categories[], preview_media, has_certificate, objectives[], authors[{name, role, bio, avatar_url}], skills/models/languages/tools, lessons[{lesson_id, slug, url, title, position, reading_minutes, video_url, homework_required}], published_at, updated_at` |
| `site_academy_lesson` | `lesson_id, slug, course_slug, course_title, position, xp_reward, reading_minutes, video_url, thumbnail_url, video_subtitles[], video_cues[], resources[{type, name, download_url, page_count}], next_lesson_slug` + body: `content_format=hast, content_markdown, content_text, word_count, headings[], links[], images[]` |
| `site_mcp_skill` | `skill_id, slug, title, skill_label (/command), description, overview_description, external_url, tags[], card_prompt, agents[{agent, destination, label, prompt}], bundle_slugs[], example_conversation[{role, text}], example_result, medias[], tutorial_*` |
| `site_mcp_bundle` | `bundle_id, slug, title, description, skill_slugs[], prompt, download_url, chatgpt_url, seo_*` |
| `site_original_series` | `series_id, slug, title, description, full_description, author_type, series_type, state, duration_seconds, likes, views, comments, vote_count, subscriber_count, engagement_score, first_episode_slug, project_publication_id (joins to the projects scraper), artwork/trailer URLs, in_hero` |
| `site_original_episode` | `episode_id, slug, series_slug, series_title, title, description, likes, dislikes, views, total_views, video_url (HLS), thumbnail_url, created_at, episodes[], project_* , recommended_slugs[], uploader (opt-in)` |
| `site_mixed_media_preset` | `preset_id, name, description, sample_count, samples[{sample_id, job_id, job_set_type, media, likes, creator (opt-in)}]` |
| `site_landing` | `page_id, path, page_type (landing\|plugin\|home\|room), h1, sections[] (h2s), breadcrumbs[], ld_types[], app_name, app_category, offer_price (Decimal) + offer_currency + offer_price_raw, how_to_name, how_to_steps[], faq[], seo{page_title, meta_description, keywords, canonical, og_image}` + Markdown body (not for rooms) |
| `site_promo_event` | `event_id (source key), starts_at, ends_at, params{}` |
| `site_business_unlim_offer` | `offer_id, section, plan_type, billing_period, duration_days, model, max_duration_seconds, max_resolution, requires_business_verification, models[]` |
| `site_game_gift` | `gift_id, network, country_code, fulfillment_mode, amount_label` |

`cost_credits` on app templates is the credit price the app UI shows per generation (`template.cost`), a Decimal
string. Some pages carry a `secondaryAppPreset` (e.g. `/apps/face-swap` → video face swap, 25 credits); its templates
are included with `preset: secondary`. Landing `offer_price` comes from JSON-LD (`"0"` USD = free to start), never from `$` parsing.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--what` | all but `rooms` | comma list of `apps, academy, mcp, originals, mixed-media, landings, rooms, promos` or `all` |
| `--with-content` / `--no-content` | on | `--no-content` = index pages only where an index exists (apps, academy, mcp, originals): ≈ 15 requests, no lesson/landing text |
| `--only` | — | keep only detail pages whose URL path contains one of these strings (`kling,/plugins/,blockbuster-4k`) |
| `--with-profiles` | off | keep creators' usernames (app authors, episode uploaders, mixed-media sample creators, series cast) |
| `--no-markdown` | off | don't write `output/articles/{lessons,landings}/*.md` |

Shared options work as for every scraper. `--max-items N` caps each collection (and the detail pages requested per
page type) at N; `--max-pages` has no effect (no paginated listings); `--download-media thumbs|full|all` saves
thumbnails/posters, then videos (HLS playlists are skipped), then lesson PDFs, inline images and mixed-media samples.

```bash
python -m higgsfield_scraper scrape site
python -m higgsfield_scraper scrape site --what apps --label apps
python -m higgsfield_scraper scrape site --what academy --only blockbuster-4k
python -m higgsfield_scraper scrape site --what mcp,promos --no-content
python -m higgsfield_scraper scrape site --what landings --only /plugins/,kling --max-items 10
python -m higgsfield_scraper scrape site --what all,rooms --max-items 20 --label smoke-site
python -m higgsfield_scraper normalize --run runs/<id> --scraper site      # re-parse raw/ offline
```

## Outputs

`output/dataset.json`, `output/json/<collection>.json`, `output/csv/<collection>.csv` plus child tables
(`app_templates`, `app_landing_faqs`, `course_lessons`, `course_objectives`, `course_authors`, `lesson_resources`,
`lesson_headings/links/images`, `mcp_skill_agents`, `mcp_skill_example_conversation`, `mcp_skill_medias`,
`mcp_bundle_agents`, `episode_episodes`, `mixed_media_samples`, `landing_how_to_steps`, `landing_faq`,
`landing_headings/links/images`), `output/schema/dataset.schema.json`, `output/summary.md` (with an app → credits
table) and `output/articles/lessons/<course>__<nn>__<lesson>.md`, `output/articles/landings/<path>.md`.

## Privacy

`personal_data=True`: `raw/` and JSON bodies in `http/` are redacted (usernames, avatars, names inside
`author/user/profile/team` containers) unless `--with-profiles`. Without the flag the dataset drops app author names,
episode uploaders, mixed-media sample creators and series cast. Academy course instructors (name, role, bio) are
published staff bylines and are kept in the dataset; note that the `raw/` redaction also blanks them, so a
`normalize` of a run without `--with-profiles` has empty instructor names.

## Not built (and why)

| Source | Why |
|---|---|
| `/effects`, `/effects/examples/<preset>` (87) | The presets are the same objects as `catalog` → `viral_presets` (`/viral-hub/presets/all`, incl. price matrix); the example generations are community generations (`community --preset …`) |
| `/community/rooms/<slug>` chat | Client-side and per-user content; only the page title/description is kept (`--what rooms`) |
| `/feature`, `/user/meta`, `/user/features`, `/youtube-faceless/hot-right-now`, `/contests/trending` | Anonymous feature flags / your IP's country / empty lists — no catalog data |
| Academy JSON API (`/api/v1/courses`, `/academy/_catalog`) | 401 without login; the SSR pages carry the same data |
| Localized landing copies (`/es`, `/ja`, `/ko`, `/de`), `sitemap-es.xml`, `sitemap-ko.xml` | Duplicates of English pages |
| `/@user/projects/<slug>` (`sitemap-projects.xml`) | Covered by the `projects` scraper (`/project-publications`) |

## Limits / gaps

- Landing Markdown is generated from the rendered HTML, so it includes UI labels (e.g. "Generate", model pickers)
  that appear inside `<main>`; structured fields (`faq`, `how_to_steps`, `sections`) are the cleaner source.
- `/apps/click-to-ad` renders the Marketing Studio route (no appPreset): it only appears as an index card.
- Sitemaps list a few dead pages (e.g. `/wan-3-0` → 404). Detail page types are optional endpoints, so these do not
  make a run partial; they are counted in `meta.totals_available.pages_not_200`.
- HTML can't be redacted field by field, so without `--with-profiles` the HTTP archive (`http/`) stores a short
  "body withheld" note instead of each HTML body (JSON bodies are redacted as usual). With `--with-profiles` the
  bodies are archived byte-exact. `normalize` reads `raw/`, so it is unaffected.
- Mixed-media presets: only the 6 samples rendered on the page; more samples need the login-only API.
