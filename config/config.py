"""Single source of truth for Machine Politics.

Category codes, confidence tiers, absence tiers, palette tokens, paths, and
site constants live here and nowhere else. Tools and the site build import
from this module; the site's CSS custom properties are generated from
PALETTE, never hand-copied.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_SOURCE_DIR = REPO_ROOT / ".scratch" / "source"
DATA_SOURCE_DIR = REPO_ROOT / "data" / "source"
DATA_DERIVED_DIR = REPO_ROOT / "data" / "derived"
CONTENT_DIR = REPO_ROOT / "content"
STATES_DIR = CONTENT_DIR / "states"
SITE_DIR = REPO_ROOT / "site"

VOTES_EXTRACT_CSV = DATA_SOURCE_DIR / "ga_voting_extract.csv.gz"
VOTES_DERIVED_JSON = DATA_DERIVED_DIR / "votes.json.gz"
RUBRIC_YAML = CONTENT_DIR / "rubric.yaml"
SOURCES_YAML = CONTENT_DIR / "sources.yaml"

# ---------------------------------------------------------------------------
# Position categories (Axis A of the rubric; mutually exclusive at a dated
# point in time). Order here is the canonical display order.
# ---------------------------------------------------------------------------

POSITION_CATEGORIES = {
    "LBI-BAN": "Supports a legally binding instrument that includes prohibitions",
    "LBI-OPEN": "Supports negotiating a legally binding instrument, form unspecified",
    "REG-SOFT": "Supports new non-binding measures",
    "CCW-ONLY": "Supports the CCW/GGE consensus process only, no stated outcome position",
    "OPPOSE": "Opposes new international instruments",
    "AMBIG": "Position ambiguous or evolving",
    "NONE": "No substantive position on record",
}

# ---------------------------------------------------------------------------
# Confidence tiers (Axis B). Confidence modulates saturation and a
# dotted-underline convention in the UI. It never changes hue.
# PROVISIONAL (P3c, analyst ruling 2026-07-17): coded from secondary
# reporting pending verification against the primary record. Renders with
# the lowered-confidence treatment (reduced saturation, dotted underline)
# plus a required provisional_note surfaced in captions and telemetry.
# Distinct from the data-integrity red state, which stays reserved for
# corrections and superseded codings.
# ---------------------------------------------------------------------------

CONFIDENCE_TIERS = ("EXPLICIT", "INFERRED", "AMBIGUOUS", "PROVISIONAL")

TRANSLATION_VALUES = ("official", "unofficial", "none")

EVIDENCE_QUOTE_MAX_WORDS = 25

# ---------------------------------------------------------------------------
# Absence tiers (invariant 6). These are coverage statements, never
# positions, and the two values are never conflated or blended.
# ---------------------------------------------------------------------------

ABSENCE_TIERS = ("no_position_on_record", "not_yet_reviewed")

DOCTRINE_ABSENCE = "no_policy_identified"  # requires as_of + search_note
DOCTRINE_ABSENCE_PHRASE = (
    "no published national policy identified by this project, as of {as_of}"
)

# ---------------------------------------------------------------------------
# Vote values as they appear in the derived votes.json
# ---------------------------------------------------------------------------

# Exactly the domain the UN data dictionary defines; verified against all
# 947,434 rows of the source dataset in Phase 0.
VOTE_VALUES = {
    "Y": "Yes",
    "N": "No",
    "A": "Abstain",
    "X": "Non-voting",
}

# The three LAWS resolutions tracked in v1, with expected plenary tallies
# (yes, no, abstain) used as extraction sanity checks.
LAWS_RESOLUTIONS = {
    "78/241": {"year": 2023, "tally": (152, 4, 11)},
    "79/62": {"year": 2024, "tally": (166, 3, 15)},
    "80/57": {"year": 2025, "tally": (164, 6, 7)},
}

# ---------------------------------------------------------------------------
# Palette tokens (DESIGN.md is authoritative for semantics; these are the
# concrete values). No position renders red or green. Saturated red carries
# exactly two reserved meanings (DESIGN v2.1 rule 10): data-integrity
# notices, and the shift-seam marking the moment a coded position changes.
# AMBIG is a hatch texture, not a hue.
# ---------------------------------------------------------------------------

PALETTE = {
    "ground": "#F7F4EE",  # warm paper
    "ink": "#1A1A1A",
    "positions": {
        "LBI-BAN": "#3B5BA5",   # blue
        "LBI-OPEN": "#2E7F86",  # teal
        "REG-SOFT": "#B07D2B",  # ochre
        "CCW-ONLY": "#7A5C99",  # plum
        "OPPOSE": "#7A5648",    # brown
        "AMBIG": None,           # hatch texture over neutral; no fill hue
        "NONE": "#D8D3C8",      # light neutral (absence: on record, nothing substantive)
    },
    "not_yet_reviewed": None,    # empty/paper with explicit label, never a fill
    "integrity_red": "#C0392B",  # data-integrity notices + shift-seams ONLY
}

# ---------------------------------------------------------------------------
# Site constants
# ---------------------------------------------------------------------------

SITE_NAME = "Machine Politics"
SITE_DOMAIN = "machinepolitics.walker-robinson.com"
TIMELINE_START_YEAR = 2013
UPDATED_THROUGH = "2026-02-06"  # date of the UN dataset snapshot in use
UN_DATASET_DOWNLOADED_ON = "2026-07-16"
UN_DATASET_RECORD_URL = "https://digitallibrary.un.org/record/4060887"
