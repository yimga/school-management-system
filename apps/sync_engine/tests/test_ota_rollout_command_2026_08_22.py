"""`ota_rollout` is the ONLY way to widen a release, and nothing exercised it.

The fleet console is read-only on purpose — a button that ships a build to every school is
a button that gets clicked by accident — which makes this command the single path from
"the canary looks fine" to "everybody gets it". A typo in a field name or an f-string here
would not fail a gate, would not fail a test, and would surface the first time an operator
tried to promote a release during an incident.

These tests are cheap and they pin the parts an operator's hands are on: every flag runs,
a bad ring is refused instead of silently written, promoting with no manifest says what to
do about it, and the listing admits when it has truncated.
"""
from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.sync_engine.models_rollout import EdgeRolloutPolicy, ManifestRelease, RolloutRing

HASH_A = "a" * 64
MANIFEST = {"manifest_hash": HASH_A, "version_label": "v1", "channel": "stable"}


def _school(name="Canary High", slug="canary-high"):
    from apps.schools.models import School

    # `subdomain` is blank=True AND unique=True, so a second school left blank collides on
    # the empty string. Every school here gets its own.
    return School.objects.create(name=name, slug=slug, subdomain=slug)


def _run(*argv, manifest=MANIFEST):
    """Run the command with a pinned manifest, capturing stdout."""
    out = StringIO()
    with mock.patch(
        "apps.sync_engine.management.commands.ota_rollout.load_manifest",
        return_value=manifest,
    ):
        call_command("ota_rollout", *argv, stdout=out, stderr=out)
    return out.getvalue()


class StatusTests(TestCase):
    def test_status_runs_and_names_the_manifest_it_would_ship(self):
        """The first thing anybody types."""
        output = _run("--status")
        self.assertIn(HASH_A[:12], output)
        self.assertIn("default rings", output)

    def test_status_says_so_when_there_are_no_schools(self):
        """A fresh operator deployment. The migrated test database is NOT empty -- it
        carries a seeded school -- so this clears them rather than assuming."""
        from apps.schools.models import School

        School.objects.all().delete()
        output = _run("--status")
        self.assertIn("no schools on this deployment", output)

    def test_status_runs_with_no_manifest_at_all(self):
        """An operator that has never built one must still get a readable answer."""
        output = _run("--status", manifest={})
        self.assertIn("(none)", output)

    def test_status_lists_a_school_with_its_ring_and_state(self):
        _school()
        output = _run("--status")
        self.assertIn("Canary High", output)
        self.assertIn(RolloutRing.STABLE.value, output)

    def test_a_truncated_listing_says_so(self):
        """A list that silently stops reads as 'that is the whole fleet'."""
        from apps.schools.models import School
        from apps.sync_engine.management.commands import ota_rollout

        School.objects.all().delete()  # the migrated database seeds one; count from zero
        for i in range(3):
            _school(name=f"School {i:02d}", slug=f"school-{i:02d}")
        with mock.patch.object(ota_rollout, "_STATUS_ROW_CAP", 2):
            output = _run("--status")
        self.assertIn("showing 2 of 3 schools", output)
        self.assertIn("1 not listed", output)

    def test_an_untruncated_listing_does_not_cry_wolf(self):
        """Calibration: without this, "it warns on truncation" proves nothing."""
        _school()
        self.assertNotIn("not listed", _run("--status"))


class RingTests(TestCase):
    def setUp(self):
        super().setUp()
        self.school = _school()

    def test_a_school_can_be_put_on_canary(self):
        _run("--ring", "canary-high", "canary")
        self.assertEqual(
            EdgeRolloutPolicy.objects.get(school=self.school).ring, RolloutRing.CANARY.value
        )

    def test_a_school_is_found_by_name_when_the_slug_does_not_match(self):
        _run("--ring", "Canary High", "canary")
        self.assertEqual(
            EdgeRolloutPolicy.objects.get(school=self.school).ring, RolloutRing.CANARY.value
        )

    def test_an_unknown_ring_is_refused_not_written(self):
        """A typo'd ring must not become a ring nothing will ever match."""
        with self.assertRaises(CommandError) as caught:
            _run("--ring", "canary-high", "canry")
        self.assertIn("canary", str(caught.exception))
        self.assertFalse(EdgeRolloutPolicy.objects.filter(school=self.school).exists())

    def test_an_unknown_school_is_refused_and_says_what_it_tried(self):
        with self.assertRaises(CommandError) as caught:
            _run("--ring", "no-such-school", "canary")
        self.assertIn("no-such-school", str(caught.exception))

    def test_putting_a_paused_school_on_a_ring_resumes_it(self):
        """Pinned deliberately: --ring is an active decision, so it clears the hold.

        If this ever flips, an operator who paused a school and later moved it to canary
        would watch it sit there receiving nothing, with the console reporting `paused`
        and the ring saying `canary`.
        """
        _run("--pause", "canary-high")
        _run("--ring", "canary-high", "canary")
        self.assertFalse(EdgeRolloutPolicy.objects.get(school=self.school).paused)


class PauseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.school = _school()

    def test_pause_then_resume(self):
        _run("--pause", "canary-high")
        self.assertTrue(EdgeRolloutPolicy.objects.get(school=self.school).paused)
        _run("--resume", "canary-high")
        self.assertFalse(EdgeRolloutPolicy.objects.get(school=self.school).paused)

    def test_a_note_is_kept_where_the_next_operator_reads_it(self):
        _run("--pause", "canary-high", "--note", "term reports running until Friday")
        self.assertIn("Friday", EdgeRolloutPolicy.objects.get(school=self.school).note)


class PromoteTests(TestCase):
    def test_promoting_without_a_manifest_says_what_to_do(self):
        """The failure mode is 'nothing happened'; it must not be silent."""
        with self.assertRaises(CommandError) as caught:
            _run("--promote", "stable", manifest={})
        self.assertIn("generate_system_manifest", str(caught.exception))
        self.assertFalse(ManifestRelease.objects.exists())

    def test_promoting_records_the_rings(self):
        output = _run("--promote", "canary")
        self.assertEqual(ManifestRelease.objects.get(manifest_hash=HASH_A).rings, ["canary"])
        self.assertIn(HASH_A[:12], output)

    def test_promoting_is_reversible(self):
        """Pulling a bad release back is the same command with a narrower ring."""
        _run("--promote", "canary", "stable")
        self.assertEqual(
            ManifestRelease.objects.get(manifest_hash=HASH_A).rings, ["canary", "stable"]
        )
        _run("--promote", "canary")
        self.assertEqual(ManifestRelease.objects.get(manifest_hash=HASH_A).rings, ["canary"])

    def test_an_unknown_ring_promotes_nothing(self):
        with self.assertRaises(CommandError) as caught:
            _run("--promote", "prod")
        self.assertIn("prod", str(caught.exception))
        self.assertFalse(ManifestRelease.objects.exists())

    def test_the_promoted_hash_is_the_one_this_operator_holds_the_files_for(self):
        """Promoting an arbitrary hash would be a promise the operator cannot keep."""
        _run("--promote", "stable", manifest={"manifest_hash": "c" * 64, "channel": "stable"})
        self.assertTrue(ManifestRelease.objects.filter(manifest_hash="c" * 64).exists())
        self.assertFalse(ManifestRelease.objects.filter(manifest_hash=HASH_A).exists())


class QueryCountTests(TestCase):
    """A fleet-wide readout must not cost a query per school.

    `may_receive` looks up the school's policy and the manifest's rings, which is exactly
    right on the handshake path — one school, one call. Called inside a loop over the whole
    fleet it is two round trips per school, and the console was paying them on top of the
    policy map it had just built. At 300 schools that is 600 avoidable queries to render
    one page, and the page an operator opens during a rollout is the worst possible place
    to find that out.

    This asserts the shape rather than a magic number: the cost of listing the fleet must
    not depend on how big the fleet is.
    """

    def test_status_does_not_query_per_school(self):
        for i in range(2):
            _school(name=f"Small {i}", slug=f"small-{i}")
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as small:
            _run("--status")
        small_count = len(small.captured_queries)

        for i in range(6):
            _school(name=f"Big {i}", slug=f"big-{i}")
        with CaptureQueriesContext(connection) as big:
            _run("--status")

        self.assertEqual(
            len(big.captured_queries),
            small_count,
            f"listing 8 schools cost {len(big.captured_queries)} queries where 2 cost "
            f"{small_count}; the readout scales with the fleet, so it gets slowest exactly "
            f"when the fleet is biggest",
        )


class PreloadedStateTests(TestCase):
    """The mechanism the fleet-wide callers rely on."""

    def setUp(self):
        super().setUp()
        self.school = _school()

    def test_preloaded_state_costs_nothing(self):
        from apps.sync_engine.models_rollout import may_receive

        with self.assertNumQueries(0):
            allowed, reason = may_receive(
                self.school, HASH_A, ring="canary", paused=False, released=["canary"]
            )
        self.assertTrue(allowed)
        self.assertIn("canary", reason)

    def test_a_caller_that_passes_nothing_still_gets_the_right_answer(self):
        """The handshake path must be unchanged by the fleet-listing optimisation."""
        from apps.sync_engine.models_rollout import may_receive

        EdgeRolloutPolicy.objects.create(school=self.school, ring=RolloutRing.CANARY)
        ManifestRelease.promote(HASH_A, rings=["canary"])
        allowed, reason = may_receive(self.school, HASH_A)
        self.assertTrue(allowed)
        self.assertIn("canary", reason)

    def test_a_paused_school_is_refused_from_preloaded_state_too(self):
        from apps.sync_engine.models_rollout import may_receive

        allowed, reason = may_receive(
            self.school, HASH_A, ring="canary", paused=True, released=["canary"]
        )
        self.assertFalse(allowed)
        self.assertIn("paused", reason)
