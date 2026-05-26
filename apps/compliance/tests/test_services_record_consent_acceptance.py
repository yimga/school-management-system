"""Tests for apps.compliance.services.record_consent_acceptance.

Shim called by the Unified Wizard Framework's parent-onboarding writer to land
a ConsentRecord per signed document on top of the cockpit cascade.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.compliance import services
from apps.compliance.models import ConsentRecord
from apps.schools.models import School


class RecordConsentAcceptanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Consent School",
            slug="consent-school",
            subdomain="consent-school",
            is_active=True,
        )
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="parent@example.com",
            email="parent@example.com",
            password="x",  # noqa: S106 — test fixture
        )

    def test_records_one_per_signed_document(self):
        written = services.record_consent_acceptance(
            school=self.school,
            payload={
                "privacy_policy": True,
                "data_residency_acknowledgment": True,
                "terms_of_service": True,
            },
            actor_user_id=self.user.pk,
        )
        self.assertEqual(written, 3)
        # tenant-isolation-allow: test-scoped-explicit-school-fk
        records = ConsentRecord.objects.filter(school=self.school, user=self.user)
        titles = sorted(r.title for r in records)
        self.assertEqual(
            titles,
            ["Data Residency Acknowledgment", "Privacy Policy", "Terms of Service"],
        )

    def test_only_truthy_keys_produce_records(self):
        written = services.record_consent_acceptance(
            school=self.school,
            payload={
                "privacy_policy": True,
                "data_residency_acknowledgment": False,
                "terms_of_service": True,
            },
            actor_user_id=self.user.pk,
        )
        self.assertEqual(written, 2)

    def test_unknown_keys_ignored(self):
        written = services.record_consent_acceptance(
            school=self.school,
            payload={"some_random_key": True, "privacy_policy": True},
            actor_user_id=self.user.pk,
        )
        self.assertEqual(written, 1)

    def test_no_op_inputs(self):
        self.assertEqual(
            services.record_consent_acceptance(school=None, payload={"privacy_policy": True}),
            0,
        )
        self.assertEqual(
            services.record_consent_acceptance(school=self.school, payload={}),
            0,
        )
        self.assertEqual(
            services.record_consent_acceptance(
                school=self.school,
                payload={"privacy_policy": True},
                actor_user_id=None,
            ),
            0,
        )
        self.assertEqual(
            services.record_consent_acceptance(
                school=self.school,
                payload={"privacy_policy": True},
                actor_user_id=99999999,
            ),
            0,
        )
