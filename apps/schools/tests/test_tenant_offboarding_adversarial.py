"""Phase 12 — adversarial tenant isolation for offboarding paths."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.models import School, SchoolMembership, SchoolProvisioningEvent
from apps.schools.super_views_tenant_offboarding import (
    api_school_offboarding,
    api_school_offboarding_purge,
)
from apps.schools.tenant_offboarding import request_self_service_closure
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*"],
    TENANT_SELF_SERVICE_OFFBOARDING_ENABLED="1",
    TENANT_AUTO_PURGE_ENABLED="1",
)
class TenantOffboardingAdversarialTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.region = RegionConfig.get_default()
        self.school_a = School.objects.create(
            name="Alpha School",
            slug="alpha-adversarial",
            subdomain="alpha-adversarial",
            is_active=True,
            default_region=self.region,
        )
        self.school_b = School.objects.create(
            name="Beta School",
            slug="beta-adversarial",
            subdomain="beta-adversarial",
            is_active=True,
            default_region=self.region,
        )
        self.owner_a = User.objects.create_user(
            username="owner_alpha",
            email="owner@alpha-adversarial.test",
            password="testpass123",
        )
        self.owner_b = User.objects.create_user(
            username="owner_beta",
            email="owner@beta-adversarial.test",
            password="testpass123",
        )
        SchoolMembership.objects.create(
            school=self.school_a,
            user=self.owner_a,
            role="ADMIN",
            is_primary=True,
        )
        SchoolMembership.objects.create(
            school=self.school_b,
            user=self.owner_b,
            role="ADMIN",
            is_primary=True,
        )
        self.staff = User.objects.create_superuser(
            username="offboard_staff",
            email="staff@example.com",
            password="testpass123",
        )

    def test_non_staff_cannot_purge_via_manager_api(self):
        request = self.factory.post(
            f"/super/api/schools/{self.school_a.id}/offboarding/purge/",
            data=json.dumps(
                {"confirm_slug": self.school_a.slug, "dry_run": True}
            ).encode(),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.owner_a
        request.public_host_kind = "manager"
        response = api_school_offboarding_purge(request, school_id=self.school_a.id)
        self.assertIn(response.status_code, (403, 302))

    def test_purge_slug_mismatch_blocks_even_for_staff(self):
        request = self.factory.post(
            f"/super/api/schools/{self.school_a.id}/offboarding/purge/",
            data=json.dumps({"confirm_slug": self.school_b.slug, "dry_run": True}).encode(),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.staff
        request.public_host_kind = "manager"
        response = api_school_offboarding_purge(request, school_id=self.school_a.id)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        preview = body.get("preview", {})
        self.assertIn("confirm_slug_mismatch", preview.get("purge_blocked_reasons", []))

    def test_self_service_closure_scoped_to_target_school(self):
        request_self_service_closure(
            self.school_a,
            actor=self.owner_a,
            acknowledge=True,
        )

        self.school_a.refresh_from_db()
        self.school_b.refresh_from_db()
        self.assertFalse(self.school_a.is_active)
        self.assertTrue(self.school_b.is_active)
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school_a,
                event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_SELF_SERVICE_REQUESTED,
            ).exists()
        )
        self.assertFalse(
            SchoolProvisioningEvent.objects.filter(
                school=self.school_b,
                event_type=SchoolProvisioningEvent.EventType.OFFBOARDING_SELF_SERVICE_REQUESTED,
            ).exists()
        )

    def test_offboarding_snapshot_never_leaks_other_tenant_slug_in_path(self):
        request = self.factory.get(
            f"/super/api/schools/{self.school_a.id}/offboarding/",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.staff
        request.public_host_kind = "manager"
        response = api_school_offboarding(request, school_id=self.school_a.id)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body.get("school_slug"), self.school_a.slug)
        self.assertNotEqual(body.get("school_slug"), self.school_b.slug)

    @patch("apps.schools.tenant_offboarding.drop_tenant_schema_for_school", return_value=None)
    def test_apply_purge_slug_must_match_url_school(self, _mock_drop):
        request = self.factory.post(
            f"/super/api/schools/{self.school_b.id}/offboarding/purge/",
            data=json.dumps(
                {
                    "confirm_slug": self.school_a.slug,
                    "dry_run": True,
                }
            ).encode(),
            content_type="application/json",
            HTTP_HOST="manager.runmycampus.com",
        )
        request.user = self.staff
        request.public_host_kind = "manager"
        response = api_school_offboarding_purge(request, school_id=self.school_b.id)
        self.assertIn(response.status_code, (200, 400))
        body = json.loads(response.content)
        if response.status_code == 200:
            preview = body.get("preview", {})
            self.assertIn("confirm_slug_mismatch", preview.get("purge_blocked_reasons", []))
        else:
            self.assertFalse(body.get("ok", True))
