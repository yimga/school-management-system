"""Tenant School Studio hub — launch path, readiness, tenant safety."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission, User
from apps.people.models import TeacherProfile
from apps.siteconfig.models import Plan
from apps.schools.models import School

UserModel = get_user_model()


class TenantStudioUrlContractTests(SimpleTestCase):
    def test_school_studio_routes_registered(self):
        for name in (
            "school_studio",
            "school_studio_setup",
            "school_studio_readiness",
            "school_studio_migration",
            "school_studio_help",
            "school_studio_launch",
        ):
            path = reverse(name, urlconf="config.tenant_urls")
            self.assertTrue(path.startswith("/school/studio"), msg=f"{name} -> {path}")


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class TenantStudioOperatingSystemViewTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="Studio OS School",
            slug="schoolstudio",
            subdomain="schoolstudio",
            is_active=True,
            plan=cls.plan,
        )
        cls.perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _staff_request(self, path: str = "/school/studio/"):
        user = UserModel.objects.create_user(
            username=f"studio_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        user.feature_permissions.add(self.perm)
        TeacherProfile.objects.create(
            user=user,
            school=self.school,
            staff_id=f"S{uuid.uuid4().hex[:4].upper()}",
        )
        rf = RequestFactory()
        req = rf.get(path)
        req.user = user
        req.school = self.school
        return req

    def test_school_studio_hub_renders_launch_markers(self):
        from apps.siteconfig.views_tenant_studio_hub import school_studio_hub

        resp = school_studio_hub(self._staff_request())
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('data-rmc-tenant-studio-launch-path="1"', html)
        self.assertIn('data-rmc-tenant-studio-readiness="1"', html)
        self.assertIn("data-rmc-tenant-studio-ai-guidance", html)
        self.assertIn("data-rmc-ai-guided", html)

    def test_school_studio_setup_redirects_to_onboarding(self):
        from apps.siteconfig.views_tenant_studio_hub import school_studio_redirect_setup

        resp = school_studio_redirect_setup(self._staff_request("/school/studio/setup/"))
        self.assertIsInstance(resp, HttpResponseRedirect)
        self.assertIn("/siteconfig/onboarding", resp.url)

    def test_forbidden_without_school(self):
        from apps.siteconfig.views_tenant_studio_hub import school_studio_hub

        rf = RequestFactory()
        req = rf.get("/school/studio/")
        req.user = UserModel.objects.create_user(
            username=f"nostudio_{uuid.uuid4().hex[:6]}",
            password="x" * 8,
            is_staff=True,
        )
        req.school = None
        resp = school_studio_hub(req)
        self.assertEqual(resp.status_code, 403)
