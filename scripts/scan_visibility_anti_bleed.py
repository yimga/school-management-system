#!/usr/bin/env python3
"""MAX Wave 4: visibility / anti-bleed contract for masthead + archetype CSS.

Locks:
  - chip wrap + overflow:visible on masthead
  - minmax(0, 1fr) (or min-width:0) on work grids
  - host chroma limited to chrome classes (not body text selectors)

Usage:
  python scripts/scan_visibility_anti_bleed.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "static/css/rmc-page-archetypes-max.css"
MASTHEAD = ROOT / "templates/components/rmc_page_masthead.html"


def main() -> int:
    failed: list[str] = []
    if not CSS.exists():
        failed.append(f"missing {CSS.relative_to(ROOT)}")
    else:
        css = CSS.read_text(encoding="utf-8", errors="ignore")
        if "overflow: visible" not in css and "overflow:visible" not in css:
            failed.append("rmc-page-archetypes-max.css: masthead must keep overflow:visible")
        if "flex-wrap: wrap" not in css and "flex-wrap:wrap" not in css:
            failed.append("rmc-page-archetypes-max.css: chips/actions must flex-wrap")
        if "min-width: 0" not in css and "min-width:0" not in css:
            failed.append("rmc-page-archetypes-max.css: need min-width:0 to prevent grid bleed")
        # Host chroma only on chrome classes
        bad_host = re.findall(
            r"(?:^|\n)\s*(?:body|main|\.rmc-app-shell)[^{]*\{[^}]*--rmc-host-(?:operator|tenant)",
            css,
        )
        if bad_host:
            failed.append("host chroma must not paint body/main shell text containers")
        if ".rmc-page-masthead--operator" not in css or ".rmc-page-masthead--tenant" not in css:
            failed.append("missing host-chroma masthead modifiers")
    if not MASTHEAD.exists():
        failed.append("missing rmc_page_masthead.html")
    else:
        mh = MASTHEAD.read_text(encoding="utf-8", errors="ignore")
        if "rmc-page-masthead__chips" not in mh:
            failed.append("masthead missing chips row (wrap contract)")
        if "truncate" not in mh:
            failed.append("masthead titles should truncate rather than overflow")
    if failed:
        print("FAIL visibility / anti-bleed:", file=sys.stderr)
        for f in failed:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("OK: visibility / anti-bleed contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
