"""E2E signup verification token helper (CI-gated)."""

from __future__ import annotations

import os
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SignupVerification


@override_settings(ALLOWED_HOSTS=["*"])
class E2ESignupVerificationTokenTests(TestCase):
    def test_disabled_without_env_flag(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RMC_E2E_SIGNUP_HELPERS", None)
            resp = self.client.get(
                reverse("e2e_signup_verification_token"),
                {"email": "x@example.com"},
            )
        self.assertEqual(resp.status_code, 403)

    def test_returns_token_when_enabled(self) -> None:
        school = School.objects.create(
            name="Cold E2E",
            slug="e2e-cold-helper",
            subdomain="e2e-cold-helper",
            is_active=False,
        )
        email = "cold@runmycampus.test"
        verification = SignupVerification.objects.create(
            school=school,
            email=email,
            expires_at=timezone.now() + timedelta(days=1),
        )
        with patch.dict(os.environ, {"RMC_E2E_SIGNUP_HELPERS": "1"}, clear=False):
            resp = self.client.get(
                reverse("e2e_signup_verification_token"),
                {"email": email, "slug": school.slug},
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["token"], str(verification.token))
        self.assertEqual(data["slug"], school.slug)
