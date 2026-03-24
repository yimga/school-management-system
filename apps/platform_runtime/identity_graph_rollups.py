"""
Platform-wide and per-tenant rollups for identity / roster posture (wedges 44–45, §11.4).
"""

from __future__ import annotations

from typing import Any

from django.db import DatabaseError

_ROLLUP_SOFT = (AttributeError, DatabaseError, LookupError, TypeError, ValueError)


def compute_platform_identity_rollups() -> dict[str, Any]:
    """Cross-tenant aggregates for manager control plane (no PII rows)."""
    out: dict[str, Any] = {
        "schema_version": "1.0",
        "active_schools": None,
        "active_students": None,
        "active_teachers": None,
        "guardian_links": None,
        "distinct_guardian_users": None,
        "schools_with_parent": None,
        "federation_integrations_tracked": None,
    }
    try:
        from apps.accounts.models import FederationSsoHealth
        from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
        from apps.schools.models import School

        out["active_schools"] = School.objects.filter(is_active=True).count()
        out["active_students"] = StudentProfile.objects.filter(is_active=True).count()
        out["active_teachers"] = TeacherProfile.objects.filter(is_active=True).count()
        out["guardian_links"] = StudentGuardian.objects.count()
        out["distinct_guardian_users"] = (
            StudentGuardian.objects.values("guardian_user_id").distinct().count()
        )
        out["schools_with_parent"] = School.objects.filter(
            is_active=True, parent_school__isnull=False
        ).count()
        out["federation_integrations_tracked"] = FederationSsoHealth.objects.count()
    except _ROLLUP_SOFT:
        out["error"] = "rollup_unavailable"
    return out


def compute_tenant_identity_graph_summary(school) -> dict[str, Any]:
    """Per-tenant counts for roster ↔ guardian ↔ integration spine."""
    out: dict[str, Any] = {
        "schema_version": "1.0",
        "school_id": str(school.pk),
        "active_students": None,
        "active_teachers": None,
        "guardian_links": None,
        "distinct_guardian_users": None,
        "active_service_integrations": None,
        "oauth_oidc_integrations": None,
    }
    try:
        from apps.integrations_marketplace.models import ServiceIntegration
        from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile

        out["active_students"] = StudentProfile.objects.filter(
            school=school, is_active=True
        ).count()
        out["active_teachers"] = TeacherProfile.objects.filter(
            school=school, is_active=True
        ).count()
        gq = StudentGuardian.objects.filter(student__school=school)
        out["guardian_links"] = gq.count()
        out["distinct_guardian_users"] = (
            gq.values("guardian_user_id").distinct().count()
        )
        si = ServiceIntegration.objects.filter(school=school, is_active=True)
        out["active_service_integrations"] = si.count()
        out["oauth_oidc_integrations"] = si.filter(
            service_type=ServiceIntegration.ServiceType.OAUTH
        ).count()
    except _ROLLUP_SOFT:
        out["error"] = "summary_unavailable"
    return out
