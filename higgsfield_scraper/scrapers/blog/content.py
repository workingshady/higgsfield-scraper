"""Article body conversion (pure): CMS HTML and Lexical trees -> Markdown, plain text, headings, links, images."""
from __future__ import annotations

import html as htmlmod
import json
import re
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import unquote, urljoin

from .endpoints import SITE

_BLOCK = {"p", "div", "section", "article", "header", "footer", "figure", "figcaption", "blockquote", "pre", "table",
          "thead", "tbody", "tr", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "caption", "hr", "br"}


def _norm_ws(s: str) -> str:
    return re.sub(r"[ \t\r\f\v\u00a0]+", " ", s)


def _abs(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if url.startswith(("#", "mailto:", "tel:", "javascript:")):
        return url
    return urljoin(SITE + "/", url)


class Body:
    """Accumulates the outputs of one conversion."""

    def __init__(self) -> None:
        self.headings: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.images: list[dict[str, Any]] = []

    def result(self, markdown: str, fmt: str) -> dict[str, Any]:
        md = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        text = markdown_to_text(md)
        return {"content_format": fmt, "content_markdown": md or None, "content_text": text or None,
                "word_count": len(re.findall(r"\w+", text)) if text else 0,
                "headings": self.headings, "links": self.links, "images": self.images}


# ------------------------------------------------------------------ HTML -> Markdown

class _H2M(HTMLParser):
    def __init__(self, body: Body):
        super().__init__(convert_charrefs=True)
        self.b = body
        self.out: list[str] = []
        self.lists: list[list] = []          # stack of [type, counter]
        self.href: list[Optional[str]] = []
        self.link_text: list[list[str]] = []
        self.heading: Optional[tuple[int, Optional[str], list[str]]] = None
        self.table: Optional[list[list[str]]] = None
        self.row: Optional[list[str]] = None
        self.cell: Optional[list[str]] = None
        self.table_has_head = False
        self.pre = 0
        self.code = 0
        self.skip = 0

    # sink: the innermost open collector
    def emit(self, s: str) -> None:
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)
        if self.heading is not None:
            self.heading[2].append(s)
        for lt in self.link_text:
            lt.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lvl = int(tag[1])
            self.emit("\n\n" + "#" * lvl + " ")
            self.heading = (lvl, a.get("id"), [])
        elif tag == "p":
            self.emit("\n\n" if not self.lists else "")
        elif tag == "br":
            self.emit("  \n")
        elif tag == "hr":
            self.emit("\n\n---\n\n")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, int(a.get("start") or 1)])
            self.emit("\n")
        elif tag == "li":
            depth = max(0, len(self.lists) - 1)
            if self.lists and self.lists[-1][0] == "ol":
                marker = f"{self.lists[-1][1]}. "
                self.lists[-1][1] += 1
            else:
                marker = "- "
            self.emit("\n" + "  " * depth + marker)
        elif tag in ("strong", "b"):
            self.emit("**")
        elif tag in ("em", "i"):
            self.emit("*")
        elif tag in ("s", "del", "strike"):
            self.emit("~~")
        elif tag == "code" and not self.pre:
            self.code += 1
            self.emit("`")
        elif tag == "pre":
            self.pre += 1
            self.emit("\n\n```\n")
        elif tag == "blockquote":
            self.emit("\n\n> ")
        elif tag == "a":
            href = _abs(a.get("href"))
            self.emit("[")
            self.href.append(href)
            self.link_text.append([])
        elif tag in ("img", "source", "video", "iframe"):
            src = a.get("src") or a.get("data-src")
            if src:
                src = _abs(src)
                kind = {"img": "image", "iframe": "embed"}.get(tag, "video")
                alt = a.get("alt") or a.get("title") or ""
                self.b.images.append({"url": src, "alt": alt or None, "kind": kind, "ref_id": None})
                self.emit(f"![{alt}]({src})" if kind == "image" else f"\n\n[{kind}: {src}]({src})\n\n")
        elif tag == "table":
            self.table, self.table_has_head = [], False
        elif tag == "thead":
            self.table_has_head = True
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "caption" and self.table is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.heading is not None:
            lvl, hid, parts = self.heading
            title = markdown_to_text(_norm_ws("".join(parts)))
            if title:
                self.b.headings.append({"level": lvl, "text": title, "anchor": hid})
            self.heading = None
            self.emit("\n\n")
        elif tag == "p":
            self.emit("\n\n" if not self.lists else "")
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self.emit("\n\n" if not self.lists else "")
        elif tag in ("strong", "b"):
            self.emit("**")
        elif tag in ("em", "i"):
            self.emit("*")
        elif tag in ("s", "del", "strike"):
            self.emit("~~")
        elif tag == "code" and not self.pre:
            self.code = max(0, self.code - 1)
            self.emit("`")
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.emit("\n```\n\n")
        elif tag == "blockquote":
            self.emit("\n\n")
        elif tag == "a" and self.href:
            href = self.href.pop()
            text = markdown_to_text(_norm_ws("".join(self.link_text.pop())))
            self.emit(f"]({href})" if href else "]")
            if href:
                self.b.links.append({"url": href, "text": text or None,
                                     "internal": href.startswith(SITE) or href.startswith("#")})
        elif tag in ("td", "th") and self.row is not None and self.cell is not None:
            self.row.append(_norm_ws("".join(self.cell)).replace("|", "\\|").replace("\n", " ").strip())
            self.cell = None
        elif tag == "caption" and self.table is not None and self.cell is not None:
            cap = _norm_ws("".join(self.cell)).strip()
            self.cell = None
            if cap:
                self.out.append(f"\n\n*{cap}*\n")
        elif tag == "tr" and self.table is not None and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            rows, self.table = self.table, None
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [""] * (width - len(r)) for r in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                self.out.append("\n\n" + "\n".join(lines) + "\n\n")

    def handle_comment(self, data):
        """CMS blocks are serialized as comments: <!--post-asset-block:{urlencoded JSON}--> etc."""
        name, _, payload = data.strip().partition(":")
        if not name.startswith("post-") or not payload:
            return
        try:
            j = json.loads(unquote(payload))
        except ValueError:
            return
        if not isinstance(j, dict):
            return
        out = []
        prompt = j.get("prompt")
        if name in ("post-code-block", "post-code-group"):
            tabs = j.get("tabs") if isinstance(j.get("tabs"), list) else [j]
            for t in tabs:
                if isinstance(t, dict) and t.get("text"):
                    label = t.get("label") or t.get("title") or ""
                    head = f"**{label}**\n" if label and len(tabs) > 1 else ""
                    out.append(f"\n\n{head}```{t.get('language') or ''}\n{t['text'].rstrip()}\n```\n\n")
        if prompt:
            out.append(f"\n\n**Prompt:**\n\n```\n{str(prompt).rstrip()}\n```\n\n")
            if j.get("recreateLink"):
                out.append(f"[Recreate]({_abs(j['recreateLink'])})\n\n")
        url = j.get("url")
        if url:
            ctype = str(j.get("contentType") or "")
            kind = "video" if ctype.startswith("video") or re.search(r"\.(mp4|webm|mov)$", url, re.I) else "image"
            alt = j.get("description") or j.get("filename") or ""
            u = _abs(url)
            self.b.images.append({"url": u, "alt": alt or None, "kind": kind, "ref_id": None,
                                  "poster_url": _abs(j.get("posterUrl")) if j.get("posterUrl") else None})
            out.insert(0, f"\n\n![{alt}]({u})\n\n" if kind == "image" else f"\n\n[video: {alt or u}]({u})\n\n")
        for x in out:
            self.emit(x)

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre:
            self.emit(data)
        else:
            self.emit(_norm_ws(data.replace("\n", " ")))


