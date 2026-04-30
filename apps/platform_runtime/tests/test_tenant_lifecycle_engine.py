"""Canonical lifecycle phases, health dimensions, and retention helpers."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.tenant_lifecycle_engine import (
    ACTIVE,
    AT_RISK,
    CHURNED,
    ONBOARDING,
    TRIAL,
    ALL_PHASES,
    compute_health_dimensions,
    get_inactivity_alert,
    get_success_automation_nudges,
    resolve_lifecycle_phase,
    validate_phase_transition,
)
from apps.schools.models import School


class TenantLifecycleEngineTests(TestCase):
    def test_validate_phase_transition_grid(self):
        self.assertTrue(validate_phase_transition(TRIAL, ACTIVE))
        self.assertTrue(validate_phase_transition(AT_RISK, CHURNED))
        self.assertFalse(validate_phase_transition("bogus", ACTIVE))
        self.assertFalse(validate_phase_transition(ACTIVE, "bogus"))

    def test_resolve_churned_when_inactive(self):
        s = School.objects.create(
            name="Off",
            slug="lc-off",
            subdomain="lc-off",
            is_active=False,
        )
        out = resolve_lifecycle_phase(s)
        self.assertEqual(out["phase"], CHURNED)

    def test_compute_health_dimensions_has_required_keys(self):
        s = School.objects.create(
            name="Dims",
            slug="lc-dims",
            subdomain="lc-dims",
            is_active=True,
            last_activity=timezone.now(),
        )
        dims = compute_health_dimensions(s)
        for k in (
            "feature_usage",
            "login_frequency",
            "payment_activity",
            "completion_pct",
            "composite_health",
        ):
            self.assertIn(k, dims)
            self.assertIsInstance(dims[k], int)

    def test_onboarding_phase_when_low_completion_non_trial(self):
        s = School.objects.create(
            name="Partial",
            slug="lc-part",
            subdomain="lc-part",
            is_active=True,
            billing_type=School.BillingType.REGULAR,
            last_activity=timezone.now(),
        )
        out = resolve_lifecycle_phase(s)
        self.assertEqual(out["phase"], ONBOARDING)
        self.assertIn("onboarding_lt_85_pct", ";".join(out["reasons"]))

    def test_inactivity_alert_when_stale(self):
        s = School.objects.create(
            name="Stale",
            slug="lc-stale",
            subdomain="lc-stale",
            is_active=True,
            last_activity=timezone.now() - timedelta(days=30),
        )
        alert = get_inactivity_alert(s)
        self.assertIsNotNone(alert)
        self.assertIn("login_frequency_score", alert)

    def test_automation_nudges_is_list(self):
        s = School.objects.create(
            name="Nudge",
            slug="lc-nudge",
            subdomain="lc-nudge",
            is_active=True,
        )
        n = get_success_automation_nudges(s, limit=3)
        self.assertIsInstance(n, list)
        self.assertLessEqual(len(n), 3)

    def test_all_phases_exported(self):
        self.assertEqual(len(ALL_PHASES), 5)
