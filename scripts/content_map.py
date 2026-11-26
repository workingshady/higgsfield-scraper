"""Regenerate the tables of docs/CONTENT_MAP.md (master content map of higgsfield.ai).

The rows below are the source of truth for the per-category tables. Each row is one content source (a route group
or an API endpoint). `python scripts/content_map.py` prints the tables; `--write` replaces the blocks between the
`<!-- BEGIN content-map:<section> -->` / `<!-- END content-map:<section> -->` markers in docs/CONTENT_MAP.md.

`--live` refreshes the "Live total" column first: for rows with a `total_url` it sends ONE public GET (no token,
`size=1`/`limit=1`, about 1 request per second) and reads only the count field (`total_field`, default `total`).
Nothing is created, liked or posted, and no ids or usernames are printed.

    python scripts/content_map.py                 # print all tables (offline, recorded totals)
    python scripts/content_map.py --write         # rewrite the tables in docs/CONTENT_MAP.md
    python scripts/content_map.py --live --write  # refresh live totals (~45 GETs, ~1 min), then rewrite
    python scripts/content_map.py --gaps          # print only the GAP rows
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "CONTENT_MAP.md"
GW = "https://fnf-api-gw.higgsfield.ai"
CMS = "https://cms.higgsfield.ai"
CHECKED = "2026-11-26"

# Section keys -> titles (the doc's category index uses the same keys as anchors).
SECTIONS = {
    "published": "All published videos / images / outputs",
    "avatars": "Avatars",
    "influencer": "AI influencer",
    "trends": "Trends",
    "reels": "Reels",
    "shorts": "Shorts and short videos",
    "cinematic": "Cinematic video",
    "templates": "Templates and presets",
    "ideas": "Ideas, prompt suggestions, tips",
    "models": "Model information",
    "users": "Users and profiles",
    "text": "Text, learning, apps and marketplaces",
    "private": "Login-only, share-code, websocket, blocked",
}

# Visibility: public | login (own data) | login (any) | share-code only | websocket-only | blocked
# covered: "scraper --option", "in progress (agent)", "GAP", "not scraped (reason)"
R = []


def row(sections, source, endpoint, content, vis="public", pub="published", total="", comments="no",
        engagement="", prompt="no", model="no", covered="GAP", evidence="", total_url=None, total_field="total"):
    R.append(dict(sections=sections.split(","), source=source, endpoint=endpoint, content=content, vis=vis, pub=pub,
                  total=total, comments=comments, engagement=engagement, prompt=prompt, model=model,
                  covered=covered, evidence=evidence, total_url=total_url, total_field=total_field))


# ---------------------------------------------------------------- published outputs (generations)
row("published,trends", "Community gallery, trending", f"`{GW}/fnf/publications/community/trending?size&cursor&type&model`",
    "image (99.9 %), video, prompt, input assets", total="75,257 (image 75,226 / video 31)",
    comments="`generation_publication` (key = publication id)", engagement="views, likes", prompt="yes (`params.prompt`)",
    model="yes (`job_set_type`, `params.model`)", covered="`community` (default `--feeds trending`)",
    evidence="ENGAGEMENT.md §1", total_url=f"{GW}/fnf/publications/community/trending?size=1")
row("published,cinematic", "Community gallery, approved (curated)", "`…/publications/community/approved`",
    "video (100 %), prompt, inputs", total="6,175", comments="`generation_publication`", engagement="views, likes",
    prompt="yes", model="yes", covered="`community --feeds approved`", evidence="ENGAGEMENT.md §1",
    total_url=f"{GW}/fnf/publications/community/approved?size=1")
row("published,trends", "Community gallery, top picks", "`…/publications/community/trending/top`", "image, video",
    total="≤ 100", comments="`generation_publication`", engagement="views, likes", prompt="yes", model="yes",
    covered="`community --feeds top`", evidence="HIGGSFIELD_DATA_INVENTORY.md §3.1")
row("published,models", "Community gallery, featured model (model-x)", "`…/publications/community/model-x`",
    "image, video", total="61", comments="`generation_publication`", engagement="views, likes", prompt="yes",
    model="yes", covered="`community --feeds model-x`", evidence="inventory §3.1",
    total_url=f"{GW}/fnf/publications/community/model-x?size=1")
row("published", "Publication detail", "`/fnf/publications/{publication_id}`", "one generation", total="detail",
    comments="`generation_publication`", engagement="views, likes", prompt="yes", model="yes",
    covered="`community --detail`, `--publication-ids`", evidence="COMMUNITY_COVERAGE.md §3")
row("published,models", "Shots (`/community/generations`)", f"`{GW}/fnf-community/generations/feed?limit≤50&cursor&type&models`",
    "image, video (same publications as the gallery)", total="no total (snapshot cursor); `available_models` = 168",
    comments="`generation_publication` (`comment_count` on card)", engagement="likes, views, comments, aesthetic score",
    prompt="via the gallery item (`generation_id`)", model="yes (`model`)", covered="`community --feeds shots [--with-comments]`",
    evidence="chunk `MPUTFNVU3ZLbcp0N`; COMMUNITY_COVERAGE.md")
row("published", "Shots search", "`/fnf-community/generations/search?q&offset&size`", "same objects", total="needs a query",
    comments="—", engagement="—", prompt="—", model="—", covered="not scraped (search view of covered objects)",
    evidence="COMMUNITY_COVERAGE.md §7")
row("published,trends", "Community Feed tab (mixed)", "`/fnf-community/feed?limit≤50&cursor`",
    "shots, projects, blog posts, posts", total="no total (ranked snapshot)",
    comments="per card type (`generation_publication`, `project_publication`, `blog_post`, post)",
    engagement="likes, comments, shares, views, top comment likes", prompt="no (card)", model="`made_with`",
    covered="`community --feeds feed [--with-comments]`", evidence="COMMUNITY_COVERAGE.md")
row("published,text", "Community posts", "`/fnf-community/publications/feed?limit&offset`", "text + attached media/project cards",
    total="≈ 24,294 (binary search)", comments="post thread `/publications/{id}/comments`",
    engagement="likes, dislikes, comments, views, shares", prompt="no", model="card stack",
    covered="`community --feeds posts [--with-comments]`", evidence="ENGAGEMENT.md §4")
row("published", "Per-model community galleries", "`/soul-community`, `/soul-cinema-community`, `/seedance-2(-5)-community`, "
    "`/seedance-4k-community`, `/kling-30-community`, `/gpt-image-2-community`, `/marketing-studio-community`, "
    "`/mixed-media-community/$id`, `/nano-banana-pro-preview/$id`, `/sora-video/$id`, `/wan-video/$id`, "
    "`/motion/$id/publication/$id`, `/mixed-media-presets/publication/$id`",
    "image, video", total="subsets of the gallery (`model=` filter)", comments="`generation_publication`",
    engagement="views, likes", prompt="yes", model="yes", covered="in progress (agent) — per-model galleries; "
    "today reachable with `community --models <job_set_type>`", evidence="routes.json; inventory §2.5")
row("published,trends", "Video explore (Higgsfield Multiplier), community", f"`{CMS}/higgsfield-multiplier/video-explore/v2?source=community&sort=new|trending&size=20&cursor`",
    "video trends + variants (original / edit / generation), prompts", total="49,237",
    comments="count only (`comments_count`)", engagement="likes (+ views/comments/times_made on top items)",
    prompt="yes (generation variants)", model="yes (`job_set_type`)",
    covered="`showcase --what explore_categories --explore-pages 0 --explore-sort both`", evidence="ENGAGEMENT.md §12",
    total_url=f"{CMS}/higgsfield-multiplier/video-explore/v2?lang=en&source=community&size=20&cursor=1&sort=new")
row("published,trends", "Video explore, curated (Higgsfield)", "`…/video-explore/v2?source=higgsfield`", "video trends",
    total="35", comments="no", engagement="none", prompt="yes", model="yes", covered="`showcase --what explore_categories`",
    evidence="scrapers/showcase.md", total_url=f"{CMS}/higgsfield-multiplier/video-explore/v2?lang=en&source=higgsfield&size=20&cursor=1")
row("published,trends,reels", "CMS main feed (home 'Explore' feed of Genjutsu community presets)", f"`{CMS}/main-feed?lang&size=20&cursor`",
    "video presets (original video + edit/generation variants), title, description", total="no total (cursor); 13 of 20 ids also in video explore",
    comments="count only (`comments_count`)", engagement="likes, views, comments, times_made",
    prompt="variant params", model="yes (`job_set_type`, e.g. `hf_mult_replace_object`)", covered="**GAP**",
    evidence="chunk `uBUqSEKZIqX571QB` (`Sn('/main-feed')`); sample `content_map/cms_main_feed.json`")
row("published,templates", "Soul samples", "`/fnf/soul-samples`", "image + prompt", total="1,263", comments="no",
    engagement="none", prompt="yes", model="yes (soul)", covered="`catalog` (default)", evidence="scrapers/catalog.md",
    total_url=f"{GW}/fnf/soul-samples?size=1")
row("published,templates", "Motion samples", "`/fnf/motion-samples?motion_id&size`", "video per motion (~3–5 each)",
    total="≈ 1,500 (419 motions)", comments="no", engagement="none", prompt="yes", model="preset family",
    covered="`catalog --with-samples`", evidence="scrapers/catalog.md")
row("published,trends,templates", "Effect example generations", "`/effects/examples/{slug}` (SSR, 87 pages)",
    "image, video, prompt, inputs", total="87 pages × first SSR page", comments="no", engagement="none",
    prompt="yes", model="yes", covered="`showcase --what effect_examples` (pages 2+ come from a per-build server fn: not fetched)",
    evidence="scrapers/showcase.md §9")
row("published,text", "Project publications (films, series, carousels)", "`/fnf/project-publications?limit≤50&cursor`, `/{id}`",
    "video (cover/trailer/gallery), project assets", total="> 2,000 walked; trending list total 15,276",
    comments="`project_publication`", engagement="views, likes, comments, votes", prompt="assets: yes if `show_prompts`",
    model="assets `job_set_type`, stats stack", covered="`projects` (+ `--with-project-assets/-stats/-comments`)",
    evidence="scrapers/projects.md")
row("published,trends", "Trending project publications (ranking + total)", "`/fnf/project-publications/trending?limit&cursor&sort&filter&with_contest`",
    "same objects as above", total="15,276", comments="`project_publication`", engagement="views, likes, comments",
    prompt="—", model="—", covered="**GAP** (objects reachable via `projects`, this ranking and its total are not)",
    evidence="COMMUNITY_COVERAGE.md (Discovery); live total", total_url=f"{GW}/fnf/project-publications/trending?limit=1")
row("published", "Contest entries (festival, talent contest)", "`/fnf/contest-participations/publications?tab&contest_key&size&cursor`",
    "film projects", total="4,516 public (counters: 66,645 total, 62,129 private)", comments="`project_publication`",
    engagement="views, likes, comments, votes", prompt="via project assets", model="via project stats",
    covered="`projects --what entries`", evidence="probe `contest_participation_counters.json`",
    total_url=f"{GW}/fnf/contest-participations/publications?size=1")
row("published", "Contest participation counters + config", "`/fnf/contest-participations/publications/counters`, `/config`",
    "counts, rules", total="66,645 / 4,516 public", comments="no", engagement="—", covered="**GAP** (tiny)",
    evidence="sample `content_map/contest_participation_counters.json`")
row("published,shorts", "Contest submissions", "`/fnf/contests/{id}/submissions?limit≤100&offset&ordering`", "video",
    total="9,158 over 10 contests", comments="no public thread (entity `contest_submission` → 400)",
    engagement="likes, dislikes, views, social views", prompt="no", model="no",
    covered="`projects --what contests --with-submissions`", evidence="ENGAGEMENT.md §7")
row("published", "Room works", "`/fnf-community/rooms/{id}/items`", "shots (with prompt), projects, blog posts",
    total="1,202 works in 89 rooms", comments="by item type", engagement="likes, views", prompt="shots: yes", model="yes",
    covered="`site --what room-content`", evidence="COMMUNITY_COVERAGE.md")
row("published,shorts", "Original series + episodes", f"`{GW}/fnf-series/series`, `/hero`, `/series/{{slug}}`; `/original-series/*` SSR",
    "HLS video episodes, trailers", total="35 series (+5 hero), 40 episodes", comments="count only (no public thread found)",
    engagement="views, likes, dislikes, votes, subscribers", prompt="no", model="no",
    covered="`site --what originals`, `projects --what series --public-series`", evidence="ENGAGEMENT.md §8",
    total_url=f"{GW}/fnf-series/series?limit=1")
row("published,templates", "Mixed-media preset samples", "`/mixed-media-presets/preset/{id}` SSR", "6 community samples per preset",
    total="33 presets", comments="no", engagement="likes", prompt="yes", model="yes", covered="`site --what mixed-media`",
    evidence="scrapers/site.md")
row("published,templates", "Editing Room example projects + renders", "`/fnf/videoshop/project-examples`, CMS `/videoshop-examples`",
    "video edits, tool params", total="11 examples, 6 projects, 41 renders", comments="no", engagement="none",
    prompt="edit prompts", model="tool", covered="`showcase --what editing_room_examples`", evidence="scrapers/showcase.md")
row("published,users", "A user's published works", "`/fnf/user/{user_id}/v2/publications?publication_type&limit=50&cursor`",
    "assets (generations with prompt/params/results), projects, submissions", total="per user (`total`)",
    comments="by type", engagement="views, clones", prompt="yes", model="yes",
    covered="**GAP (privacy: opt-in only)**; projects only via `projects --users`", evidence="chunk `3On2TPGk30aH8MrG`; "
    "sample `content_map/fnf_user_v2_publications.json`")

# ---------------------------------------------------------------- avatars / influencer
row("avatars,templates", "Avatars", "`/fnf/avatars?size&cursor&category`", "image/video avatar, params", total="100",
    comments="no", engagement="none", prompt="params", model="avatar job", covered="`catalog` (default)",
    evidence="scrapers/catalog.md", total_url=f"{GW}/fnf/avatars?size=1")
row("avatars,templates", "Avatar presets", "`/fnf/avatar-presets`", "preset media", total="21", comments="no",
    engagement="none", prompt="preset prompt", model="—", covered="`catalog` (default)", evidence="scrapers/catalog.md",
    total_url=f"{GW}/fnf/avatar-presets?size=1")
row("avatars", "Avatar / character pages and galleries", "`/avatars`, `/avatar/$category`, `/characters`, `/character`, `/cast`",
    "avatar galleries", total="—", comments="—", engagement="—", prompt="—", model="—",
    covered="in progress (agent) — characters / avatars", evidence="routes.json")
row("avatars,private", "Own characters (Soul ID / custom references / elements)", "`/fnf/custom-references`, `/v2/reference-elements/*`, `/kling-elements/{id}`",
    "trained characters, reference media", vis="login (own data)", pub="private", total="per account", comments="no",
    engagement="—", covered="not scraped (personal library)", evidence="LOGIN_COVERAGE.md §2.4")
row("avatars", "Outfit characters", "`/fnf/outfits/characters`", "2 model images", total="2", comments="no",
    engagement="none", covered="**GAP** (trivial)", evidence="chunk `sGxtyi5DXhlNSfix`; sample `content_map/fnf_outfits_characters.json`")
row("influencer,templates", "AI influencer builder options", f"`{CMS}/ai-influencer-config` (= `fnf-cms-api`)",
    "4 categories → subcategories → options with preview media", total="4 categories", comments="no", engagement="none",
    prompt="no (trait config)", model="`ai_influencer`", covered="**GAP**",
    evidence="chunk `YNwTwBIMiHh-jeot`; sample `content_map/cms_ai_influencer_config.json`")
row("influencer,published", "AI influencer outputs in the gallery", "`…/publications/community/trending?model=ai_influencer`",
    "image + trait config", total="1,017", comments="`generation_publication`", engagement="views, likes",
    prompt="`config` (traits; prompt often empty)", model="yes", covered="`community --models ai_influencer`",
    evidence="live total", total_url=f"{GW}/fnf/publications/community/trending?size=1&model=ai_influencer")
row("influencer,private", "Own AI influencers", "`/fnf/ai-influencers?size=30&direction&cursor`", "own characters",
    vis="login (own data)", pub="private", total="0 anonymous / own list", covered="not scraped (personal)",
    evidence="chunk `keixfeJScOR0pZEX`; live 200 `{items: []}`")
row("influencer,private", "Shared AI influencer", "`/ai-influencer/shared/$code`", "one shared character",
    vis="share-code only", pub="private (link)", covered="not scraped (never enumerate codes)", evidence="routes.json")

# ---------------------------------------------------------------- trends
row("trends,templates", "Viral effects / viral-hub presets", "`/fnf/viral-hub/presets/all`, `/viral-hub/types`",
    "effect presets, preview media, price matrix", total="87 presets, 6 types", comments="no", engagement="none",
    prompt="preset", model="`viral_transform_*`", covered="`catalog --kinds viral_preset,viral_type`",
    evidence="scrapers/catalog.md", total_url=f"{GW}/fnf/viral-hub/presets/all?limit=1&lang=en")
row("trends,templates", "Collections (`/collection/catch-the-pulse`, `/collection/effects`)", "`/fnf/collections/{slug}`",
    "curated preset lists (name, media, params, tags)", total="catch-the-pulse: 15", comments="no", engagement="none",
    prompt="params", model="preset", covered="in progress (agent) — collections",
    evidence="chunk `tCLaulKUdGQfxqgZ` (`HW`); sample `content_map/fnf_collection_catch_the_pulse.json`")
row("trends", "Sora trends (`/sora-trends`, `/sora-trends/$category`)", "route only", "redirect to `/ai/video` with a preset prompt",
    total="—", covered="nothing to scrape (client redirect, chunk `qQFcAZLo87VHkLMU`)", evidence="chunk `qQFcAZLo87VHkLMU`")
row("trends", "Feed hashtag categories", "`/fnf-community/feed/categories`, `/feed/ongoing`", "hashtag contests with post counts, previews",
    total="2 categories; ongoing `[]`", comments="no", engagement="`post_count`", covered="**GAP** (tiny)",
    evidence="COMMUNITY_COVERAGE.md §3")
row("trends", "Contests trending / weekly latest", "`/fnf/contests/trending`, `/contests/weekly-challenge/latest`",
    "—", total="204 / 404", covered="nothing to scrape", evidence="scrapers/projects.md")
row("trends,shorts", "Faceless 'hot right now'", "`/fnf/youtube-faceless/hot-right-now`", "trending topics", total="empty",
    covered="not built (empty)", evidence="inventory §3.6")

# ---------------------------------------------------------------- reels
row("reels", "Reels (showcase)", "`/ai-reels`, reels showcase sources", "short vertical videos", total="—",
    covered="in progress (agent) — reels (showcase)", evidence="task brief")
row("reels,private", "Shared reels", "`/ai-reels/shared/$code`", "one shared reel", vis="share-code only",
    pub="private (link)", covered="not scraped (never enumerate codes)", evidence="routes.json")
row("reels,published", "Viral transform outputs (reels made with effects)", "gallery `model=viral_transform_image|viral_transform_video`",
    "image/video", total="12 / 0 today", comments="`generation_publication`", engagement="views, likes", prompt="yes",
    model="yes", covered="`community --models viral_transform_image,viral_transform_video`", evidence="live totals")
row("reels,templates", "Genjutsu for reels / Genjutsu presets", "`/genjutsu-for-reels`, CMS main feed `genjutsu` items",
    "video presets", total="see main feed", covered="**GAP** (via main feed row)", evidence="routes.json")

# ---------------------------------------------------------------- shorts
row("shorts", "Shorts / Shorts Studio / Short Drama / Production / Popcorn / AI Host / Faceless Studio",
    "`/shorts/$id`, `/shorts-studio/$id`, `/short-drama/$projectId`, `/production/$episodeId`, `/popcorn`, "
    "`/ai-host/channel/$id`, `/faceless-studio/channel/$id`", "studio projects, episodes, storyboards",
    total="—", covered="in progress (agent) — `studios` scraper", evidence="routes.json; PRODUCTS.md §3.18–3.19")
row("shorts,templates", "YouTube faceless presets + showcases", f"`{CMS}/youtube-faceless-presets`, `/youtube-faceless-showcases`",
    "presets; showcase videos", total="12 presets; 9 showcases", comments="no", engagement="none",
    covered="`catalog --kinds youtube_faceless_preset`; `showcase --what faceless_showcases`", evidence="catalog.md, showcase.md",
    total_url=f"{CMS}/youtube-faceless-showcases?size=1&lang=en")
row("shorts,private", "Own studio projects (channels, storyboards, timelines)", "`/youtube-faceless/channels/*`, `/video-storyboards`, "
    "`/timeline-renders`, `/videoshop/projects`, `/realtor-studio/projects/*`", "own projects", vis="login (own data)",
    pub="private", covered="not scraped (personal)", evidence="newpaths in js2")

# ---------------------------------------------------------------- cinematic
row("cinematic,templates", "Cinema Studio creative controls", f"`{GW}/fnf/cinema-studio-4-0/creative-controls?type`",
    "camera model/lens/aperture/movement, color, pacing, light, genre, era + sample media", total="78",
    comments="no", engagement="none", prompt="no", model="Cinema Studio 4.0", covered="`showcase --what cinema_controls`",
    evidence="chunk `bKEXuDpgggSxxXuu`")
row("cinematic,published", "Cinema Studio outputs in the gallery", "gallery `model=cinematic_studio_image|cinematic_studio_3_0|cinematic_studio_video_4_0`",
    "image, video", total="image 489 (trending); 3.0 video 41 (approved); 4.0 video 0", comments="`generation_publication`",
    engagement="views, likes", prompt="yes", model="yes", covered="`community --models cinematic_studio_image,cinematic_studio_3_0`; "
    "4.0 videos via `community --feeds shots --models cinematic_studio_video_4_0`", evidence="live totals")
row("cinematic,templates", "Soul cinematic styles", f"`{CMS}/soul-cinematic-styles`", "style presets", total="2",
    covered="`catalog --kinds soul_style`", evidence="scrapers/catalog.md")
row("cinematic,private", "Own camera settings", "`/fnf/camera-settings`", "saved settings", vis="login (own data)",
    pub="private", total="0", covered="`catalog --kinds camera_setting` (login)", evidence="scrapers/catalog.md")

# ---------------------------------------------------------------- templates / presets
row("templates", "Motions (camera / VFX presets)", "`/fnf/motions?size&cursor`, `/motions/{id}`", "preset + preview video",
    total="419", covered="`catalog` (+ `--with-details`)", prompt="params", model="`preset_family`", engagement="none",
    evidence="scrapers/catalog.md", total_url=f"{GW}/fnf/motions?size=1")
row("templates", "Per-model motion / style lists", f"`{CMS}/veo3-styles`, `/kling-motions`, `/kling2-6-motions`, `/seedance-motions`, "
    "`/wan2-2-motions`, `/wan2-5-motions`, `/minimax-motions`", "presets", total="241 (17+58+22+25+27+15+77)",
    covered="`catalog --kinds model_motion` (login group, public)", model="per family", evidence="scrapers/catalog.md")
row("templates", "Soul styles (+ keyframe)", f"`{CMS}/soul-styles`, `/soul-keyframe-styles`", "style presets", total="106 + 17",
    covered="`catalog --kinds soul_style`", evidence="scrapers/catalog.md", total_url=f"{CMS}/soul-styles?size=1&lang=en")
row("templates", "Image styles", "`/fnf/styles`", "style presets", total="5", covered="`catalog`", evidence="catalog.md")
row("templates", "Chain presets (game character creator)", "`/fnf-cms-api/job-set-chain-presets[?show_hidden]`",
    "presets with credit prices", total="48 (58 with hidden)", model="yes (`model`)", covered="`catalog --kinds chain_preset [--include-hidden]`",
    evidence="LOGIN_COVERAGE.md §2.2")
row("templates", "Restyle presets", "`/fnf-cms-api/restyle-presets`", "presets + preview media", total="21",
    covered="`catalog --kinds restyle_preset`", evidence="catalog.md", total_url=f"{GW}/fnf-cms-api/restyle-presets?size=1")
row("templates", "Mixed-media presets", f"`{CMS}/mixed-media-presets`", "presets", total="33",
    covered="`catalog --kinds mixed_media_preset`, `site --what mixed-media`", evidence="catalog.md",
    total_url=f"{CMS}/mixed-media-presets?size=1&lang=en")
row("templates", "Katana categories + presets", "`/fnf-cms-api/katana-categories`, `/katana-presets`", "presets (authors redacted)",
    total="3 / ~100+", covered="`catalog --kinds katana_category,katana_preset`", evidence="catalog.md")
row("templates", "Marketing Studio v2 catalog + presets", f"`{CMS}/marketing-studio-v2/catalog`, `/categories/{{slug}}/presets`",
    "ad presets (prompts, media)", total="7 categories; 1,051 presets (`total` is global, not per category)",
    prompt="yes", covered="`catalog --kinds marketing_category,marketing_preset`; brands/products/community: in progress (agent)",
    evidence="catalog.md; live")
row("templates", "Playable-ads presets", f"`{CMS}/playable-ads-presets?size&cursor`", "game ad presets (video, poster, game, recreate)",
    total="112", covered="in progress (agent) — ads / studios", evidence="chunk `uBUqSEKZIqX571QB`; sample",
    total_url=f"{CMS}/playable-ads-presets?size=1&cursor=1&lang=en")
row("templates", "Music cards presets", f"`{CMS}/music-cards-presets?q&category`", "song cards: lyrics, music, video, style",
    total="111 (26 categories)", prompt="lyrics", covered="in progress (agent) — music-cards",
    evidence="chunk `Hba1h6PAxZ4rbHsX`; sample")
row("templates", "Seedance 2.0 presets / Kling motion-control presets / Intone examples", f"`{CMS}/seedance-2-0`, `/kling-motion-control-presets`, `/intone/explore`",
    "preview media", total="14 / 36 / 18", covered="`showcase --what seedance_presets,motion_control_presets,intone_examples`",
    evidence="scrapers/showcase.md")
row("templates", "Canvas templates", "`canvas-worker.higgsfield.ai/api/templates`", "workflow templates", total="5",
    covered="`showcase --what canvas_templates` (graph only over a login websocket)", evidence="showcase.md",
    total_url="https://canvas-worker.higgsfield.ai/api/templates?limit=1")
row("templates", "Property Studio presets", "JS preset table + `static.higgsfield.ai/realty-studio/…`", "before/after/tour media",
    total="69", covered="`showcase --what property_studio_examples`", evidence="showcase.md")
row("templates,text", "Apps (`/apps/{slug}`) and app templates", "`/apps` SSR, `/apps/{slug}`; `fnf-cms-api /applications/explore`",
    "app templates, inputs, credit cost", total="84 on index, 98 in sitemap", covered="`site --what apps`", evidence="scrapers/site.md")
row("templates", "Voices / reference voices / sounds", "`/fnf/voices`, `/reference-elements/voices`, `/sounds`", "audio",
    total="82 / 115 / 11", covered="`catalog`", evidence="catalog.md", total_url=f"{GW}/fnf/voices?size=1")
row("templates", "Notices (model badges, retirements)", f"`{CMS}/notices`", "model lifecycle text", total="10",
    model="yes", covered="`catalog --kinds notice`", evidence="catalog.md")
row("templates,private", "Own presets (custom restyle, color presets, mixed-media configs, recraft styles)",
    "`/fnf/restyle/presets/custom`, `/color-presets`, `/mixed-media/configs`, `/recraft-styles`", "own presets",
    vis="login (own data)", pub="private", total="recraft: anon 401, login 200 `[]`", covered="`catalog --kinds color_preset` (login); rest not scraped",
    evidence="catalog.md; live")
row("templates", "Promo cards / banners", f"`{CMS}/cards`", "192 promo banners", total="192",
    covered="not scraped (marketing banners)", evidence="showcase.md §9")

# ---------------------------------------------------------------- ideas
row("ideas", "Random tip", f"`{CMS}/tips/random?plan&job_set_type`", "UI tip", total="404 `No matching tips found` for free/basic/starter/plus/pro",
    covered="nothing to scrape today", evidence="chunk `eiD1gGu1p32WESpz` (`tt` = CMS builder); live")
row("ideas,private", "Agent / chat suggestions, inspiration tool", "`/claudesfield/chats/{id}/suggestions`, `agent-suggestions`, `tool-higgsfield_inspiration`",
    "per-chat prompt ideas", vis="login (own data)", pub="private", covered="not scraped (per chat, login)",
    evidence="chunks `Qh3eKMIijLiIcSip`, `uEHtQK8MdgAsd1Z0`")
row("ideas,users", "Follow suggestions", "`/fnf-community/users/suggestions`", "people to follow", total="10 per call",
    covered="not scraped (lists of people)", evidence="LOGIN_COVERAGE.md §2.3")
row("ideas,text", "Prompt guides and examples (public text)", "blog guides, `/nano-banana-pro-prompt-guide`, academy lessons, MCP skill prompts, "
    "skills marketplace `example_prompt`", "prompt examples", prompt="yes", covered="`blog`, `site --what academy,mcp,landings`; skills marketplace: GAP",
    evidence="see rows in §text")

# ---------------------------------------------------------------- model info
row("models", "Model prices and availability", f"`{GW}/fnf/job-sets/costs`, `pricing.higgsfield.ai/v2/pricing-config`, `/pricing.md`",
    "job_set_type × resolution cost rows", total="87 anon / 88 logged in", model="yes", covered="`pricing` (`--sections models`; `--logged-in-prices`)",
    evidence="ENDPOINTS.md, LOGIN_COVERAGE.md §1")
row("models", "JS model registry (`defineJob`, menus, gating, routes)", "`assets.higgsfield.ai/tanstack/assets/*.js`",
    "~100 job types: params schema, enums, plans, flags", model="yes", covered="offline only: `scripts/gen_model_catalog.py` → PRODUCTS.md §4; "
    "**GAP**: no `models` scraper", evidence="MODEL_LOADING.md §2–3, §8")
row("models", "Feature flags `__HF_FF`", "any SSR page", "23 flags (model gating)", model="gating", covered="`scripts/re_check_changes.py` (monitor); no scraper",
    evidence="MODEL_LOADING.md §1")
row("models", "Public API model docs", "`docs.higgsfield.ai/llms-full.txt`, `/docs/openapi.json`", "83 endpoints, 580 params, prices",
    total="83", model="yes", covered="`showcase --what api_models`", evidence="showcase.md")
row("models,text", "Model landing pages", "`/kling-3.0`, `/seedance/2.5`, `/veo3.1`, … (sitemap-marketing)", "marketing text, FAQ",
    total="~165", model="yes", covered="`site --what landings`", evidence="scrapers/site.md")
row("models,text", "Help center 'AI models' articles", "`/creator-hub/help-center/ai-models/*`", "model docs", covered="`blog --what help`",
    evidence="scrapers/blog.md")

# ---------------------------------------------------------------- users
row("users", "Creators directory", "`/fnf/community/discovery/v2/creators?all=true&sort&cursor`", "creator cards + works",
    total="646", engagement="followers, following, likes, views, rating", comments="no",
    covered="`community --feeds creators` (aggregate stats; names only `--with-profiles`)", evidence="COMMUNITY_COVERAGE.md",
    total_url=f"{GW}/fnf/community/discovery/v2/creators?all=true&sort=default&limit=1")
row("users", "Talents hub", "`/fnf/community/discovery/talents?sort`", "talent cards", total="80",
    covered="`community --feeds talents`", evidence="COMMUNITY_COVERAGE.md",
    total_url=f"{GW}/fnf/community/discovery/talents?sort=recent&limit=1")
row("users", "Public profile (full)", "`/fnf/user/{username}`", "name, bio, headline, location, 6 social handles, totals",
    total="per user", engagement="total_projects_views/likes", covered="not scraped by design (identity + social handles)",
    evidence="live 200 anonymous; shape-only sample `content_map/fnf_user_profile.json`")
row("users", "Profile preview card", "`/fnf-community/profiles/{username}/preview`", "counts + identity", total="per user",
    engagement="followers, following, likes, views, rating", covered="not scraped (creators feed gives the same counts)",
    evidence="chunk `2LEglrRfQ_sthOCg`; shape-only sample")
row("users", "User stats", "`/fnf/user/{user_id}/stats`", "posts, likes, views", total="per user",
    covered="**GAP (opt-in, pseudonymous)**", evidence="live 200 anonymous")
row("users", "User projects (`/@user/projects`)", "`/fnf/project-publications/{username}/{slug}`, user project list",
    "projects", covered="`projects --users <handles>`", evidence="scrapers/projects.md")
row("users", "Followers / following / room members", "`/fnf/users/{id}/subscribers|subscriptions`, `/fnf-community/rooms/{id}/followers`",
    "lists of people", covered="never collected (rule)", evidence="COMMUNITY_COVERAGE.md §7")
row("users,private", "Achievements, presence, rating", "`/fnf/users/{id}/achievements`, `/user/{id}/compact`, `/users/me/*`",
    "per user", vis="login (any)", covered="not scraped", evidence="live 401 anonymous")

# ---------------------------------------------------------------- text, learning, marketplaces
row("text", "Blog (CMS) + authors", "`/blog/*` SSR", "articles", total="342 + 5 authors", covered="`blog`", evidence="scrapers/blog.md")
row("text", "Talent + community blog posts", "`/fnf/community/discovery/talents/blog-posts`, `/fnf/blog/posts/recommended`",
    "user articles (Yjs body)", total="57 / ≈ 50 per day", comments="`blog_post`", engagement="likes, views",
    covered="`blog --what talents,community`; comments via `community --feeds feed --with-comments`", evidence="scrapers/blog.md")
row("text", "Help centers, case studies, changelog", "`/creator-hub/*`, `/enterprise-help-center/*`", "articles",
    total="75 + 30 help, 24 case studies, 189 changelog", covered="`blog` (default)", evidence="scrapers/blog.md")
row("text", "Academy courses + lessons", "`/academy/*` SSR; `fnf-academy /api/v1/courses`", "lessons (Markdown), videos",
    total="17 courses, 179 lessons", covered="`site --what academy` (JSON list with `free_generations`: open item)", evidence="site.md; LOGIN_COVERAGE.md")
row("text", "MCP skills + bundles", "`/mcp`, `/mcp/{slug}`, `/mcp/bundles/{id}`", "prompt packages", total="75 + 3",
    prompt="yes", covered="`site --what mcp`", evidence="scrapers/site.md")
row("text,templates", "Skills marketplace (builtin + community)", f"`{GW}/fnf-skills-marketplace/api/v1/skills/builtin`, `/skills/community?limit≤100&cursor`, "
    "`/skills/community/{id}/content`", "agent skills: description, `example_prompt`, examples, preview media",
    total="80 builtin + 632 community", engagement="usage_total, usage_count, installs_count, unique_users_count",
    prompt="yes (`example_prompt`)", covered="**GAP** (check overlap with the studios agent's 'marketplace' first)",
    evidence="chunk `73K2QNngizhBbx6B`; samples `content_map/skills_*.json`")
row("text,templates", "Apps marketplace (community-built apps, games, websites)", f"`{GW}/fnf-apps-marketplace/api/v1/apps/community?offset&limit=50`",
    "apps: cover image/video, description, `credits_usage`", total="≈ 59,550 (binary search on offset)",
    engagement="views, likes, dislikes, remixes", covered="in progress (agent) — apps marketplace", evidence="ENGAGEMENT.md §11; live")
row("text", "Employees / games / connectors marketplace", "`/marketplace/{employees,games,connectors}`, `/api/v1/ai-agents/`",
    "AI employees, games", covered="in progress (agent) — marketplace / other studios", evidence="routes.json")
row("text", "Rooms", "`/fnf-community/rooms`, `/rooms/{id}`, room-stats, discussions", "rooms, works, discussion posts",
    total="89 rooms", comments="discussion posts", engagement="followers, works", covered="`site --what room-list|room-content`",
    evidence="COMMUNITY_COVERAGE.md", total_url=f"{GW}/fnf-community/rooms?limit=1")
row("text", "Magazine issues", "`/community/magazine/$issue` (+ `static.higgsfield.ai/public/magazine/…`)", "static issue",
    covered="in progress (agent) — magazine", evidence="COMMUNITY_COVERAGE.md §1")
row("text", "Promo APIs", "`/fnf/datetime-settings`, `/business-unlim/state`, `/game-gift/networks`", "promo windows",
    total="17 / 8 / 37", covered="`site --what promos`", evidence="scrapers/site.md")

# ---------------------------------------------------------------- private / share-code / websocket / blocked
row("private", "Own library (jobs, assets, folders, favourites, trash)", "`/fnf/jobs/accessible`, `/assets`, `/folders*`, `/trash/*`",
    "own generations with real cost", vis="login (own data)", pub="private", covered="`account --with-jobs` (jobs only)",
    evidence="LOGIN_COVERAGE.md §2.4")
row("private", "Shared links", "`/shared/$code`, `/share/$id`, `/s/{code}`, `/go/$code`, `/genjutsu|katana|what-if/shared/$code`, "
    "`/v2/reference-elements/shared/{id}`, `/marketplace/employees/shared/$slug`, `/supercomputer/shared/$code`",
    "one shared object per link", vis="share-code only", pub="private (link)", covered="never (no enumeration of codes)",
    evidence="routes.json, js2")
row("private", "Realtime streams", "`fnf-notification /notifications/stream` (SSE), canvas `wss …/api/templates/{id}/connect`, `fnf-meet`",
    "job status, canvas graph sync, calls", vis="websocket-only", pub="private", covered="not scraped (not GET APIs)",
    evidence="MODEL_LOADING.md §1; showcase.md §9")
row("private", "Bot-protected paths", "`/fnf/jobs`, `/media`, `/v2/reference-elements/picker`", "—", vis="blocked",
    covered="never (DataDome 403)", evidence="inventory §6")
row("private", "Season / quests", "`fnf-score /v1/season`", "per-user season", vis="login (own data)", pub="private",
    total="`null`", covered="`showcase --what season` (login)", evidence="showcase.md")


# ------------------------------------------------------------------------------------------------ rendering
COLS = [("Source", "source"), ("Endpoint / route (GET)", "endpoint"), ("Content", "content"), ("Visibility", "vis"),
        ("Published?", "pub"), ("Live total", "total"), ("Comments (entity type)", "comments"), ("Engagement", "engagement"),
        ("Prompt", "prompt"), ("Model / job_set_type", "model"), ("Covered by", "covered"), ("Evidence", "evidence")]


def esc(v: str) -> str:
    return (v or "—").replace("|", "\\|").replace("\n", " ")


def table(rows) -> str:
    out = ["| " + " | ".join(c for c, _ in COLS) + " |", "|" + "---|" * len(COLS)]
    for r in rows:
        out.append("| " + " | ".join(esc(r[k]) for _, k in COLS) + " |")
    return "\n".join(out)


def live_refresh() -> None:
    sys.path.insert(0, str(ROOT))
    import requests
    from higgsfield_scraper.constants import USER_AGENT
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Origin": "https://higgsfield.ai"}
    for r in R:
        if not r["total_url"]:
            continue
        time.sleep(1.05)
        try:
            resp = requests.get(r["total_url"], headers=headers, timeout=40)
            val = resp.json().get(r["total_field"]) if resp.ok else None
        except Exception:
            val = None
        if isinstance(val, int):
            r["total"] = f"{val:,} (live {time.strftime('%Y-%m-%d')})"
        print(f"{r['source'][:50]:50} -> {val}", file=sys.stderr)


def render_all() -> dict[str, str]:
    blocks = {key: table([r for r in R if key in r["sections"]]) for key in SECTIONS}
    blocks["gaps"] = table([r for r in R if "GAP" in r["covered"]])
    return blocks


def write_doc(blocks: dict[str, str]) -> None:
    text = DOC.read_text(encoding="utf-8")
    for key, body in blocks.items():
        begin, end = f"<!-- BEGIN content-map:{key} -->", f"<!-- END content-map:{key} -->"
        pat = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
        if not pat.search(text):
            print(f"marker for section {key!r} not found; skipped", file=sys.stderr)
            continue
        text = pat.sub(lambda _m: f"{begin}\n{body}\n{end}", text)
    DOC.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="refresh totals with one public GET per row (~1 req/s)")
    ap.add_argument("--write", action="store_true", help="rewrite the tables in docs/CONTENT_MAP.md")
    ap.add_argument("--gaps", action="store_true", help="print only GAP rows")
    a = ap.parse_args()
    if a.live:
        live_refresh()
    if a.gaps:
        print(table([r for r in R if "GAP" in r["covered"]]))
        return
    blocks = render_all()
    if a.write:
        write_doc(blocks)
        print(f"wrote {len(blocks)} tables, {len(R)} rows -> {DOC}")
    else:
        for key, body in blocks.items():
            print(f"\n## {SECTIONS.get(key, 'GAP rows')}\n\n{body}")


if __name__ == "__main__":
    main()
