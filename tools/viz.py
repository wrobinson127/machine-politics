"""The home page's figures: the data payload they read, and the static flat
map that is their first paint and their no-JS fallback.

One payload feeds the globe, Strands and the assembly, so every figure shows
the same 193 states with the same approved readings. It is embedded in the
page as JSON at build time: no fetch, no runtime data source.

The static map is the Equal Earth projection drawn in SVG, with the exact
scale and centre the canvas uses when it flattens, so the hand-off from
poster to interactive figure does not move a pixel of meaning. Equal Earth
preserves area, so "too small to see" is a plain area test on the projected
shape: those states, and the one with no shape at 1:110m (Tuvalu), are drawn
as dots at their Natural Earth label point.

Label points, ISO alpha-2 codes and subregions come from Natural Earth
(public domain): data/source/ne_labels.json, extracted once from
ne_50m_admin_0_countries.geojson, fields LABEL_X, LABEL_Y, ISO_A2 (fallback
ISO_A2_EH) and SUBREGION.
"""

import html
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config

NE_LABELS = config.REPO_ROOT / "data" / "source" / "ne_labels.json"
COUNTRIES_TOPOJSON = config.DATA_SOURCE_DIR / "countries-110m.json"
ISO_NUMERIC_TABLE = config.REPO_ROOT / "data" / "derived" / "iso_numeric_alpha3.json"

# Shared with site/js/viz.js: the flat map's frame. Change both together.
VIEW_W, VIEW_H = 1100, 620
FLAT_SCALE = 196
# A state whose projected area is below this many square units is drawn as
# a dot. Equal Earth is equal-area, so this is a true-area threshold:
# 0.0008 steradians, about 20,000 square kilometres.
SMALL_AREA = 0.0008 * FLAT_SCALE ** 2

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def equal_earth(lon, lat):
    """Equal Earth (Savric, Patterson, Jenny 2018), scaled and centred the
    way d3.geoEqualEarth is: x right, y down."""
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(M * math.sin(phi))
    t2 = t * t
    t6 = t2 * t2 * t2
    x = lam * math.cos(t) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return VIEW_W / 2 + FLAT_SCALE * x, VIEW_H / 2 - FLAT_SCALE * y


def _decode_topology():
    topo = json.loads(COUNTRIES_TOPOJSON.read_text(encoding="utf-8"))
    table = json.loads(ISO_NUMERIC_TABLE.read_text(encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        pts, x, y = [], 0, 0
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(ids):
        out = []
        for a in ids:
            pts = arcs[a] if a >= 0 else arcs[~a][::-1]
            out.extend(pts[1:] if out else pts)
        # Unwrap across the antimeridian so each ring is continuous; the
        # part beyond 180 degrees is drawn again shifted and clipped.
        unwrapped = [out[0]]
        for x, y in out[1:]:
            px = unwrapped[-1][0]
            while x - px > 180:
                x -= 360
            while x - px < -180:
                x += 360
            unwrapped.append((x, y))
        return unwrapped

    shapes = {}
    for geom in topo["objects"]["countries"]["geometries"]:
        iso = table.get(str(geom.get("id")))
        if geom["type"] == "Polygon":
            polys = [geom["arcs"]]
        elif geom["type"] == "MultiPolygon":
            polys = geom["arcs"]
        else:
            continue
        rings = [ring(r) for poly in polys for r in poly]
        shapes.setdefault(iso or f"_{geom.get('id')}", []).extend(rings)
    return shapes


def _projected_rings(rings):
    """Project each ring, plus a copy shifted 360 degrees for any ring that
    crosses the antimeridian; the sphere clip trims the overflow."""
    out = []
    for r in rings:
        lons = [p[0] for p in r]
        shifts = [0]
        if max(lons) > 180:
            shifts.append(-360)
        if min(lons) < -180:
            shifts.append(360)
        for s in shifts:
            out.append([equal_earth(x + s, y) for x, y in r])
    return out


def _area(pts):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def _path(rings):
    return "".join(
        "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z" for r in rings
    )


def sphere_path():
    edge = [equal_earth(180, lat) for lat in range(-90, 91, 3)]
    edge += [equal_earth(-180, lat) for lat in range(90, -91, -3)]
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in edge) + "Z"


def payload(votes, content_states, preview, current_position, display_name, iso):
    """Every member state with its three votes and its approved reading
    today. Unapproved readings never enter it (same filter as every page)."""
    labels = json.loads(NE_LABELS.read_text(encoding="utf-8"))["states"]
    shapes = _decode_topology()
    rows = []
    for iso3 in sorted(votes["states"]):
        entry = votes["states"][iso3]
        cs = content_states.get(iso3, {})
        pos = current_position(cs, preview)
        lab = labels[iso3]
        rings = shapes.get(iso3)
        small = not rings or sum(_area(r) for r in _projected_rings(rings)) < SMALL_AREA
        rows.append({
            "i": iso3,
            "n": display_name(iso3, entry, cs),
            "a": lab["a2"],
            "r": lab["region"],
            "lon": lab["lon"],
            "lat": lab["lat"],
            "v": "".join(entry["votes"][k] for k in config.LAWS_RESOLUTIONS),
            "p": pos["code"] if pos else "",
            "c": (pos.get("confidence") or "") if pos else "",
            "s": iso(pos["as_of"]) if pos else "",
            "sm": 1 if small else 0,
        })
    return rows


def static_map_svg(rows):
    """The flat map as SVG: countries filled by position, small states as
    dots. It is the figure's first paint and its no-JS form. Texture
    patterns come from the page's shared defs (build_site.viz_textures_svg)."""
    shapes = _decode_topology()
    by_iso = {r["i"]: r for r in rows}
    parts = [
        f'<svg class="viz-poster" viewBox="0 0 {VIEW_W} {VIEW_H}" role="img" '
        'aria-label="World map of the UN member states, coloured by the position '
        'this site has read for each. The table below lists every state.">',
        f'<defs><clipPath id="viz-sphere"><path d="{sphere_path()}"/></clipPath></defs>',
        f'<path class="viz-sphere" d="{sphere_path()}"/>',
        '<g clip-path="url(#viz-sphere)">',
    ]
    for iso3 in sorted(shapes):
        r = by_iso.get(iso3)
        cls = "viz-land" if not r else ("viz-nr" if not r["p"] else f"viz-p p-{r['p']}")
        parts.append(f'<path class="{cls}" d="{_path(_projected_rings(shapes[iso3]))}"/>')
    parts.append("</g>")
    for r in rows:
        if not r["sm"]:
            continue
        x, y = equal_earth(r["lon"], r["lat"])
        cls = "viz-dot-nr" if not r["p"] else f"viz-p p-{r['p']}"
        parts.append(f'<circle class="viz-dot {cls}" cx="{x:.1f}" cy="{y:.1f}" r="4.2">'
                     f"<title>{html.escape(r['n'])}</title></circle>")
    parts.append("</svg>")
    return "".join(parts)
