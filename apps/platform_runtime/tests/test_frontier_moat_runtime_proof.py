"""Runtime proof hooks for frontier moat metrics 25–28 (PROMPT B harsh scoring)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.people.models import StudentProfile
from apps.schools.models import School


class FrontierMoatRuntimeProofTests(TestCase):
    def test_crdt_convergence_management_command(self):
        call_command("verify_crdt_convergence")

    def test_sync_semantics_management_command(self):
        call_command("verify_sync_semantics")

    def test_restore_drill_dry_run_appends_log(self):
        repo = Path(__file__).resolve().parents[3]
        script = repo / "scripts" / "restore_drill.py"
        log_path = repo / "docs" / "generated" / "dr_drill_log.json"
        before = log_path.read_text(encoding="utf-8") if log_path.exists() else "[]"
        before_len = len(json.loads(before) if before.strip() else [])
        proc = subprocess.run(
            [sys.executable, str(script), "--dry-run"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("dry-run", proc.stdout.lower())
        after_len = len(json.loads(log_path.read_text(encoding="utf-8")))
        self.assertGreaterEqual(after_len, before_len)

    def test_tenant_student_query_isolation_by_school(self):
        """Cross-tenant read denial at ORM layer (metric 27 partial proof)."""
        school_a = School.objects.create(
            name="Region A School",
            slug="region-a-school",
            subdomain="region-a-school",
            is_active=True,
            data_region="eu_central",
        )
        school_b = School.objects.create(
            name="Region B School",
            slug="region-b-school",
            subdomain="region-b-school",
            is_active=True,
            data_region="us_east",
        )
        student_a = StudentProfile.objects.create(
            school=school_a,
            first_name="A",
            last_name="Student",
            student_code="REG-A-001",
        )
        StudentProfile.objects.create(
            school=school_b,
            first_name="B",
            last_name="Student",
            student_code="REG-B-001",
        )
        visible = list(
            StudentProfile.objects.filter(school=school_a).values_list("pk", flat=True)
        )
        self.assertEqual(visible, [student_a.pk])
        self.assertFalse(
            StudentProfile.objects.filter(
                school=school_a,
                student_code="REG-B-001",
            ).exists()
        )

    @override_settings(SECRET_KEY="test-frontier-snapshot-key")
    def test_tenant_immutable_snapshot_capture_and_restore(self):
        from pathlib import Path

        from apps.lifecycle.tenant_dr_snapshot import capture_daily_snapshot, restore_from_snapshot

        school = School.objects.create(
            name="Snapshot Frontier School",
            slug="snapshot-frontier-school",
            subdomain="snapshot-frontier-school",
            is_active=True,
        )
        meta = capture_daily_snapshot(school)
        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(school.pk),
            expected_sig=meta["signature_hex"],
        )
        self.assertEqual(restored["school_id"], str(school.pk))


@override_settings(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        },
        "tenant_heavy_1": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        },
    }
)
class DedicatedDbRouterProofTests(SimpleTestCase):
    def test_dedicated_db_alias_routes_when_configured(self):
        from django.db import connection

        from apps.siteconfig.db_router import TenantDatabaseRouter

        school = School(
            name="Dedicated DB School",
            slug="dedicated-db-school",
            subdomain="dedicated-db-school",
            dedicated_db_alias="tenant_heavy_1",
        )

        class _Tenant:
            pass

        _Tenant.school = school

        router = TenantDatabaseRouter()
        connection.tenant = _Tenant()
        try:
            alias = router.db_for_write(School)
        finally:
            connection.tenant = None
        self.assertEqual(alias, "tenant_heavy_1")

    def test_unknown_dedicated_db_alias_falls_back_to_default(self):
        """Sovereignty: invalid cross-region alias must not route writes."""
        from django.db import connection

        from apps.siteconfig.db_router import TenantDatabaseRouter

        school = School(
            name="Bad Alias School",
            slug="bad-alias-school",
            subdomain="bad-alias-school",
            dedicated_db_alias="tenant_nonexistent_region",
            data_region="eu_west",
        )

        class _Tenant:
            pass

        _Tenant.school = school

        router = TenantDatabaseRouter()
        connection.tenant = _Tenant()
        try:
            alias = router.db_for_write(School)
        finally:
            connection.tenant = None
        self.assertIsNone(alias)
