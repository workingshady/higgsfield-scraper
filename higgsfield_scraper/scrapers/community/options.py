"""Community scraper options: CLI flags, the Selection dataclass, and parsing from CLI args / manifest / `-a k=v`."""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from ...estimate import DEFAULT_ESTIMATE_VERSION, ESTIMATE_VERSIONS
from .endpoints import ESTIMATE_MODES, EXTRA_FEEDS, FEEDS, KNOWN_MODELS, TYPES

log = logging.getLogger(__name__)

FEED_ALIASES = {"model_x": "model-x", "modelx": "model-x", "trending_top": "top", "trending-top": "top",
                "music_cards": "music-cards", "job_showcase": "job-showcase", "showcase-jobs": "job-showcase",
                "explore_cards": "explore-cards", "collection": "collections"}


def _split(value: Any) -> list[str]:
    """'a,b' | ['a,b', 'c'] | None -> ['a', 'b', 'c'] (order kept, duplicates removed)."""
    if value is None:
        return []
    items: Iterable[Any] = value if isinstance(value, (list, tuple)) else [value]
    out = [p.strip() for v in items for p in str(v).split(",") if p.strip()]
    return list(dict.fromkeys(out))


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Selection:
    feeds: list[str] = field(default_factory=lambda: ["trending"])
    type: str = "all"
    models: list[str] = field(default_factory=list)
    preset_ids: list[str] = field(default_factory=list)
    resolution: Optional[str] = None
    publication_ids: list[str] = field(default_factory=list)
    with_profiles: bool = False
    with_raw_params: bool = False
    estimate_cost: str = "off"
    usd_reference: str = "plus:annual"
    usd_plan_set: str = "ps_a3"
    detail: bool = False
    with_comments: bool = False
    estimate_version: int = DEFAULT_ESTIMATE_VERSION   # 1 = default estimator; 2 = JS formulas (estimate/v2.py)
    # opt-in Community pages (shots, posts, feed, creators, talents): given through --feeds, kept apart from the
    # gallery feeds so 'all' and every default stay unchanged
    extra_feeds: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        feeds = [FEED_ALIASES.get(f.lower(), f.lower()) for f in _split(self.feeds)]
        extra = [f for f in feeds if f in EXTRA_FEEDS]
        feeds = [f for f in feeds if f not in EXTRA_FEEDS]
        extra += [f.lower() for f in _split(self.extra_feeds) if f.lower() not in extra]
        bad_extra = [f for f in extra if f not in EXTRA_FEEDS]
        if bad_extra:
            raise ValueError(f"unknown feed(s) {bad_extra}; opt-in feeds are {list(EXTRA_FEEDS)}")
        self.extra_feeds = list(dict.fromkeys(extra))
        self.publication_ids = _split(self.publication_ids)
        if feeds == ["all"]:
            feeds = list(FEEDS)
        elif "all" in feeds:                       # e.g. 'all,shots' (the opt-in feeds were split off above)
            feeds = list(FEEDS) + [f for f in feeds if f not in FEEDS and f != "all"]
        if feeds == ["none"]:                      # only --publication-ids
            if not self.publication_ids and not self.extra_feeds:
                raise ValueError("--feeds none needs --publication-ids")
            feeds = []
        bad = [f for f in feeds if f not in FEEDS]
        if bad:
            raise ValueError(f"unknown feed(s) {bad}; choose from {list(FEEDS)}, 'all', or the opt-in "
                             f"{list(EXTRA_FEEDS)}")
        self.feeds = feeds if (feeds or self.publication_ids or self.extra_feeds) else ["trending"]
        self.type = (self.type or "all").lower()
        if self.type not in TYPES:
            raise ValueError(f"--type must be one of {list(TYPES)}")
        self.estimate_cost = (self.estimate_cost or "off").lower()
        if self.estimate_cost not in ESTIMATE_MODES:
            raise ValueError(f"--estimate-cost must be one of {list(ESTIMATE_MODES)}")
        self.models = _split(self.models)
        self.preset_ids = _split(self.preset_ids)
        try:
            self.estimate_version = int(self.estimate_version)
        except (TypeError, ValueError):
            raise ValueError(f"--estimate-version must be one of {list(ESTIMATE_VERSIONS)}") from None
        if self.estimate_version not in ESTIMATE_VERSIONS:
            raise ValueError(f"--estimate-version must be one of {list(ESTIMATE_VERSIONS)}")
        if ":" not in (self.usd_reference or ""):
            raise ValueError("--usd-reference must look like plan_type:billing_period, e.g. plus:annual")

    # ---------------------------------------------------------------- helpers
    @property
    def estimating(self) -> bool:
        return self.estimate_cost != "off"

    def estimate_for(self, media_type: Optional[str]) -> bool:
        return self.estimate_cost == "all" or (self.estimate_cost == "images" and media_type == "image") or \
            (self.estimate_cost == "videos" and media_type == "video")

    def unknown_models(self) -> list[str]:
        return [m for m in self.models if m not in KNOWN_MODELS]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["estimate_version"] == DEFAULT_ESTIMATE_VERSION:   # default runs keep the pre-option manifest/meta
            d.pop("estimate_version")
        if not d["extra_feeds"]:                                # same for the opt-in Community pages
            d.pop("extra_feeds")
        return d

    def wants(self, extra_feed: str) -> bool:
        return extra_feed in self.extra_feeds


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("community: what to scrape")
    g.add_argument("--feeds", default="trending",
                   help="comma list of feeds: trending (main feed, ~78.6k), approved (curated, ~6.7k, mostly video), "
                        "top (single page, <=100), model-x (featured model showcase), 'all', or 'none' (only --publication-ids) "
                        "(default: %(default)s). Opt-in Community pages, never part of 'all': shots (/community/"
                        "generations, fnf-community generations feed), posts (Community posts, ~24k), feed (the "
                        "/community/feed mix of shots, projects, blogs and posts), creators (/community/creators, "
                        "~650, aggregate stats; names only with --with-profiles), talents (Talents hub, ~80), music-cards "
                        "(Music Cards templates: lyrics, recipients, preview videos, ~111 + option lists), "
                        "job-showcase (Seedance 2 community 'movies': 54 jobs with prompt, inputs, all result "
                        "variants), collections (motion collection Catch the Pulse), explore-cards (explore/home "
                        "cards, ~192). --max-items caps each opt-in feed separately")
    g.add_argument("--type", default="all", choices=TYPES,
                   help="media type filter (API `type`). image|video are also enforced client-side because the "
                        "approved feed ignores it; speak|upscale are server-side only (default: %(default)s)")
    g.add_argument("--models", action="append", default=None, metavar="JOB_SET_TYPES",
                   help="job_set_type filter, comma list and/or repeatable, e.g. --models seedance_2_5,nano_banana_2 "
                        "(API `model`, trending/approved; enforced client-side for top/model-x)")
    g.add_argument("--preset-ids", action="append", default=None, metavar="IDS",
                   help="preset/motion id filter (API `preset_id`, repeatable). Passed through; server effect unverified")
    g.add_argument("--resolution", default=None,
                   help="API `resolution` filter (passed through; the trending feed ignores it, approved returned 0 "
                        "items for 720p in tests — use with care)")
    g.add_argument("--publication-ids", action="append", default=None, metavar="IDS",
                   help="also fetch these publications by id (GET /publications/{id}); their feed is 'detail'")
    d = p.add_argument_group("community: extra data (opt-in)")
    d.add_argument("--with-profiles", action="store_true",
                   help="PERSONAL DATA: include creators' username, avatar, social handles and badges (creators table). "
                        "Default: only the pseudonymous user_id")
    d.add_argument("--with-raw-params", action="store_true",
                   help="keep each generation's untouched `params` dict (raw_params) next to the normalized fields")
    d.add_argument("--detail", action="store_true",
                   help="fetch GET /publications/{id} for every listed item and use that (1 extra request per item)")
    d.add_argument("--with-comments", action="store_true",
                   help="fetch comments (+ replies) from the Community posts service (fnf-community): reads the "
                        "posts feed (limit = --max-items, max 50) and the threads of posts that have comments. "
                        "With the opt-in feeds shots/feed/posts it instead reads the comment threads of those items "
                        "(fnf-community /entities/{type}/{id}/comments for shots, projects and blogs). "
                        "Public; commenter identities only with --with-profiles")
    c = p.add_argument_group("community: cost estimate (optional)")
    c.add_argument("--estimate-cost", default="off", choices=ESTIMATE_MODES,
                   help="attach an estimated credit cost per generation from /job-sets/costs: off (default) | images | "
                        "videos | all. An estimate, not what the creator actually paid")
    c.add_argument("--usd-reference", default="plus:annual",
                   help="plan_type:billing_period whose after-offer $/credit converts credits to USD (default: %(default)s)")
    c.add_argument("--usd-plan-set", default="ps_a3",
                   help="plan_set_key used for the USD reference plan (default: %(default)s)")
    c.add_argument("--estimate-version", type=int, default=DEFAULT_ESTIMATE_VERSION, choices=ESTIMATE_VERSIONS,
                   help="cost formulas used by --estimate-cost: 1 (default, unchanged) or 2 (matches the web app's JS "
                        "formulas, docs/COST_FORMULAS.md §8; v2 estimates carry formula_version: 2)")


