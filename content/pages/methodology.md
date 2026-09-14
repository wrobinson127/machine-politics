---
approved: true
title: Methodology
---
## What this site does

Machine Politics records where every UN member state stands on autonomous weapons. For each state it tracks five things: how it voted at the UN, what pledges it signed, what resolutions and papers it co-sponsored, what its officials have said, and what rules it has written for its own military. Positions are trajectories, not snapshots. The site shows who moved, when, and on what evidence.

The site takes no position on whether autonomous weapons should be banned or regulated. It records who says what.

## Five things, never a score

The five things above are shown side by side. They are never combined into a rank, grade, or index. The site lays them out and leaves the weighing to the reader.

Signing something never decides a state's position on its own. Neither does co-sponsoring, and neither does a state's own military rulebook. Signing the US Political Declaration is not a vote against a treaty: Austria signed it and co-sponsored the treaty resolution in the same year. Positions come from what states say and how they vote, with the reasoning shown. This rule is enforced in code: a position whose only evidence is a signature, a co-sponsorship, or a policy document fails the build.

A state missing from a signing list is shown as not listed. Not signing is not opposing, and the site never colours it as if it were.

## How much has been reviewed

Signatures and co-sponsorships are copied from each document's own list, so there is nothing to review; they are complete. The other three things are read and weighed, and each is covered to a different depth.

**Votes:** complete. All 193 member states, from the official UN voting dataset. The extraction code and its checks are public in the repository. Nothing is scraped.

**Statements:** deep for a first set of states, chosen by published criteria: states that changed their vote, states that voted No or abstained on the latest resolution, states that co-sponsored a resolution, states with a published military policy, and states that sent their own submission to the UN Secretary-General. Every other state shows its votes and a note saying it has not been reviewed yet.

**National policy:** narrow scope, major military powers only. A national policy here means a document that specifically governs autonomy in weapons, like the US Department of Defense directive on the subject. Military AI strategies, responsible-AI principles, and draft laws are shown as context, never as evidence.

Of the seven major powers reviewed, three have a published policy specifically governing autonomy in weapons and four do not. That split is a finding about what is public, not a gap in the review: each of the four carries a dated note saying where this site looked. It says nothing about rules that exist but are not published.

{{doctrine-coverage}}

## The rubric

Every position sits on two axes. Axis A is what the state wants: seven answers, from a treaty with bans to no new rules, plus unclear and no stated position. Axis B is how sure this site is: EXPLICIT when the state said it directly, INFERRED when the reading rests on interpretation, AMBIGUOUS when the state's words point both ways, PROVISIONAL when the reading rests on someone else's report of a document not yet checked. The [rubric page](rubric.html) defines all of them and states the one special rule in full: a state that co-writes a draft treaty is read as stating the position the text takes.

Unclear is a real category. When a state has said things that point both ways, the site says so and shows both. China is the worked example.

A shift is a state moving from one position to another on a dated statement. Shifts are the point of this site. Each one carries the evidence that dates it.

## Evidence rules

Every position links to a quoted, dated primary source. The build enforces it: a word-for-word quote of at most 25 words, the document's date, a direct link, the source language, whether the translation is official, and a confidence level.

Translation is always stated. A quote from an official translation says so. A quote from an unofficial one says so. A document with no translation yields no English quote at all: the entry describes and links it, and any reading it supports is INFERRED at best.

## What absence means

There are two kinds of absence, and they are never mixed.

"No stated position" means this site read what the state has said and found nothing. "Not yet reviewed" means exactly that. Neither is shown as a position.

For national policy, the site only ever says: no published policy found by this site, as of a stated date, with a note on where it looked. The site never says a state has nothing. The build rejects that kind of claim.

## Secondary sources

Reputable secondary sources do three jobs here: finding primary documents, providing citable background under their own name, and checking whether this site missed something. They never decide a position. Every position rests on primary documents.

Two numbers on this site differ from the widely reported ones because of that. A September 2025 joint statement is usually said to carry 42 parties. Its own text reads "on behalf of the following 39 High-Contracting Parties", names 39, and then lists Kiribati, Samoa and Thailand separately as observers who associate themselves: 39 plus 3, reported as 42. A 2023 draft-articles paper is usually credited to seven states; its first revision names six, and the seventh joins in the second revision two months later. Neither correction needed special access. Both needed someone to open the document and count the names, which is what this site does instead of repeating a figure.

Translations by research institutes are quoted as unofficial, with the original linked. Trackers run by advocacy groups are used only as a cross-check and named once under related work.

## Links that outlive governments

Government web addresses die when governments change. Every policy and signing source carries both its live link and an archived copy, and the build warns on any that is missing one. Where a live page blocks automated access, the archived copy is the verified record and the page says so.

## Who decides, and how

Walker Robinson makes every judgment call. Software drafts, checks, and formats. It never decides. No position, shift, policy claim, or sentence of analysis is published without his explicit approval, and the build refuses to ship anything unapproved. No software classifies positions, and the published site makes no AI calls. It runs on $0 of infrastructure.

## Corrections

Errors get fixed in the open. A replaced position stays visible with a correction notice. Red on this site means exactly two things: that notice, and the thin seam marking the day a position changed. The [corrections page](corrections.html) lists every correction with dates. Found an error? Open an issue in the repository. The [about page](about.html) says who runs this.

## Related work

Automated Decision Research, the monitoring arm of the Stop Killer Robots campaign, runs a state-positions tracker at automatedresearch.org. It is the closest existing resource. This site differs in structure: it tracks positions over time, it sets votes, statements, and national policy side by side, and it publishes the rubric and the confidence levels. ADR is used only as a cross-check, never to decide a position.

## Sources and licensing

Two layers, two sets of terms. The vote data is © United Nations, taken from the UN Digital Library with attribution, and may be reused for non-commercial purposes only. This site's own work, meaning the positions, shifts, confidence levels, rubric, and analysis, is CC BY 4.0: free to reuse, including commercially, with credit. The CC BY licence does not cover the vote data. Where a page shows both, the stricter terms apply to the part they cover. Code is MIT. Full details in the repository's DATA_LICENSE.
