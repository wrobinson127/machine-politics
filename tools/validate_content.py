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

# Keys a doctrine context annotation may carry. Context is never coded
# evidence (invariant 7), so anything beyond descriptive fields is rejected.
CONTEXT_ALLOWED_KEYS = {"note", "title", "url", "date", "source"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Errors:
    def __init__(self):
        self.items = []

    def add(self, where, message):
        self.items.append(f"{where}: {message}")

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
        check_coding(errors, f"{where}.position_codings[{i}]", coding, source_ids)
    for i, event in enumerate(data.get("shift_events") or []):
        check_shift_event(errors, f"{where}.shift_events[{i}]", event, iso3, source_ids)
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
    return errors


def main():
    errors = validate()
    if errors:
        print(f"content validation FAILED with {len(errors.items)} error(s):")
        for item in errors.items:
            print(f"  - {item}")
        sys.exit(1)
    print("content validation OK")


if __name__ == "__main__":
    main()
