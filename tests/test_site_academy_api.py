"""site --what academy-api (opt-in): the fnf-academy JSON API (categories, courses + free_generations / test_count,
lessons with MDX source). Not in the default nor in `all`; runs without it keep SiteDataset unchanged.
Fixtures: tests/fixtures/site_academy_api/ (live 2026-11-26 raw archive, trimmed; author names already redacted
by the archive privacy rule)."""
from __future__ import annotations

import csv
from pathlib import Path

from higgsfield_scraper.core.base import CommonOptions, RunMeta
from higgsfield_scraper.raw import Envelope
from higgsfield_scraper.scrapers.site import SCRAPER
from higgsfield_scraper.scrapers.site.endpoints import DEFAULT_WHAT, WHAT
from higgsfield_scraper.scrapers.site.options import Selection, default_label
from higgsfield_scraper.scrapers.site.parsers import keep, parse_envelope
from higgsfield_scraper.validation import validate_entity

FX = Path(__file__).parent / "fixtures" / "site_academy_api"


def env(prefix: str) -> Envelope:
    return Envelope.load(next(p for p in sorted(FX.glob(prefix + "*"))))


def spider(sel: Selection, **common):
    from higgsfield_scraper.scrapers.site.spider import SiteSpider
    return SiteSpider(selection=sel, common=CommonOptions(auth="off", **common))


def ents(sel: Selection) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for p in sorted(FX.glob("*.json")):
        for e in parse_envelope(Envelope.load(p), sel):
            if keep(e, sel):
                v = validate_entity(e)
                out.setdefault(v["kind"], []).append(v)
    return out


def test_option_is_opt_in_and_not_in_all():
    assert "academy-api" in WHAT and "academy-api" not in DEFAULT_WHAT
    assert Selection().what == list(DEFAULT_WHAT) and Selection(what="all").what == list(DEFAULT_WHAT)
    assert Selection(what="academy_api").what == ["academy-api"] and Selection(what="academy-json").academy_api
    assert Selection(what="all,academy-api").what == list(DEFAULT_WHAT) + ["academy-api"]
    assert default_label(Selection(what="academy-api")) == "academy-api"
    assert not any("fnf-academy" in r.url for r in spider(Selection(what="all")).build_requests())


def test_first_requests_and_follow_ups():
    sp = spider(Selection(what="academy-api"), max_items=2)
    first = list(sp.build_requests())
    assert [r.url for r in first] == ["https://fnf-api-gw.higgsfield.ai/fnf-academy/api/v1/categories",
                                      "https://fnf-api-gw.higgsfield.ai/fnf-academy/api/v1/courses"]
    assert all(r.method == "GET" and not r.meta["auth"] for r in first)
    courses = list(sp.follow_up(env("academy_api_courses"), [], None))
    assert [r.url.rsplit("/", 1)[-1] for r in courses] == ["blockbuster-4k", "santiago-cinematic"]   # max_items=2
    assert any("academy_api_course" in x for x in sp.limits_hit)
    lessons = list(sp.follow_up(env("academy_api_course__"), [], None))
    assert len(lessons) == 2 and lessons[0].url.startswith("https://fnf-api-gw.higgsfield.ai/fnf-academy/api/v1/lessons/")
    p = lessons[0].meta["params"]
    assert p["course_slug"] == "blockbuster-4k" and p["position"] == "1" and p["lesson_id"]
    none = spider(Selection(what="academy-api", with_content=False))
    list(none.build_requests())
    assert list(none.follow_up(env("academy_api_courses"), [], None)) == []
    only = spider(Selection(what="academy-api", only="santiago"))
    list(only.build_requests())
    assert [r.url.rsplit("/", 1)[-1] for r in only.follow_up(env("academy_api_courses"), [], None)] == \
        ["santiago-cinematic"]


def test_parsers():
    e = ents(Selection(what="academy-api"))
    assert {k: len(v) for k, v in e.items()} == {"site_academy_api_category": 3, "site_academy_api_course": 4,
                                                 "site_academy_api_lesson": 1}
    lst = next(c for c in e["site_academy_api_course"] if c["record_key"] == "blockbuster-4k@list")
    assert lst["free_generations"] == 0 and lst["test_count"] == 0 and lst["lesson_count"] == 10
    det = next(c for c in e["site_academy_api_course"] if c["record_key"] == "blockbuster-4k@detail")
    assert det["lessons"][0]["position"] == 1 and det["lessons"][0]["access_allowed"] is True
    assert "completed" not in det["lessons"][0]["extra"] and "certificate_unlocked" not in det["extra"]
    les = e["site_academy_api_lesson"][0]
    assert les["course_slug"] == "santiago-cinematic" and les["xp_reward"] == 20 and les["position"] == 1
    assert les["content_mdx"] and les["word_count"] > 50
    assert les["url"] == "https://higgsfield.ai/academy/courses/santiago-cinematic/emotional-short-film-showcase"
    assert "progress_pct" not in les["extra"] and "completed" not in les["extra"]


def test_dataset_and_outputs(tmp_path):
    sel = Selection(what="academy-api")
    ds = SCRAPER.build_dataset(ents(sel), sel, RunMeta())
    courses = {c["slug"]: c for c in ds["academy_api_courses"]}
    assert len(ds["academy_api_courses"]) == 3                    # list + detail merged by slug
    bb = courses["blockbuster-4k"]
    assert bb["record_source"] == "detail" and bb["test_count"] == 0 and bb["lessons"]
    assert "rooms" not in ds and ds["meta"]["counts"]["academy_api_lessons"] == 1
    assert "academy_api_lesson" in ds["meta"]["endpoints"]
    SCRAPER.write_outputs(ds, tmp_path)
    for t in ("academy_api_courses", "academy_api_lessons", "academy_api_categories", "academy_api_courses_lessons"):
        with (tmp_path / "csv" / f"{t}.csv").open(encoding="utf-8-sig", newline="") as f:
            assert list(csv.DictReader(f)), t
    assert "Academy JSON API" in (tmp_path / "summary.md").read_text(encoding="utf-8")
    both = Selection(what="academy-api,room-list")
    ds2 = SCRAPER.build_dataset(ents(both), both, RunMeta())
    assert "rooms" in ds2 and "academy_api_courses" in ds2
    plain = SCRAPER.build_dataset({}, Selection(), RunMeta())     # default run: SiteDataset, no new keys
    assert "academy_api_courses" not in plain and "academy_api_course" not in plain["meta"]["endpoints"]
