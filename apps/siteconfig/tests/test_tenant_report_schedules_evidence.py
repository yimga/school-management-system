"""1099: Tenant scheduled report schedules — read-only evidence (real TenantReportSchedule rows)."""

from __future__ import annotations

import datetime

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Permission as FeaturePermission, User
from apps.reports.models import TenantReportSchedule
from apps.siteconfig.models import Plan
from apps.schools.models import School

_T_HOST = "sched-ev.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST]
)
class TenantReportSchedulesEvidenceRouteTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="SchedEvPlan",
            slug="sched-ev-plan",
            included_features=[],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Sched Evidence School",
            slug="sched-ev",
            subdomain="sched-ev",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="sched_evidence_adm",
            password="w" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.user.feature_permissions.add(self.perm_settings)
        t = datetime.time(6, 30)
        n = timezone.now()
        self.schedule = TenantReportSchedule.objects.create(
            school=self.school,
            name="Daily summary",
            report_key="summary",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=t,
            recipients=["ops@example.com"],
            is_active=True,
            next_run=n,
            created_by_id=self.user.pk,
        )

    def test_settings_manager_gets_200_with_markers(self) -> None:
        client = Client(HTTP_HOST=_T_HOST)
        client.login(username="sched_evidence_adm", password="w" * 8)
        path = reverse(
            "siteconfig:tenant_report_schedules_evidence", urlconf="config.tenant_urls"
        )
        self.assertIn("/siteconfig/reports/tenant-schedules-evidence/", path)
        resp = client.get(path)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-cp-evidence-surface="tenant-report-schedules"', body)
        self.assertIn("data-rmc-operator-evidence-surface", body)
        self.assertIn("data-rmc-operator-evidence-summary", body)
        self.assertIn("data-rmc-evidence-related-links", body)
        self.assertIn("data-rmc-report-bulk-evidence", body)
        self.assertIn("Daily summary", body)
        self.assertIn("Due now", body)
        self.assertIn("Needs recipients", body)
        self.assertIn("Run history", body)
        self.assertIn("Never", body)
        self.assertIn("Report templates (catalog)", body)
        self.assertIn("/siteconfig/reports/report-templates-catalog/", body)
        self.assertIn("Report output history", body)
        self.assertIn("/siteconfig/reports/output-history-evidence/", body)

    def test_anonymous_redirects_or_403(self) -> None:
        client = Client(HTTP_HOST=_T_HOST)
        path = reverse(
            "siteconfig:tenant_report_schedules_evidence", urlconf="config.tenant_urls"
        )
        resp = client.get(path)
        self.assertIn(resp.status_code, (302, 403))
