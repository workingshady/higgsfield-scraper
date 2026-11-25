"""RunContext: one timestamped, labelled folder per run.

runs/
  20261125-143005_us-full/
    manifest.json            # schema_version 2: status, timings, command, host, git, config, progress, counts,
                             #   close_reason, error, outputs (size + sha256), scrapy stats, file list — atomic writes
    _SUCCESS                 # written last, only when status == success
    logs/
      events.jsonl           # canonical structured log (JSON envelope, DEBUG+)
      run.log                # the same events as human text (UTC)
      errors.log             # WARNING+ with tracebacks
      access.jsonl           # one `http.request.finished` line per HTTP response
    raw/                     # API responses as JSON envelopes (meta + pretty body) — input for `normalize`
    http/                    # wire-level archive: NNN_<endpoint>/{request.json,response.json,body.raw,curl.sh},
                             #   index.jsonl, session.har (import into Chrome DevTools)
    output/
      dataset.json  summary.md  json/  csv/  schema/  items/ (Scrapy JSONL feeds per item type)
  latest.json                # {"run.id", "dir", "finished_at"} of the newest SUCCESSFUL run
  LATEST                     # name of the newest successful run (kept for older tools)
  index.jsonl                # one line per finished run (appended under a file lock)

Statuses: running -> success | partial | failure | cancelled (old manifests may say "failed" == failure).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..core.redact import redact
from .logging_setup import parse_iso, utc_iso

SCHEMA_VERSION = 2
STATUSES = ("running", "success", "partial", "failure", "cancelled")
FINAL_STATUSES = ("success", "partial", "failure", "cancelled")
RUN_DIR_RE = re.compile(r"^\d{8}-\d{6}_")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "run"


def normalize_status(status: Optional[str]) -> Optional[str]:
    """Old manifests: "failed" -> "failure"."""
    return {"failed": "failure", "error": "failure", "interrupted": "cancelled"}.get(status or "", status)


def atomic_write_text(path: Path, text: str) -> None:
    """temp file in the same folder -> fsync -> os.replace (readers never see half a file)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:          # Windows: a reader holds the target open for a moment
            if attempt == 4:
                raise
            import time
            time.sleep(0.05 * (attempt + 1))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


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
        m = read_manifest(run_dir)
        started = parse_iso(m.get("started_at")) or datetime.now(timezone.utc)
        return cls(run_id=run_dir.name, label=m.get("label", "run"), root=run_dir.parent, run_dir=run_dir,
                   started_at=started, meta=m)

    # ----------------------------------------------------------- manifest
    def write_manifest(self, data: dict[str, Any]) -> Path:
        """Merge `data` into the manifest and write it atomically (secrets redacted, updated_at refreshed)."""
        self.meta.update(data)
        self.meta.setdefault("schema_version", SCHEMA_VERSION)
        self.meta.setdefault("run_id", self.run_id)
        self.meta.setdefault("label", self.label)
        self.meta.setdefault("started_at", utc_iso(self.started_at))
        self.meta["updated_at"] = utc_iso()
        doc = redact(json.loads(json.dumps(self.meta, ensure_ascii=False, default=str)))
        atomic_write_text(self.manifest_path, json.dumps(doc, ensure_ascii=False, indent=4))
        return self.manifest_path

    def update_progress(self, progress: dict[str, Any]) -> None:
        self.write_manifest({"progress": progress})

    def outputs(self) -> dict[str, dict[str, Any]]:
        """{relative path: {size_bytes, sha256}} for every file under output/."""
        out: dict[str, dict[str, Any]] = {}
        if self.output_dir.exists():
            for p in sorted(x for x in self.output_dir.rglob("*") if x.is_file()):
                rel = str(p.relative_to(self.run_dir)).replace("\\", "/")
                out[rel] = {"size_bytes": p.stat().st_size, "sha256": sha256_file(p)}
        return out

    def finalize(self) -> None:
        """Publish the run: `_SUCCESS` + runs/latest.json + runs/LATEST only on success; always append index.jsonl."""
        status = normalize_status(self.meta.get("status"))
        if status == "success":
            atomic_write_text(self.run_dir / "_SUCCESS", "")
            atomic_write_text(self.root / "latest.json", json.dumps({
                "run.id": self.run_id, "dir": self.run_dir.name, "finished_at": self.meta.get("finished_at"),
                "status": status}, indent=4))
            atomic_write_text(self.root / "LATEST", self.run_id + "\n")
        line = {k: self.meta.get(k) for k in ("run_id", "label", "scraper", "status", "started_at", "finished_at",
                                              "duration_s", "duration_ms", "exit_code", "counts", "country_code",
                                              "close_reason")}
        append_index(self.root, line)

    def relpaths(self, paths) -> list[dict[str, Any]]:
        return [{"path": str(Path(p).relative_to(self.run_dir)).replace("\\", "/"), "bytes": Path(p).stat().st_size}
                for p in paths if Path(p).exists()]


def append_index(root: Path, line: dict[str, Any]) -> None:
    from filelock import FileLock
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".index.lock"), timeout=30):
        with (root / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(redact(line), default=str) + "\n")


def read_manifest(run_dir: Path) -> dict[str, Any]:
    p = Path(run_dir) / "manifest.json"
    if not p.exists():
        return {}
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if "status" in m:
        m["status"] = normalize_status(m["status"])
    return m


def latest_run(runs_root: str | Path = "runs") -> Optional[Path]:
    """Newest successful run (latest.json, then LATEST), else the newest run folder."""
    root = Path(runs_root)
    lj = root / "latest.json"
    if lj.exists():
        try:
            d = root / json.loads(lj.read_text(encoding="utf-8"))["dir"]
            if d.exists():
                return d
        except (ValueError, KeyError, OSError):
            pass
    p = root / "LATEST"
    if p.exists():
        d = root / p.read_text(encoding="utf-8").strip()
        if d.exists():
            return d
    dirs = sorted((d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")),
                  key=lambda d: d.name) if root.exists() else []
    return dirs[-1] if dirs else None


def latest_success_dir(runs_root: str | Path) -> Optional[Path]:
    root = Path(runs_root)
    for name in ("latest.json", "LATEST"):
        p = root / name
        if p.exists():
            try:
                target = json.loads(p.read_text("utf-8"))["dir"] if name.endswith(".json") else \
                    p.read_text("utf-8").strip()
                return root / target
            except (ValueError, KeyError, OSError):
                continue
    return None
