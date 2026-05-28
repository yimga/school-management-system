"""Wave R-B (v3.96.0 — 2026-05-26) — Admission application kernel.

Augments the existing ``apps.people.models.Applicant`` row with document
checklist tracking, stage-transition validation, and a single canonical
``enroll_applicant_to_student`` service. Documents are referenced by URL or
storage key — actual upload handling stays in the existing file-upload
pattern (PassportDocument shape) per the recon report.

All extended state is stored in ``Applicant.extra_data`` under a top-level
``"application"`` key so the kernel ships ZERO new migrations.

Stage transition rules (FSM):

    LEAD ─→ APPLIED ─→ UNDER_REVIEW ─→ ACCEPTED ─→ ENROLLED
                              └──────→ REJECTED

Reverting from ACCEPTED to UNDER_REVIEW is allowed (admissions officer
changed their mind). Reverting from ENROLLED is NOT allowed.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---- Document registry ----------------------------------------------------


@dataclass(frozen=True)
class DocumentSpec:
    """One required document in the admissions checklist."""

    key: str
    label: str
    required: bool = True
    accepted_extensions: tuple[str, ...] = (".pdf", ".jpg", ".jpeg", ".png")


_DOCUMENT_REGISTRY: dict[str, DocumentSpec] = {
    "birth_certificate": DocumentSpec(
        key="birth_certificate", label="Birth certificate", required=True,
    ),
    "previous_school_report": DocumentSpec(
        key="previous_school_report", label="Previous school report card", required=True,
    ),
    "immunization_record": DocumentSpec(
        key="immunization_record", label="Immunization record", required=True,
    ),
    "passport_photo": DocumentSpec(
        key="passport_photo", label="Passport-sized photo",
        accepted_extensions=(".jpg", ".jpeg", ".png"), required=True,
    ),
    "guardian_id": DocumentSpec(
        key="guardian_id", label="Guardian government-issued ID", required=True,
    ),
    "proof_of_address": DocumentSpec(
        key="proof_of_address", label="Proof of address", required=False,
    ),
    "transfer_certificate": DocumentSpec(
        key="transfer_certificate",
        label="Transfer certificate from prior school",
        required=False,
    ),
}


def list_required_documents() -> list[DocumentSpec]:
    return [d for d in _DOCUMENT_REGISTRY.values() if d.required]


def list_all_documents() -> list[DocumentSpec]:
    return list(_DOCUMENT_REGISTRY.values())


def get_document_spec(key: str) -> DocumentSpec | None:
    return _DOCUMENT_REGISTRY.get(key)


# ---- Stage FSM ------------------------------------------------------------


# Mirror Applicant.Stage exactly. We don't import the model here so this
# kernel is unit-testable without Django's app registry primed.
LEAD = "LEAD"
APPLIED = "APPLIED"
UNDER_REVIEW = "UNDER_REVIEW"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
ENROLLED = "ENROLLED"

ALL_STAGES = (LEAD, APPLIED, UNDER_REVIEW, ACCEPTED, REJECTED, ENROLLED)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    LEAD: frozenset({APPLIED}),
    APPLIED: frozenset({UNDER_REVIEW, REJECTED}),
    UNDER_REVIEW: frozenset({ACCEPTED, REJECTED}),
    ACCEPTED: frozenset({UNDER_REVIEW, ENROLLED}),
    REJECTED: frozenset({UNDER_REVIEW}),
    ENROLLED: frozenset(),  # terminal — re-enrollment is a brand-new applicant
}


class InvalidStageTransition(ValueError):
    pass


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, frozenset())


def require_transition(current: str, target: str) -> None:
    if current == target:
        return
    if not can_transition(current, target):
        raise InvalidStageTransition(
            f"Cannot advance applicant from {current!r} to {target!r}."
        )


# ---- Application payload helpers -----------------------------------------


@dataclass
class DocumentChecklistEntry:
    key: str
    label: str
    required: bool
    received: bool
    storage_ref: str = ""
    received_at: str = ""


@dataclass
class ApplicationSummary:
    stage: str
    document_count_received: int
    document_count_required: int
    required_outstanding: list[str]
    last_stage_change_at: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_document_complete(self) -> bool:
        return not self.required_outstanding


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_application_payload(extra_data: dict[str, Any] | None) -> dict[str, Any]:
    """Return the (read-only copy of the) application sub-payload."""
    if not extra_data:
        return {"documents": {}, "history": [], "metadata": {}}
    payload = extra_data.get("application") or {}
    return {
        "documents": copy.deepcopy(payload.get("documents") or {}),
        "history": copy.deepcopy(payload.get("history") or []),
        "metadata": copy.deepcopy(payload.get("metadata") or {}),
    }


def _write_application_payload(
    extra_data: dict[str, Any] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    new = dict(extra_data or {})
    new["application"] = payload
    return new


def attach_document_reference(
    *,
    extra_data: dict[str, Any] | None,
    document_key: str,
    storage_ref: str,
) -> dict[str, Any]:
    """Mark a document as received; returns the new extra_data dict."""
    spec = get_document_spec(document_key)
    if spec is None:
        raise ValueError(f"Unknown document key {document_key!r}")
    if not storage_ref:
        raise ValueError("storage_ref is required")
    payload = get_application_payload(extra_data)
    payload["documents"][document_key] = {
        "received": True,
        "storage_ref": storage_ref,
        "received_at": _now_iso(),
    }
    return _write_application_payload(extra_data, payload)


def remove_document_reference(
    *,
    extra_data: dict[str, Any] | None,
    document_key: str,
) -> dict[str, Any]:
    payload = get_application_payload(extra_data)
    payload["documents"].pop(document_key, None)
    return _write_application_payload(extra_data, payload)


def build_summary(
    *,
    stage: str,
    extra_data: dict[str, Any] | None,
) -> ApplicationSummary:
    payload = get_application_payload(extra_data)
    docs = payload["documents"]
    required = [spec for spec in _DOCUMENT_REGISTRY.values() if spec.required]
    outstanding = [
        spec.key for spec in required
        if not (docs.get(spec.key) or {}).get("received")
    ]
    received = sum(1 for d in docs.values() if (d or {}).get("received"))
    last = ""
    history = payload.get("history") or []
    if history:
        last = history[-1].get("at", "")
    return ApplicationSummary(
        stage=stage,
        document_count_received=received,
        document_count_required=len(required),
        required_outstanding=outstanding,
        last_stage_change_at=last,
        history=list(history),
    )


def advance_stage(
    *,
    current_stage: str,
    target_stage: str,
    extra_data: dict[str, Any] | None,
    actor_id: int | None = None,
    note: str = "",
) -> tuple[str, dict[str, Any]]:
    """Validate + record the stage transition.

    Returns ``(new_stage, new_extra_data)``. Caller persists.
    """
    if target_stage not in ALL_STAGES:
        raise ValueError(f"Unknown stage {target_stage!r}")
    require_transition(current_stage, target_stage)

    payload = get_application_payload(extra_data)
    payload["history"].append(
        {
            "at": _now_iso(),
            "from": current_stage,
            "to": target_stage,
            "actor_id": actor_id,
            "note": note[:240],
        }
    )
    return target_stage, _write_application_payload(extra_data, payload)


def can_enroll(*, current_stage: str, extra_data: dict[str, Any] | None) -> tuple[bool, list[str]]:
    """A pre-flight check before ``enroll_applicant_to_student`` runs."""
    reasons: list[str] = []
    if current_stage != ACCEPTED:
        reasons.append(f"applicant_must_be_accepted_not_{current_stage}")
    summary = build_summary(stage=current_stage, extra_data=extra_data)
    if not summary.is_document_complete:
        reasons.append(
            "required_documents_outstanding:" + ",".join(summary.required_outstanding)
        )
    return (not reasons, reasons)


# ---- Enrollment service (Applicant → StudentProfile) ---------------------


@dataclass
class EnrollmentResult:
    ok: bool
    student_id: int | None = None
    student_external_id: str = ""
    error: str = ""
    blockers: list[str] = field(default_factory=list)


def enroll_applicant_to_student(
    *,
    applicant_id: int,
    school_id: int,
    actor_user_id: int | None = None,
    db_runner=None,
) -> EnrollmentResult:
    """Promote an ACCEPTED applicant with full document set to a StudentProfile.

    Thin DB seam via ``db_runner`` so the FSM + document logic is unit-testable
    without Django. The default runner uses the live Applicant + StudentProfile
    models.
    """
    runner = db_runner or _default_enroll_runner
    return runner(
        applicant_id=applicant_id,
        school_id=school_id,
        actor_user_id=actor_user_id,
    )


def _default_enroll_runner(
    *, applicant_id: int, school_id: int, actor_user_id: int | None,
) -> EnrollmentResult:
    from django.db import transaction  # type: ignore

    from apps.people.models import Applicant, StudentProfile  # type: ignore

    # tenant-isolation-allow: admissions-enrollment-applicant-confined-to-school
    applicant = Applicant.objects.filter(
        id=applicant_id, school_id=school_id,
    ).first()
    if applicant is None:
        return EnrollmentResult(ok=False, error="applicant_not_found")

    ok, blockers = can_enroll(
        current_stage=applicant.stage, extra_data=applicant.extra_data,
    )
    if not ok:
        return EnrollmentResult(ok=False, error="preflight_failed", blockers=blockers)

    with transaction.atomic():
        # Promote to ENROLLED stage first so a partial-failure on student
        # create leaves the applicant intact for retry.
        new_stage, new_extra = advance_stage(
            current_stage=applicant.stage,
            target_stage=ENROLLED,
            extra_data=applicant.extra_data,
            actor_id=actor_user_id,
            note="auto-promoted by enrollment service",
        )
        applicant.stage = new_stage
        applicant.extra_data = new_extra
        applicant.save(update_fields=["stage", "extra_data", "updated_at"])

        student = StudentProfile.objects.create(
            school_id=school_id,
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            email=applicant.email or "",
        )
    return EnrollmentResult(
        ok=True,
        student_id=student.id,
        student_external_id=getattr(student, "external_id", "") or "",
    )
