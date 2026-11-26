---
name: reverse-engineer-site
description: Use when starting to scrape a new website or page — recon how it works, find its hidden JSON/API endpoints, embedded state (__NEXT_DATA__ etc.), auth/tokens and pagination, and document them before writing a spider.
---

# Reverse-engineer a site before scraping it

Full reference: `.claude/docs/reverse-engineering.md`. Follow these steps in order and write findings down.

**Higgsfield.ai:** don't start from scratch. Use `.claude/docs/higgsfield-re-playbook.md` (how) and
`.claude/docs/higgsfield-re-checkpoint.md` (where we are), or the `continue-reverse-engineering` skill.

1. **Permissions** — fetch `robots.txt`, `sitemap.xml`; note Disallow/Crawl-delay; check ToS. Stop and tell the
   user if the target data is disallowed, behind a login they don't own, or paywalled.
2. **Raw vs rendered** — `scrapy fetch --nolog <url> > samples/<site>/page.html`. Search it for a known on-page
   value (price, plan name). Decide: in markup / in `<script>` JSON / absent (→ XHR).
3. **Stack fingerprint** — look for `__NEXT_DATA__`, `self.__next_f`, `__NUXT__`, `__APOLLO_STATE__`,
   `ld+json`, `/wp-json`, Shopify `.json`, Algolia hosts. Use the table in the reference doc.
4. **Endpoints** — if data is loaded via XHR: ask the user for a "Copy as cURL" / HAR from DevTools, or capture
   with Playwright (`page.on("response")`) if available. Grep JS bundles for `/api/`, `graphql`, `sha256Hash`, `apiKey`.
5. **Replay minimally** — `scrapy shell` + `fetch(scrapy.Request.from_curl(...))`; strip headers one at a time
   until it breaks; record the minimal set and where each token comes from.
6. **Pagination & limits** — identify page/offset/cursor/next-URL pattern, max page size, stop condition, 429 behaviour.
7. **Document** — write `docs/endpoints/<site>.md` using the endpoint template; save 3+ raw responses to
   `samples/<site>/`; infer a schema with `genson`.
8. **Design the schema** — map responses to entities per `.claude/docs/schema-design.md` (natural keys,
   nest vs split, Decimal + ISO currency, raw + cleaned fields).
9. Only then write the spider (see `scrape-spider` skill). Prefer API > embedded JSON > HTML > browser.

Never build anti-bot evasion, bypass auth/paywalls, or use non-public credentials.