def html_to_markdown(html: Optional[str], body: Optional[Body] = None) -> tuple[str, Body]:
    body = body or Body()
    if not html:
        return "", body
    p = _H2M(body)
    p.feed(html)
    p.close()
    md = "".join(p.out)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\*\*\s*\*\*", "", md)
    return md, body


def convert_html(html: Optional[str]) -> dict[str, Any]:
    md, body = html_to_markdown(html)
    return body.result(md, "html")


def convert_markdown(md: Optional[str], html: Optional[str] = None) -> dict[str, Any]:
    """Source already provides Markdown (help centers); still derive headings/links/images from it (or the HTML)."""
    body = Body()
    if html:
        html_to_markdown(html, body)
    else:
        for m in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", md or "", re.M):
            body.headings.append({"level": len(m.group(1)), "text": m.group(2).strip(), "anchor": None})
    if not html:
        for m in re.finditer(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)", md or ""):
            if m.group(1):
                body.images.append({"url": _abs(m.group(3)), "alt": m.group(2) or None, "kind": "image",
                                    "ref_id": None})
            else:
                u = _abs(m.group(3))
                body.links.append({"url": u, "text": m.group(2) or None, "internal": u.startswith(SITE)})
    return body.result(md or "", "markdown")


def markdown_to_text(md: str) -> str:
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", md)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    t = re.sub(r"^\|?[-:| ]+\|\s*$", "", t, flags=re.M)
    t = re.sub(r"^\|\s*|\s*\|\s*$", "", t, flags=re.M)
    t = t.replace(" | ", "\t")
    t = re.sub(r"(\*\*|__|~~|`)", "", t)
    t = re.sub(r"(?<!\w)\*(?!\s)([^*\n]+?)\*(?!\w)", r"\1", t)
    t = re.sub(r"^---$", "", t, flags=re.M)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return htmlmod.unescape(re.sub(r"\n{3,}", "\n\n", t)).strip()


# ------------------------------------------------------------------ Lexical -> Markdown

