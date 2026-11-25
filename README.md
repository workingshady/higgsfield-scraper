# higgs-price

A Scrapy project that collects **all public pricing data from [higgsfield.ai/pricing](https://higgsfield.ai/pricing)**.
It covers:

- every subscription plan, with **USD prices before and after the offer and on renewal**, plus the discount and when it applies
- the **credit cost of every model** (Seedance, Kling, GPT Image, Nano Banana, Veo, Wan, ElevenLabs, … 86 models), covering
  every option combination: resolution, quality, mode, audio, input video, FPS, and so on
- each plan's benefits (unlimited models, free generations, caps), the plan comparison matrix, and the marketing copy

The page itself contains no prices. They come from JSON APIs that this project calls directly, without parsing any HTML.

| Doc | Contents |
|---|---|
| [`CLI.md`](CLI.md) | **Every command and option**, their choices, example output, recipes, exit codes |
| [`docs/ENDPOINTS.md`](docs/ENDPOINTS.md) | Every endpoint: params, auth, response fields and their meaning |
| [`docs/ENDPOINT_FIELDS.md`](docs/ENDPOINT_FIELDS.md) | Auto-generated list of every JSON path, with types and examples |
| [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md) | All reverse-engineering findings, evidence and verification |
| [`docs/higgsfield.postman_collection.json`](docs/higgsfield.postman_collection.json) | Postman collection |

---

## 1. Setup

```bash
# Python 3.10+
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
# optional: pip install -e .      -> adds a `higgs-price` command
cp .env.example .env              # optional settings (token, defaults)
```

Check that it works:

```bash
python -m pytest -q                     # offline tests (fixtures)
python -m higgs_price scrape --dry-run  # prints the requests it would make
```

## 2. Quick start

```bash
python -m higgs_price scrape                    # default: US prices, all public sections
python -m higgs_price show plans                # plan table from the latest run
python -m higgs_price show models seedance      # models matching "seedance"
python -m higgs_price show model seedance_2_5   # every option combination + credits + ≈USD
python -m higgs_price show compare "kling 3.0"  # comparison matrix rows
```

## 3. Commands and options

| Command | Purpose |
|---|---|
| `scrape` | Fetch live data into a new run folder (this is the default when no command is given) |
| `normalize --run DIR` | Re-parse a previous run's `raw/` responses **offline** into a new run, for example after a parser change |
| `show plans\|models\|model <id>\|plan-sets\|benefits\|compare [filter] [--run DIR]` | Print tables from a run's dataset |
| `plan-sets` | List every `plan_set_key`, the presets, and the frontend's tier mapping |
| `sections` | List what each section fetches |
| `runs` | List recent runs with their status and counts |
| `schema --out schemas/` | Export the JSON Schemas |

### `scrape` options

| Option | Default | Meaning |
|---|---|---|
| `--sections` | `plans,compare,benefits,models,marketing` | Any of `plans`, `compare`, `benefits`, `models`, `marketing`, `auth`, or `all` |
| `--plan-sets` | `us` (= `ps_a3`) | One or more of the 25 `plan_set_key` values, or a preset: `us`, `tiers` (ps_a3, default, max_v1, max_v2), `all` |
| `--billing` | `monthly,annual` | Billing periods requested from `/compare` |
| `--plan-types` | all | Output filter, for example `plus,ultra,team` |
| `--models` | all | Output filter: substrings or globs on id, family, or name, for example `seedance,kling*,gpt_image_2_6` |
| `--categories` | all | `video,image,audio,other` |
| `--marketing-versions` | `latest` | `latest`, `all`, or a list such as `v51,v50` |
| `--locale` | `en` | `en de es fr ja ko pt-BR zh-CN` (affects benefits and marketing text) |
| `--usd-reference` | `plus:annual` | The plan whose after-offer price per credit is used to convert model credits to USD |
| `--include-hidden-plans` | off | Keep `trial` and `secret` plan types (the site hides them) |
| `--include-raw-cost` | off | Embed each model's untouched cost JSON |
| `--token` / `HF_TOKEN` | — | Clerk session JWT, needed for `--sections auth` (top-ups, bundles, credit price) |
| `--label` | auto | Suffix for the run folder name |
| `--runs-dir` | `runs` | Where run folders are created |
| `--log-level` / `--file-log-level` / `--scrapy-log-level` | `INFO` / `DEBUG` / `INFO` | Logging verbosity |
| `--cache` | off | Scrapy HTTP cache, for development |
| `--no-http-archive` | off | Skip the `http/` subfolder (raw request and response of every HTTP exchange) |
| `--dry-run` | — | Print the planned requests and exit |

Examples:

```bash
python -m higgs_price scrape --sections plans --plan-sets all --label every-plan-set
python -m higgs_price scrape --sections models --models "seedance*,kling*" --label video-costs
python -m higgs_price scrape --sections all --plan-sets tiers --marketing-versions all
python -m higgs_price scrape --sections auth,plans --token "$HF_TOKEN"
scrapy crawl higgsfield -a sections=models -a models=seedance        # plain Scrapy works too (no manifest)
```

Exit codes: `0` success, `2` partial (some non-200 responses or invalid items), `1` failed.

## 4. Run folders

Each run gets its own timestamped, labelled folder. Nothing is ever overwritten.

```
runs/
  20261125-104415_tiers/
    manifest.json              status, args, selection, versions, timings, counts, HTTP statuses, Scrapy stats, file list
    logs/
      run.log                  everything (DEBUG+)
      app.log                  higgs_price.* only
      scrapy.log               scrapy / twisted / warnings only
      errors.log               WARNING and above
      events.jsonl             structured JSON log (ts, level, logger, run_id, endpoint, status…)
    raw/                       API responses as JSON envelopes {"meta": {endpoint,url,params,status,fetched_at}, "body": …}
                               (pretty-printed; input for `normalize`)
    http/                      wire-level archive of EVERY HTTP exchange (incl. robots.txt, redirects, retries, errors)
      index.jsonl              one line per exchange: seq, endpoint, method, url, status, bytes, latency_ms, error, dir
      session.har              HAR 1.2 of the run → Chrome DevTools → Network → "Import HAR file"
      004_plans__plan_set_key-ps_a3/
        request.json           method, url, query, every header sent (Authorization/Cookie masked), sent_at, retry_times, meta
        response.json          status, reason, every response header (Set-Cookie masked), content_type, bytes,
                               latency_ms, received_at, protocol, ip_address
        body.raw               response bytes exactly as received (decompressed), byte-for-byte
        curl.sh                ready-to-run curl command that replays the request
    output/
      dataset.json             ★ everything, nested and validated
      summary.md               readable tables (plans, cheapest option per model)
      json/                    plans, plan_sets, credit_values, models, benefit_cards, comparisons, marketing, auth
      csv/                     plans, models, model_price_points, model_entitlements, benefit_rows,
                               comparison_matrix, credit_values, marketing_features
      items/                   Scrapy JSONL feeds, one file per item type
      schema/dataset.schema.json
  LATEST                       name of the newest run
  index.jsonl                  one line per run
```

## 5. Data model (`output/dataset.json`)

```
Dataset
├─ meta: run_id, scraped_at, country_code, currency, plan_set_keys, costs_version, usd_reference, counts, warnings
├─ plan_sets[]: plan_set_key, country_code, special_offer
│   └─ plans[]: plan_id, plan_type, name, audience, billing_period, credits_per_month, seats, currency
│       ├─ pricing: before_offer{total, per_month}, after_offer{…}, renewal{…}     (USD, decimal strings)
│       ├─ discount: percent_off, duration, applies_to (first_payment | all_payments | first_N_months)
│       ├─ savings{total, per_month, percent}, price_per_credit{before_offer, after_offer, renewal}
│       └─ benefit_card_ids[], unlimited_model_ids[], free_gens[]
├─ credit_values[]: $/credit and credits/$ per plan
├─ models[]: model_id (job_set_type), display_name, family, category, units[], components[]
│   ├─ options: {resolution: [480p, 720p, …], quality: […], mode: […], audio: [on, off], video_input: […]}
│   ├─ price_points[]: dimensions{…}, component, unit, credits, original_credits, discount_percent,
│   │                  example{seconds: 5, credits: 35}, usd_estimate, attributes{}, formula{} (audio/TTS)
│   └─ entitlements[]: which plans make it unlimited or give free gens (count, days, caps)
├─ benefit_cards[]: plan_type × billing_period × tab → sections → rows → entitlement{type, count, caps…}
├─ comparisons[]: plan_set × billing → categories → features{detail, credits, per} → values per plan
├─ marketing[]: config_version × billing × plan → tagline, credits copy, features, feature_groups
└─ auth: credit_packages[], payloads[]   (only with --token)
```

Conventions:

- Money is a `Decimal` serialized as a string, in USD.
- IDs are stable hashes of natural keys.
- `None` means not provided, and `[]` means an empty list.
- `schema_version` is set on every entity.

The Pydantic models in `higgs_price/schemas/` are the source of truth. Run `python -m higgs_price schema` to export
the JSON Schemas.

**Model cost units:**

| unit | meaning |
|---|---|
| `credits_per_generation` | per image or generation |
| `credits_per_second` | per second of video or audio (`example` shows 5 s) |
| `credits_per_minute` | per minute of input |
| `credits_per_image` / `credits_per_frame` | extra charge per input image or frame |
| `base_credits` | flat cost added per job |
| `credits_per_50_characters` / `credits_per_10_seconds` / `credits_per_character` | TTS and audio formulas (`formula` holds the raw params) |

## 6. Prices and geography

Prices depend on the visitor's country, which the API works out from the IP address and which can't be overridden.
All prices are in **USD**. The site serves different *plan sets* to different visitors. `ps_a3` matches the official
US price list at `https://higgsfield.ai/pricing.md`, so it is the default. Use `--plan-sets tiers` or `--plan-sets all`
to capture the other variants. `meta.country_code` records which country the API detected.

## 7. Project layout

```
higgs_price/
  cli.py                 entry point (python -m higgs_price)
  constants.py           endpoints, plan_set_keys, presets
  selection.py           sections, plan sets, and filters chosen for a run
  spiders/higgsfield.py  the Scrapy spider (JSON APIs only)
  parsers/               pure raw-JSON → entity functions (plans, costs, benefits, compare, marketing, auth)
  schemas/               pydantic v2 models (one per entity + Dataset)
  items.py               Scrapy Items generated from the schemas
  validation.py          entity validation (used by the pipeline and by normalize)
  pipelines.py           raw archive → validation → collect/assemble/export
  assemble.py            joins: plans↔benefits↔models, seats, USD estimates
  exporters.py           JSON / CSV / schema / summary.md writers
  logformatter.py        one-line item logs (no 4 MB dumps)
  run/                   RunContext (folders, manifest), logging setup, RunManager
  settings.py            Scrapy settings (polite: robots.txt, AutoThrottle, retries)
tests/                   offline tests on captured fixtures (+ live test with HF_LIVE=1)
docs/                    ENDPOINTS.md, ENDPOINT_FIELDS.md, REVERSE_ENGINEERING.md, Postman collection
scripts/                 gen_endpoint_fields.py (regenerates docs/ENDPOINT_FIELDS.md)
samples/higgsfield/      raw captures from the recon
```

## 8. Testing

```bash
python -m pytest -q                       # offline, ~5 s
HF_LIVE=1 python -m pytest -q -m live     # real end-to-end scrape into a temp folder
```

## 9. Notes

- These are undocumented internal APIs and may change without notice. Each run logs any non-200 response,
  and `manifest.json` records a `partial` status when that happens.
- Keep the request volume low: one snapshot per run is about 6–20 requests. The spider follows robots.txt and
  uses throttling.
- Never call the purchase, checkout, or offer-mutation endpoints listed in the bundle (see the endpoint doc).
