"""Operator copilot Lens API — health snapshot + requeue provisioning."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.platform_runtime.operator_identity import ensure_platform_operator_profile
from apps.schools.models import School
from apps.schools.super_views_school_api import (
    api_school_lens_snapshot,
    api_school_requeue_provision,
)
from apps.schools.super_views_operator_team import api_operator_lens_snapshot
from apps.siteconfig.models import RegionConfig

User = get_user_model()
_MANAGER_HOST = "manager.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"])
class OperatorSchoolLensApiTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username=f"lens_api_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(self.user, tier="break_glass")
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Lens API School",
            slug="lens-api-school",
            subdomain="lens-api-school",
            is_active=False,
            default_region=self.region,
        )

    def _get(self, view, school_id):
        request = self.factory.get(
            f"/super/api/schools/{school_id}/lens/",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.user
        return view(request, school_id=school_id)

    def _post(self, view, school_id):
        request = self.factory.post(
            f"/super/api/schools/{school_id}/requeue-provision/",
            data="{}",
            content_type="application/json",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.user
        return view(request, school_id=school_id)

    def test_lens_snapshot_includes_health_and_train(self):
        response = self._get(api_school_lens_snapshot, self.school.id)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertTrue(payload.get("ok"))
        self.assertIn("health_chips", payload)
        self.assertGreaterEqual(len(payload["health_chips"]), 2)
        prov = payload.get("provisioning") or {}
        self.assertIn("extended_steps", prov)
        self.assertEqual(len(prov["extended_steps"]), 14)
        self.assertIn("can_requeue", prov)

    @patch("apps.schools.tasks.kick_complete_provisioning_background")
    def test_requeue_provision_for_inactive_school(self, kick_mock):
        response = self._post(api_school_requeue_provision, self.school.id)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertTrue(payload.get("ok"))
        self.assertIn("lens", payload)
        kick_mock.assert_called_once()

    def test_requeue_rejects_active_portal_ready_school(self):
        self.school.is_active = True
        self.school.save(update_fields=["is_active"])
        response = self._post(api_school_requeue_provision, self.school.id)
        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertFalse(payload.get("ok"))


@override_settings(ALLOWED_HOSTS=["*"])
class OperatorTeamLensApiTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.viewer = User.objects.create_user(
            username=f"team_lens_viewer_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        ensure_platform_operator_profile(self.viewer, tier="break_glass")
        self.operator = User.objects.create_user(
            username=f"team_lens_target_{uuid.uuid4().hex[:8]}",
            password="testpass123",
            is_staff=True,
        )
        ensure_platform_operator_profile(self.operator, tier="support")

    def _get(self, user_id):
        request = self.factory.get(
            f"/super/team/{user_id}/lens/",
            HTTP_HOST=_MANAGER_HOST,
        )
        request.user = self.viewer
        return api_operator_lens_snapshot(request, user_id=user_id)

    def test_operator_lens_snapshot_health_chips_no_provisioning(self):
        response = self._get(self.operator.id)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertTrue(payload.get("ok"))
        self.assertIn("health_chips", payload)
        self.assertGreaterEqual(len(payload["health_chips"]), 3)
        self.assertNotIn("provisioning", payload)
        self.assertIn("operator", payload)

    def test_operator_lens_rejects_non_operator_user(self):
        outsider = User.objects.create_user(
            username=f"not_operator_{uuid.uuid4().hex[:8]}",
            password="testpass123",
        )
        response = self._get(outsider.id)
        self.assertEqual(response.status_code, 404)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertFalse(payload.get("ok"))
