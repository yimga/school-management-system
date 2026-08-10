"""Wave 7 (v2.80) — First-school operating proof readiness preflight.

Sister module to ``rls_readiness.py`` (O2), ``residency_readiness.py`` (K4),
``security/csp_readiness.py`` (L2), and ``analytics/at_risk_readiness.py`` (O1).

The platform may be infrastructurally ready (RLS armed, CSP enforced, residency
backfilled) and still be unable to operate even one real school because no
tenant has the minimum operational scaffolding. This preflight asks:

  "Is there at least one tenant on this platform that can host a real school
  for one full academic term TODAY?"

A green answer is the precondition for our first paying customer — the "first
school operating proof" line item from the master prompt's top-12 priorities.

Checks (a tenant must satisfy ALL to be counted as operating-ready):

* At least one ``AcademicYear`` exists for the tenant.
* At least one ``Term`` exists, attached to one of those years.
* At least one ``Classroom`` is defined.
* At least one active ``TeacherProfile`` linked to an enabled user.
* At least one active ``StudentProfile``.
* At least one active (non-suspended) OWNER membership — somebody who can
  actually log in and administer the tenant. A school with full academic
  scaffolding + roster + brand but no owner cannot be operated (nobody can
  approve, manage the term, or receive critical comms), so it is NOT ready.
* The School row itself has a non-blank ``name`` (the very first branding
  signal a parent sees in an email subject).

A tenant that fails any one check is "not operating-ready" and its slug
appears in ``report.tenants_not_ready`` with the missing-pieces list. If the
platform has zero tenants meeting all checks, ``report.ready`` is ``False``
and the platform cannot honestly claim "first school is live."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FirstSchoolReadinessReport:
    schools_total: int = 0
    schools_operating_ready: int = 0
    tenants_ready: list[str] = field(default_factory=list)
    tenants_not_ready: list[dict[str, Any]] = field(default_factory=list)
    """Each row: {'slug': str, 'name': str, 'missing': list[str]}."""
    error_detail: str = ""

    @property
    def ready(self) -> bool:
        return self.schools_operating_ready >= 1 and not self.error_detail

    def issue_count(self) -> int:
        if self.error_detail:
            return 1
        return 0 if self.ready else max(1, len(self.tenants_not_ready))


# Minimum-operating-condition probes. Each returns ``True`` when the school
# meets that criterion. Iteration order is deterministic so the missing-pieces
# list reads top-down the same way every run.
def _has_academic_year(school) -> bool:
    from apps.academics.models import AcademicYear

    return AcademicYear.objects.filter(school=school).exists()


def _has_term(school) -> bool:
    from apps.academics.models import Term

    return Term.objects.filter(school=school).exists()


def _has_classroom(school) -> bool:
    from apps.academics.models import Classroom

    return Classroom.objects.filter(school=school).exists()


def _has_active_teacher(school) -> bool:
    from apps.people.models import TeacherProfile

    return TeacherProfile.objects.filter(
        school=school, is_active=True, user__is_active=True
    ).exists()


def _has_active_student(school) -> bool:
    from apps.people.models import StudentProfile

    return StudentProfile.objects.filter(school=school, is_active=True).exists()


def _has_active_owner(school) -> bool:
    from apps.schools.models import SchoolMembership

    return SchoolMembership.has_active_owner(school)


def _has_brand_name(school) -> bool:
    return bool((getattr(school, "name", "") or "").strip())


_CRITERIA = (
    ("academic_year", _has_academic_year),
    ("term", _has_term),
    ("classroom", _has_classroom),
    ("active_teacher", _has_active_teacher),
    ("active_student", _has_active_student),
    ("active_owner", _has_active_owner),
    ("brand_name", _has_brand_name),
)


def assess_first_school_readiness() -> FirstSchoolReadinessReport:
    """Run every criterion against every active tenant. Return the report."""
    report = FirstSchoolReadinessReport()
    try:
        from apps.schools.models import School
    except ImportError as e:
        report.error_detail = f"School model not importable: {e}"
        return report

    schools = School.objects.all()
    report.schools_total = schools.count()

    for school in schools.iterator():
        missing: list[str] = []
        for key, probe in _CRITERIA:
            try:
                if not probe(school):
                    missing.append(key)
            except Exception as exc:  # noqa: BLE001
                missing.append(f"{key}:probe_failed:{exc.__class__.__name__}")
        if not missing:
            report.tenants_ready.append(getattr(school, "slug", "") or str(school.pk))
            report.schools_operating_ready += 1
        else:
            report.tenants_not_ready.append(
                {
                    "slug": getattr(school, "slug", "") or str(school.pk),
                    "name": getattr(school, "name", ""),
                    "missing": missing,
                }
            )
    return report
