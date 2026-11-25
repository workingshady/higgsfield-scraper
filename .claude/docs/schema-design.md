# Schema Design for Scraped Data (Items, Nested Schemas, Validation, Storage)

Sources: Scrapy Items/Loaders docs, itemadapter, Pydantic v2 docs, Spidermon, Zyte "storing and curating data",
Postgres INSERT…ON CONFLICT (links at bottom).

---

## 1. Principles

**Entities first, pages second.** Model business objects (Product, Plan, PriceTier, Feature), not HTML layout.
One page can yield several entities; one entity can span several pages (listing + detail).

**Stable natural keys.** Every entity gets a deterministic ID identical on every crawl.
- Prefer source-native IDs (SKU, slug, `data-id`, API/JSON-LD id).
- Else composite natural key: `(source, canonical_url)`, `(product_id, plan_slug)`, `(plan_id, billing_period, min_units)`.
- Store a hash of the natural key. **Never** hash volatile fields (price, scraped_at).

```python
import hashlib
from w3lib.url import canonicalize_url

def make_id(*parts: str) -> str:
    key = "|".join(str(p).strip().lower() for p in parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]

product_id = make_id("acme.com", canonicalize_url(response.url))
plan_id    = make_id(product_id, plan_slug)
```

**Nest vs split.**
- **Nest** when the child has no identity outside the parent, is scraped together with it, is small/bounded,
  and is rarely queried alone: `features: list[str]`, `price: {amount, currency}`, `images`.
- **Split into separate item types linked by ID** when the child comes from another request/page, is
  unbounded/paginated (reviews), is shared by many parents, needs history (prices), or is queried/aggregated alone.
- Rule of thumb: ≤ 2 nesting levels inside one item. Anything you'll `GROUP BY` gets its own table.

**Normalize to store, denormalize to export.** Scraper emits nested JSONL documents; the DB loader normalizes
into parent/child tables; flat CSV / analytics views are built from those.

**Required vs optional.** Required: ID, `source_url`, `scraped_at`, plus fields without which the record is
useless (name; amount + currency for a price row). Everything else `Optional` — layouts change. Drop items
missing required fields; *monitor* null rates on optional fields.

**Types.**
- Money: `Decimal`, never float. SQL `NUMERIC(12,4)`.
- Currency: separate ISO 4217 code (`USD`). `$` is ambiguous (USD/CAD/AUD) — don't guess; keep raw symbol.
- Time: timezone-aware UTC, ISO 8601 (`2026-11-25T10:00:00Z`).
- Closed sets → enums: `billing_period ∈ {month, year, one_time, usage}`.
- Provenance on every item: `source_url`, `scraped_at`, `spider`, `schema_version`.

**Raw + cleaned.** Keep the raw string next to the parsed value for hard-to-parse fields
(`price_raw="$1,299/mo billed annually"` + `amount=Decimal("1299")`) → re-parse without re-crawling.
Tiers: raw (HTML/JSON cache) → staged/validated → production.

**Versioning.** `schema_version: int` on every item. Bump on breaking change (rename, type change, removal);
adding an optional field is non-breaking. Keep old models/JSON Schemas for migrations.

**Missing data convention (use this):** key always present; `None` = looked, not there; `[]` = list present but empty;
never `""` or `0` as sentinels.

## 2. Scrapy item types

Scrapy accepts dict, `scrapy.Item`, dataclass, attrs, and **pydantic models** (itemadapter, pydantic ≥ 2.7).
Only pydantic enforces types at runtime.

```python
import scrapy
from dataclasses import dataclass, field
from typing import Optional

class ProductItem(scrapy.Item):
    product_id = scrapy.Field()
    name = scrapy.Field()
    plans = scrapy.Field()           # nested: list of dicts / sub-items
    source_url = scrapy.Field()
    scraped_at = scrapy.Field()

@dataclass
class PlanDC:                        # dataclass items need defaults to work with ItemLoader
    name: Optional[str] = None
    features: list[str] = field(default_factory=list)
```

ItemAdapter — write pipelines that work with any item type:

```python
from itemadapter import ItemAdapter
a = ItemAdapter(item)
a.get("price"); a["name"] = "x"; a.field_names()
a.asdict()                      # RECURSIVE (nested items → dicts); dict(a) is not
ItemAdapter.is_item(obj)
ItemAdapter.get_json_schema(ProductItem)
```

### Nested ItemLoaders

`nested_css()/nested_xpath()` scope selectors but **share the parent's item** — they do not create sub-items.
For a list of sub-items, run a separate loader per child and add the loaded list to the parent.

