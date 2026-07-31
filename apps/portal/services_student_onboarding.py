"""student_self_onboarding wizard → create a ``StudentProfile`` (+ optional Student ``User``).

Date of birth is intentionally NOT available here — the wizard strips it before
delegating (only ``date_of_birth_hash`` is forwarded), so the profile is built
from non-sensitive fields and ``admission_number`` auto-generates on save.
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def create_student_from_wizard(*, school, wizard_payload, actor_user_id=None) -> dict:
    """Create a student profile (and a STUDENT user when an email is supplied).

    Returns a structured result dict. User + profile are created atomically.
    """
    from apps.accounts.models import User
    from apps.people.models import StudentProfile

    payload = wizard_payload or {}
    first = (payload.get("first_name") or "").strip()
    last = (payload.get("last_name") or "").strip()
    if school is None or not (first or last):
        return {"ok": False, "error": "missing_school_or_name"}

    # COPPA gate: a minor's account may only be created through a flow that
    # recorded a verifiable consent basis (school authorization / guardian
    # consent). Operator/school-mediated wizards stamp
    # ``coppa_consent_basis=school_authorization`` upstream; a basis-less minor
    # payload is refused rather than silently provisioning a child's account.
    if payload.get("is_minor"):
        from apps.compliance.childrens_privacy import (
            consent_basis_is_sufficient_for_minor,
        )

        if not consent_basis_is_sufficient_for_minor(payload.get("coppa_consent_basis")):
            logger.warning(
                "create_student_from_wizard blocked: minor without consent basis school=%s",
                getattr(school, "pk", None),
            )
            return {"ok": False, "error": "coppa_consent_required"}

    email = (payload.get("email") or "").strip().lower()

    try:
        with transaction.atomic():
            student_user = None
            if email and not User.objects.filter(email__iexact=email).exists():
                student_user = User.objects.create_user(
                    username=email,
                    email=email,
                    first_name=first,
                    last_name=last,
                    role=User.Role.STUDENT,
                )
            profile = StudentProfile.objects.create(
                first_name=first or "Student",
                last_name=last,
                school=school,
                status=StudentProfile.Status.NEW,
                is_active=True,
                user=student_user,
            )
    except Exception as exc:  # noqa: BLE001 — return structured failure, never silent
        logger.warning("create_student_from_wizard failed: %s", exc)
        return {"ok": False, "error": "create_failed"}

    logger.info(
        "create_student_from_wizard student=%s school=%s user=%s",
        profile.pk, getattr(school, "pk", None), getattr(student_user, "pk", None),
    )
    return {
        "ok": True,
        "student_profile_id": profile.pk,
        "admission_number": profile.admission_number,
        "user_id": getattr(student_user, "pk", None),
    }
