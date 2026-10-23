"""The home page (redesign, 2026-10-19): one h1 that says what the site is,
the Review Conference date, the globe figure with a static map as its first
paint, Strands, and every member state in a table. The figures read one
payload, built from approved content only."""

import hashlib
import json
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


def _payload(index):
    m = re.search(r'<script type="application/json" id="viz-data">(.*?)</script>', index, re.S)
    assert m, "no figure payload on the page"
    return json.loads(m.group(1))


def test_one_h1_and_it_is_the_opener(deploy):
    index = _index(deploy)
    h1s = re.findall(r"<h1\b[^>]*>(.*?)</h1>", index, re.S)
    assert len(h1s) == 1 and "autonomous weapons" in h1s[0]
    assert (index.find('class="opener') < index.find('id="viz-world"')
            < index.find('id="viz-strands"') < index.find('id="states"'))


def test_opener_states_the_conference_date(deploy):
    """The first screen names the conference date, in either the approved
    sentence or the hero's shorter line."""
    hero = _index(deploy)
    hero = hero[hero.find('class="opener'):hero.find('id="viz-world"')]
    assert re.search(r"16 (to 20 )?November 2026", hero)


def test_hero_is_the_headline_two_ways_in_and_a_globe(deploy):
    """The hero is only the headline, two ways in, the conference on one
    line, and a globe canvas that stays hidden until the script draws it
    (so the page reads the same without JavaScript). The key lives with
    the map below, not here."""
    index = _index(deploy)
    hero = index[index.find('class="opener'):index.find('id="viz-world"')]
    assert re.search(r'<canvas class="hero-globe"[^>]*\shidden>', hero)
    assert 'href="#viz-world"' in hero and 'href="#states"' in hero
    assert "hero-key" not in hero and "hero-count" not in hero
    assert hero.count('<p class="hero-conf">') == 1


def test_world_figure_opens_on_the_flat_map(deploy):
    """The hero is the globe, so the world figure below starts on the map."""
    index = _index(deploy)
    fig = index[index.find('id="viz-world"'):index.find('id="viz-strands"')]
    assert '<figure class="viz" id="viz-world" data-start="map"' in index
    assert 'data-view="map" aria-pressed="true"' in fig
    assert 'data-view="globe" aria-pressed="false"' in fig


def test_unapproved_landing_copy_falls_back_to_plain_words(deploy):
    """Hero copy is gated: until approved the page shows a plain date
    line, never the draft."""
    _, manifest = deploy
    landing = bs.load_yaml(config.CONTENT_DIR / "landing.yaml")
    entry = next(e for e in manifest["entries"] if e["kind"] == "landing_copy")
    index = _index(deploy)
    if bs.is_approved(landing):
        assert entry["rendered"] is True
        assert " ".join(landing["conference_line"].split()) in index
    else:
        assert entry["rendered"] is False
        assert bs.LANDING_FALLBACK["conference_line"] in index
        assert " ".join(landing["conference_line"].split()) not in index


def test_the_retired_tour_and_board_are_gone(deploy):
    index = _index(deploy)
    for gone in ('class="tour"', "scrollama", "gsap", "board-row", "tour.js"):
        assert gone not in index, gone


def test_the_static_map_is_the_first_paint(deploy):
    """Without JavaScript the figure is a real map, not an empty box."""
    index = _index(deploy)
    stage = index[index.find('id="viz-world"'):index.find('id="viz-strands"')]
    assert 'class="viz-poster"' in stage
    assert stage.count('class="viz-p p-') >= 30  # reviewed states, filled


def test_payload_covers_every_member_state_once(deploy):
    rows = _payload(_index(deploy))["rows"]
    assert len(rows) == len(bs.load_votes()["states"])
    assert len({r["i"] for r in rows}) == len(rows)
    assert all(len(r["v"]) == len(config.LAWS_RESOLUTIONS) for r in rows)
    assert all(r["p"] == "" or r["p"] in config.POSITION_CATEGORIES for r in rows)


def test_table_lists_every_state_and_matches_the_payload(deploy):
    index = _index(deploy)
    table = index[index.find('class="states-table"'):]
    assert table.count('<tr data-name="') == len(bs.load_votes()["states"])
    reviewed = sum(1 for r in _payload(index)["rows"] if r["p"])
    assert f"Positions have been reviewed for {reviewed} states" in index


def test_payload_respects_the_approval_gate():
    cs = {"position_codings": [
        {"code": "OPPOSE", "confidence": "EXPLICIT", "as_of": "2026-01-01", "approved": False}
    ]}
    assert bs.current_position(cs, preview=False) is None
    assert bs.current_position(cs, preview=True)["code"] == "OPPOSE"


