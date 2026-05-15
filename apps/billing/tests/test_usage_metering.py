"""Wave C — G2: metering writer + usage_report tests."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import UsageMeter
from apps.billing.models_metering import (
    USAGE_DIMENSION_CODES,
    record,
    snapshot,
)
from apps.billing.usage_report import (
    QUOTA_DEFAULTS,
    current_period,
    over_quota,
    period as period_summary,
    quota_for,
    reset_today,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class UsageMeteringTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Use", slug="use", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="UM", name="UMland", timezone="UTC", default_currency="USD")

    def setUp(self):
        slug = f"meter-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name=f"Meter School {slug}", slug=slug, subdomain=slug, is_active=True,
            plan=self.plan, default_region=self.region, settings={},
        )

    def test_dimension_codes_canonical_set(self):
        for code in ("storage_bytes", "db_sessions", "api_calls", "ai_tokens", "marketplace_installs"):
            self.assertIn(code, USAGE_DIMENSION_CODES)

    def test_record_creates_first_row(self):
        record(self.school, "db_sessions", delta=1)
        rows = UsageMeter.objects.filter(school=self.school, metric_code="db_sessions")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().quantity, 1)

    def test_record_increments_existing_row_same_day(self):
        record(self.school, "api_calls", delta=5)
        record(self.school, "api_calls", delta=7)
        record(self.school, "api_calls", delta=3)
        row = UsageMeter.objects.get(school=self.school, metric_code="api_calls", period_start=timezone.now().date())
        self.assertEqual(row.quantity, 15)

    def test_record_silently_drops_unknown_dimension(self):
        record(self.school, "bogus_dim", delta=1)
        self.assertEqual(UsageMeter.objects.filter(school=self.school).count(), 0)

    def test_record_silently_drops_none_school(self):
        record(None, "db_sessions", delta=1)  # must not raise

    def test_snapshot_returns_zeros_for_unrecorded(self):
        snap = snapshot(self.school)
        self.assertEqual(set(snap.keys()), set(USAGE_DIMENSION_CODES))
        self.assertEqual(snap["storage_bytes"], 0)

    def test_snapshot_reflects_recorded_values(self):
        record(self.school, "storage_bytes", delta=1024)
        record(self.school, "ai_tokens", delta=42)
        snap = snapshot(self.school)
        self.assertEqual(snap["storage_bytes"], 1024)
        self.assertEqual(snap["ai_tokens"], 42)

    def test_current_period_aggregates_month_to_date(self):
        record(self.school, "api_calls", delta=10)
        record(self.school, "api_calls", delta=5)
        summary = current_period(self.school)
        self.assertEqual(summary["api_calls"], 15)
        self.assertEqual(summary["db_sessions"], 0)

    def test_period_window_filters_correctly(self):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        # Today
        record(self.school, "ai_tokens", delta=20)
        # Yesterday — manual row
        UsageMeter.objects.create(
            billing_account_id=UsageMeter.objects.first().billing_account_id,
            school=self.school,
            metric_code="ai_tokens",
            period_start=yesterday,
            period_end=yesterday,
            quantity=100,
        )
        summary_today = period_summary(self.school, today, today)
        summary_week = period_summary(self.school, yesterday, today)
        self.assertEqual(summary_today["ai_tokens"], 20)
        self.assertEqual(summary_week["ai_tokens"], 120)

    def test_default_quota_lookup(self):
        # No Entitlement row exists -> returns QUOTA_DEFAULTS value.
        self.assertEqual(quota_for(self.school, "db_sessions"), QUOTA_DEFAULTS["db_sessions"])

    def test_over_quota_flips_when_exceeded(self):
        # Record more sessions than the default quota allows.
        over, usage, quota = over_quota(self.school, "db_sessions")
        self.assertFalse(over)
        record(self.school, "db_sessions", delta=QUOTA_DEFAULTS["db_sessions"] + 5)
        over, usage, quota = over_quota(self.school, "db_sessions")
        self.assertTrue(over)
        self.assertGreater(usage, quota)

    def test_reset_today_clears_rows(self):
        record(self.school, "ai_tokens", delta=100)
        self.assertEqual(current_period(self.school)["ai_tokens"], 100)
        reset_today(self.school)
        self.assertEqual(current_period(self.school)["ai_tokens"], 0)
