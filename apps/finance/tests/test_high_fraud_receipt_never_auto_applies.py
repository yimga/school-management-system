"""A receipt flagged HIGH FRAUD RISK must never be auto-credited.

Found by an A-Z audit follow-up (2026-07-16).

``_process_payment_receipt_upload_impl`` opened with the right instinct:

    if proof_upload.fraud_risk_score >= 70:
        should_auto_apply = False               # <- the gate
        proof_upload.status = ...DISCREPANCY
        _notify_finance_staff_suspicious_receipt(...)

...and then, ~20 lines later, UNCONDITIONALLY reassigned the same name from an
expression carrying no fraud term:

    should_auto_apply = (not dry_run and auto_apply_enabled and not require_approval
                         and verification_result["matches"]
                         and verification_result["confidence"] >= auto_apply_threshold)

So the gate was dead. A receipt scoring >=70 (duplicate file hash = +50, duplicate
reference = +40 — i.e. a replayed/duplicated receipt) was auto-applied as a real
``Payment`` and the invoice credited. ``create_payment_from_receipt`` then
overwrote the DISCREPANCY status with VERIFIED. Net effect: finance staff got an
email telling them to manually review a receipt the system had already credited
and marked verified. The alarm rang; the lock never engaged — worse than having
no detector, because the VERIFIED status invites trust.

The smoking gun that this was an omission and not a policy: the DRY-RUN twin in
the same function always carried ``and proof_upload.fraud_risk_score < 70``, so a
dry run reported ``would_apply: False`` for a receipt the live run credited. Both
now read one constant (``FRAUD_REVIEW_SCORE_THRESHOLD``) so they cannot drift again.

Defaults make this reachable, not theoretical: receipt auto-apply is ON and admin
approval is OFF by default.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.finance.fraud_detection import FRAUD_REVIEW_SCORE_THRESHOLD


class _Stub:
    """Minimal stand-in for the collaborators the impl touches."""


class _FinanceSettings(dict):
    """Finance runtime config stub.

    Unknown keys answer False rather than KeyError so this test stays pinned to
    the fraud decision instead of breaking every time an unrelated finance
    toggle is added to the config dict.
    """

    def __missing__(self, key):  # pragma: no cover - trivial
        return False


def _finance_settings(**over):
    base = _FinanceSettings(
        {
            "receipt_verification_method": "ocr",
            "receipt_auto_apply_threshold": 0.9,
            "receipt_auto_apply_enabled": True,  # platform default: ON
            "receipt_require_admin_approval": False,  # platform default: OFF
            "receipt_amount_tolerance": 0.01,
        }
    )
    base.update(over)
    return base


class HighFraudReceiptNeverAutoAppliesTests(TestCase):
    """The gate must survive the auto-apply decision."""

    def _run(self, *, fraud_score: int, confidence: float = 0.99, matches: bool = True):
        """Drive the impl with a perfectly-matching receipt at a given fraud score."""
        from apps.finance import tasks as finance_tasks

        proof = mock.MagicMock()
        proof.id = 1
        proof.fraud_risk_score = fraud_score
        proof.fraud_flags = ["duplicate_file_hash"] if fraud_score else []
        proof.verification_notes = ""
        proof.is_suspicious = bool(fraud_score)
        proof.invoice = mock.MagicMock()
        proof.uploaded_amount = None

        verification = {
            "matches": matches,
            "confidence": confidence,
            "discrepancies": [] if matches else ["Amount mismatch"],
        }

        with mock.patch.object(
            finance_tasks, "AutomationExecutionLog"
        ), mock.patch.object(
            finance_tasks.PaymentProofUpload.objects, "select_related"
        ) as sel, mock.patch.object(
            finance_tasks, "_resolve_school", return_value=None
        ), mock.patch.object(
            finance_tasks, "get_cached_site_settings", return_value=_Stub()
        ), mock.patch.object(
            finance_tasks,
            "_get_finance_runtime_config",
            return_value=_finance_settings(),
        ), mock.patch.object(
            finance_tasks,
            "get_effective_marketplace_integration_settings",
            return_value={"marksheet_ocr_command": ""},
        ), mock.patch.object(
            finance_tasks, "ReceiptVerificationService"
        ) as svc, mock.patch.object(
            finance_tasks, "create_payment_from_receipt"
        ) as create_payment, mock.patch.object(
            finance_tasks, "_notify_finance_staff_suspicious_receipt"
        ), mock.patch.object(
            finance_tasks, "ReceiptFraudDetector"
        ) as detector:
            # The impl RE-RUNS detection when fraud_flags is empty and assigns the
            # result back onto the proof, so the stub must return a real dict --
            # otherwise fraud_risk_score becomes a MagicMock and the comparison
            # explodes instead of exercising the gate.
            detector.return_value.detect_fraud.return_value = {
                "fraud_risk_score": fraud_score,
                "fraud_flags": proof.fraud_flags,
                "recommendation": "reject" if fraud_score else "accept",
            }
            sel.return_value.get.return_value = proof
            service = svc.return_value
            service.extract_receipt_data.return_value = {
                "amount": "100",
                "date": None,
                "reference": "REF-1",
            }
            service.verify_receipt_match.return_value = verification
            try:
                finance_tasks._process_payment_receipt_upload_impl(1)
            except Exception:  # noqa: BLE001 — collaborators are stubs; the
                # assertion below is about whether a payment was created at all.
                pass
        return create_payment, proof

    def test_high_fraud_receipt_is_not_turned_into_a_payment(self):
        create_payment, _ = self._run(fraud_score=FRAUD_REVIEW_SCORE_THRESHOLD)
        self.assertFalse(
            create_payment.called,
            "a receipt at/above the fraud-review threshold must NEVER be auto-applied "
            "-- it was being credited to the invoice while staff were emailed to "
            "'manually review' it",
        )

    def test_a_well_over_threshold_receipt_is_not_applied(self):
        create_payment, _ = self._run(fraud_score=95)
        self.assertFalse(create_payment.called)

    def test_a_clean_receipt_still_auto_applies(self):
        """The gate must not break the happy path it guards."""
        create_payment, _ = self._run(fraud_score=0)
        self.assertTrue(
            create_payment.called,
            "a clean, high-confidence, matching receipt must still auto-apply",
        )

    def test_just_below_threshold_still_auto_applies(self):
        create_payment, _ = self._run(fraud_score=FRAUD_REVIEW_SCORE_THRESHOLD - 1)
        self.assertTrue(create_payment.called)


class FraudThresholdIsSingleSourcedTests(TestCase):
    """The live decision and its dry-run twin must not drift apart again."""

    def test_no_bare_seventy_literal_remains_in_the_receipt_task(self):
        import inspect

        from apps.finance import tasks as finance_tasks

        src = inspect.getsource(
            finance_tasks._process_payment_receipt_upload_impl
        )
        self.assertNotIn(
            "fraud_risk_score >= 70",
            src,
            "the threshold must come from FRAUD_REVIEW_SCORE_THRESHOLD, not a "
            "literal -- the duplicated literal is how the live path and its "
            "dry-run twin drifted apart in the first place",
        )
        self.assertNotIn("fraud_risk_score < 70", src)
