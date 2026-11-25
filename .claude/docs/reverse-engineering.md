# Reverse-Engineering a Website for Data Extraction

**Core rule:** HTML is the last thing to parse. Page data almost always reaches the browser as JSON — embedded
in a `<script>` tag or fetched via XHR/fetch. Find that source, replay it with the minimum needed, parse JSON.

**Preference order** (most stable/cheapest first):
1. Documented/public API or feed (RSS, sitemap)
2. Hidden JSON API used by the frontend (REST, GraphQL, Algolia…)
3. JSON embedded in HTML (`__NEXT_DATA__`, `__NUXT__`, `ld+json`…)
4. HTML selectors (CSS/XPath)
5. Headless browser (scrapy-playwright) — only when requests can't reasonably be reproduced

---

## 1. Recon workflow

**Step 0 — what's allowed:** `GET /robots.txt` (Disallow, Crawl-delay, `Sitemap:` lines), `GET /sitemap.xml`
(often lists every product URL with `lastmod` → `SitemapSpider`), read the ToS.

**Step 1 — view-source vs rendered DOM.** `view-source:` (Ctrl+U) = what Scrapy sees; Elements = DOM after JS.
Pick a distinctive on-page value (price, SKU) and Ctrl+F in view-source:
- found in markup → server-rendered; selectors work (still check for a cleaner JSON copy in `<script>`)
- found inside `<script>` → embedded state (§2)
- not found → loaded after render via XHR → Network tab
- Also: DevTools → Ctrl+Shift+P → "Disable JavaScript" → reload.
- See what Scrapy gets: `scrapy fetch --nolog URL > page.html` or `scrapy shell URL` + `view(response)`.

**Step 2 — DevTools Network tab.**
- Enable **Preserve log** + **Disable cache**, hard reload, then interact (scroll, paginate, filter, search, open detail).
- Filter **Fetch/XHR** (also Doc for HTML fragments, WS for websockets); text filter `api`, `graphql`, `json`, `search`.
- **Ctrl+F inside the Network panel searches ALL request/response bodies** — search the known value to find the carrier request instantly.
- Per request: Headers, Payload, Preview/Response (JSON shape), **Initiator** (JS call stack → set breakpoints to see how params/tokens are built).
- Right-click → **Copy as cURL (bash)** → confirm it works in a terminal before writing code.
- Application tab: Cookies, Local/Session Storage, IndexedDB for tokens.
- Console: `__NEXT_DATA__`, `window.__NUXT__`, `window.__INITIAL_STATE__`, `window.__APOLLO_STATE__`.

**Step 3 — identify the stack** (tells you where to look):

| Signal | Stack | Where data is |
|---|---|---|
| `<script id="__NEXT_DATA__">`, `/_next/static/` | Next.js Pages Router | `__NEXT_DATA__`, `/_next/data/<buildId>/<path>.json` |
| `self.__next_f.push(` | Next.js App Router (RSC) | flight chunks → `njsparser` |
| `window.__NUXT__`, `#__NUXT_DATA__`, `/_nuxt/` | Nuxt | `__NUXT_DATA__` JSON |
| `/page-data/<path>/page-data.json` | Gatsby | that JSON |
| `__APOLLO_STATE__`, `/graphql` | Apollo/GraphQL | normalized cache / GraphQL endpoint |
| `/products/<handle>.json`, `/products.json?page=N` | Shopify | append `.json` |
| `/wp-json/wp/v2/...` | WordPress | REST API |
| `*-dsn.algolia.net` | Algolia | search API with public key |

Wappalyzer and `x-powered-by`/`server` headers also help.

## 2. Where data hides

