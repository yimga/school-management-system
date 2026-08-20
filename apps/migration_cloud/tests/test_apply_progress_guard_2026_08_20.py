"""An apply that changes nothing must not be allowed to re-queue itself forever.

Observed live on 2026-08-20, gilead-tech bundle 84: eighty-five ``mc_apply_bundle``
outbox rows, eighty-four ``succeeded``, every one reporting exactly
``0 created, 105 updated, 442 quarantined``, a fresh row minted one to two seconds
after each finished, running continuously since 2026-08-16.

The two properties that made it unbounded, and which these tests pin:

1. ``enqueue_heavy_work`` dedupes an idempotency key only against ``pending`` /
   ``processing`` rows, so the key frees the instant a row succeeds and the next
   caller mints another. That behaviour is deliberate for provisioning and is NOT
   changed here — the guard sits above it.
2. Nothing asked whether the previous apply had accomplished anything.

The tests use pure model objects and a fake bundle rather than driving a real
apply, because the property under test is arithmetic on recorded outcomes, not the
apply itself; a test that needed a real 90-second apply to run would not be run.
"""
from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.migration_cloud.apply_progress_guard import (
    apply_is_livelocked,
    livelock_reason,
    no_progress_limit,
    no_progress_streak,
    outcome_fingerprint,
    record_apply_outcome,
    reset_apply_progress,
)


class FakeBundle:
    """Stands in for a MigrationBundle without needing the database.

    ``save`` is a no-op and ``pk`` is None, so ``_db_summary``'s lookup misses and
    it falls back to the in-memory ``size_summary`` — exactly the documented
    fallback path, exercised here rather than assumed.
    """

    def __init__(self, size_summary=None):
        self.pk = None
        self.size_summary = dict(size_summary or {})
        self.save_calls = 0

    def save(self, update_fields=None):
        self.save_calls += 1


class OutcomeFingerprintTests(SimpleTestCase):
    def test_identical_totals_produce_identical_fingerprints(self):
        a = outcome_fingerprint(created=0, updated=105, quarantined=442, status="APPLIED")
        b = outcome_fingerprint(created=0, updated=105, quarantined=442, status="APPLIED")
        self.assertEqual(a, b)

    def test_any_differing_total_changes_the_fingerprint(self):
        base = outcome_fingerprint(created=0, updated=105, quarantined=442, status="APPLIED")
        for kwargs in (
            {"created": 1, "updated": 105, "quarantined": 442, "status": "APPLIED"},
            {"created": 0, "updated": 106, "quarantined": 442, "status": "APPLIED"},
            {"created": 0, "updated": 105, "quarantined": 441, "status": "APPLIED"},
            {"created": 0, "updated": 105, "quarantined": 442, "status": "FAILED"},
        ):
            with self.subTest(**kwargs):
                self.assertNotEqual(base, outcome_fingerprint(**kwargs))


class NoProgressStreakTests(SimpleTestCase):
    """The bundle-84 signature: same numbers, nothing created, over and over."""

    BUNDLE_84 = {"created": 0, "updated": 105, "quarantined": 442, "status": "APPLIED"}

    def test_first_apply_is_never_a_no_progress_apply(self):
        bundle = FakeBundle()
        record_apply_outcome(bundle, **self.BUNDLE_84)
        self.assertEqual(no_progress_streak(bundle), 0)
        self.assertFalse(apply_is_livelocked(bundle))

    def test_repeating_the_identical_result_accumulates_a_streak(self):
        bundle = FakeBundle()
        record_apply_outcome(bundle, **self.BUNDLE_84)
        for expected in (1, 2, 3):
            record_apply_outcome(bundle, **self.BUNDLE_84)
            self.assertEqual(no_progress_streak(bundle), expected)

    @override_settings(RMC_MC_APPLY_NO_PROGRESS_LIMIT=3)
    def test_the_breaker_trips_at_the_configured_limit(self):
        bundle = FakeBundle()
        record_apply_outcome(bundle, **self.BUNDLE_84)
        record_apply_outcome(bundle, **self.BUNDLE_84)  # streak 1
        record_apply_outcome(bundle, **self.BUNDLE_84)  # streak 2
        self.assertFalse(apply_is_livelocked(bundle))
        record_apply_outcome(bundle, **self.BUNDLE_84)  # streak 3
        self.assertTrue(apply_is_livelocked(bundle))

    def test_creating_rows_resets_the_streak_even_when_totals_repeat(self):
        """Conservatism check: a bundle actually inserting rows is never blocked."""
        bundle = FakeBundle()
        making_rows = {"created": 7, "updated": 105, "quarantined": 442, "status": "APPLIED"}
        for _ in range(10):
            record_apply_outcome(bundle, **making_rows)
        self.assertEqual(no_progress_streak(bundle), 0)
        self.assertFalse(apply_is_livelocked(bundle))

    def test_a_changed_result_resets_the_streak(self):
        bundle = FakeBundle()
        for _ in range(5):
            record_apply_outcome(bundle, **self.BUNDLE_84)
        self.assertGreater(no_progress_streak(bundle), 0)
        record_apply_outcome(
            bundle, created=0, updated=105, quarantined=400, status="APPLIED"
        )
        self.assertEqual(no_progress_streak(bundle), 0)

    def test_repair_re_arms_the_breaker(self):
        bundle = FakeBundle()
        for _ in range(6):
            record_apply_outcome(bundle, **self.BUNDLE_84)
        self.assertTrue(apply_is_livelocked(bundle))
        reset_apply_progress(bundle)
        self.assertEqual(no_progress_streak(bundle), 0)
        self.assertFalse(apply_is_livelocked(bundle))

    def test_recording_preserves_sibling_summary_keys(self):
        """The progress block must not clobber apply_run_started_at."""
        bundle = FakeBundle({"apply_run_started_at": "2026-08-20T10:00:00Z"})
        record_apply_outcome(bundle, **self.BUNDLE_84)
        self.assertEqual(
            bundle.size_summary.get("apply_run_started_at"), "2026-08-20T10:00:00Z"
        )


