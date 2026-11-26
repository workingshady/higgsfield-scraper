# `community` scraper — Higgsfield community generations

```
python -m higgsfield_scraper scrape community [options]
```

Collects public community generations: the model (`job_set_type`), prompt, normalized settings, input media, result
media, engagement, timestamps, moderation flags, and optionally creator profiles, Community-post comments (public, fnf-community) and an
estimated credit cost. Every run writes the standard run folder (`runs/<ts>_community-<label>/`), and
`python -m higgsfield_scraper normalize --run <run>` rebuilds the dataset offline from `raw/`.

Package: `higgsfield_scraper/scrapers/community/` (`endpoints.py`, `options.py`, `parsers.py`, `schemas.py`,
`dataset.py`, `spider.py`). Tests: `tests/test_community.py` with scrubbed fixtures in `tests/fixtures/community/`.

> **Opt-in Community pages (2026-11-26):** `--feeds shots|posts|feed|creators|talents` (never part of `--feeds all`)
> and comment threads of shots/projects/blogs with `--with-comments`. Endpoints, JS evidence, data model (ER
> diagram + field tables), totals and the anonymous-vs-logged-in check: [`../COMMUNITY_COVERAGE.md`](../COMMUNITY_COVERAGE.md).

## Endpoints (reverse-engineered 2026-11-25)

Base `https://fnf-api-gw.higgsfield.ai/fnf`, header `Accept: application/json`, all GET.

| Feed / use | Path | Params | Max `size` | Cursor | Stop signal |
|---|---|---|---:|---|---|
| `trending` (main feed, total 78,595) | `/publications/community/trending` | `size`, `cursor`, `type`, `model`*, `preset_id`*, `resolution` | **50** (422 above) | float trending **score**, decreasing | `has_more=false` |
| `approved` (curated, 6,701) | `/publications/community/approved` | same | **no limit** (5,000 accepted); we cap at 200 | unix time (`published_at`-like), decreasing | `has_more=false` |
| `top` (≤100 picks) | `/publications/community/trending/top` | `size`, `type` | **100** (422 above) | returned but **ignored** (same page again) | no `has_more` → single page |
| `model-x` (featured model, 64) | `/publications/community/model-x` | `size`, `cursor` | **50** | unix time | `has_more=false`, `cursor=null` |
| detail | `/publications/{publication_id}` | — | — | — | 404 `Publication not found` for unknown ids (also for a *generation* id) |
| comments (see below) | `fnf-community` `/publications/{publication_id}/comments` | `limit`, `offset`, `parent_id` | 50 used | `offset` | `has_more=false` |
| cost basis (only with `--estimate-cost`) | `/job-sets/costs`, `/subscriptions/v2/plans?plan_set_key=<set>&with_localization=true` | | | | |

`*` repeatable (`model=a&model=b`). **Not used**: `fnf-community` `/publications/{id}/related`, `/users/search`.

### Comments (verified live 2026-11-26)

Comments belong to the separate **Community posts** service, base `https://fnf-api-gw.higgsfield.ai/fnf-community`
(JS `Axe()` in core chunk `aXyXjC_KHBp09DNW.js`). It is public (200 with and without a session).

- The old guess `fnf/publications/{id}/comments` -> 401 without a session and **404 `Not Found` with one**.
- Gallery publications (the feeds above) are **not** fnf-community publications:
  `fnf-community/publications/{gallery id}` -> 404, and `.../{any id}/comments` -> `{"comments": [], "has_more": false}`
  (also for a made-up id). **Gallery generations have no comments.**
- So `--with-comments` reads the posts feed `GET fnf-community/publications/feed?limit=N` (N = `--max-items`, default
  20, max 50; posts are not stored), then `GET .../publications/{post_id}/comments?limit=50` for every post with
  `comment_count > 0` (next page with `offset` while `has_more`), and the replies of each comment with
  `reply_count > 0` (`&parent_id=<comment_id>`, one level like the web app).
- Comment shape: `{comments: [{id, entity_type, publication_id, parent_id?, user_id, content, author{id, username,
  full_name, avatar_url, headline, badge, rating_points}, reply_count, like_count, dislike_count, is_mine,
  reactions[{emoji, count}], mentions[], created_at, updated_at}], has_more}`.
  Samples: `samples/higgsfield/login_endpoints/community_*.json` (redacted).

Response shape (listings): `{items: [...], cursor, has_more, total}`. **`total` is the number of items remaining from
the cursor** (page 1: whole filtered feed; approved page 2 returned 6,651 = 6,701 − 50). `meta.totals_available` is
therefore taken from the first page of each feed.

