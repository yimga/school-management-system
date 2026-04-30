"""Forced demo conversion step machine (session order)."""

from __future__ import annotations

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.models import MarketingFunnelEvent, School, SchoolMembership

UserModel = get_user_model()


@patch.dict(
    os.environ,
    {"MULTI_TENANT_BASE_DOMAIN": "example.com"},
    clear=False,
)
@override_settings(
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=False,
    DEBUG=True,
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="example.com",
)
class DemoConversionFlowTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name="Demo Flow School",
            slug="demo-flow-school",
            subdomain="demo-flow-school",
            is_active=True,
            settings={},
        )
        self.user = UserModel.objects.create_user(
            username="demoflow",
            email="demoflow@example.edu",
            password="Test1234!ab",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.user,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )
        self.client.login(username="demoflow", password="Test1234!ab")

    def test_index_redirects_to_attendance(self):
        r = self.client.get(
            "/demo/flow/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/demo/flow/attendance/", r["Location"])

    def test_cannot_open_marks_before_attendance(self):
        r = self.client.get(
            "/demo/flow/marks/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/demo/flow/attendance/", r["Location"])

    def test_cannot_open_report_before_marks(self):
        self.client.get(
            "/demo/flow/attendance/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/attendance/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        r = self.client.get(
            "/demo/flow/report/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/demo/flow/marks/", r["Location"])

    def test_flow_advances_after_posts(self):
        self.client.get(
            "/demo/flow/attendance/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        r1 = self.client.post(
            "/demo/flow/attendance/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.assertEqual(r1.status_code, 302)
        r_marks = self.client.get(
            "/demo/flow/marks/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r_marks.status_code, 200)
        r2 = self.client.post(
            "/demo/flow/marks/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.assertEqual(r2.status_code, 302)
        r_rep = self.client.get(
            "/demo/flow/report/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r_rep.status_code, 200)
        r3 = self.client.post(
            "/demo/flow/report/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.assertEqual(r3.status_code, 302)
        r_done = self.client.get(
            "/demo/flow/complete/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r_done.status_code, 200)

    def test_cannot_open_complete_before_flow(self):
        r = self.client.get(
            "/demo/flow/complete/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)

    def test_complete_redirects_until_report_step_done(self):
        """Cannot show final CTA until report step is completed (session at 'report')."""
        self.client.get(
            "/demo/flow/attendance/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/attendance/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/marks/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        r = self.client.get(
            "/demo/flow/complete/",
            HTTP_HOST="demo-flow-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/demo/flow/report/", r["Location"])

    def test_create_your_school_cta_after_full_flow(self):
        self.client.get(
            "/demo/flow/attendance/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/attendance/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/marks/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/report/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        r = self.client.get(
            "/demo/flow/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Create your school")

    def test_onboarding_funnel_events_after_full_flow(self):
        self.assertEqual(
            MarketingFunnelEvent.objects.filter(
                school=self.school, event_type="onboarding_start"
            ).count(),
            0,
        )
        self.client.get(
            "/demo/flow/attendance/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.assertEqual(
            MarketingFunnelEvent.objects.filter(
                school=self.school, event_type="onboarding_start"
            ).count(),
            1,
        )
        self.client.post(
            "/demo/flow/attendance/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/marks/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.post(
            "/demo/flow/report/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.client.get(
            "/demo/flow/complete/",
            HTTP_HOST="demo-flow-school.example.com",
        )
        self.assertEqual(
            MarketingFunnelEvent.objects.filter(
                school=self.school, event_type="onboarding_complete"
            ).count(),
            1,
        )
