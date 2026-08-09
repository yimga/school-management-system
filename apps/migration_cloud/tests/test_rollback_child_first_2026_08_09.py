"""Seal: a failed-apply rollback must run CHILD-FIRST (2026-08-09 re-audit).

``orchestrator._rollback_all_runs`` iterated the apply outcomes in append (=
dependency-wave) order, so a wave-1 ``students`` run rolled back BEFORE its
wave-3 ``grades`` run. ``Evaluation.student`` / ``Evaluation.teacher`` are
``on_delete=PROTECT``, so deleting the student first raised ``IntegrityError``
(swallowed at debug), the grades rolled back afterwards, and the student /
teacher were left ORPHANED and live though the bundle read FAILED.

The fix rolls runs back most-recent-first (``order_by("-started_at")``), i.e. the
reverse of the wave order — grades before students. This test FAILS against the
append-order code and PASSES against the fix.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.automation.models import MigrationRun
from apps.migration_cloud.orchestrator import ArtifactApplyOutcome, _rollback_all_runs


class RollbackChildFirstTests(TestCase):
    def test_rollback_runs_child_first_by_started_at(self):
        early = MigrationRun.objects.create(migration_type="students")
        late = MigrationRun.objects.create(migration_type="grades")
        # Pin started_at deterministically: students (wave 1) started BEFORE
        # grades (wave 3), mirroring the real serial-wave apply order.
        now = timezone.now()
        MigrationRun.objects.filter(pk=early.pk).update(
            started_at=now - timedelta(minutes=5),
        )
        MigrationRun.objects.filter(pk=late.pk).update(started_at=now)

        # Outcomes in APPEND (wave) order: students first, grades last.
        outcomes = [
            ArtifactApplyOutcome(
                artifact_id=1, path_within_bundle="students.csv",
                domain="students", migration_run_id=early.pk,
            ),
            ArtifactApplyOutcome(
                artifact_id=2, path_within_bundle="grades.csv",
                domain="grades", migration_run_id=late.pk,
            ),
        ]

        order: list = []

        def _record(self, user=None):
            order.append(self.pk)
            return {"success": True, "reverted_count": 0}

        with mock.patch.object(MigrationRun, "trigger_rollback", _record):
            _rollback_all_runs(outcomes)

        # Child-first == most-recent-first: grades (late) roll back BEFORE
        # students (early). Append order would give [early, late].
        self.assertEqual(order, [late.pk, early.pk])

    def test_no_runs_is_a_safe_noop(self):
        outcomes = [
            ArtifactApplyOutcome(
                artifact_id=1, path_within_bundle="x.csv",
                domain="students", migration_run_id=None,
            ),
        ]
        # Must not raise even when no run ids are present.
        _rollback_all_runs(outcomes)
