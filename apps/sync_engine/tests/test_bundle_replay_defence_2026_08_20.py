"""A signature proves WHO built a bundle. It never proves you have not seen it before.

Every delta bundle is HMAC-signed over HTTPS with a bearer edge credential, which
authenticates the builder and protects the bytes in flight. Anyone who can obtain the
bundle afterwards — a LAN data-mule USB stick, a logging proxy, a backup of the box's
spool directory — can present the identical bytes later and the signature verifies
perfectly, every time.

That is not merely wasteful now that deletions propagate. A bundle captured BEFORE a row
was deleted resurrects that row: its payload predates the tombstone, so the burial does
not dominate it. A bundle captured before a human resolved a conflict re-applies the value
they decided against.

The defence is a random nonce inside the SIGNED header — so it cannot be rewritten to
disguise a capture as a fresh build — recorded per school and refused on a second sighting.
"""
from __future__ import annotations

import time
import uuid

from django.test import TestCase, override_settings

from apps.academics.models import Department
from apps.accounts.models import User
from apps.schools.models import School
from apps.sync_engine.delta_bundle import export_delta_bundle, verify_and_parse_bundle
from apps.sync_engine.models import SyncBundleReceipt
from apps.sync_engine.replay_guard import (
    check_bundle_freshness,
    prune_receipts,
    register_bundle,
)

_SIGN_KEY = "replay-defence-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class BundleNonceTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Replay {uid}", slug=f"replay-{uid}", subdomain=f"replay{uid}"
        )
        self.user = User.objects.create_superuser(
            username=f"replay_{uid}", password="Test1234", email=f"r{uid}@t.com"
        )
        self.dept = Department.objects.create(school=self.school, name="D", code=f"D-{uid}")

    def _bundle(self):
        return export_delta_bundle(
            school_id=str(self.school.id),
            rows=[{
                "entity_type": "department", "id": self.dept.pk,
                "changes": {"name": "Renamed"}, "updated_at": "2026-08-20T09:00:00+00:00",
            }],
            device_id="box",
        )

    def _parse(self, data):
        collected = {}
        rows, errors = verify_and_parse_bundle(
            data, expected_school_id=self.school.pk, collect=collected
        )
        self.assertEqual(errors, [])
        return rows, collected

    def test_the_nonce_rides_inside_the_signed_payload(self):
        """Outside the signature it would be rewritable, and the defence cosmetic."""
        _rows, collected = self._parse(self._bundle())
        self.assertTrue(collected["header"].get("nonce"))

    def test_two_builds_of_the_same_rows_get_different_nonces(self):
        """A legitimate retry after a network timeout must still be accepted."""
        _r1, c1 = self._parse(self._bundle())
        _r2, c2 = self._parse(self._bundle())
        self.assertNotEqual(c1["header"]["nonce"], c2["header"]["nonce"])

    def test_the_first_delivery_is_accepted_and_the_replay_is_refused(self):
        data = self._bundle()
        rows, collected = self._parse(data)
        self.assertEqual(register_bundle(self.school, collected, row_count=len(rows)), "")

        _again, collected_again = self._parse(data)  # the identical captured bytes
        self.assertEqual(
            register_bundle(self.school, collected_again, row_count=len(rows)),
            "bundle_replayed",
        )

    def test_a_rebuilt_bundle_is_not_mistaken_for_a_replay(self):
        rows, first = self._parse(self._bundle())
        register_bundle(self.school, first, row_count=len(rows))
        rows2, second = self._parse(self._bundle())
        self.assertEqual(register_bundle(self.school, second, row_count=len(rows2)), "")

    def test_a_replay_aimed_at_another_school_is_independent(self):
        """Receipts are per school, matching the school binding the bundle already has."""
        other = School.objects.create(name="Other", slug="other-rp", subdomain="otherrp")
        rows, collected = self._parse(self._bundle())
        self.assertEqual(register_bundle(self.school, collected, row_count=len(rows)), "")
        self.assertEqual(register_bundle(other, collected, row_count=len(rows)), "")

    def test_an_empty_bundle_is_not_recorded(self):
        """At a 20s cadence the overwhelmingly common bundle carries nothing; recording
        those would fill the table with rows that protect against nothing."""
        rows, collected = self._parse(
            export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="box")
        )
        self.assertEqual(register_bundle(self.school, collected, row_count=len(rows)), "")
        self.assertEqual(SyncBundleReceipt.objects.count(), 0)

    @override_settings(RMC_SYNC_BUNDLE_REPLAY_DEFENCE=False)
    def test_the_kill_switch_accepts_a_replay(self):
        rows, collected = self._parse(self._bundle())
        register_bundle(self.school, collected, row_count=len(rows))
        _again, collected_again = self._parse(self._bundle())
        self.assertEqual(register_bundle(self.school, collected_again, row_count=1), "")

    def test_receipts_outside_the_window_are_pruned(self):
        from datetime import timedelta

        from django.utils import timezone

        rows, collected = self._parse(self._bundle())
        register_bundle(self.school, collected, row_count=len(rows))
        SyncBundleReceipt.objects.update(
            received_at=timezone.now() - timedelta(days=30)
        )
        self.assertEqual(prune_receipts(self.school), 1)


class BundleFreshnessTests(TestCase):
    """The window IS the guarantee, so a bundle older than it must be refused."""

    def test_a_bundle_inside_the_window_is_fresh(self):
        self.assertEqual(check_bundle_freshness({"exported_at": int(time.time())}), "")

    def test_a_bundle_older_than_the_window_is_refused(self):
        old = int(time.time()) - (8 * 24 * 3600)
        self.assertEqual(check_bundle_freshness({"exported_at": old}), "bundle_expired")

    def test_a_bundle_from_the_future_names_the_clock(self):
        """An appliance without an RTC comes up with a wrong clock routinely, so this is
        a diagnosis to surface, not an attack to hide."""
        ahead = int(time.time()) + (3 * 24 * 3600)
        self.assertEqual(check_bundle_freshness({"exported_at": ahead}), "bundle_clock_ahead")

    def test_a_sender_that_stamps_nothing_is_not_aged_out(self):
        """Backwards compatibility: the nonce still protects such a sender."""
        self.assertEqual(check_bundle_freshness({}), "")

    @override_settings(RMC_SYNC_BUNDLE_REPLAY_WINDOW_SECONDS=60)
    def test_the_window_is_configurable(self):
        old = int(time.time()) - 120
        self.assertEqual(check_bundle_freshness({"exported_at": old}), "bundle_expired")
