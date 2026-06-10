"""Verify control-plane copilot rail grid placement contract.

The manager copilot rail must live in .rmc-app-shell grid row 2 / column 3 as a
narrow right strip — never as a full-width bottom band from grid auto-placement.

Surface families (single mount per family):
  A) control_plane_skeleton.html — ALL manager /super/*, /help-center/*, and
     siteconfig operator pages extending control_plane_base.html. Copilot is
     included once in the skeleton; page templates only fill cp_content.
  B) templates/admin/base.html (manager host) — Django admin unified shell;
     grid pin in rmc-platform-vertical-compact.css + rmc-app-shell.css.
  C) templates/portal_base.html (manager-portal-bridge) — legacy Bootstrap
     bridge uses fixed .rmc-manager-portal-copilot-mount (intentional alternate).

/super/ was not a separate copilot implementation — only super_dashboard.html
adds extra extrastyle (manager-control-plane.css). The grid-lock sheet loads
after every extrastyle block so landing and help-center share the same pin.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

REQUIRED_CSS_SNIPPETS = (
    (
        REPO_ROOT / "static" / "css" / "rmc-app-shell.css",
        (
            '.rmc-app-shell[data-rmc-app-shell-copilot="1"]',
            "grid-template-columns:",
            'grid-column: 3',
        ),
    ),
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

REQUIRED_TEMPLATE_MARKERS = (
    (REPO_ROOT / "templates" / "control_plane_skeleton.html", 'data-rmc-app-shell-copilot="1"'),
    (REPO_ROOT / "templates" / "control_plane_skeleton.html", "rmc-isomorphic-grid.css"),
    (REPO_ROOT / "templates" / "control_plane_skeleton.html", "rmc-cp-copilot-grid-lock.css"),
)

REQUIRED_GRID_AREA_SNIPPETS = (
    (REPO_ROOT / "static" / "css" / "rmc-app-shell.css", "grid-template-areas:", "rmc-shell-cp"),
    (REPO_ROOT / "static" / "css" / "rmc-cp-copilot-grid-lock.css", "grid-area: rmc-shell-cp", "rmc-shell-cp"),
)


def main() -> int:
    findings: list[str] = []

    for path, snippets in REQUIRED_CSS_SNIPPETS:
        text = path.read_text(encoding="utf-8", errors="replace")
        for snippet in snippets:
            if snippet not in text:
                findings.append(f"{path.relative_to(REPO_ROOT)}: missing '{snippet}'")

    for path, marker in REQUIRED_TEMPLATE_MARKERS:
        text = path.read_text(encoding="utf-8", errors="replace")
        if marker not in text:
            findings.append(f"{path.relative_to(REPO_ROOT)}: missing '{marker}'")

    for path, *snippets in REQUIRED_GRID_AREA_SNIPPETS:
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
