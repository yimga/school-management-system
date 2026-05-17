"""
Degree audit: compute progress and eligibility from credits, requirements_json, and optional milestones.
Phase 3-4 (global platform). Uses Subject.credits and evals/grades; TransferCredit; GraduateMilestone when present.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from apps.metadata.services import get_dynamic_field_value
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from django.db import DatabaseError
from django.db.models import ObjectDoesNotExist, Sum

from .models import GraduateMilestone, StudentDegreeEnrollment, TransferCredit
from .services import get_approved_transfer_equivalency_map


def _normalize_course_code(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _normalize_code_list(values: Iterable[Any] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        code = _normalize_course_code(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def _normalize_code_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[str]] = {}
    for raw_key, raw_values in value.items():
        key = _normalize_course_code(raw_key)
        if not key:
            continue
        if isinstance(raw_values, (list, tuple, set)):
            out[key] = _normalize_code_list(raw_values)
        elif raw_values is None:
            out[key] = []
        else:
            out[key] = _normalize_code_list([raw_values])
    return out


def _to_decimal(value: Any, default: Decimal) -> Decimal:
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _default_min_credits(level: str) -> Decimal:
    defaults = {
        "ASC": Decimal("60"),
        "BSC": Decimal("120"),
        "MSC": Decimal("36"),
        "PHD": Decimal("84"),
    }
    return defaults.get((level or "").upper(), Decimal("120"))


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _month_delta(start_date, end_date) -> int:
    if not start_date or not end_date:
        return 0
    months = (end_date.year - start_date.year) * 12 + (
        end_date.month - start_date.month
    )
    if end_date.day < start_date.day:
        months -= 1
    return months


def run_degree_audit(enrollment: StudentDegreeEnrollment) -> dict[str, Any]:
    """
    Compute is_eligible, progress_percent, missing_courses, and missing_milestones.

    requirements_json supports:
    - min_credits, pass_threshold, min_gpa
    - required_course_codes (list[str])
    - waived_course_codes (list[str])
    - course_equivalencies ({required_code: [equivalent_code, ...]})
    - prerequisite_graph / prerequisites ({course_code: [prereq_code, ...]})
    - corequisite_graph / corequisites ({course_code: [coreq_code, ...]})
    - milestones_required (list[str])
    - milestone_rules ({milestone_type: {committee_min_members, external_member_min, require_committee_chair, require_embargo, max_embargo_months}})
    """
    student = enrollment.student
    program = enrollment.program
    req = program.requirements_json or {}

    pass_threshold = _to_decimal(req.get("pass_threshold"), Decimal("0"))
    earned_credits = Decimal("0.00")
    completed_course_codes = set(
        _normalize_code_list(req.get("completed_course_codes"))
    )
    credited_subject_ids: set[Any] = set()

    # Credits + completed courses from passed evaluations (deduped by subject).
    try:
        from apps.evals.models import Evaluation

        evals = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            Evaluation.objects.filter(
                student=student,
                subject_assignment__subject__credits__isnull=False,
            )
            .exclude(final_score__isnull=True)
            .select_related("subject_assignment__subject")
        )
        for ev in evals:
            score = _to_decimal(ev.final_score, Decimal("-1"))
            if score < pass_threshold:
                continue

            subject = ev.subject_assignment.subject
            completed_code = _normalize_course_code(getattr(subject, "name", ""))
            if completed_code:
                completed_course_codes.add(completed_code)

            subject_id = getattr(subject, "pk", None)
            if subject_id in credited_subject_ids:
                continue
            credited_subject_ids.add(subject_id)
            earned_credits += _to_decimal(
                getattr(subject, "credits", None), Decimal("0.00")
            )
    except (
        ImportError,
        AttributeError,
        TypeError,
        ValueError,
        ObjectDoesNotExist,
        DatabaseError,
    ) as e:
        # Keep degree audit resilient if eval subsystem is unavailable.
        logging.getLogger(__name__).debug("Degree audit eval credits skipped: %s", e)

    transfer_qs = TransferCredit.objects.filter(
        student=student, approved_at__isnull=False
    )
    for transfer_credit in transfer_qs.only("course_code"):
        code = _normalize_course_code(transfer_credit.course_code)
        if code:
            completed_course_codes.add(code)

    transfer_credits = _to_decimal(
        transfer_qs.aggregate(s=Sum("credits")).get("s"), Decimal("0.00")
    )
    total_earned = earned_credits + transfer_credits

    min_credits = _to_decimal(
        req.get("min_credits"), _default_min_credits(program.level)
    )
    required_codes = _normalize_code_list(req.get("required_course_codes"))
    waived_codes = set(_normalize_code_list(req.get("waived_course_codes")))
    equivalencies = _normalize_code_map(req.get("course_equivalencies"))
    approved_equivalencies = get_approved_transfer_equivalency_map(
        student=student, program=program
    )
    for internal_code, external_codes in approved_equivalencies.items():
        existing = equivalencies.setdefault(internal_code, [])
        for external_code in external_codes:
            if external_code not in existing:
                existing.append(external_code)
    prerequisite_graph = _normalize_code_map(
        req.get("prerequisite_graph") or req.get("prerequisites")
    )
    corequisite_graph = _normalize_code_map(
        req.get("corequisite_graph") or req.get("corequisites")
    )

    def is_course_satisfied(code: str) -> bool:
        normalized = _normalize_course_code(code)
        if not normalized:
            return False
        if normalized in waived_codes:
            return True
        if normalized in completed_course_codes:
            return True
        for equivalent in equivalencies.get(normalized, []):
            if equivalent in waived_codes or equivalent in completed_course_codes:
                return True
        return False

    missing_courses = [code for code in required_codes if not is_course_satisfied(code)]

    missing_prerequisites: dict[str, list[str]] = defaultdict(list)
    for course_code, prereqs in prerequisite_graph.items():
        if course_code in waived_codes:
            continue
        if not is_course_satisfied(course_code):
            continue
        for prereq in prereqs:
            if not is_course_satisfied(prereq):
                missing_prerequisites[course_code].append(prereq)

    missing_corequisites: dict[str, list[str]] = defaultdict(list)
    for course_code, coreqs in corequisite_graph.items():
        if course_code in waived_codes:
            continue
        if not is_course_satisfied(course_code):
            continue
        for coreq in coreqs:
            if not is_course_satisfied(coreq):
                missing_corequisites[course_code].append(coreq)

    milestone_rules = req.get("milestone_rules") or {}
    if not isinstance(milestone_rules, dict):
        milestone_rules = {}
    missing_milestones: list[str] = []
    milestone_rule_violations: dict[str, list[str]] = {}
    for raw_mtype in req.get("milestones_required") or []:
        mtype = _normalize_course_code(raw_mtype)
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        milestone = (
            GraduateMilestone.objects.filter(
                student=student,
                type=mtype,
                status="COMPLETED",
                is_signed_off=True,
            )
            .order_by("-completion_date", "-updated_at", "-id")
            .first()
        )
        if not milestone:
            missing_milestones.append(mtype)
            continue

        rules = milestone_rules.get(mtype) or {}
        if not isinstance(rules, dict):
            continue
        violations: list[str] = []

        min_members = _to_int(rules.get("committee_min_members"), 0)
        if min_members > 0 and int(milestone.committee_member_count or 0) < min_members:
            violations.append(f"committee_member_count<{min_members}")

        external_min = _to_int(rules.get("external_member_min"), 0)
        if (
            external_min > 0
            and int(milestone.external_member_count or 0) < external_min
        ):
            violations.append(f"external_member_count<{external_min}")

        require_chair = bool(rules.get("require_committee_chair", mtype == "DEFENSE"))
        if require_chair and not milestone.committee_chair_id:
            violations.append("committee_chair_missing")

        require_embargo = bool(rules.get("require_embargo", False))
        if require_embargo and not milestone.embargo_until:
            violations.append("embargo_missing")

        max_embargo_months = _to_int(rules.get("max_embargo_months"), 0)
        if (
            max_embargo_months > 0
            and milestone.embargo_until
            and milestone.completion_date
        ):
            months = _month_delta(milestone.completion_date, milestone.embargo_until)
            if months < 0 or months > max_embargo_months:
                violations.append(f"embargo_exceeds_{max_embargo_months}_months")

        if violations:
            milestone_rule_violations[mtype] = violations

    min_gpa = req.get("min_gpa")
    gpa_ok = True
    if min_gpa is not None:
        try:
            gpa = float(
                get_dynamic_field_value(
                    student, "gpa", default=getattr(student, "gpa", None)
                )
                or 0
            )
            gpa_ok = gpa >= float(min_gpa)
        except (TypeError, ValueError):
            gpa_ok = False

    progress = (float(total_earned) / float(min_credits) * 100) if min_credits else 0
    progress = min(100, progress)

    is_eligible = (
        total_earned >= min_credits
        and len(missing_courses) == 0
        and len(missing_milestones) == 0
        and len(missing_prerequisites) == 0
        and len(missing_corequisites) == 0
        and len(milestone_rule_violations) == 0
        and gpa_ok
    )

    return {
        "is_eligible": is_eligible,
        "progress_percent": round(progress, 1),
        "earned_credits": total_earned,
        "transfer_credits": transfer_credits,
        "min_credits": min_credits,
        "completed_course_codes": sorted(completed_course_codes),
        "waived_course_codes": sorted(waived_codes),
        "missing_courses": missing_courses,
        "missing_prerequisites": dict(missing_prerequisites),
        "missing_corequisites": dict(missing_corequisites),
        "missing_milestones": missing_milestones,
        "milestone_rule_violations": milestone_rule_violations,
        "gpa_ok": gpa_ok,
    }
