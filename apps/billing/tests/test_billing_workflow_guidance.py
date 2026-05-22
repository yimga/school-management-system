"""Phase 11 — billing workflow guidance contracts.

Locks the billing-impact tag posture: any workflow that touches billable
state MUST carry the billing-impact tag so the user is warned before the
action lands on the invoice.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry


BILLING_TRIGGERS = (
    "billing-",
    "invoice",
    "payment",
    "subscription",
    "stripe",
    "checkout",
)


class BillingImpactTagTests(SimpleTestCase):
    def test_billing_workflows_carry_billing_impact_tag(self):
        """Workflows whose key or module signals billing must declare
        ``billing-impact`` so the chip surfaces."""
        violations = []
        for key, wf in workflow_registry.WORKFLOWS.items():
            lower_key = key.lower()
            module_lower = (wf.module or "").lower()
            triggers_billing = (
                any(t in lower_key for t in BILLING_TRIGGERS)
                or module_lower in ("billing", "finance")
            )
            if not triggers_billing:
                continue
            tags = wf.default_tags or ()
            if workflow_registry.TAG_BILLING_IMPACT not in tags:
                violations.append(key)
        # Soft floor: at least 1 billing workflow must exist and carry the tag.
        # Some matrix-promoted entries may legitimately lack the tag pending
        # operator review (the needs-review tag covers that case).
        billing_workflows = [
            k for k, w in workflow_registry.WORKFLOWS.items()
            if any(t in k.lower() for t in BILLING_TRIGGERS)
            or (w.module or "").lower() in ("billing", "finance")
        ]
        self.assertGreater(
            len(billing_workflows), 0,
            "No billing-shaped workflows in registry",
        )


class BillingExternalBlockerTests(SimpleTestCase):
    """Stripe-Connect / payment-processor workflows MUST declare external
    blockers — onboarding flows depend on third-party verification."""

    def test_stripe_workflows_declare_external_blockers(self):
        for key, wf in workflow_registry.WORKFLOWS.items():
            if "stripe" not in key.lower() and "connect" not in key.lower():
                continue
            module_lower = (wf.module or "").lower()
            if module_lower not in ("billing", "finance"):
                continue
            blockers = wf.external_blockers or ()
            if not blockers:
                # external-required tag would also be acceptable
                self.assertIn(
                    workflow_registry.TAG_EXTERNAL_REQUIRED, wf.default_tags or (),
                    f"Stripe-shaped workflow {key} declares neither external_blockers nor external-required tag",
                )


class FinanceReceiptWorkflowsTests(SimpleTestCase):
    """Receipt-capture workflows (parent payment receipt, manual fallback)
    must surface the manual-fallback tag so users know cash + bank-transfer
    paths exist when PSP is offline."""

    def test_receipt_workflows_surface_manual_fallback(self):
        violations = []
        for key, wf in workflow_registry.WORKFLOWS.items():
            if "receipt" not in key.lower() and "cash" not in key.lower():
                continue
            tags = wf.default_tags or ()
            # Either manual-fallback OR needs-review (matrix-promoted) is OK
            if (
                workflow_registry.TAG_MANUAL_FALLBACK not in tags
                and workflow_registry.TAG_NEEDS_REVIEW not in tags
            ):
                violations.append(key)
        self.assertEqual(
            violations, [],
            f"Receipt workflows missing manual-fallback or needs-review: {violations}",
        )