def make_selection(a: argparse.Namespace) -> Selection:
    sel = Selection(feeds=a.feeds, type=a.type, models=a.models, preset_ids=a.preset_ids, resolution=a.resolution,
                    publication_ids=a.publication_ids, with_profiles=a.with_profiles,
                    with_raw_params=a.with_raw_params, estimate_cost=a.estimate_cost, usd_reference=a.usd_reference,
                    usd_plan_set=a.usd_plan_set, detail=a.detail, with_comments=a.with_comments,
                    estimate_version=getattr(a, "estimate_version", DEFAULT_ESTIMATE_VERSION))
    unknown = sel.unknown_models()
    if unknown:
        print(f"warning: --models {unknown} are not in the known job_set_type list; the API may answer 422",
              file=sys.stderr)
    return sel


def selection_from_dict(d: Optional[dict]) -> Selection:
    """Accepts Selection.to_dict() (manifest) and string values (`scrapy crawl community -a feeds=approved`)."""
    d = dict(d or {})
    kw: dict[str, Any] = {}
    for k in ("feeds", "models", "preset_ids", "publication_ids", "extra_feeds"):
        if k in d:
            kw[k] = d[k]
    for k in ("type", "resolution", "estimate_cost", "usd_reference", "usd_plan_set"):
        if d.get(k) not in (None, ""):
            kw[k] = str(d[k])
    for k in ("with_profiles", "with_raw_params", "detail", "with_comments"):
        if k in d:
            kw[k] = _truthy(d[k])
    if d.get("estimate_version") not in (None, ""):
        kw["estimate_version"] = d["estimate_version"]
    return Selection(**kw)


def default_label(sel: Selection) -> str:
    parts = ["-".join(sel.feeds + sel.extra_feeds) or "detail"]
    if sel.type != "all":
        parts.append(sel.type)
    if sel.models:
        parts.append(sel.models[0] + (f"+{len(sel.models) - 1}" if len(sel.models) > 1 else ""))
    return "-".join(parts)
