#!/usr/bin/env python3
"""Platform-wide chromatic compliance — tables, list-groups, manager light bleed.

Extends marketplace proof-surface checks with platform floor rules that prevent
white-on-white across control-plane tables (incidents, AI Center, catalogs).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "platform_chromatic_compliance.json"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    checks: list[dict[str, str]] = []

    def record(cid: str, ok: bool, detail: str) -> None:
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})

    # Delegate marketplace slice (batch 1297)
    mp = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_marketplace_proof_surface_dark.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    record("marketplace_proof_surface", mp.returncode == 0, "verify_marketplace_proof_surface_dark.py")

    manager = _read("static/css/manager-aesthetic-polish.css")
    safety = _read("static/css/dark-mode-safety-net.css")
    contrast = _read("static/css/theme-platform-contrast.css")
    table_sys = _read("static/css/table-system.css")
    ai_body = _read("templates/siteconfig/partials/ai_center_body.html")
    incidents = _read("templates/observability/platform_incidents.html")

    record(
        "manager_cards_light_scoped",
        'html[data-resolved-theme="light"] #cp-main-content .card' in manager
        and 'html[data-resolved-theme="light"] #cp-main-content,' in manager,
        "manager-aesthetic light card surfaces scoped to resolved-light only",
    )
    record(
        "safety_net_table_tbody_floor",
        ".table tbody td" in safety and "Platform chromatic floor" in safety,
        "dark-mode-safety-net forces dark tbody cells on control plane",
    )
    record(
        "safety_net_list_group",
        ".list-group-item" in safety.split("Platform chromatic floor")[1],
        "dark-mode-safety-net covers list-group (AI Center assistants)",
    )
    record(
        "table_family_dark_tokens",
        'html[data-resolved-theme="dark"] .table-family tbody td' in table_sys,
        "table-system.css dark rules for .table-family",
    )
    record(
        "ai_center_no_bg_light",
        "bg-light" not in ai_body,
        "AI Center body dropped bg-light slabs",
    )
    record(
        "safety_net_bg_light_triple_theme",
        'html[data-theme="dark"] body:not(.marketing-surface) .bg-light' in safety
        and 'html[data-resolved-theme="dark"] body:not(.marketing-surface) .bg-light' in safety,
        "dark-mode-safety-net remaps .bg-light under all dark theme attributes",
    )
    record(
        "safety_net_text_bg_light",
        "body:not(.marketing-surface) .text-bg-light" in safety
        and "color: var(--text-primary) !important" in safety,
        "dark-mode-safety-net remaps Bootstrap text-bg-light badges",
    )
    record(
        "safety_net_pre_cardbody_bg_light",
        "pre.bg-light" in safety and "card-body.bg-light" in safety,
        "dark-mode-safety-net covers pre/card-body bg-light slabs",
    )
    record(
        "contrast_dark_table_tokens",
        'html[data-resolved-theme="dark"]' in contrast
        and "Tables: dark canvas" in contrast
        and "--bs-table-color: var(--text-primary)" in contrast.split("Tables: dark canvas")[1][:1200],
        "theme-platform-contrast dark table token block mirrors light",
    )
    record(
        "incidents_no_alert_light",
        "alert-light" not in incidents,
        "platform incidents console dropped alert-light",
    )

    failed = [c for c in checks if c["status"] == "FAIL"]
    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for c in checks:
        mark = "OK" if c["status"] == "PASS" else "FAIL"
        print(f"[{mark}] {c['id']}: {c['detail']}")

    if failed:
        print(f"\nPLATFORM_CHROMATIC_COMPLIANCE_FAIL ({len(failed)} checks)")
        return 1
    print("\nPLATFORM_CHROMATIC_COMPLIANCE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
