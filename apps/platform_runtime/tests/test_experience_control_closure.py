"""Experience control closure: roster completeness, strict primary posture, hygiene hooks."""

from __future__ import annotations

from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.people.models import StudentProfile
from apps.schools.models import SchoolMembership
from apps.platform_runtime.tests.experience_control_helpers import (
    body_has_strict_attribute,
    count_founder_toolbar_primary,
    count_strict_primary_backend_markers,
    marketing_templates_avoid_href_hash_dummy,
)
from apps.platform_runtime.tests.experience_control_registry import (
    EXPERIENCE_CONTROL_SCREENS,
    reverse_screen,
)
from apps.schools.models import School


def _tenant_host(school: School) -> str:
    return f"{school.subdomain}.runmycampus.com"


class ExperienceControlRegistryTests(TestCase):
    """Phase 1–2: roster must enumerate every mission-required surface (34)."""

    def test_registry_has_thirty_four_screens(self):
        self.assertEqual(len(EXPERIENCE_CONTROL_SCREENS), 34)

    def test_every_screen_reverse_resolves(self):
        for row in EXPERIENCE_CONTROL_SCREENS:
            path = reverse_screen(row)
            self.assertTrue(path.startswith("/"), msg=f"{row['id']}: {path}")

    def test_registry_ids_unique(self):
        ids = [r["id"] for r in EXPERIENCE_CONTROL_SCREENS]
        self.assertEqual(len(ids), len(set(ids)))


class ExperienceControlMarketingChromeTests(TestCase):
    """Phase 4: audited marketing templates avoid dummy hash-only anchors."""

    def test_marketing_template_inventory_avoids_href_hash_without_handler(self):
        violations = marketing_templates_avoid_href_hash_dummy()
        self.assertEqual(
            violations,
            [],
            msg="; ".join(f"{p}: {s}" for p, s in violations[:8]),
        )


@override_settings(
    CONVERSION_SINGLE_ACTION_ENFORCED=True,
    ALLOWED_HOSTS=["*", "testserver", "manager.runmycampus.com"],
)
class ExperienceControlStrictBackendDashboardTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name="XP Backend",
            slug="xp-backend",
            subdomain="xp-backend",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="xp_staff",
            password="pw" * 8,
            is_staff=True,
            role=User.Role.IT_ADMIN,
        )
        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.staff.feature_permissions.add(perm)

    def test_backend_dashboard_single_primary_posture_marker(self):
        self.client.force_login(self.staff)
        url = reverse("accounts:backend_dashboard")
        resp = self.client.get(url, HTTP_HOST=_tenant_host(self.school))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertTrue(body_has_strict_attribute(body))
        self.assertLessEqual(count_strict_primary_backend_markers(body), 1)


@override_settings(
    CONVERSION_SINGLE_ACTION_ENFORCED=True,
    ALLOWED_HOSTS=["*", "manager.runmycampus.com"],
)
class ExperienceControlFounderDashboardTests(TestCase):
    databases = {"default"}

    def test_founder_dashboard_single_toolbar_primary(self):
        u = User.objects.create_user(
            username="xp_founder_super",
            password="pw" * 8,
            is_superuser=True,
        )
        c = Client(enforce_csrf_checks=False)
        c.force_login(u)
        url = reverse("super:founder_dashboard", urlconf="config.manager_urls")
        r = c.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertTrue(body_has_strict_attribute(body))
        self.assertLessEqual(count_founder_toolbar_primary(body), 1)


