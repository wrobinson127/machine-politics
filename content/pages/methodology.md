---
approved: true
title: Methodology
---
## What this site does

Machine Politics records where every United Nations member state stands on autonomous weapons systems. It tracks five signals per state: recorded General Assembly votes, endorsements of political-commitment instruments, sponsorships of resolutions and working papers, official statements, and national policy documents. Positions are trajectories, not snapshots. The site shows who moved, when, and on what record.

The site takes no position on whether autonomous weapons should be banned or regulated. It records who says what.

## Five signals, never a score

The tracker records five separable signals per state: recorded votes, endorsements of political-commitment instruments, sponsorships of resolutions and working papers, official statements, and national policy. They display side by side. They never merge into a rank, grade, or index. The site triangulates; it does not grade.

**The no-inference rule:** endorsements, sponsorships, and doctrine never produce a position coding by themselves. Endorsing the US Political Declaration is not a position against a binding instrument; Austria endorses it and sponsors the treaty resolution in the same year. Codings derive from statements and votes, with the reasoning shown. The validator enforces this rule in code: a coding whose only evidence is an endorsement, a sponsorship, or a policy document fails the build.

**Endorsement absence:** a state missing from an endorsement list renders as not listed, an absence tier. Not endorsing is not opposing, and the site never colors it as if it were.

## Coverage depth: the three signals that carry coded depth

Endorsements and sponsorships are recorded as membership facts, taken verbatim from the face of each instrument's own roster. They are never coded and never graded, so they have no coverage depth to report. The three signals below are the ones this project reads, weighs, and codes from, and each is covered to a different depth.

**Votes:** complete. All 193 member states, from the official UN General Assembly voting dataset published by the Dag Hammarskjöld Library. The extraction code, the reconciliation checks, and the committed extract are public in the repository. Nothing is scraped.

**Statements:** deep for a bounded launch set of states, selected by published criteria: vote changers, No votes and abstentions on the most recent resolution, resolution sponsors, states with major-power doctrine, and states that made individual submissions to the Secretary-General. Every other state shows its votes and an explicit coverage notice.

**National policy:** strict scope, major players only. A doctrine entry means a policy document specifically governing autonomy in weapons systems, like DoD Directive 3000.09. Military AI strategies, responsible-AI frameworks, and legislative bills are context notes, never coded evidence.

## The rubric

Every coded position sits on two axes.

Axis A is instrument preference: what kind of international instrument, if any, does the state support? Seven categories: LBI-BAN, LBI-OPEN, REG-SOFT, CCW-ONLY, OPPOSE, AMBIG, NONE. The [rubric page](rubric.html) defines each in plain language. Categories are mutually exclusive at a dated point in time.

Axis B is confidence: EXPLICIT when the state says it directly, INFERRED when the coding rests on interpretation, AMBIGUOUS when the record points in more than one direction, PROVISIONAL when the coding rests on secondary reporting of a primary record this project has not yet verified. A provisional coding says so on its face, carries a note stating exactly what is pending, and is upgraded or corrected once the primary record is reviewed.

One rule inside Axis B is worth stating plainly, because it decides how a whole bloc of states is coded. When a state is a named author of a substantive draft treaty text, this site reads that authorship as an explicit statement of the position the text takes, and codes it EXPLICIT. A draft instrument is the most committing written form available to a state in a negotiation: not a speech about what should happen, but the operative language the state is asking others to sign. The rule is narrow and applies symmetrically to drafts that prohibit and drafts that do not. Co-sponsoring a resolution is not authorship. Signing a joint statement is not authorship. An author that later departs from its own text is coded on the later record. Every coding made this way shows the draft text, the document symbol, the date, and the state's name among the authors, so a reader who thinks authorship should count for less can see what the coding rests on and weigh it differently. The [rubric page](rubric.html) states the rule in full.

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

Reputable secondary sources serve three functions here: discovery (finding primary documents), context (citable background, attributed by name), and cross-check (did this project miss something). They are never coding sources. Every coding traces to primary documents.

This is not a formality, and two counts on this site differ from the widely reported ones because of it. A September 2025 joint statement is usually described as carrying 42 parties. Its own text reads "on behalf of the following 39 High-Contracting Parties" and then names 39, listing Kiribati, Samoa and Thailand separately as observer states that associate themselves: 39 plus 3, reported as 42. A 2023 draft-articles paper is usually credited to seven states; the face of its first revision names six, and the seventh joins at the second revision two months later. Neither correction required special access. Both required opening the document and counting the names, which is what this project does instead of repeating a figure. Translations of official documents by research institutes are quoted as unofficial translations with the originals linked. Advocacy-affiliated trackers are consulted as cross-checks only and cited once as related work.

## Links that outlive administrations

Government URLs die when governments change. Every doctrine and endorsement source carries both its live link and an archived snapshot, and the build warns on any entry missing one. Where a live page blocks automated access, the archived capture is the verified record and the page says so.

## Who codes, and how

Walker Robinson is the analyst of record. Tooling drafts, checks, and formats. It never decides. No coded position, shift event, doctrine claim, or analyst sentence publishes without explicit approval, and the site build refuses to ship unapproved content. There is no automated or model-assisted position classification, and the publishing pipeline makes no model calls. The site runs on $0 infrastructure.

## Corrections

Errors get fixed in the open. A superseded coding stays visible with a data-integrity notice. Red on this site carries exactly two meanings: that notice, and the thin seam marking the moment a coded position changed. The [corrections page](corrections.html) lists every correction with dates. If you find an error, open an issue in the repository. The [about page](about.html) says who runs this.

## Related work

Automated Decision Research, the monitoring arm of the Stop Killer Robots campaign, maintains a state-positions tracker at automatedresearch.org. It is the closest existing resource. This project differs in structure: time as a first-class axis, triangulation across votes, statements, and doctrine, and a published rubric with confidence tiers. ADR is consulted as a cross-check only, never as a coding source.

## Sources and licensing

Two layers, two sets of terms, and the split is deliberate. The vote extracts are © United Nations, taken from the UN Digital Library with attribution and passed on for non-commercial use only. This project's own coded data, meaning the codings, shift events, confidence tiers, rubric, and analyst notes, is CC BY 4.0 and free to reuse commercially with attribution. The CC BY grant does not reach the vote extracts. Any page showing both is a composite, and the stricter terms control the part they cover. Code: MIT. The full split, including the composite rule, is in the repository's DATA_LICENSE.
