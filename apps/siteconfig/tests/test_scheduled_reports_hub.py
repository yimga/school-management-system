"""Scheduled report delivery hub: tenant admin deep link under tenant urlconf."""

from datetime import timedelta, time
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf
from django.utils import timezone

from apps.accounts.models import Permission
from apps.reports.models import TenantReportSchedule
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.views import scheduled_reports_delivery_hub

User = get_user_model()


class ScheduledReportsHubAdminLinkTests(TestCase):
    def test_staff_sees_tenant_admin_schedules_link(self):
        plan = Plan.objects.create(
            name="Ph",
            slug="ph-hub",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Sh",
            slug="sh-hub",
            subdomain="sh-hub",
            is_active=True,
            plan=plan,
        )
        user = User.objects.create_user(
            username="hubstaff",
            email="hub@example.com",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        request = RequestFactory().get("/siteconfig/reports/scheduled/")
        request.user = user
        request.school = school
        set_urlconf("config.tenant_urls")
        try:
            response = scheduled_reports_delivery_hub(request)
        finally:
            set_urlconf(None)
        self.assertEqual(response.status_code, 200)
        body = response.content
        self.assertIn(b"/admin/reports/tenantreportschedule/", body)
        self.assertIn(b"Advanced/Admin", body)
        self.assertIn(b'data-shell-surface="scheduled-reports-delivery-hub"', body)
        self.assertIn(b"data-rmc-operator-evidence-summary", body)
        admin_idx = body.find(b"/admin/reports/tenantreportschedule/")
        self.assertNotEqual(admin_idx, -1)
        # 1075+: term publish + academic years evidence before advanced Django admin row.
        self.assertIn(b"Term publish status", body)
        tp = body.find(b"Term publish status")
        self.assertNotEqual(tp, -1)
        self.assertLess(tp, admin_idx)
        self.assertIn(b"Academic years (setup)", body)
        ay = body.find(b"Academic years (setup)")
        self.assertNotEqual(ay, -1)
        self.assertLess(ay, admin_idx)
        self.assertIn(b"Departments (setup)", body)
        dep = body.find(b"Departments (setup)")
        self.assertNotEqual(dep, -1)
        self.assertLess(dep, admin_idx)
        self.assertIn(b"Config mutation audit", body)
        cm = body.find(b"Config mutation audit")
        self.assertNotEqual(cm, -1)
        self.assertLess(cm, admin_idx)
        self.assertIn(b"/api/v1/reports/scheduled", body)
        self.assertIn(b'href="/api/v1/reports/scheduled"', body)
        self.assertIn(b"--school-id", body)
        # API + primary hub content (empty state here) before advanced Django admin.
        self.assertLess(body.find(b"/api/v1/reports/scheduled"), admin_idx)
        self.assertLess(body.find(b"No schedules for this tenant yet."), admin_idx)

    def test_non_staff_with_settings_manage_sees_hub_without_admin_link(self):
        plan = Plan.objects.create(
            name="Ph2",
            slug="ph-hub2",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Sh2",
            slug="sh-hub2",
            subdomain="sh-hub2",
            is_active=True,
            plan=plan,
        )
        user = User.objects.create_user(
            username="hubnonstaff",
            email="hub2@example.com",
            password="x",
            is_staff=False,
            is_superuser=False,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        user.feature_permissions.add(manage_perm)
        request = RequestFactory().get("/siteconfig/reports/scheduled/")
        request.user = user
        request.school = school
        set_urlconf("config.tenant_urls")
        try:
            response = scheduled_reports_delivery_hub(request)
        finally:
            set_urlconf(None)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"/admin/reports/tenantreportschedule/", response.content)
        self.assertIn(b"/api/v1/reports/scheduled", response.content)

    def test_hub_warns_active_row_with_zero_recipients(self):
        plan = Plan.objects.create(
            name="Ph3",
            slug="ph-hub3",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="Sh3",
            slug="sh-hub3",
            subdomain="sh-hub3",
            is_active=True,
            plan=plan,
        )
        user = User.objects.create_user(
            username="hubwarn",
            email="hub3@example.com",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        now = timezone.now()
        TenantReportSchedule.objects.create(
            school=school,
            name="Broken row",
            report_key="brk",
            schedule_frequency=TenantReportSchedule.Frequency.DAILY,
            schedule_time=time(6, 0),
            recipients=["keep@example.com"],
            parameters={},
            is_active=True,
            last_run=None,
            next_run=now + timedelta(days=1),
            created_by=user,
        )
        sch = TenantReportSchedule.objects.get(name="Broken row")
        TenantReportSchedule.objects.filter(pk=sch.pk).update(recipients=[])
        request = RequestFactory().get("/siteconfig/reports/scheduled/")
        request.user = user
        request.school = school
        set_urlconf("config.tenant_urls")
        try:
            response = scheduled_reports_delivery_hub(request)
        finally:
            set_urlconf(None)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"add addresses", response.content)

    def test_hub_empty_state_renders_translated_no_schedules_copy(self):
        plan = Plan.objects.create(
            name="PhEmpty",
            slug="ph-hub-empty",
            included_features=["reports"],
            is_active=True,
        )
        school = School.objects.create(
            name="ShEmpty",
            slug="sh-hub-empty",
            subdomain="sh-hub-empty",
            is_active=True,
            plan=plan,
        )
        user = User.objects.create_user(
            username="hubempty",
            email="hubempty@example.com",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        request = RequestFactory().get("/siteconfig/reports/scheduled/")
        request.user = user
        request.school = school
        set_urlconf("config.tenant_urls")
        try:
            response = scheduled_reports_delivery_hub(request)
        finally:
            set_urlconf(None)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No schedules for this tenant yet.", response.content)


class ScheduledReportsHubTranslatableCatalogTests(TestCase):
    def test_scheduled_hub_user_facing_msgids_in_en_catalog(self):
        """Hub-specific ``{% trans %}`` strings remain in ``en`` catalog (batch 15 #144)."""
        po = Path(settings.BASE_DIR) / "locale" / "en" / "LC_MESSAGES" / "django.po"
        self.assertTrue(po.is_file(), msg="en django.po missing")
        text = po.read_text(encoding="utf-8")
        for fragment in (
            'msgid "No schedules for this tenant yet."',
            'msgid "Scheduled report delivery"',
            'msgid "add addresses (active schedule)"',
            'msgid "Advanced/Admin: open schedules in Django admin (full CRUD)"',
        ):
            self.assertIn(fragment, text, msg=f"missing catalog entry for {fragment!r}")
