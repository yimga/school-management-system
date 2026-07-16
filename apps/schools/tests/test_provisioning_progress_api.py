"""Provisioning progress API contract tests."""

from __future__ import annotations

import json

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.views_pending_provision import api_public_pending_provision_progress


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class PublicPendingProvisionProgressTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Pending Academy",
            slug="pending-academy",
            subdomain="pending-academy",
            is_active=False,
        )

    def test_public_api_returns_progress_for_pending_subdomain(self):
        request = self.factory.get(
            "/api/pending-provision/progress/",
            HTTP_HOST="pending-academy.runmycampus.com",
        )
        response = api_public_pending_provision_progress(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload.get("ok"))
        self.assertIn("progress_percent", payload)
        self.assertIn("steps", payload)
        self.assertIn("workflow_key", payload)
        self.assertEqual(payload.get("workflow_key"), "tenant_school_provision")
        # Pin the payload against the step SPEC, not a literal: the strip is meant
        # to grow as provisioning gains steps (it went 14 -> 15 when the teaching
        # grid became a real seeded step), and a hardcoded count turns every such
        # addition into a false failure while proving nothing extra.
        from apps.schools.provisioning_progress import EXTENDED_PROVISION_STEP_COUNT

        self.assertEqual(
            len(payload.get("extended_steps") or []), EXTENDED_PROVISION_STEP_COUNT
        )
        self.assertEqual(
            payload.get("extended_step_count"), EXTENDED_PROVISION_STEP_COUNT
        )
        self.assertGreaterEqual(EXTENDED_PROVISION_STEP_COUNT, 14)

    def test_public_api_404_when_school_active(self):
        self.school.is_active = True
        self.school.save(update_fields=["is_active"])
        request = self.factory.get(
            "/api/pending-provision/progress/",
            HTTP_HOST="pending-academy.runmycampus.com",
        )
        response = api_public_pending_provision_progress(request)
        self.assertEqual(response.status_code, 404)


class OwnerProvisionProgressApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Owner School",
            slug="owner-school",
            subdomain="owner-school",
            is_active=False,
        )
        self.user = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="Test1234!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )

    def test_owner_progress_api_includes_bar_fields(self):
        self.client.force_login(self.user)
        url = reverse("accounts:owner_onboarding_provision_progress")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload.get("ok"))
        self.assertIn("progress_percent", payload)
        self.assertIn("current_step_label", payload)
        self.assertIn("portal_ready", payload)
        self.assertIsInstance(payload.get("steps"), list)
