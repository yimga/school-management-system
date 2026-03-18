"""
North-star internal APIs: event catalog (Tier 4), wedge playbook, marketplace package impact (N17).
Staff/superuser or school-scoped admin; BR-11 Clever/ClassLink native remains blocked—OneRoster + hub substitute.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.api.br_northstar_views import _StaffSchoolMixin, _school_from_request


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
class NorthStarPackageImpactView(_StaffSchoolMixin, View):
    """
    N17-style package impact preview: uses PackageVersion payload + preview_diff for tenant.
    Query: package_id (required), version (optional), school_id (optional if tenant context).
    """

    def get(self, request):
        from apps.packages.engine import preview_diff
        from apps.packages.models import InstalledPackage, PackageVersion
        from apps.schools.models import School

        package_id = (request.GET.get("package_id") or "").strip()
        if not package_id:
            return JsonResponse({"error": "package_id required"}, status=400)

        school = _school_from_request(request)
        sid = request.GET.get("school_id")
        if school is None and sid:
            school = School.objects.filter(pk=sid).first()
        if school is None:
            return JsonResponse(
                {
                    "error": "school context required",
                    "hint": "Pass school_id or open session with tenant school.",
                },
                status=400,
            )

        version = (request.GET.get("version") or "").strip()
        if not version:
            inst = (
                InstalledPackage.objects.filter(
                    package_id=package_id, school=school, is_active=True
                )
                .order_by("-applied_at")
                .first()
            )
            if inst:
                version = inst.version
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

        if not pv or not (pv.payload_sections or {}):
            inst = (
                InstalledPackage.objects.filter(
                    package_id=package_id, school=school, is_active=True
                )
                .order_by("-applied_at")
                .first()
            )
            return JsonResponse(
                {
                    "package_id": package_id,
                    "school_id": str(school.pk),
                    "preview_available": False,
                    "installed": bool(inst),
                    "installed_version": inst.version if inst else None,
                    "impact_summary_stored": (inst.impact_summary if inst else {})
                    or {},
                    "hint": "Register PackageVersion with payload_sections for full preview_diff.",
                }
            )

        diff = preview_diff(
            school.pk, package_id, version, dict(pv.payload_sections or {})
        )
        return JsonResponse(
            {
                "package_id": package_id,
                "version": version,
                "school_id": str(school.pk),
                "preview_available": True,
                "preview": diff,
            }
        )
