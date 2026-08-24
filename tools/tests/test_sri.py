"""The pinned CDN hashes must match the bytes the CDN actually serves.

The existing animation-stack tests assert that the script tag carries
bs.GSAP_SCRIPTS' hash, which compares build_site's constant against
build_site's own output and passes whatever the constant says. This test
compares against the CDN instead, which is the only comparison that can fail
when a hash is wrong.
"""
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import build_site as bs
from tools import check_sri


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("sri_site")
    bs.build(out, preview=True)  # preview carries the full animation stack
    return out


def test_pinned_hashes_match_the_cdn(built):
    found = check_sri.pinned_hashes(built)
    assert found, "expected pinned subresources in the preview build"
    mismatches = []
    for url, pinned in found.items():
        try:
            actual = check_sri.actual_hash(url, timeout=30)
        except (urllib.error.URLError, OSError) as exc:
            pytest.skip(f"CDN unreachable, cannot verify SRI: {exc}")
        if actual != pinned:
            mismatches.append(f"{url}\n  pinned: {pinned}\n  actual: {actual}")
    assert not mismatches, (
        "pinned SRI hashes do not match what the CDN serves, so the browser "
        "will silently refuse to run these:\n" + "\n".join(mismatches)
    )
