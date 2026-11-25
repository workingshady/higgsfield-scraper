"""HAST (the `mdxTree` of academy lessons) -> HTML, so the shared HTML -> Markdown converter can be reused."""
from __future__ import annotations

import html as htmlmod
from typing import Any

_VOID = {"img", "br", "hr", "source", "input", "meta", "link", "track", "wbr"}
_ATTR_NAMES = {"className": "class", "htmlFor": "for"}


def _attrs(props: Any) -> str:
    if not isinstance(props, dict):
        return ""
    out = []
    for k, v in props.items():
        if v in (None, False) or isinstance(v, (dict,)):
            continue
        name = _ATTR_NAMES.get(k, k)
        if isinstance(v, list):
            v = " ".join(map(str, v))
        out.append(f'{name}="{htmlmod.escape(str(v), quote=True)}"' if v is not True else name)
    return (" " + " ".join(out)) if out else ""


def to_html(node: Any) -> str:
    """Serialize a HAST node. MDX JSX elements become <div data-component="Name"> wrappers (children kept)."""
    if isinstance(node, list):
        return "".join(to_html(n) for n in node)
    if not isinstance(node, dict):
        return ""
    t = node.get("type")
    kids = node.get("children") or []
    if t == "text":
        return htmlmod.escape(str(node.get("value") or ""), quote=False)
    if t == "raw":
        return str(node.get("value") or "")
    if t in ("root", "doctype", "comment"):
        return to_html(kids) if t == "root" else ""
    if t == "element":
        tag = str(node.get("tagName") or "div")
        if tag in _VOID:
            return f"<{tag}{_attrs(node.get('properties'))}/>"
        return f"<{tag}{_attrs(node.get('properties'))}>{to_html(kids)}</{tag}>"
    if t in ("mdxJsxFlowElement", "mdxJsxTextElement"):
        props = {a.get("name"): a.get("value") for a in node.get("attributes") or []
                 if isinstance(a, dict) and isinstance(a.get("value"), (str, int, float))}
        tag = "div" if t == "mdxJsxFlowElement" else "span"
        src = props.get("src") or props.get("url")
        media = ""
        if isinstance(src, str):
            media = f'<video src="{htmlmod.escape(src)}"></video>' if src.endswith((".mp4", ".webm", ".m3u8")) \
                else f'<img src="{htmlmod.escape(src)}" alt="{htmlmod.escape(str(props.get("alt") or ""))}"/>'
        return f"<{tag}>{media}{to_html(kids)}</{tag}>"
    return to_html(kids)
