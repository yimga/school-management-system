"""G15 — an operator entry point for the REAL (rolled-back) DR restore drill.

The command wraps lifecycle.verify_tenant_snapshot_restore_integrity (which is
itself exercised by the DR snapshot tests); these lock the command's contract:
slug/uuid resolution, JSON output, and a non-zero exit (CommandError) when the
drill does not come back ok -- so a wiped/ephemeral blob (G14) surfaces as a hard
failure the operator can act on, not a warning nobody reads. The task is patched
so no real snapshot/disk is needed.
"""
from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.schools.models import School

_TASK = (
    "apps.lifecycle.tasks_dr_snapshot.verify_tenant_snapshot_restore_integrity"
)


class DrillTenantSnapshotRestoreCommandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Drill", slug="drill-school", subdomain="drill-school", is_active=True
        )

    def test_requires_school_id_or_slug(self):
        with self.assertRaises(CommandError):
            call_command("drill_tenant_snapshot_restore")

    def test_unknown_slug_errors(self):
        with self.assertRaises(CommandError):
            call_command("drill_tenant_snapshot_restore", "--slug", "does-not-exist")

    def test_ok_drill_prints_counts_and_succeeds(self):
        with mock.patch(
            _TASK,
            return_value={
                "ok": True,
                "school_id": str(self.school.pk),
                "counts": {"students": 3},
            },
        ) as task:
            out = StringIO()
            call_command(
                "drill_tenant_snapshot_restore", "--slug", "drill-school", stdout=out
            )
        task.assert_called_once_with(str(self.school.pk))
        body = out.getvalue()
        self.assertIn("students", body)
        self.assertIn("OK", body)

    def test_uuid_positional_arg_resolves(self):
        with mock.patch(
            _TASK, return_value={"ok": True, "school_id": str(self.school.pk)}
        ) as task:
            call_command(
                "drill_tenant_snapshot_restore", str(self.school.pk), stdout=StringIO()
            )
        task.assert_called_once_with(str(self.school.pk))

    def test_restore_error_exits_nonzero_with_ephemeral_hint(self):
        with mock.patch(_TASK, return_value={"ok": False, "reason": "restore_error"}):
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "drill_tenant_snapshot_restore", str(self.school.pk), stdout=StringIO()
                )
        self.assertIn("ephemeral", str(ctx.exception).lower())

    def test_no_snapshot_reason_surfaces(self):
        with mock.patch(_TASK, return_value={"ok": False, "reason": "no_snapshot"}):
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "drill_tenant_snapshot_restore", str(self.school.pk), stdout=StringIO()
                )
        self.assertIn("no_snapshot", str(ctx.exception))
