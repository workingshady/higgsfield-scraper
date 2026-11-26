# Engagement audit — likes, views, comments, votes (old vs new, anonymous vs logged in)

Live check on 2026-11-26: about 140 GET requests at ~1 request/s, each engagement endpoint called once **without
login** and once **with a Bearer token** (same URL; the token was never printed or stored). No 429 and no DataDome
block. Host `GW` = `https://fnf-api-gw.higgsfield.ai`. Item ids in the evidence are shortened hashes.

## Summary

- **Every engagement count is public.** No count needs a login, on any endpoint checked. Logging in only turns
  per-viewer flags from `null` into `true/false` (`is_liked_by_user`, `liked_by_me`, `is_liked`…) and adds
  `is_followed` / `join_requested` on rooms. These flags are **personal** (about the logged-in user) and stay off by
  default in every scraper.
- **Old items keep their counts** (non-null, often non-zero). Most feeds can be paged to the oldest item, often in one
  request (offset / page number / score or timestamp cursor). The exception is the blog recommendation feed
  (sequential cursor only).
- **Counts are live**: views change within minutes (gallery, posts, Feed tab, series); gallery likes changed too.
  Project-publication counts did not move in 4.5 min (low-activity items, so live vs cached is unproven there).
- **Not collected yet** by any scraper: the community apps marketplace (views/likes/dislikes/remixes) — listed in
  §11. The CMS video-explore community feed (likes) is now collected by `scrape showcase`.
  **Update 2026-11-26:** the marketplaces are now collected by the opt-in `scrape studios` (apps: views / likes /
  dislikes / remixes / credits; games: plays / unique players / remixes; skills and AI employees: installs / unique
  users / usage; per-studio galleries: views / likes + comments), see §11. The CMS main feed (likes / views /
  comments / `times_made`) is `scrape showcase --what main_feed`.
- **No engagement at all**: MCP skills, `/apps/*` app pages, viral-hub presets, CMS blog posts, all other showcase
  sources (canvas templates, editing-room examples, Property Studio, effect samples, API models, CMS showcases).

Legend for "anonymous vs logged in": **same** = identical counts and keys for the same URL.

## 1. Community generations (gallery feeds)

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items have it? | Live or frozen | Collected by |
|---|---|---|---|---|---|---|---|
| views | `publication.views_count` | `GW/fnf/publications/community/{trending,approved,trending/top}`, `/fnf/publications/{id}` | yes | same | yes (e.g. 796 views on a 2025-12 item; deepest trending scores have 0) | **live** | `scrape community` → `engagement.views` |
| likes | `publication.likes_count` | same | yes | same | yes (e.g. 90 likes, 2025-12) | **live** | `engagement.likes` |
| liked by me (**personal**) | `publication.is_liked_by_user` | same | `null` | **`true/false` only when logged in** | n/a | n/a | `engagement.is_liked_by_user` (null by default) |

No comment/share/vote fields on gallery items (`/fnf/publications/{id}/comments` → 404; comments are on
fnf-community, §3).

Old vs new: `trending` (`total` 75 528) uses a float score cursor; `cursor=1e-4…1e-8` reached items created back to
2025-11-26; `cursor=0` → empty, `has_more:false` (end). `approved` (`total` 6 187) uses an epoch cursor:
`1795600000` → 2026-09-09, `1788000000` → 2026-08-26, `1750000000` → empty. Live: `trending?size=20` fetched
5.2 min apart, all 20 changed, e.g. `[views, likes]` `[249,2]→[280,3]`, `[227,1]→[272,1]`. A detail GET may itself
count as a view (267 anon → 268 logged in seconds later).

## 2. Shots (`/community/generations`)

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| likes / views / comments | `like_count`, `view_count`, `comment_count` | `GW/fnf-community/generations/feed?limit&cursor` | yes | same | snapshot cursor (base64), not jumpable | same counters as the Feed tab (live) | `scrape community --feeds shots` |
| liked by me (**personal**) | `is_liked_by_user` | same | `null` | `false/true` | | | |

## 3. Comments (fnf-community)

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| likes / dislikes | `like_count`, `dislike_count` | `GW/fnf-community/publications/{post_id}/comments?limit&offset`; `/entities/{generation_publication\|project_publication\|blog_post}/{id}/comments?limit&cursor` | yes | same | not measured | not measured | `scrape community --with-comments`; `scrape projects --with-project-comments` |
| replies | `reply_count` | same | yes | same | | | same |
| reactions | `reactions[].count` | same | yes | same | | | `reactions` |
| comments per entity | envelope `total` | entity comments | yes | same | | | |
| is mine / my vote (**personal**) | `is_mine`, `top_comment.my_vote` | comments, Feed tab | `false` / `null` | viewer-specific | | | not exported |