class LivelockReasonTests(SimpleTestCase):
    """A refusal the operator cannot read is a silent failure."""

    def test_reason_is_empty_when_not_livelocked(self):
        self.assertEqual(livelock_reason(FakeBundle()), "")

    def test_reason_names_the_counts_that_stopped_moving(self):
        bundle = FakeBundle()
        for _ in range(6):
            record_apply_outcome(
                bundle, created=0, updated=105, quarantined=442, status="APPLIED"
            )
        reason = livelock_reason(bundle)
        self.assertIn("442", reason)
        self.assertIn("105", reason)
        self.assertTrue(reason.strip())


class NoProgressLimitSettingTests(SimpleTestCase):
    @override_settings(RMC_MC_APPLY_NO_PROGRESS_LIMIT=7)
    def test_reads_the_configured_value(self):
        self.assertEqual(no_progress_limit(), 7)

    @override_settings(RMC_MC_APPLY_NO_PROGRESS_LIMIT=0)
    def test_floors_at_one_so_the_breaker_can_never_be_disabled(self):
        self.assertEqual(no_progress_limit(), 1)

    @override_settings(RMC_MC_APPLY_NO_PROGRESS_LIMIT="not-a-number")
    def test_a_junk_value_falls_back_to_the_default(self):
        self.assertEqual(no_progress_limit(), 3)


class GuardIsNeverFatalTests(SimpleTestCase):
    """A guard that raises would take out the apply path it protects."""

    def test_livelock_check_on_a_junk_object_is_false_not_an_exception(self):
        class Junk:
            size_summary = "not-a-dict"

        self.assertFalse(apply_is_livelocked(Junk()))

    def test_recording_against_a_junk_object_does_not_raise(self):
        class Junk:
            pk = None
            size_summary = None

            def save(self, update_fields=None):
                raise RuntimeError("db is down")

        self.assertEqual(
            record_apply_outcome(
                Junk(), created=0, updated=1, quarantined=0, status="APPLIED"
            ),
            {},
        )


