"""HTTP contract tests for tenant Group Console (Phase 4A)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import Permission as FeaturePermission
from apps.accounts.models import User
from apps.governance.models import Organization
from apps.governance.operating_modes import GovernanceOperatingMode
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School, SchoolMembership

_ALLOWED_HOSTS = [
    "testserver",
    "127.0.0.1",
    "localhost",
    "trust-grp.runmycampus.com",
    "solo-gr.runmycampus.com",
]


@override_settings(ALLOWED_HOSTS=_ALLOWED_HOSTS)
class GroupConsoleHttpTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="GrpPlan",
            slug=f"grp-plan-{uuid.uuid4().hex[:8]}",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code=f"R{uuid.uuid4().hex[:6].upper()}",
            name="Region",
            timezone="UTC",
            default_currency="USD",
        )
        cls.org = Organization.objects.create(
            name="Test Trust",
            slug=f"trust-{uuid.uuid4().hex[:8]}",
        )
        cls.group_school = School.objects.create(
            name="Trust HQ",
            slug="trust-grp",
            subdomain="trust-grp",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
            organization=cls.org,
            governance_operating_mode=GovernanceOperatingMode.GROUP_MEMBER,
        )
        cls.member_school = School.objects.create(
            name="Member Campus",
            slug=f"member-{uuid.uuid4().hex[:6]}",
            subdomain=f"member-{uuid.uuid4().hex[:6]}",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
            organization=cls.org,
            governance_operating_mode=GovernanceOperatingMode.GROUP_MEMBER,
        )
        cls.standalone_school = School.objects.create(
            name="Solo School",
            slug="solo-gr",
            subdomain="solo-gr",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
            governance_operating_mode=GovernanceOperatingMode.STANDALONE,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def _admin(self, username: str, school: School) -> User:
        user = User.objects.create_user(
            username=username,
            password="passwordxx",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        user.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.get_or_create(
            user=user,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        return user

    def _login(self, client: Client, user: User) -> None:
        TOTPDevice.objects.get_or_create(user=user, name="default", defaults={"confirmed": True})
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session.save()

    def test_group_console_200_lists_member_schools(self):
        user = self._admin(f"gadm_{uuid.uuid4().hex[:8]}", self.group_school)
        client = Client(HTTP_HOST="trust-grp.runmycampus.com")
        self._login(client, user)
        url = reverse("siteconfig:group_console", urlconf="config.tenant_urls")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:600])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Group Console", body)
        self.assertIn("Member Campus", body)
        self.assertIn("data-rmc-scroll-policy", body)

    def test_standalone_school_forbidden(self):
        user = self._admin(f"solo_{uuid.uuid4().hex[:8]}", self.standalone_school)
        client = Client(HTTP_HOST="solo-gr.runmycampus.com")
        self._login(client, user)
        url = reverse("siteconfig:group_console", urlconf="config.tenant_urls")
        resp = client.get(url)
        self.assertEqual(resp.status_code, 403)
