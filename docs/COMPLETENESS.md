# Completeness audit: generations, media and everything around them

Audit date: 2026-11-26. Read-only audit of every generation-like record the scrapers produce (community
generations, shots, posts, feed items, project assets, contest entries, showcase items, presets/templates with
sample outputs, reels, apps, MCP skills). Question: **for every product and model, does every record carry
everything the source API provides, and is anything dropped between `raw/` and `output/`?**

Tooling: [`scripts/completeness_audit.py`](../scripts/completeness_audit.py) (reusable, offline, low RAM).
End-to-end mapping samples: [`samples/higgsfield/completeness/`](../samples/higgsfield/completeness/).

## 1. Verdict

**Mostly complete for the core generation records; real, fixable gaps at the edges.**

> **Update 2026-11-26 (later the same day):** fixes #1–#17 of §11 are implemented (creator/talent works, feed and
> post media, input roles, Intone / Editing Room / reels / effect fields, effect presets, shot model facets, series
> variants, folder path, katana archive redaction, and one shared `creator_uid_key` across scrapers). The findings
> below describe the state **before** those fixes; the `--max-items` truncation (#18) is still open.

- **Community generations (trending / approved / detail) and project assets are complete.** Every raw leaf of
  `params`, `results`, `meta.cost`, `publication`, moderation flags and timestamps reaches the output, either
  mapped (`prompt`, `settings.*`, `inputs[]`, `results[]`, `engagement`, `upstream_usage`) or verbatim in the
  `raw_params` / `params` blob. Prompt, all media variants (`raw`, `min`, `thumbnail_url`, and `hls`/`h264`
  when the API sends them), input media with roles, `job_set_type`, every setting, engagement and timestamps:
  **0 valuable fields lost** in the live runs (the only drops are usernames/avatars, by design). The three
  end-to-end examples in §9 show this field by field.
- **The gaps are in the "secondary" shapes**: the Community **Feed** drops the embedded post / project card
  media; **posts** drop the attached project card's counters and `published_at`; **showcase** flattens every input
  role to `"input"` (loses `start_image` / `image` / …), drops Intone's compressed video, Editing Room take
  posters/previews/storyboards and timeline thumbnails, and the effect page's preset metadata; **reels** drop
  `recreates`. Contest entries, folders and project assets are complete (only `path`, viewer flags and user
  blocks are dropped).
- **Creators / Talents "works" are dropped entirely (biggest gap, still in today's parser).**
  `community --feeds creators,talents` receives each creator's showcased works with full jobs (prompt, params,
  `reference_elements`, results, `meta.cost`, `enhanced_prompt`, `job_set_parent_id`, project cards with
  `gallery_media`); `creators.json` / `creator_stats.json` keep only the profile stats. 94 + 76 valuable raw paths
  lost (re-normalized run `20261126-161607_completeness-renorm-extras`). Related projects (`projects_related`)
  similarly keep only the link, not the cover / gallery media / trailer.
- **Missing in source, not our bug:** lineage (`job_set_parent_id` is `null` in every community feed record; set on
  ~1 % of project assets, which keep it, and on 1 talent work, which is dropped with the works), negative
  prompts (only a few `nano_banana_2` jobs have one), enhanced prompt (only 2 talent works carry
  `params.enhanced_prompt`), multi prompts (null in every effect sample),
  `hls`/`h264` for most community videos (API sends `null` for `magi_2`/`seedance_*`; `viral_hub_video` jobs carry `hls` 84 % / `h264` 6 %, kept; project videos and explore items have HLS), cost per
  job (only `meta.cost` upstream token usage / USD on some jobs, e.g. GPT Image, Nano Banana 2.1, Kling 4.0,
  Gemini Omni, all kept; no credit price per job anywhere public; estimated cost is ours, opt-in), project folder asset
  counts vs the paged list (the API returns 1–5 % fewer items than `count`; pagination ends with `cursor: null`).
- **Cross-source identity is inconsistent (a design choice per scraper, not a data loss):** the same creator is the raw
  Clerk id in `community`, `sha256("user|id")[:16]` in `projects` and `sha256("creator|id")[:16]` in
  `showcase`/`studios`. The same person therefore has three different keys (§7).
- **`--max-items` truncates silently:** for `community` (multi-feed), `catalog --kinds all` and `showcase`,
  `--max-items N` stops *item emission* after N items while further pages are still fetched into `raw/`. In the
  live run `catalog --kinds all --max-items 30` produced output for motions only (28 kinds: raw fetched, 0
  records). Not a parser gap, but a data-loss trap (§4.3).
- **Privacy note (not completeness):** `raw/` and `http/…/body.raw` of `catalog_katana_presets` keep the preset
  author's username and avatar unredacted (the output is redacted). Fix in the fix list.

## 2. Scope, method and how to re-run

**Runs audited**

| set | runs | what |
|---|---|---|
| OLD | 156 run folders with `raw/` + `output/` (all community, projects incl. the `*nested*` runs, catalog, site, showcase, blog, account runs, plus the newest full pricing run `20261126-115444_all-prices`; the ~60 `pricing-identity-check` runs and pure `normalize` copies were skipped as duplicates) | content produced by earlier parser versions |
| NEW | `20261126-154810_completeness-community` (`--feeds trending,approved,shots,posts --with-raw-params --detail`), `20261126-154921_completeness-projects` (`--what contests --contest talent-contest --with-submissions --max-submissions 2 --with-project-assets`), `20261126-155638_completeness-catalog-pages` (`--kinds all --max-pages 1 --page-size 30`, see §4.3 for why not `--max-items 30`), `20261126-155108_completeness-showcase` (`--what all`), `20261126-155310_completeness-site` (`--what apps,mcp`) | fresh live GET-only runs, `--delay 1.0 --concurrency 1 --auth off --max-items 30` |
| re-normalized | `20261126-160942_completeness-renorm-community` = `normalize` of `20261126-133558_cov-community-comments` with today's parser | proves the Feed gap is in the current parser, not only in old output |
| re-normalized | `20261126-161607_completeness-renorm-extras` = `normalize` of `20261126-133046_cov-community-extras` | proves the creators / talents gap is in the current parser |

The studios scraper and the new community/showcase options were being written during the audit; audit them
later with the same script.

**Method** (`scripts/completeness_audit.py`, no network, no package import):

1. *Output pass.* Every record of every `output/json/<kind>.json` is streamed element by element
   (`json.JSONDecoder.raw_decode`, so the 54 MB `assets.json` is never a full tree in memory) and walked leaf by
   leaf. Distinctive values (strings ≥ 8 chars, URLs with and without query, timestamps normalized to UTC
   seconds from ISO or epoch, large numbers) go into a run-wide hash set; low-entropy values (bools, small ints,
   short strings) are stored per record as `(key, value)` pairs, indexed by the record's ids. JSON strings
   (e.g. `meta.cost`) are exploded.
2. *Raw pass.* Every `raw/*.json` envelope body is split into records (the lists of objects nearest to the root,
   else the body as one entity). A raw leaf is **kept** if its canonical value is in the output (distinctive:
   anywhere in the run; low-entropy: in the joined output record under the same or a similar key). Records whose
   ids never reach the output are reported as **not emitted** instead of polluting the field list.
3. *Coverage.* Key-name heuristics compute, on the raw record and on its joined output record(s) (the record
   plus split-out children such as explore variants): prompt, negative / enhanced / multi prompt, output media
   and their variants (`raw`, `min`, `h264`, `hls`, `thumb`, `main`), media kinds (video / image / audio /
   3d-file), input media and roles, model id, number of setting keys, cost, engagement, lineage, timestamps,
   status, template. `lost in output` = the raw record has it and the output does not. A `0%` with no `lost`
   means **missing in source**.
4. *Classification* of dropped raw paths: `valuable` (prompt / media / input / model / setting / cost /
   engagement / lineage words), `intentional (personal)` (profile, username, avatar, handles, badges, user ids
   that are re-keyed), `intentional (ui/internal)` (`is_*_by_user`, `trace_id`, `cluster_hash`, cursors, colors,
   order), `technical metadata` (mime type, size bytes, `_tag`, bucket keys, `object_fit`), `unknown`.

Caveats: value matching can call a common value "kept" when it was dropped (and vice versa when the parser
transforms a value, e.g. units); HTML/text bodies (site landing pages) are only audited where the site scraper
stores their embedded JSON; live counters change between the list and the detail request
(`publication.views_count` 33 present / 2 identical is that, not a loss); a few raw records that were not
emitted as generations but appear as shots join to the shot record and show as `lost` (the 3 single-record
`community_trending` rows).

**Re-run**

```bash
.venv\Scripts\activate
set PYTHONIOENCODING=utf-8
python scripts/completeness_audit.py runs/<a> runs/<b> ...                       # Markdown to stdout
python scripts/completeness_audit.py "runs/*completeness-*" --md new.md --json new.json
python scripts/completeness_audit.py "runs/*completeness-*" --baseline "runs/2026112*" --md diff.md   # + new raw paths
python scripts/completeness_audit.py "runs/*studios*"                              # new scrapers, unchanged script
```

Options: `--baseline <runs…>` (list raw paths that are new since those runs), `--md`, `--json`, `--title`,
`--max-dropped N`. Output sections: coverage per area, per primary media kind, per endpoint × model; output-side
coverage; dropped raw paths with class and a redacted sample; not-emitted records; creator key scheme.

## 3. Is everything captured?

| area | status | reason |
|---|---|---|
| videos | ⚠️ | Community, project-asset, explore, effect-sample, reel and preset videos keep every URL the API sends (`raw`, `min`, thumbnail, `hls`/`h264` where present). Lost: Intone `compressed_video` (url + size), Editing Room take poster / preview / storyboard VTT and timeline-version thumbnails, Feed post / project-card videos, post card `job_result.thumbnail_url`. |
| images | ✅ | `raw` + `min` (+ `result`, deduped when identical) for every image job; preset/sample thumbnails kept. Only catalog `motions[].media` placeholders are dropped (intended unless `--keep-placeholders`). |
| audio | ✅ | Project audio assets (`elevenlabs_music_v2_5`, `seed_audio`, `audio_input`) with `raw`/`min`/waveform; catalog voices, reference voices, sounds; Intone audio. No audio-only community generations were seen. |
| 3D / files | ✅ (rare) | `file_input` project assets keep `url` + `download_url` + filename/extension/size. No 3D model output (`.glb` etc.) appeared in any source; the `3d_jutsu_angles` / `cinematic_studio_image_3d_recomposition` jobs output images. |
| references / inputs | ⚠️ | Community and project assets keep every input URL **with its role** (`medias[].role`, `input_images`, `start_image`/`end_image`, `style`, `custom_reference`, `camera_*`, `image_reference`, `reference_elements`) and the untouched `raw_params`. Showcase (explore variants, effect samples) keeps the URLs but rewrites every role to `"input"` (raw: `image`, `start_image`, …). |
| prompts | ✅ | 100 % of community and project jobs that have a prompt keep it (plus the copy in `raw_params`). Missing in source: shots / posts / feed (no prompt in the API), effect samples (`prompt: ""`, preset-driven), most catalog presets. Reels keep `prompt` (90 %). Negative prompt kept where present; enhanced / multi / system prompt fields are `null` in every sample seen. |
| models | ✅ | `job_set_type` 100 % where the source has it; also `params.model` (codename like `aurora-img-alpha`, `sunburst`) in `settings.model`. Old project runs grouped assets by display name ("Seedance 2.5"), the current parser by id (`seedance_2_5`) — both kept. |
| settings | ✅ | Community: normalized `settings` + `params_extra` + full `raw_params` (with `--with-raw-params`); projects: full `params` blob + promoted `aspect_ratio`/`resolution`/`duration`/`seed`/`batch_size`. Showcase effect samples keep a curated `params` (7 keys) instead of the 13–14 raw keys (`raw_params.medias[].role`, `chain_preset.preview_media`, `params.provider`, `prompt.enhance`). |
| templates / presets | ⚠️ | Preset/template ids kept on jobs (`style_id`, `motion_id`, `chain_preset_id`, `preset_id`); catalogs keep presets with price matrices. Effect page preset block (`inputs[].binds_to`, `param_choices`, `price_matrix`, preview/widescreen media) is not stored by `showcase` (the same preset is in `catalog_viral_presets`, so low impact). |
| trends | ⚠️ | Trending / approved feeds complete; explore (`--explore-sort trending`) complete except input roles; viral effects (effect samples) see videos/templates. `recreates` (reel trend counter) dropped. Sora-trends / catch-the-pulse have no dedicated endpoint in the scrapers yet (studios scraper in progress). |
| showcase | ⚠️ | Prompt exists in source and is kept for: explore variants (63 % of items have one), Editing Room renders/projects, reels (90 %), Intone (title/description only). No prompt in source: canvas templates, cinema controls, faceless, seedance / motion-control presets, property studio, effect samples (empty). Media gaps listed under videos. |
| user generations | ❌ / ⚠️ | Complete for community generations, user projects (`--users`), project folders/assets and shots. **Creator / talent works (`--feeds creators,talents`) are dropped entirely** (prompt, params, references, results). The creator key differs per scraper (raw Clerk id vs two different hashes), so "the same creator across sources" cannot be joined without re-hashing (§7). |
| contests | ✅ | Contest detail, rules, prizes, judges, winners, submissions and entries (likes, views, comments, votes, author followers) kept; each entry's project → folders → assets with prompts complete (§6). Submissions without a project (video-only contests) have no prompts in the source; entries are capped by `--max-submissions` by design. |
| comments | ✅ | Comment text, parent id, likes, timestamps, pseudonymous author kept for generations, projects, blogs, posts, reels. Dropped: `is_mine` (viewer flag, intended). |
| engagement | ⚠️ | Views / likes / comments / shares / votes kept on generations, posts, shots, projects, submissions, reels, explore items. Dropped: post-attached project card `like_count`/`views_count`/`comment_count` (and the same card inside Feed items), reel `recreates`. |

## 4. Coverage tables

Column meaning: `n` raw generation-like records (records with a prompt, an output media URL or input media),
`joined` = found in the output, then the share of records that have each feature in the **raw** record,
`media (variants)` per variant, `kinds` = records containing that media kind, `inputs (roles)` with the roles
seen, `avg settings` = distinct setting keys per record, `lost in output` = count of records where the raw has the
feature and the output does not. Everything not listed as lost is missing in the source.

### 4.1 NEW runs, per area

| area | scraper | endpoint | n | joined | prompt | neg | media (variants) | kinds | inputs (roles) | model | avg settings | cost | engagement | lineage | lost in output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| community generations (feeds) | community | community_approved | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| community generations (feeds) | community | community_detail | 30 | 100% | 100% | 0% | 100% (main:7%,min:100%,raw:100%,thumb:70%) | image:9,video:21 | 90% (camera_lens,camera_model,input_images,medias,style) | 100% | 9.9 | 7% | 100% like,view | 0% | - |
| community generations (feeds) | community | community_trending | 33 | 100% | 100% | 0% | 100% (main:6%,min:100%,raw:100%,thumb:64%) | image:12,video:21 | 91% (camera_lens,camera_model,input_images,medias,style) | 100% | 9.9 | 9% | 100% like,view | 0% | cost:1, input_urls:3, inputs:3, prompt:3, settings_keys:3, status:3, raw:3 |
| community posts | community | community_posts_list | 28 | 100% | 0% | 0% | 100% (hls:46%,main:100%,min:29%,thumb:82%) | image:28,video:22 | 0% () | 100% | 0.0 | 50% | 100% comment,like,share,view | 0% | thumb:8 |
| community shots | community | community_shots | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:40%) | image:18,video:12 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| contests | projects | projects_contest_by_slug | 1 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:1,video:1 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| contests | projects | projects_contest_entries | 2 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:2,video:2 | 0% () | 0% | 0.0 | 0% | 100% comment,follower,like,view,vote | 0% | - |
| project nested (folders/assets) | projects | projects_folder | 2 | 100% | 0% | 0% | 100% (thumb:100%) | image:2 | 0% () | 0% | 0.0 | 0% | 100% view | 0% | - |
| project nested (folders/assets) | projects | projects_folder_children | 13 | 100% | 0% | 0% | 100% (thumb:100%) | image:13 | 0% () | 0% | 0.0 | 0% | 100% view | 100% | - |
| project nested (folders/assets) | projects | projects_folder_items | 560 | 100% | 97% | 0% | 96% (main:3%,min:96%,raw:96%,thumb:71%) | audio:8,image:128,other:8,video:400 | 94% (download_url,image_reference,input,medias,style) | 97% | 14.4 | 18% | 100% comment | 0% | inputs:19 |
| project nested (folders/assets) | projects | projects_publication_detail | 4 | 100% | 0% | 0% | 100% (main:100%) | image:2,video:2 | 0% () | 0% | 0.0 | 0% | 0% | 0% | main:1 |
| showcase canvas | showcase | showcase_canvas_templates | 5 | 100% | 0% | 0% | 100% (thumb:100%) | image:5 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase cinema controls | showcase | showcase_cinema_controls | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:56%) | image:12,video:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase editing room | showcase | showcase_videoshop_examples | 11 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:11,video:11 | 100% (input,thumbnail_url) | 0% | 0.0 | 0% | 0% | 0% | inputs:11 |
| showcase editing room | showcase | showcase_videoshop_project_examples | 6 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | image:6,other:6,video:6 | 100% (reference,references) | 0% | 0.0 | 0% | 0% | 0% | main:6, thumb:6 |
| showcase effects (viral) | showcase | showcase_effect_page | 41 | 100% | 0% | 0% | 100% (hls:90%,main:98%,raw:90%,thumb:100%) | image:41,video:41 | 90% (input_image,input_media,main_url,medias,optimized_url,preset_meta) | 100% | 13.6 | 10% | 0% | 0% | cost:4, input_urls:37, settings_keys:37, hls:7, main:10, raw:7, thumb:41 |
| showcase explore (trends) | showcase | showcase_explore_feed | 30 | 100% | 63% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:30 | 100% (image,input_assets) | 100% | 1.2 | 0% | 33% comment,like | 0% | multi:2, status:30 |
| showcase faceless | showcase | showcase_faceless_showcases | 9 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:9,video:9 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase intone | showcase | showcase_intone_explore | 18 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | audio:18,image:18,video:18 | 100% (character) | 0% | 0.0 | 0% | 0% | 0% | status:18, main:18 |
| showcase reels | showcase | showcase_reels_preset_detail | 120 | 100% | 45% | 0% | 100% (main:100%,thumb:100%) | image:120,video:120 | 80% (character_media) | 0% | 0.0 | 0% | 75% comment,like,view | 0% | - |
| showcase reels | showcase | showcase_reels_presets | 60 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:60,video:60 | 80% (character_media) | 0% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| showcase seedance/motion presets | showcase | showcase_motion_control_presets | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase seedance/motion presets | showcase | showcase_seedance_presets | 14 | 100% | 0% | 0% | 100% (thumb:100%) | image:4,video:14 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site apps | site | app_page | 86 | 0% | 0% | 0% | 100% (main:100%,thumb:40%) | image:63,video:34 | 29% (source,thumbnail) | 0% | 0.0 | 57% | 0% | 0% | - |
| site apps | site | apps_index | 2 | 0% | 0% | 0% | 100% (main:50%,thumb:50%) | image:2,video:1 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site mcp | site | mcp_bundle_page | 6 | 0% | 50% | 0% | 100% (main:100%,thumb:50%) | image:6,video:3 | 33% (poster_url,reference_medias) | 0% | 1.5 | 0% | 0% | 0% | - |
| site mcp | site | mcp_index | 2 | 0% | 50% | 0% | 100% (main:100%,thumb:50%) | image:2,video:1 | 50% (poster_url,reference_medias) | 0% | 1.5 | 0% | 0% | 0% | - |
| site mcp | site | mcp_skill_page | 60 | 0% | 50% | 0% | 100% (main:100%,thumb:50%) | image:55,video:30 | 30% (poster_url,reference_medias) | 0% | 1.5 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_kling2_6_motions | 22 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:22 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_kling_motions | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_minimax_motions | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_motion_samples | 3 | 100% | 0% | 0% | 100% (main:100%) | video:3 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_motions | 2 | 100% | 0% | 0% | 100% (main:100%) | image:2 | 0% () | 0% | 4.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_seedance_motions | 25 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:25 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_wan2_2_motions | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:27 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_wan2_5_motions | 15 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_avatar_presets | 21 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:21 | 0% () | 0% | 2.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_avatars | 30 | 100% | 0% | 0% | 100% (main:100%) | image:30 | 100% (input_image) | 0% | 3.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_color_presets | 6 | 100% | 0% | 0% | 100% (thumb:100%) | image:6 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_katana_presets | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:97%) | image:28,other:1,video:30 | 93% (reference_thumbnail_media,reference_video_media) | 0% | 0.0 | 0% | 0% | 0% | inputs:28 |
| templates: other presets | catalog | catalog_marketing_catalog | 7 | 100% | 0% | 0% | 100% (thumb:100%) | image:7,video:3 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_marketing_presets | 210 | 100% | 0% | 0% | 100% (thumb:100%) | image:123,video:87 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_mixed_media_presets | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 13% (media) | 0% | 0.9 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_reference_voices | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | audio:30,image:30,other:29 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_restyle_presets | 21 | 100% | 5% | 0% | 100% (hls:95%,main:100%,thumb:100%) | image:21,video:21 | 0% () | 100% | 1.9 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_soul_cinematic_styles | 2 | 100% | 0% | 0% | 100% (main:100%) | image:2 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_soul_samples | 30 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:30 | 100% (style) | 100% | 14.2 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_soul_styles | 30 | 100% | 0% | 0% | 100% (main:100%) | image:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_sounds | 11 | 100% | 0% | 0% | 100% (main:100%) | audio:11,other:11 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_styles | 5 | 100% | 0% | 0% | 100% (main:100%) | image:5 | 0% () | 0% | 2.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_veo3_styles | 17 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:17 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_voices | 30 | 100% | 0% | 0% | 100% (main:100%) | audio:30,image:30,other:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_youtube_faceless_presets | 12 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:12,video:12 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: viral/chain presets | catalog | catalog_chain_presets | 48 | 100% | 0% | 0% | 100% (thumb:100%) | image:14,video:48 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| templates: viral/chain presets | catalog | catalog_viral_presets | 87 | 100% | 0% | 0% | 100% (main:56%,thumb:100%) | image:87,video:87 | 6% (media,options) | 100% | 0.3 | 62% | 0% | 0% | - |

