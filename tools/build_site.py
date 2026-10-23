"""Build the static site from the derived votes data and the content layer.

Two modes:
- deploy (default): writes site/ and HARD-EXCLUDES every content entry that
  is not approved: true. A manifest records what rendered; CI asserts zero
  unapproved entries in the deploy artifact.
- --preview: writes .scratch/preview/ (gitignored, localhost only) rendering
  unapproved entries behind an unmistakable DRAFT banner.

Every page is fully server-rendered: no content is gated on
JavaScript. Output is deterministic; rebuilding without input changes
produces byte-identical files.
"""

import argparse
import csv
import gzip
import hashlib
import html
import io
import json
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config
from tools import dossier_render
from tools import viz

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


def _warn_missing(path):
    """These files are expected. Absent them the build still succeeds and
    silently drops a whole layer (the tour, the instrument rosters), which
    reads as a clean build of a site that quietly lost its homepage
    narrative. Say so on stderr rather than degrade in silence."""
    print(f"WARNING: expected content file missing, layer will be empty: {path}",
          file=sys.stderr)


def load_endorsements():
    path = config.CONTENT_DIR / "endorsements.yaml"
    if not path.exists():
        _warn_missing(path)
        return []
    return load_yaml(path).get("instruments") or []


def load_sponsorships():
    path = config.CONTENT_DIR / "sponsorships.yaml"
    if not path.exists():
        _warn_missing(path)
        return []
    return load_yaml(path).get("records") or []


def load_conference():
    path = config.CONTENT_DIR / "conference.yaml"
    return load_yaml(path) if path.exists() else None


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


