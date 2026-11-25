---
name: scrape-spider
description: Use when writing or modifying a Scrapy spider, item, item loader, pipeline, or feed/database export in this project.
---

# Build a Scrapy spider (project conventions)

References: `.claude/docs/scrapy.md` (Scrapy mechanics), `.claude/docs/schema-design.md` (items/validation/storage),
`.claude/docs/reverse-engineering.md` (finding data sources). If the site hasn't been mapped yet, run the
`reverse-engineer-site` skill first.

Checklist:
1. **Source choice** — use the endpoint doc in `docs/endpoints/<site>.md`; prefer JSON API → embedded JSON → HTML.
2. **Schema first** — define/extend pydantic models in `higgsfield_scraper/schemas/` (one module per entity,
   registered in `MODEL_BY_KIND`); Scrapy items in `items.py` are generated from them.
   Every item: stable hashed ID, `source_url`, `scraped_at` (UTC ISO 8601), `schema_version`.
   Money = Decimal string + ISO 4217 currency + `price_raw`. `None` = missing, `[]` = empty.
3. **Spider** — `scrapy genspider`; `allowed_domains`; `response.json()` / `response.jmespath()` for APIs;
   ItemLoaders for HTML; `response.follow` + `cb_kwargs` between callbacks; one new item per record.
4. **Pagination** — next link / API next / fan-out from total pages; explicit stop condition.
5. **Pipelines** — order: clean (100) → pydantic validate (300, DropItem + stats) → dedup (400) → store (500+).
   Every `process_item` returns the item or raises `DropItem`. Credentials from env vars only.
6. **Export** — JSONL feed as raw archive (`data/%(name)s/%(name)s_%(time)s.jsonl`); DB upserts keyed on natural
   IDs; prices appended to history.
7. **Politeness** — robots.txt off by default (`--obey-robots` to enable), AutoThrottle, `DOWNLOAD_DELAY ≥ 1`, retry 429; `HTTPCACHE_ENABLED`
   during development.
8. **Verify** — `scrapy shell` for selectors; `scrapy crawl <name> -O tmp.jsonl -s CLOSESPIDER_ITEMCOUNT=20`;
   inspect output and stats (`item_scraped_count`, `item_dropped_count`, `validation/*`, error counts) before
   claiming it works.
