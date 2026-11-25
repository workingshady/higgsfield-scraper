# Logging, run-folder and CLI upgrade plan

**Status: PLAN.** It will be applied after the scraper agents finish.

**Source:** the owner's engineering guides (`claude-folder_9/.claude`):
- `docs/LOGGING-GUIDE.md`
- `docs/LOGGING-PYTHON.md`
- `docs/RUN-FOLDERS-GUIDE.md`
- `docs/CONFIG-AND-CLI.md`
- `docs/OBSERVABILITY-GUIDE.md`
- `rules/logging.md`

The guide folder has no license, so the patterns are **re-implemented, not copied**.

## Gaps found (most important first)

| # | Today | Target | Guide |
|---|---|---|---|
| G1 | No central secret redaction in logs (only the http archive masks headers) | One `redact()` applied to every formatter, the http archive, the HAR and the manifest. It covers keys (`authorization`, `cookie`, `__client`, `jwt`, `hf_*`…), `user:pass@` in URLs, secret query params (`token`, `api_key`, `signature`, `meta`…), and bare JWTs (`eyJ…`) → `[REDACTED_JWT]`. It also applies to exception text | LOGGING §4–5 |
| G2 | Local-time timestamps | ISO-8601 UTC with ms and `Z` everywhere | LOGGING §1.1 |
| G3 | Free-text messages | `entity.action` events with structured fields, no f-strings in log calls | LOGGING §1.5, §7 |
| G4 | Small JSON schema; extra fields dropped | Envelope `timestamp, level, logger, event, message` + OTel-style dotted keys | LOGGING §1.2–1.3 |
| G5 | No heartbeat | `worker.heartbeat` every 30 s, plus `progress` / `updated_at` in the manifest | LOGGING §2, RUN-FOLDERS §6.1 |
| G6 | No access log | `logs/access.jsonl`: one `http.request.finished` line per request | LOGGING §2 |
| G7 | No excepthooks; finish isn't in `finally` | `sys.excepthook` / `threading.excepthook` → `app.crashed`, and finalize in `finally` | LOGGING-PY §7, RUN-FOLDERS §7.2 |
| G8 | No `cancelled` status; Ctrl-C counts as failed | `running → success \| partial \| failure \| cancelled`, mapped from Scrapy close reasons | RUN-FOLDERS §6.4 |
| G9 | Manifest isn't atomic or versioned | Atomic write (tmp + fsync + replace); `schema_version`, `command` (redacted), `cwd`, host, pid, git commit/branch/dirty, `config`, `progress`, `metrics`, `close_reason`, `error`, output sha256 | RUN-FOLDERS §6, §9.3 |
| G10 | `LATEST` updated even on failure; no success marker | `_SUCCESS` written last; `latest.json` updated on success only; `index.jsonl` written under a file lock | RUN-FOLDERS §10 |
| G11 | Exit 2 means both "partial" and "usage error" | 0 ok · 1 failure · 2 usage · 3 partial · 4 blocked · 130 cancelled | CONFIG §6 |
| G12 | Settings read from env in many places; no config file | One typed settings object (pydantic-settings), `--config higgsfield.toml`, secrets as SecretStr. Precedence: defaults < toml < `--config` < .env < env < flags/menu | CONFIG §1, §4–6 |
| G13 | No `-v`/`-q`/`--json` | `-v` (count), `-q`, `--log-format console\|json`, `--no-color`, `--json` on `runs`/`show`/`auth-check`, `show-config`. Data on stdout, logs on stderr | CONFIG §6 |
| G14 | 5 overlapping log files | `events.jsonl` (canonical) + `run.log` (human copy of the same events) + `errors.log` (warning and up, with tracebacks) + `access.jsonl` | RUN-FOLDERS §5.7 |
| G15 | No logging tests | Tests: events emitted, JSON shape, secrets never present, CR/LF injection escaped | LOGGING-PY §9 |
| G16 | No retention | `runs clean --keep-last N --keep-days D` (dry-run by default; never touches running/KEEP/latest); stale `running` → `abandoned` | RUN-FOLDERS §11 |

## Logging design

**Console:** `rich.logging.RichHandler(console=Console(stderr=True), rich_tracebacks=True, tracebacks_show_locals=False, markup=False, show_path=False)`.
- `tracebacks_show_locals=False` keeps tokens out of printed tracebacks.
- `markup=False` stops Rich from interpreting `[...]` in URLs as markup.
- The same Console is shared with the interactive live dashboard.
- Levels: INFO by default, `-v` for project DEBUG, `-vv` for Scrapy DEBUG too, `-q` for WARNING. `--log-level` wins over all three.

**Files** in `<run>/logs/` (one per run, no rotation needed):
- `events.jsonl`: everything, in the canonical JSON envelope.
- `run.log`: the same events as `2026-11-25T14:30:05.120Z INFO logger event k=v …`.
- `errors.log`: WARNING and up, with full tracebacks.
- `access.jsonl`: request lines only.

**Fields on every line:**
- `timestamp, level, logger, event, message`
- `run.id`, `scraper.name` (through a contextvars filter)
- `service.name`, `service.version`, `process.pid`, `host.name`
- `request_id`: a per-request sequence that retries keep, linking the access log, `http/NNN_…`, the HAR and the parse/validation lines

**Event catalog:**

| Event | Level | Notes |
|---|---|---|
| `app.started` | info | |
| `config.loaded` | info | |
| `run.started` | info | |
| `endpoint.started` | info | |
| `http.request.finished` | info / warn | 4xx/5xx warn, except optional endpoints |
| `external.call.retried` | warn | |
| `external.call.failed` | error | |
| `page.fetched` | debug | |
| `item.dropped` | warn | first 100 logged, then counts only |
| `limit.hit` | info / warn | info for user limits, warn for safety caps |
| `auth.token.refreshed` | info | |
| `auth.token.expired` | warn | |
| `auth.refresh.failed` | error | |
| `request.blocked` | error | DataDome |
| `worker.heartbeat` | info, every 30 s | requests, responses, errors, items, rate, queue depth, memory, %, ETA |
| `run.finished` | info / error | wide summary: outcome, duration, exit code, counts, dropped, limits hit, close reason |
| `app.crashed` | critical | |

**Errors:** log once, where handled, with `exc_info`. In JSON that's `error.type`, `exception.type`, `exception.message` and `exception.stacktrace`, all redacted.

## Implementation order

1. Logging core (G1–G4, G7) + tests (G15)
2. Lifecycle, access and heartbeat events (G5, G6)
3. Manifest, statuses, `_SUCCESS`, `latest.json` (G8–G10)
4. Exit codes and flags (G11, G13)
5. Typed settings and config file (G12)
6. Interactive mode (see `INTERACTIVE_FLOW_PLAN.md`)
7. `runs clean` (G16)

**Dependencies:** `rich`, `questionary` (interactive extra), `pydantic-settings`, `tomli` (Python 3.10 only), `psutil` (memory in the heartbeat). `filelock` is already present.

**Compatibility:** pricing output files stay byte-identical, checked by the baseline diff. Old run folders and `LATEST` remain readable.
