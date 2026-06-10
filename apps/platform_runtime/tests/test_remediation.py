"""Tenant remediation payload tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.remediation import (
    from_workflow_run,
    normalize_remediation,
    provisioning_failed_remediation,
    signup_slug_taken_remediation,
)


class RemediationPayloadTests(SimpleTestCase):
    def test_signup_slug_taken_includes_alternatives(self):
        payload = signup_slug_taken_remediation("demo-school")
        data = payload.to_dict()
        self.assertEqual(data["code"], "signup.slug_taken")
        self.assertIn("alternatives", data["suggested_values"])
        self.assertTrue(len(data["suggested_values"]["alternatives"]) >= 1)

    def test_provisioning_failed_owner_may_apply_requeue(self):
        payload = provisioning_failed_remediation(error="DNS timeout")
        data = payload.to_tenant_api_dict(operator_debug_reference="wf-run-abc")
        self.assertEqual(data["error_type"], "tenant.provisioning_failed")
        self.assertEqual(data["auto_fix_kind"], "requeue_provision")
        self.assertTrue(data["owner_may_apply"])
        self.assertTrue(data["remediation_available"])
        self.assertEqual(data["remediation_action_token"], "requeue_provision")

    def test_normalize_legacy_blob(self):
        raw = {
            "human_action": "Retry from dashboard.",
            "auto_fix_available": True,
            "auto_fix_kind": "resend_welcome",
        }
        data = normalize_remediation(raw)
        self.assertTrue(data["owner_may_apply"])
        self.assertEqual(data["auto_fix_kind"], "resend_welcome")

    def test_from_workflow_run_empty_when_none(self):
        data = from_workflow_run(None)
        self.assertEqual(data["code"], "")
        self.assertFalse(data["auto_fix_available"])
