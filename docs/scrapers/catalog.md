# `catalog` scraper — presets & asset catalogs

`python -m higgsfield_scraper scrape catalog [options]` collects every preset/asset catalog a user can pick in the
Higgsfield generators: motions (camera moves / video effects), their sample videos, avatars, avatar presets, TTS voices,
reference voices, sound effects, image styles, Soul sample generations and viral-hub effect presets — plus, with a
login session, the login-only catalogs (soul styles, per-model motions, mixed media, katana, color presets, …).

Package: `higgsfield_scraper/scrapers/catalog/` (`endpoints.py`, `options.py`, `parsers.py`, `schemas.py`,
`dataset.py`, `spider.py`). Tests: `tests/test_catalog.py`, fixtures `tests/fixtures/catalog/`.

## Quick start

```bash
python -m higgsfield_scraper scrape catalog                                   # all public catalogs (~10 requests)
python -m higgsfield_scraper scrape catalog --kinds motion,voice,sound        # some catalogs
python -m higgsfield_scraper scrape catalog --kinds motion --with-samples --with-details   # ~840 extra requests
python -m higgsfield_scraper scrape catalog --kinds motion --with-samples --max-pages 50   # samples of 50 motions
python -m higgsfield_scraper scrape catalog --kinds all --include-login-only yes          # + login-only (needs login)
python -m higgsfield_scraper scrape catalog --kinds viral_preset,viral_type --lang de
python -m higgsfield_scraper scrape catalog --kinds chain_preset,notice,restyle_preset   # opt-in extras (public)
python -m higgsfield_scraper scrape catalog --kinds chain_preset --include-hidden      # + 10 hidden presets
python -m higgsfield_scraper scrape catalog --download-media thumbs           # preview images too
python -m higgsfield_scraper normalize --run runs/<run>                       # offline re-parse of raw/
```

Live result (2026-11-25, no session): **10 requests, 20 s, status success, 0 validation drops**:
motions 419 · avatars 100 · avatar presets 21 · voices 82 · reference voices 115 · sounds 11 · styles 5 ·
soul samples 1,260 (API total 1,263; 3 ids appear twice) · viral types 6 · viral presets 87.

## Options

| Option | Default | Meaning |
|---|---|---|
| `--kinds` | `public` | comma list of short names (`motion`) or kinds (`catalog_motion`); `public`, `login`, `all`. Plurals accepted (`motions`). |
| `--with-samples` | off | fetch `/motion-samples` for every motion (1 request per motion → ~419). Off by default because it is 40× the rest of the run. `--kinds motion_sample` does the same. |
| `--with-details` | off | fetch `/motions/{id}` for every motion (~419 requests): adds `description` and the real preview media of the kling/minimax/seedance/wan families, whose list entries only carry the URL `<placeholder>` (190 of 419). |
| `--lang` | `en` | `lang=` for viral-hub, soul styles, mixed media, veo3 styles, katana. |
| `--include-login-only` | `auto` | `auto`: add the login-only kinds when a session is configured; `yes`: always schedule them (requests use `auth="required"` → skipped cleanly without a session, run stays `success`); `no`: never (also removes them from an explicit `--kinds`). |
| `--keep-placeholders` | off | keep the base64 blur placeholders (`data:image/webp;base64,…`, up to 60 KB each) in `media[].placeholder`. |
| `--include-hidden` | off | `chain_preset` only: also request `show_hidden=true` (1 extra request, after the visible list). Presets only in that list get `is_hidden=true`. |
| `--with-profiles` | off | keep creator credits: `chain_preset.collaborator` (API `collaborate`) and the katana preset `author` objects. Default: dropped (`has_collaborator` tells whether there was one) / redacted. |

`--include-hidden` and `--with-profiles` are left out of `meta.options` while off, so runs without them keep the
same `meta.options` as before.

Common flags (all scrapers) apply: `--max-items` counts all catalog kinds except motion samples (primary kinds);
`--max-pages N` caps pages **per listing** — samples and details are one listing each
(`catalog_motion_samples`, `catalog_motion_detail`), so `--max-pages 50` = samples/details of at most 50 motions;
`--page-size` overrides every listing's page size (clamped to its maximum); `--download-media none|thumbs|full|all`
(`thumbs` = images: previews, thumbnails, optimized webp, avatar/voice images; `full` = videos + audio;
`all` = everything incl. waveform JSON); `--auth`, `--token`, `--max-requests`, `--delay`, …

