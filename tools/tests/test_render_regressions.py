"""Small rendering regressions found by the 2026-10-19 gauntlet."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import build_site as bs


@pytest.fixture(scope="module")
def deploy(tmp_path_factory):
    out = tmp_path_factory.mktemp("deploy")
    bs.build(out, preview=False)
    return out


def test_resolution_symbols_are_not_double_prefixed(deploy):
    for f in deploy.rglob("*.html"):
        assert "A/RES/A/RES/" not in f.read_text(encoding="utf-8"), f.name


def test_every_page_carries_the_byline(deploy):
    for name in ("index.html", "votes.html", "state/USA.html", "404.html"):
        text = (deploy / name).read_text(encoding="utf-8")
        assert "researched and written by" in text and "Walker Robinson" in text, name
