"""Interactive (menu) mode: argparse -> questions -> argv, dynamic registry, prefs, TTY fallback, login (mocked).

No network and no real terminal: prompts are answered by ScriptedPrompter (or by questionary itself driven through a
prompt_toolkit pipe input), and scrapes go to an injected runner instead of a child process.
"""
from __future__ import annotations

import argparse
import io
import json
from dataclasses import dataclass

import pytest
from rich.console import Console

from higgsfield_scraper import cli
from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import ScraperDef
from higgsfield_scraper.interactive import app as app_mod
from higgsfield_scraper.interactive import options as opt
from higgsfield_scraper.interactive import prefs as prefs_mod
from higgsfield_scraper.interactive.prompter import ScriptedPrompter


@pytest.fixture(autouse=True)
def _isolated_prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_PREFS", str(tmp_path / "prefs" / "prefs.json"))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("HF_NO_MENU", raising=False)


def make_console() -> Console:
    return Console(file=io.StringIO(), width=140, color_system=None, force_terminal=False)


def make_app(answers, runner=None, console=None):
    calls = []

    def fake_runner(argv):
        calls.append(list(argv))
        return 0

    a = app_mod.App(prompter=ScriptedPrompter(answers), console=console or make_console(),
                    runner=runner or fake_runner)
    return a, calls


# ---------------------------------------------------------------- argparse -> questions
def by_dest(qs):
    return {q.dest: q for q in qs}


def test_questions_follow_the_flag_parser():
    qs = by_dest(opt.questions_for("community"))
    assert not {"token", "dry_run", "label", "help"} & set(qs)            # secrets / handled elsewhere
    assert qs["type"].kind == "select" and "video" in qs["type"].choices and qs["type"].default == "all"
    assert qs["with_profiles"].kind == "confirm" and qs["with_profiles"].default is False
    assert qs["max_items"].kind == "int" and qs["max_items"].default is None
    assert qs["delay"].kind == "float" and qs["delay"].default == 1.0
    assert qs["verbose"].kind == "count"
    assert qs["feeds"].kind == "text" and qs["feeds"].default == "trending"
    assert qs["download_media"].choices == ["none", "thumbs", "full", "all"]
    assert qs["max_items"].help.startswith("stop after N")
    groups = opt.groups_of(list(qs.values()))
    assert groups[0].startswith("community:") and groups.index("limits") < groups.index("logging")


def test_paired_store_true_false_become_one_confirm():
    qs = by_dest(opt.questions_for("blog"))
    q = qs["with_content"]
    assert q.kind == "confirm" and q.default is True and len(q.actions) == 2
    assert q.title == "with content" and q.to_argv(True) == [] and q.to_argv(False) == ["--no-content"]
    md = qs["write_markdown"]                                               # store_false only (--no-markdown)
    assert md.title == "write markdown" and md.to_argv(False) == ["--no-markdown"] and md.to_argv(True) == []


def test_question_validation_and_to_argv():
    qs = by_dest(opt.questions_for("community"))
    mi = qs["max_items"]
    assert mi.validate("10") is True and mi.validate("") is True
    assert mi.validate("ten") is not True and mi.validate("-1") is not True
    assert qs["delay"].validate("0.5") is True and qs["delay"].validate("x") is not True
    assert mi.to_argv("") == [] and mi.to_argv("10") == ["--max-items", "10"]
    assert qs["delay"].to_argv("1.0") == [] and qs["delay"].to_argv("2") == ["--delay", "2"]
    assert qs["type"].to_argv("all") == [] and qs["type"].to_argv("video") == ["--type", "video"]
    assert qs["with_profiles"].to_argv(True) == ["--with-profiles"] and qs["with_profiles"].to_argv(False) == []
    assert qs["verbose"].to_argv("2") == ["--verbose", "--verbose"]
    assert qs["models"].to_argv("kling,seedance") == ["--models", "kling,seedance"]
    assert qs["feeds"].initial() == "trending" and qs["max_items"].initial() == "" and qs["type"].initial("video") == "video"


