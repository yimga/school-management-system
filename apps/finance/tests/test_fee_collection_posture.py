"""Fee-collection posture is an explicit tenant decision, never an inference.

The live-payment readiness gate used to read a static blueprint tuple, so no
tenant could ever satisfy it. It now resolves against this module. The danger in
that move is obvious and is what these tests guard: if "no rail configured"
quietly resolved to "manual, therefore done", the meter would hand a pass to
every school that simply never set payments up — false credit, which is worse
than the unmovable meter it replaced.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.fee_collection_posture import (
    POSTURE_MANUAL,
    STATE_LIVE,
    STATE_MANUAL_RECORDED,
    STATE_PENDING,
    get_recorded_posture,
    record_collection_posture,
    resolve_live_collection_state,
)
from apps.schools.models import School

_NO_RAILS = {"stripe_connect": False, "verified_corridors": []}


class FeeCollectionPostureTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Posture School",
            slug="posture-school",
            subdomain="posture-school",
            is_active=True,
            settings={"existing": "kept"},
        )
        self.actor = User.objects.create_user(
            username="posture_bursar", password="x" * 12, role=User.Role.ADMIN
        )

    def _resolve(self, evidence=None):
        with patch(
            "apps.finance.fee_collection_posture._live_rail_evidence",
            return_value=dict(evidence or _NO_RAILS),
        ):
            return resolve_live_collection_state(self.school)

    def test_no_rail_and_no_decision_is_pending_not_manual(self):
        # The load-bearing assertion: silence is not a decision.
        state = self._resolve()

        self.assertEqual(state["state"], STATE_PENDING)
        self.assertTrue(state["gate_open"])
        self.assertFalse(state["not_applicable"])

    def test_recorded_manual_posture_makes_the_gate_not_applicable(self):
        record_collection_posture(
            self.school, mode=POSTURE_MANUAL, actor=self.actor, note="Cash at bursary"
        )
        self.school.refresh_from_db()

        state = self._resolve()

        self.assertEqual(state["state"], STATE_MANUAL_RECORDED)
        self.assertTrue(state["not_applicable"])
        self.assertFalse(state["gate_open"])
        self.assertFalse(state["live"])

    def test_recording_persists_actor_and_timestamp_and_keeps_other_settings(self):
        record_collection_posture(
            self.school, mode=POSTURE_MANUAL, actor=self.actor, note="Bank transfer"
        )
        self.school.refresh_from_db()

        recorded = get_recorded_posture(self.school)
        self.assertEqual(recorded["mode"], POSTURE_MANUAL)
        self.assertEqual(recorded["recorded_by"], self.actor.pk)
        self.assertTrue(recorded["recorded_at"])
        self.assertEqual(recorded["note"], "Bank transfer")
        self.assertEqual(self.school.settings["existing"], "kept")

    def test_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            record_collection_posture(self.school, mode="whatever", actor=self.actor)
        self.school.refresh_from_db()
        self.assertEqual(get_recorded_posture(self.school), {})

    def test_a_live_rail_wins_over_a_recorded_manual_posture(self):
        record_collection_posture(self.school, mode=POSTURE_MANUAL, actor=self.actor)
        self.school.refresh_from_db()

        state = self._resolve({"stripe_connect": True, "verified_corridors": []})

        self.assertEqual(state["state"], STATE_LIVE)
        self.assertTrue(state["live"])
        self.assertFalse(state["not_applicable"])

    def test_verified_corridor_counts_as_live(self):
        state = self._resolve({"stripe_connect": False, "verified_corridors": ["fapshi"]})

        self.assertEqual(state["state"], STATE_LIVE)

    def test_payment_readiness_page_renders_each_posture_state(self):
        # The finance page is the posture's home surface. It is gated by
        # require_permission + require_step_up, so this exercises the panel at
        # the template level: each state must render its own affordance, and the
        # record form must appear ONLY when there is something to settle.
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        # A request is required so the shell's context processors run; without
        # one the base template cannot resolve its site context.
        request = RequestFactory().get("/finance/payments/setup/")
        request.school = self.school
        request.user = self.actor

        def render(context):
            return render_to_string(
                "finance/payment_readiness_setup.html", context, request=request
            )

        base = {
            "profile": None,
            "readiness": {"status": "FALLBACK_ONLY", "headline": "", "subhead": "", "checklist": []},
            "status_badge_class": "warning",
            "stripe_connect": {"connected": False, "charges_enabled": False, "account_id": ""},
            "stripe_connect_url": "/x/",
            "lane2_corridors": [],
            "posture_manual_value": POSTURE_MANUAL,
        }

        pending = render({**base, "collection_posture": self._resolve()})
        self.assertIn("Record manual reconciliation", pending)

        record_collection_posture(self.school, mode=POSTURE_MANUAL, actor=self.actor)
        self.school.refresh_from_db()
        recorded = render({**base, "collection_posture": self._resolve()})
        self.assertNotIn("Record manual reconciliation", recorded)

        live = render(
            {
                **base,
                "collection_posture": self._resolve(
                    {"stripe_connect": True, "verified_corridors": []}
                ),
            }
        )
        self.assertIn("live collection is enabled", live)
        self.assertNotIn("Record manual reconciliation", live)

    def test_malformed_stored_posture_is_ignored(self):
        self.school.settings = {"fee_collection_posture": {"mode": "nonsense"}}
        self.school.save(update_fields=["settings"])

        self.assertEqual(get_recorded_posture(self.school), {})
        self.assertEqual(self._resolve()["state"], STATE_PENDING)
