"""Dossier render: the country state page as the signature artifact.

Ported from the approved France style tile (2026-07-19). Five arena bands in
their native forms plus the corpus band, all server-rendered from real content
YAML behind the approval gate; the JS layer only enhances (hover info panel,
linked highlighting, click-to-expand, draw-in), so the page stands with no JS.

Data flows one way: build_site imports this module and passes plain data; this
module imports only `config` and reimplements the two tiny helpers it needs, so
there is no circular import.
"""
import html as _html

from config import config

POS = config.PALETTE["positions"]
CAMP_USE = "#BA7517"
CAMP_TREATY = "#0F6E56"

# Position families as lateral shelves, ordered by how much binding law each
# seeks (never a ranking of the states; the axis is the instrument sought).
FAMILY_ORDER = ["LBI-BAN", "LBI-OPEN", "REG-SOFT", "CCW-ONLY", "OPPOSE"]
FAMILY_BLURB = {
    "LBI-BAN": "Binding, ban+regulate",
    "LBI-OPEN": "Binding, clarify IHL",
    "REG-SOFT": "Responsible use, no treaty",
    "CCW-ONLY": "The CCW forum only",
    "OPPOSE": "No new law",
}


def esc(v):
    return _html.escape("" if v is None else str(v), quote=True)


def _approved(entry):
    return isinstance(entry, dict) and entry.get("approved") is True


def _shows(entry, preview):
    return preview or _approved(entry)


def iso(v):
    return "" if v is None else str(v)


# ---------------------------------------------------------------------------
# Arena 1: the position spectrum (the world lensed through one state)
# ---------------------------------------------------------------------------

def spectrum(coded, self_iso, self_name):
    """coded: list of {iso3, name, code, confidence}. self highlighted large,
    peers muted to context. Absent families render an honest empty shelf."""
    by_fam = {f: [] for f in FAMILY_ORDER}
    for c in coded:
        if c["code"] in by_fam:
            by_fam[c["code"]].append(c)
    shelves = []
    for fam in FAMILY_ORDER:
        members = sorted(by_fam[fam], key=lambda c: (c["iso3"] != self_iso, c["name"]))
        host = any(c["iso3"] == self_iso for c in members)
        marks = []
        n = len(members)
        for i, c in enumerate(members):
            me = c["iso3"] == self_iso
            left = (i + 1) / (n + 1) * 100
            code2 = c["iso3"][:2].upper()
            info = (f"<b>{esc(c['name'])}</b> holds {esc(c['code'])}: "
                    f"{esc(FAMILY_BLURB.get(c['code'], ''))}."
                    + (" This page's state." if me else ""))
            cls = "pmark mk me" if me else "pmark mk"
            marks.append(
                f'<span class="{cls}" tabindex="0" data-tags="f:{esc(fam)}" '
                f'style="left:{left:.1f}%" data-info="{info}">{esc(code2)}</span>'
            )
        empty = '' if members else '<div class="fam-empty">none coded yet</div>'
        shelf_info = (f"<b>{esc(fam)}</b>: {esc(FAMILY_BLURB[fam])}. "
                      + (f"{n} coded state{'s' if n != 1 else ''} here."
                         if n else "No coded state here yet."))
        shelves.append(
            f'<div class="fam mk{" host" if host else ""}" tabindex="0" '
            f'data-hi="f:{esc(fam)}" data-info="{shelf_info}" '
            f'style="--famhue:{POS.get(fam) or "#999"}">'
            f'<div class="fam-h">{esc(fam)}</div>'
            f'<div class="fam-s">{esc(FAMILY_BLURB[fam])}</div>'
            f'{empty}{"".join(marks)}</div>'
        )
    return (
        '<div class="spectrum">'
        f'<div class="spec-cap"><b>{esc(self_name)}</b> among the states coded so far</div>'
        '<div class="spec-ax"><span>&larr; seeks the most binding law</span>'
        '<span>seeks no new law &rarr;</span></div>'
        f'<div class="shelves">{"".join(shelves)}</div></div>'
    )


# ---------------------------------------------------------------------------
# Arena 2: the voting floor (locate-pattern waffle, exactly 193 per grid)
# ---------------------------------------------------------------------------

VOTE_WORD = {"Y": "in favour", "N": "against", "A": "abstained", "X": "did not vote"}


def waffles(iso3, name, entry, votes):
    resolutions = votes["resolutions"]
    grids = []
    for key in config.LAWS_RESOLUTIONS:
        res = resolutions[key]
        tally = {"y": 0, "n": 0, "a": 0, "x": 0}
        for e in votes["states"].values():
            v = e["votes"][key]
            tally[{"Y": "y", "N": "n", "A": "a", "X": "x"}[v]] += 1
        self_vote = entry["votes"][key]
        seq = (["y"] * tally["y"] + ["n"] * tally["n"]
               + ["a"] * tally["a"] + ["x"] * tally["x"])
        assert len(seq) == 193, f"waffle {key} has {len(seq)} cells, not 193"
        self_class = {"Y": "y", "N": "n", "A": "a", "X": "x"}[self_vote]
        cells = []
        placed = False
        for v in seq:
            if not placed and v == self_class:
                cells.append(
                    f'<div class="cell me mk" tabindex="0" data-tags="v:{v}" '
                    f'data-info="<b>{esc(name)}</b> voted {esc(VOTE_WORD[self_vote])} '
                    f'on resolution {esc(res["symbol"])}."></div>'
                )
                placed = True
            else:
                cells.append(f'<div class="cell {v}" data-tags="v:{v}"></div>')
        grids.append(
            f'<div class="waffle"><h4>Resolution {esc(res["symbol"])}</h4>'
            f'<div class="res">{esc(res["date"])} &middot; '
            f'<a class="reslink" href="{esc(res["undl_link"])}">A/RES/{esc(res["symbol"])} &nearr;</a></div>'
            f'<div class="grid">{"".join(cells)}</div>'
            f'<div class="tally"><span class="big">{tally["y"]}</span>'
            f'<span class="of">in favour of 193</span></div></div>'
        )
    legend = (
        '<div class="vlegend">'
        '<span class="vg" data-hi="v:y" data-info="<b>In favour.</b> The large majority every time."><span class="cell y"></span> In favour</span>'
        '<span class="vg" data-hi="v:n" data-info="<b>Against.</b> A handful of states."><span class="cell n"></span> Against</span>'
        '<span class="vg" data-hi="v:a" data-info="<b>Abstained.</b>"><span class="cell a"></span> Abstained</span>'
        '<span class="vg" data-hi="v:x" data-info="<b>Non-voting</b> or absent."><span class="cell x"></span> Non-voting</span>'
        f'<span class="vg"><span class="cell me" style="box-shadow:0 0 0 1.5px var(--ink)"></span> {esc(name)}</span>'
        '</div>'
    )
    return f'<div class="waffles">{"".join(grids)}</div>{legend}'


