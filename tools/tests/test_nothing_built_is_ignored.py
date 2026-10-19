"""Every file the deploy build writes must be committable. Pages publishes
the committed site/, so a built file that .gitignore swallows is linked
from the live site and 404s there, while CI's freshness check, which only
sees tracked and untracked-but-unignored files, stays green. This happened
once: the *.csv rule swallowed site/data/positions.csv (gauntlet, 2026-10-19)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import config
from tools import build_site as bs


def test_no_built_file_is_gitignored(tmp_path):
    out = tmp_path / "site"
    bs.build(out, preview=False)
    rels = ["site/" + p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()]
    assert "site/data/positions.csv" in rels
    # Bytes, not text: on Windows, text-mode stdin turns each newline into
    # CRLF, git then matches no path at all, and the test passes vacuously.
    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input=("\n".join(rels) + "\n").encode("utf-8"),
        capture_output=True,
        cwd=config.REPO_ROOT,
    )
    assert proc.returncode in (0, 1), proc.stderr
    ignored = [line for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]
    assert ignored == [], f"built files that .gitignore would drop: {ignored}"
