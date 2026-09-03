#!/usr/bin/env python3
"""Gate: the portal shell CSS bundle must match its source manifest.

Sibling of ``verify_marketing_css_bundles_fresh.py``. The marketing bundles have
had a freshness gate wired into ``marketing-gates.yml`` for months; the portal
bundle -- which every authenticated tenant page loads -- had none, and drifted.

Measured 2026-09-02 before this gate existed: ``portal-shell-enhanced.min.css``
was built 2026-08-08 and **12 of its 77 sources had changed since**, so the
tenant shell was serving those rules in their pre-08-08 form. Two of the twelve
were already edited BEFORE the manifest commit itself, so that build shipped
stale on the day it landed -- which is exactly the failure a freshness gate
exists to make impossible to repeat.

``build_portal_css_bundles.py --check`` already knew: it compares each source's
sha256 against the manifest and exits 1 on any drift. Nothing ran it. This is
the wiring, not new logic -- deliberately a thin delegation so there is only one
implementation of "is the bundle fresh" and it is the builder's own.

Exit codes::

    0 -- bundle matches every source
    1 -- at least one source has drifted; run `python scripts/build_portal_css_bundles.py`
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "scripts" / "build_portal_css_bundles.py"


def main() -> int:
    if not BUILD.is_file():
        # A missing builder is a fault, not a pass: without it nothing can
        # establish freshness, and reporting 0 here would be the exact
        # "green means nothing" shape this gate exists to remove.
        print(
            "PORTAL_CSS_BUNDLES_FRESH_FAIL: builder missing at %s"
            % BUILD.relative_to(REPO),
            file=sys.stderr,
        )
        return 1
    proc = subprocess.run([sys.executable, str(BUILD), "--check"], cwd=REPO)
    if proc.returncode == 0:
        print("PORTAL_CSS_BUNDLES_FRESH_PASS")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
