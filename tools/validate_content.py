"""Validate the claim-bearing content layer.

Enforces, as code, the invariants the handoff makes project law:
- evidence schema: quote length, date, url, lang, translation, confidence
  (a quote with no translation cannot appear for a non-English source)
- approval gate: every claim-bearing entry carries an explicit approved flag
- prohibited-claim class: no copy may assert a state has no policy; absence
  is only ever a coverage statement with an as_of date
- rubric integrity: category codes and confidence tiers match config exactly
- registry integrity: every evidence source resolves to content/sources.yaml
- key integrity: every state file matches its filename and appears in the
  derived votes data

Exit code 1 with itemized errors on any violation. Importable for tests and
the site build.
"""

import gzip
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config

DOCTRINE_STATUSES = ("policy_identified", "no_policy_identified", "not_yet_reviewed")

# Invariant 10, the no-inference rule: these source types never support an
# axis-A coding by themselves. Endorsing an instrument is not a position;
# sponsoring a text is not a position; doctrine is its own signal.
NON_CODING_SOURCE_TYPES = {"policy", "endorsement_list", "sponsorship_record"}

ENDORSEMENT_STATUSES = ("endorsed", "documented_non_endorsement", "not_listed")

# Invariant 13: no state ever receives a rank, grade, or index. The display
# layer enforces the rest; the schema layer refuses to even hold one.
SCORE_KEYS = {"score", "rank", "grade", "rating", "index", "tier"}

ISO3_RE = re.compile(r"^[A-Z]{3}$")


def _check_entry_dict(errors, where, entry):
    if not isinstance(entry, dict):
        errors.add(where, f"entry must be a mapping, got {type(entry).__name__}")
        return False
    hits = set(entry) & SCORE_KEYS
    if hits:
        errors.add(where, f"no composite scores, ranks, or grades, ever (invariant 13): {sorted(hits)}")
    return True

# Evidence entries may carry an optional kind; EOVs are a named subtype.
EVIDENCE_KINDS = ("eov", "statement", "submission", "working_paper")

