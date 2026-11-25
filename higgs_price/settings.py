"""Scrapy settings for higgs_price. The RunManager overrides FEEDS / LOG_* / HIGGS_* per run."""
from .constants import DEFAULT_HEADERS, USER_AGENT

BOT_NAME = "higgs_price"
SPIDER_MODULES = ["higgs_price.spiders"]
NEWSPIDER_MODULE = "higgs_price.spiders"

# --- politeness -------------------------------------------------------------
ROBOTSTXT_OBEY = True
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
    "higgs_price.middlewares.HttpArchiveMiddleware": 580,   # below HttpCompression (590): sees decoded bodies
}
HIGGS_HTTP_ARCHIVE = True

# --- pipelines --------------------------------------------------------------
ITEM_PIPELINES = {
    "higgs_price.pipelines.RawArchivePipeline": 50,
    "higgs_price.pipelines.ValidationPipeline": 300,
    "higgs_price.pipelines.CollectAndExportPipeline": 800,
}

# --- logging ----------------------------------------------------------------
LOG_FORMATTER = "higgs_price.logformatter.QuietLogFormatter"
LOG_LEVEL = "INFO"
LOGSTATS_INTERVAL = 30.0

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
