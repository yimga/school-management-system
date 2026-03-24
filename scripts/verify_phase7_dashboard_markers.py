#!/usr/bin/env python3
"""
Gate: every registered full-page dashboard template must expose the Phase 7
decision surface contract (partial include, phase7_de context, or data attribute).

See docs/PHASE_7_DASHBOARD_AND_ROLE_HOME_REWRITE.md § Full dashboard registry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

# Full-page dashboards (exclude fragments under admin/components/, widgets/, etc.)
PHASE7_DASHBOARD_TEMPLATES = [
    "accounts/backend_dashboard.html",
    "accounts/rbac_dashboard.html",
    "admin/admin_dashboard.html",
    "analytics/at_risk_dashboard.html",
    "analytics/dashboard.html",
    "analytics/executive_dashboard.html",
    "apicenter/dashboard.html",
    "compliance/dashboard.html",
    "customersuccess/super_dashboard.html",
    "emis/dashboard.html",
    "evals/compliance_dashboard.html",
    "finance/dashboard.html",
    "marketplace/incident_dashboard.html",
    "observability/slo_dashboard.html",
    "parent/dashboard.html",
    "payroll/dashboard.html",
    "people/employer_dashboard.html",
    "requests/dashboard.html",
    "schools/billing_dashboard.html",
    "schools/marketing_funnel_dashboard.html",
    "schools/parent_tenant_dashboard.html",
    "schools/super_dashboard.html",
    "schools/super_dashboard_packs.html",
    "schools/super_support_dashboard.html",
    "siteconfig/dashboard_configuration_hub.html",
    "siteconfig/dashboard_hub.html",
    "student/learning_home.html",
    "studio_os/experience_dashboard_visual_packs.html",
    "teacher/dashboard.html",
]

_MARKER_RE = re.compile(
    r"(phase7_de|decision_engine_surface\.html|data-decision-engine\s*=)",
    re.MULTILINE,
)


def main() -> int:
    failures: list[str] = []
    for rel in sorted(PHASE7_DASHBOARD_TEMPLATES):
        path = TEMPLATES / rel
        if not path.is_file():
            failures.append(f"{rel}: file missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not _MARKER_RE.search(text):
            failures.append(
                f"{rel}: no Phase 7 marker "
                "(need phase7_de, decision_engine_surface.html include, or data-decision-engine=)"
            )
    if failures:
        print("FAIL Phase 7 dashboard marker audit:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"OK   Phase 7 dashboard markers ({len(PHASE7_DASHBOARD_TEMPLATES)} templates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