```python
from itemloaders.processors import TakeFirst, MapCompose, Identity
from scrapy.loader import ItemLoader

def strip(s): return s.strip() if isinstance(s, str) else s

class BaseLoader(ItemLoader):
    default_input_processor = MapCompose(strip)
    default_output_processor = TakeFirst()

class PlanLoader(BaseLoader):
    default_item_class = dict
    features_out = Identity()

class ProductLoader(BaseLoader):
    default_item_class = dict
    plans_out = Identity()             # list of built dicts — don't TakeFirst

def parse_product(self, response):
    pl = ProductLoader(response=response)
    pl.add_css("name", "h1::text")
    pl.add_value("source_url", response.url)
    pl.add_value("scraped_at", datetime.now(timezone.utc).isoformat())
    meta = pl.nested_css("div.product-meta")     # scoped selector, same item
    meta.add_css("vendor", ".brand::text")
    plans = []
    for card in response.css("div.plan-card"):
        l = PlanLoader(selector=card)            # child loader → child item
        l.add_css("name", ".plan-name::text")
        l.add_css("price_raw", ".price::text")
        l.add_css("features", "li.feature::text")
        plans.append(l.load_item())
    pl.add_value("plans", plans)
    yield pl.load_item()
```

Processor precedence: loader `field_in/_out` → Field metadata `input_processor/output_processor` → loader defaults.

Multiple item types per spider → pipelines dispatch with `isinstance(item, PlanItem)` and pass others through.

## 3. Validation

### Pydantic v2 (source of truth)

`condecimal` is discouraged → use `Annotated[Decimal, Field(...)]`.

```python
# schemas.py
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Optional
import re
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, AwareDatetime, field_validator, model_validator

SCHEMA_VERSION = 1
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=4)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
SYMBOL_TO_ISO = {"€": "EUR", "£": "GBP", "¥": "JPY"}       # "$" deliberately not mapped

class BillingPeriod(str, Enum):
    month = "month"; year = "year"; one_time = "one_time"; usage = "usage"

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class PriceTier(Strict):
    amount: Optional[Money] = None              # None = custom / contact sales
    currency: Optional[Currency] = None
    billing_period: BillingPeriod
    min_units: Optional[int] = Field(default=None, ge=0)
    max_units: Optional[int] = Field(default=None, ge=0)
    unit_label: Optional[str] = None            # "seat", "1k credits"
    price_raw: Optional[str] = None
    is_custom: bool = False

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        if v is None or isinstance(v, Decimal):
            return v
        s = re.sub(r"[^\d.,-]", "", str(v)).replace(",", "")   # assumes US number format
        if not s:
            return None
        try:
            return Decimal(s)
        except InvalidOperation:
            raise ValueError(f"unparseable amount {v!r}")

    @field_validator("currency", mode="before")
    @classmethod
    def norm_currency(cls, v):
        return None if v is None else SYMBOL_TO_ISO.get(str(v).strip(), str(v).strip().upper())

    @model_validator(mode="after")
    def check(self):
        if self.amount is not None and self.currency is None:
            raise ValueError("amount without currency")
        if self.amount is None and not self.is_custom:
            raise ValueError("amount missing and tier not marked custom")
        if self.min_units and self.max_units and self.max_units < self.min_units:
            raise ValueError("max_units < min_units")
        return self

class Plan(Strict):
    plan_id: str
    name: str = Field(min_length=1)
    slug: str
    description: Optional[str] = None
    tiers: list[PriceTier] = Field(min_length=1)
    features: list[str] = Field(default_factory=list)
    trial_days: Optional[int] = Field(default=None, ge=0)

    @field_validator("features")
    @classmethod
    def dedupe(cls, v): return list(dict.fromkeys(f for f in v if f))

class Product(Strict):
    schema_version: int = SCHEMA_VERSION
    product_id: str
    source: str
    name: str
    vendor: Optional[str] = None
    source_url: HttpUrl
    scraped_at: AwareDatetime                   # rejects naive datetimes
    plans: list[Plan] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_plan_ids(self):
        ids = [p.plan_id for p in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate plan_id")
        return self
```

Validation pipeline (early, e.g. priority 300, so later pipelines get clean typed data):