def test_none_yields_to_a_substantive_reading():
    cs = {"position_codings": [
        {"code": "NONE", "confidence": "INFERRED", "as_of": "2026-07-17", "approved": True},
        {"code": "LBI-BAN", "confidence": "EXPLICIT", "as_of": "2022-08-09", "approved": True},
    ]}
    assert bs.current_position(cs, preview=False)["code"] == "LBI-BAN"


def test_unapproved_captions_fall_back_to_plain_labels(deploy):
    """Caption prose is gated. Until it is approved the figures show the
    count-only labels, and the drafted sentences never reach the page."""
    _, manifest = deploy
    copy = bs.load_yaml(config.CONTENT_DIR / "viz.yaml")
    entry = next(e for e in manifest["entries"] if e["kind"] == "viz_copy")
    caps = _payload(_index(deploy))["captions"]
    if bs.is_approved(copy):
        assert entry["rendered"] is True
    else:
        assert entry["rendered"] is False
        assert caps == bs.VIZ_FALLBACK["captions"]
        assert "Drag to turn the globe" not in _index(deploy)


def test_every_state_with_a_file_has_an_alpha2_mark_label():
    """Marks label states with ISO alpha-2. Truncated alpha-3 collides
    (UKR as "UK") and must never be the fallback for a state with a file."""
    from tools import dossier_render
    for path in config.CONTENT_DIR.joinpath("states").glob("*.yaml"):
        assert path.stem in dossier_render.ALPHA2, path.stem
    labels = list(dossier_render.ALPHA2.values())
    assert len(labels) == len(set(labels))


def test_every_member_state_has_a_label_point_and_code():
    path = config.REPO_ROOT / "data" / "source" / "ne_labels.json"
    labels = json.loads(path.read_text(encoding="utf-8"))["states"]
    assert set(labels) == set(bs.load_votes()["states"])
    codes = [v["a2"] for v in labels.values()]
    assert len(codes) == len(set(codes)) and all(len(c) == 2 for c in codes)


def _film(index):
    m = re.search(r'<div class="film" id="film".*?</div>\s*</div>', index, re.S)
    assert m, "no film panel in the hero"
    return m.group(0)


def test_the_film_sits_inside_the_hero_hidden_until_it_plays(deploy):
    """The film plays over the hero and fades out to reveal it, so it lives
    inside #hero, starts hidden (no JavaScript: the hero stands alone), and
    has its controls and a text description from the first frame."""
    index = _index(deploy)
    hero = index[index.find('id="hero"'):index.find('id="viz-world"')]
    assert '<div class="film" id="film"' in hero
    film = _film(index)
    assert re.search(r'id="film"[^>]*\shidden\b', film)
    assert 'class="film-skip"' in film and 'class="film-pause"' in film
    assert 'class="film-desc"' in film
    assert re.search(r'<button type="button" class="film-replay" aria-label="Replay the film"[^>]*\shidden>', hero)


def test_unapproved_film_copy_shows_no_end_card(deploy):
    """The end-card lines are gated with the rest of the hero copy: until
    approved the card is empty, so the film fades straight to the hero."""
    landing = bs.load_yaml(config.CONTENT_DIR / "landing.yaml")
    film = _film(_index(deploy))
    card = re.search(r'<div class="film-card" hidden>(.*?)</div>', film, re.S).group(1)
    if bs.is_approved(landing):
        for k in bs.FILM_LINES:
            assert bs.esc(" ".join(landing[k].split())) in card
    else:
        assert card == ""
        assert bs.esc(" ".join(landing["film_question"].split())) not in film
        assert bs.LANDING_FALLBACK["film_description"] in film


def test_the_preview_shows_the_draft_end_card(tmp_path):
    out = tmp_path / "preview"
    bs.build(out, preview=True)
    index = (out / "index.html").read_text(encoding="utf-8")
    landing = bs.load_yaml(config.CONTENT_DIR / "landing.yaml")
    card = re.search(r'<div class="film-card" hidden>(.*?)</div>', index, re.S).group(1)
    assert [bs.esc(" ".join(landing[k].split())) for k in bs.FILM_LINES] == re.findall(r"<p[^>]*>(.*?)</p>", card)


def test_the_film_ships_with_its_player_and_videos(deploy):
    """film.js is linked on the home page only, and every video the panel
    names is in the build, versioned by its bytes."""
    out, _ = deploy
    index = _index(deploy)
    assert re.search(r'<script defer src="js/film\.js\?v=[0-9a-f]{10}"></script>', index)
    assert (out / "js" / "film.js").exists()
    film = _film(index)
    for attr in ("data-src", "data-src-small", "data-src-webm", "data-src-small-webm", "data-poster"):
        src = re.search(rf'{attr}="([^"]+)"', film).group(1)
        path, _, digest = src.partition("?v=")
        target = out / path
        assert target.exists(), src
        assert digest == hashlib.sha256(target.read_bytes()).hexdigest()[:10]
    assert "film.js" not in (out / "votes.html").read_text(encoding="utf-8")