### 4.2 OLD runs, per area

| area | scraper | endpoint | n | joined | prompt | neg | media (variants) | kinds | inputs (roles) | model | avg settings | cost | engagement | lineage | lost in output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| community extras | community | community_collection | 15 | 100% | 0% | 0% | 100% (main:100%) | image:15 | 0% () | 0% | 4.0 | 0% | 0% | 0% | - |
| community extras | community | community_explore_cards | 191 | 100% | 0% | 0% | 100% (main:100%,thumb:93%) | image:13,video:178 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| community extras | community | community_music_card_options | 35 | 0% | 0% | 0% | 100% (thumb:100%) | image:35 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| community extras | community | community_music_cards | 111 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:111,video:111 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| community feed | community | community_feed | 40 | 100% | 0% | 0% | 100% (hls:25%,main:85%,min:10%,thumb:85%) | image:26,video:30 | 0% () | 80% | 0.0 | 30% | 100% comment,like,share,view | 0% | cost:3, media:9, model:7, hls:10, main:8, min:4, thumb:17 |
| community generations (feeds) | community | community_approved | 1559 | 100% | 17% | 3% | 100% (h264:6%,hls:84%,main:3%,min:100%,raw:100%,thumb:99%) | video:1559 | 94% (input_image,main_url,medias,motion,optimized_url) | 100% | 11.6 | 0% | 100% like,view | 0% | settings_keys:790 |
| community generations (feeds) | community | community_detail | 121 | 100% | 96% | 2% | 100% (main:22%,min:100%,raw:100%,thumb:20%) | image:97,video:24 | 80% (camera_lens,camera_model,custom_reference,input_image,input_images,media,medias,) | 100% | 10.7 | 34% | 100% like,view | 0% | settings_keys:1 |
| community generations (feeds) | community | community_top | 30 | 100% | 100% | 3% | 100% (main:10%,min:100%,raw:100%,thumb:30%) | image:20,video:10 | 77% (custom_reference,input_image,input_images,medias,style) | 100% | 12.5 | 33% | 100% like,view | 0% | settings_keys:9 |
| community generations (feeds) | community | community_trending | 2937 | 100% | 97% | 1% | 100% (main:27%,min:100%,raw:100%,thumb:10%) | image:2643,video:294 | 79% (camera_aperture,camera_focal_length,camera_lens,camera_model,custom_reference,im) | 100% | 10.5 | 30% | 100% like,view | 0% | input_urls:2, settings_keys:911, min:3, raw:3 |
| community posts | community | community_posts | 4 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:4,video:4 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | cost:4, media:4, model:4, hls:4, main:4, thumb:4 |
| community posts | community | community_posts_list | 40 | 100% | 0% | 0% | 100% (hls:55%,main:100%,min:35%,thumb:80%) | image:40,video:30 | 0% () | 100% | 0.0 | 55% | 100% comment,like,share,view | 0% | thumb:8 |
| community shots | community | community_shots | 40 | 100% | 0% | 0% | 100% (main:100%,thumb:40%) | image:24,video:16 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| contests | projects | projects_contest_by_slug | 3 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:3,video:3 | 0% () | 0% | 3.3 | 67% | 67% like,view | 0% | - |
| contests | projects | projects_contest_detail | 59 | 100% | 0% | 0% | 100% (main:76%,thumb:100%) | image:57,video:53 | 0% () | 0% | 2.8 | 56% | 53% like,view | 0% | - |
| contests | projects | projects_contest_entries | 458 | 100% | 0% | 0% | 100% (hls:96%,main:100%,thumb:100%) | image:458,video:456 | 0% () | 0% | 0.0 | 0% | 100% comment,follower,like,view,vote | 0% | eng:2, hls:4, main:5, thumb:5 |
| contests | projects | projects_contest_submissions | 2586 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:1959,video:2586 | 0% () | 0% | 0.0 | 0% | 100% like,view | 0% | - |
| contests | projects | projects_contests | 72 | 100% | 0% | 0% | 100% (main:24%,thumb:100%) | image:70,video:64 | 0% () | 0% | 0.0 | 0% | 0% | 0% | main:1, thumb:9 |
| creators | community | community_creators | 20 | 100% | 35% | 0% | 100% (hls:100%,main:100%,min:40%,raw:35%,thumb:100%) | image:20,video:20 | 30% (input_images,medias,style) | 35% | 5.2 | 10% | 100% comment,follower,like,view | 0% | cost:2, input_urls:6, inputs:6, media:20, model:7, multi:5, prompt:7, settings_keys:7, status:20, template:1, hls:20, main:20, min:7, raw:7, thumb:20 |
| creators | community | community_talents | 18 | 100% | 61% | 0% | 100% (hls:89%,main:89%,min:67%,raw:67%,thumb:94%) | image:17,video:17 | 61% (input_video,medias) | 67% | 11.6 | 6% | 100% comment,follower,like,view | 6% | cost:1, enh:1, input_urls:11, inputs:11, lineage:1, media:18, model:12, multi:7, prompt:11, settings_keys:12, status:18, hls:16, main:16, min:12, raw:11, thumb:17 |
| blog / help (text) | blog | blog_author | 201 | 0% | 0% | 0% | 100% (main:100%) | image:201 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | blog_index | 6 | 0% | 0% | 0% | 100% (main:100%) | image:6 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | blog_page | 1374 | 0% | 0% | 0% | 100% (main:100%) | 3d/file:2,image:1374 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | case_studies_index | 104 | 0% | 0% | 0% | 100% (main:100%) | image:104 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | case_study | 122 | 0% | 0% | 0% | 100% (main:100%) | image:122 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | changelog | 4 | 0% | 0% | 0% | 100% (main:100%) | image:4 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | enterprise_article | 140 | 0% | 0% | 0% | 100% (main:100%) | image:140 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | enterprise_index | 6 | 0% | 0% | 0% | 100% (main:100%) | image:6 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | help_article | 306 | 0% | 0% | 0% | 100% (main:100%) | image:306 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | help_index | 6 | 0% | 0% | 0% | 100% (main:100%) | image:6 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | post_content | 117 | 0% | 0% | 0% | 100% (main:100%) | other:117 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| blog / help (text) | blog | talent_posts | 117 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:117,other:117 | 0% () | 0% | 0.0 | 0% | 100% like,view | 0% | - |
| templates: viral/chain presets | community | community_viral_presets | 42 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:42,video:42 | 5% (options) | 100% | 0.1 | 100% | 0% | 0% | input_urls:2, settings_keys:2, main:42, thumb:42 |
| project nested (folders/assets) | projects | projects_folder | 14 | 100% | 0% | 0% | 100% (thumb:100%) | image:14 | 0% () | 0% | 0.0 | 0% | 100% view | 0% | - |
| project nested (folders/assets) | projects | projects_folder_children | 86 | 100% | 0% | 0% | 100% (thumb:100%) | image:86 | 0% () | 0% | 0.0 | 0% | 100% view | 100% | - |
| project nested (folders/assets) | projects | projects_folder_items | 5882 | 100% | 80% | 0% | 82% (main:1%,min:82%,raw:82%,thumb:36%) | audio:20,image:2851,other:20,video:2108 | 94% (camera_aperture,camera_lens,camera_model,custom_reference,download_url,era_contr) | 82% | 10.6 | 11% | 100% comment | 1% | inputs:1043 |
| project nested (folders/assets) | projects | projects_publication_detail | 3454 | 100% | 0% | 0% | 100% (hls:31%,main:100%,min:1%,thumb:50%) | image:2039,video:1835 | 0% () | 0% | 0.0 | 0% | 0% | 0% | main:3, thumb:3 |
| project nested (folders/assets) | projects | projects_related | 300 | 100% | 0% | 0% | 100% (hls:98%,main:100%,thumb:100%) | image:300,video:300 | 0% () | 0% | 0.0 | 47% | 100% comment,follower,like,view | 0% | cost:140, status:300, hls:295, main:300, thumb:286 |
| projects / series | projects | projects_publications | 792 | 100% | 0% | 0% | 100% (hls:33%,main:98%,min:3%,thumb:97%) | image:749,video:667 | 0% () | 0% | 0.0 | 0% | 100% comment,follower,like,view | 0% | - |
| projects / series | projects | projects_recommended | 2587 | 100% | 0% | 0% | 100% (hls:78%,main:99%,min:1%,thumb:99%) | image:2535,video:2467 | 0% () | 0% | 0.0 | 51% | 100% comment,follower,like,view | 0% | cost:10, status:3, hls:13, main:10, thumb:13 |
| projects / series | projects | projects_series_public | 20 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:20,video:20 | 0% () | 0% | 0.0 | 0% | 100% comment,like,play,view,vote | 0% | main:20, thumb:6 |
| projects / series | projects | projects_user_publications | 3 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 100% | 100% follower,like,view | 0% | - |
| projects / series | site | episode_page | 189 | 0% | 0% | 0% | 100% (hls:43%,main:100%,thumb:67%) | image:189,video:126 | 0% () | 0% | 0.0 | 0% | 33% like,share,view | 0% | - |
| showcase canvas | showcase | showcase_canvas_templates | 15 | 100% | 0% | 0% | 100% (thumb:100%) | image:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase cinema controls | showcase | showcase_cinema_controls | 167 | 100% | 0% | 0% | 100% (main:100%,thumb:78%) | image:36,video:131 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase editing room | showcase | showcase_videoshop_examples | 55 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:55,video:55 | 100% (input,thumbnail_url) | 0% | 0.0 | 0% | 0% | 0% | inputs:55 |
| showcase editing room | showcase | showcase_videoshop_project_examples | 30 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | image:30,other:30,video:30 | 100% (reference,references) | 0% | 0.0 | 0% | 0% | 0% | main:30, thumb:30 |
| showcase effects (viral) | showcase | showcase_effect_page | 1640 | 100% | 0% | 0% | 100% (hls:89%,main:95%,raw:89%,thumb:100%) | image:1356,video:1640 | 89% (input_image,input_media,input_video,main_url,media,medias,optimized_url,options,) | 100% | 12.7 | 25% | 0% | 0% | cost:403, input_urls:1431, settings_keys:1467, hls:3, main:110, raw:3, thumb:1606 |
| showcase explore (trends) | showcase | showcase_explore_feed | 610 | 100% | 74% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:610 | 100% (image,input_assets) | 100% | 2.6 | 0% | 72% comment,like,view | 0% | multi:37, status:610 |
| showcase faceless | showcase | showcase_faceless_showcases | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:27,video:27 | 0% () | 0% | 0.0 | 0% | 0% | 0% | main:1 |
| showcase intone | showcase | showcase_intone_explore | 54 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | audio:54,image:54,video:54 | 100% (character) | 0% | 0.0 | 0% | 0% | 0% | status:54, main:54 |
| showcase reels | showcase | showcase_reels_preset_detail | 240 | 100% | 44% | 0% | 100% (main:100%,thumb:100%) | image:240,video:240 | 82% (character_media) | 0% | 0.0 | 0% | 75% comment,like,view | 0% | - |
| showcase reels | showcase | showcase_reels_presets | 120 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:120,video:120 | 82% (character_media) | 0% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| showcase seedance/motion presets | showcase | showcase_motion_control_presets | 102 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:102 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| showcase seedance/motion presets | showcase | showcase_seedance_presets | 42 | 100% | 0% | 0% | 100% (thumb:100%) | image:12,video:42 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site apps | site | app_page | 423 | 0% | 0% | 0% | 100% (main:100%,thumb:35%) | image:292,video:149 | 32% (source,thumbnail) | 0% | 0.0 | 63% | 0% | 0% | - |
| site apps | site | apps_index | 10 | 0% | 0% | 0% | 100% (main:50%,thumb:50%) | image:10,video:5 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site mcp | site | mcp_bundle_page | 24 | 0% | 50% | 0% | 100% (main:100%,thumb:50%) | image:24,video:12 | 33% (poster_url,reference_medias) | 0% | 1.5 | 0% | 0% | 0% | - |
| site mcp | site | mcp_index | 8 | 0% | 50% | 0% | 100% (main:100%,thumb:50%) | image:8,video:4 | 50% (poster_url,reference_medias) | 0% | 1.5 | 0% | 0% | 0% | - |
| site mcp | site | mcp_skill_page | 270 | 0% | 50% | 0% | 100% (main:100%,thumb:50%) | image:242,video:135 | 20% (poster_url,reference_medias) | 0% | 1.5 | 0% | 0% | 0% | - |
| site pages | site | academy_index | 9 | 0% | 0% | 0% | 100% (main:33%,thumb:67%) | image:9,video:6 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site pages | site | course_page | 153 | 0% | 0% | 0% | 100% (main:100%,thumb:33%) | image:153,video:51 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site pages | site | landing_page | 1081 | 0% | 0% | 0% | 100% (hls:0%,main:86%,raw:1%,thumb:63%) | image:1074,video:497 | 1% (character_media,first_frame_url,preset_meta,style) | 1% | 0.1 | 5% | 1% comment,follower,like,view | 6% | - |
| site pages | site | lesson_page | 120 | 0% | 35% | 0% | 100% (main:100%,thumb:100%) | 3d/file:9,image:120,other:6,video:60 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site pages | site | mixed_media_page | 96 | 0% | 0% | 0% | 100% (hls:100%,main:100%,raw:100%,thumb:100%) | video:96 | 0% () | 100% | 0.0 | 0% | 100% like | 0% | - |
| site pages | site | originals_index | 4 | 0% | 0% | 0% | 100% (hls:100%,thumb:100%) | image:4,video:4 | 0% () | 0% | 0.0 | 0% | 100% comment,like,view,vote | 0% | - |
| site rooms | site | room_discussions | 1 | 100% | 0% | 0% | 100% (thumb:100%) | image:1 | 0% () | 0% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| site rooms | site | room_items | 23 | 100% | 4% | 0% | 100% (main:96%,min:4%,raw:4%,thumb:100%) | image:22,other:12,video:11 | 0% () | 4% | 0.3 | 4% | 100% comment,follower,like,view | 0% | cost:1, settings_keys:1, status:23, main:22, min:1, thumb:14 |
| site rooms | site | room_page | 60 | 0% | 0% | 0% | 100% (main:100%) | image:60 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| site rooms | site | rooms_api | 88 | 100% | 0% | 0% | 100% (thumb:100%) | image:88,video:34 | 0% () | 0% | 0.0 | 0% | 100% follower | 0% | media:2, status:88, thumb:70 |
| templates: motions | catalog | catalog_kling2_6_motions | 22 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:22 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_kling_motions | 58 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:58 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_minimax_motions | 77 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:77 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_motion_detail | 4 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:4 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_motion_samples | 18 | 100% | 0% | 0% | 100% (main:100%) | video:18 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_motions | 1832 | 100% | 0% | 0% | 100% (main:100%) | image:1832 | 0% () | 0% | 3.9 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_seedance_motions | 25 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:25 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_wan2_2_motions | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:27 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: motions | catalog | catalog_wan2_5_motions | 15 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_avatar_presets | 126 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:126 | 0% () | 0% | 2.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_avatars | 600 | 100% | 0% | 0% | 100% (main:100%) | image:600 | 100% (input_image) | 0% | 3.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_color_presets | 12 | 100% | 0% | 0% | 100% (thumb:100%) | image:12 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_katana_presets | 100 | 100% | 0% | 0% | 100% (main:100%,thumb:99%) | image:85,other:14,video:100 | 73% (reference_thumbnail_media,reference_video_media) | 0% | 0.0 | 0% | 0% | 0% | inputs:73 |
| templates: other presets | catalog | catalog_marketing_catalog | 7 | 100% | 0% | 0% | 100% (thumb:100%) | image:7,video:3 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_marketing_presets | 700 | 100% | 0% | 0% | 100% (thumb:100%) | image:442,video:258 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_mixed_media_presets | 33 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:33 | 12% (media) | 0% | 0.8 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_reference_voices | 690 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | audio:690,image:690,other:594 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_restyle_presets | 42 | 100% | 5% | 0% | 100% (hls:95%,main:100%,thumb:100%) | image:42,video:42 | 0% () | 100% | 1.9 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_soul_cinematic_styles | 2 | 100% | 0% | 0% | 100% (main:100%) | image:2 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_soul_samples | 7576 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:7570 | 100% (image_reference,style) | 100% | 14.3 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_soul_styles | 130 | 100% | 0% | 0% | 100% (main:100%) | image:130 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_sounds | 88 | 100% | 0% | 0% | 100% (main:100%) | audio:88,other:88 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_styles | 35 | 100% | 0% | 0% | 100% (main:100%) | image:35 | 0% () | 0% | 2.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_veo3_styles | 17 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:17 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_voices | 492 | 100% | 0% | 0% | 100% (main:100%) | audio:492,image:492,other:492 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: other presets | catalog | catalog_youtube_faceless_presets | 12 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:12,video:12 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| templates: viral/chain presets | catalog | catalog_chain_presets | 96 | 100% | 0% | 0% | 100% (thumb:100%) | image:28,video:96 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| templates: viral/chain presets | catalog | catalog_chain_presets_hidden | 114 | 100% | 0% | 0% | 100% (thumb:100%) | image:44,video:112 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| templates: viral/chain presets | catalog | catalog_viral_presets | 522 | 100% | 0% | 0% | 100% (main:56%,thumb:100%) | image:522,video:522 | 6% (media,options) | 100% | 0.3 | 62% | 0% | 0% | - |