```python
from itemadapter import ItemAdapter
from pydantic import ValidationError
from scrapy.exceptions import DropItem
from .schemas import Product

class PydanticValidationPipeline:
    def process_item(self, item, spider):
        data = ItemAdapter(item).asdict()
        try:
            obj = Product.model_validate(data)
        except ValidationError as e:
            stats = spider.crawler.stats
            stats.inc_value("validation/dropped")
            for err in e.errors():
                stats.inc_value(f"validation/error/{'.'.join(map(str, err['loc']))}")
            raise DropItem(f"invalid {data.get('source_url')}: {e.errors(include_url=False)}")
        return obj.model_dump(mode="json")     # Decimal→str, datetime→ISO, Enum→value
```

Gotcha: Scrapy's JSON exporter writes datetimes as `"%Y-%m-%d %H:%M:%S"` (no tz). Emit ISO strings yourself.

Generate the JSON Schema contract:

```python
json.dump(Product.model_json_schema(mode="serialization"), open("schemas/product.v1.json", "w"), indent=2)
```

### JSON Schema alternatives

```python
# plain jsonschema
from jsonschema import Draft202012Validator
V = Draft202012Validator(json.load(open("schemas/product.v1.json")))
if errs := list(V.iter_errors(data)):
    raise DropItem("; ".join(f"{'/'.join(map(str, e.path))}: {e.message}" for e in errs))
```

```python
# Spidermon
ITEM_PIPELINES = {"spidermon.contrib.scrapy.pipelines.ItemValidationPipeline": 800}
SPIDERMON_VALIDATION_SCHEMAS = {ProductItem: "schemas/product.json"}
SPIDERMON_VALIDATION_DROP_ITEMS_WITH_ERRORS = True
```

Pydantic = coercion + validation in Python; JSON Schema = language-neutral contract. Common: pydantic is
source of truth, `model_json_schema()` produces the contract.

## 4. Nested schema → storage

| Target | How |
|---|---|
| **JSONL** | keeps nesting natively; append-only, streamable. Use as raw archive even if you also load SQL. |
| **CSV** | must flatten. *Explode* (one row per leaf, parent fields repeated) or *collapse* (lists → `"a|b|c"`/JSON string). Fix column order with `FEED_EXPORT_FIELDS`. |
| **SQL** | one table per entity, child FK → parent natural-key ID; upsert parent then children in one transaction. |
| **Postgres JSONB hybrid** | typed columns for keys/queried fields + `raw JSONB` full document (`GIN (raw jsonb_path_ops)`). Don't make everything JSONB — slow and hard to migrate later. |

```python
def explode(product: dict):
    base = {k: product[k] for k in ("product_id", "name", "source_url", "scraped_at")}
    for plan in product["plans"]:
        p = {**base, "plan_id": plan["plan_id"], "plan_name": plan["name"], "features": "|".join(plan["features"])}
        for t in plan["tiers"]:
            yield {**p, **{f"tier_{k}": v for k, v in t.items()}}
# ad hoc: pandas.json_normalize(products, record_path=["plans", "tiers"], meta=["product_id", ["plans", "plan_id"]])
```

- Children that disappear from the current scrape: delete, or mark `is_active=false`.
- **Prices are a time series**: upsert a "current" table AND append to a "history" table (or append only on change).

```sql
INSERT INTO product (product_id, source, name, source_url, last_seen_at, raw)
VALUES (%(product_id)s, %(source)s, %(name)s, %(source_url)s, %(scraped_at)s, %(raw)s)
ON CONFLICT (product_id) DO UPDATE
SET name = EXCLUDED.name, source_url = EXCLUDED.source_url,
    last_seen_at = EXCLUDED.last_seen_at, raw = EXCLUDED.raw
WHERE product.raw IS DISTINCT FROM EXCLUDED.raw;      -- skip no-op writes
-- SQLite ≥ 3.24 supports the same ON CONFLICT ... DO UPDATE SET col = excluded.col
```

```python
class PostgresPipeline:      # psycopg 3
    def open_spider(self, spider):  self.conn = psycopg.connect(os.environ["DATABASE_URL"])
    def close_spider(self, spider): self.conn.close()
    def process_item(self, item, spider):
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(UPSERT_PRODUCT, {**item, "raw": Jsonb(item)})
            for plan in item["plans"]:
                cur.execute(UPSERT_PLAN, {**plan, "product_id": item["product_id"], "seen": item["scraped_at"]})
                for t in plan["tiers"]:
                    cur.execute(UPSERT_TIER, {**t, "plan_id": plan["plan_id"], "seen": item["scraped_at"]})
                    cur.execute(INSERT_PRICE_OBS, {**t, "plan_id": plan["plan_id"], "scraped_at": item["scraped_at"]})
        return item
```

## 5. Reference pricing schema (product → plans → price tiers, features)

Example JSONL record:

