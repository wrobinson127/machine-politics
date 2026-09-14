"""UPDATED_THROUGH is the date the record is current to. It ends the board
axis and stamps every "as of" phrase on the site, so if it falls behind the
content it makes the site claim less than it holds, and if it runs ahead it
claims a review that never happened. Both are truth problems, and neither is
visible in a build that succeeds. This holds it to the content."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs


def _approved_dates():
    _, _, states = bs.load_content()
    out = []
    for iso3, cs in states.items():
        for c in cs.get("position_codings") or []:
            if bs.is_approved(c):
                out.append((f"{iso3} coding", bs.iso(c["as_of"])))
        for s in cs.get("shift_events") or []:
            if bs.is_approved(s):
                out.append((f"{iso3} shift", bs.iso(s["date"])))
        d = cs.get("doctrine") or {}
        if bs.is_approved(d) and d.get("as_of"):
            out.append((f"{iso3} doctrine review", bs.iso(d["as_of"])))
    return out


def test_updated_through_is_not_behind_any_approved_record():
    late = [(w, d) for w, d in _approved_dates() if d > config.UPDATED_THROUGH]
    assert not late, (
        f"UPDATED_THROUGH is {config.UPDATED_THROUGH} but approved records "
        f"are dated later: {sorted(late, key=lambda x: x[1])[-5:]}")


def test_updated_through_is_a_date_the_record_actually_reaches():
    """Guards the other direction: the constant must equal the latest
    approved date, not float ahead of it."""
    latest = max(d for _, d in _approved_dates())
    assert config.UPDATED_THROUGH == latest, (
        f"UPDATED_THROUGH is {config.UPDATED_THROUGH}; the latest approved "
        f"record is {latest}. Set the constant to the record, not to a date "
        "nothing was reviewed on.")
