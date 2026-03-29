"""Delegation auto-expire task: idempotent runs (batch 6 / SOT §11.4)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User, Delegation
from apps.accounts.tasks import _expire_past_delegations_body


class ExpirePastDelegationsTests(TestCase):
    def test_second_run_does_not_reprocess_already_inactive_delegations(self):
        now = timezone.now()
        delegator = User.objects.create_user(
            "delegator-exp", "dexp@test.com", "pass", role=User.Role.DEAN
        )
        d = Delegation.objects.create(
            delegator=delegator,
            delegate=User.objects.create_user(
                "delegate-exp", "delexp@test.com", "pass", role=User.Role.TEACHER
            ),
            start_date=now - timedelta(days=10),
            end_date=now - timedelta(days=1),
            is_active=True,
        )
        r1 = _expire_past_delegations_body()
        self.assertEqual(r1.get("expired"), 1)
        d.refresh_from_db()
        self.assertFalse(d.is_active)

        r2 = _expire_past_delegations_body()
        self.assertEqual(r2.get("expired"), 0)
        d.refresh_from_db()
        self.assertFalse(d.is_active)
