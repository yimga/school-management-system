"""G4: an appliance a month behind must be told, and must still get its attendance.

The LOCAL half already existed (``schema_guard.drift_note`` — "this box is N migrations
behind, run migrate"). It cannot answer the question that actually breaks a cycle: is the
deployment I am TALKING TO on a different schema from mine? A box behind on migrations
receives rows referencing columns it does not have. Those degrade per row rather than
killing the bundle, but the box still silently fails to receive whole entities and nobody
is told why — an operator sees "12 NOT applied" with no cause.

DEGRADE, DO NOT REFUSE. The tempting design refuses the whole cycle on any skew, which
takes a school offline for a migration it may not need. The comparison is therefore per
APP, and only the entities owned by an app the box is behind on are withheld: a box stale
only on `finance` keeps receiving attendance, timetables and marks.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleDownloadView, _schema_handshake
from apps.api.sync_services import entity_app_labels
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_outbox import (
    SYNC_SCHEMA_ADVICE_HEADER,
    SYNC_SCHEMA_HEAD_HEADER,
    SYNC_WITHHELD_HEADER,
    local_schema_head_header,
    mint_edge_credential,
)
from apps.sync_engine.schema_guard import (
    compare_heads,
    decode_heads,
    describe_skew,
    encode_heads,
    local_migration_heads,
)

_SIGN_KEY = "schema-handshake-test-key"


class HeadEncodingTests(TestCase):
    def test_round_trip(self):
        heads = {"academics": "0083_x", "finance": "0120_y"}
        self.assertEqual(decode_heads(encode_heads(heads)), heads)

    def test_the_encoding_is_sorted_and_header_safe(self):
        raw = encode_heads({"finance": "0120_y", "academics": "0083_x"})
        self.assertEqual(raw, "academics=0083_x,finance=0120_y")
        self.assertNotIn("\n", raw)

    def test_garbage_decodes_to_nothing_rather_than_raising(self):
        self.assertEqual(decode_heads("nonsense;;;"), {})
        self.assertEqual(decode_heads(""), {})

    def test_the_local_heads_cover_every_app_that_owns_a_synced_entity(self):
        """A new entity whose app is unknown here would be invisible to the handshake —
        it would never be withheld, so a stale box would keep failing on it in silence."""
        heads = local_migration_heads(set(entity_app_labels().values()))
        self.assertTrue(heads, "no migration heads resolved at all")
        self.assertIn("academics", heads)


class HeadComparisonTests(TestCase):
    def test_a_peer_on_an_older_migration_is_behind(self):
        result = compare_heads({"academics": "0080_a"}, {"academics": "0083_b"})
        self.assertIn("academics", result["behind"])
        self.assertFalse(result["ahead"])

    def test_a_peer_on_a_newer_migration_is_ahead(self):
        result = compare_heads({"finance": "0130_z"}, {"finance": "0120_y"})
        self.assertIn("finance", result["ahead"])

    def test_an_app_the_peer_did_not_report_is_treated_as_compatible(self):
        """A sender that predates the handshake keeps working exactly as before —
        silence must never be read as "behind"."""
        result = compare_heads({}, {"academics": "0083_b"})
        self.assertEqual(result, {"behind": {}, "ahead": {}})

    def test_the_message_names_the_app_both_versions_and_the_remedy(self):
        note = describe_skew(compare_heads({"academics": "0080_a"}, {"academics": "0083_b"}))
        self.assertIn("academics", note)
        self.assertIn("0080_a", note)
        self.assertIn("0083_b", note)
        self.assertIn("migrate", note)


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class DownloadHandshakeTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Skew {uid}", slug=f"skew-{uid}", subdomain=f"skew{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"skew_{uid}", password="Test1234", email=f"s{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.token, _obj = mint_edge_credential(
            self.school, self.user, device_id="skew-box", days=30
        )
        self.rf = APIRequestFactory()

    def _get(self, head_header=None):
        extra = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}
        if head_header is not None:
            extra["HTTP_" + SYNC_SCHEMA_HEAD_HEADER.upper().replace("-", "_")] = head_header
        request = self.rf.get("/api/v1/sync/bundle/download/", **extra)
        return SyncBundleDownloadView.as_view()(request)

    def test_a_box_on_the_same_schema_gets_everything(self):
        resp = self._get(local_schema_head_header())
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(SYNC_WITHHELD_HEADER, resp)

    def test_a_box_that_says_nothing_is_treated_as_compatible(self):
        resp = self._get(None)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(SYNC_WITHHELD_HEADER, resp)

    def test_a_box_behind_on_one_app_has_only_that_app_withheld(self):
        """The whole point: a stale `finance` must not cost the school its attendance."""
        resp = self._get("finance=0001_initial")
        self.assertEqual(resp.status_code, 200)
        withheld = set((resp[SYNC_WITHHELD_HEADER] or "").split(","))
        self.assertIn("invoice", withheld)
        self.assertNotIn("attendance", withheld)
        self.assertNotIn("student", withheld)
        self.assertIn("finance", resp[SYNC_SCHEMA_ADVICE_HEADER])

    def test_the_advice_tells_the_operator_what_to_do(self):
        resp = self._get("finance=0001_initial")
        self.assertIn("migrate", resp[SYNC_SCHEMA_ADVICE_HEADER])

    def test_a_box_AHEAD_of_the_cloud_is_not_withheld_from(self):
        """Being ahead is the cloud's problem, not the box's: the box can accept every
        column the cloud can produce. Withholding here would starve a healthy box."""
        request = self.rf.get(
            "/api/v1/sync/bundle/download/",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
            **{"HTTP_" + SYNC_SCHEMA_HEAD_HEADER.upper().replace("-", "_"): "academics=9999_future"},
        )
        withheld, advice = _schema_handshake(request)
        self.assertEqual(withheld, set())
        self.assertIn("AHEAD", advice)
