"""
Tenant-scoped statutory extract payload (JSON) — live aggregates for ministry/EMIS shells.

§11.4 depth: real counts from the tenant DB; jurisdiction narrative from catalog hints.
No student-level rows (aggregate only).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from django.db import DatabaseError
_STAT_SOFT = (AttributeError, DatabaseError, LookupError, TypeError, ValueError)


def build_statutory_tenant_extract(
    school,
    *,
    stub: str,
    country_code: str | None = None,
) -> dict[str, Any]:
    """Return JSON-serializable statutory shell with live tenant counts."""
    from apps.governance.country_matrix_service import resolve_statutory_jurisdiction_hint
    from apps.platform_runtime.learning_institution_catalog import CATALOG_VERSION

    cc = (country_code or "").strip().upper()[:2]
    hint = resolve_statutory_jurisdiction_hint(cc) if cc and len(cc) == 2 else None

    active_students = active_teachers = guardian_links = distinct_guardians = 0
    try:
        from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile

        active_students = StudentProfile.objects.filter(
            school=school, is_active=True
        ).count()
        active_teachers = TeacherProfile.objects.filter(
            school=school, is_active=True
        ).count()
        gq = StudentGuardian.objects.filter(student__school=school)
        guardian_links = gq.count()
        distinct_guardians = gq.values("guardian_user_id").distinct().count()
    except _STAT_SOFT:
        pass

    return {
        "schema_version": "1.0",
        "catalog_version": CATALOG_VERSION,
        "extract_kind": "tenant_statutory_aggregate",
        "stub": stub,
        "jurisdiction_alpha2": cc or None,
        "jurisdiction_label": (hint or {}).get("label") if hint else None,
        "framework_note": (hint or {}).get("framework") if hint else None,
        "school": {
            "id": str(school.pk),
            "name": school.name,
            "country_code": getattr(school, "country_code", "") or "",
            "subdomain": getattr(school, "subdomain", "") or "",
        },
        "counts": {
            "active_students": active_students,
            "active_teachers": active_teachers,
            "guardian_links": guardian_links,
            "distinct_guardian_users": distinct_guardians,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Aggregate counts only; not a legal filing until connectors and mappings are certified for your jurisdiction.",
    }
