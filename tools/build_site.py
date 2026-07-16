"""Build the static site from the derived votes data and the content layer.

Two modes:
- deploy (default): writes site/ and HARD-EXCLUDES every content entry that
  is not approved: true. A manifest records what rendered; CI asserts zero
  unapproved entries in the deploy artifact.
- --preview: writes .scratch/preview/ (gitignored, localhost only) rendering
  unapproved entries behind an unmistakable DRAFT banner.

The board and every page are fully server-rendered: no content is gated on
JavaScript. Output is deterministic; rebuilding without input changes
produces byte-identical files.
"""

import argparse
import gzip
import html
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config

T0 = date(config.TIMELINE_START_YEAR, 1, 1)
T1 = date.fromisoformat(config.UPDATED_THROUGH)
TRACK_W = 1000
TRACK_H = 30

VOTE_GLYPHS = {"Y": "Yes", "N": "No", "A": "Abstain", "X": "Non-voting"}


def esc(value):
    return html.escape(str(value), quote=True)


SMALL_WORDS = {"of", "and", "the", "for", "in", "on", "at", "de", "da", "do"}

# Names whose conventional English rendering the generic title-caser cannot
# reach. Curated display_name fields in content files still win over these.
DISPLAY_NAME_OVERRIDES = {
    "TÜRKİYE": "Türkiye",
    "CÔTE D'IVOIRE": "Côte d'Ivoire",
    "COTE D'IVOIRE": "Côte d'Ivoire",  # the LAWS rows carry the unaccented form
}


def display_from_un_name(un_name):
    if un_name in DISPLAY_NAME_OVERRIDES:
        return DISPLAY_NAME_OVERRIDES[un_name]
    un_name = un_name.replace("İ", "I")  # Unicode lowercasing artifact guard
    return _titlecase_un_name(un_name)


def _titlecase_un_name(un_name):
    """UN names arrive uppercase; render them in book title case with small
    words and possessives handled ("DEMOCRATIC PEOPLE'S REPUBLIC OF KOREA"
    -> "Democratic People's Republic of Korea"). Curated display names in
    content files always win over this fallback."""
    words = []
    for i, raw in enumerate(un_name.lower().split()):
        core = raw.strip("()")
        if i > 0 and core in SMALL_WORDS:
            words.append(raw)
            continue
        fixed = raw[0].upper() + raw[1:] if raw[0].isalpha() else (
            raw[0] + raw[1].upper() + raw[2:] if len(raw) > 1 else raw
        )
        for mark in ("'", "’", "-"):
            if mark in fixed:
                fixed = mark.join(
                    (p if p in ("s", "d") and mark != "-" else (p[:1].upper() + p[1:] if p else p))
                    for p in fixed.split(mark)
                )
        words.append(fixed)
    return " ".join(words)


def as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def iso(value):
    return as_date(value).isoformat()


