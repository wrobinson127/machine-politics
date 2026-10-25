"""Search engines show a site's icon only from a crawlable square image of at
least 48x48, and many still ask for /favicon.ico. The raster icons are
committed (tools/gen_favicons.py), so these checks keep them present, linked
from every page, and in the current palette."""

import sys
from pathlib import Path

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import gen_favicons

SITE = Path(__file__).resolve().parents[2] / "site"
ICO = SITE / "favicon.ico"
PNG = SITE / "assets" / "favicon-192.png"


def test_the_root_favicon_ico_holds_a_48_pixel_icon():
    with Image.open(ICO) as img:
        assert img.format == "ICO"
        assert (48, 48) in img.info["sizes"]


def test_the_png_icon_is_192_square():
    with Image.open(PNG) as img:
        assert img.format == "PNG" and img.size == (192, 192)


def test_every_page_links_all_three_icons():
    for page in (SITE / "index.html", SITE / "state" / "USA.html", SITE / "404.html"):
        html = page.read_text(encoding="utf-8")
        assert 'favicon.svg' in html, page.name
        assert 'favicon.ico" sizes="48x48"' in html, page.name
        assert 'favicon-192.png" type="image/png" sizes="192x192"' in html, page.name


def test_the_raster_icons_match_the_palette_and_the_generator():
    """The committed PNG is what the generator draws now, so a palette change
    without a re-run fails here. Re-run: python tools/gen_favicons.py"""
    ground = gen_favicons._rgb(config.PALETTE["ground"])
    with Image.open(PNG) as img:
        committed = img.convert("RGB")
    assert committed.getpixel((2, 2)) == ground
    # A few levels of slack: resampling can round differently across Pillow builds.
    diff = ImageChops.difference(committed, gen_favicons.mark(192))
    worst = max(hi for _, hi in diff.getextrema())
    assert worst <= 8, "favicon-192.png is stale. Re-run: python tools/gen_favicons.py"
