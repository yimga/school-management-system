"""Migration 0086 enables platform-wide self-healing for provisioning.

The stuck-workflow sweep only auto-applies a fix when a WorkflowAutopilotPolicy
allows it. Migration 0086 ships the platform-wide row that lets
``tenant_school_provision`` auto-requeue (which now resumes Phase B). These tests
lock that the row exists and that the policy resolver honours it.
"""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.models import WorkflowAutopilotPolicy
from apps.platform_runtime.workflow_autopilot import policy_allows_auto_fix


class ProvisioningAutopilotPolicyTests(TestCase):
    def test_platform_wide_policy_row_shipped_by_migration(self):
        pol = WorkflowAutopilotPolicy.objects.filter(
            workflow_key="tenant_school_provision", tenant_schema=""
        ).first()
        self.assertIsNotNone(pol, "migration 0086 must ship the platform-wide policy")
        self.assertTrue(pol.enabled)
        self.assertIn("requeue_provision", pol.allowed_auto_fix_kinds or [])

    def test_policy_allows_requeue_provision_platform_wide(self):
        # No per-tenant row → the platform-wide ("") row must still grant it.
        self.assertTrue(
            policy_allows_auto_fix(
                workflow_key="tenant_school_provision",
                auto_fix_kind="requeue_provision",
                tenant_schema="some_new_tenant",
            )
        )

    def test_policy_does_not_grant_unrelated_kinds(self):
        self.assertFalse(
            policy_allows_auto_fix(
                workflow_key="tenant_school_provision",
                auto_fix_kind="some_other_fix",
            )
        )
