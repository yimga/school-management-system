"""Unit tests for fleet report markdown and tenant operational health."""
from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.schools.fleet_report_markdown import build_fleet_status_markdown
from apps.schools.models import School
from apps.schools.tenant_operational_health import (
    TIER_UP,
    resolve_tenant_operational_health,
)


class FleetReportMarkdownTests(SimpleTestCase):
    def test_markdown_contains_header_and_table(self):
        md = build_fleet_status_markdown()
        self.assertIn("# RunMyCampus Fleet Status Report", md)
        self.assertIn("| School | Slug | Fleet status |", md)


class TenantOperationalHealthTests(TestCase):
    def test_active_school_is_up(self):
        school = School.objects.create(
            name="Ops Health School",
            slug="ops-health-school",
            subdomain="ops-health-school",
            is_active=True,
            is_approved=True,
        )
        payload = resolve_tenant_operational_health(school, surface="admin")
        self.assertEqual(payload["tier"], TIER_UP)
        self.assertIn("revision", payload)

    def test_inactive_school_is_down(self):
        school = School.objects.create(
            name="Ops Down School",
            slug="ops-down-school",
            subdomain="ops-down-school",
            is_active=False,
        )
        payload = resolve_tenant_operational_health(school, surface="teacher")
        self.assertEqual(payload["tier"], "down")

    def test_parent_surface_without_links_is_degraded(self):
        school = School.objects.create(
            name="Ops Parent School",
            slug="ops-parent-school",
            subdomain="ops-parent-school",
            is_active=True,
            is_approved=True,
        )
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        User = get_user_model()
        user = User.objects.create_user(
            username="ops-parent-user",
            password="Test1234!",
            role=User.Role.PARENT,
        )
        request = RequestFactory().get("/portal/api/operational-health.json?surface=parent")
        request.user = user
        request.school = school
        payload = resolve_tenant_operational_health(school, request=request, surface="parent")
        self.assertEqual(payload["tier"], "degraded")
        self.assertTrue(any(sig.get("key") == "link_child" for sig in payload["signals"]))

    def test_student_surface_without_profile_is_degraded(self):
        school = School.objects.create(
            name="Ops Student School",
            slug="ops-student-school",
            subdomain="ops-student-school",
            is_active=True,
            is_approved=True,
        )
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        User = get_user_model()
        user = User.objects.create_user(
            username="ops-student-user",
            password="Test1234!",
            role=User.Role.STUDENT,
        )
        request = RequestFactory().get("/portal/api/operational-health.json?surface=student")
        request.user = user
        request.school = school
        payload = resolve_tenant_operational_health(school, request=request, surface="student")
        self.assertEqual(payload["tier"], "degraded")
        self.assertTrue(any(sig.get("key") == "student_profile" for sig in payload["signals"]))

    def test_student_surface_portal_disabled_is_degraded(self):
        school = School.objects.create(
            name="Ops Student Off School",
            slug="ops-student-off-school",
            subdomain="ops-student-off-school",
            is_active=True,
            is_approved=True,
        )
        from types import SimpleNamespace
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        User = get_user_model()
        user = User.objects.create_user(
            username="ops-student-off-user",
            password="Test1234!",
            role=User.Role.STUDENT,
        )
        request = RequestFactory().get("/portal/api/operational-health.json?surface=student")
        request.user = user
        request.school = school
        site = SimpleNamespace(enable_student_portal=False)
        from unittest.mock import patch

        with patch(
            "apps.siteconfig.config_service.get_effective_site_settings",
            return_value=site,
        ):
            payload = resolve_tenant_operational_health(
                school, request=request, surface="student"
            )
        self.assertEqual(payload["tier"], "degraded")
        self.assertTrue(any(sig.get("key") == "student_portal" for sig in payload["signals"]))
