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
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config  # noqa: E402


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


W, H = 1200, 630
BG = _rgb(config.PALETTE["ground"])
INK = _rgb(config.PALETTE["ink"])
SOFT = (122, 116, 105)   # muted ink for secondary text

# Position palette, in the rubric's own category order, as the motif strip
# that echoes the board. Derived from config rather than copied: this strip
# previously held its own literal hex values and silently kept showing the old
# NONE neutral for a week after the palette moved, on the single most-seen
# image the project has. AMBIG is absent because it has no hue at all; it is a
# texture over paper, and a solid swatch would misrepresent it.
BANDS = [_rgb(config.PALETTE["positions"][code])
         for code in config.POSITION_CATEGORIES
         if config.PALETTE["positions"].get(code)]


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
