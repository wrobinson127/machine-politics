"""Verify every pinned subresource-integrity hash against what the CDN serves.

This exists because a wrong SRI hash is invisible to every other gate. The
build succeeds, the validator passes, and the test suite passes, because the
tests compare build_site's pinned constant against build_site's own output:
self-referential, and true regardless of whether the hash is correct. The
browser is the only thing that checks, and when it fails it fails silently.
It refuses to execute the script, logs nothing the page can see, and the site
degrades to its no-JS fallback while looking deliberate.

That is exactly what happened. Four of five pinned hashes were wrong, so the
home-page tour never ran and the instruments map never loaded, on a build
whose gates were all green.

Usage:  python tools/check_sri.py
Exit:   0 if every hash matches, 1 otherwise. Requires network.
"""
import base64
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

TAG = re.compile(
    r'(?:src|href)="(https://[^"]+)"\s+integrity="([^"]+)"'
)


def pinned_hashes(site=SITE):
    """Every (url, integrity) pair in the built site, deduplicated."""
    found = {}
    for page in sorted(site.glob("*.html")):
        for url, integrity in TAG.findall(page.read_text(encoding="utf-8")):
            found.setdefault(url, integrity)
    return found


def actual_hash(url, timeout=30):
    body = urllib.request.urlopen(url, timeout=timeout).read()
    return "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode()


def main():
    found = pinned_hashes()
    if not found:
        print("no pinned subresources found; nothing to check")
        return 0
    bad = []
    for url, pinned in found.items():
        name = url.rsplit("/", 1)[-1]
        try:
            actual = actual_hash(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  UNREACHABLE {name}: {exc}")
            bad.append((url, pinned, f"unreachable: {exc}"))
            continue
        if actual == pinned:
            print(f"  OK       {name}")
        else:
            print(f"  MISMATCH {name}")
            bad.append((url, pinned, actual))
    print()
    if bad:
        print(f"{len(bad)} pinned hash(es) do not match what the CDN serves:")
        for url, pinned, actual in bad:
            print(f"  {url}\n    pinned: {pinned}\n    actual: {actual}")
        return 1
    print(f"all {len(found)} pinned hashes match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
