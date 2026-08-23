"""A repair that did not repair must not re-arm the sweep.

``_run_sync_cycle_body`` called ``parity.reset(school)`` unconditionally after a
flush, so the very next tick swept again -- bypassing ``interval_seconds()``,
whose whole documented purpose is that running a full-corpus digest every cycle
"would turn a 20-second cadence into a continuous table scan on hardware chosen
for being small and silent".  That is fine when the flush worked: re-checking
promptly is honest.  It is a permanent cost when the flush CANNOT work -- a
drifted entity the box refuses on apply -- because then every cycle digests the
whole corpus and re-pulls up to three complete tables, forever, on a link the
school may be paying for by the megabyte.

So: re-arm on a repair, hold the ordinary interval otherwise, and escalate to a
human when the same entities come back drifted a second time -- a repair that
cannot work must stop looping and start being visible.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.schools.models import School
from apps.sync_engine import parity

_PULL = "apps.sync_engine.edge_outbox.pull_bundle"
_POST = "apps.sync_engine.edge_outbox.post_bundle"
_FLUSH = "apps.sync_engine.sync_runner._flush_drifted_entities"


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://hub.test")
class ParityRearmIsConditionalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username="parity-principal", email="p@example.test", password="x"
        )
        School.objects.update(is_active=False)
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Parity Box {0}".format(uid),
            slug="parity-box-{0}".format(uid),
            subdomain="paritybox{0}".format(uid),
            is_active=True,
        )
        AcademicYear.objects.create(
            school=self.school, name="Y1", starts_on="2024-09-01", ends_on="2025-06-30"
        )

    # ------------------------------------------------------------------ #
    def _cycle(self, *, drifted, flush_outcome):
        from apps.sync_engine import sync_runner
        from apps.sync_engine.delta_bundle import export_delta_bundle

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            if collect is not None:
                collect["parity_drift"] = list(drifted)
            return (
                200,
                export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="cloud"),
                timezone.now().isoformat(),
            )

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ), mock.patch(_FLUSH, return_value=flush_outcome):
            return sync_runner.run_sync_cycle(self.school, mode="live")

    def _sweep_marker(self):
        """The cadence marker itself: present means the hourly throttle still holds."""
        return cache.get(parity._CACHE_KEY % self.school.pk)

    # ------------------------------------------------------------------ #
    def test_a_flush_that_repaired_re_arms_the_sweep(self):
        """The honest-and-prompt case, and the guard against a vacuous test below.

        If nothing in this cycle ever reached the drift branch, the failure case
        would 'pass' for the wrong reason. This proves the branch runs and can
        still clear the marker.
        """
        from apps.sync_engine.sync_runner import FlushOutcome

        result = self._cycle(
            drifted=["department"],
            flush_outcome=FlushOutcome("parity flush repaired department", ["department"], []),
        )
        self.assertEqual(result.get("parity_drift"), ["department"])
        self.assertIsNone(self._sweep_marker())

    def test_a_flush_that_repaired_nothing_does_not_re_arm(self):
        from apps.sync_engine.sync_runner import FlushOutcome

        self._cycle(
            drifted=["department"],
            flush_outcome=FlushOutcome(
                "parity flush could NOT repair department (HTTP 503)", [], ["department (HTTP 503)"]
            ),
        )
        self.assertIsNotNone(
            self._sweep_marker(),
            "an unrepairable drift re-armed the sweep, so the next tick pays for a "
            "full-corpus digest and another whole-entity re-pull",
        )

    def test_a_partial_flush_does_not_re_arm_either(self):
        """One repaired and one failed is still a drift the next sweep cannot fix."""
        from apps.sync_engine.sync_runner import FlushOutcome

        self._cycle(
            drifted=["department", "classroom"],
            flush_outcome=FlushOutcome(
                "mixed", ["department (1 created, 0 updated)"], ["classroom (HTTP 503)"]
            ),
        )
        self.assertIsNotNone(self._sweep_marker())

    def test_the_same_drift_twice_stops_flushing_and_says_so(self):
        """A repair that cannot work must escalate to a human, not loop."""
        from apps.sync_engine.sync_runner import FlushOutcome

        failed = FlushOutcome("could NOT repair", [], ["department (HTTP 503)"])
        self._cycle(drifted=["department"], flush_outcome=failed)
        parity.reset(self.school)  # let the second sweep run without waiting an hour

        from apps.sync_engine import sync_runner
        from apps.sync_engine.delta_bundle import export_delta_bundle

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            if collect is not None:
                collect["parity_drift"] = ["department"]
            return (
                200,
                export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="cloud"),
                timezone.now().isoformat(),
            )

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ), mock.patch(_FLUSH, return_value=failed) as flush:
            second = sync_runner.run_sync_cycle(self.school, mode="live")

        self.assertFalse(
            flush.called,
            "the same entities drifted twice running; re-pulling them a third time "
            "spends the link on a repair already shown not to work",
        )
        self.assertTrue(second.get("parity_unrepairable"))
        self.assertIn("unrepairable", second.get("message", ""))


class FlushOutcomeShapeTests(TestCase):
    """`_flush_drifted_entities` must report WHAT happened, not only narrate it.

    It already knows which entities it repaired and which it could not -- it says so
    in its own note. Returning only the prose meant the caller could not act on it,
    which is how the unconditional re-arm survived review.
    """

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name="Flush {0}".format(uid),
            slug="flush-{0}".format(uid),
            subdomain="flush{0}".format(uid),
            is_active=True,
        )
        self.user = get_user_model().objects.create_superuser(
            username="flush-principal-{0}".format(uid),
            email="f{0}@example.test".format(uid),
            password="x",
        )

    def test_a_successful_pull_and_apply_is_reported_as_repaired(self):
        from apps.sync_engine import sync_runner

        with mock.patch(_PULL, return_value=(200, b"", None)), mock.patch(
            "apps.sync_engine.edge_inbox.apply_pulled_bundle",
            return_value={"ok": True, "created": 2, "upserted": 0},
        ):
            outcome = sync_runner._flush_drifted_entities(
                self.school, "https://hub.test/x", "tok", self.user, ["department"]
            )
        self.assertEqual(outcome.failed, [])
        self.assertEqual(len(outcome.repaired), 1)
        self.assertIn("department", outcome.note)

    def test_a_rejected_pull_is_reported_as_failed(self):
        from apps.sync_engine import sync_runner

        with mock.patch(_PULL, return_value=(503, b"", None)):
            outcome = sync_runner._flush_drifted_entities(
                self.school, "https://hub.test/x", "tok", self.user, ["department"]
            )
        self.assertEqual(outcome.repaired, [])
        self.assertEqual(len(outcome.failed), 1)
        self.assertIn("could NOT repair", outcome.note)
