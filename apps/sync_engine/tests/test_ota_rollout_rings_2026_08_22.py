"""A release reaches the boxes an operator nominated, and stops there until widened.

Without rings, "push an upgrade" means "push it to every school at once": the manifest
endpoint served one manifest to whoever asked, so the first box to sync after a deploy
took the new release and so did every box behind it. The whole reason this pipeline
exists is that some releases are wrong in ways no test caught — so the fleet must not
receive one before anyone has looked at the first box.

The failure mode being guarded against is subtle: it is NOT "a box gets a bad release",
it is "every box gets it simultaneously and there is no healthy peer left to compare
against".
"""
from __future__ import annotations

from django.test import TestCase, override_settings

from apps.sync_engine.models_rollout import (
    DEFAULT_RING,
    EdgeRolloutPolicy,
    ManifestRelease,
    RolloutRing,
    default_release_rings,
    may_receive,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def _school(name="Ring High"):
    from apps.schools.models import School

    return School.objects.create(name=name)


class DefaultRingTests(TestCase):
    def test_a_school_with_no_policy_row_is_on_stable(self):
        """A fresh install must not need a row per school before anything works."""
        school = _school()
        ring, paused = EdgeRolloutPolicy.ring_for(school)
        self.assertEqual(ring, DEFAULT_RING.value)
        self.assertFalse(paused)

    def test_a_manifest_with_no_release_row_uses_the_configured_default(self):
        """Reading an unseen manifest must not WRITE — the read path stays a read."""
        before = ManifestRelease.objects.count()
        self.assertEqual(ManifestRelease.rings_for(HASH_A), ["canary"])
        self.assertEqual(ManifestRelease.objects.count(), before)

    @override_settings(RMC_OTA_DEFAULT_RELEASE_RINGS="canary,stable")
    def test_release_to_everyone_immediately_is_configurable(self):
        self.assertEqual(default_release_rings(), ["canary", "stable"])

    @override_settings(RMC_OTA_DEFAULT_RELEASE_RINGS="nonsense")
    def test_an_unreadable_ring_list_falls_back_to_canary_not_to_everyone(self):
        """A typo must never widen the blast radius."""
        self.assertEqual(default_release_rings(), ["canary"])

    @override_settings(RMC_OTA_DEFAULT_RELEASE_RINGS="")
    def test_an_empty_ring_list_falls_back_to_canary(self):
        self.assertEqual(default_release_rings(), ["canary"])


class RolloutDecisionTests(TestCase):
    def setUp(self):
        super().setUp()
        self.school = _school()

    def test_a_stable_school_does_not_get_an_unpromoted_release(self):
        allowed, reason = may_receive(self.school, HASH_A)
        self.assertFalse(allowed, "an unpromoted release reached the whole fleet")
        self.assertIn("not yet released", reason)

    def test_a_canary_school_does(self):
        EdgeRolloutPolicy.objects.create(school=self.school, ring=RolloutRing.CANARY)
        allowed, reason = may_receive(self.school, HASH_A)
        self.assertTrue(allowed)
        self.assertIn("canary", reason)

    def test_promotion_widens_to_stable(self):
        self.assertFalse(may_receive(self.school, HASH_A)[0])
        ManifestRelease.promote(HASH_A, rings=["canary", "stable"], by="operator")
        self.assertTrue(may_receive(self.school, HASH_A)[0])

    def test_a_release_can_be_pulled_back(self):
        """Promotion is not monotonic: a bad release must be retractable."""
        ManifestRelease.promote(HASH_A, rings=["canary", "stable"])
        self.assertTrue(may_receive(self.school, HASH_A)[0])
        ManifestRelease.promote(HASH_A, rings=["canary"])
        self.assertFalse(may_receive(self.school, HASH_A)[0])

    def test_a_paused_school_is_held_even_on_a_fully_promoted_release(self):
        """Pause survives the next promotion; moving a school to an empty ring does not."""
        ManifestRelease.promote(HASH_A, rings=["canary", "stable"])
        EdgeRolloutPolicy.objects.create(school=self.school, ring=RolloutRing.STABLE, paused=True)
        allowed, reason = may_receive(self.school, HASH_A)
        self.assertFalse(allowed)
        self.assertIn("paused", reason)

    def test_pausing_a_canary_school_also_holds_it(self):
        ManifestRelease.promote(HASH_A, rings=["canary"])
        EdgeRolloutPolicy.objects.create(school=self.school, ring=RolloutRing.CANARY, paused=True)
        self.assertFalse(may_receive(self.school, HASH_A)[0])

    def test_no_manifest_is_refused_with_a_reason_not_a_crash(self):
        allowed, reason = may_receive(self.school, "")
        self.assertFalse(allowed)
        self.assertIn("no manifest", reason)

    def test_promotion_is_per_manifest_not_global(self):
        """Promoting one release must not silently release the next one."""
        ManifestRelease.promote(HASH_A, rings=["canary", "stable"])
        self.assertTrue(may_receive(self.school, HASH_A)[0])
        self.assertFalse(
            may_receive(self.school, HASH_B)[0],
            "a NEW manifest inherited the previous release's promotion; every future "
            "deploy would reach the whole fleet unreviewed",
        )

    def test_promote_ignores_an_unknown_ring_rather_than_storing_it(self):
        row = ManifestRelease.promote(HASH_A, rings=["canary", "moon"])
        self.assertEqual(row.rings, ["canary"])

    def test_promote_records_who_and_when(self):
        row = ManifestRelease.promote(HASH_A, rings=["stable"], by="ops@example.com", note="watched 2h")
        self.assertEqual(row.promoted_by, "ops@example.com")
        self.assertEqual(row.note, "watched 2h")
        self.assertIsNotNone(row.promoted_at)


class TenancyShapeTests(TestCase):
    """The two records are scoped differently on purpose; RLS coverage depends on it."""

    def test_rollout_policy_is_tenant_scoped(self):
        self.assertTrue(
            any(f.name == "school" for f in EdgeRolloutPolicy._meta.get_fields()),
            "EdgeRolloutPolicy lost its school FK; it is per-school state",
        )

    def test_manifest_release_is_not_tenant_scoped(self):
        """How far a release has been promoted is identical for every school."""
        self.assertFalse(
            any(f.name == "school" for f in ManifestRelease._meta.get_fields()),
            "ManifestRelease gained a school FK — it is fleet state, and the FK would "
            "enrol it in the tenant RLS coverage gate for data it does not hold",
        )


class HandshakeRespectsRingsTests(TestCase):
    """The advice header must not name a target the box will then be refused.

    A box told "upgrade available" that is then refused the bytes retries every cycle
    forever, and its operator sees a box that looks stuck. So an unreleased manifest is
    not advertised at all, rather than advertised-and-refused.
    """

    def setUp(self):
        super().setUp()
        self.school = _school("Handshake High")

    def _handshake(self, box_hash, target_hash):
        from unittest import mock

        from django.test import RequestFactory

        from apps.api.sync_bundle_api import _manifest_handshake
        from apps.sync_engine.edge_outbox import SYNC_MANIFEST_HEADER

        header = "HTTP_" + SYNC_MANIFEST_HEADER.upper().replace("-", "_")
        request = RequestFactory().get("/api/sync/bundle/download/", **{header: box_hash})
        with mock.patch(
            "apps.sync_engine.system_manifest.load_manifest",
            return_value={"manifest_hash": target_hash, "files": {}},
        ):
            return _manifest_handshake(request, self.school)

    def test_an_unreleased_target_is_not_advertised(self):
        target, advice = self._handshake(HASH_B, HASH_A)
        self.assertEqual(target, "", "the handshake advertised a manifest the box cannot fetch")
        self.assertEqual(advice, "")

    def test_a_released_target_is_advertised_with_the_reason(self):
        ManifestRelease.promote(HASH_A, rings=["canary", "stable"])
        target, advice = self._handshake(HASH_B, HASH_A)
        self.assertEqual(target, HASH_A)
        self.assertIn("upgrade available", advice)

    def test_an_unreleased_target_does_not_leave_the_school_held(self):
        """A school staying where it is must keep syncing its records."""
        from apps.sync_engine import upgrade_lock

        upgrade_lock.hold(self.school, target_hash=HASH_A, current_hash=HASH_B)
        self.assertTrue(upgrade_lock.is_held(self.school))
        self._handshake(HASH_B, HASH_A)
        self.assertFalse(
            upgrade_lock.is_held(self.school),
            "a school that is not released to yet was left holding its data sync",
        )
