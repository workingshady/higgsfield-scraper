"""Pure-Python decoder for Yjs v1 document updates + a renderer for Lexical editor trees.

Community / talent blog posts (`content_url` = https://cdn.higgsfield.ai/blog/<uuid>.bin) are stored as a binary
Yjs update (`Y.encodeStateAsUpdate(doc)`) of a Lexical editor bound with `@lexical/yjs`. We decode the update,
integrate it with the YATA rules (enough for a full-state update), and rebuild the Lexical node tree:

* element nodes (root, paragraph, heading, list, listitem, quote, link, ...) are `Y.XmlText`; their properties
  (`__type`, `__tag`, `__listType`, `__url`, ...) are the XmlText's attributes (map entries);
* text nodes are a `Y.Map` (properties: `__type`="text", `__format` bitmask, ...) followed by the text characters
  inside the parent XmlText;
* decorator nodes (images, videos, embeds, ...) are `Y.XmlElement` whose attributes hold their properties.

No third-party dependency (pycrdt / y-py) is needed.
"""
from __future__ import annotations

import json
import struct
from typing import Any, Optional

# ------------------------------------------------------------------ lib0 decoding


class _Dec:
    def __init__(self, data: bytes):
        self.b, self.i = data, 0

    def u8(self) -> int:
        v = self.b[self.i]
        self.i += 1
        return v

    def var_uint(self) -> int:
        num, mult = 0, 1
        while True:
            r = self.b[self.i]
            self.i += 1
            num += (r & 0x7F) * mult
            mult *= 128
            if r < 0x80:
                return num

    def var_int(self) -> int:
        r = self.u8()
        num = r & 0x3F
        mult = 64
        neg = r & 0x40
        if r & 0x80:
            while True:
                r = self.u8()
                num += (r & 0x7F) * mult
                mult *= 128
                if r < 0x80:
                    break
        return -num if neg else num

    def bytes_(self, n: int) -> bytes:
        v = self.b[self.i:self.i + n]
        self.i += n
        return v

    def var_bytes(self) -> bytes:
        return self.bytes_(self.var_uint())

    def var_string(self) -> str:
        return self.var_bytes().decode("utf-8", "surrogatepass")

    def any(self) -> Any:
        t = self.u8()
        if t == 127:
            return None
        if t == 126:
            return None
        if t == 125:
            return self.var_int()
        if t == 124:
            return struct.unpack(">f", self.bytes_(4))[0]
        if t == 123:
            return struct.unpack(">d", self.bytes_(8))[0]
        if t == 122:
            return struct.unpack(">q", self.bytes_(8))[0]
        if t == 121:
            return False
        if t == 120:
            return True
        if t == 119:
            return self.var_string()
        if t == 118:
            return {self.var_string(): self.any() for _ in range(self.var_uint())}
        if t == 117:
            return [self.any() for _ in range(self.var_uint())]
        if t == 116:
            return self.var_bytes().hex()
        raise ValueError(f"unknown lib0 any type {t}")


# ------------------------------------------------------------------ structs

class YType:
    """A shared type (root or nested): ordered sequence + map of attributes."""

    __slots__ = ("kind", "name", "start", "map")

    def __init__(self, kind: str, name: Optional[str] = None):
        self.kind, self.name = kind, name          # kind: array|map|text|xmlelement|xmlfragment|xmlhook|xmltext
        self.start: Optional[_Item] = None
        self.map: dict[str, _Item] = {}           # key -> last (rightmost) item


class _Item:
    __slots__ = ("id", "origin", "right_origin", "parent", "parent_sub", "content", "left", "right", "deleted")

    def __init__(self, id_, origin, right_origin, parent, parent_sub, content):
        self.id, self.origin, self.right_origin = id_, origin, right_origin
        self.parent, self.parent_sub, self.content = parent, parent_sub, content   # content: ("str", ch) etc.
        self.left: Optional[_Item] = None
        self.right: Optional[_Item] = None
        self.deleted = False


_TYPE_REFS = {0: "array", 1: "map", 2: "text", 3: "xmlelement", 4: "xmlfragment", 5: "xmlhook", 6: "xmltext"}


def _utf16_units(s: str) -> list[str]:
    b = s.encode("utf-16-le", "surrogatepass")
    return [b[i:i + 2].decode("utf-16-le", "surrogatepass") for i in range(0, len(b), 2)]


