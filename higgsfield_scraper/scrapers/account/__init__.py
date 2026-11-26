"""account scraper (OPT-IN, needs a login session): the logged-in user's own wallet / plan / subscription / free
gens / generation seconds / auto top-up snapshot, optionally their jobs with the credits actually charged, and an
estimate-vs-actual comparison that validates docs/COST_FORMULAS.md. Never part of a default run.
See docs/scrapers/account.md.
"""
from __future__ import annotations

from ...core.base import ScraperDef
from . import endpoints as ep
from .dataset import build_dataset, write_outputs
from .options import add_args, default_label, make_selection, selection_from_dict
from .parsers import keep, parse_envelope
from .schemas import ID_FIELD_BY_KIND, MODEL_BY_KIND, AccountDataset

SCRAPER = ScraperDef(
    name="account",
    description="OPT-IN, login required: your own balances/plan/subscription snapshot, your jobs with the credits "
                "actually charged (--with-jobs) and estimate-vs-actual checks (--compare-estimate)",
    spider_cls="higgsfield_scraper.scrapers.account.spider:AccountSpider",
    model_by_kind=MODEL_BY_KIND,
    id_field_by_kind=ID_FIELD_BY_KIND,
    add_args=add_args,
    make_selection=make_selection,
    selection_from_dict=selection_from_dict,
    parse_envelope=parse_envelope,
    keep=keep,
    build_dataset=build_dataset,
    write_outputs=write_outputs,
    default_label=default_label,
    optional_endpoints=ep.OPTIONAL,
    personal_data=True,               # core redaction on top of the account whitelist (redaction.py)
    media_urls=None,                  # never downloads the user's media
    dataset_model=AccountDataset,
    examples=(
        "python -m higgsfield_scraper scrape account",
        "python -m higgsfield_scraper scrape account --with-jobs --max-items 100",
        "python -m higgsfield_scraper scrape account --with-jobs --compare-estimate --max-items 20",
    ),
)
