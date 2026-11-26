"""Minimal, read-only decoder of a Yjs *v1 update* (the binary served by the brief snapshot endpoint
`https://dam-editor-worker.higgsfield.ai/brief/{folder_id}/snapshot`) into a tree of plain Python objects.

The web app loads that snapshot into a Y.Doc and renders it with Lexical's Yjs binding
(JS chunk `PublishedProjectBriefSnapshot`: `fetch(`${l}/brief/${e}/snapshot`)` -> `Y.applyUpdate`). No Yjs package is
needed: this module implements the v1 wire format (lib0 varints, structs, delete set) and the YATA ordering
(`Item.integrate`) on length-1 items, which is enough to rebuild the final document state of a snapshot.

Public API: `decode_doc(data) -> YDoc`; `YDoc.root(name)` returns a `YNode` whose `.children()` is the ordered list of
non-deleted content (str characters, dicts for embeds, nested `YNode`s) and `.attrs` the map entries (parentSub keys).
"""
from __future__ import annotations

import json
import struct
from typing import Any, Optional

ID = tuple  # (client, clock)

TYPE_REFS = {0: "array", 1: "map", 2: "text", 3: "xml_element", 4: "xml_fragment", 5: "xml_hook", 6: "xml_text"}


class YjsDecodeError(ValueError):
    pass


# ------------------------------------------------------------------ lib0 decoding
class _Reader:
    __slots__ = ("b", "i")

    def __init__(self, b: bytes):
        self.b, self.i = b, 0

    def u8(self) -> int:
        if self.i >= len(self.b):
            raise YjsDecodeError("unexpected end of update")
        v = self.b[self.i]
        self.i += 1
        return v

    def var_uint(self) -> int:
        num, shift = 0, 0
        while True:
            r = self.u8()
            num |= (r & 0x7F) << shift
            shift += 7
            if r < 0x80:
                return num
            if shift > 70:
                raise YjsDecodeError("varuint too long")

    def var_int(self) -> int:
        r = self.u8()
        num = r & 0x3F
        sign = -1 if r & 0x40 else 1
        shift = 6
        while r & 0x80:
            r = self.u8()
            num |= (r & 0x7F) << shift
            shift += 7
        return sign * num

    def buf(self) -> bytes:
        n = self.var_uint()
        if self.i + n > len(self.b):
            raise YjsDecodeError("buffer overrun")
        v = self.b[self.i:self.i + n]
        self.i += n
        return v

    def string(self) -> str:
        return self.buf().decode("utf-8", "surrogatepass")

    def any(self) -> Any:
        t = self.u8()
        if t == 127:
            return None          # undefined
        if t == 126:
            return None
        if t == 125:
            return self.var_int()
        if t == 124:
            v = struct.unpack(">f", self.b[self.i:self.i + 4])[0]
            self.i += 4
            return v
        if t == 123:
            v = struct.unpack(">d", self.b[self.i:self.i + 8])[0]
            self.i += 8
            return v
        if t == 122:
            v = struct.unpack(">q", self.b[self.i:self.i + 8])[0]
            self.i += 8
            return v
        if t == 121:
            return False
        if t == 120:
            return True
        if t == 119:
            return self.string()
        if t == 118:
            return {self.string(): self.any() for _ in range(self.var_uint())}
        if t == 117:
            return [self.any() for _ in range(self.var_uint())]
        if t == 116:
            return self.buf()
        raise YjsDecodeError(f"unknown any type {t}")


def _utf16_units(s: str) -> list[str]:
    """Split a str into JS UTF-16 code units (Yjs clocks count code units; astral chars take two)."""
    out: list[str] = []
    for ch in s:
        if ord(ch) > 0xFFFF:
            enc = ch.encode("utf-16-le")
            out += [enc[:2].decode("utf-16-le", "surrogatepass"), enc[2:].decode("utf-16-le", "surrogatepass")]
        else:
            out.append(ch)
    return out


def _join_utf16(units: list[str]) -> str:
    return "".join(units).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


