#!/usr/bin/env python
"""Universal Command Bar shell coverage (v3.53.0, 2026-05-21).

Verifies the command bar partial + JS + CSS are wired into all 4
dashboard shells:

  * templates/base.html
  * templates/portal_base.html
  * templates/control_plane_skeleton.html
  * templates/admin/base_site.html

For each shell the gate asserts:
  - {% include "partials/rmc_command_bar.html" %} present
  - <link rel=stylesheet ... rmc-command-bar.css> loaded
  - <link rel=stylesheet ... rmc-signature-motion.css> loaded
  - <script ... rmc-command-bar.js> loaded WITHOUT defer/async
    (armed-attribute invariant — flag must land before first paint)

Stdlib-only. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SHELLS = (
    REPO_ROOT / "templates" / "base.html",
    REPO_ROOT / "templates" / "portal_base.html",
    REPO_ROOT / "templates" / "control_plane_skeleton.html",
    REPO_ROOT / "templates" / "admin" / "base_site.html",
)

PARTIAL_TOKEN = 'partials/rmc_command_bar.html'
CSS_BAR_TOKEN = 'rmc-command-bar.css'
CSS_MOTION_TOKEN = 'rmc-signature-motion.css'
JS_TOKEN = 'rmc-command-bar.js'

_SCRIPT_RE = re.compile(
    r"<script[^>]*src=\"[^\"]*" + re.escape(JS_TOKEN) + r"[^\"]*\"[^>]*>"
)


def _check_shell(path: Path) -> list[str]:
    if not path.exists():
        return [f"{path.relative_to(REPO_ROOT)}: shell template missing"]
    text = path.read_text(encoding="utf-8")
    findings: list[str] = []

    if PARTIAL_TOKEN not in text:
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing include of {PARTIAL_TOKEN}"
        )
    if CSS_BAR_TOKEN not in text:
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing stylesheet {CSS_BAR_TOKEN}"
        )
    if CSS_MOTION_TOKEN not in text:
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing stylesheet {CSS_MOTION_TOKEN}"
        )

    script_tags = _SCRIPT_RE.findall(text)
    if not script_tags:
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing <script src=...{JS_TOKEN}>"
        )
    else:
        for tag in script_tags:
            if " defer" in tag or " async" in tag:
                findings.append(
                    f"{path.relative_to(REPO_ROOT)}: {JS_TOKEN} must load "
                    f"synchronously (no defer/async) per armed-attribute invariant"
                )

    return findings


def main() -> int:
    all_findings: list[str] = []
    for shell in SHELLS:
        all_findings.extend(_check_shell(shell))

    if all_findings:
        print(f"FAIL: command-bar shell coverage — {len(all_findings)} violation(s)")
        for f in all_findings:
            print(f"  - {f}")
        return 1

    print("PASS: command-bar shell coverage clean")
    print(f"  shells wired: {len(SHELLS)}")
    for s in SHELLS:
        print(f"    {s.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