def _join_units(units: list[str]) -> str:
    raw = "".join(units)
    try:
        return raw.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    except UnicodeDecodeError:
        return raw.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def decode_update(data: bytes) -> dict[str, YType]:
    """Decode a Yjs v1 update into root types {name: YType}."""
    d = _Dec(data)
    raw: list[tuple] = []                          # (id, origin, right_origin, parent_info, parent_sub, content)
    gc_ids: set[tuple[int, int]] = set()
    for _ in range(d.var_uint()):
        n_structs = d.var_uint()
        client = d.var_uint()
        clock = d.var_uint()
        for _ in range(n_structs):
            info = d.u8()
            ref = info & 0x1F
            if ref == 0:                           # GC
                ln = d.var_uint()
                for k in range(ln):
                    gc_ids.add((client, clock + k))
                clock += ln
                continue
            if ref == 10:                          # Skip
                clock += d.var_uint()
                continue
            origin = (d.var_uint(), d.var_uint()) if info & 0x80 else None
            right_origin = (d.var_uint(), d.var_uint()) if info & 0x40 else None
            cant_copy = (info & 0xC0) == 0
            parent_info = None
            if cant_copy:
                if d.var_uint() == 1:
                    parent_info = ("root", d.var_string())
                else:
                    parent_info = ("id", (d.var_uint(), d.var_uint()))
            parent_sub = d.var_string() if cant_copy and (info & 0x20) else None
            units = _read_content(d, ref)
            for k, unit in enumerate(units):
                o = origin if k == 0 else (client, clock + k - 1)
                raw.append(((client, clock + k), o, right_origin, parent_info if k == 0 else ("same", None),
                            parent_sub, unit))
            clock += len(units)
    deleted: set[tuple[int, int]] = set()
    for _ in range(d.var_uint() if d.i < len(d.b) else 0):
        client = d.var_uint()
        for _ in range(d.var_uint()):
            clk, ln = d.var_uint(), d.var_uint()
            for k in range(ln):
                deleted.add((client, clk + k))
    return _integrate(raw, deleted, gc_ids)


def _read_content(d: _Dec, ref: int) -> list[tuple]:
    if ref == 1:                                   # ContentDeleted
        return [("deleted", None)] * d.var_uint()
    if ref == 2:                                   # ContentJSON
        out = []
        for _ in range(d.var_uint()):
            s = d.var_string()
            out.append(("any", None if s == "undefined" else json.loads(s)))
        return out
    if ref == 3:                                   # ContentBinary
        return [("any", d.var_bytes().hex())]
    if ref == 4:                                   # ContentString (length in UTF-16 units)
        return [("str", u) for u in _utf16_units(d.var_string())]
    if ref == 5:                                   # ContentEmbed
        return [("embed", json.loads(d.var_string()))]
    if ref == 6:                                   # ContentFormat
        key = d.var_string()
        return [("format", (key, json.loads(d.var_string())))]
    if ref == 7:                                   # ContentType
        tref = d.var_uint()
        name = d.var_string() if tref in (3, 5) else None
        return [("type", YType(_TYPE_REFS.get(tref, f"type{tref}"), name))]
    if ref == 8:                                   # ContentAny
        return [("any", d.any()) for _ in range(d.var_uint())]
    if ref == 9:                                   # ContentDoc
        guid = d.var_string()
        opts = d.any()
        return [("doc", {"guid": guid, "opts": opts})]
    raise ValueError(f"unknown Yjs content ref {ref}")


def _integrate(raw: list[tuple], deleted: set, gc_ids: set) -> dict[str, YType]:
    roots: dict[str, YType] = {}
    store: dict[tuple[int, int], _Item] = {}
    pending = list(raw)
    # resolve "same" parent (continuation units inherit the parent of the previous unit of the same struct)
    last_parent: dict[tuple[int, int], Any] = {}
    fixed = []
    for rec in pending:
        id_, o, ro, pinfo, psub, unit = rec
        if pinfo == ("same", None):
            pinfo = last_parent.get((id_[0], id_[1] - 1))
        last_parent[id_] = pinfo
        fixed.append((id_, o, ro, pinfo, psub, unit))
    pending = fixed
    progress = True
    while pending and progress:
        progress = False
        rest = []
        for rec in pending:
            id_, o, ro, pinfo, psub, unit = rec
            if (o and o not in store and o not in gc_ids) or (ro and ro not in store and ro not in gc_ids):
                rest.append(rec)
                continue
            if (o and o in gc_ids) or (ro and ro in gc_ids):
                progress = True                    # its neighbourhood was garbage-collected -> deleted subtree
                continue
            left = store.get(o) if o else None
            right = store.get(ro) if ro else None
            parent: Optional[YType]
            if pinfo is None:                      # copy parent from neighbours
                src = left or right
                if src is None:
                    progress = True
                    continue
                parent, psub = src.parent, src.parent_sub
            elif pinfo[0] == "root":
                parent = roots.setdefault(pinfo[1], YType("root", pinfo[1]))
            else:
                pid = pinfo[1]
                if pid in gc_ids:
                    progress = True
                    continue
                pitem = store.get(pid)
                if pitem is None:
                    rest.append(rec)
                    continue
                if pitem.content[0] != "type":
                    progress = True
                    continue
                parent = pitem.content[1]
            item = _Item(id_, o, ro, parent, psub, unit)
            item.left, item.right = left, right
            _yata(item, store)
            store[id_] = item
            if id_ in deleted or unit[0] == "deleted":
                item.deleted = True
            progress = True
        pending = rest
    return roots


