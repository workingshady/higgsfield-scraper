"""CLI options + Selection for the models scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from .endpoints import DEFAULT_MAX_CHUNKS, DEFAULT_PAGES, PAGE_PATH_RE


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("models: what to read")
    g.add_argument("--pages", default=",".join(DEFAULT_PAGES),
                   help="comma list of tool pages whose JS bundle is crawled (default: %(default)s)")
    g.add_argument("--max-chunks", type=int, default=DEFAULT_MAX_CHUNKS,
                   help="max JS chunks fetched (default %(default)s; 0 = no cap). Preloaded chunks of the pages "
                        "come first, then imports of chunks holding model data, then everything else; ~540 "
                        "reach the whole registry")
    g.add_argument("--no-costs", dest="with_costs", action="store_false", default=True,
                   help="skip /job-sets/costs (in_costs, costs version)")
    g.add_argument("--no-shots", dest="with_shots", action="store_false", default=True,
                   help="skip the Shots feed facet (available_models -> shot_facets, in_shots)")


@dataclass
class Selection:
    pages: list[str] = field(default_factory=lambda: list(DEFAULT_PAGES))
    max_chunks: int = DEFAULT_MAX_CHUNKS
    with_costs: bool = True
    with_shots: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _list(v: Any) -> list[str]:
    items: Iterable[Any] = v if isinstance(v, (list, tuple)) else str(v).split(",")
    return [str(x).strip() for x in items if x is not None and str(x).strip()]


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "on")


def build(pages: Any = None, max_chunks: Any = DEFAULT_MAX_CHUNKS, with_costs: Any = True,
          with_shots: Any = True) -> Selection:
    ps = _list(pages) if pages not in (None, "") else list(DEFAULT_PAGES)
    ps = ["/" + p.lstrip("/") for p in ps]
    bad = [p for p in ps if not PAGE_PATH_RE.match(p)]
    if bad:
        raise ValueError(f"invalid page path(s) {bad}: use site paths like /ai/video")
    mc = int(max_chunks if max_chunks not in (None, "") else DEFAULT_MAX_CHUNKS)
    if mc < 0:
        raise ValueError("max_chunks must be >= 0 (0 = no cap)")
    return Selection(pages=list(dict.fromkeys(ps)), max_chunks=mc, with_costs=_truthy(with_costs),
                     with_shots=_truthy(with_shots))


def make_selection(a: argparse.Namespace) -> Selection:
    return build(pages=a.pages, max_chunks=a.max_chunks, with_costs=a.with_costs, with_shots=a.with_shots)


def selection_from_dict(d: Optional[dict]) -> Selection:
    d = dict(d or {})
    return build(**{k: d[k] for k in ("pages", "max_chunks", "with_costs", "with_shots") if k in d})


def default_label(sel: Selection) -> str:
    return "registry" if sel.pages == list(DEFAULT_PAGES) else f"registry-{len(sel.pages)}pages"
