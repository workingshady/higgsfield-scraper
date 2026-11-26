"""Tiny helpers to read *minified* JS without executing it: balanced-bracket scanning that skips strings and
template literals, top-level splitting of object / array literals, and a literal parser that resolves identifiers
to the nearest assignment in the same chunk. Best effort by design: anything it cannot read is returned as `raw`
text, never guessed. Pure functions (unit-tested on fixtures)."""
from __future__ import annotations

import re
from typing import Any, Optional

OPEN = {"{": "}", "[": "]", "(": ")"}
CLOSE = set(OPEN.values())
MAX_SCAN = 200_000                  # never scan further than this from a start bracket
IDENT = r"[A-Za-z_$][\w$]*"


def match_bracket(text: str, start: int, limit: int = MAX_SCAN) -> int:
    """Index of the bracket closing text[start] (one of { [ ( ), or -1. Strings ('', "", ``) and `${}` inside
    template literals are skipped. Regex literals are not understood (rare inside the objects we read)."""
    if start < 0 or start >= len(text) or text[start] not in OPEN:
        return -1
    stack: list[str] = []
    i, n = start, min(len(text), start + limit)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            i = _skip_quoted(text, i, c, n)
            continue
        if c == "`":
            i = _skip_template(text, i, n)
            continue
        if c in OPEN:
            stack.append(OPEN[c])
        elif c in CLOSE:
            if not stack or stack[-1] != c:
                return -1
            stack.pop()
            if not stack:
                return i
        i += 1
    return -1


def _skip_quoted(text: str, i: int, q: str, n: int) -> int:
    i += 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == q or c == "\n":
            return i + 1
        i += 1
    return n


def _skip_template(text: str, i: int, n: int) -> int:
    """i at an opening backtick -> index after the closing one (nested `${ ... }` handled)."""
    i += 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        if c == "$" and i + 1 < n and text[i + 1] == "{":
            end = match_bracket(text, i + 1, n - i)
            if end < 0:
                return n
            i = end + 1
            continue
        i += 1
    return n


def split_top(inner: str) -> list[str]:
    """Split the inside of an object / array / argument list on top-level commas."""
    parts, depth, cur, i, n = [], 0, 0, 0, len(inner)
    while i < n:
        c = inner[i]
        if c in ("'", '"'):
            i = _skip_quoted(inner, i, c, n)
            continue
        if c == "`":
            i = _skip_template(inner, i, n)
            continue
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(inner[cur:i].strip())
            cur = i + 1
        i += 1
    tail = inner[cur:].strip()
    if tail:
        parts.append(tail)
    return parts


_KEY_RE = re.compile(r'^(?:([A-Za-z_$][\w$]*)|"([^"]*)"|\'([^\']*)\'|`([^`$]*)`|(\d+))\s*:(?!:)')


def object_props(obj_text: str) -> dict[str, str]:
    """`{a:1,b:x(),"c-d":[..]}` -> {"a": "1", "b": "x()", "c-d": "[..]"} (spreads and methods are skipped)."""
    t = obj_text.strip()
    if not (t.startswith("{") and t.endswith("}")):
        return {}
    out: dict[str, str] = {}
    for part in split_top(t[1:-1]):
        m = _KEY_RE.match(part)
        if m:
            key = next(g for g in m.groups() if g is not None)
            out[key] = part[m.end():].strip()
    return out


def object_spreads(obj_text: str) -> list[str]:
    """`{...a(b),x:1}` -> ["a(b)"] (spread sources that could not be inlined)."""
    t = obj_text.strip()
    if not (t.startswith("{") and t.endswith("}")):
        return []
    return [p[3:].strip() for p in split_top(t[1:-1]) if p.startswith("...")]


def array_items(arr_text: str) -> list[str]:
    t = arr_text.strip()
    if not (t.startswith("[") and t.endswith("]")):
        return []
    return split_top(t[1:-1])