### 4.3 Records fetched but never emitted (`--max-items` truncation)

NEW runs:

| scraper | endpoint | raw records | not emitted |
|---|---|---:|---:|
| community | community_approved | 50 | 29 |
| community | community_trending | 50 | 17 |
| projects | projects_publication_detail | 21 | 2 |
| showcase | showcase_cinema_controls | 78 | 48 |
| showcase | showcase_effect_page | 59 | 18 |
| showcase | showcase_explore_feed | 55 | 25 |
| showcase | showcase_motion_control_presets | 36 | 6 |
| showcase | showcase_reels_preset_detail | 180 | 60 |
| showcase | showcase_reels_presets | 117 | 57 |

OLD runs:

| scraper | endpoint | raw records | not emitted |
|---|---|---:|---:|
| account | account_benefits | 48 | 4 |
| account | account_compare | 46 | 46 |
| account | account_viral_presets | 174 | 174 |
| catalog | catalog_color_presets | 18 | 6 |
| catalog | catalog_katana_categories | 7 | 3 |
| catalog | catalog_katana_presets | 201 | 100 |
| catalog | catalog_kling2_6_motions | 45 | 22 |
| catalog | catalog_kling_motions | 117 | 58 |
| catalog | catalog_marketing_catalog | 15 | 7 |
| catalog | catalog_minimax_motions | 155 | 77 |
| catalog | catalog_mixed_media_presets | 67 | 33 |
| catalog | catalog_seedance_motions | 51 | 25 |
| catalog | catalog_soul_cinematic_styles | 5 | 2 |
| catalog | catalog_soul_keyframe_styles | 35 | 17 |
| catalog | catalog_soul_styles | 201 | 70 |
| catalog | catalog_veo3_styles | 35 | 17 |
| catalog | catalog_wan2_2_motions | 55 | 27 |
| catalog | catalog_wan2_5_motions | 31 | 15 |
| catalog | catalog_youtube_faceless_presets | 25 | 12 |
| community | community_approved | 1638 | 68 |
| community | community_benefits | 72 | 6 |
| community | community_compare | 66 | 66 |
| community | community_model_x | 50 | 50 |
| community | community_music_cards | 137 | 26 |
| community | community_plans | 70 | 70 |
| community | community_posts | 10 | 6 |
| community | community_top | 110 | 80 |
| community | community_trending | 3581 | 607 |
| community | community_viral_presets | 174 | 132 |
| pricing | compare | 1080 | 100 |
| projects | projects_categories | 18 | 4 |
| projects | projects_contest_detail | 69 | 10 |
| projects | projects_contest_entries | 925 | 467 |
| projects | projects_contest_submissions | 3303 | 690 |
| projects | projects_contests | 111 | 39 |
| projects | projects_publication_detail | 17237 | 3132 |
| projects | projects_publications | 1220 | 413 |
| projects | projects_recommended | 3960 | 1358 |
| projects | projects_user_publications | 24 | 21 |
| showcase | showcase_cinema_controls | 234 | 48 |
| showcase | showcase_effect_page | 1645 | 5 |
| showcase | showcase_explore_feed | 635 | 25 |
| showcase | showcase_motion_control_presets | 108 | 6 |
| showcase | showcase_reels_preset_detail | 360 | 120 |
| showcase | showcase_reels_presets | 427 | 307 |
| site | landing_page | 1707 | 2 |
| site | room_items | 51 | 14 |
| site | rooms_api | 138 | 30 |

`catalog --kinds all --max-items 30` (run `20261126-154952_completeness-catalog`) fetched all 31 endpoints but
wrote records for `motions` (30), `motion_samples` and `soul_samples` only; `normalize` of that run reproduces the
cap. The audit therefore uses the `--max-pages 1` catalog run. Same pattern in community (approved feed after 30
trending items), showcase (explore / reels / cinema controls) and site (`mcp_index` 75 items, 30 written).

### 4.4 All videos (and audio / other non-image media), NEW runs

Every video-producing source; one row per source endpoint (models rolled up; per-model rows in 4.6).

