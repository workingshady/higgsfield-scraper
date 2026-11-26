"""Idempotent output sink: every file goes through tmp + os.replace and is only replaced when its bytes changed.

* `write_text` / `commit_tmp`: write to `<name>.export-tmp`, compare sha256 with the existing file, then either drop
  the tmp (unchanged: mtime untouched) or `os.replace` it in (atomic on POSIX, best effort on Windows).
* `place_file`: copy / hardlink a media file; skipped when the destination already has the same size+mtime (copy)
  or is the same inode (hardlink). Hardlinks fall back to copies across volumes.
* `finish`: removes files that the previous export (export_manifest.json) wrote but this one did not (stale).
* dry-run: nothing touches the disk; only counts are kept.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from collections import OrderedDict
from pathlib import Path
from typing import IO, Optional

from .paths import long_path

TMP_SUFFIX = ".export-tmp"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Sink:
    def __init__(self, root: Path, *, dry_run: bool = False, prev_files: Optional[dict] = None) -> None:
        self.root = root
        self.dry_run = dry_run
        self.prev = prev_files or {}
        self.files: dict[str, dict] = {}
        self.stats = {"written": 0, "unchanged": 0, "removed": 0, "copied": 0, "hardlinked": 0,
                      "hardlink_fallback_copies": 0, "bytes": 0}
        self._handles: "OrderedDict[str, IO[str]]" = OrderedDict()
        self.staging = root / ".export-staging"

    # ------------------------------------------------------------------ helpers
    def abs(self, rel: str) -> Path:
        return self.root / rel

    def _mkparent(self, p: Path) -> None:
        os.makedirs(long_path(p.parent), exist_ok=True)

    def _known_sha(self, rel: str, p: Path) -> Optional[str]:
        """sha256 of an existing destination, reusing the previous manifest entry when size+mtime still match."""
        try:
            st = os.stat(long_path(p))
        except OSError:
            return None
        e = self.prev.get(rel)
        if e and e.get("bytes") == st.st_size and e.get("mtime") == int(st.st_mtime) and e.get("sha256"):
            return e["sha256"]
        return sha256_file(p)

    def _record(self, rel: str, p: Optional[Path], size: int, sha: str) -> None:
        mt = 0
        if p is not None and not self.dry_run:
            try:
                mt = int(os.stat(long_path(p)).st_mtime)
            except OSError:
                mt = 0
        self.files[rel] = {"bytes": size, "sha256": sha, "mtime": mt}
        self.stats["bytes"] += size

    # ------------------------------------------------------------------ writes
    def write_bytes(self, rel: str, data: bytes) -> None:
        sha = hashlib.sha256(data).hexdigest()
        dest = self.abs(rel)
        if self.dry_run:
            self.files[rel] = {"bytes": len(data), "sha256": sha, "mtime": 0}
            self.stats["bytes"] += len(data)
            return
        if os.path.exists(long_path(dest)) and os.path.getsize(long_path(dest)) == len(data) \
                and self._known_sha(rel, dest) == sha:
            self.stats["unchanged"] += 1
        else:
            self._mkparent(dest)
            tmp = Path(str(dest) + TMP_SUFFIX)
            with open(long_path(tmp), "wb") as f:
                f.write(data)
            os.replace(long_path(tmp), long_path(dest))
            self.stats["written"] += 1
        self._record(rel, dest, len(data), sha)

    def write_text(self, rel: str, text: str) -> None:
        self.write_bytes(rel, text.encode("utf-8"))

    def commit_tmp(self, rel: str, tmp: Path) -> None:
        """Move a fully written temp file into place unless the destination already has identical bytes."""
        dest = self.abs(rel)
        size = os.path.getsize(long_path(tmp))
        sha = sha256_file(tmp)
        if os.path.exists(long_path(dest)) and os.path.getsize(long_path(dest)) == size \
                and self._known_sha(rel, dest) == sha:
            os.remove(long_path(tmp))
            self.stats["unchanged"] += 1
        else:
            self._mkparent(dest)
            os.replace(long_path(tmp), long_path(dest))
            self.stats["written"] += 1
        self._record(rel, dest, size, sha)

    def place_file(self, rel: str, src: Path, mode: str) -> None:
        """copy | hardlink `src` to `rel` (never modifies src)."""
        size = os.path.getsize(long_path(src))
        dest = self.abs(rel)
        if self.dry_run:
            self.files[rel] = {"bytes": size, "sha256": None, "mtime": 0}
            self.stats["bytes"] += size
            return
        if os.path.exists(long_path(dest)):
            same = False
            try:
                if mode == "hardlink":
                    same = os.path.samefile(long_path(dest), long_path(src))
                else:
                    sd, ss = os.stat(long_path(dest)), os.stat(long_path(src))
                    same = sd.st_size == ss.st_size and int(sd.st_mtime) == int(ss.st_mtime)
            except OSError:
                same = False
            if same:
                self.stats["unchanged"] += 1
                e = self.prev.get(rel) or {}
                sha = e.get("sha256") if e.get("bytes") == size else None
                self._record(rel, dest, size, sha or sha256_file(dest))
                return
        self._mkparent(dest)
        tmp = Path(str(dest) + TMP_SUFFIX)
        if os.path.exists(long_path(tmp)):
            os.remove(long_path(tmp))
        if mode == "hardlink":
            try:
                os.link(long_path(src), long_path(tmp))
                self.stats["hardlinked"] += 1
            except OSError:                      # other volume / FS without hardlinks -> copy
                shutil.copy2(long_path(src), long_path(tmp))
                self.stats["hardlink_fallback_copies"] += 1
        else:
            shutil.copy2(long_path(src), long_path(tmp))
            self.stats["copied"] += 1
        os.replace(long_path(tmp), long_path(dest))
        self.stats["written"] += 1
        self._record(rel, dest, size, sha256_file(dest))

    # ------------------------------------------------------------------ staging (streamed group files)
    def append(self, key: str, line: str) -> None:
        """Append a line to the staging file `key` (an LRU of open handles keeps the fd count bounded)."""
        if self.dry_run:
            return
        h = self._handles.pop(key, None)
        if h is None:
            p = self.staging / key
            os.makedirs(long_path(p.parent), exist_ok=True)
            h = open(long_path(p), "a", encoding="utf-8", newline="\n")
            if len(self._handles) >= 64:
                _, old = self._handles.popitem(last=False)
                old.close()
        h.write(line)
        self._handles[key] = h

    def staged(self, key: str) -> Path:
        h = self._handles.pop(key, None)
        if h is not None:
            h.close()
        return self.staging / key

    def reset_staging(self) -> None:
        for h in self._handles.values():
            h.close()
        self._handles.clear()
        if not self.dry_run and self.staging.exists():
            shutil.rmtree(long_path(self.staging), ignore_errors=True)

    # ------------------------------------------------------------------ cleanup
    def finish(self, keep_prefixes: tuple[str, ...] = (".media_cache/",)) -> None:
        self.reset_staging()
        if self.dry_run:
            return
        for rel in sorted(set(self.prev) - set(self.files)):
            if rel.startswith(keep_prefixes):
                continue
            p = self.abs(rel)
            if os.path.isfile(long_path(p)):
                os.remove(long_path(p))
                self.stats["removed"] += 1
                d = p.parent
                while d != self.root and d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
                    d = d.parent
