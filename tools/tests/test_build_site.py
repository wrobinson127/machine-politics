"""Tests for the site build: the approval gate, the both-direction guard,
absence-tier rendering, and determinism."""

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs


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


def test_both_direction_guard(deploy):
    """Invariant 8: every state in votes resolves to a page and back."""
    out, _ = deploy
    votes = bs.load_votes()
    pages = {p.stem for p in (out / "state").glob("*.html")}
    assert pages == set(votes["states"])
    assert len(pages) == 193
    index = (out / "index.html").read_text(encoding="utf-8")
    for iso3 in votes["states"]:
        assert f'href="state/{iso3}.html"' in index


def test_deploy_renders_zero_unapproved(deploy):
    out, manifest = deploy
    assert manifest["unapproved_rendered"] == 0
    written = json.loads((out / "build_manifest.json").read_text(encoding="utf-8"))
    assert written["unapproved_rendered"] == 0
    # every claim-bearing entry in content is currently unapproved, so none
    # of their rationales may appear anywhere in the deploy artifact
    html_blob = "".join(
        p.read_text(encoding="utf-8") for p in out.rglob("*.html")
    )
    assert "draft-banner" not in html_blob
    assert "DRAFT" not in html_blob
    for state_file in sorted(config.STATES_DIR.glob("*.yaml")):
        data = yaml.safe_load(state_file.read_text(encoding="utf-8"))
        for coding in data.get("position_codings", []):
            marker = " ".join((coding.get("rationale") or "").split())[:60]
            if marker:
                assert marker not in " ".join(html_blob.split()), state_file.name


def test_deploy_states_show_absence_tiers_not_positions(deploy):
    out, _ = deploy
    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    assert "not yet reviewed by this project" in usa
    assert "REG-SOFT" not in usa  # unapproved coding must not leak
    assert "Recorded votes" in usa
    assert "A/RES/80/57" in usa


def test_preview_renders_drafts_behind_banner(preview):
    out, manifest = preview
    assert manifest["unapproved_rendered"] > 0
    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    assert "draft-banner" in usa
    assert "DRAFT" in usa
    assert "REG-SOFT" in usa
    assert "appropriate levels of human judgment" in usa


def test_votes_page_tallies(deploy):
    out, _ = deploy
    votes_html = (out / "votes.html").read_text(encoding="utf-8")
    assert "152 in favour, 4 against, 11 abstentions" in votes_html
    assert "166 in favour, 3 against, 15 abstentions" in votes_html
    assert "164 in favour, 6 against, 7 abstentions" in votes_html


def test_no_valence_hues_in_generated_output(deploy):
    """Invariant 5: no position renders red or green anywhere, and the
    integrity red appears only in css, never as an SVG band fill."""
    out, _ = deploy
    for svg_source in (
        (out / "index.html").read_text(encoding="utf-8"),
        (out / "assets" / "board-poster.svg").read_text(encoding="utf-8"),
    ):
        for hexval in set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', svg_source)):
            r, g, b = (int(hexval[i : i + 2], 16) for i in (1, 3, 5))
            assert not (r > g + 60 and r > b + 60), f"red fill {hexval}"
            assert not (g > r + 60 and g > b + 60), f"green fill {hexval}"
        assert config.PALETTE["integrity_red"] not in svg_source


def test_doctrine_absence_renders_exact_phrase(tmp_path):
    """Invariant 6: the mandated coverage phrasing, nothing else."""
    doctrine = {
        "status": "no_policy_identified",
        "approved": True,
        "as_of": "2026-02-01",
        "search_note": "Searched ministry publications.",
    }
    html_out = bs.doctrine_signal({"doctrine": doctrine}, {}, preview=False)
    assert (
        "No published national policy identified by this project, as of 2026-02-01"
        in html_out
    )
    assert "has no" not in html_out


def test_unapproved_doctrine_renders_as_not_reviewed(deploy):
    out, _ = deploy
    chn = (out / "state" / "CHN.html").read_text(encoding="utf-8")
    assert "Doctrine not yet reviewed by this project" in chn


def test_build_is_deterministic(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    bs.build(a, preview=False)
    bs.build(b, preview=False)
    for rel in ("index.html", "votes.html", "state/USA.html", "assets/board-poster.svg"):
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_deploy_build_refuses_to_render_unapproved():
    """The hard exclusion is a refusal, not a filter that can silently fail."""
    dirty = {"unapproved_rendered": 1}
    with pytest.raises(SystemExit, match="refusing"):
        bs.assert_deploy_clean(dirty, preview=False)
    # the same manifest is fine in preview mode, which never deploys
    bs.assert_deploy_clean(dirty, preview=True)
    bs.assert_deploy_clean({"unapproved_rendered": 0}, preview=False)
