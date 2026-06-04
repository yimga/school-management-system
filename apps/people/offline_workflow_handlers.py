"""Offline person-creation workflows (edge/LAN onboarding).

Closes the biggest offline-first gap: an edge/LAN school could not onboard a
person offline. The student / teacher / applicant create forms each queue to the
OfflineAction ``field_capture`` rail with a
``data-rmc-offline-workflow="people_<kind>_create"`` marker; this module is the
missing server applier, mirroring ``apps.finance.offline_workflow_handlers``.

Security: the OfflineAction rail carries the authenticated offline user's id, but
authorization to create a person is RE-DERIVED here server-side (the matching
``people.add_*`` permission) — the client form must never be the authorization
boundary. Idempotency: the client_offline_id is stored on the created record
(``custom_attributes`` / ``extra_data``) so a replay (or two devices) cannot
create duplicates.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db import DatabaseError, IntegrityError, transaction

logger = logging.getLogger(__name__)

PEOPLE_WORKFLOWS: frozenset[str] = frozenset(
    {
        "people_student_create",
        "people_teacher_create",
        "people_applicant_create",
    }
)


def _client_key(payload: dict[str, Any]) -> str:
    return str(
        payload.get("client_offline_id") or payload.get("idempotency_key") or "",
    )[:128]


def _resolve_actor(user_id, perm: str):
    """Return ``(user, allowed)``; ``user`` is None when the id is unknown.

    Authorization is RE-DERIVED here: the offline client supplies the author id
    but never the verdict. ``perm`` is checked against the live permission graph.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()  # tenant-isolation-allow: offline-author-resolved-by-pk-then-permission-checked
    if user is None:
        return None, False
    return user, bool(user.has_perm(perm))


def _user_can_add_student(user_id):
    return _resolve_actor(user_id, "people.add_studentprofile")


def _user_can_add_teacher(user_id):
    return _resolve_actor(user_id, "people.add_teacherprofile")


def _user_can_add_applicant(user_id):
    return _resolve_actor(user_id, "people.add_applicant")


def _reject_cross_tenant_fks(form, school_id, fk_names) -> dict[str, Any] | None:
    """Reject any FK in ``fk_names`` whose ``school_id`` is not the bound tenant.

    The backend create forms' FK querysets are NOT school-scoped (online they
    rely on request RLS). On the offline drain there is no request, so a forged
    FK id from another tenant could otherwise be accepted — guard each one.
    """
    for fk_name in fk_names:
        obj = form.cleaned_data.get(fk_name)
        obj_school = getattr(obj, "school_id", None) if obj is not None else None
        if obj_school is not None and str(obj_school) != str(school_id):
            return {"ok": False, "error": "cross_tenant_%s" % fk_name}
    return None


def _existing_by_offline_id(model, school_id, client_key):
    """Return the row with this offline id for the tenant, or None.

    Dedupe is on the first-class ``client_offline_id`` column (DB-unique per
    tenant), not a JSON sub-key — so it is both race-safe (the constraint backs
    it) and index-backed.
    """
    if not client_key:
        return None
    return model.objects.filter(  # tenant-isolation-allow: explicit-school-scoped-offline-idempotency-lookup
        school_id=school_id, client_offline_id=client_key
    ).first()


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
    if workflow == "people_teacher_create":
        return _apply_teacher_create(school_id, user_id, fields, payload)
    if workflow == "people_applicant_create":
        return _apply_applicant_create(school_id, user_id, fields, payload)
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
    # A freshly-created parent has an unusable password; send the one-time
    # set-password link so they are not locked out. Runs during the (online)
    # drain, so this is the right moment to deliver. Best-effort — the invite
    # helper never raises, and email delivery itself is an external dependency.
    if created:
        try:
            from apps.accounts.guardian_invite import send_guardian_invite

            send_guardian_invite(
                parent_user, school=getattr(student, "school", None)
            )
        except Exception:  # noqa: BLE001 — credential delivery must not break creation
            logger.warning("people.offline_guardian_invite_failed student=%s", student.pk)
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
        existing = _existing_by_offline_id(StudentProfile, school_id, client_key)
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

    # Defense-in-depth: reject any FK from another tenant (querysets aren't
    # school-scoped offline; there is no request RLS on the drain).
    cross = _reject_cross_tenant_fks(
        form, school_id, ("classroom", "academic_year", "specialty")
    )
    if cross is not None:
        return cross

    try:
        with transaction.atomic():
            student = form.save(commit=False)
            student.school_id = school_id
            student.created_by_id = user_id
            student.is_active = True
            student.client_offline_id = client_key
            attrs = dict(getattr(student, "custom_attributes", None) or {})
            attrs["created_offline"] = True
            student.custom_attributes = attrs
            student.save()
            parent_email = (form.cleaned_data.get("parent_email") or "").strip()
            guardian_linked = False
            if parent_email:
                guardian_linked = _link_parent(
                    student, parent_email, form.cleaned_data.get("parent_phone") or ""
                )
    except IntegrityError:
        existing = _existing_by_offline_id(StudentProfile, school_id, client_key)
        if existing:
            return {"ok": True, "dedup": True, "student_id": existing.pk, "people_create_capture": True}
        logger.warning("people.offline_student_create integrity school=%s", school_id)
        return {"ok": False, "error": "create_failed:IntegrityError"}
    except (DatabaseError, ValueError) as exc:
        logger.warning("people.offline_student_create failed school=%s err=%s", school_id, exc)
        return {"ok": False, "error": "create_failed:%s" % type(exc).__name__}

    return {
        "ok": True,
        "student_id": student.pk,
        "guardian_linked": guardian_linked,
        "people_create_capture": True,
    }