# ------------------------------------------------------------------ document model
class YNode:
    """A shared type (root or nested): ordered sequence + map attributes."""
    __slots__ = ("type", "name", "start", "map", "item")

    def __init__(self, type_: str, name: Optional[str] = None, item: Optional["_Item"] = None):
        self.type, self.name, self.item = type_, name, item
        self.start: Optional[_Item] = None
        self.map: dict[str, _Item] = {}

    def children(self) -> list[Any]:
        """Ordered, non-deleted sequence content. Consecutive characters are merged into one str."""
        out: list[Any] = []
        units: list[str] = []
        it = self.start
        while it is not None:
            if not it.deleted and it.countable:
                if isinstance(it.content, _Char):
                    units.append(it.content.c)
                else:
                    if units:
                        out.append(_join_utf16(units))
                        units = []
                    out.append(it.content.value())
            it = it.right
        if units:
            out.append(_join_utf16(units))
        return out

    @property
    def attrs(self) -> dict[str, Any]:
        out = {}
        for k, it in self.map.items():
            if not it.deleted:
                out[k] = it.content.value()
        return out

    def __repr__(self) -> str:  # pragma: no cover
        return f"YNode({self.type}, {self.name!r})"


class _Char:
    __slots__ = ("c",)

    def __init__(self, c: str):
        self.c = c

    def value(self) -> str:
        return self.c


class _Val:
    __slots__ = ("v",)

    def __init__(self, v: Any):
        self.v = v

    def value(self) -> Any:
        return self.v


class _Type:
    __slots__ = ("node",)

    def __init__(self, node: YNode):
        self.node = node

    def value(self) -> YNode:
        return self.node


class _Item:
    __slots__ = ("id", "origin", "right_origin", "parent", "parent_sub", "content", "countable", "deleted",
                 "left", "right", "integrated")

    def __init__(self, id_, origin, right_origin, parent, parent_sub, content, countable=True):
        self.id, self.origin, self.right_origin = id_, origin, right_origin
        self.parent, self.parent_sub = parent, parent_sub      # parent: str (root name) | ID | None
        self.content, self.countable = content, countable
        self.deleted = False
        self.left: Optional[_Item] = None
        self.right: Optional[_Item] = None
        self.integrated = False


class YDoc:
    def __init__(self) -> None:
        self.items: dict[ID, _Item] = {}
        self.gc: set[ID] = set()
        self.roots: dict[str, YNode] = {}
        self.types: dict[ID, YNode] = {}

    def root(self, name: str) -> Optional[YNode]:
        return self.roots.get(name)


# ------------------------------------------------------------------ decoding
def _read_content(r: _Reader, ref: int, id_: ID, doc: YDoc) -> list[tuple[Any, bool]]:
    """-> one (content, countable) per clock unit."""
    if ref == 1:                                   # ContentDeleted
        return [(_Val(None), False)] * 0 + [(None, False)] * r.var_uint()
    if ref == 2:                                   # ContentJSON
        out = []
        for _ in range(r.var_uint()):
            s = r.string()
            out.append((_Val(None if s == "undefined" else json.loads(s)), True))
        return out
    if ref == 3:                                   # ContentBinary
        return [(_Val(r.buf()), True)]
    if ref == 4:                                   # ContentString
        return [(_Char(u), True) for u in _utf16_units(r.string())]
    if ref == 5:                                   # ContentEmbed
        return [(_Val({"embed": json.loads(r.string())}), True)]
    if ref == 6:                                   # ContentFormat (not countable)
        key = r.string()
        return [(_Val({"format": key, "value": json.loads(r.string())}), False)]
    if ref == 7:                                   # ContentType
        tref = r.var_uint()
        name = r.string() if tref in (3, 5) else None
        node = YNode(TYPE_REFS.get(tref, str(tref)), name)
        doc.types[id_] = node
        return [(_Type(node), True)]
    if ref == 8:                                   # ContentAny
        return [(_Val(r.any()), True) for _ in range(r.var_uint())]
    if ref == 9:                                   # ContentDoc (subdocument)
        guid = r.string()
        return [(_Val({"subdoc": guid, "opts": r.any()}), True)]
    raise YjsDecodeError(f"unknown content ref {ref}")


