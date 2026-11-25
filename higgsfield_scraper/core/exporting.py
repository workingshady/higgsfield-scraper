"""Generic export helpers used by every scraper.

* JSON: always indent=4, UTF-8, ensure_ascii=False.
* CSV: COMPLETE — every JSON leaf becomes a column (nested -> dotted columns, lists -> JSON text), UTF-8 with BOM.
* `write_standard_outputs` writes the layout every scraper shares:
      output/dataset.json            the whole validated dataset
      output/json/<part>.json        one file per collection (+ meta.json)
      output/csv/<table>.csv         complete flat tables
      output/schema/dataset.schema.json
      output/summary.md
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Optional

from pydantic import BaseModel

from ..run.logging_setup import emit

log = logging.getLogger(__name__)


def dump_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    return path


def flatten(obj: Any, prefix: str = "", out: Optional[dict] = None) -> dict[str, Any]:
    """{'a': {'b': 1}, 'c': [1, 2]} -> {'a.b': 1, 'c': '[1, 2]'}. Empty dicts become an empty cell."""
    out = {} if out is None else out
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    elif isinstance(obj, dict):
        out[prefix] = None
    elif isinstance(obj, list):
        out[prefix] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix] = obj
    return out


def row(*parts: dict, **keys: Any) -> dict[str, Any]:
    """Merge parent keys + flattened parts into one CSV row."""
    r = dict(keys)
    for p in parts:
        r.update(flatten(p))
    return r


def without(d: dict, *keys: str) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def write_csv(path: Path, rows: Iterable[dict], first: Iterable[str] = ()) -> Path:
    rows = list(rows)
    cols = list(dict.fromkeys([c for c in first if any(c in r for r in rows)] + [k for r in rows for k in r]))
    # a null parent ("discount": null) next to its flattened children ("discount.percent_off") is just a placeholder
    cols = [c for c in cols if not (any(o.startswith(c + ".") for o in cols)
                                    and all(r.get(c) in (None, "") for r in rows))]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig: Excel shows symbols correctly
        w = csv.DictWriter(f, fieldnames=cols or list(first) or ["empty"],          # empty table: keep key headers
                           extrasaction="ignore")  # only empty placeholders dropped
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    return path


def meta_table(meta: dict) -> tuple[list[dict], list[str]]:
    """key/value rows for csv/run_meta.csv."""
    return ([{"key": k, "value": json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v}
             for k, v in flatten(meta).items()], ["key"])


def write_standard_outputs(ds: dict, out_dir: Path, *, json_parts: dict[str, Any],
                           csv_tables: dict[str, tuple[list[dict], list[str]]],
                           dataset_model: Optional[type[BaseModel]] = None, summary_md: str = "") -> list[Path]:
    files = [dump_json(out_dir / "dataset.json", ds),
             dump_json(out_dir / "json" / "meta.json", {"schema_version": ds.get("schema_version"), "meta": ds.get("meta")})]
    for name, data in json_parts.items():
        files.append(dump_json(out_dir / "json" / f"{name}.json", data))
    tables = {"run_meta": meta_table({"schema_version": ds.get("schema_version"), "meta": ds.get("meta")}), **csv_tables}
    for name, (rows, first) in tables.items():
        files.append(write_csv(out_dir / "csv" / f"{name}.csv", rows, first))
    if dataset_model is not None:
        files.append(dump_json(out_dir / "schema" / "dataset.schema.json",
                               dataset_model.model_json_schema(mode="serialization")))
    md = out_dir / "summary.md"
    md.write_text(summary_md or f"# {ds.get('meta', {}).get('scraper', 'dataset')}\n", encoding="utf-8")
    files.append(md)
    emit(log, "info", "output.written", f"wrote {len(files)} output files to {out_dir}", files__count=len(files),
         output__dir=str(out_dir))
    return files
