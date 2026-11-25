"""Logging / run-folder / CLI upgrade: events, JSON envelope, redaction, heartbeat, statuses, exit codes, retention."""
import io
import json
import logging
import shutil
import sys
from datetime import datetime, timedelta, timezone

import pytest
from scrapy.http import Request, TextResponse
from scrapy.settings import Settings

from higgsfield_scraper.cli import main
from higgsfield_scraper.core import registry
from higgsfield_scraper.core.base import CommonOptions
from higgsfield_scraper.core.redact import redact, redact_argv, redact_text
from higgsfield_scraper.extensions import HeartbeatExtension
from higgsfield_scraper.middlewares import AccessLogMiddleware, HttpArchiveMiddleware
from higgsfield_scraper.run.context import RunContext, latest_run, normalize_status, read_manifest
from higgsfield_scraper.run.logging_setup import (ENVELOPE, RESOURCE, DropReporter, emit, setup_logging,
                                                  teardown_logging)
from higgsfield_scraper.run.manager import RunManager, classify, exit_code_for

FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyIsImV4cCI6OTk5OTk5OTk5OX0.c2lnbmF0dXJlX3NlY3JldA"
SECRETS = [FAKE_JWT, "hunter2pass", "clientcookieSECRET", "s3cr3tqs", "pw-in-url"]


def _lines(path):
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


@pytest.fixture
def logs(tmp_path):
    hs = setup_logging(tmp_path, "rid-1", "WARNING", scraper="pricing")
    yield tmp_path
    teardown_logging(hs)


def _close(hs_dir):
    teardown_logging([h for h in logging.getLogger().handlers if getattr(h, "_higgs", False)])


# ------------------------------------------------------------------ envelope
def test_json_envelope_order_and_required_fields(logs):
    log = logging.getLogger("higgsfield_scraper.t")
    emit(log, "info", "endpoint.started", "plans started", endpoint__name="plans", zeta=1, alpha=2)
    _close(logs)
    ev = [e for e in _lines(logs / "events.jsonl") if e["event"] == "endpoint.started"][0]
    keys = list(ev)
    assert keys[:len(ENVELOPE) + len(RESOURCE)] == [*ENVELOPE, *RESOURCE]
    rest = keys[len(ENVELOPE) + len(RESOURCE):]
    assert rest == sorted(rest) == ["alpha", "endpoint.name", "zeta"]
    assert ev["run.id"] == "rid-1" and ev["scraper.name"] == "pricing" and ev["service.name"] == "higgsfield_scraper"
    assert ev["level"] == "INFO" and ev["logger"] == "higgsfield_scraper.t" and ev["message"] == "plans started"
    assert ev["timestamp"].endswith("Z") and len(ev["timestamp"]) == len("2026-11-25T14:30:05.120Z")
    assert isinstance(ev["process.pid"], int) and ev["host.name"]
    first = _lines(logs / "events.jsonl")[0]
    assert first["event"] == "app.started"


def test_access_log_only_gets_request_lines_and_run_log_is_human(logs):
    log = logging.getLogger("higgsfield_scraper.t")
    emit(log, "info", "http.request.finished", "GET plans -> 200", http__response__status_code=200)
    emit(log, "info", "run.started", "run started")
    _close(logs)
    acc = _lines(logs / "access.jsonl")
    assert [a["event"] for a in acc] == ["http.request.finished"]
    run_log = (logs / "run.log").read_text("utf-8").splitlines()
    assert any(" INFO " in x and " run.started " in x and "run started" in x for x in run_log)
    assert all(x.split()[0].endswith("Z") for x in run_log)


