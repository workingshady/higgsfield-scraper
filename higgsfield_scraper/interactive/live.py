"""Rich live progress panel for a crawl, fed by Scrapy signals (connected with weak=False) + the stats collector.

It shares the run's Console with the logging RichHandler, so log lines scroll above the panel.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Any


class LiveProgress:
    def __init__(self, console: Any, title: str = "crawl"):
        self.console, self.title = console, title
        self.t0 = time.monotonic()
        self.scheduled = self.responses = self.items = self.dropped = self.errors = 0
        self.status: Counter = Counter()
        self.kinds: Counter = Counter()
        self.crawler = None
        self.live = None

    # -------------------------------------------------------------- signals
    def attach(self, crawler) -> None:
        """RunManager.scrape(on_crawler=...) hook: connect signals, start the panel."""
        from scrapy import signals
        self.crawler = crawler
        c = crawler.signals.connect
        c(self._on_scheduled, signals.request_scheduled, weak=False)
        c(self._on_response, signals.response_received, weak=False)
        c(self._on_item, signals.item_scraped, weak=False)
        c(self._on_dropped, signals.item_dropped, weak=False)
        c(self._on_error, signals.spider_error, weak=False)
        c(self._on_stopped, signals.engine_stopped, weak=False)
        self.start()

    def _on_scheduled(self, **kw) -> None:
        self.scheduled += 1

    def _on_response(self, response=None, **kw) -> None:
        self.responses += 1
        if response is not None:
            self.status[f"{response.status // 100}xx"] += 1

    def _on_item(self, item=None, **kw) -> None:
        self.items += 1
        kind = None
        try:
            kind = item.get("kind") if hasattr(item, "get") else None
        except Exception:
            kind = None
        self.kinds[kind or type(item).__name__.removesuffix("Item").lower()] += 1

    def _on_dropped(self, **kw) -> None:
        self.dropped += 1

    def _on_error(self, **kw) -> None:
        self.errors += 1

    def _on_stopped(self, **kw) -> None:
        self.stop()

    # -------------------------------------------------------------- render
    def _stat(self, key: str) -> int:
        try:
            return int((self.crawler.stats.get_value(key) if self.crawler and self.crawler.stats else 0) or 0)
        except Exception:
            return 0

    def elapsed(self) -> str:
        s = int(time.monotonic() - self.t0)
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

    def __rich__(self):
        from rich.panel import Panel
        from rich.table import Table
        el = max(time.monotonic() - self.t0, 0.001)
        t = Table.grid(padding=(0, 3))
        t.add_column(style="bold")
        t.add_column()
        codes = " · ".join(f"{k} {v}" for k, v in sorted(self.status.items())) or "-"
        t.add_row("requests", f"{self.responses} done / {self.scheduled} scheduled  ({self.responses / el:.1f}/s)  "
                              f"retries {self._stat('retry/count')}")
        t.add_row("http", codes)
        kinds = ", ".join(f"{k} {v}" for k, v in self.kinds.most_common(6))
        t.add_row("items", f"{self.items}" + (f"  ({kinds})" if kinds else ""))
        t.add_row("problems", f"dropped {self.dropped} · errors {max(self.errors, self._stat('log_count/ERROR'))}")
        return Panel(t, title=f"[bold]{self.title}[/]  {self.elapsed()}", subtitle="Ctrl-C = stop (cancelled)",
                     border_style="cyan")

    def start(self) -> None:
        if self.live is not None:
            return
        from rich.live import Live
        self.live = Live(self, console=self.console, refresh_per_second=4, transient=False)
        self.live.start()

    def stop(self) -> None:
        if self.live is not None:
            try:
                self.live.stop()
                if not self.console.is_terminal:     # non-TTY: rich leaves the final frame without a newline
                    self.console.line()
            finally:
                self.live = None
