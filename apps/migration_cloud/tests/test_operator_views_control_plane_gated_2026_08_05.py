"""Must-fire seal: Migration Cloud operator views are control-plane gated (2026-08-05).

These cross-tenant operator surfaces (token/webhook/audit/health/DSAR/… admin)
were gated by ``staff_member_required`` and mounted on BOTH the manager
(``migration_cloud_super``) and tenant (``migration_cloud_portal``) namespaces —
so an ``is_staff`` tenant admin could reach cross-tenant operator tooling from
their own subdomain (``scan_staff_gate_on_tenant_surface`` flagged 30 sites).
This asserts every one now gates on ``require_control_plane_access`` and no longer
references ``staff_member_required`` in a decorator. Fails against the pre-fix code.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

_FILES = [
    "apps/migration_cloud/views_webhook_admin.py",
    "apps/migration_cloud/views_token_admin.py",
    "apps/migration_cloud/views_audit_admin.py",
    "apps/migration_cloud/views_command_center.py",
    "apps/migration_cloud/views_cutover.py",
    "apps/migration_cloud/views_dlq_admin.py",
    "apps/migration_cloud/views_dsar_admin.py",
    "apps/migration_cloud/views_health.py",
    "apps/migration_cloud/views_lms_diagnostics.py",
    "apps/migration_cloud/views_maa_counsel_activate.py",
    "apps/migration_cloud/views_maa_promotion.py",
    "apps/migration_cloud/views_smoke_history.py",
    "apps/migration_cloud/views_smoke_trigger.py",
]


class OperatorViewsControlPlaneGatedTests(SimpleTestCase):
    def test_no_operator_view_file_gates_on_staff_member_required(self):
        # Check for the ACTUAL gate usage (import + decorator), not a docstring
        # mention (views_webhook_admin.py explains WHY staff_member_required is
        # the wrong gate — that reference is documentation, not a gate).
        offenders = []
        for rel in _FILES:
            src = Path(rel).read_text(encoding="utf-8")
            if (
                "import staff_member_required" in src
                or "@staff_member_required" in src
                or "method_decorator(staff_member_required" in src
            ):
                offenders.append(rel)
        self.assertEqual(offenders, [], f"still staff-gated: {offenders}")

    def test_every_operator_view_file_imports_control_plane_gate(self):
        missing = []
        for rel in _FILES:
            src = Path(rel).read_text(encoding="utf-8")
            if "require_control_plane_access" not in src:
                missing.append(rel)
        self.assertEqual(missing, [], f"not control-plane gated: {missing}")
