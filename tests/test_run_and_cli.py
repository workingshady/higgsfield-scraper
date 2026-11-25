import json
import logging
import shutil
import subprocess
import sys

import pytest
from scrapy.http import Request, TextResponse

from higgsfield_scraper.cli import main
from higgsfield_scraper.run.context import RunContext, latest_run, slugify
from higgsfield_scraper.run.logging_setup import setup_logging, teardown_logging
from higgsfield_scraper.selection import Selection, normalize_version
from higgsfield_scraper.spiders.higgsfield import HiggsfieldSpider


def test_selection_presets_and_errors():
    assert Selection.build(plan_sets="us").plan_set_keys == ["ps_a3"]
    assert "max_v2" in Selection.build(plan_sets="tiers").plan_set_keys
    assert len(Selection.build(plan_sets="all").plan_set_keys) == 25
    with pytest.raises(ValueError):
        Selection.build(plan_sets="nope")
    with pytest.raises(ValueError):
        Selection.build(sections="prices")
    assert normalize_version("51") == normalize_version("v51") == "v51.0.0"
    assert "plan_benefits" in Selection.build(sections="models").endpoints()


def test_run_context_layout(tmp_path):
    ctx = RunContext.create(tmp_path, "My Label!")
    assert ctx.run_id.endswith("_my-label") and ctx.logs_dir.is_dir() and ctx.raw_dir.is_dir() and ctx.output_dir.is_dir()
    ctx2 = RunContext.create(tmp_path, "My Label!", now=ctx.started_at)
    assert ctx2.run_dir != ctx.run_dir                       # same second -> suffixed, never overwritten
    ctx.write_manifest({"status": "success"})
    ctx.finalize()
    assert latest_run(tmp_path) == ctx.run_dir
    assert json.loads((tmp_path / "index.jsonl").read_text().splitlines()[0])["status"] == "success"
    assert slugify("") == "run"


def test_logging_files(tmp_path):
    hs = setup_logging(tmp_path, "rid", "WARNING")
    logging.getLogger("higgsfield_scraper.test").info("hello app")
    logging.getLogger("scrapy.core").warning("hello scrapy")
    teardown_logging(hs)
    assert not (tmp_path / "app.log").exists() and not (tmp_path / "scrapy.log").exists()   # only with --split-logs
    run_log = (tmp_path / "run.log").read_text("utf-8")
    assert "hello app" in run_log and "hello scrapy" in run_log
    assert "hello scrapy" in (tmp_path / "errors.log").read_text("utf-8")
    assert "hello app" not in (tmp_path / "errors.log").read_text("utf-8")
    ev = [json.loads(x) for x in (tmp_path / "events.jsonl").read_text("utf-8").splitlines()]
    assert ev[0]["run.id"] == "rid" and ev[0]["event"] == "app.started"
    assert (tmp_path / "access.jsonl").read_text("utf-8") == ""


def test_logging_split_logs(tmp_path):
    hs = setup_logging(tmp_path, "rid", "WARNING", split_logs=True)
    logging.getLogger("higgsfield_scraper.test").info("hello app")
    logging.getLogger("scrapy.core").warning("hello scrapy")
    teardown_logging(hs)
    assert "hello app" in (tmp_path / "app.log").read_text("utf-8")
    assert "hello scrapy" in (tmp_path / "scrapy.log").read_text("utf-8")
    assert "hello app" not in (tmp_path / "scrapy.log").read_text("utf-8")


def test_spider_requests_and_parse(fixtures_dir):
    sp = HiggsfieldSpider(selection=Selection.build(sections="all", plan_sets="ps_a3"))
    urls = [r.url for r in sp.build_requests()]
    assert any("plan_set_key=ps_a3" in u for u in urls) and any("job-sets/costs" in u for u in urls)
    assert not any("packages" in u for u in urls)                     # auth not requested without token

    class _Stats:
        def __init__(self):
            self.d = {}

        def inc_value(self, k, n=1):
            self.d[k] = self.d.get(k, 0) + n

    class _Crawler:
        stats = _Stats()

    sp.crawler = _Crawler()
    body = json.loads((fixtures_dir / "plans__plan_set_key-ps_a3.json").read_text("utf-8"))["body"]
    req = Request("https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?plan_set_key=ps_a3",
                  meta={"endpoint": "plans", "params": {"plan_set_key": "ps_a3"}})
    resp = TextResponse(req.url, body=json.dumps(body).encode(), encoding="utf-8", request=req, status=200)
    items = list(sp.parse_api(resp))
    kinds = [i["kind"] for i in items]
    assert kinds[0] == "raw_response" and kinds.count("plan") == 14 and "plan_set" in kinds


def test_cli_dry_run_and_info(capsys):
    assert main(["scrape", "--dry-run", "--sections", "plans", "--plan-sets", "ps_a3"]) == 0
    out = capsys.readouterr().out
    assert "plan_set_key=ps_a3" in out
    assert main(["plan-sets"]) == 0 and main(["sections"]) == 0
    assert main(["scrape", "--plan-sets", "bogus", "--dry-run"]) == 2


def test_cli_normalize_offline_end_to_end(tmp_path, fixtures_dir, capsys):
    src = tmp_path / "runs" / "20260101-000000_fixture"
    shutil.copytree(fixtures_dir, src / "raw")
    rc = main(["normalize", "--run", str(src), "--runs-dir", str(tmp_path / "runs"), "--sections", "all",
               "--plan-sets", "ps_a3,default", "--log-level", "ERROR"])
    assert rc == 0
    run = latest_run(tmp_path / "runs")
    m = json.loads((run / "manifest.json").read_text("utf-8"))
    assert m["status"] == "success" and m["counts"]["models"] >= 80
    assert (run / "output" / "dataset.json").exists() and (run / "logs" / "run.log").exists()
    assert main(["show", "model", "kling3_0", "--run", str(run)]) == 0
    assert "audio=on" in capsys.readouterr().out
    teardown_logging([h for h in logging.getLogger().handlers if getattr(h, "_higgs", False)])


@pytest.mark.live
def test_live_scrape(tmp_path):
    rc = subprocess.run([sys.executable, "-m", "higgsfield_scraper", "scrape", "--sections", "all", "--runs-dir",
                         str(tmp_path), "--label", "pytest-live", "--log-level", "WARNING"], timeout=600).returncode
    assert rc == 0
    m = json.loads((latest_run(tmp_path) / "manifest.json").read_text("utf-8"))
    assert m["counts"]["plans"] > 0 and m["counts"]["models"] > 0
