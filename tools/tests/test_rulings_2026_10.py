"""Analyst ruling R1 (2026-10-19): the UN's automatic meeting transcripts
are not official records. Evidence from one is INFERRED at most, is never
the only evidence for a shift, and is labelled as a transcript wherever its
citation renders."""

import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import validate_content as vc


def _sources():
    return yaml.safe_load((config.CONTENT_DIR / "sources.yaml").read_text(
        encoding="utf-8"))["sources"]


def test_every_transcript_source_says_so_in_its_title():
    for s in _sources():
        if s["type"] == "transcript":
            assert "transcript" in s["title"].lower(), s["id"]


def _work(tmp_path):
    work = tmp_path / "content"
    shutil.copytree(config.CONTENT_DIR, work)
    return work


def _transcript_id():
    return next(s["id"] for s in _sources() if s["type"] == "transcript")


def test_validator_caps_transcript_evidence_at_inferred(tmp_path):
    work = _work(tmp_path)
    p = work / "states" / "UKR.yaml"
    text = p.read_text(encoding="utf-8")
    assert "confidence: INFERRED" in text
    p.write_text(text.replace("        confidence: INFERRED", "        confidence: EXPLICIT", 1),
                 encoding="utf-8")
    errors = vc.validate(work).items
    assert any("caps evidence confidence at INFERRED" in e for e in errors), errors


def test_validator_rejects_a_shift_resting_on_transcripts_alone(tmp_path):
    work = _work(tmp_path)
    p = work / "states" / "BRA.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    tid = _transcript_id()
    shift = data["shift_events"][0]
    for e in shift["evidence"]:
        e["source"] = tid
        e["confidence"] = "INFERRED"
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    errors = vc.validate(work).items
    assert any("machine transcripts alone" in e for e in errors), errors


def test_live_content_obeys_r1():
    assert vc.validate().items == []
