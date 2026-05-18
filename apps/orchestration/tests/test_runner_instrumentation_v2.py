"""Move 2 — orchestration runner instrumentation.

Verifies that BaseOrchestrationRunner emits OrchestrationStepEvent rows
around each step and binds runs to a ProcessDefinitionVersion.
"""

from __future__ import annotations

from django.test import TestCase

from apps.orchestration.models import (
    OrchestrationRun,
    OrchestrationStepEvent,
    ProcessDefinition,
)
from apps.orchestration.runners import BaseOrchestrationRunner


class _OkRunner(BaseOrchestrationRunner):
    code = "ok"

    def run_step(self) -> dict:
        return {"step": "ok", "rows": 3}


class _FailRunner(BaseOrchestrationRunner):
    code = "fail"

    def run_step(self) -> dict:
        raise ValueError("boom")


class RunnerInstrumentationTests(TestCase):
    def setUp(self):
        self.defn = ProcessDefinition.objects.create(code="ok", name="ok")
        self.run = OrchestrationRun.objects.create(
            definition=self.defn, status=OrchestrationRun.Status.PENDING
        )

    def test_success_emits_started_and_completed_events(self):
        runner = _OkRunner(self.run)
        runner.execute()
        types = list(
            OrchestrationStepEvent.objects.filter(run=self.run)
            .order_by("sequence_number")
            .values_list("event_type", flat=True)
        )
        # Expect: run_started, step_started, step_succeeded, run_completed
        self.assertIn("run_started", types)
        self.assertIn("step_succeeded", types)
        self.assertIn("run_completed", types)
        # Run is now bound to a version.
        self.run.refresh_from_db()
        self.assertIsNotNone(self.run.definition_version_id)

    def test_failure_emits_step_failed_and_retry_scheduled(self):
        # Force 3-max-retries; first failure schedules a retry.
        runner = _FailRunner(self.run, max_retries=3)
        runner.execute()
        types = list(
            OrchestrationStepEvent.objects.filter(run=self.run)
            .order_by("sequence_number")
            .values_list("event_type", flat=True)
        )
        self.assertIn("step_failed", types)
        self.assertIn("retry_scheduled", types)

    def test_terminal_failure_emits_run_failed(self):
        # Pre-set retry count near limit so next failure terminates.
        defn2 = ProcessDefinition.objects.create(code="boom", name="boom")
        run2 = OrchestrationRun.objects.create(
            definition=defn2, status=OrchestrationRun.Status.PENDING, retry_count=2
        )
        runner = _FailRunner(run2, max_retries=3)
        runner.execute()
        types = list(
            OrchestrationStepEvent.objects.filter(run=run2).values_list("event_type", flat=True)
        )
        self.assertIn("run_failed", types)
