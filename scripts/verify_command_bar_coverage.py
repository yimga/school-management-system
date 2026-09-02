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
  - rmc-command-bar.css delivered
  - rmc-signature-motion.css delivered
  - <script ... rmc-command-bar.js> loaded WITHOUT defer/async
    (armed-attribute invariant -- flag must land before first paint)

"Delivered" is not "the filename appears in this file". templates/portal_base.html
links ONE minified sheet, css/portal-shell-enhanced.min.css, which concatenates 77
sources including both of these; the old substring test therefore reported
"missing stylesheet" for CSS the tenant shell has always shipped. Resolution now
runs through scripts/shell_css_contract.py, which accepts a bundle ONLY when the
shell links it, a hash manifest declares it, the stylesheet is one of its sources,
AND that source's sha256 still matches the file on disk -- a bundle built from an
older copy serves stale rules and is reported, never passed.

The include/script assertions run against REACHABLE template text: markup parked
behind {% if False %} or inside {% comment %} is not shipped, and a raw substring
test happily finds it there.

Stdlib-only. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import shell_css_contract  # noqa: E402

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
    rel = path.relative_to(REPO_ROOT).as_posix()
    text = shell_css_contract.reachable_text(rel)
    findings: list[str] = []

    if PARTIAL_TOKEN not in text:
        findings.append(
            f"{path.relative_to(REPO_ROOT)}: missing include of {PARTIAL_TOKEN}"
        )
    for css in (CSS_BAR_TOKEN, CSS_MOTION_TOKEN):
        finding = shell_css_contract.missing_stylesheet(rel, css)
        if finding:
            findings.append(finding)

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
        rel = s.relative_to(REPO_ROOT).as_posix()
        how = ", ".join(
            f"{css}={shell_css_contract.resolve(rel, css)[0]}"
            for css in (CSS_BAR_TOKEN, CSS_MOTION_TOKEN)
        )
        print(f"    {rel}  [{how}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
