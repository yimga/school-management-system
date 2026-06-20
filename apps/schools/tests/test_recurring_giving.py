from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.schools.models import (
    AdvancementDonor,
    DonationPledge,
    RecurringDonationSchedule,
    School,
)
from apps.schools.recurring_giving_services import (
    _advance,
    mint_due_recurring_pledges,
    mint_pledge_for_schedule,
)


class RecurringGivingTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Recurring School", slug="recurring-school",
            subdomain="recurring-school", is_active=True,
        )
        self.donor = AdvancementDonor.objects.create(
            school=self.school, display_name="Monthly Donor"
        )

    def _schedule(self, **kw):
        today = date(2026, 1, 15)
        defaults = dict(
            school=self.school, donor=self.donor, amount=Decimal("50.00"),
            currency="USD", frequency=RecurringDonationSchedule.Frequency.MONTHLY,
            start_date=today, next_run_date=today,
        )
        defaults.update(kw)
        return RecurringDonationSchedule.objects.create(**defaults)

    def test_mint_creates_pledge_and_advances(self):
        s = self._schedule()
        res = mint_pledge_for_schedule(s, on_date=date(2026, 1, 15))
        self.assertTrue(res["ok"])
        s.refresh_from_db()
        self.assertEqual(s.pledges_created, 1)
        self.assertEqual(s.next_run_date, date(2026, 2, 15))
        pledge = DonationPledge.objects.get(pk=res["pledge_id"])
        self.assertEqual(pledge.amount, Decimal("50.00"))
        self.assertEqual(pledge.due_date, date(2026, 1, 15))
        self.assertEqual(pledge.donor_id, self.donor.pk)

    def test_due_batch_only_mints_active_due(self):
        self._schedule(next_run_date=date(2026, 1, 10))  # due
        self._schedule(next_run_date=date(2099, 1, 1))  # future
        self._schedule(
            next_run_date=date(2026, 1, 1),
            status=RecurringDonationSchedule.Status.PAUSED,
        )  # paused
        res = mint_due_recurring_pledges(today=date(2026, 1, 15))
        self.assertEqual(res["minted"], 1)
        self.assertEqual(
            DonationPledge.objects.filter(school=self.school).count(), 1
        )

    def test_completes_after_end_date(self):
        s = self._schedule(end_date=date(2026, 1, 20))
        mint_pledge_for_schedule(s, on_date=date(2026, 1, 15))  # advances past end
        s.refresh_from_db()
        self.assertEqual(s.status, RecurringDonationSchedule.Status.COMPLETED)

    def test_paused_schedule_not_minted(self):
        s = self._schedule(status=RecurringDonationSchedule.Status.PAUSED)
        self.assertFalse(mint_pledge_for_schedule(s)["ok"])

    def test_month_end_is_clamped(self):
        # Jan 31 + 1 month must clamp to Feb 28 (2026 is not a leap year), never an
        # invalid date; quarterly from Mar 31 clamps to Jun 30.
        self.assertEqual(_advance(date(2026, 1, 31), "monthly"), date(2026, 2, 28))
        self.assertEqual(_advance(date(2026, 3, 31), "quarterly"), date(2026, 6, 30))
