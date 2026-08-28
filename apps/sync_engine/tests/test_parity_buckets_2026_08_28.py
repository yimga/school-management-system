"""One differing row must not cost the whole table.

G8 compares ONE digest per entity, so a single bad `subject_assignment` condemned all
41,755 of them to be re-shipped -- and a whole-entity pull re-offers every row the box
already holds, which is the same waste the corpus replay was. The repair was the shape
of the disease.

Folding the per-row digests into BUCKETS turns that into 1/N of a table. A bucket that
agrees is proof -- to the strength of sha256 over the rail fields -- that every row in
it is identical on both sides, and proof is exactly what lets the sender stop sending.

The bucket function hashes the SAME identity string `entity_digest` already folds over,
so both deployments bucket a row identically without exchanging anything. These tests
care most about the two ways that could be wrong: a row bucketed differently on the two
sides (the repair would serve the wrong rows and report success), and a comparison that
could not be made being mistaken for a comparison that found nothing (which withholds
rows the box needs -- silent data loss, the one failure mode worse than the waste).
"""
from __future__ import annotations

import uuid

from django.test import SimpleTestCase, TestCase

from apps.api.sync_services import _get_entity_config
from apps.sync_engine import parity
from apps.sync_engine.edge_outbox import build_edge_delta_bundle
from apps.sync_engine.delta_bundle import verify_and_parse_bundle


class TheBucketWireFormatTests(SimpleTestCase):
    def test_it_round_trips(self):
        d = {"buckets": 64, "b": {0: "aaaa", 7: "bbbb"}}
        self.assertEqual(parity.decode_buckets(parity.encode_buckets(d)), d)

    def test_the_fan_out_travels_with_the_digests(self):
        # Bucket 7 of 64 and bucket 7 of 128 hold different rows. Comparing them would
        # report drift on a converged table, forever.
        self.assertTrue(parity.encode_buckets({"buckets": 64, "b": {7: "x"}}).startswith("64|"))

    def test_a_version_this_one_has_never_met_decodes_to_nothing(self):
        for raw in ("", "nonsense", "abc|0:x", "0|0:x", "9999|0:x", "64"):
            self.assertEqual(parity.decode_buckets(raw), {}, raw)

    def test_a_row_lands_in_the_same_bucket_every_time(self):
        self.assertEqual(parity.row_bucket("pk:42", 64), parity.row_bucket("pk:42", 64))

    def test_the_rows_spread_across_the_buckets(self):
        # A hash that piled every row into one bucket would pass every other test here
        # and deliver none of the saving.
        used = {parity.row_bucket("pk:%d" % i, 64) for i in range(1000)}
        self.assertGreater(len(used), 50)

    def test_a_fan_out_of_one_is_the_old_whole_entity_behaviour(self):
        self.assertEqual(parity.row_bucket("anything", 1), 0)

    # -- the distinction that prevents silent data loss ----------------------

    def test_compared_and_agreeing_is_an_empty_list(self):
        d = {"buckets": 8, "b": {1: "aa"}}
        self.assertEqual(parity.drifting_buckets(d, d), [])

    def test_could_not_compare_is_None_not_an_empty_list(self):
        # An empty list serves NOTHING. None serves EVERYTHING. Confusing them withholds
        # rows the box needs, which is worse than any amount of over-sending.
        d = {"buckets": 8, "b": {1: "aa"}}
        self.assertIsNone(parity.drifting_buckets(d, {}))
        self.assertIsNone(parity.drifting_buckets({}, d))
        self.assertIsNone(parity.drifting_buckets(d, {"buckets": 16, "b": {1: "aa"}}))

    def test_a_bucket_only_one_side_has_is_drift(self):
        # One side holds rows the other does not. Comparing only the intersection would
        # report agreement about rows nobody compared.
        a = {"buckets": 8, "b": {1: "aa", 3: "cc"}}
        b = {"buckets": 8, "b": {1: "aa"}}
        self.assertEqual(parity.drifting_buckets(a, b), [3])


