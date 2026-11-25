# `projects` scraper: community projects and contests

```
python -m higgsfield_scraper scrape projects [options]
```

This scraper collects Higgsfield's community **project publications** (films, series, carousels), the
**recommended** feeds, **contest entries** (festival and talent contest submissions published as projects),
**contests** (with rules, rewards, prizes, judges, FAQ, timeline and winners) and **contest submissions**. With a
login session it also collects the **original series**.

All requests are GET. Every endpoint is public except `/series`. The code lives in
`higgsfield_scraper/scrapers/projects/` and the tests are in `tests/test_projects.py`
(fixtures: `tests/fixtures/projects/`).

## Endpoints (base `https://fnf-api-gw.higgsfield.ai/fnf`)

| key (`endpoint`) | path | params | pagination / limits |
|---|---|---|---|
| `projects_publications` | `/project-publications` | `limit` (max **50**), `cursor`, `category` (slug), `featured=true` | `next_cursor` (`"<score>:<uuid>"`), `null` at end. No total. Unknown category -> 404 `Category not found` |
| `projects_recommended` | `/project-publications/recommended` | `scope`, `limit` (max 50), `cursor`, `current_publication_id` | `next_cursor` is an **offset** string (`"50"`). Response also has `feed{source,version,snapshot_id}` |
| `projects_categories` | `/project-publications/categories` | none | `{items:[{slug,label}]}` (currently 2: `open-sourced-by-higgsfield`, `spotlight`) |
| `projects_publication_detail` | `/project-publications/{publication_id}` | none | detail. The same record is also served at `/project-publications/{username}/{slug}` (the web page `/@user/projects/slug`) |
| `projects_contest_entries` | `/contest-participations/publications` | `tab`, `contest_key`, `size` (max **100**), `cursor` (offset), also `trending`, `standing`, `sort`, `query`, `homepage` | `{items, next_cursor, total}`. `total` is recorded in `meta.totals_available` |
| `projects_contests` | `/contests` | `contest_type` (`global` default \| `weekly`), `status` (repeatable), `size` (max **100**), `cursor` | `{items, has_more, cursor}`. **Without `contest_type` only global contests are returned** |
| `projects_contest_detail` | `/contests/by-id/{id}` (also `/contests/{slug}`) | none | full contest |
| `projects_contest_submissions` | `/contests/{id}/submissions` | `limit` (max **100**), `offset`, `ordering`, `user_id`, `search` | `{items, has_more}`, offset pagination |
| `projects_series` 🔒 | `/series` | `limit` (the web app uses 100) | 401 `Invalid or expired token` without a session |
| `projects_series_detail` 🔒 | `/series/{slug}` | none | 401 without a session |

Enums, read from the API's own 422 messages:

* recommended `scope`: `community`, or a ContestKey: `ad_contest`, `ai_film_festival`, `talent_contest`,
  `discord`. Without a scope the API serves a ranking of `ai_film_festival` films.
* contest `status`: `created`, `open`, `shortlist`, `judge`, `finished`. `contest_type`: `weekly`, `global`.
* submissions `ordering`: `newest`, `most-liked`, `most-viewed`, `trending`.
* contest-participations `contest_key`: only `ai_film_festival` or `talent_contest`. `tab`: `trending`,
  `submissions`, `latest`, `most_watched`, `all_entries`, `liked`, `voted`. The tabs `top_50`,
  `higgsfield_choice` and `audience_choice` are served by `/contest-participations/lists/{tab}` (not scraped).

These endpoints were looked at but are not used:

* `/contests/trending` returns 204 (empty).
* `/contests/weekly-challenge/latest` returns 404.
* `/contests/{id}/projects` returns 405.
* `/contests/{id}/submissions/me` and `/contests/{id}/projects/me` are per-user.
* `/project-publications/{id}/report` and the `/reaction`, `/vote` and `/subscribe` endpoints are mutating. They are
  never called.

Live sizes on 2026-11-25:

* More than 2,000 discoverable publications. 40 pages were walked without reaching the end; the order is a decaying
  score.
* 4 global contests and 5 weekly contests.
* 4,518 `ai_film_festival` entries and about 2,220 `talent_contest` entries.
* 8,752 submissions to *Make Your Action Scene*. The weekly contests have 19–137 submissions each.

