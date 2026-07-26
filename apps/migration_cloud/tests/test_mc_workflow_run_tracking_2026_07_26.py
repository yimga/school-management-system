"""Migration Cloud apply/advance must be VISIBLE to the stall watchdogs.

MC work reaches its service function via the durable HeavyWorkOutbox drain (and
repair), which calls ``apply_bundle`` / ``advance_bundle`` directly — bypassing the
``@track_workflow``-decorated Celery task. So NO WorkflowRun existed for the work,
and every stuck / abandoned watchdog (which all key on a WorkflowRun) was blind to
a wedged import. ``ensure_workflow_run`` now guarantees a run at the service layer
for all callers, without double-tracking the decorated-task path.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.migration_cloud import orchestrator
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_tracker import (
    active_workflow_run,
    begin_run,
    clear_workflow_run_stack_for_tests,
    ensure_workflow_run,
    pop_workflow_run,
    push_workflow_run,
)


class _Bundle(TestCase):
    def tearDown(self):
        clear_workflow_run_stack_for_tests()
        super().tearDown()

    def _bundle(self, key, status):
        return MigrationBundle.objects.create(
            label="wf",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=key,
            status=status,
            school=None,
        )


class ApplyCreatesWorkflowRunTests(_Bundle):
    def test_apply_creates_a_workflow_run(self):
        b = self._bundle("wfapply", BundleStatus.MAPPED)
        self.assertFalse(
            WorkflowRun.objects.filter(workflow_key="migration_bundle_apply").exists()
        )
        orchestrator.apply_bundle(bundle_id=b.pk, dry_run=True)
        run = (
            WorkflowRun.objects.filter(workflow_key="migration_bundle_apply")
            .order_by("-pk")
            .first()
        )
        self.assertIsNotNone(run)  # was ZERO before the fix -> watchdogs blind
        self.assertEqual(run.status, "succeeded")

    def test_apply_failure_finalizes_run_failed(self):
        # A wedged/failed apply now surfaces as a FAILED WorkflowRun the operator
        # + watchdogs can see, instead of silently no run at all.
        b = self._bundle("wffail", BundleStatus.MAPPED)
        with mock.patch.object(
            orchestrator, "_maybe_check_financial_guardrail", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                orchestrator.apply_bundle(bundle_id=b.pk, dry_run=False)
        run = (
            WorkflowRun.objects.filter(workflow_key="migration_bundle_apply")
            .order_by("-pk")
            .first()
        )
        self.assertIsNotNone(run)
        self.assertEqual(run.status, "failed")


class EnsureWorkflowRunTests(_Bundle):
    def test_creates_and_finalizes_when_no_active_run(self):
        with ensure_workflow_run("migration_bundle_apply", steps=("prepare",)) as run:
            self.assertIsNotNone(run)
            self.assertEqual(active_workflow_run(), run)
        run.refresh_from_db()
        self.assertEqual(run.status, "succeeded")

    def test_no_double_track_when_same_key_already_active(self):
        outer = begin_run(workflow_key="migration_bundle_apply", steps=("prepare",))
        push_workflow_run(outer)
        try:
            before = WorkflowRun.objects.count()
            with ensure_workflow_run("migration_bundle_apply") as run:
                self.assertEqual(run.pk, outer.pk)  # reused, not a second run
            self.assertEqual(WorkflowRun.objects.count(), before)  # no new row
        finally:
            pop_workflow_run(outer)

    def test_nested_distinct_key_creates_a_nested_run(self):
        outer = begin_run(workflow_key="tenant_school_provision", steps=())
        push_workflow_run(outer)
        try:
            with ensure_workflow_run("migration_bundle_advance") as run:
                self.assertIsNotNone(run)
                self.assertNotEqual(run.pk, outer.pk)  # nested distinct workflow
        finally:
            pop_workflow_run(outer)