```python
import json, chompjs

# Next.js Pages Router
data = json.loads(response.css("script#__NEXT_DATA__::text").get())
page_props, build_id = data["props"]["pageProps"], data["buildId"]

# JSON-LD (schema.org Product/Offer) — may be multiple blocks
for raw in response.xpath('//script[@type="application/ld+json"]/text()').getall():
    obj = json.loads(raw)

# JSON in data-* attributes
json.loads(response.css("[data-product]::attr(data-product)").get())

# JS object literals (unquoted keys, single quotes, trailing commas)
js = response.xpath('//script[contains(., "__INITIAL_STATE__")]/text()').get()
state = chompjs.parse_js_object(js)
```

- Other names to grep: `__INITIAL_DATA__`, `__PRELOADED_STATE__`, `__remixContext`, `__sveltekit`, `var product =`, `dataLayer`.
- `__NUXT__` IIFE with minified args → chompjs can't resolve vars; use `__NUXT_DATA__` or evaluate in a browser.
- Apollo cache is normalized (`Product:123`, `__ref` pointers) — resolve refs yourself.
- Next.js App Router: no `__NEXT_DATA__`; data in `self.__next_f.push([1,"..."])` → `njsparser.BeautifulFD(html)`.
- Fallbacks: `js2xml`, regex + `json.loads`. `nested_lookup` finds a key at any depth.

**Next.js data route:** `/product/abc` → `GET /_next/data/<buildId>/product/abc.json` returns `{"pageProps": ...}`.
`buildId` changes every deploy → re-read per crawl; 404 = stale buildId.

**REST APIs:** `/api/`, `/v1/`, `/search`, `?format=json`, `.json`. Pagination: `page/per_page`, `offset/limit`,
cursor (`after`, `cursor`, `next_page_token`, `pageInfo.endCursor`), or `next` URL. Try a larger page size, politely.

**GraphQL:** `POST /graphql {"operationName","variables","query"}` — copy the query from the payload.
- Introspection `{"query":"{__schema{types{name fields{name}}}}"}` (often disabled in prod).
- Persisted queries (APQ): `extensions={"persistedQuery":{"version":1,"sha256Hash":"..."}}`, often GET; replay the
  hash with your own `variables`. Hash = sha256 of query text; find it in captured requests or JS bundles
  (`sha256Hash`, `operationName`). `PERSISTED_QUERY_NOT_FOUND` = unknown hash.

**Algolia (and Typesense, Constructor.io, Searchspring, Klevu…):** `POST https://<APPID>-dsn.algolia.net/1/indexes/*/queries`
with `x-algolia-application-id` + `x-algolia-api-key` (public search-only key) and
`{"requests":[{"indexName":"...","params":"query=&hitsPerPage=1000&page=0"}]}`. ~1000-hit cap → slice with `facetFilters`/`numericFilters`.

**WebSockets:** DevTools WS → Messages. Scrapy has no WS support — use `websockets`/`aiohttp`. Look for a REST snapshot endpoint first.

**JS bundles & source maps:** grep `.js` chunks for `"/api/`, `fetch(`, `axios`, `baseURL`, `graphql`, `apiKey`,
`x-api-key`, `sha256Hash`, `Authorization`, `Bearer`. A reachable `//# sourceMappingURL=` exposes the original
source (DevTools Sources). Keys shipped to every browser are public by design — use only for the same read access
the frontend gets.

## 3. Replaying requests

```python
req = scrapy.Request.from_curl(
    """curl 'https://example.com/api/items?page=1' -H 'accept: application/json'""",
    callback=self.parse_api)                      # extra kwargs → Request(); unknown curl flags ignored
# scrapy shell: fetch(scrapy.Request.from_curl("...")); response.json()
```

Converters: curlconverter.com (`requests`/`httpx`), curl2scrapy.

**Minimize headers by elimination** (bisect until it breaks). What usually matters:
- method + exact body format — `JsonRequest(url, data=...)` vs `FormRequest(url, formdata=...)` are not interchangeable
- `Accept: application/json` (some endpoints return HTML without it)
- `Referer` / `Origin`
- `X-Requested-With: XMLHttpRequest`
- custom headers: `X-CSRF-Token`, `X-Api-Key`, `Authorization: Bearer …` (missing → 400/401/403)
- consistent realistic `User-Agent`
- usually droppable: `sec-ch-ua*`, `sec-fetch-*`, `priority`, `accept-language`, most cookies

