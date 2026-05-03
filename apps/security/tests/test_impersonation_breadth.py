"""Impersonation audit disposition surfaces on the enterprise security hub (operator)."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School
from apps.siteconfig.models import ImpersonationLog

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MGR],
)
class ImpersonationBreadthHubTests(TestCase):
    databases = {"default"}

    def test_impersonation_row_and_reason_visible_on_command_center(self):
        school = School.objects.create(
            name="Impersonation Breadth School",
            slug="imp-breadth",
            subdomain="imp-breadth",
            is_active=True,
        )
        actor = User.objects.create_user(
            username=f"imp_{uuid.uuid4().hex[:8]}",
            password="y" * 8,
            is_staff=True,
            is_superuser=True,
        )
        tag = "breadth-verify ticket INC-42"
        ImpersonationLog.objects.create(
            actor=actor,
            school=school,
            action=ImpersonationLog.Action.SWITCH,
            reason=tag,
            read_only=True,
        )
        c = Client(HTTP_HOST=_MGR)
        c.force_login(actor)
        r = c.get(reverse("super:enterprise_security_command_center"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Impersonation & proxy", html=False)
        self.assertContains(r, tag[:40], html=False)
        self.assertContains(r, school.name, html=False)