def doctrine_coverage_table(content_states, preview):
    """The national-policy coverage list as a table, derived from the state
    files rather than written out.

    A hand-written list of which states have doctrine is the staleness failure
    this repo keeps meeting: it reads as current and silently stops being so
    the moment a review lands. Generating it means the page cannot disagree
    with the records it describes.

    Gated doctrine is absent entirely rather than listed as pending, because
    its status is itself an unapproved claim.
    """
    rows = []
    for iso3, cs in sorted(content_states.items()):
        doctrine = cs.get("doctrine") or {}
        status = doctrine.get("status")
        if status not in ("policy_identified", "no_policy_identified"):
            continue
        if not (preview or is_approved(doctrine)):
            continue
        name = cs.get("display_name") or iso3
        if status == "policy_identified":
            titles = [e.get("title") for e in (doctrine.get("entries") or [])
                      if preview or is_approved(e)]
            detail = "; ".join(t for t in titles if t)
            finding = "Published policy"
        else:
            detail = (f"Reviewed {iso(doctrine['as_of'])}"
                      if doctrine.get("as_of") else "Reviewed")
            finding = "None identified"
        rows.append((iso3, name, finding, detail))

    if not rows:
        return ""
    body = "\n".join(
        f'<tr><th scope="row"><a href="state/{esc(iso3)}.html">{esc(name)}</a></th>'
        f"<td>{esc(finding)}</td><td>{esc(detail)}</td></tr>"
        for iso3, name, finding, detail in rows
    )
    return (
        '<div class="table-scroll">'
        '<table class="coverage-table">'
        "<caption>National-policy coverage: every state on the list, and what "
        "the review found.</caption>"
        '<thead><tr><th scope="col">State</th><th scope="col">Finding</th>'
        '<th scope="col">Record</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def prose_page(key, pages, fallback_lines, preview, manifest, blocks=None):
    """A prose page renders only when approved (invariant 1 covers analyst
    sentences); otherwise the factual shell stands in.

    `blocks` maps a {{marker}} in the markdown to generated HTML, so a page can
    carry a table the markdown subset cannot express without the prose having
    to restate data that lives in the content files.
    """
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
            body = f"<h1>{esc(title)}{chip}</h1>\n" + _render_with_blocks(
                entry["body"], blocks or {})
            return page(title, '<article class="prose-page">' + body + '</article>', current=f"{key}.html", preview=preview)
    return shell_page(title, f"{key}.html", fallback_lines, preview)


def _conference_entry_html(ev, preview):
    chip = ('<span class="draft-chip">DRAFT</span>'
            if preview and not is_approved(ev) else "")
    links = " · ".join(
        f'<a href="{esc(l["url"])}" rel="noopener">{esc(l["label"])}</a>'
        + (f' (<a href="{esc(l["archived"])}" rel="noopener">archived</a>)'
           if l.get("archived") else "")
        for l in ev.get("links") or []
    )
    who = ""
    if ev.get("state"):
        who = (f'<a class="cf-state" href="state/{esc(ev["state"])}.html">'
               f'{esc(ev.get("state_name") or ev["state"])}</a> ')
    return (
        f'<li class="cf-entry" id="{esc(ev["id"])}">'
        f'<p class="cf-date citation">{esc(iso(ev["date"]))}</p>'
        f'<h3>{who}{esc(ev["title"])}{chip}</h3>'
        f'{md_to_html(str(ev["text"]).strip())}'
        f'<p class="citation">Source: {links}</p>'
        "</li>"
    )


def conference_page(conference, content_states, votes, preview, manifest):
    """The Review Conference page: what the conference starts from, then one
    section per conference day. Entries are link-only facts (date, what
    happened, the official document), each approval-gated on its own; the
    page shell renders only when its own copy is approved. A day with no
    entries says that this site has added none, never that nothing
    happened."""
    approved_page = is_approved(conference)
    manifest["entries"].append({"state": None, "kind": "conference_page",
                                "approved": approved_page,
                                "rendered": bool(preview or approved_page)})
    events = []
    for ev in conference.get("events") or []:
        ok = is_approved(ev)
        manifest["entries"].append({"state": ev.get("state"),
                                    "kind": f"conference:{ev.get('id')}",
                                    "approved": ok, "rendered": bool(preview or ok)})
        if preview or ok:
            ev = dict(ev)
            if ev.get("state"):
                cs = content_states.get(ev["state"], {})
                un = votes["states"].get(ev["state"], {}).get("un_name", ev["state"])
                ev["state_name"] = cs.get("display_name") or display_from_un_name(un)
            events.append(ev)
    events.sort(key=lambda e: (iso(e["date"]), e["id"]))
    start, end = config.REVCON_DATES
    before = [e for e in events if iso(e["date"]) < start]
    chip = ('<span class="draft-chip">DRAFT</span>'
            if preview and not approved_page else "")
    sections = []
    if before:
        sections.append(
            f'<h2>{esc(conference.get("before_heading", "Before the conference"))}</h2>'
            '<ol class="cf-list">' + "".join(_conference_entry_html(e, preview) for e in before)
            + "</ol>")
    sections.append(f'<h2>{esc(conference.get("during_heading", "During the conference"))}</h2>')
    d0 = as_date(start)
    during = [e for e in events if start <= iso(e["date"]) <= end]
    if not during:
        first = f"{d0.day} {d0.strftime('%B')}"
        sections.append(f'<p class="cf-empty">Daily entries begin on {esc(first)}, '
                        "the first day of the conference.</p>")
    for i in range((as_date(end) - d0).days + 1 if during else 0):
        day = d0 + timedelta(days=i)
        todays = [e for e in events if iso(e["date"]) == day.isoformat()]
        label = f"{day.strftime('%A')} {day.day} {day.strftime('%B')}"
        body = ('<ol class="cf-list">' + "".join(_conference_entry_html(e, preview) for e in todays)
                + "</ol>") if todays else (
            '<p class="cf-empty">This site has not added entries for this day yet.</p>')
        sections.append(f'<section class="cf-day" id="day-{day.isoformat()}">'
                        f"<h3>{esc(label)}</h3>{body}</section>")
    body = (
        f'<h1>{esc(conference.get("title", "The Review Conference"))}{chip}</h1>\n'
        + md_to_html(str(conference.get("intro", "")).strip())
        + "\n".join(sections)
    )
    return page(conference.get("title", "The Review Conference"), '<article class="prose-page">' + body + '</article>',
                current="conference.html", preview=preview,
                description=conference.get("description", ""))


def _render_with_blocks(md, blocks):
    """Render markdown, substituting {{name}} markers with generated HTML.

    An unknown marker raises rather than rendering: a literal {{doctrine-
    coverage}} shipped to readers is the silent-failure shape this project has
    hit before, and it should stop the build instead of reaching a page.
    """
    parts = re.split(r"^\{\{([a-z0-9-]+)\}\}$", md, flags=re.M)
    out = [md_to_html(parts[0])] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        name, rest = parts[i], parts[i + 1]
        if name not in blocks:
            raise SystemExit(
                f"prose page references unknown block {{{{{name}}}}}; "
                f"known blocks: {sorted(blocks) or 'none'}")
        out.append(blocks[name])
        if rest.strip():
            out.append(md_to_html(rest))
    return "\n".join(out)


def is_approved(entry):
    return entry.get("approved") is True


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------

NAV = [
    ("index.html", "Home"),
    ("votes.html", "Votes"),
    ("instruments.html", "Instruments"),
    ("rubric.html", "Rubric"),
    ("methodology.html", "Methodology"),
    ("about.html", "About"),
    ("corrections.html", "Corrections"),
]

# The Review Conference page joins the nav only in a build where it renders
# (approved, or preview). build() sets this before any page is written, so no
# page ever links a conference page that the same build did not produce.
CONFERENCE_NAV = ("conference.html", "Conference")
_conference_live = False


def nav_items():
    if not _conference_live:
        return NAV
    return NAV[:1] + [CONFERENCE_NAV] + NAV[1:]


# ---------------------------------------------------------------------------
# Asset versioning.
#
# The stylesheets and scripts are served from stable paths, so a browser or CDN
# that has cached one will keep serving it after a deploy. That is not a
# theoretical risk: during the color-vision work a stale site.css made a
# working board render with transparent bands twice, and it looked exactly like
# a bug in the build. On a live site the same thing hands returning readers a
# page whose markup and stylesheet disagree.
#
# So every locally served asset is linked with a short content hash. Same bytes
# means same URL, which keeps the build deterministic and the CI freshness gate
# meaningful; changed bytes means a new URL, which no cache can answer from
# stale storage. Hashes are filled in during build() after the assets are
# written and before any page is rendered.
#
# Not covered: the font files, which are referenced from inside tokens.css by
# name. A stale font is the same font, so it costs nothing.
# ---------------------------------------------------------------------------

_ASSET_HASHES = {}


def _record_asset_hashes(out):
    """Hash every asset the pages link, keyed by its site-relative path."""
    _ASSET_HASHES.clear()
    out = Path(out)
    for rel in ("css/tokens.css", "css/site.css", "css/dossier.css",
                "js/board.js", "js/dossier.js", "js/viz.js", "js/film.js",
                "js/instruments.js", "assets/favicon.svg"):
        path = out / rel
        if path.exists():  # instruments.js is conditional
            # Hash the normalised text, not the raw bytes. Every generated
            # asset is written with newline="\n", but site.css is copied from
            # the source tree, so on Windows it carries CRLF while a CI
            # checkout has LF. Hashing bytes made the same stylesheet produce
            # two different URLs by platform and broke the freshness gate.
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            _ASSET_HASHES[rel] = digest[:10]
    # The film is binary, so its bytes are the same on every platform
    for path in sorted(p for p in (out / "assets" / "film").glob("*") if p.suffix in (".mp4", ".webm", ".png")):
        rel = path.relative_to(out).as_posix()
        _ASSET_HASHES[rel] = hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def asset(prefix, rel):
    """Link an asset at `rel` with its content hash, so a deploy invalidates
    any cached copy. Falls back to the bare path if the asset was not hashed,
    which keeps preview builds and tests working."""
    digest = _ASSET_HASHES.get(rel)
    return f"{prefix}{rel}?v={digest}" if digest else f"{prefix}{rel}"


def page(title, body, *, current, depth=0, preview=False, description="",
         absolute=False, extra_scripts="", extra_head="", og_path=None):
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
        for href, label in nav_items()
    )
    banner = (
        '<div class="draft-banner" role="status">DRAFT PREVIEW: unapproved '
        "working copy, not published, not citable</div>\n"
        if preview
        else ""
    )
    desc = description or ('Where every country stands on autonomous weapons: '
                           'recorded votes, official statements, and national '
                           'policy, tracked as they shift over time.')
    og_desc = description or ('Where every country stands on autonomous weapons, '
                              'tracked as positions shift over time.')
    # Absolute URL for canonical + og:url. State pages pass og_path explicitly
    # (their `current` is empty); others derive it from `current`.
    _path = og_path if og_path is not None else (current or "")
    canonical = f"https://{config.SITE_DOMAIN}/{_path}"
    og_title = f"{esc(title)} · {esc(config.SITE_NAME)}"
    og_image = f"https://{config.SITE_DOMAIN}/assets/og-card.png"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · {esc(config.SITE_NAME)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(config.SITE_NAME)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{esc(og_desc)}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{og_title}">
<meta name="twitter:description" content="{esc(og_desc)}">
<meta name="twitter:image" content="{og_image}">
<link rel="preload" href="{prefix}assets/fonts/newsreader-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{prefix}assets/fonts/newsreader-italic-var.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{asset(prefix, 'css/tokens.css')}">
<link rel="stylesheet" href="{asset(prefix, 'css/site.css')}">
<link rel="icon" href="{asset(prefix, 'assets/favicon.svg')}" type="image/svg+xml">
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
    <p>Vote data from the UN General Assembly voting dataset. © United Nations, 2026, <a href="https://digitallibrary.un.org">digitallibrary.un.org</a>. Reuse terms in <a href="https://github.com/wrobinson127/machine-politics">the repository</a>.</p>
    <p><span class="updated-through">Updated through {esc(config.UPDATED_THROUGH)}</span> · Every position links to a quoted, dated source · <a href="{prefix}corrections.html">Corrections</a></p>
    <p>Machine Politics is researched and written by <a href="https://walker-robinson.com">Walker Robinson</a>. <a href="{prefix}about.html">About</a></p>
    <p>Download the positions: <a href="{prefix}data/positions.csv">CSV</a>, <a href="{prefix}data/positions.json">JSON</a>. CC BY 4.0.</p>
  </div>
</footer>
<button class="to-top" type="button" aria-label="Back to top">&uarr;</button>
<script src="{asset(prefix, 'js/board.js')}" defer></script>
{extra_scripts}</body>
</html>
"""


# ---------------------------------------------------------------------------
# Board rendering
# ---------------------------------------------------------------------------

def pct(d):
    return f"{x_of(d, 100):.2f}%"


def band_style(code, confidence):
    """Fill styling for a coded band. Every substantive position carries both a
    hue and a texture, so the category survives color-vision deficiency (see
    config.POSITION_TEXTURES). AMBIG is texture only, over paper, because it
    has no hue. Confidence modulates opacity, hue never changes."""
    opacity = "1" if confidence == "EXPLICIT" else "0.55"
    texture = config.POSITION_TEXTURES.get(code, "")
    color = config.PALETTE["positions"][code]
    if color is None:
        return f"opacity:{opacity}", texture
    # The hue rides on a custom property rather than the background shorthand
    # so the texture class can set background-image without being clobbered:
    # an inline shorthand resets background-image to none and outranks the
    # stylesheet, which would silently drop every texture.
    return f"--fill:{color};opacity:{opacity}", texture


def vote_glyph_svg(vote, size=12):
    """Monochrome ink shapes; meaning never carried by hue. 12px in the
    table of member states."""
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


def coding_spans(codings):
    """Yield (coding, start, end) for each coding, as ISO dates or None for
    the track edges, in drawing order.

    A substantive coding starts on its as_of date and runs to the next one.
    NONE is different in kind: it is a coverage statement, never a position
    (config invariant 6), and its as_of is the date the record was reviewed,
    not a date a position began. A band starting on the review date would
    say "no position from July onward" when the finding is "no position
    anywhere in the record, as reviewed in July". So NONE starts at the
    origin and runs to the first substantive coding, or the end of the track
    if there is none, and its review date goes in the label instead.

    This is also what makes the axis end irrelevant to NONE: a review dated
    after UPDATED_THROUGH used to clamp to the track edge and vanish.
    """
    substantive = sorted((c for c in codings if c["code"] != "NONE"),
                         key=lambda c: iso(c["as_of"]))
    first = iso(substantive[0]["as_of"]) if substantive else None
    for coding in codings:
        if coding["code"] == "NONE":
            yield coding, None, first
    for i, coding in enumerate(substantive):
        nxt = iso(substantive[i + 1]["as_of"]) if i + 1 < len(substantive) else None
        yield coding, iso(coding["as_of"]), nxt


def compute_bands(codings):
    """Segment a coding timeline into bands in TRACK_W (0-1000) units."""
    bands = []
    for coding, start, end in coding_spans(codings):
        left = x_of(start) if start else 0.0
        right = x_of(end) if end else float(TRACK_W)
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


def legend_html():
    items = []
    for code, label in config.POSITION_CATEGORIES.items():
        # The legend swatch carries the same hue and the same texture as the
        # band, so the reader learns both channels from one place.
        style, texture = band_style(code, "EXPLICIT")
        swatch = (f'<span class="swatch{texture}" style="{style}" '
                  f'aria-hidden="true"></span>')
        plain = config.POSITION_PLAIN[code]
        desc = label[0].lower() + label[1:]
        items.append(f'<span>{swatch}{esc(plain)} <small class="code">({esc(code)})</small>: '
                     f"{esc(desc)}</span>")
    items.append(
        '<span><i class="swatch swatch-empty" aria-hidden="true"></i>'
        "Not yet reviewed: this site has not read this state's record yet</span>"
    )
    items.append(
        "<span>Vote marks: filled disc Yes, crossed ring No, half disc Abstain, dash Non-voting</span>"
    )
    return '<div class="board-legend">' + "\n".join(items) + "</div>"


def current_position(cs, preview):
    """The state's position today, for the opener's unit field: the latest
    substantive reading, else NONE if the record was reviewed and nothing
    found, else None (not yet reviewed). Same approval filter as the board."""
    codings = [c for c in cs.get("position_codings", []) if preview or is_approved(c)]
    substantive = sorted((c for c in codings if c["code"] != "NONE"),
                         key=lambda c: iso(c["as_of"]))
    if substantive:
        return substantive[-1]
    none = [c for c in codings if c["code"] == "NONE"]
    return max(none, key=lambda c: iso(c["as_of"])) if none else None


# ---------------------------------------------------------------------------
# Home page: the globe, Strands, and every state in a table
# ---------------------------------------------------------------------------

# The opener's sentences are taken from text the analyst has already approved
# for the live site: the site meta description, the footer, and the clock
# line. New claim-bearing prose does not belong in this file; it goes through
# content/ and the approval gate.
OPENER_HEADLINE = "Where every country stands on autonomous weapons."
OPENER_CLOCK = ("The Geneva weapons convention holds its Seventh Review Conference "
                "on 16 November 2026, and that is the next moment any of this can "
                "turn into law.")

D3_VERSION = "7.8.5"
D3_SRI = "sha512-M7nHCiNUOwFt6Us3r8alutZLm9qMt4s9951uo8jqO4UwJ1hziseL6O3ndFyigx6+LREfZqnhHxYjKRJ8ZQ69DQ=="
TOPOJSON_VERSION = "3.0.2"
TOPOJSON_SRI = "sha512-4UKI/XKm3xrvJ6pZS5oTRvIQGIzZFoXR71rRBb1y2N+PbwAsKa5tPl2J6WvbEvwN3TxQCm8hMzsl/pO+82iRlg=="

# Plain labels the figures use until the analyst approves content/viz.yaml.
# Counts and names only: chart furniture, the same standard the board's
# teaching sentences were held to.
VIZ_FALLBACK = {
    "world_heading": "", "strands_heading": "Votes and positions", "strands_intro": "",
    "states_heading": "Every state", "assembly_intro": "",
    "captions": {
        "globe": "Color: the position this site has read, {reviewed} states. Pale: not yet reviewed.",
        "map": "Color: the position this site has read, {reviewed} states. Small states are drawn as dots.",
        "vote": "{year}, resolution {res}: {Y} Yes, {N} No, {A} abstained, {X} did not vote.",
        "movers": "Highlighted: {movers} states that changed a recorded vote.",
        "position": "{stated} with a stated position, {none} reviewed with none found, {nr} not yet reviewed.",
        "matrix": "Rows: position. Columns: {vote2025} vote.",
        "strands": "{n} states. Left to right: the 2023, 2024 and 2025 votes, then position.",
        "strands_movers": "{n} states that changed a recorded vote.",
        "assembly": "One seat per member state, ordered by vote.",
        "assembly_moved": "{moved} changed their vote from the year before.",
        "assembly_position": "Seats colored by position.",
    },
}


def load_viz_copy(preview, manifest=None):
    path = config.CONTENT_DIR / "viz.yaml"
    copy = load_yaml(path) if path.exists() else None
    ok = bool(copy and (preview or is_approved(copy)))
    if manifest is not None and copy is not None:
        manifest["entries"].append({"state": None, "kind": "viz_copy",
                                    "approved": is_approved(copy), "rendered": ok})
    if not ok:
        return VIZ_FALLBACK
    out = {k: " ".join(str(copy.get(k) or "").split()) for k in VIZ_FALLBACK if k != "captions"}
    out["captions"] = {k: " ".join(str((copy.get("captions") or {}).get(k) or v).split())
                       for k, v in VIZ_FALLBACK["captions"].items()}
    return out


# Plain hero copy shown until the analyst approves content/landing.yaml: the
# conference as a bare date line. The opening film plays either way; without
# approved lines it has no end card, and its description says only what is
# on screen.
LANDING_FALLBACK = {
    "conference_line": "Seventh Review Conference, 16 to 20 November 2026",
    "film_question": "",
    "film_line": "",
    "film_cta": "",
    "film_description": "A short film with no sound: a drone flies to a person, its display unable to classify them.",
}
FILM_LINES = ("film_question", "film_line", "film_cta")


def load_landing_copy(preview, manifest=None):
    path = config.CONTENT_DIR / "landing.yaml"
    copy = load_yaml(path) if path.exists() else None
    ok = bool(copy and (preview or is_approved(copy)))
    if manifest is not None and copy is not None:
        manifest["entries"].append({"state": None, "kind": "landing_copy",
                                    "approved": is_approved(copy), "rendered": ok})
    if not ok:
        return dict(LANDING_FALLBACK)
    return {k: " ".join(str(copy.get(k) or v).split()) for k, v in LANDING_FALLBACK.items()}


def film_html(landing):
    """The opening film over the hero: hidden, and inert, until film.js plays
    it. The video is a grey master (rendered privately; the models never
    ship); film.js plays it as it is, the same in every browser."""
    lines = [landing[k] for k in FILM_LINES if landing[k]]
    card = "".join(f'<p class="film-l{i}">{esc(t)}</p>' for i, t in enumerate(lines))
    return f"""
  <div class="film" id="film" role="region" aria-label="Opening film" hidden
       data-src="{asset("", "assets/film/film-1080.mp4")}" data-src-small="{asset("", "assets/film/film-720.mp4")}"
       data-src-webm="{asset("", "assets/film/film-1080.webm")}" data-src-small-webm="{asset("", "assets/film/film-720.webm")}"
       data-poster="{asset("", "assets/film/poster.png")}">
    <p class="film-desc">{esc(landing["film_description"])}</p>
    <div class="film-stage" aria-hidden="true"></div>
    <div class="film-card" hidden>{card}</div>
    <div class="film-controls"><button type="button" class="film-pause">Pause</button><button type="button" class="film-skip">Skip</button></div>
  </div>"""


def hero_html(rows, landing, conf_link):
    """The first screen: the headline, two ways in, the conference on one
    line, and a large turning globe (drawn by viz.js; hidden until it is
    live, so the page reads the same without JavaScript). The key lives with
    the map below."""
    return f"""
<section class="opener hero" id="hero" aria-labelledby="opener-h">
  <canvas class="hero-globe" role="img" aria-label="A turning globe of the 193 UN member states, colored by the position each has stated on autonomous weapons. The figures and table below have every value." hidden></canvas>
  <div class="hero-text">
    <h1 id="opener-h">{esc(OPENER_HEADLINE)}</h1>
    <div class="hero-go">
      <a class="hero-cta" href="#viz-world">See the world map</a>
      <a class="hero-cta alt" href="#states">Find a country</a>
    </div>
    <p class="hero-conf">{esc(landing["conference_line"])}{conf_link}</p>
    <button type="button" class="film-replay" hidden><span class="film-replay-i" aria-hidden="true"></span>Replay the film <span class="film-replay-t">0:38</span></button>
  </div>{film_html(landing)}
</section>"""


def viz_scripts():
    return (
        f'<script defer src="https://cdnjs.cloudflare.com/ajax/libs/d3/{D3_VERSION}/d3.min.js" '
        f'integrity="{D3_SRI}" crossorigin="anonymous"></script>\n'
        f'<script defer src="https://cdnjs.cloudflare.com/ajax/libs/topojson/{TOPOJSON_VERSION}/topojson.min.js" '
        f'integrity="{TOPOJSON_SRI}" crossorigin="anonymous"></script>\n'
        f'<script defer src="{asset("", "js/viz.js")}"></script>'
    )


def film_script():
    return f'<script defer src="{asset("", "js/film.js")}"></script>'


def viz_textures_svg():
    """SVG patterns for the position textures, shared by every inline SVG on
    the page (the static map, the assembly, Strands). Hue paired with texture:
    no category depends on color alone."""
    pos = config.PALETTE["positions"]
    tex = "rgba(255,255,255,.45)"
    return (
        f'<pattern id="tx-open" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="{pos["LBI-OPEN"]}"/><rect y="4" width="6" height="1.4" fill="{tex}"/></pattern>'
        f'<pattern id="tx-soft" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="{pos["REG-SOFT"]}"/><rect x="5.5" width="1.4" height="7" fill="{tex}"/><rect y="5.5" width="7" height="1.4" fill="{tex}"/></pattern>'
        f'<pattern id="tx-ccw" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="6" height="6" fill="{pos["CCW-ONLY"]}"/><rect x="4.4" width="1.6" height="6" fill="{tex}"/></pattern>'
        f'<pattern id="tx-oppose" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="{pos["OPPOSE"]}"/><circle cx="3" cy="3" r="1.15" fill="{tex}"/></pattern>'
        f'<pattern id="tx-ambig" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="{config.PALETTE["ground"]}"/><rect x="4.4" width="1.6" height="6" fill="rgba(26,26,26,.55)"/></pattern>'
    )


def _swatch(code):
    if not code:
        return '<i class="swatch swatch-empty" aria-hidden="true"></i>'
    style, texture = band_style(code, "EXPLICIT")
    return f'<i class="swatch{texture}" style="{style}" aria-hidden="true"></i>'


def viz_payload(votes, content_states, preview, copy):
    rows = viz.payload(
        votes, content_states, preview, current_position,
        lambda iso3, entry, cs: cs.get("display_name") or display_from_un_name(entry["un_name"]),
        iso,
    )
    keys = list(config.LAWS_RESOLUTIONS)
    pack = {
        "rows": rows,
        "captions": copy["captions"],
        "plain": dict(config.POSITION_PLAIN),
        "conf": {"EXPLICIT": "stated directly", "INFERRED": "inferred",
                 "AMBIGUOUS": "the record points both ways", "PROVISIONAL": "provisional"},
        "years": [votes["resolutions"][k]["date"][:4] for k in keys],
        "resolutions": keys,
        "base": "",
        "view": [viz.VIEW_W, viz.VIEW_H],
        "flatScale": viz.FLAT_SCALE,
        "swatch": {k: _swatch(k) for k in [*config.POSITION_CATEGORIES, ""]},
    }
    # </script> cannot appear inside the JSON: escape the slash.
    data = json.dumps(pack, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    return rows, f'<script type="application/json" id="viz-data">{data}</script>'


def _vote_cell(v):
    return (f'<td class="vt" data-v="{v}">{vote_glyph_svg(v)}'
            f'<span>{esc(VOTE_GLYPHS[v])}</span></td>')


def states_table_html(rows, coverage_line, copy):
    order = {c: i for i, c in enumerate([*config.POSITION_CATEGORIES, ""])}
    body = []
    for r in sorted(rows, key=lambda r: r["n"]):
        pos = (f'{_swatch(r["p"])}{esc(config.POSITION_PLAIN[r["p"]])}' if r["p"]
               else f'{_swatch("")}<span class="muted">Not yet reviewed</span>')
        since = (f"reviewed {esc(r['s'])}" if r["p"] == "NONE"
                 else esc(r["s"]) if r["p"] else "")
        body.append(
            f'<tr data-name="{esc(r["n"])}" data-v2025="{"YANX".index(r["v"][2])}" '
            f'data-pos="{order[r["p"]]:02d}">'
            f'<th scope="row"><a href="state/{r["i"]}.html">{esc(r["n"])}</a></th>'
            + "".join(_vote_cell(v) for v in r["v"])
            + f'<td class="pos">{pos}</td><td class="since">{since}</td></tr>'
        )
    years = [k for k in config.LAWS_RESOLUTIONS]
    res = load_votes()["resolutions"]
    head = [f'{res[k]["date"][:4]}<span class="th-sub">{esc(k)}</span>' for k in years]
    return f"""
<section class="states" id="states" aria-labelledby="states-h">
  <h2 id="states-h">{esc(copy["states_heading"])}</h2>
  <p class="viz-intro">{esc(coverage_line)}</p>
  <div class="states-tools">
    <label for="states-find">Find a state</label>
    <input class="states-find" id="states-find" type="search" autocomplete="off" placeholder="India">
    <span class="states-status" aria-live="polite"></span>
  </div>
  <div class="board-key states-key">{legend_html()}</div>
  <div class="table-scroll">
  <table class="states-table">
    <thead><tr>
      <th scope="col"><button type="button" data-sort="name">State</button></th>
      <th scope="col">{head[0]}</th><th scope="col">{head[1]}</th>
      <th scope="col"><button type="button" data-sort="v2025">{head[2]}</button></th>
      <th scope="col"><button type="button" data-sort="pos">Position</button></th>
      <th scope="col">As of</th>
    </tr></thead>
    <tbody>
{chr(10).join(body)}
    </tbody>
  </table>
  </div>
</section>"""


def _res_label(key):
    """A resolution button reads as its year and symbol: "2025 · 80/57"."""
    return f"{load_votes()['resolutions'][key]['date'][:4]} · {key}"


def world_figure_html(rows, copy):
    reviewed = sum(1 for r in rows if r["p"])
    first = copy["captions"]["map"].replace("{reviewed}", str(reviewed))
    views = [("globe", "Globe"), ("map", "Flat map"), ("vote", "The vote"),
             ("position", "Positions"), ("matrix", "Vote against position")]
    keys = list(config.LAWS_RESOLUTIONS)
    years = [k for k in keys]
    head = f'<h2 class="viz-h">{esc(copy["world_heading"])}</h2>' if copy["world_heading"] else ""
    return f"""
<figure class="viz" id="viz-world" data-start="map" aria-labelledby="viz-world-cap">
  {head}
  <div class="viz-controls">
    <div class="seg" role="group" aria-label="View">
      {"".join(f'<button type="button" data-view="{k}" aria-pressed="{str(k == "map").lower()}">{esc(label)}</button>' for k, label in views)}
    </div>
    <label class="find">Find <input class="viz-find" type="search" autocomplete="off" placeholder="India"></label>
  </div>
  <div class="viz-controls viz-yearbar" hidden>
    <div class="seg" role="group" aria-label="Resolution">
      {"".join(f'<button type="button" data-year="{i}" aria-pressed="{str(i == 2).lower()}">{esc(_res_label(k))}</button>' for i, k in enumerate(years))}
    </div>
    <label><input class="viz-movers" type="checkbox"> Only the states that changed a vote</label>
  </div>
  <p class="viz-caption" id="viz-world-cap" aria-live="polite">{esc(first)}</p>
  <div class="viz-key">{"".join(f"<span>{_swatch(k)}{esc(config.POSITION_PLAIN[k] if k else 'Not yet reviewed')}</span>" for k in [*config.POSITION_CATEGORIES, ""])}</div>
  <div class="viz-stage">{viz.static_map_svg(rows)}</div>
  <figcaption class="info">
    <button type="button" class="info-btn" aria-describedby="map-sources"><span class="info-i" aria-hidden="true">i</span>Map sources</button>
    <span class="info-tip" role="tooltip" id="map-sources">Shapes: Natural Earth via world-atlas (public domain). Equal Earth projection when flat. States under about 20,000 km² are drawn as dots at their Natural Earth label point. The table below lists every state.</span>
  </figcaption>
</figure>"""


def strands_figure_html(copy):
    intro = f'<p class="viz-intro">{esc(copy["strands_intro"])}</p>' if copy["strands_intro"] else ""
    return f"""
<section class="viz-section" aria-labelledby="strands-h">
  <h2 id="strands-h">{esc(copy["strands_heading"])}</h2>
  {intro}
  <figure class="viz" id="viz-strands">
    <div class="viz-controls">
      <label><input class="viz-movers" type="checkbox"> Only the states that changed a vote</label>
      <label><input class="viz-reviewed" type="checkbox"> Only the reviewed states</label>
      <label class="find">Find <input class="viz-find" type="search" autocomplete="off" placeholder="United States"></label>
    </div>
    <p class="viz-caption" aria-live="polite"></p>
    <div class="viz-stage"></div>
    <noscript><p class="citation">This figure needs JavaScript. The table below has the same votes and positions.</p></noscript>
  </figure>
</section>"""


def index_page(votes, content_states, preview, manifest=None):
    copy = load_viz_copy(preview, manifest)
    rows, data_tag = viz_payload(votes, content_states, preview, copy)
    n_reviewed = sum(1 for r in rows if r["p"])
    coverage_line = (f"Votes cover all {len(rows)} member states. "
                     f"Positions have been reviewed for {n_reviewed} states so far.")
    conf_link = (' <span aria-hidden="true">&middot;</span> <a href="conference.html">Follow the conference</a>'
                 if _conference_live else "")
    landing = load_landing_copy(preview, manifest)
    body = f"""
<svg class="viz-defs" width="0" height="0" aria-hidden="true"><defs>{viz_textures_svg()}</defs></svg>
{hero_html(rows, landing, conf_link)}
{world_figure_html(rows, copy)}
{strands_figure_html(copy)}
{states_table_html(rows, coverage_line, copy)}
{data_tag}
"""
    return page(
        "Where every country stands",
        body,
        current="index.html",
        preview=preview,
        extra_scripts=viz_scripts() + "\n" + film_script(),
        extra_head=dataset_jsonld(),
        og_path="",
        description="Where every country stands on autonomous weapons, tracked as positions shift over time.",
    )


def assembly_figure_html(copy):
    keys = list(config.LAWS_RESOLUTIONS)
    intro = f'<p class="viz-intro">{esc(copy["assembly_intro"])}</p>' if copy["assembly_intro"] else ""
    return f"""
<svg class="viz-defs" width="0" height="0" aria-hidden="true"><defs>{viz_textures_svg()}</defs></svg>
{intro}
<figure class="viz" id="viz-assembly">
  <div class="viz-controls">
    <div class="seg" role="group" aria-label="Resolution">
      {"".join(f'<button type="button" data-year="{i}" aria-pressed="{str(i == 2).lower()}">{esc(_res_label(k))}</button>' for i, k in enumerate(keys))}
    </div>
    <div class="seg" role="group" aria-label="Color">
      <button type="button" data-colour="vote" aria-pressed="true">Color by vote</button>
      <button type="button" data-colour="position" aria-pressed="false">Color by position</button>
    </div>
    <label class="find">Find <input class="viz-find" type="search" autocomplete="off" placeholder="Russia"></label>
  </div>
  <p class="viz-caption" aria-live="polite"></p>
  <div class="viz-key"></div>
  <div class="viz-stage"></div>
  <noscript><p class="citation">The seating chart needs JavaScript. The rosters below list every state's vote.</p></noscript>
</figure>"""

# ---------------------------------------------------------------------------
# Votes page
# ---------------------------------------------------------------------------

def votes_page(votes, content_states, preview):
    copy = load_viz_copy(preview)
    _, data_tag = viz_payload(votes, content_states, preview, copy)
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
  <p class="citation">Adopted {esc(res["date"])}, {tally["yes"]} in favor, {tally["no"]} against, {tally["abstain"]} abstentions ·
  <a href="{esc(res["undl_link"])}">UN Digital Library record</a></p>
  {tally_bar}
  <table class="vote-table">
{chr(10).join(rows)}
  </table>
</section>
""")
    body = f"""
<h1>Recorded votes</h1>
<p>The three UN General Assembly resolutions on lethal autonomous weapons, with
every member state's vote. Taken from the official UN voting dataset. The
extraction and the checks are in the open repository.</p>
{assembly_figure_html(copy)}
{chr(10).join(sections)}
{data_tag}
"""
    return page("Votes", body, current="votes.html", preview=preview,
                extra_scripts=viz_scripts())


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
  <p>This site has not yet reviewed this state's statements, as of
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
  <p>Military policy not yet reviewed by this site, as of {esc(config.UPDATED_THROUGH)}.</p>