**Tokens / cookies / CSRF:** find each dynamic value's origin — Network search, view-source, JS, earlier
`Set-Cookie`, Local Storage, `<meta name="csrf-token">`, hidden inputs, embedded JSON. Rarely-changing values
(app version) can be hard-coded; random IDs are often `uuid4()`. Pattern: GET HTML page → extract token → call API.
`CookiesMiddleware` keeps sessions; `meta={"cookiejar": n}` for separate sessions. Guest bearer tokens often come
from `/oauth/token`, `/guest/activate`, `/session` — refresh on 401.

**Parsing JSON:**
```python
data = response.json()
names = response.jmespath("items[*].name").getall()          # Scrapy ≥ 2.9
jmespath.search("data.products.edges[].node.{id:id,price:price.amount}", data)
Selector(text=data["html"]).css(".card")                     # API returning HTML fragments
```
CLI: `curl ... | jq '.data.items[0] | keys'`, `jq '[paths(scalars)]'` lists every leaf path.

## 4. Mapping the API — document every endpoint

Write each endpoint to `docs/endpoints/<site>.md`:

```
GET https://example.com/api/v2/search
  params:   q (str), page (int, 1-based), page_size (int, max 100), sort=price_asc|newest
  headers:  Accept: application/json; X-Api-Key: <from /static/js/main.*.js "apiKey">
  auth:     none | guest token from POST /api/session (TTL 1h)
  paging:   stop when len(items)==0 or page >= meta.total_pages
  response: {items:[{id,name,price:{amount,currency},url}], meta:{total,total_pages}}
  limits:   429 after ~X req/min; Retry-After honored
  observed: YYYY-MM-DD
```

Save raw sample responses to `samples/<site>/<endpoint>_<n>.json`, then infer a schema:

```python
from genson import SchemaBuilder
b = SchemaBuilder()
for obj in samples: b.add_object(obj)
print(b.to_json(indent=2))       # shows optional/nullable fields → drive pydantic models (see schema-design.md)
```

**Tools:** HAR export (Network → "Save all as HAR with content"; analyze with `haralyzer` or
`jq '.log.entries[] | select(.response.content.mimeType|test("json")) | .request.url'`), mitmproxy/mitmweb
(also for mobile apps — often cleaner APIs), Burp Repeater, Postman/Insomnia/Bruno.

**Playwright capture** (when traffic is too dynamic to click through):
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(record_har_path="capture.har")
    page = ctx.new_page()
    def on_resp(r):
        if "application/json" in (r.headers.get("content-type") or ""):
            print(r.request.method, r.url, r.request.post_data)
    page.on("response", on_resp)
    page.goto("https://example.com/pricing"); page.mouse.wheel(0, 5000); page.wait_for_timeout(3000)
    ctx.close(); b.close()
