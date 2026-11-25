"""Scrapy extensions: `worker.heartbeat` every HIGGS_HEARTBEAT seconds (CLI --heartbeat, default 30; 0 = off).

Each beat logs one `worker.heartbeat` event (uptime, request/response/error/item counts, rate, queue depth, memory,
percent/ETA when --max-items or --max-requests bounds the run) and writes the same values into the run manifest as
`progress` (+ `updated_at`), so a stuck or killed run can be told apart from a slow one.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional

from scrapy import signals
from scrapy.exceptions import NotConfigured

from .run.logging_setup import emit, utc_iso

log = logging.getLogger("higgsfield_scraper.heartbeat")


def memory_usage_mb() -> Optional[float]:
    """Resident memory of this process in MB: psutil if installed, else an OS fallback, else tracemalloc."""
    try:
        import psutil  # type: ignore[import-not-found]
        return round(psutil.Process().memory_info().rss / 1048576, 1)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return round(pmc.WorkingSetSize / 1048576, 1)
        except Exception:
            pass
    else:
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss      # KB on Linux, bytes on macOS (peak)
            return round(rss / (1048576 if sys.platform == "darwin" else 1024), 1)
        except Exception:
            pass
    try:
        import tracemalloc
        if tracemalloc.is_tracing():
            return round(tracemalloc.get_traced_memory()[0] / 1048576, 1)
    except Exception:
        pass
    return None


def _sum_prefix(stats: dict, prefix: str) -> int:
    return sum(v for k, v in stats.items() if k.startswith(prefix) and isinstance(v, (int, float)))


class HeartbeatExtension:
    def __init__(self, crawler, interval: float):
        self.crawler = crawler
        self.interval = interval
        self.task = None
        self.t0 = time.monotonic()
        self.last_t = self.t0
        self.last_responses = 0
        self.beats = 0
        self.clock = None

    @classmethod
    def from_crawler(cls, crawler):
        interval = crawler.settings.getfloat("HIGGS_HEARTBEAT", 30.0)
        if not interval or interval <= 0:
            raise NotConfigured
        ext = cls(crawler, interval)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_opened(self, spider=None):
        from twisted.internet import task
        self.t0 = self.last_t = time.monotonic()
        self.task = task.LoopingCall(self.beat)
        if self.clock is not None:                 # tests: twisted.internet.task.Clock
            self.task.clock = self.clock
        self.task.start(self.interval, now=False)

    def spider_closed(self, spider=None, reason=None):
        if self.task is not None and self.task.running:
            self.task.stop()

    # ------------------------------------------------------------ values
    def _queue_depth(self) -> Optional[int]:
        engine = getattr(self.crawler, "engine", None)
        try:
            sched = getattr(engine, "scheduler", None)
            if sched is None:
                slot = getattr(engine, "_slot", None) or getattr(engine, "slot", None)
                sched = getattr(slot, "scheduler", None)
            if sched is not None:
                return len(sched)
        except Exception:
            pass
        return None

    def snapshot(self) -> dict[str, Any]:
        stats = self.crawler.stats.get_stats() if self.crawler.stats else {}
        now = time.monotonic()
        uptime = now - self.t0
        requests = int(stats.get("downloader/request_count", 0) or 0)
        responses = int(stats.get("downloader/response_count", 0) or 0)
        errors = int(stats.get("log_count/ERROR", 0) or 0) + int(stats.get("log_count/CRITICAL", 0) or 0)
        items = int(stats.get("item_scraped_count", 0) or 0)
        window = max(now - self.last_t, 1e-6)
        rate = (responses - self.last_responses) / window * 60.0
        self.last_t, self.last_responses = now, responses
        snap: dict[str, Any] = {
            "uptime_s": round(uptime, 1), "requests.count": requests, "responses.count": responses,
            "errors.count": errors, "items.count": items, "rate_per_min": round(rate, 1),
            "queue.depth": self._queue_depth(), "memory.usage_mb": memory_usage_mb(),
            "dropped.count": int(_sum_prefix(stats, "validation/dropped/")) or int(stats.get("validation/dropped", 0)),
        }
        spider = getattr(self.crawler, "spider", None)
        common = getattr(spider, "common", None)
        max_items = getattr(common, "max_items", None)
        max_requests = self.crawler.settings.getint("CLOSESPIDER_PAGECOUNT", 0)
        pct, basis = None, None
        if max_items:
            done = getattr(spider, "primary_count", None)
            done = items if done is None else done
            pct, basis = min(100.0, 100.0 * done / max_items), "max_items"
        elif max_requests:
            pct, basis = min(100.0, 100.0 * responses / max_requests), "max_requests"
        if pct is not None:
            snap["percent"] = round(pct, 1)
            snap["progress.basis"] = basis
            snap["eta_s"] = round(uptime * (100 - pct) / pct, 0) if pct > 0 else None
        return snap

    def beat(self) -> dict[str, Any]:
        self.beats += 1
        snap = self.snapshot()
        pct = f", {snap['percent']}%" if snap.get("percent") is not None else ""
        emit(log, "info", "worker.heartbeat",
             f"alive {snap['uptime_s']:.0f}s: {snap['responses.count']} responses, {snap['items.count']} items, "
             f"{snap['errors.count']} errors{pct}",
             **{k.replace(".", "__"): v for k, v in snap.items()})
        ctx = getattr(getattr(self.crawler, "spider", None), "run_ctx", None)
        if ctx is not None:
            try:
                ctx.update_progress({**snap, "heartbeat_at": utc_iso(), "beats": self.beats, "pid": os.getpid()})
            except Exception:
                log.debug("manifest progress update failed", exc_info=True)
        return snap
