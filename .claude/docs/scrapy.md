# Scrapy Reference

Digest of The Python Scrapy Playbook (thepythonscrapyplaybook.com): beginner guide parts 1–4, Items,
feed exporters & DB pipelines, login, pagination, plus scrapy-redis docs (the playbook's Redis page
returned 502). Code is corrected where the guides had bugs — corrections are marked `# FIX`.

---

## 1. Setup & CLI

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows (Linux: source .venv/bin/activate)
pip install scrapy itemadapter
scrapy startproject <project>                         # creates scrapy.cfg + <project>/{items,middlewares,pipelines,settings}.py, spiders/
scrapy genspider <name> <domain>
scrapy crawl <name>                                   # run from project root
scrapy crawl <name> -o out.jsonl                      # APPEND
scrapy crawl <name> -O out.json                       # OVERWRITE
scrapy crawl <name> -O file:///abs/path/out.csv:csv   # explicit format
scrapy shell "https://example.com"                    # test selectors: response, fetch(url), view(response)
scrapy parse --spider=<name> -c parse_item <url>      # run one callback against one URL
scrapy check / scrapy list
```

Always prototype selectors in `scrapy shell` before writing spider code. Selectors are site-specific.

## 2. Spider anatomy

```python
import scrapy

class ProductSpider(scrapy.Spider):
    name = "products"
    allowed_domains = ["example.com"]          # blocks off-domain crawling
    start_urls = ["https://example.com/collections/all"]

    # or, for headers/meta/POST on the first request:
    # async def start(self):  (Scrapy >= 2.13)  /  def start_requests(self):
    #     yield scrapy.Request(url, callback=self.parse, headers={...}, meta={...})

    def parse(self, response):
        for card in response.css("product-item"):
            yield {
                "name": card.css("a.title::text").get(),            # first match or None
                "tags": card.css(".tag::text").getall(),            # list
                "url": response.urljoin(card.css("a::attr(href)").get()),
            }
        next_page = response.css('[rel="next"]::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)   # follow() handles relative URLs

    def parse_detail(self, response):
        ...  # pass data between callbacks with cb_kwargs={"product_id": pid}
```

- Selectors: `::text`, `::attr(x)`, `.attrib["href"]`, `.xpath(...)`, `.re(r"...")`, `.re_first(...)`.
- JSON responses: `response.json()`.
- Spider classes: `Spider`, `CrawlSpider` (+ `Rule(LinkExtractor(allow=..., deny=...), callback="parse_item", follow=True)`
  — never name a CrawlSpider callback `parse`), `SitemapSpider` (`sitemap_urls`, `sitemap_rules = [("/product/", "parse_product")]`).

## 3. Items

```python
# items.py
import scrapy

class ProductItem(scrapy.Item):
    name = scrapy.Field()
    price = scrapy.Field()
    url = scrapy.Field()
```

- Assigning an undeclared field raises `KeyError` — catches typos (`prce`).
- Spiders may also yield dicts, `@dataclass`, or `attrs` objects; access all uniformly via `itemadapter.ItemAdapter`.
- **Create a new item per record** inside the loop (guide bug: reused one instance for all products).
- Schema design / nesting / validation → see `.claude/docs/schema-design.md`.

## 4. ItemLoaders (clean at extraction time)

```python
# itemloaders.py
from itemloaders.processors import TakeFirst, MapCompose, Join, Identity, Compose
from scrapy.loader import ItemLoader
from w3lib.html import remove_tags

def strip(x): return x.strip() if isinstance(x, str) else x

class ProductLoader(ItemLoader):
    default_input_processor = MapCompose(remove_tags, strip)
    default_output_processor = TakeFirst()          # first non-empty value, else None
    price_in = MapCompose(remove_tags, strip, lambda x: x.replace("£", "").replace(",", ""))
    tags_out = Identity()                           # keep the list
    description_out = Join(" ")
```

```python
# spider
def parse(self, response):
    for card in response.css("product-item"):
        l = ProductLoader(item=ProductItem(), selector=card)
        l.add_css("name", "a.title::text")
        l.add_css("price", "span.price::text", re=r"[\d.,]+")
        l.add_value("url", response.urljoin(card.css("a::attr(href)").get()))  # FIX: don't blindly prefix base URL
        yield l.load_item()
```

- `<field>_in` / `<field>_out` naming; `MapCompose` applies each fn to each value; `TakeFirst` → scalar.
- Nested loaders: `nl = l.nested_css("div.footer"); nl.add_css("phone", "a.phone::text")`.
- Avoid whitespace-exact regexes on raw HTML — select the text node instead.

## 5. Item pipelines (clean → validate → dedup → store)

```python
from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

class PriceCleanPipeline:
    def process_item(self, item, spider):
        a = ItemAdapter(item)
        if not a.get("price"):
            raise DropItem(f"Missing price: {a.get('url')}")
        a["price"] = Decimal(a["price"])                     # money → Decimal, never float
        return item                                          # MUST return item (or raise DropItem)

class DuplicatesPipeline:
    def __init__(self):
        self.seen = set()
    def process_item(self, item, spider):
        key = ItemAdapter(item)["url"]
        if key in self.seen:
            raise DropItem(f"Duplicate: {key}")
        self.seen.add(key)
        return item
```

```python
ITEM_PIPELINES = {                       # lower number runs first (0–1000)
    "project.pipelines.PriceCleanPipeline": 100,
    "project.pipelines.DuplicatesPipeline": 200,
    "project.pipelines.PostgresPipeline": 300,
}
```

- Pipeline hooks: `open_spider(self, spider)`, `close_spider(self, spider)`, `from_crawler(cls, crawler)` (read settings).
- Item-type-specific logic: `if isinstance(item, PlanItem): ...` and pass others through untouched.
- In-memory dedup is per run only; persistent dedup belongs in the DB (UNIQUE + upsert).

## 6. Feed exports (files)

```python
FEEDS = {
    "data/%(name)s/%(name)s_%(time)s.jsonl": {
        "format": "jsonlines",            # json | jsonlines | csv | xml | pickle
        "encoding": "utf8",
        "overwrite": True,                # local default False
        "store_empty": False,
        "fields": None,                   # or ordered list of fields (CSV column order)
        "item_classes": ["project.items.ProductItem"],   # per-item-type feeds
        "indent": None,
        "item_export_kwargs": {"export_empty_fields": True},
    },
    "data/%(name)s_batch_%(batch_id)d.csv": {"format": "csv", "batch_item_count": 1000},  # needs %(batch_id)d or %(batch_time)s
}
```

- Placeholders: `%(name)s` spider name, `%(time)s` timestamp, `%(any_attr)s` → spider attribute.
- **Prefer JSON Lines** (`.jsonl`): streams, appendable, keeps nesting. `-o` onto a `.json` array corrupts it.
- CSV flattens poorly — nested fields need flattening (see schema-design doc).
- Per-spider: `custom_settings = {"FEEDS": {...}}`.
- **S3**: `pip install botocore`; URI `s3://bucket/%(name)s/%(name)s_%(time)s.jsonl`; set `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` from env vars (never hardcode or put in URI); IAM policy scoped to the one bucket.
  File is written locally and uploaded when the crawl ends.

## 7. Database pipelines

Pattern: connect in `open_spider` (or `__init__`), ensure table, insert/upsert in `process_item`, close in `close_spider`.
Credentials from env vars. The guides' versions had bugs (missing `return item`, wrong attribute names,
no `close_spider`, dedup via SELECT with no UNIQUE constraint) — use these instead:

```python
# SQLite (stdlib)
import sqlite3, json

class SqlitePipeline:
    def open_spider(self, spider):
        self.con = sqlite3.connect("data.db")
        self.con.execute("""CREATE TABLE IF NOT EXISTS products(
            url TEXT PRIMARY KEY, name TEXT, price TEXT, tags TEXT, scraped_at TEXT)""")
    def process_item(self, item, spider):
        a = ItemAdapter(item)
        self.con.execute(
            """INSERT INTO products (url, name, price, tags, scraped_at) VALUES (?,?,?,?,?)
               ON CONFLICT(url) DO UPDATE SET name=excluded.name, price=excluded.price,
               tags=excluded.tags, scraped_at=excluded.scraped_at""",
            (a["url"], a.get("name"), str(a.get("price")), json.dumps(a.get("tags", [])), a.get("scraped_at")))
        self.con.commit()
        return item
    def close_spider(self, spider):
        self.con.close()
```

```python
# Postgres: pip install psycopg[binary]   (or psycopg2-binary)
import os, psycopg
from psycopg.types.json import Jsonb

class PostgresPipeline:
    def open_spider(self, spider):
        self.conn = psycopg.connect(os.environ["DATABASE_URL"])
    def process_item(self, item, spider):
        a = ItemAdapter(item)
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO products (url, name, price, tags, raw)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (url) DO UPDATE SET name=EXCLUDED.name, price=EXCLUDED.price,
                     tags=EXCLUDED.tags, raw=EXCLUDED.raw, updated_at=now()""",
                (a["url"], a.get("name"), a.get("price"), a.get("tags"), Jsonb(a.asdict())))
        self.conn.commit()
        return item
    def close_spider(self, spider):
        self.conn.close()
```