### API behaviour worth knowing

- `type` accepts only `image|video|speak|upscale` (422 otherwise; `all` is not valid → the scraper omits it).
  `upscale` returned the unfiltered feed; `speak` returned 1 item (a `wan2_5_video`).
- **`trending` contains almost no video**: `type=video` gave 10 items in total (all also approved). Videos live in the
  **`approved`** feed (99% `viral_hub_video`, plus `seedance_2_5`, `kling3_0`, …). Use `--feeds approved --type video`.
- **`approved` ignores `type`** (type=image still returned videos) → the scraper enforces `--type image|video`
  client-side (items are dropped *before* counting toward `--max-items`).
- `model` works on trending and approved (unknown value → 422 with the full enum of 359 job_set_types, saved in
  `endpoints.KNOWN_MODELS`). `top`/`model-x` do not take it → enforced client-side.
- `resolution`: ignored by trending; on approved `720p` returned 0 items although 720p items exist. Semantics unknown,
  passed through unchanged. `preset_id` with an unknown uuid was ignored (total unchanged). `approved=true|false` on
  trending is ignored (not exposed).
- Cursors are floats; the scraper sends `repr(cursor)` (full precision). A bad cursor → 400 `Invalid favourites
  cursor`.
- No duplicates were seen across 6 consecutive trending pages, but trending scores move over time, so duplicates are
  possible on long crawls → dedup by `generation_id` (first occurrence wins, its `feed` is kept).
- Detail returns exactly the list-item shape (no extra fields), so `--detail` only refreshes the counters.
- No rate limiting or bot protection was hit at ~1 request/s.

### Pagination / stop logic (`spider.next_page`)

Stop a feed when any of: empty page · `has_more` false · `has_more` missing (top) · `cursor` null · cursor equal to the
one sent · page brought no unseen item · `--max-items` budget spent · `--max-pages` reached.

## Options

Common framework flags apply (`--max-items`, `--max-pages`, `--page-size` (clamped per feed), `--max-requests`,
`--delay`, `--download-media`, `--auth`, `--dry-run`, …). Community flags:

| Flag | Default | Meaning |
|---|---|---|
| `--feeds` | `trending` | comma list of `trending, approved, top, model-x`, `all`, or `none` (only `--publication-ids`). Opt-in, not in `all`: `shots` (fnf-community `/generations/feed` → `community_shot`), `posts` (Community posts → `community_post`), `feed` (`/community/feed` cards → `community_feed_item`), `creators` / `talents` (aggregate creator stats → `community_creator_stats`; names only with `--with-profiles`). `--max-items` caps each opt-in feed separately |
| `--type` | `all` | `all|image|video|speak|upscale`; image/video also enforced client-side |
| `--models` | all | job_set_types, comma list and/or repeatable |
| `--preset-ids` | — | API `preset_id` (repeatable); effect unverified |
| `--resolution` | — | API `resolution`; see caveat above |
| `--publication-ids` | — | fetch these publications by id; their `feed` is `detail`; never filtered |
| `--with-profiles` | off | **personal data**: username, avatar, social handles, badges + `creators` table |
| `--with-raw-params` | off | keep the untouched `params` dict as `raw_params` |
| `--detail` | off | fetch `/publications/{id}` for every listed item (1 extra request per item); `detail_fetched=true` |
| `--with-comments` | off | comments + replies of Community posts (fnf-community, public, no session needed). With the opt-in feeds `shots`/`feed`/`posts`: the threads of those items (`/entities/{generation_publication\|project_publication\|blog_post}/{id}/comments`, `thread_type` = entity type). Without opt-in feeds: unchanged |
| `--estimate-cost` | `off` | `off|images|videos|all`: attach `estimated_cost` |
| `--usd-reference` | `plus:annual` | plan whose after-offer $/credit converts credits to USD |
| `--usd-plan-set` | `ps_a3` | plan set of the USD reference plan |

Examples:

```
python -m higgsfield_scraper scrape community --max-items 300
python -m higgsfield_scraper scrape community --feeds approved --type video --max-items 500
python -m higgsfield_scraper scrape community --models nano_banana_2,seedream_v4_5 --max-items 1000
python -m higgsfield_scraper scrape community --feeds all --estimate-cost all --max-items 400
python -m higgsfield_scraper scrape community --feeds top --with-profiles --download-media thumbs --max-items 50
python -m higgsfield_scraper scrape community --feeds none --publication-ids 06f9721a-592b-4f83-ba01-093c804d6610
scrapy crawl community -a feeds=approved -a type=video -a max_items=100
```

