"""Minimal parser for TanStack Router SSR state (seroval-serialized JS literals)."""
from __future__ import annotations

import json
import re
from typing import Any

_UNDEF = object()


class TsrParseError(ValueError):
    pass


class _P:
    def __init__(self, s: str, i: int = 0):
        self.s, self.i, self.refs = s, i, {}
        self.stop_keys, self.stopped = ("dehydratedData",), False

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def peek(self, n=1):
        return self.s[self.i:self.i + n]

    def expect(self, t):
        if not self.s.startswith(t, self.i):
            raise TsrParseError(f"expected {t!r} at {self.i}: {self.s[self.i:self.i+60]!r}")
        self.i += len(t)

    def value(self) -> Any:
        self.ws()
        s, i = self.s, self.i
        c = s[i]
        if s.startswith("$R[", i):
            m = re.compile(r"\$R\[(\d+)\]").match(s, i)
            self.i = m.end()
            n = int(m.group(1))
            if self.peek() == "=":
                self.i += 1
                v = self.value()
                self.refs[n] = v
                return v
            return self.refs.get(n)
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c == '"':
            return self.string()
        if s.startswith("!0", i):
            self.i += 2
            return True
        if s.startswith("!1", i):
            self.i += 2
            return False
        if s.startswith("void 0", i):
            self.i += 6
            return None
        for lit, v in (("null", None), ("undefined", None), ("NaN", None), ("Infinity", None), ("-Infinity", None)):
            if s.startswith(lit, i):
                self.i += len(lit)
                return v
        if s.startswith("new Date(", i):
            self.i += 9
            v = self.value()
            self.expect(")")
            return v
        if s.startswith("new Set(", i) or s.startswith("new Map(", i):
            is_map = s.startswith("new Map(", i)
            self.i += 8
            v = self.value() if self.peek() != ")" else []
            self.expect(")")
            return {str(k): val for k, val in v} if is_map else v
        m = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?n?").match(s, i)
        if m:
            self.i = m.end()
            t = m.group(0).rstrip("n")
            return float(t) if any(ch in t for ch in ".eE") else int(t)
        raise TsrParseError(f"unsupported token at {i}: {s[i:i+80]!r}")

    def string(self) -> str:
        s = self.s
        j = self.i + 1
        out = []
        while True:
            k = j
            while s[k] not in '"\\':
                k += 1
            out.append(s[j:k])
            if s[k] == '"':
                self.i = k + 1
                return "".join(out)
            e = s[k + 1]
            if e == "x":
                out.append(chr(int(s[k + 2:k + 4], 16)))
                j = k + 4
            elif e == "u":
                if s[k + 2] == "{":
                    end = s.index("}", k)
                    out.append(chr(int(s[k + 3:end], 16)))
                    j = end + 1
                else:
                    out.append(chr(int(s[k + 2:k + 6], 16)))
                    j = k + 6
            else:
                out.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}.get(e, e))
                j = k + 2

    def key(self) -> str:
        self.ws()
        if self.peek() == '"':
            return self.string()
        m = re.compile(r"[A-Za-z_$][\w$]*|\d+").match(self.s, self.i)
        if not m:
            raise TsrParseError(f"bad key at {self.i}: {self.s[self.i:self.i+60]!r}")
        self.i = m.end()
        return m.group(0)

    def obj(self) -> dict:
        self.expect("{")
        d: dict = {}
        self.ws()
        if self.peek() == "}":
            self.i += 1
            return d
        while True:
            k = self.key()
            if k in self.stop_keys:
                self.stopped = True
                return d
            self.ws()
            self.expect(":")
            d[k] = self.value()
            if self.stopped:
                return d
            self.ws()
            if self.peek() == ",":
                self.i += 1
                continue
            self.expect("}")
            # surrogate-paired strings etc. are already handled; fix utf-16 escapes below
            return d

    def arr(self) -> list:
        self.expect("[")
        a: list = []
        self.ws()
        if self.peek() == "]":
            self.i += 1
            return a
        while True:
            self.ws()
            if self.peek() == ",":          # hole
                a.append(None)
                self.i += 1
                continue
            a.append(self.value())
            if self.stopped:
                return a
            self.ws()
            if self.peek() == ",":
                self.i += 1
                self.ws()
                if self.peek() == "]":
                    self.i += 1
                    return a
                continue
            self.expect("]")
            return a


def _fix_surrogates(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return v.encode("utf-16", "surrogatepass").decode("utf-16")
        except UnicodeError:
            return v
    if isinstance(v, list):
        return [_fix_surrogates(x) for x in v]
    if isinstance(v, dict):
        return {k: _fix_surrogates(x) for k, x in v.items()}
    return v


def router_matches(html: str) -> list[dict]:
    """Return the TanStack router `matches` list (each {i: routeId, l: loaderData, ...}) from SSR HTML."""
    start = html.find("$_TSR.router=")
    if start < 0:
        return []
    m = html.find("$R[0]=", start)
    if m < 0:
        return []
    p = _P(html, m)
    root = p.value()
    return _fix_surrogates((root or {}).get("matches") or [])


if __name__ == "__main__":
    import sys
    h = open(sys.argv[1], encoding="utf-8").read()
    print(json.dumps(router_matches(h), ensure_ascii=False, indent=1)[: int(sys.argv[2]) if len(sys.argv) > 2 else 5000])
