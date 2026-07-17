"""Phase 0b gates as tests: the tour scaffold is approval-gated, fallback-
first, and the animation stack is pinned with integrity hashes."""

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs
from tools import validate_content as vc


@pytest.fixture(scope="module")
def deploy(tmp_path_factory):
    out = tmp_path_factory.mktemp("deploy")
    manifest = bs.build(out, preview=False)
    return out, manifest


@pytest.fixture(scope="module")
def preview(tmp_path_factory):
    out = tmp_path_factory.mktemp("preview")
    manifest = bs.build(out, preview=True)
    return out, manifest


def test_deploy_has_no_tour_and_no_gsap(deploy):
    """Unapproved beat copy never reaches the deploy artifact, and neither
    do the animation scripts that exist only to serve it."""
    out, manifest = deploy
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "PLACEHOLDER BEAT" not in index
    assert 'class="tour"' not in index
    assert "gsap" not in index.lower()
    assert "tour.js" not in index
    tour_entries = [e for e in manifest["entries"] if e["kind"] == "tour"]
    assert tour_entries and tour_entries[0]["rendered"] is False


def test_preview_tour_scaffold_renders(preview):
    out, manifest = preview
    index = (out / "index.html").read_text(encoding="utf-8")
    assert index.count('class="beat"') == 4
    assert "PLACEHOLDER BEAT 1" in index
    # no-JS completeness: figures are server-rendered content, not JS mounts,
    # and each carries its own numbers and labels (self-explanatory rule)
    tour_markup = index.split('class="tour"')[1].split("board-head")[0]
    assert "tally-units" in tour_markup
    assert "<strong>152</strong>" in tour_markup  # the count is on the figure
    assert tour_markup.count("<i style=") == 193  # one unit mark per state
    assert 'id="us-band-path"' in tour_markup  # the DrawSVG stroke pre-renders
    assert "mover-table" in tour_markup
    assert "mv-changed" in tour_markup  # changed votes are marked in markup
    assert 'id="beat-us-shift"' in index
    tour_entries = [e for e in manifest["entries"] if e["kind"] == "tour"]
    assert tour_entries and tour_entries[0]["rendered"] is True


def test_skip_link_precedes_tour_and_targets_board(preview):
    out, _ = preview
    index = (out / "index.html").read_text(encoding="utf-8")
    skip = index.find('class="skip-board"')
    tour = index.find('class="tour"')
    board = index.find('id="board-top"')
    assert -1 < skip < tour < board
    assert 'href="#board-top"' in index


def test_gsap_pinned_with_integrity(preview):
    out, _ = preview
    index = (out / "index.html").read_text(encoding="utf-8")
    for name, sri in bs.GSAP_SCRIPTS:
        tag = re.search(
            rf'<script defer src="https://cdnjs\.cloudflare\.com/ajax/libs/gsap/'
            rf'{re.escape(bs.GSAP_VERSION)}/{re.escape(name)}" integrity="([^"]+)" '
            rf'crossorigin="anonymous"></script>',
            index,
        )
        assert tag, name
        assert tag.group(1) == sri
    assert '<script defer src="js/tour.js">' in index


def test_tour_js_guards_are_first(preview):
    out, _ = preview
    tour_js = (out / "js" / "tour.js").read_text(encoding="utf-8")
    body = tour_js.split('"use strict";')[1]
    reduced = body.find("prefers-reduced-motion")
    gsap_use = body.find("registerPlugin")
    assert -1 < reduced < gsap_use


def test_movers_are_the_substantive_changers():
    votes = bs.load_votes()
    movers = bs.substantive_changers(votes)
    assert len(movers) == 18
    assert "IND" in movers and "USA" in movers and "POL" in movers
    assert "TUV" not in movers  # attendance-only changer


def test_validator_enforces_tour_rules(tmp_path):
    (tmp_path / "sources.yaml").write_text("sources: []\n", encoding="utf-8")
    rubric_src = Path(__file__).resolve().parents[2] / "content" / "rubric.yaml"
    (tmp_path / "rubric.yaml").write_text(rubric_src.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "tour.yaml").write_text(
        "approved: false\nbeats:\n"
        "  - {id: a, title: One — dash, copy: Text, figure: f}\n"
        "  - {id: b, title: Two, copy: This state has no policy., figure: f}\n"
        "  - {id: c, title: Three, copy: Text, figure: f}\n",
        encoding="utf-8",
    )
    errs = vc.validate(tmp_path).items
    assert any("exactly four beats" in e for e in errs)
    assert any("em dash" in e for e in errs)
    assert any("prohibited claim" in e for e in errs)


def test_real_tour_validates():
    assert vc.validate().items == []
