#!/usr/bin/env python3
"""High-risk /super/ views must declare @require_platform_scope."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "super_platform_scope_coverage.json"

# view function name -> module path (under apps/schools/)
HIGH_RISK_VIEWS: dict[str, str] = {
    "super_usage": "super_views_platform_monitoring.py",
    "super_pulse": "super_views_platform_monitoring.py",
    "super_tenant_health": "super_views_platform_monitoring.py",
    "super_tenant_360": "super_views_platform_monitoring.py",
    "super_control_health_dashboard": "super_views_platform_monitoring.py",
    "super_runtime_inspector": "super_views_runtime_ops.py",
    "super_runtime_truth_hub": "super_views_runtime_ops.py",
    "super_workflow_simulator": "super_views_runtime_ops.py",
    "super_playbook_operator_hub": "super_views_runtime_ops.py",
    "super_policy_diff": "super_views_policy.py",
    "super_apply_policy_bundle_to_sandbox": "super_views_policy.py",
    "super_incidents_list": "super_views_config.py",
    "super_fleet_governed_changes": "super_views_config.py",
    "super_billing_accounts_list": "super_views_config.py",
    "super_migration_runs_list": "super_views_config.py",
    "super_migration_cloud": "super_views_migration.py",
    "super_migration_profile_registry": "super_views_migration.py",
    "super_migration_rollback": "super_views_migration.py",
    "super_migration_exception_ack": "super_views_migration.py",
    "super_migration_quarantine_waive": "super_views_migration.py",
    "super_offboarding_queue": "super_views_offboarding_queue.py",
    "super_compliance_overview": "super_views_trust_surface.py",
    "super_trust_center": "super_views_trust_surface.py",
    "super_audit_export": "super_views_trust_surface.py",
    "super_platform_events": "super_views_trust_surface.py",
    "super_schools_list": "super_views_overview_surfaces.py",
    "super_analytics_overview": "super_views_overview_surfaces.py",
    "super_governed_data_query": "super_views_beyond_reach.py",
    "super_migration_csv_diff": "super_views_beyond_reach.py",
    "super_legacy_sis_csv_preview": "super_views_beyond_reach.py",
    "super_support_tickets_export_csv": "super_views_support.py",
    "super_security_hub": "super_views_enterprise_security.py",
    "super_security_surface_dashboard": "super_views_security_surface.py",
}


@dataclass
class Row:
    view: str
    module: str
    ok: bool
    proof: str


def _module_text(rel: str) -> str:
    return (ROOT / "apps" / "schools" / rel).read_text(encoding="utf-8", errors="replace")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _view_has_scope_decorator(src: str, view_name: str) -> bool:
    pattern = re.compile(
        rf"@require_platform_scope\([^)]+\)\s*\n(?:@\w+\([^)]*\)\s*\n)*def {re.escape(view_name)}\(",
        re.MULTILINE,
    )
    if pattern.search(src):
        return True
    pattern2 = re.compile(
        rf"def {re.escape(view_name)}\(",
    )
    m = pattern2.search(src)
    if not m:
        return False
    prefix = src[max(0, m.start() - 400) : m.start()]
    return "@require_platform_scope(" in prefix


def main() -> int:
    rows: list[Row] = []
    for view, module in sorted(HIGH_RISK_VIEWS.items()):
        path = ROOT / "apps" / "schools" / module
        if not path.is_file():
            rows.append(Row(view, module, False, "module missing"))
            continue
        src = _module_text(module)
        ok = _view_has_scope_decorator(src, view)
        rows.append(
            Row(
                view,
                module,
                ok,
                "decorated" if ok else "missing @require_platform_scope",
            )
        )

    migration_ok = (
        ROOT / "apps/accounts/migrations/0038_accessrole_school_scope.py"
    ).is_file()
    access_helpers_ok = "roles_queryset_for_school" in (
        ROOT / "apps/accounts/access_roles.py"
    ).read_text(encoding="utf-8")
    rbac_src = _read("apps/accounts/views.py")
    rbac_edit_scoped = (
        "roles_queryset_for_school(school).prefetch_related" in rbac_src
        and "edit_role" in rbac_src
    )

    finding_count = sum(1 for r in rows if not r.ok)
    if not migration_ok:
        finding_count += 1
    if not access_helpers_ok:
        finding_count += 1
    if not rbac_edit_scoped:
        finding_count += 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": finding_count,
        "migration_0038": migration_ok,
        "access_roles_helpers": access_helpers_ok,
        "rbac_edit_role_school_scoped": rbac_edit_scoped,
        "rows": [
            {"view": r.view, "module": r.module, "ok": r.ok, "proof": r.proof}
            for r in rows
        ],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if finding_count:
        print("SUPER_PLATFORM_SCOPE_COVERAGE_FAIL")
        for r in rows:
            if not r.ok:
                print(f"  {r.view} ({r.module}): {r.proof}")
        if not migration_ok:
            print("  missing 0038_accessrole_school_scope migration")
        if not access_helpers_ok:
            print("  missing access_roles.py helpers")
        if not rbac_edit_scoped:
            print("  rbac_dashboard edit_role GET not school-scoped")
        return 1
    print("SUPER_PLATFORM_SCOPE_COVERAGE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
