"""Tests for the content validator: every enforced invariant has a case
that passes and a tampered case that must fail."""

import copy
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import validate_content as vc

RUBRIC_SRC = Path(__file__).resolve().parents[2] / "content" / "rubric.yaml"

VALID_SOURCES = {
    "sources": [
        {
            "id": "dod-3000-09",
            "title": "DoD Directive 3000.09, Autonomy in Weapon Systems",
            "publisher": "United States Department of Defense",
            "date": "2023-01-25",
            "url": "https://www.esd.whs.mil/portals/54/documents/dd/issuances/dodd/300009p.pdf",
            "type": "policy",
            "lang": "en",
            "accessed": "2026-07-16",
        }
    ]
}

VALID_EVIDENCE = {
    "source": "dod-3000-09",
    "quote": "Autonomous and semi-autonomous weapon systems will be designed to allow commanders and operators to exercise appropriate levels of human judgment over the use of force.",
    "date": "2023-01-25",
    "url": "https://www.esd.whs.mil/portals/54/documents/dd/issuances/dodd/300009p.pdf",
    "lang": "en",
    "translation": "none",
    "confidence": "EXPLICIT",
}

VALID_STATE = {
    "iso3": "USA",
    "un_name": "UNITED STATES",
    "display_name": "United States",
    "position_codings": [
        {
            "code": "REG-SOFT",
            "confidence": "EXPLICIT",
            "as_of": "2023-02-16",
            "approved": False,
            "evidence": [VALID_EVIDENCE],
        }
    ],
    "shift_events": [
        {
            "state": "USA",
            "date": "2025-12-01",
            "from": "REG-SOFT",
            "to": "OPPOSE",
            "approved": False,
            "evidence": [VALID_EVIDENCE],
        }
    ],
    "doctrine": {
        "status": "policy_identified",
        "approved": False,
        "entries": [
            {
                "title": "DoD Directive 3000.09",
                "approved": False,
                "evidence": [VALID_EVIDENCE],
            }
        ],
    },
}


def write_tree(tmp_path, state=VALID_STATE, sources=VALID_SOURCES):
    (tmp_path / "states").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources.yaml").write_text(
        yaml.safe_dump(sources, allow_unicode=True), encoding="utf-8"
    )
    (tmp_path / "rubric.yaml").write_text(
        RUBRIC_SRC.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "states" / f"{state['iso3']}.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )


def errors_for(tmp_path, mutate=None):
    state = copy.deepcopy(VALID_STATE)
    if mutate:
        mutate(state)
    write_tree(tmp_path, state)
    return vc.validate(tmp_path).items


def test_valid_tree_passes(tmp_path):
    assert errors_for(tmp_path) == []


def test_real_content_dir_validates():
    errors = vc.validate()
    assert errors.items == []


def test_quote_over_25_words_rejected(tmp_path):
    def mutate(s):
        s["position_codings"][0]["evidence"][0] = dict(
            VALID_EVIDENCE, quote=" ".join(["word"] * 26)
        )
    errs = errors_for(tmp_path, mutate)
    assert any("exceeds 25 words" in e for e in errs)


def test_untranslated_foreign_quote_rejected(tmp_path):
    def mutate(s):
        s["position_codings"][0]["evidence"][0] = dict(
            VALID_EVIDENCE, lang="zh", translation="none"
        )
    errs = errors_for(tmp_path, mutate)
    assert any("cannot carry a quote" in e for e in errs)


def test_untranslated_foreign_source_capped_below_explicit(tmp_path):
    def mutate(s):
        ev = dict(VALID_EVIDENCE, lang="zh", translation="none", description="Position paper.")
        del ev["quote"]
        s["position_codings"][0]["evidence"][0] = ev
    errs = errors_for(tmp_path, mutate)
    assert any("caps confidence at INFERRED" in e for e in errs)


def test_missing_approved_rejected(tmp_path):
    def mutate(s):
        del s["position_codings"][0]["approved"]
    errs = errors_for(tmp_path, mutate)
    assert any("approved" in e for e in errs)


def test_prohibited_claim_rejected(tmp_path):
    def mutate(s):
        s["position_codings"][0]["rationale"] = "The state has no national policy on autonomy in weapons."
        s["position_codings"][0]["approved"] = False
    errs = errors_for(tmp_path, mutate)
    assert any("prohibited claim" in e for e in errs)


def test_prohibited_claim_variants_rejected(tmp_path):
    for phrase in (
        "This state does not have a policy on the matter.",
        "No national policy exists in this country.",
        "The government lacks a stated position on the issue.",
    ):
        def mutate(s, p=phrase):
            s["position_codings"][0]["rationale"] = p
        errs = errors_for(tmp_path, mutate)
        assert any("prohibited claim" in e for e in errs), phrase


def test_coverage_statement_is_allowed(tmp_path):
    def mutate(s):
        s["doctrine"] = {
            "status": "no_policy_identified",
            "approved": False,
            "as_of": "2026-07-16",
            "search_note": "Searched defense ministry publications and UNODA submissions.",
        }
    assert errors_for(tmp_path, mutate) == []


def test_doctrine_absence_requires_as_of_and_search_note(tmp_path):
    def mutate(s):
        s["doctrine"] = {"status": "no_policy_identified", "approved": False}
    errs = errors_for(tmp_path, mutate)
    assert any("as_of" in e for e in errs)
    assert any("search_note" in e for e in errs)


def test_unknown_code_rejected(tmp_path):
    def mutate(s):
        s["position_codings"][0]["code"] = "BANNED"
    errs = errors_for(tmp_path, mutate)
    assert any("unknown Axis A code" in e for e in errs)


def test_shift_event_same_category_rejected(tmp_path):
    def mutate(s):
        s["shift_events"][0]["to"] = s["shift_events"][0]["from"]
    errs = errors_for(tmp_path, mutate)
    assert any("from == to" in e for e in errs)


def test_shift_event_state_mismatch_rejected(tmp_path):
    def mutate(s):
        s["shift_events"][0]["state"] = "CAN"
    errs = errors_for(tmp_path, mutate)
    assert any("!= file state" in e for e in errs)


def test_unregistered_source_rejected(tmp_path):
    def mutate(s):
        s["position_codings"][0]["evidence"][0] = dict(VALID_EVIDENCE, source="ghost")
    errs = errors_for(tmp_path, mutate)
    assert any("not in sources.yaml" in e for e in errs)


def test_iso3_not_in_votes_rejected(tmp_path):
    state = copy.deepcopy(VALID_STATE)
    state["iso3"] = "ZZZ"
    state["shift_events"][0]["state"] = "ZZZ"
    write_tree(tmp_path, state)
    errs = vc.validate(tmp_path).items
    assert any("not present in derived votes data" in e for e in errs)


def test_none_coding_requires_search_note(tmp_path):
    def mutate(s):
        s["position_codings"][0] = {
            "code": "NONE",
            "confidence": "EXPLICIT",
            "as_of": "2026-07-16",
            "approved": False,
        }
        del s["shift_events"]
    errs = errors_for(tmp_path, mutate)
    assert any("search_note" in e for e in errs)


def test_context_annotation_with_coding_fields_rejected(tmp_path):
    def mutate(s):
        s["doctrine"]["context"] = [
            {"note": "National AI strategy, context only.", "code": "REG-SOFT"}
        ]
    errs = errors_for(tmp_path, mutate)
    assert any("strict scope" in e for e in errs)
