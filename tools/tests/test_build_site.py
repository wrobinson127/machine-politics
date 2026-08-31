"""Tests for the site build: the approval gate, the both-direction guard,
absence-tier rendering, and determinism."""

import html
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
    # the gate is per-coding: an approved coding's rationale renders on
    # deploy, an unapproved one's never does. (Before any approvals every
    # coding was unapproved; the first launch-set approvals landed
    # 2026-07-17.)
    html_blob = "".join(
        p.read_text(encoding="utf-8") for p in out.rglob("*.html")
    )
    # rationale prose is HTML-escaped when rendered (apostrophes become
    # entities); unescape the blob so raw markers compare naturally
    flat = html.unescape(" ".join(html_blob.split()))
    assert "draft-banner" not in html_blob
    assert "DRAFT" not in html_blob
    approved_seen = 0
    for state_file in sorted(config.STATES_DIR.glob("*.yaml")):
        data = yaml.safe_load(state_file.read_text(encoding="utf-8"))
        for coding in data.get("position_codings", []):
            marker = " ".join((coding.get("rationale") or "").split())[:60]
            if not marker:
                continue
            if coding.get("approved") is True:
                assert marker in flat, f"approved coding not rendered: {state_file.name}"
                approved_seen += 1
            else:
                assert marker not in flat, f"unapproved coding leaked: {state_file.name}"
    # guard against the whole loop silently matching nothing
    assert approved_seen >= 5


def test_deploy_states_show_absence_tiers_not_positions(deploy):
    out, _ = deploy
    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    # The USA is coded (CCW-ONLY, approved 2026-07-21) and its doctrine was
    # approved 2026-08-31, so both legitimately render. The gate itself is
    # exercised against a forced-unapproved copy in test_instruments_surfaces,
    # not here, so that approving real content never restales this test.
    assert "DoD Directive 3000.09" in usa  # approved doctrine renders
    assert "not yet reviewed by this project" not in usa
    assert "in favour of 193" in usa  # the vote waffle renders
    assert "A/RES/80/57" in usa
    # A genuinely uncoded state must show absence tiers and NOT be located in
    # the position spectrum. Picked dynamically so future approvals do not
    # restale this test (the USA used to be this example until it was coded).
    picked = None
    for sf in sorted(config.STATES_DIR.glob("*.yaml")):
        d = yaml.safe_load(sf.read_text(encoding="utf-8"))
        if any(c.get("approved") is True for c in (d.get("position_codings") or [])):
            continue
        if (d.get("doctrine") or {}).get("approved") is True:
            continue
        page = out / "state" / f"{sf.stem}.html"
        if page.exists():
            picked = (sf.stem, page.read_text(encoding="utf-8"))
            break
    assert picked, "expected at least one uncoded state on deploy"
    iso, html = picked
    assert "not yet reviewed by this project" in html, iso
    assert 'class="pmark mk me"' not in html, f"{iso} uncoded but located in spectrum"


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
    sources = {
        "index": (out / "index.html").read_text(encoding="utf-8"),
        "poster": (out / "assets" / "board-poster.svg").read_text(encoding="utf-8"),
        "tokens": (out / "css" / "tokens.css").read_text(encoding="utf-8"),
    }
    # preview renders position bands; scan those too (banner red excepted)
    preview_index = config.REPO_ROOT / ".scratch" / "preview" / "index.html"
    if preview_index.exists():
        sources["preview"] = re.sub(
            r'<div class="draft-banner".*?</div>', "",
            preview_index.read_text(encoding="utf-8"),
        )
    for name, text in sources.items():
        hexes = set(re.findall(r'fill="(#[0-9A-Fa-f]{6})"', text))
        hexes |= set(re.findall(r"background:(#[0-9A-Fa-f]{6})", text))
        hexes |= set(re.findall(r"--pos-[a-z]+:\s*(#[0-9A-Fa-f]{6})", text))
        for hexval in hexes:
            r, g, b = (int(hexval[i : i + 2], 16) for i in (1, 3, 5))
            assert not (r > g + 60 and r > b + 60), f"red fill {hexval} in {name}"
            assert not (g > r + 60 and g > b + 60), f"green fill {hexval} in {name}"
        if name != "tokens":  # tokens.css defines the variable; that is its job
            assert config.PALETTE["integrity_red"] not in text, name


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
