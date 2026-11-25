"""SSR page -> compact envelope body (pure; used by the spider before archiving, and by parsers for saved HTML).

Body shape (`format: "tsr"`):
    {"format": "tsr", "path": "/apps/angles", "page_type": "app", "sitemap_lastmod": ..., "head": {...},
     "matches": [{"i": routeId, "l": loaderData}, ...],          # root route and duplicated head/schemas dropped
     "main_html": "<main>...</main>"}                             # landings only: cleaned SSR markup
Base64 `data:` placeholders (blurred previews, ~20 KB each) are removed everywhere.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..blog.parsers import _Head
from ..blog.tsr import TsrParseError, router_matches

_DROP_LOADER_KEYS = ("head", "schemas", "shellCategories")     # duplicated by <head> / JSON-LD / categories
_KEEP_ATTRS = ("href", "src", "alt", "poster", "title")
_TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)(\s[^<>]*?)?(/?)>")
_ATTR = re.compile(r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+)""")


def head_of(html: str) -> dict[str, Any]:
    end = html.find("$_TSR")
    p = _Head()
    try:
        p.feed(html[: end if end > 0 else 400_000])
    except Exception:  # pragma: no cover - malformed markup
        pass
    ld = []
    for s in p.ld:
        try:
            ld.append(json.loads(s))
        except ValueError:
            continue
    m = p.meta
    return {"title": p.title, "lang": p.lang, "canonical": p.canonical, "description": m.get("description"),
            "keywords": m.get("keywords"), "og_title": m.get("og:title"), "og_description": m.get("og:description"),
            "og_image": m.get("og:image"), "og_type": m.get("og:type"), "robots": m.get("robots"), "ld_json": ld}


def strip_placeholders(v: Any) -> Any:
    """Drop base64 data: URIs (inline blurred previews) recursively."""
    if isinstance(v, dict):
        return {k: strip_placeholders(x) for k, x in v.items()
                if not (isinstance(x, str) and x.startswith("data:"))}
    if isinstance(v, list):
        return [strip_placeholders(x) for x in v]
    return v


def _balanced_div(html: str, start: int) -> tuple[str, int]:
    """Inner HTML of the <div> starting at `start` and the index after its closing tag."""
    open_end = html.find(">", start) + 1
    depth, i = 1, open_end
    tok = re.compile(r"<div\b|</div\s*>", re.I)
    while depth:
        m = tok.search(html, i)
        if not m:
            return html[open_end:], len(html)
        depth += -1 if m.group(0).startswith("</") else 1
        i = m.end()
    return html[open_end:m.start()], i


def resolve_suspense(html: str) -> str:
    """React streaming SSR: move `<div hidden id="S:n">` chunks into their `<template id="B:n">` placeholders."""
    chunks: dict[str, str] = {}
    for m in re.finditer(r'<div hidden id="S:(\d+)">', html):
        inner, _ = _balanced_div(html, m.start())
        chunks[m.group(1)] = inner
    if not chunks:
        return html
    return re.sub(r'<template id="B:(\d+)"></template>', lambda m: chunks.get(m.group(1), ""), html)


def _clean_tag(m: re.Match) -> str:
    name, attrs, selfclose = m.group(1), m.group(2) or "", m.group(3)
    kept = [f'{k}={v}' for k, v in _ATTR.findall(attrs) if k.lower() in _KEEP_ATTRS and not v.strip("\"'")
            .startswith("data:")]
    return f"<{name}{(' ' + ' '.join(kept)) if kept else ''}{selfclose}>"


def main_html(html: str) -> Optional[str]:
    """The page's <main> (suspense chunks resolved), without footer, scripts, styles, svg and presentational attrs."""
    body_at = html.find("<body")
    tsr_at = html.find("$_TSR", body_at if body_at > 0 else 0)
    doc = resolve_suspense(html[body_at if body_at > 0 else 0: tsr_at if tsr_at > 0 else len(html)])
    i = doc.find("<main")
    if i < 0:
        return None
    j = doc.rfind("</main>")
    part = doc[i: j + 7] if j > i else doc[i:]
    f = part.find("<footer")
    if f > 0:
        part = part[:f]
    part = re.sub(r"<(script|style|svg|noscript|template|button|form|select|textarea)\b.*?</\1\s*>", "", part,
                  flags=re.S | re.I)
    part = re.sub(r"<!--.*?-->", "", part, flags=re.S)
    part = _TAG.sub(_clean_tag, part)
    return part or None


def extract_page(html: str, path: Optional[str] = None, lastmod: Optional[str] = None,
                 page_type: Optional[str] = None) -> dict[str, Any]:
    body: dict[str, Any] = {"format": "tsr", "path": path, "page_type": page_type, "sitemap_lastmod": lastmod,
                            "head": head_of(html)}
    try:
        matches = router_matches(html)
    except (TsrParseError, IndexError, KeyError, ValueError) as e:
        matches = []
        body["tsr_error"] = f"{type(e).__name__}: {e}"[:300]
    out = []
    for m in matches:
        if not isinstance(m, dict) or m.get("l") is None or str(m.get("i", "")).startswith("__root__"):
            continue
        loader = m["l"]
        if isinstance(loader, dict):
            if page_type == "room":                 # loader = the page's <head> tags only
                continue
            if page_type in ("course", "lesson") and set(loader) == {"courses"}:
                continue                            # the academy layout's course list, repeated on every page
            if page_type == "app" and "categories" in loader and "appPreset" not in loader \
                    and loader.get("kind") != "category":
                continue                            # /apps layout (only on the index itself)
            loader = {k: v for k, v in loader.items() if k not in _DROP_LOADER_KEYS}
        out.append({"i": m.get("i"), "l": strip_placeholders(loader)})
    body["matches"] = out
    if page_type == "landing":
        body["main_html"] = main_html(html)
    return body


def page_body(body: Any) -> dict[str, Any]:
    """Envelope body -> compact body (accepts a saved page {"html": ..., "path": ..., "page_type": ...})."""
    if isinstance(body, dict) and "html" in body and "matches" not in body:
        return extract_page(body["html"], body.get("path"), body.get("sitemap_lastmod"), body.get("page_type"))
    return body if isinstance(body, dict) else {}


def loader(body: dict, key: Optional[str] = None) -> Optional[dict]:
    """Innermost route loader (optionally the last one that contains `key`)."""
    for m in reversed(body.get("matches") or []):
        l_ = m.get("l")
        if isinstance(l_, dict) and (key is None or key in l_):
            return l_
    return None
