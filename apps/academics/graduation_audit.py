"""Graduation-requirements audit (W22 / M29 EOY lifecycle).

Year-end rollover can mark a student a graduate (``RolloverProposalItem.is_graduate``)
and the apply path then closes their enrollment, flips ``StudentProfile.status`` to
ALUMNI and drops them from the active roll — irreversibly, in one pass. Until now
that decision was a *bare manual checkbox*: nothing verified the student had
actually met any graduation requirement.

This module is the requirements engine that gate reads. It has two branches:

* **Higher-ed** — when the student has a resolvable ``StudentDegreeEnrollment``
  it DELEGATES to :func:`apps.academics.degree_audit.run_degree_audit` (a full
  credits / required-courses / prerequisites / milestones / GPA engine that until
  now was ORPHANED — called only by its own tests). The presence of a degree
  enrollment linked to a ``DegreeProgram`` is itself the opt-in for that gating.

* **K-12** — a settings-driven check against
  ``School.settings["graduation_requirements"]`` (a migration-free JSON blob, the
  same pattern as ``School.settings["onboarding_waivers"]``). The three optional
  requirements are ``min_annual_average``, ``required_subject_codes`` and
  ``min_subjects_passed``. Nothing is hardcoded — every threshold comes from that
  config, and the per-year average / per-subject averages are computed by REUSING
  the canonical report-path helpers (``_annual_average_for_student`` /
  ``_annual_subject_averages``), never re-derived here.

Behaviour-preserving contract: when a K-12 school has NOT configured any
requirement the audit returns ``requirements_configured=False`` and
``is_eligible=True`` — so the gate does not bite and today's behaviour is
unchanged. The gate only bites once a school opts in by configuring requirements
(or by running higher-ed degree programs).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import DatabaseError

logger = logging.getLogger(__name__)

# ``School.settings`` JSON key holding the K-12 requirements (migration-free —
# ``settings`` is a JSONField, mirroring ``onboarding_waivers``).
_SETTINGS_KEY = "graduation_requirements"

# Query-time exceptions the reuse helpers / reverse-relation reads may raise; the
# audit degrades to "cannot verify" rather than 500-ing the rollover.
_AUDIT_SOFT_ERRORS: tuple[type[BaseException], ...] = (
    DatabaseError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
)


@dataclass
class GraduationAuditResult:
    """Outcome of a single student's graduation-eligibility audit.

    ``source`` is one of ``"degree-audit"`` (delegated to the higher-ed engine),
    ``"k12-settings"`` (tenant settings requirements evaluated) or
    ``"no-requirements"`` (no requirement configured — behaviour-preserving pass).
    """

    is_eligible: bool = True
    requirements_configured: bool = False
    annual_average: Optional[Decimal] = None
    min_annual_average: Optional[Decimal] = None
    subjects_passed: int = 0
    min_subjects_passed: Optional[int] = None
    required_subject_codes: list = field(default_factory=list)
    missing_required_subjects: list = field(default_factory=list)
    source: str = "no-requirements"
    reasons: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Coercion / normalization helpers (subject codes are normalized IDENTICALLY to
# how degree_audit normalizes course codes, so the K-12 "passed" set — derived
# from Subject.name — matches configured required_subject_codes).
# --------------------------------------------------------------------------- #
def _normalize_code(value) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _normalize_code_list(values) -> list[str]:
    if not values or not isinstance(values, (list, tuple, set)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        code = _normalize_code(raw)
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _to_decimal(value, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _to_int_or_none(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Requirements resolution
# --------------------------------------------------------------------------- #
def resolve_graduation_requirements(school) -> dict:
    """Read the tenant's K-12 graduation requirements from ``School.settings``.

    Returns a typed dict with ``configured`` (True when at least one requirement
    is set), ``min_annual_average`` (Decimal|None), ``required_subject_codes``
    (normalized list[str]) and ``min_subjects_passed`` (int|None). Absent/empty
    config → ``configured=False`` so the gate stays inert (behaviour-preserving).
    """
    blob = getattr(school, "settings", None) or {}
    raw = blob.get(_SETTINGS_KEY) if isinstance(blob, dict) else None
    if not isinstance(raw, dict):
        raw = {}
    min_avg = _to_decimal(raw.get("min_annual_average"))
    required = _normalize_code_list(raw.get("required_subject_codes"))
    min_passed = _to_int_or_none(raw.get("min_subjects_passed"))
    configured = (min_avg is not None) or bool(required) or (min_passed is not None)
    return {
        "configured": configured,
        "min_annual_average": min_avg,
        "required_subject_codes": required,
        "min_subjects_passed": min_passed,
    }


# --------------------------------------------------------------------------- #
# Higher-ed delegation
# --------------------------------------------------------------------------- #
def _resolve_degree_enrollment(student):
    """The student's active (else most-recent) degree enrollment, or None.

    Reverse-relation read scoped by the ``student`` object (itself school-scoped);
    prefers an active enrollment, newest ``start_date`` first (the model's own
    default ordering).
    """
    if student is None or getattr(student, "degree_enrollments", None) is None:
        return None
    try:
        active = (
            student.degree_enrollments.filter(is_active=True)  # tenant-isolation-allow: reverse-relation-scoped-by-parent-student-object
            .select_related("program")
            .order_by("-start_date", "-created_at")
            .first()
        )
        if active is not None:
            return active
        return (
            student.degree_enrollments.select_related("program")  # tenant-isolation-allow: reverse-relation-scoped-by-parent-student-object
            .order_by("-start_date", "-created_at")
            .first()
        )
    except _AUDIT_SOFT_ERRORS as exc:
        logger.debug("graduation_audit degree-enrollment resolve failed: %s", exc)
        return None


def _audit_via_degree(enrollment) -> GraduationAuditResult:
    """Delegate to the (previously orphaned) degree-audit engine and normalize."""
    from .degree_audit import run_degree_audit

    d = run_degree_audit(enrollment)
    reasons: list[str] = []

    missing_courses = list(d.get("missing_courses") or [])
    if missing_courses:
        reasons.append("missing required course(s): " + ", ".join(missing_courses))
    missing_prereq = d.get("missing_prerequisites") or {}
    if missing_prereq:
        reasons.append("unmet prerequisite(s): " + ", ".join(sorted(missing_prereq)))
    missing_coreq = d.get("missing_corequisites") or {}
    if missing_coreq:
        reasons.append("unmet corequisite(s): " + ", ".join(sorted(missing_coreq)))
    missing_milestones = list(d.get("missing_milestones") or [])
    if missing_milestones:
        reasons.append(
            "outstanding milestone(s): " + ", ".join(missing_milestones)
        )
    violations = d.get("milestone_rule_violations") or {}
    if violations:
        reasons.append(
            "milestone rule violation(s): " + ", ".join(sorted(violations))
        )
    if not d.get("gpa_ok", True):
        reasons.append("GPA below program minimum")
    earned = _to_decimal(d.get("earned_credits"))
    min_credits = _to_decimal(d.get("min_credits"))
    if earned is not None and min_credits is not None and earned < min_credits:
        reasons.append(f"credits earned {earned} of {min_credits} required")

    is_eligible = bool(d.get("is_eligible"))
    if is_eligible and not reasons:
        reasons.append("all degree requirements met")

    return GraduationAuditResult(
        is_eligible=is_eligible,
        requirements_configured=True,
        annual_average=None,
        min_annual_average=None,
        subjects_passed=len(d.get("completed_course_codes") or []),
        min_subjects_passed=None,
        required_subject_codes=[],
        missing_required_subjects=missing_courses,
        source="degree-audit",
        reasons=reasons,
    )


# --------------------------------------------------------------------------- #
# K-12 settings audit (reuses canonical report-path computations)
# --------------------------------------------------------------------------- #
def _compute_annual_average(student, academic_year) -> Optional[Decimal]:
    """Per-year average via the SAME helper the promotion/transcript path uses."""
    if student is None or academic_year is None:
        return None
    classroom = getattr(student, "classroom", None)
    if classroom is None:
        return None
    try:
        from apps.reports.services import (
            _annual_average_for_student,
            terms_for_student,
        )

        terms = terms_for_student(academic_year, classroom)
        if not terms:
            return None
        avg = _annual_average_for_student(student, terms)
    except _AUDIT_SOFT_ERRORS as exc:
        logger.debug("graduation_audit annual-average failed: %s", exc)
        return None
    return _to_decimal(avg) if avg is not None else None


def _resolve_subject_pass_threshold(school) -> Decimal:
    """The pass mark on the school's OPERATIONAL grading scale (no magic number).

    1. An explicit tenant ``GradingScale.config["pass_threshold"]`` (the admin /
       wizard choice) — already expressed on the operational scale.
    2. Else half the school's operational ``score_scale`` — the platform's own
       pass-mark convention (``pass_mark = score_scale // 2``: 10 on /20, 50 on
       /100). The scale MAX itself comes from tenant config, so nothing is
       hardcoded; only the "pass = half the scale" convention is applied.
    """
    try:
        from apps.evals.grading_scale_service import (
            get_effective_grading_scale_for_school,
        )

        scale = get_effective_grading_scale_for_school(school)
        cfg = getattr(scale, "config", None) if scale is not None else None
        if isinstance(cfg, dict) and cfg.get("pass_threshold") is not None:
            explicit = _to_decimal(cfg["pass_threshold"])
            if explicit is not None:
                return explicit
    except (ImportError,) + _AUDIT_SOFT_ERRORS as exc:
        logger.debug("graduation_audit explicit pass-threshold lookup failed: %s", exc)

    try:
        from apps.evals.grading_provisioning import resolve_school_score_scale

        score_scale = _to_decimal(
            resolve_school_score_scale(school, default=Decimal("20"))
        )
        if score_scale is not None and score_scale > 0:
            return score_scale / Decimal("2")
    except (ImportError,) + _AUDIT_SOFT_ERRORS as exc:
        logger.debug("graduation_audit derived pass-threshold failed: %s", exc)

    # Unresolvable → 0 degrades OPEN (any recorded subject counts as passed)
    # rather than falsely blocking graduation on a config-resolution gap.
    return Decimal("0")


def _compute_passed_subjects(student, academic_year, school):
    """(set_of_passed_subject_codes, count) using canonical per-subject averages.

    Reuses ``_annual_subject_averages`` (the report path's per-subject annual
    average) and marks a subject passed when its average meets the school's own
    pass mark. Subject codes are ``Subject.name`` normalized the SAME way the
    configured ``required_subject_codes`` are, so the two sets are comparable.
    """
    passed: set[str] = set()
    count = 0
    if student is None or academic_year is None:
        return passed, count
    try:
        from apps.reports.services import _annual_subject_averages

        rows = _annual_subject_averages(student, academic_year)
        threshold = _resolve_subject_pass_threshold(school)
        for subject, _category, avg in rows:
            avg_dec = _to_decimal(avg)
            if avg_dec is not None and avg_dec >= threshold:
                count += 1
                code = _normalize_code(getattr(subject, "name", ""))
                if code:
                    passed.add(code)
    except _AUDIT_SOFT_ERRORS as exc:
        logger.debug("graduation_audit passed-subjects failed: %s", exc)
    return passed, count


def _audit_via_settings(student, academic_year, school, reqs) -> GraduationAuditResult:
    min_avg: Optional[Decimal] = reqs["min_annual_average"]
    required_codes: list = reqs["required_subject_codes"]
    min_passed: Optional[int] = reqs["min_subjects_passed"]

    annual_avg = _compute_annual_average(student, academic_year)
    passed_codes, subjects_passed = _compute_passed_subjects(
        student, academic_year, school
    )

    reasons: list[str] = []
    is_eligible = True

    if min_avg is not None:
        if annual_avg is None:
            is_eligible = False
            reasons.append(f"no annual average on record (need >= {min_avg})")
        elif annual_avg < min_avg:
            is_eligible = False
            reasons.append(f"annual average {annual_avg} below required {min_avg}")

    missing_required = [c for c in required_codes if c not in passed_codes]
    if required_codes and missing_required:
        is_eligible = False
        reasons.append(
            "missing required subject(s): " + ", ".join(missing_required)
        )

    if min_passed is not None and subjects_passed < min_passed:
        is_eligible = False
        reasons.append(
            f"passed {subjects_passed} subject(s), {min_passed} required"
        )

    if is_eligible and not reasons:
        reasons.append("all configured graduation requirements met")

    return GraduationAuditResult(
        is_eligible=is_eligible,
        requirements_configured=True,
        annual_average=annual_avg,
        min_annual_average=min_avg,
        subjects_passed=subjects_passed,
        min_subjects_passed=min_passed,
        required_subject_codes=list(required_codes),
        missing_required_subjects=missing_required,
        source="k12-settings",
        reasons=reasons,
    )


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def audit_graduation_eligibility(student, academic_year) -> GraduationAuditResult:
    """Audit one student's graduation eligibility for ``academic_year``.

    ``academic_year`` is the year whose COMPLETED grades the audit reads — the
    SOURCE year being closed at rollover, where the student's final marks live
    (NOT the target year they are moving into).
    """
    # Higher-ed degree student → delegate to the real requirements engine.
    enrollment = _resolve_degree_enrollment(student)
    if enrollment is not None:
        return _audit_via_degree(enrollment)

    # K-12 → tenant-configured settings requirements.
    school = getattr(student, "school", None)
    reqs = resolve_graduation_requirements(school)
    if not reqs["configured"]:
        # Behaviour-preserving: no requirement configured → the gate stays inert.
        return GraduationAuditResult(
            is_eligible=True,
            requirements_configured=False,
            source="no-requirements",
            reasons=["no graduation requirements configured"],
        )
    return _audit_via_settings(student, academic_year, school, reqs)


def audit_graduating_cohort(proposal):
    """Audit every ``is_graduate`` item on a rollover proposal.

    Returns a list of ``(RolloverProposalItem, GraduationAuditResult)`` tuples.
    Grades are read from the proposal's SOURCE year (the year being closed).
    """
    results: list = []
    if proposal is None:
        return results
    source_year = getattr(proposal, "source_year", None)
    try:
        items = list(
            proposal.items.filter(is_graduate=True).select_related(  # tenant-isolation-allow: reverse-relation-scoped-by-parent-proposal-object
                "student", "student__classroom"
            )
        )
    except _AUDIT_SOFT_ERRORS as exc:
        logger.debug("graduation_audit cohort resolve failed: %s", exc)
        return results
    for item in items:
        results.append(
            (item, audit_graduation_eligibility(item.student, source_year))
        )
    return results
