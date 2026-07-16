"""PAST_DUE must survive ensure_subscription_for_school.

Regression: ``_resolve_subscription_status`` derived status from the *school* row
alone and ``ensure_subscription_for_school`` wrote the result back unconditionally.
PAST_DUE is set by the renewal lifecycle from unpaid invoices and — unlike
SUSPENDED — does not set ``school.is_frozen``, so nothing on the school recorded
the debt and the resolver returned ACTIVE. Any read path that calls ensure_*
therefore cleared the tenant's own dunning state: a past-due tenant opening their
billing page silently absolved itself until the next nightly sweep re-set it.
"""

from decimal import Decimal

from django.test import TestCase

from apps.billing.models import TenantSubscription
from apps.billing.services import (
    _resolve_subscription_status,
    ensure_subscription_for_school,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan


class ResolveSubscriptionStatusTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="dunning-resolver", slug="dunning-resolver",
            subdomain="dunning-resolver", is_active=True,
        )

    def test_past_due_is_preserved(self):
        self.assertEqual(
            _resolve_subscription_status(
                self.school, current_status=TenantSubscription.Status.PAST_DUE
            ),
            TenantSubscription.Status.PAST_DUE,
        )

    def test_active_without_current_status_still_active(self):
        # Default arg must keep the historical behaviour for every other caller.
        self.assertEqual(
            _resolve_subscription_status(self.school),
            TenantSubscription.Status.ACTIVE,
        )

    def test_active_current_status_stays_active(self):
        self.assertEqual(
            _resolve_subscription_status(
                self.school, current_status=TenantSubscription.Status.ACTIVE
            ),
            TenantSubscription.Status.ACTIVE,
        )

    def test_frozen_school_suspends_even_when_past_due(self):
        # SUSPENDED is a harder state than PAST_DUE — freezing must still win,
        # otherwise the PAST_DUE guard would shadow a freeze.
        self.school.is_frozen = True
        self.school.save(update_fields=["is_frozen"])
        self.assertEqual(
            _resolve_subscription_status(
                self.school, current_status=TenantSubscription.Status.PAST_DUE
            ),
            TenantSubscription.Status.SUSPENDED,
        )


class EnsureSubscriptionPreservesDunningTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Free", slug="free", base_price=Decimal("0.00"),
            is_active=True, is_default=True,
        )
        self.school = School.objects.create(
            name="dunning-ensure", slug="dunning-ensure",
            subdomain="dunning-ensure", is_active=True,
        )

    def test_ensure_does_not_clear_past_due(self):
        _account, subscription, created = ensure_subscription_for_school(self.school)
        self.assertTrue(created)

        # The renewal lifecycle marks the tenant past due (unpaid invoice).
        subscription.status = TenantSubscription.Status.PAST_DUE
        subscription.save(update_fields=["status"])

        # The tenant opens their own billing page -> ensure_* runs on a read path.
        _account, subscription2, created2 = ensure_subscription_for_school(self.school)
        self.assertFalse(created2)
        self.assertEqual(subscription2.pk, subscription.pk)
        self.assertEqual(
            subscription2.status,
            TenantSubscription.Status.PAST_DUE,
            "ensure_subscription_for_school reset PAST_DUE -> ACTIVE; the tenant "
            "cleared its own dunning state by loading a page.",
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, TenantSubscription.Status.PAST_DUE)

    def test_ensure_still_suspends_a_frozen_past_due_tenant(self):
        _account, subscription, _created = ensure_subscription_for_school(self.school)
        subscription.status = TenantSubscription.Status.PAST_DUE
        subscription.save(update_fields=["status"])

        self.school.is_frozen = True
        self.school.save(update_fields=["is_frozen"])

        _account, subscription2, _created2 = ensure_subscription_for_school(self.school)
        self.assertEqual(subscription2.status, TenantSubscription.Status.SUSPENDED)

    def test_ensure_leaves_active_tenant_active(self):
        _account, subscription, _created = ensure_subscription_for_school(self.school)
        self.assertEqual(subscription.status, TenantSubscription.Status.ACTIVE)
        _account, subscription2, _created2 = ensure_subscription_for_school(self.school)
        self.assertEqual(subscription2.status, TenantSubscription.Status.ACTIVE)