```

**scrapy-playwright** (only for pages that truly need a browser):
```python
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# yield scrapy.Request(url, meta={"playwright": True})
```
Hybrid: use the browser once to discover endpoints / harvest a token, then plain Scrapy requests.

## 5. Anti-bot (awareness only)

- Detection layers: IP reputation/rate, header order/consistency, TLS (JA3/JA4) + HTTP/2 fingerprint, JS
  challenges (Cloudflare, Akamai, DataDome, HUMAN), browser fingerprinting.
- Python TLS stacks don't look like Chrome — a perfect header copy can still 403. `curl_cffi`
  (`impersonate="chrome"`) / `scrapy-impersonate` exist for this.
- Symptoms: 403/503 challenge page, `cf-ray` header, `__cf_bm`/`_abck`/`datadome` cookies.
- Heavy anti-bot is the site saying "no". Prefer official APIs / data licensing; don't build evasion tooling.

## 6. Ethics & legal (non-negotiable)

- `ROBOTSTXT_OBEY = True`; read ToS; public data only.
- Never bypass auth, paywalls or access controls you lack rights to; never use leaked/admin keys.
- Throttle (AutoThrottle, `DOWNLOAD_DELAY ≥ 1`, low per-domain concurrency), honor `429`/`Retry-After`,
  `HTTPCACHE_ENABLED = True` during development.
- Minimize personal data (GDPR/CCPA). Hidden APIs aren't contracts — monitor and validate.

## 7. Scrapy patterns

### A. `__NEXT_DATA__` + `/_next/data` route
```python
class NextDataSpider(scrapy.Spider):
    name = "nextdata"
    start_urls = ["https://example.com/products"]

    def parse(self, response):
        raw = response.css("script#__NEXT_DATA__::text").get()
        if not raw:
            self.logger.warning("No __NEXT_DATA__ (App Router?) on %s", response.url)
            return
        data = json.loads(raw)
        props = data["props"]["pageProps"]
        yield from self.items_from(props)
        for page in range(2, props.get("pagination", {}).get("totalPages", 1) + 1):
            yield scrapy.Request(
                f"https://example.com/_next/data/{data['buildId']}/products.json?page={page}",
                callback=self.parse_data_route, headers={"x-nextjs-data": "1"})

    def parse_data_route(self, response):
        yield from self.items_from(response.json()["pageProps"])
```

### B. JSON API with offset pagination (+ GraphQL cursor variant)
```python
class ApiSpider(scrapy.Spider):
    name = "api"
    api = "https://example.com/api/v2/search"
    page_size = 50
    headers = {"Accept": "application/json", "Referer": "https://example.com/search"}

    async def start(self):                     # Scrapy ≥ 2.13; else start_requests()
        yield self.page_request(0)

    def page_request(self, offset):
        return scrapy.Request(f"{self.api}?q=&offset={offset}&limit={self.page_size}",
                              headers=self.headers, cb_kwargs={"offset": offset})

    def parse(self, response, offset):
        data = response.json()
        items = data.get("items", [])
        yield from (self.to_item(it) for it in items)
        if items and offset + self.page_size < data.get("meta", {}).get("total", 0):
            yield self.page_request(offset + self.page_size)

# GraphQL cursor:
# yield JsonRequest(GQL, data={"operationName": "Products", "variables": {"first": 50, "after": cursor}, "query": Q})
# if page["pageInfo"]["hasNextPage"]: request again with after=page["pageInfo"]["endCursor"]
```

### C. Token bootstrap + `from_curl`
```python
def parse(self, response):                       # HTML page sets cookies + exposes token
    token = response.css('meta[name="csrf-token"]::attr(content)').get()
    req = scrapy.Request.from_curl(CURL, callback=self.parse_api)
    req.headers["x-csrf-token"] = token          # replace the stale captured value
    yield req
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| HTML instead of JSON | missing `Accept: application/json` / `X-Requested-With`, or redirected to challenge/login |
| 400 | wrong body format (JSON vs form) or missing param |
| 401/403 | missing token/cookie/Referer/Origin, or TLS fingerprint |
| 404 on `/_next/data` | stale `buildId` |
| works once then fails | token/signature expired or rate limited (429) — slow down |
| 200 but empty | locale/region/currency cookie or filter params differ |

## Sources
- https://docs.scrapy.org/en/latest/topics/dynamic-content.html
- https://scrapfly.io/blog/posts/how-to-scrape-hidden-apis
- https://scrapfly.io/blog/posts/how-to-scrape-hidden-web-data
- https://www.trickster.dev/post/scraping-nextjs-web-sites-in-2025/
- https://www.apollographql.com/docs/apollo-server/performance/apq
- https://scrapy-playwright.readthedocs.io/en/latest/
- https://curl-cffi.readthedocs.io/
- https://curlconverter.com/
