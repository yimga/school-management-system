"""
Badge creation/revocation triggered by events (syllabus approval, delegation start/end).
"""

from django.utils import timezone
from django.core.signing import Signer


def _signer():
    return Signer(salt="badge.verify")


def _set_badge_qr_data(badge):
    """Set qr_data to signed payload 'badge:<pk>' for verification (Phase 2)."""
    if not badge.pk:
        return
    payload = f"badge:{badge.pk}"
    badge.qr_data = _signer().sign(payload)
    badge.save(update_fields=["qr_data"])


def get_signed_id_token(kind: str, pk: int) -> str:
    """Return signed token for digital ID verification (Phase 4). kind is 'staff' or 'student'."""
    return _signer().sign(f"{kind}:{pk}")


def create_teacher_badge_for_syllabus_approval(syllabus):
    """When a syllabus is approved, award a configurable badge to the teacher (e.g. Syllabus Master)."""
    from apps.people.models import BadgeType, Badge
    from apps.evals.models import TeacherAssignment

    ta = (
        TeacherAssignment.objects.filter(
            subject_assignment=syllabus.subject_assignment,
            is_active=True,
        )
        .select_related("teacher", "teacher__user")
        .first()
    )
    if not ta or not ta.teacher or not ta.teacher.user_id:
        return None
    badge_type, _ = BadgeType.objects.get_or_create(
        code="syllabus_master",
        defaults={
            "label": "Syllabus Master",
            "audience": BadgeType.Audience.STAFF,
            "criteria_rule": {"trigger": "syllabus_approved"},
        },
    )
    return Badge.objects.get_or_create(
        badge_type=badge_type,
        user=ta.teacher.user,
        defaults={
            "criteria_met": {
                "syllabus_id": syllabus.pk,
                "subject_assignment_id": syllabus.subject_assignment_id,
            },
        },
    )[0]


def create_acting_badge_for_delegation(delegation):
    """When delegation starts, create a temporary badge for the delegate (e.g. Acting Principal)."""
    from apps.people.models import BadgeType, Badge

    role_label = getattr(delegation.delegator, "role", "") or "Principal"
    badge_type, _ = BadgeType.objects.get_or_create(
        code="acting_role",
        defaults={
            "label": f"Acting {role_label}",
            "audience": BadgeType.Audience.STAFF,
            "criteria_rule": {"trigger": "delegation_start"},
        },
    )
    # Update label if existing
    if badge_type.label != f"Acting {role_label}":
        badge_type.label = f"Acting {role_label}"
        badge_type.save(update_fields=["label"])
    expiry = delegation.extended_end_date or delegation.end_date
    badge = Badge.objects.create(
        badge_type=badge_type,
        user=delegation.delegate,
        criteria_met={
            "delegation_id": delegation.pk,
            "acting_for": delegation.delegator_id,
        },
        expiry_at=expiry,
    )
    _set_badge_qr_data(badge)
    return badge


def revoke_acting_badges_for_delegation(delegation):
    """When delegation ends, set expiry on badges created for this delegation."""
    from apps.people.models import Badge

    now = timezone.now()
    Badge.objects.filter(
        user=delegation.delegate,
        criteria_met__delegation_id=delegation.pk,
        expiry_at__gt=now,
    ).update(expiry_at=now)


def create_staff_badge_for_onboarding(teacher_profile):
    """Phase 3: When a teacher profile is first created, award an 'Active Member' / 'Identity' staff badge."""
    from apps.people.models import BadgeType, Badge

    if not teacher_profile or not teacher_profile.user_id:
        return None
    badge_type, _ = BadgeType.objects.get_or_create(
        code="active_member",
        defaults={
            "label": "Active Member",
            "audience": BadgeType.Audience.STAFF,
            "criteria_rule": {"trigger": "onboarding"},
        },
    )
    badge, created = Badge.objects.get_or_create(
        badge_type=badge_type,
        user=teacher_profile.user,
        defaults={"criteria_met": {"teacher_profile_id": teacher_profile.pk}},
    )
    if created:
        _set_badge_qr_data(badge)
    return badge


def create_honor_roll_badge_for_student(student, academic_year, term, overall_average):
    """
    Phase 3: When a term report is published (or average computed), award Honor Roll badge
    if student's overall average meets threshold. Threshold from BadgeType.criteria_rule or default 16/20.
    One badge per student per term (get_or_create with criteria_met term_id).
    """
    from apps.people.models import BadgeType, Badge

    if not student or overall_average is None or not academic_year or not term:
        return None
    try:
        _threshold = float(
            overall_average
        )  # validation only; criteria use badge_type rule
    except (TypeError, ValueError):
        return None
    badge_type = BadgeType.objects.filter(
        code="honor_roll",
        audience=BadgeType.Audience.STUDENT,
        is_active=True,
    ).first()
    if not badge_type:
        badge_type = BadgeType.objects.create(
            code="honor_roll",
            label="Honor Roll",
            audience=BadgeType.Audience.STUDENT,
            criteria_rule={"trigger": "term_average", "threshold": 16.0},
        )
    threshold_val = (badge_type.criteria_rule or {}).get("threshold", 16.0)
    try:
        threshold_val = float(threshold_val)
    except (TypeError, ValueError):
        threshold_val = 16.0
    if overall_average < threshold_val:
        return None
    criteria_met = {
        "academic_year_id": academic_year.pk,
        "term_id": term.pk,
        "overall_average": overall_average,
    }
    existing = Badge.objects.filter(
        badge_type=badge_type,
        student=student,
        criteria_met__term_id=term.pk,
    ).first()
    if existing:
        return existing
    badge = Badge.objects.create(
        badge_type=badge_type,
        student=student,
        criteria_met=criteria_met,
    )
    _set_badge_qr_data(badge)
    return badge