</div>
"""
    status = doctrine.get("status")
    chip = draft_chip(preview, doctrine)
    if status == "no_policy_identified":
        phrase = config.DOCTRINE_ABSENCE_PHRASE.format(as_of=iso(doctrine["as_of"]))
        return f"""
<div class="coverage-card">
  <p>{esc(phrase.capitalize())}.{chip}</p>
  <p class="citation">{esc(doctrine.get("search_note", ""))}</p>
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
  <p>Military policy not yet reviewed by this site, as of {esc(config.UPDATED_THROUGH)}.{chip}</p>
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
        kind_label = "core policy" if r["kind"] == "core" else "context"
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
        '<p class="era-legend citation">Government eras, for context only: '
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
            "core policy, filled marker" if r["kind"] == "core"
            else "context, outlined marker"
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


def state_page(iso3, entry, votes, cs, sources, preview, manifest, eras=None,
               endorsements=None, sponsorships=None, coded=None):
    """The country dossier: the signature artifact (DESIGN v3). Five arena
    bands plus the corpus, server-rendered from the content YAML behind the
    approval gate; tools/dossier_render.py holds the render, this wires the
    data and the manifest accounting."""
    endorsements = endorsements or []
    sponsorships = sponsorships or []
    if coded is None:
        coded = dossier_render.coded_states({iso3: cs}, votes, preview)
    name = cs.get("display_name") or display_from_un_name(entry["un_name"])
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
    body = dossier_render.state_body(
        iso3, name, entry["un_name"], entry, votes, cs, sources,
        endorsements, sponsorships, coded, preview, config.UPDATED_THROUGH,
        doctrine_timeline=doctrine_timeline_html(name, cs, eras, preview),
    )
    return page(
        name, body, current="", depth=1, preview=preview,
        og_path=f"state/{iso3}.html",
        description=f"{name}: recorded votes, position, framework signings, engagement record, and national policy on autonomous weapons systems.",
        extra_head=f'<link rel="stylesheet" href="{asset("../", "css/dossier.css")}">',
        extra_scripts=f'<script src="{asset("../", "js/dossier.js")}" defer></script>',
    )


