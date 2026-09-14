"""NONE is a coverage statement, never a position (config invariant 6). Its
as_of is the date the record was reviewed, not a date a position began, so
the band it draws must cover the record rather than start on the review date.

Before this, a NONE coding dated after UPDATED_THROUGH clamped to the end of
the track, computed zero width, and vanished: five states coded on the record
and blank on the board. Anchoring NONE at the origin makes the axis end
irrelevant to it and keeps the review date true.
"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import build_site as bs


def _none(as_of, confidence="INFERRED"):
    return {"code": "NONE", "as_of": as_of, "confidence": confidence,
            "approved": True}


def test_none_alone_covers_the_whole_track():
    (band,) = bs.compute_bands([_none("2026-07-17")])
    assert band["code"] == "NONE"
    assert band["left"] == 0.0
    assert band["width"] == float(bs.TRACK_W)
    assert band["since"] == "2026-07-17"  # the review date, kept for the label


def test_none_dated_after_the_axis_still_renders():
    """The failure this exists for: five real states were once dated after
    the axis end and vanished from the board."""
    past = bs.iso(bs.T1 + timedelta(days=160))
    bands = bs.compute_bands([_none(past)])
    assert len(bands) == 1, "a NONE past the axis end was dropped"
    assert bands[0]["width"] == float(bs.TRACK_W)


def test_none_runs_up_to_the_first_substantive_coding():
    """If a real coding follows, NONE covers the record before it and the
    substantive coding takes over from its own date, whatever order the two
    as_of dates fall in."""
    codings = [
        {"code": "LBI-BAN", "as_of": "2024-05-01", "confidence": "EXPLICIT",
         "approved": True},
        _none("2026-07-17"),  # reviewed later, but covers the earlier record
    ]
    bands = {b["code"]: b for b in bs.compute_bands(codings)}
    assert set(bands) == {"NONE", "LBI-BAN"}
    boundary = bs.x_of("2024-05-01")
    assert bands["NONE"]["left"] == 0.0
    assert bands["NONE"]["width"] == boundary
    assert bands["LBI-BAN"]["left"] == boundary
    assert bands["LBI-BAN"]["left"] + bands["LBI-BAN"]["width"] == float(bs.TRACK_W)


def test_substantive_codings_are_unchanged():
    """The origin anchor is for NONE only. A real coding still starts on its
    date and a real coding past the axis still drops, so the past-axis
    warning keeps its meaning."""
    codings = [{"code": "REG-SOFT", "as_of": "2023-02-16", "confidence": "EXPLICIT",
                "approved": True}]
    (band,) = bs.compute_bands(codings)
    assert band["left"] == bs.x_of("2023-02-16")
    past = bs.iso(bs.T1 + timedelta(days=90))
    assert bs.compute_bands([{"code": "REG-SOFT", "as_of": past,
                              "confidence": "EXPLICIT", "approved": True}]) == []


def _real_entry():
    """A real vote entry: the row renderers read a vote for every resolution,
    so a minimal stub raises before it reaches the band."""
    votes = bs.load_votes()
    return votes["states"]["PRK"], votes["resolutions"]


def test_the_board_labels_none_as_a_review_not_a_start():
    entry, resolutions = _real_entry()
    html = bs.row_track_html("PRK", entry, resolutions, [_none("2026-07-17")], [])
    assert "no substantive position on record, reviewed as of 2026-07-17" in html
    assert "NONE since" not in html
    assert "left:0.00%;width:100.00%" in html


def test_the_tour_canvas_anchors_none_at_the_origin():
    entry, resolutions = _real_entry()
    html = bs.canvas_row_html(
        "PRK", entry, resolutions,
        {"position_codings": [_none("2026-07-17")]}, preview=False)
    assert 'data-code="NONE"' in html
    assert "left:5.0%;width:90.00%" in html  # the canvas margins, edge to edge


def test_the_past_axis_warning_ignores_none():
    past = bs.iso(bs.T1 + timedelta(days=90))
    states = {"AAA": {"position_codings": [_none(past)]}}
    assert bs.report_codings_past_axis(states) == []
