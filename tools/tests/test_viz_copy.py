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


def test_a_missing_approval_flag_fails(tmp_path):
    def m(v):
        del v["approved"]
    assert _run(tmp_path, m)