def _apply_teacher_create(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from django.contrib.auth import get_user_model

    from apps.people.forms_backend import TeacherCreateForm
    from apps.people.models import TeacherProfile

    actor, allowed = _user_can_add_teacher(user_id)
    if actor is None:
        return {"ok": False, "error": "unknown_user"}
    if not allowed:
        return {"ok": False, "error": "not_authorized_to_create_teacher"}

    client_key = _client_key(payload)
    if client_key:
        existing = _existing_by_offline_id(TeacherProfile, school_id, client_key)
        if existing:
            return {
                "ok": True,
                "dedup": True,
                "teacher_id": existing.pk,
                "people_create_capture": True,
            }

    form = TeacherCreateForm(data=fields)
    if not form.is_valid():
        return {
            "ok": False,
            "error": "validation_failed",
            "details": form.errors.get_json_data(),
        }

    cross = _reject_cross_tenant_fks(form, school_id, ("department", "reports_to"))
    if cross is not None:
        return cross

    User = get_user_model()
    email = (form.cleaned_data["email"] or "").strip().lower()
    username = (form.cleaned_data.get("username") or email).strip()
    password = form.cleaned_data["password"]

    # Email uniqueness is the second idempotency/conflict boundary: if the email
    # already belongs to a user, we must not double-create. A replay of the SAME
    # offline action is caught by client_offline_id above; reaching here with an
    # existing email means a genuine conflict (someone else created it, or the
    # address is taken by another role) — surface it as FAILED, never crash.
    if User.objects.filter(email__iexact=email).exists() or (
        username and User.objects.filter(username__iexact=username).exists()
    ):
        return {"ok": False, "error": "email_or_username_taken"}

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=User.Role.TEACHER,
                is_active=True,
            )
            teacher = form.save(commit=False)
            teacher.user = user
            teacher.school_id = school_id
            teacher.is_active = True
            teacher.client_offline_id = client_key
            attrs = dict(getattr(teacher, "custom_attributes", None) or {})
            attrs["created_offline"] = True
            teacher.custom_attributes = attrs
            teacher.save()
    except IntegrityError:
        existing = _existing_by_offline_id(TeacherProfile, school_id, client_key)
        if existing:
            return {"ok": True, "dedup": True, "teacher_id": existing.pk, "people_create_capture": True}
        logger.warning("people.offline_teacher_create integrity school=%s", school_id)
        return {"ok": False, "error": "create_failed:IntegrityError"}
    except (DatabaseError, ValueError) as exc:
        logger.warning(
            "people.offline_teacher_create failed school=%s err=%s", school_id, exc
        )
        return {"ok": False, "error": "create_failed:%s" % type(exc).__name__}

    return {
        "ok": True,
        "teacher_id": teacher.pk,
        "user_id": user.pk,
        "people_create_capture": True,
    }


def _apply_applicant_create(
    school_id: int, user_id: int, fields: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    from apps.people.forms_backend import ApplicantCreateForm
    from apps.people.models import Applicant

    actor, allowed = _user_can_add_applicant(user_id)
    if actor is None:
        return {"ok": False, "error": "unknown_user"}
    if not allowed:
        return {"ok": False, "error": "not_authorized_to_create_applicant"}

    client_key = _client_key(payload)
    if client_key:
        existing = _existing_by_offline_id(Applicant, school_id, client_key)
        if existing:
            return {
                "ok": True,
                "dedup": True,
                "applicant_id": existing.pk,
                "people_create_capture": True,
            }

    form = ApplicantCreateForm(data=fields)
    if not form.is_valid():
        return {
            "ok": False,
            "error": "validation_failed",
            "details": form.errors.get_json_data(),
        }

    try:
        with transaction.atomic():
            applicant = form.save(commit=False)
            applicant.school_id = school_id
            applicant.client_offline_id = client_key
            extra = dict(getattr(applicant, "extra_data", None) or {})
            extra["created_offline"] = True
            applicant.extra_data = extra
            applicant.save()
    except IntegrityError:
        existing = _existing_by_offline_id(Applicant, school_id, client_key)
        if existing:
            return {"ok": True, "dedup": True, "applicant_id": existing.pk, "people_create_capture": True}
        logger.warning("people.offline_applicant_create integrity school=%s", school_id)
        return {"ok": False, "error": "create_failed:IntegrityError"}
    except (DatabaseError, ValueError) as exc:
        logger.warning(
            "people.offline_applicant_create failed school=%s err=%s", school_id, exc
        )
        return {"ok": False, "error": "create_failed:%s" % type(exc).__name__}

    return {
        "ok": True,
        "applicant_id": applicant.pk,
        "people_create_capture": True,
    }