## Options

| flag | default | meaning |
|---|---|---|
| `--what` | `all` | `publications,recommended,contests,entries,series` (comma list) |
| `--categories` | none | publication category slugs, filtered server-side (one listing per slug) |
| `--featured` | off | publications listing with `featured=true` |
| `--scope` | `all` | recommended scopes (see enum) |
| `--with-details` | off | fetches `/project-publications/{id}` for every publication and `/contests/by-id/{id}` for every contest. The detail is merged into the same record (`detail_fetched=true`, `detail_source`) |
| `--with-submissions` | off | pages through every contest's submissions |
| `--contest-status` | `all` | `open` (created/open/shortlist/judge), `closed` (finished) or `all`. Filtered server-side and in `keep()` |
| `--contest-types` | `all` | `global,weekly` |
| `--entry-keys` | `all` | contest keys for the contest-entries listing |
| `--entry-tab` | `latest` | tab of the contest-entries listing |
| `--submission-ordering` | `newest` | |
| `--max-submissions N` | all | cap on submissions per contest |
| `--with-profiles` | off | **opt-in personal data**: user ids, usernames, names, avatars, headlines, locations, profile URLs, page URLs that contain a handle, the names of `some_contestants`, social `post_urls`, and judge avatars and links |

The common flags also apply: `--max-items` (counts publications and contests), `--max-pages` (per listing: each
publication listing, each recommended scope, each entries key, the contests of each type, the submissions of each
contest), `--page-size` (clamped to the API maxima above), `--download-media`, `--delay`, `--auth` and the rest.
When `--max-items` is reached, pagination stops.

## Entity kinds and fields

Every entity has `source` (Provenance: endpoint, url, params, fetched_at). Timestamps are ISO-8601 UTC strings.
Keys that the API returns but the scraper does not map are kept in `extra`, including viewer-specific flags such as
`is_liked_by_user`, `watch_required` and `watched_percent`.

| kind | id | collection |
|---|---|---|
| `projects_publication` (primary) and `projects_publication_detail` (merged) | `publication_id` | `publications` |
| `projects_episode` | `episode_id` | `episodes` |
| `projects_category` | `slug` | `categories` |
| `projects_contest` (primary) and `projects_contest_detail` (merged) | `contest_id` | `contests` |
| `projects_contest_submission` | `submission_id` | `submissions` |
| `projects_series` 🔒 | `series_id` | `series` |
| `projects_listing_entry` | `entry_id` | `listing_entries` |

**Publication** fields:

* Ids: `publication_id`, `project_id`, `snapshot_folder_id`, `original_folder_id` (detail), `root_folder_id`
  (entries).
* Description: `name`, `slug`, `type` (`film`/`series`/`carousel`), `state`, `description`, `duration_seconds`.
* Flags: `is_ongoing`, `is_open_source`, `has_changes_since_publish`, `show_prompts`, `show_canvas`,
  `is_discoverable`, `is_featured`, `is_higgsfield_featured`, `is_talents_hub`, `can_receive_audience_choice_votes`.
* Featured episode: `featured_episode_id`, `featured_episode_slug` and `featured_episode_url` (these point to
  `/original-series/<series>/<episode>`).
* Contest: `contest_key`. `contest_badges[]` holds `{contest_key, list_key}`, for example `top_50`.
* Classification: `tags[]`, `categories[]` (slugs).
* Media:
  * `media[]` is normalized. Each item has `role` (cover/gallery/trailer), `position`, `media_id`, `type`
    (`media`=image, `video`, `job`=a generation), `name`, `url`, `original_url`, `preview_url`, `thumbnail_url`,
    `min_url`, `download_url`, `width`, `height`, `duration_seconds`, `object_fit` and `extra`.
  * `cover_url` and `trailer_url` are shortcuts.
  * `media_count`, and `episode_count` for series.
* People: `authors[]` and `team` are **Person** records (below). `author_count`, `author_keys[]`.
* Counters: `views`, `likes`, `comments`, `votes` (entries only), `awards[]`.
* Detail only: `generations_count`, `credits_spent`, `free_generations`, `size_bytes`, and `model_usage[]` with
  `{job_set_type, display_name, count, credits_spent}`.
