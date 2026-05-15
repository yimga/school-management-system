"""Group intelligence aggregates (permission-aware; no fabricated counts)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission
from apps.accounts.models import User
from apps.schools.group_analytics import build_group_intelligence_context
from apps.schools.models import School, SchoolMembership

_ALLOWED = [
    "testserver",
    "127.0.0.1",
    "localhost",
    "metro-gi.runmycampus.com",
    "north-gi.runmycampus.com",
    "south-gi.runmycampus.com",
    "solo-gi.runmycampus.com",
]


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class GroupIntelligenceTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        cls.parent_school = School.objects.create(
            name="GI Root",
            slug="metro-gi",
            subdomain="metro-gi",
            is_active=True,
        )
        cls.child_a = School.objects.create(
            name="GI North",
            slug="north-gi",
            subdomain="north-gi",
            parent_school=cls.parent_school,
            is_active=True,
        )
        cls.child_b = School.objects.create(
            name="GI South",
            slug="south-gi",
            subdomain="south-gi",
            parent_school=cls.parent_school,
            is_active=True,
        )

    def _admin(self, school: School) -> User:
        u = User.objects.create_user(
            username=f"gi_{uuid.uuid4().hex[:8]}",
            password="passwordxx",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm)
        SchoolMembership.objects.get_or_create(
            user=u, school=school, defaults={"role": User.Role.ADMIN, "is_primary": True}
        )
        return u

    def _force_login_verified(self, client: Client, user: User) -> None:
        TOTPDevice.objects.get_or_create(
            user=user,
            name="test-device",
            defaults={"confirmed": True},
        )
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def test_parent_admin_sees_intelligence_marker_and_real_counts(self):
        u = self._admin(self.parent_school)
        ctx = build_group_intelligence_context(self.parent_school, u)
        self.assertIsNotNone(ctx.get("group_school"))
        gs = ctx["group_school"]
        assert gs is not None
        self.assertGreaterEqual(gs.get("campus_count", 0), 1)

        c = Client(HTTP_HOST="metro-gi.runmycampus.com")
        self._force_login_verified(c, u)
        url = reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-group-intelligence="1"', body)

    def test_child_admin_no_sibling_leak_in_page(self):
        u = self._admin(self.child_b)
        c = Client(HTTP_HOST="south-gi.runmycampus.com")
        self._force_login_verified(c, u)
        url = reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertNotIn("GI North", body)

    def test_teacher_blocked(self):
        tu = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:8]}",
            password="passwordxx",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=tu, school=self.child_b, role=User.Role.TEACHER
        )
        c = Client(HTTP_HOST="south-gi.runmycampus.com")
        c.force_login(tu)
        r = c.get(reverse("siteconfig:school_group_hierarchy", urlconf="config.tenant_urls"))
        self.assertEqual(r.status_code, 403)

    def test_single_school_summary_safe(self):
        solo = School.objects.create(
            name="GI Solo",
            slug="solo-gi",
            subdomain="solo-gi",
            is_active=True,
        )
        u = self._admin(solo)
        s = build_group_intelligence_context(solo, u)
        self.assertIsNotNone(s.get("group_school"))
