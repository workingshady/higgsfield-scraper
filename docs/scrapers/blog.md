# `blog` scraper

`python -m higgsfield_scraper scrape blog [options]` collects Higgsfield's written content, metadata **and** full
article text:

| Collection (dataset key) | Kind | Source | Live count (2026-11-25) |
|---|---|---|---:|
| `posts` | `blog_post` | `/blog/<slug>` SSR pages (Sanity CMS), discovered via `/blog` + `/blog/sitemap.xml` | 342 |
| `authors` | `blog_author` | `/blog/author/<slug>` pages (+ authors referenced by posts, e.g. the "Higgsfield" team) | 5 |
| `talent_posts` | `blog_talent_post` | API `GET /community/discovery/talents/blog-posts` + Yjs body (`content_url`) | 57 |
| `community_posts` | `blog_community_post` | API `GET /blog/posts/recommended` + Yjs body — **opt-in** (`--what community`) | ≈50/day, not totalled |
| `help_articles` | `blog_help_article` | `/creator-hub/help-center/<category>/<slug>` and `/enterprise-help-center/<category>/<slug>` | 75 + 30 |
| `case_studies` | `blog_case_study` | `/creator-hub/case-studies/<slug>` | 24 |
| `changelog` | `blog_changelog_entry` | `/creator-hub/changelog` (all entries on one page) | 189 |

`blog_post_content` is an internal kind (decoded body of a talent/community post) that `build_dataset` merges into
its post.

## Sources (reverse-engineered, GET only)

### SSR pages: TanStack Start router state (preferred over HTML)
All `higgsfield.ai` content pages are TanStack Start SSR. The HTML embeds the router state as a
[seroval](https://github.com/lxsmnsyc/seroval)-serialized JS literal:
`<script>$_TSR.router=($R=>$R[0]={manifest:…,matches:[…],dehydratedData:…})($R["tsr"])</script>`.
Each `matches[i]` is `{i: routeId, s: status, l: loaderData}`; the innermost route's `l` holds the page's CMS data:

| Page | Route id (suffix) | Loader data |
|---|---|---|
| `/blog` | `#blog##blog#` | `mainPost`, `featuredPosts[]`, `categoryAndPosts[{category, posts[]}]` (all 337 posts, 6 categories) |
| `/blog/<slug>` | `#blog#$id#…` | `entry: {type: "post", post: {id, title, breadcrumbTitle, slug, description, seoDescription, content (HTML), mainBannerUrl, author, category, cta, hero{media}, headings[], relatedPosts[], readingTime, dateCreated, dateModified, publishDate, seoPublishDateISO, aboutSection, faqSection, banner, cardUrl}}`, `cmsLocalization`; `type: "category"` for `/blog/guides` etc. |
| `/blog/author/<slug>` | `#author#$authorId#…` | `screen: {author: {id, slug, fullName, position, description, photoUrl, hrefLinkedin}, posts[]}` |
| `/creator-hub/help-center` | `#help-center##…` | `homeScreen`, `navigation.groups[{category, articles[]}]` (12 categories, 75 articles) |
| `/creator-hub/help-center/<cat>/<slug>` | `#$categorySlug#$articleSlug#…` | `article: {id, slug, title, description, category, author, content (HTML), markdown, headings[], faqSection, relatedPosts[], readingTime, dateCreated, dateModified, seoTitle, seoDescription, searchKeywords[], order}`, `markdownLink` (`<url>.md`), `fullDocsLink` (`/llms-full.txt`) |
| `/creator-hub/case-studies` | `#case-studies##…` | `featuredCaseStudy`, `categories[{category, posts[]}]` (24 + 0) |
| `/creator-hub/case-studies/<slug>` | `#case-studies#$id#…` | `entry.post` like a blog post + `heroMetrics[]`, `toolsUsed[]`, `aboutSection{title,intro,facts}`, `sidebarCta` |
| `/creator-hub/changelog` | `#changelog#…` | `categories[]` (announcement, release, feature, improvement, fix), `entries[{id, anchor, title, summary, content (HTML), releaseDate, dateModified, searchKeywords, category, chips[]}]` (189) |
| `/enterprise-help-center` | `#enterprise-help-center##…` | `name`, `description`, `items[{name, path}]` (30 articles) |
| `/enterprise-help-center/<cat>/<slug>` | `#$categorySlug#$articleSlug#…` | `article: {…, cardTitle, cardImageUrl, lastUpdated, content, markdown, headings, relatedArticles}`, `previousArticle`, `nextArticle`, `contentLanguage`, `markdownLink` |

The parser for this format is `scrapers/blog/tsr.py` (handles `$R[n]=` definitions/back-references, `!0/!1`,
`void 0`, `\xNN`/`\uNNNN` escapes, `new Date/Map/Set`; parsing stops before `dehydratedData`, which holds
JS functions). Each page's `<head>` is also read (title, description, canonical, og:image, JSON-LD — breadcrumbs and
`datePublished`/`dateModified` fallbacks). Pages without router state fall back to the `<article>` HTML.

