"""Organization-level EMIS aggregate pipeline (Phase 4D).

Role-separated reporting: inspectors receive de-identified aggregates only;
org owners may see school-level breakdown without student PII.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.governance.models import Organization

INSPECTOR_ROLES = frozenset({"inspector", "superintendent"})
OWNER_ROLES = frozenset({"owner", "group_admin"})


@dataclass(frozen=True)
class OrgEmisAggregate:
    organization_id: str
    reporter_role: str
    schools_count: int
    students_count: int
    teachers_count: int
    by_school: tuple[dict[str, Any], ...]
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "organization_id": self.organization_id,
            "reporter_role": self.reporter_role,
            "schools_count": self.schools_count,
            "students_count": self.students_count,
            "teachers_count": self.teachers_count,
            "schema_version": self.schema_version,
        }
        if self.by_school:
            payload["by_school"] = list(self.by_school)
        return payload


def _normalize_role(role: str | None) -> str:
    return str(role or "").strip().lower()


def aggregate_organization_emis(
    organization: "Organization",
    *,
    reporter_role: str,
) -> OrgEmisAggregate:
    """
    Build role-separated EMIS aggregates for an organization.

    Inspectors: org totals only (no per-school breakdown).
    Owners/group admins: per-school counts without PII fields.
    """
    from apps.people.models import StudentProfile, TeacherProfile
    from apps.schools.models import School

    role = _normalize_role(reporter_role)
    # tenant-isolation-allow: emis-org-aggregate-explicit-organization-school-fk-scope
    schools = list(School.objects.filter(organization=organization, is_active=True))
    school_ids = [s.pk for s in schools]

    students_count = 0
    teachers_count = 0
    by_school: list[dict[str, Any]] = []

    if school_ids:
        students_count = StudentProfile.objects.filter(
            school_id__in=school_ids,
            is_active=True,
        ).count()
        teachers_count = TeacherProfile.objects.filter(
            school_id__in=school_ids,
            is_active=True,
        ).count()

        if role in OWNER_ROLES:
            for school in schools:
                sc = StudentProfile.objects.filter(school=school, is_active=True).count()
                tc = TeacherProfile.objects.filter(school=school, is_active=True).count()
                by_school.append(
                    {
                        "school_id": str(school.pk),
                        "school_name": school.name,
                        "students_count": sc,
                        "teachers_count": tc,
                    }
                )

    return OrgEmisAggregate(
        organization_id=str(organization.pk),
        reporter_role=role or "unknown",
        schools_count=len(schools),
        students_count=students_count,
        teachers_count=teachers_count,
        by_school=tuple(by_school),
    )
