"""HTTP integration tests for bulk school and operator JSON APIs."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.platform_runtime.models_operator_identity import PlatformOperatorProfile
from apps.platform_runtime.operator_identity import ensure_platform_operator_profile
from apps.schools.models import School
from apps.schools.super_views_bulk import api_bulk_operators, api_bulk_schools
from apps.siteconfig.models import RegionConfig

User = get_user_model()
_MANAGER_HOST = "manager.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"])
class SuperBulkApiHttpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username=f"bulk_api_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(self.user, tier="break_glass")
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Bulk API School",
            slug="bulk-api-school",
            subdomain="bulk-api-school",
            is_active=True,
            default_region=self.region,
        )
        self.operator_target = User.objects.create_user(
            username=f"bulk_api_target_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(self.operator_target, tier="support")
        PlatformOperatorProfile.objects.filter(user=self.operator_target).update(
            status=PlatformOperatorProfile.Status.ACTIVE
        )

    def _post(self, view, path: str, payload: dict):
        request = self.factory.post(
            path,
            data=json.dumps(payload).encode(),
            content_type="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.user
        request.public_host_kind = "manager"
        return view(request)

    def test_bulk_schools_freeze_returns_json(self):
        response = self._post(
            api_bulk_schools,
            "/super/api/bulk/schools/",
            {
                "action": "freeze",
                "reason": "STORAGE",
                "ids": [str(self.school.pk)],
            },
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("succeeded"), 1)
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_frozen)

    def test_bulk_operators_suspend_returns_json(self):
        response = self._post(
            api_bulk_operators,
            "/super/api/bulk/operators/",
            {"action": "suspend", "ids": [self.operator_target.pk]},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get("ok"))
        profile = PlatformOperatorProfile.objects.get(user=self.operator_target)
        self.assertEqual(profile.status, PlatformOperatorProfile.Status.SUSPENDED)

    def test_bulk_schools_export_requires_confirm_phrase(self):
        response = self._post(
            api_bulk_schools,
            "/super/api/bulk/schools/",
            {"action": "export", "ids": [str(self.school.pk)]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("EXPORT TENANTS", json.loads(response.content).get("error", ""))