# ---------------------------------------------------------------------------
# Instruments page: endorsement + sponsorship record, quadrant view, wave map
# ---------------------------------------------------------------------------

# MapLibre GL JS: pinned version with SRI hashes from cdnjs, loaded deferred
# and ONLY on the instruments page when endorsement instruments render. The
# server-rendered lists and tables ARE the content; the map is enhancement.
MAPLIBRE_VERSION = "5.12.0"
MAPLIBRE_JS_SRI = (
    "sha512-0BWq+SR7EMt0191JMIlQk0jZxAQmrTvGFA4xzd/NukRhDKZvqfF7sxIq5m5tecR4OMaXRb+Ry52hmng5gTBaVQ=="
)
MAPLIBRE_CSS_SRI = (
    "sha512-A+upg1UEqFAoCJJ4P5OFl2JXKybtcKh4qyhvPxTcusRMWf55btrRVY/1pOTE83R/oXzrRzwh1FakAtXfta62rg=="
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
        f'<p class="citation">Date {esc(iso(inst["date"]))}{(" (" + esc(inst["date_note"]) + ")") if inst.get("date_note") else ""} · {links} · '
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
<p>Each dot is a member state. Left to right: how many of the three UN
resolutions on autonomous weapons the state voted Yes on. Bottom to top:
whether the state signed the US Political Declaration on Responsible Military
Use of AI and Autonomy. The two axes are the two documents. The four regions
have no names on purpose.</p>
{search}
<div class="scrub-control">
  <label for="quadrant-time">Timeline</label>
  <input type="range" id="quadrant-time" min="0" max="{len(steps) - 1}" step="1"
    value="{len(steps) - 1}" disabled>
  <output id="quadrant-step" for="quadrant-time">{esc(last["date"])} · {esc(last["label"])}</output>
</div>
<p class="citation">Type a state's name to ring its dot and filter the table
below. Drag the timeline to step through the three vote dates and the four
signing dates. Both need JavaScript. Without it, the chart shows the record
as of {esc(config.UPDATED_THROUGH)} and the table lists every state.</p>
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
<h2>Signing map</h2>
<p>One document at a time. States that had signed it by the month shown fill
in with that document's color. States not yet on the list stay blank. The
lists above are the record; the map only shows the wave.</p>
<fieldset class="map-controls">
  <legend>Document</legend>
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
            f'<script defer src="{asset("", "js/instruments.js")}"></script>'
        )
    body = f"""
<h1>Instruments</h1>
<p>Who has signed what. This page lists every pledge, declaration, resolution,
and joint paper this site tracks, with the states on each one, taken from the
official list. Being on a list is a fact. Not being on a list is not
opposition, and this site never treats it as such. Signing something never
decides a state's position on its own.</p>
{chr(10).join(sections)}
"""
    return page(
        "Instruments", body, current="instruments.html", preview=preview,
        extra_head=extra_head, extra_scripts=extra_scripts,
        description="Endorsement and sponsorship records for the political-commitment instruments on military AI and autonomy.",
    )



