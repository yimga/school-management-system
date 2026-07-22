"""Seal tenant chrome finish without spoiling working contracts.

PASS exits 0 with TENANT_CHROME_FINISH_PASS.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []

    portal = _read("templates/portal_base.html")
    finish = _read("static/css/rmc-tenant-chrome-finish.css")
    sw = _read("static/js/service-worker.js")
    cockpit = _read("apps/siteconfig/cockpit_context.py")

    if "rmc-tenant-chrome-finish.css" not in portal:
        findings.append("portal_base.html must load rmc-tenant-chrome-finish.css")

    for needle in (
        "display: flex !important",
        "flex: 1 1 auto !important",
        "margin-right: auto !important",
        "width: 360px !important",
        'data-rmc-copilot-shell="expanded"',
        "table.table.table-sm.rmc-data-table[data-density=\"compact\"]",
        "tp-v3-shell-footer",
    ):
        if needle not in finish:
            findings.append(f"rmc-tenant-chrome-finish.css missing: {needle}")

    if "grid-template-columns: auto auto minmax(0, 1fr)" in finish:
        findings.append(
            "rmc-tenant-chrome-finish.css must use flex header (grid stacks Home link)"
        )

    # Must NOT force dark footer via backend palette class (spoils light themes).
    if "body.portal-backend-dark .rmc-civic-footer" in finish:
        findings.append(
            "rmc-tenant-chrome-finish.css must not force dark footer on portal-backend-dark"
        )

    # Source header must not reintroduce nav-growth grid (cramped center).
    header = _read("static/css/rmc-tenant-header-100x.css")
    if "grid-template-columns: auto minmax(0, 1fr) auto" in header:
        findings.append(
            "rmc-tenant-header-100x.css must not grow the NAV column (use flex + actions growth)"
        )
    if "margin-right: auto !important" not in header:
        findings.append(
            "rmc-tenant-header-100x.css must stretch search with margin-right: auto"
        )

    # Density prefs must update <html>, not only the sidebar root.
    sidebar_js = _read("static/js/rmc-sidebar-intelligence.js")
    if "document.documentElement.setAttribute(\"data-rmc-density\"" not in sidebar_js:
        findings.append(
            "rmc-sidebar-intelligence.js must set html[data-rmc-density] for Compact/Cozy/Roomy"
        )

    # Copilot expanded width sealed at source (not only finish overlay).
    compact = _read("static/css/rmc-platform-vertical-compact.css")
    if "width: 360px !important" not in compact:
        findings.append(
            "rmc-platform-vertical-compact.css must force 360px when copilot is expanded"
        )

    if "sms-v4.06.13-tenant-chrome-rootfix-2026-07-22" not in sw:
        findings.append("service-worker CACHE_VERSION must bump for chrome rootfix")

    # Keep onboarding auto-expand (preview parity); width seal prevents crush.
    resolve_fn = cockpit.split("def _resolve_tenant_copilot_default_state")[1][:1200]
    if "pct < 70" not in resolve_fn or 'return "expanded"' not in resolve_fn:
        findings.append(
            "_resolve_tenant_copilot_default_state must keep onboarding <70% → expanded"
        )

    if findings:
        for f in findings:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("TENANT_CHROME_FINISH_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
