"""Verify control-plane copilot rail grid placement contract.

The manager copilot rail must live in .rmc-app-shell grid row 2 / column 3 as a
narrow right strip — never as a full-width bottom band from grid auto-placement.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

REQUIRED_CSS_SNIPPETS = (
    (
        REPO_ROOT / "static" / "css" / "rmc-cp-200x.css",
        (
            '[data-rmc-shell-main="control-plane"] .rmc-app-shell__copilot',
            "grid-column: 3",
            "max-width: var(--rmc-app-shell-copilot-w, 44px)",
        ),
    ),
    (
        REPO_ROOT / "static" / "css" / "rmc-isomorphic-grid.css",
        (
            '[data-rmc-isomorphic-template="operator-control-plane"] .rmc-app-shell__copilot',
            "grid-row: 2",
            "grid-column: 3",
        ),
    ),
)

REQUIRED_TEMPLATE_ORDER = (
    REPO_ROOT / "templates" / "control_plane_skeleton.html",
    "_ai_copilot_rail.html",
    "_pulse_drill_sheet.html",
)


def main() -> int:
    findings: list[str] = []

    for path, snippets in REQUIRED_CSS_SNIPPETS:
        text = path.read_text(encoding="utf-8", errors="replace")
        for snippet in snippets:
            if snippet not in text:
                findings.append(f"{path.relative_to(REPO_ROOT)}: missing '{snippet}'")

    skeleton = REQUIRED_TEMPLATE_ORDER[0].read_text(encoding="utf-8", errors="replace")
    copilot_idx = skeleton.find(REQUIRED_TEMPLATE_ORDER[1])
    pulse_idx = skeleton.find(REQUIRED_TEMPLATE_ORDER[2])
    if copilot_idx < 0:
        findings.append("control_plane_skeleton.html: missing _ai_copilot_rail include")
    if pulse_idx < 0:
        findings.append("control_plane_skeleton.html: missing _pulse_drill_sheet include")
    if copilot_idx >= 0 and pulse_idx >= 0 and copilot_idx > pulse_idx:
        findings.append(
            "control_plane_skeleton.html: copilot rail must precede pulse drill sheet in DOM"
        )

    if findings:
        for item in findings:
            print(f"FAIL: {item}")
        return 1

    print("PASS: control-plane copilot grid contract clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