## Endpoints (all GET; base `https://fnf-api-gw.higgsfield.ai/fnf` unless noted)

### Public

| Kind | Endpoint | Params (from JS bundles) | Page size used / max | Paging | Total |
|---|---|---|---|---|---:|
| `catalog_motion` | `/motions` | `size` (required), `cursor` (int), `category`, `hide_collection=true`, `preset_family`, `search`, `device-type`, `show_hidden` | 1000 / 1000 | `cursor` (negative int = priority), `total` | 419 |
| (merged) | `/motions/{id}` | — | — | detail | adds `description`, full `media` |
| `catalog_motion_sample` | `/motion-samples` | `motion_id` + `size` (both required, 422 otherwise), `cursor` | 100 / 1000 | `cursor`, `total` per motion | ~3–5 per motion |
| `catalog_avatar` | `/avatars` | `size`, `cursor`, `category` | 100 / 200 (size=1000 → HTTP 500) | `cursor`, `total` | 100 |
| `catalog_avatar_preset` | `/avatar-presets` | `size`, `cursor` | 100 / 200 | `cursor`, `total` | 21 (**public**, the inventory marked it 🚫) |
| `catalog_voice` | `/voices` | `size`, `cursor`, `category`, `search` | 500 / 1000 | `cursor`, `total` | 82 |
| `catalog_reference_voice` | `/reference-elements/voices` | `size`, `model` (elevenlabs, minimax, seed_speech, qwen_audio), `age`*, `gender`*, `user_cursor`, `preset_cursor` | 500 / 1000 | `has_more` + `user_cursor`/`preset_cursor`; no total | 115 |
| `catalog_sound` | `/sounds` | `size`, `cursor`, `categories`, `search` | 500 / 1000 | `cursor`, `total` | 11 |
| `catalog_style` | `/styles` | `size`, `cursor` | 500 / 1000 | `cursor`, `total` | 5 |
| `catalog_soul_sample` | `/soul-samples` | `size`, `cursor` (float epoch of `created_at`) | 2000 / 5000 | `cursor`, `total` | 1,263 |
| `catalog_viral_type` | `/viral-hub/types` | `lang` | — | none | 6 |
| `catalog_viral_preset` | `/viral-hub/presets/all` | `lang`, `limit`, `offset`, `category`, `kind`, `type` (type slug), `search`, `main_page`, `show_hidden` | all (no limit) | `limit`/`offset`, `total` | 87 |

Notes:
* The `/motions` list already contains **all families** (higgsfield 229, minimax 77, kling 56, seedance 25,
  wan2_2_video 17, wan2_5_video 15). The web app filters `preset_family=higgsfield`.
* Soul samples: cursor paging over `created_at` loses ~2 items at page boundaries; one page of 2000 returns all 1,263
  rows (3 ids occur twice → 1,260 after dedup). User ids are a generic `content_user_id`; only `user_id` is kept.
* `/viral-hub/presets?lang=&category=` (the old endpoint) is always `[]`; the app uses `/viral-hub/presets/all`.
  `/viral-hub/main-page-previews` returns the same 87 presets as 94 rows (multiple previews), not scraped.
* `*` `age`/`gender` are repeated (`append`) params.

### Opt-in group (`--kinds login`, `--include-login-only`) — verified live 2026-11-26

These were first guessed as `fnf/<path>` (401 without a session, **404 `Not Found` with one**). The JS bundle
(build 548e0f3a, core chunk `aXyXjC_KHBp09DNW.js`) shows they use other bases: `Ixe(path, lang)` =
`https://cms.higgsfield.ai{path}?lang=…` and `_V(path)` = `https://fnf-api-gw.higgsfield.ai/fnf-cms-api{path}`.
On the right base they are **public** (same bytes with and without a session), so they are sent without a token.
Only `color-presets` and `camera-settings` (fnf gateway) really need a session (`auth="required"`). The group keeps
its CLI name `login` for compatibility. Samples: `samples/higgsfield/login_endpoints/` (redacted).

