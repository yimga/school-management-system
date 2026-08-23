"""Regression: a day-N nudge may only be marked sent once it is really sent.

``deliver_onboarding_day_n_nudges`` used to call ``record_nudge_sent`` and
nothing else — no send path at all — so every nudge was written into
``School.settings['customersuccess']['nudges_sent']`` and thereby suppressed
forever, while the admin's inbox got nothing.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.customersuccess.onboarding_day_n_nudges import get_sent_markers
from apps.customersuccess.tasks import deliver_onboarding_day_n_nudges
from apps.schools.models import School, SignupVerification


class OnboardingNudgeDeliveryTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Nudge Delivery {tag}",
            slug=f"nudge-delivery-{tag}",
            subdomain=f"nudge-delivery-{tag}",
            is_active=True,
        )
        # ``School.created_at`` is auto_now_add, so it cannot be set on create();
        # without this the school is 0 days old, NO nudge is ever due and every
        # assertion below would pass against completely broken code.
        School.objects.filter(pk=self.school.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )
        self.school.refresh_from_db()
        self.admin_email = f"owner-{tag}@example.com"

    def _markers(self):
        self.school.refresh_from_db()
        return get_sent_markers(self.school.settings or {})

    def _add_recipient(self):
        SignupVerification.objects.create(
            school=self.school,
            email=self.admin_email,
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_undelivered_nudge_is_not_marked_sent(self):
        with patch(
            "apps.customersuccess.onboarding_day_n_nudges.deliver_nudge",
            return_value=False,
        ) as mock_deliver:
            result = deliver_onboarding_day_n_nudges(limit=200)

        # Proves nudges really were due for this school — otherwise "no markers
        # written" would pass against code that never evaluates anything.
        self.assertGreaterEqual(mock_deliver.call_count, 1)
        self.assertGreaterEqual(result["undelivered"], 1)
        self.assertEqual(result["sent"], 0)
        self.assertEqual(self._markers(), set())

    def test_delivered_nudge_reaches_the_admin_and_is_marked(self):
        self._add_recipient()
        mail.outbox = []

        result = deliver_onboarding_day_n_nudges(limit=200)

        self.assertGreaterEqual(result["sent"], 1)
        to_us = [m for m in mail.outbox if self.admin_email in m.to]
        self.assertTrue(to_us, "no nudge email reached the tenant admin")
        self.assertTrue(self._markers())

    def test_a_failed_send_does_not_burn_the_nudge(self):
        """The marker is permanent, so a transient failure must stay retryable."""
        with patch(
            "apps.customersuccess.onboarding_day_n_nudges.deliver_nudge",
            return_value=False,
        ):
            deliver_onboarding_day_n_nudges(limit=200)
        self.assertEqual(self._markers(), set())

        self._add_recipient()
        mail.outbox = []
        result = deliver_onboarding_day_n_nudges(limit=200)

        self.assertGreaterEqual(result["sent"], 1)
        self.assertTrue([m for m in mail.outbox if self.admin_email in m.to])
        self.assertTrue(self._markers())