## 4. Community posts (`/feed` posts service)

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items have it? | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| likes | `like_count` | `GW/fnf-community/publications/feed?limit&offset` | yes | same | yes (mostly 0 on old posts) | live | `scrape community --feeds posts` → `likes` |
| dislikes | `dislike_count` | same | yes | same | yes | | `dislikes` |
| comments | `comment_count` | same | yes | same | yes | | `comments` |
| views | `views_count` | same | yes | same | **yes, non-zero** (305, 297 on 2026-03-25 posts) | **live** | `views` |
| shares | `share_count` | same | yes | same | yes | | `shares` |
| embedded card stats | `content.medias[].card.{views_count, like_count, comment_count, stats.generations_count}` | same | yes | same | | | raw only (not mapped) |
| **personal** | `is_mine`, `is_subscribed`, `content.medias[].card.is_liked` | same | `is_liked` null | `null → false` | | | dropped (viewer flags) |

Old vs new: offset paging. `offset=10000` → 2026-05-20…23; `offset=24000` → 2026-03-25…27 (all with views > 0);
`offset=24300+` → empty, `has_more:false`. Oldest post ≈ offset 24.0–24.3k (≈2026-03-25). Live: `limit=50`, 4.3 min
apart, all 50 changed (views only), e.g. `[like, comments, views, shares]` `[3,4,2098,1]→[3,4,2102,1]`.

## 5. Community Feed tab (mixed: generation / project_publication / blog_post / post)

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| likes / comments / shares | `like_count`, `comment_count`, `share_count` | `GW/fnf-community/feed?limit&cursor` | yes | **logged-in feed is personalised** (`unified-unseen` cursor, different items/order); counts of the same item are equal | snapshot cursor only | **live** | `scrape community --feeds feed` |
| views | `generation.view_count` / `card.views_count` / `post.views_count` | same | yes | same values | | live | `views` |
| top comment likes | `top_comment.like_count` | same | yes | same | | | `top_comment_likes` |
| usage ("made with") | `card.stats.generations_count`, `card.stats.stack[].count` | same | yes | same | | | not mapped |
| **personal** | `is_liked`, `is_mine`, `author.is_subscribed`, `generation.is_liked_by_user`, `card.is_liked`, `card.liked_by_me`, `top_comment.my_vote` | same | null/false | `null → false` | | | not exported |

Live: 5.6 min apart, 8/10 changed (views), e.g. `[1571,16,6,27939]→[1571,16,6,27953]`.

## 6. Project publications

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items have it? | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| views / likes / comments | `views`, `likes`, `comments` | `GW/fnf/project-publications?limit&cursor`, `/project-publications/{id}` | yes | same | yes (views > 0 on 50/50 items in the tail, created back to 2026-07-22) | no change in 2.9 / 4.5 min (unproven) | `scrape projects --what publications` |
| contest votes | `votes` | `GW/fnf/contest-participations/publications` | yes | same | yes (0) | | `--what entries` → `votes` |
| author aggregates | `authors[].total_projects_views/likes`, `followers_count` | same | yes | same | | | projects author schema |
| usage | `stats.generations_count`, `stats.stack[].count` | `/project-publications/{id}` | yes | same | | | `--with-details` / `--with-project-stats` |
| liked by me (**personal**) | `is_liked_by_user` | list | `null` | `false/true` | | | not exported |

Old vs new: cursor `"<score>:<uuid>"`; 8 pages × 50 sequential (created 2026-08-24…11-26, not date-ordered); crafted
`cursor=1.0:000…` → items from 2026-07-22; `cursor=0.0:000…` → empty (end).

## 7. Contest submissions and entries

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| likes / dislikes | `likes_count`, `dislikes_count` | `GW/fnf/contests/{id}/submissions?limit&offset&ordering` | yes | same | **yes**: 100/100 > 0 at offset 1000 and 4000 | not measured | `scrape projects --what contests --with-submissions` |
| views | `views_count`, `total_views`, `social_media_metrics.{instagram,tiktok,youtube,x}_views` | same | yes | same | yes | | same |
| clone flag | `clone_available` | same | yes | same | | | same |
| my mark (**personal**) | `like_mark` | same | `null` | `null` (not populated) | | | not exported |
| entries views / likes / comments / **votes** | `views`, `likes`, `comments`, `votes` | `GW/fnf/contest-participations/publications?tab&contest_key&size&cursor` | yes — **votes need no login to read** | same | yes: `cursor=4450` (2026-08-14…17) 66/66 likes & views > 0, votes 0 | | `scrape projects --what entries` |
| **personal** | `watch_required`, `watch_completed`, `watched_percent`, `is_liked_by_user` | entries | false/0/null | identical | | | not exported |