# The prohibited-claim class (invariant 6): copy that asserts a state has no
# policy or position. The site only ever makes dated coverage statements.
# The scan skips `quote` fields: quotes are verbatim source material, and the
# prohibition binds this project's copy, not what states or documents say.
_PPD = r"(?:policy|position|doctrine)"
PROHIBITED_CLAIM_PATTERNS = [
    re.compile(r"\bhas\s+no\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
    re.compile(r"\bhave\s+no\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
    re.compile(r"\bdoes\s+not\s+have\s+(?:\w+\s+){0,3}?" + _PPD, re.I),
    re.compile(r"\bno\s+(?:\w+\s+){0,2}?" + _PPD + r"\s+exists\b", re.I),
    re.compile(r"\bwithout\s+(?:a|any)\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
    re.compile(r"\blacks?\s+(?:a|any)\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
    re.compile(r"\b(?:maintains?|holds?|possess(?:es)?)\s+no\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
    re.compile(r"\b(?:has\s+)?(?:adopted|published|issued|articulated|stated)\s+no\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
    re.compile(r"\bthere\s+is\s+no\s+(?:\w+\s+){0,3}?" + _PPD, re.I),
    re.compile(r"\bnever\s+(?:adopted|published|issued|articulated|stated|held)\s+(?:a|any)\s+(?:\w+\s+){0,2}?" + _PPD, re.I),
]

# Keys a doctrine context annotation may carry. Context instruments are
# first-class timeline entries (two-class model) but never coded evidence
# (invariant 7), so nothing codeable is allowed.
CONTEXT_ALLOWED_KEYS = {"note", "title", "url", "date", "archived", "source", "approved"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Errors:
    def __init__(self):
        self.items = []
        self.warnings = []  # reported, never fatal (invariant 11 archive links)

    def add(self, where, message):
        self.items.append(f"{where}: {message}")

    def warn(self, where, message):
        self.warnings.append(f"{where}: {message}")

    def __bool__(self):
        return bool(self.items)


def _is_date(value):
    # PyYAML parses unquoted ISO dates into datetime.date; both forms are fine
    if isinstance(value, date):
        return True
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _check_date(errors, where, value, field="date"):
    if not _is_date(value):
        errors.add(where, f"{field} must be YYYY-MM-DD, got {value!r}")


def _check_url(errors, where, value):
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        errors.add(where, f"url must be an http(s) link, got {value!r}")


def _check_approved(errors, where, entry):
    if not isinstance(entry.get("approved"), bool):
        errors.add(where, "claim-bearing entry needs an explicit approved: true/false")


def scan_prohibited_claims(errors, where, value, key=None):
    """Walk every string in a structure for the prohibited-claim class."""
    if key == "quote":
        return  # verbatim source material is exempt; the ban binds our copy
    if isinstance(value, str):
        for pattern in PROHIBITED_CLAIM_PATTERNS:
            if pattern.search(value):
                errors.add(
                    where,
                    "prohibited claim (asserts absence of a policy/position "
                    f"instead of a dated coverage statement): {value.strip()[:90]!r}",
                )
    elif isinstance(value, dict):
        for k, v in value.items():
            scan_prohibited_claims(errors, f"{where}.{k}", v, key=k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            scan_prohibited_claims(errors, f"{where}[{i}]", v, key=key)


def check_evidence(errors, where, entry, source_ids):
    if not isinstance(entry, dict):
        errors.add(where, "evidence entry must be a mapping")
        return
    for field in ("source", "date", "url", "lang", "translation", "confidence"):
        if field not in entry:
            errors.add(where, f"evidence missing required field {field!r}")
    if entry.get("source") not in source_ids:
        errors.add(where, f"evidence source {entry.get('source')!r} not in sources.yaml")
    if "date" in entry:
        _check_date(errors, where, entry["date"])
    if "url" in entry:
        _check_url(errors, where, entry["url"])
    translation = entry.get("translation")
    if translation not in config.TRANSLATION_VALUES:
        errors.add(where, f"translation must be one of {config.TRANSLATION_VALUES}")
    confidence = entry.get("confidence")
    if confidence not in config.CONFIDENCE_TIERS:
        errors.add(where, f"confidence must be one of {config.CONFIDENCE_TIERS}")
    lang = entry.get("lang")
    quote = entry.get("quote")
    if quote is not None:
        if not isinstance(quote, str) or not quote.strip():
            errors.add(where, "quote, when present, must be a non-empty string")
        elif len(quote.split()) > config.EVIDENCE_QUOTE_MAX_WORDS:
            errors.add(
                where,
                f"quote exceeds {config.EVIDENCE_QUOTE_MAX_WORDS} words "
                f"({len(quote.split())})",
            )
        if translation == "none" and lang != "en":
            errors.add(
                where,
                "a source with translation: none and a non-English lang cannot "
                "carry a quote; describe and link instead (INFERRED at best)",
            )
    if translation == "none" and lang != "en":
        if not entry.get("description"):
            errors.add(where, "untranslated non-English source needs a description")
        if confidence == "EXPLICIT":
            errors.add(where, "untranslated non-English source caps confidence at INFERRED")
    if quote is None and not entry.get("description"):
        errors.add(where, "evidence needs a quote or, where none can exist, a description")
    kind = entry.get("kind")
    if kind is not None and kind not in EVIDENCE_KINDS:
        errors.add(where, f"evidence kind must be one of {EVIDENCE_KINDS}")


def check_no_inference(errors, where, coding, source_ids):
    """Invariant 10: a coding whose every evidence ref is an endorsement,
    sponsorship, or doctrine source has no statement or vote behind it."""
    evidence = [e for e in (coding.get("evidence") or []) if isinstance(e, dict)]
    if not evidence:
        return
    types = {
        (source_ids.get(e.get("source")) or {}).get("type") for e in evidence
    }
    if types and types <= NON_CODING_SOURCE_TYPES:
        errors.add(
            where,
            "no-inference rule: endorsements, sponsorships, and doctrine "
            f"never feed a coding by themselves (evidence types: {sorted(t for t in types if t)})",
        )


def check_coding(errors, where, coding, source_ids):
    if coding.get("code") not in config.POSITION_CATEGORIES:
        errors.add(where, f"unknown Axis A code {coding.get('code')!r}")
    if coding.get("confidence") not in config.CONFIDENCE_TIERS:
        errors.add(where, f"confidence must be one of {config.CONFIDENCE_TIERS}")
    _check_date(errors, where, coding.get("as_of"), "as_of")
    _check_approved(errors, where, coding)
    evidence = coding.get("evidence") or []
    if coding.get("code") == "NONE":
        if not coding.get("search_note"):
            errors.add(where, "a NONE coding needs a search_note recording the look")
    elif not evidence:
        errors.add(where, "a coding other than NONE needs at least one evidence entry")
    for i, entry in enumerate(evidence):
        check_evidence(errors, f"{where}.evidence[{i}]", entry, source_ids)
    check_no_inference(errors, where, coding, source_ids)


def check_shift_event(errors, where, event, iso3, source_ids):
    if event.get("state") != iso3:
        errors.add(where, f"shift event state {event.get('state')!r} != file state {iso3}")
    _check_date(errors, where, event.get("date"))
    for field in ("from", "to"):
        if event.get(field) not in config.POSITION_CATEGORIES:
            errors.add(where, f"{field} must be an Axis A code, got {event.get(field)!r}")
    if event.get("from") == event.get("to"):
        errors.add(where, "shift event must change category (from == to)")
    _check_approved(errors, where, event)
    evidence = event.get("evidence") or []
    if not evidence:
        errors.add(where, "shift event needs at least one evidence entry")
    for i, entry in enumerate(evidence):
        check_evidence(errors, f"{where}.evidence[{i}]", entry, source_ids)
    check_no_inference(errors, where, event, source_ids)


def check_doctrine(errors, where, doctrine, source_ids):
    status = doctrine.get("status")
    if status not in DOCTRINE_STATUSES:
        errors.add(where, f"doctrine status must be one of {DOCTRINE_STATUSES}")
        return
    _check_approved(errors, where, doctrine)
    if status == "no_policy_identified":
        if not _is_date(doctrine.get("as_of")):
            errors.add(where, "no_policy_identified requires an as_of date")
        if not doctrine.get("search_note"):
            errors.add(where, "no_policy_identified requires a search_note")
    if status == "policy_identified":
        entries = doctrine.get("entries") or []
        if not entries:
            errors.add(where, "policy_identified requires at least one entry")
        for i, entry in enumerate(entries):
            e_where = f"{where}.entries[{i}]"
            if not entry.get("title"):
                errors.add(e_where, "doctrine entry needs a title")
            _check_approved(errors, e_where, entry)
            _check_archived(errors, e_where, entry)
            evidence = entry.get("evidence") or []
            if not evidence:
                errors.add(e_where, "doctrine entry needs evidence")
            for j, ev in enumerate(evidence):
                check_evidence(errors, f"{e_where}.evidence[{j}]", ev, source_ids)
    # context annotations are never coded evidence (invariant 7): only
    # descriptive keys are allowed, so nothing codeable can be smuggled in
    for i, note in enumerate(doctrine.get("context") or []):
        n_where = f"{where}.context[{i}]"
        extra = set(note) - CONTEXT_ALLOWED_KEYS
        if extra:
            errors.add(
                n_where,
                f"context annotations allow only {sorted(CONTEXT_ALLOWED_KEYS)}; "
                f"found {sorted(extra)} (strict scope)",
            )
        if not note.get("note"):
            errors.add(n_where, "context annotation needs a note")
        # dated context instruments are timeline entries; they carry links
        if note.get("date"):
            if not note.get("url"):
                errors.add(n_where, "a dated context instrument needs a url")
            _check_archived(errors, n_where, note)


def _check_archived(errors, where, entry):
    """Invariant 11: doctrine and endorsement entries carry url + archived.
    Missing links are CI warnings, not failures; the research passes fill
    them and the morning report carries the outstanding count."""
    if not entry.get("url"):
        errors.warn(where, "entry has no url (invariant 11)")
    elif not entry.get("archived"):
        errors.warn(where, "no archived snapshot for this url (invariant 11)")


def load_sources(errors, content_dir):
    path = content_dir / "sources.yaml"
    if not path.exists():
        errors.add("sources.yaml", "missing")
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources") or []
    ids = {}
    for i, src in enumerate(sources):
        where = f"sources.yaml[{i}]"
        sid = src.get("id")
        if not sid:
            errors.add(where, "source needs an id")
            continue
        if sid in ids:
            errors.add(where, f"duplicate source id {sid!r}")
        ids[sid] = src
        for field in ("title", "publisher", "date", "url", "type", "lang", "accessed"):
            if not src.get(field):
                errors.add(f"{where}({sid})", f"missing field {field!r}")
        if "date" in src:
            _check_date(errors, f"{where}({sid})", src["date"])
        if "accessed" in src:
            _check_date(errors, f"{where}({sid})", src["accessed"], "accessed")
        if "url" in src:
            _check_url(errors, f"{where}({sid})", src["url"])
    return ids


def load_votes_states():
    if not config.VOTES_DERIVED_JSON.exists():
        return None
    with gzip.open(config.VOTES_DERIVED_JSON, "rt", encoding="utf-8") as f:
        return set(json.load(f)["states"])


def check_rubric(errors, content_dir):
    path = content_dir / "rubric.yaml"
    if not path.exists():
        errors.add("rubric.yaml", "missing")
        return
    rubric = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(rubric.get("approved"), bool):
        errors.add("rubric.yaml", "needs an explicit approved: true/false")
    categories = (rubric.get("axis_a") or {}).get("categories") or {}
    if list(categories) != list(config.POSITION_CATEGORIES):
        errors.add(
            "rubric.yaml",
            f"axis_a categories {list(categories)} must match config order "
            f"{list(config.POSITION_CATEGORIES)}",
        )
    for code, body in categories.items():
        if not (body or {}).get("description"):
            errors.add("rubric.yaml", f"category {code} needs a plain-language description")
    tiers = (rubric.get("axis_b") or {}).get("tiers") or {}
    if set(tiers) != set(config.CONFIDENCE_TIERS):
        errors.add("rubric.yaml", f"axis_b tiers must be {config.CONFIDENCE_TIERS}")
    scan_prohibited_claims(errors, "rubric.yaml", rubric)


def check_state_file(errors, path, source_ids, vote_states):
    iso3 = path.stem
    where = f"states/{path.name}"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("iso3") != iso3:
        errors.add(where, f"iso3 {data.get('iso3')!r} must match filename {iso3!r}")
    if not re.fullmatch(r"[A-Z]{3}", iso3):
        errors.add(where, "filename must be an uppercase alpha-3 code")
    if vote_states is not None and iso3 not in vote_states:
        errors.add(where, f"{iso3} not present in derived votes data")
    for field in ("un_name", "display_name"):
        if not data.get(field):
            errors.add(where, f"missing field {field!r}")
    for i, coding in enumerate(data.get("position_codings") or []):
        c_where = f"{where}.position_codings[{i}]"
        if _check_entry_dict(errors, c_where, coding):
            check_coding(errors, c_where, coding, source_ids)
    for i, event in enumerate(data.get("shift_events") or []):
        e_where = f"{where}.shift_events[{i}]"
        if _check_entry_dict(errors, e_where, event):
            check_shift_event(errors, e_where, event, iso3, source_ids)
    if "doctrine" in data:
        check_doctrine(errors, f"{where}.doctrine", data["doctrine"], source_ids)
    scan_prohibited_claims(errors, where, data)


def check_page_file(errors, path):
    where = f"pages/{path.name}"
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    if not m:
        errors.add(where, "prose page needs YAML front matter with approved and title")
        return
    meta = yaml.safe_load(m.group(1)) or {}
    _check_approved(errors, where, meta)
    if not meta.get("title"):
        errors.add(where, "front matter needs a title")
    body = re.sub(r"<!--.*?-->", "", m.group(2), flags=re.S)  # comments are notes to the analyst
    scan_prohibited_claims(errors, where, body)
    for ch, name in (("—", "em dash"), ("–", "en dash")):
        if ch in body:
            errors.add(where, f"prose contains an {name}; voice rules forbid it")


def validate(content_dir=None):
    content_dir = Path(content_dir) if content_dir else config.CONTENT_DIR
    errors = Errors()
    source_ids = load_sources(errors, content_dir)
    check_rubric(errors, content_dir)
    vote_states = load_votes_states()
    states_dir = content_dir / "states"
    if states_dir.exists():
        for path in sorted(states_dir.glob("*.yaml")):
            check_state_file(errors, path, source_ids, vote_states)
    pages_dir = content_dir / "pages"
    if pages_dir.exists():
        for path in sorted(pages_dir.glob("*.md")):
            check_page_file(errors, path)
    tour_path = content_dir / "tour.yaml"
    if tour_path.exists():
        check_tour(errors, tour_path)
    endorsements = content_dir / "endorsements.yaml"
    if endorsements.exists():
        check_endorsements(errors, endorsements, vote_states)
    sponsorships = content_dir / "sponsorships.yaml"
    if sponsorships.exists():
        check_sponsorships(errors, sponsorships, vote_states)
    eras_dir = content_dir / "eras"
    if eras_dir.exists():
        check_eras(errors, eras_dir, vote_states)
    return errors


def check_endorsements(errors, path, vote_states):
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    seen = set()
    for i, inst in enumerate(data.get("instruments") or []):
        where = f"endorsements.yaml[{i}]"
        if not _check_entry_dict(errors, where, inst):
            continue
        where = f"endorsements.yaml[{i}]({inst.get('id', '?')})"
        for field in ("id", "name", "date", "list_source_url", "list_as_of"):
            if not inst.get(field):
                errors.add(where, f"instrument needs {field!r}")
        if inst.get("id") in seen:
            errors.add(where, f"duplicate instrument id {inst['id']!r}")
        seen.add(inst.get("id"))
        _check_approved(errors, where, inst)
        _check_archived(errors, where, {"url": inst.get("list_source_url"),
                                        "archived": inst.get("list_source_archived")})
        for j, row in enumerate(inst.get("states") or []):
            r_where = f"{where}.states[{j}]"
            if not _check_entry_dict(errors, r_where, row):
                continue
            status = row.get("status")
            if status not in ENDORSEMENT_STATUSES:
                errors.add(r_where, f"status must be one of {ENDORSEMENT_STATUSES}")
            iso3 = row.get("iso3")
            if not iso3 or not isinstance(iso3, str) or not ISO3_RE.match(iso3):
                errors.add(r_where, f"row needs an uppercase alpha-3 iso3, got {iso3!r}")
            elif vote_states is not None and iso3 not in vote_states and not str(row.get("non_member_note") or "").strip():
                errors.add(
                    r_where,
                    f"{iso3} is not a UN member state in the vote data; "
                    "non-member endorsers need a non_member_note",
                )
            if status == "documented_non_endorsement" and not (row.get("evidence") or row.get("note")):
                errors.add(
                    r_where,
                    "documented_non_endorsement needs evidence or a note recording "
                    "the official documentation (attendance + non-signature)",
                )
            if row.get("date"):
                _check_date(errors, r_where, row["date"])
    scan_prohibited_claims(errors, "endorsements.yaml", data)


def check_sponsorships(errors, path, vote_states):
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    seen = set()
    for i, rec in enumerate(data.get("records") or []):
        where = f"sponsorships.yaml[{i}]"
        if not _check_entry_dict(errors, where, rec):
            continue
        where = f"sponsorships.yaml[{i}]({rec.get('instrument_id', '?')})"
        for field in ("instrument_id", "name", "date", "url", "members"):
            if not rec.get(field):
                errors.add(where, f"record needs {field!r}")
        if rec.get("instrument_id") in seen:
            errors.add(where, f"duplicate instrument_id {rec['instrument_id']!r}")
        seen.add(rec.get("instrument_id"))
        _check_approved(errors, where, rec)
        _check_archived(errors, where, rec)
        if "date" in rec:
            _check_date(errors, where, rec["date"])
        members = rec.get("members") or []
        if len(set(members)) != len(members):
            errors.add(where, "duplicate members")
        for m in members:
            if not isinstance(m, str) or not ISO3_RE.match(m):
                errors.add(where, f"member {m!r} must be an uppercase alpha-3 code")
            elif vote_states is not None and m not in vote_states:
                errors.add(where, f"member {m!r} not a UN member state in the vote data")
    scan_prohibited_claims(errors, "sponsorships.yaml", data)


CAUSAL_WORDS = re.compile(
    r"\bbecause\b|\bcaused?\b|\bled to\b|\bresult(?:ed|ing) in\b|\bdue to\b|\bin response to\b",
    re.I,
)


def check_eras(errors, eras_dir, vote_states):
    for path in sorted(eras_dir.glob("*.yaml")):
        iso3 = path.stem
        where = f"eras/{path.name}"
        if vote_states is not None and iso3 not in vote_states:
            errors.add(where, f"{iso3} not a UN member state in the vote data")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for i, era in enumerate(data.get("eras") or []):
            e_where = f"{where}[{i}]"
            if not _check_entry_dict(errors, e_where, era):
                continue
            for field in ("label", "start", "source"):
                if not era.get(field):
                    errors.add(e_where, f"era needs {field!r}")
            if era.get("start"):
                _check_date(errors, e_where, era["start"], "start")
            if era.get("end"):
                _check_date(errors, e_where, era["end"], "end")
            text = f"{era.get('label', '')} {era.get('note', '')}"
            if CAUSAL_WORDS.search(text):
                errors.add(
                    e_where,
                    "era bands are context data; causal copy is prohibited "
                    "(invariant 14; documented-causation lives in evidence, not era labels)",
                )
        scan_prohibited_claims(errors, where, data)


def check_tour(errors, path):
    where = "tour.yaml"
    tour = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _check_approved(errors, where, tour)
    beats = tour.get("beats") or []
    if len(beats) != 4:
        errors.add(where, f"the tour has exactly four beats, found {len(beats)}")
    known_figures = {"tally-78-241", "track-USA", "movers", "full-board"}
    for i, beat in enumerate(beats):
        b_where = f"{where}.beats[{i}]"
        for field in ("id", "title", "copy", "figure"):
            if not beat.get(field):
                errors.add(b_where, f"beat needs {field!r}")
        if beat.get("figure") and beat["figure"] not in known_figures:
            errors.add(b_where, f"unknown figure {beat['figure']!r}; known: {sorted(known_figures)}")
        for ch, name in (("—", "em dash"), ("–", "en dash")):
            if ch in str(beat.get("copy", "")) + str(beat.get("title", "")):
                errors.add(b_where, f"beat title or copy contains an {name}; voice rules forbid it")
    scan_prohibited_claims(errors, where, tour)


def main():
    errors = validate()
    for warning in errors.warnings:
        print(f"WARNING {warning}")
    if errors:
        print(f"content validation FAILED with {len(errors.items)} error(s):")
        for item in errors.items:
            print(f"  - {item}")
        sys.exit(1)
    print(
        "content validation OK"
        + (f" ({len(errors.warnings)} warning(s))" if errors.warnings else "")
    )


if __name__ == "__main__":
    main()
