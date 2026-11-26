"""The menu. Screens return to the main menu; Ctrl-C inside a prompt = back, at the main menu = quit (130).

Scrapes and normalizes run in a child process (`interactive/runner.py`) built from the same argv the flag CLI
takes, so the menu process never starts Scrapy's (single-use) reactor and several scrapes can run in a row.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from .. import __version__
from ..core import registry
from . import options as opt
from .prefs import load_prefs, prefs_path, remember_scrape, reset_prefs, save_prefs
from .prompter import Prompter

EXIT_STATUS = {0: "success", 1: "failure", 2: "usage error", 3: "partial", 4: "blocked", 130: "cancelled"}
STATUS_STYLE = {"success": "green", "partial": "yellow", "blocked": "red", "failure": "red", "cancelled": "magenta",
                "usage error": "red", "running": "cyan"}
MENU = [
    ("Scrape                     pick scrapers, options, run", "scrape"),
    ("Normalize a past run       re-parse raw/ offline", "normalize"),
    ("Browse runs                table, summaries, errors", "runs"),
    ("Login / session            status, log in, log out", "login"),
    ("Pricing tools              diff two runs, cross-check pricing.md", "pricing"),
    ("Test request               one GET of a public endpoint", "test"),
    ("Show config                resolved settings (secrets hidden)", "config"),
    ("Clean old runs             dry run first, then confirm", "clean"),
    ("Settings / prefs           remembered choices", "settings"),
    ("Quit", "quit"),
]
BACK = ("<- Back", None)


def runner_cmd(argv: list[str]) -> list[str]:
    return [sys.executable, "-m", "higgsfield_scraper.interactive.runner", *argv]


def run_child(argv: list[str]) -> int:
    """Run one scrape/normalize in a fresh process (one Scrapy reactor per process). Ctrl-C goes to the child too;
    the menu waits for it to finish its graceful shutdown instead of dying with it."""
    proc = subprocess.Popen(runner_cmd(argv))
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:
            continue                            # the child got the same Ctrl-C and is stopping (status: cancelled)


def default_runs_dir() -> str:
    return os.environ.get("HF_RUNS_DIR", "runs")


def run_dirs(runs_dir: str | Path) -> list[Path]:
    from ..run.context import RUN_DIR_RE
    root = Path(runs_dir)
    if not root.exists():
        return []
    return sorted((d for d in root.iterdir() if d.is_dir() and RUN_DIR_RE.match(d.name)), key=lambda d: d.name,
                  reverse=True)


def recent_runs(runs_dir: str | Path, limit: int = 20) -> list[tuple[Path, dict]]:
    from ..run.context import read_manifest
    return [(d, read_manifest(d)) for d in run_dirs(runs_dir)[:limit]]


def session_summary() -> str:
    """Cheap (no network) description of the configured login."""
    from ..core.auth_login import CACHE_PATH
    if os.environ.get("HF_TOKEN"):
        return "static token (HF_TOKEN)"
    if CACHE_PATH.exists():
        return "logged in (cached session)"
    if os.environ.get("HF_CLERK_CLIENT"):
        return "browser cookie (HF_CLERK_CLIENT)"
    return "not logged in"


def v_code(s: str) -> bool | str:
    return True if (s or "").strip().isdigit() and len(s.strip()) == 6 else "enter exactly 6 digits"


def v_email(s: str) -> bool | str:
    s = (s or "").strip()
    return True if "@" in s and "." in s.rsplit("@", 1)[-1] else "enter an email address"


class App:
    def __init__(self, prompter: Optional[Prompter] = None, console: Any = None,
                 runner: Optional[Callable[[list[str]], int]] = None):
        if prompter is None:
            from .prompter import QuestionaryPrompter
            prompter = QuestionaryPrompter()
        if console is None:
            from ..run.logging_setup import make_console
            console = make_console()
        self.p, self.console, self.run_child = prompter, console, runner or run_child
        self.prefs = load_prefs()

    # ============================================================== main loop
    def header(self) -> None:
        from rich.panel import Panel
        names = " · ".join(registry.available())
        self.console.print(Panel(f"scrapers: {names}\nsession:  {session_summary()}\n"
                                 "[dim]Ctrl-C = back · flags: python -m higgsfield_scraper --help[/]",
                                 title=f"[bold]higgsfield-scraper {__version__}[/] · interactive",
                                 border_style="blue", expand=False), highlight=False)

    def run(self) -> int:
        screens = {"scrape": self.scrape, "normalize": self.normalize, "runs": self.browse_runs,
                   "login": self.login_menu, "test": self.test_request, "pricing": self.pricing_tools, "config": self.show_config,
                   "clean": self.clean_runs, "settings": self.settings}
        while True:
            self.header()
            try:
                choice = self.p.select("What do you want to do?", MENU, default="scrape")
            except KeyboardInterrupt:
                choice = None
            if choice is None:
                self.console.print("bye (cancelled)")
                return 130
            if choice == "quit":
                return 0
            try:
                screens[choice]()
            except KeyboardInterrupt:
                self.console.print("[magenta]cancelled[/] - back to the main menu")
            except Exception as e:                     # a failing screen must not kill the menu
                self.console.print(f"[red]error:[/] {type(e).__name__}: {e}")

    def say(self, msg: str) -> None:
        self.console.print(msg)

    # ============================================================== scrape
    def scrape(self) -> None:
        avail = registry.available()
        last = [n for n in self.prefs.get("last_scrapers") or [] if n in avail] or [registry.DEFAULT_SCRAPER]
        names = self.p.checkbox("Which scrapers? (they run one after another, each in its own run folder)",
                                [(f"{n:10} {s.description}", n) for n, s in avail.items()], checked=last, min_one=True)
        if not names:
            return
        plans: dict[str, dict] = {}
        for n in names:
            if not self.configure(n, plans):
                return
        while True:
            self.summary(plans)
            act = self.p.select("Proceed?", [("Run", "run"), ("Dry run (print the first requests)", "dry"),
                                              ("Edit options", "edit"), ("Cancel", "cancel")], default="run")
            if act in (None, "cancel"):
                self.say("cancelled - nothing was run")
                return
            if act == "edit":
                which = names[0] if len(names) == 1 else self.p.select(
                    "Edit which scraper?", [(n, n) for n in names] + [BACK])
                if which and not self.configure(which, plans):
                    return
                continue
            self.remember(plans)
            if act == "dry":
                for n, plan in plans.items():
                    self.dry_run(plan["argv"])
                continue
            self.run_all(plans)
            return

    def configure(self, name: str, plans: dict[str, dict]) -> bool:
        """Options + label for one scraper -> plans[name]. False when the user backed out."""
        qs = opt.questions_for(name)
        saved = (self.prefs.get("scrapers") or {}).get(name) or {}
        current = (plans.get(name) or {}).get("answers")
        modes = [("Quick - defaults", "quick"), ("Customize options", "custom")]
        if saved.get("answers"):
            modes.insert(1, ("Last used options", "last"))
        while True:
            mode = self.p.select(f"{name}: options", modes, default="custom" if current else "quick")
            if mode is None:
                return False
            if mode == "quick":
                answers: Optional[dict] = {}
            elif mode == "last":
                answers = dict(saved["answers"])
            else:
                answers = self.customize(name, qs, dict(current if current is not None else saved.get("answers") or {}))
                if answers is None:
                    return False
            argv = opt.build_argv(name, answers, questions=qs)
            _, err = opt.parse_argv(argv)
            if err:
                self.say(f"[red]invalid options:[/] {err} - try again")
                continue
            try:
                from ..cli import default_label
                suggested = default_label(opt.parse_argv(argv)[0])
            except ValueError as e:                   # make_selection rejected a value (e.g. unknown plan set)
                self.say(f"[red]invalid options:[/] {e} - try again")
                current = answers
                continue
            break
        dflt = saved.get("label") if saved.get("label") and self.prefs.get("remember", True) else suggested
        label = self.p.text(f"{name}: run label", default=dflt, validate=opt.validate_label,
                            instruction=f"(suggested: {suggested})")
        if label is None:
            return False
        label = label.strip() or suggested
        lab = None if label == suggested else label
        plans[name] = {"answers": answers, "label": lab, "shown_label": label, "questions": qs,
                       "argv": opt.build_argv(name, answers, lab, questions=qs)}
        return True

    def customize(self, name: str, qs: list[opt.Question], answers: dict) -> Optional[dict]:
        groups = opt.groups_of(qs)
        own = [g for g in groups if g not in opt.COMMON_GROUPS]
        pre = own + [g for g in opt.DEFAULT_GROUPS if g in groups]
        counts = {g: sum(1 for q in qs if q.group == g) for g in groups}
        pick = self.p.checkbox(f"{name}: which option groups do you want to change?",
                               [(f"{g} ({counts[g]})", g) for g in groups], checked=pre)
        if pick is None:
            return None
        for q in qs:
            if q.group not in pick:
                continue
            val = self.ask_question(q, answers.get(q.dest))
            if val is None:
                return None
            answers[q.dest] = val
        return answers

    def ask_question(self, q: opt.Question, prev: Any = None) -> Any:
        if q.help:
            self.console.print(f"  [dim]{q.flag}: {q.help}[/]", highlight=False)
        init = q.initial(prev)
        if q.kind == "select":
            return self.p.select(q.title, [(f"{c}{'  (default)' if c == q.default else ''}", c) for c in q.choices],
                                 default=init)
        if q.kind == "checkbox":
            return self.p.checkbox(q.title, [(str(c), c) for c in q.choices], checked=init)
        if q.kind == "confirm":
            return self.p.confirm(f"{q.title}?", default=init)
        dflt = "" if q.default is None else opt._fmt_default(q.default)
        return self.p.text(q.title, default=init, validate=q.validate,
                           instruction=f"(empty = {'default ' + dflt if dflt else 'not set'})")

    def summary(self, plans: dict[str, dict]) -> None:
        from rich.panel import Panel
        from rich.table import Table
        t = Table(title="Review", show_lines=True, expand=False)
        t.add_column("scraper", style="bold")
        t.add_column("label")
        t.add_column("changed options (everything else: defaults)")
        for n, plan in plans.items():
            ch = opt.changed(n, plan["answers"], plan["questions"])
            t.add_row(n, plan["shown_label"], "\n".join(f"{f} {v}" for f, v in ch) or "(defaults)")
        self.console.print(t)
        cmds = "\n".join(opt.command_line(plan["argv"]) for plan in plans.values())
        self.console.print(Panel(cmds, title="equivalent command" + ("s" if len(plans) > 1 else ""),
                                 border_style="cyan", expand=False), highlight=False)

    def remember(self, plans: dict[str, dict]) -> None:
        if not self.prefs.get("remember", True):
            return
        self.prefs["last_scrapers"] = list(plans)
        for n, plan in plans.items():
            remember_scrape(self.prefs, n, plan["answers"], plan["label"])
        try:
            save_prefs(self.prefs)
        except OSError as e:
            self.say(f"[yellow]could not save prefs:[/] {e}")

    def dry_run(self, argv: list[str]) -> int:
        from ..cli import cmd_scrape
        a, err = opt.parse_argv([*argv, "--dry-run"])
        if err:
            self.say(f"[red]{err}[/]")
            return 2
        self.console.rule(f"dry run: {a.scraper}")
        try:
            return cmd_scrape(a)
        except ValueError as e:
            self.say(f"[red]error:[/] {e}")
            return 2
        finally:
            sys.stdout.flush()

    def run_one(self, argv: list[str]) -> dict:
        a, _ = opt.parse_argv(argv)
        runs_dir = Path(getattr(a, "runs_dir", None) or default_runs_dir())
        before = set(run_dirs(runs_dir))
        self.console.print(f"[dim]$ {opt.command_line(argv)}[/]", highlight=False)
        t0 = time.monotonic()
        code = self.run_child(argv)
        new = [d for d in run_dirs(runs_dir) if d not in before]
        from ..run.context import read_manifest
        m = read_manifest(new[0]) if new else {}
        status = "blocked" if code == 4 else (m.get("status") or EXIT_STATUS.get(code, f"exit {code}"))
        return {"argv": argv, "code": code, "status": status, "run_dir": new[0] if new else None,
                "secs": round(time.monotonic() - t0, 1), "items": m.get("items_count")}

    def run_all(self, plans: dict[str, dict]) -> list[dict]:
        results = []
        names = list(plans)
        for i, n in enumerate(names):
            self.console.rule(f"[{i + 1}/{len(names)}] scrape {n}")
            res = self.run_one(plans[n]["argv"])
            res["scraper"] = n
            results.append(res)
            if res["code"] == 130 and i + 1 < len(names):
                if not self.p.confirm(f"{n} was cancelled. Run the remaining scrapers ({', '.join(names[i + 1:])})?",
                                      default=False):
                    break
        self.show_results(results)
        return results

    def show_results(self, results: list[dict]) -> None:
        from rich.table import Table
        t = Table(title="Results")
        for c in ("scraper", "status", "exit", "secs", "items"):
            t.add_column(c, no_wrap=True)
        t.add_column("run folder", overflow="fold")
        for r in results:
            st = r["status"]
            t.add_row(r.get("scraper") or "-", f"[{STATUS_STYLE.get(st, 'white')}]{st}[/]", str(r["code"]),
                      str(r["secs"]), str(r.get("items") if r.get("items") is not None else "-"),
                      str(r["run_dir"].resolve()) if r["run_dir"] else "-")
        self.console.print(t)

    # ============================================================== normalize
    def normalize(self) -> None:
        runs_dir = default_runs_dir()
        runs = [(d, m) for d, m in recent_runs(runs_dir, 30) if (d / "raw").is_dir()][:20]
        if not runs:
            self.say(f"no runs with a raw/ folder in {runs_dir}/")
            return
        pick = self.p.select("Normalize which run? (re-parses raw/ offline into a new run)",
                             [(f"{d.name:48} {m.get('scraper') or '?':10} {m.get('status') or '?'}", str(d))
                              for d, m in runs] + [BACK])
        if not pick:
            return
        argv = ["normalize", "--run", pick, "--runs-dir", runs_dir]
        self.say(f"[cyan]{opt.command_line(argv)}[/]")
        if not self.p.confirm("Run it?", default=True):
            return
        res = self.run_one(argv)
        res["scraper"] = "normalize"
        self.show_results([res])

    # ============================================================== runs
    def browse_runs(self) -> None:
        from rich.table import Table
        runs_dir = default_runs_dir()
        runs = recent_runs(runs_dir, 20)
        if not runs:
            self.say(f"no runs yet in {runs_dir}/")
            return
        t = Table(title=f"Recent runs ({Path(runs_dir).resolve()})")
        t.add_column("run", no_wrap=True)
        for c in ("scraper", "status", "secs", "items"):
            t.add_column(c, no_wrap=True)
        t.add_column("counts", overflow="ellipsis", no_wrap=True, max_width=44)
        for d, m in runs:
            st = m.get("status") or "?"
            counts = m.get("counts") if isinstance(m.get("counts"), dict) else {}
            t.add_row(d.name, m.get("scraper") or "?", f"[{STATUS_STYLE.get(st, 'white')}]{st}[/]",
                      str(m.get("duration_s") or "-"), str(m.get("items_count") if m.get("items_count") is not None
                                                           else "-"),
                      ", ".join(f"{k}={v}" for k, v in counts.items() if v))
        self.console.print(t)
        while True:
            pick = self.p.select("Open which run?", [(d.name, str(d)) for d, _ in runs] + [BACK])
            if not pick:
                return
            self.run_actions(Path(pick))

    def run_actions(self, run: Path) -> None:
        while True:
            act = self.p.select(f"{run.name}", [("Show summary", "summary"), ("Show errors.log (tail)", "errors"),
                                                ("Open the folder", "open"), BACK])
            if not act:
                return
            if act == "summary":
                self.show_summary(run)
            elif act == "errors":
                p = run / "logs" / "errors.log"
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-30:] if p.exists() else []
                self.console.print("\n".join(lines) if lines else "(no warnings or errors)", highlight=False,
                                   markup=False)
            elif act == "open":
                self.open_folder(run)

    def show_summary(self, run: Path) -> None:
        from rich.markdown import Markdown
        p = run / "output" / "summary.md"
        if p.exists():
            self.console.print(Markdown(p.read_text(encoding="utf-8")))
            return
        from ..run.context import read_manifest
        m = read_manifest(run)
        keep = ("run_id", "scraper", "status", "exit_code", "duration_s", "close_reason", "counts", "limits_hit",
                "items_count", "requests_count", "errors_count", "error")
        self.console.print_json(json.dumps({k: m.get(k) for k in keep if k in m}, default=str))

    def open_folder(self, run: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(run.resolve()))                     # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(run.resolve())])
        except Exception as e:
            self.say(f"could not open the folder ({e}); it is {run.resolve()}")

    # ============================================================== login
    def login_menu(self) -> None:
        while True:
            self.say(f"session: [bold]{session_summary()}[/]")
            act = self.p.select("Login / session", [("Check session (auth-check)", "check"), ("Log in", "login"),
                                                    ("Log out (delete the cached session)", "logout"), BACK])
            if not act:
                return
            {"check": self.auth_check, "login": self.login, "logout": self.logout}[act]()

    def auth_check(self) -> dict:
        from ..core.auth import TokenProvider
        prov = TokenProvider.from_env()
        if not prov.configured:
            self.say("no login configured: choose [bold]Log in[/], or set HF_CLERK_CLIENT in .env")
            return {"configured": False, "ok": False}
        st = {k: v for k, v in prov.status().items() if k != "session_id"}
        self.console.print_json(json.dumps(st, default=str))
        return st

    def login(self) -> bool:
        from ..core.auth_login import LoginError, finish_login, start_login
        email = self.p.text("Email", default=os.environ.get("HF_EMAIL", ""), validate=v_email)
        if email is None:
            return False
        password = None
        if os.environ.get("HF_PASSWORD"):
            use = self.p.confirm("Use the password from HF_PASSWORD (not shown)?", default=True)
            if use is None:
                return False
            if use:
                password = os.environ["HF_PASSWORD"]
        if password is None:
            password = self.p.password("Password", validate=lambda s: bool(s) or "enter the password")
            if password is None:
                return False
        try:
            self.say("signing in ...")
            res = start_login(email.strip(), password)
        except LoginError as e:
            self.say(f"[red]login failed:[/] {e}")
            return False
        finally:
            password = None                                   # don't keep the secret around
        if res.get("status") != "complete":
            self.say(f"Clerk emailed a one-time code to [bold]{res.get('sent_to')}[/] (valid ~15 min).")
            for attempt in range(3):
                code = self.p.password("Enter the 6-digit code from your email", validate=v_code)
                if code is None:
                    self.say("login not finished - later: Login / session -> Log in, or `login --code NNNNNN`")
                    return False
                try:
                    finish_login(code.strip())
                    break
                except LoginError as e:
                    self.say(f"[red]code rejected:[/] {e}")
                    if "expired" in str(e) or "no pending" in str(e) or attempt == 2:
                        return False
        self.say("[green]login complete[/] - session cached in runs/.auth/ (auto-refreshing tokens)")
        self.auth_check()
        return True

    def logout(self) -> bool:
        from ..core.auth_login import CACHE_PATH, PENDING_PATH
        if not CACHE_PATH.exists() and not PENDING_PATH.exists():
            self.say("no cached session to delete")
            return False
        if not self.p.confirm(f"Delete the cached session ({CACHE_PATH.name})? You'll need to log in again.",
                              default=False):
            return False
        for p in (CACHE_PATH, PENDING_PATH):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        self.say("logged out (cached session deleted)")
        if os.environ.get("HF_TOKEN") or os.environ.get("HF_CLERK_CLIENT"):
            self.say("[yellow]note:[/] HF_TOKEN / HF_CLERK_CLIENT is still set in the environment/.env and is "
                     "still used for login-only endpoints")
        return True

    # ============================================================== test request
    def test_request(self) -> Optional[dict]:
        avail = registry.available()
        name = self.p.select("Send one GET to which scraper's first public endpoint?",
                             [(n, n) for n in avail] + [BACK], default=registry.DEFAULT_SCRAPER)
        if not name:
            return None
        from ..cli import first_requests
        a, err = opt.parse_argv(["scrape", name])
        reqs = [r for r in first_requests(a) if r.method == "GET" and not r.meta.get("auth")
                and b"Authorization" not in r.headers]
        if not reqs:
            self.say("this scraper has no public first request")
            return None
        res = http_get(reqs[0].url, {k: v for k, v in reqs[0].headers.to_unicode_dict().items()
                                     if k.lower() not in ("authorization", "cookie")})
        from rich.table import Table
        t = Table.grid(padding=(0, 2))
        for k in ("url", "status", "latency_ms", "bytes", "content_type", "json_keys", "error"):
            if res.get(k) is not None:
                t.add_row(f"[bold]{k}[/]", str(res[k]))
        self.console.print(t)
        return res

    # ============================================================== pricing tools
    def pricing_tools(self) -> None:
        runs_dir = default_runs_dir()
        pricing = [(d, m) for d, m in recent_runs(runs_dir, 60)
                   if (m.get("scraper") or "pricing") == "pricing" and m.get("status") == "success"
                   and (d / "output" / "dataset.json").is_file()][:25]
        act = self.p.select("Pricing tools", [
            ("Diff: latest pricing run vs the previous compatible one", "diff"),
            ("Diff: pick the two runs", "diff_pick"),
            ("Cross-check a run with the official higgsfield.ai/pricing.md", "cross"), BACK])
        if not act:
            return
        choices = [(f"{d.name:48} {m.get('status') or '?'}", str(d)) for d, m in pricing]
        if act != "diff" and not choices:
            self.say(f"no successful pricing runs in {runs_dir}/ - scrape pricing first")
            return
        if act == "diff":
            argv = ["diff"]
        elif act == "diff_pick":
            old = self.p.select("Old run (before)", choices + [BACK])
            if not old:
                return
            new = self.p.select("New run (after)", [c for c in choices if c[1] != old] + [BACK])
            if not new:
                return
            argv = ["diff", "--old", old, "--new", new]
        else:
            run = self.p.select("Cross-check which run?", choices + [BACK])
            if not run:
                return
            argv = ["crosscheck", "--run", run]
            if self.p.confirm("Save pricing.md + the report into <run>/crosscheck/?", default=False):
                argv.append("--save")
        if act == "diff" or act == "diff_pick":
            out = self.p.text("Also write a report file? (.md or .json, empty = no)", default="",
                              validate=lambda v: (not v.strip() or v.strip().lower().endswith((".md", ".json")))
                              or "must end in .md or .json")
            if out is None:
                return
            if out.strip():
                argv += ["--out", out.strip()]
        self.say(f"[cyan]{opt.command_line(argv)}[/]")
        from ..cli import build_parser
        ns = build_parser().parse_args(argv)
        code = ns.func(ns)
        self.say(f"exit code {code}")

    # ============================================================== misc
    def show_config(self) -> None:
        from ..cli import cmd_show_config
        cmd_show_config(argparse.Namespace(json=False))

    def clean_runs(self) -> None:
        from ..cli import cmd_runs_clean
        from ..run.retention import plan_cleanup
        keep = self.p.text("Keep the newest N runs", default="10",
                           validate=lambda s: s.strip().isdigit() or "enter a whole number")
        if keep is None:
            return
        days = self.p.text("...and keep runs younger than D days", default="",
                           validate=lambda s: _is_number(s) or "a number, or empty", instruction="(empty = ignore)")
        if days is None:
            return
        ns = argparse.Namespace(runs_dir=default_runs_dir(), keep_last=int(keep), json=False, yes=False,
                                keep_days=float(days) if days.strip() else None)
        cmd_runs_clean(ns)                                         # dry run
        todo = [c for c in plan_cleanup(ns.runs_dir, ns.keep_last, ns.keep_days) if c.action == "delete"]
        if not todo:
            self.say("nothing to delete")
            return
        if self.p.confirm(f"Delete these {len(todo)} run folder(s)?", default=False):
            ns.yes = True
            cmd_runs_clean(ns)

    def settings(self) -> None:
        while True:
            self.say(f"prefs file: {prefs_path()}  (env HF_PREFS overrides)")
            self.console.print_json(json.dumps(self.prefs, default=str))
            rem = self.prefs.get("remember", True)
            act = self.p.select("Settings", [(f"Remember choices: {'on' if rem else 'off'} (toggle)", "toggle"),
                                             ("Reset remembered choices", "reset"), BACK])
            if not act:
                return
            if act == "toggle":
                self.prefs["remember"] = not rem
            elif act == "reset":
                if not self.p.confirm("Forget all remembered scrapers, labels and options?", default=False):
                    continue
                self.prefs = reset_prefs()
            try:
                save_prefs(self.prefs)
            except OSError as e:
                self.say(f"[yellow]could not save prefs:[/] {e}")


def _is_number(s: str) -> bool:
    if not (s or "").strip():
        return True
    try:
        return float(s) >= 0
    except ValueError:
        return False


def http_get(url: str, headers: Optional[dict] = None, timeout: float = 20) -> dict:
    """One plain GET with the project's browser-like headers (constants.DEFAULT_HEADERS + USER_AGENT)."""
    from ..constants import DEFAULT_HEADERS, USER_AGENT
    h = {**DEFAULT_HEADERS, "User-Agent": USER_AGENT, **(headers or {})}
    out: dict[str, Any] = {"url": url}
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, headers=h, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            out.update(status=resp.status, content_type=resp.headers.get("Content-Type"))
    except urllib.error.HTTPError as e:
        body = e.read() or b""
        out.update(status=e.code, content_type=e.headers.get("Content-Type") if e.headers else None)
    except (urllib.error.URLError, OSError) as e:
        out.update(status=None, error=f"{type(e).__name__}: {getattr(e, 'reason', e)}",
                   latency_ms=int((time.monotonic() - t0) * 1000))
        return out
    out["latency_ms"] = int((time.monotonic() - t0) * 1000)
    out["bytes"] = len(body)
    try:
        data = json.loads(body)
        out["json_keys"] = ", ".join(list(data)[:12]) if isinstance(data, dict) else f"list[{len(data)}]"
    except ValueError:
        pass
    return out