```json
{"schema_version":1,"product_id":"a1b2c3d4e5f60718","source":"acme.com","name":"Acme CRM","vendor":"Acme Inc",
 "source_url":"https://acme.com/pricing","scraped_at":"2026-11-25T10:00:00Z",
 "plans":[{"plan_id":"9f8e7d6c5b4a3210","name":"Pro","slug":"pro","trial_days":14,
   "features":["SSO","API access","Audit log"],
   "tiers":[{"amount":"29.0000","currency":"USD","billing_period":"month","min_units":1,"max_units":null,
             "unit_label":"seat","price_raw":"$29/seat/mo","is_custom":false},
            {"amount":"290.0000","currency":"USD","billing_period":"year","min_units":1,"max_units":null,
             "unit_label":"seat","price_raw":"$290/seat/yr","is_custom":false}]}]}
```

```sql
CREATE TYPE billing_period AS ENUM ('month','year','one_time','usage');

CREATE TABLE product (
  product_id     TEXT PRIMARY KEY,                  -- hash(source, canonical_url)
  source         TEXT NOT NULL,
  name           TEXT NOT NULL,
  vendor         TEXT,
  source_url     TEXT NOT NULL,
  schema_version INT  NOT NULL,
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at   TIMESTAMPTZ NOT NULL,
  raw            JSONB,
  UNIQUE (source, source_url)
);

CREATE TABLE plan (
  plan_id      TEXT PRIMARY KEY,                    -- hash(product_id, slug)
  product_id   TEXT NOT NULL REFERENCES product(product_id) ON DELETE CASCADE,
  slug         TEXT NOT NULL,
  name         TEXT NOT NULL,
  description  TEXT,
  trial_days   INT CHECK (trial_days >= 0),
  is_active    BOOLEAN NOT NULL DEFAULT true,
  last_seen_at TIMESTAMPTZ NOT NULL,
  UNIQUE (product_id, slug)
);

CREATE TABLE feature (feature_id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE plan_feature (
  plan_id    TEXT REFERENCES plan(plan_id) ON DELETE CASCADE,
  feature_id INT  REFERENCES feature(feature_id),
  raw_label  TEXT,
  PRIMARY KEY (plan_id, feature_id)
);

CREATE TABLE price_tier (                            -- current state (upserted)
  plan_id        TEXT NOT NULL REFERENCES plan(plan_id) ON DELETE CASCADE,
  billing_period billing_period NOT NULL,
  min_units      INT NOT NULL DEFAULT 0,
  max_units      INT,
  amount         NUMERIC(12,4) CHECK (amount >= 0),  -- NULL = custom
  currency       CHAR(3) CHECK (currency ~ '^[A-Z]{3}$'),
  unit_label     TEXT,
  is_custom      BOOLEAN NOT NULL DEFAULT false,
  price_raw      TEXT,
  last_seen_at   TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (plan_id, billing_period, min_units),
  CHECK (amount IS NULL OR currency IS NOT NULL)
);

CREATE TABLE price_observation (                     -- append-only history
  plan_id        TEXT NOT NULL REFERENCES plan(plan_id),
  billing_period billing_period NOT NULL,
  min_units      INT NOT NULL DEFAULT 0,
  amount         NUMERIC(12,4),
  currency       CHAR(3),
  scraped_at     TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (plan_id, billing_period, min_units, scraped_at)
);
CREATE INDEX ON price_observation (plan_id, scraped_at DESC);
```

## Checklist

1. Stable hashed natural-key ID computed in the spider.
2. Every item: `source_url`, `scraped_at` (UTC ISO 8601), `schema_version`.
3. Money = `Decimal` + ISO 4217 currency; raw price text kept.
4. `None` = missing, `[]` = empty list, never `""`.
5. Pydantic validation pipeline (~300): `DropItem` on failure, error counts in stats, `model_dump(mode="json")`.
6. JSON Schema generated from pydantic, versioned in `schemas/`.
7. JSONL = raw archive; SQL normalized with append-only price history.
8. Nest only owned, bounded children; anything queried alone or tracked over time gets its own table.

## Sources
- https://docs.scrapy.org/en/latest/topics/items.html
- https://docs.scrapy.org/en/latest/topics/loaders.html
- https://github.com/scrapy/itemadapter
- https://pydantic.dev/docs/validation/latest/api/pydantic/types/
- https://spidermon.readthedocs.io/en/latest/item-validation.html
- https://dev.zyte.com/blog/storing-and-curating-data/
- https://www.postgresql.org/docs/current/sql-insert.html
- https://jsonlines.org/
