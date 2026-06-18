"""parent_link_child wizard → bind a guardian user to a student by admission number.

Canonical link target: ``apps.people.models.StudentGuardian`` (unique per
``(guardian_user, student)``). This is the direct admission-number bind the
wizard collects — distinct from ``apps.portal.services.link_guardian_via_invite``
(the token/invite claim flow). Idempotent, tenant-scoped, audited.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


def _norm_relationship(raw: str | None) -> str:
    """Wizard sends lowercase tokens (mother/father/…); model stores uppercase."""
    from apps.people.models import StudentGuardian

    val = (raw or "").strip().upper()
    valid = {c for c, _ in StudentGuardian.Relationship.choices}
    return val if val in valid else StudentGuardian.Relationship.GUARDIAN


def _norm_preferred_contact(raw: str | None) -> str:
    from apps.people.models import StudentGuardian

    val = (raw or "").strip().upper()
    valid = {c for c, _ in StudentGuardian.PreferredContact.choices}
    return val if val in valid else StudentGuardian.PreferredContact.EMAIL


def link_guardian_to_student(
    *,
    school,
    actor_user_id: int | None,
    admission_number: str | None,
    relationship: str | None,
    preferred_contact: str | None,
) -> dict:
    """Bind the actor (a guardian/parent) to a student found by admission number.

    Returns a structured result dict. Idempotent: an existing
    ``(guardian, student)`` link returns ``already_linked`` rather than raising.
    The student is looked up *within* ``school`` (tenant scope).
    """
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian, StudentProfile

    adm = (admission_number or "").strip()
    if school is None or not actor_user_id or not adm:
        return {"ok": False, "error": "missing_inputs"}

    try:
        guardian = User.objects.get(pk=actor_user_id)
    except User.DoesNotExist:
        logger.warning("link_guardian_to_student: actor %s not found", actor_user_id)
        return {"ok": False, "error": "actor_not_found"}

    # StudentGuardian.clean() requires the guardian to be a PARENT or TEACHER.
    if guardian.role not in (User.Role.PARENT, User.Role.TEACHER):
        return {"ok": False, "error": "actor_not_guardian_role"}

    student = (
        # tenant-isolation-allow: student resolved within the wizard's own school scope
        StudentProfile.objects.filter(school=school, admission_number=adm).first()
    )
    if student is None:
        logger.info(
            "link_guardian_to_student: no student for admission number in school=%s",
            getattr(school, "pk", None),
        )
        return {"ok": False, "error": "student_not_found"}

    rel = _norm_relationship(relationship)
    pref = _norm_preferred_contact(preferred_contact)

    try:
        with transaction.atomic():
            link, created = StudentGuardian.objects.get_or_create(
                # tenant-isolation-allow: both sides already resolved to this school
                guardian_user=guardian,
                student=student,
                defaults={
                    "relationship": rel,
                    "preferred_contact": pref,
                    "email": guardian.email or "",
                },
            )
    except IntegrityError:
        # Lost a race on the unique constraint — treat as already linked.
        link = StudentGuardian.objects.filter(  # tenant-isolation-allow: resolved pair
            guardian_user=guardian, student=student
        ).first()
        created = False

    _audit_link(guardian=guardian, student=student, link=link, created=created)
    logger.info(
        "link_guardian_to_student guardian=%s student=%s created=%s",
        guardian.pk, student.pk, created,
    )
    return {
        "ok": True,
        "created": bool(created),
        "already_linked": not created,
        "link_id": getattr(link, "pk", None),
    }


def _audit_link(*, guardian, student, link, created) -> None:
    """Best-effort cross-cutting audit; never blocks the link."""
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            user=guardian,
            action=AuditLog.Action.CREATE,
            model_name="StudentGuardian",
            object_id=str(getattr(link, "pk", "") or ""),
            object_repr=f"guardian={guardian.pk} student={student.pk}",
            sensitivity=AuditLog.Sensitivity.HIGH,
            app_label="people",
            reason="Guardian-student link via parent_link_child wizard",
        )
    except Exception as exc:  # noqa: BLE001 — audit is best-effort
        logger.debug("link_guardian_to_student audit skipped: %s", exc)
