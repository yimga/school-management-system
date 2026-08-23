"""Regression: auto-ticket rules must not re-open the same ticket every beat.

``customersuccess.run_auto_ticket_rules`` runs every 10 minutes while the rules
select source rows over a 24-hour window, so one unhealthy tenant produced 144
identical FeedbackSubmission rows a day and buried the support inbox.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.customersuccess.auto_ticket_runner import run_all_rules
from apps.customersuccess.models import AutoTicketRule, TenantHealthScore
from apps.feedback.models import FeedbackSubmission
from apps.schools.models import School


class AutoTicketRuleDedupTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Auto Ticket {tag}",
            slug=f"auto-ticket-{tag}",
            subdomain=f"auto-ticket-{tag}",
            is_active=True,
        )
        self.rule = AutoTicketRule.objects.create(
            name=f"Health below 50 {tag}",
            trigger=AutoTicketRule.Trigger.HEALTH_BELOW,
            config={"threshold": 50},
            is_active=True,
        )
        self.health = TenantHealthScore.objects.create(
            school=self.school,
            score=Decimal("43.00"),
            dimensions={"activity": 20},
            computed_at=timezone.now(),
        )

    def _tickets(self):
        return FeedbackSubmission.objects.filter(school=self.school)

    def test_second_run_opens_no_duplicate(self):
        counts = run_all_rules()
        # Vacuity guard: the rule really fired and really wrote a row — without
        # this, "still 1 ticket" would also pass against a rule that never runs.
        self.assertEqual(counts.get(self.rule.name), 1)
        self.assertEqual(self._tickets().count(), 1)

        counts_again = run_all_rules()

        self.assertEqual(counts_again.get(self.rule.name), 0)
        self.assertEqual(self._tickets().count(), 1)

    def test_a_new_health_score_row_still_opens_its_own_ticket(self):
        """Dedup is per source row, not a blanket 'never fire twice'."""
        run_all_rules()
        self.assertEqual(self._tickets().count(), 1)

        TenantHealthScore.objects.create(
            school=self.school,
            score=Decimal("41.00"),
            dimensions={"activity": 15},
            computed_at=timezone.now(),
        )
        run_all_rules()

        self.assertEqual(self._tickets().count(), 2)
