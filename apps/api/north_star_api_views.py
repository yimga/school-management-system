"""
North-star internal APIs: event catalog (Tier 4), wedge playbook, marketplace package impact (N17).
Staff/superuser or school-scoped admin; BR-11 Clever/ClassLink native remains blocked—OneRoster + hub substitute.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.api.br_northstar_views import _StaffSchoolMixin


class _StaffSuperuserOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Platform-wide aggregates: staff/superuser only (not tenant teacher/admin)."""

    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False
        return bool(
            getattr(u, "is_superuser", False) or getattr(u, "is_staff", False)
        )


@method_decorator(csrf_exempt, name="dispatch")
class NorthStarEventCatalogView(_StaffSchoolMixin, View):
    """Full platform EVENT_CATALOG for operators and automation (Tier 4 lineage / outbox visibility)."""

    def get(self, request):
        from apps.platform_runtime.events import get_event_catalog

        return JsonResponse({"version": "2026.03", "events": get_event_catalog()})


@method_decorator(csrf_exempt, name="dispatch")
class NorthStarWedgePlaybookView(_StaffSchoolMixin, View):
    """Learning institution wedges 23–43: delivery modes, institution types, ministry stubs (SOT)."""

    def get(self, request):
        from apps.platform_runtime.learning_institution_catalog import (
            CATALOG_VERSION,
            INSTITUTION_TYPE_PACKS,
            LEARNING_DELIVERY_MODES,
            MINISTRY_REPORT_STUBS,
        )

        return JsonResponse(
            {
                "catalog_version": CATALOG_VERSION,
                "delivery_modes": [
                    {
                        "code": m["code"],
                        "label": m.get("label", m["code"]),
                        "wedge": m.get("wedge"),
                        "pack_slugs": [
                            s.strip()
                            for s in str(m.get("pack_slugs") or "").split(",")
                            if s.strip()
                        ],
                    }
                    for m in LEARNING_DELIVERY_MODES
                ],
                "institution_types": [
                    {
                        "code": p["code"],
                        "label": p.get("label", p["code"]),
                        "wedge": p.get("wedge"),
                        "pack_slugs": [
                            s.strip()
                            for s in str(p.get("pack_slugs") or "").split(",")
                            if s.strip()
                        ],
                    }
                    for p in INSTITUTION_TYPE_PACKS
                ],
                "ministry_report_stub_keys": list(MINISTRY_REPORT_STUBS.keys()),
                "substitute_interop": {
                    "oneroster": "/api/oneroster/v1p1/manifest",
                    "br11_status": "Clever/ClassLink native blocked; use OneRoster + district hub.",
                },
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class NorthStarRumWebVitalsSummaryView(_StaffSuperuserOnlyMixin, View):
    """
    N10 read path: aggregate recent rum_web_vitals from PlatformEventLog (staff-only).
    Query: hours (1–168, default 24), limit (max rows scanned, default 2000, cap 5000).
    """

    def get(self, request):
        from apps.platform_runtime.rum_aggregate import summarize_rum_web_vitals

        try:
            hours = int(request.GET.get("hours") or 24)
        except (TypeError, ValueError):
            hours = 24
        try:
            limit = int(request.GET.get("limit") or 2000)
        except (TypeError, ValueError):
            limit = 2000

        body = summarize_rum_web_vitals(hours=hours, limit_rows=limit)
        key = (getattr(settings, "RUM_INGEST_KEY", None) or "").strip()
        body["version"] = "2026.03"
        body["rum_ingest_configured"] = len(key) >= 16
        body["read_model"] = "platform_event_log.rum_web_vitals"
        return JsonResponse(body)


@method_decorator(csrf_exempt, name="dispatch")
class NorthStarUpcomingDeadlinesView(_StaffSchoolMixin, View):
    """
    N28 proactive signals: merged upcoming grading deadlines + public school calendar events.
    Tenant-scoped: requires ``request.school`` / tenant runtime or ``school_id`` query (staff).
    """

    def get(self, request):
        from apps.academics.services import get_active_year_and_term
        from apps.portal.services import merged_upcoming_events_for_api

        from apps.schools.tenant_api_guards import resolve_school_from_request_param

        school, deny = resolve_school_from_request_param(request)
        if deny is not None:
            return deny
        if school is None:
            return JsonResponse(
                {
                    "error": "school context required",
                    "hint": "Open in tenant context or pass school_id.",
                },
                status=400,
            )

        year, _term = get_active_year_and_term(school=school)
        events = (
            merged_upcoming_events_for_api(year, school=school) if year else []
        )
        return JsonResponse(
            {
                "version": "2026.03",
                "read_model": "subject_assignment.grading_deadline_at + school_events",
                "academic_year_id": year.pk if year else None,
                "school_id": str(school.pk),
                "events": events,
                "count": len(events),
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class NorthStarPackageImpactView(_StaffSchoolMixin, View):
    """
    N17-style package impact preview: uses PackageVersion payload + preview_diff for tenant.
    Query: package_id (required), version (optional), school_id (optional if tenant context).
    """

    def get(self, request):
        from apps.packages.engine import (
            list_reverse_dependent_package_ids,
            normalize_declared_dependencies,
            preview_diff,
        )
        from apps.packages.models import InstalledPackage, PackageVersion

        package_id = (request.GET.get("package_id") or "").strip()
        if not package_id:
            return JsonResponse({"error": "package_id required"}, status=400)

        from apps.schools.tenant_api_guards import resolve_school_from_request_param

        school, deny = resolve_school_from_request_param(request)
        if deny is not None:
            return deny
        if school is None:
            return JsonResponse(
                {
                    "error": "school context required",
                    "hint": "Pass school_id or open session with tenant school.",
                },
                status=400,
            )

        inst_active = (
            InstalledPackage.objects.filter(
                package_id=package_id, school=school, is_active=True
            )
            .order_by("-applied_at")
            .first()
        )

        version = (request.GET.get("version") or "").strip()
        if not version and inst_active:
            version = inst_active.version
        pv = None
        if version:
            pv = PackageVersion.objects.filter(
                package_id=package_id, version=version
            ).first()
        if not pv:
            pv = (
                PackageVersion.objects.filter(package_id=package_id)
                .order_by("-created_at")
                .first()
            )
            if pv:
                version = pv.version

        downstream = list_reverse_dependent_package_ids(package_id)

        def _dependency_graph_payload() -> dict:
            upstream: list[str] = []
            if pv:
                try:
                    upstream = normalize_declared_dependencies(pv.dependencies)
                except ValueError:
                    upstream = []
            if not upstream and inst_active:
                try:
                    upstream = normalize_declared_dependencies(
                        inst_active.dependency_snapshot
                    )
                except ValueError:
                    upstream = []
            return {
                "upstream_package_ids": upstream,
                "downstream_package_ids": downstream,
                "note": "N17 advisory graph: downstream from a bounded PackageVersion scan; not a full solver.",
            }

        if not pv or not (pv.payload_sections or {}):
            return JsonResponse(
                {
                    "package_id": package_id,
                    "school_id": str(school.pk),
                    "preview_available": False,
                    "installed": bool(inst_active),
                    "installed_version": inst_active.version if inst_active else None,
                    "impact_summary_stored": (
                        (inst_active.impact_summary if inst_active else {}) or {}
                    ),
                    "dependency_graph": _dependency_graph_payload(),
                    "hint": "Register PackageVersion with payload_sections for full preview_diff.",
                }
            )

        diff = preview_diff(
            school.pk, package_id, version, dict(pv.payload_sections or {})
        )
        body = {
            "package_id": package_id,
            "version": version,
            "school_id": str(school.pk),
            "preview_available": True,
            "preview": diff,
            "dependency_graph": _dependency_graph_payload(),
        }
        # preview_diff already includes dependencies; graph adds reverse edges for operators.
        return JsonResponse(body)