`--download-media`: `thumbs` → `min` image (for video: the `.webp` thumbnail); `full` → `raw` (+ `h264` mp4 for
video); `all` → every result variant except the HLS playlist, plus thumbnails and input media. Note: for images
`min` is usually the same URL as `raw` (full-size PNG, several MB).

## Output

`output/dataset.json` = `{schema_version: 1, meta, generations[], creators[], comments[], pages[], stats}`
(JSON Schema in `output/schema/dataset.schema.json`). JSON parts in `output/json/`. CSVs in `output/csv/` (complete:
every JSON leaf is a column, lists as JSON text, child lists as own tables):

| CSV | Rows |
|---|---|
| `generations.csv` | one per generation, fully flattened (`settings.*`, `params_extra.*`, `engagement.*`, …) |
| `generation_inputs.csv` | one per input media (`generation_id`, `publication_id`, `job_set_type`, …) |
| `generation_results.csv` | one per result variant |
| `creators.csv` | only with `--with-profiles` |
| `comments.csv` | only with `--with-comments` |
| `pages.csv` | one per listing page: cursor chain, `has_more`, `total` |
| `stats.csv` | `dimension, value, count` |
| `run_meta.csv` | meta key/values |

`summary.md`: counts, API totals, top models (items, media, avg views/likes, est. credits), media/feeds/status/
resolution/aspect-ratio tables, top settings, estimate totals, most-viewed prompts (truncated).

### `community_generation` fields

| Field | Meaning (API source) |
|---|---|
| `generation_id` | job id (`id`); dedup key |
| `publication_id` | `publication.id` (use for `/publications/{id}`) |
| `feed` | first listing it was collected from: `trending|approved|top|model-x`, or `detail` (`--publication-ids`) |
| `detail_fetched` | values come from the detail endpoint (`--detail`) |
| `job_set_type`, `model_id` | model/tool (same value; `model_id` joins the pricing dataset) |
| `job_set_id`, `parent_id` | job set; `job_set_parent_id` (derived job, e.g. upscale/extend) |
| `media_type` | `image|video|audio|unknown` from `results.raw/min/h264/hls.type` or legacy `result.type` (`unknown` e.g. for nsfw items without results) |
| `status` | `completed`, `nsfw`, … |
| `prompt`, `negative_prompt` | `params.prompt` / `params.negative_prompt` (prompt may be `""`, e.g. viral_hub videos) |
| `settings.*` | typed known params: width, height, aspect_ratio, resolution, quality, duration, batch_size, seed, model (internal, e.g. `aurora-img-alpha`), mode, style_id, style_strength, preset_id, chain_preset_id, motion_id, enhance_prompt, output_format, background, remove_bg, generate_audio, sound, cfg_scale, steps, thinking_level, genre, speedramp, prompt_language, bitrate_mode, draft, multi_shots, multi_shot_mode, use_unlim, use_relax, camera_model_id, camera_lens_id. A value of an unexpected type stays in `params_extra` |
| `params_extra` | **every other param, untouched** (style/preset/chain_preset/camera_* objects, use_* flags, multi_prompt, …) |
| `raw_params` | untouched `params` (only `--with-raw-params`) |
| `inputs[]` | `index, param` (medias, input_images, input_image, reference_elements, custom_reference, image_reference, kling_elements, …), `role` (medias role e.g. `start_image`; reference category e.g. `character`), `url, id, type, name, width, height`, `extra` (all other keys: object_key, strength, reference element `medias`, …) |
| `results[]` | `name` (`raw` original, `min` preview, `hls` m3u8, `h264` mp4, `result` legacy), `type, url, thumbnail_url, extra`. Null variants are omitted |
| `engagement` | `views` (`views_count`), `likes` (`likes_count`), `approved`, `pinned_at`, `is_liked_by_user` (null without login) |
| `created_at`, `published_at`, `expires_at` | ISO-8601 UTC (API: unix seconds) |
| `can_upgrade_to_4k`, `upgrade_options` | present on some video items (viral_hub); null otherwise |
| `moderation` | `ip_check_finished, ip_detected, deepfake_consent_required, can_bypass_ip` |
| `cluster_hash`, `trace_id`, `board_ids` | as in the API (`cluster_hash` missing on ~30% of items) |
| `client_meta` | `job_set_client_meta`, e.g. `{source: viral_hub_web}` |
| `is_bonus_generation` | `meta.is_bonus_generation` |
| `upstream_usage` | parsed `meta.cost` JSON string: the **upstream provider's token usage** (GPT Image: input/output text/image tokens). **Not Higgsfield credits**; null for most models |
| `meta_extra` | other `meta.*` keys (e.g. `duration`) |
| `extra` | any other non-null top-level field (forward compatibility; `representation`/`drama` were always null) |
| `creator` | `{user_id}` (pseudonymous Clerk id); profile fields filled only with `--with-profiles` |
| `estimated_cost` | `EstimatedCost` (see below) or null when `--estimate-cost off` |
| `source` | provenance: endpoint, url, params, fetched_at. For detail/comments, `params` carries `publication_id` (+ `feed`) — these are labels, not query params |

