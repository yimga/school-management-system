"""Full resync — how a box that has missed a lot of changes catches up.

The cloud cannot reach a box on a private LAN, so "make the box replay everything" cannot
be a cloud->box call. It is a DIRECTIVE the cloud records and the box collects on its own
next download, riding the response it was already going to receive.

Locked here:
  * the download endpoint stamps ``X-RMC-Sync-Directive`` and marks the directive served,
    ONCE (a one-shot, so one request cannot cause a resync loop);
  * the box, on collecting it, rewinds BOTH cursors so the next cycle replays the corpus —
    and does NOT let that same cycle's delta high-water silently cancel the rewind;
  * the request is idempotent while pending, and observable before and after delivery;
  * the box-side ``edge_sync_resync`` command is the same primitive for an operator who is
    already on the box.
"""
from __future__ import annotations

import datetime as dt
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.schools.models import School
from apps.sync_engine.edge_outbox import SYNC_DIRECTIVE_HEADER
from apps.sync_engine.models import (
    EdgeSyncCursor,
    EdgeSyncDirective,
    claim_pending_directive,
    get_sync_cursor,
    request_full_resync,
    set_sync_cursor,
)

_POST = "apps.sync_engine.edge_outbox.post_bundle"
_PULL = "apps.sync_engine.edge_outbox.pull_bundle"


class DirectiveLifecycleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Directive School", slug="directive-school", subdomain="directive-school"
        )

    def test_request_is_idempotent_while_pending(self):
        first = request_full_resync(self.school)
        second = request_full_resync(self.school)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(EdgeSyncDirective.objects.filter(school=self.school).count(), 1)

    def test_claim_marks_served_and_never_serves_twice(self):
        request_full_resync(self.school)
        claimed = claim_pending_directive(self.school)
        self.assertIsNotNone(claimed)
        self.assertIsNotNone(claimed.served_at)
        self.assertIsNone(
            claim_pending_directive(self.school),
            "a served directive was handed out again — one request would resync forever",
        )

    def test_a_new_request_after_delivery_is_a_fresh_directive(self):
        request_full_resync(self.school)
        claim_pending_directive(self.school)
        again = request_full_resync(self.school)
        self.assertIsNone(again.served_at)
        self.assertEqual(EdgeSyncDirective.objects.filter(school=self.school).count(), 2)

    def test_claim_on_a_school_with_no_directive_is_none(self):
        self.assertIsNone(claim_pending_directive(self.school))


@override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://hub.test")
class BoxHonoursTheDirectiveTests(TestCase):
    """The box rewinds on collection — and the rewind must survive the same cycle."""

    def setUp(self):
        get_user_model().objects.filter(is_superuser=True).delete()
        get_user_model().objects.create_superuser(
            username="resync-principal", email="r@example.test", password="x"
        )
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Resync Box", slug="resync-box", subdomain="resync-box", is_active=True
        )
        AcademicYear.objects.create(
            school=self.school,
            name="Y1",
            start_date=dt.date(2024, 9, 1),
            end_date=dt.date(2025, 6, 30),
        )
        # Pretend both directions are already well past everything.
        self.old = timezone.now()
        set_sync_cursor(self.school, EdgeSyncCursor.PUSH, self.old)
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, self.old)

    def _cycle(self, *, directive="", mode="live"):
        from apps.sync_engine import sync_runner
        from apps.sync_engine.delta_bundle import export_delta_bundle

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            if collect is not None:
                collect["directive"] = directive
            # A non-empty high-water: the pre-fix bug was that this value, recorded on the
            # SAME cycle, silently cancelled the rewind.
            return (
                200,
                export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="cloud"),
                timezone.now().isoformat(),
            )

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ):
            return sync_runner.run_sync_cycle(self.school, mode=mode)

    def test_no_directive_leaves_the_cursors_alone(self):
        self._cycle(directive="")
        self.assertIsNotNone(get_sync_cursor(self.school, EdgeSyncCursor.PUSH))
        self.assertIsNotNone(get_sync_cursor(self.school, EdgeSyncCursor.PULL))

    def test_full_resync_rewinds_both_cursors(self):
        result = self._cycle(directive="full-resync")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIsNone(
            get_sync_cursor(self.school, EdgeSyncCursor.PUSH), "push cursor not rewound"
        )
        self.assertIsNone(
            get_sync_cursor(self.school, EdgeSyncCursor.PULL),
            "pull cursor was rewound and then immediately re-advanced by this same "
            "cycle's delta high-water, cancelling the resync",
        )
        self.assertIn("full resync", result["message"])

    def test_the_next_cycle_after_a_rewind_really_replays_everything(self):
        self._cycle(directive="full-resync")
        seen = {}

        def _pull(endpoint, token, *, since=None, entities=None, timeout=30.0, collect=None, **_kw):
            from apps.sync_engine.delta_bundle import export_delta_bundle

            seen["since"] = since
            if collect is not None:
                collect["directive"] = ""
            return (
                200,
                export_delta_bundle(school_id=str(self.school.id), rows=[], device_id="cloud"),
                None,
            )

        with mock.patch(_PULL, side_effect=_pull), mock.patch(
            _POST, return_value=(200, {"ok": True})
        ):
            from apps.sync_engine import sync_runner

            sync_runner.run_sync_cycle(self.school, mode="live")
        self.assertIsNone(seen["since"], "the post-resync pull still carried a cursor")

    def test_dry_run_never_rewinds(self):
        """A read-only probe must not mutate sync position."""
        self._cycle(directive="full-resync", mode="dry")
        self.assertIsNotNone(get_sync_cursor(self.school, EdgeSyncCursor.PUSH))
        self.assertIsNotNone(get_sync_cursor(self.school, EdgeSyncCursor.PULL))


