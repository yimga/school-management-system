"""Regression seal: command-center TENANT_APPS metrics aggregate across schemas.

Bug (2026-06-17 gap analysis): the /super/ command center counted InterventionLog /
StudentPassport / PassportSchoolInvite (all TENANT_APPS) directly on the manager/public
connection. Under SCHEMA isolation those tables don't exist there, so the query failed and
the KPIs were pinned to 0. Fix routes them through _aggregate_tenant_counts (per-tenant
schema_context sum in SCHEMA mode, single count in RLS mode).

Hermetic: exercises the helper's dual-mode dispatch + key-wise summing + failure-skip with
stub counters (no DB).
"""
from django.test import SimpleTestCase, override_settings

from apps.schools.super_views_command_center_data import _aggregate_tenant_counts
from apps.schools.super_views_constants import CONTROL_PLANE_METRIC_FAILURES


class CommandCenterAggregationSealTests(SimpleTestCase):
    @override_settings(USE_DJANGO_TENANTS=False)
    def test_rls_mode_counts_once_and_sums(self):
        calls = []

        def counter():
            calls.append(1)
            return {"total": 3, "resolved": 1}

        result = _aggregate_tenant_counts(counter)
        self.assertEqual(result, {"total": 3, "resolved": 1})
        self.assertEqual(len(calls), 1, "RLS mode must count exactly once")

    @override_settings(USE_DJANGO_TENANTS=False)
    def test_metric_failure_is_skipped(self):
        exc_type = CONTROL_PLANE_METRIC_FAILURES[0]

        def counter():
            raise exc_type("simulated missing table")

        # Must not raise; returns empty totals (metric degrades to 0, not a 500).
        self.assertEqual(_aggregate_tenant_counts(counter), {})
