"""Project brief: Yjs snapshot (Lexical collaboration document) -> Markdown.

Source: `GET https://dam-editor-worker.higgsfield.ai/brief/{folder_id}/snapshot` (binary Yjs v1 update, header
`X-Brief-Updated-At` = epoch ms). The web app (chunk `PublishedProjectBriefSnapshot`) applies it to a Y.Doc and
renders it read-only with Lexical's Yjs binding, where:

* `doc.get("root", XmlText)` is the root; every block is an embedded `XmlText` whose attributes carry the Lexical
  node (`__type` = paragraph | heading | quote | callout | list | listitem | code | table | tablerow | tablecell |
  link, plus `__tag`, `__listType`, `__url`, `__emoji` …);
* a text node is a `Map` embed (`__type` text | code-highlight | linebreak | tab, `__format` bit mask) followed by its
  characters; decorator nodes (horizontalrule, images …) are `XmlElement` embeds.

`brief_markdown(data)` returns (markdown, info) where info has block/word counts, links and referenced UUIDs.
"""
from __future__ import annotations

import re
from typing import Any

from .yjs import YNode, decode_doc

# Lexical TextNode format bits
BOLD, ITALIC, STRIKE, UNDERLINE, CODE = 1, 2, 4, 8, 16
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
BLOCK_TYPES = {"paragraph", "heading", "quote", "callout", "list", "code", "table", "horizontalrule"}


def _wrap(text: str, fmt: int) -> str:
    if not text.strip() or not fmt:
        return text
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text.strip()
    if fmt & CODE:
        core = f"`{core}`"
    if fmt & BOLD:
        core = f"**{core}**"
    if fmt & ITALIC:
        core = f"*{core}*"
    if fmt & STRIKE:
        core = f"~~{core}~~"
    return lead + core + trail


