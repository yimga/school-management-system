"""
Badge creation/revocation triggered by events (syllabus approval, delegation start/end).
"""
from django.utils import timezone


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
            "criteria_met": {"syllabus_id": syllabus.pk, "subject_assignment_id": syllabus.subject_assignment_id},
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
    return Badge.objects.create(
        badge_type=badge_type,
        user=delegation.delegate,
        criteria_met={"delegation_id": delegation.pk, "acting_for": delegation.delegator_id},
        expiry_at=expiry,
    )


def revoke_acting_badges_for_delegation(delegation):
    """When delegation ends, set expiry on badges created for this delegation."""
    from apps.people.models import Badge

    now = timezone.now()
    Badge.objects.filter(
        user=delegation.delegate,
        criteria_met__delegation_id=delegation.pk,
        expiry_at__gt=now,
    ).update(expiry_at=now)
