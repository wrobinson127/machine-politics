"""Generate data/derived/iso_numeric_alpha3.json from pycountry.

world-atlas country features carry ISO 3166-1 numeric ids; the site's
content layer keys on alpha-3. This table bridges them. It is generated
once and committed so the site build stays deterministic and free of a
pycountry runtime dependency. Rerun this tool only when ISO 3166 itself
changes.

Special case: Kosovo has no ISO 3166 code and no numeric id in the
world-atlas data; the build maps it by feature name to the user-assigned
code XKX (the same convention the endorsement records use).
"""

import json
import sys
from pathlib import Path

import pycountry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import config

OUT = config.DATA_DERIVED_DIR / "iso_numeric_alpha3.json"


def main():
    table = {c.numeric: c.alpha_3 for c in pycountry.countries}
    OUT.write_text(
        json.dumps(table, indent=0, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"wrote {OUT} ({len(table)} entries)")


if __name__ == "__main__":
    main()