def x_of(d, w=TRACK_W):
    span = (T1 - T0).days
    return round(max(0.0, min(1.0, (as_date(d) - T0).days / span)) * w, 1)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_votes():
    with gzip.open(config.VOTES_DERIVED_JSON, "rt", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_content():
    rubric = load_yaml(config.RUBRIC_YAML)
    sources = {s["id"]: s for s in load_yaml(config.SOURCES_YAML).get("sources", [])}
    states = {}
    if config.STATES_DIR.exists():
        for path in sorted(config.STATES_DIR.glob("*.yaml")):
            states[path.stem] = load_yaml(path)
    return rubric, sources, states


def parse_front_matter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def load_pages():
    pages = {}
    pages_dir = config.CONTENT_DIR / "pages"
    if pages_dir.exists():
        for path in sorted(pages_dir.glob("*.md")):
            meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
            pages[path.stem] = {"meta": meta, "body": body}
    return pages


def _md_inline(text):
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return text


def md_to_html(md):
    """Deliberately small markdown subset: h2/h3, paragraphs, bold, links,
    flat lists. Prose pages need nothing more, and no dependency."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        lines = block.strip().splitlines()
        if block.startswith("### "):
            out.append(f"<h3>{_md_inline(block[4:].strip())}</h3>")
        elif block.startswith("## "):
            out.append(f"<h2>{_md_inline(block[3:].strip())}</h2>")
        elif all(ln.lstrip().startswith("- ") for ln in lines):
            items = "".join(f"<li>{_md_inline(ln.lstrip()[2:])}</li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{_md_inline(' '.join(ln.strip() for ln in lines))}</p>")
    return "\n".join(out)


def prose_page(key, pages, fallback_lines, preview, manifest):
    """A prose page renders only when approved (invariant 1 covers analyst
    sentences); otherwise the factual shell stands in."""
    entry = pages.get(key)
    title = (entry or {}).get("meta", {}).get("title", key.capitalize())
    if entry:
        approved = is_approved(entry["meta"])
        manifest["entries"].append(
            {"state": None, "kind": f"page:{key}", "approved": approved,
             "rendered": bool(preview or approved)}
        )
        if preview or approved:
            chip = (
                '<span class="draft-chip">DRAFT</span>'
                if preview and not approved
                else ""
            )
            body = f"<h1>{esc(title)}{chip}</h1>\n" + md_to_html(entry["body"])
            return page(title, body, current=f"{key}.html", preview=preview)
    return shell_page(title, f"{key}.html", fallback_lines, preview)


def is_approved(entry):
    return entry.get("approved") is True


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------

NAV = [
    ("index.html", "Board"),
    ("votes.html", "Votes"),
    ("rubric.html", "Rubric"),
    ("methodology.html", "Methodology"),
    ("about.html", "About"),
    ("corrections.html", "Corrections"),
]


def page(title, body, *, current, depth=0, preview=False, description=""):
    prefix = "../" * depth
    nav = "\n".join(
        f'      <a href="{prefix}{href}"'
        + (' aria-current="page"' if href == current else "")
        + f">{esc(label)}</a>"
        for href, label in NAV
    )
    banner = (
        '<div class="draft-banner" role="status">DRAFT PREVIEW: unapproved '
        "working copy, not published, not citable</div>\n"
        if preview
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · {esc(config.SITE_NAME)}</title>
<meta name="description" content="{esc(description or 'Where every country stands on autonomous weapons: recorded votes, official statements, and national policy, tracked as they shift over time.')}">
<meta property="og:title" content="{esc(title)} · {esc(config.SITE_NAME)}">
<meta property="og:description" content="{esc(description or 'Where every country stands on autonomous weapons, tracked as positions shift over time.')}">
<meta property="og:image" content="https://{config.SITE_DOMAIN}/assets/board-poster.svg">
<link rel="stylesheet" href="{prefix}css/tokens.css">
<link rel="stylesheet" href="{prefix}css/site.css">
<link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
</head>
<body>
{banner}<header class="masthead">
  <div class="shell masthead-inner">
    <a class="wordmark" href="{prefix}index.html">{esc(config.SITE_NAME)}</a>
    <nav class="primary" aria-label="Site">
{nav}
    </nav>
  </div>
</header>
<main class="shell">
{body}
</main>
<footer class="colophon">
  <div class="shell">
    <p>Votes from the United Nations General Assembly voting dataset. © United Nations, 2026, <a href="https://digitallibrary.un.org">digitallibrary.un.org</a>. Data reuse terms in <a href="https://github.com/wrobinson127/machine-politics">the repository</a>.</p>
    <p><span class="updated-through">Updated through {esc(config.UPDATED_THROUGH)}</span> · Every coding traces to a quoted, dated, linked source · <a href="{prefix}corrections.html">Corrections</a></p>
  </div>
</footer>
<script src="{prefix}js/board.js" defer></script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Board rendering
# ---------------------------------------------------------------------------

def pct(d):
    return f"{x_of(d, 100):.2f}%"


def band_style(code, confidence):
    """Fill styling for a coded band. AMBIG is a designed hatch texture,
    confidence modulates opacity, hue never changes."""
    opacity = "1" if confidence == "EXPLICIT" else "0.55"
    if code == "AMBIG":
        return f"opacity:{opacity}", " band-hatch"
    return f"background:{config.PALETTE['positions'][code]};opacity:{opacity}", ""


def vote_glyph_svg(vote):
    """Fixed-size monochrome ink shapes; meaning never carried by hue."""
    ink = config.PALETTE["ink"]
    if vote == "Y":
        shape = f'<circle cx="6" cy="6" r="4.2" fill="{ink}"/>'
    elif vote == "N":
        shape = (
            f'<circle cx="6" cy="6" r="4.2" fill="none" stroke="{ink}" stroke-width="1.6"/>'
            f'<line x1="3.4" y1="8.6" x2="8.6" y2="3.4" stroke="{ink}" stroke-width="1.4"/>'
        )
    elif vote == "A":
        shape = (
            f'<path d="M 6 1.8 A 4.2 4.2 0 0 0 6 10.2 Z" fill="{ink}"/>'
            f'<circle cx="6" cy="6" r="4.2" fill="none" stroke="{ink}" stroke-width="1.2"/>'
        )
    else:  # X non-voting
        shape = f'<line x1="2.5" y1="6" x2="9.5" y2="6" stroke="{ink}" stroke-width="1.6" stroke-opacity="0.5"/>'
    return f'<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">{shape}</svg>'


def compute_bands(codings):
    """Segment a coding timeline into bands in TRACK_W (0-1000) units."""
    bands = []
    timeline = sorted(codings, key=lambda c: iso(c["as_of"]))
    for i, coding in enumerate(timeline):
        left = x_of(coding["as_of"])
        right = x_of(timeline[i + 1]["as_of"]) if i + 1 < len(timeline) else float(TRACK_W)
        if right <= left:
            continue
        bands.append(
            {
                "code": coding["code"],
                "confidence": coding.get("confidence"),
                "left": left,
                "width": right - left,
                "opacity": "1" if coding.get("confidence") == "EXPLICIT" else "0.55",
                "since": iso(coding["as_of"]),
            }
        )
    return bands


def row_track_html(iso3, entry, resolutions, codings, shifts):
    """One state's track: coded bands where approved, vote marks always.
    Everything is percent-positioned HTML, so nothing distorts at any
    viewport width and every trigger is a real button."""
    parts = ['<div class="row-track">']
    for band in compute_bands(codings):
        style, extra_class = band_style(band["code"], band["confidence"])
        title = f"{band['code']} since {band['since']}, confidence {band['confidence']}"
        parts.append(
            f'<div class="band{extra_class}" style="left:{band["left"] / 10:.2f}%;'
            f'width:{band["width"] / 10:.2f}%;{style}" title="{esc(title)}"></div>'
        )
    for shift in sorted(shifts, key=lambda s: iso(s["date"])):
        parts.append(
            f'<button type="button" class="shift-node" style="left:{pct(shift["date"])}" '
            f'data-shift="{esc(json.dumps(_shift_payload(shift), ensure_ascii=False))}" '
            f'aria-label="Shift from {esc(shift["from"])} to {esc(shift["to"])} on {esc(iso(shift["date"]))}">'
            "<span></span></button>"
        )
    for key in config.LAWS_RESOLUTIONS:
        vote = entry["votes"][key]
        res = resolutions[key]
        parts.append(
            f'<button type="button" class="vote-mark" style="left:{pct(res["date"])}" '
            f'data-vote="{esc(json.dumps(_vote_payload(iso3, key, vote, res), ensure_ascii=False))}" '
            f'aria-label="{esc(VOTE_GLYPHS[vote])} on {esc(key)}, {esc(res["date"])}">'
            + vote_glyph_svg(vote)
            + "</button>"
        )
    parts.append("</div>")
    return "".join(parts)


def _vote_payload(iso3, key, vote, res):
    return {
        "kind": "vote",
        "state": iso3,
        "resolution": f"A/RES/{key}",
        "vote": VOTE_GLYPHS[vote],
        "date": res["date"],
        "url": res["undl_link"],
    }


def _shift_payload(shift):
    ev = []
    for e in shift.get("evidence", []):
        ev.append(
            {
                "quote": e.get("quote"),
                "date": iso(e["date"]),
                "url": e.get("url"),
                "confidence": e.get("confidence"),
            }
        )
    return {
        "kind": "shift",
        "from": shift["from"],
        "to": shift["to"],
        "date": iso(shift["date"]),
        "evidence": ev,
    }


def axis_html():
    parts = ['<div class="axis-track" aria-hidden="true">']
    for year in range(config.TIMELINE_START_YEAR, T1.year + 1, 2):
        parts.append(
            f'<span class="axis-tick" style="left:{pct(date(year, 1, 1))}">'
            f"<span>{year}</span></span>"
        )
    parts.append("</div>")
    return "".join(parts)


def board_rows(votes, content_states, preview):
    resolutions = votes["resolutions"]
    rows = []
    for iso3, entry in votes["states"].items():
        cs = content_states.get(iso3, {})
        codings = [
            c for c in cs.get("position_codings", []) if preview or is_approved(c)
        ]
        shifts = [s for s in cs.get("shift_events", []) if preview or is_approved(s)]
        latest_shift = max((iso(s["date"]) for s in shifts), default="")
        name = cs.get("display_name") or display_from_un_name(entry["un_name"])
        rows.append(
            {
                "iso3": iso3,
                "name": name,
                "latest_shift": latest_shift,
                "reviewed": bool(codings),
                "bands": compute_bands(codings),
                "html": (
                    f'<div class="board-row" id="{iso3}" data-name="{esc(name)}" '
                    f'data-shift="{latest_shift}">'
                    f'<div class="row-label"><a href="state/{iso3}.html">{esc(name)}</a>'
                    + (
                        f'<span class="draft-chip">DRAFT</span>'
                        if preview and (codings or shifts) and not all(
                            map(is_approved, codings + shifts)
                        )
                        else ""
                    )
                    + "</div>"
                    + row_track_html(iso3, entry, resolutions, codings, shifts)
                    + "</div>"
                ),
            }
        )
    # Default order: most recent shift first, then coded, then name
    rows.sort(key=lambda r: (r["latest_shift"] == "", not r["reviewed"], r["name"]))
    rows_with_shifts = [r for r in rows if r["latest_shift"]]
    rows_with_shifts.sort(key=lambda r: r["latest_shift"], reverse=True)
    ordered = rows_with_shifts + [r for r in rows if not r["latest_shift"]]
    return ordered


def legend_html():
    items = []
    for code, label in config.POSITION_CATEGORIES.items():
        color = config.PALETTE["positions"][code]
        if code == "AMBIG":
            swatch = '<span class="swatch band-hatch" aria-hidden="true"></span>'
        else:
            swatch = f'<span class="swatch" style="background:{color}" aria-hidden="true"></span>'
        items.append(f"<span>{swatch}{esc(code)}: {esc(label)}</span>")
    items.append(
        "<span><span class=\"swatch\" style=\"border:1px dashed "
        f"{config.PALETTE['ink']}66\" aria-hidden=\"true\"></span>"
        "Empty track: not yet reviewed by this project</span>"
    )
    items.append(
        "<span>Vote marks: solid Yes, crossed ring No, half disc Abstain, faint dash non-voting</span>"
    )
    return '<div class="board-legend">' + "\n".join(items) + "</div>"


def index_page(votes, content_states, preview):
    rows = board_rows(votes, content_states, preview)
    n_reviewed = sum(1 for r in rows if r["reviewed"])
    coverage_line = (
        f"Recorded votes cover all {len(rows)} member states. "
        f"Reviewed position codings cover {n_reviewed} states so far."
    )
    body = f"""
<h1>Who moved, when, and on what record.</h1>
<p>Recorded United Nations votes, official statements, and national policy on
autonomous weapons systems, per state, over time. Positions are trajectories,
not snapshots.</p>
<p class="citation">{esc(coverage_line)}</p>
{legend_html()}
<div class="board-controls">
  <span id="sort-label">Sort rows:</span>
  <button type="button" data-sort="shift" aria-pressed="true">Most recent shift</button>
  <button type="button" data-sort="name" aria-pressed="false">By name</button>
</div>
<section class="board" aria-label="Trajectory board">
  <div class="board-axis">
    <div class="axis-label">State</div>
    {axis_html()}
  </div>
  <div id="board-rows">
{chr(10).join(r["html"] for r in rows)}
  </div>
</section>
"""
    return page(
        "Trajectory board",
        body,
        current="index.html",
        preview=preview,
        description="Where every country stands on autonomous weapons, tracked as positions shift over time.",
    )


# ---------------------------------------------------------------------------
# Votes page
# ---------------------------------------------------------------------------

def votes_page(votes, content_states, preview):
    resolutions = votes["resolutions"]
    states = votes["states"]
    sections = []
    for key, res in resolutions.items():
        groups = {"Y": [], "N": [], "A": [], "X": []}
        for iso3, entry in states.items():
            groups[entry["votes"][key]].append(iso3)
        tally = res["tally"]
        rows = []
        for vote, label in (("Y", "Yes"), ("N", "No"), ("A", "Abstain"), ("X", "Non-voting")):
            names = ", ".join(
                f'<a href="state/{iso3}.html">{esc((content_states.get(iso3, {}).get("display_name") or display_from_un_name(states[iso3]["un_name"])))}</a>'
                for iso3 in groups[vote]
            )
            rows.append(
                f"<tr><th scope=\"row\">{label} ({len(groups[vote])})</th><td>{names}</td></tr>"
            )
        sections.append(f"""
<section class="signal">
  <h2>{esc(res["symbol"])}</h2>
  <p>{esc(res["title"])}</p>
  <p class="citation">Adopted {esc(res["date"])}, {tally["yes"]} in favour, {tally["no"]} against, {tally["abstain"]} abstentions ·
  <a href="{esc(res["undl_link"])}">UN Digital Library record</a></p>
  <table class="vote-table">
{chr(10).join(rows)}
  </table>
</section>
""")
    body = f"""
<h1>Recorded votes</h1>
<p>The three General Assembly resolutions on lethal autonomous weapons systems,
with the recorded vote of every member state. Extracted from the official UN
GA voting dataset; extraction and checks are in the open repository.</p>
{chr(10).join(sections)}
"""
    return page("Votes", body, current="votes.html", preview=preview)


# ---------------------------------------------------------------------------
# State pages
# ---------------------------------------------------------------------------

def evidence_html(e, sources):
    src = sources.get(e.get("source"), {})
    bits = []
    if e.get("quote"):
        bits.append(f'<span class="quote">“{esc(e["quote"])}”</span>')
    elif e.get("description"):
        bits.append(esc(e["description"]))
    link_title = src.get("title", e.get("url", "source"))
    bits.append(
        f'<span class="citation conf-{esc(e.get("confidence", ""))}">'
        f'{esc(iso(e["date"]))} · <a href="{esc(e.get("url", src.get("url", "#")))}">{esc(link_title)}</a>'
        f" · confidence {esc(e.get('confidence', ''))}"
        + (f" · translation {esc(e['translation'])}" if e.get("translation") not in (None, "none") else "")
        + "</span>"
    )
    return "<li>" + "\n".join(bits) + "</li>"


def draft_chip(preview, entry):
    return (
        '<span class="draft-chip">DRAFT</span>'
        if preview and not is_approved(entry)
        else ""
    )


def positions_signal(cs, sources, preview):
    codings = [c for c in cs.get("position_codings", []) if preview or is_approved(c)]
    shifts = [s for s in cs.get("shift_events", []) if preview or is_approved(s)]
    if not codings and not shifts:
        return f"""
<div class="coverage-card">
  <p>Statements for this state are not yet reviewed by this project, as of
  {esc(config.UPDATED_THROUGH)}. That is a statement about this project's
  coverage, not about the state's record. Recorded votes above are complete.</p>
</div>
"""
    parts = []
    for coding in sorted(codings, key=lambda c: iso(c["as_of"])):
        cat = config.POSITION_CATEGORIES.get(coding["code"], "")
        parts.append(f"""
<h3>{esc(coding["code"])} <span class="citation">since {esc(iso(coding["as_of"]))},
confidence {esc(coding["confidence"])}</span>{draft_chip(preview, coding)}</h3>
<p>{esc(cat)}.</p>
{f"<p>{esc(coding['rationale'])}</p>" if coding.get("rationale") else ""}
<ul>
{chr(10).join(evidence_html(e, sources) for e in coding.get("evidence", []))}
</ul>
""")
    for shift in sorted(shifts, key=lambda s: iso(s["date"])):
        parts.append(f"""
<h3>Shift: {esc(shift["from"])} → {esc(shift["to"])}
<span class="citation">{esc(iso(shift["date"]))}</span>{draft_chip(preview, shift)}</h3>
{f"<p>{esc(shift['rationale'])}</p>" if shift.get("rationale") else ""}
<ul>
{chr(10).join(evidence_html(e, sources) for e in shift.get("evidence", []))}
</ul>
""")
    return "\n".join(parts)


def doctrine_signal(cs, sources, preview):
    doctrine = cs.get("doctrine")
    renderable = doctrine and (preview or is_approved(doctrine))
    if not renderable:
        return f"""
<div class="coverage-card">
  <p>Doctrine not yet reviewed by this project, as of {esc(config.UPDATED_THROUGH)}.</p>
</div>
"""
    status = doctrine.get("status")
    chip = draft_chip(preview, doctrine)
    if status == "no_policy_identified":
        phrase = config.DOCTRINE_ABSENCE_PHRASE.format(as_of=iso(doctrine["as_of"]))
        return f"""
<div class="coverage-card">
  <p>{esc(phrase.capitalize())}.{chip}</p>
  <p class="citation">Where this project looked: {esc(doctrine.get("search_note", ""))}</p>
</div>
"""
    if status == "not_yet_reviewed":
        note = "".join(
            f"<p class=\"citation\">{esc(n['note'])}</p>"
            for n in doctrine.get("context", [])
            if n.get("note")
        )
        return f"""
<div class="coverage-card">
  <p>Doctrine not yet reviewed by this project, as of {esc(config.UPDATED_THROUGH)}.{chip}</p>
  {note}
</div>
"""
    parts = []
    for entry in doctrine.get("entries", []):
        if not (preview or is_approved(entry)):
            continue
        parts.append(f"""
<h3>{esc(entry["title"])}{draft_chip(preview, entry)}</h3>
{f"<p>{esc(entry['note'])}</p>" if entry.get("note") else ""}
<ul>
{chr(10).join(evidence_html(e, sources) for e in entry.get("evidence", []))}
</ul>
""")
    for n in doctrine.get("context", []):
        if n.get("note"):
            parts.append(f'<p class="citation">Context: {esc(n["note"])}</p>')
    return "\n".join(parts) if parts else doctrine_signal({}, sources, preview)


def state_page(iso3, entry, votes, cs, sources, preview, manifest):
    resolutions = votes["resolutions"]
    name = cs.get("display_name") or display_from_un_name(entry["un_name"])
    vote_rows = []
    for key in config.LAWS_RESOLUTIONS:
        res = resolutions[key]
        vote = entry["votes"][key]
        vote_rows.append(
            f"<tr><td>{esc(res['symbol'])}</td><td>{esc(res['date'])}</td>"
            f'<td class="vote-glyph">{esc(VOTE_GLYPHS[vote])}</td>'
            f'<td><a href="{esc(res["undl_link"])}">record</a></td></tr>'
        )
    for kind in ("position_codings", "shift_events"):
        for item in cs.get(kind, []):
            manifest["entries"].append(
                {"state": iso3, "kind": kind, "approved": is_approved(item),
                 "rendered": bool(preview or is_approved(item))}
            )
    if cs.get("doctrine"):
        manifest["entries"].append(
            {"state": iso3, "kind": "doctrine", "approved": is_approved(cs["doctrine"]),
             "rendered": bool(preview or is_approved(cs["doctrine"]))}
        )
    body = f"""
<h1>{esc(name)}</h1>
<p class="citation">{esc(entry["un_name"])} · {esc(iso3)}</p>
<section class="signal">
  <h2>Recorded votes</h2>
  <table class="vote-table">
    <tr><th>Resolution</th><th>Date</th><th>Vote</th><th>Source</th></tr>
{chr(10).join(vote_rows)}
  </table>
</section>
<section class="signal">
  <h2>Stated positions</h2>
{positions_signal(cs, sources, preview)}
</section>
<section class="signal">
  <h2>National policy</h2>
{doctrine_signal(cs, sources, preview)}
</section>
"""
    return page(
        name, body, current="", depth=1, preview=preview,
        description=f"{name}: recorded votes, stated positions, and national policy on autonomous weapons systems.",
    )


# ---------------------------------------------------------------------------
# Rubric and prose shells
# ---------------------------------------------------------------------------

def rubric_page(rubric, preview):
    if not (preview or is_approved(rubric)):
        body = f"""
<h1>The coding rubric</h1>
<div class="coverage-card">
  <p>The published rubric appears here once the analyst of record approves
  it. Positions are coded on two axes: instrument preference and confidence.
  As of {esc(config.UPDATED_THROUGH)}, codings are in analyst review.</p>
</div>
"""
        return page("Rubric", body, current="rubric.html", preview=preview)
    cats = []
    for code, cat in (rubric.get("axis_a", {}).get("categories") or {}).items():
        cats.append(
            f"<h3>{esc(code)} <span class=\"citation\">{esc(cat.get('label', ''))}</span></h3>"
            f"<p>{esc(cat.get('description', ''))}</p>"
        )
    tiers = [
        f"<h3>{esc(tier)}</h3><p>{esc(text)}</p>"
        for tier, text in (rubric.get("axis_b", {}).get("tiers") or {}).items()
    ]
    chip = '<span class="draft-chip">DRAFT</span>' if preview and not is_approved(rubric) else ""
    body = f"""
<h1>The coding rubric{chip}</h1>
<p>{esc((rubric.get("axis_a") or {}).get("rules", ""))}</p>
<section class="signal"><h2>Axis A: instrument preference</h2>
{chr(10).join(cats)}</section>
<section class="signal"><h2>Axis B: confidence</h2>
<p>{esc((rubric.get("axis_b") or {}).get("rules", ""))}</p>
{chr(10).join(tiers)}</section>
"""
    return page("Rubric", body, current="rubric.html", preview=preview)


def shell_page(title, current, lines, preview):
    body = f"<h1>{esc(title)}</h1>\n" + "\n".join(f"<p>{line}</p>" for line in lines)
    return page(title, body, current=current, preview=preview)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

def tokens_css():
    pos_vars = "\n".join(
        f"  --pos-{code.lower().replace('-', '')}: {color};"
        for code, color in config.PALETTE["positions"].items()
        if color
    )
    return f""":root {{
  --ground: {config.PALETTE["ground"]};
  --ground-raise: #F1EDE4;
  --ink: {config.PALETTE["ink"]};
  --ink-soft: #55524C;
  --rule: #D9D3C6;
  --rule-faint: #E8E3D8;
  --shadow-tint: rgba(26, 26, 26, 0.12);
  --integrity-red: {config.PALETTE["integrity_red"]};
{pos_vars}
  --font-display: "Newsreader", "Source Serif 4", Georgia, "Times New Roman", serif;
  --font-data: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --label-col: clamp(7.5rem, 18vw, 13rem);
}}
"""


def favicon_svg():
    """Ledger mark: three bands, one visibly broken. The break is the story."""
    ink = config.PALETTE["ink"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<rect width="32" height="32" fill="{config.PALETTE["ground"]}"/>
<rect x="5" y="8" width="22" height="3.5" rx="1" fill="{ink}"/>
<rect x="5" y="14.5" width="12" height="3.5" rx="1" fill="{ink}"/>
<rect x="20" y="14.5" width="7" height="3.5" rx="1" fill="{ink}" fill-opacity="0.45"/>
<rect x="5" y="21" width="22" height="3.5" rx="1" fill="{ink}"/>
</svg>
"""


def poster_svg(votes, content_states):
    """Condensed pre-rendered board poster: the whole wall at a glance."""
    rows = board_rows(votes, content_states, preview=False)
    rh = 4
    height = 40 + rh * len(rows)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {TRACK_W} {height}" '
        f'font-family="Georgia, serif">',
        f'<rect width="{TRACK_W}" height="{height}" fill="{config.PALETTE["ground"]}"/>',
        f'<text x="8" y="24" font-size="18" fill="{config.PALETTE["ink"]}">'
        f"{esc(config.SITE_NAME)}: positions over time, {config.TIMELINE_START_YEAR} to {T1.year}</text>",
    ]
    y = 40
    ink = config.PALETTE["ink"]
    for r in rows:
        for band in r["bands"]:
            if band["code"] == "AMBIG":
                continue  # the poster is a glance artifact; hatch needs defs
            color = config.PALETTE["positions"][band["code"]]
            if color is None:
                continue
            parts.append(
                f'<rect x="{band["left"]:.1f}" y="{y}" '
                f'width="{band["width"]:.1f}" height="{rh - 1}" fill="{color}" '
                f'fill-opacity="{band["opacity"]}"/>'
            )
        for key in config.LAWS_RESOLUTIONS:
            x = x_of(votes["resolutions"][key]["date"])
            vote = votes["states"][r["iso3"]]["votes"][key]
            op = {"Y": "0.9", "N": "0.9", "A": "0.6", "X": "0.2"}[vote]
            parts.append(
                f'<rect x="{x}" y="{y}" width="3" height="{rh - 1}" fill="{ink}" fill-opacity="{op}"/>'
            )
        y += rh
    parts.append("</svg>")
    return "".join(parts)