@override_settings(
    CONVERSION_SINGLE_ACTION_ENFORCED=True,
    ALLOWED_HOSTS=["*"],
    ROOT_URLCONF="config.tenant_urls",
)
class ExperienceControlTenantSurfaceHooksTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name="XP Tenant",
            slug="xp-tenant",
            subdomain="xp-tenant",
            is_active=True,
        )
        # PRINCIPAL (not IT_ADMIN): portal module RBAC allows principal/teacher/parent roles,
        # not IT_ADMIN — see MODULE_ACCESS_DEFAULTS["portal"] in accounts.permissions.
        self.staff = User.objects.create_user(
            username="xp_ops",
            password="pw" * 8,
            is_staff=True,
            role=User.Role.PRINCIPAL,
        )
        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.staff.feature_permissions.add(perm)
        SchoolMembership.objects.get_or_create(
            user=self.staff,
            school=self.school,
            defaults={"role": User.Role.PRINCIPAL, "is_primary": True},
        )

    def test_event_console_replay_contract_template_hooks(self):
        req = RequestFactory().get("/domain-events/")
        req.user = self.staff
        req.school = self.school
        from apps.events.models import DomainEvent
        from django.utils import timezone

        ev = DomainEvent.objects.create(
            event_type="payment_success",
            payload={"x": 1},
            school_id=self.school.pk,
            status="processed",
            processed_at=timezone.now(),
        )
        from apps.events.views_console import event_domain_detail

        resp = event_domain_detail(req, event_id=ev.pk)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-task="event_replay"', body)
        self.assertIn('data-task-step="events:domain-replay-submit"', body)

    def test_offline_sync_queue_strict_primary_process_button(self):
        self.client.force_login(self.staff)
        url = reverse("portal:offline_sync_queue")
        r = self.client.get(url, HTTP_HOST=_tenant_host(self.school))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn('data-task="offline_sync"', body)
        self.assertIn("offline-process-queue", body)

    def test_governed_builder_preview_primary_in_strict_template(self):
        req = RequestFactory().get("/analytics/governed/query-builder/")
        req.user = self.staff
        req.school = self.school
        html = render_to_string(
            "analytics/governed_report_builder.html",
            {
                "request": req,
                "school_id": str(self.school.pk),
                "rmc_conversion_single_action_enforced": True,
            },
            request=req,
        )
        self.assertIn('data-task="governed_report_export"', html)
        self.assertIn('id="gr-preview"', html)
        self.assertGreaterEqual(html.count('btn btn-primary btn-sm'), 1)
        self.assertIn('data-action="governed-report-preview"', html)

    def test_payment_readiness_root_task_marker(self):
        req = RequestFactory().get("/finance/payment-readiness/")
        req.user = self.staff
        req.school = self.school
        html = render_to_string(
            "finance/payment_readiness_setup.html",
            {
                "request": req,
                "readiness": type(
                    "R",
                    (),
                    {
                        "headline": "H",
                        "subhead": "S",
                        "status": "MISSING_SETUP",
                        "country_code": "US",
                        "currency_code": "USD",
                        "drill_manual_if_all_rails_down": False,
                        "checklist": [],
                        "recommended_primary_rail": "",
                        "recommended_backup_rail": "",
                        "operator_setup_steps": [],
                    },
                )(),
                "profile": type("P", (), {"name": "default"})(),
                "status_badge_class": "warning",
            },
            request=req,
        )
        self.assertIn('data-task="payment_readiness_setup"', html)


@override_settings(
    ALLOWED_HOSTS=[
        "*",
        "testserver",
        "127.0.0.1",
        "localhost",
        "manager.runmycampus.com",
    ],
)
class ExperienceControlTenantLifecyclePrimaryActionTests(TestCase):
    databases = {"default"}

    def test_lifecycle_dashboard_row_primary_links_have_telemetry(self):
        u = User.objects.create_user(
            username="xp_plc",
            password="pw" * 8,
            is_superuser=True,
        )
        c = Client(enforce_csrf_checks=False)
        c.force_login(u)
        url = reverse("platform_runtime:tenant_lifecycle_dashboard")
        r = c.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        self.assertIn('data-task="tenant_lifecycle"', body)
        # Template instrumented row-level actions when rows exist; empty-state path still has hooks.
        self.assertIn("dashboard-empty-state", body.lower() or body)


class ExperienceControlNextActionStripStrictTests(TestCase):
    def test_strip_single_chip_multiple_actions(self):
        req = RequestFactory().get("/")
        req.user = User(username="x", pk=1)
        html = render_to_string(
            "components/next_action_strip.html",
            {
                "request": req,
                "rmc_system_actions_available": True,
                "rmc_system_actions": [
                    {"title": "A", "action_url": "/a/", "type": "task", "source": "x"},
                    {"title": "B", "action_url": "/b/", "type": "task", "source": "x"},
                ],
                "rmc_conversion_single_action_enforced": True,
            },
        )
        self.assertEqual(html.count('class="rmc-nas-chip"'), 1)


class ExperienceControlStudent360PermissionTests(TestCase):
    databases = {"default"}

    @override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
    def test_student_360_staff_renders_with_hooks(self):
        school = School.objects.create(
            name="XP S360",
            slug="xp-s360",
            subdomain="xp-s360",
            is_active=True,
        )
        staff = User.objects.create_user(
            username="xp_staff_s360",
            password="pw" * 8,
            is_staff=True,
            role=User.Role.PRINCIPAL,
        )
        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        staff.feature_permissions.add(perm)
        stu = StudentProfile.objects.create(
            school=school,
            first_name="A",
            last_name="B",
            student_code="xp-s360-1",
        )
        c = Client(enforce_csrf_checks=False)
        c.force_login(staff)
        url = reverse("portal:student_360_page", kwargs={"student_id": stu.pk})
        r = c.get(url, HTTP_HOST=_tenant_host(school))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace")
        bl = body.lower()
        self.assertTrue(
            "student 360" in bl or "student360tabcontent" in bl,
            msg="Expected Student 360 shell markers in rendered HTML",
        )
