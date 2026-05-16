"""Data Quality checks for a tenant school.

Provides a small but real set of completeness + reachability checks. Each
check returns a `DataQualityIssue`-shaped dict so the view layer (and any
future digest job) can render them uniformly.

Wave 5 (v2.76): replaces the v1 stub that returned `[]`. The checks here are
deliberately conservative — they only inspect data already in tenant scope and
use FK relations the per-tenant RLS layer already enforces. No cross-tenant
reads.

Each check is registered in `DATA_QUALITY_CHECKS` so tests can iterate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Iterable, List


SEVERITY_BLOCKER = "blocker"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass
class DataQualityIssue:
    """One row in the Data Quality Center report."""

    key: str
    severity: str
    title: str
    description: str
    record_count: int
    record_sample_ids: list[int] = field(default_factory=list)
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CheckFn = Callable[[Any], "DataQualityIssue | None"]


def _students_without_guardian(school) -> "DataQualityIssue | None":
    from apps.people.models import StudentProfile

    qs = (
        StudentProfile.objects.filter(school=school, is_active=True)
        .filter(guardian_links__isnull=True)
        .order_by("id")
    )
    count = qs.count()
    if not count:
        return None
    sample = list(qs.values_list("id", flat=True)[:10])
    return DataQualityIssue(
        key="students_without_guardian",
        severity=SEVERITY_BLOCKER,
        title="Students without a guardian link",
        description=(
            "These students have no parent or guardian on file. The school "
            "cannot reach them via parent communications, fee notices, or "
            "emergency contact."
        ),
        record_count=count,
        record_sample_ids=sample,
        fix_hint=(
            "Open each student profile and link an existing parent user or "
            "invite a new one via the People → Parents directory."
        ),
    )


def _teachers_with_disabled_login(school) -> "DataQualityIssue | None":
    """Teacher records are flagged active locally but the linked user can't log in."""
    from apps.people.models import TeacherProfile

    qs = (
        TeacherProfile.objects.filter(school=school, is_active=True, user__is_active=False)
        .order_by("id")
    )
    count = qs.count()
    if not count:
        return None
    sample = list(qs.values_list("id", flat=True)[:10])
    return DataQualityIssue(
        key="teachers_with_disabled_login",
        severity=SEVERITY_BLOCKER,
        title="Active teachers whose login is disabled",
        description=(
            "These teacher records are marked active but the linked user "
            "account has `is_active=False`, so the teacher cannot log in to "
            "take attendance, enter grades, or receive notifications."
        ),
        record_count=count,
        record_sample_ids=sample,
        fix_hint=(
            "Either reactivate the user account or mark the teacher record "
            "inactive so it stops appearing in coverage and assignment lists."
        ),
    )


def _students_without_classroom(school) -> "DataQualityIssue | None":
    from apps.people.models import StudentProfile

    qs = (
        StudentProfile.objects.filter(
            school=school, is_active=True, classroom__isnull=True
        )
        .order_by("id")
    )
    count = qs.count()
    if not count:
        return None
    sample = list(qs.values_list("id", flat=True)[:10])
    return DataQualityIssue(
        key="students_without_classroom",
        severity=SEVERITY_WARNING,
        title="Active students with no classroom assigned",
        description=(
            "These active students are not placed in any classroom for the "
            "current year, so they will be invisible in attendance, gradebook, "
            "and class-based reports."
        ),
        record_count=count,
        record_sample_ids=sample,
        fix_hint=(
            "Open each profile and pick a classroom, or run the rollover "
            "wizard if you have just opened a new academic year."
        ),
    )


def _students_without_parent_phone(school) -> "DataQualityIssue | None":
    from apps.people.models import StudentProfile

    qs = (
        StudentProfile.objects.filter(school=school, is_active=True, parent_phone="")
        .order_by("id")
    )
    count = qs.count()
    if not count:
        return None
    sample = list(qs.values_list("id", flat=True)[:10])
    return DataQualityIssue(
        key="students_without_parent_phone",
        severity=SEVERITY_INFO,
        title="Students missing a parent phone number",
        description=(
            "These active students have no `parent_phone` on the profile. "
            "SMS blasts and fee reminders that fall back to phone may not "
            "reach the family when no guardian link covers the gap."
        ),
        record_count=count,
        record_sample_ids=sample,
        fix_hint=(
            "Open each profile, add a parent phone, or capture it via the "
            "guardian linkage if a parent user record already has one."
        ),
    )


DATA_QUALITY_CHECKS: tuple[CheckFn, ...] = (
    _students_without_guardian,
    _teachers_with_disabled_login,
    _students_without_classroom,
    _students_without_parent_phone,
)


def data_quality_checks(school_id: Any = None, *, school: Any = None) -> list[dict[str, Any]]:
    """Run each registered check against the given tenant scope.

    Accepts either ``school_id`` (legacy positional) or ``school=`` (preferred).
    Returns a list of dicts (ready to JSON-serialize / render).
    """
    if school is None and school_id is not None:
        from apps.schools.models import School

        school = School.objects.filter(pk=school_id).first()
    if school is None:
        return []
    issues: list[DataQualityIssue] = []
    for check in DATA_QUALITY_CHECKS:
        try:
            issue = check(school)
        except Exception:  # noqa: BLE001 - one broken check must not break the report
            continue
        if issue is not None:
            issues.append(issue)
    return [i.to_dict() for i in issues]


def summarize(issues: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Roll-up: counts per severity, used by the meter component."""
    out = {SEVERITY_BLOCKER: 0, SEVERITY_WARNING: 0, SEVERITY_INFO: 0, "total": 0}
    for it in issues:
        sev = it.get("severity") or SEVERITY_INFO
        out[sev] = out.get(sev, 0) + 1
        out["total"] += 1
    return out
