"""Blog scraper options: CLI flags, Selection dataclass, parsing from CLI args / manifest / `-a k=v`."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Iterable, Optional

from .endpoints import DEFAULT_WHAT, LOCALES, WHAT

ALIASES = {"posts": "blog", "talent": "talents", "help-center": "help", "helpcenter": "help",
           "enterprise": "enterprise-help", "case-study": "case-studies", "casestudies": "case-studies",
           "recommended": "community"}


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
    with_content: bool = True
    locale: str = "en"
    tags: list[str] = field(default_factory=list)
    since: Optional[str] = None                     # YYYY-MM-DD (inclusive)
    include_author_avatars: bool = False            # community/talent authors' avatar URLs (personal data, opt-in)
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
        self.what = what
        self.locale = (self.locale or "en").strip()
        if self.locale not in LOCALES:
            raise ValueError(f"--locale must be one of {list(LOCALES)}")
        self.tags = [t.lower() for t in _split(self.tags)]
        if self.since:
            date.fromisoformat(str(self.since))     # validate
            self.since = str(self.since)
        else:
            self.since = None
        self.with_content = _truthy(self.with_content)
        self.include_author_avatars = _truthy(self.include_author_avatars)
        self.write_markdown = _truthy(self.write_markdown)

    def wants(self, what: str) -> bool:
        return what in self.what

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("blog: what to scrape")
    g.add_argument("--what", default=",".join(DEFAULT_WHAT),
                   help=f"comma list of {list(WHAT)} or 'all' (default: %(default)s; 'community' = the large "
                        "user blog feed /blog/posts/recommended, opt-in)")
    g.add_argument("--with-content", dest="with_content", action="store_true", default=True,
                   help="fetch the full article text (default: on)")
    g.add_argument("--no-content", dest="with_content", action="store_false",
                   help="metadata only from the index pages / feeds (~10 requests): no per-article pages, no post "
                        "bodies; text fields stay empty")
    g.add_argument("--locale", default="en", help=f"one of {list(LOCALES)} (default: en; others fall back to "
                                                  "English where no translation exists)")
    f = p.add_argument_group("blog: filters (applied to output)")
    f.add_argument("--tags", default=None, help="keep posts whose category slug/title or tags match (comma list)")
    f.add_argument("--since", default=None, help="keep items published/updated on or after YYYY-MM-DD")
    o = p.add_argument_group("blog: output")
    o.add_argument("--include-author-avatars", action="store_true",
                   help="keep community/talent authors' avatar URLs (personal data; off by default)")
    o.add_argument("--no-markdown", dest="write_markdown", action="store_false", default=True,
                   help="don't write output/articles/<collection>/<slug>.md")


def make_selection(a: argparse.Namespace) -> Selection:
    return Selection(what=a.what, with_content=a.with_content, locale=a.locale, tags=a.tags, since=a.since,
                     include_author_avatars=a.include_author_avatars, write_markdown=a.write_markdown)


def selection_from_dict(d: Optional[dict]) -> Selection:
    d = dict(d or {})
    kw = {k: v for k, v in d.items() if k in Selection.__dataclass_fields__}
    return Selection(**kw)


def default_label(sel: Selection) -> str:
    base = "all" if set(sel.what) >= set(DEFAULT_WHAT) else "-".join(sel.what)
    return base + ("" if sel.locale == "en" else f"-{sel.locale}")