def _yata(item: _Item, store: dict) -> None:
    parent, psub = item.parent, item.parent_sub
    left = item.left
    if (left is None and (item.right is None or item.right.left is not None)) or \
            (left is not None and left.right is not item.right):
        if left is not None:
            o = left.right
        elif psub is not None:
            o = parent.map.get(psub)
            while o is not None and o.left is not None:
                o = o.left
        else:
            o = parent.start
        conflicting: set[int] = set()
        before_origin: set[int] = set()
        while o is not None and o is not item.right:
            before_origin.add(id(o))
            conflicting.add(id(o))
            if item.origin == o.origin:
                if o.id[0] < item.id[0]:
                    left = o
                    conflicting.clear()
                elif item.right_origin == o.right_origin:
                    break
            elif o.origin is not None and o.origin in store and id(store[o.origin]) in before_origin:
                if id(store[o.origin]) not in conflicting:
                    left = o
                    conflicting.clear()
            else:
                break
            o = o.right
        item.left = left
    if item.left is not None:
        item.right = item.left.right
        item.left.right = item
    else:
        if psub is not None:
            r = parent.map.get(psub)
            while r is not None and r.left is not None:
                r = r.left
        else:
            r = parent.start
            parent.start = item
        item.right = r
    if item.right is not None:
        item.right.left = item
    elif psub is not None:
        parent.map[psub] = item
        if item.left is not None:
            item.left.deleted = True


# ------------------------------------------------------------------ Yjs -> Lexical JSON-ish tree

def _attrs(t: YType) -> dict[str, Any]:
    out = {}
    for k, it in t.map.items():
        if it.deleted:
            continue
        kind, val = it.content
        out[k] = val if kind in ("any", "str", "embed") else (_type_to_node(val) if kind == "type" else val)
    return out


def _seq(t: YType):
    it = t.start
    while it is not None:
        if not it.deleted:
            yield it
        it = it.right


def _type_to_node(t: YType) -> dict[str, Any]:
    props = _attrs(t)
    node: dict[str, Any] = {"type": props.pop("__type", t.name or t.kind)}
    node.update({k.lstrip("_"): v for k, v in props.items()})
    if t.kind in ("xmltext", "root", "text"):
        children: list[dict] = []
        cur: Optional[dict] = None
        units: list[str] = []

        def flush():
            nonlocal cur, units
            if cur is not None or units:
                tn = cur if cur is not None else {"type": "text"}
                tn["text"] = _join_units(units)
                children.append(tn)
            cur, units = None, []

        for it in _seq(t):
            kind, val = it.content
            if kind == "str":
                units.append(val)
            elif kind == "type":
                flush()
                if val.kind == "map":            # a Lexical text-node (properties); its text follows
                    p = _attrs(val)
                    cur = {"type": p.pop("__type", "text")}
                    cur.update({k.lstrip("_"): v for k, v in p.items()})
                else:
                    children.append(_type_to_node(val))
            elif kind == "embed":
                flush()
                children.append({"type": "embed", "value": val})
        flush()
        node["children"] = children
    elif t.kind == "xmlelement":
        kids = [_type_to_node(it.content[1]) for it in _seq(t) if it.content[0] == "type"]
        if kids:
            node["children"] = kids
    return node


def decode_lexical(data: bytes, root_name: str = "root") -> Optional[dict[str, Any]]:
    """Binary Yjs update -> Lexical-like node tree {"type": "root", "children": [...]} (None when absent)."""
    roots = decode_update(data)
    root = roots.get(root_name) or (next(iter(roots.values())) if roots else None)
    if root is None:
        return None
    root.kind = "xmltext"
    node = _type_to_node(root)
    node["type"] = "root"
    return node
