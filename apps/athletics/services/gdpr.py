"""GDPR wiring for the athletics module.

Two athletics models carry data-subject PII that must ride the DSAR
Data-Portability export (GDPR Art. 20) and be scrubbed on Right-to-Erasure
(GDPR Art. 17):

- ``MedicalClearance`` — free-text ``notes`` (sensitive health context) plus an
  uploaded clearance ``document``.
- ``ParticipationConsent`` — ``guardian_name`` / ``guardian_email`` (third-party
  guardian PII captured at consent time).

``TeamMembership`` is non-sensitive but is part of the athlete's record, so it
rides the export (never scrubbed — preserved for referential integrity).

Erasure PRESERVES every row (memberships, clearances, consents keep their FKs so
eligibility history and audit chains stay intact) and only redacts the PII-bearing
columns in place — mirroring ``apps.compliance.gdpr_services`` for guardians /
incidents. No PII is ever emitted to logs.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)

# Typed exception tuples — no broad except on ORM / file-storage paths.
_ATHLETICS_GDPR_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    ObjectDoesNotExist,
    AttributeError,
    TypeError,
    ValueError,
)
_ATHLETICS_FILE_DELETE_ERRORS = (
    OSError,
    PermissionError,
    ValueError,
    AttributeError,
    TypeError,
)


def _model(model_name: str):
    """Resolve an athletics model, or ``None`` if the app is unavailable."""
    try:
        return apps.get_model("athletics", model_name)
    except LookupError:
        logger.warning("athletics GDPR: model %s unavailable", model_name)
        return None


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def athletics_export_sections(*, school_id, student_id) -> dict[str, list[dict[str, Any]]]:
    """Return the athlete's athletics records for the Art. 20 export.

    School-scoped and student-scoped. Every value is JSON-serializable (dates
    isoformat, UUID pk stringified). ``token_sha256`` is deliberately NOT
    exported — it is a security credential, not the subject's personal data.
    """
    sections: dict[str, list[dict[str, Any]]] = {
        "team_memberships": [],
        "medical_clearances": [],
        "participation_consents": [],
    }

    TeamMembership = _model("TeamMembership")
    MedicalClearance = _model("MedicalClearance")
    ParticipationConsent = _model("ParticipationConsent")

    try:
        if TeamMembership:
            memberships = TeamMembership.objects.filter(
                school_id=school_id, student_id=student_id
            ).order_by("team_id", "id")
            for m in memberships:
                sections["team_memberships"].append(
                    {
                        "id": m.pk,
                        "team_id": m.team_id,
                        "jersey_number": m.jersey_number,
                        "position": m.position,
                        "status": m.status,
                        "joined_at": _iso(m.joined_at),
                        "left_at": _iso(m.left_at),
                        "created_at": _iso(m.created_at),
                    }
                )

        if MedicalClearance:
            clearances = MedicalClearance.objects.filter(
                school_id=school_id, student_id=student_id
            ).order_by("-valid_from", "id")
            for c in clearances:
                document = getattr(c, "document", None)
                sections["medical_clearances"].append(
                    {
                        "id": c.pk,
                        "sport_id": c.sport_id,
                        "status": c.status,
                        "cleared_by_id": c.cleared_by_id,
                        "valid_from": _iso(c.valid_from),
                        "valid_until": _iso(c.valid_until),
                        "notes": c.notes,
                        "document": document.name if document else None,
                        "created_at": _iso(c.created_at),
                    }
                )

        if ParticipationConsent:
            # Scope through the membership graph AND the direct school FK so the
            # export never crosses a tenant or student boundary.
            consents = ParticipationConsent.objects.filter(
                school_id=school_id, membership__student_id=student_id
            ).order_by("-token_issued_at")
            for p in consents:
                sections["participation_consents"].append(
                    {
                        "id": str(p.pk),
                        "membership_id": p.membership_id,
                        "guardian_name": p.guardian_name,
                        "guardian_email": p.guardian_email,
                        "decision": p.decision,
                        "consent_text_version": p.consent_text_version,
                        "consented_at": _iso(p.consented_at),
                        "declined_at": _iso(p.declined_at),
                        "token_issued_at": _iso(p.token_issued_at),
                        "expires_at": _iso(p.expires_at),
                        "created_at": _iso(p.created_at),
                    }
                )
    except _ATHLETICS_GDPR_ERRORS:
        logger.exception(
            "athletics GDPR export failed for school_id=%s student_id=%s",
            school_id,
            student_id,
        )

    return sections


def athletics_scrub_student(*, school_id, student_id) -> dict[str, int]:
    """Redact athletics PII in place for an Art. 17 erasure.

    The CALLER owns the transaction (this function opens none of its own).
    Rows are PRESERVED for referential integrity — only the PII-bearing columns
    are anonymized:

    - ``MedicalClearance.notes`` -> ``""``; ``document`` -> deleted + cleared.
    - ``ParticipationConsent.guardian_name`` -> ``"[erased]"``;
      ``guardian_email`` -> ``""``.

    Returns a count summary. School-scoped.
    """
    summary = {"medical_clearances": 0, "participation_consents": 0}

    MedicalClearance = _model("MedicalClearance")
    ParticipationConsent = _model("ParticipationConsent")

    if MedicalClearance:
        med_qs = MedicalClearance.objects.filter(
            school_id=school_id, student_id=student_id
        )
        for clearance in med_qs:
            document = getattr(clearance, "document", None)
            if document:
                try:
                    document.delete(save=False)
                except _ATHLETICS_FILE_DELETE_ERRORS:
                    logger.warning(
                        "athletics GDPR: could not delete clearance document "
                        "school_id=%s clearance_id=%s",
                        school_id,
                        clearance.pk,
                    )
        summary["medical_clearances"] = med_qs.update(notes="", document=None)

    if ParticipationConsent:
        summary["participation_consents"] = ParticipationConsent.objects.filter(
            school_id=school_id, membership__student_id=student_id
        ).update(
            guardian_name="[erased]",
            guardian_email="",
            # The decision IP + user-agent re-identify the guardian; a Right-to-
            # Erasure run must wipe them alongside name/email or the erasure is
            # defeated (the consent-text sha256 proof + version are retained as
            # non-PII legal evidence that consent was given).
            ip_address_decision=None,
            user_agent_decision="",
        )

    return summary


__all__ = ["athletics_export_sections", "athletics_scrub_student"]
