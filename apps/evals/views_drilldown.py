"""Pass 9.E: evaluation drill-down view.

Closes the audit-log roadmap gap "evaluation drill-down once the canonical
detail view lands". Renders one Evaluation row plus its full GradeAudit
trail. Operator-only (teachers can see their own students' rows; admins
see all). Decorated with @audit_pii_view so reads land in the audit log
beside the writes captured by GradeAudit.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.accounts.models import User
from apps.compliance.decorators import audit_pii_view
from apps.evals.models import Evaluation


def _can_view_evaluation(user, evaluation: Evaluation) -> bool:
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser or user.is_staff:
        return True
    role = (getattr(user, "role", "") or "").upper()
    admin_roles = {
        "ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
        "DEAN",
        "CENSOR",
    }
    if role in admin_roles:
        return True
    # Additive granular-RBAC: anyone granted grades.enter / grades.manage (e.g. a
    # registrar/HOD custom role) may view this evaluation drill-down.
    try:
        _school = getattr(evaluation, "school", None)
        if user.has_feature_permission(
            "grades.enter", school=_school
        ) or user.has_feature_permission("grades.manage", school=_school):
            return True
    except (AttributeError, TypeError, ValueError):
        pass
    if role == User.Role.TEACHER:
        teacher_profile = getattr(user, "teacher_profile", None)
        return bool(teacher_profile and evaluation.teacher_id == teacher_profile.id)
    return False


@login_required
@require_GET
@audit_pii_view(
    model_name="Evaluation",
    object_id_kwarg="pk",
    sensitivity="HIGH",
    reason="Evaluation drill-down (grade detail + audit trail)",
)
def evaluation_drilldown(request, pk: int):
    """One Evaluation + its full GradeAudit trail."""
    school = getattr(request, "school", None)
    qs = Evaluation.objects.select_related(
        "student", "student__user", "teacher", "teacher__user",
        "subject_assignment", "subject_assignment__subject",
        "subject_assignment__classroom", "academic_year", "term",
    )
    if school is not None:
        qs = qs.filter(school=school)
    evaluation = get_object_or_404(qs, pk=pk)

    if not _can_view_evaluation(request.user, evaluation):
        return HttpResponseForbidden(
            "You are not authorized to view this evaluation."
        )

    audit_trail = (
        evaluation.audit_trail.select_related("changed_by")
        .order_by("-changed_at")[:200]
    )

    return render(
        request,
        "evals/evaluation_drilldown.html",
        {
            "evaluation": evaluation,
            "audit_trail": audit_trail,
        },
    )
