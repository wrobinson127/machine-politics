"""P1b tests: the five-signal schemas and the validator rules that guard
them. Every enforced rule has a passing case and a failing case."""

import copy
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import validate_content as vc
from tools.tests.test_validate_content import (
    RUBRIC_SRC, VALID_EVIDENCE, VALID_STATE, VALID_SOURCES,
)


def write_base(tmp_path):
    (tmp_path / "states").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources.yaml").write_text(
        yaml.safe_dump(VALID_SOURCES, allow_unicode=True), encoding="utf-8"
    )
    (tmp_path / "rubric.yaml").write_text(
        RUBRIC_SRC.read_text(encoding="utf-8"), encoding="utf-8"
    )


VALID_INSTRUMENT = {
    "id": "us-political-declaration",
    "name": "Political Declaration on Responsible Military Use of AI and Autonomy",
    "date": "2023-02-16",
    "list_source_url": "https://www.state.gov/example",
    "list_source_archived": "http://web.archive.org/web/20241219/https://www.state.gov/example",
    "list_as_of": "2024-11-27",
    "approved": False,
    "states": [
        {"iso3": "DEU", "status": "endorsed", "date": "2023-02-16"},
        {"iso3": "CHN", "status": "not_listed"},
    ],
}


def endorsement_errors(tmp_path, mutate=None):
    write_base(tmp_path)
    inst = copy.deepcopy(VALID_INSTRUMENT)
    if mutate:
        mutate(inst)
    (tmp_path / "endorsements.yaml").write_text(
        yaml.safe_dump({"instruments": [inst]}, allow_unicode=True), encoding="utf-8"
    )
    return vc.validate(tmp_path)


def test_valid_endorsements_pass(tmp_path):
    result = endorsement_errors(tmp_path)
    assert result.items == []


def test_endorsement_bad_status_rejected(tmp_path):
    def mutate(inst):
        inst["states"][0]["status"] = "opposed"  # not a thing: not endorsing is not opposing
    errs = endorsement_errors(tmp_path, mutate).items
    assert any("status must be one of" in e for e in errs)


def test_non_endorsement_needs_documentation(tmp_path):
    def mutate(inst):
        inst["states"][0] = {"iso3": "CHN", "status": "documented_non_endorsement"}
    errs = endorsement_errors(tmp_path, mutate).items
    assert any("documented_non_endorsement needs evidence" in e for e in errs)


def test_non_member_endorser_needs_note(tmp_path):
    def mutate(inst):
        inst["states"].append({"iso3": "XKX", "status": "endorsed"})
    errs = endorsement_errors(tmp_path, mutate).items
    assert any("non_member_note" in e for e in errs)

    def mutate_ok(inst):
        inst["states"].append(
            {"iso3": "XKX", "status": "endorsed",
             "non_member_note": "Kosovo appears on the official list; no ISO code; not a UN member state."}
        )
    assert endorsement_errors(tmp_path, mutate_ok).items == []


def test_missing_archived_is_warning_not_error(tmp_path):
    def mutate(inst):
        del inst["list_source_archived"]
    result = endorsement_errors(tmp_path, mutate)
    assert result.items == []
    assert any("archived" in w for w in result.warnings)


def test_sponsorship_schema(tmp_path):
    write_base(tmp_path)
    record = {
        "instrument_id": "co-sponsors-80-57",
        "name": "Co-sponsors of A/C.1/80/L.41 as tabled",
        "date": "2025-10-14",
        "url": "https://documents.un.org/api/symbol/access?s=A/C.1/80/L.41&l=en",
        "archived": "http://web.archive.org/web/20260717/https://example",
        "approved": False,
        "members": ["AUT", "BEL", "BRA"],
    }
    (tmp_path / "sponsorships.yaml").write_text(
        yaml.safe_dump({"records": [record]}, allow_unicode=True), encoding="utf-8"
    )
    assert vc.validate(tmp_path).items == []
    record["members"].append("ZZZ")
    (tmp_path / "sponsorships.yaml").write_text(
        yaml.safe_dump({"records": [record]}, allow_unicode=True), encoding="utf-8"
    )
    errs = vc.validate(tmp_path).items
    assert any("'ZZZ' not a UN member state" in e for e in errs)


def test_eras_schema_and_causal_ban(tmp_path):
    write_base(tmp_path)
    eras_dir = tmp_path / "eras"
    eras_dir.mkdir()
    (eras_dir / "USA.yaml").write_text(
        yaml.safe_dump({"eras": [
            {"label": "Biden administration", "start": "2021-01-20",
             "end": "2025-01-20", "source": "https://example.gov"},
        ]}), encoding="utf-8",
    )
    assert vc.validate(tmp_path).items == []
    (eras_dir / "USA.yaml").write_text(
        yaml.safe_dump({"eras": [
            {"label": "Biden administration, because policy changed",
             "start": "2021-01-20", "source": "https://example.gov"},
        ]}), encoding="utf-8",
    )
    errs = vc.validate(tmp_path).items
    assert any("causal copy is prohibited" in e for e in errs)


