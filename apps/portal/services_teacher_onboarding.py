"""teacher_self_onboarding wizard → create a Teacher ``User`` + ``TeacherProfile``.

Callable mirror of the canonical creation in ``apps.portal.views_onboarding``:
email-uniqueness guard + atomic User+profile create + role TEACHER. The password
is left unusable so the teacher activates via the standard invite/reset link.
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

# Optional TeacherProfile fields the wizard may collect (only set when present).
_TEACHER_PROFILE_FIELDS = ("phone", "staff_id", "position_title")


def create_teacher_from_wizard(*, school, wizard_payload, actor_user_id=None) -> dict:
    """Create a teacher account from self-onboarding wizard answers.

    Returns a structured result dict. Refuses on missing email or a duplicate
    email (base ``User.email`` is not DB-unique; ``username`` is). User + profile
    are created atomically so a profile failure rolls back the user.
    """
    from apps.accounts.models import User
    from apps.people.models import TeacherProfile

    payload = wizard_payload or {}
    email = (payload.get("email") or "").strip().lower()
    if school is None or not email:
        return {"ok": False, "error": "missing_school_or_email"}

    if User.objects.filter(email__iexact=email).exists():
        logger.info("create_teacher_from_wizard: email already exists")
        return {"ok": False, "error": "email_exists"}

    first = (payload.get("first_name") or "").strip()
    last = (payload.get("last_name") or "").strip()
    profile_kwargs = {
        k: str(payload.get(k)) for k in _TEACHER_PROFILE_FIELDS if payload.get(k)
    }

    try:
        with transaction.atomic():
            # No password -> create_user marks it unusable (activation via reset link).
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=first,
                last_name=last,
                role=User.Role.TEACHER,
            )
            profile = TeacherProfile.objects.create(
                user=user, school=school, **profile_kwargs
            )
    except Exception as exc:  # noqa: BLE001 — return structured failure, never silent
        logger.warning("create_teacher_from_wizard failed: %s", exc)
        return {"ok": False, "error": "create_failed"}

    logger.info(
        "create_teacher_from_wizard user=%s school=%s",
        user.pk, getattr(school, "pk", None),
    )
    return {"ok": True, "user_id": user.pk, "teacher_profile_id": profile.pk}
