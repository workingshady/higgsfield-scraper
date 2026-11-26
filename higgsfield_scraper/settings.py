"""Scrapy settings for higgsfield_scraper. The RunManager overrides FEEDS / LOG_* / HIGGS_* per run."""
from .constants import DEFAULT_HEADERS, USER_AGENT

BOT_NAME = "higgsfield_scraper"
SPIDER_MODULES = ["higgsfield_scraper.spiders"]
NEWSPIDER_MODULE = "higgsfield_scraper.spiders"

# --- politeness -------------------------------------------------------------
ROBOTSTXT_OBEY = False           # owner decision: robots.txt not obeyed by default (CLI: --obey-robots)
USER_AGENT = USER_AGENT
DEFAULT_REQUEST_HEADERS = DEFAULT_HEADERS
CONCURRENT_REQUESTS = 4
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 1.0             # randomized ±50% by default
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 15.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
DOWNLOAD_TIMEOUT = 60
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504, 522, 524, 408]
COOKIES_ENABLED = False          # public endpoints need no cookies
TELNETCONSOLE_ENABLED = False

# --- raw HTTP archive (<run>/http/: request.json, response.json, body.raw, curl.sh, session.har)
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "higgsfield_scraper.middlewares.RetryEventsMiddleware": 550,   # Scrapy retry + external.call.retried/failed events
    "higgsfield_scraper.core.auth.AuthMiddleware": 560,            # bearer token + auto refresh (meta auth=True only)
    "higgsfield_scraper.middlewares.HttpArchiveMiddleware": 580,   # below HttpCompression (590): sees decoded bodies
    "higgsfield_scraper.middlewares.AccountPrivacyMiddleware": 583,  # pricing --sections account: whitelist bodies first
    "higgsfield_scraper.middlewares.AccessLogMiddleware": 585,     # http.request.finished -> logs/access.jsonl
}
HIGGS_HTTP_ARCHIVE = True
RETRY_GIVE_UP_LOG_LEVEL = "DEBUG"  # our external.call.failed event replaces Scrapy's give-up error line

# --- pipelines --------------------------------------------------------------
ITEM_PIPELINES = {
    "higgsfield_scraper.pipelines.RawArchivePipeline": 50,
    "higgsfield_scraper.pipelines.ValidationPipeline": 300,
    "higgsfield_scraper.pipelines.DedupPipeline": 350,                # opt-in per scraper (pricing: none)
    "higgsfield_scraper.pipelines.CollectAndExportPipeline": 800,
}

# --- logging ----------------------------------------------------------------
LOG_FORMATTER = "higgsfield_scraper.logformatter.QuietLogFormatter"
LOG_LEVEL = "INFO"
LOGSTATS_INTERVAL = 0              # Scrapy's LogStats off: the worker.heartbeat extension replaces it
EXTENSIONS = {
    "scrapy.extensions.logstats.LogStats": None,
    "higgsfield_scraper.extensions.HeartbeatExtension": 500,
}
HIGGS_HEARTBEAT = 30.0             # seconds between worker.heartbeat events (CLI --heartbeat; 0 = off)

# --- dev cache (enable with --cache) ----------------------------------------
HTTPCACHE_ENABLED = False
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_EXPIRATION_SECS = 3600
HTTPCACHE_IGNORE_HTTP_CODES = [401, 403, 429, 500, 502, 503, 504]

FEED_EXPORT_ENCODING = "utf-8"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# --- project ----------------------------------------------------------------
HIGGS_RUNS_DIR = "runs"
HIGGS_RUN_LABEL = "scrapy-crawl"
