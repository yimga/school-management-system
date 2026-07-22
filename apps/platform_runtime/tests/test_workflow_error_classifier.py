"""Error fingerprinting for Workflow Flight Deck self-healing."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_error_classifier import classify_workflow_run
from apps.schools.models import School


class WorkflowErrorClassifierTests(TestCase):
    def _provision_run(self, *, message: str) -> WorkflowRun:
        school = School.objects.create(
            name="Classifier School",
            slug=f"cls-{uuid.uuid4().hex[:8]}",
            subdomain=f"cls{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        return WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision school",
            status="failed",
            school_id=str(school.pk),
            tenant_schema=school.subdomain,
            error_summary={"type": "OperationalError", "message": message},
        )

    def test_duplicate_relation_chain(self):
        run = self._provision_run(
            message='relation "tenant_foo" already exists during migrate',
        )
        fp = classify_workflow_run(run)
        self.assertEqual(fp.class_key, "duplicate_relation")
        self.assertIn("repair_tenant_schema_drift", fp.recommended_chain)
        self.assertIn("requeue_provision", fp.recommended_chain)

    def test_worker_timeout_chain(self):
        run = self._provision_run(message="upstream worker did not respond; no heartbeat")
        fp = classify_workflow_run(run)
        self.assertEqual(fp.class_key, "worker_timeout")
        self.assertIn("clear_stale_lock", fp.recommended_chain)
        self.assertIn("requeue_provision", fp.recommended_chain)

    def test_migration_bundle_retry_chain(self):
        run = WorkflowRun.objects.create(
            workflow_key="migration_bundle_advance",
            workflow_label="Migration advance",
            status="failed",
            error_summary={"type": "Error", "message": "mapping failed"},
        )
        fp = classify_workflow_run(run)
        self.assertIn("retry_failed_step", fp.recommended_chain)

    def test_default_requeue_for_generic_failure(self):
        run = self._provision_run(message="something unexpected blew up")
        fp = classify_workflow_run(run)
        self.assertEqual(fp.recommended_chain, ["requeue_provision"])

    def test_tenant_schema_step_gets_repair_then_requeue(self):
        run = self._provision_run(message="killed by gunicorn timeout")
        run.current_step_name = "tenant_schema"
        run.save(update_fields=["current_step_name"])
        fp = classify_workflow_run(run)
        self.assertEqual(fp.class_key, "tenant_schema_stalled")
        self.assertEqual(
            fp.recommended_chain,
            [
                "cancel_duplicate_run",
                "repair_tenant_schema_drift",
                "requeue_provision",
            ],
        )
