"""verify_signup must land a brand-new owner in the guided onboarding wizard —
even when provisioning is ASYNC (broker-backed), so the owner User is NOT
created in-request.

Regression for the 2026-06-08 production dead-end: on Render, ``CELERY_BROKER_URL``
is set, so ``dispatch_provision_school`` queues provisioning on a worker and the
owner User (created inside provisioning) does not exist yet at verify time →
``admin_user`` was None → the new owner was redirected to the login page instead
of the wizard. It "worked in dev" only because the broker-less dev box runs
provisioning synchronously, creating the User in-request. This test pins the
async case by mocking the dispatch to a no-op (worker hasn't run).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SignupVerification


@override_settings(RATELIMIT_ENABLE=False)
class VerifySignupOnboardingTests(TestCase):
    def setUp(self):
        cache.clear()

    def _pending(self, email="newowner@cedar.test"):
        school = School.objects.create(
            name="Cedar School",
            slug="cedar-vs",
            subdomain="cedar-vs",
            is_active=False,
            country_code="US",
        )
        verification = SignupVerification.objects.create(
            school=school,
            email=email,
            token=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(days=2),
        )
        return school, verification

    def test_async_provisioning_still_redirects_into_onboarding_wizard(self):
        _school, verification = self._pending()
        User = get_user_model()
        self.assertFalse(User.objects.filter(email=verification.email).exists())

        # Simulate ASYNC provisioning: dispatch queues to a worker that has not
        # run yet, so it creates NOTHING in-request (the prod failure mode).
        with mock.patch(
            "apps.schools.tasks.dispatch_provision_school",
            return_value={"queued": True},
        ):
            resp = self.client.get(
                reverse("verify_signup") + f"?token={verification.token}"
            )

        # verify_signup must create the owner row up-front itself...
        owner = User.objects.filter(email=verification.email).first()
        self.assertIsNotNone(owner, "owner account was not created at verify time")

        # ...and redirect INTO the onboarding wizard, never the login wall.
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/authentication/onboarding/account/", resp.url)
        self.assertNotIn("/authentication/login", resp.url)

    def test_owner_creation_is_idempotent_when_user_already_exists(self):
        # A retry / double-click must not create a second account or crash.
        _school, verification = self._pending(email="dupe@cedar.test")
        from apps.schools.tasks import ensure_admin_user_for_school

        u1, created1 = ensure_admin_user_for_school(_school, verification.email)
        u2, created2 = ensure_admin_user_for_school(_school, verification.email)
        self.assertEqual(u1.pk, u2.pk)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(
            get_user_model().objects.filter(email=verification.email).count(), 1
        )
