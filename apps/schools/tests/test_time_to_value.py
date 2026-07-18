"""S1 Time-to-Value: per-tenant signup->operating clock + SLO predicate.

The SLO bar (PROMPT S §S8, row S1) is signup -> operating school in under one hour.
This proves the repo-side MEASUREMENT + predicate: the ``created_at``->``launched_at``
delta, that the < 1-hour gate FIRES when a tenant overruns, and that the readiness
payload surfaces it. The full browser signup->operating E2E proof remains external
(classified EXTERNAL_PROOF_REQUIRED) — this is the repo-side leg the audit demanded.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase

from apps.schools.models import School
from apps.schools.school_readiness import (
    TTV_SLO_MAX_MINUTES,
    _provisioning_slo,
    time_to_value_seconds,
    time_to_value_within_slo,
)
from apps.setup_studio.models import SetupProgress


class TimeToValueTests(TestCase):
    def _school(self, slug):
        return School.objects.create(name="TTV " + slug, slug=slug, subdomain=slug)

    def test_unlaunched_school_has_no_ttv(self):
        # An unlaunched tenant has no realized TTV yet — honestly None, not 0.
        school = self._school("ttv-unlaunched")
        self.assertIsNone(time_to_value_seconds(school))
        self.assertIsNone(time_to_value_within_slo(school))

    def test_launched_within_slo(self):
        school = self._school("ttv-fast")
        SetupProgress.objects.create(
            school=school, launched_at=school.created_at + timedelta(minutes=30)
        )
        self.assertEqual(time_to_value_seconds(school), 30 * 60)
        self.assertTrue(time_to_value_within_slo(school))

    def test_launched_over_one_hour_breaches_slo(self):
        # MUST-FIRE: a tenant that took 90 min to reach operating BREACHES the < 1h bar.
        # A predicate that could never return False would be a dead guard — this asserts
        # it actually fires on an over-SLO tenant.
        school = self._school("ttv-slow")
        SetupProgress.objects.create(
            school=school, launched_at=school.created_at + timedelta(minutes=90)
        )
        self.assertEqual(time_to_value_seconds(school), 90 * 60)
        self.assertFalse(time_to_value_within_slo(school))
        self.assertEqual(TTV_SLO_MAX_MINUTES, 60)

    def test_readiness_slo_payload_surfaces_ttv(self):
        # Proves the clock is WIRED into the customer-facing readiness payload, not dead.
        school = self._school("ttv-surfaced")
        SetupProgress.objects.create(
            school=school, launched_at=school.created_at + timedelta(minutes=15)
        )
        slo = _provisioning_slo({"status": "completed"}, school=school)
        self.assertEqual(slo["time_to_value_seconds"], 15 * 60)
        self.assertTrue(slo["within_ttv_slo"])
        self.assertEqual(slo["ttv_slo_minutes"], 60)

    def test_readiness_slo_payload_ttv_none_when_unlaunched(self):
        school = self._school("ttv-surfaced-none")
        slo = _provisioning_slo({"status": "provisioning"}, school=school)
        self.assertIsNone(slo["time_to_value_seconds"])
        self.assertIsNone(slo["within_ttv_slo"])
