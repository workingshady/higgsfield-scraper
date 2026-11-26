"""CLI flags and the Selection object of the projects scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

from ...core.dataset import make_id
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


def user_key(handle: str) -> str:
    """Pseudonymous stable key of a --users handle (16 hex); 'key:<hex>' (from a redacted manifest) passes through."""
    h = str(handle)
    return h[4:] if h.startswith("key:") else make_id("handle", h.lstrip("@"))


# accepted by --what but NOT part of 'all' (so `--what all` plans the same requests as before they existed):
# user-projects needs --users; trending (ranking + total, 2026-11-26) and contest-participation (counters + config,
# 2026-11-26) are opt-in. `--what all,trending` = all + trending.
WHAT_OPT_IN = ("trending", "contest-participation")
WHAT_EXTRA = ("user-projects",) + WHAT_OPT_IN
OPT_IN_KEYS = ("public_series", "with_project_assets", "with_project_brief", "with_project_stats",
               "with_project_comments", "with_project_related", "users", "contests", "contest_tabs",
               "with_user_works", "trending_sort", "trending_filter", "trending_with_contest")


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
    # ---- nested project data (opt-in; added 2026-11-26). Omitted from to_dict() at their defaults so the default
    # run's meta.options (and so its outputs) stay byte-identical.
    with_project_assets: bool = False                # folders + every asset (job/upload) with prompt, model, params, media
    with_project_brief: bool = False                 # the project brief (Lexical/Yjs snapshot -> Markdown)
    with_project_stats: bool = False                 # generations, credits spent, size, stack (model shares)
    with_project_comments: bool = False              # comments + replies (fnf-community)
    with_project_related: bool = False               # the "related projects" list of the project page
    users: tuple[str, ...] = ()                      # --users: handles whose public projects are listed (input only)
    contests: tuple[str, ...] = ()                   # --contest: contest slugs (fetched by slug instead of listed)
    contest_tabs: tuple[str, ...] = ()               # --contest-tabs: entry tabs of a --contest (default: --entry-tab)
    # ---- opt-in extras (added 2026-11-26; omitted from to_dict() at their defaults, like the nested flags)
    with_user_works: bool = False                    # works + stats of users already found in the run (by user id)
    trending_sort: Optional[str] = None              # --what trending: sort (None/'default' = not sent)
    trending_filter: Optional[str] = None            # --what trending: filter (None = not sent)
    trending_with_contest: bool = False              # --what trending: with_contest=true (ignored with a filter, as JS)

    def __post_init__(self) -> None:
        self.what = tuple(self.what)
        self.categories = tuple(self.categories)
        self.scopes = tuple(self.scopes)
        self.contest_types = tuple(self.contest_types)
        self.entry_keys = tuple(self.entry_keys)
        self.users = tuple(self.users)
        self.contests = tuple(self.contests)
        self.contest_tabs = tuple(self.contest_tabs)
        bad = [t for t in self.contest_tabs if t not in ep.CONTEST_TABS]
        if bad:
            raise ValueError(f"--contest-tabs: unknown {bad}; choose from {list(ep.CONTEST_TABS)} or 'all'")
        if "user-projects" in self.what and not self.users:
            raise ValueError("--what user-projects needs --users <handle>[,handle]")
        if self.users and "user-projects" not in self.what:
            self.what = self.what + ("user-projects",)
        if self.contest_status not in ep.CONTEST_STATUS_GROUPS:
            raise ValueError(f"--contest-status must be one of {list(ep.CONTEST_STATUS_GROUPS)}")
        if self.entry_tab not in ep.ENTRY_TABS:
            raise ValueError(f"--entry-tab must be one of {list(ep.ENTRY_TABS)}")
        if self.submission_ordering not in ep.SUBMISSION_ORDERINGS:
            raise ValueError(f"--submission-ordering must be one of {list(ep.SUBMISSION_ORDERINGS)}")
        if self.trending_sort == "default":
            self.trending_sort = None
        if self.trending_sort is not None and self.trending_sort not in ep.TRENDING_SORTS:
            raise ValueError(f"--trending-sort must be one of {list(ep.TRENDING_SORTS)}")
        if self.trending_filter is not None and self.trending_filter not in ep.TRENDING_FILTERS:
            raise ValueError(f"--trending-filter must be one of {list(ep.TRENDING_FILTERS)}")

    @property
    def extras(self) -> bool:
        """Any opt-in extra collection requested (trending, contest participation, user works)."""
        return self.wants("trending") or self.wants("contest-participation") or self.with_user_works

    @property
    def statuses(self) -> tuple[str, ...]:
        return ep.CONTEST_STATUS_GROUPS[self.contest_status]

    def wants(self, part: str) -> bool:
        return part in self.what

    @property
    def nested(self) -> bool:
        """Any per-project nested data requested (each needs the publication detail first)."""
        return (self.with_project_assets or self.with_project_brief or self.with_project_stats
                or self.with_project_comments or self.with_project_related)

    @property
    def tabs_for_contest(self) -> tuple[str, ...]:
        return self.contest_tabs or (self.entry_tab,)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in OPT_IN_KEYS:                   # added later: omitted at their default so default meta.options is unchanged
            if not d[k]:
                del d[k]
        if d.get("users") and not self.with_profiles:   # handles are inputs: the dataset keeps pseudonymous keys
            d["users"] = [f"key:{user_key(u)}" for u in self.users]
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}

    @classmethod
    def build(cls, *, what: Any = None, categories: Any = None, featured: Any = False, scope: Any = None,
              with_details: Any = False, with_submissions: Any = False, contest_status: Any = "all",
              contest_types: Any = None, entry_keys: Any = None, entry_tab: Any = "latest",
              submission_ordering: Any = "newest", max_submissions: Any = None, with_profiles: Any = False,
              public_series: Any = False, with_project_assets: Any = False, with_project_brief: Any = False,
              with_project_stats: Any = False, with_project_comments: Any = False, with_project_related: Any = False,
              users: Any = None, contests: Any = None, contest_tabs: Any = None, with_user_works: Any = False,
              trending_sort: Any = None, trending_filter: Any = None,
              trending_with_contest: Any = False) -> "Selection":
        ms = None if max_submissions in (None, "", "None") else int(max_submissions)
        tabs = _csv(contest_tabs)
        whats = _csv(what)
        chosen = _choose(whats, ep.WHAT + WHAT_EXTRA, "--what", ep.WHAT)
        if "all" in whats:                         # 'all' = the default parts; opt-in parts listed with it are kept
            chosen = chosen + tuple(w for w in dict.fromkeys(whats) if w in WHAT_OPT_IN)
        return cls(
            what=chosen,
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
            with_project_assets=_truthy(with_project_assets),
            with_project_brief=_truthy(with_project_brief),
            with_project_stats=_truthy(with_project_stats),
            with_project_comments=_truthy(with_project_comments),
            with_project_related=_truthy(with_project_related),
            users=tuple(dict.fromkeys(u.lstrip("@") for u in _csv(users))),
            contests=tuple(dict.fromkeys(_csv(contests))),
            contest_tabs=ep.CONTEST_TABS if "all" in tabs else tuple(dict.fromkeys(tabs)),
            with_user_works=_truthy(with_user_works),
            trending_sort=None if trending_sort in (None, "", "None") else str(trending_sort),
            trending_filter=None if trending_filter in (None, "", "None") else str(trending_filter),
            trending_with_contest=_truthy(trending_with_contest),
        )


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("projects: what to scrape")
    g.add_argument("--what", default="all",
                   help=f"comma list of {list(ep.WHAT)} or 'all' (default). 'series' needs a login session "
                        f"unless --public-series. Opt-in (not in 'all'): {list(WHAT_OPT_IN)}")
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
    n = p.add_argument_group("projects: nested project data (opt-in; each fetches the publication detail first)")
    n.add_argument("--with-project-assets", action="store_true",
                   help="folders (+ counts) and every asset of each project: prompt (only when the author enabled "
                        "show_prompts), model/job_set_type, params, media URLs/variants, folder, created_at")
    n.add_argument("--with-project-brief", action="store_true",
                   help="the project brief as Markdown (field + output/briefs/<slug>.md)")
    n.add_argument("--with-project-stats", action="store_true",
                   help="generations, credits spent, size and the model stack with the page's percentages")
    n.add_argument("--with-project-comments", action="store_true", help="comments and replies of each project")
    n.add_argument("--with-project-related", action="store_true", help="the page's related-projects list")
    n.add_argument("--users", default=None,
                   help="comma list of handles: list their public projects (adds 'user-projects' to --what). "
                        "Handles are inputs only; outputs stay pseudonymous unless --with-profiles")
    n.add_argument("--contest", dest="contests", default=None,
                   help="comma list of contest slugs (e.g. talent-contest,wcc-the-place-you-know): fetch these "
                        "contests by slug instead of listing all contests")
    n.add_argument("--contest-tabs", default=None,
                   help=f"entry tabs of a --contest that has an entries listing (talent-contest, festival): "
                        f"{list(ep.CONTEST_TABS)} or 'all' (default: --entry-tab). Needs --with-submissions")
    x = p.add_argument_group("projects: opt-in extras (not part of the default run or of --what all)")
    x.add_argument("--trending-sort", default=None, choices=list(ep.TRENDING_SORTS),
                   help="--what trending: ranking order (default: the site's default ranking; not sent)")
    x.add_argument("--trending-filter", default=None, choices=list(ep.TRENDING_FILTERS),
                   help="--what trending: filter (default: not sent = every project)")
    x.add_argument("--trending-with-contest", action="store_true",
                   help="--what trending: with_contest=true (ignored when --trending-filter is given, like the site)")
    x.add_argument("--with-user-works", action="store_true",
                   help="published works (generations with prompt/params/results, projects, folders, contest "
                        "submissions) + stats of users ALREADY found in this run (owners of --users projects, "
                        "contest entrants and submitters); never enumerates users. Pseudonymous (creator_uid_key) "
                        "unless --with-profiles")
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
                           public_series=getattr(a, "public_series", False),
                           **{k: getattr(a, k, None) for k in OPT_IN_KEYS if k != "public_series"})


def selection_from_dict(d: dict) -> Selection:
    """Accepts Selection.to_dict() (manifest) or `scrapy crawl projects -a key=value` strings."""
    d = dict(d or {})
    return Selection.build(
        what=d.get("what"), categories=d.get("categories"), featured=d.get("featured", False),
        scope=d.get("scopes", d.get("scope")), with_details=d.get("with_details", False),
        with_submissions=d.get("with_submissions", False), contest_status=d.get("contest_status", "all"),
        contest_types=d.get("contest_types"), entry_keys=d.get("entry_keys"), entry_tab=d.get("entry_tab", "latest"),
        submission_ordering=d.get("submission_ordering", "newest"), max_submissions=d.get("max_submissions"),
        with_profiles=d.get("with_profiles", False), public_series=d.get("public_series", False),
        **{k: d.get(k) for k in OPT_IN_KEYS if k != "public_series"})


def default_label(sel: Selection) -> str:
    return "all" if set(sel.what) == set(ep.WHAT) else "-".join(sel.what)
