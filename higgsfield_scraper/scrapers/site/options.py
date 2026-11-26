"""Site scraper options: CLI flags, Selection dataclass, parsing from CLI args / manifest / `-a k=v`."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from .endpoints import DEFAULT_WHAT, WHAT

ALIASES = {"app": "apps", "courses": "academy", "lessons": "academy", "skills": "mcp", "original-series": "originals",
           "series": "originals", "mixed-media-presets": "mixed-media", "mixedmedia": "mixed-media",
           "landing": "landings", "marketing": "landings", "plugins": "landings", "room": "rooms", "promo": "promos",
           "config": "promos", "rooms-api": "room-list", "room-items": "room-content",
           "room-discussions": "room-content", "academy_api": "academy-api", "academy-json": "academy-api"}


def _split(value: Any) -> list[str]:
    if value is None:
        return []
    items: Iterable[Any] = value if isinstance(value, (list, tuple)) else [value]
    return list(dict.fromkeys(p.strip() for v in items for p in str(v).split(",") if p.strip()))


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Selection:
    what: list[str] = field(default_factory=lambda: list(DEFAULT_WHAT))
    with_content: bool = True                       # detail pages + Markdown bodies
    only: list[str] = field(default_factory=list)   # keep only pages whose path contains one of these strings
    with_profiles: bool = False                     # creators' usernames / avatars (personal data, opt-in)
    write_markdown: bool = True                     # output/articles/<collection>/<slug>.md

    def __post_init__(self) -> None:
        what = [ALIASES.get(w.lower(), w.lower()) for w in _split(self.what)]
        if not what or what == ["all"]:
            what = list(DEFAULT_WHAT)
        elif "all" in what:
            what = list(dict.fromkeys(list(DEFAULT_WHAT) + [w for w in what if w != "all"]))
        bad = [w for w in what if w not in WHAT]
        if bad:
            raise ValueError(f"unknown --what value(s) {bad}; choose from {list(WHAT)} or 'all'")
        self.what = list(dict.fromkeys(what))
        self.only = [o.lower() for o in _split(self.only)]
        self.with_content = _truthy(self.with_content)
        self.with_profiles = _truthy(self.with_profiles)
        self.write_markdown = _truthy(self.write_markdown)

    def wants(self, what: str) -> bool:
        return what in self.what

    def path_ok(self, path: Optional[str]) -> bool:
        return not self.only or any(o in (path or "").lower() for o in self.only)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def rooms_api(self) -> bool:
        return self.wants("room-list") or self.wants("room-content")

    @property
    def academy_api(self) -> bool:
        return self.wants("academy-api")


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("site: what to scrape")
    g.add_argument("--what", default=",".join(DEFAULT_WHAT),
                   help=f"comma list of {list(WHAT)} or 'all' (default: %(default)s; 'rooms' = community room "
                        "pages, title/description only, opt-in; 'room-list' = every room from the public rooms API "
                        "with member/works counts and room-stats (posts, discussions); 'room-content' = room-list + "
                        "each room's works (shots, projects, blog posts) and discussion posts. All three are opt-in, "
                        "not part of 'all'; --max-items caps rooms, room items and discussions separately; "
                        "'academy-api' = the academy JSON API (fnf-academy: categories, courses with "
                        "free_generations / test_count, lessons with MDX source, xp, subtitles), opt-in, not in "
                        "'all'; --no-content = categories + course list only)")
    g.add_argument("--with-content", dest="with_content", action="store_true", default=True,
                   help="fetch every detail page (apps, courses, lessons, MCP skills, episodes) and convert bodies "
                        "to Markdown (default: on)")
    g.add_argument("--no-content", dest="with_content", action="store_false",
                   help="index pages only where an index exists (apps, academy, mcp, originals): fewer requests, "
                        "no lesson/landing text")
    g.add_argument("--only", default=None,
                   help="keep only detail pages whose URL path contains one of these strings (comma list), "
                        "e.g. 'kling,/plugins/,blockbuster-4k'")
    o = p.add_argument_group("site: output")
    o.add_argument("--with-profiles", action="store_true",
                   help="keep creators' usernames/avatars (app authors, episode uploaders, mixed-media sample "
                        "creators). Personal data: off by default")
    o.add_argument("--no-markdown", dest="write_markdown", action="store_false", default=True,
                   help="don't write output/articles/<collection>/<slug>.md")


def make_selection(a: argparse.Namespace) -> Selection:
    return Selection(what=a.what, with_content=a.with_content, only=a.only, with_profiles=a.with_profiles,
                     write_markdown=a.write_markdown)


def selection_from_dict(d: Optional[dict]) -> Selection:
    d = dict(d or {})
    return Selection(**{k: v for k, v in d.items() if k in Selection.__dataclass_fields__})


def default_label(sel: Selection) -> str:
    return "all" if set(sel.what) >= set(DEFAULT_WHAT) else "-".join(sel.what)
