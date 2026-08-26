"""Assets are served from stable paths, so a browser or CDN holding a cached
copy keeps serving it after a deploy. During the colour-vision work a stale
site.css twice made a working board render with transparent bands, and it
looked exactly like a build bug. On a live site the same thing hands returning
readers markup and a stylesheet that disagree.

Every locally served asset therefore carries a content hash in its URL. These
tests hold the two halves of that: the link must be versioned, and the version
must be the version of the bytes actually on disk.
"""

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import build_site as bs

# Local assets only. CDN scripts are pinned by version in the URL and locked
# by subresource integrity, so they are already immune to this.
LOCAL_ASSET = re.compile(r'(?:href|src)="((?!https?://)[^"]*?'
                         r'(?:\.css|\.js|favicon\.svg))(\?v=([0-9a-f]+))?"')


def _pages(root):
    return sorted(root.rglob("*.html"))


def test_every_local_asset_link_is_versioned(tmp_path):
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    unversioned = []
    for page in _pages(out):
        for path, query, _ in LOCAL_ASSET.findall(page.read_text(encoding="utf-8")):
            if not query:
                unversioned.append(f"{page.name} -> {path}")
    assert not unversioned, (
        "these asset links carry no content hash, so a cached copy survives a "
        "deploy:\n" + "\n".join(sorted(set(unversioned))))


def test_every_version_matches_the_bytes_on_disk(tmp_path):
    """A hash that does not track the file is worse than none: it looks like
    cache-busting and never busts anything."""
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    wrong = []
    for page in _pages(out):
        for path, _, digest in LOCAL_ASSET.findall(page.read_text(encoding="utf-8")):
            if not digest:
                continue
            # 404.html links root-absolute, because Pages serves it from any
            # path; every other page links relative to itself.
            base = out if path.startswith("/") else page.parent
            target = (base / path.lstrip("/")).resolve()
            assert target.exists(), f"{page.name} links missing asset {path}"
            # Newlines normalised, deliberately restated here rather than
            # imported, so a change to how the build hashes has to be a
            # conscious change to this rule too. See the line-endings test.
            text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
            actual = hashlib.sha256(text.encode("utf-8")).hexdigest()[:len(digest)]
            if actual != digest:
                wrong.append(f"{page.name} -> {path}: links {digest}, file is {actual}")
    assert not wrong, "stale asset hashes:\n" + "\n".join(wrong)


def test_changing_an_asset_changes_its_url(tmp_path):
    """The point of the mechanism. If a byte changes and the URL does not, a
    cached copy is still served and the deploy is invisible to returning
    readers."""
    first = tmp_path / "a"
    bs.build(first, preview=False)
    before = LOCAL_ASSET.findall((first / "index.html").read_text(encoding="utf-8"))
    before = {p: d for p, _, d in before}

    css = first / "css" / "site.css"
    css.write_text(css.read_text(encoding="utf-8") + "\n.probe { color: red; }\n",
                   encoding="utf-8", newline="\n")
    bs._record_asset_hashes(first)
    after = bs.asset("", "css/site.css")

    assert after != f"css/site.css?v={before['css/site.css']}", (
        "editing site.css left its URL unchanged, so no cache would refetch it")


def test_identical_content_produces_an_identical_url(tmp_path):
    """The CI freshness gate rebuilds and diffs, so the hash has to be a pure
    function of content. Anything time or path dependent would make every
    build dirty."""
    one, two = tmp_path / "one", tmp_path / "two"
    bs.build(one, preview=False)
    first = (one / "index.html").read_text(encoding="utf-8")
    bs.build(two, preview=False)
    second = (two / "index.html").read_text(encoding="utf-8")
    assert first == second, "two builds of the same content disagree"


def test_the_hash_ignores_line_endings(tmp_path):
    """Generated assets are written with newline="\\n", but site.css is copied
    from the source tree, so on Windows it carries CRLF while a CI checkout
    has LF. Hashing raw bytes made one stylesheet produce two URLs depending
    on the platform, and the freshness gate failed on CI while passing
    locally. The hash describes content, not line endings."""
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    css = out / "css" / "site.css"

    bs._record_asset_hashes(out)
    with_lf = bs.asset("", "css/site.css")

    crlf = css.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    css.write_bytes(crlf.encode("utf-8"))
    bs._record_asset_hashes(out)
    with_crlf = bs.asset("", "css/site.css")

    assert with_lf == with_crlf, (
        f"line endings alone changed the asset URL ({with_lf} vs {with_crlf}), "
        "so the same stylesheet versions differently on Windows and CI")


def test_cdn_assets_are_left_alone(tmp_path):
    """Appending a query to a CDN URL would change the request without
    changing the bytes, and subresource integrity already pins those."""
    out = tmp_path / "dep"
    bs.build(out, preview=False)
    index = (out / "index.html").read_text(encoding="utf-8")
    for url in re.findall(r'src="(https://[^"]+)"', index):
        assert "?v=" not in url, f"CDN asset was version-stamped: {url}"
