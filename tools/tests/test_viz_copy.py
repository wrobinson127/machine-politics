"""The figure captions (content/viz.yaml) are claim-bearing copy. Each rule
the validator enforces on them has a passing case and a tampered case."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import validate_content as vc

SRC = config.CONTENT_DIR / "viz.yaml"


def _run(tmp_path, mutate=None):
    viz = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    if mutate:
        mutate(viz)
    path = tmp_path / "viz.yaml"
    path.write_text(yaml.safe_dump(viz, allow_unicode=True), encoding="utf-8")
    errors = vc.Errors()
    vc.check_viz(errors, path)
    return errors.items


def test_the_committed_copy_passes(tmp_path):
    assert _run(tmp_path) == []


def test_a_dash_in_a_caption_fails(tmp_path):
    def m(v):
        v["captions"]["globe"] += " Pale states — not yet reviewed."
    assert _run(tmp_path, m)


def test_an_unknown_placeholder_fails(tmp_path):
    def m(v):
        v["captions"]["vote"] += " {invented}"
    items = _run(tmp_path, m)
    assert any("unknown placeholder {invented}" in i for i in items)


def test_a_missing_caption_fails(tmp_path):
    def m(v):
        del v["captions"]["assembly"]
    items = _run(tmp_path, m)
    assert any("missing caption 'assembly'" in i for i in items)


def test_a_prohibited_absence_claim_fails(tmp_path):
    def m(v):
        v["strands_intro"] = "Pale states have no position on autonomous weapons."
    items = _run(tmp_path, m)
    assert any("prohibited claim" in i for i in items)


def test_the_assembly_position_caption_is_true_of_the_data():
    """The caption is fixed text, so the data must keep it true: in every
    year the Yes block holds every position read except No new rules. If a
    new reading breaks that, this fails and the caption is rewritten."""
    from tools import build_site as bs
    viz = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    if "except No new rules" not in viz["captions"]["assembly_position"]:
        return
    states = {p.stem: bs.load_yaml(p) for p in config.CONTENT_DIR.joinpath("states").glob("*.yaml")}
    rows = bs.viz.payload(bs.load_votes(), states, False, bs.current_position,
                          lambda i, e, c: i, bs.iso)
    read = {r["p"] for r in rows if r["p"] and r["p"] != "NONE"}
    for y in range(len(config.LAWS_RESOLUTIONS)):
        yes = {r["p"] for r in rows if r["p"] and r["p"] != "NONE" and r["v"][y] == "Y"}
        assert yes == read - {"OPPOSE"}, (y, sorted(read - yes))


def test_a_missing_approval_flag_fails(tmp_path):
    def m(v):
        del v["approved"]
    assert _run(tmp_path, m)


LANDING = config.CONTENT_DIR / "landing.yaml"


def _landing(tmp_path, mutate=None):
    data = yaml.safe_load(LANDING.read_text(encoding="utf-8"))
    if mutate:
        mutate(data)
    path = tmp_path / "landing.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    errors = vc.Errors()
    vc.check_landing(errors, path)
    return errors.items


def test_the_committed_landing_copy_passes(tmp_path):
    assert _landing(tmp_path) == []


def test_landing_copy_with_a_dash_fails(tmp_path):
    def m(d):
        d["count_caption"] = "of 193 countries read \u2014 every position sourced"
    assert _landing(tmp_path, m)


def test_landing_copy_missing_a_key_fails(tmp_path):
    def m(d):
        del d["conference_line"]
    assert any("conference_line" in i for i in _landing(tmp_path, m))


def test_landing_copy_with_an_absence_claim_fails(tmp_path):
    def m(d):
        d["count_caption"] = "of 193 countries read; many have no position"
    assert any("prohibited claim" in i for i in _landing(tmp_path, m))