def world_topology():
    """world-atlas 1:110m with each country's ISO alpha-3 in its properties,
    so the globe can match shapes to states without a lookup at runtime."""
    topo = json.loads(COUNTRIES_TOPOJSON.read_text(encoding="utf-8"))
    table = json.loads(ISO_NUMERIC_TABLE.read_text(encoding="utf-8"))
    for g in topo["objects"]["countries"]["geometries"]:
        g["properties"] = {"i": table.get(str(g.get("id")), "")}
    return json.dumps(topo, separators=(",", ":"), sort_keys=True)

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

def rubric_page(rubric, preview, states=None):
    if not (preview or is_approved(rubric)):
        body = f"""
<h1>The rubric</h1>
<div class="coverage-card">
  <p>The published rubric appears here once the analyst of record approves
  it. Positions are coded on two axes: instrument preference and confidence.
  As of {esc(config.UPDATED_THROUGH)}, codings are in analyst review.</p>
</div>
"""
        return page("Rubric", '<article class="prose-page">' + body + '</article>', current="rubric.html", preview=preview)
    cats = []
    for code, cat in (rubric.get("axis_a", {}).get("categories") or {}).items():
        cats.append(
            f"<h3>{esc(cat.get('label', ''))} <span class=\"citation\">({esc(code)})</span></h3>"
            f"<p>{esc(cat.get('description', ''))}</p>"
        )
    tiers = [
        f"<h3>{esc(tier)}</h3><p>{esc(text)}</p>"
        for tier, text in (rubric.get("axis_b", {}).get("tiers") or {}).items()
    ]
    # The authorship rule decides how a whole bloc of states is coded, and
    # the confidence tiers cross-reference it by name, so it has to render or
    # the tier text points at nothing. Fields are emitted in a fixed order
    # and only when present, so the rubric stays the single source.
    auth = rubric.get("instrument_authorship") or {}
    auth_html = ""
    if auth:
        parts = [
            f'<h2>{esc(auth.get("name", "Co-writing a draft treaty"))}</h2>'
        ]
        # Every prose field in the block renders, in file order. An allowlist
        # of key names was silently dropping fields added to the rubric later,
        # which is how a load-bearing clause reached the YAML but never the
        # page. The rubric file is the source; the renderer does not curate it.
        for key, value in auth.items():
            if key == "name" or not isinstance(value, str):
                continue
            parts.append(f"<p>{esc(value)}</p>")
        auth_html = (
            '<section class="signal" id="instrument-authorship">'
            + chr(10).join(parts)
            + "</section>"
        )

    # Worked examples are the "re-derive it yourself" promise made concrete,
    # so each one links to the state page carrying the evidence.
    examples = []
    for ex in rubric.get("worked_examples") or []:
        iso3 = str(ex.get("state", ""))
        name = (states or {}).get(iso3, {}).get("display_name") or iso3
        head = (f'<a href="state/{esc(iso3)}.html">{esc(name)}</a>'
                if iso3 else "")
        examples.append(f"<h3>{head}</h3><p>{esc(ex.get('why', ''))}</p>")
    examples_html = ""
    if examples:
        examples_html = (
            '<section class="signal"><h2>Worked examples</h2><p>Each of these is a reading you can check yourself. Follow the link and read the documents it rests on.</p>'
            "<p>Each of these is a coding you can check against its own "
            "evidence. Follow the link and read the documents the coding "
            "rests on.</p>" + chr(10).join(examples) + "</section>"
        )

    chip = '<span class="draft-chip">DRAFT</span>' if preview and not is_approved(rubric) else ""
    body = f"""
<h1>The rubric{chip}</h1>
<section class="signal"><h2>How positions are classified</h2>
<p>{esc((rubric.get("axis_a") or {}).get("rules", ""))}</p></section>
<section class="signal"><h2>Axis A: what does the state want?</h2>
{chr(10).join(cats)}</section>
<section class="signal"><h2>Axis B: how sure are we?</h2>
<p>{esc((rubric.get("axis_b") or {}).get("rules", ""))}</p>
{chr(10).join(tiers)}</section>
{auth_html}
{examples_html}
"""
    return page("Rubric", '<article class="prose-page">' + body + '</article>', current="rubric.html", preview=preview)


