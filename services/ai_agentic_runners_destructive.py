"""Phase 3 — destructive agentic runners (dual-control, EraseRequest-backed).

**OPT-IN ONLY**, like the mutating siblings — importing this module changes no
global state. The Phase-3 orchestration in ``services.ai_agentic_service`` wires
these in explicitly, behind the dedicated ``RMC_AI_AGENTIC_DESTRUCTIVE_ENABLED``
flag AND a two-party (requester ≠ approver) human gate.

**Critical design rule (owner-approved):** a destructive action NEVER opens a new
delete path. ``purge_student_record`` routes through the platform's existing,
counsel-aware GDPR Art. 17 erasure machinery in ``apps.compliance``:

- the *request* step creates an ``EraseRequest`` (status PENDING) — the durable,
  SLA-tracked record the compliance team already understands;
- the *approve* step calls ``apps.compliance.gdpr_services.fulfill_pending_erasure``
  — the ONLY sanctioned PENDING/APPROVED→COMPLETED transition — which runs
  ``gdpr_scrub_student`` (anonymization that preserves referential integrity, not
  a hard row delete) and writes a ``ComplianceAuditLog`` entry.

So "purge" is really "the existing erasure pipeline, fronted by an AI proposal and
a dual-control gate." No raw ``Student.objects.delete()`` anywhere.
"""

from __future__ import annotations

import logging
from typing import Any

from .ai_agentic import ActionContext, ProposedAction

logger = logging.getLogger(__name__)


