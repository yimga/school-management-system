"""A queued repair that never drains strands the import with no way out.

Reported from a live tenant: "Repair this import" was pressed and the board went
Needs review (50%) -> Running (75%) -> Queued (75%) and stayed there, with
created / updated / held frozen at 0 / 105 / 442 in every state.

Three independent defects produce exactly that, and each is pinned below.

D1  ``repair_bundle`` flips the bundle to MAPPED and *then* enqueues. If the
    queued apply is never drained, the bundle is stranded at MAPPED, where NO
    recovery path recognises it: ``repair_readiness`` answers "this upload
    hasn't been imported yet" (so the Repair button is withdrawn),
    ``applying_stale_by_time`` only inspects APPLYING, and the outbox reclaim
    only inspects PROCESSING. A dead end with no operator affordance.

D2  The apply idempotency key ``mc-apply:<id>:live:active`` matches PENDING and
    PROCESSING rows, so once a row is wedged every later enqueue returns that
    same dead row. The caller is told "queued" while nothing was queued, which
    is why pressing Repair again changes nothing.

D3  ``refresh_snapshot`` aggregates EVERY progress event for the bundle with no
    run boundary, and stage pct only ever ratchets up
    (``if pct > by_stage[s]["pct"]``). A repair therefore inherits the previous
    run's APPLYING pct (100) and its last live totals, which is where the frozen
    75% and the frozen 0 / 105 / 442 come from -- the bar replays the last run.
"""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
    MigrationProgressEvent,
)
from apps.migration_cloud.progress import refresh_snapshot
from apps.migration_cloud.repair import repair_bundle, repair_readiness
from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox


def _bundle(key: str, status: str, *, quarantined: int = 0) -> MigrationBundle:
    b = MigrationBundle.objects.create(
        label="repair-wedge",
        intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=f"repair-wedge-{key}",
        status=status,
        school=None,
    )
    if quarantined:
        b.mapping_summary = {
            "apply_totals": {
                "created": 0,
                "updated": 105,
                "quarantined": quarantined,
                "applied_at": timezone.now().isoformat(),
            }
        }
        b.save(update_fields=["mapping_summary"])
    return b


def _apply_row(bundle, status, *, age_seconds: int = 0) -> HeavyWorkOutbox:
    row = HeavyWorkOutbox.objects.create(
        kind=HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE,
        bundle_id=bundle.pk,
        payload={"bundle_id": bundle.pk, "dry_run": False, "reconcile_after": True},
        idempotency_key=f"mc-apply:{bundle.pk}:live:active",
        status=status,
    )
    if age_seconds:
        old = timezone.now() - timedelta(seconds=age_seconds)
        HeavyWorkOutbox.objects.filter(pk=row.pk).update(created_at=old, claimed_at=old)
        row.refresh_from_db()
    return row