class EnqueueRefusesALivelockedApplyTests(SimpleTestCase):
    """The breaker has to sit on the ENQUEUE path, not just record history.

    Mocked rather than DB-backed on purpose: the contract under test is "a
    livelocked bundle yields a refusal instead of a new outbox row", which is
    decided entirely by ``apply_is_livelocked``. Building a real MigrationBundle
    would test the ORM, not the breaker.
    """

    def _fake_bundle(self, *, livelocked):
        bundle = FakeBundle()
        if livelocked:
            for _ in range(no_progress_limit() + 2):
                record_apply_outcome(
                    bundle, created=0, updated=105, quarantined=442, status="APPLIED"
                )
        return bundle

    def _patch_lookup(self, bundle):
        from unittest import mock

        return mock.patch(
            "apps.migration_cloud.models.MigrationBundle.objects.filter",
            return_value=mock.Mock(first=mock.Mock(return_value=bundle)),
        )

    def test_a_livelocked_bundle_is_refused(self):
        from apps.migration_cloud.celery_tasks import _refuse_livelocked_apply

        with self._patch_lookup(self._fake_bundle(livelocked=True)):
            refusal = _refuse_livelocked_apply(84)
        self.assertIsNotNone(refusal)
        self.assertFalse(refusal.queued)
        self.assertTrue(refusal.refused)
        self.assertIn("442", refusal.reason)

    def test_a_healthy_bundle_is_not_refused(self):
        from apps.migration_cloud.celery_tasks import _refuse_livelocked_apply

        with self._patch_lookup(self._fake_bundle(livelocked=False)):
            self.assertIsNone(_refuse_livelocked_apply(84))

    def test_a_missing_bundle_is_not_refused(self):
        from apps.migration_cloud.celery_tasks import _refuse_livelocked_apply

        with self._patch_lookup(None):
            self.assertIsNone(_refuse_livelocked_apply(999999))

    def test_a_broken_lookup_never_blocks_a_real_apply(self):
        from unittest import mock

        from apps.migration_cloud.celery_tasks import _refuse_livelocked_apply

        with mock.patch(
            "apps.migration_cloud.models.MigrationBundle.objects.filter",
            side_effect=RuntimeError("db is down"),
        ):
            self.assertIsNone(_refuse_livelocked_apply(84))

    def test_a_dry_run_is_never_refused(self):
        """Dry runs write nothing, so re-running one costs nothing but time."""
        from unittest import mock

        from apps.migration_cloud.celery_tasks import _kick_apply_off_request

        with mock.patch(
            "apps.migration_cloud.celery_tasks._refuse_livelocked_apply"
        ) as refuse, mock.patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_heavy_work"
        ) as enqueue:
            enqueue.return_value = mock.Mock(pk="row-1")
            _kick_apply_off_request(84, dry_run=True)
        refuse.assert_not_called()

    def test_force_bypasses_the_breaker_so_a_human_repair_always_runs(self):
        from unittest import mock

        from apps.migration_cloud.celery_tasks import _kick_apply_off_request

        with mock.patch(
            "apps.migration_cloud.celery_tasks._refuse_livelocked_apply"
        ) as refuse, mock.patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_heavy_work"
        ) as enqueue:
            enqueue.return_value = mock.Mock(pk="row-1")
            _kick_apply_off_request(84, dry_run=False, force=True)
        refuse.assert_not_called()
        enqueue.assert_called_once()

    def test_an_automatic_live_apply_consults_the_breaker(self):
        from unittest import mock

        from apps.migration_cloud.celery_tasks import _kick_apply_off_request

        with mock.patch(
            "apps.migration_cloud.celery_tasks._refuse_livelocked_apply"
        ) as refuse, mock.patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_heavy_work"
        ) as enqueue:
            refuse.return_value = None
            enqueue.return_value = mock.Mock(pk="row-1")
            _kick_apply_off_request(84, dry_run=False)
        refuse.assert_called_once_with(84)

    def test_enqueue_apply_forwards_force(self):
        from unittest import mock

        from apps.migration_cloud import celery_tasks

        with mock.patch.object(celery_tasks, "_kick_apply_off_request") as kick:
            celery_tasks.enqueue_apply(84, dry_run=False, force=True)
        self.assertTrue(kick.call_args.kwargs["force"])


class RepairReArmsTheBreakerTests(SimpleTestCase):
    """Bounding automatic re-entry is the point; bounding people is not."""

    def test_repair_imports_and_calls_the_reset_helper(self):
        import inspect

        from apps.migration_cloud import repair

        source = inspect.getsource(repair)
        self.assertIn("reset_apply_progress(bundle)", source)
        self.assertIn("force=True", source)


class RefusalIsVisibleToTheOperatorTests(SimpleTestCase):
    """A silent refusal is its own bug.

    This subsystem already carries scar tissue for exactly this shape: a caller told
    "queued" while nothing was queued, with the real reason sitting in a log nobody
    reads. That is the reported "Repair does nothing". The breaker must not recreate it.
    """

    def test_the_refusal_handle_carries_a_readable_reason(self):
        from apps.migration_cloud.celery_tasks import RefusedApply

        refusal = RefusedApply("442 records are held for review")
        self.assertTrue(refusal.refused)
        self.assertFalse(refusal.queued)
        self.assertIn("442", refusal.reason)

    def test_the_refusal_handle_is_shaped_like_a_success_handle(self):
        """No caller should crash on attribute access when work is declined."""
        from apps.migration_cloud.celery_tasks import RefusedApply

        refusal = RefusedApply("nope")
        for attr in ("id", "outbox_id", "durable_outbox"):
            self.assertTrue(hasattr(refusal, attr), attr)

    def test_the_tenant_apply_view_reports_the_refusal(self):
        import inspect

        from apps.migration_cloud import views_tenant_upload

        source = inspect.getsource(views_tenant_upload.TenantMigrationApplyView)
        self.assertIn('getattr(result, "refused", False)', source)
        # ...and does NOT fall through to the "queued" message.
        refusal_branch = source.split('getattr(result, "refused", False)', 1)[1][:600]
        self.assertIn("messages.warning", refusal_branch)
        self.assertIn("return redirect", refusal_branch)

    def test_the_operator_apply_view_reports_the_refusal(self):
        import inspect

        from apps.migration_cloud import views

        source = inspect.getsource(views)
        self.assertIn('"refused": True', source)
        self.assertIn("status=409", source)