- MySQL: `pip install mysql-connector-python` (NOT `mysql`); `%s` params; upsert with
  `INSERT ... ON DUPLICATE KEY UPDATE`; database must already exist.
- Store lists as JSON / Postgres arrays / JSONB — not `str(list)`.
- For high volume, batch inserts (buffer N items, `executemany`, flush in `close_spider`).

## 8. Login

1. Inspect the login in DevTools → Network: login URL, POST payload, hidden fields, cookies, headers.
2. Pick the method:

```python
from scrapy.http import FormRequest

# A) simple form, no tokens
yield FormRequest(login_url, formdata={"email": EMAIL, "password": PW}, callback=self.after_login)

# B) form with CSRF/hidden fields — GET page first; from_response pre-fills hidden inputs
def start_requests(self):
    yield scrapy.Request(login_url, callback=self.login)
def login(self, response):
    yield FormRequest.from_response(response, formdata={"username": U, "password": PW},
                                    callback=self.after_login)

# C) JSON API login
yield scrapy.Request(api_login, method="POST", body=json.dumps({"email": U, "password": PW}),
                     headers={"Content-Type": "application/json"}, callback=self.after_login)
# then send token: headers={"Authorization": f"Bearer {token}"}

def after_login(self, response):
    if "Logout" not in response.text:          # verify with a logged-in-only marker
        raise CloseSpider("login failed")
```

- D) JS-generated tokens / multi-step: log in with a headless browser (Playwright / scrapy-playwright),
  export cookies, pass `cookies={...}` to normal Scrapy requests.
- Scrapy's CookiesMiddleware keeps the session automatically after login.
- Logged-in scraping: `CONCURRENT_REQUESTS = 1`, `DOWNLOAD_DELAY` several seconds, constant UA per session.
- Credentials from env vars. Only log into accounts you own/are authorized to use; check ToS.

## 9. Pagination (6 methods)

