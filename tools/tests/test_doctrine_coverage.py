"""The methodology page states a finding about the national-policy coverage
list: three of seven states have a published policy governing weapon autonomy
and four do not. The table under it is generated from the state files, so the
page cannot quietly disagree with the records it describes.

The prose carries the numbers in words, because it is the analyst's approved
sentence and belongs in the approved markdown. That leaves one seam: the words
and the data could drift apart. These tests close it.
"""

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _tally(html):
    rows = re.findall(r'<tr><th scope="row">.*?</tr>', html)
    have = sum(1 for r in rows if "Published policy" in r)
    return len(rows), have, len(rows) - have


def test_no_unreplaced_marker_reaches_a_page(tmp_path):
    """A literal {{doctrine-coverage}} on a public page is the silent-failure
    shape this project has hit before."""
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    for page in out.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "{{" not in text, f"{page.name} ships an unreplaced marker"


def test_an_unknown_marker_stops_the_build():
    """It must fail loudly rather than render the marker to readers."""
    try:
        bs._render_with_blocks("intro\n\n{{nonesuch}}\n\ntail", {})
    except SystemExit as exc:
        assert "nonesuch" in str(exc)
    else:
        raise AssertionError("an unknown block marker was silently accepted")


def test_the_prose_numbers_match_the_generated_table(tmp_path):
    """The seam: the sentence is written out in words, the table is derived."""
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    html = (out / "methodology.html").read_text(encoding="utf-8")

    prose = re.search(
        r"Of the (\w+) states on this list, (\w+) have a published policy"
        r"[^.]*?and (\w+) do not", html)
    assert prose, "the coverage finding is missing from the methodology page"
    total, have, lack = (WORDS[w.lower()] for w in prose.groups())
    assert (total, have, lack) == _tally(html), (
        f"the sentence says {total}/{have}/{lack} but the table shows "
        f"{_tally(html)}")
    assert have + lack == total, "the sentence does not add up"


def test_the_table_lists_every_covered_state_and_nothing_else(tmp_path):
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    html = (out / "methodology.html").read_text(encoding="utf-8")

    _, _, states = bs.load_content()
    expected = {
        iso3 for iso3, cs in states.items()
        if (cs.get("doctrine") or {}).get("status")
        in ("policy_identified", "no_policy_identified")
        and bs.is_approved(cs["doctrine"])
    }
    listed = set(re.findall(r'<th scope="row"><a href="state/([A-Z]{3})\.html"',
                            html))
    assert listed == expected, (
        f"table lists {sorted(listed)}, coverage list is {sorted(expected)}")
    assert expected, "fixture expects at least one approved doctrine record"


def test_gated_doctrine_never_appears_in_the_table(tmp_path, monkeypatch):
    """A gated record's status is itself an unapproved claim, so the row must
    be absent rather than shown as pending."""
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    chn = work / "states" / "CHN.yaml"
    text = chn.read_text(encoding="utf-8")
    marker = "approved: true   # render-approved 2026-09-02"
    assert marker in text, "fixture expects the China doctrine approved"
    chn.write_text(text.replace(marker, "approved: false"), encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", work)
    monkeypatch.setattr(config, "STATES_DIR", work / "states")

    out = tmp_path / "dep"
    manifest = bs.build(out, preview=False)
    assert manifest["unapproved_rendered"] == 0
    html = (out / "methodology.html").read_text(encoding="utf-8")
    assert 'href="state/CHN.html"' not in html, "gated doctrine leaked a row"
    # The table cell, not the bare date: UPDATED_THROUGH is the same day and
    # stamps the masthead on every page.
    assert "Reviewed 2026-08-31" not in html, "gated doctrine leaked its review date"
    # and the sentence still agrees with the smaller table
    prose = re.search(
        r"Of the (\w+) states on this list, (\w+) have a published policy"
        r"[^.]*?and (\w+) do not", html)
    if prose:
        total, have, lack = (WORDS[w.lower()] for w in prose.groups())
        assert (total, have, lack) != _tally(html), (
            "expected the hardcoded sentence to disagree once a record is "
            "pulled; if this now passes, the sentence became generated and "
            "test_the_prose_numbers_match_the_generated_table is the guard")
