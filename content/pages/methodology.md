---
approved: false
title: Methodology
---
## What this site does

Machine Politics records where every United Nations member state stands on autonomous weapons systems. It tracks three signals per state: recorded General Assembly votes, official statements, and national policy documents. Positions are trajectories, not snapshots. The site shows who moved, when, and on what record.

The site takes no position on whether autonomous weapons should be banned or regulated. It records who says what.

## Five signals, never a score

The tracker records five separable signals per state: recorded votes, endorsements of political-commitment instruments, sponsorships of resolutions and working papers, official statements, and national policy. They display side by side. They never merge into a rank, grade, or index. The site triangulates; it does not grade.

**The no-inference rule:** endorsements, sponsorships, and doctrine never produce a position coding by themselves. Endorsing the US Political Declaration is not a position against a binding instrument; Austria endorses it and sponsors the treaty resolution in the same year. Codings derive from statements and votes, with the reasoning shown. The validator enforces this rule in code: a coding whose only evidence is an endorsement, a sponsorship, or a policy document fails the build.

**Endorsement absence:** a state missing from an endorsement list renders as not listed, an absence tier. Not endorsing is not opposing, and the site never colors it as if it were.

## Three signals, three coverage depths

**Votes:** complete. All 193 member states, from the official UN General Assembly voting dataset published by the Dag Hammarskjöld Library. The extraction code, the reconciliation checks, and the committed extract are public in the repository. Nothing is scraped.

**Statements:** deep for a bounded launch set of states, selected by published criteria: vote changers, No votes and abstentions on the most recent resolution, resolution sponsors, states with major-power doctrine, and states that made individual submissions to the Secretary-General. Every other state shows its votes and an explicit coverage notice.

**National policy:** strict scope, major players only. A doctrine entry means a policy document specifically governing autonomy in weapons systems, like DoD Directive 3000.09. Military AI strategies, responsible-AI frameworks, and legislative bills are context notes, never coded evidence.

## The rubric

Every coded position sits on two axes.

Axis A is instrument preference: what kind of international instrument, if any, does the state support? Seven categories: LBI-BAN, LBI-OPEN, REG-SOFT, CCW-ONLY, OPPOSE, AMBIG, NONE. The [rubric page](rubric.html) defines each in plain language. Categories are mutually exclusive at a dated point in time.

Axis B is confidence: EXPLICIT when the state says it directly, INFERRED when the coding rests on interpretation, AMBIGUOUS when the record points in more than one direction, PROVISIONAL when the coding rests on secondary reporting of a primary record this project has not yet verified. A provisional coding says so on its face, carries a note stating exactly what is pending, and is upgraded or corrected once the primary record is reviewed.

AMBIG is a first-class category, not a failure state. When a state's record supports two readings, the coding says so and the evidence shows both. China is the worked example.

A shift event records a state moving from one category to another on a dated record. Shift events are the point of this site. Each one carries the evidence that dates the move.

## Evidence rules

Every coding traces to a quoted, dated, linked primary source. The validator enforces the schema: a verbatim quote of at most 25 words, the document date, a direct link, the source language, the translation status, and a confidence tier.

Translation provenance is explicit. A quote from an official translation says so. A quote from an unofficial translation says so. A source with no translation yields no English quote at all: the entry describes and links the document, and the coding it supports is INFERRED at best.

## What absence means

Absence is tiered, and the tiers never blend.

"No substantive position on record" means this project reviewed the record and found no stated position. "Not yet reviewed by this project" means exactly that. Neither renders as a position.

For national policy, the site only ever makes a dated coverage statement: no published national policy identified by this project, as of a stated date, with a note recording where the project looked. The site never asserts that a state has nothing. The validator rejects that entire class of claim.

## Secondary sources, used honestly

Reputable secondary sources serve three functions here: discovery (finding primary documents), context (citable background, attributed by name), and cross-check (did this project miss something). They are never coding sources. Every coding traces to primary documents. Translations of official documents by research institutes are quoted as unofficial translations with the originals linked. Advocacy-affiliated trackers are consulted as cross-checks only and cited once as related work.

## Links that outlive administrations

Government URLs die when governments change. Every doctrine and endorsement source carries both its live link and an archived snapshot, and the build warns on any entry missing one. Where a live page blocks automated access, the archived capture is the verified record and the page says so.

## Who codes, and how

Walker Robinson is the analyst of record. Tooling drafts, checks, and formats. It never decides. No coded position, shift event, doctrine claim, or analyst sentence publishes without explicit approval, and the site build refuses to ship unapproved content. There is no automated or model-assisted position classification, and the publishing pipeline makes no model calls. The site runs on $0 infrastructure.

## Corrections

Errors get fixed in the open. A superseded coding stays visible with a data-integrity notice. Red on this site carries exactly two meanings: that notice, and the thin seam marking the moment a coded position changed. The [corrections page](corrections.html) lists every correction with dates. If you find an error, open an issue in the repository. The [about page](about.html) says who runs this.

## Related work

Automated Decision Research, the monitoring arm of the Stop Killer Robots campaign, maintains a state-positions tracker at automatedresearch.org. It is the closest existing resource. This project differs in structure: time as a first-class axis, triangulation across votes, statements, and doctrine, and a published rubric with confidence tiers. ADR is consulted as a cross-check only, never as a coding source.

## Sources and licensing

Vote data: © United Nations, used with attribution under the UN Digital Library terms, non-commercial. This project's own coded data: CC BY 4.0. Code: MIT. Details in the repository's DATA_LICENSE.
