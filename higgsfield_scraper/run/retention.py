"""`runs clean`: retention for run folders (dry-run by default).

A run folder is deleted only when it is in NEITHER keep set:
  * the newest `keep_last` runs (by start time), and
  * runs younger than `keep_days` days.
Never deleted: runs whose status is `running`, the latest successful run (latest.json / LATEST), and folders that
contain a `KEEP` file. Only folders named like a run (`YYYYmmdd-HHMMSS_label`) are considered.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .context import RUN_DIR_RE, latest_success_dir, read_manifest
from .logging_setup import parse_iso


@dataclass
class Candidate:
    path: Path
    status: Optional[str]
    started_at: datetime
    action: str           # "keep" | "delete"
    reason: str
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {"run_id": self.path.name, "status": self.status, "started_at": self.started_at.isoformat(),
                "action": self.action, "reason": self.reason, "size_bytes": self.size_bytes}


def _started(d: Path, m: dict) -> datetime:
    dt = parse_iso(m.get("started_at"))
    if dt:
        return dt
    try:
        return datetime.strptime(d.name[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromtimestamp(d.stat().st_mtime, timezone.utc)


def _size(d: Path) -> int:
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())


def plan_cleanup(runs_dir: str | Path, keep_last: Optional[int] = None, keep_days: Optional[float] = None,
                 now: Optional[datetime] = None) -> list[Candidate]:
    if keep_last is None and keep_days is None:
        raise ValueError("runs clean needs --keep-last N and/or --keep-days D")
    root = Path(runs_dir)
    now = now or datetime.now(timezone.utc)
    latest = latest_success_dir(root)
    latest_name = latest.name if latest else None
    runs = []
    for d in (x for x in root.iterdir() if x.is_dir() and RUN_DIR_RE.match(x.name)) if root.exists() else []:
        m = read_manifest(d)
        runs.append((d, m.get("status"), _started(d, m)))
    runs.sort(key=lambda r: (r[2], r[0].name), reverse=True)
    newest = {r[0].name for r in runs[:keep_last]} if keep_last else set()
    cutoff = now - timedelta(days=keep_days) if keep_days is not None else None
    out: list[Candidate] = []
    for d, status, started in runs:
        if status == "running":
            action, reason = "keep", "status is running"
        elif d.name == latest_name:
            action, reason = "keep", "latest successful run"
        elif (d / "KEEP").exists():
            action, reason = "keep", "KEEP file"
        elif d.name in newest:
            action, reason = "keep", f"within the newest {keep_last}"
        elif cutoff is not None and started >= cutoff:
            action, reason = "keep", f"younger than {keep_days:g} days"
        else:
            action, reason = "delete", "outside the retention window"
        out.append(Candidate(d, status, started, action, reason, _size(d) if action == "delete" else 0))
    return out


def apply_cleanup(cands: list[Candidate]) -> list[Candidate]:
    deleted = []
    for c in cands:
        if c.action == "delete":
            # re-check right before deleting: a run may have started/been pinned meanwhile
            if (c.path / "KEEP").exists() or read_manifest(c.path).get("status") == "running":
                c.action, c.reason = "keep", "changed during cleanup"
                continue
            shutil.rmtree(c.path)
            deleted.append(c)
    return deleted
