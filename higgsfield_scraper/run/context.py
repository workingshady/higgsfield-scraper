"""RunContext: one timestamped, labelled folder per run.

runs/
  20261125-143005_us-full/
    manifest.json            # args, selection, status, timings, counts, scrapy stats, file list
    logs/
      run.log                # everything (DEBUG+)
      app.log                # higgsfield_scraper.* only
      scrapy.log             # scrapy.* / twisted / py.warnings
      errors.log             # WARNING+
      events.jsonl           # structured JSON log lines
    raw/                     # API responses as JSON envelopes (meta + pretty body) — input for `normalize`
    http/                    # wire-level archive: NNN_<endpoint>/{request.json,response.json,body.raw,curl.sh},
                             #   index.jsonl, session.har (import into Chrome DevTools)
    output/
      dataset.json  summary.md  json/  csv/  schema/  items/ (Scrapy JSONL feeds per item type)
  LATEST                     # name of the most recent run
  index.jsonl                # one line per finished run
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "run"


@dataclass
class RunContext:
    run_id: str
    label: str
    root: Path
    run_dir: Path
    started_at: datetime
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def raw_dir(self) -> Path:
        return self.run_dir / "raw"

    @property
    def output_dir(self) -> Path:
        return self.run_dir / "output"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @classmethod
    def create(cls, runs_root: str | Path = "runs", label: str = "scrape",
               now: Optional[datetime] = None) -> "RunContext":
        now = now or datetime.now(timezone.utc)
        root = Path(runs_root)
        slug = slugify(label)
        run_id = f"{now.strftime('%Y%m%d-%H%M%S')}_{slug}"
        run_dir = root / run_id
        n = 1
        while run_dir.exists():
            n += 1
            run_dir = root / f"{run_id}-{n}"
        run_id = run_dir.name
        for sub in ("logs", "raw", "output"):
            (run_dir / sub).mkdir(parents=True, exist_ok=True)
        return cls(run_id=run_id, label=slug, root=root, run_dir=run_dir, started_at=now)

    @classmethod
    def open(cls, run_dir: str | Path) -> "RunContext":
        run_dir = Path(run_dir)
        m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")) if (run_dir / "manifest.json").exists() else {}
        started = datetime.fromisoformat(m["started_at"]) if m.get("started_at") else datetime.now(timezone.utc)
        return cls(run_id=run_dir.name, label=m.get("label", "run"), root=run_dir.parent, run_dir=run_dir,
                   started_at=started, meta=m)

    # ----------------------------------------------------------- manifest
    def write_manifest(self, data: dict[str, Any]) -> Path:
        self.meta.update(data)
        self.meta.setdefault("run_id", self.run_id)
        self.meta.setdefault("label", self.label)
        self.meta.setdefault("started_at", self.started_at.isoformat())
        self.manifest_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=4, default=str), encoding="utf-8")
        return self.manifest_path

    def finalize(self) -> None:
        """Update runs/LATEST and append to runs/index.jsonl."""
        (self.root / "LATEST").write_text(self.run_id + "\n", encoding="utf-8")
        line = {k: self.meta.get(k) for k in ("run_id", "label", "status", "started_at", "finished_at",
                                              "duration_s", "counts", "country_code")}
        with (self.root / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")

    def relpaths(self, paths) -> list[dict[str, Any]]:
        return [{"path": str(Path(p).relative_to(self.run_dir)).replace("\\", "/"), "bytes": Path(p).stat().st_size}
                for p in paths if Path(p).exists()]


def latest_run(runs_root: str | Path = "runs") -> Optional[Path]:
    root = Path(runs_root)
    p = root / "LATEST"
    if p.exists():
        d = root / p.read_text(encoding="utf-8").strip()
        if d.exists():
            return d
    dirs = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.name) if root.exists() else []
    return dirs[-1] if dirs else None
