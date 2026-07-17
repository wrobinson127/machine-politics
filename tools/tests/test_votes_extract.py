"""Tests for the votes extraction pipeline.

The fixture is a real-sample cut of the official dataset: all 579 rows of
the three LAWS resolutions plus 12 real non-LAWS rows that the extractor
must ignore. Nothing here is synthetic.
"""

import copy
import csv
import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import votes_extract as vx

FIXTURE = Path(__file__).parent / "fixtures" / "ga_voting_sample.csv"


def load_fixture_rows():
    rows_by_res = {key: [] for key in config.LAWS_RESOLUTIONS}
    with open(FIXTURE, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = vx.TARGET_RESOLUTIONS.get(row["resolution"])
            if key is not None:
                rows_by_res[key].append(row)
    return rows_by_res


@pytest.fixture(scope="module")
def rows_by_res():
    return load_fixture_rows()


def test_fixture_filters_non_laws_rows(rows_by_res):
    total = sum(len(v) for v in rows_by_res.values())
    assert total == 579
    with open(FIXTURE, encoding="utf-8", newline="") as f:
        all_rows = list(csv.DictReader(f))
    assert len(all_rows) == 591  # 579 LAWS + 12 real non-LAWS rows ignored


def test_reconcile_passes_on_real_rows(rows_by_res):
    vx.reconcile(rows_by_res)


def test_reconcile_rejects_flipped_vote(rows_by_res):
    tampered = copy.deepcopy(rows_by_res)
    row = next(r for r in tampered["78/241"] if r["ms_vote"] == "Y")
    row["ms_vote"] = "N"
    with pytest.raises(vx.ExtractionError, match="tally"):
        vx.reconcile(tampered)


def test_reconcile_rejects_missing_row(rows_by_res):
    tampered = copy.deepcopy(rows_by_res)
    tampered["79/62"].pop()
    with pytest.raises(vx.ExtractionError, match="193"):
        vx.reconcile(tampered)


def test_reconcile_rejects_duplicate_state(rows_by_res):
    tampered = copy.deepcopy(rows_by_res)
    tampered["80/57"][0] = copy.deepcopy(tampered["80/57"][1])
    with pytest.raises(vx.ExtractionError, match="duplicate|193"):
        vx.reconcile(tampered)


def test_reconcile_rejects_unknown_vote_value(rows_by_res):
    tampered = copy.deepcopy(rows_by_res)
    tampered["78/241"][0]["ms_vote"] = "Z"
    with pytest.raises(vx.ExtractionError, match="unexpected vote value"):
        vx.reconcile(tampered)


def test_extract_carries_provenance_header(rows_by_res, tmp_path):
    out = tmp_path / "extract.csv.gz"
    vx.write_extract(rows_by_res, out)
    with gzip.open(out, "rt", encoding="utf-8") as f:
        text = f.read()
    comments = [ln for ln in text.splitlines() if ln.startswith("#")]
    joined = " ".join(comments)
    assert "United Nations" in joined
    assert config.UN_DATASET_RECORD_URL in joined
    assert config.UN_DATASET_DOWNLOADED_ON in joined
    assert "Non-commercial" in joined


def test_extract_round_trip_reproduces_derived(rows_by_res, tmp_path):
    out = tmp_path / "extract.csv.gz"
    vx.write_extract(rows_by_res, out)
    direct = vx.build_derived(rows_by_res)
    rt_rows = {key: [] for key in config.LAWS_RESOLUTIONS}
    for row in vx.read_extract(out):
        rt_rows[vx.TARGET_RESOLUTIONS[row["resolution"]]].append(row)
    vx.reconcile(rt_rows)
    assert vx.build_derived(rt_rows) == direct


def test_derived_structure_and_guard(rows_by_res):
    derived = vx.build_derived(rows_by_res)
    vx.check_derived(derived)  # raises on any gap
    assert len(derived["states"]) == 193
    assert list(derived["states"]) == sorted(derived["states"])
    assert set(derived["resolutions"]) == set(config.LAWS_RESOLUTIONS)
    for res in derived["resolutions"].values():
        assert res["undl_link"].startswith("https://digitallibrary.un.org/")


def test_known_truth_votes_in_derived(rows_by_res):
    states = vx.build_derived(rows_by_res)["states"]
    assert states["IND"]["votes"] == {"78/241": "N", "79/62": "A", "80/57": "Y"}
    assert states["USA"]["votes"] == {"78/241": "Y", "79/62": "Y", "80/57": "N"}
    assert states["POL"]["votes"] == {"78/241": "Y", "79/62": "A", "80/57": "A"}
    assert states["RUS"]["votes"] == {"78/241": "N", "79/62": "N", "80/57": "N"}
    assert states["TUR"]["un_name"] == "TÜRKİYE"


def test_gz_output_is_deterministic(rows_by_res, tmp_path):
    a, b = tmp_path / "a.gz", tmp_path / "b.gz"
    vx.write_extract(rows_by_res, a)
    vx.write_extract(rows_by_res, b)
    assert a.read_bytes() == b.read_bytes()
    da, db = tmp_path / "da.gz", tmp_path / "db.gz"
    derived = vx.build_derived(rows_by_res)
    vx.write_derived(derived, da)
    vx.write_derived(derived, db)
    assert da.read_bytes() == db.read_bytes()
