#!/usr/bin/env python3
"""Gate: platform sidebar rail contract — no canvas void below short nav."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CSS = ROOT / "static/css/rmc-sidebar-rail-contract.css"
MCP_CSS = ROOT / "static/css/manager-control-plane.css"

SHELL_MARKERS = (
    ("templates/control_plane_skeleton.html", "rmc-sidebar-rail-contract.css"),
    ("templates/control_plane_base.html", "rmc-sidebar-rail-contract.css"),
    ("templates/portal_base.html", "rmc-sidebar-rail-contract.css"),
    ("templates/admin/base_site.html", "rmc-sidebar-rail-contract.css"),
)

CONTRACT_REQUIRED = (
    "align-self: stretch",
    ".cp-sidebar-inner",
    "min-height: 100%",
    "flex: 1 1 auto",
    ".portal-sidebar-col",
)

# Regression: document-scroll inner must not shrink to content only.
MCP_FORBIDDEN = re.compile(
    r"data-rmc-cp-scroll=\"document\"]\s*\.cp-sidebar-col\s*\.cp-sidebar-inner\s*\{[^}]*flex:\s*0\s+1\s+auto",
    re.DOTALL,
)
MCP_FORBIDDEN_MAXHEIGHT_TRAP = re.compile(
    r"#cp-sidebar-col\s*\{\s*max-height:\s*calc\(100vh",
    re.DOTALL,
)


def main() -> int:
    errors: list[str] = []

    if not CONTRACT_CSS.is_file():
        errors.append(f"missing {CONTRACT_CSS.relative_to(ROOT)}")
    else:
        text = CONTRACT_CSS.read_text(encoding="utf-8")
        for token in CONTRACT_REQUIRED:
            if token not in text:
                errors.append(f"contract missing required token: {token!r}")

    if MCP_CSS.is_file():
        mcp = MCP_CSS.read_text(encoding="utf-8")
        if MCP_FORBIDDEN.search(mcp):
            errors.append(
                "manager-control-plane.css regressed: document-scroll .cp-sidebar-inner uses flex: 0 1 auto"
            )
        if MCP_FORBIDDEN_MAXHEIGHT_TRAP.search(mcp):
            errors.append(
                "manager-control-plane.css regressed: #cp-sidebar-col max-height calc trap still present"
            )

    for rel, marker in SHELL_MARKERS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing shell template {rel}")
            continue
        body = path.read_text(encoding="utf-8")
        if marker not in body:
            errors.append(f"{rel} does not load {marker}")

    if errors:
        print("verify_sidebar_rail_contract: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("verify_sidebar_rail_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
