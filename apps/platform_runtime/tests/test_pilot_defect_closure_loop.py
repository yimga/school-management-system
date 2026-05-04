"""Pilot defect registry policy and dashboard."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.models import PilotDefect
from apps.platform_runtime.pilot_defect_closure import (
    fixed_defect_has_proof,
    sort_defects_for_dashboard,
)


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class PilotDefectClosureTests(TestCase):
    def test_critical_sorts_first(self):
        rows = sort_defects_for_dashboard(
            [
                {"id": "b", "severity": "low", "status": "reported"},
                {"id": "a", "severity": "critical", "status": "reported"},
            ]
        )
        self.assertEqual(rows[0]["id"], "a")

    def test_fixed_requires_test_or_exception(self):
        self.assertFalse(
            fixed_defect_has_proof(
                {"status": "fixed", "linked_test": "", "documented_exception": ""}
            )
        )
        self.assertTrue(
            fixed_defect_has_proof(
                {
                    "status": "fixed",
                    "linked_test": "apps.platform_runtime.tests.test_x",
                    "documented_exception": "",
                }
            )
        )

    def test_dashboard_200(self):
        PilotDefect.objects.all().delete()
        PilotDefect.objects.create(
            title="Critical item",
            source_school_slug="p1",
            severity=PilotDefect.Severity.CRITICAL,
            module="finance",
            owner="eng",
            status=PilotDefect.Status.REPORTED,
        )
        PilotDefect.objects.create(
            title="Fixed no proof",
            source_school_slug="p1",
            severity=PilotDefect.Severity.LOW,
            module="portal",
            owner="eng",
            status=PilotDefect.Status.FIXED,
            sot_batch="1170-op-excellence",
        )
        User.objects.create_user(
            username="defect_dash",
            password="x" * 8,
            is_superuser=True,
        )
        c = Client()
        self.assertTrue(c.login(username="defect_dash", password="x" * 8))
        r = c.get(
            reverse("platform_runtime:pilot_defect_dashboard"),
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn("Fixes without proof", body)
        self.assertIn("1170-op-excellence", body)