# ---------------------------------------------------------------------------
# Arena 3: the signing table (both camps side by side)
# ---------------------------------------------------------------------------

def _seal(check):
    if check:
        return ('<span class="wax" aria-hidden="true"><svg viewBox="0 0 20 20">'
                '<path d="M4 10l4 4 8-9" fill="none" stroke="currentColor" '
                'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
                '</svg></span>')
    return '<span class="wax" aria-hidden="true"></span>'


def _sign_row(cls, check, nm, meta, info, src):
    body = (f'<span><span class="s-name">{esc(nm)}</span>'
            f'<span class="s-meta">{meta}</span></span>')
    tags = 'c:use' if 'use' in cls else 'c:treaty'
    attrs = f'data-tags="{tags}" data-info="{info}"'
    if src:
        attrs += f' data-src="{esc(src)}"'
    return (f'<div class="sign {cls} mk" tabindex="0" {attrs}>'
            f'{_seal(check)}{body}</div>')


def signing(iso3, name, endorsements, sponsorships):
    use_rows, treaty_rows = [], []
    n_use = 0
    for inst in endorsements:
        states = {r.get("iso3"): r for r in (inst.get("states") or []) if isinstance(r, dict)}
        row = states.get(iso3)
        date = iso(inst.get("date"))
        src = inst.get("list_source_url") or "#"
        if row and row.get("status") == "endorsed":
            n_use += 1
            use_rows.append(_sign_row(
                "use", True, inst.get("name", ""), f"Endorsed &middot; {esc(date)}",
                f"<b>{esc(name)}</b> endorsed the {esc(inst.get('name',''))}, {esc(date)}.",
                src))
        elif inst.get("states"):
            use_rows.append(_sign_row(
                "use absent", False, inst.get("name", ""), "Not on the list",
                f"{esc(name)} is not on the {esc(inst.get('name',''))} list. "
                "Not listed is an absence, not opposition.", None))
        else:
            use_rows.append(_sign_row(
                "use absent", False, inst.get("name", ""), "Named list not located",
                f"No official named list has been located for the "
                f"{esc(inst.get('name',''))}; {esc(name)}'s status is unrecorded.", None))
    n_treaty = 0
    for rec in sponsorships:
        members = set(rec.get("members") or [])
        date = iso(rec.get("date"))
        src = rec.get("url") or "#"
        if iso3 in members:
            n_treaty += 1
            treaty_rows.append(_sign_row(
                "treaty", True, rec.get("name", ""),
                f"Member &middot; {esc(date)}",
                f"<b>{esc(name)}</b> is a party to: {esc(rec.get('name',''))} ({esc(date)}).",
                src))
    if not treaty_rows:
        treaty_rows.append(_sign_row(
            "treaty absent", False, "No treaty-track membership on record",
            "None recorded",
            f"{esc(name)} has no treaty-track membership on record in this project yet.",
            None))
    return (
        '<div class="camps">'
        f'<div class="camp"><div class="camp-h mk" tabindex="0" data-hi="c:use" '
        f'data-info="The <b>responsible-use track</b>: voluntary pledges on military AI.">'
        f'<span class="cdot cdot-use"></span>'
        f'<span class="nm">Responsible-use track</span>'
        f'<span class="ct">Endorsed {n_use}</span></div>{"".join(use_rows)}</div>'
        f'<div class="camp"><div class="camp-h mk" tabindex="0" data-hi="c:treaty" '
        f'data-info="The <b>treaty / governance track</b>: statements and papers seeking a binding instrument.">'
        f'<span class="cdot cdot-treaty"></span>'
        f'<span class="nm">Treaty / governance track</span>'
        f'<span class="ct">Member {n_treaty}</span></div>{"".join(treaty_rows)}</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Arena 4: the chamber (engagement cadence rug + cumulative record)
# ---------------------------------------------------------------------------
from datetime import date as _date

CAD_START = _date(2013, 1, 1)
CAD_END = _date(2026, 6, 1)


def _xp(d):
    span = (CAD_END - CAD_START).days
    return max(0.0, min(100.0, (d - CAD_START).days / span * 100))


def _pdate(s):
    try:
        y, m, dd = str(s)[:10].split("-")
        return _date(int(y), int(m), int(dd))
    except Exception:
        return None


def cadence(iso3, name, entry, votes, cs, endorsements, sponsorships, preview):
    """One rug of dated acts in four type-lanes plus a cumulative 'record to
    date' strip. Sparse states honestly show few marks."""
    acts = []
    res = votes["resolutions"]
    for key in config.LAWS_RESOLUTIONS:
        v = entry["votes"][key]
        if v == "X":
            continue
        d = _pdate(res[key]["date"])
        if d:
            acts.append((3, "vote", d,
                         f"<b>{esc(name)}</b> voted {esc(VOTE_WORD[v])} on resolution "
                         f"{esc(res[key]['symbol'])}, {esc(res[key]['date'])}.",
                         res[key]["undl_link"]))
    for inst in endorsements:
        states = {r.get("iso3"): r for r in (inst.get("states") or []) if isinstance(r, dict)}
        row = states.get(iso3)
        if row and row.get("status") == "endorsed":
            d = _pdate(inst.get("date"))
            if d:
                acts.append((1, "pledge", d,
                             f"<b>{esc(name)}</b> endorsed the {esc(inst.get('name',''))}, "
                             f"{esc(iso(inst.get('date')))}.", inst.get("list_source_url")))
    for rec in sponsorships:
        if iso3 in set(rec.get("members") or []):
            d = _pdate(rec.get("date"))
            if d:
                acts.append((2, "stmt", d,
                             f"<b>{esc(name)}</b> is a party to {esc(rec.get('name',''))}, "
                             f"{esc(iso(rec.get('date')))}.", rec.get("url")))
    seen = set()
    for coding in cs.get("position_codings", []):
        if not _shows(coding, preview):
            continue
        for e in coding.get("evidence") or []:
            d = _pdate(e.get("date"))
            key = (str(e.get("date")), e.get("source"))
            if d and key not in seen:
                seen.add(key)
                acts.append((0, "paper", d,
                             f"{esc(name)} document on record: {esc(e.get('claim',''))} "
                             f"({esc(iso(e.get('date')))}).", e.get("url")))
    if not acts:
        return ('<div class="cadence"><p class="coverage-note">No dated acts on this '
                "project's record yet beyond the votes above.</p></div>")
    marks = []
    for lane, kind, d, info, src in acts:
        y = [21, 63, 105, 147][lane]
        attrs = f'data-tags="k:{kind}" data-info="{info}"'
        if src:
            attrs += f' data-src="{esc(src)}"'
        marks.append(f'<span class="cmark mk g-{kind}" tabindex="0" '
                     f'style="left:{_xp(d):.2f}%;top:{y}px" {attrs}></span>')
    reslines = "".join(
        f'<div class="resline" style="left:{_xp(_pdate(res[k]["date"])):.2f}%"></div>'
        for k in config.LAWS_RESOLUTIONS if _pdate(res[k]["date"]))
    dated = sorted(a[2] for a in acts)
    total = len(dated)
    H, TOP = 42, 7
    step = f"M 0 {H}"
    prev = 0
    for i, d in enumerate(dated):
        x = _xp(d)
        yv = H - ((i + 1) / total) * (H - TOP)
        yprev = H - (prev / total) * (H - TOP)
        step += f" L {x:.2f} {yprev:.2f} L {x:.2f} {yv:.2f}"
        prev = i + 1
    step += f" L 100 {H - (prev / total) * (H - TOP):.2f} L 100 {H} Z"
    cum = (f'<svg class="cum-area" viewBox="0 0 100 {H}" preserveAspectRatio="none">'
           f'<path d="{step}" fill="rgba(26,26,26,.09)" stroke="#6E675C" '
           'stroke-width="1" vector-effect="non-scaling-stroke"/></svg>')
    years = "".join(
        f'<span class="ytick" style="left:{_xp(_date(y,1,1)):.2f}%">{y}</span>'
        for y in (2014, 2018, 2022, 2026))
    return (
        '<div class="cadence">'
        f'<div class="cad-top"><div class="cad-total"><span class="ct-n">{total}</span>'
        '<span class="ct-l">acts on record</span></div></div>'
        '<div class="rug"><div class="lane-labels">'
        '<span>Submissions &amp; papers</span><span>Framework pledges</span>'
        '<span>Joint statements</span><span>Recorded votes</span>'
        '<span class="ll-cum">Record to date</span></div>'
        f'<div class="plot">{reslines}{cum}{"".join(marks)}</div></div>'
        f'<div class="years">{years}</div>'
        '<div class="clegend">'
        '<span class="cg" data-hi="k:paper"><span class="gl g-paper"></span> Submission</span>'
        '<span class="cg" data-hi="k:pledge"><span class="gl g-pledge"></span> Framework pledge</span>'
        '<span class="cg" data-hi="k:stmt"><span class="gl g-stmt"></span> Joint statement</span>'
        '<span class="cg" data-hi="k:vote"><span class="gl g-vote"></span> Recorded vote</span>'
        '</div></div>'
    )


# ---------------------------------------------------------------------------
# Arena 5: the ministry (doctrine) + the record (corpus)
# ---------------------------------------------------------------------------

def doctrine(cs, sources, preview, updated_through):
    d = cs.get("doctrine")
    if not (d and _shows(d, preview)):
        return ('<div class="coverage mk" tabindex="0" '
                'data-info="Doctrine has not been reviewed by this project for this state yet.">'
                f'<p class="cv-h">Doctrine not yet reviewed by this project, as of {esc(updated_through)}.</p></div>')
    status = d.get("status")
    if status == "no_policy_identified":
        return ('<div class="coverage mk" tabindex="0" '
                'data-info="A coverage statement, not a finding of no policy.">'
                f'<p class="cv-h">No published national policy identified by this project, as of {esc(iso(d.get("as_of")))}.</p>'
                f'<p class="cv-b">{esc(d.get("search_note",""))}</p></div>')
    parts = []
    for entry in d.get("entries") or []:
        if not _shows(entry, preview):
            continue
        draft = ' <span class="dchip">DRAFT</span>' if (preview and not _approved(entry)) else ''
        note = f'<p class="cv-b">{esc(entry.get("note",""))}</p>' if entry.get("note") else ''
        ev = "".join(_evi(e, sources) for e in entry.get("evidence") or [])
        parts.append(f'<div class="coverage mk" tabindex="0" data-info="{esc(entry.get("title",""))}">'
                     f'<p class="cv-h">{esc(entry.get("title",""))}{draft}</p>{note}{ev}</div>')
    for n in d.get("context") or []:
        if n.get("note"):
            parts.append('<div class="timeline"><div class="tl-item mk" tabindex="0" '
                         f'data-info="{esc(n["note"])}"><div class="t-h">Context on record</div></div></div>')
    return "".join(parts) if parts else doctrine({}, sources, preview, updated_through)


def corpus(iso3, name, cs, sources, preview):
    ids = []
    blocks = [c for c in cs.get("position_codings", []) if _shows(c, preview)]
    d = cs.get("doctrine")
    if d and _shows(d, preview):
        blocks += [e for e in (d.get("entries") or []) if _shows(e, preview)]
    for b in blocks:
        for e in b.get("evidence") or []:
            if e.get("source") and e["source"] not in ids:
                ids.append(e["source"])
    if not ids:
        return ('<p class="coverage-note">No primary documents on record for this state '
                'yet; the recorded votes above link to their UN records.</p>')
    docs = []
    for sid in ids:
        s = sources.get(sid) or {}
        title = str(s.get("title", sid))
        date = iso(s.get("date"))
        url = s.get("url") or "#"
        info = f"{esc(name)} document on record: {esc(title)} ({esc(date)})."
        docs.append(f'<a class="doc mk" tabindex="0" href="{esc(url)}" data-info="{info}">'
                    f'<div class="d-ic"></div><div class="d-t">{esc(title[:64])}</div>'
                    f'<div class="d-d">{esc(date)}</div></a>')
    return f'<div class="corpus">{"".join(docs)}</div>'


# ---------------------------------------------------------------------------
# Assembler: the full dossier body + the fixed info panel and popover
# ---------------------------------------------------------------------------

def _plain_position(cs, preview):
    codings = [c for c in cs.get("position_codings", []) if _shows(c, preview)]
    if not codings:
        return "Not yet coded by this project."
    c = sorted(codings, key=lambda c: iso(c.get("as_of")))[-1]
    cat = config.POSITION_CATEGORIES.get(c["code"], "")
    return f"Coded {esc(c['code'])}: {esc(cat)}."


def _vote_pattern(entry):
    seq = [entry["votes"][k] for k in config.LAWS_RESOLUTIONS]
    words = {"Y": "Yes", "N": "No", "A": "Abstain", "X": "did not vote"}
    if all(v == "Y" for v in seq):
        return "Yes on all three UN votes on autonomous weapons."
    return "Votes: " + ", ".join(words[v] for v in seq) + " across the three resolutions."


def state_body(iso3, name, un_name, entry, votes, cs, sources,
               endorsements, sponsorships, coded, preview, updated_through,
               doctrine_timeline=""):
    def band(q, plain, arena, hint=""):
        h = f'<p class="hint">{hint}</p>' if hint else ""
        return (f'<section class="arena" data-band>'
                f'<h2 class="band-q">{esc(q)}</h2>'
                f'<p class="plain">{plain}</p>{arena}{h}</section>')
    body = [
        f'<section class="hero"><p class="doc-label">State dossier</p>'
        f'<h1>{esc(name)}</h1>'
        f'<p class="sub"><b>{esc(iso3)}</b> &middot; {esc(un_name)} &middot; board row present</p></section>',
        band("What does this state want?", _plain_position(cs, preview),
             spectrum(coded, iso3, name)
             + own_coding(iso3, name, cs, sources, preview, updated_through),
             "This state shown large among peers &middot; hover a mark for its coding"),
        band("How did it vote?", esc(_vote_pattern(entry)),
             waffles(iso3, name, entry, votes),
             "Hover a legend chip to light those votes &middot; each resolution links to its record"),
        band("What has it signed?", "Membership is fact, not opposition.",
             signing(iso3, name, endorsements, sponsorships),
             "Hover a track header to light its signings &middot; click a seal to open the document"),
        band("When is it on the record?", "The engagement cadence, dated.",
             cadence(iso3, name, entry, votes, cs, endorsements, sponsorships, preview),
             "Hover a mark for its act &middot; a legend chip lights that type"),
        band("What has it written down at home?", "National doctrine.",
             doctrine_timeline + doctrine(cs, sources, preview, updated_through)),
        band("The record", "The documents on file.",
             corpus(iso3, name, cs, sources, preview),
             "Each mark opens its source"),
    ]
    panel = (
        '<div id="info" aria-live="polite"><div class="iw">'
        '<span class="lbl">Reading</span>'
        '<span class="body" id="info-body">Point at any mark to read its record. '
        'Click a mark to open the evidence.</span></div></div>'
        '<div id="pop" role="dialog" aria-label="Evidence">'
        '<button class="p-x" id="pop-x" aria-label="Close">&times;</button>'
        '<div id="pop-q" class="p-q"></div><div id="pop-m" class="p-m"></div>'
        '<a id="pop-src" class="p-src" target="_blank" rel="noopener">Open primary document &nearr;</a></div>'
    )
    return '<div class="dossier">' + "\n".join(body) + "</div>" + panel


def coded_states(content_states, votes, preview):
    """The comparative field for the spectrum: every state with a shown coding."""
    out = []
    for iso3, cs in content_states.items():
        codings = [c for c in cs.get("position_codings", []) if _shows(c, preview)]
        if not codings:
            continue
        c = sorted(codings, key=lambda c: iso(c.get("as_of")))[-1]
        entry = votes["states"].get(iso3)
        name = cs.get("display_name") or (entry["un_name"].title() if entry else iso3)
        out.append({"iso3": iso3, "name": name, "code": c["code"],
                    "confidence": c.get("confidence", "EXPLICIT")})
    out.sort(key=lambda c: c["iso3"])
    return out


# ---------------------------------------------------------------------------
# Static assets: dossier CSS (reuses site tokens for ground/ink/rule/fonts;
# hardcodes the dossier-specific palette) and the interaction JS (enhancement
# only; every mark is already server-rendered).
# ---------------------------------------------------------------------------

def dossier_css():
    return DOSSIER_CSS


def dossier_js():
    return DOSSIER_JS


DOSSIER_CSS = """/* Dossier: the country state page. Generated by tools/dossier_render.py.
   Reuses site tokens (--ground, --ink, --ink-soft, --rule, --font-display,
   --font-data); dossier-specific colors are hardcoded so nothing collides. */
:root{--mp-g2:#F1ECE2;--mp-faint:#8A8479;--mp-rs:#B9B0A0;
  --mp-lbiban:#3B5BA5;--mp-lbiopen:#2E7F86;--mp-regsoft:#B07D2B;
  --mp-ccwonly:#7A5C99;--mp-oppose:#7A5648;--mp-none:#D8D3C8;
  --mp-use:#BA7517;--mp-treaty:#0F6E56}
.dossier{padding-bottom:96px}
.dossier .hero{padding:6px 0 22px}
.dossier .doc-label{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--mp-faint);margin:0}
.dossier h1{font-family:var(--font-display);font-weight:500;font-size:clamp(48px,8vw,96px);line-height:.92;letter-spacing:-.01em;margin:6px 0 0}
.dossier .sub{font-size:13px;letter-spacing:.05em;color:var(--ink-soft);margin-top:10px}
.dossier .sub b{color:var(--ink);font-weight:600}
.arena{padding:28px 0;border-top:1px solid var(--rule)}
.band-q{font-family:var(--font-display);font-weight:500;font-size:clamp(22px,3.2vw,28px);margin:0 0 6px}
.plain{font-family:var(--font-display);font-size:19px;line-height:1.45;max-width:60ch;margin:0 0 4px;color:var(--ink)}
.hint{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mp-faint);margin:14px 0 0}
.coverage-note{font-size:13.5px;color:var(--ink-soft);max-width:64ch}
.mk{cursor:pointer;transition:opacity .18s ease,transform .18s ease,box-shadow .18s ease,filter .18s ease}
.mk:focus{outline:none}.mk:focus-visible{outline:2px solid var(--mp-lbiban);outline-offset:3px}
.dim{opacity:.3}.faint{opacity:.2}.glow{box-shadow:0 0 0 2px rgba(26,26,26,.4)}
/* spectrum */
.spectrum{margin:16px 0 0;border:1px solid var(--rule);background:var(--mp-g2);padding:16px 16px 12px}
.spec-cap{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mp-faint);margin-bottom:10px}
.spec-cap b{color:var(--ink);font-weight:600}
.spec-ax{display:flex;justify-content:space-between;font-size:10.5px;color:var(--mp-faint);margin-bottom:8px}
.shelves{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.fam{position:relative;border-top:3px solid var(--famhue);padding:9px 8px 40px;background:#FBF9F5;border-radius:0 0 2px 2px}
.fam-h{font-family:var(--font-display);font-weight:600;font-size:13.5px}
.fam-s{font-size:10.5px;color:var(--ink-soft);margin-top:2px;line-height:1.3;min-height:26px}
.fam.host{background:#fff;box-shadow:inset 0 0 0 1px var(--mp-rs)}
.fam-empty{position:absolute;bottom:14px;left:0;right:0;text-align:center;font-size:10px;color:var(--mp-faint);font-style:italic}
.pmark{position:absolute;bottom:10px;transform:translateX(-50%);width:19px;height:19px;border-radius:50%;
  background:var(--famhue);border:2px solid var(--ground);box-shadow:0 0 0 1px var(--mp-rs);
  display:grid;place-content:center;font-size:7.5px;font-weight:700;color:#fff;opacity:.5}
.pmark.me{width:36px;height:36px;box-shadow:0 0 0 2px var(--ink);z-index:2;font-size:11px;opacity:1}
.pmark.me::after{content:"this state";position:absolute;top:-15px;left:50%;transform:translateX(-50%);
  font-family:var(--font-data);font-size:8.5px;font-weight:600;color:var(--ink);white-space:nowrap}
.pmark.hot{transform:translateX(-50%) scale(1.15);opacity:1}
/* waffles */
.waffles{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin:16px 0 0}
.waffle h4{margin:0 0 2px;font-size:12px}
.waffle .res{font-size:10.5px;color:var(--mp-faint);margin-bottom:9px}
.reslink{color:var(--ink-soft);text-decoration:none;border-bottom:1px solid var(--mp-rs)}
.reslink:hover{color:var(--ink);border-bottom-color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(13,1fr);gap:2px}
.cell{aspect-ratio:1/1;border-radius:1px}
.cell.y{background:#6E675C}
.cell.n{background:transparent;box-shadow:inset 0 0 0 2px #6E675C}
.cell.a{background:linear-gradient(135deg,#9c968b 0 50%,transparent 50% 100%);box-shadow:inset 0 0 0 1px var(--mp-rs)}
.cell.x{background:#E7E1D6}
.cell.me{background:var(--mp-lbiban);box-shadow:0 0 0 2px var(--ground),0 0 0 3.5px var(--ink);z-index:2}
.cell.hot{transform:scale(1.35);z-index:3}
.tally{margin-top:12px;display:flex;align-items:baseline;gap:8px}
.tally .big{font-family:var(--font-display);font-weight:600;font-size:32px;line-height:1;font-variant-numeric:tabular-nums}
.tally .of{font-size:11px;color:var(--mp-faint)}
.vlegend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:16px 0 0;font-size:11px;color:var(--ink-soft)}
.vlegend .vg{display:inline-flex;align-items:center;gap:7px;cursor:pointer;padding:2px 4px;border-radius:2px}
.vlegend .vg:hover{background:var(--mp-g2)}
.vlegend .cell{width:13px;height:13px;aspect-ratio:auto;flex:none}
/* signing */
.camps{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:16px 0 0}
.camp{border:1px solid var(--rule);background:var(--mp-g2)}
.camp-h{padding:11px 15px;border-bottom:1px solid var(--rule);display:flex;align-items:center;gap:9px;cursor:pointer}
.camp-h:hover{background:#fff}
.camp-h .cdot{width:10px;height:10px;border-radius:50%;flex:none}
.cdot-use{background:var(--mp-use)}.cdot-treaty{background:var(--mp-treaty)}
.camp-h .nm{font-family:var(--font-display);font-weight:600;font-size:15px}
.camp-h .ct{margin-left:auto;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--mp-faint)}
.sign{display:flex;gap:12px;padding:12px 15px;border-top:1px solid var(--rule);align-items:center}
.sign:first-of-type{border-top:0}
.wax{flex:none;width:34px;height:34px;border-radius:50%;display:grid;place-content:center;border:1.5px solid currentColor;position:relative}
.wax::before{content:"";position:absolute;inset:3px;border-radius:50%;border:1px solid currentColor;opacity:.5}
.wax svg{width:15px;height:15px}
.sign.use .wax{color:var(--mp-use)}
.sign.treaty .wax{color:var(--mp-treaty)}
.sign.absent .wax{color:var(--mp-faint);border-style:dashed}
.sign.absent .wax::before{border-style:dashed}
.sign .s-name{display:block;font-size:13.5px;font-weight:500;line-height:1.35}
.sign.absent .s-name{color:var(--ink-soft);font-weight:400;font-style:italic}
.sign .s-meta{display:block;font-size:11px;color:var(--mp-faint);margin-top:3px}
.sign.hot{background:#fff}
/* cadence */
.cadence{margin:16px 0 0;border:1px solid var(--rule);background:var(--mp-g2);padding:16px 18px 12px}
.cad-top{display:flex;align-items:baseline;gap:11px;margin-bottom:16px}
.cad-total .ct-n{font-family:var(--font-display);font-weight:600;font-size:44px;line-height:.85;font-variant-numeric:tabular-nums}
.cad-total .ct-l{font-size:11px;color:var(--mp-faint);margin-left:9px}
.rug{display:grid;grid-template-columns:150px 1fr}
.lane-labels{height:210px;display:flex;flex-direction:column;justify-content:space-around;align-items:flex-end;padding-right:14px;text-align:right}
.lane-labels span{font-size:10.5px;color:var(--ink-soft);line-height:1.2}
.lane-labels .ll-cum{color:var(--mp-faint);font-style:italic}
.plot{position:relative;height:210px;background:repeating-linear-gradient(to bottom,transparent 0 41px,var(--rule) 41px 42px)}
.resline{position:absolute;top:0;height:168px;border-left:1px dotted var(--mp-rs);opacity:.7}
.cum-area{position:absolute;left:0;top:168px;width:100%;height:42px;overflow:visible}
.cmark{position:absolute;transform:translate(-50%,-50%);display:block}
.cmark.g-stmt{transform:translate(-50%,-50%) rotate(45deg)}
.cmark.g-stmt.hot{transform:translate(-50%,-50%) rotate(45deg) scale(1.4)}
.cmark.hot{transform:translate(-50%,-50%) scale(1.4);z-index:3}
.g-paper{width:14px;height:17px;border:1.5px solid var(--ink);background:var(--ground)}
.g-pledge{width:15px;height:15px;border-radius:50%;border:2px solid var(--mp-use);background:var(--ground)}
.g-stmt{width:14px;height:14px;background:var(--mp-treaty)}
.g-vote{width:11px;height:11px;background:#6E675C;border-radius:1px}
.years{position:relative;height:20px;margin:5px 0 0 150px;border-top:1px solid var(--mp-rs)}
.ytick{position:absolute;top:0;transform:translateX(-50%);font-size:10.5px;color:var(--mp-faint);padding-top:4px}
.clegend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:14px 0 0;font-size:11px;color:var(--ink-soft)}
.clegend .cg{display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:2px 4px;border-radius:2px}
.clegend .cg:hover{background:#fff}.clegend .gl{flex:none}.clegend .gl.g-stmt{transform:rotate(45deg)}
/* doctrine + corpus */
.coverage{margin:14px 0 0;padding:14px 16px;border:1px dashed var(--mp-rs)}
.coverage .cv-h{font-family:var(--font-display);font-size:16px;margin:0 0 4px}
.coverage .cv-b{font-size:13px;color:var(--ink-soft);line-height:1.55;max-width:66ch}
.dchip{font-size:9px;letter-spacing:.16em;color:var(--mp-faint);border:1px solid var(--mp-rs);border-radius:2px;padding:0 5px}
.timeline{margin:12px 0 0;border-left:2px solid var(--mp-rs);padding:2px 0 2px 18px}
.tl-item{position:relative;padding:5px 0 8px}
.tl-item::before{content:"";position:absolute;left:-25px;top:8px;width:11px;height:11px;border-radius:50%;background:var(--ground);border:2px dashed var(--mp-faint)}
.tl-item .t-h{font-size:13.5px;font-weight:500;color:var(--ink-soft);font-style:italic}
.corpus{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 0}
.doc{width:130px;border:1px solid var(--rule);background:var(--mp-g2);padding:12px;display:block;text-align:left;text-decoration:none;color:var(--ink)}
.doc .d-ic{width:26px;height:32px;border:1.5px solid var(--ink);margin-bottom:9px}
.doc .d-t{font-size:11.5px;line-height:1.35;font-weight:500}
.doc .d-d{font-size:10.5px;color:var(--mp-faint);margin-top:6px}
.doc.hot{border-color:var(--ink);background:#fff}
/* own-coding detail */
.codings{margin:18px 0 0}
.own-coding{padding:14px 0 0;border-top:1px solid var(--rule);margin-top:14px}
.own-coding:first-child{border-top:0;margin-top:0}
.oc-h{font-family:var(--font-display);font-weight:600;font-size:18px;margin:0}
.oc-c{font-size:11px;letter-spacing:.04em;color:var(--mp-faint);font-weight:400;margin-left:8px}
.oc-cat{font-size:13px;color:var(--ink-soft);margin:4px 0 6px}
.oc-claim{font-size:13px;color:var(--ink);margin:10px 0 2px;max-width:66ch}
.oc-q{font-family:var(--font-display);font-size:17px;line-height:1.45;margin:10px 0 4px;
  padding-left:14px;border-left:3px solid var(--mp-lbiban)}
.oc-q::before{content:"\\201C"}.oc-q::after{content:"\\201D"}
.oc-lang{font-family:var(--font-data);font-size:10px;color:var(--mp-faint)}
.oc-cite{font-size:11.5px;color:var(--mp-faint);margin:0 0 8px;padding-left:14px}
.oc-cite a{color:var(--ink);border-bottom:1px solid var(--mp-rs);text-decoration:none}
/* info panel */
#info{position:fixed;left:0;right:0;bottom:0;z-index:60;background:var(--ink);color:var(--ground);min-height:70px;display:flex;align-items:center}
#info .iw{max-width:960px;margin:0 auto;width:100%;padding:14px 28px;display:flex;gap:16px;align-items:center}
#info .lbl{flex:none;font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:#9a948a;border-right:1px solid #3a362f;padding-right:16px;align-self:stretch;display:flex;align-items:center}
#info .body{transition:opacity .13s ease;font-size:15px;line-height:1.5}
#info .body b{font-family:var(--font-display);font-weight:600}
#info .body a{color:#fff;border-bottom:1px solid #6f6a61}
/* popover */
#pop{position:fixed;z-index:70;max-width:340px;background:var(--ground);color:var(--ink);border:1px solid var(--ink);box-shadow:0 8px 26px rgba(20,16,10,.22);padding:15px 16px;display:none}
#pop.on{display:block}
#pop .p-q{font-family:var(--font-display);font-size:16px;line-height:1.45}
#pop .p-q:empty{display:none}
#pop .p-q::before{content:"\\201C"}#pop .p-q:not(:empty)::after{content:"\\201D"}
#pop .p-m{font-size:11px;color:var(--ink-soft);margin-top:9px}
#pop .p-src{display:inline-block;margin-top:11px;font-size:12px;color:var(--ink);border-bottom:1px solid var(--mp-rs);text-decoration:none}
#pop .p-x{position:absolute;top:8px;right:10px;font-size:14px;color:var(--mp-faint);background:none;border:0;cursor:pointer;line-height:1}
/* draw-in */
.arena .mk,.arena .tally,.arena .spectrum,.arena .waffle,.arena .camp,.arena .cadence,.arena .coverage,.arena .corpus{opacity:0;transform:translateY(10px);transition:opacity .5s ease,transform .5s ease}
.arena.in .mk,.arena.in .tally,.arena.in .spectrum,.arena.in .waffle,.arena.in .camp,.arena.in .cadence,.arena.in .coverage,.arena.in .corpus{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  .mk{transition:none}
  .arena .mk,.arena .tally,.arena .spectrum,.arena .waffle,.arena .camp,.arena .cadence,.arena .coverage,.arena .corpus{opacity:1;transform:none;transition:none}
  #info .body{transition:none}
}
/* mobile */
@media (max-width:720px){
  .dossier h1{font-size:60px}
  .shelves{grid-template-columns:1fr 1fr;gap:8px}
  .waffles{grid-template-columns:1fr;gap:26px}.grid{grid-template-columns:repeat(15,1fr)}
  .camps{grid-template-columns:1fr}
  .rug{grid-template-columns:88px 1fr}.lane-labels{padding-right:8px}.lane-labels span{font-size:9px}.years{margin-left:88px}
  .doc{width:calc(50% - 5px)}
  #info .iw{padding:12px 18px;gap:12px}
}
"""


DOSSIER_JS = """/* Dossier interaction layer (enhancement only; marks are server-rendered).
   Ported from the approved France tile: bottom info panel fade-swap, hover
   dim-siblings + scale, linked highlighting, click-to-expand popover, draw-in.
   Focus mirrors hover; reduced-motion is handled in CSS. */
(function(){
  var info=document.getElementById("info-body");
  if(!info) return;
  var DEFAULT=info.innerHTML;
  function setInfo(h){info.style.opacity=0;setTimeout(function(){info.innerHTML=h;info.style.opacity=1;},110);}
  function clearInfo(){info.style.opacity=0;setTimeout(function(){info.innerHTML=DEFAULT;info.style.opacity=1;},110);}
  function bandMarks(el){var b=el.closest("[data-band]")||el.closest(".hero");return b?b.querySelectorAll(".mk"):[];}
  function enter(el){if(el.dataset.info)setInfo(el.dataset.info);bandMarks(el).forEach(function(s){if(s!==el)s.classList.add("dim");});el.classList.add("hot");}
  function leave(el){bandMarks(el).forEach(function(s){s.classList.remove("dim");});el.classList.remove("hot");clearInfo();}
  function highlight(val){document.querySelectorAll("[data-tags]").forEach(function(m){if((" "+m.dataset.tags+" ").indexOf(" "+val+" ")>-1)m.classList.add("glow");else m.classList.add("faint");});}
  function unhighlight(){document.querySelectorAll(".glow,.faint").forEach(function(m){m.classList.remove("glow","faint");});}
  document.querySelectorAll(".mk, [data-hi]").forEach(function(el){
    var hi=el.dataset.hi;
    el.addEventListener("mouseenter",function(){if(hi){highlight(hi);if(el.dataset.info)setInfo(el.dataset.info);}else enter(el);});
    el.addEventListener("mouseleave",function(){if(hi){unhighlight();clearInfo();}else leave(el);});
    el.addEventListener("focus",function(){if(hi){highlight(hi);if(el.dataset.info)setInfo(el.dataset.info);}else enter(el);});
    el.addEventListener("blur",function(){if(hi){unhighlight();clearInfo();}else leave(el);});
    if(el.dataset.quote||el.dataset.src){
      el.addEventListener("click",function(e){e.preventDefault();e.stopPropagation();openPop(el);});
      el.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();openPop(el);}});
    }
  });
  var pop=document.getElementById("pop"),pq=document.getElementById("pop-q"),
      pm=document.getElementById("pop-m"),ps=document.getElementById("pop-src");
  function openPop(el){
    pq.textContent=el.dataset.quote||"";
    pm.textContent=el.dataset.date||el.dataset.meta||"";
    if(el.dataset.src){ps.style.display="inline-block";ps.href=el.dataset.src;}else ps.style.display="none";
    pop.classList.add("on");
    var r=el.getBoundingClientRect(),pw=Math.min(340,window.innerWidth-24);
    var x=Math.min(Math.max(12,r.left),window.innerWidth-pw-12),y=r.bottom+8;
    if(y+180>window.innerHeight)y=Math.max(12,r.top-190);
    pop.style.left=x+"px";pop.style.top=y+"px";pop.style.maxWidth=pw+"px";
  }
  function closePop(){pop.classList.remove("on");}
  var px=document.getElementById("pop-x");if(px)px.addEventListener("click",closePop);
  document.addEventListener("click",function(e){if(pop&&!pop.contains(e.target))closePop();});
  document.addEventListener("keydown",function(e){if(e.key==="Escape")closePop();});
  if("IntersectionObserver" in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(en){if(en.isIntersecting){en.target.classList.add("in");io.unobserve(en.target);}});},{threshold:.12});
    document.querySelectorAll(".arena").forEach(function(b){io.observe(b);});
  }else document.querySelectorAll(".arena").forEach(function(b){b.classList.add("in");});
})();
"""


def _evi(e, sources):
    src = sources.get(e.get("source")) or {}
    cite = f'{esc(src.get("title", e.get("source", "")))}, {esc(iso(e.get("date")))}'
    url = e.get("url") or src.get("url")
    link = f' <a href="{esc(url)}">source</a>' if url else ''
    claim = e.get("claim")
    lead = f'<p class="oc-claim">{esc(claim)}</p>' if claim else ''
    q = e.get("quote")
    if q:
        lang = e.get("lang", "en")
        note = f' <span class="oc-lang">[{esc(lang)}]</span>' if lang != "en" else ''
        return (f'{lead}<blockquote class="oc-q">{esc(q)}{note}</blockquote>'
                f'<p class="oc-cite">{cite}{link}</p>')
    d = e.get("description")
    if d or url or claim:
        return f'{lead}<p class="oc-cite">{esc(d or "")} {cite}{link}</p>'
    return ''


def own_coding(iso3, name, cs, sources, preview, updated_through):
    """The page-state's own coding detail: category, rationale, and evidence
    with source links. Gated; unapproved never renders on deploy."""
    codings = [c for c in cs.get("position_codings", []) if _shows(c, preview)]
    shifts = [s for s in cs.get("shift_events", []) if _shows(s, preview)]
    if not codings and not shifts:
        return ('<div class="coverage"><p class="cv-b">Statements for this state are '
                f'not yet reviewed by this project, as of {esc(updated_through)}. The '
                'recorded votes above are complete.</p></div>')
    parts = []
    for c in sorted(codings, key=lambda c: iso(c.get("as_of"))):
        cat = config.POSITION_CATEGORIES.get(c["code"], "")
        draft = ' <span class="dchip">DRAFT</span>' if (preview and not _approved(c)) else ''
        rat = f'<p class="cv-b">{esc(c.get("rationale", ""))}</p>' if c.get("rationale") else ''
        ev = "".join(_evi(e, sources) for e in c.get("evidence") or [])
        parts.append(
            f'<div class="own-coding"><h3 class="oc-h">{esc(c["code"])} '
            f'<span class="oc-c">since {esc(iso(c.get("as_of")))}, {esc(c.get("confidence", ""))}</span>'
            f'{draft}</h3><p class="oc-cat">{esc(cat)}.</p>{rat}{ev}</div>')
    for s in sorted(shifts, key=lambda s: iso(s.get("date"))):
        draft = ' <span class="dchip">DRAFT</span>' if (preview and not _approved(s)) else ''
        ev = "".join(_evi(e, sources) for e in s.get("evidence") or [])
        parts.append(
            f'<div class="own-coding"><h3 class="oc-h">Shift: {esc(s.get("from", ""))} '
            f'&rarr; {esc(s.get("to", ""))} <span class="oc-c">{esc(iso(s.get("date")))}</span>'
            f'{draft}</h3>{ev}</div>')
    return '<div class="codings">' + "".join(parts) + '</div>'