* Dates: `created_at`, `published_at`, `project_updated_at`, `final_submitted_at`, `grant_awarded_at`.
* Bookkeeping: `url` (with `--with-profiles` only, because it is `/@<username>/projects/<slug>`), `listing` (the
  listing where it was first seen), `detail_fetched`, `detail_source`, `extra`.

**Person** (authors, team, winner, contestants, submitters):

* Always included: `role`, `author_key` (sha256 of the user id, 16 hex; stable across runs), `is_owner`,
  `total_projects_views`, `total_projects_likes`, `followers_count`, and `badges[]` with
  `{badge_id, name, icon_url, description}`.
* With `--with-profiles` only: `user_id`, `username`, `full_name`, `avatar_url`, `headline`, `location`,
  `profile_url`.

**Episode**: a series-type publication's gallery videos are its episodes, ordered by `number`. Each has
`publication_id`, `media_id`, `title`, `duration_seconds`, `video_url` (often HLS), `original_url` (mp4),
`preview_url`, `thumbnail_url`, `width` and `height`. Episodes of an original series (login only) also have
`series_id`, `series_slug`, `slug`, `description`, `is_locked`, `is_adults_only` and `url`. The film detail's
`featured_episode_slug` links a publication to its original-series page.

**Contest**:

* Basics: `contest_id`, `slug`, `title`, `description`, `contest_type`, `status`, `status_group` (open/closed).
* Dates: `start_at`, `end_at`, `submissions_close_at`, `rules_effective_at` (a date).
* Results: `results_published`.
* Media and links: `preview_image`, `preview_video`, `logo_url`, `redirect_url`.
* Prizes: `prize_pool` with `prize_pool_unit`. The unit is `usd` or `credits`, taken from the detail's prizes:
  global contests are USD and weekly contests are credits.
* Counts: `submissions_count`, `entries_count`, `is_trending`.
* People: `winner` (Person), `some_contestants_count` and `some_contestants[]` (with profiles only), `judge_count`.
* `judges[]`: `display_name` and `description` are always included. `user_id`, `avatar_url`, `background_url` and
  `external_link` need `--with-profiles`.
* From the detail:
  * `settings{max_submissions, new_project_per_submission, allow_generation_move, allow_generation_copy,
    source_clip_required}`
  * `rewards{first/second/third_place_credits, honorable_mention_credits, honorable_mentions_count,
    style_champion_credits}`
  * `prizes[]{label, type, value, count}`
  * `theme_markdown`, `details_markdown` (the full rules), `faq[]`
  * `timeline` (the festival programme, as returned)
  * `winner_submission_ids[]`, `submission_ids[]`
* Bookkeeping: `url`, `detail_fetched`, `detail_source`.

The detail's `winners[]` are also emitted as submissions with `listing="winners"`.

**Submission**:

* Ids and basics: `submission_id`, `contest_id`, `contest_slug`, `type`, `project_id`, `title`, `description`.
* Media: `thumbnail_id`, `thumbnail_url`, `video_id`, `video_url` (mp4), `video_preview_url`.
* Results: `winner_place` (1st/2nd/3rd/hm/cc), `honorable_mention`, `style_champion`, `shortlisted`.
* Flags: `has_source_video`, `has_assets`, `clone_available`.
* Counters: `likes_count`, `dislikes_count`, `views_count`, `total_views`, and `social_media_metrics{instagram,
  tiktok, youtube, x}_views`.
* Social posts: `post_url_count`. `post_urls[]` needs profiles.
* Moderation and review: `moderation_status`, `suspend_reason`, `winner_feedback`, `winner_reviewer_name`,
  `winner_reviewer_company`.
* Other: `badges[]`, `user` (Person), `publication_id`, `publication_slug`, `publication_url` (profiles), `listing`,
  `url`.