def shell_page(title, current, lines, preview):
    body = f"<h1>{esc(title)}</h1>\n" + "\n".join(f"<p>{line}</p>" for line in lines)
    return page(title, '<article class="prose-page">' + body + '</article>', current=current, preview=preview)


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


BOARD_JS = """// Progressive enhancement only: every page is complete without JavaScript.
(function () {
  "use strict";
  // The masthead is sticky; anchored content offsets by its real
  // height, which wraps on narrow screens, so measure rather than assume.
  function mastheadHeight() {
    var m = document.querySelector("header.masthead");
    // Below 720px the masthead is not sticky (see site.css), so nothing
    // needs to offset by it.
    var narrow = window.matchMedia("(max-width: 720px)").matches;
    if (m) document.documentElement.style.setProperty("--masthead-h", narrow ? "0px" : m.offsetHeight + "px");
  }
  mastheadHeight();
  window.addEventListener("resize", mastheadHeight);
  // Back to top, phones only (CSS hides it on wider screens): appears once
  // the reader is well into the page, scrolls smoothly unless motion is
  // reduced.
  var toTop = document.querySelector(".to-top");
  if (toTop) {
    var onScroll = function () { toTop.classList.toggle("is-on", window.scrollY > 600); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    toTop.addEventListener("click", function () {
      var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
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
    global _conference_live
    conference = load_conference()
    _conference_live = bool(conference and (preview or is_approved(conference)))

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
    (out / "css" / "dossier.css").write_text(dossier_render.dossier_css(), encoding="utf-8", newline="\n")
    (out / "js" / "dossier.js").write_text(dossier_render.dossier_js(), encoding="utf-8", newline="\n")
    (out / "assets" / "favicon.svg").write_text(favicon_svg(), encoding="utf-8", newline="\n")

    # The figures: viz.js is a source file (like site.css), the topology is
    # world-atlas 1:110m with each shape tagged by ISO alpha-3.
    src_viz = config.SITE_DIR / "js" / "viz.js"
    if src_viz.resolve() != (out / "js" / "viz.js").resolve():
        shutil.copyfile(src_viz, out / "js" / "viz.js")
    # The opening film: film.js and the videos are source files too. The videos
    # are rendered in the private dev repo (docs/finish/cinematic); only the
    # finished grey masters ship, never the models they were rendered from.
    src_film = config.SITE_DIR / "js" / "film.js"
    if src_film.resolve() != (out / "js" / "film.js").resolve():
        shutil.copyfile(src_film, out / "js" / "film.js")
    src_media = config.SITE_DIR / "assets" / "film"
    if src_media.exists() and src_media.resolve() != (out / "assets" / "film").resolve():
        shutil.copytree(src_media, out / "assets" / "film", dirs_exist_ok=True)
    (out / "assets" / "world.json").write_text(world_topology(), encoding="utf-8", newline="\n")
    endorsements = load_endorsements()
    sponsorships = load_sponsorships()
    if any(preview or is_approved(i) for i in endorsements):
        (out / "js" / "instruments.js").write_text(
            INSTRUMENTS_JS, encoding="utf-8", newline="\n"
        )
        (out / "assets" / "countries.geojson").write_text(
            countries_geojson(), encoding="utf-8", newline="\n"
        )

    # Every asset a page can link now exists on disk. Hash them before
    # rendering any page, so the links carry the version of the bytes actually
    # shipped. Conditional assets are written above for this reason: a page
    # rendered before its script exists would link an unversioned path.
    _record_asset_hashes(out)

    (out / "index.html").write_text(
        index_page(votes, content_states, preview, manifest),
        encoding="utf-8", newline="\n",
    )
    (out / "votes.html").write_text(
        votes_page(votes, content_states, preview), encoding="utf-8", newline="\n"
    )
    conf_path = out / "conference.html"
    if _conference_live:
        conf_path.write_text(
            conference_page(conference, content_states, votes, preview, manifest),
            encoding="utf-8", newline="\n")
    else:
        if conference:
            # Still recorded in the manifest, so the gate is auditable.
            conference_page(conference, content_states, votes, preview, manifest)
        if conf_path.exists():
            conf_path.unlink()
    (out / "instruments.html").write_text(
        instruments_page(votes, content_states, endorsements, sponsorships,
                         preview, manifest),
        encoding="utf-8", newline="\n",
    )
    (out / "rubric.html").write_text(
        rubric_page(rubric, preview, content_states), encoding="utf-8", newline="\n")
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
            blocks={"doctrine-coverage":
                    doctrine_coverage_table(content_states, preview)},
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
            '<p><a href="/index.html#states">The table of member states</a> lists every state.</p>',
            current="", preview=preview, absolute=True,
        ),
        encoding="utf-8", newline="\n",
    )

    endorsements = load_endorsements()
    sponsorships = load_sponsorships()
    coded = dossier_render.coded_states(content_states, votes, preview)
    for iso3, entry in votes["states"].items():
        cs = content_states.get(iso3, {})
        (out / "state" / f"{iso3}.html").write_text(
            state_page(iso3, entry, votes, cs, sources, preview, manifest,
                       eras=load_eras(iso3), endorsements=endorsements,
                       sponsorships=sponsorships, coded=coded),
            encoding="utf-8", newline="\n",
        )

    write_discovery_files(out, votes, content_states, preview)

    manifest["unapproved_rendered"] = sum(
        1 for e in manifest["entries"] if e["rendered"] and not e["approved"]
    )
    manifest["codings_past_axis"] = report_codings_past_axis(content_states)
    (out / "build_manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8", newline="\n"
    )
    assert_deploy_clean(manifest, preview)
    return manifest


def report_codings_past_axis(content_states):
    """A coding dated after UPDATED_THROUGH clamps to the end of the track, so
    its band computes zero width and compute_bands drops it. The coding is
    real, its approval flag means something, and the board shows nothing: the
    silent-absence failure mode this repo has shipped before.

    This warns rather than refuses, because the fix is an editorial call
    between moving the axis and re-dating the coding, and every case today is
    still gated. The manifest count makes it checkable rather than a message
    someone has to notice scrolling past."""
    past = []
    for iso3, cs in sorted(content_states.items()):
        for coding in cs.get("position_codings") or []:
            if coding["code"] == "NONE":
                # NONE spans the record from the origin (coding_spans); its
                # as_of is a review date and never places the band.
                continue
            if as_date(coding["as_of"]) > T1:
                past.append({"iso3": iso3, "code": coding["code"],
                             "as_of": iso(coding["as_of"]),
                             "approved": bool(coding.get("approved"))})
    if past:
        listed = ", ".join(f"{p['iso3']} {p['code']} {p['as_of']}" for p in past)
        print(
            f"warning: {len(past)} coding(s) dated after UPDATED_THROUGH "
            f"({config.UPDATED_THROUGH}) render no band at all: {listed}. "
            "Either move the axis or re-date the coding.",
            file=sys.stderr,
        )
    return past


SITE_URL = f"https://{config.SITE_DOMAIN}/"
STATIC_PAGES = ["", "votes.html", "instruments.html", "rubric.html",
                "methodology.html", "about.html", "corrections.html"]


def dataset_jsonld():
    """schema.org Dataset for the home page, so search engines and agents can
    cite the record. The text reuses the approved site description."""
    data = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": config.SITE_NAME,
        "description": ("Where every country stands on autonomous weapons: recorded "
                        "votes, official statements, and national policy, tracked "
                        "as they shift over time."),
        "url": SITE_URL,
        "creator": {"@type": "Person", "name": "Walker Robinson",
                    "url": "https://walker-robinson.com"},
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isAccessibleForFree": True,
        "spatialCoverage": "UN member states",
        "dateModified": config.UPDATED_THROUGH,
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "text/csv",
             "contentUrl": SITE_URL + "data/positions.csv"},
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": SITE_URL + "data/positions.json"},
        ],
    }
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False, sort_keys=True) + "</script>")


def position_rows(votes, content_states, preview):
    """Every position reading that renders, one row per reading, oldest first
    per state. Votes are left out: they are UN data under the UN's own terms,
    and the repository's data/ directory carries them."""
    rows = []
    for iso3 in sorted(votes["states"]):
        cs = content_states.get(iso3, {})
        name = cs.get("display_name") or display_from_un_name(votes["states"][iso3]["un_name"])
        codings = sorted((c for c in cs.get("position_codings", [])
                          if preview or is_approved(c)), key=lambda c: iso(c["as_of"]))
        current = current_position(cs, preview)
        for c in codings:
            rows.append({
                "iso3": iso3,
                "state": name,
                "code": c["code"],
                "position": config.POSITION_PLAIN[c["code"]],
                "confidence": c.get("confidence") or "",
                "as_of": iso(c["as_of"]),
                "current": c is current,
                "page": f"{SITE_URL}state/{iso3}.html",
                "sources": " ".join(dict.fromkeys(
                    e["url"] for e in c.get("evidence") or [] if e.get("url"))),
            })
    return rows


