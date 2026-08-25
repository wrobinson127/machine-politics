"""The board encodes a state's position in the fill of a band, so a reader who
cannot separate two fills cannot read the board. These tests hold the guarantee
that no category depends on colour vision alone, and that the mechanism which
delivers it is actually wired up end to end.

The wiring tests exist because this project has twice shipped a feature whose
gates were all green and whose effect was silently absent: four wrong SRI
hashes that killed the tour, and a rubric allowlist that dropped rendered
fields. A texture that is assigned in config but never defined in CSS, or a
fill that clobbers its own texture, would fail exactly that way.
"""

import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs
from tools import color_vision as cv

SITE_CSS = Path(__file__).resolve().parents[2] / "site" / "css" / "site.css"
ERA_A, ERA_B = "#F4F0E8", "#EAE4D6"


def _hued_bands():
    """Position categories that render as a filled band with a hue. AMBIG is
    excluded because it has no hue at all: it is texture on paper, and so is
    separable from every fill by construction."""
    return {k: v for k, v in config.PALETTE["positions"].items() if v}


def _texture_of(code):
    return config.POSITION_TEXTURES[code].strip()


def test_no_two_bands_rely_on_hue_alone():
    """The load-bearing guarantee. For any pair of bands a colour-vision
    deficient reader cannot tell apart by hue, the textures must differ."""
    cats = _hued_bands()
    failures = []
    for a, b in itertools.combinations(cats, 2):
        worst = cv.worst_separation(cats[a], cats[b])
        if worst < cv.SEPARATION_THRESHOLD and _texture_of(a) == _texture_of(b):
            failures.append(
                f"{a} vs {b}: hue separation {worst:.1f} is below "
                f"{cv.SEPARATION_THRESHOLD} and both render as "
                f"{_texture_of(a) or 'solid'}")
    assert not failures, "bands separable by neither hue nor texture:\n" + \
        "\n".join(failures)


def test_the_threshold_actually_bites():
    """Guards the test above from passing vacuously. If every pair were already
    far apart on hue, the loop would assert nothing at all."""
    cats = _hued_bands()
    colliding = [
        (a, b) for a, b in itertools.combinations(cats, 2)
        if cv.worst_separation(cats[a], cats[b]) < cv.SEPARATION_THRESHOLD]
    assert len(colliding) >= 3, (
        "expected several hue collisions for texture to rescue, found "
        f"{len(colliding)}; if the palette really did separate on hue alone "
        "this test and the textures could go, but verify that before deleting")


def test_integrity_red_is_never_a_position_fill():
    """Red's separation from the positions is not what protects it. Under
    deuteranopia it sits 32 from REG-SOFT. What protects it is that it is never
    a band: it is a seam and a notice border, so shape carries the meaning."""
    red = config.PALETTE["integrity_red"]
    clashing = [k for k, v in config.PALETTE["positions"].items() if v == red]
    assert not clashing, f"integrity red used as a position fill: {clashing}"


def test_the_shift_seam_stays_visible_when_its_hue_collides():
    """The seam marks when a position changed. Against a REG-SOFT band a
    deuteranope cannot see it by colour, so it must carry a non-colour cue."""
    css = SITE_CSS.read_text(encoding="utf-8")
    # Anchored to the start of a line so this finds the standalone `.c-seam`
    # rule and not the `#c-board .c-seam` animation rule, which sets only
    # opacity and would make this assertion fail no matter what.
    rule = re.search(r"^\.c-seam\s*\{([^}]*)\}", css, re.M)
    assert rule, "no standalone .c-seam rule found"
    body = rule.group(1)
    assert re.search(r"^\s*(box-shadow|outline|border)\s*:", body, re.M), (
        "the shift seam is a bare red fill with no shape cue, so it "
        "disappears into any band whose hue it collides with")


def test_every_category_declares_a_texture():
    missing = set(config.POSITION_CATEGORIES) - set(config.POSITION_TEXTURES)
    assert not missing, f"categories with no texture decision: {sorted(missing)}"


