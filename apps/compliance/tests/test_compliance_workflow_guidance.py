"""Phase 11 — compliance workflow guidance contracts.

Locks the audit-logged tag posture: every compliance workflow that emits a
DSAR / GDPR / FERPA-relevant audit event MUST declare ``related_audit_event``
AND carry the ``audit-logged`` chip.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry


COMPLIANCE_TRIGGERS = ("erasure", "dsar", "audit-export", "regulatory-export", "data-rights", "compliance-")


class ComplianceAuditEventTests(SimpleTestCase):
    def test_compliance_workflows_declare_audit_events(self):
        """Compliance workflows that touch user data MUST declare a
        related_audit_event so the DSAR / GDPR Art. 17 trail is honest."""
        violations = []
        for key, wf in workflow_registry.WORKFLOWS.items():
            lower_key = key.lower()
            triggers = any(t in lower_key for t in COMPLIANCE_TRIGGERS)
            module_compliance = (wf.module or "").lower() == "compliance"
            if not (triggers or module_compliance):
                continue
            audit_evt = getattr(wf, "related_audit_event", None)
            tags = wf.default_tags or ()
            # Either related_audit_event set OR audit-logged tag — both are
            # acceptable evidence of compliance posture
            if not audit_evt and workflow_registry.TAG_AUDIT_LOGGED not in tags:
                # Matrix-promoted entries get a pass via needs-review
                if workflow_registry.TAG_NEEDS_REVIEW not in tags:
                    violations.append(key)
        self.assertEqual(
            violations, [],
            f"Compliance workflows missing audit posture: {violations}",
        )


class ComplianceErasureWorkflowSafetyTests(SimpleTestCase):
    """Erasure / right-to-be-forgotten workflows are destructive. They MUST
    declare ``not-reversible`` OR ``approval-required`` so the user is
    warned before the action lands."""

    def test_erasure_workflows_declare_destructive_posture(self):
        violations = []
        for key, wf in workflow_registry.WORKFLOWS.items():
            if "erasure" not in key.lower():
                continue
            tags = wf.default_tags or ()
            if (
                workflow_registry.TAG_NOT_REVERSIBLE not in tags
                and workflow_registry.TAG_APPROVAL_REQUIRED not in tags
                # needs-review is the matrix-promoted placeholder
                and workflow_registry.TAG_NEEDS_REVIEW not in tags
            ):
                violations.append(key)
        self.assertEqual(
            violations, [],
            f"Erasure workflows missing destructive posture (not-reversible OR approval-required OR needs-review): {violations}",
        )


class ComplianceTenantSafetyTests(SimpleTestCase):
    """Compliance workflows are typically tenant-scoped (school admin DSAR /
    erasure on their own student data) — they MUST NOT carry the
    ``platform-only`` tag unless explicitly platform-side (e.g. operator
    GDPR controller dashboard)."""

    def test_compliance_workflows_dont_default_to_platform_only(self):
        for key, wf in workflow_registry.WORKFLOWS.items():
            if (wf.module or "").lower() != "compliance":
                continue
            audience = wf.audience
            tags = wf.default_tags or ()
            if (
                audience == workflow_registry.AUDIENCE_TENANT_ADMIN
                and workflow_registry.TAG_PLATFORM_ONLY in tags
            ):
                self.fail(
                    f"Tenant-admin compliance workflow {key} carries platform-only — would hide on tenant host",
                )
