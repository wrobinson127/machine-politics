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
- `config/config.py` is the single source of truth for codes, tiers, palette, paths, dates.

## Where things are

- `content/` is the claim-bearing layer: `rubric.yaml`, `states/{iso3}.yaml`, `sources.yaml` (every evidence source resolves here), `pages/*.md` (prose with front matter).
- `tools/build_site.py` renders everything under `site/` except `site/css/site.css`, `site/assets/og-card.png` (regenerate with `tools/gen_og_card.py`) and the font files in `site/assets/fonts/`.
- `docs/METHODOLOGY.md` is the write-up behind the site's methodology page.
