"""Tests for timezone-aware scheduled fee-invoice generation (B1)."""
from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.finance.scheduled_invoicing import (
    billing_period_key,
    is_invoice_generation_due,
    is_invoice_generation_due_for_school,
    is_local_billing_window,
    resolve_school_timezone,
    school_local_now,
)


class _SchoolStub:
    def __init__(self, tz: str = "Africa/Douala"):
        self.timezone = tz


class ScheduledInvoicingTests(SimpleTestCase):
    def test_monthly_due_on_clamped_february_day(self):
        schedule = {"mode": "monthly_day_of_month", "day_of_month": 31}
        self.assertTrue(
            is_invoice_generation_due(
                today=date(2026, 2, 28),
                schedule=schedule,
                academic_year_start=None,
                term_start=None,
            )
        )
        self.assertFalse(
            is_invoice_generation_due(
                today=date(2026, 2, 27),
                schedule=schedule,
                academic_year_start=None,
                term_start=None,
            )
        )

    def test_local_billing_window_requires_configured_hour(self):
        school = _SchoolStub("UTC")
        schedule = {
            "mode": "monthly_day_of_month",
            "day_of_month": 15,
            "local_hour": 6,
        }
        inside = datetime(2026, 6, 15, 6, 30, tzinfo=dt_timezone.utc)
        outside = datetime(2026, 6, 15, 7, 30, tzinfo=dt_timezone.utc)
        self.assertTrue(
            is_local_billing_window(school, schedule, now_utc=inside)
        )
        self.assertFalse(
            is_local_billing_window(school, schedule, now_utc=outside)
        )

    def test_due_for_school_respects_timezone_window(self):
        school = _SchoolStub("America/New_York")
        schedule = {
            "mode": "monthly_day_of_month",
            "day_of_month": 1,
            "local_hour": 6,
        }
        # 10:00 UTC = 06:00 EDT on Jun 1
        due_moment = datetime(2026, 6, 1, 10, 0, tzinfo=dt_timezone.utc)
        self.assertTrue(
            is_invoice_generation_due_for_school(
                school,
                schedule,
                academic_year_start=date(2025, 9, 1),
                term_start=None,
                now_utc=due_moment,
            )
        )

    def test_billing_period_key_monthly(self):
        school = _SchoolStub("UTC")
        key = billing_period_key(
            school,
            {"mode": "monthly_day_of_month", "day_of_month": 1},
            now_utc=datetime(2026, 6, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(key, "2026-06")

    def test_invalid_timezone_falls_back_to_utc(self):
        school = _SchoolStub("Not/A_Timezone")
        self.assertEqual(resolve_school_timezone(school), ZoneInfo("UTC"))

    def test_school_local_now_converts_utc(self):
        school = _SchoolStub("UTC")
        utc = datetime(2026, 1, 1, 0, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(school_local_now(school, now_utc=utc).hour, 0)

    @patch("apps.finance.scheduled_invoicing.monthly_invoice_already_run")
    def test_tasks_body_skips_when_period_already_run(self, already_run):
        from apps.automation.models import AutomationExecutionLog
        from apps.finance import tasks as finance_tasks

        already_run.return_value = True
        school = _SchoolStub()
        school.pk = 1
        school.id = 1
        school.is_active = True

        class _Year:
            start_date = date(2025, 9, 1)

        with patch.object(
            finance_tasks, "get_cached_site_settings", return_value=object()
        ), patch.object(
            finance_tasks, "_get_finance_runtime_config",
            return_value={
                "auto_generate_invoices_enabled": True,
                "auto_generate_schedule": {
                    "mode": "monthly_day_of_month",
                    "day_of_month": 1,
                    "local_hour": 6,
                },
                "auto_generate_due_date_offset_days": 30,
                "auto_generate_require_approval": False,
            },
        ), patch(
            "apps.automation.helpers.get_current_academic_year", return_value=_Year()
        ), patch(
            "apps.automation.helpers.get_current_term", return_value=None
        ), patch(
            "apps.schools.models.School.objects.filter"
        ) as school_filter, patch(
            "apps.finance.scheduled_invoicing.is_invoice_generation_due_for_school",
            return_value=True,
        ), patch(
            "apps.finance.scheduled_invoicing.billing_period_key",
            return_value="2026-06",
        ), patch.object(
            AutomationExecutionLog.objects, "create",
            return_value=AutomationExecutionLog(pk=99),
        ):
            school_filter.return_value.first.return_value = school
            result = finance_tasks._auto_generate_fee_invoices_body(
                False, school_id=1
            )
        self.assertEqual(result.get("status"), "already_run")