def write_discovery_files(out, votes, content_states, preview):
    """sitemap.xml, robots.txt, the IndexNow key, llms.txt and the CC BY position download.
    Deterministic, with no build timestamps, so the freshness gate holds."""
    out = Path(out)
    pages = list(STATIC_PAGES)
    if (out / "conference.html").exists():
        pages.insert(1, "conference.html")
    pages += [f"state/{iso3}.html" for iso3 in sorted(votes["states"])]
    urls = "".join(
        f"  <url><loc>{SITE_URL}{p}</loc><lastmod>{config.UPDATED_THROUGH}</lastmod></url>\n"
        for p in pages)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + urls + "</urlset>\n", encoding="utf-8", newline="\n")
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n",
        encoding="utf-8", newline="\n")
    # IndexNow key file: lets Bing and other IndexNow engines verify that
    # submissions for this host come from its owner.
    (out / f"{config.INDEXNOW_KEY}.txt").write_text(config.INDEXNOW_KEY, encoding="utf-8", newline="\n")

    rows = position_rows(votes, content_states, preview)
    (out / "data").mkdir(exist_ok=True)
    cols = ["iso3", "state", "code", "position", "confidence", "as_of", "current",
            "page", "sources"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({**r, "current": "yes" if r["current"] else "no"})
    (out / "data" / "positions.csv").write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    payload = {
        "name": f"{config.SITE_NAME}: position readings",
        "license": "CC BY 4.0, https://creativecommons.org/licenses/by/4.0/",
        "credit": f"{config.SITE_NAME}, Walker Robinson, {SITE_URL}",
        "updated_through": config.UPDATED_THROUGH,
        "note": ("Positions as read by this site from each state's own words. "
                 "A state with no row has not been reviewed yet. Vote data is "
                 "not included; it is UN data under the UN's terms."),
        "codes": config.POSITION_CATEGORIES,
        "rows": rows,
    }
    (out / "data" / "positions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")

    listing = "\n".join(f"- [{label}]({SITE_URL}{href})" for href, label in nav_items()
                        if href != "index.html")
    (out / "llms.txt").write_text(
        f"# {config.SITE_NAME}\n\n"
        "> Where every country stands on autonomous weapons: recorded votes, "
        "official statements, and national policy, tracked as they shift over "
        "time. Every position links to a quoted, dated source.\n\n"
        "The site takes no position on whether autonomous weapons should be "
        "banned or regulated. It records who says what.\n\n"
        f"## Pages\n\n- [Home: world map, vote paths and the table of member states]({SITE_URL})\n"
        + listing + "\n"
        f"- State pages: {SITE_URL}state/ISO3.html (ISO 3166-1 alpha-3 code, for example USA)\n\n"
        "## Data\n\n"
        f"- [Positions, CSV]({SITE_URL}data/positions.csv) (CC BY 4.0)\n"
        f"- [Positions, JSON]({SITE_URL}data/positions.json) (CC BY 4.0)\n"
        "- Votes: https://github.com/wrobinson127/machine-politics (UN terms, non-commercial)\n",
        encoding="utf-8", newline="\n")


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