| # | Method | Use when |
|---|---|---|
| 1 | Page number in URL (`?page=N`, `/page/N/`) | predictable URLs; stop on 404/empty (`handle_httpstatus_list=[404]`, `CloseSpider`) |
| 2 | **Follow next link** `response.css('li.next a::attr(href)')` → `response.follow` | default "Scrapy way" |
| 3 | `SitemapSpider` | sitemap lists all target URLs (often best for product catalogs) |
| 4 | `CrawlSpider` + `LinkExtractor` rules | broad crawl; can over-crawl/miss pages |
| 5 | **API pagination** (JSON) — follow `next` / generate all pages from `total_pages` / offset / cursor | site has a backing API (preferred — see reverse-engineering doc) |
| 6 | `autopager` (`autopager.urls(requests.get(url))`) | investigation tool only, to discover the pattern |

```python
# 5a follow next / cursor
def parse(self, response):
    data = response.json()
    yield from (self.to_item(r) for r in data["results"])
    if nxt := data["info"].get("next"):
        yield response.follow(nxt, callback=self.parse)

# 5b fan out all pages at once (parallel) — only from page 1
def parse_first(self, response):
    data = response.json()
    yield from self.parse_page(response)
    for p in range(2, data["info"]["pages"] + 1):
        yield scrapy.Request(f"{API}?page={p}", callback=self.parse_page)
```

Infinite scroll = a hidden XHR API with offset/cursor params → find it in the Network tab and use method 5.

## 10. Politeness, headers, proxies

```python
# settings.py baseline
ROBOTSTXT_OBEY = True
USER_AGENT = "<realistic browser UA or identifying bot UA with contact URL>"
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 1                         # randomized 0.5x–1.5x by default
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504, 522, 524, 408]
HTTPCACHE_ENABLED = True                   # dev only: replay responses offline while iterating
FEED_EXPORT_ENCODING = "utf-8"
```

- Default UA `Scrapy/VERSION (+https://scrapy.org)` is flagged. Set a real UA; random-UA middleware:
  `scrapy-user-agents` (`'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None`,
  `'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 400`). Do NOT spoof Googlebot.
- Rate limits key on IP + UA together. Free proxy pools are unreliable and insecure; paid proxy APIs wrap
  the URL (`http://api.provider.com/?api_key=...&url=...`) — then `response.url` is the proxy URL, so carry
  the original URL in `cb_kwargs`/`meta`. API keys from env vars.

## 11. Distributed crawling — scrapy-redis

`pip install scrapy-redis` (Redis ≥ 5, Scrapy ≥ 2, redis-py ≥ 4.2). Use for large crawls split across workers.

```python
SCHEDULER = "scrapy_redis.scheduler.Scheduler"
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"     # dedup shared across workers
SCHEDULER_PERSIST = True                                       # keep queue → pause/resume
SCHEDULER_QUEUE_CLASS = "scrapy_redis.queue.PriorityQueue"     # or FifoQueue / LifoQueue
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")  # wins over REDIS_HOST/PORT
REDIS_START_URLS_KEY = "%(name)s:start_urls"                   # default
REDIS_START_URLS_AS_SET = False                                # True → push with SADD instead of LPUSH
ITEM_PIPELINES = {"scrapy_redis.pipelines.RedisPipeline": 300} # items → "%(spider)s:items" list
# REDIS_IDLE_BACKOFF_ENABLED = True   # newer versions: back off polling when queue empty
# REDIS_PROTOCOL = 2                  # redis-py 8 defaults to RESP3
```

```python
from scrapy_redis.spiders import RedisSpider   # also RedisCrawlSpider

class MySpider(RedisSpider):
    name = "myspider"
    redis_key = "myspider:start_urls"   # optional; defaults to REDIS_START_URLS_KEY
    def parse(self, response): ...
```

```bash
redis-cli lpush myspider:start_urls https://example.com/a   # feed URLs (sadd if AS_SET)
scrapy crawl myspider        # start N identical workers on N machines, same REDIS_URL
```

- Spider idles waiting for URLs (fetches on idle signal → small start delay).
- Newer versions accept JSON start payloads (`{"url": ..., "meta": {...}}`); verify against the installed version.
- Default serializer is pickle — not portable across Python versions. Separate consumers can read the items list.
