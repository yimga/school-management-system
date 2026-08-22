"""The cloud must KEEP what every box already tells it, and show it to an operator.

Before this, the box's manifest hash arrived on every handshake and was compared and
dropped, and a failed upgrade went to a logfile. `EdgeDeploymentHistory` could not fill the
gap: it is written on the BOX, in the box's own database, behind that school's link, and
the cloud never sees a row of it. So "which school is on which release, and which one is
stuck" had no answer, and the honest way to get one was to ring the school.

The distinctions these tests pin are the ones that make the page usable rather than
decorative:

  * SEEN is not MOVED. A box that checked in minutes ago and last changed manifest in June
    is healthy on the network and stuck on the upgrade.
  * WAITING is not STUCK. A school not yet promoted to is behaving correctly; painting it
    the same as a failure teaches an operator to ignore the colour.
  * A resolved failure must stop being shown, or the operator chases a ghost.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.sync_engine.models_fleet import EdgeFleetState
from apps.sync_engine.models_rollout import EdgeRolloutPolicy, ManifestRelease, RolloutRing
from apps.sync_engine.views_fleet_console import _state_for

HASH_A = "a" * 64
HASH_B = "b" * 64


def _school(name="Fleet High"):
    from apps.schools.models import School

    return School.objects.create(name=name)


class RecordingTests(TestCase):
    def setUp(self):
        super().setUp()
        self.school = _school()

    def test_a_handshake_is_remembered(self):
        row = EdgeFleetState.record_seen(self.school, reported_hash=HASH_A, engine="e1", offered_hash=HASH_B)
        self.assertEqual(row.reported_manifest_hash, HASH_A)
        self.assertEqual(row.offered_manifest_hash, HASH_B)
        self.assertEqual(row.reported_engine, "e1")
        self.assertIsNotNone(row.last_seen_at)

    def test_seen_and_moved_are_different_columns(self):
        """A box seen minutes ago that last moved in June is stuck, not healthy."""
        first = EdgeFleetState.record_seen(self.school, reported_hash=HASH_A, offered_hash=HASH_B)
        moved_at = first.last_manifest_change_at
        self.assertIsNotNone(moved_at)

        second = EdgeFleetState.record_seen(self.school, reported_hash=HASH_A, offered_hash=HASH_B)
        self.assertEqual(
            second.last_manifest_change_at,
            moved_at,
            "last_manifest_change_at moved on a check-in that reported the SAME hash; a "
            "stuck box would look like it was upgrading every cycle",
        )
        self.assertGreaterEqual(second.last_seen_at, first.last_seen_at)

    def test_moving_to_a_new_manifest_updates_moved(self):
        first = EdgeFleetState.record_seen(self.school, reported_hash=HASH_A)
        before = first.last_manifest_change_at
        after = EdgeFleetState.record_seen(self.school, reported_hash=HASH_B)
        self.assertGreater(after.last_manifest_change_at, before)

    def test_a_failure_is_kept_where_a_person_can_find_it(self):
        row = EdgeFleetState.record_failure(self.school, text="verify FAILED — dashboard.js")
        self.assertIn("verify FAILED", row.last_failure_text)
        self.assertIsNotNone(row.last_failure_at)

    def test_arriving_on_the_offered_manifest_clears_the_failure(self):
        """A failure that outlives its own resolution is an operator chasing a ghost."""
        EdgeFleetState.record_failure(self.school, text="verify FAILED")
        row = EdgeFleetState.record_seen(self.school, reported_hash=HASH_A, offered_hash=HASH_A)
        self.assertEqual(row.last_failure_text, "")
        self.assertIsNone(row.last_failure_at)

    def test_a_failure_survives_a_check_in_that_did_not_resolve_it(self):
        EdgeFleetState.record_failure(self.school, text="verify FAILED")
        row = EdgeFleetState.record_seen(self.school, reported_hash=HASH_A, offered_hash=HASH_B)
        self.assertIn("verify FAILED", row.last_failure_text)

    def test_recording_never_raises(self):
        """Observability must never be able to cost a school its data sync."""
        self.assertIsNone(EdgeFleetState.record_seen(None, reported_hash=HASH_A))
        self.assertIsNone(EdgeFleetState.record_failure(None, text="x"))
        self.assertIsNone(EdgeFleetState.record_failure(self.school, text="   "))

    def test_a_long_failure_string_is_bounded(self):
        row = EdgeFleetState.record_failure(self.school, text="x" * 5000)
        self.assertLessEqual(len(row.last_failure_text), 500)


class StateClassificationTests(TestCase):
    """One school, one honest state. The ordering is the design."""

    def setUp(self):
        super().setUp()
        self.now = timezone.now()
        self.school = _school()

    def _row(self, **kw):
        row = EdgeFleetState(school=self.school)
        row.last_seen_at = kw.pop("last_seen_at", self.now)
        for k, v in kw.items():
            setattr(row, k, v)
        return row

    def test_never_seen(self):
        state, _label = _state_for(None, "stable", False, True, "", HASH_A, self.now)
        self.assertEqual(state, "never")

    def test_a_failure_outranks_drift(self):
        """A box that TRIED and stopped is a different problem from one not yet offered."""
        row = self._row(reported_manifest_hash=HASH_B, last_failure_text="verify FAILED")
        state, _label = _state_for(row, "stable", False, True, "", HASH_A, self.now)
        self.assertEqual(state, "failed")

    def test_waiting_is_not_stuck(self):
        row = self._row(reported_manifest_hash=HASH_B)
        state, label = _state_for(row, "stable", False, False, "not yet released to stable", HASH_A, self.now)
        self.assertEqual(state, "waiting", "a school awaiting promotion was painted as a fault")
        self.assertIn("not yet released", label)

    def test_behind_is_reported_when_it_HAS_been_released(self):
        row = self._row(reported_manifest_hash=HASH_B)
        state, _label = _state_for(row, "canary", False, True, "released to canary", HASH_A, self.now)
        self.assertEqual(state, "behind")

    def test_parity(self):
        row = self._row(reported_manifest_hash=HASH_A)
        state, _label = _state_for(row, "stable", False, True, "", HASH_A, self.now)
        self.assertEqual(state, "parity")

    def test_a_long_silence_reads_as_quiet_even_in_parity(self):
        row = self._row(reported_manifest_hash=HASH_A, last_seen_at=self.now - timedelta(days=5))
        state, _label = _state_for(row, "stable", False, True, "", HASH_A, self.now)
        self.assertEqual(state, "quiet")

    def test_paused_outranks_drift_but_not_failure(self):
        row = self._row(reported_manifest_hash=HASH_B)
        self.assertEqual(_state_for(row, "stable", True, True, "", HASH_A, self.now)[0], "paused")
        row.last_failure_text = "verify FAILED"
        self.assertEqual(_state_for(row, "stable", True, True, "", HASH_A, self.now)[0], "failed")


class ConsoleViewTests(TestCase):
    """The page itself: gated, and truthful about an operator with no manifest."""

    def test_the_console_is_operator_only(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_user(username="nobody", password="pw-not-a-secret-1")
        self.client.login(username="nobody", password="pw-not-a-secret-1")
        response = self.client.get("/super/edge-fleet/")
        self.assertIn(
            response.status_code,
            (302, 403, 404),
            "a non-operator reached the fleet console",
        )

    def test_anonymous_is_redirected_not_served(self):
        response = self.client.get("/super/edge-fleet/")
        self.assertNotEqual(response.status_code, 200)


class ConsoleContextTests(TestCase):
    """The rollout state the page reads, exercised without the shell."""

    def setUp(self):
        super().setUp()
        self.school = _school()

    def test_a_canary_school_on_an_unpromoted_release_is_behind_not_waiting(self):
        EdgeRolloutPolicy.objects.create(school=self.school, ring=RolloutRing.CANARY)
        EdgeFleetState.record_seen(self.school, reported_hash=HASH_B, offered_hash=HASH_A)
        row = EdgeFleetState.objects.get(school=self.school)
        from apps.sync_engine.models_rollout import may_receive

        allowed, reason = may_receive(self.school, HASH_A)
        state, _label = _state_for(row, "canary", False, allowed, reason, HASH_A, timezone.now())
        self.assertEqual(state, "behind")

    def test_a_stable_school_on_the_same_release_is_waiting(self):
        EdgeFleetState.record_seen(self.school, reported_hash=HASH_B, offered_hash=HASH_A)
        row = EdgeFleetState.objects.get(school=self.school)
        from apps.sync_engine.models_rollout import may_receive

        allowed, reason = may_receive(self.school, HASH_A)
        state, _label = _state_for(row, "stable", False, allowed, reason, HASH_A, timezone.now())
        self.assertEqual(state, "waiting")

    def test_after_promotion_the_same_school_becomes_behind(self):
        """The state must follow the promotion, not a cached judgement."""
        EdgeFleetState.record_seen(self.school, reported_hash=HASH_B, offered_hash=HASH_A)
        ManifestRelease.promote(HASH_A, rings=["canary", "stable"])
        row = EdgeFleetState.objects.get(school=self.school)
        from apps.sync_engine.models_rollout import may_receive

        allowed, reason = may_receive(self.school, HASH_A)
        state, _label = _state_for(row, "stable", False, allowed, reason, HASH_A, timezone.now())
        self.assertEqual(state, "behind")


class FilterTests(TestCase):
    """A count you cannot reach the rows behind is a number, not a readout.

    `scan_actionless_attention_surfaces` caught this page reporting "N failed" with no way
    to act on it, and it was right: across 300 schools that means scrolling a table hunting
    for red. Each summary tile is a filter link, so the count and the rows behind it are
    the same click.
    """

    def test_every_summary_tile_is_a_link_to_its_own_rows(self):
        from pathlib import Path

        template = (
            Path(__file__).resolve().parents[3]
            / "templates/sync_engine/super/fleet_console.html"
        ).read_text(encoding="utf-8")
        for state in ("parity", "behind", "waiting", "failed", "quiet", "never"):
            with self.subTest(state=state):
                self.assertIn(
                    f'href="?state={state}"',
                    template,
                    f"the {state} tile reports a count with no way to reach the rows",
                )

    def test_an_unknown_state_does_not_silently_empty_the_table(self):
        """A typo'd query param must not look like "the fleet is fine"."""
        import inspect

        from apps.sync_engine import views_fleet_console

        source = inspect.getsource(views_fleet_console)
        self.assertIn(
            "if wanted in counts:",
            source,
            "the filter does not check the requested state against the known set, so "
            "?state=faild would return an empty table that reads as a healthy fleet",
        )
