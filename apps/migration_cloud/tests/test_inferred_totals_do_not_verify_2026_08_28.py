"""An inferred control total is not a verified one (2026-08-28).

``auto_infer_expected_totals`` writes ``expected_totals = observed``, so the
guardrail that follows compares a number to itself and can only ever agree. That
is fine as a convenience -- it stops cutover blocking because nobody typed
control totals upfront -- but it ran BEFORE the unverified-finance decision, and
that decision is the one with teeth:

  * ``RMC_MIGRATION_REQUIRE_FINANCE_TOTALS`` exists so a sensitive tenant can
    REFUSE a finance import nobody verified (FAILED + rolled back). Once
    inference has populated ``expected_totals``, the branch that raises is never
    reached, so the switch silently stops switching.
  * ``finance_landed_unverified`` -- the durable record that money landed
    unchecked -- was actively popped by the inference step.

The existing coverage in ``test_finance_guardrail_scope_2026_08_16`` stayed
green throughout, because its bundles have no landed rows: observed totals are
all "0", inference skips zeros, and the old path still runs. The regression only
appears once finance ACTUALLY lands something -- which is every real import.

Order matters, and that is all these tests pin: answer "was this verified?"
while ``expected_totals`` is still genuinely empty, then infer.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings

from apps.migration_cloud import orchestrator
from apps.migration_cloud.guardrails import FinancialMismatchError
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.orchestrator import ArtifactApplyOutcome
from apps.schools.models import School

# What a real finance import looks like to the guardrail: non-zero, so inference
# actually fires. The committed tests use an empty bundle, where it does not.
LANDED_TOTALS = {
    "finance.invoice_total_amount": "450000",
    "finance.invoice_count": "12",
}


class InferredTotalsAreNotVerificationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Inferred Totals School",
            slug="inferred-totals-school",
            subdomain="inferred-totals-school",
            is_active=True,
            is_approved=True,
        )
        self.bundle = MigrationBundle.objects.create(
            label="inferred-totals",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="inferred-totals-b1",
            status=BundleStatus.APPLIED,
            school=self.school,
            expected_totals={},
        )

    def _finance_outcome(self):
        return ArtifactApplyOutcome(
            artifact_id=1,
            path_within_bundle="fees.csv",
            domain="finance",
            migration_run_id=None,
            status="SUCCESS",
        )

    def _observed(self, totals):
        # Patched in the guardrails module so BOTH the inference step and the
        # enforcement step below see the same numbers.
        return mock.patch(
            "apps.migration_cloud.guardrails.compute_observed_totals",
            return_value=dict(totals),
        )

    @override_settings(RMC_MIGRATION_REQUIRE_FINANCE_TOTALS=True)
    def test_the_hard_refuse_switch_still_refuses_when_finance_landed(self):
        with self._observed(LANDED_TOTALS):
            with self.assertRaises(
                FinancialMismatchError,
                msg="a tenant that opted into refusing unverified money got it applied",
            ):
                orchestrator._maybe_check_financial_guardrail(
                    self.bundle, [self._finance_outcome()]
                )

    def test_the_unverified_marker_survives_inference(self):
        with self._observed(LANDED_TOTALS):
            orchestrator._maybe_check_financial_guardrail(
                self.bundle, [self._finance_outcome()]
            )
        self.bundle.refresh_from_db()
        summary = self.bundle.mapping_summary or {}
        self.assertTrue(
            summary.get("finance_landed_unverified"),
            "inferring a total from the import does not verify the import",
        )
        self.assertTrue(
            summary.get("expected_totals_requires_confirmation"),
            "the operator still has to confirm the inferred figures",
        )

    def test_inference_still_populates_the_totals(self):
        """The convenience the inference was added for must keep working."""
        with self._observed(LANDED_TOTALS):
            orchestrator._maybe_check_financial_guardrail(
                self.bundle, [self._finance_outcome()]
            )
        self.bundle.refresh_from_db()
        self.assertEqual(
            self.bundle.expected_totals.get("finance.invoice_count"), "12"
        )

    def test_operator_supplied_totals_are_never_overwritten_or_re_flagged(self):
        self.bundle.expected_totals = {"finance.invoice_count": "12"}
        self.bundle.save(update_fields=["expected_totals"])
        with self._observed(LANDED_TOTALS):
            orchestrator._maybe_check_financial_guardrail(
                self.bundle, [self._finance_outcome()]
            )
        self.bundle.refresh_from_db()
        summary = self.bundle.mapping_summary or {}
        self.assertEqual(self.bundle.expected_totals.get("finance.invoice_count"), "12")
        self.assertNotIn(
            "finance_landed_unverified",
            summary,
            "this import WAS verified against an operator total",
        )