def decode_doc(data: bytes) -> YDoc:
    if not data:
        raise YjsDecodeError("empty update")
    r = _Reader(bytes(data))
    doc = YDoc()
    order: list[_Item] = []
    for _ in range(r.var_uint()):
        n_structs, client, clock = r.var_uint(), r.var_uint(), r.var_uint()
        for _ in range(n_structs):
            info = r.u8()
            low = info & 0x1F
            if low == 0:                           # GC
                n = r.var_uint()
                doc.gc.update((client, clock + k) for k in range(n))
                clock += n
                continue
            if low == 10:                          # Skip
                clock += r.var_uint()
                continue
            origin = (r.var_uint(), r.var_uint()) if info & 0x80 else None
            right_origin = (r.var_uint(), r.var_uint()) if info & 0x40 else None
            parent: Any = None
            parent_sub = None
            if not info & 0xC0:
                has_key = r.var_uint() == 1
                parent = r.string() if has_key else (r.var_uint(), r.var_uint())
                if info & 0x20:
                    parent_sub = r.string()
            units = _read_content(r, low, (client, clock), doc)
            for k, (content, countable) in enumerate(units):
                id_ = (client, clock + k)
                it = _Item(id_, origin if k == 0 else (client, clock + k - 1),
                           right_origin, parent if k == 0 else None, parent_sub if k == 0 else None,
                           content, countable)
                if content is None:
                    it.deleted = True
                    it.content = _Val(None)
                doc.items[id_] = it
                order.append(it)
            clock += len(units)
    # delete set
    try:
        for _ in range(r.var_uint()):
            client = r.var_uint()
            for _ in range(r.var_uint()):
                clock, ln = r.var_uint(), r.var_uint()
                for k in range(ln):
                    it = doc.items.get((client, clock + k))
                    if it is not None:
                        it.deleted = True
    except YjsDecodeError:
        pass
    _integrate_all(doc, order)
    return doc


# ------------------------------------------------------------------ YATA integration
def _parent_node(doc: YDoc, it: _Item) -> Optional[YNode]:
    p = it.parent
    if isinstance(p, str):
        node = doc.roots.get(p)
        if node is None:
            node = doc.roots[p] = YNode("root", p)
        return node
    if isinstance(p, tuple):
        return doc.types.get(p)
    return None


def _resolve_parent(doc: YDoc, it: _Item) -> bool:
    """Items written without parent info inherit it from their left (origin) or right neighbour."""
    if it.parent is not None:
        return True
    for ref in (it.origin, it.right_origin):
        if ref is None:
            continue
        other = doc.items.get(ref)
        if other is None:
            return False
        if not other.integrated:
            return False
        it.parent, it.parent_sub = other.parent, other.parent_sub
        return True
    return False


def _ready(doc: YDoc, it: _Item) -> Optional[bool]:
    """True = can integrate now, False = wait, None = can never integrate (refers to GC / unknown)."""
    for ref in (it.origin, it.right_origin):
        if ref is None:
            continue
        if ref in doc.gc:
            return None
        other = doc.items.get(ref)
        if other is None:
            return None
        if not other.integrated:
            return False
    if isinstance(it.parent, tuple):
        if it.parent in doc.gc:
            return None
        p = doc.items.get(it.parent)
        if p is None:
            return None
        if not p.integrated:
            return False
    return True


def _integrate_all(doc: YDoc, order: list[_Item]) -> None:
    pending = order
    while pending:
        nxt: list[_Item] = []
        progressed = False
        for it in pending:
            st = _ready(doc, it)
            if st is None:
                it.deleted = True
                it.integrated = True
                progressed = True
                continue
            if not st or not _resolve_parent(doc, it):
                nxt.append(it)
                continue
            _integrate(doc, it)
            progressed = True
        if not progressed:
            for it in nxt:                         # unresolvable: drop
                it.deleted = True
                it.integrated = True
            break
        pending = nxt


def _integrate(doc: YDoc, it: _Item) -> None:
    it.integrated = True
    parent = _parent_node(doc, it)
    if parent is None:
        it.deleted = True
        return
    left = doc.items.get(it.origin) if it.origin else None
    right = doc.items.get(it.right_origin) if it.right_origin else None
    sub = it.parent_sub
    if (left is None and (right is None or right.left is not None)) or (left is not None and left.right is not right):
        if left is not None:
            o = left.right
        elif sub is not None:
            o = parent.map.get(sub)
            while o is not None and o.left is not None:
                o = o.left
        else:
            o = parent.start
        conflicting: set[ID] = set()
        before_origin: set[ID] = set()
        while o is not None and o is not right:
            before_origin.add(o.id)
            conflicting.add(o.id)
            if it.origin == o.origin:
                if o.id[0] < it.id[0]:
                    left = o
                    conflicting.clear()
                elif it.right_origin == o.right_origin:
                    break
            elif o.origin is not None and o.origin in before_origin:
                if o.origin not in conflicting:
                    left = o
                    conflicting.clear()
            else:
                break
            o = o.right
    it.left = left
    if left is not None:
        r = left.right
        left.right = it
    else:
        if sub is not None:
            r = parent.map.get(sub)
            while r is not None and r.left is not None:
                r = r.left
        else:
            r = parent.start
            parent.start = it
    it.right = r
    if r is not None:
        r.left = it
    elif sub is not None:
        parent.map[sub] = it
        if left is not None:
            left.deleted = True
