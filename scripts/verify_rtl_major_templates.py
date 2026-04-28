#!/usr/bin/env python3
"""
Major shell templates — RTL / direction hygiene (heuristic).

Checks that canonical base templates either:
- set ``<html ... dir=...>`` or body ``dir`` for locale switching, OR
- include a ``data-rmc-text-direction`` hook for future RTL packs.

Exits 0 when all listed templates pass. This is a **readiness** signal, not a full
visual RTL proof (that requires browser + locale fixtures).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Shell roots that own ``<html>`` (child templates extend these for ``dir=`` / locale).
TEMPLATES = [
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
]

NEED = re.compile(
    r"(\bdir\s*=\s*[\"'][^\"']*[\"'])|"
    r"(data-rmc-text-direction)|"
    r"(data-logical|logical-properties|dir--auto)",
    re.IGNORECASE,
)


def main() -> int:
    failed: list[str] = []
    for rel in TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            failed.append(f"missing file: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if NEED.search(text):
            continue
        failed.append(
            f"{rel}: no dir= / data-rmc-text-direction / logical hook (add explicit direction contract)"
        )
    if failed:
        print("verify_rtl_major_templates: FAIL", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("verify_rtl_major_templates: PASS (bases include direction hooks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
