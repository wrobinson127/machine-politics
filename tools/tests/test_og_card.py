"""The social card is a committed PNG that build_site never rewrites, for a
good reason: PNG text rendering depends on locally installed fonts and is not
byte-identical across platforms, so generating it in the build would break the
CI freshness gate. The cost of that decision is that nothing notices when the
card falls behind the palette, and nothing did: the strip kept showing the old
NONE neutral after the palette moved, on the most-seen image the project has.

This reads the committed pixels back instead. It does not regenerate anything,
so it stays platform-independent while still failing the moment the card and
the palette disagree.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config

Image = pytest.importorskip("PIL.Image", reason="Pillow not installed")

CARD = Path(__file__).resolve().parents[2] / "site" / "assets" / "og-card.png"

# Where gen_og_card.py paints the motif strip: y=452, height 26, inset by an
# 84px margin, split into equal segments with a 6px gap.
STRIP_Y, MARGIN, GAP = 465, 84, 6


def _hex(rgb):
    return "#%02X%02X%02X" % rgb


def _expected_bands():
    """Hued positions in the rubric's category order. AMBIG is excluded: it
    has no hue, and a solid swatch would misrepresent a texture."""
    return [config.PALETTE["positions"][code]
            for code in config.POSITION_CATEGORIES
            if config.PALETTE["positions"].get(code)]


def _sampled_bands(img):
    width = img.size[0]
    bands = _expected_bands()
    seg = (width - 2 * MARGIN) / len(bands)
    out = []
    for i in range(len(bands)):
        # Sample the middle of each segment, clear of the inter-segment gap.
        x = int(MARGIN + i * seg + (seg - GAP) / 2)
        out.append(_hex(img.getpixel((x, STRIP_Y))))
    return out


def test_the_card_exists_and_is_the_right_size():
    assert CARD.exists(), "no social card committed"
    with Image.open(CARD) as img:
        assert img.size == (1200, 630), (
            f"card is {img.size}; Open Graph wants 1200x630")


def test_the_card_strip_matches_the_live_palette():
    """The failure this exists for: a palette change that never reaches the
    card, so every share preview shows colours the site no longer uses."""
    with Image.open(CARD) as img:
        sampled = _sampled_bands(img.convert("RGB"))
    expected = [c.upper() for c in _expected_bands()]
    assert sampled == expected, (
        "the committed social card no longer matches the palette.\n"
        f"  card:    {sampled}\n"
        f"  palette: {expected}\n"
        "Re-run: python tools/gen_og_card.py")


def test_the_card_ground_matches_the_paper():
    with Image.open(CARD) as img:
        corner = _hex(img.convert("RGB").getpixel((4, 4)))
    assert corner == config.PALETTE["ground"].upper(), (
        f"card ground is {corner}, palette paper is {config.PALETTE['ground']}")


def test_the_generator_reads_the_palette_rather_than_copying_it():
    """The root cause of the drift was a second copy of the hex values living
    in the generator. A literal position colour there means it can happen
    again, whatever the pixels happen to say today."""
    src = (Path(__file__).resolve().parents[2]
           / "tools" / "gen_og_card.py").read_text(encoding="utf-8")
    for code, color in config.PALETTE["positions"].items():
        if not color:
            continue
        h = color.lstrip("#")
        literal = ", ".join(f"0x{h[i:i + 2]}" for i in (0, 2, 4))
        assert literal.lower() not in src.lower(), (
            f"gen_og_card.py hardcodes {code} ({color}) instead of reading "
            "config.PALETTE, so the card can drift out of sync again")