def _scope_school(tenant_id: str):
    """Resolve the School for tenant-scoped lookups.

    Resolves by primary key first — this handles BOTH UUID pks (``School.id`` is
    a UUIDField) and integer pks, since Django coerces the string form. Falls
    back to slug for non-pk tenant handles (e.g. ``"platform"``). Self-contained
    (does not delegate to the mutating sibling) so a destructive lookup never
    silently no-ops on a UUID tenant if that sibling's resolver lags behind."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return None
    try:
        from django.core.exceptions import ValidationError
        from apps.schools.models import School  # type: ignore

        try:
            school = School.objects.filter(pk=tid).first()
        except (ValueError, TypeError, ValidationError):
            school = None
        if school is not None:
            return school
        return School.objects.filter(slug=tid).first()
    except Exception as exc:  # noqa: BLE001
        logger.warning("destructive _scope_school failed tenant=%s err=%s", tid, exc)
        return None


def _resolve_student_profile(school, student_id: str):
    """Resolve a tenant-scoped StudentProfile by pk. Returns None if not found."""
    sid = str(student_id or "").strip()
    if not sid or school is None:
        return None
    try:
        from apps.people.models import StudentProfile  # type: ignore

        return StudentProfile.objects.filter(school=school, pk=sid).first()
    except Exception as exc:  # noqa: BLE001
        logger.warning("destructive student lookup failed err=%s", exc)
        return None


def create_purge_request(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Party-A step: create a PENDING ``EraseRequest`` for the named student.

    Does NOT erase anything — it records the intent in the compliance subsystem so
    the actual work (on a second operator's approval) flows through the sanctioned
    ``fulfill_pending_erasure`` path.

    Params: ``student_id`` (StudentProfile PK), ``justification`` (free text, the
    EraseRequest.reason). Returns ``{"ok", "erase_request_id", "student_pk",
    "subject_user_id"}`` or ``{"ok": False, "error": ...}``.
    """
    params = proposed.params or {}
    student_id = str(params.get("student_id") or "").strip()
    justification = str(params.get("justification") or "").strip()[:2000]
    if not student_id:
        return {"ok": False, "error": "student_id required"}

    school = _scope_school(ctx.tenant_id)
    if school is None:
        return {"ok": False, "error": "tenant scope unavailable"}

    student = _resolve_student_profile(school, student_id)
    if student is None:
        return {"ok": False, "error": f"student {student_id} not found in tenant"}

    subject_user_id = getattr(student, "user_id", None)
    if not subject_user_id:
        # The sanctioned fulfill path resolves the StudentProfile via the subject
        # User; a student with no linked account can't ride that rail. Refuse
        # cleanly rather than invent a second erasure path.
        return {"ok": False, "error": "subject_has_no_user"}

    try:
        from apps.compliance.models import EraseRequest  # type: ignore

        requested_by_id = None
        try:
            requested_by_id = int(ctx.user_id)
        except (TypeError, ValueError):
            requested_by_id = None

        er = EraseRequest.objects.create(
            school=school,
            requested_by_id=requested_by_id,
            subject_user_id=subject_user_id,
            status=EraseRequest.Status.PENDING,
            reason=justification or "AI-proposed erasure (dual-control)",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_purge_request: EraseRequest create failed")
        return {"ok": False, "error": f"erase request create failed: {exc}"}

    return {
        "ok": True,
        "erase_request_id": er.pk,
        "student_pk": str(student.pk),
        "subject_user_id": str(subject_user_id),
    }


def run_purge_student_record(
    proposed: ProposedAction,
    ctx: ActionContext,
) -> dict[str, Any]:
    """Party-B (approval) step: fulfill the previously-created EraseRequest.

    The orchestration injects ``params["_erase_request_id"]`` (from the request
    row's snapshot). Delegates to ``fulfill_pending_erasure`` — the single
    sanctioned PENDING/APPROVED→COMPLETED transition — using the approver
    (``ctx.confirmed_by``) as the fulfilling actor for the compliance audit.
    """
    params = proposed.params or {}
    erase_request_id = str(params.get("_erase_request_id") or "").strip()
    if not erase_request_id:
        return {"ok": False, "error": "_erase_request_id required"}

    fulfilled_by_id = None
    try:
        fulfilled_by_id = int(ctx.confirmed_by) if ctx.confirmed_by else None
    except (TypeError, ValueError):
        fulfilled_by_id = None

    try:
        from apps.compliance.gdpr_services import fulfill_pending_erasure

        result = fulfill_pending_erasure(
            int(erase_request_id),
            fulfilled_by_user_id=fulfilled_by_id,
            dry_run=False,
        )
    except (TypeError, ValueError):
        return {"ok": False, "error": f"invalid erase_request_id {erase_request_id!r}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_purge_student_record: fulfill failed")
        return {"ok": False, "error": f"erasure fulfillment failed: {exc}"}

    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "erasure failed",
                "erase_request_id": erase_request_id}
    return {
        "ok": True,
        "erase_request_id": erase_request_id,
        "status": result.get("status"),
    }


def reject_purge_request(erase_request_id: str) -> dict[str, Any]:
    """Cancel a still-PENDING EraseRequest (no erasure happens)."""
    erid = str(erase_request_id or "").strip()
    if not erid:
        return {"ok": False, "error": "erase_request_id required"}
    try:
        from apps.compliance.models import EraseRequest  # type: ignore

        er = EraseRequest.objects.filter(pk=erid).first()
        if er is None:
            return {"ok": False, "error": "EraseRequest not found"}
        if er.status not in {EraseRequest.Status.PENDING, EraseRequest.Status.APPROVED}:
            return {"ok": False, "error": f"already terminal: {er.status}"}
        er.status = EraseRequest.Status.REJECTED
        er.save(update_fields=["status"])
        return {"ok": True, "erase_request_id": erid, "status": er.status}
    except (TypeError, ValueError):
        return {"ok": False, "error": f"invalid erase_request_id {erid!r}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("reject_purge_request failed")
        return {"ok": False, "error": str(exc)}


# Opt-in lookup (the orchestration imports this and picks what to enable).
OPT_IN_DESTRUCTIVE_RUNNERS: dict[str, Any] = {
    "purge_student_record": run_purge_student_record,
}