### Sitemaps
`/blog/sitemap.xml` (352 URLs: posts, 6 category pages, 4 authors; `<lastmod>` per post),
`/creator-hub/sitemap.xml` (116: help center index + 12 categories + articles, case studies index + 2 category pages +
24 studies, changelog), `/enterprise-help-center/sitemap.xml` (35). The spider takes the union of index pages and
sitemaps (deduped by path), skips category listing pages, and records `<lastmod>` as `sitemap_lastmod`.

### JSON API (`https://fnf-api-gw.higgsfield.ai/fnf`, public)
| Endpoint | Params | Notes |
|---|---|---|
| `GET /community/discovery/talents/blog-posts` | `size` (≤ 50, larger → 422), `cursor` | `{items[], next_cursor}`; ~57 posts (2 pages) |
| `GET /blog/posts/recommended` | `size` (≤ 50), `cursor` | community (user) blog feed, very large (≈ 50 posts/day); opt-in |
| `GET /blog/public/posts/{uuid}` | | single post (same item shape); slug → 422 (must be a UUID). Not needed (lists carry every field) |
| `GET /blog/{username}/posts`, `/blog/{username}/posts/{slug}` | | per-user posts (seen in JS, not used) |
| 🔒 `GET /blog/posts` | | 401 without login — not used (sitemaps + public feeds cover the content) |

Item fields: `id, state, title, subtitle, slug, cover{id,url,type,width,height}, tags, related_posts, reading_time,
reading_time_minutes, breadcrumb_label, pinned_position, likes_count, views_count, liked_by_me, folder_id,
content_url, draft, published_at, created_at, updated_at (epoch seconds), author{id, username, avatar_url},
review_state, flagged_media`. Pagination stops when `next_cursor` is null (or `--max-pages`, `--max-items`).
The page URL of a post is `https://higgsfield.ai/@<username>/blogs/<slug>` (rendered client-side only).

### Community/talent post bodies: Yjs binary
`content_url` (`https://cdn.higgsfield.ai/blog/<uuid>.bin`, `application/octet-stream`) is a **Yjs v1 document
update** (`Y.encodeStateAsUpdate`) of a **Lexical** editor (`@lexical/yjs` binding): element nodes are `Y.XmlText`
with `__type`/`__tag`/`__listType`… attributes, text nodes are a `Y.Map` (`__type: "text"`, `__format` bitmask)
followed by the characters, decorators (`asset-embed`: image/video with `url` or only a media `refId`) are
`Y.XmlElement`. `scrapers/blog/yjs.py` is a dependency-free decoder (lib0 varints, all content types, YATA
integration, delete set) that rebuilds the Lexical tree; `content.py` renders it to Markdown/text.

