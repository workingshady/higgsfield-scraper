"""Regression tests for shared-framework fixes made while integrating the new scrapers."""
import json

from higgsfield_scraper.core.privacy import REDACTED, redact_json_bytes, redact_personal
from higgsfield_scraper.core import registry
from higgsfield_scraper.raw import MAX_NAME, Envelope


def test_redact_personal_keeps_ids_and_content():
    item = {"id": "g1", "user_id": "user_abc", "params": {"prompt": "a cat", "model": "x"},
            "profile": {"username": "realname", "avatar_url": "https://a/b.png", "twitter_handle": "rn",
                        "badges": []},
            "authors": [{"user_id": "u2", "full_name": "Jane Doe", "username": "jd", "location": "Paris"}],
            "location": "studio"}
    out = redact_personal(item)
    assert out["id"] == "g1" and out["user_id"] == "user_abc" and out["params"]["prompt"] == "a cat"
    assert out["profile"]["username"] == REDACTED and out["profile"]["avatar_url"] == REDACTED
    assert out["profile"]["twitter_handle"] == REDACTED
    assert out["authors"][0]["full_name"] == REDACTED and out["authors"][0]["location"] == REDACTED
    assert out["authors"][0]["user_id"] == "u2"
    assert out["location"] == "studio"                  # outside person containers ambiguous keys stay
    assert json.loads(redact_json_bytes(json.dumps(item).encode()))["profile"]["username"] == REDACTED
    assert redact_json_bytes(b"<html>not json</html>") == b"<html>not json</html>"


def test_personal_data_flag_on_people_scrapers():
    av = registry.available()
    for name in ("community", "projects"):
        if name in av:
            assert av[name].personal_data is True
    assert av["pricing"].personal_data is False


def test_raw_envelopes_never_overwrite_each_other(tmp_path):
    a = Envelope("detail", "https://x/api/items/1", 200, {"a": 1})
    b = Envelope("detail", "https://x/api/items/2", 200, {"b": 2})
    pa, pb = a.save(tmp_path), b.save(tmp_path)
    assert pa != pb and len(list(tmp_path.glob("*.json"))) == 2
    assert a.save(tmp_path) == pa                       # same URL again -> same file (idempotent)


def test_raw_filename_is_bounded_for_long_cursors():
    e = Envelope("feed", "https://x/feed?cursor=" + "c" * 400, 200, {}, params={"cursor": "c" * 400})
    assert len(e.filename) <= MAX_NAME + len(".json")
    e2 = Envelope("feed", "https://x/feed?cursor=" + "d" * 400, 200, {}, params={"cursor": "d" * 400})
    assert e.filename != e2.filename


def test_pricing_raw_filenames_unchanged():
    e = Envelope("plans", "u", 200, {}, params={"plan_set_key": "ps_a3", "with_localization": "true"})
    assert e.filename == "plans__plan_set_key-ps_a3.json"