class RepairWedgeTests(TestCase):
    """D1 + D2 — the reported 'Repair does nothing' dead end."""

    def test_queued_repair_that_never_drains_is_not_a_dead_end(self):
        """D1: stranded at MAPPED, every recovery path declines to see it."""
        b = _bundle("strand", BundleStatus.APPLIED, quarantined=442)
        self.assertTrue(repair_readiness(b).repairable)  # button offered

        result = repair_bundle(bundle_id=b.pk, off_http=True)
        self.assertTrue(result.queued)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.MAPPED)

        # Nothing drains the row. Age it well past any stuck threshold.
        HeavyWorkOutbox.objects.filter(bundle_id=b.pk).update(
            created_at=timezone.now() - timedelta(hours=6)
        )

        # The tenant presses Repair again. Before the fix this is refused with
        # "This upload hasn't been imported yet - preview and import it first",
        # so the ONLY recovery control on the page is withdrawn and the import
        # can never be rescued from the UI.
        again = repair_readiness(b)
        self.assertTrue(
            again.repairable,
            "a repair stranded at MAPPED with a long-dead queued apply must stay "
            "recoverable; got refusal: %r" % (again.reason,),
        )

    def test_second_repair_enqueues_real_work_not_the_wedged_row(self):
        """D2: the idempotency key silently re-serves the dead row."""
        b = _bundle("dedupe", BundleStatus.APPLIED, quarantined=442)
        wedged = _apply_row(b, HeavyWorkOutbox.Status.PENDING, age_seconds=6 * 3600)

        result = repair_bundle(bundle_id=b.pk, off_http=True)
        self.assertTrue(result.queued)

        # Before the fix: the returned outbox id IS the six-hour-old dead row and
        # no new row exists, so the "queued" message is untrue.
        self.assertNotEqual(
            str(result.outbox_id),
            str(wedged.pk),
            "repair re-served the wedged outbox row instead of queueing work",
        )
        wedged.refresh_from_db()
        self.assertIn(
            wedged.status,
            (HeavyWorkOutbox.Status.FAILED, HeavyWorkOutbox.Status.SUCCEEDED),
            "the superseded row must be retired, not left PENDING forever",
        )

    def test_fresh_queued_apply_is_still_deduped(self):
        """The dedupe must survive for its real purpose: double-clicks."""
        b = _bundle("fresh", BundleStatus.APPLIED, quarantined=7)
        fresh = _apply_row(b, HeavyWorkOutbox.Status.PENDING)  # just queued

        result = repair_bundle(bundle_id=b.pk, off_http=True)

        self.assertEqual(
            str(result.outbox_id),
            str(fresh.pk),
            "a freshly queued apply must still collapse a double-click into one run",
        )
        self.assertEqual(
            HeavyWorkOutbox.objects.filter(bundle_id=b.pk).count(),
            1,
            "double-click must not fan out into duplicate applies",
        )


class LiveProgressRunBoundaryTests(TestCase):
    """D3 — the board replays the previous run instead of reporting this one."""

    def _previous_run_events(self, bundle) -> None:
        """A completed apply: APPLYING pulsed to 100% with 0/105/442."""
        MigrationProgressEvent.objects.create(
            bundle=bundle, kind="stage_started", stage="APPLYING", detail={}
        )
        MigrationProgressEvent.objects.create(
            bundle=bundle,
            kind="artifact_progress",
            stage="APPLYING",
            detail={"pct": 100, "created": 0, "updated": 105, "quarantined": 442},
        )
        old = timezone.now() - timedelta(hours=2)
        MigrationProgressEvent.objects.filter(bundle=bundle).update(created_at=old)

    def test_repair_does_not_inherit_the_previous_runs_percent(self):
        b = _bundle("pct", BundleStatus.APPLIED, quarantined=442)
        self._previous_run_events(b)

        # A repair begins: status back to MAPPED, a new run starting now.
        repair_bundle(bundle_id=b.pk, off_http=True)
        b.refresh_from_db()

        snap = refresh_snapshot(bundle=b, persist=False)
        applying = next(s for s in snap["stages"] if s["name"] == "APPLYING")
        self.assertEqual(
            applying["pct"],
            0,
            "the new run inherited the previous run's APPLYING pct, which is what "
            "pins the board at 75%% before any work has happened",
        )

    def test_repair_does_not_inherit_the_previous_runs_live_totals(self):
        b = _bundle("totals", BundleStatus.APPLIED, quarantined=442)
        self._previous_run_events(b)

        repair_bundle(bundle_id=b.pk, off_http=True)
        b.refresh_from_db()

        snap = refresh_snapshot(bundle=b, persist=False)
        self.assertEqual(
            snap.get("live_totals") or {},
            {},
            "the new run reported the previous run's 0/105/442 as its own live "
            "counts, so the tenant sees 442 held before the repair has written "
            "anything",
        )

    def test_events_from_the_current_run_are_still_counted(self):
        """The boundary must not blind the board to the run it is watching."""
        b = _bundle("current", BundleStatus.APPLIED, quarantined=442)
        self._previous_run_events(b)
        repair_bundle(bundle_id=b.pk, off_http=True)
        b.refresh_from_db()

        MigrationProgressEvent.objects.create(
            bundle=b,
            kind="artifact_progress",
            stage="APPLYING",
            detail={"pct": 40, "created": 12, "updated": 3, "quarantined": 1},
        )

        snap = refresh_snapshot(bundle=b, persist=False)
        applying = next(s for s in snap["stages"] if s["name"] == "APPLYING")
        self.assertEqual(applying["pct"], 40)
        totals = snap["live_totals"]
        self.assertEqual(totals["created"], 12)
        self.assertEqual(totals["updated"], 3)
        self.assertEqual(totals["quarantined"], 1)