# ---------------------------------------------------------------- answers -> argv
def test_build_argv_matches_the_equivalent_flags():
    answers = {"type": "video", "max_items": "10", "with_profiles": False, "delay": "1.0", "feeds": "trending,top",
               "detail": True, "verbose": "1"}
    argv = opt.build_argv("community", answers, label="my-run")
    assert argv == ["scrape", "community", "--feeds", "trending,top", "--type", "video", "--detail",
                    "--max-items", "10", "--verbose", "--label", "my-run"]
    a, err = opt.parse_argv(argv)
    assert err is None
    flags = cli.build_parser().parse_args(["scrape", "community", "--type", "video", "--max-items", "10",
                                           "--feeds", "trending,top", "--detail", "-v", "--label", "my-run"])
    assert {k: v for k, v in vars(a).items() if k != "func"} == {k: v for k, v in vars(flags).items() if k != "func"}
    assert opt.build_argv("pricing", {}) == ["scrape", "pricing"]          # quick = defaults = no flags
    assert opt.command_line(argv).startswith(
        "python -m higgsfield_scraper scrape community --feeds trending,top --type video")


def test_parse_argv_reports_errors_and_label_validation():
    a, err = opt.parse_argv(["scrape", "community", "--type", "nope"])
    assert a is None and "invalid choice" in err
    assert opt.validate_label("full-ps_a3") is True and opt.validate_label("") is True
    assert opt.validate_label("bad label!") is not True and opt.validate_label("-x") is not True
    assert opt.suggested_label(["scrape", "community", "--type", "video"]) == "community-trending-video"