_FMT = ((1, "**"), (2, "*"), (4, "~~"), (16, "`"))


def _inline(nodes: list[dict], body: Body) -> str:
    out = []
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            s = n.get("text") or ""
            f = int(n.get("format") or 0)
            if s.strip():
                lead = s[: len(s) - len(s.lstrip())]
                trail = s[len(s.rstrip()):]
                core = s.strip()
                for bit, mark in _FMT:
                    if f & bit:
                        core = f"{mark}{core}{mark}"
                s = lead + core + trail
            out.append(s)
        elif t == "linebreak":
            out.append("  \n")
        elif t == "tab":
            out.append("\t")
        elif t in ("link", "autolink"):
            url = _abs(n.get("url"))
            txt = _inline(n.get("children") or [], body)
            if url:
                body.links.append({"url": url, "text": markdown_to_text(txt) or None,
                                   "internal": url.startswith(SITE)})
                out.append(f"[{txt}]({url})")
            else:
                out.append(txt)
        elif n.get("children"):
            out.append(_inline(n["children"], body))
        else:
            out.append(_decorator(n, body))
    return "".join(out)


def _decorator(n: dict, body: Body) -> str:
    url = n.get("url") or n.get("src") or n.get("videoUrl") or n.get("href")
    mk = (n.get("mediaKind") or n.get("fileKind") or n.get("kind") or n.get("type") or "").lower()
    ref = n.get("refId") or n.get("ref_id") or n.get("id")
    if not url:
        if not ref:
            return ""
        kind = "video" if "video" in mk else ("image" if "image" in mk else "embed")
        body.images.append({"url": None, "alt": n.get("description") or None, "kind": kind, "ref_id": str(ref)})
        return f"[{kind}: {ref}]"
    url = _abs(url)
    is_video = "video" in mk or re.search(r"\.(mp4|webm|mov)(\?|$)", url or "", re.I)
    kind = "video" if is_video else ("image" if re.search(r"\.(png|jpe?g|webp|gif|avif)(\?|$)", url, re.I)
                                     or "image" in mk or "file" in mk else "embed")
    alt = n.get("altText") or n.get("alt") or n.get("caption") or n.get("filename") or ""
    body.images.append({"url": url, "alt": alt or None, "kind": kind, "ref_id": str(ref) if ref else None})
    return f"![{alt}]({url})" if kind == "image" else f"[{kind}: {alt or url}]({url})"


def _block(n: dict, body: Body, depth: int = 0) -> str:
    t = n.get("type")
    kids = n.get("children") or []
    if t == "heading":
        lvl = int(str(n.get("tag") or "h2")[1:] or 2)
        txt = _inline(kids, body)
        plain = markdown_to_text(txt)
        if plain:
            body.headings.append({"level": lvl, "text": plain, "anchor": None})
        return "#" * lvl + " " + txt.strip()
    if t == "paragraph":
        return _inline(kids, body).strip()
    if t == "quote":
        return "\n".join("> " + ln for ln in _inline(kids, body).strip().splitlines())
    if t == "code":
        return "```" + (n.get("language") or "") + "\n" + markdown_to_text(_inline(kids, body)) + "\n```"
    if t == "horizontalrule":
        return "---"
    if t == "list":
        ordered = n.get("listType") == "number" or n.get("tag") == "ol"
        lines, i = [], int(n.get("start") or 1)
        for li in kids:
            nested = [c for c in (li.get("children") or []) if c.get("type") == "list"]
            inline = [c for c in (li.get("children") or []) if c.get("type") != "list"]
            if inline or not nested:
                mark = f"{i}. " if ordered else ("- [x] " if li.get("checked") else "- ")
                if n.get("listType") == "check" and not li.get("checked"):
                    mark = "- [ ] "
                lines.append("  " * depth + mark + _inline(inline, body).strip())
                i += 1
            for sub in nested:
                lines.append(_block(sub, body, depth + 1))
        return "\n".join(lines)
    if t == "table":
        rows = [[_inline(c.get("children") or [], body).replace("|", "\\|").replace("\n", " ").strip()
                 for c in (r.get("children") or [])] for r in kids]
        rows = [r for r in rows if r]
        if not rows:
            return ""
        w = max(len(r) for r in rows)
        rows = [r + [""] * (w - len(r)) for r in rows]
        return "\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w] +
                         ["| " + " | ".join(r) + " |" for r in rows[1:]])
    if kids:
        if all(k.get("type") in ("text", "linebreak", "link", "autolink", "tab") for k in kids):
            return _inline(kids, body).strip()
        return "\n\n".join(s for s in (_block(k, body, depth) for k in kids) if s)
    return _decorator(n, body)


def convert_lexical(tree: Optional[dict]) -> dict[str, Any]:
    body = Body()
    if not tree:
        return body.result("", "lexical")
    md = "\n\n".join(s for s in (_block(c, body) for c in tree.get("children") or []) if s.strip())
    return body.result(md, "lexical")
