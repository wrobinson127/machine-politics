# Third-party components

Runtime libraries load from cdnjs, version-pinned with subresource
integrity hashes declared in `tools/build_site.py`. Nothing else is
fetched at runtime; the site sets no cookies and calls no APIs beyond
the map tiles noted below.

| Component | Version | License | Use |
|---|---|---|---|
| D3 | 7.8.5 | ISC | The globe, Strands and the assembly (projections, timers, easing) |
| TopoJSON client | 3.0.2 | ISC | Decoding the country shapes for the globe |
| MapLibre GL JS | 5.12.0 | BSD-3-Clause | Endorsement wave map on the instruments page |
| OpenFreeMap tiles (Positron style) | rolling | tiles © OpenFreeMap, data © OpenStreetMap contributors (ODbL); credited on-map | Base map |
| world-atlas TopoJSON (countries-110m) | 2.0.2 | ISC; derived from Natural Earth (public domain) | Country polygons for the globe, the static map and the wave map |
| Natural Earth 1:50m Admin 0 label points | 5 | Public domain | One dot per state at its label point, ISO alpha-2 codes, subregions (`data/source/ne_labels.json`) |
| Newsreader variable fonts (self-hosted) | 2.0 | SIL Open Font License 1.1 (OFL.txt ships beside the fonts) | Display type |

Data licensing (UN-derived extracts, this project's coded data, code)
is in `DATA_LICENSE.md`.
