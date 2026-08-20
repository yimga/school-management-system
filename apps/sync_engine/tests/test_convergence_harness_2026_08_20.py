"""G7: run the sequences, do not assert them.

Every other guarantee in this engine is a claim about an ORDER of events — dark for two
weeks, writes on both sides, a restore; a bundle that dies half-applied; a power cut
between the apply and the cursor advance; a clock ten minutes out; the same bundle
delivered twice. Unit tests check the pieces. Until this harness existed, nothing ran the
sequences, so "the appliance converges with the cloud" was an argument.

WHAT THIS PROVES, AND WHAT IT DOES NOT. The harness drives one real database through the
REAL wire — actual signed bundles from ``build_edge_delta_rows``, applied through the
actual apply paths — and models the far side as the state a peer would hold after
applying exactly what crossed. So it proves the PROTOCOL converges: what ships, what the
cursor does, who wins, and whether a replay or a half-applied bundle can leave the two
sides different.

It does not prove two independent Postgres databases agreeing, because this suite runs on
SQLite against a single database — and on the one property where those differ (deferred
foreign keys) SQLite is the WEAKER environment, which is exactly how the 2026-08-19 wedge
stayed invisible for so long. That gap is named rather than papered over; the two-box
drill in docs/EDGE_SYNC_OPERATIONS.md covers what a single database cannot show.
"""
from __future__ import annotations

import datetime as dt
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import Department
from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.convergence_harness import ConvergenceHarness, Mirror

