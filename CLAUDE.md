# CLAUDE.md

Machine Politics: a static tracker of state positions on autonomous weapons. Votes from the official UN dataset, positions coded by the analyst of record (Walker Robinson), everything approval-gated.

## Commands

```
python -m pytest tools/tests -q        # run the suite before every commit
python tools/validate_content.py       # content schema, evidence rules, prohibited claims
python tools/votes_extract.py          # source CSV -> extract -> votes.json (needs .scratch/source/)
python tools/build_site.py             # deploy site into site/ (hard-excludes approved: false)
python tools/build_site.py --preview   # drafts behind a DRAFT banner, .scratch/preview/, localhost only
```

Serve locally: `python -m http.server 8080 --bind 127.0.0.1 --directory .scratch/preview`

## Law of the repo

- Nothing claim-bearing renders without `approved: true`. Author everything `approved: false`. The deploy build refuses otherwise, and CI checks the committed `site/` is byte-identical to a fresh rebuild, so commit regenerated output with any content or tool change.
- Never fetch the UN dataset, anything from digitallibrary.un.org records, or reachingcriticalwill.org (link-only; their WAF blocks tooling anyway). Individual assisted fetches of specific cited documents elsewhere are fine. No bulk downloading, ever.
- No red or green on positions, anywhere. AMBIG is a hatch, not gray. Saturated red means data-integrity only.
- No category may depend on hue alone. Every position pairs its hue with a texture from `config.POSITION_TEXTURES`, because six pairs are indistinguishable under simulated colour-vision deficiency and repaletting cannot fix it. `tools/tests/test_color_vision.py` holds the guarantee. Keep the legend swatch and the band on the same texture, and never set a band's hue with a `background:` shorthand: it erases the texture.
- Absence is tiered: `no_position_on_record` vs `not_yet_reviewed`, and doctrine absence only as the dated coverage phrase in `config.DOCTRINE_ABSENCE_PHRASE`. NONE is a coverage statement, never a position: it spans the record and carries its review date in the label.
- Voice: no em dashes, active, short, no corporate speak. The validator enforces the dash rule on prose pages.
- No model calls in any tool or workflow. No nightly workflows.
- `config/config.py` is the single source of truth for codes, tiers, palette, paths, dates. `UPDATED_THROUGH` is the latest dated fact in approved content (readings, shifts, their evidence, policy reviews, conference entries); a test holds it there in both directions.
- UN machine transcripts (transcripts.un.org, source type `transcript`) are evidence at INFERRED at most and never the only evidence for a shift (analyst ruling R1, 2026-10-19). Co-written elements papers count as the co-authors' position only when they state an instrument preference (R2). Joint statements delivered by another state corroborate only (R3).
- Rendered fields of approved entries (rationale, scope_note, provisional_note) speak to the reader. The validator rejects working-note phrasing there; keep analyst questions in `flags`, which never render.
- Every file the build writes must be committable: `.gitignore` swallowing a built file makes it 404 live while CI stays green. A test checks this.
- Every merge to `main` deploys to production (pages.yml). There is no staging.

## Where things are

- `content/` is the claim-bearing layer: `rubric.yaml`, `states/{iso3}.yaml`, `sources.yaml` (every evidence source resolves here), `pages/*.md` (prose with front matter).
- `tools/build_site.py` renders everything under `site/` except `site/css/site.css`, `site/js/viz.js` (the globe, Strands and the assembly; copied and content-hashed like the stylesheet), `site/assets/og-card.png` (regenerate with `tools/gen_og_card.py`) and the font files in `site/assets/fonts/`.
- `docs/METHODOLOGY.md` is the write-up behind the site's methodology page.
- `content/conference.yaml` drives `conference.html`, the Seventh CCW Review Conference log (16 to 20 Nov 2026). Daily path: draft each day's entries as link-only facts (date, what happened, official link) from https://meetings.unoda.org/meeting/79323/statements, `approved: false`, for the analyst to approve as a batch. No reading changes during the conference week.
- The home page is the globe (`#viz-world`), Strands and the table of every state; the Votes page leads with the assembly. All three figures read one payload built by `tools/viz.py` from approved content only. Their captions live in `content/viz.yaml` (approval-gated; until approved the figures use the count-only labels in `build_site.VIZ_FALLBACK`). The flat map is also rendered as static SVG at build time: it is the first paint and the no-JS figure. The scroll tour and the trajectory board were retired on 2026-10-19.
- The build also writes `sitemap.xml`, `robots.txt`, `llms.txt`, and `data/positions.{csv,json}` (every rendered reading, CC BY 4.0; votes stay out under UN terms).
- Working notes for the October 2026 finish run (state, audit, plan, decisions, approval packet, ship verdict) live on branch `finish` of the private `machine-politics-dev` repo, never here.
