"""CLI flags and the Selection object of the projects scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

from . import endpoints as ep


def _csv(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        items = [str(x) for x in v]
    else:
        items = str(v).split(",")
    return [x.strip() for x in items if x and x.strip()]


def _truthy(v: Any) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def _choose(values: Iterable[str], allowed: Iterable[str], what: str, all_value: tuple[str, ...]) -> tuple[str, ...]:
    vals = list(values)
    allowed = tuple(allowed)
    if not vals or "all" in vals:
        return all_value
    bad = [v for v in vals if v not in allowed]
    if bad:
        raise ValueError(f"unknown {what}: {bad}; choose from {list(allowed)} or 'all'")
    return tuple(dict.fromkeys(vals))


@dataclass
class Selection:
    what: tuple[str, ...] = ep.WHAT
    categories: tuple[str, ...] = ()                 # publication category slugs (server-side filter); () = unfiltered
    featured: bool = False                           # /project-publications?featured=true
    scopes: tuple[str, ...] = ep.RECOMMENDED_SCOPES  # recommended feed scopes
    with_details: bool = False
    with_submissions: bool = False
    contest_status: str = "all"                      # open | closed | all
    contest_types: tuple[str, ...] = ep.CONTEST_TYPES
    entry_keys: tuple[str, ...] = ep.ENTRY_CONTEST_KEYS
    entry_tab: str = "latest"
    submission_ordering: str = "newest"
    max_submissions: Optional[int] = None           # per contest
    with_profiles: bool = False                      # opt-in: usernames, names, avatars, handles, profile URLs
    public_series: bool = False                      # opt-in: series from the public fnf-series service (no login)

    def __post_init__(self) -> None:
        self.what = tuple(self.what)
        self.categories = tuple(self.categories)
        self.scopes = tuple(self.scopes)
        self.contest_types = tuple(self.contest_types)
        self.entry_keys = tuple(self.entry_keys)
        if self.contest_status not in ep.CONTEST_STATUS_GROUPS:
            raise ValueError(f"--contest-status must be one of {list(ep.CONTEST_STATUS_GROUPS)}")
        if self.entry_tab not in ep.ENTRY_TABS:
            raise ValueError(f"--entry-tab must be one of {list(ep.ENTRY_TABS)}")
        if self.submission_ordering not in ep.SUBMISSION_ORDERINGS:
            raise ValueError(f"--submission-ordering must be one of {list(ep.SUBMISSION_ORDERINGS)}")

    @property
    def statuses(self) -> tuple[str, ...]:
        return ep.CONTEST_STATUS_GROUPS[self.contest_status]

    def wants(self, part: str) -> bool:
        return part in self.what

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not d["public_series"]:              # added later: omitted at its default so default meta.options is unchanged
            del d["public_series"]
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}

    @classmethod
    def build(cls, *, what: Any = None, categories: Any = None, featured: Any = False, scope: Any = None,
              with_details: Any = False, with_submissions: Any = False, contest_status: Any = "all",
              contest_types: Any = None, entry_keys: Any = None, entry_tab: Any = "latest",
              submission_ordering: Any = "newest", max_submissions: Any = None, with_profiles: Any = False,
              public_series: Any = False) -> "Selection":
        ms = None if max_submissions in (None, "", "None") else int(max_submissions)
        return cls(
            what=_choose(_csv(what), ep.WHAT, "--what", ep.WHAT),
            categories=tuple(_csv(categories)),
            featured=_truthy(featured),
            scopes=_choose(_csv(scope), ep.RECOMMENDED_SCOPES, "--scope", ep.RECOMMENDED_SCOPES),
            with_details=_truthy(with_details),
            with_submissions=_truthy(with_submissions),
            contest_status=str(contest_status or "all"),
            contest_types=_choose(_csv(contest_types), ep.CONTEST_TYPES, "--contest-types", ep.CONTEST_TYPES),
            entry_keys=_choose(_csv(entry_keys), ep.ENTRY_CONTEST_KEYS, "--entry-keys", ep.ENTRY_CONTEST_KEYS),
            entry_tab=str(entry_tab or "latest"),
            submission_ordering=str(submission_ordering or "newest"),
            max_submissions=ms,
            with_profiles=_truthy(with_profiles),
            public_series=_truthy(public_series),
        )


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("projects: what to scrape")
    g.add_argument("--what", default="all",
                   help=f"comma list of {list(ep.WHAT)} or 'all' (default). 'series' needs a login session "
                        "unless --public-series")
    g.add_argument("--categories", default=None,
                   help="publication category slugs (server-side filter), e.g. spotlight,open-sourced-by-higgsfield")
    g.add_argument("--featured", action="store_true", help="publications listing: only featured (featured=true)")
    g.add_argument("--scope", default="all",
                   help=f"recommended feed scopes: {list(ep.RECOMMENDED_SCOPES)} or 'all' (default)")
    g.add_argument("--with-details", action="store_true",
                   help="fetch each publication's / contest's detail endpoint (stats, rules, rewards, prizes, winners…)")
    g.add_argument("--with-submissions", action="store_true", help="fetch every contest's submissions (paginated)")
    g.add_argument("--contest-status", choices=list(ep.CONTEST_STATUS_GROUPS), default="all",
                   help="open (created/open/shortlist/judge) | closed (finished) | all (default)")
    g.add_argument("--contest-types", default="all", help="global,weekly or 'all' (default)")
    g.add_argument("--entry-keys", default="all",
                   help=f"contest entries (contest-participations) for {list(ep.ENTRY_CONTEST_KEYS)} or 'all'")
    g.add_argument("--entry-tab", choices=list(ep.ENTRY_TABS), default="latest",
                   help="ordering/tab of the contest-entries listing (default latest = every entry)")
    g.add_argument("--submission-ordering", choices=list(ep.SUBMISSION_ORDERINGS), default="newest")
    g.add_argument("--max-submissions", type=int, default=None, help="cap submissions per contest (default: all)")
    g.add_argument("--public-series", action="store_true",
                   help="series: use the public fnf-series service (no login; 35 series, --with-details adds "
                        "/series/{slug}; --max-items caps the series). Without it series keep the legacy "
                        "login-only fnf path (skipped without a session)")
    o = p.add_argument_group("projects: personal data")
    o.add_argument("--with-profiles", action="store_true",
                   help="opt-in: include authors'/contestants' usernames, names, avatars, headlines, locations, "
                        "judge links and profile-based page URLs (default: pseudonymous author keys only)")


def make_selection(a: argparse.Namespace) -> Selection:
    return Selection.build(what=a.what, categories=a.categories, featured=a.featured, scope=a.scope,
                           with_details=a.with_details, with_submissions=a.with_submissions,
                           contest_status=a.contest_status, contest_types=a.contest_types, entry_keys=a.entry_keys,
                           entry_tab=a.entry_tab, submission_ordering=a.submission_ordering,
                           max_submissions=a.max_submissions, with_profiles=a.with_profiles,
                           public_series=getattr(a, "public_series", False))


def selection_from_dict(d: dict) -> Selection:
    """Accepts Selection.to_dict() (manifest) or `scrapy crawl projects -a key=value` strings."""
    d = dict(d or {})
    return Selection.build(
        what=d.get("what"), categories=d.get("categories"), featured=d.get("featured", False),
        scope=d.get("scopes", d.get("scope")), with_details=d.get("with_details", False),
        with_submissions=d.get("with_submissions", False), contest_status=d.get("contest_status", "all"),
        contest_types=d.get("contest_types"), entry_keys=d.get("entry_keys"), entry_tab=d.get("entry_tab", "latest"),
        submission_ordering=d.get("submission_ordering", "newest"), max_submissions=d.get("max_submissions"),
        with_profiles=d.get("with_profiles", False), public_series=d.get("public_series", False))


def default_label(sel: Selection) -> str:
    return "all" if set(sel.what) == set(ep.WHAT) else "-".join(sel.what)
