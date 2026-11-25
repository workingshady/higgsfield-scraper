# Interactive console mode: flow plan

**Status: PLAN.** Not built yet. Implementation starts after the scraper agents finish; the library choice will be
confirmed by the prototype research.

**Goal:** two ways to run the scraper, sharing one code path.

| Mode | Command | For |
|---|---|---|
| **Flags** (unchanged) | `python -m higgsfield_scraper scrape community --type video --max-items 500` | scripts, cron, CI, power users |
| **Interactive** (new) | `python -m higgsfield_scraper` with no args on a terminal, or `python -m higgsfield_scraper interactive` | guided use: menus, checkboxes, login, live progress |

## 1. Principles

Sources: clig.dev, PatternFly CLI handbook, and the logging/CLI guides in `claude-folder_9`.

1. **Every menu choice maps to a flag.** The wizard only fills in the same `argparse` namespace and calls the same
   `cmd_*` functions, so both modes behave identically.
2. **Prompt only on a real terminal.** If stdin or stdout isn't a TTY, or `--no-input` / `CI=1` is set, never prompt.
   Fall back to flags, or fail with a clear message naming the missing flag.
3. **Always show the equivalent command** before running, so users learn the flags and can copy them into scripts.
4. **Esc or Back goes back one step; Ctrl+C cancels cleanly** with no half-written run folder. "Run" is always
   confirmed.
5. **Secrets:** password and code input is never echoed, and the password is never written anywhere except `.env`,
   and only if the user chooses to save it.
6. **Remember last choices** per scraper in `runs/.prefs.json` (gitignored) and offer them as defaults.
7. **Accessibility:** honor `NO_COLOR`, never rely on color alone (icons + text), and keep the layout usable at
   80 columns.

## 2. Main menu

```
╭─ higgsfield-scraper ─────────────────────────── v0.x · session: ✓ logged in (expires 59 s, auto-refresh) ─╮
│  What do you want to do?                                                                                  │
│  ❯ 🕷  Scrape                    pricing · community · catalog · projects · blog                           │
│    🔑  Login / account           log in, enter emailed code, check session                                │
│    📂  Browse runs               open summaries, CSV/JSON, manifest, errors                               │
│    ♻  Re-parse a run (normalize) rebuild outputs offline from raw/                                       │
│    🧪  Test request              one quick request to check connectivity / login                          │
│    ⚙  Settings                  defaults: runs dir, delay, concurrency, log level, media caps            │
│    ✖  Exit                                                                                                │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## 3. Scrape flow

```
Scrape
 ├─ 1. Pick scraper (single select, with one-line descriptions and last-used marked)
 ├─ 2. What to scrape (checkbox multi-select; options depend on the scraper)
 │     pricing   : ☑ plans ☑ compare ☑ benefits ☑ models ☑ marketing ☐ auth (🔒)
 │     community : feeds ☑ trending ☐ approved ☐ top ☐ model-x · type (all/image/video) · models (multi)
 │     catalog   : ☑ public kinds ☐ login-only kinds (🔒) · ☐ samples ☐ details
 │     projects  : ☑ publications ☑ contests ☐ recommended · ☐ details ☐ submissions
 │     blog      : ☑ blog ☑ talents ☑ help ☑ enterprise-help ☑ case-studies ☑ changelog · ☑ article text
 ├─ 3. Filters (optional, skippable): plan sets / plan types / models / categories / locale / since …
 ├─ 4. Extras: ☐ estimate cost (images / videos / all) · ☐ include personal profiles (warning) · media
 │            download (none / thumbs / full / all + caps)
 ├─ 5. Limits & safety: max items · max pages · page size · delay · concurrency · max minutes
 │     (presets: "quick test" 50 items · "standard" · "everything" (shows request estimate))
 ├─ 6. Run label (default: <scraper>-<choices>, validated) + runs dir
 ├─ 7. Review screen
 │     • table of choices    • request estimate    • 🔒 items that will be skipped without login
 │     • equivalent command: python -m higgsfield_scraper scrape community --feeds trending --type video …
 │     [ Run ]  [ Test request first ]  [ Copy command ]  [ Back ]  [ Cancel ]
 └─ 8. Run with live display (see §5), then the summary screen:
       status · counts · limits hit · warnings · output paths
       [ Open run folder ]  [ Show summary.md ]  [ Scrape again with same options ]  [ Main menu ]
