# Third-party components

Runtime libraries load from cdnjs, version-pinned with subresource
integrity hashes declared in `tools/build_site.py`. Nothing else is
fetched at runtime; the site sets no cookies and calls no APIs beyond
the map tiles noted below.

| Component | Version | License | Use |
|---|---|---|---|
| GSAP (gsap.min.js, DrawSVGPlugin) | 3.15.0 | GreenSock Standard License (free, including commercial use; DrawSVG free since April 2025) | Within-beat drawing on the preview tour |
| Scrollama | 3.2.0 | MIT | Scroll step enter/exit triggering (IntersectionObserver) |
| MapLibre GL JS | 5.12.0 | BSD-3-Clause | Endorsement wave map on the instruments page |
| OpenFreeMap tiles (Positron style) | rolling | tiles © OpenFreeMap, data © OpenStreetMap contributors (ODbL); credited on-map | Base map |
| world-atlas TopoJSON (countries-110m) | 2.0.2 | ISC; derived from Natural Earth (public domain) | Country polygons, converted at build time |
| Newsreader variable fonts (self-hosted) | 2.0 | SIL Open Font License 1.1 (OFL.txt ships beside the fonts) | Display type |

Data licensing (UN-derived extracts, this project's coded data, code)
is in `DATA_LICENSE.md`.
