"""P3b surface tests: the instruments page approval gate (deploy shell vs
preview render), both-direction integrity for endorsement and sponsorship
rows, hue discipline on the new outputs, the two era tokens, the doctrine
timeline's marker classes, and deterministic rebuilds."""

import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs


@pytest.fixture(scope="module")
def deploy(tmp_path_factory):
    out = tmp_path_factory.mktemp("deploy_inst")
    manifest = bs.build(out, preview=False)
    return out, manifest


@pytest.fixture(scope="module")
def preview(tmp_path_factory):
    out = tmp_path_factory.mktemp("preview_inst")
    manifest = bs.build(out, preview=True)
    return out, manifest


def test_nav_places_instruments_between_votes_and_rubric(deploy):
    out, _ = deploy
    html = (out / "index.html").read_text(encoding="utf-8")
    assert (
        html.index('href="votes.html"')
        < html.index('href="instruments.html"')
        < html.index('href="rubric.html"')
    )


def test_deploy_instruments_is_a_factual_shell(tmp_path, monkeypatch):
    """The gate, tested on the mechanism rather than on today's editorial
    state. The instruments were approved on 2026-08-24, so this no longer
    holds for the live content and is exercised against an unapproved copy:
    gated instruments produce the prose-shell pattern with no rows, no
    scripts and no surfaces. The live-approved counterpart is the test
    below."""
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    for name in ("endorsements.yaml", "sponsorships.yaml"):
        path = work / name
        text = path.read_text(encoding="utf-8")
        assert "approved: true" in text, f"fixture expects {name} approved"
        path.write_text(text.replace("approved: true", "approved: false"),
                        encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", work)

    out = tmp_path / "dep"
    manifest = bs.build(out, preview=False)
    html = (out / "instruments.html").read_text(encoding="utf-8")
    assert "analyst review" in html
    assert "maplibre" not in html.lower()
    assert "quadrant" not in html.lower()
    assert "wave-map" not in html
    assert 'type="range"' not in html
    assert 'href="state/' not in html
    for marker in ("XKX", "Kosovo", "Palestine", "endorser"):
        assert marker not in html
    assert not (out / "js" / "instruments.js").exists()
    assert not (out / "assets" / "countries.geojson").exists()
    # the search box is a quadrant surface: preview only
    assert "quadrant-search" not in html
    assert "quadrant-state-list" not in html
    assert "<datalist" not in html
    ends = [e for e in manifest["entries"]
            if str(e["kind"]).startswith("endorsement_instrument:")]
    recs = [e for e in manifest["entries"]
            if str(e["kind"]).startswith("sponsorship_record:")]
    assert len(ends) == 4
    # 6 records since the WP.8 ten-state joint statement was verified and
    # recorded in the launch-set coding pass (2026-07-17)
    assert len(recs) == 6
    assert all(not e["rendered"] and not e["approved"] for e in ends + recs)


def test_deploy_instruments_render_once_approved(deploy):
    """The other half of the gate, against the live content as approved on
    2026-08-24: the rosters, the quadrant and the wave map now ship in the
    deploy artifact, and the manifest records every record as approved and
    rendered with nothing unapproved leaking through."""
    out, manifest = deploy
    html = (out / "instruments.html").read_text(encoding="utf-8")
    assert manifest["unapproved_rendered"] == 0
    assert "analyst review" not in html
    assert "58 endorsers on the official list." in html
    assert 'id="quadrant-svg"' in html
    assert html.count('class="q-dot"') == 193
    assert f"maplibre-gl/{bs.MAPLIBRE_VERSION}/maplibre-gl.min.js" in html
    assert (out / "js" / "instruments.js").exists()
    # The count-only Blueprint still renders its honest zero-row disclosure
    # rather than a roster it does not have.
    assert "61 supporting states" in html
    ends = [e for e in manifest["entries"]
            if str(e["kind"]).startswith("endorsement_instrument:")]
    recs = [e for e in manifest["entries"]
            if str(e["kind"]).startswith("sponsorship_record:")]
    assert len(ends) == 4 and len(recs) == 6
    assert all(e["rendered"] and e["approved"] for e in ends + recs)


def test_preview_instruments_renders_everything(preview):
    out, manifest = preview
    html = (out / "instruments.html").read_text(encoding="utf-8")
    # server-rendered endorsement record
    assert "58 endorsers on the official list." in html
    assert "Non-member endorsers" in html
    assert "Kosovo" in html and "Palestine" in html
    # Blueprint renders its count-only note honestly, with zero rows
    assert "61 supporting states" in html
    # sponsorship records with associates and non-member notes
    assert "Draft articles on autonomous weapon systems" in html
    assert "Associating states (3)" in html
    assert "Non-member participants" in html
    # quadrant: SVG, one dot per member state, scrub, table fallback
    assert 'id="quadrant-svg"' in html
    assert html.count('class="q-dot"') == 193
    assert 'id="quadrant-time"' in html
    assert 'id="quadrant-data"' in html
    assert "The same data as a table" in html
    # wave map: pinned MapLibre with SRI, radios, scrub, fallback, credit
    assert f"maplibre-gl/{bs.MAPLIBRE_VERSION}/maplibre-gl.min.js" in html
    assert f'integrity="{bs.MAPLIBRE_JS_SRI}"' in html
    assert f'integrity="{bs.MAPLIBRE_CSS_SRI}"' in html
    assert html.count('name="map-instrument"') == 4
    # the Blueprint's all-paper map is explained at its own control
    assert "REAIM Blueprint for Action (count only, no named list)" in html
    assert html.count("(count only, no named list)") == 1
    assert "Map unavailable" in html
    assert "OpenStreetMap contributors, tiles by OpenFreeMap" in html
    assert (out / "js" / "instruments.js").exists()
    assert (out / "assets" / "countries.geojson").exists()
    ends = [e for e in manifest["entries"]
            if str(e["kind"]).startswith("endorsement_instrument:")]
    assert all(e["rendered"] for e in ends)


def test_quadrant_search_renders_in_preview(preview):
    """DESIGN v2 mobile contract: a state search box is the quadrant's
    primary nav. Server-rendered, disabled until JS enables it, one
    datalist option per member state carrying name and ISO code."""
    out, _ = preview
    html = (out / "instruments.html").read_text(encoding="utf-8")
    assert re.search(
        r'<input type="search" id="quadrant-search" list="quadrant-state-list"'
        r'\s+autocomplete="off" spellcheck="false" disabled>', html
    )
    assert '<label for="quadrant-search">' in html
    assert 'id="quadrant-state-list"' in html
    m = re.search(r"<datalist[^>]*>(.*?)</datalist>", html, re.S)
    assert m
    options = re.findall(r'<option value="([^"]+) \(([A-Z]{3})\)">', m.group(1))
    assert len(options) == 193
    votes = bs.load_votes()
    assert {iso3 for _, iso3 in options} == set(votes["states"])
    # the search input appears before the SVG, and the JS hooks exist
    assert html.index('id="quadrant-search"') < html.index('id="quadrant-svg"')
    assert 'id="quadrant-table"' in html
    js = (out / "js" / "instruments.js").read_text(encoding="utf-8")
    for hook in ("quadrant-search", "quadrant-table", "q-hit"):
        assert hook in js


def test_countries_topojson_never_ships(deploy, preview):
    """The world-atlas TopoJSON lives in data/source; no output artifact
    carries it, and the committed deploy dir carries no copy either."""
    assert bs.COUNTRIES_TOPOJSON == config.DATA_SOURCE_DIR / "countries-110m.json"
    assert bs.COUNTRIES_TOPOJSON.exists()
    for out, _ in (deploy, preview):
        assert not list(Path(out).rglob("countries-110m.json"))
    assert not list(config.SITE_DIR.rglob("countries-110m.json"))


def test_no_quadrant_region_labels(preview):
    """DESIGN v2 rule 9: quadrant regions get no interpretive names."""
    out, _ = preview
    html = (out / "instruments.html").read_text(encoding="utf-8")
    for word in ("skeptic", "leader", "laggard", "champion", "dual-track",
                 "governance-without", "neither-camp"):
        assert word not in html.lower()


def test_both_direction_integrity(preview):
    """Every iso3 in the endorsement and sponsorship records resolves to a
    state page link, or carries a rendered non-member note."""
    out, _ = preview
    html = (out / "instruments.html").read_text(encoding="utf-8")
    votes = bs.load_votes()
    members = set(votes["states"])
    endorsements = yaml.safe_load(
        (config.CONTENT_DIR / "endorsements.yaml").read_text(encoding="utf-8")
    )["instruments"]
    sponsorships = yaml.safe_load(
        (config.CONTENT_DIR / "sponsorships.yaml").read_text(encoding="utf-8")
    )["records"]
    seen_member, seen_non_member = set(), set()
    for inst in endorsements:
        for row in inst.get("states") or []:
            (seen_member if row["iso3"] in members else seen_non_member).add(row["iso3"])
    for rec in sponsorships:
        for iso3 in (rec.get("members") or []) + (rec.get("associates") or []):
            (seen_member if iso3 in members else seen_non_member).add(iso3)
        for nm in rec.get("non_members") or []:
            seen_non_member.add(nm["iso3"])
    assert seen_member <= members, "member rows must be UN member states"
    for iso3 in sorted(seen_member):
        assert f'href="state/{iso3}.html"' in html, iso3
        assert (out / "state" / f"{iso3}.html").exists(), iso3
    for iso3 in sorted(seen_non_member):
        assert f"({iso3})" in html, f"non-member {iso3} needs a rendered note"
        assert not (out / "state" / f"{iso3}.html").exists(), iso3


HEX_RE = re.compile(r"#([0-9A-Fa-f]{6})\b")


def _assert_no_valence(text, where):
    for hexval in set(HEX_RE.findall(text)):
        r, g, b = (int(hexval[i:i + 2], 16) for i in (0, 2, 4))
        assert not (r > g + 60 and r > b + 60), f"red hue #{hexval} in {where}"
        assert not (g > r + 60 and g > b + 60), f"green hue #{hexval} in {where}"


def test_no_valence_hues_in_new_outputs(preview):
    """No red, no green: not in the instrument hues, not in the map data,
    not in the timeline. Non-endorsement is paper, never an opposing color."""
    out, _ = preview
    for rel in ("instruments.html", "state/USA.html", "js/instruments.js"):
        _assert_no_valence((out / rel).read_text(encoding="utf-8"), rel)
    html = (out / "instruments.html").read_text(encoding="utf-8")
    assert config.PALETTE["integrity_red"] not in html
    # the four instrument hues are distinct and come from the position family
    hues = set(bs.INSTRUMENT_HUES.values())
    assert len(hues) == 4
    assert hues <= {v for v in config.PALETTE["positions"].values() if v}


def test_era_tokens_exactly_two(deploy):
    out, _ = deploy
    tokens = (out / "css" / "tokens.css").read_text(encoding="utf-8")
    era_tokens = re.findall(r"--era-[a-z0-9]+\s*:\s*(#[0-9A-Fa-f]{6})", tokens)
    assert len(era_tokens) == 2
    assert len(set(era_tokens)) == 2, "the two shades must be distinguishable"
    _assert_no_valence(" ".join(era_tokens), "era tokens")
    for hexval in era_tokens:  # neutral paper family: near-gray, warm
        r, g, b = (int(hexval[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) - min(r, g, b) < 40, f"{hexval} is not a neutral shade"


def _content_with_usa_doctrine_gated(tmp_path, monkeypatch):
    """A copy of the live content with the USA doctrine forced unapproved.

    The USA doctrine was approved on 2026-08-31, and it was the only state
    carrying doctrine entries that were ever gated, so the gate can no longer
    be exercised against live content at all. Testing the mechanism instead of
    today's editorial state is also what keeps these tests from restaling the
    next time something is approved.

    STATES_DIR is bound at import from CONTENT_DIR, so it does not follow a
    CONTENT_DIR monkeypatch and has to be redirected on its own.
    """
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    usa = work / "states" / "USA.yaml"
    text = usa.read_text(encoding="utf-8")
    marker = "approved: true   # render-approved 2026-08-31"
    assert text.count(marker) == 2, (
        "fixture expects the USA doctrine block and its entry both approved")
    usa.write_text(text.replace(marker, "approved: false"), encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", work)
    monkeypatch.setattr(config, "STATES_DIR", work / "states")
    return work


def test_doctrine_timeline_deploy_excludes_unapproved(tmp_path, monkeypatch):
    """The gate, tested on the mechanism: with the doctrine unapproved, deploy
    keeps the not-yet-reviewed card, renders no markers, and leaks no quote.
    Era bands are context data and may stand."""
    _content_with_usa_doctrine_gated(tmp_path, monkeypatch)
    out = tmp_path / "dep"
    manifest = bs.build(out, preview=False)
    assert manifest["unapproved_rendered"] == 0

    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    assert "Doctrine not yet reviewed by this project" in usa
    assert "DoD Directive" not in usa
    assert "appropriate levels of human judgment" not in usa  # the quote
    assert "tl-core" not in usa
    assert "tl-context" not in usa
    assert "timeline-list" not in usa
    # era bands render from the eras file: factual labels, two shades
    assert 'class="doctrine-timeline"' in usa
    assert "Obama administration" in usa
    assert "var(--era-a)" in usa and "var(--era-b)" in usa
    # a state with no eras file and no doctrine gets no timeline at all
    afg = (out / "state" / "AFG.html").read_text(encoding="utf-8")
    assert "doctrine-timeline" not in afg


def test_doctrine_timeline_deploy_renders_approved_doctrine(deploy):
    """The approved-side counterpart: the guarantee above must be the gate
    doing its job, not the timeline being broken for everyone."""
    out, _ = deploy
    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    assert "DoD Directive 3000.09" in usa
    assert 'class="tl-core"' in usa
    assert "2023-01-25" in usa
    assert "timeline-list" in usa
    assert "Doctrine not yet reviewed by this project" not in usa


def test_doctrine_timeline_preview_renders_markers(preview):
    out, _ = preview
    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    assert 'class="doctrine-timeline"' in usa
    assert 'class="tl-core"' in usa  # filled marker for core doctrine
    assert "core doctrine, filled marker" in usa
    assert "2023-01-25" in usa  # the dated list below the SVG
    assert "timeline-list" in usa


def test_doctrine_timeline_preview_chips_unapproved_entries(tmp_path, monkeypatch):
    """Preview renders gated doctrine, but has to say it is gated."""
    _content_with_usa_doctrine_gated(tmp_path, monkeypatch)
    out = tmp_path / "prev"
    bs.build(out, preview=True)
    usa = (out / "state" / "USA.html").read_text(encoding="utf-8")
    assert "DoD Directive" in usa, "preview should still render gated doctrine"
    m = re.search(r'<ul class="timeline-list">.*?</ul>', usa, re.S)
    assert m and "draft-chip" in m.group(0)


def test_rebuilds_are_byte_identical(tmp_path):
    for mode in (False, True):
        a, b = tmp_path / f"a{mode}", tmp_path / f"b{mode}"
        bs.build(a, preview=mode)
        bs.build(b, preview=mode)
        rels = ["instruments.html", "state/USA.html", "css/tokens.css"]
        if mode:
            rels += ["assets/countries.geojson", "js/instruments.js"]
        for rel in rels:
            assert (a / rel).read_bytes() == (b / rel).read_bytes(), (mode, rel)
