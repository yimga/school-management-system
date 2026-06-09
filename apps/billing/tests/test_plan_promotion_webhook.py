"""Checkout webhook promotes school.plan from metadata."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.services import apply_processor_snapshot, ensure_subscription_for_school
from apps.siteconfig.models import Plan
from apps.schools.models import School


class PlanPromotionWebhookTests(TestCase):
    def setUp(self):
        self.basic = Plan.objects.create(
            name="Basic", slug="basic-plan", is_active=True
        )
        self.growth = Plan.objects.create(
            name="Growth", slug="growth-plan", is_active=True
        )
        self.school = School.objects.create(
            name="Promo School",
            slug="promo-school",
            subdomain="promo-school",
            is_active=True,
            plan=self.basic,
        )

    def test_checkout_completed_promotes_school_plan(self):
        payload = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "plan_code": "growth-plan",
                        "school_id": str(self.school.pk),
                    },
                    "customer": "cus_test",
                    "subscription": "sub_test",
                    "amount_total": 2900,
                    "currency": "usd",
                }
            },
        }
        apply_processor_snapshot(
            school=self.school,
            processor_code="stripe",
            event_type="checkout.session.completed",
            account_status="active",
            subscription_status="active",
            external_customer_ref="cus_test",
            external_subscription_ref="sub_test",
            billed_amount=Decimal("29.00"),
            happened_at=timezone.now(),
            payload=payload,
        )
        self.school.refresh_from_db()
        self.assertEqual(self.school.plan_id, self.growth.pk)
        _, subscription, _ = ensure_subscription_for_school(self.school)
        self.assertEqual(subscription.plan_id, self.growth.pk)
