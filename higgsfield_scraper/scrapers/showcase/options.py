"""CLI options + Selection for the showcase scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from .endpoints import (CMS_LANGS, DEFAULT_WHATS, EXPLORE_DEFAULT_PAGES, EXPLORE_SORTS, EXPLORE_SOURCES, L10N_LANGS,
                        OPT_IN_WHATS, PUBLIC_WHATS, REELS_SOURCES, WHAT, WHATS)


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("showcase: what to scrape")
    g.add_argument("--what", default=None,
                   help="comma list of sources, 'public' (default: every public source except the opt-in ones) or "
                        "'all' (+ opt-in " + ", ".join(sorted(OPT_IN_WHATS)) + " and login-only `season`). "
                        "Available: " + ", ".join(WHATS))
    g.add_argument("--lang", default="en",
                   help="language for CMS lists and Property Studio titles (en, es, de, ja, ko; zh titles only)")
    g.add_argument("--explore-sources", default=",".join(EXPLORE_SOURCES),
                   help="video explore feeds: higgsfield (curated, ~35), community (~49k) (default: both)")
    g.add_argument("--explore-sort", default="new", choices=EXPLORE_SORTS + ("both",),
                   help="community explore sort: new (page-numbered, has `total`), trending (opaque cursor), both")
    g.add_argument("--explore-pages", type=int, default=EXPLORE_DEFAULT_PAGES,
                   help=f"pages (20 items) per explore feed (default {EXPLORE_DEFAULT_PAGES}; 0 = until the end; "
                        "--max-pages also applies)")
    g.add_argument("--explore-categories", default=None,
                   help="also crawl the community feed per category: comma list or 'all' (from /categories)")
    g.add_argument("--effects", default=None,
                   help="only these /effects/examples slugs (comma list); default: every slug in the sitemap")
    g.add_argument("--reels-sources", default=",".join(REELS_SOURCES),
                   help="Shorts Studio preset lists for reels_presets/reels_comments: higgsfield (curated, ~40), "
                        "community (user-published, ~75) (default: both)")
    o = p.add_argument_group("showcase: personal data")
    o.add_argument("--with-profiles", action="store_true",
                   help="opt-in: keep creator user_id/username/avatar on explore variants, effect samples and reels "
                        "presets/comments, and the reference reel's author handle (default: only a pseudonymous "
                        "creator_key hash)")


@dataclass
class Selection:
    what: Optional[list[str]] = None            # None = DEFAULT_WHATS
    lang: str = "en"
    explore_sources: list[str] = field(default_factory=lambda: list(EXPLORE_SOURCES))
    explore_sort: str = "new"
    explore_pages: int = EXPLORE_DEFAULT_PAGES
    explore_categories: Optional[list[str]] = None   # ["all"] = every category
    effects: Optional[list[str]] = None
    with_profiles: bool = False
    reels_sources: list[str] = field(default_factory=lambda: list(REELS_SOURCES))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolve(self) -> list[str]:
        ws = list(self.what) if self.what is not None else list(DEFAULT_WHATS)
        return [w for w in WHATS if w in ws]

    def explore_sorts(self) -> list[str]:
        return list(EXPLORE_SORTS) if self.explore_sort == "both" else [self.explore_sort]

    def login_whats(self) -> list[str]:
        return [w for w in self.resolve() if WHAT[w][2]]


def _list(v: Any) -> list[str]:
    items: Iterable[str] = v if isinstance(v, (list, tuple)) else str(v).split(",")
    return [x.strip() for x in items if x and x.strip()]


def parse_what(value: Any) -> Optional[list[str]]:
    if value in (None, ""):
        return None
    out: list[str] = []
    for raw in _list(value):
        k = raw.lower().replace("-", "_")
        if k == "all":
            out += list(WHATS)
        elif k == "public":
            out += list(PUBLIC_WHATS)
        elif k in WHAT:
            out.append(k)
        elif k + "s" in WHAT:                       # singular convenience: canvas_template
            out.append(k + "s")
        elif k == "explore":
            out.append("explore_categories")
        elif k in ("reels", "shorts_studio", "ai_reels"):
            out.append("reels_presets")
        else:
            raise ValueError(f"unknown showcase source {raw!r}; available: {', '.join(WHATS)}")
    return list(dict.fromkeys(out))


def _truthy(v: Any) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def build(what: Any = None, lang: Any = "en", explore_sources: Any = None, explore_sort: Any = "new",
          explore_pages: Any = EXPLORE_DEFAULT_PAGES, explore_categories: Any = None, effects: Any = None,
          with_profiles: Any = False, reels_sources: Any = None) -> Selection:
    lang = str(lang or "en").lower()
    if lang not in L10N_LANGS:
        raise ValueError(f"lang must be one of {L10N_LANGS} (CMS lists: {CMS_LANGS})")
    sources = _list(explore_sources) if explore_sources not in (None, "") else list(EXPLORE_SOURCES)
    bad = [s for s in sources if s not in EXPLORE_SOURCES]
    if bad:
        raise ValueError(f"unknown explore source(s) {bad}; available: {EXPLORE_SOURCES}")
    sort = str(explore_sort or "new")
    if sort not in EXPLORE_SORTS + ("both",):
        raise ValueError(f"explore_sort must be one of {EXPLORE_SORTS + ('both',)}")
    pages = int(explore_pages if explore_pages not in (None, "") else EXPLORE_DEFAULT_PAGES)
    if pages < 0:
        raise ValueError("explore_pages must be >= 0")
    cats = _list(explore_categories) if explore_categories not in (None, "") else None
    reels = _list(reels_sources) if reels_sources not in (None, "") else list(REELS_SOURCES)
    bad = [s for s in reels if s not in REELS_SOURCES]
    if bad or not reels:
        raise ValueError(f"unknown reels source(s) {bad}; available: {REELS_SOURCES}")
    return Selection(what=parse_what(what), lang=lang, explore_sources=sources, explore_sort=sort,
                     explore_pages=pages, explore_categories=cats,
                     effects=_list(effects) if effects not in (None, "") else None,
                     with_profiles=_truthy(with_profiles), reels_sources=reels)


def make_selection(a: argparse.Namespace) -> Selection:
    return build(what=a.what, lang=a.lang, explore_sources=a.explore_sources, explore_sort=a.explore_sort,
                 explore_pages=a.explore_pages, explore_categories=a.explore_categories, effects=a.effects,
                 with_profiles=a.with_profiles, reels_sources=a.reels_sources)


def selection_from_dict(d: Optional[dict]) -> Selection:
    """Accepts Selection.to_dict() (manifest) and string kwargs (`scrapy crawl showcase -a what=api_models`)."""
    d = dict(d or {})
    return build(**{k: d[k] for k in ("what", "lang", "explore_sources", "explore_sort", "explore_pages",
                                       "explore_categories", "effects", "with_profiles", "reels_sources")
                       if k in d})


def default_label(sel: Selection) -> str:
    ws = sel.resolve()
    if sel.what is None:
        return "public"
    if set(ws) == set(WHATS):
        return "all"
    return "-".join(ws) if len(ws) <= 2 else f"{len(ws)}sources"
