# Machine Politics

Where every country stands on autonomous weapons: recorded votes, official statements, and national policy, tracked as they shift over time.

Positions are trajectories, not snapshots. This repository builds a static site whose home page is a trajectory board: 193 states as rows, time as the axis, position bands with visible breaks where states moved. Every coding traces to a quoted, dated, linked primary source. The site takes no position on whether autonomous weapons should be banned or regulated. It records who says what.

## How it fits together

```
.scratch/source/          official UN voting dataset (manual download only, never committed)
tools/votes_extract.py    -> data/source/ga_voting_extract.csv.gz  (579 rows + provenance header)
                          -> data/derived/votes.json.gz            (per-state trajectories, ISO alpha-3)
content/                  the claim-bearing layer: rubric, per-state codings, source registry, page prose
tools/validate_content.py enforces the evidence schema, the approval gate, and the prohibited-claim class
tools/build_site.py       -> site/  (static, deterministic, hard-excludes unapproved content)
```

The analyst of record approves every coded position, shift event, doctrine claim, and analyst sentence before it renders. Tooling drafts and checks; it does not decide. The deploy build refuses to ship unapproved content, and CI asserts the committed site is byte-identical to a fresh rebuild.

## Commands

```
pip install -r requirements.txt
python -m pytest tools/tests -q        # full test suite
python tools/validate_content.py       # content schema + claim rules
python tools/votes_extract.py          # rebuild extract + derived votes (needs the source CSV)
python tools/build_site.py             # build the deploy site into site/
python tools/build_site.py --preview   # draft preview with DRAFT banner, .scratch/preview/, localhost only
```

## Data and licensing

Three regimes, split on purpose:

- **UN-derived vote extracts** (`data/`, plus the test fixture): © United Nations, non-commercial with attribution, per the [UN Digital Library terms](https://digitallibrary.un.org/pages/?ln=en&page=tos). The raw dataset is never committed and never fetched by tooling.
- **Project-coded data** (`content/`): CC BY 4.0.
- **Code**: MIT.

Composite files follow the stricter terms. Details in [DATA_LICENSE.md](DATA_LICENSE.md).

## Verification

Phase 0 evidence lives in [docs/verification_report.md](docs/verification_report.md): tally reconciliation for all three resolutions, known-truth vote checks, ISO alpha-3 validation for all 193 states, and the access-posture record for every linked-document host. The methodology is in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).
