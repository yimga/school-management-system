"""Product lifecycle states derived from funnel + billing signals."""

from django.test import TestCase
from django.utils import timezone

from apps.platform_runtime.tenant_lifecycle_state_machine import (
    ALL_LIFECYCLE_STATES,
    STATE_AT_RISK,
    STATE_CHURNED,
    STATE_DEMO,
    STATE_PAYING,
    STATE_RECOVERED,
    STATE_SIGNUP_STARTED,
    resolve_tenant_lifecycle_state,
    validate_lifecycle_transition,
)
from apps.schools.models import MarketingFunnelEvent, School


class TenantLifecycleStateMachineTests(TestCase):
    def test_validate_transition_grid(self):
        self.assertTrue(
            validate_lifecycle_transition(STATE_DEMO, STATE_SIGNUP_STARTED)
        )
        self.assertTrue(validate_lifecycle_transition(STATE_PAYING, STATE_AT_RISK))
        self.assertFalse(validate_lifecycle_transition(STATE_CHURNED, STATE_PAYING))

    def test_all_states_exported(self):
        self.assertEqual(len(ALL_LIFECYCLE_STATES), 9)

    def test_resolve_churned_inactive(self):
        s = School.objects.create(
            name="X",
            slug="lc-churn",
            subdomain="lc-churn",
            is_active=False,
        )
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_CHURNED)

    def test_resolve_demo_with_demo_started_only(self):
        s = School.objects.create(
            name="Demo",
            slug="lc-demo",
            subdomain="lc-demo",
            is_active=True,
            settings={},
            last_activity=timezone.now(),
        )
        MarketingFunnelEvent.objects.create(
            event_type="demo_started",
            school=s,
            session_key="",
            metadata={},
        )
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_DEMO)

    def test_resolve_signup_started_event(self):
        s = School.objects.create(
            name="Su",
            slug="lc-su",
            subdomain="lc-su",
            is_active=True,
            last_activity=timezone.now(),
        )
        MarketingFunnelEvent.objects.create(
            event_type="signup_started",
            school=s,
            session_key="",
            metadata={},
        )
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_SIGNUP_STARTED)

    def test_resolve_recovered_marker(self):
        s = School.objects.create(
            name="Rec",
            slug="lc-rec",
            subdomain="lc-rec",
            is_active=True,
            last_activity=timezone.now(),
        )
        MarketingFunnelEvent.objects.create(
            event_type="tenant_recovered",
            school=s,
            session_key="",
            metadata={},
        )
        out = resolve_tenant_lifecycle_state(s)
        self.assertEqual(out["state"], STATE_RECOVERED)
