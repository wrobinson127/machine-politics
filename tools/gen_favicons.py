"""Generate the raster favicons from the same ledger mark as favicon.svg.

Google's search results show a site's favicon only from a square raster or SVG
it can crawl, at least 48x48 and ideally a multiple of 48, and many crawlers
still ask for /favicon.ico. The SVG stays the icon browsers use; these are the
fallbacks. Like gen_og_card.py this runs once, locally, and the results are
committed as static assets that build_site never rewrites. Re-run only when
the mark or the palette changes.

Usage:  python tools/gen_favicons.py
Output: site/favicon.ico (16, 32, 48), site/assets/favicon-192.png
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import config  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site"


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


GROUND = _rgb(config.PALETTE["ground"])
INK = _rgb(config.PALETTE["ink"])
# The broken band is ink at 45% over the ground, as in favicon.svg.
SOFT = tuple(round(i * 0.45 + g * 0.55) for i, g in zip(INK, GROUND))
# favicon.svg's bands on its 32-unit grid: x, y, width, height (radius 1).
BANDS = [(5, 8, 22, INK), (5, 14.5, 12, INK), (20, 14.5, 7, SOFT), (5, 21, 22, INK)]


def mark(size):
    """The mark at size x size, drawn 8x larger and scaled down for clean edges."""
    big = size * 8
    k = big / 32
    img = Image.new("RGB", (big, big), GROUND)
    d = ImageDraw.Draw(img)
    for x, y, w, color in BANDS:
        d.rounded_rectangle([x * k, y * k, (x + w) * k, (y + 3.5) * k], radius=k, fill=color)
    return img.resize((size, size), Image.LANCZOS)


def main():
    mark(192).save(SITE / "assets" / "favicon-192.png", optimize=True)
    mark(48).save(SITE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote site/favicon.ico and site/assets/favicon-192.png")


if __name__ == "__main__":
    main()
