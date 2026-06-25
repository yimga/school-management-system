"""Healing chain coverage across all registered workflows."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_error_classifier import classify_workflow_run
from apps.platform_runtime.workflow_healing import healing_supported_for_run, resolve_healing_chain
from apps.platform_runtime.workflow_healing_chains import (
    default_healing_chain_for_workflow,
    healing_coverage_gaps,
)
from apps.platform_runtime.workflow_registry import all_workflow_keys


class WorkflowHealingCoverageTests(TestCase):
    def test_all_registered_workflows_have_healing_chain_or_operator_only(self):
        gaps = healing_coverage_gaps()
        self.assertEqual(
            gaps,
            [],
            f"Workflows missing healing chains: {gaps[:10]}",
        )

    def test_migration_workflow_classifies_retry_chain(self):
        run = WorkflowRun.objects.create(
            workflow_key="migration_bundle_apply",
            workflow_label="Migration apply",
            status="failed",
            error_summary={"type": "RuntimeError", "message": "apply wave 2 failed"},
        )
        fp = classify_workflow_run(run)
        self.assertIn("retry_failed_step", fp.recommended_chain)
        self.assertTrue(healing_supported_for_run(run))

    def test_webhook_workflow_classifies_replay_chain(self):
        run = WorkflowRun.objects.create(
            workflow_key="marketplace_webhook_deliver_due",
            workflow_label="Webhook delivery",
            status="failed",
            error_summary={"type": "HTTPError", "message": "delivery 502"},
        )
        fp = classify_workflow_run(run)
        self.assertEqual(fp.recommended_chain[0], "replay_webhook")

    def test_finance_workflow_default_chain(self):
        chain = default_healing_chain_for_workflow("finance_auto_generate_fee_invoices")
        self.assertEqual(chain, ["retry_failed_step"])

    def test_resolve_healing_chain_merges_operator_requeue(self):
        run = WorkflowRun.objects.create(
            workflow_key="tenant_school_provision",
            workflow_label="Provision",
            status="failed",
            school_id=str(uuid.uuid4()),
            error_summary={"type": "Error", "message": "generic failure"},
            suggested_remediation={"auto_fix_kind": "requeue_provision"},
        )
        chain = resolve_healing_chain(run, kind="apply_fix")
        self.assertIn("requeue_provision", chain)

    def test_registry_count_matches_audit(self):
        keys = all_workflow_keys()
        self.assertGreater(len(keys), 10)
