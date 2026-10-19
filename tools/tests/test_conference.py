"""The Review Conference page: approval-gated as a page and per entry, one
section per conference day, honest wording for a day with no entries, and
no nav link to a page the same build did not produce."""

import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs
from tools import validate_content as vc

DAYS = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]


def _conf(page_ok, entries):
    return {
        "approved": page_ok,
        "title": "The Review Conference",
        "intro": "Test intro.",
        "events": entries,
    }


def _entry(eid, day, ok, **kw):
    e = {"id": eid, "date": day, "kind": "document", "title": f"Entry {eid}",
         "text": f"Text for {eid}.", "approved": ok,
         "links": [{"label": "Official record", "url": "https://docs.un.org/x"}]}
    e.update(kw)
    return e


def _build(tmp_path, monkeypatch, conf, preview):
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    (work / "conference.yaml").write_text(yaml.safe_dump(conf, sort_keys=False),
                                          encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", work)
    out = tmp_path / ("pre" if preview else "dep")
    manifest = bs.build(out, preview=preview)
    return out, manifest


def test_unapproved_page_ships_nothing(tmp_path, monkeypatch):
    conf = _conf(False, [_entry("a", "2026-11-16", True)])
    out, manifest = _build(tmp_path, monkeypatch, conf, preview=False)
    assert not (out / "conference.html").exists()
    for f in ("index.html", "votes.html", "state/USA.html"):
        assert "conference.html" not in (out / f).read_text(encoding="utf-8")
    assert manifest["unapproved_rendered"] == 0


def test_approved_page_shows_only_approved_entries(tmp_path, monkeypatch):
    conf = _conf(True, [_entry("shown", "2026-11-17", True),
                        _entry("hidden", "2026-11-18", False),
                        _entry("background-x", "2026-09-05", True)])
    out, manifest = _build(tmp_path, monkeypatch, conf, preview=False)
    page = (out / "conference.html").read_text(encoding="utf-8")
    assert "Entry shown" in page and "Entry background-x" in page
    assert "Entry hidden" not in page
    assert "DRAFT" not in page
    assert page.index("Entry background-x") < page.index('id="day-2026-11-16"')
    for day in DAYS:
        assert f'id="day-{day}"' in page
    # A day without entries says the site has not added any, never that
    # nothing happened.
    assert page.count("This site has not added entries for this day yet.") == 4
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="conference.html"' in index
    assert manifest["unapproved_rendered"] == 0


def test_preview_shows_drafts_with_chip(tmp_path, monkeypatch):
    conf = _conf(False, [_entry("draft", "2026-11-19", False, state="RUS")])
    out, _ = _build(tmp_path, monkeypatch, conf, preview=True)
    page = (out / "conference.html").read_text(encoding="utf-8")
    assert "Entry draft" in page and "DRAFT" in page
    assert 'href="state/RUS.html"' in page


def _validate(tmp_path, conf):
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    (work / "conference.yaml").write_text(yaml.safe_dump(conf, sort_keys=False),
                                          encoding="utf-8")
    return vc.validate(work)


def test_validator_accepts_a_good_log(tmp_path):
    errors = _validate(tmp_path, _conf(False, [_entry("ok", "2026-11-16", False)]))
    assert not [e for e in errors.items if e.startswith("conference.yaml")]


@pytest.mark.parametrize("bad, needle", [
    ({"links": []}, "links at least one"),
    ({"text": "A pause — then more."}, "em dash"),
    ({"state": "XYZ"}, "member-state code"),
    ({"kind": "opinion"}, "kind must be"),
    ({"approved": "yes"}, "approved"),
    ({"text": '"' + " ".join(["word"] * 26) + '"'}, "25 words"),
    ({"text": "Russia has no position on this."}, "prohibited claim"),
])
def test_validator_rejects_bad_entries(tmp_path, bad, needle):
    errors = _validate(tmp_path, _conf(False, [_entry("bad", "2026-11-16", False, **bad)]))
    assert any(needle in e for e in errors.items), errors.items


def test_before_the_conference_one_line_replaces_five_empty_days(tmp_path, monkeypatch):
    conf = _conf(True, [_entry("background-only", "2026-09-04", True)])
    out, _ = _build(tmp_path, monkeypatch, conf, preview=False)
    page = (out / "conference.html").read_text(encoding="utf-8")
    assert "Daily entries begin on 16 November" in page
    assert 'id="day-2026-11-16"' not in page
    assert "This site has not added entries for this day yet." not in page