class TheDigestMustFollowTheDataTests(TestCase):
    """Against real rows, because the bucket is computed from the identity of a row."""

    def setUp(self):
        from apps.accounts.models import User
        from apps.schools.models import School, SchoolMembership

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Bucket {uid}", slug=f"bucket-{uid}", subdomain=f"bucket{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"bk_{uid}", password="Test1234", email=f"b{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.model, self.allowed = _get_entity_config(include_derived=True)["academic_year"]
        self.rows = [
            self.model.objects.create(
                school=self.school, name=f"Year {i} {uid}",
                start_date="2026-09-01", end_date="2027-07-31",
            )
            for i in range(12)
        ]

    def _digests(self):
        return parity.bucket_digests(
            self.school, "academic_year", self.model, self.allowed, buckets=8
        )

    def test_the_same_data_digests_the_same_way_twice(self):
        self.assertEqual(self._digests(), self._digests())

    def test_changing_one_row_moves_exactly_one_bucket(self):
        before = self._digests()
        row = self.rows[3]
        row.name = row.name + " renamed"
        row.save(update_fields=["name"])
        after = self._digests()

        drift = parity.drifting_buckets(before, after)
        self.assertEqual(len(drift), 1, "one edit should not condemn the whole table")
        # And it is the bucket that row actually lives in, not merely *a* bucket.
        self.assertEqual(drift[0], parity.row_bucket(f"pk:{row.pk}", 8))

    def test_the_fan_out_is_reported_so_the_other_side_can_agree(self):
        self.assertEqual(self._digests()["buckets"], 8)

    def test_a_bundle_row_buckets_the_same_way_the_digest_does(self):
        # THE failure this would hide: if the two spellings of identity disagree, the
        # repair serves rows from the wrong buckets and reports success.
        data, _meta = build_edge_delta_bundle(
            self.school, since=None, entities=["academic_year"], device_id="cloud"
        )
        rows, errors = verify_and_parse_bundle(data)
        self.assertFalse(errors, errors)
        self.assertTrue(rows)
        for row in rows:
            identity = parity.bundle_row_identity(row)
            self.assertEqual(identity, f"pk:{row['id']}")
            self.assertEqual(
                parity.row_bucket(identity, 8),
                parity.row_bucket(f"pk:{row['id']}", 8),
            )


class TheBundleMustCarryOnlyTheAskedForBucketsTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.schools.models import School, SchoolMembership

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Keep {uid}", slug=f"keep-{uid}", subdomain=f"keep{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"kp_{uid}", password="Test1234", email=f"k{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        model, _allowed = _get_entity_config(include_derived=True)["academic_year"]
        for i in range(12):
            model.objects.create(
                school=self.school, name=f"Year {i} {uid}",
                start_date="2026-09-01", end_date="2027-07-31",
            )

    def _bundle(self, keep):
        data, meta = build_edge_delta_bundle(
            self.school, since=None, entities=["academic_year"],
            device_id="cloud", keep_buckets=keep,
        )
        rows, errors = verify_and_parse_bundle(data)
        self.assertFalse(errors, errors)
        return rows, meta

    def test_no_filter_ships_everything(self):
        rows, meta = self._bundle(None)
        self.assertEqual(len(rows), 12)
        self.assertEqual(meta["row_count"], 12)

    def test_an_empty_bucket_set_ships_nothing(self):
        # "Compared, and every bucket agreed." Shipping the table anyway would make the
        # whole exchange pointless.
        rows, meta = self._bundle((8, set()))
        self.assertEqual(rows, [])
        self.assertEqual(meta["row_count"], 0)

    def test_only_the_named_buckets_ship(self):
        everything, _ = self._bundle(None)
        wanted = {parity.row_bucket(parity.bundle_row_identity(everything[0]), 8)}
        rows, meta = self._bundle((8, wanted))

        self.assertTrue(rows)
        self.assertLess(len(rows), 12, "narrowing shipped the whole table")
        self.assertEqual(meta["row_count"], len(rows), "row_count must match the body")
        for row in rows:
            self.assertIn(parity.row_bucket(parity.bundle_row_identity(row), 8), wanted)

    def test_the_signature_covers_the_filtered_body(self):
        # Filtering AFTER signing would ship a bundle whose signature does not verify;
        # filtering before the count is written would ship one whose count lies.
        rows, meta = self._bundle((8, {0, 1}))
        self.assertEqual(meta["row_count"], len(rows))

    def test_every_bucket_named_ships_the_whole_table_back(self):
        rows, _meta = self._bundle((8, set(range(8))))
        self.assertEqual(len(rows), 12)


class TheBoxMustOnlyOfferBucketsOnARepairPullTests(SimpleTestCase):
    """Buckets narrow a response. Sending them on a CURSOR pull could withhold rows the
    cursor then records as delivered, so the request shape is constrained at the source.
    """

    def _query(self, **kw):
        """The URL pull_bundle actually builds.

        Captured at Request construction and the transport short-circuited, so the test
        asserts on the real query string this function assembles rather than on a copy
        of the logic written here -- which would pass whatever the function did.
        """
        import urllib.request
        from unittest import mock

        from apps.sync_engine import edge_outbox

        seen = {}
        real_request = urllib.request.Request

        def _capture(url, *a, **kwargs):
            seen.setdefault("url", url)
            return real_request(url, *a, **kwargs)

        with mock.patch.object(urllib.request, "Request", _capture), mock.patch.object(
            edge_outbox, "call_with_gateway_retry", lambda *a, **k: (200, b"")
        ):
            edge_outbox.pull_bundle("https://hub.test/pull", "tok", **kw)
        return seen["url"]

    def test_a_single_entity_repair_pull_carries_them(self):
        url = self._query(since=None, entities=["subject"], parity_buckets="8|0:aa")
        self.assertIn("parity_buckets", url)

    def test_a_cursor_pull_does_not(self):
        url = self._query(
            since="2026-08-01T00:00:00+00:00", entities=["subject"], parity_buckets="8|0:aa"
        )
        self.assertNotIn("parity_buckets", url)

    def test_a_multi_entity_pull_does_not(self):
        url = self._query(since=None, entities=["subject", "student"], parity_buckets="8|0:aa")
        self.assertNotIn("parity_buckets", url)

    def test_the_guard_is_in_the_source_not_only_in_the_caller(self):
        # The behavioural tests above depend on the transport being patchable. This one
        # does not, so the constraint cannot silently stop being enforced.
        import inspect

        from apps.sync_engine import edge_outbox

        src = inspect.getsource(edge_outbox.pull_bundle)
        self.assertIn('if parity_buckets and len(ents) == 1 and not query.get("since"):', src)