Other kinds: `community_creator` (`user_id`, username, avatar_url, instagram/twitter/youtube/tiktok handle, badge,
badges, `generations_in_dataset`), `community_comment` (`comment_id, publication_id` (Community post id), `thread_type`,
`parent_id` (replies), `text, created_at, updated_at, likes, dislikes, reply_count, reactions[{emoji,count}],
mention_count, user_id` (pseudonymous), `username` + `author.full_name/avatar_url/headline` (only
`--with-profiles`), `author.badge/rating_points`, `extra`), `community_page` (audit of each listing page),
`community_cost_basis` (internal: the `/job-sets/costs` body and the USD reference; summarized in
`stats.cost_basis`, not exported as a collection).

`stats`: counts by feed, job_set_type, media_type, status, resolution, aspect_ratio; top 10 values of key settings;
frequency of every `params_extra` key and input param; prompt/input coverage; views/likes totals; distinct creators;
estimated credits by model / total / USD total; estimate status counts; cost basis.

## Cost estimate semantics

Optional (`--estimate-cost images|videos|all`). The spider additionally fetches `/job-sets/costs` and the plans of
`--usd-plan-set`; the USD rate is the after-offer $/credit of `--usd-reference` (via `parsers.plans.parse_plans`).
At assembly time `higgsfield_scraper.estimate.CostEstimator.from_job_costs_body(...)` estimates each selected
generation from `job_set_type` + params (`raw_params` when kept, otherwise params rebuilt from `settings`,
`params_extra` and `inputs`) + `media_type`. Status: `exact` (all price dimensions matched), `approximate` (some
assumed), `unpriced` (model/params not in the price list — e.g. `nano_banana_2`, `text2image_soul_v2`,
`viral_hub_video` are not in `/job-sets/costs`), `skipped` (media type not selected, or pricing/estimator unavailable;
reason in `notes` and `meta.warnings`). It is the **list price today for those settings**, not what the creator paid
(plans, promotions, unlimited modes and batch handling differ). Estimation happens in `build_dataset`, so
`output/items/community_generation.jsonl` has `estimated_cost: null`; `dataset.json`/CSVs have the estimate, and
`normalize` reproduces it from `raw/`.

## Limits and privacy

- `--max-items` is global across feeds (feeds are crawled concurrently; first come, first served). Always set it; the
  full trending feed is ~1,600 pages of 50.
- **Personal data**: by default only the pseudonymous `user_id` is exported (it also appears inside CDN URLs).
  Usernames/avatars/social handles/badges only with `--with-profiles`. **However the framework's `raw/` and `http/`
  archives store the full API responses, including `profile.*`, in every run** — treat run folders as personal data
  or use `--no-http-archive` (raw/ is still written; see recommended framework change in the report).
- Test fixtures are scrubbed (fake user ids, usernames, avatars, handles).
- GET only; nothing is liked/voted/commented.

## Known gaps

- Correction 2026-11-26: gallery generations **do** have comments — on fnf-community
  `/entities/generation_publication/{publication_id}/comments` (cursor, 20/page), not on `/publications/{id}/comments`.
  They are collected for `--feeds shots` / `--feeds feed` items with `--with-comments`; the default trending/approved
  path does not request them (that would be 1 request per generation without a known comment count).
- Community posts are stored only with `--feeds posts` (default `--with-comments` still keeps only their comments). Replies of
  replies are not fetched.
- `/publications/{id}/related` and `/users/search` (login) not implemented.
- `resolution`/`preset_id` filter semantics unverified (see above).
- `normalize` re-parses every item in `raw/`, so it can contain up to one page more than the crawl's `--max-items`.
- Media `type` values other than image/video/audio map to `media_type=unknown` (raw type stays in `results[].type`).