def find_assignment(text: str, ident: str, near: int) -> Optional[str]:
    """Right-hand side of the assignment `ident=<value>` closest before `near` (else the first one after).
    Minified chunks reuse short names in every module, so proximity picks the right module. Returns the value
    text when it is a bracketed literal / call, a string, a number or a single identifier."""
    rx = re.compile(r"(?<![\w$.])" + re.escape(ident) + r"=(?![=>])")
    best: Optional[int] = None
    for m in rx.finditer(text):
        if m.start() <= near:
            best = m.end()
        elif best is None:
            best = m.end()
            break
        else:
            break
    if best is None:
        return None
    return _value_at(text, best)


_SIMPLE_VALUE = re.compile(r"(?:!0|!1|null|void 0|-?\d+(?:\.\d+)?(?:e\d+)?|-?\.\d+|" + IDENT + r"(?:\.[\w$]+)*)")


def _value_at(text: str, i: int) -> Optional[str]:
    """The JS expression starting at text[i] (bracketed / string / call / simple token)."""
    if i >= len(text):
        return None
    c = text[i]
    if c in OPEN:
        end = match_bracket(text, i)
        return text[i:end + 1] if end > 0 else None
    if c in ("'", '"'):
        return text[i:_skip_quoted(text, i, c, len(text))]
    if c == "`":
        return text[i:_skip_template(text, i, len(text))]
    if text.startswith("new Set(", i):
        end = match_bracket(text, i + 7)
        return text[i:end + 1] if end > 0 else None
    m = _SIMPLE_VALUE.match(text, i)
    if not m:
        return None
    j = m.end()
    if j < len(text) and text[j] == "(":                 # call: f(...)
        end = match_bracket(text, j)
        return text[i:end + 1] if end > 0 else None
    return m.group(0)


class Unreadable(ValueError):
    pass


def parse_literal(expr: str, text: str = "", near: int = 0, depth: int = 0) -> Any:
    """JS literal -> Python value. Identifiers are resolved via `find_assignment` (depth <= 3);
    `Object.values(X)` / `new Set([...])` give lists. Raises Unreadable for anything else."""
    e = (expr or "").strip()
    if not e:
        raise Unreadable(expr)
    if e == "!0" or e == "true":
        return True
    if e == "!1" or e == "false":
        return False
    if e in ("null", "void 0", "undefined"):
        return None
    if re.fullmatch(r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:e-?\d+)?", e):
        v = float(e)
        return int(v) if v.is_integer() and "." not in e and "e-" not in e else v
    if e[0] == "`" and e[-1] == "`" and "${" not in e:
        return e[1:-1]
    if e[0] in ("'", '"') and e[-1] == e[0]:
        return e[1:-1].encode("utf-8").decode("unicode_escape", "ignore") if "\\" in e else e[1:-1]
    if e[0] == "[":
        return [parse_literal(x, text, near, depth) for x in array_items(e)]
    if e[0] == "{":
        out = {}
        for part in split_top(e[1:-1]):
            m = _KEY_RE.match(part)
            if not m:
                raise Unreadable(part)
            key = next(g for g in m.groups() if g is not None)
            out[key] = literal_or_raw(part[m.end():], text, near)      # one unreadable value stays raw
        return out
    m = re.fullmatch(r"new Set\((.*)\)", e, flags=re.S)
    if m:
        return parse_literal(m.group(1), text, near, depth)
    m = re.fullmatch(r"Object\.(values|keys)\((" + IDENT + r")\)", e)
    if m:
        d = parse_literal(m.group(2), text, near, depth)
        if isinstance(d, dict):
            return list(d.values()) if m.group(1) == "values" else list(d.keys())
        raise Unreadable(e)
    if re.fullmatch(IDENT, e) and text and depth < 3:
        rhs = find_assignment(text, e, near)
        if rhs is not None and rhs != e:
            return parse_literal(rhs, text, near, depth + 1)
    raise Unreadable(e)


def literal_or_raw(expr: str, text: str = "", near: int = 0, max_raw: int = 300) -> Any:
    try:
        return parse_literal(expr, text, near)
    except (Unreadable, RecursionError, ValueError):
        return {"raw": (expr or "")[:max_raw]}
