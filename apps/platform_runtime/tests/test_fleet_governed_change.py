"""Fleet governed change model + transition service (WHATS_LEFT §2.1 thin slice)."""

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.admin import FleetGovernedChangeAdminForm
from apps.platform_runtime.fleet_apply_surfaces import resolve_fleet_apply_surface
from apps.platform_runtime.fleet_governed_change import transition_fleet_governed_change
from apps.platform_runtime.models import FleetGovernedChange, PlatformEventLog


class FleetGovernedChangeTransitionTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="fleet_actor",
            password="x",
            is_staff=True,
        )

    def test_happy_path_sets_approved_and_applied(self):
        ch = FleetGovernedChange.objects.create(
            change_type="PACKAGE_ROLLOUT",
            title="Rollout X",
            created_by=self.actor,
        )
        self.assertEqual(ch.status, FleetGovernedChange.Status.DRAFT)
        transition_fleet_governed_change(
            ch, FleetGovernedChange.Status.PENDING_APPROVAL
        )
        ch.refresh_from_db()
        self.assertEqual(ch.status, FleetGovernedChange.Status.PENDING_APPROVAL)
        transition_fleet_governed_change(
            ch, FleetGovernedChange.Status.SCHEDULED, actor=self.actor
        )
        ch.refresh_from_db()
        self.assertEqual(ch.status, FleetGovernedChange.Status.SCHEDULED)
        self.assertEqual(ch.approved_by_id, self.actor.pk)
        transition_fleet_governed_change(ch, FleetGovernedChange.Status.APPLYING)
        transition_fleet_governed_change(ch, FleetGovernedChange.Status.SUCCEEDED)
        ch.refresh_from_db()
        self.assertEqual(ch.status, FleetGovernedChange.Status.SUCCEEDED)
        self.assertIsNotNone(ch.applied_at)

    def test_failed_records_error_and_applied_at(self):
        ch = FleetGovernedChange.objects.create(change_type="FEATURE_FLAG")
        for s in (
            FleetGovernedChange.Status.PENDING_APPROVAL,
            FleetGovernedChange.Status.SCHEDULED,
            FleetGovernedChange.Status.APPLYING,
        ):
            transition_fleet_governed_change(ch, s)
        transition_fleet_governed_change(
            ch,
            FleetGovernedChange.Status.FAILED,
            error_message="apply timeout",
        )
        ch.refresh_from_db()
        self.assertEqual(ch.status, FleetGovernedChange.Status.FAILED)
        self.assertIn("timeout", ch.error_message)
        self.assertIsNotNone(ch.applied_at)

    def test_illegal_transition_raises(self):
        ch = FleetGovernedChange.objects.create(change_type="T")
        with self.assertRaises(ValueError):
            transition_fleet_governed_change(ch, FleetGovernedChange.Status.SUCCEEDED)

    def test_terminal_cannot_move(self):
        ch = FleetGovernedChange.objects.create(change_type="T")
        transition_fleet_governed_change(ch, FleetGovernedChange.Status.CANCELLED)
        with self.assertRaises(ValueError):
            transition_fleet_governed_change(ch, FleetGovernedChange.Status.DRAFT)

    def test_create_writes_fleet_governed_change_created_event(self):
        before = PlatformEventLog.objects.count()
        ch = FleetGovernedChange.objects.create(change_type="EV_CREATE")
        self.assertEqual(PlatformEventLog.objects.count(), before + 1)
        row = PlatformEventLog.objects.order_by("-pk").first()
        self.assertEqual(row.event_type, "fleet_governed_change_created")
        self.assertEqual(row.payload.get("change_id"), ch.pk)
        self.assertEqual(row.payload.get("change_type"), "EV_CREATE")

    def test_transition_writes_platform_event_log(self):
        ch = FleetGovernedChange.objects.create(change_type="EV_TEST")
        before = PlatformEventLog.objects.count()
        transition_fleet_governed_change(
            ch, FleetGovernedChange.Status.PENDING_APPROVAL, actor=self.actor
        )
        self.assertEqual(PlatformEventLog.objects.count(), before + 1)
        row = PlatformEventLog.objects.filter(
            event_type="fleet_governed_change_transitioned"
        ).order_by("-pk").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.payload.get("change_id"), ch.pk)
        self.assertEqual(row.payload.get("from_status"), "DRAFT")
        self.assertEqual(row.payload.get("to_status"), "PENDING_APPROVAL")
        self.assertEqual(row.payload.get("actor_id"), self.actor.pk)

    def test_failed_transition_includes_error_in_event_payload(self):
        ch = FleetGovernedChange.objects.create(change_type="EV_FAIL")
        for s in (
            FleetGovernedChange.Status.PENDING_APPROVAL,
            FleetGovernedChange.Status.SCHEDULED,
            FleetGovernedChange.Status.APPLYING,
        ):
            transition_fleet_governed_change(ch, s)
        transition_fleet_governed_change(
            ch,
            FleetGovernedChange.Status.FAILED,
            error_message="boom",
        )
        row = (
            PlatformEventLog.objects.filter(event_type="fleet_governed_change_transitioned")
            .order_by("-pk")
            .first()
        )
        self.assertEqual(row.payload.get("to_status"), "FAILED")
        self.assertEqual(row.payload.get("error_message"), "boom")


class FleetApplySurfaceResolutionTests(TestCase):
    def test_known_preset_resolves_to_path(self):
        path = resolve_fleet_apply_surface("super:package_rollout")
        self.assertIsNotNone(path)
        self.assertTrue(str(path).startswith("/"))

    def test_admin_form_preset_fills_url_and_payload_name(self):
        form = FleetGovernedChangeAdminForm(
            data={
                "change_type": "PKG",
                "status": FleetGovernedChange.Status.DRAFT,
                "scope": "{}",
                "payload": "{}",
                "apply_surface_preset": "super:package_rollout",
                "apply_surface_url": "",
                "notes": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertTrue((obj.apply_surface_url or "").startswith("/"))
        self.assertEqual(obj.payload.get("apply_surface_name"), "super:package_rollout")

    def test_manual_url_wins_over_preset(self):
        form = FleetGovernedChangeAdminForm(
            data={
                "change_type": "PKG",
                "status": FleetGovernedChange.Status.DRAFT,
                "scope": "{}",
                "payload": "{}",
                "apply_surface_preset": "super:package_rollout",
                "apply_surface_url": "/custom/only/",
                "notes": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save()
        self.assertEqual(obj.apply_surface_url, "/custom/only/")
        self.assertIsNone(obj.payload.get("apply_surface_name"))
