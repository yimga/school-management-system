"""Wave O4 (2026-05-15): at-risk outcome labeling queue.

GET  /portal/at-risk/labeling/                 — queue of unlabeled students
                                                  + their RiskFactor scores
                                                  + labeling form per row
POST /portal/at-risk/labeling/                 — save / update a label

Permissioned to school admins / principals / proprietors. Other users
get 403.

The queue is intentionally simple: list students from the current school
with a RiskFactor score in the current academic year, group by band
(red/amber/green) descending, and let the operator select a label from
the AtRiskOutcomeLabel.Label TextChoices. Labels are stored against
(student, academic_year) — see migration 0020.

This view ships the **input side** of the labeling loop. The export side
(`export_at_risk_training_data` mgmt command) reads these labels and
emits CSV consumable by `train_at_risk.py --csv`.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def _user_can_label(request: HttpRequest) -> bool:
    user = request.user
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    role = (getattr(user, "role", "") or "").lower()
    return role in {"admin", "principal", "proprietor"}


def _active_academic_year(school):
    """Return the most-current AcademicYear for the school, or None."""
    from apps.academics.models import AcademicYear

    # tenant-isolation-allow: scoped via school= below
    return (
        AcademicYear.objects.filter(school=school, is_active=True)
        .order_by("-start_date")
        .first()
    )


def _queue_rows(school, academic_year, *, limit: int = 200):
    """Return [(student, risk_factor_or_None, existing_label_or_None), ...] for the queue."""
    from apps.analytics.models import AtRiskOutcomeLabel, RiskFactor
    from apps.people.models import StudentProfile

    # tenant-isolation-allow: scoped via school= below
    students = list(
        StudentProfile.objects.filter(school=school, is_active=True)
        .select_related("user")
        .order_by("user__last_name", "user__first_name")[:limit]
    )
    if not students:
        return []

    student_ids = [s.pk for s in students]

    # Latest RiskFactor per student — use a single query + group in Python.
    # tenant-isolation-allow: scoped via school=
    risk_rows = list(
        RiskFactor.objects.filter(school=school, student_id__in=student_ids)
        .order_by("student_id", "-computed_at")
    )
    latest_risk_by_student: dict[int, object] = {}
    for row in risk_rows:
        latest_risk_by_student.setdefault(row.student_id, row)

    existing_labels: dict[int, object] = {}
    if academic_year is not None:
        # tenant-isolation-allow: scoped via school= + academic_year FK
        for label in AtRiskOutcomeLabel.objects.filter(
            school=school, academic_year=academic_year, student_id__in=student_ids
        ):
            existing_labels[label.student_id] = label

    rows = []
    for student in students:
        rows.append((
            student,
            latest_risk_by_student.get(student.pk),
            existing_labels.get(student.pk),
        ))
    # Sort by score desc (None last), then by name asc — most-at-risk first.
    def _sort_key(row):
        _student, risk, _label = row
        score = float(risk.score) if risk is not None else -1.0
        return (-score, _student.user.last_name if _student.user else "")
    rows.sort(key=_sort_key)
    return rows


@login_required
@require_http_methods(["GET", "POST"])
def at_risk_labeling_queue(request: HttpRequest) -> HttpResponse:
    if not _user_can_label(request):
        return render(
            request, "portal/at_risk_labeling/forbidden.html", status=403
        )
    school = getattr(request, "school", None)
    if school is None:
        return render(
            request, "portal/at_risk_labeling/no_tenant.html", status=400
        )

    academic_year = _active_academic_year(school)
    if academic_year is None:
        return render(
            request,
            "portal/at_risk_labeling/no_academic_year.html",
            {"school": school},
            status=400,
        )

    if request.method == "POST":
        return _handle_post(request, school, academic_year)

    rows = _queue_rows(school, academic_year)
    from apps.analytics.models import AtRiskOutcomeLabel

    context = {
        "school": school,
        "academic_year": academic_year,
        "rows": rows,
        "label_choices": list(AtRiskOutcomeLabel.Label.choices),
        "labeled_count": sum(1 for _, _, lbl in rows if lbl is not None),
        "total_count": len(rows),
    }
    return render(request, "portal/at_risk_labeling/queue.html", context)


def _handle_post(request, school, academic_year):
    """Upsert one (student, academic_year) label per POST."""
    from apps.analytics.models import AtRiskOutcomeLabel
    from apps.people.models import StudentProfile

    student_id = request.POST.get("student_id", "").strip()
    label_value = request.POST.get("label", "").strip()
    notes = request.POST.get("notes", "").strip()

    if not student_id or not label_value:
        messages.error(request, "student_id and label are required")
        return HttpResponseRedirect(reverse("portal_at_risk_labeling"))

    valid_labels = {choice.value for choice in AtRiskOutcomeLabel.Label}
    if label_value not in valid_labels:
        messages.error(request, f"Unknown label: {label_value}")
        return HttpResponseRedirect(reverse("portal_at_risk_labeling"))

    # tenant-isolation-allow: scoped via school= below
    student = StudentProfile.objects.filter(school=school, pk=student_id).first()
    if student is None:
        messages.error(request, "student not found in this school")
        return HttpResponseRedirect(reverse("portal_at_risk_labeling"))

    AtRiskOutcomeLabel.objects.update_or_create(
        student=student,
        academic_year=academic_year,
        defaults={
            "school": school,
            "label": label_value,
            "labeled_by": request.user,
            "notes": notes,
        },
    )
    messages.success(
        request, f"Saved label for {student.user.get_full_name() if student.user else student.pk}"
    )
    return HttpResponseRedirect(reverse("portal_at_risk_labeling"))
