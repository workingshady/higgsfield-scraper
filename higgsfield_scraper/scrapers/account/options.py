"""CLI flags and the Selection object of the account scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from typing import Any

from ...estimate import DEFAULT_ESTIMATE_VERSION, ESTIMATE_VERSIONS


def _csv(v: Any) -> list[str]:
    if v is None:
        return []
    items = [str(x) for x in v] if isinstance(v, (list, tuple)) else str(v).split(",")
    return [x.strip() for x in items if x and x.strip()]


def _truthy(v: Any) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


@dataclass
class Selection:
    with_jobs: bool = False            # /jobs/accessible (the user's own jobs + actual charged cost)
    compare_estimate: bool = False     # CostEstimator vs actual cost per job (needs with_jobs)
    with_prompts: bool = False         # store the user's OWN prompt text (default: only its length)
    job_types: tuple[str, ...] = ()    # server-side job_set_type filter for /jobs/accessible
    with_profiles: bool = False        # always False: the core --with-profiles opt-in never applies to this scraper
    estimate_version: int = DEFAULT_ESTIMATE_VERSION   # estimator formulas for --compare-estimate (1 or 2)

    def __post_init__(self) -> None:
        self.job_types = tuple(self.job_types)
        try:
            self.estimate_version = int(self.estimate_version)
        except (TypeError, ValueError):
            raise ValueError(f"--estimate-version must be one of {list(ESTIMATE_VERSIONS)}") from None
        if self.estimate_version not in ESTIMATE_VERSIONS:
            raise ValueError(f"--estimate-version must be one of {list(ESTIMATE_VERSIONS)}")
        if self.estimate_version != DEFAULT_ESTIMATE_VERSION and not self.compare_estimate:
            raise ValueError("--estimate-version needs --compare-estimate")
        if self.compare_estimate and not self.with_jobs:
            raise ValueError("--compare-estimate needs --with-jobs")
        if self.job_types and not self.with_jobs:
            raise ValueError("--job-types needs --with-jobs")
        self.with_profiles = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("with_profiles", None)
        if d.get("estimate_version") == DEFAULT_ESTIMATE_VERSION:   # default runs keep the pre-option manifest/meta
            d.pop("estimate_version")
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}

    @classmethod
    def build(cls, *, with_jobs: Any = False, compare_estimate: Any = False, with_prompts: Any = False,
              job_types: Any = None, estimate_version: Any = None) -> "Selection":
        return cls(with_jobs=_truthy(with_jobs), compare_estimate=_truthy(compare_estimate),
                   with_prompts=_truthy(with_prompts), job_types=tuple(dict.fromkeys(_csv(job_types))),
                   estimate_version=DEFAULT_ESTIMATE_VERSION if estimate_version in (None, "") else estimate_version)


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("account: what to read (needs a login session; GET only)")
    g.add_argument("--with-jobs", action="store_true",
                   help="also read your own jobs from /jobs/accessible (paginated; --max-items / --max-pages apply): "
                        "job_set_type, status, created_at, pricing-relevant params and the actual credits charged")
    g.add_argument("--compare-estimate", action="store_true",
                   help="needs --with-jobs: run the CostEstimator on each job's params and compare it with the "
                        "credits actually charged (fetches the public /job-sets/costs etc.)")
    g.add_argument("--job-types", default=None,
                   help="needs --with-jobs: comma list of job_set_type values to request (server-side filter)")
    g.add_argument("--estimate-version", type=int, default=DEFAULT_ESTIMATE_VERSION, choices=ESTIMATE_VERSIONS,
                   help="needs --compare-estimate: estimator formulas, 1 (default, unchanged) or 2 (the web app's JS "
                        "formulas, docs/COST_FORMULAS.md §8)")
    o = p.add_argument_group("account: personal data")
    o.add_argument("--with-prompts", action="store_true",
                   help="opt-in: STORE YOUR OWN PROMPT TEXT (prompt, negative_prompt, text …) in the dataset and in "
                        "the raw/ and http/ archives. Default: prompts are replaced by their length only")


def make_selection(a: argparse.Namespace) -> Selection:
    return Selection.build(with_jobs=a.with_jobs, compare_estimate=a.compare_estimate, with_prompts=a.with_prompts,
                           job_types=a.job_types, estimate_version=getattr(a, "estimate_version", None))


def selection_from_dict(d: dict) -> Selection:
    """Accepts Selection.to_dict() (manifest) or `scrapy crawl account -a key=value` strings."""
    d = dict(d or {})
    return Selection.build(with_jobs=d.get("with_jobs", False), compare_estimate=d.get("compare_estimate", False),
                           with_prompts=d.get("with_prompts", False), job_types=d.get("job_types"),
                           estimate_version=d.get("estimate_version"))


def default_label(sel: Selection) -> str:
    if sel.compare_estimate:
        return "jobs-compare"
    return "jobs" if sel.with_jobs else "snapshot"