# ---------------------------------------------------------------- the scrape wizard
def test_scrape_wizard_customize_summary_and_run(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_RUNS_DIR", str(tmp_path / "runs"))
    # the community "what to scrape" group: feeds, type, models, preset-ids, resolution, publication-ids
    answers = ["scrape", ["community"], "custom", ["community: what to scrape", "limits"],
               "trending", "video", "", "", "", "",                            # feeds type models preset res pub-ids
               "10", "", "",                                                    # max-items max-pages page-size
               ...,                                                             # label: accept suggestion
               "run", "quit"]
    console = make_console()
    app, calls = make_app(answers, console=console)
    assert app.run() == 0
    assert calls == [["scrape", "community", "--type", "video", "--max-items", "10"]]
    out = console.file.getvalue()
    assert "python -m higgsfield_scraper scrape community --type video --max-items 10" in out
    assert "community-trending-video" in out                                    # suggested label in the summary
    saved = json.loads(prefs_mod.prefs_path().read_text(encoding="utf-8"))
    assert saved["last_scrapers"] == ["community"]
    assert saved["scrapers"]["community"]["answers"]["max_items"] == "10"


def test_multiple_scrapers_run_in_order_and_cancel_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_RUNS_DIR", str(tmp_path / "runs"))
    codes = iter([130])
    calls = []

    def runner(argv):
        calls.append(argv)
        return next(codes)

    answers = ["scrape", ["pricing", "community"], "quick", "nightly", "quick", ..., "run",
               False,                                       # pricing cancelled -> don't run the rest
               "quit"]
    app, _ = make_app(answers, runner=runner)
    assert app.run() == 0
    assert calls == [["scrape", "pricing", "--label", "nightly"]]


def test_edit_and_dry_run_then_cancel(monkeypatch):
    dry = []
    monkeypatch.setattr(app_mod.App, "dry_run", lambda self, argv: dry.append(argv) or 0)
    answers = ["scrape", ["pricing"], "quick", ..., "edit", "custom", ["pricing: output options"],
               "", True, False, ..., "dry", "cancel", "quit"]
    app, calls = make_app(answers)
    assert app.run() == 0
    assert calls == [] and dry == [["scrape", "pricing", "--include-hidden-plans"]]


def test_ctrl_c_in_a_prompt_goes_back_and_quits_cleanly():
    app, calls = make_app(["scrape", None, None])          # Esc/Ctrl-C at scraper pick -> menu; at menu -> quit
    assert app.run() == 130 and calls == []


# ---------------------------------------------------------------- dynamic registry
@dataclass
class _Sel:
    colour: str
    deep: bool

    def to_dict(self):
        return {"colour": self.colour, "deep": self.deep}


def _fake_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("fake: what to scrape")
    g.add_argument("--colour", choices=["red", "blue"], default="red", help="which colour")
    g.add_argument("--deep", action="store_true", help="go deep")
    g.add_argument("--depth", type=int, default=3, help="how deep")


FAKE = ScraperDef(name="fakescraper", description="a scraper the menu has never heard of", spider_cls=object,
                  model_by_kind={}, id_field_by_kind={}, add_args=_fake_args,
                  make_selection=lambda a: _Sel(a.colour, a.deep), selection_from_dict=lambda d: _Sel(**d),
                  parse_envelope=lambda e, s: [], build_dataset=lambda e, s, m: {}, write_outputs=lambda d, p: [],
                  default_label=lambda s: s.colour)


def test_new_registry_scraper_appears_with_its_options(monkeypatch):
    real = registry.available()
    monkeypatch.setattr(registry, "available", lambda: {**real, "fakescraper": FAKE})
    real_get = registry.get
    monkeypatch.setattr(registry, "get", lambda n: FAKE if n == "fakescraper" else real_get(n))
    qs = by_dest(opt.questions_for("fakescraper"))
    assert qs["colour"].kind == "select" and qs["deep"].kind == "confirm" and qs["depth"].kind == "int"
    assert "max_items" in qs and "delay" in qs                               # shared flags come along

    seen = {}

    def scraper_pick(method, message, kw):
        seen["choices"] = [v for _, v in kw["choices"]]
        return ["fakescraper"]

    answers = ["scrape", scraper_pick, "custom", ["fake: what to scrape"], "blue", True, "7", ..., "run", "quit"]
    console = make_console()
    app, calls = make_app(answers, console=console)
    assert app.run() == 0
    assert "fakescraper" in seen["choices"]
    assert calls == [["scrape", "fakescraper", "--colour", "blue", "--deep", "--depth", "7"]]
    assert "fakescraper-blue" in console.file.getvalue()                    # label from its default_label


# ---------------------------------------------------------------- prefs
def test_prefs_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "x" / "p.json"
    monkeypatch.setenv("HF_PREFS", str(path))
    assert prefs_mod.prefs_path() == path
    p = prefs_mod.load_prefs()
    assert p == prefs_mod.default_prefs()
    prefs_mod.remember_scrape(p, "community", {"max_items": "5", "type": "video"}, "lbl")
    p["last_scrapers"] = ["community"]
    prefs_mod.save_prefs(p)
    again = prefs_mod.load_prefs()
    assert again["scrapers"]["community"] == {"answers": {"max_items": "5", "type": "video"}, "label": "lbl"}
    assert again["last_scrapers"] == ["community"]
    assert "    \"version\"" in path.read_text(encoding="utf-8")              # indent=4
    p["remember"] = False
    prefs_mod.remember_scrape(p, "blog", {"x": 1}, None)
    assert "blog" not in p["scrapers"]
    path.write_text("not json", encoding="utf-8")
    assert prefs_mod.load_prefs() == prefs_mod.default_prefs()
    assert prefs_mod.reset_prefs() == prefs_mod.default_prefs() and not path.exists()


def test_default_prefs_location(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_PREFS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert prefs_mod.prefs_path() == tmp_path / "higgsfield_scraper" / "prefs.json"


def test_last_used_options_are_offered(tmp_path, monkeypatch):
    p = prefs_mod.default_prefs()
    prefs_mod.remember_scrape(p, "community", {"max_items": "5"}, None)
    p["last_scrapers"] = ["community"]
    prefs_mod.save_prefs(p)
    seen = {}

    def pick_scrapers(method, message, kw):
        seen["checked"] = list(kw["checked"])
        return ["community"]

    def pick_mode(method, message, kw):
        seen["modes"] = [v for _, v in kw["choices"]]
        return "last"

    app, calls = make_app(["scrape", pick_scrapers, pick_mode, ..., "run", "quit"])
    assert app.run() == 0
    assert seen == {"checked": ["community"], "modes": ["quick", "last", "custom"]}
    assert calls == [["scrape", "community", "--max-items", "5"]]


# ---------------------------------------------------------------- entry / TTY fallback
class _Tty(io.StringIO):
    def __init__(self, tty):
        super().__init__()
        self._tty = tty

    def isatty(self):
        return self._tty


def test_should_auto_launch_needs_a_tty_and_no_ci(monkeypatch):
    from higgsfield_scraper import interactive
    monkeypatch.setattr("sys.stdin", _Tty(True))
    monkeypatch.setattr("sys.stdout", _Tty(True))
    assert interactive.should_auto_launch() is True
    monkeypatch.setenv("CI", "1")
    assert interactive.should_auto_launch() is False
    monkeypatch.delenv("CI")
    monkeypatch.setattr("sys.stdin", _Tty(False))
    assert interactive.should_auto_launch() is False


def test_no_args_without_tty_keeps_the_pricing_default(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "cmd_scrape", lambda a: seen.append(a.scraper) or 0)
    monkeypatch.setattr("sys.argv", ["higgsfield_scraper"])
    monkeypatch.setattr("sys.stdin", _Tty(False))
    launched = []
    monkeypatch.setattr("higgsfield_scraper.interactive.launch", lambda *a, **k: launched.append(1) or 0)
    assert cli.main() == 0
    assert seen == ["pricing"] and launched == []
    assert cli.main([]) == 0 and seen == ["pricing", "pricing"]          # explicit empty argv: never the menu


def test_no_args_on_a_tty_opens_the_menu(monkeypatch):
    launched = []
    monkeypatch.setattr("sys.argv", ["higgsfield_scraper"])
    monkeypatch.setattr(cli, "_auto_menu", lambda: True)
    monkeypatch.setattr("higgsfield_scraper.interactive.launch", lambda *a, **k: launched.append(1) or 0)
    assert cli.main() == 0 and launched == [1]


@pytest.mark.parametrize("argv", [["menu"], ["-i"], ["--interactive"]])
def test_menu_without_a_terminal_exits_2_with_a_hint(argv, capsys):
    assert cli.main(argv) == 2                       # pytest's stdin is not a TTY
    err = capsys.readouterr().err.strip()
    assert len(err.splitlines()) == 1 and "--help" in err


def test_missing_questionary_is_reported(monkeypatch):
    from higgsfield_scraper import interactive
    monkeypatch.setitem(__import__("sys").modules, "questionary", None)
    msg = interactive.prompt_problem()
    assert "interactive" in msg and "pip install" in msg
    assert interactive.launch() == 2


def test_real_questionary_prompter_through_a_pipe():
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from higgsfield_scraper.interactive.prompter import QuestionaryPrompter
    with create_pipe_input() as inp:
        inp.send_text("\x1b[A\r")                                 # main menu: up from "Scrape" wraps to "Quit"
        app = app_mod.App(prompter=QuestionaryPrompter(input=inp, output=DummyOutput()), console=make_console(),
                          runner=lambda argv: 0)
        assert app.run() == 0
    with create_pipe_input() as inp:
        inp.send_text("12345\r6\r")                               # 5 digits rejected, then 123456 accepted
        p = QuestionaryPrompter(input=inp, output=DummyOutput())
        assert p.password("code", validate=app_mod.v_code) == "123456"


# ---------------------------------------------------------------- login / logout (mocked, no network)
def test_login_flow_with_code_retry(monkeypatch):
    from higgsfield_scraper.core import auth_login
    monkeypatch.setenv("HF_EMAIL", "me@example.com")
    monkeypatch.setenv("HF_PASSWORD", "s3cret-pw")
    calls = {"start": [], "finish": []}

    def start(email, password):
        calls["start"].append((email, password))
        return {"status": "code_sent", "sent_to": "m*@example.com"}

    def finish(code):
        calls["finish"].append(code)
        if len(calls["finish"]) == 1:
            raise auth_login.LoginFailed("attempt_second_factor -> HTTP 422 form_code_incorrect: wrong code")
        return {"status": "complete", "expires_at": 0}

    monkeypatch.setattr(auth_login, "start_login", start)
    monkeypatch.setattr(auth_login, "finish_login", finish)
    monkeypatch.setattr(app_mod.App, "auth_check", lambda self: {"ok": True})
    assert app_mod.v_code("12345") is not True and app_mod.v_code("12a456") is not True and app_mod.v_code("123456")

    console = make_console()
    app, _ = make_app([..., True, "111111", "222222"], console=console)     # email default, use HF_PASSWORD
    assert app.login() is True
    assert calls == {"start": [("me@example.com", "s3cret-pw")], "finish": ["111111", "222222"]}
    out = console.file.getvalue()
    assert "s3cret-pw" not in out and "111111" not in out and "222222" not in out
    assert "m*@example.com" in out and "code rejected" in out and "login complete" in out


def test_login_typed_password_and_failure(monkeypatch):
    from higgsfield_scraper.core import auth_login
    monkeypatch.delenv("HF_PASSWORD", raising=False)
    monkeypatch.setenv("HF_EMAIL", "me@example.com")

    def start(email, password):
        raise auth_login.LoginFailed("sign-in rejected: HTTP 422 form_password_incorrect: bad")

    monkeypatch.setattr(auth_login, "start_login", start)
    console = make_console()
    app, _ = make_app(["other@example.com", "typed-pw"], console=console)
    assert app.login() is False
    out = console.file.getvalue()
    assert "login failed" in out and "typed-pw" not in out
    assert app.p.asked[1] == ("password", "Password")                         # masked prompt


def test_logout_deletes_the_cached_session(tmp_path, monkeypatch):
    from higgsfield_scraper.core import auth_login
    cache, pending = tmp_path / "clerk_client.json", tmp_path / "pending_login.json"
    cache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth_login, "CACHE_PATH", cache)
    monkeypatch.setattr(auth_login, "PENDING_PATH", pending)
    app, _ = make_app([False, True])
    assert app.logout() is False and cache.exists()                          # declined
    assert app.logout() is True and not cache.exists()
    assert app.logout() is False                                              # nothing left


# ---------------------------------------------------------------- runner / live panel / misc
def test_runner_uses_interactive_mode_and_live_panel(monkeypatch):
    from higgsfield_scraper.interactive import runner
    seen = {}

    def fake_scrape(a, **kw):
        seen.update(kw, scraper=a.scraper, max_items=a.max_items)
        return 0

    monkeypatch.setattr(cli, "cmd_scrape", fake_scrape)
    assert runner.main(["scrape", "community", "--max-items", "3"]) == 0
    assert seen["invocation_mode"] == "interactive" and seen["console"] is not None
    assert callable(seen["on_crawler"]) and seen["scraper"] == "community" and seen["max_items"] == 3
    assert app_mod.runner_cmd(["scrape", "blog"])[1:] == ["-m", "higgsfield_scraper.interactive.runner",
                                                          "scrape", "blog"]


def test_live_progress_counts_signals():
    from scrapy import signals

    from higgsfield_scraper.interactive.live import LiveProgress

    class Sig:
        def __init__(self):
            self.handlers = {}

        def connect(self, fn, signal, weak=True):
            assert weak is False
            self.handlers[signal] = fn

    class Stats:
        def get_value(self, k):
            return {"retry/count": 2}.get(k, 0)

    class Crawler:
        signals, stats = Sig(), Stats()

    class Resp:
        status = 200

    lp = LiveProgress(make_console(), "scrape x")
    lp.start = lambda: None                                 # no live thread in tests
    c = Crawler()
    lp.attach(c)
    h = c.signals.handlers
    h[signals.request_scheduled](request=None, spider=None)
    h[signals.response_received](response=Resp(), request=None, spider=None)
    h[signals.item_scraped](item={"kind": "community_generation"}, response=None, spider=None)
    h[signals.item_dropped](item={}, response=None, exception=None, spider=None)
    assert (lp.scheduled, lp.responses, lp.items, lp.dropped) == (1, 1, 1, 1)
    con = make_console()
    con.print(lp)
    text = con.file.getvalue()
    assert "2xx 1" in text and "community_generation 1" in text and "retries 2" in text
    h[signals.engine_stopped]()


def test_run_one_reports_the_new_run_folder(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setenv("HF_RUNS_DIR", str(runs))

    def runner(argv):
        d = runs / "20991231-235959_x"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"status": "partial", "items_count": 4}), encoding="utf-8")
        return 3

    app, _ = make_app([], runner=runner)
    res = app.run_one(["scrape", "pricing"])
    assert res["status"] == "partial" and res["code"] == 3 and res["items"] == 4
    assert res["run_dir"].name == "20991231-235959_x"


