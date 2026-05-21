#!/usr/bin/env python
"""Studio OS Mission Cockpit shell contract (v3.53.0, 2026-05-21).

Verifies:
  1. templates/studio_os/shell.html includes all three cockpit
     partials (signal strip / canvas / co-pilot rail).
  2. shell.html instantiates the `.rmc-cockpit` grid class.
  3. shell.html loads studio-os-cockpit.css.
  4. Each cockpit partial uses the expected `.rmc-cockpit__*` BEM
     hook so the CSS in studio-os-cockpit.css actually applies.

Stdlib-only. Exits 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SHELL = REPO_ROOT / "templates" / "studio_os" / "shell.html"
PARTIALS = REPO_ROOT / "templates" / "studio_os" / "partials"

REQUIRED_INCLUDES = (
    "studio_os/partials/cockpit_signal_strip.html",
    "studio_os/partials/cockpit_canvas.html",
    "studio_os/partials/cockpit_copilot_rail.html",
)
REQUIRED_CLASSES = ("rmc-cockpit",)
REQUIRED_STYLESHEET = "studio-os-cockpit.css"

PARTIAL_EXPECTATIONS = {
    "cockpit_signal_strip.html": "rmc-cockpit__signal",
    "cockpit_canvas.html": "rmc-cockpit__canvas",
    "cockpit_copilot_rail.html": "rmc-cockpit__rail",
}


def main() -> int:
    failures: list[str] = []

    if not SHELL.exists():
        print(f"FAIL: shell template missing: {SHELL.relative_to(REPO_ROOT)}")
        return 1

    shell_text = SHELL.read_text(encoding="utf-8")

    for inc in REQUIRED_INCLUDES:
        if inc not in shell_text:
            failures.append(f"shell.html missing include of {inc}")

    for cls in REQUIRED_CLASSES:
        if cls not in shell_text:
            failures.append(f"shell.html missing class '{cls}'")

    if REQUIRED_STYLESHEET not in shell_text:
        failures.append(
            f"shell.html missing <link> to {REQUIRED_STYLESHEET}"
        )

    for partial_name, expected_class in PARTIAL_EXPECTATIONS.items():
        path = PARTIALS / partial_name
        if not path.exists():
            failures.append(f"partial missing: {path.relative_to(REPO_ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        if expected_class not in text:
            failures.append(
                f"{partial_name} missing CSS hook '{expected_class}'"
            )

    if failures:
        print(f"FAIL: studio_os cockpit contract — {len(failures)} violation(s)")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: studio_os cockpit contract clean")
    print(f"  shell.html: {SHELL.relative_to(REPO_ROOT)}")
    print(f"  partials: {len(REQUIRED_INCLUDES)} verified")
    print(f"  stylesheet: {REQUIRED_STYLESHEET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
