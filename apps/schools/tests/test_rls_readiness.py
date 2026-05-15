"""Wave O2: RLS runtime readiness preflight tests."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.schools.rls_readiness import assess_rls_readiness


_MW_TARGET = "apps.schools.middleware.TenantMiddleware"


class RlsReadinessTests(TestCase):

    def test_default_wiring_is_ready_on_sqlite(self):
        with override_settings(
            MIDDLEWARE=(_MW_TARGET,),
            USE_DJANGO_TENANTS=False,
        ):
            report = assess_rls_readiness()
        self.assertTrue(
            report.ready,
            msg=(
                f"expected ready on dev/sqlite, got issues: "
                f"middleware_wired={report.middleware_wired}, "
                f"importable={report.rls_context_importable}, "
                f"use_django_tenants_disabled={report.use_django_tenants_disabled}, "
                f"guc={report.guc_settable}, policies={report.policy_count}"
            ),
        )
        # On SQLite, Postgres-only checks are skipped.
        if connection.vendor != "postgresql":
            self.assertIsNone(report.guc_settable)
            self.assertIsNone(report.policy_count)
            self.assertTrue(len(report.skipped_checks) >= 1)

    def test_middleware_not_wired_blocks(self):
        with override_settings(MIDDLEWARE=(), USE_DJANGO_TENANTS=False):
            report = assess_rls_readiness()
        self.assertFalse(report.middleware_wired)
        self.assertFalse(report.ready)

    def test_use_django_tenants_true_blocks(self):
        """RLS mode requires USE_DJANGO_TENANTS=False."""
        with override_settings(
            MIDDLEWARE=(_MW_TARGET,),
            USE_DJANGO_TENANTS=True,
        ):
            report = assess_rls_readiness()
        self.assertFalse(report.use_django_tenants_disabled)
        self.assertFalse(report.ready)

    def test_rls_context_module_is_importable(self):
        """The middleware imports `set_rls_school_id`; preflight verifies same."""
        with override_settings(MIDDLEWARE=(_MW_TARGET,), USE_DJANGO_TENANTS=False):
            report = assess_rls_readiness()
        self.assertTrue(report.rls_context_importable)

    def test_backend_vendor_recorded(self):
        report = assess_rls_readiness()
        self.assertIn(report.backend_vendor, ("postgresql", "sqlite", "mysql", "oracle"))


class VerifyRlsReadinessCommandTests(TestCase):
    @override_settings(MIDDLEWARE=(_MW_TARGET,), USE_DJANGO_TENANTS=False)
    def test_command_exits_0_when_ready(self):
        out = StringIO()
        call_command("verify_rls_readiness", stdout=out)
        self.assertIn("READY", out.getvalue())

    @override_settings(MIDDLEWARE=(), USE_DJANGO_TENANTS=False)
    def test_command_exits_1_when_not_ready(self):
        with self.assertRaises(SystemExit) as cm:
            call_command("verify_rls_readiness", "--quiet", stdout=StringIO())
        self.assertEqual(cm.exception.code, 1)


class OrchestratorRlsSectionTests(TestCase):
    @override_settings(MIDDLEWARE=(_MW_TARGET,), USE_DJANGO_TENANTS=False)
    def test_rls_section_runs_via_orchestrator(self):
        out = StringIO()
        call_command(
            "verify_platform_readiness",
            "--section", "rls",
            "--json",
            stdout=out,
        )
        import json
        payload = json.loads(out.getvalue())
        self.assertIn("rls", payload["sections"])
        details = payload["sections"]["rls"]["details"]
        self.assertTrue(details["middleware_wired"])
        self.assertTrue(details["use_django_tenants_disabled"])

    @override_settings(MIDDLEWARE=(), USE_DJANGO_TENANTS=False)
    def test_rls_section_failure_propagates_exit_1(self):
        with self.assertRaises(SystemExit) as cm:
            call_command(
                "verify_platform_readiness",
                "--section", "rls",
                stdout=StringIO(),
            )
        self.assertEqual(cm.exception.code, 1)