Paging: finished contest (`submissions_count` 8 752): `offset=8700` → empty (moderated items are not listed).
Entries `total` 4 516; offset-string cursor, `cursor=4450` reached the end.

## 8. Series and episodes (fnf-series)

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|
| series likes / views / comments | `engagement.{like_count, view_count, comment_count}` (list only) | `GW/fnf-series/series?limit=100` | yes | same | yes (2026-03-18 series: 534/383 likes) | **live** | `scrape projects --what series --public-series`; `scrape site --what originals` |
| votes / subscribers | `vote_count`, `subscriber_count`, `engagement_score` | list + `/series/{slug}` | yes | same | yes | | `vote_count`, `subscriber_count` |
| episode likes / dislikes / views | `episodes[].like_count`, `dislike_count`, `view_count` | same | yes | same | yes | live | site originals |
| **personal** | `is_vote_triggered`, `is_notify_triggered`, `episodes[].like_mark` | same | false/null | identical (not populated) | | | not exported |

Single page (`total` 35): complete. Live: 2.1 min apart, 8/35 changed (views), e.g. views 1 287 330 → 1 287 331.

## 9. Rooms

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Collected by |
|---|---|---|---|---|---|
| followers / works | `followers_count`, `works_count`, `works_counts{blog_post,project_publication,shot}` | `GW/fnf-community/rooms?limit&cursor` (`total` 88) | yes | **logged in adds personal `is_followed`, `join_requested`** | `scrape site --what room-list` |
| posts / discussions | `posts`, `discussions` | `/fnf-community/publications/room-stats?room_id` | yes | same | `--what room-list` |
| room item likes / views | `item.likes_count`, `item.views_count` (+ personal `item.liked_by_me`) | `/fnf-community/rooms/{id}/items?limit` | yes | `liked_by_me` null → false | `--what room-content` |
| discussion posts | as §4 | `/fnf-community/publications/feed?room_id&kind=discussion` | yes | same | `--what room-content` |

## 10. Blog / community user posts

| Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old | Collected by |
|---|---|---|---|---|---|---|
| likes / views | `likes_count`, `views_count` | `GW/fnf/blog/posts/recommended?size<=50&cursor`, `/fnf/community/discovery/talents/blog-posts`, `/fnf/blog/public/posts/{id}` | yes | same; personal `liked_by_me` null → false | yes (older pages have more likes: page 6 → 27/50 > 0) | `scrape blog --what community` / `talents` |

CMS blog posts (`/blog/<slug>`) have no counts. Paging: 8 × 50 sequential pages covered only 2026-11-17…26; the cursor
is base64 `{after:[ts,id],context}`, a crafted older `after` returns empty → **old posts only by sequential paging**.

## 11. Apps / presets / MCP

| Content | Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Collected by |
|---|---|---|---|---|---|---|
| Community apps marketplace | views / likes / dislikes / remixes / credits spent | `views_count`, `likes_count`, `dislikes_count`, `remixes_count`, `credits_usage` | `GW/fnf-apps-marketplace/api/v1/apps/community?limit≤100&offset&sort` (`next_offset`) | yes | same; personal `my_reaction` stays null | `scrape studios --what apps` → `apps.engagement.{views, likes, dislikes, remixes, credits_usage}` (+ `--apps-sort`) |
| Community games | plays / unique players / remixes | `plays_count`, `unique_players_count`, `remixes_count` | `GW/fnf-skills-marketplace/api/v1/games/community?limit&offset` | yes | same | `scrape studios --what games` → `plays`, `unique_players`, `remixes` |
| Skills marketplace (community) | installs / unique users / usage | `installs_count`, `unique_users_count`, `usage_count` | `GW/fnf-skills-marketplace/api/v1/skills/community?limit&cursor` | yes | same (`usage_total/usage_personal` empty, personal: dropped) | `scrape studios --what skills` → `installs`, `unique_users`, `usage` |
| AI employees marketplace | installs / unique users / usage | same fields | `GW/fnf-skills-marketplace/api/v1/ai-agents/community?limit&cursor` | yes | same; `owned_by_current_user`, `installed_*` per viewer (dropped) | `scrape studios --what employees` |
| Studio galleries (Marketing Studio, Cinema Studio, Canvas, AI influencer, …) | views / likes; comments | `publication.views_count`, `likes_count`; comment `like_count`, `dislike_count`, `reply_count` | `GW/fnf/publications/community/{approved,trending}?model=…`; `fnf-community /entities/generation_publication/{id}/comments` | yes | same; `is_liked_by_user` / `is_mine` per viewer (dropped) | `scrape studios --what galleries [--with-comments]` → `gallery_items.engagement`, `comments` |
| `/apps/*` app pages | — | none | SSR | — | — | `scrape site --what apps` (no counts) |
| Viral-hub presets | — | none (no uses/likes) | `GW/fnf/viral-hub/presets/all` | — | — | `scrape catalog` |
| MCP skills / bundles | — | none (`installations`, `view_label` are UI text) | SSR `/mcp/*` | — | — | `scrape site --what mcp` |
| Creators | aggregate likes / views / followers | `likes_count`, `views_count`, `followers_count` | community discovery | yes | same | `scrape community --feeds creators\|talents` |

