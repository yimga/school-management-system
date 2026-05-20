#!/usr/bin/env python3
"""
Stage 8 workspace cockpit browser QA ledger — role homes + manager surfaces.

Aggregates static route contracts and the latest apple_class_authenticated_browser_report
when present. Does not require a live server for PASS on structural checks.

Writes docs/generated/workspace_cockpit_browser_qa.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "workspace_cockpit_browser_qa.json"
APPLE_REPORT = ROOT / "docs" / "generated" / "apple_class_authenticated_browser_report.json"

COCKPIT_ROUTES = [
    {"role": "operator", "surface": "manager", "path": "/super/", "primary_action": "Setup Studio", "next_action": "Configuration center"},
    {"role": "operator", "surface": "manager", "path": "/super/configuration/", "primary_action": "Open domains", "next_action": "Studio OS"},
    {"role": "admin", "surface": "tenant", "path": "/authentication/backend/", "primary_action": "Today", "next_action": "Needs attention"},
    {"role": "teacher", "surface": "tenant", "path": "/teacher/dashboard/", "primary_action": "Marks", "next_action": "Attendance"},
    {"role": "parent", "surface": "tenant", "path": "/parent/dashboard/", "primary_action": "Children", "next_action": "Messages"},
    {"role": "student", "surface": "tenant", "path": "/student360/", "primary_action": "Profile", "next_action": "Schedule"},
    {"role": "studio", "surface": "manager", "path": "/super/studio/", "primary_action": "Launch", "next_action": "Control"},
    {"role": "feedback", "surface": "tenant", "path": "/feedback/", "primary_action": "Submit", "next_action": "Roadmap"},
    {"role": "analytics", "surface": "tenant", "path": "/analytics/", "primary_action": "View report", "next_action": "Export"},
]


def _template_markers() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    mapping = {
        "operator": "templates/schools/super_dashboard.html",
        "admin": "templates/accounts/backend_dashboard.html",
        "teacher": "templates/teacher/dashboard.html",
        "parent": "templates/parent/dashboard.html",
        "student": "templates/student360/student_360_page.html",
        "studio": "templates/studio_os/shell.html",
    }
    for role, rel in mapping.items():
        path = ROOT / rel
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        rows.append(
            {
                "role": role,
                "template": rel,
                "exists": path.is_file(),
                "has_page_header": any(m in text for m in ("data-page-header", "<h1", "page_header.html")),
                "has_action_bar": any(m in text for m in ("ds-action-bar", "action-bar", "page_families/action_bar.html")),
                "has_zero_click": "data-rmc-zero-click" in text or "rmc_zero_click_command_strip" in text,
            }
        )
    return rows


def main() -> int:
    apple: dict[str, object] | None = None
    if APPLE_REPORT.is_file():
        apple = json.loads(APPLE_REPORT.read_text(encoding="utf-8"))

    template_rows = _template_markers()
    template_fail = [
        r for r in template_rows
        if not r.get("has_page_header") or not r.get("has_action_bar")
    ]

    payload: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "cockpit_routes": COCKPIT_ROUTES,
        "template_contracts": template_rows,
        "template_contract_failures": len(template_fail),
        "apple_class_report_ref": str(APPLE_REPORT.relative_to(ROOT)).replace("\\", "/"),
        "apple_class_verdict": (apple or {}).get("verdict"),
        "apple_class_generated_at": (apple or {}).get("generated_at"),
        "verdict": "WORKSPACE_COCKPIT_QA_READY"
        if not template_fail
        else "WORKSPACE_COCKPIT_QA_PARTIAL",
    }

    if apple:
        routes = apple.get("routes") if isinstance(apple.get("routes"), list) else []
        manager_ok = sum(
            1
            for r in routes
            if isinstance(r, dict)
            and r.get("surface") == "platform"
            and r.get("status") == 200
        )
        payload["apple_class_manager_routes_200"] = manager_ok

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} — {payload['verdict']}")
    return 1 if template_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