def test_no_inference_rule(tmp_path):
    """Invariant 10: a coding backed only by doctrine/endorsement/sponsorship
    sources is rejected; adding a statement source makes it valid."""
    write_base(tmp_path)
    sources = copy.deepcopy(VALID_SOURCES)
    sources["sources"].append(
        {"id": "some-statement", "title": "GGE statement", "publisher": "X",
         "date": "2023-03-01", "url": "https://docs-library.unoda.org/x.pdf",
         "type": "statement", "lang": "en", "accessed": "2026-07-17"}
    )
    (tmp_path / "sources.yaml").write_text(
        yaml.safe_dump(sources, allow_unicode=True), encoding="utf-8"
    )
    state = copy.deepcopy(VALID_STATE)
    # dod-3000-09 has type: policy; make it the coding's only evidence
    policy_evidence = dict(
        VALID_EVIDENCE,
        source="dod-3000-09",
        url="https://www.esd.whs.mil/portals/54/documents/dd/issuances/dodd/300009p.pdf",
        date="2023-01-25",
    )
    state["position_codings"][0]["evidence"] = [policy_evidence]
    del state["shift_events"]
    (tmp_path / "states" / "USA.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )
    errs = vc.validate(tmp_path).items
    assert any("no-inference rule" in e for e in errs)

    state["position_codings"][0]["evidence"].append(
        dict(VALID_EVIDENCE, source="some-statement",
             url="https://docs-library.unoda.org/x.pdf")
    )
    (tmp_path / "states" / "USA.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )
    assert not any("no-inference rule" in e for e in vc.validate(tmp_path).items)


def test_eov_evidence_kind(tmp_path):
    write_base(tmp_path)
    state = copy.deepcopy(VALID_STATE)
    state["position_codings"][0]["evidence"][0]["kind"] = "eov"
    (tmp_path / "states" / "USA.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )
    errs = [e for e in vc.validate(tmp_path).items if "kind" in e]
    assert errs == []
    state["position_codings"][0]["evidence"][0]["kind"] = "vibe"
    (tmp_path / "states" / "USA.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )
    assert any("evidence kind must be one of" in e for e in vc.validate(tmp_path).items)


def test_dated_context_instrument_needs_url(tmp_path):
    write_base(tmp_path)
    state = copy.deepcopy(VALID_STATE)
    state["doctrine"]["context"] = [
        {"note": "Executive order on AI.", "date": "2023-10-30"}
    ]
    (tmp_path / "states" / "USA.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )
    errs = vc.validate(tmp_path).items
    assert any("dated context instrument needs a url" in e for e in errs)


def test_malformed_rows_report_instead_of_crashing(tmp_path):
    """P1b review REJECT: non-dict entries must produce itemized errors."""
    write_base(tmp_path)
    (tmp_path / "endorsements.yaml").write_text(
        "instruments:\n  - just-a-string\n", encoding="utf-8"
    )
    (tmp_path / "sponsorships.yaml").write_text(
        "records:\n  - also-a-string\n", encoding="utf-8"
    )
    state = copy.deepcopy(VALID_STATE)
    state["position_codings"] = ["not-a-mapping"]
    del state["shift_events"]
    (tmp_path / "states" / "USA.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8"
    )
    errs = vc.validate(tmp_path).items  # must not raise
    assert sum("must be a mapping" in e for e in errs) == 3


def test_score_keys_rejected_everywhere(tmp_path):
    """Invariant 13 tripwire: the schema layer refuses to hold a score."""
    def mutate(inst):
        inst["states"][0]["score"] = 9.5
    errs = endorsement_errors(tmp_path, mutate).items
    assert any("invariant 13" in e for e in errs)


def test_iso3_format_enforced_despite_note(tmp_path):
    def mutate(inst):
        inst["states"][0] = {"iso3": "deu", "status": "endorsed",
                             "non_member_note": "laundering attempt"}
    errs = endorsement_errors(tmp_path, mutate).items
    assert any("uppercase alpha-3" in e for e in errs)


def test_causal_net_extended(tmp_path):
    write_base(tmp_path)
    eras_dir = tmp_path / "eras"
    eras_dir.mkdir()
    (eras_dir / "USA.yaml").write_text(
        yaml.safe_dump({"eras": [
            {"label": "Reforms resulting in change", "start": "2021-01-20",
             "source": "https://example.gov"},
        ]}), encoding="utf-8",
    )
    errs = vc.validate(tmp_path).items
    assert any("causal copy is prohibited" in e for e in errs)


def test_real_content_still_validates():
    result = vc.validate()
    assert result.items == []
