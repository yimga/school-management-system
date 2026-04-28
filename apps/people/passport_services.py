"""Tenant-safe passport + transcript vault services (North Star SLICE 13)."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from django.db import transaction

from apps.people.models import StudentPassport
from apps.people.student_passport_models import (
    StudentPassportMembership,
    TranscriptVaultItem,
)

if TYPE_CHECKING:
    from apps.accounts.models import User


def get_or_create_passport_for_student(student_profile, user: "User"):
    """Return ``(passport, created)`` scoped to student's school."""
    if student_profile is None or getattr(student_profile, "school_id", None) is None:
        raise ValueError("student_profile missing school.")
    school = student_profile.school
    existing = StudentPassportMembership.objects.filter(
        student_profile_id=student_profile.pk,
        school_id=school.pk,
    ).first()
    if existing:
        return existing.passport, False
    with transaction.atomic():
        passport = StudentPassport.objects.create()
        StudentPassportMembership.objects.create(
            passport=passport,
            school=school,
            student_profile=student_profile,
            consent_status=StudentPassportMembership.ConsentStatus.PRIVATE,
            role=getattr(user, "role", "")[:40],
        )
        return passport, True


def link_student_to_passport(passport: StudentPassport, student_profile, user: "User"):
    """Explicit link for second-school enrollment."""
    school = getattr(student_profile, "school", None)
    if school is None:
        raise ValueError("Enrollment missing school.")
    StudentPassportMembership.objects.get_or_create(
        passport=passport,
        school=school,
        student_profile=student_profile,
        defaults={
            "consent_status": StudentPassportMembership.ConsentStatus.PRIVATE,
            "role": getattr(user, "role", "")[:40],
        },
    )


def create_transcript_vault_item(student_profile, *, artifact_type: str, artifact_bytes: bytes | memoryview | None, user: "User"):
    """Persist vault row with SHA-256 hash when ``artifact_bytes`` supplied."""
    passport = get_or_create_passport_for_student(student_profile, user)[0]
    hv = ""
    if artifact_bytes:
        hv = hashlib.sha256(bytes(artifact_bytes)).hexdigest()
    school = student_profile.school
    ref = ""
    return TranscriptVaultItem.objects.create(
        passport=passport,
        issuing_school=school,
        student_profile=student_profile,
        artifact_type=(artifact_type or "").strip()[:64],
        artifact_ref=ref[:512],
        verification_hash=hv[:128],
        issued_at=None,
        access_status=TranscriptVaultItem.AccessStatus.SHARED_WITH_SCHOOL,
        created_by=user if getattr(user, "pk", None) else None,
    )


def user_can_view_passport(user: "User", passport: StudentPassport, school=None) -> bool:
    """Fail-closed membership check."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    qs = StudentPassportMembership.objects.filter(passport_id=passport.pk)
    if school is not None:
        qs = qs.filter(school_id=school.pk)
    school_ids = set(qs.values_list("school_id", flat=True))
    from apps.schools.models import SchoolMembership

    return SchoolMembership.objects.filter(user=user, school_id__in=school_ids).exists()


def list_visible_vault_items(user: "User", passport: StudentPassport, school=None):
    """Return queryset of items the user may read (membership + not revoked)."""
    if not user_can_view_passport(user, passport, school=school):
        return TranscriptVaultItem.objects.none()
    qs = TranscriptVaultItem.objects.filter(passport_id=passport.pk)
    if school is not None:
        qs = qs.filter(issuing_school_id=school.pk)
    revoked_schools = StudentPassportMembership.objects.filter(
        passport_id=passport.pk,
        consent_status=StudentPassportMembership.ConsentStatus.REVOKED,
    ).values_list("school_id", flat=True)
    return (
        qs.exclude(access_status=TranscriptVaultItem.AccessStatus.REVOKED)
        .exclude(issuing_school_id__in=revoked_schools)
        .select_related("issuing_school", "student_profile")
    )
