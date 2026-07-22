"""Generate the social-share (Open Graph) card as a static PNG.

This is deliberately NOT part of build_site.py: PNG text rendering depends on
locally installed fonts and is not byte-identical across platforms, so baking
it into the build would break the CI freshness gate (build + git diff on the
Linux runner would not match a Windows-committed PNG). Instead this runs once,
locally, and the result is committed as a static asset that build_site never
rewrites. Re-run only when the card design or wordmark changes.

The card is intentionally generic (wordmark + standing tagline + a palette
motif), not a live board snapshot, so it never goes stale as data changes.

Usage:  python tools/gen_og_card.py
Output: site/assets/og-card.png  (1200x630)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (247, 244, 238)     # #F7F4EE paper
INK = (26, 26, 26)       # #1A1A1A
SOFT = (122, 116, 105)   # muted ink for secondary text

# Position palette, in axis order, as the motif strip (echoes the board).
BANDS = [
    (0x3B, 0x5B, 0xA5),  # LBI-BAN blue
    (0x2E, 0x7F, 0x86),  # LBI-OPEN teal
    (0xA9, 0x74, 0x1F),  # REG-SOFT ochre
    (0x7A, 0x5C, 0x99),  # CCW-ONLY plum
    (0x7A, 0x56, 0x48),  # OPPOSE brown
    (0xD8, 0xD3, 0xC8),  # NONE neutral
]


def _font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _tracked(draw, xy, text, font, fill, tracking):
    """Draw letter-spaced text (Pillow has no native tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Serif display for the wordmark (Newsreader's stack falls back to Georgia).
    title_font = _font(["georgia.ttf", "Georgia.ttf", "times.ttf",
                        "DejaVuSerif.ttf"], 108)
    tag_font = _font(["georgia.ttf", "Georgia.ttf", "times.ttf",
                     "DejaVuSerif.ttf"], 40)
    label_font = _font(["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"], 22)
    foot_font = _font(["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"], 24)

    margin = 84

    # Eyebrow label
    _tracked(d, (margin, 92), "A PUBLIC REGISTRY", label_font, SOFT, 5)

    # Wordmark
    d.text((margin - 4, 150), "Machine Politics", font=title_font, fill=INK)

    # Tagline (two lines, generous measure)
    d.text((margin, 300),
           "Where every country stands on", font=tag_font, fill=INK)
    d.text((margin, 350),
           "lethal autonomous weapons.", font=tag_font, fill=INK)

    # Palette motif strip
    strip_y = 452
    strip_h = 26
    seg_w = (W - 2 * margin) / len(BANDS)
    for i, rgb in enumerate(BANDS):
        x0 = margin + i * seg_w
        d.rectangle([x0, strip_y, x0 + seg_w - 6, strip_y + strip_h], fill=rgb)

    # Footer: what it tracks + the domain
    d.text((margin, 520),
           "Recorded votes  ·  official statements  ·  national policy",
           font=foot_font, fill=SOFT)
    d.text((margin, 556),
           "machinepolitics.walker-robinson.com", font=foot_font, fill=INK)

    out = Path(__file__).resolve().parent.parent / "site" / "assets" / "og-card.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
