"""Regression: the GDPR offboarding-confirmation notice must carry a real address.

``notify_offboarding_confirmed`` captures the tenant admin's address BEFORE the
purge wipes it. It read ``school.signupverification`` — but the reverse accessor
is ``signup_verification`` (see ``SignupVerification.school``'s ``related_name``),
so ``getattr`` returned the default on every call and the published payload
carried ``admin_email: ""``. The recipient resolver skips an empty address, so
the notice reached nobody.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.lifecycle.services_offboarding import notify_offboarding_confirmed
from apps.schools.models import School, SignupVerification


class OffboardingConfirmationEmailTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Offboard Notice {tag}",
            slug=f"offboard-notice-{tag}",
            subdomain=f"offboard-notice-{tag}",
        )
        self.admin_email = f"owner-{tag}@example.com"

    def _publish(self, school):
        """Run the notifier, returning (returned, publish_mock)."""
        event = SimpleNamespace(
            event_type="OFFBOARDING_PURGE_REQUESTED", school=school
        )
        with patch(
            "apps.platform_runtime.event_bus.publish_event", return_value=object()
        ) as mock_publish:
            returned = notify_offboarding_confirmed(event)
        return returned, mock_publish

    def test_publishes_admin_email_from_signup_verification(self):
        SignupVerification.objects.create(
            school=self.school,
            email=self.admin_email,
            expires_at=timezone.now() + timedelta(days=7),
        )
        returned, mock_publish = self._publish(self.school)

        self.assertTrue(returned)
        # Reached the publish call at all (a swallowed exception would also
        # return False, so pin the call itself, not just the return value).
        mock_publish.assert_called_once()
        args, kwargs = mock_publish.call_args
        self.assertEqual(args[0], "tenant.offboarding.confirmed")
        self.assertEqual(args[1]["admin_email"], self.admin_email)

    def test_school_without_signup_verification_still_publishes_blank(self):
        """Control: the assertion above measures the accessor, not the publish."""
        returned, mock_publish = self._publish(self.school)

        self.assertTrue(returned)
        mock_publish.assert_called_once()
        self.assertEqual(mock_publish.call_args[0][1]["admin_email"], "")