```

**Login-aware:** if a step needs login and there's no session, the item shows 🔒 and offers "Log in now" inline,
which jumps to the login flow and then returns to the same step.

## 4. Login flow

```
Login / account
 ├─ Status panel: source (cached session / cookie / token / none) · expires in · last refresh · account email (masked)
 ├─ Log in with email + password
 │    email (prefilled from .env) → password (masked; prefilled from .env if present)
 │    → "Clerk emailed a 6-digit code to w*******y@gmail.com" → code input (digits only, 6 chars, masked)
 │    → ✓ session cached (runs/.auth) → auto auth-check
 │    errors: wrong code (retry ≤3) · expired (resend) · captcha/protect-check → explain, no workaround
 ├─ Use browser cookie (paste __client, masked) → validate → save to .env? (y/N)
 ├─ Check session (auth-check)
 └─ Log out (delete cached session)
```

## 5. Live run display (Rich)

```
 Scraping community · run 20261125-151200_community-video                       ⏱ 00:01:42   ctrl+c = stop
 ┌ Requests ─────────────────────────┐ ┌ Items ─────────────────────────┐ ┌ Health ────────────────────────┐
 │ ███████████████░░░░░  312 / ~400  │ │ generations   2,950 ✓  0 ✗     │ │ 2xx 309 · 4xx 3 · 5xx 0       │
 │ 2.9 req/s · avg 310 ms            │ │ estimates     2,950 (41% exact)│ │ retries 2 · auth refresh 1     │
 └───────────────────────────────────┘ └────────────────────────────────┘ └────────────────────────────────┘
 14:12:03 INFO  community  trending page 59 → 50 items (has_more)
 14:12:04 WARN  limit      max_items=3000 reached
```

- **Logs scroll above the live panel.** RichHandler and the Live display share one Console.
- **Heartbeat every N seconds:** requests, items, rate, ETA, memory. It goes to the panel and also to
  `events.jsonl` as `heartbeat` events.
- **Data comes from** Scrapy signals (`request_scheduled`, `response_received`, `item_scraped`, `item_dropped`) and
  the stats collector, polled about 4 times per second.

## 6. Other screens

- **Browse runs:** a table of the last 20 runs (status, scraper, counts, duration). Select one to open `summary.md`
  in the pager, list its errors, open the folder, or re-run with the same options.
- **Normalize:** pick a run, confirm, then run with the same live display.
- **Test request:** pick a target (public plans endpoint, login check, or a scraper's first request). It shows
  status, latency, size and the first keys, and offers to save the request and response under `runs/.tests/`.
- **Settings:** edit defaults saved to `runs/.prefs.json`, show where config comes from (flag > env > .env >
  prefs > built-in default), and reset.

## 7. Implementation outline (after the agents finish)

```
higgsfield_scraper/interactive/
  __init__.py       run_interactive() entry; TTY / --no-input checks
  app.py            main menu loop, navigation stack (back/cancel)
  screens/          scrape.py · login.py · runs.py · normalize.py · test_request.py · settings.py
  options.py        per-scraper question specs → argparse Namespace (reuses each ScraperDef.add_args parser)
  prefs.py          runs/.prefs.json load/save (last choices per scraper)
  live.py           Rich Live dashboard fed by Scrapy signals + stats; shared Console with RichHandler
```

**Library:** questionary (built on prompt_toolkit) for prompts, plus Rich for panels, tables and the live display.
The final choice will follow the prototype's Windows Terminal and Git Bash results. Textual (a full-screen TUI) is
heavier, and is kept as a later option.

## 8. Acceptance checks

- [ ] Every wizard path produces exactly the same Namespace as the equivalent flags (unit test per scraper).
- [ ] Non-TTY, `--no-input` and `CI=1` never prompt (test).
- [ ] Ctrl+C during menus exits with code 130 and leaves no files; during a run it stops gracefully and writes a
      "partial" manifest.
- [ ] Password and code are never echoed, logged or written to the manifest (test with a log scan).
- [ ] Works in Windows Terminal, PowerShell, cmd and Git Bash (mintty: falls back to plain numbered prompts if
      prompt_toolkit can't use the console).
- [ ] `NO_COLOR=1` gives readable monochrome output.

Sources: [clig.dev](https://clig.dev/) · [PatternFly CLI handbook](https://www.patternfly.org/developer-resources/cli-handbook/writing-guidelines)
· [Build interactive CLI prompts that don't annoy users](https://dev.to/chengyixu/build-interactive-cli-prompts-that-dont-annoy-your-users-3m44)
· [CLI prompt libraries 2026 (questionary et al.)](https://www.pistack.xyz/posts/2026-07-27-cli-prompt-libraries-inquirerjs-enquirer-questionary-dialoguer/)
· [Python CLI menu libraries](https://brianbraatz.github.io/p/best-python-cli-menu-libraries)
