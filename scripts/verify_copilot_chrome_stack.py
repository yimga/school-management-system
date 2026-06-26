"""Platform-wide copilot chrome stack — tenant header gutter + z-index ladder.

Ensures tenant school surfaces (mission strip, pinned header) never paint over
the fixed AI copilot rail, while operator /super/ grid contract stays separate.

PASS exits 0 with COPILOT_CHROME_STACK_PASS; any breach exits 1.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []

    compact = _read("static/css/rmc-platform-vertical-compact.css")
    canvas = _read("static/css/rmc-tenant-workspace-canvas.css")
    portal = _read("templates/portal_base.html")
    mission = _read("templates/partials/tenant/tp_mission_strip.html")

    if "--rmc-copilot-rail-z:" not in compact:
        findings.append("rmc-platform-vertical-compact.css: missing --rmc-copilot-rail-z token")

    if "z-index: var(--rmc-copilot-rail-z" not in compact:
        findings.append(
            "rmc-platform-vertical-compact.css: copilot mount must use --rmc-copilot-rail-z"
        )

    if "z-index: 45" in compact:
        findings.append(
            "rmc-platform-vertical-compact.css: legacy copilot z-index 45 must be retired"
        )

    if "padding-inline-end: calc(var(--rmc-app-shell-copilot-w" not in canvas:
        findings.append(
            "rmc-tenant-workspace-canvas.css: tenant .tp-header missing copilot gutter"
        )

    idx = portal.find("tp_mission_strip.html")
    if idx < 0:
        findings.append("portal_base.html: missing tp_mission_strip include")
    else:
        window = portal[max(0, idx - 500) : idx]
        if "tp_v3_tenant_shell" not in window:
            findings.append(
                "portal_base.html: tp_mission_strip must be gated to tp_v3_tenant_shell (tenant only)"
            )
        if "public_host_kind == 'manager'" in window:
            findings.append(
                "portal_base.html: tp_mission_strip must not render on manager host"
            )

    if "TENANT SCHOOL SURFACE ONLY" not in mission:
        findings.append(
            "tp_mission_strip.html: missing tenant-only surface documentation"
        )

    if "control-plane-shell" in mission:
        findings.append("tp_mission_strip.html: must not reference control-plane shell")

    if findings:
        for f in findings:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("COPILOT_CHROME_STACK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