| Kind | Endpoint(s) | Params sent (JS) | Paging | Total (2026-11-26) | Group field |
|---|---|---|---|---:|---|
| `catalog_soul_style` | CMS `/soul-styles`, `/soul-cinematic-styles`, `/soul-keyframe-styles` | `size`, `lang` (+ JS: `category`, `show_hidden`) | `cursor` = next page number, `total` | 106 / 2 / 17 | `style_set` = soul / cinematic / keyframe |
| `catalog_mixed_media_preset` | CMS `/mixed-media-presets` | `size`, `lang` | `cursor`, `total` | 33 | — |
| `catalog_model_motion` | CMS `/veo3-styles`, `/kling-motions`, `/kling2-6-motions`, `/seedance-motions`, `/wan2-2-motions`, `/wan2-5-motions`, `/minimax-motions` | `size`, `lang` (+ JS: `search`, `category`, `show_hidden`) | `cursor`, `total` | 17 / 58 / 22 / 25 / 27 / 15 / 77 | `model_family` |
| `catalog_youtube_faceless_preset` | CMS `/youtube-faceless-presets` | `size`, `lang`, `cursor` | `cursor`, `total` | 12 | — (`title` → `name`) |
| `catalog_marketing_category` | CMS `/marketing-studio-v2/catalog` | `lang`, `show_hidden=false` | single response `{schema_version, categories}` | 7 | id = category `slug`; `formats[]` in `extra` |
| `catalog_marketing_preset` | CMS `/marketing-studio-v2/categories/{slug}/presets` | `size`, `lang`, `show_hidden=false`, `cursor` | `cursor`, `total` | e.g. ugc 1,051 | `category_id` (= slug) |
| `catalog_katana_category` | fnf-cms-api `/katana-categories` | `limit` (1–100), `lang`, `cursor` | `next_cursor` | 3 | — |
| `catalog_katana_preset` | fnf-cms-api `/katana-presets` | `limit` (≤100), `lang`, `cursor` | `next_cursor` (opaque) | ~100+ | — (`title` → `name`; `author` redacted) |
| `catalog_color_preset` | fnf `/color-presets` (**session required**) | `size` | `has_more` + cursors | 6 | user-owned `type`s dropped |
| `catalog_camera_setting` | fnf `/camera-settings` (**session required**) | — | `has_more` | 0 (the account's own saved settings; empty for the test account) | — |

The old `fnf/<path>` URLs answer 404 even when logged in — do not use them.
Parsing stays generic (typed common keys, media-like values → `media`, the rest in `extra`). Person objects inside
items (`katana_presets[].author = {user_id, username, avatar_url, badge}`) are reduced to non-identifying
fields + `redacted: true` unless `--with-profiles`.
`--max-items` is one budget for the whole run (the first listing can use all of it); use `--max-pages 1` to sample
every listing once.

### Opt-in extras (`--kinds chain_preset,notice,restyle_preset` or `--kinds all`) — public, verified 2026-11-26

Not part of the default run, of `--kinds public` or of the `login` group, so default output is unchanged. When none
of them is selected the dataset has no `chain_presets` / `notices` / `restyle_presets` keys, no counts, endpoints or
summary rows for them, and the per-run `schema/dataset.schema.json` is the plain `CatalogDataset`
(`CatalogDatasetFull` = + the three collections, only when one is selected). The `schema` command exports
`catalog.dataset.schema.json` from `CatalogDatasetFull` (since 2026-11-26), so the opt-in collections are
documented there too; per-run schemas are unaffected. New item fields follow the project
convention: `source_url`, `scraped_at`, `schema_version` (plus the usual `source`, `media`, `extra`).

| Kind (id) | Endpoint | Params sent | Paging | Total (2026-11-26) |
|---|---|---|---|---:|
| `catalog_chain_preset` (`id` = API uuid) | fnf-cms-api `/job-set-chain-presets` | `lang` (+ `show_hidden=true` with `--include-hidden`; JS also `product_key`) | none (JSON array) | 48 (58 with hidden) |
| `catalog_notice` (`id` = hash of section + sorted `job_set_types` + badge label / header title) | CMS `/notices` (= fnf-cms-api `/notices`; `fnf/notices` is 404) | `lang` (translated: `de` differs) | none | 10 job-set notices, 0 header notices |
| `catalog_restyle_preset` (`id`) | fnf-cms-api `/restyle-presets` | `size` (100; app 20), `lang`, `cursor` | `cursor` = next page number, `total` | 21 |

* **Chain preset prices.** `cost_credits` and `discount_credits` are **credits** (integers 10–56), not credit units:
  unlike viral `price_matrix` (`credit_units / 100`), the app shows them as is (`higgsfield-preset-credit-display`).
  With the app's discount display on it shows `cost_credits` with `discount_credits` struck through; otherwise
  `discount_credits` alone. 9 of 58 differ (`is_discounted`), e.g. `BASEBALL GAME` 10 vs 14 (one hidden preset has
  28 vs 14). `pricing_mode`: `fixed` 57, `dynamic_chain` 1 (`pricing_schema` is `{}` for all). All are
  `product_key = game_character_creator`, `runtime = preset_chain`; `runtime_params` → `chain_type`,
  `runtime_endpoint` (`/chains/game-character-creator`), `runtime_model`. Media: `image_preview` (empty `{}` for 36),
  `preview*` per entry of `previews[]` (`aspect_ratio`, `is_main`, `preview_id` in `media[].extra`). `inputs[]` →
  child table `chain_preset_inputs` (`type`, `min`, `max`).
* **Hidden presets.** The API has no per-item hidden flag, so `--include-hidden` requests the hidden list strictly
  after the visible one: visible rows win the dedup, rows only in the hidden list keep `is_hidden=true`
  (`normalize` reads raw files in name order: `catalog_chain_presets__…` before `catalog_chain_presets_hidden__…`).
* **Notices**: `section` (`job_set` | `header`), `job_set_types[]`, `variant` (info, warning), `badge_label`,
  `badge_tooltip`, `popup_title`, `popup_description`, `params`; header notices: `title`, `description`, `link`
  (`view.*`; the rest of `view` and `config` in `extra`). E.g. "Seedance 1.5 Pro is being retired".
* **Restyle presets**: `name`, `title`, `description`, `preset_source` (API `source`: higgsfield), `job_set_type`
  (restyle), `priority`, `variants[{id, type}]` (edit / original / generation; their media are `variant_<type>*`
  roles), `image_count`; media roles `image*`, `images_<n>*`, `preview*`, `video*`, `original_video*`.
* `--max-items` caps them like any primary kind; `--max-pages` caps restyle paging; `--page-size` sets the restyle
  `size`; `--lang` is sent to all three. A user's own restyle presets (`fnf/restyle/presets/custom`) are not scraped.

Live check 2026-11-26 (`--kinds chain_preset,notice,restyle_preset --include-hidden`): 4 requests, success:
chain presets 58 (10 hidden, 9 discounted, 13 with a collaborator credit), notices 10, restyle presets 21.

Also login-only (not scraped, no catalog value or would need ids): `/mixed-media-presets/preset/{id}`,
`/test-presets`, `/collections/{id}` (unverified), `/series`. Not found publicly: viral preset details
(`/viral-hub/presets/{id}`, `/by-slug/{slug}`, `/{id}/how-it-works`, `/viral-hub/chain-presets/{id}` all 404 for every
preset id/slug tried).

## Entities and fields

Every entity: `media: list[MediaRef]`, `extra: dict` (API keys not mapped — empty for all public kinds on the
2026-11-25 data), `source: Provenance` (`endpoint, url, params, fetched_at`).

**MediaRef**: `role, url, type (image|video|audio|json|other, from extension/content type/API type), api_type, width,
height, duration, duration_ms, content_type, placeholder (only --keep-placeholders), extra`. Roles: `preview`,
`preview_main` (full-res), `preview_optimized` (webp), `preview_thumbnail`, `widescreen*`, `preview_image*`, `video`
(motion samples), `input_image` (avatar), `voice`, `image`, `waveform`, `thumbnail`, `sound`, `result`,
`results_raw`, `results_min`, `style`. `<placeholder>` URLs and `data:` URIs are never media.

| Kind (id field) | Typed fields |
|---|---|
| `catalog_motion` (`id`) | `name, description (details), preset_family, categories, tags, priority, cms_id, params, has_preview, mix[{id,name,extra}], is_collection, detail_fetched` |
| `catalog_motion_sample` (`sample_uid` = motion_id:id) | `id, motion_id, preset_family, priority` |
| `catalog_avatar` (`id`) | `name, voice_id, input_image_id, params` |
| `catalog_avatar_preset` (`id`) | `name, quality, chunks_count, params` |
| `catalog_voice` (`id`) | `name, gender, age, categories, is_gpt, voice_url, waveform_url, image_url` |
| `catalog_reference_voice` (`id`) | `name, gender, age, voice_type (API type), supported_models, audio_url (API source), thumbnail_url, waveform_url` |
| `catalog_sound` (`id`) | `name, description, sound_url, waveform_url` |
| `catalog_style` (`id`) | as motion presets: `name, preset_family, categories, tags, priority, cms_id, params (steps, strength), has_preview` |
| `catalog_soul_sample` (`id`) | `status, job_set_type, job_set_id, user_id (pseudonymous), created_at, published_at, prompt, width, height, steps, seed, batch_size, quality, style_id, style_name, style_url, style_strength, result_url, result_type, params (full)`; `extra`: board_ids, can_bypass_ip, meta, trace_id, job_set_parent_id, job_set_client_meta |
| `catalog_viral_type` (`id`) | `slug, name, priority, lang` |
| `catalog_viral_preset` (`id`) | `slug, preset_kind (API kind: chain), name, description, job_set_type, duration, ip_check_required, is_main_page, priority, tags, type_ids, type_slugs (resolved), preview_url, thumbnail_url, pricing_type, pricing, default_credit_units, min_credit_units, max_credit_units, price_matrix[{key, credit_units}], param_choices, inputs[], param_inputs, lang` |
| opt-in group (`uid` = group:id or id) | `id, group, name, slug, description, preset_family, categories, tags, priority, cms_id, params, lang` (+ `style_set` / `model_family` / `category_id`) |
| `catalog_chain_preset` (`id`) | `product_key, name, description, category, priority, model, preset_family, runtime, chain_type, runtime_endpoint, runtime_model, runtime_params, pricing_mode, pricing_schema, cost_credits, discount_credits, is_discounted, duration, inputs[{id, type, min, max, properties}], is_hidden, has_collaborator, collaborator (--with-profiles), image_preview_url, lang, source_url, scraped_at, schema_version` |
| `catalog_notice` (`id`, hashed) | `section, job_set_types, variant, badge_label, badge_tooltip, popup_title, popup_description, title, description, link, params, lang, source_url, scraped_at, schema_version` |
| `catalog_restyle_preset` (`id`) | `name, title, description, preset_source, job_set_type, priority, variants[{id, type}], image_count, lang, source_url, scraped_at, schema_version` |
| `catalog_page` (`page_id`) | one per listing response: `endpoint, catalog, group, params, first_page, total, item_count, next_cursor, has_more` (auditing + `totals_available`, also after `normalize`) |
| `catalog_motion_detail` | `/motions/{id}` responses; merged into `catalog_motion` (not a collection) |

## Outputs (`runs/<run>/output/`)

* `dataset.json` = `{schema_version, meta (CoreMeta; totals_available per kind), summary, motions, motion_samples,
  avatars, …, marketing_presets, pages}`; `json/<collection>.json` per non-empty collection + `summary.json`,
  `pages.json`, `meta.json`; `schema/dataset.schema.json`; `summary.md`.
* `summary`: `counts` per kind, `totals_available`, `by_category` (motion categories/tags, voice categories, reference
  voice models, viral preset types, soul sample quality, login-only categories), `by_model_family` (motion, style,
  motion_sample, model_motion), `login_only` status per kind (fetched / skipped / not selected),
  `motions_without_preview`, `motions_with_details`, `soul_sample_styles` (78 Soul styles referenced by the public
  samples: id, name, preview url, count — the only public view of the login-only soul style catalog).
* CSVs (complete: every JSON leaf is a column; string lists are JSON text): one per collection, `<collection>_media`
  child tables (parent id + position), `motion_mix`, `viral_preset_prices`, `viral_preset_inputs`,
  `chain_preset_inputs` (opt-in),
  `soul_sample_styles`, `summary_counts`, `summary_by_category`, `summary_by_model_family`, `pages`, `run_meta`.

## Gaps / caveats

* Opt-in catalogs: verified live 2026-11-26 (see the table above). Motion lists are large (kling-motions ≈ 3 MB for
  58 items: inline media variants). `camera-settings` is account data (empty for the test account).
* Motion descriptions and the previews of 190 non-higgsfield motions need `--with-details` (419 requests).
* Viral preset detail / "how it works" endpoints return 404 publicly.
* Soul samples: API total 1,263 contains 3 duplicate ids.
* Voice categories contain API typos (`сoaching` with Cyrillic с, `Podcast` vs `podcast`); kept as-is.
* Without a session, skipped login-only requests are logged by the spider at INFO (`higgs/auth/skipped/<endpoint>`)
  instead of the framework's `request_errors` so the run stays `success`.
