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
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import date, timedelta
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


def load_tour():
    path = config.CONTENT_DIR / "tour.yaml"
    return load_yaml(path) if path.exists() else None


def load_endorsements():
    path = config.CONTENT_DIR / "endorsements.yaml"
    return (load_yaml(path).get("instruments") or []) if path.exists() else []


def load_sponsorships():
    path = config.CONTENT_DIR / "sponsorships.yaml"
    return (load_yaml(path).get("records") or []) if path.exists() else []


def load_eras(iso3):
    """Government eras are context data (invariant 14): factual labels and
    dates, no approval gate because nothing in them is a claim about a
    position. The validator enforces the no-causal-copy rule."""
    path = config.CONTENT_DIR / "eras" / f"{iso3}.yaml"
    return (load_yaml(path).get("eras") or []) if path.exists() else []


def state_display_name(iso3, votes, content_states):
    cs = content_states.get(iso3, {})
    entry = votes["states"].get(iso3)
    if entry is None:
        return None  # non-member: no board row, no vote record
    return cs.get("display_name") or display_from_un_name(entry["un_name"])


def substantive_changers(votes):
    """States whose cast vote (Y/N/A) changed across the three resolutions.
    Moves between voting and non-voting are attendance, not position."""
    out = []
    for iso3, entry in votes["states"].items():
        cast = {entry["votes"][k] for k in config.LAWS_RESOLUTIONS} - {"X"}
        if len(cast) > 1:
            out.append(iso3)
    return sorted(out)


def tally_bar_html(tally):
    non_voting = 193 - tally["yes"] - tally["no"] - tally["abstain"]
    segments = []
    for count, label, opacity in (
        (tally["yes"], "Yes", "0.9"),
        (tally["no"], "No", "0.65"),
        (tally["abstain"], "Abstain", "0.45"),
        (non_voting, "Non-voting", "0.22"),
    ):
        if count:
            segments.append(
                f'<span style="width:{count / 193 * 100:.2f}%;opacity:{opacity}" '
                f'title="{label}: {count}"></span>'
            )
    return (
        '<div class="tally-bar" role="img" '
        f'aria-label="{tally["yes"]} yes, {tally["no"]} no, '
        f'{tally["abstain"]} abstain, {non_voting} non-voting">'
        + "".join(segments) + "</div>"
    )


# Tour figures. The board earns its legibility from its shared year axis
# and reading key; inside the tour neither exists, so every figure is
# purpose-built and carries its own numbers and labels. The resolutions
# cluster after mid-2023, so the tour figures use a zoomed domain.
MOVE_T0 = date(2023, 6, 1)


def move_x(d, w=1000.0):
    """Map a date into the tour's zoomed domain, with 4% margins."""
    span = (T1 - MOVE_T0).days
    frac = max(0.0, min(1.0, (as_date(d) - MOVE_T0).days / span))
    return round((0.04 + 0.92 * frac) * w, 1)


# ---------------------------------------------------------------------------
# The persistent canvas (P2c). ONE server-rendered board that the tour
# reveals progressively: it is complete markup at build time (the end
# state), hidden until JS enhances, so the no-JS and reduced-motion paths
# read the stacked prose above the classic board and lose nothing.
# The canvas uses a zoomed domain: the resolutions cluster after mid-2023
# and the story ends at the Review Conference.
# ---------------------------------------------------------------------------

CANVAS_T0 = date(2023, 6, 1)
CANVAS_T1 = date(2027, 1, 15)
REVCON_START = date(2026, 11, 16)


def canvas_x(d):
    """Percent position in the canvas domain, with 5%/95% margins."""
    span = (CANVAS_T1 - CANVAS_T0).days
    frac = max(0.0, min(1.0, (as_date(d) - CANVAS_T0).days / span))
    return round((0.05 + 0.90 * frac) * 100, 2)


def canvas_stats(votes, content_states, preview):
    """Stat-row values: sourced counts only (handoff II.3). Tallies come
    from the dataset's reconciled tally block; non-voting is counted from
    the dataset's X values, never back-computed. Disagreement between the
    two is a build failure, not a rounding choice."""
    per_res = {}
    for key in config.LAWS_RESOLUTIONS:
        res = votes["resolutions"][key]
        t = res["tally"]
        nv = sum(1 for e in votes["states"].values() if e["votes"][key] == "X")
        if t["yes"] + t["no"] + t["abstain"] + nv != len(votes["states"]):
            raise SystemExit(
                f"stat-row reconciliation failed for {key}: tally block and "
                "per-state non-voting count disagree"
            )
        per_res[key] = dict(t, non_voting=nv, year=res["date"][:4], date=res["date"])
    coded = sum(
        1 for iso3 in votes["states"]
        if any(preview or is_approved(c)
               for c in content_states.get(iso3, {}).get("position_codings", []))
    )
    return {
        "res": per_res,
        "coded": coded,
        "movers": len(substantive_changers(votes)),
        "states": len(votes["states"]),
    }


def _last_move_year(entry):
    """Year of the state's most recent cast-vote change, or None."""
    prev, year = None, None
    for key in config.LAWS_RESOLUTIONS:
        vote = entry["votes"][key]
        if vote == "X":
            continue
        if prev is not None and vote != prev:
            year = config.LAWS_RESOLUTIONS[key]["year"]
        prev = vote
    return year


def canvas_row_html(iso3, entry, resolutions, cs, preview):
    name = cs.get("display_name") or display_from_un_name(entry["un_name"])
    codings = [c for c in cs.get("position_codings", []) if preview or is_approved(c)]
    shifts = [s for s in cs.get("shift_events", []) if preview or is_approved(s)]
    parts = []
    timeline = sorted(codings, key=lambda c: iso(c["as_of"]))
    for i, c in enumerate(timeline):
        left = canvas_x(c["as_of"])
        right = canvas_x(timeline[i + 1]["as_of"]) if i + 1 < len(timeline) else 95.0
        if right <= left:
            continue
        style, extra = band_style(c["code"], c.get("confidence"))
        parts.append(
            f'<i class="c-band{extra}" data-code="{esc(c["code"])}" '
            f'style="left:{left}%;width:{right - left:.2f}%;{style}"></i>'
        )
    for s in shifts:
        # The seam is one of red's two reserved meanings (DESIGN v2.1 rule
        # 10): the moment a coded position changes, direction-neutral.
        parts.append(f'<i class="c-seam" style="left:{canvas_x(s["date"])}%"></i>')
    for key in config.LAWS_RESOLUTIONS:
        vote = entry["votes"][key]
        parts.append(
            f'<span class="c-mark c-mark-{vote}" '
            f'style="left:{canvas_x(resolutions[key]["date"])}%">'
            + vote_glyph_svg(vote, 12) + "</span>"
        )
    note = next(
        (str(c["provisional_note"]).strip() for c in timeline
         if c.get("provisional_note")), None,
    )
    note_html = (
        f'<span class="c-note citation">{esc(note)}</span>' if note else ""
    )
    move_year = _last_move_year(entry)
    attrs = [
        f'data-iso3="{iso3}"',
        f'data-name="{esc(name)}"',
    ]
    if move_year:
        attrs.append(f'data-move-year="{move_year}"')
    if timeline:
        attrs.append(f'data-code="{esc(timeline[-1]["code"])}"')
    return (
        f'<div class="c-row" {" ".join(attrs)}>'
        f'<span class="c-label">{esc(name)}</span>'
        f'<span class="c-track">{"".join(parts)}</span>'
        f"{note_html}</div>"
    )


def canvas_teach_sets(stats):
    """The teaching sentences: plain lines naming unit and count above the
    mark-field (the craft standard's highest-value rule). Factual chart
    furniture computed from the dataset, never analyst prose."""
    r = stats["res"]
    keys = list(config.LAWS_RESOLUTIONS)
    r1, r2, r3 = (r[k] for k in keys)
    return {
        "b1": "",
        "b2": f"One state. One recorded vote, adopted {r1['date']}.",
        "b3": "One state. Three recorded votes, 2023 to 2025.",
        "b4": "One state. Three recorded votes, 2023 to 2025.",
        "b5": "The band is the coded position. The seam marks the change.",
        "b6": "Two states. Three recorded votes each.",
        "b7": f"{stats['movers']} states changed a recorded vote. One row per state.",
        "b8": f"{stats['coded']} states with a coded position, one row per state.",
        "b9": f"{stats['states']} member states. One row per state, three recorded votes each.",
        "b10": f"{stats['states']} member states. Seventh Review Conference: 16 to 20 November 2026.",
    }


def canvas_stat_sets(stats):
    """Stat-row variants per beat: always hard numbers, never adjectives."""
    r = stats["res"]
    keys = list(config.LAWS_RESOLUTIONS)

    def tally_chip(k):
        t = r[k]
        return (
            f'<span class="c-stat"><strong>{t["year"]}</strong> '
            f'{t["yes"]} Y · {t["no"]} N · {t["abstain"]} A · '
            f'{t["non_voting"]} NV</span>'
        )

    first = r[keys[0]]
    all_three = "".join(tally_chip(k) for k in keys)
    full = (
        f'<span class="c-stat"><strong>{stats["states"]}</strong> states</span>'
        '<span class="c-stat"><strong>3</strong> recorded votes</span>'
        f'<span class="c-stat"><strong>{stats["coded"]}</strong> positions coded</span>'
    )
    # Beat 2's stat-row is a single figure (the storyboard's one-unit
    # start); the full tallies arrive with the third vote at beat 3.
    return {
        "b1": "",
        "b2": (
            '<span class="c-stat"><strong>1</strong> recorded vote shown · '
            f'{first["yes"]} in favour, {first["no"]} against, '
            f'{first["abstain"]} abstentions</span>'
        ),
        "b3": all_three,
        "b4": all_three,
        "b5": all_three,
        "b6": all_three,
        "b7": f'<span class="c-stat"><strong>{stats["movers"]}</strong> states changed a recorded vote</span>',
        "b8": (
            f'<span class="c-stat"><strong>{stats["coded"]}</strong> coded</span>'
            f'<span class="c-stat"><strong>{stats["states"] - stats["coded"]}</strong> not yet coded</span>'
        ),
        "b9": full,
        "b10": full,
    }


