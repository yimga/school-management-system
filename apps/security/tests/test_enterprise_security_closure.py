"""Consolidated enterprise security hub / command center (super operator only)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

_MGR = "manager.runmycampus.com"
_T = "entsec.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=[
        "*",
        "testserver",
        "127.0.0.1",
        "localhost",
        _T,
        _MGR,
    ]
)
class EnterpriseSecurityHubClosureTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.superuser = User.objects.create_user(
            username=f"esu_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=True,
        )

    def test_security_hub_renders_command_center_strip(self):
        c = Client(HTTP_HOST=_MGR)
        c.force_login(self.superuser)
        url = reverse("super:security_hub")
        r = c.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Governance verifier summaries", html=False)
        self.assertContains(r, "Impersonation", html=False)

    def test_security_command_center_alias_matches_hub(self):
        c = Client(HTTP_HOST=_MGR)
        c.force_login(self.superuser)
        r1 = c.get(reverse("super:security_hub"))
        r2 = c.get(reverse("super:security_command_center"))
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "Governance verifier summaries", html=False)

    def test_enterprise_security_command_center_route(self):
        c = Client(HTTP_HOST=_MGR)
        c.force_login(self.superuser)
        r = c.get(reverse("super:enterprise_security_command_center"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Kill test regression", html=False)
        self.assertContains(r, "North Star audit", html=False)
        self.assertContains(r, "Test module contract", html=False)

    def test_security_hub_forbidden_on_tenant_host(self):
        staff = User.objects.create_user(
            username=f"sf_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=False,
        )
        c = Client(HTTP_HOST=_T)
        c.force_login(staff)
        self.assertIn(c.get(reverse("super:security_hub")).status_code, (302, 403))

    def test_security_hub_staff_non_super_blocked_on_manager(self):
        staff = User.objects.create_user(
            username=f"mg_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=False,
        )
        c = Client(HTTP_HOST=_MGR)
        c.force_login(staff)
        self.assertIn(c.get(reverse("super:security_hub")).status_code, (302, 403))
