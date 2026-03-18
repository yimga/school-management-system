"""
World Engine: Tests for JIT impersonation consent views, emergency_broadcast_fanout, national_syllabus_sync.
"""

import json

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from apps.schools.models import School
from apps.siteconfig.models import BroadcastCampaign, RegionConfig
from apps.siteconfig.views_impersonation_consent import (
    grant_impersonation_consent,
    revoke_impersonation_consent,
)
from apps.siteconfig.tasks import national_syllabus_sync, emergency_broadcast_fanout

User = get_user_model()


def _response_json(response):
    return json.loads(response.content.decode("utf-8"))


class JITImpersonationConsentTests(TestCase):
    """Grant and revoke impersonation consent."""

    def setUp(self):
        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CM",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )
        self.school = School.objects.create(
            name="JIT Test School",
            slug="jit-test-school",
            subdomain="jit-test-school",
            is_active=True,
            default_region=self.region,
        )
        self.user = User.objects.create_user(
            username="admin_jit_test",
            email="admin@jit.test",
            password="testpass123",
            role="ADMIN",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_grant_consent_requires_school_context(self):
        """Without request.school, grant returns 400."""
        request = self.client.post(
            reverse("siteconfig:grant_impersonation_consent")
        ).wsgi_request
        request.user = self.user
        request.school = None
        response = grant_impersonation_consent(request)
        self.assertEqual(response.status_code, 400)
        data = _response_json(response)
        self.assertIn("ok", data)
        self.assertFalse(data["ok"])

    def test_grant_consent_sets_timestamp_and_granter(self):
        """With request.school, grant sets impersonation_consent_granted_at and _by."""
        request = self.client.post(
            reverse("siteconfig:grant_impersonation_consent")
        ).wsgi_request
        request.user = self.user
        request.school = self.school
        response = grant_impersonation_consent(request)
        self.assertEqual(response.status_code, 200)
        data = _response_json(response)
        self.assertTrue(data.get("ok"))
        self.school.refresh_from_db()
        self.assertIsNotNone(self.school.impersonation_consent_granted_at)
        self.assertEqual(self.school.impersonation_consent_granted_by_id, self.user.id)

    def test_revoke_consent_clears_fields(self):
        """Revoke clears consent_at and consent_by."""
        self.school.impersonation_consent_granted_at = timezone.now()
        self.school.impersonation_consent_granted_by_id = self.user.id
        self.school.save(
            update_fields=[
                "impersonation_consent_granted_at",
                "impersonation_consent_granted_by_id",
            ]
        )
        request = self.client.post(
            reverse("siteconfig:revoke_impersonation_consent")
        ).wsgi_request
        request.user = self.user
        request.school = self.school
        response = revoke_impersonation_consent(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_json(response).get("ok"))
        self.school.refresh_from_db()
        self.assertIsNone(self.school.impersonation_consent_granted_at)
        self.assertIsNone(self.school.impersonation_consent_granted_by_id)


class NationalSyllabusSyncTaskTests(TestCase):
    """national_syllabus_sync returns expected stub structure."""

    def test_returns_country_code_and_status(self):
        result = national_syllabus_sync("CM")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("country_code"), "CM")
        self.assertIn("status", result)
        self.assertIn("syllabus_nodes", result)

    def test_syllabus_nodes_count(self):
        result = national_syllabus_sync("US")
        self.assertIsInstance(result.get("syllabus_nodes"), int)


class EmergencyBroadcastFanoutTaskTests(TestCase):
    """emergency_broadcast_fanout with mock campaign."""

    def setUp(self):
        self.region = RegionConfig.objects.first()
        if not self.region:
            self.region = RegionConfig.objects.create(
                code="CM",
                name="Cameroon",
                default_language="en",
                timezone="Africa/Douala",
            )
        self.campaign = BroadcastCampaign.objects.create(
            subject="Test Alert",
            body="Test body",
            status=BroadcastCampaign.Status.QUEUED,
            slide_confirm_required=True,
        )

    def test_campaign_not_found_returns_error(self):
        result = emergency_broadcast_fanout.run(999999, [])
        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("error"), "campaign_not_found")

    def test_with_campaign_returns_ok_and_batches(self):
        result = emergency_broadcast_fanout.run(self.campaign.pk, [1, 2, 3, 4, 5])
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("campaign_id"), self.campaign.pk)
        self.assertIn("batches", result)
        self.assertEqual(result["batches"], 1)

    def test_large_recipient_list_chunks(self):
        ids = list(range(250))
        result = emergency_broadcast_fanout.run(self.campaign.pk, ids)
        self.assertTrue(result.get("ok"))
        self.assertEqual(result["batches"], 3)