BOARD_JS = """// Progressive enhancement only: the board is complete without JavaScript.
(function () {
  "use strict";
  var rowsBox = document.getElementById("board-rows");
  if (rowsBox) {
    document.querySelectorAll(".board-controls button").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var mode = btn.getAttribute("data-sort");
        var rows = Array.prototype.slice.call(rowsBox.children);
        rows.sort(function (a, b) {
          if (mode === "name") {
            return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
          }
          var sa = a.getAttribute("data-shift") || "";
          var sb = b.getAttribute("data-shift") || "";
          if (sa !== sb) return sb.localeCompare(sa);
          return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
        });
        rows.forEach(function (r) { rowsBox.appendChild(r); });
        document.querySelectorAll(".board-controls button").forEach(function (b) {
          b.setAttribute("aria-pressed", String(b === btn));
        });
      });
    });
  }

  var open = null;
  function close() {
    if (open) { open.remove(); open = null; }
  }
  // Popovers are built with textContent, never markup injection, because
  // quote and url values come from the content layer.
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }
  function link(url, label) {
    var a = el("a", null, label);
    a.href = url;
    return a;
  }
  function show(trigger, data) {
    close();
    var pop = el("div", "popover");
    pop.setAttribute("role", "dialog");
    if (data.kind === "vote") {
      pop.appendChild(el("strong", null, data.vote));
      pop.appendChild(document.createTextNode(" on " + data.resolution));
      var cite = el("span", "citation", data.date + " · ");
      cite.appendChild(link(data.url, "UN record"));
      pop.appendChild(cite);
    } else {
      pop.appendChild(el("strong", null, data.from + " → " + data.to));
      pop.appendChild(el("span", "citation", data.date));
      (data.evidence || []).forEach(function (e) {
        var row = el("span", "citation", (e.quote ? "“" + e.quote + "” · " : "") + e.date);
        if (e.url) {
          row.appendChild(document.createTextNode(" · "));
          row.appendChild(link(e.url, "source"));
        }
        if (e.confidence) row.appendChild(document.createTextNode(" · " + e.confidence));
        pop.appendChild(row);
      });
    }
    document.body.appendChild(pop);
    var r = trigger.getBoundingClientRect();
    if (window.matchMedia("(min-width: 641px)").matches) {
      pop.style.left = Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - pop.offsetWidth - 16) + "px";
      pop.style.top = (window.scrollY + r.bottom + 8) + "px";
    }
    open = pop;
  }
  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-vote],[data-shift]") : null;
    if (t && t.hasAttribute("data-vote")) { show(t, JSON.parse(t.getAttribute("data-vote"))); ev.stopPropagation(); return; }
    if (t && t.hasAttribute("data-shift") && t.classList.contains("shift-node")) { show(t, JSON.parse(t.getAttribute("data-shift"))); ev.stopPropagation(); return; }
    close();
  });
  // Triggers are real <button> elements, so Enter and Space already fire
  // click; only Escape needs handling.
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") close();
  });
})();
"""


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(out_dir, preview=False):
    out = Path(out_dir)
    votes = load_votes()
    rubric, sources, content_states = load_content()
    manifest = {"mode": "preview" if preview else "deploy", "entries": []}

    (out / "state").mkdir(parents=True, exist_ok=True)
    (out / "css").mkdir(exist_ok=True)
    (out / "js").mkdir(exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)

    (out / "css" / "tokens.css").write_text(tokens_css(), encoding="utf-8", newline="\n")
    src_css = config.SITE_DIR / "css" / "site.css"
    if src_css.resolve() != (out / "css" / "site.css").resolve():
        shutil.copyfile(src_css, out / "css" / "site.css")
    (out / "js" / "board.js").write_text(BOARD_JS, encoding="utf-8", newline="\n")
    (out / "assets" / "favicon.svg").write_text(favicon_svg(), encoding="utf-8", newline="\n")
    (out / "assets" / "board-poster.svg").write_text(
        poster_svg(votes, content_states), encoding="utf-8", newline="\n"
    )

    (out / "index.html").write_text(
        index_page(votes, content_states, preview), encoding="utf-8", newline="\n"
    )
    (out / "votes.html").write_text(
        votes_page(votes, content_states, preview), encoding="utf-8", newline="\n"
    )
    (out / "rubric.html").write_text(rubric_page(rubric, preview), encoding="utf-8", newline="\n")
    pages = load_pages()
    (out / "methodology.html").write_text(
        prose_page(
            "methodology", pages,
            [
                "The full methodology write-up publishes after analyst approval.",
                "Until then: every coding on this site traces to a quoted, dated, "
                "linked primary source, and nothing renders without the analyst "
                "of record approving it. The site takes no position on whether "
                "autonomous weapons should be banned or regulated. It records "
                "who says what.",
            ],
            preview, manifest,
        ),
        encoding="utf-8", newline="\n",
    )
    (out / "about.html").write_text(
        prose_page(
            "about", pages,
            [
                "Machine Politics records where every country stands on autonomous "
                "weapons: recorded votes, official statements, and national policy, "
                "tracked as they shift over time.",
                "The site takes no position on whether autonomous weapons should be "
                "banned or regulated. It records who says what.",
            ],
            preview, manifest,
        ),
        encoding="utf-8", newline="\n",
    )
    (out / "corrections.html").write_text(
        prose_page(
            "corrections", pages,
            [
                "The corrections policy publishes with the methodology. Data-"
                "integrity notices, and only they, render in red on this site.",
            ],
            preview, manifest,
        ),
        encoding="utf-8", newline="\n",
    )

    for iso3, entry in votes["states"].items():
        cs = content_states.get(iso3, {})
        (out / "state" / f"{iso3}.html").write_text(
            state_page(iso3, entry, votes, cs, sources, preview, manifest),
            encoding="utf-8", newline="\n",
        )

    manifest["unapproved_rendered"] = sum(
        1 for e in manifest["entries"] if e["rendered"] and not e["approved"]
    )
    (out / "build_manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8", newline="\n"
    )
    assert_deploy_clean(manifest, preview)
    return manifest


def assert_deploy_clean(manifest, preview):
    """A deploy artifact carrying unapproved content is a refusal, not a
    warning (invariant 1)."""
    if not preview and manifest["unapproved_rendered"]:
        raise SystemExit("deploy build rendered unapproved content; refusing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true",
                        help="render unapproved content behind a DRAFT banner "
                             "into .scratch/preview/ (never deployed)")
    parser.add_argument("--out", default=None, help="override output directory")
    args = parser.parse_args()
    if args.out:
        out = Path(args.out)
    elif args.preview:
        out = config.REPO_ROOT / ".scratch" / "preview"
    else:
        out = config.SITE_DIR
    manifest = build(out, preview=args.preview)
    print(
        f"built {manifest['mode']} site at {out}: "
        f"{len(list((Path(out) / 'state').glob('*.html')))} state pages, "
        f"{manifest['unapproved_rendered']} unapproved entries rendered"
    )


if __name__ == "__main__":
    main()
