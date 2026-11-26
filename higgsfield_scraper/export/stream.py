"""Streaming JSON readers (stdlib only, constant memory per record).

`output/json/assets.json` can be 54 MB+; `json.load` would hold the whole parsed tree (~10x the file size) in RAM.
These readers decode one array element at a time with `json.JSONDecoder.raw_decode` over a sliding text buffer,
so peak memory is "largest single record + one chunk", not "whole file".

    iter_json_array(path)      top-level `[ {...}, {...} ]`            -> yields each element
    iter_dataset(path)         top-level `{"k": [..], "meta": {..}}`  -> yields (key, element) for list values,
                                                                          (key, value) once for non-list values
    peek_json_kind(path)       "list" | "dict" | "other" from the first non-space character
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Optional, TextIO

CHUNK = 1 << 16          # 64 KiB of text per read
_WS = " \t\r\n"
_decoder = json.JSONDecoder()


class _Buf:
    """A forward-only text buffer over a file: refills on demand and drops consumed text."""

    def __init__(self, f: TextIO) -> None:
        self.f = f
        self.s = ""
        self.i = 0
        self.eof = False

    def fill(self) -> bool:
        if self.eof:
            return False
        chunk = self.f.read(CHUNK)
        if not chunk:
            self.eof = True
            return False
        if self.i:
            self.s = self.s[self.i:]
            self.i = 0
        self.s += chunk
        return True

    def skip_ws(self) -> Optional[str]:
        """Skip whitespace; return the next character without consuming it (None at EOF)."""
        while True:
            while self.i < len(self.s) and self.s[self.i] in _WS:
                self.i += 1
            if self.i < len(self.s):
                return self.s[self.i]
            if not self.fill():
                return None

    def expect(self, ch: str) -> None:
        c = self.skip_ws()
        if c != ch:
            raise ValueError(f"expected {ch!r}, got {c!r}")
        self.i += 1

    def value(self) -> Any:
        """Decode one JSON value at the cursor, reading more text until it parses (or EOF)."""
        self.skip_ws()
        while True:
            try:
                obj, end = _decoder.raw_decode(self.s, self.i)
            except json.JSONDecodeError:
                if self.fill():
                    continue
                raise
            # a number at the very end of the buffer may be truncated ("12" of "123"): make sure it is complete
            if end == len(self.s) and not self.eof and not isinstance(obj, (dict, list, str)):
                if self.fill():
                    continue
            self.i = end
            return obj


def _open(path: Path) -> TextIO:
    return open(path, "r", encoding="utf-8-sig")      # tolerate a BOM


def peek_json_kind(path: Path) -> str:
    with _open(path) as f:
        c = _Buf(f).skip_ws()
    return {"[": "list", "{": "dict"}.get(c or "", "other")


def _iter_array(b: _Buf) -> Iterator[Any]:
    b.expect("[")
    if b.skip_ws() == "]":
        b.i += 1
        return
    while True:
        yield b.value()
        c = b.skip_ws()
        b.i += 1
        if c == "]":
            return
        if c != ",":
            raise ValueError(f"expected ',' or ']' in array, got {c!r}")


def iter_json_array(path: Path) -> Iterator[Any]:
    """Yield the elements of a top-level JSON array one by one. A non-array file yields nothing."""
    with _open(path) as f:
        b = _Buf(f)
        if b.skip_ws() != "[":
            return
        yield from _iter_array(b)


def iter_dataset(path: Path, only: Optional[set[str]] = None) -> Iterator[tuple[str, Any]]:
    """Stream a dict-of-collections file (`output/dataset.json`): yields (key, element) for every element of a list
    value, and (key, value) once for any other value. `only` restricts list keys (others are skipped cheaply-ish:
    they are still decoded element by element, never as a whole)."""
    with _open(path) as f:
        b = _Buf(f)
        b.expect("{")
        if b.skip_ws() == "}":
            return
        while True:
            key = b.value()
            b.expect(":")
            if b.skip_ws() == "[":
                for el in _iter_array(b):
                    if only is None or key in only:
                        yield key, el
            else:
                v = b.value()
                if only is None or key in only:
                    yield key, v
            c = b.skip_ws()
            b.i += 1
            if c == "}":
                return
            if c != ",":
                raise ValueError(f"expected ',' or '}}' in object, got {c!r}")


def iter_jsonl(path: Path) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
