"""CLI options + Selection for the catalog scraper."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

from .endpoints import AUX_KINDS, DEFAULT_PUBLIC, KIND_OF, KINDS, LOGIN_ONLY, PUBLIC, SHORT_OF

LOGIN_MODES = ("auto", "yes", "no")


def add_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("catalog: what to scrape")
    g.add_argument("--kinds", default=None,
                   help="comma list of catalog kinds (short names like motion,voice or catalog_motion), or "
                        "'public' (default), 'login', 'all'. Available: " + ", ".join(KINDS))
    g.add_argument("--with-samples", action="store_true",
                   help="also fetch the sample videos of every motion (1 request per motion, ~419; "
                        "--max-pages caps the number of sample requests)")
    g.add_argument("--with-details", action="store_true",
                   help="also fetch /motions/{id} per motion (adds description + real preview media for the "
                        "kling/minimax/seedance/wan families; ~419 requests; --max-pages caps them)")
    g.add_argument("--lang", default="en", help="language for viral-hub, soul styles, mixed media, katana (default: en)")
    g.add_argument("--include-login-only", default="auto", choices=LOGIN_MODES,
                   help="login-only catalogs: auto = when a session is configured (default), yes = always "
                        "(skipped cleanly without a session), no = never")
    g.add_argument("--keep-placeholders", action="store_true",
                   help="keep the base64 blur placeholders (data: URIs) found in media objects (large)")


@dataclass
class Selection:
    kinds: Optional[list[str]] = None          # explicit short names; None = default (public [+ login-only])
    with_samples: bool = False
    with_details: bool = False
    lang: str = "en"
    include_login_only: str = "auto"
    keep_placeholders: bool = False
    has_session: bool = False                  # informational (from CLI); the spider decides with its own provider

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------ kinds
    def resolve_kinds(self, authed: bool) -> list[str]:
        """Short kind names to fetch in this run."""
        if self.kinds is not None:
            ks = list(self.kinds)
            if self.include_login_only == "no":
                ks = [k for k in ks if k not in LOGIN_ONLY]
        else:
            ks = list(DEFAULT_PUBLIC)
            if self.include_login_only == "yes" or (self.include_login_only == "auto" and authed):
                ks += list(LOGIN_ONLY)
        if self.with_samples and "motion_sample" not in ks:
            ks.append("motion_sample")
        return [k for k in KINDS if k in ks]       # canonical order

    @property
    def samples(self) -> bool:
        return self.with_samples or bool(self.kinds and "motion_sample" in self.kinds)

    def output_kinds(self) -> Optional[set[str]]:
        """Entity kinds kept in the output; None = keep everything that was fetched."""
        if self.kinds is None:
            base = None if self.samples else {KIND_OF[k] for k in KINDS if k != "motion_sample"}
        else:
            base = {KIND_OF[k] for k in self.kinds}
            if self.samples:
                base.add(KIND_OF["motion_sample"])
        return None if base is None else base | set(AUX_KINDS)


def parse_kinds(value: Any) -> Optional[list[str]]:
    if value in (None, "", "public"):
        return None if value != "public" else list(DEFAULT_PUBLIC)
    items: Iterable[str] = value if isinstance(value, (list, tuple)) else str(value).split(",")
    out: list[str] = []
    for raw in items:
        k = raw.strip().lower().replace("-", "_")
        if not k:
            continue
        if k == "all":
            out += list(KINDS)
        elif k == "public":
            out += list(PUBLIC)
        elif k in ("login", "login_only"):
            out += list(LOGIN_ONLY)
        elif k in KINDS:
            out.append(k)
        elif k in SHORT_OF:
            out.append(SHORT_OF[k])
        elif k.rstrip("s") in KINDS:                      # plural convenience: motions, voices
            out.append(k.rstrip("s"))
        else:
            raise ValueError(f"unknown catalog kind {raw!r}; available: {', '.join(KINDS)}")
    return list(dict.fromkeys(out))


def _truthy(v: Any) -> bool:
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def build(kinds: Any = None, with_samples: Any = False, with_details: Any = False, lang: Any = "en",
          include_login_only: Any = "auto", keep_placeholders: Any = False, has_session: Any = False) -> Selection:
    mode = str(include_login_only or "auto").lower()
    if mode in ("true", "1"):
        mode = "yes"
    if mode in ("false", "0"):
        mode = "no"
    if mode not in LOGIN_MODES:
        raise ValueError(f"include_login_only must be one of {LOGIN_MODES}")
    return Selection(kinds=parse_kinds(kinds), with_samples=_truthy(with_samples), with_details=_truthy(with_details),
                     lang=str(lang or "en"), include_login_only=mode, keep_placeholders=_truthy(keep_placeholders),
                     has_session=_truthy(has_session))


def make_selection(a: argparse.Namespace) -> Selection:
    import os
    has_session = bool(getattr(a, "token", None) or os.environ.get("HF_TOKEN") or os.environ.get("HF_CLERK_CLIENT"))
    if not has_session:
        try:
            from ...core.auth_login import load_cached_client
            has_session = bool((load_cached_client() or {}).get("client_cookie"))
        except Exception:
            has_session = False
    return build(kinds=a.kinds, with_samples=a.with_samples, with_details=a.with_details, lang=a.lang,
                 include_login_only=a.include_login_only, keep_placeholders=a.keep_placeholders,
                 has_session=has_session)


def selection_from_dict(d: Optional[dict]) -> Selection:
    """Accepts Selection.to_dict() (manifest) and string kwargs (`scrapy crawl catalog -a kinds=motion,voice`)."""
    d = dict(d or {})
    return build(**{k: d[k] for k in ("kinds", "with_samples", "with_details", "lang", "include_login_only",
                                       "keep_placeholders", "has_session") if k in d})


def default_label(sel: Selection) -> str:
    if sel.kinds is None:
        base = "public"
    elif set(sel.kinds) == set(KINDS):
        base = "all"
    elif len(sel.kinds) <= 3:
        base = "-".join(sel.kinds)
    else:
        base = f"{len(sel.kinds)}kinds"
    return base + ("-samples" if sel.samples else "") + ("-details" if sel.with_details else "")