_SIGN_KEY = "convergence-harness-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class ConvergenceScenarioTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Conv {uid}", slug=f"conv-{uid}", subdomain=f"conv{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"conv_{uid}", password="Test1234", email=f"c{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.uid = uid
        for n in range(3):
            Department.objects.create(
                school=self.school, name=f"Dept {n}", code=f"D{n}-{uid}"
            )
        self.harness = ConvergenceHarness(self.school, self.user, entities={"department"})

    def _assert_converged(self, verdict):
        self.assertTrue(
            verdict["converged"],
            f"{verdict['scenario']}: {verdict['difference_count']} difference(s): "
            f"{verdict['differences']}",
        )

    def test_clean_sync(self):
        self._assert_converged(self.harness.clean_sync())

    def test_a_fourteen_day_outage_with_writes_on_both_sides_converges(self):
        """The claim every offline-first system makes and few test: go dark, both sides
        keep working, reconnect, agree."""
        remote_pk = (
            Department.objects.order_by("-pk").values_list("pk", flat=True).first() + 500
        )

        def seed_local():
            Department.objects.create(
                school=self.school, name="Made offline", code=f"OFF-{self.uid}"
            )

        def seed_remote():
            return [{
                "entity_type": "department", "id": remote_pk, "client_offline_id": "",
                "changes": {"name": "Made on the cloud", "code": f"CLOUD-{self.uid}"},
                "updated_at": timezone.now().isoformat(),
            }]

        verdict = self.harness.outage_both_sides(seed_local, seed_remote)
        self._assert_converged(verdict)
        self.assertTrue(Department.objects.filter(pk=remote_pk).exists())

    def test_a_connection_dropped_mid_bundle_loses_nothing(self):
        verdict = self.harness.midbundle_drop()
        self._assert_converged(verdict)
        self.assertTrue(
            verdict["diverged_while_partial"],
            "premise check: a half-applied bundle IS supposed to leave the sides different",
        )

    def test_a_power_cut_before_the_cursor_advanced_is_harmless(self):
        verdict = self.harness.power_cut_before_cursor()
        self._assert_converged(verdict)
        self.assertTrue(
            verdict["idempotent"],
            "re-applying the same window changed state — every unclean shutdown would corrupt",
        )

    def test_a_ten_minute_clock_skew_does_not_change_what_converges(self):
        """Echo suppression here is provenance-based, not a clock compare, so skew must
        not change the outcome — that is the whole reason it is not a clock compare."""
        self._assert_converged(self.harness.clock_skew(minutes=10))

    def test_a_duplicate_bundle_converges_and_is_recognised_as_a_replay(self):
        verdict = self.harness.duplicate_bundle()
        self._assert_converged(verdict)
        self.assertTrue(
            verdict["replay_detected"],
            "the second delivery of identical bytes was accepted as new",
        )

    def test_a_deletion_crosses_and_does_not_come_back(self):
        target = Department.objects.create(
            school=self.school, name="Doomed", code=f"DOOM-{self.uid}"
        )
        key = ("department", str(target.pk))

        def delete_one():
            target.delete()
            return key

        verdict = self.harness.delete_propagation(delete_one)
        self.assertTrue(verdict["gone_remotely"], "the deletion never crossed")
        self.assertTrue(
            verdict["stayed_gone"],
            "a full re-offer resurrected the deleted row — a delete that undoes itself",
        )
        self._assert_converged(verdict)

    def test_the_authority_invariants_hold_across_the_whole_registry(self):
        """A property of the registry, not of any one code path, so a new entity that
        forgets its policy row fails here rather than in production."""
        verdict = self.harness.authority_invariants()
        self.assertTrue(verdict["converged"], verdict["differences"])


class MirrorTests(TestCase):
    """The model of the far side has to behave like a receiver, or every verdict is noise."""

    def test_a_delete_row_removes_and_buries(self):
        mirror = Mirror()
        mirror.apply([{"entity_type": "d", "id": "1", "changes": {"n": "a"}}])
        mirror.apply([{"entity_type": "d", "id": "1", "op": "delete"}])
        self.assertEqual(mirror.rows, {})
        self.assertIn(("d", "1"), mirror.buried)

    def test_a_burial_is_not_undone_by_a_later_replay_of_older_rows(self):
        mirror = Mirror()
        mirror.apply([{"entity_type": "d", "id": "1", "op": "delete"}])
        out = mirror.apply([{"entity_type": "d", "id": "1", "changes": {"n": "a"}}])
        self.assertEqual(out["ignored"], 1)
        self.assertEqual(mirror.rows, {})

    def test_updates_merge_field_by_field(self):
        mirror = Mirror()
        mirror.apply([{"entity_type": "d", "id": "1", "changes": {"a": 1}}])
        mirror.apply([{"entity_type": "d", "id": "1", "changes": {"b": 2}}])
        self.assertEqual(mirror.rows[("d", "1")], {"a": 1, "b": 2})


class DifferenceReportingTests(TestCase):
    def test_a_type_only_difference_is_not_reported_as_divergence(self):
        """The two sides arrive by different routes — a live model instance and a JSON
        wire payload — so 3 and "3" are the same value reported differently."""
        from apps.sync_engine.convergence_harness import _differences

        self.assertEqual(
            _differences({("d", "1"): {"n": 3}}, {("d", "1"): {"n": "3"}}), []
        )

    def test_a_real_difference_survives(self):
        from apps.sync_engine.convergence_harness import _differences

        diffs = _differences({("d", "1"): {"n": 3}}, {("d", "1"): {"n": 4}})
        self.assertEqual(len(diffs), 1)

    def test_a_row_present_on_only_one_side_is_reported(self):
        from apps.sync_engine.convergence_harness import _differences

        self.assertEqual(
            _differences({("d", "1"): {}}, {})[0]["problem"], "only on this side"
        )
        self.assertEqual(
            _differences({}, {("d", "1"): {}})[0]["problem"], "only on the far side"
        )

    def test_an_aware_timestamp_difference_is_still_caught(self):
        from apps.sync_engine.convergence_harness import _differences

        now = timezone.now()
        diffs = _differences(
            {("d", "1"): {"t": now}}, {("d", "1"): {"t": now + dt.timedelta(days=1)}}
        )
        self.assertEqual(len(diffs), 1)
