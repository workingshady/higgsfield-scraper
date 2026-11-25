"""Remembered menu choices: %APPDATA%/higgsfield_scraper/prefs.json (XDG config dir elsewhere; env HF_PREFS wins).

Only non-secret choices are stored: last scrapers, and per scraper the last label and option answers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

VERSION = 1


def prefs_path() -> Path:
    if os.environ.get("HF_PREFS"):
        return Path(os.environ["HF_PREFS"])
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "higgsfield_scraper" / "prefs.json"


def default_prefs() -> dict[str, Any]:
    return {"version": VERSION, "remember": True, "last_scrapers": [], "scrapers": {}}


def load_prefs() -> dict[str, Any]:
    try:
        data = json.loads(prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_prefs()
    if not isinstance(data, dict):
        return default_prefs()
    out = default_prefs()
    out.update({k: v for k, v in data.items() if k in out})
    if not isinstance(out["scrapers"], dict):
        out["scrapers"] = {}
    return out


def save_prefs(prefs: dict[str, Any]) -> Path:
    path = prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(prefs, indent=4, default=str), encoding="utf-8")
    tmp.replace(path)                               # atomic on Windows and POSIX
    return path


def remember_scrape(prefs: dict[str, Any], scraper: str, answers: dict[str, Any], label: str | None) -> None:
    if not prefs.get("remember", True):
        return
    prefs.setdefault("scrapers", {})[scraper] = {"answers": dict(answers), "label": label}


def reset_prefs() -> dict[str, Any]:
    try:
        prefs_path().unlink()
    except OSError:
        pass
    return default_prefs()