| kind | scraper | endpoint | n | joined | prompt | neg | media (variants) | kinds | inputs (roles) | model | avg settings | cost | engagement | lineage | lost in output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| audio | catalog | catalog_reference_voices | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | audio:30,image:30,other:29 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | catalog | catalog_sounds | 11 | 100% | 0% | 0% | 100% (main:100%) | audio:11,other:11 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | catalog | catalog_voices | 30 | 100% | 0% | 0% | 100% (main:100%) | audio:30,image:30,other:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | projects | projects_folder_items | 8 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | audio:8,other:8 | 0% () | 100% | 3.0 | 0% | 100% comment | 0% | - |
| video | catalog | catalog_avatar_presets | 21 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:21 | 0% () | 0% | 2.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_chain_presets | 48 | 100% | 0% | 0% | 100% (thumb:100%) | image:14,video:48 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_katana_presets | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:97%) | image:28,other:1,video:30 | 93% (reference_thumbnail_media,reference_video_media) | 0% | 0.0 | 0% | 0% | 0% | inputs:28 |
| video | catalog | catalog_kling2_6_motions | 22 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:22 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_kling_motions | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_marketing_catalog | 3 | 100% | 0% | 0% | 100% (thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_marketing_presets | 87 | 100% | 0% | 0% | 100% (thumb:100%) | video:87 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_minimax_motions | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_mixed_media_presets | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 13% (media) | 0% | 0.9 | 0% | 0% | 0% | - |
| video | catalog | catalog_motion_samples | 3 | 100% | 0% | 0% | 100% (main:100%) | video:3 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_restyle_presets | 21 | 100% | 5% | 0% | 100% (hls:95%,main:100%,thumb:100%) | image:21,video:21 | 0% () | 100% | 1.9 | 0% | 0% | 0% | - |
| video | catalog | catalog_seedance_motions | 25 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:25 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_veo3_styles | 17 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:17 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_viral_presets | 87 | 100% | 0% | 0% | 100% (main:56%,thumb:100%) | image:87,video:87 | 6% (media,options) | 100% | 0.3 | 62% | 0% | 0% | - |
| video | catalog | catalog_wan2_2_motions | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:27 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_wan2_5_motions | 15 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_youtube_faceless_presets | 12 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:12,video:12 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | community | community_approved | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| video | community | community_detail | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| video | community | community_posts_list | 22 | 100% | 0% | 0% | 100% (hls:59%,main:100%,min:9%,thumb:100%) | image:22,video:22 | 0% () | 100% | 0.0 | 64% | 100% comment,like,share,view | 0% | thumb:7 |
| video | community | community_shots | 12 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:12 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_trending | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| video | projects | projects_contest_by_slug | 1 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:1,video:1 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | projects | projects_contest_entries | 2 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:2,video:2 | 0% () | 0% | 0.0 | 0% | 100% comment,follower,like,view,vote | 0% | - |
| video | projects | projects_folder_items | 400 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:400 | 100% (medias) | 100% | 16.6 | 1% | 100% comment | 0% | - |
| video | projects | projects_publication_detail | 2 | 100% | 0% | 0% | 100% (main:100%) | video:2 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_cinema_controls | 15 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_effect_page | 41 | 100% | 0% | 0% | 100% (hls:90%,main:98%,raw:90%,thumb:100%) | image:41,video:41 | 90% (input_image,input_media,main_url,medias,optimized_url,preset_meta) | 100% | 13.6 | 10% | 0% | 0% | cost:4, input_urls:37, settings_keys:37, hls:7, main:10, raw:7, thumb:41 |
| video | showcase | showcase_explore_feed | 30 | 100% | 63% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:30 | 100% (image,input_assets) | 100% | 1.2 | 0% | 33% comment,like | 0% | multi:2, status:30 |
| video | showcase | showcase_faceless_showcases | 9 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:9,video:9 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_intone_explore | 18 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | audio:18,image:18,video:18 | 100% (character) | 0% | 0.0 | 0% | 0% | 0% | status:18, main:18 |
| video | showcase | showcase_motion_control_presets | 30 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:30 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_reels_preset_detail | 120 | 100% | 45% | 0% | 100% (main:100%,thumb:100%) | image:120,video:120 | 80% (character_media) | 0% | 0.0 | 0% | 75% comment,like,view | 0% | - |
| video | showcase | showcase_reels_presets | 60 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:60,video:60 | 80% (character_media) | 0% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | showcase | showcase_seedance_presets | 14 | 100% | 0% | 0% | 100% (thumb:100%) | image:4,video:14 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_videoshop_examples | 11 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:11,video:11 | 100% (input,thumbnail_url) | 0% | 0.0 | 0% | 0% | 0% | inputs:11 |
| video | showcase | showcase_videoshop_project_examples | 6 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | image:6,other:6,video:6 | 100% (reference,references) | 0% | 0.0 | 0% | 0% | 0% | main:6, thumb:6 |
| video | site | app_page | 34 | 0% | 0% | 0% | 100% (main:100%,thumb:100%) | image:11,video:34 | 68% (source,thumbnail) | 0% | 0.0 | 65% | 0% | 0% | - |
| video | site | apps_index | 1 | 0% | 0% | 0% | 100% (thumb:100%) | image:1,video:1 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | site | mcp_bundle_page | 3 | 0% | 100% | 0% | 100% (main:100%,thumb:100%) | image:3,video:3 | 67% (poster_url,reference_medias) | 0% | 3.0 | 0% | 0% | 0% | - |
| video | site | mcp_index | 1 | 0% | 100% | 0% | 100% (main:100%,thumb:100%) | image:1,video:1 | 100% (poster_url,reference_medias) | 0% | 3.0 | 0% | 0% | 0% | - |
| video | site | mcp_skill_page | 30 | 0% | 100% | 0% | 100% (main:100%,thumb:100%) | image:25,video:30 | 60% (poster_url,reference_medias) | 0% | 3.0 | 0% | 0% | 0% | - |

### 4.5 All videos (and audio / other), OLD runs

| kind | scraper | endpoint | n | joined | prompt | neg | media (variants) | kinds | inputs (roles) | model | avg settings | cost | engagement | lineage | lost in output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3d/file | blog | blog_page | 2 | 0% | 0% | 0% | 100% (main:100%) | 3d/file:2,image:2 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | catalog | catalog_reference_voices | 690 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | audio:690,image:690,other:594 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | catalog | catalog_sounds | 88 | 100% | 0% | 0% | 100% (main:100%) | audio:88,other:88 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | catalog | catalog_voices | 492 | 100% | 0% | 0% | 100% (main:100%) | audio:492,image:492,other:492 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| audio | projects | projects_folder_items | 20 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | audio:20,other:20 | 30% (medias) | 100% | 7.4 | 0% | 100% comment | 0% | - |
| blog / help (text) | blog | post_content | 117 | 0% | 0% | 0% | 100% (main:100%) | other:117 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_avatar_presets | 126 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:126 | 0% () | 0% | 2.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_chain_presets | 96 | 100% | 0% | 0% | 100% (thumb:100%) | image:28,video:96 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets_hidden | 112 | 100% | 0% | 0% | 100% (thumb:100%) | image:42,video:112 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_katana_presets | 100 | 100% | 0% | 0% | 100% (main:100%,thumb:99%) | image:85,other:14,video:100 | 73% (reference_thumbnail_media,reference_video_media) | 0% | 0.0 | 0% | 0% | 0% | inputs:73 |
| video | catalog | catalog_kling2_6_motions | 22 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:22 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_kling_motions | 58 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:58 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_marketing_catalog | 3 | 100% | 0% | 0% | 100% (thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_marketing_presets | 258 | 100% | 0% | 0% | 100% (thumb:100%) | video:258 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_minimax_motions | 77 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:77 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_mixed_media_presets | 33 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:33 | 12% (media) | 0% | 0.8 | 0% | 0% | 0% | - |
| video | catalog | catalog_motion_detail | 4 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:4 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_motion_samples | 18 | 100% | 0% | 0% | 100% (main:100%) | video:18 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_restyle_presets | 42 | 100% | 5% | 0% | 100% (hls:95%,main:100%,thumb:100%) | image:42,video:42 | 0% () | 100% | 1.9 | 0% | 0% | 0% | - |
| video | catalog | catalog_seedance_motions | 25 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:25 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_veo3_styles | 17 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:17 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_viral_presets | 522 | 100% | 0% | 0% | 100% (main:56%,thumb:100%) | image:522,video:522 | 6% (media,options) | 100% | 0.3 | 62% | 0% | 0% | - |
| video | catalog | catalog_wan2_2_motions | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:27 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_wan2_5_motions | 15 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:15 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_youtube_faceless_presets | 12 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:12,video:12 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | community | community_approved | 1559 | 100% | 17% | 3% | 100% (h264:6%,hls:84%,main:3%,min:100%,raw:100%,thumb:99%) | video:1559 | 94% (input_image,main_url,medias,motion,optimized_url) | 100% | 11.6 | 0% | 100% like,view | 0% | settings_keys:790 |
| video | community | community_creators | 20 | 100% | 35% | 0% | 100% (hls:100%,main:100%,min:40%,raw:35%,thumb:100%) | image:20,video:20 | 30% (input_images,medias,style) | 35% | 5.2 | 10% | 100% comment,follower,like,view | 0% | cost:2, input_urls:6, inputs:6, media:20, model:7, multi:5, prompt:7, settings_keys:7, status:20, template:1, hls:20, main:20, min:7, raw:7, thumb:20 |
| video | community | community_detail | 24 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:24 | 88% (medias) | 100% | 9.9 | 0% | 100% like,view | 0% | settings_keys:1 |
| video | community | community_explore_cards | 178 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:178 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | community | community_feed | 30 | 100% | 0% | 0% | 100% (hls:33%,main:93%,min:7%,thumb:100%) | image:16,video:30 | 0% () | 87% | 0.0 | 40% | 100% comment,like,share,view | 0% | cost:3, media:6, model:5, hls:10, main:6, min:2, thumb:16 |
| video | community | community_music_cards | 111 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:111,video:111 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | community | community_posts | 4 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:4,video:4 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | cost:4, media:4, model:4, hls:4, main:4, thumb:4 |
| video | community | community_posts_list | 30 | 100% | 0% | 0% | 100% (hls:73%,main:100%,min:13%,thumb:100%) | image:30,video:30 | 0% () | 100% | 0.0 | 73% | 100% comment,like,share,view | 0% | thumb:6 |
| video | community | community_shots | 16 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:16 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_talents | 17 | 100% | 59% | 0% | 100% (hls:94%,main:94%,min:65%,raw:65%,thumb:100%) | image:16,video:17 | 65% (input_video,medias) | 65% | 11.8 | 6% | 100% comment,follower,like,view | 6% | cost:1, enh:1, input_urls:11, inputs:11, lineage:1, media:17, model:11, multi:7, prompt:10, settings_keys:11, status:17, hls:16, main:16, min:11, raw:10, thumb:17 |
| video | community | community_top | 10 | 100% | 100% | 10% | 100% (min:100%,raw:100%,thumb:90%) | video:10 | 90% (input_image,medias) | 100% | 15.2 | 0% | 100% like,view | 0% | settings_keys:9 |
| video | community | community_trending | 294 | 100% | 100% | 1% | 100% (min:100%,raw:100%,thumb:99%) | video:294 | 86% (input_image,medias) | 100% | 11.9 | 0% | 100% like,view | 0% | settings_keys:73 |
| video | community | community_viral_presets | 42 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:42,video:42 | 5% (options) | 100% | 0.1 | 100% | 0% | 0% | input_urls:2, settings_keys:2, main:42, thumb:42 |
| video | projects | projects_contest_by_slug | 3 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:3,video:3 | 0% () | 0% | 3.3 | 67% | 67% like,view | 0% | - |
| video | projects | projects_contest_detail | 53 | 100% | 0% | 0% | 100% (main:85%,thumb:100%) | image:51,video:53 | 0% () | 0% | 3.1 | 62% | 58% like,view | 0% | - |
| video | projects | projects_contest_entries | 456 | 100% | 0% | 0% | 100% (hls:96%,main:100%,thumb:100%) | image:456,video:456 | 0% () | 0% | 0.0 | 0% | 100% comment,follower,like,view,vote | 0% | eng:2, hls:4, main:5, thumb:5 |
| video | projects | projects_contest_submissions | 2586 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:1959,video:2586 | 0% () | 0% | 0.0 | 0% | 100% like,view | 0% | - |
| video | projects | projects_contests | 64 | 100% | 0% | 0% | 100% (main:27%,thumb:100%) | image:62,video:64 | 0% () | 0% | 0.0 | 0% | 0% | 0% | main:1, thumb:9 |
| video | projects | projects_folder_items | 2108 | 100% | 93% | 0% | 100% (main:1%,min:100%,raw:100%,thumb:100%) | image:141,video:2108 | 98% (camera_aperture,camera_lens,camera_model,era_control,genre_control,input_audio,i) | 100% | 16.5 | 4% | 100% comment | 2% | - |
| video | projects | projects_publication_detail | 1835 | 100% | 0% | 0% | 100% (hls:59%,main:100%,min:2%,thumb:94%) | image:420,video:1835 | 0% () | 0% | 0.0 | 0% | 0% | 0% | thumb:3 |
| video | projects | projects_publications | 667 | 100% | 0% | 0% | 100% (hls:39%,main:98%,min:4%,thumb:100%) | image:624,video:667 | 0% () | 0% | 0.0 | 0% | 100% comment,follower,like,view | 0% | - |
| video | projects | projects_recommended | 2467 | 100% | 0% | 0% | 100% (hls:82%,main:100%,min:1%,thumb:100%) | image:2415,video:2467 | 0% () | 0% | 0.0 | 54% | 100% comment,follower,like,view | 0% | cost:10, status:3, hls:13, main:10, thumb:13 |
| video | projects | projects_related | 300 | 100% | 0% | 0% | 100% (hls:98%,main:100%,thumb:100%) | image:300,video:300 | 0% () | 0% | 0.0 | 47% | 100% comment,follower,like,view | 0% | cost:140, status:300, hls:295, main:300, thumb:286 |
| video | projects | projects_series_public | 20 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:20,video:20 | 0% () | 0% | 0.0 | 0% | 100% comment,like,play,view,vote | 0% | main:20, thumb:6 |
| video | projects | projects_user_publications | 3 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 100% | 100% follower,like,view | 0% | - |
| video | showcase | showcase_cinema_controls | 131 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:131 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_effect_page | 1640 | 100% | 0% | 0% | 100% (hls:89%,main:95%,raw:89%,thumb:100%) | image:1356,video:1640 | 89% (input_image,input_media,input_video,main_url,media,medias,optimized_url,options,) | 100% | 12.7 | 25% | 0% | 0% | cost:403, input_urls:1431, settings_keys:1467, hls:3, main:110, raw:3, thumb:1606 |
| video | showcase | showcase_explore_feed | 610 | 100% | 74% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:610 | 100% (image,input_assets) | 100% | 2.6 | 0% | 72% comment,like,view | 0% | multi:37, status:610 |
| video | showcase | showcase_faceless_showcases | 27 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:27,video:27 | 0% () | 0% | 0.0 | 0% | 0% | 0% | main:1 |
| video | showcase | showcase_intone_explore | 54 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | audio:54,image:54,video:54 | 100% (character) | 0% | 0.0 | 0% | 0% | 0% | status:54, main:54 |
| video | showcase | showcase_motion_control_presets | 102 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:102 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_reels_preset_detail | 240 | 100% | 44% | 0% | 100% (main:100%,thumb:100%) | image:240,video:240 | 82% (character_media) | 0% | 0.0 | 0% | 75% comment,like,view | 0% | - |
| video | showcase | showcase_reels_presets | 120 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:120,video:120 | 82% (character_media) | 0% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | showcase | showcase_seedance_presets | 42 | 100% | 0% | 0% | 100% (thumb:100%) | image:12,video:42 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | showcase | showcase_videoshop_examples | 55 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:55,video:55 | 100% (input,thumbnail_url) | 0% | 0.0 | 0% | 0% | 0% | inputs:55 |
| video | showcase | showcase_videoshop_project_examples | 30 | 100% | 100% | 0% | 100% (main:100%,thumb:100%) | image:30,other:30,video:30 | 100% (reference,references) | 0% | 0.0 | 0% | 0% | 0% | main:30, thumb:30 |
| video | site | academy_index | 6 | 0% | 0% | 0% | 100% (thumb:100%) | image:6,video:6 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | site | app_page | 149 | 0% | 0% | 0% | 100% (main:100%,thumb:100%) | image:18,video:149 | 88% (source,thumbnail) | 0% | 0.0 | 85% | 0% | 0% | - |
| video | site | apps_index | 5 | 0% | 0% | 0% | 100% (thumb:100%) | image:5,video:5 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | site | course_page | 51 | 0% | 0% | 0% | 100% (main:100%,thumb:100%) | image:51,video:51 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | site | episode_page | 126 | 0% | 0% | 0% | 100% (hls:65%,main:100%,thumb:100%) | image:126,video:126 | 0% () | 0% | 0.0 | 0% | 50% like,share,view | 0% | - |
| video | site | landing_page | 497 | 0% | 0% | 0% | 100% (hls:1%,main:98%,raw:1%,thumb:100%) | image:490,video:497 | 1% (character_media,first_frame_url) | 1% | 0.1 | 1% | 1% comment,follower,like,view | 8% | - |
| video | site | lesson_page | 60 | 0% | 70% | 0% | 100% (main:100%,thumb:100%) | 3d/file:9,image:60,other:6,video:60 | 0% () | 0% | 0.0 | 0% | 0% | 0% | - |
| video | site | mcp_bundle_page | 12 | 0% | 100% | 0% | 100% (main:100%,thumb:100%) | image:12,video:12 | 67% (poster_url,reference_medias) | 0% | 3.0 | 0% | 0% | 0% | - |
| video | site | mcp_index | 4 | 0% | 100% | 0% | 100% (main:100%,thumb:100%) | image:4,video:4 | 100% (poster_url,reference_medias) | 0% | 3.0 | 0% | 0% | 0% | - |
| video | site | mcp_skill_page | 135 | 0% | 100% | 0% | 100% (main:100%,thumb:100%) | image:107,video:135 | 40% (poster_url,reference_medias) | 0% | 3.0 | 0% | 0% | 0% | - |
| video | site | mixed_media_page | 96 | 0% | 0% | 0% | 100% (hls:100%,main:100%,raw:100%,thumb:100%) | video:96 | 0% () | 100% | 0.0 | 0% | 100% like | 0% | - |
| video | site | originals_index | 4 | 0% | 0% | 0% | 100% (hls:100%,thumb:100%) | image:4,video:4 | 0% () | 0% | 0.0 | 0% | 100% comment,like,view,vote | 0% | - |
| video | site | room_items | 11 | 100% | 9% | 0% | 100% (main:91%,min:9%,raw:9%,thumb:100%) | image:10,video:11 | 0% () | 9% | 0.6 | 9% | 100% comment,follower,like,view | 0% | cost:1, settings_keys:1, status:11, main:10, min:1, thumb:11 |
| video | site | rooms_api | 34 | 100% | 0% | 0% | 100% (thumb:100%) | image:34,video:34 | 0% () | 0% | 0.0 | 0% | 100% follower | 0% | media:1, status:34, thumb:34 |

### 4.6 Per `job_set_type` / product, NEW runs

| kind | scraper | endpoint | model / job_set_type | n | joined | prompt | neg | media (variants) | kinds | inputs (roles) | model | avg settings | cost | engagement | lineage | lost in output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| video | catalog | catalog_chain_presets | seedance_2_0_fast | 27 | 100% | 0% | 0% | 100% (thumb:100%) | image:5,video:27 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets | seedance_2_0 | 14 | 100% | 0% | 0% | 100% (thumb:100%) | image:9,video:14 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets | kling3_0 | 7 | 100% | 0% | 0% | 100% (thumb:100%) | video:7 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| image | catalog | catalog_marketing_catalog | marketing_studio_2_image | 4 | 100% | 0% | 0% | 100% (thumb:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_marketing_catalog | marketing_studio_v2_video | 3 | 100% | 0% | 0% | 100% (thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_restyle_presets | restyle | 21 | 100% | 5% | 0% | 100% (hls:95%,main:100%,thumb:100%) | image:21,video:21 | 0% () | 100% | 1.9 | 0% | 0% | 0% | - |
| image | catalog | catalog_soul_samples | text2image_soul | 30 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:30 | 100% (style) | 100% | 14.2 | 0% | 0% | 0% | - |
| video | catalog | catalog_viral_presets | viral_hub_video | 87 | 100% | 0% | 0% | 100% (main:56%,thumb:100%) | image:87,video:87 | 6% (media,options) | 100% | 0.3 | 62% | 0% | 0% | - |
| video | community | community_approved | magi_2 | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| video | community | community_detail | magi_2 | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | nano_banana_2_1 | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:4 | 100% (medias) | 100% | 11.0 | 25% | 100% like,view | 0% | - |
| image | community | community_detail | nano_banana_2 | 2 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:2 | 100% (input_images) | 100% | 7.0 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | soul_cinematic | 1 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:1 | 100% (camera_lens,camera_model,style) | 100% | 12.0 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | text2image_soul_v2 | 1 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:1 | 100% (style) | 100% | 15.0 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | gpt_image_2_6 | 1 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:1 | 100% (medias) | 100% | 12.0 | 100% | 100% like,view | 0% | - |
| video | community | community_posts_list | seedance_2_5 | 10 | 100% | 0% | 0% | 100% (hls:70%,main:100%,min:10%,thumb:100%) | image:10,video:10 | 0% () | 100% | 0.0 | 70% | 100% comment,like,share,view | 0% | thumb:3 |
| video | community | community_posts_list | gpt_image_2_6 | 3 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | - |
| image | community | community_posts_list | soul_cinematic | 3 | 100% | 0% | 0% | 100% (main:100%,min:100%) | image:3 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| video | community | community_posts_list | hf_mult_motion_control | 3 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | thumb:3 |
| video | community | community_posts_list | topaz_video | 1 | 100% | 0% | 0% | 100% (main:100%,min:100%,thumb:100%) | image:1,video:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| image | community | community_posts_list | gpt_image_2_6 | 1 | 100% | 0% | 0% | 100% (main:100%,min:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| image | community | community_posts_list | text2image_soul_v2 | 1 | 100% | 0% | 0% | 100% (main:100%,min:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| image | community | community_posts_list | recraft_v4_1 | 1 | 100% | 0% | 0% | 100% (main:100%,min:100%,thumb:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | thumb:1 |
| video | community | community_posts_list | cinematic_studio_video_4_0 | 1 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:1,video:1 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | - |
| video | community | community_posts_list | hf_mult_replace_object_flash | 1 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:1,video:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | thumb:1 |
| video | community | community_posts_list | seedream_v5_pro | 1 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:1,video:1 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | - |
| video | community | community_posts_list | seedance_2_0_mini | 1 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:1,video:1 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | - |
| video | community | community_posts_list | kling4_0 | 1 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:1,video:1 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | - |
| video | community | community_shots | hf_mult_replace_object | 4 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_shots | hf_mult_motion_control | 4 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | nano_banana_2 | 4 | 100% | 0% | 0% | 100% (main:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | nano_banana_2_1 | 3 | 100% | 0% | 0% | 100% (main:100%) | image:3 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | text2image_soul_v2 | 3 | 100% | 0% | 0% | 100% (main:100%) | image:3 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_shots | magi_2 | 3 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:3 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | soul_cinematic | 2 | 100% | 0% | 0% | 100% (main:100%) | image:2 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | gpt_image_2_6 | 2 | 100% | 0% | 0% | 100% (main:100%) | image:2 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | image_auto | 1 | 100% | 0% | 0% | 100% (main:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | seedream_v5_pro | 1 | 100% | 0% | 0% | 100% (main:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | flux_2 | 1 | 100% | 0% | 0% | 100% (main:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_shots | seedance_2_5 | 1 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | gpt_image_2_5 | 1 | 100% | 0% | 0% | 100% (main:100%) | image:1 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_trending | magi_2 | 21 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:21 | 86% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | nano_banana_2_1 | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:4 | 100% (medias) | 100% | 11.0 | 25% | 100% like,view | 0% | - |
| image | community | community_trending | nano_banana_2 | 2 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:2 | 100% (input_images) | 100% | 7.0 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | text2image_soul_v2 | 1 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:1 | 100% (style) | 100% | 15.0 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | gpt_image_2_6 | 1 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:1 | 100% (medias) | 100% | 12.0 | 100% | 100% like,view | 0% | - |
| image | community | community_trending | soul_cinematic | 1 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:1 | 100% (camera_lens,camera_model,style) | 100% | 12.0 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | gpt_image_2_5 | 1 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:1 | 100% (medias) | 100% | 10.0 | 100% | 100% like,view | 0% | cost:1, input_urls:1, inputs:1, prompt:1, settings_keys:1, status:1, raw:1 |
| image | community | community_trending | flux_2 | 1 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:1 | 100% (input_images) | 100% | 11.0 | 0% | 100% like,view | 0% | input_urls:1, inputs:1, prompt:1, settings_keys:1, status:1, raw:1 |
| image | community | community_trending | image_auto | 1 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:1 | 100% (medias) | 100% | 8.0 | 0% | 100% like,view | 0% | input_urls:1, inputs:1, prompt:1, settings_keys:1, status:1, raw:1 |
| video | projects | projects_folder_items | seedance_2_5 | 361 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:361 | 100% (medias) | 100% | 17.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | gpt_image_2_6 | 88 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:88 | 82% (medias) | 100% | 10.6 | 100% | 100% comment | 0% | - |
| image | projects | projects_folder_items | seedream_5_5 | 25 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:25 | 76% (medias) | 100% | 9.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | magi_2 | 14 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:14 | 100% (medias) | 100% | 10.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | seedance_2_5_flash | 11 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:11 | 100% (medias) | 100% | 16.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | seedance_2_0 | 9 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:9 | 100% (medias) | 100% | 16.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | nano_banana_2_1 | 8 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:8 | 25% (medias) | 100% | 9.5 | 100% | 100% comment | 0% | - |
| audio | projects | projects_folder_items | elevenlabs_music_v2_5 | 8 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | audio:8,other:8 | 0% () | 100% | 3.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | text2image_soul_v2 | 7 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:7 | 100% (image_reference,style) | 100% | 10.1 | 0% | 100% comment | 0% | - |
| none (inputs/prompt only) | projects | projects_folder_items | seedance_2_5 | 5 | 100% | 100% | 0% | 0% () |  | 100% (medias) | 100% | 17.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | kling4_0 | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:4 | 100% (medias) | 100% | 11.0 | 100% | 100% comment | 0% | - |
| video | projects | projects_folder_items | gemini_omni_flash_1_2 | 1 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:1 | 100% (medias) | 100% | 11.0 | 100% | 100% comment | 0% | - |
| video | showcase | showcase_effect_page | viral_hub_video | 41 | 100% | 0% | 0% | 100% (hls:90%,main:98%,raw:90%,thumb:100%) | image:41,video:41 | 90% (input_image,input_media,main_url,medias,optimized_url,preset_meta) | 100% | 13.6 | 10% | 0% | 0% | cost:4, input_urls:37, settings_keys:37, hls:7, main:10, raw:7, thumb:41 |
| video | showcase | showcase_explore_feed | hf_mult_motion_control | 15 | 100% | 47% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:15 | 100% (image,input_assets) | 100% | 1.3 | 0% | 33% comment,like | 0% | multi:2, status:15 |
| video | showcase | showcase_explore_feed | hf_mult_replace_object | 13 | 100% | 85% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:13 | 100% (image,input_assets) | 100% | 0.7 | 0% | 23% comment,like | 0% | status:13 |
| video | showcase | showcase_explore_feed | hf_mult_replace_object_flash | 2 | 100% | 50% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:2 | 100% (image) | 100% | 3.0 | 0% | 100% comment,like | 0% | status:2 |

### 4.7 Per `job_set_type` / product, OLD runs (n ≥ 3)

| kind | scraper | endpoint | model / job_set_type | n | joined | prompt | neg | media (variants) | kinds | inputs (roles) | model | avg settings | cost | engagement | lineage | lost in output |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| video | catalog | catalog_chain_presets | seedance_2_0_fast | 54 | 100% | 0% | 0% | 100% (thumb:100%) | image:10,video:54 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets | seedance_2_0 | 28 | 100% | 0% | 0% | 100% (thumb:100%) | image:18,video:28 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets | kling3_0 | 14 | 100% | 0% | 0% | 100% (thumb:100%) | video:14 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets_hidden | seedance_2_0_fast | 66 | 100% | 0% | 0% | 100% (thumb:100%) | image:20,video:66 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets_hidden | seedance_2_0 | 32 | 100% | 0% | 0% | 100% (thumb:100%) | image:22,video:32 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| video | catalog | catalog_chain_presets_hidden | kling3_0 | 14 | 100% | 0% | 0% | 100% (thumb:100%) | video:14 | 0% () | 100% | 0.0 | 100% | 0% | 0% | - |
| image | catalog | catalog_marketing_catalog | marketing_studio_2_image | 4 | 100% | 0% | 0% | 100% (thumb:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_marketing_catalog | marketing_studio_v2_video | 3 | 100% | 0% | 0% | 100% (thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_restyle_presets | restyle | 42 | 100% | 5% | 0% | 100% (hls:95%,main:100%,thumb:100%) | image:42,video:42 | 0% () | 100% | 1.9 | 0% | 0% | 0% | - |
| image | catalog | catalog_soul_samples | text2image_soul | 7570 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:7570 | 100% (image_reference,style) | 100% | 14.3 | 0% | 0% | 0% | - |
| none (inputs/prompt only) | catalog | catalog_soul_samples | text2image_soul | 6 | 100% | 100% | 0% | 0% () |  | 100% (style) | 100% | 15.0 | 0% | 0% | 0% | - |
| video | catalog | catalog_viral_presets | viral_hub_video | 522 | 100% | 0% | 0% | 100% (main:56%,thumb:100%) | image:522,video:522 | 6% (media,options) | 100% | 0.3 | 62% | 0% | 0% | - |
| video | community | community_approved | viral_hub_video | 1253 | 100% | 0% | 0% | 100% (h264:7%,hls:100%,min:100%,raw:100%,thumb:100%) | video:1253 | 100% (main_url,medias,optimized_url) | 100% | 11.7 | 0% | 100% like,view | 0% | settings_keys:780 |
| video | community | community_approved | magi_2 | 69 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:69 | 87% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| video | community | community_approved | seedance_2_5 | 48 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:48 | 71% (medias) | 100% | 15.2 | 0% | 100% like,view | 0% | settings_keys:10 |
| video | community | community_approved | seedance_2_0 | 40 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:40 | 0% () | 100% | 13.0 | 0% | 100% like,view | 0% | - |
| video | community | community_approved | wan2_5_video | 40 | 100% | 100% | 100% | 100% (hls:55%,min:100%,raw:100%,thumb:55%) | video:40 | 100% (input_image,motion) | 100% | 11.6 | 0% | 100% like,view | 0% | - |
| video | community | community_approved | minimax_hailuo | 40 | 100% | 8% | 0% | 100% (hls:100%,main:100%,min:100%,raw:100%,thumb:100%) | video:40 | 100% (input_image,motion) | 100% | 10.0 | 0% | 100% like,view | 0% | - |
| video | community | community_approved | sora2_video | 40 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:40 | 20% (input_image,motion) | 100% | 8.6 | 0% | 100% like,view | 0% | - |
| video | community | community_approved | kling3_0 | 29 | 100% | 93% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:29 | 93% (medias) | 100% | 11.8 | 0% | 100% like,view | 0% | - |
| video | community | community_creators | seedance_2_5 | 3 | 100% | 100% | 0% | 100% (hls:100%,main:100%,min:100%,raw:100%,thumb:100%) | image:3,video:3 | 67% (medias) | 100% | 16.0 | 0% | 100% comment,follower,like,view | 0% | input_urls:2, inputs:2, media:3, model:3, multi:1, prompt:3, settings_keys:3, status:3, hls:3, main:3, min:3, raw:3, thumb:3 |
| image | community | community_detail | gpt_image_2_6 | 32 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:32 | 78% (medias) | 100% | 11.2 | 100% | 100% like,view | 0% | - |
| video | community | community_detail | magi_2 | 23 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:23 | 87% (medias) | 100% | 9.6 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | text2image_soul_v2 | 12 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:12 | 100% (custom_reference,medias,style) | 100% | 13.8 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | soul_cinematic | 12 | 100% | 83% | 0% | 100% (main:100%,min:100%,raw:100%) | image:12 | 100% (camera_lens,camera_model,medias,style) | 100% | 10.0 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | nano_banana_2 | 10 | 100% | 100% | 30% | 100% (min:100%,raw:100%) | image:10 | 90% (input_images,medias) | 100% | 10.1 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | seedream_v4_5 | 5 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:5 | 20% (input_images) | 100% | 7.4 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | nano_banana_2_1 | 5 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:5 | 100% (medias) | 100% | 11.6 | 60% | 100% like,view | 0% | - |
| image | community | community_detail | seedream_v5_lite | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:4 | 25% (medias) | 100% | 6.8 | 0% | 100% like,view | 0% | - |
| image | community | community_detail | gpt_image_2_6_flare | 3 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:3 | 67% (medias) | 100% | 19.3 | 100% | 100% like,view | 0% | - |
| video | community | community_feed | Higgsfield Genjutsu | 12 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:12 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| video | community | community_feed | seedance_2_5 | 6 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:6,video:6 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | cost:1, media:1, model:1, hls:6, main:1, thumb:6 |
| video | community | community_feed | nano_banana_2_1 | 4 | 100% | 0% | 0% | 100% (hls:50%,main:100%,thumb:100%) | image:4,video:4 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | hls:2, thumb:4 |
| video | community | community_posts_list | seedance_2_5 | 18 | 100% | 0% | 0% | 100% (hls:78%,main:100%,min:11%,thumb:100%) | image:18,video:18 | 0% () | 100% | 0.0 | 78% | 100% comment,like,share,view | 0% | thumb:4 |
| video | community | community_posts_list | gpt_image_2_6 | 6 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:6,video:6 | 0% () | 100% | 0.0 | 100% | 100% comment,like,share,view | 0% | - |
| image | community | community_posts_list | soul_cinematic | 4 | 100% | 0% | 0% | 100% (main:100%,min:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,share,view | 0% | - |
| video | community | community_shots | hf_mult_motion_control | 8 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:8 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | nano_banana_2_1 | 6 | 100% | 0% | 0% | 100% (main:100%) | image:6 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_shots | hf_mult_replace_object | 6 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | video:6 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | text2image_soul_v2 | 4 | 100% | 0% | 0% | 100% (main:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | gpt_image_2_6 | 4 | 100% | 0% | 0% | 100% (main:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | soul_cinematic | 4 | 100% | 0% | 0% | 100% (main:100%) | image:4 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| image | community | community_shots | nano_banana_2 | 3 | 100% | 0% | 0% | 100% (main:100%) | image:3 | 0% () | 100% | 0.0 | 0% | 100% comment,like,view | 0% | - |
| video | community | community_talents | seedance_2_5 | 8 | 100% | 100% | 0% | 100% (hls:88%,main:88%,min:100%,raw:100%,thumb:100%) | image:7,video:8 | 100% (medias) | 100% | 20.0 | 12% | 100% comment,follower,like,view | 0% | cost:1, enh:1, input_urls:8, inputs:8, media:8, model:8, multi:5, prompt:8, settings_keys:8, status:8, hls:7, main:7, min:8, raw:8, thumb:8 |
| video | community | community_top | seedance_2_5 | 9 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:9 | 89% (medias) | 100% | 15.7 | 0% | 100% like,view | 0% | settings_keys:8 |
| image | community | community_top | gpt_image_2_6 | 8 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:8 | 88% (medias) | 100% | 11.4 | 100% | 100% like,view | 0% | - |
| image | community | community_trending | gpt_image_2_6 | 581 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:581 | 64% (medias) | 100% | 10.4 | 100% | 100% like,view | 0% | settings_keys:241 |
| image | community | community_trending | text2image_soul_v2 | 447 | 100% | 100% | 1% | 100% (main:100%,min:100%,raw:100%) | image:447 | 100% (custom_reference,medias,style) | 100% | 14.1 | 0% | 100% like,view | 0% | settings_keys:15 |
| image | community | community_trending | nano_banana_2 | 365 | 100% | 100% | 4% | 100% (min:100%,raw:100%) | image:365 | 89% (input_images,medias) | 100% | 7.2 | 0% | 100% like,view | 0% | input_urls:1, settings_keys:211, min:2, raw:2 |
| image | community | community_trending | soul_cinematic | 260 | 100% | 97% | 0% | 100% (main:100%,min:100%,raw:100%) | image:260 | 100% (camera_lens,camera_model,medias,style) | 100% | 10.1 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | nano_banana_2_1 | 212 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:212 | 89% (medias) | 100% | 10.7 | 42% | 100% like,view | 0% | settings_keys:131 |
| video | community | community_trending | magi_2 | 176 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:176 | 85% (medias) | 100% | 9.5 | 0% | 100% like,view | 0% | settings_keys:9 |
| video | community | community_trending | seedance_2_5 | 114 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:114 | 89% (medias) | 100% | 15.7 | 0% | 100% like,view | 0% | settings_keys:63 |
| image | community | community_trending | seedream_v5_pro | 111 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:111 | 86% (medias) | 100% | 11.3 | 0% | 100% like,view | 0% | settings_keys:71 |
| image | community | community_trending | z_image | 110 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:110 | 0% () | 100% | 4.0 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | seedream_v4_5 | 75 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:75 | 35% (input_images) | 100% | 7.7 | 0% | 100% like,view | 0% | settings_keys:15 |
| image | community | community_trending | gpt_image_2_6_flare | 58 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:58 | 74% (medias) | 100% | 20.2 | 100% | 100% like,view | 0% | settings_keys:28 |
| image | community | community_trending | flux_2 | 57 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:57 | 74% (input_images) | 100% | 10.4 | 0% | 100% like,view | 0% | settings_keys:12 |
| image | community | community_trending | gpt_image_2 | 56 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:56 | 79% (medias) | 100% | 9.5 | 100% | 100% like,view | 0% | settings_keys:25 |
| image | community | community_trending | seedream_v5_lite | 52 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:52 | 48% (medias) | 100% | 7.4 | 0% | 100% like,view | 0% | settings_keys:13 |
| image | community | community_trending | nano_banana_flash | 45 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:45 | 91% (medias) | 100% | 8.7 | 53% | 100% like,view | 0% | input_urls:1, settings_keys:32, min:1, raw:1 |
| image | community | community_trending | topaz_image | 43 | 100% | 0% | 0% | 100% (main:100%,min:100%,raw:100%) | image:43 | 100% (input_image) | 100% | 12.0 | 0% | 100% like,view | 7% | - |
| image | community | community_trending | text2image_soul | 30 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:30 | 100% (custom_reference,image_reference,style) | 100% | 15.1 | 0% | 100% like,view | 0% | settings_keys:3 |
| image | community | community_trending | gpt_image_2_5 | 29 | 100% | 93% | 0% | 100% (min:100%,raw:100%) | image:29 | 55% (medias) | 100% | 9.4 | 100% | 100% like,view | 0% | settings_keys:13 |
| image | community | community_trending | grok_image_2_0 | 20 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:20 | 10% (medias) | 100% | 7.3 | 100% | 100% like,view | 0% | - |
| image | community | community_trending | recraft_v4_1 | 19 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:19 | 0% () | 100% | 6.1 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | image_auto | 17 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:17 | 100% (medias) | 100% | 8.0 | 0% | 100% like,view | 0% | settings_keys:12 |
| image | community | community_trending | cinematic_studio_soul_location | 10 | 100% | 0% | 0% | 100% (main:100%,min:100%,raw:100%) | image:10 | 100% (camera_lens,camera_model,style) | 100% | 9.3 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | grok_image | 7 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:7 | 100% (medias) | 100% | 9.0 | 100% | 100% like,view | 0% | - |
| image | community | community_trending | nano_banana | 6 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:6 | 100% (input_images) | 100% | 9.0 | 0% | 100% like,view | 0% | settings_keys:6 |
| image | community | community_trending | 3d_jutsu_angles | 6 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:6 | 100% (medias) | 100% | 11.0 | 0% | 100% like,view | 0% | settings_keys:4 |
| image | community | community_trending | flux_3_image | 6 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:6 | 100% (medias) | 100% | 8.0 | 100% | 100% like,view | 0% | - |
| image | community | community_trending | ai_influencer | 5 | 100% | 0% | 0% | 100% (min:100%,raw:100%) | image:5 | 100% (media) | 100% | 8.0 | 0% | 100% like,view | 0% | - |
| video | community | community_trending | wan2_5_video | 4 | 100% | 100% | 100% | 100% (min:100%,raw:100%) | video:4 | 100% (input_image) | 100% | 11.0 | 0% | 100% like,view | 0% | settings_keys:1 |
| image | community | community_trending | topaz_image_generative | 4 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:4 | 100% (input_image) | 100% | 14.0 | 0% | 100% like,view | 0% | - |
| image | community | community_trending | outpaint | 3 | 100% | 0% | 0% | 100% (min:100%,raw:100%) | image:3 | 100% (medias) | 100% | 6.0 | 100% | 100% like,view | 0% | - |
| image | community | community_trending | text2keyframes | 3 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:3 | 0% () | 100% | 9.0 | 0% | 100% like,view | 0% | - |
| video | community | community_viral_presets | viral_hub_video | 42 | 100% | 0% | 0% | 100% (main:100%,thumb:100%) | image:42,video:42 | 5% (options) | 100% | 0.1 | 100% | 0% | 0% | input_urls:2, settings_keys:2, main:42, thumb:42 |
| video | projects | projects_folder_items | seedance_2_5 | 1611 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:1611 | 99% (medias) | 100% | 17.6 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | seedream_v5_pro | 1509 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:1509 | 88% (medias) | 100% | 10.7 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | gpt_image_2_6 | 319 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:319 | 96% (medias) | 100% | 11.1 | 100% | 100% comment | 0% | - |
| image | projects | projects_folder_items | nano_banana_2 | 313 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:313 | 91% (input_images,medias) | 100% | 6.8 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | seedream_5_5 | 223 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:223 | 82% (medias) | 100% | 9.4 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | topaz_video | 141 | 100% | 0% | 0% | 100% (min:100%,raw:100%,thumb:100%) | image:141,video:141 | 100% (input_video) | 100% | 12.5 | 0% | 100% comment | 23% | - |
| image | projects | projects_folder_items | gpt_image_2_5 | 98 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:98 | 93% (medias) | 100% | 10.1 | 100% | 100% comment | 0% | - |
| video | projects | projects_folder_items | seedance_2_5_flash | 76 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:76 | 100% (medias) | 100% | 16.1 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | nano_banana_2_1 | 69 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:69 | 68% (medias) | 100% | 11.1 | 100% | 100% comment | 0% | - |
| video | projects | projects_folder_items | seedance_2_0_mini | 64 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:64 | 100% (medias) | 100% | 13.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | magi_2 | 61 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:61 | 100% (medias) | 100% | 10.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | gpt_image_2_6_flare | 58 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:58 | 100% (medias) | 100% | 12.0 | 100% | 100% comment | 0% | - |
| image | projects | projects_folder_items | seedream_v4_5 | 58 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:58 | 48% (input_images) | 100% | 8.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | cinematic_studio_video_4_0 | 40 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:40 | 100% (camera_aperture,camera_lens,camera_model,era_control,genre_control,light,medias,) | 100% | 20.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | kling4_0 | 37 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:37 | 100% (medias) | 100% | 10.6 | 100% | 100% comment | 0% | - |
| image | projects | projects_folder_items | text2image_soul_v2 | 22 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | image:22 | 100% (custom_reference,image_reference,style) | 100% | 11.3 | 0% | 100% comment | 0% | - |
| audio | projects | projects_folder_items | seed_audio | 14 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | audio:14,other:14 | 43% (medias) | 100% | 9.3 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | kling3_0 | 13 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:13 | 100% (medias) | 100% | 13.4 | 100% | 100% comment | 0% | - |
| video | projects | projects_folder_items | hf_mult_replace_object | 11 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%,thumb:100%) | video:11 | 100% (medias) | 100% | 10.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | soul_cinematic | 10 | 100% | 50% | 0% | 100% (main:100%,min:100%,raw:100%) | image:10 | 100% (medias,style) | 100% | 10.4 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | gpt_image_2 | 9 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:9 | 56% (medias) | 100% | 8.7 | 100% | 100% comment | 0% | - |
| video | projects | projects_folder_items | hf_mult_replace_object_flash | 9 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%,thumb:100%) | video:9 | 100% (medias) | 100% | 10.0 | 100% | 100% comment | 0% | - |
| video | projects | projects_folder_items | gemini_omni_flash_1_2 | 9 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:9 | 44% (medias) | 100% | 9.3 | 100% | 100% comment | 0% | - |
| audio | projects | projects_folder_items | elevenlabs_music_v2_5 | 6 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | audio:6,other:6 | 0% () | 100% | 3.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | minimax_hailuo | 6 | 100% | 100% | 0% | 100% (main:100%,min:100%,raw:100%) | video:6 | 100% (input_image) | 100% | 8.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | kling_video_edit | 5 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:5 | 100% (input_videos,medias) | 100% | 7.2 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | ideogram_4_6_precise_edit | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:4 | 100% (medias) | 100% | 8.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | seedream_5_0_flash | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:4 | 100% (medias) | 100% | 9.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | flux_3_video_edit | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:4 | 100% (medias) | 100% | 7.0 | 0% | 100% comment | 0% | - |
| image | projects | projects_folder_items | cinematic_studio_soul_location | 4 | 100% | 0% | 0% | 100% (main:100%,min:100%,raw:100%) | image:4 | 100% (style) | 100% | 9.5 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | wan3_0_prime | 4 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:4 | 75% (medias) | 100% | 8.2 | 0% | 100% comment | 0% | - |
| video | projects | projects_folder_items | kling_o3_image_reference | 3 | 100% | 100% | 0% | 100% (min:100%,raw:100%,thumb:100%) | video:3 | 33% (medias) | 100% | 8.0 | 100% | 100% comment | 0% | - |
| image | projects | projects_folder_items | ideogram_4_5 | 3 | 100% | 100% | 0% | 100% (min:100%,raw:100%) | image:3 | 100% (medias) | 100% | 9.0 | 0% | 100% comment | 0% | - |
| video | projects | projects_user_publications | seedream_v5_pro | 3 | 100% | 0% | 0% | 100% (hls:100%,main:100%,thumb:100%) | image:3,video:3 | 0% () | 100% | 0.0 | 100% | 100% follower,like,view | 0% | - |
| video | showcase | showcase_effect_page | viral_hub_video | 1640 | 100% | 0% | 0% | 100% (hls:89%,main:95%,raw:89%,thumb:100%) | image:1356,video:1640 | 89% (input_image,input_media,input_video,main_url,media,medias,optimized_url,options,) | 100% | 12.7 | 25% | 0% | 0% | cost:403, input_urls:1431, settings_keys:1467, hls:3, main:110, raw:3, thumb:1606 |
| video | showcase | showcase_explore_feed | hf_mult_motion_control | 398 | 100% | 71% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:398 | 100% (image,input_assets) | 100% | 2.8 | 0% | 70% comment,like,view | 0% | multi:37, status:398 |
| video | showcase | showcase_explore_feed | hf_mult_replace_object | 120 | 100% | 86% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:120 | 100% (image,input_assets) | 100% | 1.8 | 0% | 58% comment,like,view | 0% | status:120 |
| video | showcase | showcase_explore_feed | hf_mult_replace_object_flash | 92 | 100% | 72% | 0% | 100% (hls:100%,main:100%,thumb:100%) | video:92 | 100% (image) | 100% | 3.0 | 0% | 100% comment,like,view | 0% | status:92 |

## 5. Per-product mapping

| product | `job_set_type`(s) seen | collected by (scraper / option → output table) | fields present | gaps |
|---|---|---|---|---|
| Community generation (image/video models) | `gpt_image_2_5/2_6/_flare`, `nano_banana_2/2_1`, `seedream_v4_5/v5_lite/v5_pro`, `flux_2`, `grok_image_2_0`, `magi_2`, `seedance_2_0/2_5`, `kling*`, `veo3*`, `wan*`, `topaz_*`, … | `community` feeds `trending,approved,top,model-x` (+`--detail`) → `generations` | prompt, neg prompt, `settings`, `params_extra`, `raw_params`, `inputs[]` (url, role, id), `results[]` (raw, min, result, thumbnail, hls/h264), engagement, timestamps, moderation, `upstream_usage`, creator (Clerk id) | none valuable; lineage / hls null in source |
| Soul / Cinematic studio | `text2image_soul_v2`, `soul_cinematic`, `cinematic_studio_*`, `text2keyframes` | same | + style / camera lens / camera model as inputs with roles | none |
| Viral preset (effects) | `viral_hub_video` | `community` approved feed; `showcase --what effect_examples` → `effect_samples`; preset in `catalog` → `viral_presets` (price matrix) | job, curated params, output video (+poster, hls), inputs | input role flattened; `raw_params` keys dropped (role, preset preview media, provider) |
| Chain presets / apps | `seedance_2_0(_fast)`, `kling3_0` (chain presets); app templates | `catalog --kinds chain_preset` → `chain_presets`; `site --what apps` → `apps` | preview media, credit price, model | apps index card `media_description`/`preview` partly (cap) |
| Creator / talent works | any (`seedance_2_*`, `gpt_image_*`, `nano_banana_*`, project cards) | `community --feeds creators,talents` → `creators`, `creator_stats` | profile stats only | **all work fields dropped**: `items[].item.{params.*, results.*, meta.cost, prompt, enhanced_prompt, reference_elements, gallery_media, cover, likes, views, comments, created_at, job_set_parent_id}` |
| Related projects | – | `projects --with-project-related` → `related` | link (ids, scope) | `cover`, `gallery_media[]` (url, original, preview, thumbnail, download, duration), `trailer`, `description`, `duration_seconds`, `tags` |
| Shots (Community "Shots") | any (`hf_mult_*`, `nano_banana_*`, …) | `community --feeds shots` → `shots` | media url + thumbnail, model, likes/views/comments | no prompt in source; `available_models` facet list only 28/168 kept (facet, low value) |
| Posts / Feed | posts carry jobs, shots, projects | `community --feeds posts,feed` → `posts`, `feed_items` | posts: text, media, card stats, counters | posts: card `like/views/comment_count`, `published_at`, `job_result.thumbnail_url`; feed: embedded post text + media, project card video |
| Project asset | all generation models + `media_input`, `video_input`, `audio_input`, `file_input` | `projects --with-project-assets` → `assets` (+ `folders`, `briefs`, `project_stats`, `stack_items`) | prompt (when `show_prompts`), full `params`, promoted settings, `input_media[]`, url/min/thumbnail/hls/h264/download/waveform, `variants[]`, `cost_raw`, comments_count, review_status, creator_key | folder `path` only; raw user ids re-keyed (intended) |
| Contest entry / submission | (project assets as above) | `projects --what contests --with-submissions [--contest <slug>] [--contest-tabs]` → `contests`, `submissions`, `listing_entries`, `publications` | rules, prizes, judges, winners, video/thumbnail, likes/views/comments/votes, social metrics, project link | `watched_percent` / `watch_completed` (viewer state, intended) |
| Original series / episodes | – | `site --what original-series` / `projects --public-series` | views, likes, media | not re-audited live |
| Explore (video explore, trends) | `hf_mult_motion_control(_flash)`, `hf_mult_replace_object(_flash)` | `showcase --what explore` → `explore_items`, `explore_variants` | prompt, media (main, hls, thumb), inputs, engagement | input `role`, `compressed_video` size/status |
| Reels | (preset videos) | `showcase --what reels` → `reels_presets` (+ comments) | prompt, character media, video, likes/views/comments | `recreates` |
| Editing Room | renders of `cinematic_video_*` | `showcase --what editing_room_examples` → `editing_room_examples/_projects/_renders` | prompts of renders, before/after video | take poster/preview/storyboard, timeline thumbnails |
| Intone | – | `showcase --what intone_examples` → `intone_examples` | title, video, thumbnail, audio | `compressed_video` url/width/height |
| Faceless / Seedance / Motion-control / Cinema controls / Canvas / Property studio | – | `showcase` → matching tables, `catalog` faceless presets | media + names | no prompt in source |
| MCP skills | – | `site --what mcp` → `mcp_skills`, `mcp_bundles` | prompts of example conversations, media | index-level fields beyond the cap |
| Account jobs (own) | own jobs | `account --with-jobs` → `account_jobs` | hashed ids, credits charged, model, settings; prompt only with `--with-prompts` | by design |

## 6. Contests: entries → projects → assets

- Contests listed by the API in the last full listing (`20261126-124820_contests-test`): `talent-contest`,
  `higgsfield-global-film-festival`, `higgsfield-seedance-2-contest`, `make-your-action-scene`,
  `wcc-the-fixed-frame`, `wcc-the-escape`, `wcc-without-a-word`, `wcc-the-whole-scene`, `wcc-the-place-you-know`,
  `wcc-impossible-camera`. (No `adathon` in that listing.) 303 submissions were scraped there; 225 carry a
  `publication_id` (a project), 78 are video-only submissions (`make-your-action-scene`) with no project, hence
  no prompts in the source.
- Nested completeness (projects with `--with-project-assets`): NEW talent-contest run 2 projects → 17 folders
  → 560 assets (404 video, 143 image, 8 audio, 4 file, 5 unknown); prompts visible on 541. OLD
  `nested-check` 5 projects → 102 folders → 4,745 assets, 3,835 with prompts; `nested-check-wcc2` 5 projects →
  675 assets. Every asset carries prompt (when the project shows prompts), model, full params, inputs, all media
  variants. `asset_count_mismatches` (API `count` vs items paged until `cursor: null`): −1 to −34 per project
  (0.1–4.6 %), **missing in source** (the listing ends), not a scraper loss.
- Entries tab coverage depends on `--max-submissions` / `--contest-tabs`; the live run fetched 2 entries by
  design.

## 7. User generations and creator keys

| scraper | raw Clerk ids | output keeps Clerk id | sha256('user/id')[:16] | sha256('creator/id')[:16] |
|---|---:|---:|---:|---:|
| catalog | 30 | 0 | 0 | 0 |
| community | 75 | 75 | 0 | 0 |
| projects | 2 | 0 | 2 | 0 |
| showcase | 8 | 0 | 0 | 8 |
| site | 0 | 0 | 0 | 0 |

OLD runs:

| scraper | raw Clerk ids | output keeps Clerk id | sha256('user/id')[:16] | sha256('creator/id')[:16] |
|---|---:|---:|---:|---:|
| account | 0 | 0 | 0 | 0 |
| blog | 19 | 19 | 0 | 0 |
| catalog | 100 | 0 | 0 | 0 |
| community | 2835 | 2818 | 0 | 0 |
| pricing | 0 | 0 | 0 | 0 |
| projects | 4362 | 0 | 4028 | 0 |
| showcase | 304 | 0 | 0 | 304 |
| site | 348 | 100 | 0 | 0 |

- `community`, `blog` and `site` (rooms) keep the **raw Clerk id** (`creator.user_id`, `author.user_id`); `projects` writes
  `author_key/owner_key/creator_key = sha256("user|<id>")[:16]`; `showcase` and the new `studios` write
  `creator_key/author_key = sha256("creator|<id>")[:16]`. One creator → three keys; joins across scrapers are only
  possible by re-hashing the Clerk id (which only community keeps).
- `catalog` (katana presets) has the author id in raw but writes no key at all.
- User projects (`projects --users <handle>`): handles are inputs only; the dataset keeps `key:<hash of handle>`.
  The handle itself remains in `manifest.json` args of that run (out of scope here; noted for the privacy owner).

## 8. Dropped raw fields

Counts by class — NEW: {'valuable': 160, 'unknown': 73, 'technical metadata': 95, 'intentional (ui/internal)': 44, 'intentional (personal)': 58}; OLD: {'valuable': 2295, 'unknown': 679, 'technical metadata': 352, 'intentional (ui/internal)': 608, 'intentional (personal)': 725}.

The tables below list `valuable` and `unknown` paths (sitemaps, OpenAPI docs, l10n string tables, JSON-LD and
pricing/blog text excluded as non-generation noise; the full list is in the script output). `present` = raw
records carrying a value, `kept` = how many of those values reached the output.

**Review of the valuable rows (NEW runs):**

| raw path (endpoint) | verdict |
|---|---|
| `publications[].content.medias[].card.{like_count,views_count,comment_count,published_at}` (community_posts_list) | **gap**: post-attached project card counters |
| `publications[].content.medias[].job_result.thumbnail_url` (community_posts_list) | **gap**: post media thumbnail |
| `items[].post.content.*`, `items[].card.video.*` (community_feed, also after re-normalize) | **gap**: Feed items keep only counters for `post` items and no video details for project cards |
| `variants[].input_assets[].role` (showcase_explore_feed), `job.raw_params.medias[].role` (showcase_effect_page) | **gap**: reference role flattened to `"input"` |
| `items[].video.compressed_video.{url,width,height}` (showcase_intone_explore) | **gap**: second video variant |
| `items[].project.take.{assets.poster.url, assets.preview.url, assets.storyboard.vtt_url, thumbnail_url}`, `timeline.versions[].thumbnail_url` (showcase_videoshop_project_examples) | **gap**: Editing Room media |
| `items[].recreates`, `listed.recreates` (showcase_reels_*) | **gap**: engagement counter |
| `.path` (projects_folder, projects_folder_children) | minor: folder path of ids (derivable from `parent_id`) |
| `loader.preset.*` (showcase_effect_page: `inputs[].binds_to`, `param_choices`, `price_matrix`, preview/widescreen media, description) | low: duplicated by `catalog_viral_presets` |
| `job.params.{provider, prompt.enhance, preset_meta.url}`, `job.raw_params.{chain_preset,preset}.preview_media.*`, `preset_preview.*`, `job.media.meta.aspect_ratio`, `job.is_reference` (showcase_effect_page) | low/medium: keep as `extra` / raw blob |
| `available_models[].model` (community_shots) | facet list, low |
| `items[].params.{cfg,steps,model}`, `meta.cost.{input_text,…}` (community_trending, 1 record) | false positive: record not emitted as a generation (cap), joined to its shot |
| `publication.views_count` (community_trending) | false positive: live counter changed between list and detail |
| `items[].media.{url,width,height}` (catalog_motions) | intended: placeholder media dropped unless `--keep-placeholders` |

**Review of the valuable rows (OLD runs, beyond the ones above):**

| raw path (endpoint) | verdict |
|---|---|
| `users[].items[].item.*` (community_creators 76 paths, community_talents 94 paths) | **gap, still in the current parser** (re-normalized): creator / talent works |
| `items[].{cover,gallery_media[],trailer,description,duration_seconds,tags}` (projects_related) | **gap**: related projects keep only the link |
| `items[].{background,portrait,landscape,logo}.optimized.url`, `episodes[].video.{shimmer,hls.job_id,original}` (projects_series_public) | minor gap: image/video variants |
| `publications[].stats.credits_spent`, `stack[].credits_spent` (projects_user_publications) | minor gap |
| `presets[].*` (community_viral_presets, an older community endpoint) | covered by `catalog_viral_presets` |
| `comments[].content` (community_comments, 10 of 22) | old output only: the early `login-comments` run wrote 0 comments; every later run and today's parser keep 100 % |
| `winners[].post_urls[]`, `items[].post_urls[]` (contests) | intended: social links kept only with `--with-profiles` |
| `detail[].input` (community_approved / trending) | noise: a 422 validation body from a model-filter probe |
| `account_benefits`, `account_job_costs`, `community_benefits`, pricing endpoints | out of scope here: the pricing tables reshape these (verified by the pricing identity checks); value matching cannot follow the reshaping |

### 8.1 NEW runs: valuable / unknown dropped paths

| class | scraper | endpoint | raw path | present | kept | sample |
|---|---|---|---|---|---|---|
| valuable | catalog | catalog_motions | `.items[].media.height` | 30 | 2 | 0 |
| valuable | catalog | catalog_motions | `.items[].media.url` | 30 | 2 | <placeholder> |
| valuable | catalog | catalog_motions | `.items[].media.width` | 30 | 2 | 0 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.comment_count` | 14 | 3 | 9 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.like_count` | 14 | 1 | 10 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.published_at` | 14 | 0 | 2026-11-24T01:34:46.829779Z |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.views_count` | 14 | 1 | 152 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].job_result.thumbnail_url` | 9 | 0 | https://cdn.higgsfield.ai/user_<redacted>/hf_20261111_194749_f10d21ba... |
| valuable | community | community_shots | `.available_models[].model` | 168 | 28 | 3d_jutsu_angles |
| valuable | community | community_trending | `.items[].meta.cost.{json}.input_image` | 1 | 0 | 0.0121 |
| valuable | community | community_trending | `.items[].meta.cost.{json}.input_text` | 1 | 0 | 0.0009 |
| valuable | community | community_trending | `.items[].meta.cost.{json}.output_image` | 1 | 0 | 0.0592 |
| valuable | community | community_trending | `.items[].meta.cost.{json}.output_text` | 1 | 0 | 0.0000 |
| valuable | community | community_trending | `.items[].params.cfg` | 1 | 0 | 5.0 |
| valuable | community | community_trending | `.items[].params.model` | 3 | 1 | aurora-img-alpha |
| valuable | community | community_trending | `.items[].params.steps` | 1 | 0 | 30 |
| valuable | community | community_trending | `.items[].publication.views_count` | 33 | 2 | 311 |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.is_reference` | 37 | 0 | False |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.media.meta.aspect_ratio` | 37 | 0 | 1280:960 |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.params.preset_meta.url` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/0d4cd007-10c1-4eaf-a9a0-28... |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.params.prompt.enhance` | 37 | 0 | False |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.params.provider` | 37 | 0 | unknown |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.raw_params.chain_preset.preview_media.main_url` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/0d4cd007-10c1-4eaf-a9a0-28... |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.raw_params.chain_preset.preview_media.optimized_url` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/dd4a5804-a7fe-4c1a-9f6e-91... |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.raw_params.medias.[].role` | 42 | 0 | start_image |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.raw_params.preset.preview_media.main_url` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/0d4cd007-10c1-4eaf-a9a0-28... |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.raw_params.preset.preview_media.optimized_url` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/dd4a5804-a7fe-4c1a-9f6e-91... |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].preset_preview.poster_url` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/dd4a5804-a7fe-4c1a-9f6e-91... |
| valuable | showcase | showcase_effect_page | `.loader.initial_samples.items[].preset_preview.source` | 37 | 0 | https://cdn.higgsfield.ai/viral_hub_preset/0d4cd007-10c1-4eaf-a9a0-28... |
| valuable | showcase | showcase_effect_page | `.loader.preset.description` | 4 | 0 | The surroundings break apart into floating cutout layers, revealing a... |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].binds_to.[].node` | 12 | 0 | bd65e60f-2cdd-4a43-8847-9fb4a7d0137c |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].binds_to.[].port` | 12 | 0 | input_images |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].binds_to.node` | 4 | 0 | bd65e60f-2cdd-4a43-8847-9fb4a7d0137c |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].binds_to.port` | 4 | 0 | user_prompt |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].id` | 10 | 0 | 091ceb3e-d27f-4a8e-9210-22ff9242c9af_input_images |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].label` | 10 | 2 | Upload image |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].max` | 6 | 0 | 1 |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].media_input_id` | 4 | 0 | b639d8a7-f724-4670-8d21-f9801bf617cb |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].min` | 6 | 0 | 1 |
| valuable | showcase | showcase_effect_page | `.loader.preset.inputs.[].required` | 6 | 0 | True |
| valuable | showcase | showcase_effect_page | `.loader.preset.ip_check_required` | 4 | 0 | False |
| valuable | showcase | showcase_effect_page | `.loader.preset.is_main_page` | 4 | 0 | True |
| valuable | showcase | showcase_effect_page | `.loader.preset.param_choices.{id}.aspect_ratio.choices.[]` | 28 | 0 | auto |
| valuable | showcase | showcase_effect_page | `.loader.preset.param_choices.{id}.aspect_ratio.default` | 4 | 0 | 9:16 |
| valuable | showcase | showcase_effect_page | `.loader.preset.param_choices.{id}.resolution.choices.[]` | 14 | 0 | 480p |
| valuable | showcase | showcase_effect_page | `.loader.preset.param_choices.{id}.resolution.default` | 4 | 0 | 720p |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.duration_ms` | 4 | 0 | 8103 |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.height` | 4 | 0 | 450 |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.main_url` | 4 | 0 | https://cdn.higgsfield.ai/viral_hub/50e19d6b-c8ff-48e5-8b13-afed804f0... |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.optimized_url` | 4 | 0 | https://cdn.higgsfield.ai/viral_hub/c6447d94-7c69-4bc5-81cf-7dfeea1be... |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.thumbnail_url` | 4 | 0 | https://cdn.higgsfield.ai/viral_hub/b5c90864-c3c5-4b14-87a0-3739250fd... |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.url` | 4 | 0 | https://cdn.higgsfield.ai/viral_hub/a64711ac-93b8-46ee-a9ce-37ee5c18e... |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_media.width` | 4 | 0 | 600 |
| valuable | showcase | showcase_effect_page | `.loader.preset.preview_url` | 4 | 0 | https://cdn.higgsfield.ai/viral_hub/a64711ac-93b8-46ee-a9ce-37ee5c18e... |
| valuable | showcase | showcase_effect_page | `.loader.preset.price_matrix.[].credit_units` | 102 | 0 | 3600 |
| valuable | showcase | showcase_effect_page | `.loader.preset.price_matrix.[].key` | 98 | 0 | 06107d72-f5ac-4c2a-84a1-513d3565c1cd.aspect_ratio=16:9,06107d72-f5ac-... |
| valuable | showcase | showcase_effect_page | `.loader.preset.priority` | 4 | 0 | 3 |
| valuable | showcase | showcase_effect_page | `.loader.preset.thumbnail_url` | 4 | 0 | https://cdn.higgsfield.ai/viral_hub/b5c90864-c3c5-4b14-87a0-3739250fd... |
| valuable | showcase | showcase_effect_page | `.loader.preset.widescreen_media.height` | 3 | 0 | 450 |
| valuable | showcase | showcase_effect_page | `.loader.preset.widescreen_media.thumbnail_url` | 3 | 0 | https://cdn.higgsfield.ai/viral_hub/f6d0c23c-24c5-4765-bad9-c162cd662... |
| valuable | showcase | showcase_effect_page | `.loader.preset.widescreen_media.url` | 3 | 0 | https://cdn.higgsfield.ai/viral_hub/ba9aed65-528d-4ed3-a193-0a3ca9b30... |
| valuable | showcase | showcase_effect_page | `.loader.preset.widescreen_media.width` | 3 | 0 | 600 |
| valuable | showcase | showcase_explore_feed | `.items[].variants.[].input_assets.[].role` | 20 | 0 | image |
| valuable | showcase | showcase_intone_explore | `.items[].video.compressed_video.height` | 18 | 0 | 338 |
| valuable | showcase | showcase_intone_explore | `.items[].video.compressed_video.url` | 18 | 0 | https://static-public-media.higgsfield.ai/intone-explore-presets/6665... |
| valuable | showcase | showcase_intone_explore | `.items[].video.compressed_video.width` | 18 | 0 | 600 |
| valuable | showcase | showcase_videoshop_project_examples | `.items[].project.take.assets.poster.url` | 6 | 0 | https://cdn.higgsfield.ai/2552d9f4-8122-4050-b067-6cafc70c4a20_thumb.... |
| valuable | showcase | showcase_videoshop_project_examples | `.items[].project.take.assets.preview.url` | 6 | 0 | https://cdn.higgsfield.ai/videoshop/take/2552d9f4-8122-4050-b067-6caf... |
| valuable | showcase | showcase_videoshop_project_examples | `.items[].project.take.assets.storyboard.vtt_url` | 6 | 0 | https://cdn.higgsfield.ai/storyboard/cc8643e0-0846-49c0-8c48-a58db379... |
| valuable | showcase | showcase_videoshop_project_examples | `.items[].project.take.thumbnail_url` | 6 | 0 | https://cdn.higgsfield.ai/2552d9f4-8122-4050-b067-6cafc70c4a20_thumb.... |
| valuable | showcase | showcase_videoshop_project_examples | `.items[].timeline.versions.[].spec_key.{json}.[]` | 220 | 45 | relight |
| valuable | showcase | showcase_videoshop_project_examples | `.items[].timeline.versions.[].thumbnail_url` | 41 | 0 | https://cdn.higgsfield.ai/user_<redacted>/hf_20261119_111610_f58010df... |
| valuable | site | app_page | `.matches[].l.app_preset.image_template.cost` | 18 | 0 | 1 |
| valuable | site | app_page | `.matches[].l.app_preset.image_template.inputs.[].id` | 22 | 0 | input_image |
| valuable | site | app_page | `.matches[].l.app_preset.image_template.inputs.[].properties.hint` | 9 | 0 | Photo with face to replace. |
| valuable | site | app_page | `.matches[].l.app_preset.image_template.inputs.[].properties.max` | 1 | 0 | 3 |
| valuable | site | app_page | `.matches[].l.app_preset.image_template.inputs.[].properties.min` | 1 | 0 | 1 |
| valuable | site | app_page | `.matches[].l.app_preset.image_template.inputs.[].properties.optional` | 1 | 0 | False |
| valuable | site | app_page | `.matches[].l.app_preset.video_template.cost` | 8 | 0 | 6 |
| valuable | site | app_page | `.matches[].l.app_preset.video_template.inputs.[].id` | 6 | 0 | 019ac678-3cde-7145-9e33-423b2c75dff8 |
| valuable | site | app_page | `.matches[].l.app_preset.video_template.inputs.[].properties.hint` | 2 | 0 | Photo with face to replace. |
| valuable | site | app_page | `.matches[].l.app_preset.video_template.inputs.[].properties.max` | 1 | 0 | 3 |
| valuable | site | app_page | `.matches[].l.app_preset.video_template.inputs.[].properties.min` | 1 | 0 | 1 |
| valuable | site | app_page | `.matches[].l.secondary_app_preset.description` | 2 | 0 | Instantly swap faces in your footage. A powerful tool designed for vi... |
| valuable | site | app_page | `.matches[].l.secondary_app_preset.input_media.height` | 2 | 0 | 1480 |
| valuable | site | app_page | `.matches[].l.secondary_app_preset.input_media.source` | 2 | 0 | https://cdn.higgsfield.ai/card/75469997-be40-4ab6-b38d-fc325fd2b336.w... |
| valuable | site | app_page | `.matches[].l.secondary_app_preset.media_description` | 2 | 0 | Instantly swap faces in your footage. A powerful tool designed for vi... |
| valuable | site | app_page | `.matches[].l.secondary_app_preset.video_template.cost` | 2 | 0 | 25 |
| valuable | site | apps_index | `.matches[].l.active_category` | 1 | 0 | all |
| valuable | site | apps_index | `.matches[].l.categories.[].apps.[].media_description` | 84 | 23 | Predict how viral your video hook is before you post |
| valuable | site | apps_index | `.matches[].l.categories.[].apps.[].preview.source` | 84 | 30 | https://cdn.higgsfield.ai/application_main/1b47c261-e40d-4aad-8ef7-5e... |
| valuable | site | apps_index | `.matches[].l.categories.[].apps.[].preview.thumbnail` | 81 | 29 | https://cdn.higgsfield.ai/application_main/07eaf8dd-f9fd-474e-b33c-2f... |
| valuable | site | apps_index | `.matches[].l.categories.[].apps.[].tags.[].text` | 8 | 1 | Pro |
| valuable | site | mcp_bundle_page | `.matches[].l.settings.default_agent` | 3 | 0 | chatgpt |
| valuable | site | mcp_bundle_page | `.matches[].l.settings.id` | 3 | 0 | hub-settings |
| valuable | site | mcp_index | `.matches[].l.items.[].card_title` | 57 | 23 | Short Drama |
| valuable | site | mcp_index | `.matches[].l.items.[].conversation_media.download_url` | 1 | 0 | https://cdn.higgsfield.ai/gpt-skills/downloads/984803b3-e827-4f6c-a8f... |
| valuable | site | mcp_index | `.matches[].l.items.[].conversation_media.poster_url` | 75 | 35 | https://static.higgsfield.ai/short-drama-intro/hero/Grandson%20-1-pos... |
| valuable | site | mcp_index | `.matches[].l.items.[].conversation_media.url` | 75 | 35 | https://static.higgsfield.ai/short-drama-intro/hero/Grandson%20-1.mp4 |
| valuable | site | mcp_index | `.matches[].l.items.[].cover_media.poster_url` | 75 | 35 | https://static.higgsfield.ai/landing/gpt-skills/demos/short-drama-202... |
| valuable | site | mcp_index | `.matches[].l.items.[].cover_media.url` | 75 | 35 | https://static.higgsfield.ai/landing/gpt-skills/demos/short-drama-202... |
| valuable | site | mcp_index | `.matches[].l.items.[].description` | 75 | 35 | Turn your script into a series worth bingeing. Build your cast, shape... |
| valuable | site | mcp_index | `.matches[].l.items.[].external_url` | 36 | 9 | https://higgsfield.ai/short-drama |
| valuable | site | mcp_index | `.matches[].l.items.[].main_conversation.result.media.download_url` | 1 | 0 | https://cdn.higgsfield.ai/gpt-skills/downloads/984803b3-e827-4f6c-a8f... |
| valuable | site | mcp_index | `.matches[].l.items.[].main_conversation.result.media.title` | 2 | 0 | Bloodline Secrets · Episode 1 |
| valuable | site | mcp_index | `.matches[].l.items.[].short_description` | 75 | 35 | Turn your script into a series worth bingeing. Build your cast, shape... |
| valuable | site | mcp_index | `.matches[].l.items.[].tags.[].name` | 184 | 84 | (not shown) |
| valuable | site | mcp_index | `.matches[].l.items.[].title` | 75 | 35 | Short Drama |
| valuable | site | mcp_index | `.matches[].l.settings.default_agent` | 1 | 0 | chatgpt |
| valuable | site | mcp_index | `.matches[].l.settings.id` | 1 | 0 | hub-settings |
| valuable | site | mcp_skill_page | `.matches[].l.settings.default_agent` | 30 | 0 | chatgpt |
| valuable | site | mcp_skill_page | `.matches[].l.settings.id` | 30 | 0 | hub-settings |
| valuable | site | mcp_skill_page | `.matches[].l.skill.conversation_media.download_url` | 1 | 0 | https://cdn.higgsfield.ai/gpt-skills/downloads/984803b3-e827-4f6c-a8f... |
| valuable | site | mcp_skill_page | `.matches[].l.skill.main_conversation.result.media.download_url` | 1 | 0 | https://cdn.higgsfield.ai/gpt-skills/downloads/984803b3-e827-4f6c-a8f... |
| valuable | site | mcp_skill_page | `.matches[].l.skill.main_conversation.result.media.title` | 2 | 0 | Monster in the City Alley |
| unknown | catalog | catalog_chain_presets | `.[].collaborate` | 13 | 0 | (not shown) |
| unknown | community | community_posts_list | `.publications[].is_mine` | 30 | 0 | False |
| unknown | community | community_posts_list | `.publications[].is_subscribed` | 30 | 0 | False |
| unknown | projects | projects_folder | `.path` | 2 | 0 | /8e53b041-7ed1-4df6-b5f1-05b88169328b/ |
| unknown | projects | projects_folder | `.publication.has_changes_since_publish` | 2 | 0 | True |
| unknown | projects | projects_folder | `.workspace.name` | 1 | 0 | (not shown) |
| unknown | projects | projects_folder_children | `.items[].path` | 15 | 0 | /8e53b041-7ed1-4df6-b5f1-05b88169328b/adbdf84e-ba9c-45bd-a4b7-7f760d7... |
| unknown | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.asset_type_layer` | 37 | 0 | Video |
| unknown | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.can_upgrade_to4k` | 14 | 0 | False |
| unknown | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.client_meta.source` | 37 | 0 | viral_hub_web |
| unknown | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.ip_check_finished` | 37 | 0 | True |
| unknown | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.ip_detected` | 37 | 0 | False |
| unknown | showcase | showcase_effect_page | `.loader.initial_samples.items[].job.stage` | 37 | 0 | complete |
| unknown | showcase | showcase_motion_control_presets | `.[].name` | 30 | 2 | (not shown) |
| unknown | showcase | showcase_reels_preset_detail | `.listed.recreates` | 60 | 0 | 270 |
| unknown | showcase | showcase_reels_presets | `.items[].recreates` | 60 | 0 | 0 |
| unknown | showcase | showcase_videoshop_project_examples | `.items[].project.take.filename` | 6 | 0 | (not shown) |
| unknown | site | apps_index | `.matches[].l.categories.[].apps.[].id` | 84 | 30 | 525798b3-6776-4b3a-9b8f-667d8ab1b06c |
| unknown | site | apps_index | `.matches[].l.categories.[].apps.[].name.[]` | 84 | 30 | Virality Predictor |
| unknown | site | mcp_index | `.matches[].l.items.[].cover_alt` | 75 | 35 | Short Drama preview with fantasy action and dramatic reactions |
| unknown | site | mcp_index | `.matches[].l.items.[].id` | 75 | 34 | 749ee480-e8d8-43af-af14-edd783eee0d6 |
| unknown | site | mcp_index | `.matches[].l.items.[].source_id` | 46 | 12 | katana |
| unknown | site | mcp_index | `.matches[].l.locale` | 1 | 0 | en |

### 8.2 OLD runs: valuable / unknown dropped paths

| class | scraper | endpoint | raw path | present | kept | sample |
|---|---|---|---|---|---|---|
| valuable | community | community_comments | `.comments[].content` | 22 | 10 | THANKS |
| valuable | community | community_comments | `.comments[].is_mine` | 22 | 0 | False |
| valuable | community | community_feed | `.items[].card.video.duration` | 12 | 0 | 449.375 |
| valuable | community | community_feed | `.items[].card.video.height` | 12 | 0 | 2160 |
| valuable | community | community_feed | `.items[].card.video.hls_url` | 10 | 0 | https://cdn.higgsfield.ai/hls/video_input/d85e04fb-59f9-4465-8439-5d4... |
| valuable | community | community_feed | `.items[].card.video.preview_url` | 12 | 0 | https://cdn.higgsfield.ai/card_preview/video_input/d85e04fb-59f9-4465... |
| valuable | community | community_feed | `.items[].card.video.width` | 12 | 0 | 3840 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.comment_count` | 2 | 0 | 12 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.cover_url` | 2 | 0 | https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/9150a500-7809-4... |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.description` | 2 | 0 | In the Kowloon Walled City of Hong Kong, shrouded in the darkness of ... |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.id` | 2 | 0 | 6a6f9d36-3a80-4836-baff-54bcecb813af |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.like_count` | 2 | 0 | 7 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.published_at` | 2 | 0 | 2026-09-16T17:06:25.497641Z |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.slug` | 2 | 0 | a-night-called-you |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.stats.credits_spent` | 2 | 0 | 10576.5 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.stats.generations_count` | 2 | 0 | 918 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.stats.stack.[].count` | 20 | 0 | 320 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.stats.stack.[].credits_spent` | 20 | 0 | 0 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.title` | 2 | 0 | A Night Called You |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.video.duration` | 2 | 0 | 17.812999725341797 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.video.height` | 2 | 0 | 608 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.video.thumbnail_url` | 2 | 0 | https://cdn.higgsfield.ai/2f09f3ae-b804-4fdf-a920-73d023bf5c50.webp |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.video.url` | 2 | 0 | https://cdn.higgsfield.ai/1f61871b-1431-4d7d-9881-ab3319a2c66a.mp4 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.video.width` | 2 | 0 | 1080 |
| valuable | community | community_feed | `.items[].post.content.medias.[].card.views_count` | 2 | 0 | 312 |
| valuable | community | community_feed | `.items[].post.content.medias.[].height` | 8 | 0 | 1536 |
| valuable | community | community_feed | `.items[].post.content.medias.[].job_id` | 8 | 0 | 60239804-ffbb-4c77-a455-91d81f8659f2 |
| valuable | community | community_feed | `.items[].post.content.medias.[].job_result.thumbnail_url` | 2 | 0 | https://cdn.higgsfield.ai/user_<redacted>/hf_20261021_230053_71cde52e... |
| valuable | community | community_feed | `.items[].post.content.medias.[].job_result.url` | 8 | 0 | https://d8j0ntlcm91z4.cloudfront.net/user_<redacted>/hf_20261114_1455... |
| valuable | community | community_feed | `.items[].post.content.medias.[].job_type` | 8 | 0 | image |
| valuable | community | community_feed | `.items[].post.content.medias.[].made_with.tool` | 8 | 2 | image |
| valuable | community | community_feed | `.items[].post.content.medias.[].min_result.thumbnail_url` | 2 | 0 | https://cdn.higgsfield.ai/user_<redacted>/hf_20261021_230053_71cde52e... |
| valuable | community | community_feed | `.items[].post.content.medias.[].min_result.url` | 8 | 0 | https://cdn.higgsfield.ai/7b515a55-9459-4d48-a573-cda625eed6e5.webp |
| valuable | community | community_feed | `.items[].post.content.medias.[].project_publication_id` | 2 | 0 | 6a6f9d36-3a80-4836-baff-54bcecb813af |
| valuable | community | community_feed | `.items[].post.content.medias.[].share_link` | 8 | 0 | 8aFjZUBVr0Q |
| valuable | community | community_feed | `.items[].post.content.medias.[].shot_id` | 2 | 0 | 55486f5d-b624-4681-b019-41f9dd065b52 |
| valuable | community | community_feed | `.items[].post.content.medias.[].video.duration` | 2 | 0 | 17.812999725341797 |
| valuable | community | community_feed | `.items[].post.content.medias.[].video.height` | 2 | 0 | 608 |
| valuable | community | community_feed | `.items[].post.content.medias.[].video.thumbnail_url` | 2 | 0 | https://cdn.higgsfield.ai/2f09f3ae-b804-4fdf-a920-73d023bf5c50.webp |
| valuable | community | community_feed | `.items[].post.content.medias.[].video.url` | 2 | 0 | https://cdn.higgsfield.ai/1f61871b-1431-4d7d-9881-ab3319a2c66a.mp4 |
| valuable | community | community_feed | `.items[].post.content.medias.[].video.width` | 2 | 0 | 1080 |
| valuable | community | community_feed | `.items[].post.content.medias.[].width` | 8 | 0 | 2720 |
| valuable | community | community_feed | `.items[].post.dislike_count` | 6 | 2 | 0 |
| valuable | community | community_feed | `.items[].room.cover_url` | 4 | 0 | https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/c33ebd0d-3819-4... |
| valuable | community | community_music_card_options | `.items[].thumbnail_media.height` | 35 | 0 | 578 |
| valuable | community | community_music_card_options | `.items[].thumbnail_media.width` | 35 | 0 | 578 |
| valuable | community | community_posts | `.publications[].comment_count` | 4 | 0 | 4 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.comment_count` | 4 | 0 | 9 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.cover_url` | 4 | 0 | https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/be2c0bd2-f190-4... |
| valuable | community | community_posts | `.publications[].content.medias.[].card.description` | 4 | 0 | Jabari, a boy from a forgotten village, plays toward a dream stitched... |
| valuable | community | community_posts | `.publications[].content.medias.[].card.id` | 4 | 0 | 5d47d0dd-09f9-480f-90af-7bc9383b4fb6 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.like_count` | 4 | 0 | 10 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.published_at` | 4 | 0 | 2026-11-24T01:34:46.829779Z |
| valuable | community | community_posts | `.publications[].content.medias.[].card.slug` | 4 | 0 | the-patched-ball |
| valuable | community | community_posts | `.publications[].content.medias.[].card.stats.credits_spent` | 4 | 0 | 4101.25 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.stats.free_generations` | 4 | 0 | 0 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.stats.generations_count` | 4 | 0 | 241 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.stats.stack.[].count` | 24 | 2 | 85 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.stats.stack.[].credits_spent` | 24 | 0 | 39.5 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.stats.stack.[].job_set_type` | 24 | 0 | gpt_image_2_6 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.title` | 4 | 0 | THE PATCHED BALL |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.duration` | 4 | 0 | 289.941 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.height` | 4 | 0 | 1080 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.hls_url` | 4 | 0 | https://cdn.higgsfield.ai/hls/video_input_watermarked/262faab3-ab24-4... |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.preview_url` | 4 | 0 | https://cdn.higgsfield.ai/card_preview/video_input/262faab3-ab24-4383... |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.thumbnail_url` | 4 | 0 | https://cdn.higgsfield.ai/hls/video_input_watermarked/262faab3-ab24-4... |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.url` | 4 | 0 | https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/262faab3-ab24-4... |
| valuable | community | community_posts | `.publications[].content.medias.[].card.video.width` | 4 | 0 | 1920 |
| valuable | community | community_posts | `.publications[].content.medias.[].card.views_count` | 4 | 0 | 149 |
| valuable | community | community_posts | `.publications[].content.medias.[].project_publication_id` | 4 | 0 | 5d47d0dd-09f9-480f-90af-7bc9383b4fb6 |
| valuable | community | community_posts | `.publications[].created_at` | 4 | 0 | 2026-11-24T01:47:36.093104Z |
| valuable | community | community_posts | `.publications[].like_count` | 4 | 0 | 3 |
| valuable | community | community_posts | `.publications[].views_count` | 4 | 0 | 1871 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.comment_count` | 22 | 4 | 9 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.like_count` | 22 | 0 | 10 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.published_at` | 22 | 0 | 2026-11-24T01:34:46.829779Z |
| valuable | community | community_posts_list | `.publications[].content.medias.[].card.views_count` | 22 | 0 | 151 |
| valuable | community | community_posts_list | `.publications[].content.medias.[].job_result.thumbnail_url` | 8 | 0 | https://cdn.higgsfield.ai/user_<redacted>/hf_20261111_194749_f10d21ba... |
| valuable | community | community_shots | `.available_models[].model` | 336 | 54 | 3d_jutsu_angles |
| valuable | projects | projects_contest_detail | `.winners.[].post_urls.[]` | 300 | 36 | https://www.instagram.com/reel/DVMMj6ykRbu/?igsh=a2t6dzNwM21wNThi |
| valuable | projects | projects_contest_submissions | `.items[].post_urls.[]` | 1404 | 77 | https://x.com/GarryKoesoema/status/2028013473972818064 |
| valuable | projects | projects_related | `.items[].cover.height` | 300 | 0 | 1152 |
| valuable | projects | projects_related | `.items[].cover.width` | 300 | 0 | 2048 |
| valuable | projects | projects_related | `.items[].created_at` | 300 | 1 | 2026-11-19T19:35:00.052560Z |
| valuable | projects | projects_related | `.items[].description` | 300 | 3 | Where do cats go when they leave us?  We asked the people who loved t... |
| valuable | projects | projects_related | `.items[].duration_seconds` | 300 | 0 | 314.6 |
| valuable | projects | projects_related | `.items[].gallery_media.[].download_url` | 239 | 0 | https://cdn.higgsfield.ai/hls/video_input_watermarked/8839cd56-5f6e-4... |
| valuable | projects | projects_related | `.items[].gallery_media.[].duration` | 307 | 0 | 314.6 |
| valuable | projects | projects_related | `.items[].gallery_media.[].height` | 307 | 0 | 1080 |
| valuable | projects | projects_related | `.items[].gallery_media.[].id` | 307 | 0 | 8839cd56-5f6e-45a9-8f9f-88047e6d1fec |
| valuable | projects | projects_related | `.items[].gallery_media.[].name` | 81 | 0 | (not shown) |
| valuable | projects | projects_related | `.items[].gallery_media.[].original_url` | 302 | 0 | https://d2ol7oe51mr4n9.cloudfront.net/user_<redacted>/8839cd56-5f6e-4... |
| valuable | projects | projects_related | `.items[].gallery_media.[].preview_url` | 233 | 0 | https://cdn.higgsfield.ai/card_preview/video_input/8839cd56-5f6e-45a9... |
| valuable | projects | projects_related | `.items[].gallery_media.[].thumbnail_url` | 265 | 0 | https://cdn.higgsfield.ai/hls/video_input_watermarked/8839cd56-5f6e-4... |
| valuable | projects | projects_related | `.items[].gallery_media.[].url` | 307 | 0 | https://cdn.higgsfield.ai/hls/video_input_watermarked/8839cd56-5f6e-4... |
| valuable | projects | projects_related | `.items[].gallery_media.[].width` | 307 | 0 | 1920 |
| valuable | projects | projects_related | `.items[].show_prompts` | 300 | 0 | True |
| valuable | projects | projects_related | `.items[].tags.[]` | 8 | 0 | animation |
| valuable | projects | projects_related | `.items[].team.followers_count` | 7 | 0 | 696 |
| valuable | projects | projects_related | `.items[].trailer.duration` | 7 | 0 | 17.002 |
| valuable | projects | projects_related | `.items[].trailer.height` | 7 | 0 | 608 |
| valuable | projects | projects_related | `.items[].trailer.thumbnail_url` | 7 | 0 | https://cdn.higgsfield.ai/5a59272f-da87-4631-ae7f-5f37a3583530.webp |
| valuable | projects | projects_related | `.items[].trailer.url` | 7 | 0 | https://cdn.higgsfield.ai/1dd1302b-bb91-41b9-9be2-81c19d59455e.mp4 |
| valuable | projects | projects_related | `.items[].trailer.width` | 7 | 0 | 1080 |
| valuable | projects | projects_series_public | `.items[].background.optimized.url` | 6 | 0 | https://du4zrvwy3vtek.cloudfront.net/series/0d9d7a26-233a-40b5-bce3-6... |
| valuable | projects | projects_series_public | `.items[].background_url` | 6 | 0 | https://du4zrvwy3vtek.cloudfront.net/series/0d9d7a26-233a-40b5-bce3-6... |
| valuable | projects | projects_series_public | `.items[].episodes.[].thumbnail.optimized.url` | 6 | 0 | https://du4zrvwy3vtek.cloudfront.net/episode/40094aaf-a634-43b7-b399-... |
| valuable | projects | projects_series_public | `.items[].episodes.[].video.hls.job_id` | 18 | 0 | 1776718578952-y1jg3n |
| valuable | projects | projects_series_public | `.items[].episodes.[].video.original.height` | 18 | 0 | 1440 |
| valuable | projects | projects_series_public | `.items[].episodes.[].video.original.width` | 18 | 0 | 2560 |
| valuable | projects | projects_series_public | `.items[].episodes.[].video.shimmer.height` | 12 | 0 | 1080 |
| valuable | projects | projects_series_public | `.items[].episodes.[].video.shimmer.url` | 12 | 0 | https://du4zrvwy3vtek.cloudfront.net/episode/46f5150c-9437-4505-90a0-... |
| valuable | projects | projects_series_public | `.items[].episodes.[].video.shimmer.width` | 12 | 0 | 1920 |
| valuable | projects | projects_series_public | `.items[].landscape.optimized.url` | 8 | 0 | https://du4zrvwy3vtek.cloudfront.net/series/0d9d7a26-233a-40b5-bce3-6... |
| valuable | projects | projects_series_public | `.items[].logo.optimized.url` | 6 | 0 | https://du4zrvwy3vtek.cloudfront.net/series/c64a2b5f-1a91-4734-8850-e... |
| valuable | projects | projects_series_public | `.items[].logo_url` | 8 | 2 | https://du4zrvwy3vtek.cloudfront.net/series/0d9d7a26-233a-40b5-bce3-6... |
| valuable | projects | projects_series_public | `.items[].portrait.optimized.url` | 18 | 0 | https://du4zrvwy3vtek.cloudfront.net/series/0d9d7a26-233a-40b5-bce3-6... |
| valuable | projects | projects_series_public | `.items[].portrait_url` | 20 | 2 | https://du4zrvwy3vtek.cloudfront.net/series/0d9d7a26-233a-40b5-bce3-6... |
| valuable | projects | projects_series_public | `.items[].trailer.original.height` | 18 | 0 | 1716 |
| valuable | projects | projects_series_public | `.items[].trailer.original.width` | 18 | 0 | 4096 |
| valuable | projects | projects_user_publications | `.publications[].stats.credits_spent` | 3 | 0 | 506400 |
| valuable | projects | projects_user_publications | `.publications[].stats.stack.[].credits_spent` | 21 | 6 | 0 |

## 9. End-to-end examples (raw → output, every leaf)

Full tables (generated by the mapping helper used for this audit, user ids redacted):

- Seedance 2.5 community video — [`e2e_seedance_2_5_community.md`](../samples/higgsfield/completeness/e2e_seedance_2_5_community.md)
  (run `20261126-113330_pe-seedance-2-5`, `community_trending` → `generations.json`)
- GPT Image 2.6 community image — [`e2e_gpt_image_2_6_community.md`](../samples/higgsfield/completeness/e2e_gpt_image_2_6_community.md)
  (run `20261126-154810_completeness-community`, `community_detail` → `generations.json`)
- Seedance 2.5 project asset — [`e2e_seedance_2_5_project_asset.md`](../samples/higgsfield/completeness/e2e_seedance_2_5_project_asset.md)
  (run `20261126-154921_completeness-projects`, `projects_folder_items` → `assets.json`)

Seedance 2.5 community video, condensed:

| raw | output |
|---|---|
| `job_set_type`, `job_set_id`, `id` | `job_set_type` + `model_id`, `job_set_id`, `generation_id` |
| `params.prompt` | `prompt` (+ `raw_params.prompt`) |
| `params.{width,height,duration,resolution,aspect_ratio,generate_audio,multi_shots,multi_shot_mode,speedramp,prompt_language,model,bitrate_mode,draft,genre}` | `settings.*` (+ `raw_params.*`) |
| `params.medias[].{data.id,data.url,data.type,role}` | `inputs[].{id,url,type,role}` (+ `raw_params.medias`) |
| `results.{raw,min}.{type,url,thumbnail_url}` | `results[].{name,type,url,thumbnail_url}`, `media_type` |
| `created_at`, `published_at` (epoch) | `created_at`, `published_at` (ISO UTC) |
| `publication.{id,views_count,likes_count,approved}` | `publication_id`, `engagement.{views,likes,approved}` |
| `status`, `ip_*`, `deepfake_consent_required`, `can_upgrade_to_4k` | `status`, `moderation.*`, `can_upgrade_to_4k` |
| `user_id` | `creator.user_id` (Clerk id) |
| `profile.username`, `profile.avatar_url` | dropped (privacy) |

GPT Image 2.6 adds `meta.cost` (JSON string) → `upstream_usage.{request_id, input_text_tokens, input_image_tokens,
cached_*, output_*}` and `params.{quality,background,output_format,remove_bg}` → `settings.*`. The project asset maps
`job.params` → `params` (whole) + promoted `aspect_ratio/resolution/duration_seconds/seed/width/height`,
`job.results` → `url`/`min_url`/`thumbnail_url`/`variants[]`, `job.params.medias` → `input_media[]`,
`job.upgrade_options`/`expires_at`/`cluster_hash`/`ip_*`/`workspace_id` → `extra.*`, `job.folder_job_id` →
`placement_id`, `job.user_id` → `creator_key` (hash); only `is_favourite`, `is_viewed`, `has_unresolved_comment`
(viewer/UI state) and the user block are dropped.

## 10. Old vs new

**API drift is minimal.** Comparing every raw leaf path of the NEW runs with the 156 OLD runs (same endpoints),
only one new field appeared: `ip_consent_required` (community trending / approved / detail and project folder
items), and it is already kept (`extra.ip_consent_required` in `generations`, `extra` in `assets`). No new
endpoint appeared in the five re-run scrapers. No raw path we map has disappeared.

**Coverage is stable between old and new data** (same percentages within sampling noise): community jobs ≈ 97 %
with a prompt, 80–90 % with input media, 100 % model + `raw`/`min` media + likes/views; project assets 80 % prompts
visible (old) vs 97 % (new talent-contest projects, all with `show_prompts`), ~94 % with inputs.

**Differences that come from parser versions, not the API** (fix by `normalize`, no re-scrape needed):

| old output | today's parser |
|---|---|
| `20261126-095706_login-comments`: 0 comments written for 22 raw comments | all comments kept (later runs and the re-normalized run) |
| project assets grouped by display name (`"Seedance 2.5"`) in `nested_summary.assets_by_model` | grouped by `job_set_type` (`seedance_2_5`); the display name stays in `model_name` |
| 19 old community runs without `raw_params` (no `--with-raw-params`) | identical information: every param is in `settings` or `params_extra`; `raw_params` is only the verbatim copy |
| creators / talents works dropped | **still dropped** (re-normalized `20261126-161607_completeness-renorm-extras`) |
| Feed `post` items without text / media | **still dropped** (re-normalized `20261126-160942_completeness-renorm-community`) |

The `settings_keys` "lost" counts in the old community rows (790 / 911) are a heuristic artefact: they count the
`id`/`type`/`role` keys inside `params.medias[]`, which the parser moves to `inputs[]` (no raw path of
`params.*` is in the dropped list).

4 new raw paths; endpoints only in the new runs: -

New raw paths (same endpoints, first 150):

| scraper | endpoint | new raw path | kept in output? | sample |
|---|---|---|---|---|
| community | community_approved | `.items[].ip_consent_required` | 100% | False |
| community | community_detail | `.ip_consent_required` | 100% | False |
| community | community_trending | `.items[].ip_consent_required` | 91% | False |
| projects | projects_folder_items | `.items[].job.ip_consent_required` | 100% | False |

## 11. FIX LIST (prioritized, additive only)

Every item adds a field / column; nothing is renamed or removed. Implement after the builders finish; add a
fixture test per item in the scraper's `tests/` file and re-run `python scripts/completeness_audit.py` on a fresh
run to confirm the path leaves the dropped list.

**Status (2026-11-26, commit "Completeness fixes and remaining content gaps"):** #1–#17 are done, all additive (no
field, column, kind or option renamed or removed; default and existing-option dry-runs identical to the previous
HEAD; pricing 31/31 identical). Each fix has fixture tests (`tests/test_community_works.py`, `test_showcase.py`,
`test_projects_extras.py`, `test_catalog_privacy_outfits.py`, `test_studios.py`). #18 stays open as a backlog item.

| # | priority | where (parser / schema / table) | additive change | closes | status (2026-11-26) |
|---|---|---|---|---|---|
| 1 | P1 | `scrapers/community/parsers.py` creators/talents parser + `schemas.py` + `dataset.py` | add a `creator_works` table: one row per `users[].items[]` with `creator_user_id`, `rank`, `item_type`, and for generation items the same fields as `generations` (reuse `parse_generation`: prompt, settings, `raw_params`, inputs, results, engagement, `upstream_usage`, `enhanced_prompt`, `parent_id`), for project items the card fields (title, description, cover, `gallery_media[]`, likes, views, comments, duration) | creator / talent works | **done** — kind `community_creator_work` (key `work_id`), dataset `creator_works[]`, CSV `creator_works.csv` + `creator_work_{inputs,results,media}.csv`; shot items via `parse_generation` (`prompt`, `enhanced_prompt`, `settings`, `raw_params` with `--with-raw-params`, `inputs[]`, `results[]`, `upstream_usage`, `parent_id`), project items `title`, `description`, `cover_*`, `trailer_*`, `gallery_media[]`, `likes`, `views`, `comments` (docs/scrapers/community.md) |
| 2 | P1 | `scrapers/showcase/parsers.py` media/input builder + `schemas.py` input media model (`explore_variants.inputs[]`, `effect_samples.inputs[]`) | add `source_role` (the raw `role`: `image`, `start_image`, `end_image`, …) and `source_type`; keep `role="input"` as is | reference roles for explore + effect samples | **done** — `inputs[].source_role`, `inputs[].source_type` on `explore_variants`, `effect_samples` (and `main_feed_variants`); `role` stays `input` |
| 3 | P1 | `scrapers/community/parsers.py` feed parser + `schemas.py` `FeedItem` (`feed_items`) | add `text`, `media: list[PostMedia]` (reuse the posts media model) for `post` items; add `video_url`, `video_hls_url`, `video_preview_url`, `width`, `height`, `duration_seconds` for project-card items; add `extra` raw blob | Feed post/project media | **done** — `community_feed_item.text`, `media[]` (PostMedia), `video_url`, `video_hls_url`, `video_preview_url`, `width`, `height`, `duration_seconds`, `extra`; CSV `feed_item_media.csv` |
| 4 | P1 | `scrapers/community/parsers.py` posts media + `schemas.py` `PostMedia` (`posts.media[]`) | add `card_likes`, `card_views`, `card_comments`, `card_published_at`, `job_result_thumbnail_url`, `min_result_thumbnail_url` | post card engagement + thumbnail | **done** — `PostMedia.card_likes`, `card_views`, `card_comments`, `card_published_at`, `job_result_thumbnail_url`, `min_result_thumbnail_url` |
| 5 | P1 | catalog raw/http redaction (`core/privacy.py` rules for `catalog_katana_presets`) | add the katana `author.{username,avatar_url}` paths to the archive redaction list | privacy of `raw/` + `http/` | **done** — `CatalogPrivacyMiddleware` (`scrapers/catalog/privacy.py`, downloader middleware 582) redacts the `catalog_katana_presets` body before the `http/` and `raw/` archives (unless `--with-profiles`) |
| 6 | P2 | `scrapers/projects/nested.py` `parse_related` + `schemas.py` `Related` (`related`) | add `title`, `description`, `cover_url`, `trailer_url`, `duration_seconds`, `tags`, `gallery_media[]` (url, original_url, preview_url, thumbnail_url, download_url, width, height, duration), `likes`, `views` | related project media | **done** — `related`: `title`, `description`, `duration_seconds`, `tags[]`, `cover_*`, `trailer_*`, `gallery_media[]`, `creator_uid_keys[]` (docs/scrapers/projects.md) |
| 7 | P2 | `scrapers/showcase/parsers.py` intone + `schemas.py` (`intone_examples.media[]`) | add a media entry `role="video_compressed"` with url/width/height (+ `size_bytes` in `extra`) | Intone second variant | **done** — `intone_examples.media[]` role `video_compressed` (url/width/height; `extra.size_bytes`, …) |
| 8 | P2 | `scrapers/showcase/parsers.py` editing room (`editing_room_projects`, `editing_room_renders`) | add `take_poster_url`, `take_preview_url`, `take_storyboard_vtt_url`, `take_thumbnail_url`, `take_filename`; per version `thumbnail_url` | Editing Room media | **done** — `take_poster_url`, `take_preview_url`, `take_storyboard_vtt_url`, `take_thumbnail_url`, `take_filename`; per version `thumbnail_url` |
| 9 | P2 | `scrapers/showcase/parsers.py` reels + `schemas.py` (`reels_presets`) | add `recreates` (int) | reel trend counter | **done** — `reels_presets.recreates` (also `engagement.uses`) |
| 10 | P2 | identity: `scrapers/community/parsers.py`, `scrapers/projects/parsers.py`, `scrapers/showcase/parsers.py`, `scrapers/studios/parsers.py` | add one shared column `creator_uid_key = make_id("uid", <clerk id>)` (same function in `core/privacy.py`) next to the existing keys in every table that has an author/creator/owner; keep existing keys | one creator = one key across sources | **done** — `creator_uid_key` = `core/privacy.py:creator_uid_key()` = `make_id("creator", <clerk id>)` (the showcase/studios hash, not `"uid"`), on community, projects (`Person`, `creator_uid_keys[]`, folders, assets, judges), showcase, studios and catalog katana rows; null for missing/redacted ids |
| 11 | P2 | `catalog` katana presets (`katana_presets`) | add `author_key` (the shared key of #10) | creator join for presets | **done** — `katana_presets.author_key` + `creator_uid_key` (both the #10 hash) |
| 12 | P3 | `scrapers/showcase/parsers.py` effect samples (`effect_samples`) | add `raw_params` (verbatim blob, like community `--with-raw-params`), `provider`, `prompt_enhance`, `is_reference`, `preset_preview_url`/`preset_poster_url` | effect sample settings | **done** — `effect_samples.raw_params` (verbatim), `provider`, `prompt_enhance`, `is_reference`, `preset_preview_url`, `preset_poster_url` |
| 13 | P3 | `scrapers/showcase/parsers.py` effect page preset (`effect_samples` preset fields or a new `effect_presets` table) | add `preset_inputs` (id, label, min, max, required, binds_to), `param_choices`, `price_matrix` (credit units), preview/widescreen media | effect templates (also in catalog) | **done** — new kind `showcase_effect_preset` → `effect_presets` (`preset_inputs[]`, `param_choices`, `param_inputs`, `pricing_type`, `price_matrix[]` in credit units, media); CSVs `effect_presets__preset_inputs/__price_matrix/__media` |
| 14 | P3 | `scrapers/community/parsers.py` shots page (`pages` or a new `shot_model_facets` table) | add `available_models` (model, count) | facet list | **done** — kind `community_shot_model_facet` → `shot_model_facets` (`model`, `media_type`, `position`, `snapshot_id`, `shots_in_run`: the API sends no per-model count); also `models` scraper `shot_facets` |
| 15 | P3 | `scrapers/projects/parsers.py` public series (`series`, `episodes`) | add optimized image variants (`background/portrait/landscape/logo.optimized.url`), `episodes[].video.shimmer.*`, `video.hls.job_id`, `video.original.{width,height}` | series media variants | **done** — `series`: `portrait/landscape/background/logo_optimized_url`, `trailer_width/height`, `trailer_hls_job_id`; `episodes`: `thumbnail_optimized_url`, `hls_url`, `hls_job_id`, `hls_status`, `video_original_width/height`, `shimmer_url/width/height` |
| 16 | P3 | `scrapers/projects/parsers.py` user publications (`publications`) | add `stats.credits_spent` and `stack[].credits_spent` when the source is `projects_user_publications` (already mapped for other listings) | credits per project | **done** — `publications.listing_credits_spent`, `listing_model_usage[]` from `/user/{handle}/v2/publications` (kept apart: listing unit = detail × 100) |
| 17 | P3 | `scrapers/projects/nested.py` folder parser + `schemas.py` `Folder` (`folders`) | add `path` (raw id path) | folder path | **done** — `folders.path` (raw id path `/<root>/<folder>/…/`) |
| 18 | P3 | `core/api_spider.py` / per-scraper budget | additive option, e.g. `--max-items-per-kind`, so `--max-items` with several kinds/feeds does not fetch pages it will not emit; or log a `limit.items_not_emitted` count in the manifest | §4.3 truncation | **open** (backlog) — not built; `--max-items` with several kinds/feeds still fetches pages it does not emit (§4.3) |

Not fixes (missing in source): lineage (`job_set_parent_id` null in community feeds), `hls`/`h264` on non-preset community videos,
per-job credit price, negative / enhanced / multi prompts outside the few jobs that set them, project asset count
deltas, contest `post_urls` (kept only with `--with-profiles`, intended).