Apps marketplace: offsets 200, 1000, 3000 → 50 items each (`published_at` back to 2026-07-07; at offset 1000 only
2/50 have likes > 0); end not reached. Later the same day: ≈ 59,560 listings by offset binary search (`sort=newest`),
`limit` up to 100; games 1,299, skills 632, employees 296 (`docs/scrapers/studios.md` §1). Apps, games, skills and
employees have **no comment API**; only gallery generations do (`generation_publication`).

## 12. Showcase items (`scrape showcase`)

| Content | Metric | API field | Endpoint | Public anon? | Anonymous vs logged in | Old items | Live/frozen | Collected by |
|---|---|---|---|---|---|---|---|---|
| Video-explore community trends | likes | `likes_count` (item), `variants[].publication.likes_count` | `cms.higgsfield.ai/higgsfield-multiplier/video-explore/v2?source=community&sort=new\|trending&cursor=<page>` | yes | same for the same URL (the app adds `user_id` for a personalised trending feed and checks *my* likes with a token call `checkPublicationLikes` — personal, not fetched) | yes: page 1200 → 15/20 > 0; last page 2466 → 17/20 | unchanged in 2.2 min; CMS like count equalled `/fnf/publications/{id}` `likes_count` for a sampled item (mirror of the live counter) | `scrape showcase --what explore` → `explore_items.engagement.likes`, `explore_variants.publication_engagement` |
| | views / comments / times made | `views_count`, `comments_count`, `times_made` | same | fields present | same | **null / 0 / null** on most items (only trending/high items have values, e.g. 27 898 views, 16 comments, 10 463 made) | | `engagement.views/comments/uses` |
| Curated trends (`source=higgsfield`) | — | no engagement fields | same | — | — | — | — | — |
| Effect samples, canvas templates, editing-room examples/projects, Property Studio, API models, cinema controls, faceless/Intone/Seedance/motion-control showcases | — | none | | — | no difference | — | — | — |

Paging: page-number cursor with `total` (49 317–49 346 during the day); `cursor=2466` → 20 items, `cursor=2470` →
empty, so the oldest page is one request away. `sort=popular` → 422 (only `trending`, `new`).

## 13. Rate limits and caps

- No 429 or bot-protection responses at ~1 request/s on fnf, fnf-community, fnf-series, fnf-apps-marketplace, CMS.
- Deep paging always ended with `200` + empty + `has_more:false` / null cursor — never an error.
- Page-size caps (422 above): trending / model-x / shots ≤ 50; submissions / entries ≤ 100; explore fixed 20.

## 14. How to track likes over time

1. **Re-scrape on a schedule** with the same options (e.g. daily `scrape community`, `scrape projects --what
   publications,entries`, `scrape showcase --what explore --explore-pages 0`). Every run is a timestamped folder.
2. **Merge each snapshot**: `python scripts/merge_generations.py <runs of day N> --out runs/gi_dayN` → one row per
   generation (`key` = `job:<id>` or `media:<id>`), best likes/views/comments across sources.
3. **Diff**: `python scripts/merge_generations.py <runs of day N+1> --out runs/gi_dayN1 --compare
   runs/gi_dayN/generations_index.json` adds `likes_delta` / `views_delta` per key. Non-generation content (posts,
   series, projects) can be diffed the same way on their stable `id` columns (`pandas.merge` on `post_id`,
   `publication_id`, `series id`).
4. Counts are live, so snapshot time matters: compare runs at the same hour, and keep `scraped_at` (every row has it).
   Append the deltas to a history table (append-only, like price history) rather than overwriting.

Personal fields (`is_liked_by_user`, `liked_by_me`, `is_liked`, `my_vote`, `like_mark`, `my_reaction`,
`is_followed`, `join_requested`, `is_mine`, `is_subscribed`, `watch_*`) describe the logged-in viewer. They are only
non-null with a session, are never needed for public engagement, and are not exported by default.