def test_crlf_injection_is_escaped_in_run_log(logs):
    log = logging.getLogger("higgsfield_scraper.t")
    log.warning("user said %s", "hi\r\n2026-01-01T00:00:00.000Z CRITICAL forged line")
    emit(log, "info", "x.y", "msg", note="a\nb")
    _close(logs)
    text = (logs / "run.log").read_text("utf-8")
    lines = text.splitlines()
    assert not any(x.startswith("2026-01-01T00:00:00.000Z") for x in lines)
    assert "hi\\r\\n2026-01-01" in text and "note=a\\nb" in text
    assert len([x for x in lines if not x.startswith("    |")]) == len(_lines(logs / "events.jsonl"))


def test_exception_fields_and_errors_log(logs):
    log = logging.getLogger("higgsfield_scraper.t")
    try:
        raise RuntimeError(f"boom password=hunter2pass {FAKE_JWT}")
    except RuntimeError:
        emit(log, "error", "external.call.failed", "call failed", exc_info=True)
    _close(logs)
    ev = [e for e in _lines(logs / "events.jsonl") if e["event"] == "external.call.failed"][0]
    assert ev["error.type"] == ev["exception.type"] == "RuntimeError"
    assert "boom" in ev["exception.message"] and "Traceback" in ev["exception.stacktrace"]
    err = (logs / "errors.log").read_text("utf-8")
    assert "Traceback" in err and "external.call.failed" in err
    for f in logs.iterdir():
        body = f.read_text("utf-8")
        assert "hunter2pass" not in body and FAKE_JWT not in body, f.name


def test_excepthook_logs_app_crashed(logs):
    sys.excepthook(ValueError, ValueError("token=s3cr3tqs"), None)
    _close(logs)
    ev = [e for e in _lines(logs / "events.jsonl") if e["event"] == "app.crashed"]
    assert ev and ev[0]["level"] == "CRITICAL" and "s3cr3tqs" not in json.dumps(ev)


def test_json_console_and_shared_rich_console(tmp_path, capsys):
    from rich.console import Console
    buf = io.StringIO()
    hs = setup_logging(None, "rid-2", "INFO", console=Console(file=buf, width=200), announce=False)
    emit(logging.getLogger("higgsfield_scraper.t"), "info", "run.started", "hello from rich")
    teardown_logging(hs)
    assert "hello from rich" in buf.getvalue()
    hs = setup_logging(None, "rid-3", "INFO", log_format="json", announce=False)
    emit(logging.getLogger("higgsfield_scraper.t"), "info", "run.started", "hello json", url__full="https://u:pw-in-url@x/")
    teardown_logging(hs)
    err = capsys.readouterr().err.strip().splitlines()[-1]
    d = json.loads(err)
    assert d["event"] == "run.started" and d["run.id"] == "rid-3" and "pw-in-url" not in err


def test_drop_reporter_caps_logging(logs):
    rep = DropReporter(logging.getLogger("higgsfield_scraper.t"), cap=3)
    for i in range(10):
        rep("plan", f"p{i}", "bad")
    _close(logs)
    ev = _lines(logs / "events.jsonl")
    assert len([e for e in ev if e["event"] == "item.dropped"]) == 3
    assert len([e for e in ev if e["event"] == "item.dropped.suppressed"]) == 1 and rep.count == 10


# ------------------------------------------------------------------ redaction
def test_redact_text_and_structures():
    s = redact_text(f"GET https://bob:pw-in-url@h.io/p?token={FAKE_JWT}&sig=s3cr3tqs&plan_set_key=ps_a3 "
                    f"Authorization: Bearer abc.def cookie: __client=clientcookieSECRET; x=1")
    for secret in SECRETS + ["abc.def"]:
        assert secret not in s
    assert "plan_set_key=ps_a3" in s and "h.io/p" in s
    d = redact({"headers": {"Cookie": "a", "X-Api-Key": "k"}, "hf_email": "me@x.io", "token": None, "n": 1})
    assert d["headers"] == {"Cookie": "[REDACTED]", "X-Api-Key": "[REDACTED]"} and d["hf_email"] == "[REDACTED]"
    assert d["token"] is None and d["n"] == 1
    assert redact_argv(["x", "--token", "abc", "--hf-password=zz"]) == ["x", "--token", "[REDACTED]",
                                                                         "--hf-password=[REDACTED]"]


