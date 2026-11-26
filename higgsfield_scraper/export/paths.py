"""Cross-platform safe file/folder names for exports (Windows, macOS, Linux).

Rules applied (sources in docs/EXPORT.md):
* Unicode NFC normalisation (macOS tools may hand out NFD; git/HF expect NFC) and control characters removed.
* Windows-illegal characters  < > : " / \\ | ? *  -> "_" ; trailing dots/spaces stripped (Windows drops them).
* Windows reserved device names (CON, PRN, AUX, NUL, COM0-9, LPT0-9, incl. superscript digits ¹²³, CONIN$, CONOUT$)
  are reserved even with an extension ("NUL.txt") -> suffixed with "_".
* Length: each component <= 255 UTF-8 bytes (ext4/APFS/NTFS limit) and <= `max_chars`; long names are cut and get a
  short hash so different long names stay different.
* Case collisions (NTFS/APFS are case-insensitive by default): `NameRegistry` hands out "name~2" for a second
  name that differs only by case/normalisation inside the same folder.
* The 260-character Windows MAX_PATH: `fit_parts` shortens the longest components first; `long_path` adds the
  \\\\?\\ prefix on Windows as a last resort for the actual file operation.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$",
            *(f"COM{d}" for d in "0123456789¹²³"), *(f"LPT{d}" for d in "0123456789¹²³")}
MAX_COMPONENT_BYTES = 255
WIN_PATH_LIMIT = 250            # stay under MAX_PATH (260) with room for ".tmp" suffixes


def short_hash(s: str, n: int = 8) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _cut_bytes(s: str, limit: int) -> str:
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    return b[:limit].decode("utf-8", "ignore")


def safe_component(name: Optional[str], *, max_chars: int = 80, fallback: str = "_") -> str:
    """One path component (folder or file stem, WITHOUT extension handling) that is valid everywhere."""
    s = unicodedata.normalize("NFC", str(name if name is not None else ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co"))
    s = ILLEGAL.sub("_", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(". ").lstrip(" ")
    if s in ("", ".", ".."):
        s = fallback
    if len(s) > max_chars or len(s.encode("utf-8")) > MAX_COMPONENT_BYTES - 16:
        h = short_hash(s, 6)
        s = _cut_bytes(s[: max_chars - 7], MAX_COMPONENT_BYTES - 24).rstrip(". ") + "~" + h
    if s.split(".")[0].upper().rstrip(" ") in RESERVED:
        s = s + "_" if "." not in s else s.replace(".", "_.", 1)
    return s


def slug(text: Optional[str], max_chars: int = 40, fallback: str = "x") -> str:
    """ASCII-ish lowercase slug for file stems: 'Seedance 2.5 / Pro' -> 'seedance-2-5-pro'."""
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()[:max_chars].strip("-")
    s = s or fallback
    return s + "_" if s.upper() in RESERVED else s


def safe_ext(ext: Optional[str]) -> str:
    e = re.sub(r"[^A-Za-z0-9]", "", (ext or "").lstrip("."))[:8].lower()
    return f".{e}" if e else ""


class NameRegistry:
    """Hands out unique, case-insensitively distinct names per folder, deterministically for the same input order."""

    def __init__(self) -> None:
        self._taken: dict[tuple[str, str], str] = {}     # (parent_key, folded name) -> owner key

    @staticmethod
    def _fold(s: str) -> str:
        return unicodedata.normalize("NFC", s).casefold()

    def claim(self, parent: str, name: str, owner: str) -> str:
        """Return `name` (or name~2, name~3 …) for `owner` inside `parent`; the same owner always gets the same name."""
        pk = self._fold(parent)
        stem, dot, ext = name.rpartition(".") if "." in name[1:] else (name, "", "")
        stem = stem if dot else name
        ext = f".{ext}" if dot else ""
        n = 1
        while True:
            cand = name if n == 1 else f"{stem}~{n}{ext}"
            k = (pk, self._fold(cand))
            cur = self._taken.get(k)
            if cur is None:
                self._taken[k] = owner
                return cand
            if cur == owner:
                return cand
            n += 1


def fit_parts(base: Path, parts: list[str], filename: str = "", limit: int = WIN_PATH_LIMIT) -> list[str]:
    """Shorten folder components (longest first) until len(base/parts/filename) <= limit. Keeps a hash suffix."""
    parts = list(parts)
    base_len = len(str(base.resolve() if not base.is_absolute() else base))

    def total() -> int:
        return base_len + sum(len(p) + 1 for p in parts) + (len(filename) + 1 if filename else 0)

    guard = 0
    while total() > limit and parts and guard < 200:
        guard += 1
        i = max(range(len(parts)), key=lambda j: len(parts[j]))
        p = parts[i]
        if len(p) <= 12:
            break
        keep = max(4, len(p) - (total() - limit) - 7)
        parts[i] = p[:keep].rstrip(". ") + "~" + short_hash(p, 6)
    return parts


def long_path(p: Path) -> str:
    """Path string usable for file operations even when longer than MAX_PATH on Windows (\\\\?\\ prefix)."""
    s = str(p)
    if os.name == "nt":
        s = os.path.abspath(s)
        if len(s) >= 248 and not s.startswith("\\\\?\\"):
            return "\\\\?\\UNC\\" + s[2:] if s.startswith("\\\\") else "\\\\?\\" + s
    return s