class _Renderer:
    def __init__(self) -> None:
        self.links: list[str] = []
        self.blocks = 0
        self.types: dict[str, int] = {}

    # ---------------------------------------------------------- inline
    def inline(self, node: YNode, *, code: bool = False) -> str:
        out: list[str] = []
        fmt = 0
        pending_text = False
        for ch in node.children():
            if isinstance(ch, str):
                out.append(ch if code else _wrap(ch, fmt if pending_text else 0))
                continue
            if isinstance(ch, YNode):
                a = ch.attrs
                t = a.get("__type")
                self.types[t] = self.types.get(t, 0) + 1
                if ch.type == "map":
                    if t == "linebreak":
                        out.append("\n" if code else "  \n")
                        pending_text = False
                    elif t == "tab":
                        out.append("\t")
                        pending_text = False
                    else:                               # text / code-highlight / unknown text-like node
                        fmt = int(a.get("__format") or 0)
                        pending_text = True
                    continue
                if t in ("link", "autolink"):
                    url = a.get("__url") or ""
                    self.links.append(url)
                    out.append(f"[{self.inline(ch)}]({url})")
                elif ch.type == "xml_element":         # decorator inside a paragraph
                    out.append(self.decorator(ch))
                else:
                    out.append(self.inline(ch, code=code))
                pending_text = False
            # embeds / formats of other shapes are ignored
        return "".join(out)

    def decorator(self, node: YNode) -> str:
        a = node.attrs
        t = a.get("__type") or node.name
        if t == "horizontalrule":
            return "---"
        if t == "image" and a.get("__src"):
            return f"![{a.get('__altText') or ''}]({a['__src']})"
        extra = {k.lstrip("_"): v for k, v in a.items() if k != "__type" and v not in (None, "", 0, False)}
        return f"<!-- {t} {extra} -->" if extra else f"<!-- {t} -->"

    # ---------------------------------------------------------- blocks
    def blocks_of(self, node: YNode, depth: int = 0) -> list[str]:
        out: list[str] = []
        for ch in node.children():
            if isinstance(ch, YNode):
                out.append(self.block(ch, depth))
            elif isinstance(ch, str) and ch.strip():
                out.append(ch)
        return [b for b in out if b is not None]

    def block(self, node: YNode, depth: int = 0) -> str:
        a = node.attrs
        t = a.get("__type") or node.name or node.type
        self.types[t] = self.types.get(t, 0) + 1
        if depth == 0:
            self.blocks += 1
        if node.type == "xml_element":
            return self.decorator(node)
        if t == "heading":
            level = int(str(a.get("__tag") or "h2")[1:] or 2)
            return "#" * max(1, min(level, 6)) + " " + self.inline(node).strip()
        if t == "quote":
            return "\n".join("> " + ln for ln in self.inline(node).split("\n"))
        if t == "callout":
            inner = "\n\n".join(self.blocks_of(node, depth + 1))
            emoji = a.get("__emoji")
            text = (f"{emoji} " if emoji else "") + inner
            return "\n".join("> " + ln if ln else ">" for ln in text.split("\n"))
        if t == "code":
            lang = a.get("__language") or ""
            return f"```{lang}\n{self.inline(node, code=True)}\n```"
        if t == "list":
            return self.list_md(node, 0)
        if t == "table":
            return self.table_md(node)
        if t == "paragraph":
            return self.inline(node)
        # unknown element: render its block children if any, else inline text
        kids = [c for c in node.children() if isinstance(c, YNode) and c.type != "map"]
        if kids and all(c.attrs.get("__type") in BLOCK_TYPES for c in kids):
            return "\n\n".join(self.blocks_of(node, depth + 1))
        return self.inline(node)

    def list_md(self, node: YNode, level: int) -> str:
        a = node.attrs
        kind = a.get("__listType") or ("number" if a.get("__tag") == "ol" else "bullet")
        start = int(a.get("__start") or 1)
        lines: list[str] = []
        n = start
        for item in node.children():
            if not isinstance(item, YNode):
                continue
            nested = [c for c in item.children() if isinstance(c, YNode) and c.attrs.get("__type") == "list"]
            if nested and not "".join(c for c in item.children() if isinstance(c, str)).strip():
                for sub in nested:                       # Lexical nests a list inside an otherwise empty listitem
                    lines.append(self.list_md(sub, level + 1))
                continue
            ia = item.attrs
            if kind == "number":
                marker = f"{n}."
                n += 1
            elif kind == "check":
                marker = "- [x]" if ia.get("__checked") else "- [ ]"
            else:
                marker = "-"
            text = self._item_text(item)
            lines.append("  " * level + f"{marker} {text}")
            for sub in nested:
                lines.append(self.list_md(sub, level + 1))
        return "\n".join(lines)

    def _item_text(self, item: YNode) -> str:
        return self.inline(_ListlessView(item)).replace("\n", " ").strip()

    def table_md(self, node: YNode) -> str:
        rows: list[list[str]] = []
        for r in node.children():
            if not isinstance(r, YNode):
                continue
            cells = []
            for c in r.children():
                if not isinstance(c, YNode):
                    continue
                paras = self.blocks_of(c, 1)
                cells.append("<br>".join(p.replace("\n", "<br>") for p in paras).replace("|", "\\|").strip())
            rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(lines)


class _ListlessView(YNode):
    """A read-only view of an element whose children exclude nested list nodes."""
    __slots__ = ("_src",)

    def __init__(self, src: YNode):
        super().__init__(src.type, src.name)
        self._src = src

    def children(self) -> list[Any]:
        return [c for c in self._src.children()
                if not (isinstance(c, YNode) and c.attrs.get("__type") == "list")]

    @property
    def attrs(self) -> dict[str, Any]:
        return self._src.attrs


def brief_markdown(data: bytes) -> tuple[str, dict[str, Any]]:
    """Yjs snapshot bytes -> (markdown, info)."""
    doc = decode_doc(data)
    root = doc.root("root")
    r = _Renderer()
    md = "\n\n".join(b for b in r.blocks_of(root) if b.strip()) if root is not None else ""
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + ("\n" if md.strip() else "")
    meta = doc.root("meta")
    title = meta.attrs.get("title") if meta is not None else None
    info = {
        "title": title if isinstance(title, str) and title.strip() else None,
        "block_count": r.blocks,
        "node_types": dict(sorted(r.types.items(), key=lambda kv: str(kv[0]))),
        "word_count": len(re.findall(r"\w+", md)),
        "links": list(dict.fromkeys(u for u in r.links if u)),
        "referenced_ids": list(dict.fromkeys(UUID_RE.findall(md))),
    }
    return md, info
