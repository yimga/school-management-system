"""Unified lifecycle — both creation paths and offboarding checklist."""

from django.test import TestCase
from django.utils import timezone

from apps.lifecycle.enrollment_workflow_matrix import (
    build_enrollment_track,
    build_lifecycle_workflow_hub_payload,
    build_registration_track,
)
from apps.lifecycle.launch_rail import build_launch_rail_payload, FAST_PATH_STEPS
from apps.lifecycle.unified_lifecycle import (
    ALL_UNIFIED_STATES,
    CREATION_PATH_OPERATOR,
    CREATION_PATH_SELF_SERVE,
    STATE_ACTIVATING,
    STATE_CLOSED,
    STATE_DRAFT,
    STATE_PROVISIONING,
    STATE_LIVE,
    STATE_PURGED,
    STATE_WIND_DOWN,
    build_offboarding_checklist,
    get_creation_path,
    resolve_unified_lifecycle,
    set_creation_path,
    validate_unified_transition,
)
from apps.lifecycle.wind_down import apply_wind_down_mode, is_wind_down_mode
from apps.schools.models import School, SchoolProvisioningEvent


class UnifiedLifecycleE2ETests(TestCase):
    def test_all_states_exported(self):
        self.assertEqual(len(ALL_UNIFIED_STATES), 7)

    def test_creation_path_round_trip(self):
        school = School.objects.create(
            name="Path",
            slug="path-school",
            subdomain="path-school",
            is_active=False,
        )
        set_creation_path(school, CREATION_PATH_SELF_SERVE)
        self.assertEqual(get_creation_path(school), CREATION_PATH_SELF_SERVE)
        set_creation_path(school, CREATION_PATH_OPERATOR)
        self.assertEqual(get_creation_path(school), CREATION_PATH_OPERATOR)

    def test_draft_inactive_signup(self):
        school = School.objects.create(
            name="Draft",
            slug="draft-school",
            subdomain="draft-school",
            is_active=False,
        )
        set_creation_path(school, CREATION_PATH_SELF_SERVE)
        out = resolve_unified_lifecycle(school)
        self.assertEqual(out["state"], STATE_DRAFT)

    def test_provisioning_in_flight(self):
        school = School.objects.create(
            name="Prov",
            slug="prov-school",
            subdomain="prov-school",
            is_active=True,
        )
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.STARTED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="test",
        )
        out = resolve_unified_lifecycle(school)
        self.assertEqual(out["state"], STATE_PROVISIONING)
        self.assertTrue(out["provisioning_in_flight"])

    def test_launch_rail_fast_path_shape(self):
        school = School.objects.create(
            name="Rail",
            slug="rail-school",
            subdomain="rail-school",
            is_active=True,
        )
        set_creation_path(school, CREATION_PATH_OPERATOR)
        rail = build_launch_rail_payload(school)
        self.assertEqual(len(rail["fast_path"]), len(FAST_PATH_STEPS))
        self.assertIn("creation_path_label", rail)

    def test_offboarding_checklist_six_steps(self):
        school = School.objects.create(
            name="Off",
            slug="off-school",
            subdomain="off-school",
            is_active=True,
        )
        steps = build_offboarding_checklist(school)
        self.assertEqual(len(steps), 6)
        self.assertFalse(all(s["done"] for s in steps))

    def test_wind_down_mode_after_apply(self):
        school = School.objects.create(
            name="Wind",
            slug="wind-school",
            subdomain="wind-school",
            is_active=True,
        )
        apply_wind_down_mode(school, note="test")
        school.refresh_from_db()
        self.assertTrue(is_wind_down_mode(school))
        out = resolve_unified_lifecycle(school)
        self.assertEqual(out["state"], STATE_WIND_DOWN)

    def test_validate_transition_graph(self):
        self.assertTrue(validate_unified_transition(STATE_DRAFT, STATE_PROVISIONING))
        self.assertFalse(validate_unified_transition(STATE_PURGED, STATE_LIVE))

    def test_registration_and_enrollment_tracks(self):
        school = School.objects.create(
            name="Enroll",
            slug="enroll-school",
            subdomain="enroll-school",
            is_active=True,
        )
        reg = build_registration_track(school)
        enr = build_enrollment_track(school)
        self.assertGreaterEqual(reg["total"], 4)
        self.assertGreaterEqual(enr["total"], 5)
        self.assertIn("steps", reg)
        self.assertIn("percent", enr)

    def test_lifecycle_workflow_hub_payload(self):
        school = School.objects.create(
            name="Hub",
            slug="hub-school",
            subdomain="hub-school",
            is_active=True,
        )
        hub = build_lifecycle_workflow_hub_payload(school)
        self.assertIn("registration", hub)
        self.assertIn("enrollment", hub)
        self.assertIn("launch_rail", hub)
        self.assertIn("operator_offboarding", hub)
        self.assertIn("summary", hub)
