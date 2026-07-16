"""Sanity checks on config invariants that everything downstream assumes."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config


def test_position_categories_complete_and_ordered():
    assert list(config.POSITION_CATEGORIES) == [
        "LBI-BAN", "LBI-OPEN", "REG-SOFT", "CCW-ONLY", "OPPOSE", "AMBIG", "NONE",
    ]


def test_no_valence_hues_on_positions():
    """No position color may read red or green (invariant 5).

    Heuristic: reject hues where the red or green channel dominates both
    others by a wide margin. AMBIG and not_yet_reviewed carry no hue at all.
    """
    for code, hexval in config.PALETTE["positions"].items():
        if hexval is None:
            assert code in ("AMBIG",)
            continue
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", hexval), (code, hexval)
        r, g, b = (int(hexval[i : i + 2], 16) for i in (1, 3, 5))
        assert not (r > g + 60 and r > b + 60), f"{code} reads red: {hexval}"
        assert not (g > r + 60 and g > b + 60), f"{code} reads green: {hexval}"


def test_ambig_has_no_fill_hue():
    assert config.PALETTE["positions"]["AMBIG"] is None
    assert config.PALETTE["not_yet_reviewed"] is None


def test_absence_tiers_distinct():
    assert len(set(config.ABSENCE_TIERS)) == 2
    assert config.DOCTRINE_ABSENCE not in config.POSITION_CATEGORIES


def test_expected_tallies():
    assert config.LAWS_RESOLUTIONS["78/241"]["tally"] == (152, 4, 11)
    assert config.LAWS_RESOLUTIONS["79/62"]["tally"] == (166, 3, 15)
    assert config.LAWS_RESOLUTIONS["80/57"]["tally"] == (164, 6, 7)
