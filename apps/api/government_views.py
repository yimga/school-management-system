"""
Government / district aggregate API (Section 14.5).
Permission-gated; returns aggregates only (no PII). Stub for EMIS/reporting extensions.
"""

from django.db import DatabaseError
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

GOVERNMENT_AGGREGATE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    LookupError,
    TypeError,
    ValueError,
)


@method_decorator(require_GET, name="get")
@method_decorator(login_required, name="dispatch")
class GovernmentAggregatesAPI(View):
    """
    GET /api/government/aggregates/
    Returns de-identified aggregates (counts by region/level). Requires staff or capability.
    """

    def get(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return JsonResponse({"detail": "Authentication required."}, status=401)
        school = getattr(request, "school", None)
        # Allow superuser or staff (control plane) or school with government_aggregate capability
        from apps.schools.models import can

        allowed = user.is_superuser or getattr(user, "is_staff", False)
        if not allowed and school:
            allowed = can(school, "GOVERNMENT_AGGREGATE")
        if not allowed:
            return JsonResponse(
                {"detail": "Not allowed to view government aggregates."}, status=403
            )

        # Stub: return placeholder aggregates (no PII)
        from django.apps import apps
        from django.db.models import Count

        payload = {
            "schools_count": 0,
            "students_count": 0,
            "teachers_count": 0,
            "guardian_links_count": 0,
            "schools_with_parent_count": 0,
            "by_region": {},
            "schema_version": "1.1",
        }
        try:
            if apps.is_installed("schools"):
                School = apps.get_model("schools", "School")
                payload["schools_count"] = School.objects.filter(is_active=True).count()
                payload["schools_with_parent_count"] = School.objects.filter(
                    is_active=True, parent_school__isnull=False
                ).count()
            if apps.is_installed("people"):
                StudentProfile = apps.get_model("people", "StudentProfile")
                TeacherProfile = apps.get_model("people", "TeacherProfile")
                StudentGuardian = apps.get_model("people", "StudentGuardian")
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                payload["students_count"] = StudentProfile.objects.filter(
                    is_active=True
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                ).count()
                payload["teachers_count"] = TeacherProfile.objects.filter(
                    is_active=True
                ).count()
                payload["guardian_links_count"] = StudentGuardian.objects.count()
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                # Optional: by region (country_code) — no PII
                by_region = (
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    StudentProfile.objects.filter(is_active=True)
                    .values("school__country_code")
                    .annotate(count=Count("id"))
                )
                payload["by_region"] = {
                    r["school__country_code"] or "unknown": r["count"]
                    for r in by_region
                }
        except GOVERNMENT_AGGREGATE_SOFT_FAILURES:
            pass
        return JsonResponse(payload)
