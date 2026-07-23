"""The no-run provisioning fallback must be HONEST, not a fake climbing bar.

When a STARTED event exists but no ``WorkflowRun`` does, ``resolve_provisioning_progress``
falls back to a time-based estimate. Two regressions are sealed here:

  1. The old denominator was 180s, so at ~95s the bar read 53% ("Preparing your
     campus workspace") and raced to 85% in under 3 minutes — implying progress
     that was not happening. It now tracks the real 600s migrate budget
     (``begin_run(expected_duration_seconds=600)``), so early polls read an honest
     low percentage.
  2. Past the full budget with STILL no run, the fallback used to keep sitting at
     85% forever. It now surfaces ``stuck=True`` so the owner poll renders the
     "needs attention" panel + retry button (rmc-tenant-provision-progress.js
     already keys that UI on ``stuck === true``).
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.schools.models import School, SchoolProvisioningEvent
from apps.schools.provisioning_progress import (
    _PROVISION_EXPECTED_SECONDS,
    resolve_provisioning_progress,
)


class ProvisioningProgressHonestyTests(TestCase):
    def _school_started_ago(self, age_seconds: int) -> School:
        tag = f"honesty-{age_seconds}"
        school = School.objects.create(
            name="Honesty", slug=tag, subdomain=tag, is_active=False
        )
        ev = SchoolProvisioningEvent.objects.create(
            school=school, event_type="STARTED", status="INFO", message=""
        )
        # Bypass auto_now_add to backdate the STARTED event.
        SchoolProvisioningEvent.objects.filter(pk=ev.pk).update(
            created_at=timezone.now() - timedelta(seconds=age_seconds)
        )
        return school

    def test_no_run_past_budget_is_honestly_stuck(self):
        school = self._school_started_ago(_PROVISION_EXPECTED_SECONDS + 120)
        payload = resolve_provisioning_progress(school)
        self.assertIsNone(payload["workflow_run_id"], "precondition: no WorkflowRun")
        self.assertTrue(
            payload["stuck"],
            "STARTED + no run past the expected budget must surface stuck so the "
            "owner sees the retry affordance instead of a frozen fake bar",
        )

    def test_early_no_run_is_not_stuck_and_not_53_percent(self):
        school = self._school_started_ago(95)
        payload = resolve_provisioning_progress(school)
        self.assertIsNone(payload["workflow_run_id"])
        self.assertFalse(payload["stuck"], "an early no-run poll is not yet stuck")
        # The old 180s denominator put age=95 at 53%; the real 600s budget is far
        # lower. Guards against reverting to the fake fast bar.
        self.assertLess(
            payload["progress_percent"],
            40,
            "early progress must track the real 600s budget, not the old 180s race",
        )

    def test_no_started_event_is_zero_and_not_stuck(self):
        school = School.objects.create(
            name="Fresh", slug="honesty-fresh", subdomain="honesty-fresh", is_active=False
        )
        payload = resolve_provisioning_progress(school)
        self.assertFalse(payload["stuck"])
        self.assertEqual(payload["progress_percent"], 0)
