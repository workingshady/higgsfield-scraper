"""Opt-in export of finished run folders into browsable / dataset-ready folder trees.

    python -m higgsfield_scraper export --run runs/<id> [--layout tree|hf|webdataset|jsonl] [...]

Read-only on the runs; network only with --download-missing-media. See docs/EXPORT.md.
Modules: stream (streaming JSON), reader (run folders), records (generic row normalisation), keys (ids + dedup
keys, reusing scripts/merge_generations.py), profiles (per-scraper grouping), paths (safe names), media, sink
(idempotent atomic writes), engine (layouts), card (README data card).
"""
from .engine import EXPORT_VERSION, LAYOUTS, MEDIA_MODES, ExportOptions, ExportResult, parse_filters, run_export
from .reader import expand_runs

__all__ = ["EXPORT_VERSION", "LAYOUTS", "MEDIA_MODES", "ExportOptions", "ExportResult", "expand_runs",
           "parse_filters", "run_export"]
