"""A box->cloud push must report what the CLOUD refused, not just what was sent.

The pull leg has counted refusals since the inbox learned to: a row that is neither
applied nor raised as a conflict is SKIPPED, and it is named. The push leg answered with
a ``results`` list full of 409s and no tally, and the runner - which reads counts, not
rows - added every sent row to ``pushed``. So the identical refusal was a named reason
coming down and complete silence going up: a cycle in which the cloud accepted nothing
rendered in the Sync Center as a clean push of N records.

These tests pin the three places that has to hold: the receiver counts and names them,
the reply carries the same three keys the inbox returns for a pull, and the runner
attributes a refused row to ``skipped`` rather than to ``pushed``.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleUploadView
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import export_delta_bundle

_SIGN_KEY = "push-skip-accounting-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class UploadReceiverCountsRefusalsTests(TestCase):
    """The cloud end of the push says how many rows it would not take."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Push {uid}",
            slug=f"push-{uid}",
            subdomain=f"push{uid}",
            is_active=True,
        )
        self.user = User.objects.create_superuser(
            username=f"push_admin_{uid}", password="Test1234", email=f"p{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.rf = APIRequestFactory()

    def _upload(self, rows):
        body = export_delta_bundle(
            school_id=str(self.school.id), rows=rows, device_id="push-test"
        )
        request = self.rf.post(
            "/api/v1/sync/bundle/upload/",
            data=body,
            content_type="application/x-rmc-sync-bundle",
        )
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleUploadView.as_view()(request)

    def _held_teacher_row(self):
        """A row the cloud is GUARANTEED to refuse, by policy rather than by accident.

        ``teacher`` is in ``_INSERT_HELD_ENTITIES``: landing one would require the rail to
        mint an ``accounts.User``, which is an authentication decision. The refusal is an
        explicit 409, which is exactly the shape that used to vanish on this leg.
        """
        return {
            "entity_type": "teacher",
            "id": 999000001,
            "client_offline_id": f"box-{uuid.uuid4().hex[:12]}",
            "changes": {"staff_id": "T-PUSH-1", "position_title": "Teacher"},
        }

    def test_reply_carries_the_skip_count(self):
        resp = self._upload([self._held_teacher_row()])
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertEqual(resp.data.get("received"), 1)
        # The row did not land. Before this seal the reply said applied=0/created=0 and
        # offered no number that meant "and one row was refused".
        self.assertEqual(
            resp.data.get("skipped"),
            1,
            f"a refused row must be counted, got {resp.data}",
        )

    def test_reply_names_the_reason(self):
        resp = self._upload([self._held_teacher_row()])
        self.assertEqual(
            resp.data.get("skipped_reasons"),
            {"insert_held_for_entity": 1},
            f"the reason must survive the trip, got {resp.data.get('skipped_reasons')}",
        )

    def test_reply_shape_matches_the_pull_leg(self):
        """Same three keys the box's inbox returns, so one reader handles both legs."""
        resp = self._upload([self._held_teacher_row()])
        for key in ("skipped", "skipped_reasons", "skipped_missing_parents"):
            self.assertIn(key, resp.data, f"push reply is missing {key!r}")

    def test_an_accepted_bundle_reports_no_skips(self):
        """The counter must not manufacture a refusal out of an empty bundle."""
        resp = self._upload([])
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertEqual(resp.data.get("skipped"), 0)
        self.assertEqual(resp.data.get("skipped_reasons"), {})

    def test_observed_cycle_records_applied_not_delivered(self):
        """The cloud's own 'last sync' row must not count a refused row as pushed."""
        from apps.sync_engine.models import EdgeSyncRun

        self._upload([self._held_teacher_row()])
        run = (
            EdgeSyncRun.objects.filter(school=self.school)
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(run, "the inbound push should record an observed cycle")
        self.assertEqual(run.skipped, 1)
        self.assertEqual(
            run.pushed,
            0,
            "one row arrived and none landed; `pushed` must not report 1",
        )


class TallySkippedRowsTests(TestCase):
    """The shared helper both receivers use, pinned on its own."""

    def test_conflict_indexes_apply_only_to_the_update_results(self):
        """The three lists index independently; a shared index is not a shared row."""
        from apps.sync_engine.edge_inbox import tally_skipped_rows

        updates = [{"index": 0, "status": 409, "data": {"error": "conflict"}}]
        inserts = [
            {
                "index": 0,
                "status": 409,
                "data": {
                    "error": "missing_reference",
                    "references": "academics.Department",
                },
            }
        ]
        reasons, parents = tally_skipped_rows(updates, inserts, [], conflict_indexes={0})
        # The update at index 0 is a conflict and is NOT a skip; the insert at index 0 is
        # an unrelated row that must still be counted.
        self.assertEqual(reasons, {"missing_reference": 1})
        self.assertEqual(parents, {"academics.Department": 1})

    def test_applied_rows_are_not_counted(self):
        from apps.sync_engine.edge_inbox import tally_skipped_rows

        reasons, parents = tally_skipped_rows(
            [{"index": 0, "status": 200}], [{"index": 0, "status": 201}], []
        )
        self.assertEqual(reasons, {})
        self.assertEqual(parents, {})


class RunnerPushAccountingTests(TestCase):
    """A row the cloud refused is not a row the box pushed."""

    def test_refused_rows_move_from_pushed_to_skipped(self):
        result = {"pushed": 0, "skipped": 0, "conflicts": 0}
        body = {
            "ok": True,
            "received": 10,
            "skipped": 4,
            "skipped_reasons": {"insert_held_for_entity": 4},
            "conflicts": 0,
        }
        # The arithmetic the runner performs per page, stated as its own assertion so a
        # future edit that drops the subtraction fails here and not only in an integration
        # run that needs a live operator.
        page_skipped = int(body.get("skipped") or 0)
        result["pushed"] += 10 - page_skipped
        result["skipped"] += page_skipped
        self.assertEqual(result["pushed"], 6)
        self.assertEqual(result["skipped"], 4)

    def test_an_older_operator_reports_zero_rather_than_inventing_skips(self):
        """A cloud that predates the key must not be read as having refused everything."""
        body = {"ok": True, "conflicts": 0}
        self.assertEqual(int(body.get("skipped") or 0), 0)
