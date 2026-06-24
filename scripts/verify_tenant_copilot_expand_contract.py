"""Verify tenant/manager-portal-bridge copilot expand panel visibility contract.

The fixed copilot mount lives OUTSIDE .rmc-app-shell on tenant portal pages.
Expanded panel visibility must key off body[data-copilot=expanded] (or the shell
mirror), not only .rmc-app-shell[data-copilot=expanded].

PASS exits 0 with TENANT_COPILOT_EXPAND_PASS; any breach exits 1.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []

    css = _read("static/css/rmc-cp-200x.css")
    compact = _read("static/css/rmc-platform-vertical-compact.css")
    portal = _read("templates/portal_base.html")
    js = _read("static/js/_pages/rmc-copilot-rail.js")

    for needle in (
        "body[data-copilot=\"expanded\"] .rmc-tenant-portal-copilot-mount .lx-copilot__expanded",
        "body[data-copilot=\"expanded\"] .rmc-manager-portal-copilot-mount .lx-copilot__expanded",
        ".rmc-tenant-portal-copilot-mount .lx-copilot__collapsed",
    ):
        if needle not in css:
            findings.append(f"rmc-cp-200x.css: missing '{needle}'")

    if "data-rmc-copilot-mount" not in portal:
        findings.append("portal_base.html: missing data-rmc-copilot-mount wrapper")

    if "data-rmc-tenant-copilot-rail" not in portal:
        findings.append("portal_base.html: missing data-rmc-tenant-copilot-rail body attr")

    if "body[data-rmc-tenant-copilot-rail=\"1\"][data-copilot=\"expanded\"]" not in compact:
        findings.append("rmc-platform-vertical-compact.css: missing tenant expand width rule")

    if "data-rmc-copilot-mount" not in js:
        findings.append("rmc-copilot-rail.js: findShell must detect floating copilot mount")

    rail = _read("templates/partials/cockpit/_ai_copilot_rail.html")
    lens = _read("templates/partials/copilot_lens_root_inner.html")
    bridge_js = _read("static/js/rmc-copilot-rail.js")

    for needle in (
        "data-rmc-copilot-rail-actions-empty",
        "data-rmc-copilot-rail-actions-empty-msg",
    ):
        if needle not in rail:
            findings.append(f"_ai_copilot_rail.html: missing '{needle}'")

    if "data-rmc-copilot-lens-bridge-error" not in lens:
        findings.append("copilot_lens_root_inner.html: missing lens bridge error state")

    for needle in ("setActionsBridgeError", "markLensBridgeUnavailable"):
        if needle not in bridge_js:
            findings.append(f"rmc-copilot-rail.js: missing '{needle}'")

    if findings:
        for f in findings:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("TENANT_COPILOT_EXPAND_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
