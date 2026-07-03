"""Apply teacher transfer envelopes at target schools (Phase 4B)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from apps.interop.transfer_envelope import TransferEnvelope

logger = logging.getLogger(__name__)


class TransferApplyError(RuntimeError):
    pass


@dataclass(frozen=True)
class TransferApplyResult:
    employment_id: str
    assignment_id: str
    target_school_id: str
    envelope_checksum: str


def _canonical_bytes(body: dict[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_envelope_checksum(envelope: TransferEnvelope) -> None:
    body = envelope.to_dict()
    body.pop("checksum", None)
    expected = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    if not envelope.checksum or envelope.checksum != expected:
        raise TransferApplyError("envelope checksum mismatch")


def apply_teacher_transfer_envelope(
    envelope: TransferEnvelope,
    *,
    target_school_id: str,
    organization_id: str,
    user_id: int,
    started_on: date | None = None,
    allocation_fraction: Decimal | None = None,
) -> TransferApplyResult:
    """
    Materialize ``Employment`` + ``SchoolAssignment`` from a teacher envelope.

    Caller must ensure BOLA checks passed (user may access target school/org).
    """
    if envelope.envelope_kind != "teacher":
        raise TransferApplyError(f"unsupported envelope_kind {envelope.envelope_kind!r}")
    verify_envelope_checksum(envelope)

    from apps.governance.models import Employment, SchoolAssignment
    from apps.schools.models import School

    school = School.objects.filter(pk=target_school_id, is_active=True).first()
    if school is None:
        raise TransferApplyError("target school not found")
    if str(getattr(school, "organization_id", "")) != str(organization_id):
        raise TransferApplyError("target school not in organization")

    effective_date = started_on or date.today()
    fraction = allocation_fraction if allocation_fraction is not None else Decimal("1.00")

    # Idempotent re-apply (design §8 defect 3): re-sending the same envelope
    # must not stack duplicate Employment/SchoolAssignment rows.
    employment = Employment.objects.filter(  # tenant-isolation-allow: org-scoped-teacher-transfer-apply-target-verified-above
        organization_id=organization_id,
        user_id=user_id,
        is_active=True,
    ).first()
    if employment is None:
        employment = Employment.objects.create(
            organization_id=organization_id,
            user_id=user_id,
            title=str(envelope.canonical_fields.get("position_title") or "Teacher"),
            started_on=effective_date,
            is_active=True,
        )
    assignment, _created = SchoolAssignment.objects.get_or_create(
        employment=employment,
        school=school,
        role="TEACHER",  # role-string-allow: transfer-apply-teacher-envelope-default-role
        is_active=True,
        defaults={
            "allocation_fraction": fraction,
            "started_on": effective_date,
            "is_primary": True,
        },
    )

    logger.info(
        "transfer_apply.teacher employment=%s assignment=%s school=%s checksum=%s",
        employment.pk,
        assignment.pk,
        target_school_id,
        envelope.checksum[:12],
        extra={"scope": "transfer_apply.teacher"},
    )
    return TransferApplyResult(
        employment_id=str(employment.pk),
        assignment_id=str(assignment.pk),
        target_school_id=str(target_school_id),
        envelope_checksum=envelope.checksum,
    )


__all__ = [
    "TransferApplyError",
    "TransferApplyResult",
    "apply_teacher_transfer_envelope",
    "verify_envelope_checksum",
]
