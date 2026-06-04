"""Offline person-creation workflows (edge/LAN onboarding).

Closes the biggest offline-first gap: an edge/LAN school could not onboard a
student offline. The student-create form already queues to the OfflineAction
``field_capture`` rail with ``data-rmc-offline-workflow="people_student_create"``;
this module is the missing server applier, mirroring
``apps.finance.offline_workflow_handlers``.

Security: the OfflineAction rail carries the authenticated offline user's id, but
authorization to create a student is RE-DERIVED here server-side (``people.add_
studentprofile``) — the client form must never be the authorization boundary.
Idempotency: the client_offline_id is stored on the StudentProfile so a replay
(or two devices) cannot create duplicates.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError, IntegrityError, transaction

logger = logging.getLogger(__name__)

PEOPLE_WORKFLOWS: frozenset[str] = frozenset({"people_student_create"})


def _client_key(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id") or payload.get("idempotency_key") or "",
    )[:128]


def _user_can_add_student(user_id):
    """Return ``(user, allowed)``; ``user`` is None when the id is unknown."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: offline-author-resolved-by-pk-then-permission-checked
    if user is None:
        return None, False
    return user, bool(user.has_perm("people.add_studentprofile"))


def apply_people_workflow(
    school_id: int,
    user_id: int,
    workflow: str,
    fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if workflow not in PEOPLE_WORKFLOWS:
        return None
    if workflow == "people_student_create":
        return _apply_student_create(school_id, user_id, fields, payload)
    return None


def _link_parent(student, parent_email: str, parent_phone: str) -> bool:
    """Best-effort guardian link (mirrors backend_student_create). Online email
    delivery is intentionally deferred — offline we only create the linkage."""
    from django.contrib.auth import get_user_model

    from apps.people.models import StudentGuardian

    User = get_user_model()
    email = (parent_email or "").strip().lower()
    if not email:
        return False
    parent_user, created = User.objects.get_or_create(
        email=email,
        defaults={"username": email, "role": User.Role.PARENT, "is_active": True},
    )
    if created:
        parent_user.set_unusable_password()
        parent_user.save(update_fields=["password"])
    elif getattr(parent_user, "role", None) != User.Role.PARENT:
        # Do not link a staff/teacher account as a guardian.
        return False
    StudentGuardian.objects.get_or_create(
        student=student,
        guardian_user=parent_user,
        defaults={
            "relationship": StudentGuardian.Relationship.GUARDIAN,
            "email": email,
            "phone": parent_phone or "",
        },
    )
    return True


def _apply_student_create(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.people.forms_backend import StudentCreateForm
    from apps.people.models import StudentProfile

    user, allowed = _user_can_add_student(user_id)
    if user is None:
        return {"ok": False, "error": "unknown_user"}
    if not allowed:
        return {"ok": False, "error": "not_authorized_to_create_student"}

    client_key = _client_key(payload)
    if client_key:
        existing = StudentProfile.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-offline-idempotency-lookup
            school_id=school_id,
            custom_attributes__offline_client_id=client_key,
        ).first()
        if existing:
            return {
                "ok": True,
                "dedup": True,
                "student_id": existing.pk,
                "people_create_capture": True,
            }

    form = StudentCreateForm(data=fields)
    if not form.is_valid():
        return {
            "ok": False,
            "error": "validation_failed",
            "details": form.errors.get_json_data(),
        }

    # Defense-in-depth: StudentCreateForm's FK querysets are NOT school-scoped
    # (online it relies on request RLS). On the offline drain a forged
    # classroom/year/specialty id from another tenant could otherwise be
    # accepted, so reject any FK whose school does not match the bound tenant.
    for fk_name in ("classroom", "academic_year", "specialty"):
        obj = form.cleaned_data.get(fk_name)
        obj_school = getattr(obj, "school_id", None) if obj is not None else None
        if obj_school is not None and str(obj_school) != str(school_id):
            return {"ok": False, "error": "cross_tenant_%s" % fk_name}

    try:
        with transaction.atomic():
            student = form.save(commit=False)
            student.school_id = school_id
            student.created_by_id = user_id
            student.is_active = True
            attrs = dict(getattr(student, "custom_attributes", None) or {})
            attrs["created_offline"] = True
            if client_key:
                attrs["offline_client_id"] = client_key
            student.custom_attributes = attrs
            student.save()
            parent_email = (form.cleaned_data.get("parent_email") or "").strip()
            guardian_linked = False
            if parent_email:
                guardian_linked = _link_parent(
                    student, parent_email, form.cleaned_data.get("parent_phone") or ""
                )
    except (DatabaseError, IntegrityError, ValueError) as exc:
        logger.warning("people.offline_student_create failed school=%s err=%s", school_id, exc)
        return {"ok": False, "error": "create_failed:%s" % type(exc).__name__}

    return {
        "ok": True,
        "student_id": student.pk,
        "guardian_linked": guardian_linked,
        "people_create_capture": True,
    }
