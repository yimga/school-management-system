"""Promote imported parent/guardian *hints* into the live Guardian directory.

Most African / TVET rosters put a Parent column on the student sheet, not a
``guardians.csv``. G6 stored that as a student-scoped DynamicFieldValue hint so
a later claim flow could confirm the name. The Guardians sidebar
(``accounts:backend_guardian_list``) lists ``StudentGuardian`` rows that require
a ``guardian_user`` FK — so imported parents never appeared, and verification
counted 0 guardians.

This module creates the directory link (PARENT ``User`` + ``StudentGuardian``)
while keeping the original consent rule for *login*: the password stays
unusable until an admin invites the parent or hands them a one-time password.
The DFV hint is kept so the claim UX still has the source name.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model

from apps.accounts.email_delivery_policy import (
    is_deliverable_email,
    synthetic_unclaimed_email,
)

logger = logging.getLogger(__name__)

_PROMOTE_CAP = 10000  # magic-number-allow: post-apply-guardian-directory-promote-ceiling


def ensure_school_membership(*, user, school, role: str, update_role: bool = False) -> None:
    """Attach ``user`` to ``school``. Existing membership roles stay unless ``update_role``."""
    if user is None or school is None or not getattr(user, "pk", None) or not role:
        return
    from apps.schools.models import SchoolMembership

    has_primary = SchoolMembership.objects.filter(  # tenant-isolation-allow: user-scoped primary-membership check-before-create
        user=user, is_primary=True
    ).exists()
    membership, created = SchoolMembership.objects.get_or_create(
        user=user,
        school=school,
        defaults={"role": role, "is_primary": not has_primary},
    )
    if created or not update_role or getattr(membership, "is_school_owner", False):
        return
    if membership.role != role:
        membership.role = role
        membership.save(update_fields=["role"])


def promote_guardian_directory_link(
    *,
    student,
    name: str,
    phone: str = "",
    email: str = "",
    school=None,
    dry_run: bool = False,
) -> Any:
    """Create (or reuse) a PARENT user + ``StudentGuardian`` for one student.

    Returns the ``StudentGuardian`` row, or ``None`` when there is nothing to
    promote / dry-run / the student already has a matching link. Never raises.
    """
    name = (name or "").strip()
    phone = (phone or "").strip()
    email = (email or "").strip()
    school = school or getattr(student, "school", None)
    if student is None or not (name or phone or email):
        return None
    if dry_run:
        return None
    try:
        from apps.people.models import StudentGuardian
    except Exception:  # noqa: BLE001 — people app optional in some test shards
        return None

    existing = _existing_matching_link(student, name=name, phone=phone, email=email)
    if existing is not None:
        return existing

    first_name, last_name = _split_parent_name(name, student)
    deliverable = email if is_deliverable_email(email) else ""
    provision_email = deliverable or _directory_email(
        school=school,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        student_pk=getattr(student, "pk", None),
    )
    User = get_user_model()
    try:
        from apps.migration_cloud.landers.guardian_lander import _resolve_or_provision_user

        guardian_user, reason = _resolve_or_provision_user(
            User=User,
            user_ref="",
            email=provision_email,
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            school=school,
            dry_run=False,
        )
    except Exception:  # noqa: BLE001 — directory promote must never fail the student land
        logger.warning(
            "guardian_directory.provision_failed student_id=%s",
            getattr(student, "pk", None),
            exc_info=True,
        )
        return None
    if guardian_user is None:
        logger.info(
            "guardian_directory.skipped student_id=%s reason=%s",
            getattr(student, "pk", None),
            reason or "no_user",
        )
        return None

    parent_role = User.Role.PARENT
    if hasattr(guardian_user, "role") and not getattr(guardian_user, "role", None):
        guardian_user.role = parent_role
        try:
            guardian_user.save(update_fields=["role"])
        except Exception:  # noqa: BLE001
            pass
    ensure_school_membership(user=guardian_user, school=school, role=parent_role)

    model_fields = {f.name for f in StudentGuardian._meta.get_fields()}
    defaults = {
        "phone": phone,
        "email": deliverable,
        "relationship": StudentGuardian.Relationship.GUARDIAN,
        "preferred_contact": (
            StudentGuardian.PreferredContact.SMS
            if phone and not deliverable
            else StudentGuardian.PreferredContact.EMAIL
        ),
    }
    defaults = {
        k: v
        for k, v in defaults.items()
        if k in model_fields and v not in (None, "")
    }
    try:
        link, _created = StudentGuardian.objects.get_or_create(
            student=student,
            guardian_user=guardian_user,
            defaults=defaults,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "guardian_directory.link_failed student_id=%s",
            getattr(student, "pk", None),
            exc_info=True,
        )
        return None
    return link


def promote_unlinked_guardian_hints(*, school, dry_run: bool = False) -> dict[str, int]:
    """Post-apply sweep: DFV ``parent_name`` hints with no ``StudentGuardian`` yet."""
    summary = {"promoted": 0, "skipped": 0, "examined": 0, "would_promote": 0}
    if school is None:
        return summary
    try:
        from apps.metadata.models import DynamicFieldValue
        from apps.people.models import StudentGuardian, StudentProfile
    except Exception:  # noqa: BLE001
        return summary

    hint_rows = list(
        DynamicFieldValue.objects.filter(  # tenant-isolation-allow: school-scoped DFV parent hints for directory promote
            school=school,
            entity_type="student",
            field_key__in=("parent_name", "parent_phone"),
        )[: _PROMOTE_CAP * 2]
    )
    by_student: dict[str, dict[str, str]] = {}
    for row in hint_rows:
        payload = row.value_json if isinstance(row.value_json, dict) else {}
        value = payload.get("v")
        if value in (None, ""):
            continue
        bucket = by_student.setdefault(str(row.entity_id), {})
        if row.field_key == "parent_name":
            bucket["name"] = str(value)
        elif row.field_key == "parent_phone":
            bucket["phone"] = str(value)

    linked_ids = {
        str(pk)
        for pk in StudentGuardian.objects.filter(  # tenant-isolation-allow: school-scoped existing guardian links
            student__school=school
        ).values_list("student_id", flat=True)
    }
    for entity_id, contact in by_student.items():
        summary["examined"] += 1
        if entity_id in linked_ids:
            summary["skipped"] += 1
            continue
        student = StudentProfile.objects.filter(  # tenant-isolation-allow: school-scoped student lookup by DFV entity_id
            school=school, pk=entity_id
        ).first()
        if student is None:
            summary["skipped"] += 1
            continue
        if not (contact.get("name") or "").strip():
            summary["skipped"] += 1
            continue
        if dry_run:
            summary["would_promote"] += 1
            continue
        phone = (contact.get("phone") or "").strip() or (
            getattr(student, "parent_phone", "") or ""
        ).strip()
        link = promote_guardian_directory_link(
            student=student,
            name=contact.get("name") or "",
            phone=phone,
            school=school,
        )
        if link is None:
            summary["skipped"] += 1
        else:
            summary["promoted"] += 1
    return summary


def _directory_email(*, school, first_name: str, last_name: str, phone: str, student_pk) -> str:
    """Idempotent undeliverable mailbox: same parent+phone → same address."""
    school_pk = getattr(school, "pk", "") or ""
    if phone:
        seed = f"{school_pk}|{phone.strip().lower()}|{first_name.casefold()}|{last_name.casefold()}"
    else:
        seed = f"{school_pk}|{student_pk}|{first_name.casefold()}|{last_name.casefold()}"
    return synthetic_unclaimed_email(seed)


def _split_parent_name(name: str, student) -> tuple[str, str]:
    text = (name or "").strip()
    if not text:
        first = (getattr(student, "first_name", "") or "Parent").strip() or "Parent"
        last = (getattr(student, "last_name", "") or "").strip()
        return "Parent of", f"{first} {last}".strip()
    parts = text.split()
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], " ".join(parts[1:])


def _existing_matching_link(student, *, name: str, phone: str, email: str):
    from apps.people.models import StudentGuardian

    links = StudentGuardian.objects.filter(  # tenant-isolation-allow: student-pk-scoped guardian links
        student=student, is_active=True
    ).select_related("guardian_user")
    name_cf = (name or "").casefold()
    email_cf = (email or "").strip().lower()
    for link in links:
        if phone and (link.phone or "") == phone:
            return link
        if email_cf and is_deliverable_email(email_cf) and (
            (link.email or "").strip().lower() == email_cf
            or (getattr(link.guardian_user, "email", "") or "").strip().lower() == email_cf
        ):
            return link
        user = link.guardian_user
        if not name_cf or user is None:
            continue
        full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip().casefold()
        if full and (full == name_cf or name_cf in full or full in name_cf):
            return link
    return None
