"""
Deterministic rail selection and receipt reconciliation helpers.

Advisory/runtime helpers for UX and staff workflows — billing enforcement and
tenant isolation remain enforced by callers (school-scoped invoices, RBAC).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import UUID

from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError

from apps.finance.models import Invoice, PaymentProofUpload
from apps.finance.payment_fallback import select_fallback_chain
from apps.finance.regional_payment_profiles import get_normalized_regional_profile

MANUAL_FALLBACK_CODE = "MANUAL_RECEIPT"


def _rail_available(code: str, availability: Mapping[str, bool] | None) -> bool:
    if not availability:
        return True
    return bool(availability.get(code, True))


def select_primary_rail(country_code: str | None) -> str | None:
    profile = get_normalized_regional_profile(country_code)
    if not profile:
        return None
    rail = str(profile.get("primary_rail") or "").strip()
    return rail or None


def select_effective_rail(
    country_code: str | None,
    rail_availability: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """
    Pick first online rail from corridor chain that is available; otherwise manual receipt path.

    ``rail_availability`` maps rail code -> False when gateway unhealthy/disabled.
    Missing keys default to available (True).
    """
    profile = get_normalized_regional_profile(country_code)
    if not profile:
        return {
            "country_code": country_code,
            "selected_rail": MANUAL_FALLBACK_CODE,
            "primary_rail": None,
            "backup_rail": None,
            "reason": "unknown_country_manual_fallback",
            "manual_fallback": True,
            "offline_receipt_allowed": False,
        }

    chain = select_fallback_chain(country_code)
    manual_ok = bool(profile.get("manual_fallback", True))
    offline_ok = bool(profile.get("offline_receipt_allowed", False))

    chosen: str | None = None
    for rail in chain:
        if _rail_available(rail, rail_availability):
            chosen = rail
            break

    primary_code = str(profile.get("primary_rail") or "").strip()
    if chosen:
        if primary_code and chosen == primary_code:
            reason = "primary"
        elif primary_code and chosen == str(profile.get("backup_rail") or "").strip():
            reason = "backup"
        else:
            reason = "corridor_chain"
        return {
            "country_code": profile.get("country_code"),
            "selected_rail": chosen,
            "primary_rail": profile.get("primary_rail"),
            "backup_rail": profile.get("backup_rail"),
            "reason": reason,
            "manual_fallback": manual_ok,
            "offline_receipt_allowed": offline_ok,
        }

    if manual_ok:
        return {
            "country_code": profile.get("country_code"),
            "selected_rail": MANUAL_FALLBACK_CODE,
            "primary_rail": profile.get("primary_rail"),
            "backup_rail": profile.get("backup_rail"),
            "reason": "all_listed_rails_unavailable_manual_path",
            "manual_fallback": True,
            "offline_receipt_allowed": offline_ok,
        }

    return {
        "country_code": profile.get("country_code"),
        "selected_rail": MANUAL_FALLBACK_CODE,
        "primary_rail": profile.get("primary_rail"),
        "backup_rail": profile.get("backup_rail"),
        "reason": "rails_down_manual_disabled_operator_must_restore_gateway",
        "manual_fallback": False,
        "offline_receipt_allowed": offline_ok,
    }


def invoice_school_id(invoice: Invoice) -> UUID | int | None:
    """Return tenant school FK as stored (School.pk may be UUID)."""
    sid = getattr(invoice, "school_id", None)
    if sid is not None:
        return sid
    student = getattr(invoice, "student", None)
    if student is not None and getattr(student, "school_id", None) is not None:
        return student.school_id
    return None


def assert_proof_matches_school(
    proof: PaymentProofUpload, expected_school_id: UUID | int
) -> None:
    inv = proof.invoice
    actual = invoice_school_id(inv)
    if actual != expected_school_id:
        raise PermissionError("Payment proof does not belong to this school tenant.")


def describe_pending_reconciliation(proof: PaymentProofUpload) -> dict[str, Any]:
    """Structured view for queues: offline / manual items await staff decision."""
    inv = proof.invoice
    cc = getattr(getattr(inv, "profile", None), "country_code", None)
    norm = get_normalized_regional_profile(cc) or {}
    return {
        "proof_id": proof.pk,
        "invoice_id": inv.pk,
        "status": proof.status,
        "reconciliation_required": bool(norm.get("reconciliation_required", True)),
        "school_id": invoice_school_id(inv),
        "hint": norm.get("reconciliation") or "",
    }


def approve_payment_proof_reconciliation(
    proof_upload: PaymentProofUpload,
    verified_by,
    *,
    receipt_data: dict[str, Any] | None = None,
    expected_school_id: UUID | int | None = None,
):
    """
    Apply verified receipt to invoice and write APPROVE audit row.

    Raises PermissionError on tenant mismatch when ``expected_school_id`` is set.
    """
    from apps.compliance.models_audit import AuditLog
    from apps.finance.services import create_payment_from_receipt

    if expected_school_id is not None:
        assert_proof_matches_school(proof_upload, expected_school_id)

    if proof_upload.status not in (
        PaymentProofUpload.Status.PENDING,
        PaymentProofUpload.Status.DISCREPANCY,
    ):
        raise ValueError("Proof upload is not awaiting reconciliation.")

    data: dict[str, Any] = dict(receipt_data or proof_upload.verification_data or {})
    if not data.get("amount"):
        amt = proof_upload.uploaded_amount
        if amt is not None:
            data["amount"] = amt
    raw_amt = data.get("amount")
    if raw_amt is not None and not isinstance(raw_amt, Decimal):
        try:
            data["amount"] = Decimal(str(raw_amt))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Cannot approve: receipt amount invalid.") from exc
    if not data.get("amount"):
        raise ValueError("Cannot approve: receipt amount missing.")

    payment = create_payment_from_receipt(
        proof_upload, data, verified_by=verified_by
    )

    try:
        AuditLog.objects.create(
            action=AuditLog.Action.APPROVE,
            user=verified_by,
            model_name="PaymentProofUpload",
            object_id=str(proof_upload.pk),
            object_repr=str(proof_upload),
            app_label="finance",
            new_values={
                "status": PaymentProofUpload.Status.VERIFIED,
                "payment_id": payment.pk,
            },
            reason="Reconciliation approve (global payments engine)",
            sensitivity=AuditLog.Sensitivity.HIGH,
        )
    except (DatabaseError, IntegrityError, ValidationError, AttributeError, TypeError):
        pass

    return payment


def reject_payment_proof_reconciliation(
    proof_upload: PaymentProofUpload,
    verified_by,
    reason: str,
    *,
    expected_school_id: UUID | int | None = None,
) -> None:
    from apps.compliance.models_audit import AuditLog

    if expected_school_id is not None:
        assert_proof_matches_school(proof_upload, expected_school_id)

    if proof_upload.status not in (
        PaymentProofUpload.Status.PENDING,
        PaymentProofUpload.Status.DISCREPANCY,
    ):
        raise ValueError("Proof upload is not awaiting reconciliation.")

    reason = (reason or "Rejected")[:255]
    proof_upload.status = PaymentProofUpload.Status.REJECTED
    proof_upload.verified_by = verified_by
    if not proof_upload.verification_notes:
        proof_upload.verification_notes = ""
    proof_upload.verification_notes += f" Rejected: {reason}"
    proof_upload.verification_reason = reason
    proof_upload.save()

    try:
        AuditLog.objects.create(
            action=AuditLog.Action.REJECT,
            user=verified_by,
            model_name="PaymentProofUpload",
            object_id=str(proof_upload.pk),
            object_repr=str(proof_upload),
            app_label="finance",
            new_values={"status": "REJECTED"},
            reason=reason,
            sensitivity=AuditLog.Sensitivity.HIGH,
        )
    except (DatabaseError, IntegrityError, ValidationError, AttributeError, TypeError):
        pass


def coerce_verification_amount_dict(
    proof: PaymentProofUpload,
) -> dict[str, Any]:
    """Normalise minimal dict for ``create_payment_from_receipt`` in tests/helpers."""
    data = dict(proof.verification_data or {})
    if not data.get("amount") and proof.uploaded_amount is not None:
        data["amount"] = proof.uploaded_amount
    if not data.get("reference"):
        ref = proof.transaction_reference or ""
        if ref:
            data["reference"] = ref
    return data
