from decimal import Decimal

from django.test import TestCase

from apps.finance.models import AwardSource
from apps.schools.grant_services import (
    award_grant,
    close_grant,
    decline_grant,
    mark_under_review,
    open_grant_renewal,
    submit_grant,
)
from apps.schools.models import GrantApplication, GrantMilestone, School


class GrantLifecycleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Grant School", slug="grant-school",
            subdomain="grant-school", is_active=True,
        )
        self.source = AwardSource.objects.create(
            school=self.school, name="Building Fund",
            total_budget=Decimal("0.00"), remaining_funds=Decimal("0.00"),
            currency="USD",
        )

    def _grant(self, **kw):
        defaults = dict(
            school=self.school, funder_name="Big Foundation",
            program="Library build", requested_amount=Decimal("10000.00"),
            currency="USD",
        )
        defaults.update(kw)
        return GrantApplication.objects.create(**defaults)

    def test_submit_then_review(self):
        g = self._grant()
        self.assertTrue(submit_grant(g)["ok"])
        g.refresh_from_db()
        self.assertEqual(g.status, GrantApplication.Status.SUBMITTED)
        self.assertIsNotNone(g.submitted_at)
        self.assertTrue(mark_under_review(g)["ok"])
        g.refresh_from_db()
        self.assertEqual(g.status, GrantApplication.Status.UNDER_REVIEW)

    def test_cannot_submit_non_draft(self):
        g = self._grant(status=GrantApplication.Status.SUBMITTED)
        self.assertFalse(submit_grant(g)["ok"])

    def test_award_credits_fund_once(self):
        g = self._grant()
        res = award_grant(g, award_source_id=self.source.pk)
        self.assertTrue(res["ok"])
        g.refresh_from_db()
        self.assertEqual(g.status, GrantApplication.Status.AWARDED)
        self.assertEqual(g.awarded_amount, Decimal("10000.00"))
        self.assertIsNotNone(g.credited_to_fund_at)
        self.source.refresh_from_db()
        self.assertEqual(self.source.remaining_funds, Decimal("10000.00"))
        # Idempotent: re-award must not double-credit the fund.
        award_grant(g, award_source_id=self.source.pk)
        self.source.refresh_from_db()
        self.assertEqual(self.source.remaining_funds, Decimal("10000.00"))

    def test_award_without_source_just_awards(self):
        g = self._grant()
        res = award_grant(g, awarded_amount=Decimal("5000.00"))
        self.assertTrue(res["ok"])
        g.refresh_from_db()
        self.assertEqual(g.awarded_amount, Decimal("5000.00"))
        self.assertIsNone(g.credited_to_fund_at)

    def test_close_requires_milestones_done(self):
        g = self._grant()
        award_grant(g)
        GrantMilestone.objects.create(
            grant=g, title="Interim report", status=GrantMilestone.Status.PENDING
        )
        self.assertFalse(close_grant(g)["ok"])
        GrantMilestone.objects.filter(grant=g).update(
            status=GrantMilestone.Status.COMPLETED
        )
        g.refresh_from_db()
        self.assertTrue(close_grant(g)["ok"])
        g.refresh_from_db()
        self.assertEqual(g.status, GrantApplication.Status.CLOSED)

    def test_decline(self):
        g = self._grant()
        submit_grant(g)
        self.assertTrue(decline_grant(g, reason="Out of scope")["ok"])
        g.refresh_from_db()
        self.assertEqual(g.status, GrantApplication.Status.DECLINED)

    def test_renewal_links_back(self):
        g = self._grant()
        award_grant(g, awarded_amount=Decimal("8000.00"))
        res = open_grant_renewal(g)
        self.assertTrue(res["ok"])
        renewal = GrantApplication.objects.get(pk=res["renewal_id"])
        self.assertEqual(renewal.renewed_from_id, g.pk)
        self.assertEqual(renewal.requested_amount, Decimal("8000.00"))
        self.assertEqual(renewal.status, GrantApplication.Status.DRAFT)