def test_clean_runs_dry_run_then_confirm(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    for name in ("20240101-000000_a", "20240102-000000_b", "20240103-000000_c"):
        (runs / name).mkdir(parents=True)
        (runs / name / "manifest.json").write_text(json.dumps({"status": "failure"}), encoding="utf-8")
    monkeypatch.setenv("HF_RUNS_DIR", str(runs))
    app, _ = make_app(["1", "", False, "1", "", True])
    app.clean_runs()
    assert len(list(runs.iterdir())) == 3                                     # declined
    app.clean_runs()
    assert sorted(p.name for p in runs.iterdir()) == ["20240103-000000_c"]


def test_test_request_uses_the_first_public_request(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=20):
        seen["url"], seen["headers"] = url, headers
        return {"url": url, "status": 200, "latency_ms": 12, "bytes": 3, "json_keys": "a, b"}

    monkeypatch.setattr(app_mod, "http_get", fake_get)
    console = make_console()
    app, _ = make_app(["pricing"], console=console)
    res = app.test_request()
    assert res["status"] == 200 and "/subscriptions/v2/plans" in seen["url"]
    assert not any(k.lower() == "authorization" for k in seen["headers"])
    assert "latency_ms" in console.file.getvalue()


# ---------------------------------------------------------------- pricing tools (diff / crosscheck)
def _pricing_runs(tmp_path, monkeypatch):
    for name in ("20261120-000000_old", "20261121-000000_new"):
        d = tmp_path / "runs" / name
        (d / "output").mkdir(parents=True)
        (d / "output" / "dataset.json").write_text("{}", encoding="utf-8")
        (d / "manifest.json").write_text(json.dumps({"scraper": "pricing", "status": "success", "run_id": name}),
                                         encoding="utf-8")
    monkeypatch.setenv("HF_RUNS_DIR", str(tmp_path / "runs"))
    seen = []
    import higgsfield_scraper.cli as cli
    monkeypatch.setattr(cli, "cmd_diff", lambda ns: seen.append(("diff", ns.old, ns.new, ns.out)) or 0)
    monkeypatch.setattr(cli, "cmd_crosscheck", lambda ns: seen.append(("cross", ns.run, ns.save)) or 0)
    return tmp_path / "runs", seen


def test_menu_lists_pricing_tools_and_every_registered_scraper():
    assert "pricing" in [v for _, v in app_mod.MENU]
    assert "site" in registry.available()


def test_pricing_tools_diff_picked_runs(tmp_path, monkeypatch):
    runs, seen = _pricing_runs(tmp_path, monkeypatch)
    old, new = str(runs / "20261120-000000_old"), str(runs / "20261121-000000_new")
    a, _ = make_app(["diff_pick", old, new, "report.md"])
    a.pricing_tools()
    assert seen == [("diff", old, new, "report.md")]


def test_pricing_tools_default_diff_and_crosscheck(tmp_path, monkeypatch):
    runs, seen = _pricing_runs(tmp_path, monkeypatch)
    a, _ = make_app(["diff", ""])
    a.pricing_tools()
    run = str(runs / "20261121-000000_new")
    a, _ = make_app(["cross", run, True])
    a.pricing_tools()
    assert seen == [("diff", None, None, None), ("cross", run, True)]