def canvas_html(votes, content_states, preview):
    """The whole canvas, server-rendered in its end state: 193 rows, every
    mark, band, and seam, the stat-row sets, the teaching sentences, and
    the deadline line. JS only reveals and transforms; it never builds."""
    resolutions = votes["resolutions"]
    stats = canvas_stats(votes, content_states, preview)
    ordered = sorted(
        votes["states"].items(),
        key=lambda kv: (
            content_states.get(kv[0], {}).get("display_name")
            or display_from_un_name(kv[1]["un_name"])
        ),
    )
    rows = "\n".join(
        canvas_row_html(iso3, entry, resolutions, content_states.get(iso3, {}), preview)
        for iso3, entry in ordered
    )
    teach = "".join(
        f'<p class="c-teach" data-set="{k}"{" hidden" if k != "b9" else ""}>{esc(v)}</p>'
        for k, v in canvas_teach_sets(stats).items() if v
    )
    stat_sets = "".join(
        f'<div class="c-statset" data-set="{k}"{" hidden" if k != "b9" else ""}>{v}</div>'
        for k, v in canvas_stat_sets(stats).items() if v
    )
    dx = canvas_x(REVCON_START)
    deadline = (
        f'<div class="c-deadline" style="left:{dx}%">'
        '<svg viewBox="0 0 10 100" preserveAspectRatio="none" aria-hidden="true">'
        '<line id="deadline-line" x1="5" y1="0" x2="5" y2="100" '
        f'stroke="{config.PALETTE["ink"]}" stroke-width="2" '
        'stroke-dasharray="6 5"/></svg>'
        '<span class="c-deadline-label citation">16 to 20 Nov 2026</span></div>'
    )
    return f"""
    <div class="scrolly-canvas" id="scrolly-canvas" hidden>
      <div class="c-teach-slot" aria-live="polite">{teach}</div>
      <div class="c-board-wrap">
        <div class="c-board" id="c-board" data-beat="9">
{rows}
        </div>
        {deadline}
      </div>
      <div class="c-stats" aria-live="polite">{stat_sets}</div>
    </div>"""


def tour_html(tour, votes, content_states, preview):
    """The scrollytelling scaffold: ten stacked prose beats (the no-JS and
    reduced-motion path) beside the hidden server-rendered canvas. JS
    enhances into the two-column sticky layout; nothing here depends on
    script to be readable."""
    beats = []
    for i, beat in enumerate(tour.get("beats", []), 1):
        chip = (
            '<span class="draft-chip">DRAFT</span>'
            if preview and not is_approved(tour)
            else ""
        )
        beats.append(f"""
  <section class="beat" id="beat-{esc(beat["id"])}" data-beat="{i}">
    <div class="beat-copy">
      <h2>{esc(beat["title"])}{chip}</h2>
      <p>{esc(beat["copy"])}</p>
    </div>
  </section>""")
    return (
        '<a class="skip-board" href="#board-top">Skip to the board</a>\n'
        '<section class="tour" id="tour" aria-label="Guided tour">\n'
        '  <div class="scrolly">\n'
        '    <div class="scrolly-steps">'
        + "".join(beats)
        + "\n    </div>"
        + canvas_html(votes, content_states, preview)
        + "\n  </div>\n</section>\n"
    )


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

    def link(m):
        label, url = m.group(1), m.group(2)
        # http(s) and relative paths only; anything else stays plain text
        if re.match(r"^(https?://|[A-Za-z0-9_./#-]+$)", url) and not url.lower().startswith("javascript"):
            return f'<a href="{url}">{label}</a>'
        return label

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


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

# Animation stack: pinned version + SRI from cdnjs, loaded deferred and only
# on pages that render the tour. The tour is enhancement; the scaffold and
# the board are complete without it (DESIGN v2, binding).
# Division of labor (craft standard): Scrollama says WHEN, CSS sticky
# HOLDS, GSAP DRAWS. ScrollTrigger is deliberately absent: one scroll
# driver, not two.
GSAP_VERSION = "3.15.0"
GSAP_SCRIPTS = (
    ("gsap.min.js",
     "sha512-Qrpii3NEFZ02RN6ZqpTu6pS/5PEq7EzBYJLki3AKBd8IncrlAwQdZHzExYwS0+b1NM0/qfxI1GOhqWLVosocDA=="),
    ("DrawSVGPlugin.min.js",
     "sha512-AxhfgcJYY6BU9wEF3FLWSrBjzra6a0tIdNPZIG5mhdCCtrrvzkMDEARvWsTGR9FJG9z/t8l9g5gJqtMIt5Nf5w=="),
)


# Scrollama (MIT): step enter/exit triggering only, per the craft-standard
# division of labor (Scrollama says WHEN, CSS sticky HOLDS, GSAP DRAWS).
# License notes for the whole stack: docs/THIRD_PARTY.md.
SCROLLAMA_VERSION = "3.2.0"
SCROLLAMA_SRI = "sha512-YE2BOLTLBOkZ10ahg304yD425ncH98QTjdCgfsjzAJB1tMHWeruT4BBrHL2FXfXLjFJqfsB7I7qhqxubPsT/dw=="


def gsap_script_tags():
    tags = [
        f'<script defer src="https://cdnjs.cloudflare.com/ajax/libs/gsap/{GSAP_VERSION}/{name}" '
        f'integrity="{sri}" crossorigin="anonymous"></script>'
        for name, sri in GSAP_SCRIPTS
    ]
    tags.append(
        f'<script defer src="https://cdnjs.cloudflare.com/ajax/libs/scrollama/{SCROLLAMA_VERSION}/scrollama.min.js" '
        f'integrity="{SCROLLAMA_SRI}" crossorigin="anonymous"></script>'
    )
    return "\n".join(tags)


NAV = [
    ("index.html", "Board"),
    ("votes.html", "Votes"),
    ("instruments.html", "Instruments"),
    ("rubric.html", "Rubric"),
    ("methodology.html", "Methodology"),
    ("about.html", "About"),
    ("corrections.html", "Corrections"),
]


def page(title, body, *, current, depth=0, preview=False, description="",
         absolute=False, extra_scripts="", extra_head=""):
    # Pages serves 404.html from any missing path, so its asset links must
    # be root-absolute; every real page stays relative and previewable
    prefix = "/" if absolute else "../" * depth
    if extra_scripts:
        extra_scripts = extra_scripts + "\n"
    if extra_head:
        extra_head = extra_head + "\n"
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
{extra_head}</head>
<body>
{banner}<header class="masthead">
  <div class="shell masthead-inner">
    <a class="wordmark" href="{prefix}index.html">{esc(config.SITE_NAME)}</a>
    <nav class="primary" aria-label="Site">
{nav}
    </nav>
    <span class="masthead-date updated-through">Updated through {esc(config.UPDATED_THROUGH)}</span>
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
{extra_scripts}</body>
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


def vote_glyph_svg(vote, size=12):
    """Monochrome ink shapes; meaning never carried by hue. The tour
    renders them larger, the board at 12px."""
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
    return (
        f'<svg viewBox="0 0 12 12" width="{size}" height="{size}" '
        f'aria-hidden="true">{shape}</svg>'
    )


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
                "note": (str(coding["provisional_note"]).strip()
                         if coding.get("provisional_note") else None),
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
        if band.get("note"):
            title += f". {band['note']}"
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
    payload = {
        "kind": "shift",
        "from": shift["from"],
        "to": shift["to"],
        "date": iso(shift["date"]),
        "evidence": ev,
    }
    if shift.get("provisional_note"):
        payload["provisional"] = str(shift["provisional_note"]).strip()
    return payload


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


def index_page(votes, content_states, preview, tour=None):
    rows = board_rows(votes, content_states, preview)
    n_reviewed = sum(1 for r in rows if r["reviewed"])
    coverage_line = (
        f"Recorded votes cover all {len(rows)} member states. "
        f"Reviewed position codings cover {n_reviewed} states so far."
    )
    tour_block = ""
    extra_scripts = ""
    if tour and (preview or is_approved(tour)):
        tour_block = tour_html(tour, votes, content_states, preview)
        extra_scripts = gsap_script_tags() + '\n<script defer src="js/tour.js"></script>'
    body = f"""
{tour_block}<div class="board-head" id="board-top">
  <div class="board-lede">
    <h1>Who moved, when, and <em>on what record</em>.</h1>
    <p>Recorded United Nations votes, official statements, and national policy
    on autonomous weapons systems, per state, over time. Positions are
    trajectories, not snapshots.</p>
    <p class="citation">{esc(coverage_line)}</p>
  </div>
  <aside class="board-key" aria-label="How to read the board">
{legend_html()}
  </aside>
</div>
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
        extra_scripts=extra_scripts,
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
        tally_bar = tally_bar_html(tally)
        rows = []
        for vote, label in (("Y", "Yes"), ("N", "No"), ("A", "Abstain"), ("X", "Non-voting")):
            named = sorted(
                (
                    (content_states.get(iso3, {}).get("display_name")
                     or display_from_un_name(states[iso3]["un_name"])),
                    iso3,
                )
                for iso3 in groups[vote]
            )
            names = ", ".join(
                f'<a href="state/{iso3}.html">{esc(name)}</a>' for name, iso3 in named
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
  {tally_bar}
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
<h3><span class="conf-{esc(coding["confidence"])}">{esc(coding["code"])}</span>
<span class="citation">since {esc(iso(coding["as_of"]))},
confidence {esc(coding["confidence"])}</span>{draft_chip(preview, coding)}</h3>
<p>{esc(cat)}.</p>
{provisional_caption(coding)}{f"<p>{esc(coding['rationale'])}</p>" if coding.get("rationale") else ""}
<ul>
{chr(10).join(evidence_html(e, sources) for e in coding.get("evidence", []))}
</ul>
""")
    for shift in sorted(shifts, key=lambda s: iso(s["date"])):
        parts.append(f"""
<h3>Shift: {esc(shift["from"])} → {esc(shift["to"])}
<span class="citation">{esc(iso(shift["date"]))}</span>{draft_chip(preview, shift)}</h3>
{provisional_caption(shift)}{f"<p>{esc(shift['rationale'])}</p>" if shift.get("rationale") else ""}
<ul>
{chr(10).join(evidence_html(e, sources) for e in shift.get("evidence", []))}
</ul>
""")
    return "\n".join(parts)


