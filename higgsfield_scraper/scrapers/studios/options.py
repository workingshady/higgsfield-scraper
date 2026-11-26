"""CLI options + Selection for the studios scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from .endpoints import (APPS_SORTS, CMS_LANGS, DEFAULT_WHATS, GALLERY_DEFAULT_PAGES, GALLERY_FEEDS, PUBLIC_WHATS,
                        STUDIOS, WHAT, WHATS)


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("studios: what to scrape")
    g.add_argument("--what", default=None,
                   help="comma list of sources, 'public' or 'all' (same: every source is public; default: all). "
                        "Available: " + ", ".join(WHATS))
    g.add_argument("--lang", default="en",
                   help="language of the CMS lists (playable presets, AI influencer options): en es de ja ko")
    g.add_argument("--apps-sort", default="trending", choices=APPS_SORTS,
                   help="community apps order (JS default `trending`; unknown values fall back to it)")
    g.add_argument("--studios", default=None,
                   help="galleries: only these studios (comma list; default all): " + ", ".join(STUDIOS))
    g.add_argument("--gallery-feeds", default=",".join(GALLERY_FEEDS),
                   help="galleries: approved (curated) and/or trending (default: both)")
    g.add_argument("--gallery-pages", type=int, default=GALLERY_DEFAULT_PAGES,
                   help=f"galleries: pages (50 items) per studio and feed (default {GALLERY_DEFAULT_PAGES}; 0 = until "
                        "the end; --max-pages also applies)")
    g.add_argument("--with-comments", action="store_true",
                   help="galleries: also fetch the public comments of every gallery item (1+ request per item)")
    o = p.add_argument_group("studios: personal data")
    o.add_argument("--with-profiles", action="store_true",
                   help="opt-in: keep author user_id/name/avatar (apps, games, skills, employees, gallery items, "
                        "comments) (default: only a pseudonymous author_key hash)")


@dataclass
class Selection:
    what: Optional[list[str]] = None            # None = DEFAULT_WHATS
    lang: str = "en"
    apps_sort: str = "trending"
    studios: Optional[list[str]] = None         # None = all
    gallery_feeds: list[str] = field(default_factory=lambda: list(GALLERY_FEEDS))
    gallery_pages: int = GALLERY_DEFAULT_PAGES
    with_comments: bool = False
    with_profiles: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolve(self) -> list[str]:
        ws = list(self.what) if self.what is not None else list(DEFAULT_WHATS)
        return [w for w in WHATS if w in ws]

    def resolve_studios(self) -> list[str]:
        return [s for s in STUDIOS if self.studios is None or s in self.studios]


def _list(v: Any) -> list[str]:
    items: Iterable[str] = v if isinstance(v, (list, tuple)) else str(v).split(",")
    return [x.strip() for x in items if x and x.strip()]


def parse_what(value: Any) -> Optional[list[str]]:
    if value in (None, ""):
        return None
    out: list[str] = []
    for raw in _list(value):
        k = raw.lower().replace("-", "_")
        if k in ("all", "public"):
            out += list(PUBLIC_WHATS)
        elif k in WHAT:
            out.append(k)
        elif k + "s" in WHAT:                       # singular convenience: app, game, gallery -> galleries below
            out.append(k + "s")
        elif k == "gallery":
            out.append("galleries")
        else:
            raise ValueError(f"unknown studios source {raw!r}; available: {', '.join(WHATS)}")
    return list(dict.fromkeys(out))


def _truthy(v: Any) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def build(what: Any = None, lang: Any = "en", apps_sort: Any = "trending", studios: Any = None,
          gallery_feeds: Any = None, gallery_pages: Any = GALLERY_DEFAULT_PAGES, with_comments: Any = False,
          with_profiles: Any = False) -> Selection:
    lang = str(lang or "en").lower()
    if lang not in CMS_LANGS:
        raise ValueError(f"lang must be one of {CMS_LANGS}")
    sort = str(apps_sort or "trending")
    if sort not in APPS_SORTS:
        raise ValueError(f"apps_sort must be one of {APPS_SORTS}")
    st = _list(studios) if studios not in (None, "") else None
    bad = [s for s in st or [] if s not in STUDIOS]
    if bad:
        raise ValueError(f"unknown studio(s) {bad}; available: {', '.join(STUDIOS)}")
    feeds = _list(gallery_feeds) if gallery_feeds not in (None, "") else list(GALLERY_FEEDS)
    bad = [f for f in feeds if f not in GALLERY_FEEDS]
    if bad:
        raise ValueError(f"unknown gallery feed(s) {bad}; available: {GALLERY_FEEDS}")
    pages = int(gallery_pages if gallery_pages not in (None, "") else GALLERY_DEFAULT_PAGES)
    if pages < 0:
        raise ValueError("gallery_pages must be >= 0")
    return Selection(what=parse_what(what), lang=lang, apps_sort=sort, studios=st, gallery_feeds=feeds,
                     gallery_pages=pages, with_comments=_truthy(with_comments),
                     with_profiles=_truthy(with_profiles))


def make_selection(a: argparse.Namespace) -> Selection:
    return build(what=a.what, lang=a.lang, apps_sort=a.apps_sort, studios=a.studios, gallery_feeds=a.gallery_feeds,
                 gallery_pages=a.gallery_pages, with_comments=a.with_comments, with_profiles=a.with_profiles)


KEYS = ("what", "lang", "apps_sort", "studios", "gallery_feeds", "gallery_pages", "with_comments", "with_profiles")


def selection_from_dict(d: Optional[dict]) -> Selection:
    """Accepts Selection.to_dict() (manifest) and string kwargs (`scrapy crawl studios -a what=apps`)."""
    d = dict(d or {})
    return build(**{k: d[k] for k in KEYS if k in d})


def default_label(sel: Selection) -> str:
    ws = sel.resolve()
    if sel.what is None or set(ws) == set(WHATS):
        return "all"
    return "-".join(ws) if len(ws) <= 2 else f"{len(ws)}sources"