def test_every_assigned_texture_class_exists_in_the_stylesheet():
    """An assigned class with no rule behind it renders as a plain fill and
    looks exactly like success. Only the stylesheet can prove otherwise."""
    css = SITE_CSS.read_text(encoding="utf-8")
    for code, cls in config.POSITION_TEXTURES.items():
        cls = cls.strip()
        if not cls:
            continue
        rule = re.search(rf"\.{re.escape(cls)}\s*\{{([^}}]*)\}}", css)
        assert rule, f"{code} is assigned .{cls} but site.css defines no such rule"
        # Anchored to a property start: a bare substring test also matches
        # x-background-image and other typos that paint nothing.
        assert re.search(r"^\s*background-image\s*:", rule.group(1), re.M), (
            f".{cls} exists but sets no background-image, so {code} would "
            "render as a plain fill")


def test_textured_bands_do_not_clobber_their_own_texture():
    """An inline `background:` shorthand resets background-image to none and
    outranks the stylesheet, so it would silently erase every texture. The hue
    must ride on a custom property instead."""
    for code in config.POSITION_TEXTURES:
        style, _ = bs.band_style(code, "EXPLICIT")
        assert not re.search(r"(^|;)\s*background\s*:", style), (
            f"{code} emits a background shorthand ({style!r}), which would "
            "erase its texture")

    style, texture = bs.band_style("LBI-OPEN", "EXPLICIT")
    assert "--fill:" in style and texture.strip(), (
        "a textured category must emit both a --fill hue and a texture class")


def test_the_stylesheet_paints_the_custom_property():
    """--fill only becomes a colour if some rule consumes it."""
    css = SITE_CSS.read_text(encoding="utf-8")
    assert re.search(r"background-color:\s*var\(--fill", css), (
        "no rule reads --fill, so every band would render transparent")


def test_the_fill_rule_cannot_outrank_the_hatch():
    """AMBIG has no --fill, so it relies on .band-hatch setting its own paper
    background. If the --fill rule used a descendant selector it would win on
    specificity and leave AMBIG transparent wherever it appears."""
    # Strip comments first: they sit between rules and would otherwise be
    # captured as part of the selector.
    css = re.sub(r"/\*.*?\*/", "", SITE_CSS.read_text(encoding="utf-8"),
                 flags=re.S)
    rule = re.search(r"(?:^|\})([^{}]*)\{[^}]*background-color:\s*var\(--fill",
                     css, re.S)
    assert rule, "no rule consumes --fill"
    for selector in rule.group(1).split(","):
        selector = selector.strip()
        assert selector and " " not in selector, (
            f"--fill is applied via the compound selector {selector!r}, which "
            "outranks .band-hatch and would blank the AMBIG background")

    fill_at = css.index("background-color: var(--fill")
    hatch_at = css.index(".band-hatch")
    assert hatch_at > fill_at, (
        ".band-hatch must follow the --fill rule to win on source order")


def test_legend_swatches_carry_the_same_texture_as_the_bands():
    """The legend is where the reader learns the encoding. A legend that shows
    only hue teaches a code the board does not use."""
    legend = bs.legend_html()
    for code, cls in config.POSITION_TEXTURES.items():
        cls = cls.strip()
        if not cls:
            continue
        assert f'class="swatch {cls}"' in legend, (
            f"legend swatch for {code} is missing its {cls} texture")


def test_every_fill_clears_the_contrast_floor_against_both_era_bands():
    """A band a reader cannot see against the paper carries no information.
    NONE is exempt and deliberately quiet: it means 'reviewed, nothing
    substantive on record', and is pinned here so a change is a decision."""
    for code, color in config.PALETTE["positions"].items():
        if color is None or code == "NONE":
            continue
        worst = min(cv.contrast_ratio(color, ERA_A),
                    cv.contrast_ratio(color, ERA_B))
        assert worst >= 3.0, (
            f"{code} ({color}) contrasts only {worst:.2f}:1 against the era "
            "bands; 3:1 is the floor for a meaningful UI element")


def test_body_ink_clears_wcag_aa():
    ratio = cv.contrast_ratio(config.PALETTE["ink"], config.PALETTE["ground"])
    assert ratio >= 4.5, f"body text contrast is {ratio:.2f}:1"
