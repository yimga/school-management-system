#!/usr/bin/env python3
"""Platform-wide back-to-top wiring gate (batch 1500)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHELLS = (
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/base.html",
    "templates/marketing/base_marketing.html",
    "templates/admin/base.html",
)


def main() -> int:
    failures: list[str] = []
    for rel in SHELLS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing shell: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "back_to_top.html" not in text:
            failures.append(f"no back-to-top: {rel}")

    fold_css = ROOT / "templates/partials/rmc_platform_chrome_styles.html"
    if fold_css.is_file():
        if "rmc-page-fold-standards.css" not in fold_css.read_text(encoding="utf-8"):
            failures.append("rmc-page-fold-standards.css not in platform chrome styles")
    else:
        failures.append("missing rmc_platform_chrome_styles.html")

    js = ROOT / "static/js/_pages/components__back_to_top.js"
    if not js.is_file() or "data-rmc-mounted" not in js.read_text(encoding="utf-8"):
        failures.append("back-to-top JS missing idempotent mount guard")

    if failures:
        print("verify_platform_back_to_top: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_platform_back_to_top: PLATFORM_BACK_TO_TOP_PASS ({len(SHELLS)} shells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