### Locales
`--locale es|ja|ko|de` prefixes page paths (`/es/blog/<slug>`, …). Only some posts are translated
(`localization_status: "localized"`); others are served in English (`"degraded"`). The help centers report
`cmsLocalization`/`contentLanguage`. API feeds are not localized.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--what` | `blog,talents,help,enterprise-help,case-studies,changelog` | sections; `all` = default set; `community` adds the large recommended feed |
| `--with-content` / `--no-content` | on | `--no-content`: metadata from index pages / feeds only (~10 requests): no per-article pages, no Yjs bodies, text fields empty (`record_source: "index"`) |
| `--locale` | `en` | `en, es, ja, ko, de` |
| `--tags` | | keep items whose category slug/title, tags, or changelog chips match (case-insensitive, comma list) |
| `--since` | | keep items whose `published_at`/`released_at`/`updated_at`/`created_at` (first present) ≥ date; undated items are kept |
| `--include-author-avatars` | off | keep community/talent authors' `avatar_url` (personal data) |
| `--no-markdown` | | don't write `output/articles/` |
| common | | `--max-items N` caps **each** collection (detail pages beyond N are not requested), `--max-pages` (API feeds), `--page-size` (≤ 50), `--delay`, `--download-media thumbs` (covers/cards/author photos) / `full` (+ hero + article images/videos) / `all` (+ embeds) … |

## Fields

Every content kind has the **body fields**: `content_format` (`html` | `markdown` | `lexical`), `content_html`
(CMS HTML), `content_markdown`, `content_text` (Markdown stripped), `content_blocks` (Lexical tree; talent/community),
`word_count`, `headings[{level, text, anchor}]` (CMS headings with anchors when available), `links[{url, text,
internal}]`, `images[{url, alt, kind, ref_id}]`, plus `extra` (unmapped source keys) and `source` (Provenance).

* `blog_post`: `post_id, slug, url, locale, title, breadcrumb_title, subtitle (hero lead), description,
  seo_description, category{id,slug,title,description}, tags ([category slug]), author{id,slug,name,position},
  cover_url, card_url, banner_image_url, hero_media_url/type/width/height, cta{title,description,text,link},
  reading_time, reading_time_minutes, published_at, created_at, updated_at, publish_date_label, likes_count/views_count
  (not exposed for CMS posts → null), related_posts[{id,slug,title,url,category_slug,published_at}],
  faq[{question,answer_text,answer_html}], about, localization_status, sitemap_lastmod, page_title, record_source`.
* `blog_author`: `slug, author_id, name, position, description, photo_url, linkedin_url, url, post_count, post_slugs,
  record_source (page | post)`.
* `blog_talent_post` / `blog_community_post`: `post_id, feed, slug, url, state, title, subtitle, tags,
  cover{…}, author{user_id, username, avatar_url (opt-in)}, reading_time(_minutes), likes_count, views_count,
  breadcrumb_label, pinned_position, folder_id, content_url, related_posts, review_state, flagged_media,
  published_at, created_at, updated_at, content_status (ok | not_fetched | empty | error: …)`.
* `blog_help_article`: `article_id, section (creator-hub | enterprise), slug, url, locale, category_slug, category{…,
  icon, order}, title, card_title, description, seo_title, seo_description, search_keywords, order, author,
  card_image_url, reading_time(_minutes), created_at, updated_at, faq, related_articles, previous_slug, next_slug,
  markdown_url, content_language, localization_status, breadcrumbs, sitemap_lastmod, page_title, record_source`.
  Help-center bodies come as **Markdown from the CMS** (`content_format: markdown`).
* `blog_case_study`: blog-post fields + `hero_metrics[{label,value}]`, `tools_used[{name,slug,icon_url}]`,
  `about_title, about_intro, about_facts`.
* `blog_changelog_entry`: `entry_id, anchor, url (#anchor), title, summary, category, category_slug,
  chips[{id,slug,title}], search_keywords, released_at, updated_at`.

## Outputs (`runs/<run>/output/`)

* `dataset.json`, `json/{posts,authors,talent_posts,community_posts,help_articles,case_studies,changelog,summary,meta}.json`
* `csv/`: one table per collection (long text columns included) + child tables
  `post_tags, {post,talent_post,community_post,help_article,case_study,changelog}_{headings,links,images},
  {post,case_study,help_article}_related, {post,help_article,case_study}_faq, case_study_metrics, case_study_tools,
  changelog_chips, user_post_blocks` (Lexical JSON), `run_meta`. Every JSON leaf has a CSV column
  (`tests/test_blog.py::test_csvs_contain_every_json_field`).
* `summary.md`, `schema/dataset.schema.json`
* `articles/<collection>/<slug>.md` — each article as Markdown with a YAML-ish front matter (help articles are named
  `<section>__<category>__<slug>.md`).

## Raw envelopes (`raw/`, input of `normalize`)

Non-JSON responses are converted by the spider before archiving (the framework's `parse_api` expects JSON):

| Endpoint | `body` |
|---|---|
| SSR pages | `{"format": "tsr", "path", "sitemap_lastmod", "head": {title, lang, canonical, description, og_*, ld_json}, "matches": [{i, s, l}]}` — on detail pages the repeated listing data (`screen`, `navigation`) is dropped; `tsr_error` / `article_html` when the router state is missing |
| sitemaps | `{"format": "sitemap", "urls": [{loc, lastmod}]}` |
| `post_content` | `{"format": "yjs", "content_url", "content_b64"}` (the untouched binary, base64) |

Parsers also accept a saved page as `{"html": "<!DOCTYPE html>…", "path": "/…"}` (used by
`tests/fixtures/blog/html__*.json`) and a sitemap as `{"xml": "…"}`. Feed pages are archived as
`talent_posts__page-N__size-50.json` (the ~250-char cursor stays in the URL, not the file name).

## Examples

```bash
python -m higgsfield_scraper scrape blog                                   # everything (~560 requests)
python -m higgsfield_scraper scrape blog --no-content --label meta         # metadata only (~10 requests)
python -m higgsfield_scraper scrape blog --what help,enterprise-help       # help centers only
python -m higgsfield_scraper scrape blog --what blog --since 2026-10-01 --tags comparisons
python -m higgsfield_scraper scrape blog --what community --max-pages 4    # 200 newest community posts + bodies
python -m higgsfield_scraper scrape blog --locale es --what blog
python -m higgsfield_scraper normalize --run runs/<run>                    # re-parse raw/ offline
```

## Live verification (2026-11-25)

`scrape blog --label blog-test --delay 0.5`: 542 responses, all HTTP 200, 0 validation drops, status `success`,
~16 min; 783k words of article text; 1,138 media blocks in blog posts, 475 in help articles. `normalize` of that
run reproduces the dataset offline. CMS pages embed media/prompts/code as HTML comments
(`<!--post-asset-block:{urlencoded JSON}-->`, `post-prompt-block`, `post-code-block`, `post-code-group`); they are
rendered into the Markdown and listed in `images`.

## Limits & gaps

* Blog (CMS) posts expose no likes/views; tags = category only.
* The community feed (`--what community`) has no total; it is paginated until `next_cursor` is null — use
  `--max-pages`/`--max-items`. Community/talent `asset-embed` nodes sometimes carry only a media `refId` (no URL):
  they are listed in `images` with `url: null, ref_id`.
* `/blog/posts` (full list incl. drafts/own posts) needs login and is not used; nothing else here needs a session.
* `/llms-full.txt` and `<help-article>.md` (`markdown_url`) exist and mirror the help-center Markdown; not fetched
  (the page already carries `markdown`).
* Localized runs: untranslated pages return English content flagged `localization_status: "degraded"`.
* `--max-items` is applied per collection by the spider (not globally).
* Raw archive: SSR pages are stored as extracted router state (~50–250 KB each), not as full HTML (0.3–1.7 MB);
  the framework's `http/` archive still holds the full bodies (use `--no-http-archive` to skip).
