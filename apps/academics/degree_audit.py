"""
Degree audit: compute progress and eligibility from credits, requirements_json, and optional milestones.
Phase 3–4 (global platform). Uses Subject.credits and evals/grades; TransferCredit; GraduateMilestone when present.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Sum

from .models import (
    DegreeProgram,
    StudentDegreeEnrollment,
    TransferCredit,
    GraduateMilestone,
    Subject,
)
from apps.people.models import StudentProfile


def run_degree_audit(enrollment: StudentDegreeEnrollment) -> dict[str, Any]:
    """
    Compute is_eligible, progress_percent, missing_courses, missing_milestones.
    requirements_json can have: min_credits, required_course_codes, min_gpa, milestones_required (list of types).
    """
    student = enrollment.student
    program = enrollment.program
    req = program.requirements_json or {}

    earned_credits = Decimal("0.00")
    # Sum credits from Subject (evals/grades) — simplified: sum Subject.credits for subjects student has taken
    # In a full impl you would join evals/grades and sum credits for passed courses
    try:
        from apps.evals.models import Evaluation
        pass_threshold = req.get("pass_threshold", 0)
        evals = Evaluation.objects.filter(
            student=student,
            subject_assignment__subject__credits__isnull=False,
        ).exclude(final_score__isnull=True).select_related("subject_assignment__subject")
        for ev in evals:
            subj = ev.subject_assignment.subject
            if subj.credits and (ev.final_score or 0) >= pass_threshold:
                earned_credits += subj.credits
    except Exception:
        pass

    transfer = TransferCredit.objects.filter(student=student, approved_at__isnull=False).aggregate(
        s=Sum("credits")
    )
    transfer_credits = transfer["s"] or Decimal("0.00")
    if not isinstance(transfer_credits, Decimal):
        transfer_credits = Decimal(str(transfer_credits))
    total_earned = earned_credits + transfer_credits

    min_credits = req.get("min_credits")
    if min_credits is not None:
        min_credits = Decimal(str(min_credits))
    else:
        min_credits = Decimal("120")  # default bachelor

    required_codes = req.get("required_course_codes") or []
    missing_courses = []
    # Simplified: if you have a course completion model, check here
    for code in required_codes:
        missing_courses.append(code)

    missing_milestones = []
    milestones_required = req.get("milestones_required") or []
    for mtype in milestones_required:
        if not GraduateMilestone.objects.filter(
            student=student,
            type=mtype,
            status="COMPLETED",
            is_signed_off=True,
        ).exists():
            missing_milestones.append(mtype)

    min_gpa = req.get("min_gpa")
    gpa_ok = True
    if min_gpa is not None:
        try:
            gpa = float(student.custom_attributes.get("gpa") or 0)
            gpa_ok = gpa >= float(min_gpa)
        except (TypeError, ValueError):
            gpa_ok = False

    progress = (float(total_earned) / float(min_credits) * 100) if min_credits else 0
    progress = min(100, progress)

    is_eligible = (
        total_earned >= min_credits
        and len(missing_courses) == 0
        and len(missing_milestones) == 0
        and gpa_ok
    )

    return {
        "is_eligible": is_eligible,
        "progress_percent": round(progress, 1),
        "earned_credits": total_earned,
        "transfer_credits": transfer_credits,
        "min_credits": min_credits,
        "missing_courses": missing_courses,
        "missing_milestones": missing_milestones,
        "gpa_ok": gpa_ok,
    }
