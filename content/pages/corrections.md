---
approved: false   # corrections backfill drafted 2026-11-18; analyst approval flips this back
title: Corrections
---
This site will make mistakes. Reading a position is interpretation, diplomatic statements are ambiguous on purpose, and documents arrive in many languages. The policy is to fix errors fast and in the open.

## The policy

A correction never erases history. When a position is replaced, the old one stays visible with a correction notice and the date. Red on this site means exactly two things: that notice, and the thin seam marking the day a position changed. Red never marks a state's position, and it never means approval or disapproval of one.

Corrections are listed on this page as they happen, newest first, with what changed, why, and the evidence that forced it.

## Report an error

If a quote is wrong, a date is off, a link is dead, or you read a position differently, say so. Open an issue in the repository. Include the state, the page, and the source you are reading. Real disagreements about a position get answered with evidence on this page, whether or not the position changes.

## Corrections to date

Until 18 November 2026 this section said "None yet". That was wrong: the corrections below were made between 19 and 20 October 2026 and were not listed here. They were added on 18 November 2026 from the site's public change history. The state pages do not yet show their own correction notices, so the previous readings are recorded here.

### 20 October 2026: twelve readings from the review of every member state

The review of all member states went live at 00:17 UTC on 20 October. A check of those readings against their sources found twelve that said more than the evidence shows. They were corrected at 01:42 UTC the same day.

- **Brunei** changed from "Wants a treaty with bans" to "Unclear or shifting". Its statement calls for strict regulation and only takes note of the UN Secretary-General's call for a ban treaty. A sentence saying it urged other states had no source and was removed.
- **Cameroon** changed from "Keep it in Geneva" to "Unclear or shifting", dated from 28 October 2025. It called for an immediate moratorium in 2025 and backed the Geneva process in 2026.
- **Slovenia** changed from "Keep it in Geneva" to "Unclear or shifting". It names a new international instrument but leaves its form open.
- **Zimbabwe** stays "Wants a treaty with bans", but is now dated from 14 October 2024 instead of 12 November 2015. Its 2015 statement called for a ban but named no binding form.
- **Dominican Republic, Ghana, Trinidad and Tobago, Nicaragua and Fiji:** sentences with no source behind them were removed. Fiji's explanation was rewritten to say only what its quoted statements show.
- **Vanuatu, Spain and Chile:** wording fixes. Vanuatu's reading is now called "an interpretation" instead of "a careful one". Spain's explanation now separates its 2023 wording, "a legally binding instrument", from its 2024 wording, "a legal instrument". A sentence on Chile's page about other states' readings was removed.

Evidence: [pull request 15](https://github.com/wrobinson127/machine-politics/pull/15), which lists each change and the source behind it.

### 20 October 2026: the peer grid on pages of states with no position

State pages showed a grid headed "among the states with a position so far" even for states that have no place on the position scale: those with no stated position, those whose position is unclear, and those not yet reviewed. That was 112 pages at the time of the fix. The grid now shows only for states on the scale.

Evidence: [pull request 14](https://github.com/wrobinson127/machine-politics/pull/14).

### 20 October 2026: earlier start dates for eight readings

Argentina, Costa Rica, Ecuador, El Salvador, Panama, the Philippines, Sierra Leone and Uruguay read as "Wants a treaty with bans" from 9 August 2022. All eight co-wrote an earlier joint paper, dated 27 September 2021, that already calls for a legally binding instrument and prohibitions. Their readings now start from that date. The position itself did not change.

Evidence: [pull request 13](https://github.com/wrobinson127/machine-politics/pull/13).

### 19 October 2026: evidence for the 2023 United States reading

The United States' 2023 reading, "Wants new rules, not a treaty", was marked as explicit but rested on a quote that does not mention a treaty. The official UN record of the US explanation of vote on 1 November 2023 (A/C.1/78/PV.28) was added as evidence. The reading and its confidence did not change.

Evidence: [pull request 7](https://github.com/wrobinson127/machine-politics/pull/7).

### 19 October 2026: a doubled resolution symbol

Every state page cited "A/RES/A/RES/78/241" instead of "A/RES/78/241". The symbol is fixed.

Evidence: [pull request 6](https://github.com/wrobinson127/machine-politics/pull/6).

### 19 October 2026: archived copies of sources

The methodology page said every policy and signing source has an archived copy. At launch, nine did not: the French, British and US doctrine entries, the 2024 REAIM Blueprint, the three co-sponsor lists for the General Assembly resolutions, and two 2025 expert group working papers. All nine now have archived copies, so the methodology's statement is true. The wording did not change.

Evidence: [pull request 4](https://github.com/wrobinson127/machine-politics/pull/4).

### 19 October 2026: state count in the repository README

The project's README said 33 states had "a coded position". Five of those 33 had no stated position, which this site treats as a finding about coverage, not a position. The README now counts states reviewed and states with a stated position separately.

Evidence: [pull request 5](https://github.com/wrobinson127/machine-politics/pull/5).
