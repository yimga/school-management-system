"""The daily billing beat must actually be able to mark a tenant PAST_DUE.

``_advance_subscription_billing`` anchored delinquency on the very field the
same call advances: it captured ``due_anchor = subscription.current_period_end``
at the top, rolled ``current_period_end`` forward by one cycle when the period
renewed, and computed ``overdue_threshold = due_anchor + grace_days``.

Run once a day -- the way the scheduler runs it -- that anchor is ALWAYS in the
future. A monthly subscription with period 2026-01-01 -> 2026-02-01 that never
pays: on 2026-02-01 the renewal posts and the threshold is 2026-02-08 (not
reached); on every day after, ``current_period_end`` is already 2026-03-01, so
the threshold is 2026-03-08 -- a whole cycle away, forever. The tenant never
went PAST_DUE, ``BillingAccount.delinquent_since`` was never set, so
``reconcile_subscription_entitlements`` never mirrored the state onto the
account, ``FinanceSubscriptionGateMiddleware`` never returned 402, and
``run_subscription_dunning_reminders`` (which requires PAST_DUE/SUSPENDED with a
set ``delinquent_since``) never fired a single rung. The whole dunning ladder
was dead for every non-paying tenant.

The state only fired if a sweep SKIPPED a period boundary by more than
grace_days -- which is exactly the shape of
``test_run_platform_billing_lifecycle_marks_overdue_subscriptions_suspended``,
so the suite was green over a dead beat. This test runs the beat once per
simulated day, which is what production does.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import (
    BillingAccount,
    PlatformLedgerEntry,
    TenantSubscription,
)
from apps.billing.services import (
    ensure_subscription_for_school,
    platform_account_balance,
    run_platform_billing_lifecycle,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan

GRACE_DAYS = 7
SUSPENSION_DAYS = 30
BEAT_DAYS = 46


class DailyBeatDelinquencyTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Beat Growth",
            slug="beat-growth",
            base_price=Decimal("199.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Beat School",
            slug="beat-school",
            subdomain="beat-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )
        self.account, self.subscription, _ = ensure_subscription_for_school(self.school)
        # Period rolls over on day 0 of the simulation and is never paid.
        self.day_zero = timezone.now() - timedelta(days=90)
        self.subscription.status = TenantSubscription.Status.ACTIVE
        self.subscription.billing_cycle = TenantSubscription.BillingCycle.MONTHLY
        self.subscription.current_period_start = self.day_zero - timedelta(days=30)
        self.subscription.current_period_end = self.day_zero
        self.subscription.billed_amount = Decimal("199.00")
        self.subscription.save(
            update_fields=[
                "status",
                "billing_cycle",
                "current_period_start",
                "current_period_end",
                "billed_amount",
                "updated_at",
            ]
        )

    def _run_daily_beat(self, days=BEAT_DAYS):
        """Run the lifecycle once per simulated day; return {day: status}."""
        statuses = {}
        for day in range(days):
            summary = run_platform_billing_lifecycle(
                as_of=self.day_zero + timedelta(days=day),
                grace_days=GRACE_DAYS,
                suspension_days=SUSPENSION_DAYS,
            )
            # Vacuity guard: the fleet single-flight lock must not have
            # swallowed a beat -- a skipped run advances nothing and would make
            # a "never past due" result meaningless.
            self.assertNotIn("skipped", summary, f"day {day} beat was skipped")
            self.subscription.refresh_from_db()
            statuses[day] = self.subscription.status
        return statuses

    def test_daily_beat_marks_the_tenant_past_due_then_suspended(self):
        statuses = self._run_daily_beat()

        # Vacuity guards: the beat really billed, and the money really is owed.
        # Without these, "PAST_DUE" could be reached by a subscription that owes
        # nothing at all.
        self.assertGreaterEqual(
            PlatformLedgerEntry.objects.filter(
                billing_account=self.account,
                entry_type=PlatformLedgerEntry.EntryType.CHARGE,
                source="billing_lifecycle",
                status=PlatformLedgerEntry.Status.POSTED,
            ).count(),
            1,
            "the sweep never posted a renewal charge",
        )
        self.assertGreater(platform_account_balance(self.account), Decimal("0.00"))

        self.assertEqual(
            statuses[GRACE_DAYS - 1],
            TenantSubscription.Status.ACTIVE,
            "must stay ACTIVE inside the grace window",
        )
        self.assertEqual(
            statuses[GRACE_DAYS + 3],
            TenantSubscription.Status.PAST_DUE,
            "an unpaid charge past the grace window must go PAST_DUE",
        )
        self.assertEqual(
            statuses[BEAT_DAYS - 1],
            TenantSubscription.Status.SUSPENDED,
            "an unpaid charge past the suspension window must SUSPEND",
        )

        self.account.refresh_from_db()
        self.assertIsNotNone(
            self.account.delinquent_since,
            "delinquent_since gates the dunning ladder and the 402 middleware",
        )
        self.assertEqual(self.account.status, BillingAccount.Status.SUSPENDED)

    def test_a_paying_tenant_is_never_marked_delinquent_by_the_beat(self):
        # Guard against over-fixing: settle each charge as it lands and the
        # tenant must sail through all 46 beats untouched.
        statuses = {}
        for day in range(BEAT_DAYS):
            run_platform_billing_lifecycle(
                as_of=self.day_zero + timedelta(days=day),
                grace_days=GRACE_DAYS,
                suspension_days=SUSPENSION_DAYS,
            )
            outstanding = platform_account_balance(self.account)
            if outstanding > Decimal("0.00"):
                PlatformLedgerEntry.objects.create(
                    billing_account=self.account,
                    school=self.school,
                    entry_type=PlatformLedgerEntry.EntryType.CREDIT,
                    status=PlatformLedgerEntry.Status.POSTED,
                    amount=outstanding,
                    currency_code=self.account.currency_code,
                    reference=f"PAY-BEAT-{day}",
                    source="payments",
                    happened_at=self.day_zero + timedelta(days=day),
                )
            self.subscription.refresh_from_db()
            statuses[day] = self.subscription.status

        self.assertEqual(platform_account_balance(self.account), Decimal("0.00"))
        self.assertNotIn(TenantSubscription.Status.PAST_DUE, statuses.values())
        self.assertNotIn(TenantSubscription.Status.SUSPENDED, statuses.values())
        self.account.refresh_from_db()
        self.assertIsNone(self.account.delinquent_since)