def provisional_caption(entry):
    """The provisional_note is a designed visible caption (DESIGN v2.1
    rule 11), not a footnote: it renders wherever the coding renders."""
    note = entry.get("provisional_note")
    if not note:
        return ""
    return f'<p class="provisional-note citation">{esc(str(note).strip())}</p>\n'


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


# ---------------------------------------------------------------------------
# Doctrine timeline (per-state surface, DESIGN v2)
# ---------------------------------------------------------------------------

TIMELINE_H = 88
TIMELINE_BASE_Y = 58


def _doctrine_timeline_records(cs, preview):
    """Two marker classes: core doctrine entries render FILLED, dated context
    instruments render OUTLINED. Deploy hard-excludes anything unapproved:
    the whole doctrine block gates first, then every entry."""
    doctrine = cs.get("doctrine") or {}
    if not (preview or is_approved(doctrine)):
        return []
    records = []
    for entry in doctrine.get("entries") or []:
        if not isinstance(entry, dict) or not (preview or is_approved(entry)):
            continue
        ev = [e for e in entry.get("evidence") or [] if isinstance(e, dict)]
        dates = [as_date(e["date"]) for e in ev if e.get("date")]
        d = entry.get("date") or (min(dates) if dates else None)
        if d is None:
            continue
        records.append({
            "kind": "core",
            "date": as_date(d),
            "title": entry.get("title", ""),
            "url": entry.get("url") or next((e.get("url") for e in ev if e.get("url")), None),
            "archived": entry.get("archived"),
            "approved": is_approved(entry),
        })
    for note in doctrine.get("context") or []:
        if not isinstance(note, dict) or not note.get("date"):
            continue
        if not (preview or is_approved(note)):
            continue
        records.append({
            "kind": "context",
            "date": as_date(note["date"]),
            "title": note.get("title") or note.get("note", ""),
            "url": note.get("url"),
            "archived": note.get("archived"),
            "approved": is_approved(note),
        })
    records.sort(key=lambda r: (r["date"], r["title"]))
    return records


def _era_bands(eras):
    """Era bands are background context: alternating the two neutral era
    tokens in file (chronological) order, clamped to the board's span."""
    bands = []
    for i, era in enumerate(eras):
        start = as_date(era["start"])
        end = as_date(era["end"]) if era.get("end") else T1
        if end < T0 or start > T1:
            continue
        left = x_of(max(start, T0), 100)
        right = x_of(min(end, T1), 100)
        if right <= left:
            continue
        bands.append({
            "label": era.get("label", ""),
            "start": start,
            "end": as_date(era["end"]) if era.get("end") else None,
            "left": left,
            "width": right - left,
            "shade": "a" if i % 2 == 0 else "b",
        })
    return bands


def doctrine_timeline_html(name, cs, eras, preview):
    """Horizontal dated timeline: era bands behind a baseline, core doctrine
    as filled markers, dated context instruments as outlined markers, and a
    server-rendered dated list below. Complete without JavaScript."""
    records = _doctrine_timeline_records(cs, preview)
    bands = _era_bands(eras or [])
    if not records and not bands:
        return ""
    svg = [
        f'<svg class="timeline-svg" width="100%" height="{TIMELINE_H}" '
        f'role="img" aria-label="Doctrine timeline for {esc(name)}, '
        f'{config.TIMELINE_START_YEAR} to {esc(config.UPDATED_THROUGH)}. '
        'The dated list below carries the same entries.">'
    ]
    for band in bands:
        span = (
            f"{band['start'].year} to {band['end'].year}"
            if band["end"] else f"since {band['start'].year}"
        )
        svg.append(
            f'<rect x="{band["left"]:.2f}%" y="0" width="{band["width"]:.2f}%" '
            f'height="{TIMELINE_H}" style="fill:var(--era-{band["shade"]})">'
            f"<title>{esc(band['label'])}, {esc(span)}</title></rect>"
        )
        if band["width"] >= 18:
            svg.append(
                f'<text x="{band["left"] + 0.8:.2f}%" y="18" class="era-label">'
                f"{esc(band['label'])}</text>"
            )
    svg.append(
        f'<line x1="0" y1="{TIMELINE_BASE_Y}" x2="100%" y2="{TIMELINE_BASE_Y}" '
        'class="timeline-base"/>'
    )
    for r in records:
        klass = "tl-core" if r["kind"] == "core" else "tl-context"
        kind_label = "core doctrine" if r["kind"] == "core" else "context instrument"
        svg.append(
            f'<circle cx="{pct(r["date"])}" cy="{TIMELINE_BASE_Y}" r="6" '
            f'class="{klass}"><title>{esc(r["title"])} · {esc(iso(r["date"]))} · '
            f"{kind_label}</title></circle>"
        )
    svg.append("</svg>")
    legend_items = []
    for band in bands:
        span = (
            f"{band['start'].year} to {band['end'].year}"
            if band["end"] else f"since {band['start'].year}"
        )
        legend_items.append(
            f'<span><span class="swatch" style="background:var(--era-{band["shade"]})" '
            f'aria-hidden="true"></span>{esc(band["label"])}, {esc(span)}</span>'
        )
    legend = (
        '<p class="era-legend citation">Government eras (context, never a signal): '
        + " ".join(legend_items) + "</p>"
        if legend_items else ""
    )
    items = []
    for r in records:
        links = ""
        if r["url"]:
            links += f' · <a href="{esc(r["url"])}">source</a>'
        if r["archived"]:
            links += f' · <a href="{esc(r["archived"])}">archived</a>'
        kind_label = (
            "core doctrine, filled marker" if r["kind"] == "core"
            else "context instrument, outlined marker"
        )
        chip = (
            '<span class="draft-chip">DRAFT</span>'
            if preview and not r["approved"] else ""
        )
        items.append(
            f"<li>{esc(iso(r['date']))} · {esc(r['title'])}{chip}"
            f'<span class="citation">{kind_label}{links}</span></li>'
        )
    dated_list = (
        '<ul class="timeline-list">\n' + "\n".join(items) + "\n</ul>"
        if items else ""
    )
    return f"""
<div class="doctrine-timeline">
  <div class="timeline-inner">
  {chr(10).join(svg)}
  <div class="track-years" aria-hidden="true"><span>{config.TIMELINE_START_YEAR}</span><span>{T1.year}</span></div>
  </div>
</div>
{legend}
{dated_list}
"""


