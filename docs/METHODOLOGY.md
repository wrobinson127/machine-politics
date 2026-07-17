# Methodology

*This is the full methodology for Machine Politics ([machinepolitics.walker-robinson.com](https://machinepolitics.walker-robinson.com)). The site's methodology page carries the reader-facing distillation; this document adds the pipeline and verification detail. Status: draft, pending approval by the analyst of record.*

## The claim this project makes

States' positions on autonomous weapons are trajectories, not snapshots. A tracker that shows only where a state stands today hides the most informative events: the moves. Machine Politics makes movement first-class. Shift events are data objects with dates and evidence, and the home page is a board of position bands over time with visible breaks where states moved.

The site takes no position on whether autonomous weapons should be banned or regulated. It records who says what.

## Signals

Three signals per state, with different coverage depths, stated openly:

1. **Recorded votes:** complete for all 193 member states. Source: the UN General Assembly voting dataset, version 5 (February 2026), published by the Dag Hammarskjöld Library. The dataset entered the pipeline by manual download; the UN Digital Library terms forbid automated collection and this project honors that. The extraction filters exactly three resolutions: 78/241 (2023), 79/62 (2024), and 80/57 (2025), the recorded plenary votes on lethal autonomous weapons systems. The extractor refuses to write output if the rows fail reconciliation: 193 rows per resolution, no duplicate states, tallies matching both the expected plenary results and the totals embedded in the dataset itself. The reconciliation evidence is in `docs/verification_report.md`.

2. **Official statements:** deep coverage for a bounded launch set, roughly 45 states, selected in priority order: (a) states that changed their vote across the three resolutions, (b) every No vote and abstention on 80/57, (c) resolution sponsors, (d) a fixed major-power doctrine list, (e) states with individual submissions to the Secretary-General's report A/79/88, until the set is full. Every other state shows its complete vote record plus an explicit coverage notice. The site always states both numbers: states with votes, states with reviewed codings.

3. **National policy:** strict scope. A doctrine entry means a published policy document specifically governing autonomy in weapons systems (the DoD Directive 3000.09 class). Military AI strategies, responsible-AI frameworks, and pending legislation are context annotations, never coded evidence, and the validator rejects any context annotation that tries to carry coding fields. Doctrine review targets the major-power list only.

## The rubric

Axis A, instrument preference, mutually exclusive at a dated point in time:

| Code | Meaning |
|---|---|
| LBI-BAN | Supports a legally binding instrument that includes prohibitions (ban or two-tier) |
| LBI-OPEN | Supports negotiating a legally binding instrument, form unspecified |
| REG-SOFT | Supports new non-binding measures |
| CCW-ONLY | Supports the CCW/GGE consensus process only, outcome left open |
| OPPOSE | Opposes new international instruments; existing IHL suffices |
| AMBIG | Position ambiguous or evolving |
| NONE | No substantive position on record |

Axis B, confidence: EXPLICIT, INFERRED, AMBIGUOUS. Confidence describes how directly the evidence supports the coding. On the site it modulates saturation and a dotted-underline convention. It never changes the category hue.

AMBIG is a finding, not a failure. When a state supports a "ban" while defining the banned class so narrowly that little falls inside it, the honest coding is AMBIG with evidence showing both halves. That case is real and it is one of the three worked examples.

A shift event is `{state, date, from, to, evidence}`. The date marks the evidencing record, which is not always the day the position changed; where those differ, the rationale says so.

## Evidence schema, enforced in code

Every evidence entry carries: a source id resolving to the canonical registry, a verbatim quote of at most 25 words, the document date, a direct URL, the source language, the translation status (official, unofficial, or none), and a confidence tier. `tools/validate_content.py` enforces all of it in CI.

Translation rules: an untranslated non-English source cannot yield an English quote. The entry describes and links the document instead, and any coding resting on it is INFERRED at best. The lang field records the original language of the underlying document; when a state's own official English text is the primary record, the entry says lang en, translation none.

## Absence, precisely

Two absence tiers, never conflated, never rendered as positions:

- `no_position_on_record`: reviewed, nothing substantive found. Requires a search note.
- `not_yet_reviewed`: this project has not looked yet.

Doctrine absence renders only as: "no published national policy identified by this project, as of [date]", with the search note. Copy asserting a state "has no" policy is a prohibited-claim class; the validator rejects it in any phrasing it can catch, and the reviewer catches the rest.

## The approval gate

The analyst of record is Walker Robinson. Tooling drafts and checks; it does not decide. Every claim-bearing entry carries an explicit `approved` flag, authored false. The site build hard-excludes unapproved entries from the deploy artifact, writes a manifest of what rendered, refuses to build if any unapproved entry slipped through, and CI asserts the artifact is byte-identical to a fresh rebuild. A separate preview mode renders drafts behind an unmistakable banner, on localhost only, and never deploys.

There is no automated or model-assisted position classification. The publishing pipeline makes no model calls. The site runs on $0 infrastructure.

## Design rules that carry meaning

- No position category renders red or green, anywhere, including exported images. Coloring a state's position red is an editorial act, so the palette is categorical with no good/bad ordering.
- Saturated red has exactly one meaning: a data-integrity notice.
- AMBIG renders as a hatch texture, not gray and not a blend, because gray means absence.
- Annotations are outlines and markers, never fills.

## Corrections

Corrections are public, dated, and permanent. A superseded coding stays visible under a data-integrity notice. The corrections page starts at zero entries and every entry after that is on the record.

## Related work

Automated Decision Research (automatedresearch.org), the monitoring arm of the Stop Killer Robots campaign, tracks state positions and is the closest existing resource. This project consults it only as a cross-check, never as a coding source, and differs in structure: longitudinal shift tracking, vote-statement-doctrine triangulation, a published rubric, and a neutral analytical register.

## Licensing

- UN-derived vote extracts: © United Nations, non-commercial with attribution, per the UN Digital Library terms.
- This project's coded data: CC BY 4.0.
- Code: MIT.

Full terms and the composite-file rule are in `DATA_LICENSE.md`.
