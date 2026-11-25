import json

from scrapy.http import Request, TextResponse
from scrapy.settings import Settings

from higgsfield_scraper.middlewares import HttpArchiveMiddleware
from higgsfield_scraper.run.context import RunContext


class _Stats:
    def __init__(self):
        self.d = {}

    def inc_value(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n


class _Signals:
    def connect(self, *a, **k):
        pass


class _Spider:
    pass


class _Crawler:
    def __init__(self, ctx):
        self.settings = Settings({"HIGGS_HTTP_ARCHIVE": True})
        self.stats = _Stats()
        self.signals = _Signals()
        self.spider = _Spider()
        self.spider.run_ctx = ctx


def test_archive_writes_request_response_body_curl_and_har(tmp_path):
    ctx = RunContext.create(tmp_path, "t")
    mw = HttpArchiveMiddleware(_Crawler(ctx))
    req = Request("https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?plan_set_key=ps_a3",
                  headers={"Authorization": "Bearer SECRET.JWT", "Accept": "application/json"},
                  meta={"endpoint": "plans", "params": {"plan_set_key": "ps_a3"}, "download_latency": 0.25})
    mw.process_request(req)
    body = b'{"plans": [], "country_code": "EG"}'
    resp = TextResponse(req.url, body=body, status=200, request=req,
                        headers={"Content-Type": "application/json", "Set-Cookie": "a=b"})
    assert mw.process_response(req, resp) is resp

    d = ctx.run_dir / "http" / "001_plans__plan_set_key-ps_a3"
    assert (d / "body.raw").read_bytes() == body                       # exact bytes
    rq = json.loads((d / "request.json").read_text("utf-8"))
    auth = next(h["value"] for h in rq["headers"] if h["name"] == "Authorization")
    assert auth == "Bearer ***" and "SECRET" not in (d / "curl.sh").read_text("utf-8")
    rs = json.loads((d / "response.json").read_text("utf-8"))
    assert rs["status"] == 200 and rs["bytes"] == len(body) and rs["latency_ms"] == 250.0
    assert any(h["name"] == "Set-Cookie" and h["value"] == "***" for h in rs["headers"])
    assert '"status": 200' in (d / "response.json").read_text("utf-8").replace("    ", " ")  # indented JSON

    # redirect hop from robots.txt is named after its origin, without the token-bearing query string
    hop = Request("https://x.cloudflareaccess.com/login?meta=eyJTOKEN",
                  meta={"redirect_urls": ["https://pricing.higgsfield.ai/robots.txt"]})
    mw.process_exception(hop, Exception("offsite"))
    assert (ctx.run_dir / "http" / "002_robots.txt_redirect__pricing.higgsfield.ai").is_dir()

    mw.spider_closed(None)
    har = json.loads((ctx.run_dir / "http" / "session.har").read_text("utf-8"))
    assert har["log"]["version"] == "1.2" and len(har["log"]["entries"]) == 2
    idx = [json.loads(x) for x in (ctx.run_dir / "http" / "index.jsonl").read_text("utf-8").splitlines()]
    assert [i["seq"] for i in idx] == [1, 2] and idx[1]["error"]


def _privacy_mw(tmp_path, with_profiles):
    from types import SimpleNamespace
    c = _Crawler(RunContext.create(tmp_path, "p"))
    c.spider.scraper_name = "site"                                  # a personal_data scraper
    c.spider.selection = SimpleNamespace(with_profiles=with_profiles)
    return HttpArchiveMiddleware(c)


def test_html_body_withheld_for_personal_data_scraper_without_opt_in(tmp_path):
    from higgsfield_scraper.middlewares import PRIVACY_WITHHELD
    html = b"<html><body>by @someone</body></html>"
    assert _privacy_mw(tmp_path, False)._privacy(html) == PRIVACY_WITHHELD
    assert _privacy_mw(tmp_path, True)._privacy(html) == html          # --with-profiles: byte-exact


def test_json_body_redacted_not_withheld(tmp_path):
    out = _privacy_mw(tmp_path, False)._privacy(b'{"username": "someone", "title": "x"}')
    assert json.loads(out) == {"username": "[redacted]", "title": "x"}