def state_page(iso3, entry, votes, cs, sources, preview, manifest, eras=None):
    resolutions = votes["resolutions"]
    name = cs.get("display_name") or display_from_un_name(entry["un_name"])
    codings = [c for c in cs.get("position_codings", []) if preview or is_approved(c)]
    shifts = [s for s in cs.get("shift_events", []) if preview or is_approved(s)]
    mini_track = row_track_html(iso3, entry, resolutions, codings, shifts)
    vote_rows = []
    for key in config.LAWS_RESOLUTIONS:
        res = resolutions[key]
        vote = entry["votes"][key]
        vote_rows.append(
            f"<tr><td>{esc(res['symbol'])}</td><td>{esc(res['date'])}</td>"
            f'<td class="vote-glyph">{vote_glyph_svg(vote)} {esc(VOTE_GLYPHS[vote])}</td>'
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
<div class="state-track" aria-label="This state's track on the trajectory board">
  <div class="track-years" aria-hidden="true"><span>{config.TIMELINE_START_YEAR}</span><span>{T1.year}</span></div>
  {mini_track}
</div>
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
{doctrine_timeline_html(name, cs, eras, preview)}{doctrine_signal(cs, sources, preview)}
</section>
"""
    return page(
        name, body, current="", depth=1, preview=preview,
        description=f"{name}: recorded votes, stated positions, and national policy on autonomous weapons systems.",
    )


# ---------------------------------------------------------------------------
# Instruments page: endorsement + sponsorship record, quadrant view, wave map
# ---------------------------------------------------------------------------

# MapLibre GL JS: pinned version with SRI hashes from cdnjs, loaded deferred
# and ONLY on the instruments page when endorsement instruments render. The
# server-rendered lists and tables ARE the content; the map is enhancement.
MAPLIBRE_VERSION = "5.12.0"
MAPLIBRE_JS_SRI = (
    "sha512-8zwkEbAPWRxEwazkrkQuxRX5rNuyQgoXdMNUnh6CU+Ch0peJ6m6nz505BMte989ZHUQD1R1Iwwz8VV9dYCPVKg=="
)
MAPLIBRE_CSS_SRI = (
    "sha512-GT5+KstPNd/krQxWK1xI+fs/Pwlrekt9E+A9fOLGo2tvG/RsXz99dwH0mbB+zZWwA0gIb/ATWIO3/JIev0xwTA=="
)
MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron"
MAP_CREDIT = "Map data © OpenStreetMap contributors, tiles by OpenFreeMap."

# Country shapes: the world-atlas TopoJSON (Natural Earth derived, public
# domain) is committed at data/source/countries-110m.json; the build converts
# it to GeoJSON deterministically, and only the derived GeoJSON ever lands in
# an output directory (preview only, alongside the map surfaces). Nothing but
# tiles is fetched at runtime from third parties.
COUNTRIES_TOPOJSON = config.DATA_SOURCE_DIR / "countries-110m.json"
ISO_NUMERIC_TABLE = config.DATA_DERIVED_DIR / "iso_numeric_alpha3.json"

# One hue PER instrument view at fixed saturation, drawn from the position
# palette family (all non-red, non-green, colorblind-safe against paper).
# Not-yet-endorsed always renders as paper: not endorsing is not opposing.
INSTRUMENT_HUES = {
    "us-political-declaration": config.PALETTE["positions"]["LBI-BAN"],
    "reaim-2023-call-to-action": config.PALETTE["positions"]["LBI-OPEN"],
    "reaim-2024-blueprint": config.PALETTE["positions"]["REG-SOFT"],
    "reaim-2026-pathways": config.PALETTE["positions"]["CCW-ONLY"],
}

DECLARATION_ID = "us-political-declaration"

# Quadrant geometry (SVG viewBox units). Two unlabeled y rows, four x
# columns; regions carry no names, colors, or icons (DESIGN v2 rule 9).
QUAD_W, QUAD_H = 772, 340
QUAD_COLS = (210.0, 375.0, 540.0, 705.0)
QUAD_ROW_ENDORSED = 108.0
QUAD_ROW_NOT = 244.0
QUAD_JITTER_X = 55.0
QUAD_JITTER_Y = 44.0

MAP_MONTH_START = (2023, 2)
MAP_MONTH_END = (2026, 7)


def _det_jitter(iso3, salt, amp):
    """Deterministic jitter from a hash of the ISO code, never random:
    rebuilds stay byte-identical, and the client scrub reuses these values
    from the embedded JSON. sha256 rather than a polynomial hash so the x
    and y offsets are uncorrelated (a polynomial hash makes them affine in
    the salt, which draws the dots into diagonal streaks)."""
    h = int.from_bytes(hashlib.sha256((iso3 + salt).encode("ascii")).digest()[:2], "big")
    return round((h / 65535.0 - 0.5) * 2 * amp, 1)


def _map_months():
    out = []
    y, m = MAP_MONTH_START
    while (y, m) <= MAP_MONTH_END:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _endorsed_rows(inst):
    return [r for r in inst.get("states") or []
            if isinstance(r, dict) and r.get("status") == "endorsed"]


def _effective_date(row, inst):
    return iso(row.get("date") or inst["date"])


def _named_links(iso3s, votes, content_states):
    named = sorted(
        (state_display_name(iso3, votes, content_states), iso3) for iso3 in iso3s
    )
    return ", ".join(
        f'<a href="state/{iso3}.html">{esc(name)}</a>' for name, iso3 in named
    )


def _flow(text):
    return esc(" ".join(str(text).split()))


def endorsement_section(inst, votes, content_states, preview):
    chip = draft_chip(preview, inst)
    links = f'<a href="{esc(inst["list_source_url"])}">official list</a>'
    if inst.get("list_source_archived"):
        links += f' · <a href="{esc(inst["list_source_archived"])}">archived</a>'
    parts = [
        f'<section class="signal" id="{esc(inst["id"])}">',
        f'<h2>{esc(inst["name"])}{chip}</h2>',
        f'<p class="citation">Instrument date {esc(iso(inst["date"]))} · {links} · '
        f'list as of {esc(iso(inst["list_as_of"]))}</p>',
    ]
    rows = _endorsed_rows(inst)
    members = [r for r in rows if r["iso3"] in votes["states"]]
    non_members = [r for r in rows if r["iso3"] not in votes["states"]]
    if rows:
        parts.append(f"<p>{len(rows)} endorsers on the official list.</p>")
        parts.append(
            '<p class="endorser-list">'
            + _named_links([r["iso3"] for r in members], votes, content_states)
            + "</p>"
        )
        if non_members:
            parts.append("<h3>Non-member endorsers</h3>")
            parts.append('<ul class="nonmember-list">')
            for r in non_members:
                parts.append(
                    f"<li>{esc(r.get('name_as_listed', r['iso3']))} ({esc(r['iso3'])})"
                    f'<span class="citation">{_flow(r.get("non_member_note", ""))}</span></li>'
                )
            parts.append("</ul>")
    elif inst.get("display_note"):
        parts.append(f"<p>{_flow(inst['display_note'])}</p>")
    documented = [
        r for r in inst.get("states") or []
        if isinstance(r, dict) and r.get("status") == "documented_non_endorsement"
    ]
    if documented:
        parts.append("<h3>Documented non-endorsements</h3>")
        parts.append(
            '<p class="citation">Recorded only where an official source documents '
            "attendance without signature. Not listed is never opposition.</p>"
        )
        parts.append('<ul class="nonmember-list">')
        for r in documented:
            name = state_display_name(r["iso3"], votes, content_states) or r.get(
                "name_as_listed", r["iso3"]
            )
            parts.append(
                f"<li>{esc(name)}"
                f'<span class="citation">{_flow(r.get("note", ""))}</span></li>'
            )
        parts.append("</ul>")
    parts.append("</section>")
    return "\n".join(parts)


def sponsorship_section(rec, votes, content_states, preview):
    chip = draft_chip(preview, rec)
    links = f'<a href="{esc(rec["url"])}">document</a>'
    if rec.get("archived"):
        links += f' · <a href="{esc(rec["archived"])}">archived</a>'
    members = rec.get("members") or []
    parts = [
        f'<section class="signal" id="{esc(rec["instrument_id"])}">',
        f'<h2>{esc(rec["name"])}{chip}</h2>',
        f'<p class="citation">{esc(iso(rec["date"]))} · {links}</p>',
        f"<p>{len(members)} states listed.</p>",
        '<p class="endorser-list">'
        + _named_links(members, votes, content_states)
        + "</p>",
    ]
    associates = rec.get("associates") or []
    if associates:
        parts.append(
            f"<p>Associating states ({len(associates)}): "
            + _named_links(associates, votes, content_states)
            + "</p>"
        )
    non_members = rec.get("non_members") or []
    if non_members:
        parts.append("<h3>Non-member participants</h3>")
        parts.append('<ul class="nonmember-list">')
        for nm in non_members:
            parts.append(
                f"<li>{esc(nm.get('name_as_listed', nm.get('iso3', '')))} "
                f"({esc(nm.get('iso3', ''))})"
                f'<span class="citation">{_flow(nm.get("note", ""))}</span></li>'
            )
        parts.append("</ul>")
    parts.append("</section>")
    return "\n".join(parts)


def _quadrant_states(votes, content_states, declaration):
    """Per-state quadrant data: dated Yes votes and the state's Political
    Declaration endorsement date, if listed. Members only: the quadrant is
    the 193 board states."""
    endorsed_dates = {}
    for row in _endorsed_rows(declaration):
        if row["iso3"] in votes["states"]:
            endorsed_dates[row["iso3"]] = _effective_date(row, declaration)
    res_dates = {k: votes["resolutions"][k]["date"] for k in config.LAWS_RESOLUTIONS}
    states = []
    for iso3 in sorted(votes["states"]):
        entry = votes["states"][iso3]
        yes = sorted(
            res_dates[k] for k in config.LAWS_RESOLUTIONS if entry["votes"][k] == "Y"
        )
        states.append({
            "iso3": iso3,
            "name": state_display_name(iso3, votes, content_states),
            "jx": _det_jitter(iso3, "x", QUAD_JITTER_X),
            "jy": _det_jitter(iso3, "y", QUAD_JITTER_Y),
            "yes": yes,
            "endorsed": endorsed_dates.get(iso3),
        })
    return states


def _quadrant_steps(votes, instruments):
    steps = [
        {"date": votes["resolutions"][k]["date"], "label": f"A/RES/{k} adopted"}
        for k in config.LAWS_RESOLUTIONS
    ]
    steps.extend({"date": iso(i["date"]), "label": i["name"]} for i in instruments)
    steps.sort(key=lambda s: (s["date"], s["label"]))
    return steps


def _quadrant_dot_title(st, yes, endorsed, step_date):
    return (
        f"{st['name']} ({st['iso3']}): {yes} Yes vote{'' if yes == 1 else 's'}; "
        f"{'endorsed' if endorsed else 'not listed'}, as of {step_date}"
    )


def _quadrant_svg(states, declaration, step_date):
    ink = config.PALETTE["ink"]
    parts = [
        f'<svg id="quadrant-svg" class="quadrant-svg" viewBox="0 0 {QUAD_W} {QUAD_H}" '
        'role="img" aria-label="Scatter of all 193 member states: Yes votes on the '
        'three UNGA resolutions against Political Declaration endorsement. The '
        'table below carries the same data.">'
    ]
    for row_y in (QUAD_ROW_ENDORSED, QUAD_ROW_NOT):
        parts.append(
            f'<line x1="{QUAD_COLS[0] - 55}" y1="{row_y}" x2="{QUAD_COLS[-1] + 50}" '
            f'y2="{row_y}" stroke="{ink}" stroke-opacity="0.12" stroke-dasharray="2 4"/>'
        )
    parts.append(
        f'<text x="12" y="{QUAD_ROW_ENDORSED - 8}" class="q-axis">'
        f'<tspan x="12">{esc(declaration["name"].split(" on ")[0])}:</tspan>'
        f'<tspan x="12" dy="15">endorsed</tspan></text>'
    )
    parts.append(
        f'<text x="12" y="{QUAD_ROW_NOT - 8}" class="q-axis">'
        f'<tspan x="12">{esc(declaration["name"].split(" on ")[0])}:</tspan>'
        f'<tspan x="12" dy="15">not listed</tspan></text>'
    )
    for count, x in enumerate(QUAD_COLS):
        parts.append(
            f'<text x="{x}" y="308" text-anchor="middle" class="q-axis">{count}</text>'
        )
    mid_x = (QUAD_COLS[0] + QUAD_COLS[-1]) / 2
    parts.append(
        f'<text x="{mid_x}" y="330" text-anchor="middle" class="q-axis">'
        "Yes votes on UNGA resolutions 78/241, 79/62 and 80/57</text>"
    )
    for st in states:
        yes = len([d for d in st["yes"] if d <= step_date])
        endorsed = bool(st["endorsed"] and st["endorsed"] <= step_date)
        cx = QUAD_COLS[yes] + st["jx"]
        cy = (QUAD_ROW_ENDORSED if endorsed else QUAD_ROW_NOT) + st["jy"]
        parts.append(
            f'<circle class="q-dot" data-iso3="{st["iso3"]}" cx="{cx:.1f}" '
            f'cy="{cy:.1f}" r="5"><title>'
            + esc(_quadrant_dot_title(st, yes, endorsed, step_date))
            + "</title></circle>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _json_script(data, element_id):
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    return f'<script type="application/json" id="{element_id}">{payload}</script>'


def quadrant_block(votes, content_states, declaration, instruments):
    states = _quadrant_states(votes, content_states, declaration)
    steps = _quadrant_steps(votes, instruments)
    last = steps[-1]
    # State search (DESIGN v2 mobile contract): the primary nav into the
    # quadrant. Server-rendered, disabled until the script enables it, so a
    # no-JS page never shows a control that swallows input. One datalist
    # option per member state, name and ISO code together, so either matches.
    options = "\n".join(
        f'<option value="{esc(st["name"])} ({st["iso3"]})"></option>'
        for st in sorted(states, key=lambda s: (s["name"], s["iso3"]))
    )
    search = f"""<div class="quadrant-search">
  <label for="quadrant-search">Find a state</label>
  <input type="search" id="quadrant-search" list="quadrant-state-list"
    autocomplete="off" spellcheck="false" disabled>
</div>
<datalist id="quadrant-state-list">
{options}
</datalist>"""
    table_rows = []
    for st in sorted(states, key=lambda s: s["name"]):
        status = (
            f"endorsed {st['endorsed']}" if st["endorsed"] else "not listed"
        )
        table_rows.append(
            f'<tr><td><a href="state/{st["iso3"]}.html">{esc(st["name"])}</a></td>'
            f"<td>{len(st['yes'])}</td><td>{esc(status)}</td></tr>"
        )
    data = {
        "layout": {
            "cols": list(QUAD_COLS),
            "rowEndorsed": QUAD_ROW_ENDORSED,
            "rowNot": QUAD_ROW_NOT,
        },
        "steps": steps,
        "states": states,
    }
    return f"""
<section class="signal" id="quadrant">
<h2>The quadrant view</h2>
<p>Each dot is a member state. Across: how many of the three UNGA resolutions
on lethal autonomous weapons systems the state voted Yes on. Up: whether the
state endorsed the Political Declaration on Responsible Military Use of
Artificial Intelligence and Autonomy. The axes are the instruments. The
regions carry no names.</p>
{search}
<div class="scrub-control">
  <label for="quadrant-time">Timeline</label>
  <input type="range" id="quadrant-time" min="0" max="{len(steps) - 1}" step="1"
    value="{len(steps) - 1}" disabled>
  <output id="quadrant-step" for="quadrant-time">{esc(last["date"])} · {esc(last["label"])}</output>
</div>
<p class="citation">The search box rings a state's dot and filters the table
below; the scrub steps through the three resolution dates and the four
instrument dates. Both need JavaScript. Without it, the chart shows the
record through {esc(config.UPDATED_THROUGH)} and the table carries every
state.</p>
<div class="quadrant-scroll">
{_quadrant_svg(states, declaration, last["date"])}
</div>
{_json_script(data, "quadrant-data")}
<h3>The same data as a table</h3>
<table class="vote-table quadrant-table" id="quadrant-table">
<tr><th>State</th><th>Yes votes (of 3)</th><th>{esc(declaration["name"].split(" on ")[0])}</th></tr>
{chr(10).join(table_rows)}
</table>
</section>
"""


def wave_map_block(instruments):
    months = _map_months()
    radios = []
    map_instruments = []
    for i, inst in enumerate(instruments):
        hue = INSTRUMENT_HUES.get(inst["id"], config.PALETTE["ink"])
        # An instrument with no per-state rows (the Blueprint publishes only
        # a count) paints an all-paper map; say so at the control itself.
        suffix = "" if _endorsed_rows(inst) else " (count only, no named list)"
        radios.append(
            f'<label class="map-radio"><input type="radio" name="map-instrument" '
            f'value="{esc(inst["id"])}"{" checked" if i == 0 else ""}>'
            f'<span class="swatch" style="background:{hue}" aria-hidden="true"></span>'
            f'{esc(inst["name"])}{esc(suffix)}</label>'
        )
        map_instruments.append({
            "id": inst["id"],
            "name": inst["name"],
            "hue": hue,
            "states": [
                {"iso3": r["iso3"], "date": _effective_date(r, inst)}
                for r in _endorsed_rows(inst)
            ],
        })
    data = {
        "months": months,
        "paper": config.PALETTE["ground"],
        "ink": config.PALETTE["ink"],
        "style": MAP_STYLE_URL,
        "instruments": map_instruments,
    }
    return f"""
<section class="signal" id="wave-map-section">
<h2>Endorsement wave map</h2>
<p>One instrument at a time. States that endorsed by the shown month fill in
the instrument's hue. States not yet on the list render as paper. The lists
above are the record; the map only shows the wave.</p>
<fieldset class="map-controls">
  <legend>Instrument</legend>
  {chr(10).join("  " + r for r in radios)}
</fieldset>
<div class="scrub-control">
  <label for="map-time">Month</label>
  <input type="range" id="map-time" min="0" max="{len(months) - 1}" step="1"
    value="{len(months) - 1}" disabled>
  <output id="map-month" for="map-time">{months[-1]}</output>
</div>
<div id="wave-map" class="wave-map" role="region" aria-label="Endorsement wave map"></div>
<p class="map-fallback" id="map-fallback">Map unavailable. It needs JavaScript,
WebGL, and the tile server. The endorsement lists above carry the complete
data.</p>
<p class="citation">{esc(MAP_CREDIT)}</p>
{_json_script(data, "map-data")}
</section>
"""


def instruments_page(votes, content_states, endorsements, sponsorships,
                     preview, manifest):
    for inst in endorsements:
        manifest["entries"].append({
            "state": None,
            "kind": f"endorsement_instrument:{inst.get('id')}",
            "approved": is_approved(inst),
            "rendered": bool(preview or is_approved(inst)),
        })
    for rec in sponsorships:
        manifest["entries"].append({
            "state": None,
            "kind": f"sponsorship_record:{rec.get('instrument_id')}",
            "approved": is_approved(rec),
            "rendered": bool(preview or is_approved(rec)),
        })
    r_inst = [i for i in endorsements if preview or is_approved(i)]
    r_rec = [r for r in sponsorships if preview or is_approved(r)]
    if not r_inst and not r_rec:
        # The factual shell (prose-page pattern): the record is in review,
        # and the deploy artifact says so without leaking a single row.
        return shell_page(
            "Instruments", "instruments.html",
            [
                "Endorsement and sponsorship records appear here once the "
                "analyst of record approves them: which states endorsed which "
                "political-commitment instruments, and which states co-sponsored "
                "which texts, with dates and official list sources.",
                f"As of {esc(config.UPDATED_THROUGH)}, the drafted records are "
                "in analyst review. Endorsement and sponsorship are displayed "
                "facts. They never feed a position coding.",
                'Recorded votes are complete on the '
                '<a href="votes.html">votes page</a>.',
            ],
            preview,
        )
    sections = [
        endorsement_section(i, votes, content_states, preview) for i in r_inst
    ] + [
        sponsorship_section(r, votes, content_states, preview) for r in r_rec
    ]
    declaration = next((i for i in r_inst if i["id"] == DECLARATION_ID), None)
    extra_head = ""
    extra_scripts = ""
    if declaration:
        sections.append(quadrant_block(votes, content_states, declaration, r_inst))
    if r_inst:
        sections.append(wave_map_block(r_inst))
        extra_head = (
            '<link rel="stylesheet" '
            f'href="https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/{MAPLIBRE_VERSION}/maplibre-gl.css" '
            f'integrity="{MAPLIBRE_CSS_SRI}" crossorigin="anonymous">'
        )
        extra_scripts = (
            '<script defer '
            f'src="https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/{MAPLIBRE_VERSION}/maplibre-gl.min.js" '
            f'integrity="{MAPLIBRE_JS_SRI}" crossorigin="anonymous"></script>\n'
            '<script defer src="js/instruments.js"></script>'
        )
    body = f"""
<h1>Instruments</h1>
<p>Political-commitment endorsements and sponsorship records, per instrument,
from official lists. Endorsement and sponsorship are displayed facts. They
never feed a position coding. A state that is not listed is recorded as not
listed, never as opposed.</p>
{chr(10).join(sections)}
"""
    return page(
        "Instruments", body, current="instruments.html", preview=preview,
        extra_head=extra_head, extra_scripts=extra_scripts,
        description="Endorsement and sponsorship records for the political-commitment instruments on military AI and autonomy.",
    )


def countries_geojson():
    """Deterministic TopoJSON to GeoJSON conversion for the wave map. IDs in
    world-atlas are ISO 3166-1 numeric; the committed pycountry-generated
    table bridges them to alpha-3. Kosovo has no ISO code and maps by name
    to XKX, the same user-assigned code the endorsement records use."""
    topo = json.loads(COUNTRIES_TOPOJSON.read_text(encoding="utf-8"))
    table = json.loads(ISO_NUMERIC_TABLE.read_text(encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    decoded = []
    for arc in topo["arcs"]:
        pts, x, y = [], 0, 0
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((round(x * sx + tx, 4), round(y * sy + ty, 4)))
        decoded.append(pts)

    def ring(arc_ids):
        out = []
        for a in arc_ids:
            pts = decoded[a] if a >= 0 else decoded[~a][::-1]
            if out:
                pts = pts[1:]
            out.extend(pts)
        if out and out[0] != out[-1]:
            out.append(out[0])
        # Natural Earth keeps rings that jump across the antimeridian
        # (Russia, Fiji). A spherical renderer handles that; MapLibre's
        # planar fill draws a band across the world. Unwrap longitudes so
        # each ring is continuous; world copies render the wrapped part.
        unwrapped = [[out[0][0], out[0][1]]]
        for x, y in out[1:]:
            prev_x = unwrapped[-1][0]
            while x - prev_x > 180:
                x -= 360
            while x - prev_x < -180:
                x += 360
            x = round(x, 4)
            if [x, y] != unwrapped[-1]:
                unwrapped.append([x, y])
        return unwrapped

    features = []
    for geom in topo["objects"]["countries"]["geometries"]:
        name = (geom.get("properties") or {}).get("name", "")
        iso3 = table.get(str(geom.get("id")), "")
        if not iso3 and name == "Kosovo":
            iso3 = "XKX"
        if iso3 == "ATA":
            # Antarctica's ring circles the pole: it cannot close once
            # unwrapped, it is not a state, and the basemap already draws
            # the continent. Leave it to the tiles.
            continue
        if geom["type"] == "Polygon":
            coords = [ring(r) for r in geom["arcs"]]
        elif geom["type"] == "MultiPolygon":
            coords = [[ring(r) for r in poly] for poly in geom["arcs"]]
        else:
            continue
        features.append({
            "type": "Feature",
            "properties": {"iso3": iso3, "name": name},
            "geometry": {"type": geom["type"], "coordinates": coords},
        })
    return json.dumps(
        {"type": "FeatureCollection", "features": features},
        sort_keys=True, separators=(",", ":"),
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

def year_grid_gradient():
    """One 1px ledger vertical per year, at the exact timeline position.
    Generated here so the CSS lines can never drift from the data axis."""
    line = "rgba(26, 26, 26, 0.08)"
    stops = ["transparent 0%"]
    for year in range(config.TIMELINE_START_YEAR + 1, T1.year + 1):
        pos = x_of(date(year, 1, 1), 100)
        stops.append(f"transparent {pos - 0.04:.2f}%")
        stops.append(f"{line} {pos - 0.04:.2f}%")
        stops.append(f"{line} {pos + 0.04:.2f}%")
        stops.append(f"transparent {pos + 0.04:.2f}%")
    stops.append("transparent 100%")
    return f"linear-gradient(90deg, {', '.join(stops)})"


FONT_FACES = """\
@font-face {
  font-family: "Newsreader";
  src: url("../assets/fonts/newsreader-var.woff2") format("woff2");
  font-weight: 400 700;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: "Newsreader";
  src: url("../assets/fonts/newsreader-italic-var.woff2") format("woff2");
  font-weight: 400 700;
  font-style: italic;
  font-display: swap;
}
"""


def tokens_css():
    pos_vars = "\n".join(
        f"  --pos-{code.lower().replace('-', '')}: {color};"
        for code, color in config.PALETTE["positions"].items()
        if color
    )
    return f"""{FONT_FACES}:root {{
  --ground: {config.PALETTE["ground"]};
  --ground-raise: #F1EDE4;
  --ink: {config.PALETTE["ink"]};
  --ink-soft: #55524C;
  --rule: #D9D3C6;
  --rule-faint: #E8E3D8;
  --shadow-tint: rgba(26, 26, 26, 0.12);
  /* Era bands: exactly two neutral shades from the paper family, never a
     party color (invariant 14) */
  --era-a: #F4F0E8;
  --era-b: #EAE4D6;
  --integrity-red: {config.PALETTE["integrity_red"]};
{pos_vars}
  --font-display: "Newsreader", Georgia, "Times New Roman", serif;
  --font-data: system-ui, -apple-system, "Segoe UI", sans-serif;
  --label-col: clamp(7.5rem, 18vw, 13rem);
  --year-grid: {year_grid_gradient()};
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
    """Condensed pre-rendered board poster: the whole wall at a glance.
    Zoomed to the voting era (the tour's MOVE_T0 domain) so the 193-row
    wall reads as a record, not empty runway, with each vote column
    labeled with its symbol, year, and recorded tally."""
    rows = board_rows(votes, content_states, preview=False)
    rh = 4
    top = 66
    height = top + rh * len(rows) + 8
    ink = config.PALETTE["ink"]

    def zx(d):
        return move_x(d, TRACK_W)

    def conv(track_units):
        """Track units (x_of domain) back to a date, then into the zoom."""
        d = T0 + timedelta(days=track_units / TRACK_W * (T1 - T0).days)
        return zx(d)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {TRACK_W} {height}" '
        f'font-family="Georgia, serif">',
        f'<rect width="{TRACK_W}" height="{height}" fill="{config.PALETTE["ground"]}"/>',
        f'<text x="12" y="26" font-size="18" fill="{ink}">'
        f"{esc(config.SITE_NAME)}: the recorded votes, one row per member state</text>",
    ]
    # Faint year rules make the sparse span read as ledger paper, and give
    # the three vote columns their time context.
    for year in range(2024, T1.year + 1):
        gx = zx(date(year, 1, 1))
        parts.append(
            f'<line x1="{gx}" y1="36" x2="{gx}" y2="{height - 4}" '
            f'stroke="{ink}" stroke-opacity="0.08" stroke-width="1"/>'
        )
    for key in config.LAWS_RESOLUTIONS:
        res = votes["resolutions"][key]
        x = zx(res["date"])
        t = res["tally"]
        parts.append(
            f'<text x="{x}" y="47" font-size="13" text-anchor="middle" '
            f'fill="{ink}">{esc(key)} · {esc(res["date"][:4])}</text>'
        )
        parts.append(
            f'<text x="{x}" y="61" font-size="10" text-anchor="middle" '
            f'fill="{ink}" fill-opacity="0.65">'
            f'{t["yes"]} Y · {t["no"]} N · {t["abstain"]} A</text>'
        )
    y = top
    for r in rows:
        for band in r["bands"]:
            if band["code"] == "AMBIG":
                continue  # the poster is a glance artifact; hatch needs defs
            color = config.PALETTE["positions"][band["code"]]
            if color is None:
                continue
            left = conv(band["left"])
            right = conv(band["left"] + band["width"])
            if right - left < 1:
                continue
            parts.append(
                f'<rect x="{left:.1f}" y="{y}" '
                f'width="{right - left:.1f}" height="{rh - 1}" fill="{color}" '
                f'fill-opacity="{band["opacity"]}"/>'
            )
        for key in config.LAWS_RESOLUTIONS:
            # Wide marks: a 3px needle vanishes at poster scale; 22 units
            # is about three weeks of timeline, visually a vote column.
            x = zx(votes["resolutions"][key]["date"]) - 11
            vote = votes["states"][r["iso3"]]["votes"][key]
            if vote == "N":  # outline, echoing the crossed-ring glyph
                parts.append(
                    f'<rect x="{x:.1f}" y="{y}" width="22" height="{rh - 1}" '
                    f'fill="none" stroke="{ink}" stroke-width="0.9" stroke-opacity="0.9"/>'
                )
            else:
                op = {"Y": "0.9", "A": "0.5", "X": "0.15"}[vote]
                parts.append(
                    f'<rect x="{x:.1f}" y="{y}" width="22" height="{rh - 1}" '
                    f'fill="{ink}" fill-opacity="{op}"/>'
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
      if (data.provisional) pop.appendChild(el("span", "citation", data.provisional));
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
  // Coarse pointers get one sheet per row: adjacent marks are too close
  // together for separate 44px targets, so the track is the target.
  function showRow(track) {
    close();
    var pop = el("div", "popover");
    pop.setAttribute("role", "dialog");
    var row = track.closest ? track.closest(".board-row") : null;
    var label = row ? row.getAttribute("data-name") : "";
    if (label) pop.appendChild(el("strong", null, label));
    track.querySelectorAll("[data-shift]").forEach(function (node) {
      var d = JSON.parse(node.getAttribute("data-shift"));
      var line = el("span", "citation", "Shift " + d.from + " → " + d.to + ", " + d.date);
      (d.evidence || []).forEach(function (e) {
        if (e.url) {
          line.appendChild(document.createTextNode(" · "));
          line.appendChild(link(e.url, "source"));
        }
      });
      pop.appendChild(line);
    });
    track.querySelectorAll("[data-vote]").forEach(function (node) {
      var d = JSON.parse(node.getAttribute("data-vote"));
      var line = el("span", "citation", d.vote + " on " + d.resolution + ", " + d.date + " · ");
      line.appendChild(link(d.url, "UN record"));
      pop.appendChild(line);
    });
    document.body.appendChild(pop);
    if (window.matchMedia("(min-width: 641px)").matches) {
      var r = track.getBoundingClientRect();
      pop.style.left = Math.min(window.scrollX + r.left, window.scrollX + window.innerWidth - pop.offsetWidth - 16) + "px";
      pop.style.top = (window.scrollY + r.bottom + 8) + "px";
    }
    open = pop;
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-vote],[data-shift]") : null;
    if (t && t.hasAttribute("data-vote")) { show(t, JSON.parse(t.getAttribute("data-vote"))); ev.stopPropagation(); return; }
    if (t && t.hasAttribute("data-shift") && t.classList.contains("shift-node")) { show(t, JSON.parse(t.getAttribute("data-shift"))); ev.stopPropagation(); return; }
    if (window.matchMedia("(pointer: coarse)").matches) {
      var track = ev.target.closest ? ev.target.closest(".row-track") : null;
      if (track) { showRow(track); ev.stopPropagation(); return; }
    }
    close();
  });
  // Triggers are real <button> elements, so Enter and Space already fire
  // click; only Escape needs handling.
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") close();
  });
})();
"""


TOUR_JS = """// Scrollytelling spine (P2c). The stacked prose and the classic board ARE
// the page; everything here is enhancement behind guards. Division of
// labor per the craft standard: Scrollama says WHEN, CSS sticky HOLDS,
// GSAP DRAWS. Motion is one tempo in every direction (neutrality in
// motion, DESIGN v2): a row arriving, leaving, or re-sorting animates
// identically whatever the state did.
(function () {
  "use strict";
  var tour = document.querySelector(".tour");
  if (!tour) return;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var mobile = window.matchMedia("(max-width: 720px), (pointer: coarse)").matches;

  // ---- Mobile contract: tap-through stepper, never scroll-driven ----
  if (mobile) {
    var beats = Array.prototype.slice.call(tour.querySelectorAll(".beat"));
    if (beats.length < 2) return;
    var index = 0;
    var nav = document.createElement("div");
    nav.className = "tour-stepper";
    var prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "Back";
    var counter = document.createElement("span");
    counter.setAttribute("aria-live", "polite");
    var next = document.createElement("button");
    next.type = "button";
    next.textContent = "Next";
    nav.appendChild(prev); nav.appendChild(counter); nav.appendChild(next);
    tour.classList.add("tour-stepped");
    tour.appendChild(nav);
    function show(i) {
      index = Math.max(0, Math.min(beats.length - 1, i));
      beats.forEach(function (b, j) { b.hidden = j !== index; });
      counter.textContent = "Beat " + (index + 1) + " of " + beats.length;
      prev.disabled = index === 0;
      next.textContent = index === beats.length - 1 ? "To the board" : "Next";
    }
    prev.addEventListener("click", function () { show(index - 1); });
    next.addEventListener("click", function () {
      if (index === beats.length - 1) {
        document.getElementById("board-top").scrollIntoView();
        return;
      }
      show(index + 1);
    });
    show(0);
    return;
  }

  // ---- Reduced motion: instant states; the stacked scaffold stands ----
  if (reduced) return;
  if (typeof window.scrollama === "undefined" || typeof window.gsap === "undefined") return;
  var gsap = window.gsap;
  var hasDraw = typeof window.DrawSVGPlugin !== "undefined";
  if (hasDraw) gsap.registerPlugin(window.DrawSVGPlugin);

  var canvas = document.getElementById("scrolly-canvas");
  var board = document.getElementById("c-board");
  if (!canvas || !board) return;

  tour.classList.add("tour-enhanced");
  canvas.hidden = false;

  var rows = Array.prototype.slice.call(board.querySelectorAll(".c-row"));
  var ALL = rows.map(function (r) { return r.getAttribute("data-iso3"); });

  function byName(a, b) {
    return a.getAttribute("data-name").localeCompare(b.getAttribute("data-name"));
  }
  // The movers, sorted by when each state last moved (beat 7).
  var MOVERS = rows.filter(function (r) { return r.hasAttribute("data-move-year"); })
    .sort(function (a, b) {
      var ya = a.getAttribute("data-move-year"), yb = b.getAttribute("data-move-year");
      if (ya !== yb) return ya < yb ? -1 : 1;
      return byName(a, b);
    })
    .map(function (r) { return r.getAttribute("data-iso3"); });
  // The coded states, grouped into camps by category (beat 8). The order
  // is the rubric's own category order: a listing, never a ranking.
  var CODE_ORDER = ["LBI-BAN", "LBI-OPEN", "REG-SOFT", "CCW-ONLY", "OPPOSE", "AMBIG", "NONE"];
  var CODED = rows.filter(function (r) { return r.hasAttribute("data-code"); })
    .sort(function (a, b) {
      var ca = CODE_ORDER.indexOf(a.getAttribute("data-code"));
      var cb = CODE_ORDER.indexOf(b.getAttribute("data-code"));
      if (ca !== cb) return ca - cb;
      return byName(a, b);
    })
    .map(function (r) { return r.getAttribute("data-iso3"); });

  var SCALES = { xl: 88, m: 26, s: 13, xs: 3.4 };
  // The full wall must fit the stage: at poster scale the row height
  // shrinks to fill at most 58% of the viewport.
  function rowHeight(st) {
    var h = SCALES[st.scale];
    if (st.scale === "xs" && st.order.length) {
      h = Math.max(2, Math.min(h, (window.innerHeight * 0.58) / st.order.length));
    }
    return h;
  }

  // One entry per storyboard beat. P3c layers the within-beat drawing
  // (bands, glyph teaching, muting) onto this state model.
  // One entry per storyboard beat: what is on the canvas, at what scale,
  // which marks and layers have been taught so far. Color arrives as an
  // event at beat 5 (bands: true) and never leaves; the movers keep the
  // two known rows saturated as anchors (muting is focus, not valence).
  var STATES = [null,
    { order: [], scale: "xl", set: "b1", deadline: "faint", marks: 0 },
    { order: ["USA"], scale: "xl", set: "b2", marks: 1 },
    { order: ["USA"], scale: "xl", set: "b3", marks: 3, draw: "no-ring" },
    { order: ["USA"], scale: "xl", set: "b4", marks: 3 },
    { order: ["USA"], scale: "xl", set: "b5", marks: 3, bands: true },
    { order: ["USA", "IND"], scale: "xl", set: "b6", marks: 3, bands: true },
    { order: MOVERS, scale: "m", set: "b7", marks: 3, bands: true, anchors: ["USA", "IND"] },
    { order: CODED, scale: "m", set: "b8", marks: 3, bands: true },
    { order: ALL, scale: "xs", set: "b9", marks: 3, bands: true },
    { order: ALL, scale: "xs", set: "b10", marks: 3, bands: true, deadline: "draw" }
  ];

  function showSet(cls, set) {
    Array.prototype.forEach.call(canvas.querySelectorAll("." + cls), function (el) {
      el.hidden = el.getAttribute("data-set") !== set;
    });
  }

  // State application is CSS-transition-driven (set target values, the
  // browser interpolates): unlike ticker-based tweens it lands on the
  // final state even if rendering stalls mid-flight (hidden tab,
  // occluded window). GSAP is reserved for actual drawing (DrawSVG).
  var lastBeat = 0;
  function setBeat(n) {
    var st = STATES[n];
    if (!st) return;
    board.setAttribute("data-beat", String(n));
    board.setAttribute("data-scale", st.scale);
    board.classList.toggle("c-marks-0", st.marks === 0);
    board.classList.toggle("c-marks-1", st.marks === 1);
    board.classList.toggle("c-bands-on", !!st.bands);
    var h = rowHeight(st);
    var pos = {};
    st.order.forEach(function (iso, i) { pos[iso] = i; });
    rows.forEach(function (row) {
      var iso = row.getAttribute("data-iso3");
      row.classList.toggle("c-dim",
        !!st.anchors && iso in pos && st.anchors.indexOf(iso) === -1);
      if (iso in pos) {
        row.style.transform = "translateY(" + (pos[iso] * h).toFixed(2) + "px)";
        row.style.height = Math.max(h - (h > 10 ? 2 : 0.6), 2).toFixed(2) + "px";
        row.classList.remove("c-off");
      } else {
        row.classList.add("c-off");
      }
    });
    // The one within-beat GSAP draw so far: the crossed ring draws itself
    // as the word no arrives (beat 3, forward entries only). Same tempo
    // as every other reveal; motion teaches the glyph, not a verdict.
    if (st.draw === "no-ring" && hasDraw && lastBeat < n) {
      var ring = board.querySelectorAll('.c-row[data-iso3="USA"] .c-mark-N svg *');
      if (ring.length) {
        gsap.fromTo(ring, { drawSVG: "0%" },
          { drawSVG: "100%", duration: 0.7, ease: "none", stagger: 0.15 });
      }
    }
    board.style.height = (Math.max(st.order.length, 4) * h).toFixed(1) + "px";
    showSet("c-teach", st.set);
    showSet("c-statset", st.set);
    // The deadline draws by CSS clip reveal keyed off data-state, so the
    // stroke keeps its dashed identity (review R1: DrawSVG rewrites the
    // dash pattern to draw, settling the line solid).
    var dl = canvas.querySelector(".c-deadline");
    if (dl) dl.setAttribute("data-state", st.deadline || "off");
    lastBeat = n;
  }

  var scroller = window.scrollama();
  scroller.setup({ step: ".scrolly-steps .beat", offset: 0.55 })
    .onStepEnter(function (r) { setBeat(r.index + 1); });
  window.addEventListener("resize", function () { scroller.resize(); });

  // Initial state before reveal: everything off, then beat 1.
  rows.forEach(function (row) { row.classList.add("c-off"); });
  setBeat(1);

  // Positions depend on the serif loading; recalc offsets once it settles.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () { scroller.resize(); });
  }
})();
"""


INSTRUMENTS_JS = """// Instruments page enhancements. The server-rendered lists and tables ARE
// the content; the quadrant scrub and the wave map only add sequence.
// Endorsement renders in the instrument's own hue; not-yet-endorsed renders
// as paper, never as an opposing color. No motion here encodes valence, and
// every update is an instant state change (reduced-motion safe by design).
(function () {
  "use strict";

  // ---- Quadrant time scrub ----
  var qNode = document.getElementById("quadrant-data");
  var qSvg = document.getElementById("quadrant-svg");
  var qRange = document.getElementById("quadrant-time");
  var qOut = document.getElementById("quadrant-step");
  if (qNode && qSvg && qRange && qOut) {
    var q = JSON.parse(qNode.textContent);
    var dots = {};
    qSvg.querySelectorAll("[data-iso3]").forEach(function (d) {
      dots[d.getAttribute("data-iso3")] = d;
    });
    var applyStep = function (i) {
      var step = q.steps[i];
      qOut.textContent = step.date + " \\u00b7 " + step.label;
      q.states.forEach(function (st) {
        var dot = dots[st.iso3];
        if (!dot) return;
        var yes = st.yes.filter(function (d) { return d <= step.date; }).length;
        var endorsed = !!(st.endorsed && st.endorsed <= step.date);
        dot.setAttribute("cx", (q.layout.cols[yes] + st.jx).toFixed(1));
        dot.setAttribute(
          "cy",
          ((endorsed ? q.layout.rowEndorsed : q.layout.rowNot) + st.jy).toFixed(1)
        );
        var title = dot.querySelector("title");
        if (title) {
          title.textContent = st.name + " (" + st.iso3 + "): " + yes +
            " Yes vote" + (yes === 1 ? "" : "s") + "; " +
            (endorsed ? "endorsed" : "not listed") + ", as of " + step.date;
        }
      });
    };
    qRange.disabled = false;
    qRange.addEventListener("input", function () {
      applyStep(Number(qRange.value));
    });
    applyStep(Number(qRange.value));

    // ---- State search (primary nav, DESIGN v2 mobile contract) ----
    // A match rings the state's dot (ink stroke, radius bump, never a color
    // change), scrolls the chart to it when overflowed, and filters the
    // fallback table to that state. Clearing restores everything.
    var qSearch = document.getElementById("quadrant-search");
    var qTable = document.getElementById("quadrant-table");
    var qScroll = qSvg.parentElement;
    if (qSearch) {
      var lookup = {};
      q.states.forEach(function (st) {
        lookup[st.name.toLowerCase()] = st.iso3;
        lookup[st.iso3.toLowerCase()] = st.iso3;
        lookup[(st.name + " (" + st.iso3 + ")").toLowerCase()] = st.iso3;
      });
      var applySearch = function () {
        var hit = lookup[qSearch.value.trim().toLowerCase()] || null;
        Object.keys(dots).forEach(function (iso3) {
          var dot = dots[iso3];
          if (iso3 === hit) {
            dot.classList.add("q-hit");
            dot.setAttribute("r", "7");
          } else {
            dot.classList.remove("q-hit");
            dot.setAttribute("r", "5");
          }
        });
        if (hit && dots[hit]) {
          // Redraw the ringed dot above its neighbors.
          dots[hit].parentNode.appendChild(dots[hit]);
          if (qScroll && qScroll.scrollWidth > qScroll.clientWidth) {
            var vw = qSvg.viewBox.baseVal.width || 1;
            var x = (Number(dots[hit].getAttribute("cx")) / vw) * qScroll.scrollWidth;
            qScroll.scrollLeft = Math.max(0, x - qScroll.clientWidth / 2);
          }
        }
        if (qTable) {
          qTable.querySelectorAll("tr").forEach(function (row) {
            var link = row.querySelector('a[href^="state/"]');
            if (!link) return; // header row always stands
            row.hidden = !!hit &&
              link.getAttribute("href") !== "state/" + hit + ".html";
          });
        }
      };
      qSearch.disabled = false;
      qSearch.addEventListener("input", applySearch);
    }
  }

  // ---- Endorsement wave map ----
  var mNode = document.getElementById("map-data");
  var box = document.getElementById("wave-map");
  var fallback = document.getElementById("map-fallback");
  var mRange = document.getElementById("map-time");
  var mOut = document.getElementById("map-month");
  if (!mNode || !box || !mRange || !mOut) return;
  var m = JSON.parse(mNode.textContent);
  function hasWebgl() {
    try {
      var c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch (err) {
      return false;
    }
  }
  // Without MapLibre or WebGL the fallback text stands; the lists above
  // are the data either way. file:// cannot serve the local GeoJSON to
  // fetch(), so the fallback stands there too, without console noise.
  if (typeof window.maplibregl === "undefined" || !hasWebgl()) return;
  if (window.location.protocol === "file:") return;

  function currentInstrument() {
    var checked = document.querySelector('input[name="map-instrument"]:checked');
    if (!checked) return m.instruments[0];
    return m.instruments.filter(function (i) { return i.id === checked.value; })[0];
  }
  function paint(map) {
    var inst = currentInstrument();
    var month = m.months[Number(mRange.value)];
    mOut.textContent = month;
    var endorsed = inst.states
      .filter(function (s) { return s.date.slice(0, 7) <= month; })
      .map(function (s) { return s.iso3; });
    map.setPaintProperty("countries-fill", "fill-color", [
      "case",
      ["in", ["get", "iso3"], ["literal", endorsed]],
      inst.hue,
      m.paper
    ]);
  }
  fetch("assets/countries.geojson")
    .then(function (r) {
      if (!r.ok) throw new Error("geojson " + r.status);
      return r.json();
    })
    .then(function (geo) {
      box.classList.add("wave-map-live");
      var map = new maplibregl.Map({
        container: box,
        style: m.style,
        center: [10, 22],
        zoom: 0.9,
        minZoom: 0.4,
        maxZoom: 6,
        cooperativeGestures: true,
        attributionControl: { compact: false }
      });
      map.on("load", function () {
        map.addSource("countries", { type: "geojson", data: geo });
        map.addLayer({
          id: "countries-fill",
          type: "fill",
          source: "countries",
          paint: { "fill-color": m.paper, "fill-opacity": 0.75 }
        });
        map.addLayer({
          id: "countries-line",
          type: "line",
          source: "countries",
          paint: { "line-color": m.ink, "line-opacity": 0.25, "line-width": 0.5 }
        });
        // Only a fully loaded map replaces the fallback text.
        if (fallback) fallback.hidden = true;
        mRange.disabled = false;
        paint(map);
        mRange.addEventListener("input", function () { paint(map); });
        document.querySelectorAll('input[name="map-instrument"]').forEach(function (r) {
          r.addEventListener("change", function () { paint(map); });
        });
        map.resize();
      });
    })
    .catch(function () {
      box.classList.remove("wave-map-live");
      /* fallback stands */
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
    src_fonts = config.SITE_DIR / "assets" / "fonts"
    if src_fonts.exists() and src_fonts.resolve() != (out / "assets" / "fonts").resolve():
        shutil.copytree(src_fonts, out / "assets" / "fonts", dirs_exist_ok=True)
    (out / "js" / "board.js").write_text(BOARD_JS, encoding="utf-8", newline="\n")
    (out / "assets" / "favicon.svg").write_text(favicon_svg(), encoding="utf-8", newline="\n")
    (out / "assets" / "board-poster.svg").write_text(
        poster_svg(votes, content_states), encoding="utf-8", newline="\n"
    )

    tour = load_tour()
    if tour:
        manifest["entries"].append(
            {"state": None, "kind": "tour", "approved": is_approved(tour),
             "rendered": bool(preview or is_approved(tour))}
        )
        if preview or is_approved(tour):
            (out / "js" / "tour.js").write_text(TOUR_JS, encoding="utf-8", newline="\n")
    (out / "index.html").write_text(
        index_page(votes, content_states, preview, tour=tour),
        encoding="utf-8", newline="\n",
    )
    (out / "votes.html").write_text(
        votes_page(votes, content_states, preview), encoding="utf-8", newline="\n"
    )
    endorsements = load_endorsements()
    sponsorships = load_sponsorships()
    (out / "instruments.html").write_text(
        instruments_page(votes, content_states, endorsements, sponsorships,
                         preview, manifest),
        encoding="utf-8", newline="\n",
    )
    if any(preview or is_approved(i) for i in endorsements):
        (out / "js" / "instruments.js").write_text(
            INSTRUMENTS_JS, encoding="utf-8", newline="\n"
        )
        (out / "assets" / "countries.geojson").write_text(
            countries_geojson(), encoding="utf-8", newline="\n"
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

    (out / "404.html").write_text(
        page(
            "Not on the record",
            "<h1>Not on the record.</h1>\n"
            "<p>No page exists at this address. Nothing was removed; corrections "
            "and superseded material stay visible by policy.</p>\n"
            '<p><a href="/index.html">The trajectory board</a> lists every state.</p>',
            current="", preview=preview, absolute=True,
        ),
        encoding="utf-8", newline="\n",
    )

    for iso3, entry in votes["states"].items():
        cs = content_states.get(iso3, {})
        (out / "state" / f"{iso3}.html").write_text(
            state_page(iso3, entry, votes, cs, sources, preview, manifest,
                       eras=load_eras(iso3)),
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