class _Stats:
    def __init__(self):
        self.d = {}

    def inc_value(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n

    def set_value(self, k, v):
        self.d[k] = v

    def get_stats(self):
        return dict(self.d)

    def get_value(self, k, default=None):
        return self.d.get(k, default)


class _Signals:
    def connect(self, *a, **k):
        pass


class _Spider:
    pass


class _Crawler:
    def __init__(self, ctx, **settings):
        self.settings = Settings({"HIGGS_HTTP_ARCHIVE": True, **settings})
        self.stats = _Stats()
        self.signals = _Signals()
        self.spider = _Spider()
        self.spider.run_ctx = ctx
        self.spider.scraper_name = "pricing"


def test_secrets_never_reach_logs_manifest_or_http_archive(tmp_path, monkeypatch):
    """A fake run: secrets in the URL, headers, exception text, argv and manifest args never land on disk."""
    monkeypatch.setattr(sys, "argv", ["higgsfield_scraper", "scrape", "--token", FAKE_JWT])
    ctx = RunContext.create(tmp_path, "secret-scan")
    hs = setup_logging(ctx.logs_dir, ctx.run_id, "DEBUG", scraper="pricing")
    ctx.write_manifest({"status": "running", "args": {"token": FAKE_JWT, "hf_password": "hunter2pass"},
                        "command": sys.argv, "note": f"cookie=__client=clientcookieSECRET"})
    crawler = _Crawler(ctx)
    access, archive = AccessLogMiddleware(crawler), HttpArchiveMiddleware(crawler)
    url = f"https://bob:pw-in-url@fnf-api-gw.higgsfield.ai/x?token={FAKE_JWT}&signature=s3cr3tqs&page=2"
    req = Request(url, headers={"Authorization": f"Bearer {FAKE_JWT}", "Cookie": "__client=clientcookieSECRET"},
                  meta={"endpoint": "feed", "params": {"page": "2", "token": FAKE_JWT}, "download_latency": 0.1})
    for mw in (access, archive):
        mw.process_request(req)
    resp = TextResponse(req.url, body=b'{"ok": true}', status=200, request=req,
                        headers={"Set-Cookie": "__session=clientcookieSECRET"})
    archive.process_response(req, resp)
    access.process_response(req, resp)
    err = ConnectionError(f"failed for {url} password=hunter2pass")
    archive.process_exception(req, err)
    access.process_exception(req, err)
    log = logging.getLogger("higgsfield_scraper.t")
    log.info("fetched %s", url)
    emit(log, "info", "auth.token.refreshed", "minted", cookie="__client=clientcookieSECRET", jwt=FAKE_JWT)
    try:
        raise ValueError(f"bad token {FAKE_JWT} at {url}")
    except ValueError:
        log.exception("crash with secret")
    archive.spider_closed(None)
    ctx.write_manifest({"status": "success", "finished_at": "x"})
    ctx.finalize()
    teardown_logging(hs)

    acc = _lines(ctx.logs_dir / "access.jsonl")
    assert len(acc) == 2 and acc[0]["http.response.status_code"] == 200 and acc[0]["request_id"]
    assert acc[0]["request_id"] == acc[1]["request_id"]            # same request id across attempts
    for k in ("http.request.method", "url.full", "server.address", "duration_ms", "size_bytes", "retry.attempt",
              "endpoint.name", "outcome"):
        assert k in acc[0], k
    scanned = 0
    for f in ctx.run_dir.rglob("*"):
        if f.is_file() and f.name != "body.raw":
            body = f.read_text("utf-8", errors="replace")
            scanned += 1
            for secret in SECRETS:
                assert secret not in body, (secret, f)
    for f in tmp_path.glob("*.json*"):
        for secret in SECRETS:
            assert secret not in f.read_text("utf-8"), (secret, f)
    assert scanned >= 8


# ------------------------------------------------------------------ heartbeat
def test_heartbeat_event_and_manifest_progress(tmp_path):
    from twisted.internet.task import Clock
    ctx = RunContext.create(tmp_path, "hb")
    hs = setup_logging(ctx.logs_dir, ctx.run_id, "WARNING", scraper="community")
    ctx.write_manifest({"status": "running"})
    crawler = _Crawler(ctx, HIGGS_HEARTBEAT=0.05, CLOSESPIDER_PAGECOUNT=100)
    crawler.spider.common = CommonOptions(max_items=10)
    crawler.spider.primary_count = 4
    crawler.stats.d.update({"downloader/request_count": 6, "downloader/response_count": 5, "item_scraped_count": 9,
                            "log_count/ERROR": 1})
    ext = HeartbeatExtension.from_crawler(crawler)
    ext.clock = Clock()
    ext.spider_opened()
    ext.clock.advance(0.05)
    ext.clock.advance(0.05)
    ext.spider_closed()
    teardown_logging(hs)
    beats = [e for e in _lines(ctx.logs_dir / "events.jsonl") if e["event"] == "worker.heartbeat"]
    assert len(beats) == 2
    b = beats[0]
    for k in ("uptime_s", "requests.count", "responses.count", "errors.count", "items.count", "rate_per_min",
              "memory.usage_mb", "percent", "eta_s"):
        assert k in b, k
    assert b["responses.count"] == 5 and b["percent"] == 40.0 and b["progress.basis"] == "max_items"
    m = read_manifest(ctx.run_dir)
    assert m["progress"]["percent"] == 40.0 and m["progress"]["beats"] == 2 and m["updated_at"].endswith("Z")


def test_heartbeat_disabled_with_zero():
    from scrapy.exceptions import NotConfigured
    with pytest.raises(NotConfigured):
        HeartbeatExtension.from_crawler(_Crawler(None, HIGGS_HEARTBEAT=0))


# ------------------------------------------------------------------ statuses / exit codes
def test_status_mapping_and_exit_codes():
    sdef = registry.get("pricing")
    ok = {"ok": True}
    assert classify({}, ok, sdef, "finished") == ("success", False)
    assert classify({"higgs/responses/plans/500": 1}, ok, sdef, "finished")[0] == "partial"
    assert classify({}, ok, sdef, "closespider_pagecount")[0] == "partial"
    assert classify({"higgs/blocked": 1}, ok, sdef, "blocked_by_bot_protection") == ("partial", True)
    assert classify({}, ok, sdef, "shutdown")[0] == "cancelled"
    assert classify({}, {"ok": False}, sdef, None, interrupted=True)[0] == "cancelled"
    assert classify({}, {"ok": False}, sdef, "finished")[0] == "failure"
    assert classify({}, ok, sdef, "finished", crashed=True)[0] == "failure"
    assert [exit_code_for(s) for s in ("success", "failure", "partial", "cancelled")] == [0, 1, 3, 130]
    assert exit_code_for("partial", blocked=True) == 4
    assert normalize_status("failed") == "failure"


def test_cli_usage_errors_exit_2(capsys):
    with pytest.raises(SystemExit) as e:
        main(["runs", "--limit", "notanumber"])
    assert e.value.code == 2
    assert main(["scrape", "--plan-sets", "bogus", "--dry-run"]) == 2
    assert main(["runs", "clean", "--runs-dir", "nowhere-xyz"]) == 2           # needs --keep-last/--keep-days


def test_help_documents_exit_codes(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "130" in out and "partial" in out and "blocked" in out


# ------------------------------------------------------------------ manifest / run folder
def test_normalize_manifest_markers_and_hooks(tmp_path, fixtures_dir, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["higgsfield_scraper", "normalize", "--token", FAKE_JWT])
    src = tmp_path / "runs" / "20260101-000000_fixture"
    shutil.copytree(fixtures_dir, src / "raw")
    from higgsfield_scraper.selection import Selection
    mgr = RunManager(tmp_path / "runs", "norm", "ERROR")
    rc = mgr.normalize(src, Selection.build(sections="all", plan_sets="ps_a3,default"),
                       args={"token": "***"}, invocation_mode="interactive")
    assert rc == 0
    run = latest_run(tmp_path / "runs")
    m = read_manifest(run)
    for k in ("schema_version", "status", "started_at", "updated_at", "finished_at", "duration_ms", "command", "cwd",
              "invocation", "host", "git", "progress", "close_reason", "error", "outputs", "exit_code"):
        assert k in m, k
    assert m["status"] == "success" and m["invocation"]["mode"] == "interactive" and m["schema_version"] == 2
    assert m["started_at"].endswith("Z") and m["finished_at"].endswith("Z")
    assert FAKE_JWT not in json.dumps(m) and "[REDACTED]" in m["command"]
    out = m["outputs"]["output/dataset.json"]
    assert len(out["sha256"]) == 64 and out["size_bytes"] > 0
    assert (run / "_SUCCESS").exists()
    latest = json.loads((tmp_path / "runs" / "latest.json").read_text("utf-8"))
    assert latest["dir"] == run.name and (tmp_path / "runs" / "LATEST").read_text().strip() == run.name
    ev = _lines(run / "logs" / "events.jsonl")
    names = [e["event"] for e in ev]
    for e in ("app.started", "run.started", "config.loaded", "run.finished", "cli.flag.deprecated"):
        assert e in names, e
    fin = [e for e in ev if e["event"] == "run.finished"][0]
    assert fin["outcome"] == "success" and fin["exit_code"] == 0 and "duration_ms" in fin
    assert all(e["run.id"] == run.name for e in ev)
    assert not (run / "logs" / "app.log").exists()


def test_latest_only_updated_on_success(tmp_path):
    ok = RunContext.create(tmp_path, "ok")
    ok.write_manifest({"status": "success", "finished_at": "t"})
    ok.finalize()
    bad = RunContext.create(tmp_path, "bad", now=ok.started_at + timedelta(seconds=5))
    bad.write_manifest({"status": "failure"})
    bad.finalize()
    assert latest_run(tmp_path) == ok.run_dir and not (bad.run_dir / "_SUCCESS").exists()
    assert [json.loads(x)["status"] for x in (tmp_path / "index.jsonl").read_text().splitlines()] == ["success",
                                                                                                    "failure"]
    old = RunContext.create(tmp_path, "old", now=ok.started_at + timedelta(seconds=9))
    (old.run_dir / "manifest.json").write_text(json.dumps({"status": "failed"}))
    assert read_manifest(old.run_dir)["status"] == "failure"


def test_scrape_hook_signature():
    import inspect
    sig = inspect.signature(RunManager.scrape)
    assert sig.parameters["on_crawler"].default is None and sig.parameters["invocation_mode"].default == "flags"
    assert inspect.signature(RunManager.normalize).parameters["invocation_mode"].default == "flags"
    sp = inspect.signature(setup_logging)
    assert sp.parameters["console"].default is None and sp.parameters["log_format"].default == "console"


# ------------------------------------------------------------------ runs / show-config / auth-check
def _mk_run(root, name, status, days_ago, keep=False):
    d = root / name
    (d / "output").mkdir(parents=True)
    started = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    (d / "manifest.json").write_text(json.dumps({"status": status, "started_at": started}))
    if keep:
        (d / "KEEP").write_text("")
    return d


def test_runs_clean_dry_run_is_safe_and_yes_respects_protections(tmp_path, capsys):
    root = tmp_path / "runs"
    a = _mk_run(root, "20260101-000000_old-a", "success", 300)
    b = _mk_run(root, "20260102-000000_old-running", "running", 299)
    c = _mk_run(root, "20260103-000000_old-kept", "failure", 298, keep=True)
    d = _mk_run(root, "20260104-000000_latest-ok", "success", 297)
    e = _mk_run(root, "20260105-000000_old-failed", "failed", 296)
    f = _mk_run(root, "20260106-000000_new", "partial", 0)
    (root / "latest.json").write_text(json.dumps({"run.id": d.name, "dir": d.name}))
    (root / ".httpcache").mkdir()
    assert main(["runs", "clean", "--runs-dir", str(root), "--keep-last", "1", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True and plan["deleted"] == []
    acts = {r["run_id"]: r["action"] for r in plan["runs"]}
    assert acts == {a.name: "delete", b.name: "keep", c.name: "keep", d.name: "keep", e.name: "delete",
                    f.name: "keep"}
    assert all(p.exists() for p in (a, b, c, d, e, f))                    # dry run deletes nothing
    assert main(["runs", "clean", "--runs-dir", str(root), "--keep-last", "1", "--keep-days", "30", "--yes"]) == 0
    assert not a.exists() and not e.exists() and all(p.exists() for p in (b, c, d, f))
    assert (root / ".httpcache").exists()


def test_runs_json(tmp_path, capsys):
    ctx = RunContext.create(tmp_path, "j")
    ctx.write_manifest({"status": "success", "duration_ms": 1500})
    ctx.finalize()
    assert main(["runs", "--runs-dir", str(tmp_path), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["run_id"] == ctx.run_id and rows[0]["status"] == "success" and rows[0]["duration_s"] == 1.5


def test_show_config_and_auth_check_never_print_secrets(monkeypatch, capsys):
    monkeypatch.setenv("HF_TOKEN", FAKE_JWT)
    monkeypatch.setenv("HF_PASSWORD", "hunter2pass")
    monkeypatch.setenv("HF_CLERK_CLIENT", "clientcookieSECRET")
    monkeypatch.setenv("HF_LOG_FORMAT", "json")
    assert main(["show-config", "--json"]) == 0
    out = capsys.readouterr().out
    cfg = json.loads(out)
    assert cfg["env"]["HF_LOG_FORMAT"]["value"] == "json" and cfg["auth"]["configured"] is True
    for secret in SECRETS:
        assert secret not in out
    assert main(["show-config"]) == 0
    out = capsys.readouterr().out
    assert all(s not in out for s in SECRETS) and "precedence" in out
    monkeypatch.delenv("HF_TOKEN")
    monkeypatch.delenv("HF_CLERK_CLIENT")
    monkeypatch.setattr("higgsfield_scraper.core.auth_login.load_cached_client", lambda: None)
    assert main(["auth-check", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["configured"] is False


def test_verbosity_flags_resolve_levels(monkeypatch):
    from higgsfield_scraper.cli import build_parser
    from higgsfield_scraper.core.cli_common import resolve_log_levels
    monkeypatch.delenv("HF_LOG_LEVEL", raising=False)
    p = build_parser()
    assert resolve_log_levels(p.parse_args(["normalize"])) == ("INFO", "DEBUG", "INFO")
    assert resolve_log_levels(p.parse_args(["normalize", "-v"]))[0] == "DEBUG"
    assert resolve_log_levels(p.parse_args(["normalize", "-vv"])) == ("DEBUG", "DEBUG", "DEBUG")
    assert resolve_log_levels(p.parse_args(["normalize", "-q"]))[0] == "WARNING"
    assert resolve_log_levels(p.parse_args(["normalize", "-q", "--log-level", "error"]))[0] == "ERROR"
    a = p.parse_args(["scrape", "community", "--log-format", "json", "--no-color", "--heartbeat", "2"])
    assert a.log_format == "json" and a.no_color and a.heartbeat == 2.0