class StuckApplySelfHealTests(TestCase):
    """A stranded queued apply must be rescued by the heartbeat that exists.

    The tenant progress poller runs in the web process every ~2.5s while someone
    is watching. It needs no Celery worker and no beat, which makes it the only
    heartbeat guaranteed to be alive during exactly the failure being recovered.
    """

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_wedged_queued_apply_triggers_a_local_drain(self):
        from apps.migration_cloud.repair import nudge_stuck_apply

        b = _bundle("nudge", BundleStatus.MAPPED, quarantined=442)
        _apply_row(b, HeavyWorkOutbox.Status.PENDING, age_seconds=6 * 3600)

        calls: list[dict] = []
        with mock.patch(
            "apps.platform_runtime.heavy_work_outbox.kick_heavy_work_drain",
            side_effect=lambda **kw: calls.append(kw),
        ):
            fired = nudge_stuck_apply(b)

        self.assertTrue(fired)
        self.assertEqual(calls, [{"force_local": True}])

    def test_a_freshly_queued_apply_is_left_alone(self):
        from apps.migration_cloud.repair import nudge_stuck_apply

        b = _bundle("nudge-fresh", BundleStatus.MAPPED, quarantined=442)
        _apply_row(b, HeavyWorkOutbox.Status.PENDING)  # queued a moment ago

        with mock.patch(
            "apps.platform_runtime.heavy_work_outbox.kick_heavy_work_drain"
        ) as kick:
            self.assertFalse(nudge_stuck_apply(b))
        kick.assert_not_called()

    def test_nudge_is_rate_limited_per_bundle(self):
        """Every open tab polls; without a cooldown each poll would spawn a drain."""
        from apps.migration_cloud.repair import nudge_stuck_apply

        b = _bundle("nudge-rate", BundleStatus.MAPPED, quarantined=442)
        _apply_row(b, HeavyWorkOutbox.Status.PENDING, age_seconds=6 * 3600)

        with mock.patch(
            "apps.platform_runtime.heavy_work_outbox.kick_heavy_work_drain"
        ) as kick:
            self.assertTrue(nudge_stuck_apply(b))
            self.assertFalse(nudge_stuck_apply(b))
            self.assertFalse(nudge_stuck_apply(b))
        self.assertEqual(kick.call_count, 1)


class ExpectedRowTotalTests(TestCase):
    """"Expected" read a key nothing ever wrote, so it was always 0."""

    def test_expected_counts_the_uploads_real_rows(self):
        from apps.migration_cloud.models import MigrationArtifact
        from apps.migration_cloud.views_tenant_upload import _expected_row_total

        b = _bundle("expected", BundleStatus.APPLIED, quarantined=442)
        MigrationArtifact.objects.create(
            bundle=b, filename="students.csv", sha256="a" * 64, row_count=400
        )
        MigrationArtifact.objects.create(
            bundle=b, filename="staff.csv", sha256="b" * 64, row_count=147
        )
        # An archive carries no row_count and must not be counted or crash the sum.
        MigrationArtifact.objects.create(
            bundle=b, filename="drop.zip", sha256="c" * 64, row_count=None
        )

        self.assertEqual(_expected_row_total(b), 547)

    def test_expected_is_zero_before_profiling(self):
        from apps.migration_cloud.views_tenant_upload import _expected_row_total

        b = _bundle("expected-empty", BundleStatus.MAPPED)
        self.assertEqual(_expected_row_total(b), 0)