class DownloadEndpointStampsDirectiveTests(TestCase):
    """The directive must ride the box's OWN download — the only channel that exists."""

    def test_response_carries_the_directive_header_and_consumes_it(self):
        from apps.api.sync_bundle_api import SyncBundleDownloadView

        school = School.objects.create(
            name="Stamp School", slug="stamp-school", subdomain="stamp-school"
        )
        request_full_resync(school)

        with mock.patch(
            "apps.api.sync_bundle_api.build_edge_delta_bundle",
            return_value=(b"bundle", {"row_count": 0, "high_water_iso": None}),
        ), mock.patch(
            "apps.api.sync_bundle_api.user_may_operate_on_school", return_value=True
        ):
            view = SyncBundleDownloadView()
            # META must be a real dict: the download path now reads the box's
            # upgrade-failure header from request.META before stamping anything.
            request = mock.Mock(
                school=school, query_params={}, user=mock.Mock(), META={}
            )
            first = view.get(request)
            second = view.get(request)

        self.assertEqual(first[SYNC_DIRECTIVE_HEADER], EdgeSyncDirective.FULL_RESYNC)
        self.assertNotIn(
            SYNC_DIRECTIVE_HEADER,
            second,
            "the directive was re-stamped on a second download — a resync loop",
        )


class ResyncCommandTests(TestCase):
    def setUp(self):
        School.objects.update(is_active=False)
        self.school = School.objects.create(
            name="Cmd Box", slug="cmd-box", subdomain="cmd-box", is_active=True
        )
        set_sync_cursor(self.school, EdgeSyncCursor.PUSH, timezone.now())
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, timezone.now())

    def test_rewinds_both_directions_without_running_a_cycle(self):
        out = StringIO()
        with mock.patch("apps.sync_engine.sync_runner.run_sync_cycle") as cycle:
            call_command("edge_sync_resync", slug="cmd-box", stdout=out)
        cycle.assert_not_called()
        self.assertIsNone(get_sync_cursor(self.school, EdgeSyncCursor.PUSH))
        self.assertIsNone(get_sync_cursor(self.school, EdgeSyncCursor.PULL))
        self.assertIn("rewound", out.getvalue())

    def test_direction_filter_rewinds_only_that_direction(self):
        call_command("edge_sync_resync", slug="cmd-box", direction="pull", stdout=StringIO())
        self.assertIsNone(get_sync_cursor(self.school, EdgeSyncCursor.PULL))
        self.assertIsNotNone(get_sync_cursor(self.school, EdgeSyncCursor.PUSH))

    def test_run_drains_until_a_cycle_reports_nothing_left(self):
        out = StringIO()
        results = [
            {"enabled": True, "ok": True, "pushed": 5, "pulled": 0},
            {"enabled": True, "ok": True, "pushed": 0, "pulled": 0},
        ]
        with mock.patch(
            "apps.sync_engine.sync_runner.run_sync_cycle", side_effect=results
        ) as cycle:
            call_command("edge_sync_resync", slug="cmd-box", run=True, stdout=out)
        self.assertEqual(cycle.call_count, 2)
        self.assertIn("drained", out.getvalue())

    def test_run_stops_on_error_rather_than_spinning(self):
        with mock.patch(
            "apps.sync_engine.sync_runner.run_sync_cycle",
            return_value={"enabled": True, "ok": False, "pushed": 0, "pulled": 0, "error": "boom"},
        ) as cycle:
            call_command(
                "edge_sync_resync",
                slug="cmd-box",
                run=True,
                stdout=StringIO(),
                stderr=StringIO(),
            )
        self.assertEqual(cycle.call_count, 1)
