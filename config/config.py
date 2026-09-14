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

# One sentence per category, plain language (analyst rewrite, 2026-09-14).
POSITION_CATEGORIES = {
    "LBI-BAN": "Supports a legally binding treaty that prohibits some systems",
    "LBI-OPEN": "Supports negotiating a treaty but has not said what it should prohibit",
    "REG-SOFT": "Supports new international rules that are not legally binding",
    "CCW-ONLY": "Supports continuing the consensus process in the Geneva weapons convention, and has not said what it should produce",
    "OPPOSE": "Opposes any new international rules on autonomous weapons",
    "AMBIG": "Has said things that point in more than one direction",
    "NONE": "This site looked and found no stated position",
}

# The plain label that leads everywhere a code appears (key, legend, state
# pages, hover text). The code follows it in small type: the code is what the
# data files use, the label is what a reader needs. Pick the words once; the
# rubric's own label fields must match these exactly.
POSITION_PLAIN = {
    "LBI-BAN": "Wants a treaty with bans",
    "LBI-OPEN": "Wants a treaty, terms open",
    "REG-SOFT": "Wants new rules, not a treaty",
    "CCW-ONLY": "Keep it in Geneva",
    "OPPOSE": "No new rules",
    "AMBIG": "Unclear or shifting",
    "NONE": "No stated position",
}

# Confidence in plain words, paired with the tier in brackets on the page.
CONFIDENCE_PLAIN = {
    "EXPLICIT": "stated directly",
    "INFERRED": "interpreted",
    "AMBIGUOUS": "points both ways",
    "PROVISIONAL": "awaiting the document",
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
    "no published military policy on weapon autonomy found by this site, as of {as_of}"
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
# AMBIG is a hatch texture over paper and carries no hue at all. Every other
# substantive position pairs its hue with a texture from POSITION_TEXTURES
# below, so no category depends on colour vision alone.
# ---------------------------------------------------------------------------

PALETTE = {
    "ground": "#F7F4EE",  # warm paper
    "ink": "#1A1A1A",
    "positions": {
        "LBI-BAN": "#3B5BA5",   # blue
        "LBI-OPEN": "#2E7F86",  # teal
        "REG-SOFT": "#A9741F",  # ochre (deepened from #B07D2B for WCAG 3:1 on era-b cream)
        "CCW-ONLY": "#7A5C99",  # plum
        "OPPOSE": "#7A5648",    # brown
        "AMBIG": None,           # hatch texture over neutral; no fill hue
        # Absence, on record: reviewed, nothing substantive found. Deepened
        # from #D8D3C8, which sat at 1.18:1 on the era-b band and was very
        # nearly invisible, collapsing "no substantive position on record"
        # into "empty track: not yet reviewed" and contradicting the
        # methodology's promise that the absence tiers never blend. Pinned at
        # roughly 2.4:1: unmistakably a fill, and still quieter than every
        # substantive position, the lowest of which is REG-SOFT at 3.18.
        "NONE": "#9E9482",
    },
    "not_yet_reviewed": None,    # empty/paper with explicit label, never a fill
    "integrity_red": "#C0392B",  # data-integrity notices + shift-seams ONLY
}

# ---------------------------------------------------------------------------
# Position textures. Hue alone cannot carry these categories: simulated under
# deuteranopia, LBI-OPEN and CCW-ONLY separate by 30 on a scale where about 90
# is the threshold for reading as different fills, and REG-SOFT collides with
# integrity red at 32, which would silently break the promise that saturated
# red means only a data-integrity notice. A palette search confirmed this is
# structural rather than a bad choice of hex: the best available repalette
# moves the worst pair from 30 to 32, because the binding constraint just
# becomes ochre against red. So every substantive position also carries a
# texture, extending the mechanism AMBIG already used. Texture, not a printed
# label: bands can be a handful of pixels wide when a state moves twice in a
# year, and text does not survive that.
#
# Orientation is the channel, because it survives at 16px and stays legible
# when a band is narrow. Each value is a CSS class defined in site.css.
# LBI-BAN is deliberately untextured: it is the largest category, and leaving
# it plain keeps the board quiet.
#
# Two orientations are deliberately unused. Vertical rules are out because the
# track already carries vertical year gridlines and the two would read as one
# pattern. A 45 degree forward hatch is reserved for AMBIG alone, so CCW-ONLY
# takes the opposite diagonal. REG-SOFT gets the crosshatch because it is the
# category that collides with integrity red, and a two-axis texture is the
# furthest thing on the board from a thin red vertical seam.
# ---------------------------------------------------------------------------

POSITION_TEXTURES = {
    "LBI-BAN": "",                    # solid
    "LBI-OPEN": " band-horizontal",   # horizontal rules
    "REG-SOFT": " band-grid",         # crosshatch
    "CCW-ONLY": " band-backslash",    # 135 degree diagonal
    "OPPOSE": " band-dots",           # stipple
    "AMBIG": " band-hatch",           # 45 degree hatch on paper, no hue
    "NONE": "",                       # absence is flat by design
}

# ---------------------------------------------------------------------------
# Site constants
# ---------------------------------------------------------------------------

SITE_NAME = "Machine Politics"
SITE_DOMAIN = "machinepolitics.walker-robinson.com"
TIMELINE_START_YEAR = 2013
# The date the record is current to: the latest dated review or fact across
# approved content. It ends the board axis and stamps every "as of" phrase.
# It is not the vote-dataset snapshot date; that is UN_DATASET_DOWNLOADED_ON
# and the dataset version named on the methodology page. A test holds this
# at or after every approved as_of, so it cannot quietly fall behind.
UPDATED_THROUGH = "2026-08-31"
UN_DATASET_DOWNLOADED_ON = "2026-07-16"
UN_DATASET_RECORD_URL = "https://digitallibrary.un.org/record/4060887"
