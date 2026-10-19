"""The home page's first screen: one h1 that says what the site is, the
review-conference date, and a unit field whose counts add up to the whole
membership and never show an unapproved reading."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs


@pytest.fixture(scope="module")
def deploy(tmp_path_factory):
    out = tmp_path_factory.mktemp("deploy")
    manifest = bs.build(out, preview=False)
    return out, manifest


def _index(deploy):
    out, _ = deploy
    return (out / "index.html").read_text(encoding="utf-8")


def test_one_h1_and_it_is_the_opener(deploy):
    index = _index(deploy)
    h1s = re.findall(r"<h1\b[^>]*>(.*?)</h1>", index, re.S)
    assert len(h1s) == 1
    assert "autonomous weapons" in h1s[0]
    assert index.find('class="opener"') < index.find('class="tour"') < index.find('id="board-top"')


def test_opener_states_the_conference_date(deploy):
    assert "16 November 2026" in _index(deploy)


def test_unit_field_counts_cover_every_member_state(deploy):
    index = _index(deploy)
    opener = index[index.find('class="opener"'):index.find('class="tour"')]
    counts = [int(n) for n in re.findall(r'<p class="og-label"><b>(\d+)</b>', opener)]
    assert len(counts) == len(config.POSITION_CATEGORIES) + 1
    assert sum(counts) == len(bs.load_votes()["states"])
    units = re.findall(r'<i class="unit[ "]', opener)
    assert len(units) == sum(counts)


def test_unit_field_respects_the_approval_gate():
    """A reading that is not approved must not move a state out of the
    not-yet-reviewed group in the deploy build."""
    cs = {"position_codings": [
        {"code": "OPPOSE", "confidence": "EXPLICIT", "as_of": "2026-01-01", "approved": False}
    ]}
    assert bs.current_position(cs, preview=False) is None
    assert bs.current_position(cs, preview=True)["code"] == "OPPOSE"


def test_none_yields_to_a_later_substantive_reading():
    cs = {"position_codings": [
        {"code": "NONE", "confidence": "INFERRED", "as_of": "2026-07-17", "approved": True},
        {"code": "LBI-BAN", "confidence": "EXPLICIT", "as_of": "2022-08-09", "approved": True},
    ]}
    assert bs.current_position(cs, preview=False)["code"] == "LBI-BAN"


def test_none_is_shown_as_dated_coverage_not_as_a_position(deploy):
    """NONE is a coverage statement: it sits below the positions with
    "not yet reviewed", and its label carries the review date."""
    index = _index(deploy)
    opener = index[index.find('class="opener"'):index.find('class="tour"')]
    m = re.search(r'<div class="og og-coverage"><p class="og-label"><b>\d+</b> '
                  r'No stated position, reviewed (\d{4}-\d{2}-\d{2})', opener)
    assert m, "NONE group missing its review date or its coverage placement"
    positions = opener[:m.start()]
    assert "No stated position" not in positions
    assert "by position" not in opener
