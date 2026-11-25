import os
from pathlib import Path

import pytest

from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.selection import Selection

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: hits the real Higgsfield API (set HF_LIVE=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("HF_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test; set HF_LIVE=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def env():
    def load(name: str) -> Envelope:
        return Envelope.load(FIXTURES / name)
    return load


@pytest.fixture
def sel():
    return Selection.build(sections="all", plan_sets="ps_a3,default")


@pytest.fixture
def fixtures_dir():
    return FIXTURES