**Series** 🔒 (the parser was written from the web app's JS; no live sample yet):

* Basics: `series_id`, `slug`, `title`, `short_description`, `full_description`, `author_type`, `author`,
  `is_series`, `state`.
* Images and video: `portrait_url`, `landscape_url`, `background_url`, `logo_url`, `trailer_url`,
  `trailer_hls_url`.
* Links: `project_url`, `project_publication_id`.
* Counts: `duration_seconds`, `likes`, `views`, `comments`, `vote_count`, `subscriber_count`.
* Classification: `categories[]`, `tags[]`, `banner_images[]`, `episode_count`.

**ListingEntry**: `listing` (for example `publications`, `publications:category=spotlight`,
`recommended:community` or `entries:ai_film_festival:latest`), `publication_id`, `position` (the 0-based rank when
the cursor is an offset), `page_cursor` and `index_in_page`. Publications are de-duplicated, so this table keeps
every listing a publication appears in and its rank there.

## Outputs (`runs/<ts>_projects-<label>/output/`)

* `dataset.json`: the `ProjectsDataset` with `meta` (CoreMeta: options, limits, limits_hit, totals_available,
  counts, endpoints, warnings), `publications`, `episodes`, `categories`, `contests`, `submissions`, `series`,
  `listing_entries` and `summary`.
* `json/<collection>.json` (one file per collection), `json/meta.json`, `schema/dataset.schema.json`, `summary.md`.
* `csv/`: `publications`, `publication_media`, `publication_authors` (authors and team), `publication_model_usage`,
  `episodes`, `categories`, `contests`, `contest_judges`, `contest_rewards` (the prizes list; the `rewards` object is
  flattened into `contests.csv`), `contest_faq`, `contest_contestants` (profiles only), `submissions`, `series`,
  `listing_entries` and `run_meta`.
* The CSVs are complete: every JSON leaf is a column, nested lists become JSON text, and the child tables carry their
  parent keys. This is tested in `test_csvs_contain_every_json_field`.

`--download-media` picks files by mode:

* `thumbs`: cover images, thumbnails, contest preview images and logos.
* `full`: trailers and videos. The mp4 `original_url` or `preview_url` is used; HLS playlists are skipped.
* `all`: both, plus the gallery images of carousels.

## Examples

```
python -m higgsfield_scraper scrape projects --max-items 200
python -m higgsfield_scraper scrape projects --with-details --with-submissions --max-items 500
python -m higgsfield_scraper scrape projects --what contests --with-details --with-submissions --contest-status closed
python -m higgsfield_scraper scrape projects --what publications --categories spotlight --with-details
python -m higgsfield_scraper scrape projects --what recommended --scope ai_film_festival --max-pages 2
python -m higgsfield_scraper scrape projects --what entries --entry-keys talent_contest --entry-tab most_watched
python -m higgsfield_scraper normalize --run runs/<run>
```

## Gaps and notes

* **`/series` and `/series/{slug}` are login-only.** Without a session they are not requested: a warning is logged
  and the dataset gets the warning `original series ... none scraped`. With a session (`--auth auto` plus a cached
  login) they are requested with `auth="required"`. The parser follows the web app's JS (`e5`/`J8` mappers) and has
  not been checked against a real response. The 41 `/original-series/<series>/<episode>` pages in the sitemap are
  what this would cover.
* The `/project-publications` listing has no total. Its cursor is a score, so `position` is unknown after page 1.
* A publication's public URL contains the author's handle, so `url` is null unless `--with-profiles` is given. Media
  URLs on the CDN contain the raw Clerk user id (`user_…`) in their path; this is how the API serves them.
* `/project-publications/{a}/{b}` is `{username}/{slug}`, not an episode endpoint. Publication episodes are the
  series' gallery videos.
* Per-viewer fields (`is_liked_by_user`, `is_followed`, `watch_*`) are always null or false for anonymous requests.
  They are kept in `extra`.
* The same publication appears in several listings. Repeats are dropped before they count against `--max-items`,
  and the listing membership is still recorded.
* `awards[]` was empty in every sample, so it is passed through untyped.
* `normalize` re-parses every page in `raw/` and does not apply `--max-items`. A capped run therefore normalizes to
  more publications: in the verification run, 491 publications became 787, because pages had already been fetched
  past the budget. Contests and submissions come out identical.
* Path ids (publication, contest or series id, and the contest id of a submissions page) are stored in the
  envelope's `params`, so that each detail gets its own `raw/` file. `Envelope.filename` uses only the endpoint and
  the params. These ids are not query parameters of the URL.
