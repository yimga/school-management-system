"""Unit tests for unified fleet status resolver."""
from __future__ import annotations

from django.test import TestCase

from apps.billing.models import BillingAccount, TenantSubscription
from apps.schools.fleet_status import (
    HEATMAP_TIERS,
    resolve_fleet_summary,
    resolve_school_fleet_status,
)
from apps.schools.models import School


class FleetStatusResolverTests(TestCase):
    def _school(self, **kwargs):
        defaults = {
            "name": "Fleet Test School",
            "slug": "fleet-test-school",
            "subdomain": "fleet-test-school",
            "is_active": True,
            "is_approved": True,
        }
        defaults.update(kwargs)
        return School.objects.create(**defaults)

    def test_active_approved_school_is_live_healthy(self):
        school = self._school()
        row = resolve_school_fleet_status(school)
        self.assertEqual(row["fleet_state"], "live")
        self.assertEqual(row["heatmap_tier"], "healthy")

    def test_inactive_school_is_idle(self):
        school = self._school(is_active=False)
        row = resolve_school_fleet_status(school)
        self.assertEqual(row["fleet_state"], "inactive")
        self.assertEqual(row["heatmap_tier"], "idle")

    def test_frozen_school_is_suspended_danger(self):
        school = self._school(is_frozen=True, frozen_reason="STORAGE")
        row = resolve_school_fleet_status(school)
        self.assertEqual(row["fleet_state"], "suspended")
        self.assertEqual(row["heatmap_tier"], "danger")

    def test_pending_approval_is_warn(self):
        school = self._school(is_approved=False)
        row = resolve_school_fleet_status(school)
        self.assertEqual(row["fleet_state"], "pending_approval")
        self.assertEqual(row["heatmap_tier"], "warn")

    def test_billing_exception_is_danger(self):
        school = self._school()
        account = BillingAccount.objects.create(school=school, status=BillingAccount.Status.ACTIVE)
        TenantSubscription.objects.create(
            school=school,
            billing_account=account,
            status=TenantSubscription.Status.PAST_DUE,
            billed_amount=0,
        )
        row = resolve_school_fleet_status(school)
        self.assertEqual(row["fleet_state"], "billing_exception")
        self.assertEqual(row["heatmap_tier"], "danger")

    def test_fleet_summary_counts_all_tiers(self):
        self._school(slug="live-a", subdomain="live-a")
        self._school(slug="idle-a", subdomain="idle-a", is_active=False)
        summary = resolve_fleet_summary()
        self.assertGreaterEqual(summary["total"], 2)
        for tier in HEATMAP_TIERS:
            self.assertIn(tier, summary["tier_counts"])
