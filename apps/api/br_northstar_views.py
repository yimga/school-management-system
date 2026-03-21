"""
BR-01–BR-10 execution surfaces + North-star API helpers (staff/superuser scoped).
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.registries.services import (
    get_effective_attendance_codes,
    get_effective_fee_types_for_school,
)
from apps.academics.compliance_live_validation import (
    live_compliance_attendance_errors,
    live_compliance_enrollment_errors,
)

logger = logging.getLogger(__name__)


def _school_from_request(request):
    s = getattr(request, "school", None) or getattr(
        getattr(request, "tenant_runtime", None), "school", None
    )
    return s


def _school_from_request_or_body(request, data: dict):
    s = _school_from_request(request)
    if s is None and getattr(request.user, "is_staff", False):
        sid = data.get("school_id")
        if sid:
            from apps.schools.models import School

            s = School.objects.filter(pk=sid).first()
    return s


class _StaffSchoolMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        u = self.request.user
        if not u.is_authenticated:
            return False
        if getattr(u, "is_superuser", False) or getattr(u, "is_staff", False):
            return True
        return getattr(u, "is_school_admin", False) or getattr(u, "is_teacher", False)


@method_decorator(csrf_exempt, name="dispatch")
class SLOTargetsAPIView(_StaffSchoolMixin, View):
    """BR-01: Documented SLO targets + wiring reference (JSON for dashboards)."""

    def get(self, request):
        payload = {
            "version": "2026.03",
            "targets": {
                "api_p50_ms": 800,
                "api_p99_ms": 2000,
                "dashboard_lcp_ms": 2500,
                "uptime_slo_pct": 99.9,
            },
            "observability": {
                "health": "/health/",
                "slo_dashboard": "/api/v1/slo-dashboard/",
                "prometheus_metrics": "/metrics/",
                "rum_web_vitals_summary": "/api/internal/north-star/rum-web-vitals/",
                "upcoming_deadlines": "/api/internal/north-star/upcoming-deadlines/",
                "runbook": "docs/NORTH_STAR_TRUST_AND_OPS.md",
            },
            "perf_gate": "PERF_BUDGET_STRICT=1 enables strict check_performance_budgets in pre_deploy_gate",
        }
        return JsonResponse(payload)


@method_decorator(csrf_exempt, name="dispatch")
class ComplianceValidateEnrollmentView(_StaffSchoolMixin, View):
    """BR-05: POST JSON body; returns {errors: [...]}."""

    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"errors": ["invalid JSON"]}, status=400)
        if not isinstance(data, dict):
            data = {}
        school = _school_from_request_or_body(request, data)
        errs = live_compliance_enrollment_errors(school, data)
        return JsonResponse(
            {"errors": errs, "ok": len(errs) == 0}, status=200 if not errs else 422
        )


@method_decorator(csrf_exempt, name="dispatch")
class ComplianceValidateAttendanceView(_StaffSchoolMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"errors": ["invalid JSON"]}, status=400)
        data = data if isinstance(data, dict) else {}
        school = _school_from_request_or_body(request, data)
        errs = live_compliance_attendance_errors(school, data)
        return JsonResponse(
            {"errors": errs, "ok": len(errs) == 0}, status=200 if not errs else 422
        )


@method_decorator(csrf_exempt, name="dispatch")
class MigrationDiffPreviewView(_StaffSchoolMixin, View):
    """BR-04: Compare two CSV text bodies (row counts + header diff)."""

    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        a = (data.get("csv_a") or "").strip()
        b = (data.get("csv_b") or "").strip()

        def _info(text: str) -> dict:
            if not text:
                return {"rows": 0, "headers": []}
            f = io.StringIO(text)
            r = csv.reader(f)
            rows = list(r)
            if not rows:
                return {"rows": 0, "headers": []}
            return {"rows": max(0, len(rows) - 1), "headers": rows[0]}

        ia, ib = _info(a), _info(b)
        return JsonResponse(
            {
                "source": ia,
                "target": ib,
                "row_delta": ib["rows"] - ia["rows"],
                "header_match": ia.get("headers") == ib.get("headers"),
                "runbook": "docs/MIGRATION_SHADOW_RUNBOOK.md",
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class EWSListCreateView(_StaffSchoolMixin, View):
    """BR-06: List + create at-risk signals."""

    def get(self, request):
        from apps.analytics.models import StudentAtRiskSignal

        school = _school_from_request(request)
        if school is None and request.user.is_staff:
            sid = request.GET.get("school_id")
            if sid:
                from apps.schools.models import School

                school = School.objects.filter(pk=sid).first()
        if school is None:
            return JsonResponse({"results": []})
        qs = StudentAtRiskSignal.objects.filter(school=school).select_related(
            "student_user"
        )[:200]
        return JsonResponse(
            {
                "results": [
                    {
                        "id": s.id,
                        "student_id": str(s.student_user_id),
                        "score": s.score,
                        "status": s.status,
                        "factors": s.factors,
                        "updated_at": s.updated_at.isoformat(),
                    }
                    for s in qs
                ]
            }
        )

    def post(self, request):
        from apps.analytics.models import StudentAtRiskSignal

        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        data = data if isinstance(data, dict) else {}
        school = _school_from_request_or_body(request, data)
        if school is None:
            return JsonResponse(
                {"error": "no school context; pass school_id"}, status=400
            )
        uid = data.get("student_user_id")
        score = float(data.get("score") or 0)
        if not uid:
            return JsonResponse({"error": "student_user_id required"}, status=400)
        s = StudentAtRiskSignal.objects.create(
            school=school,
            student_user_id=uid,
            score=score,
            factors=data.get("factors") or {},
            created_by=request.user if request.user.is_authenticated else None,
        )
        logger.info("ews_signal_created id=%s school=%s", s.id, school.pk)
        return JsonResponse({"id": s.id, "score": s.score}, status=201)


def _intent_school_user_count(school):
    if school is None:
        return {"intent": "school_user_count", "count": 0, "note": "no school context"}
    from apps.people.models import StudentProfile, TeacherProfile

    tp = TeacherProfile.objects.filter(school=school).count()
    sp = StudentProfile.objects.filter(school=school).count()
    return {
        "intent": "school_user_count",
        "teacher_profiles": tp,
        "student_profiles": sp,
        "count": tp + sp,
    }


def _intent_active_schools_count(school):
    from apps.schools.models import School

    return {
        "intent": "active_schools_count",
        "count": School.objects.filter(is_active=True).count(),
    }


_ALLOWED_NL_INTENTS = {
    "school_user_count": _intent_school_user_count,
    "active_schools_count": _intent_active_schools_count,
}


@method_decorator(csrf_exempt, name="dispatch")
class NLAdminGovernedQueryView(UserPassesTestMixin, LoginRequiredMixin, View):
    """BR-07: Governed intents only; audited."""

    def test_func(self):
        return self.request.user.is_authenticated and (
            self.request.user.is_superuser or self.request.user.is_staff
        )

    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        intent = (data.get("intent") or "").strip()
        if intent not in _ALLOWED_NL_INTENTS:
            return JsonResponse(
                {
                    "error": "unknown intent",
                    "allowed": list(_ALLOWED_NL_INTENTS.keys()),
                },
                status=400,
            )
        school = _school_from_request(request)
        try:
            result = _ALLOWED_NL_INTENTS[intent](school)
        except Exception as e:
            logger.exception("nl_admin_intent_failed intent=%s", intent)
            return JsonResponse({"error": str(e)}, status=500)
        logger.info(
            "nl_admin_intent user=%s intent=%s result_keys=%s",
            getattr(request.user, "pk", None),
            intent,
            list(result.keys()) if isinstance(result, dict) else [],
        )
        return JsonResponse({"ok": True, "data": result})


@method_decorator(csrf_exempt, name="dispatch")
class MessagingRetentionPolicyView(_StaffSchoolMixin, View):
    """BR-08: Return effective messaging retention policy for tenant."""

    def get(self, request):
        school = _school_from_request(request)
        settings = (getattr(school, "settings", None) or {}) if school else {}
        days = 365
        if isinstance(settings, dict):
            days = int(
                settings.get("messaging_retention_days")
                or settings.get("comms_retention_days")
                or 365
            )
        return JsonResponse(
            {
                "retention_days": days,
                "translation_required_locales": (
                    settings.get("translation_required_locales") or []
                )
                if isinstance(settings, dict)
                else [],
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class LegacySisReadonlyStubView(_StaffSchoolMixin, View):
    """BR-09: Land-and-expand read-only connector config (stored in school.settings)."""

    def get(self, request):
        school = _school_from_request(request)
        cfg = {}
        if school and isinstance(getattr(school, "settings", None), dict):
            cfg = (school.settings or {}).get("legacy_sis_readonly") or {}
        return JsonResponse(
            {
                "configured": bool(cfg.get("enabled")),
                "mode": "csv_api",
                "doc": "docs/BR_LAND_AND_EXPAND_LEGACY_SIS.md",
            }
        )

    def post(self, request):
        if not request.user.is_superuser and not getattr(
            request.user, "is_staff", False
        ):
            return JsonResponse({"error": "forbidden"}, status=403)
        school = _school_from_request(request)
        if school is None:
            return JsonResponse({"error": "no school"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "invalid JSON"}, status=400)
        st = dict(school.settings or {})
        st["legacy_sis_readonly"] = {
            "enabled": bool(data.get("enabled")),
            "label": (data.get("label") or "")[:120],
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
        }
        school.settings = st
        school.save(update_fields=["settings", "updated_at"])
        return JsonResponse({"ok": True})


@method_decorator(csrf_exempt, name="dispatch")
class TenantRegistriesEffectiveView(_StaffSchoolMixin, View):
    def get(self, request):
        school = _school_from_request(request)
        if school is None and request.user.is_staff:
            sid = request.GET.get("school_id")
            if sid:
                from apps.schools.models import School

                school = School.objects.filter(pk=sid).first()
        return JsonResponse(
            {
                "attendance_codes": get_effective_attendance_codes(school),
                "fee_types": get_effective_fee_types_for_school(school),
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class DemographicInsightsView(_StaffSchoolMixin, View):
    """Wave 7: long-horizon enrollment / cohort snapshot for operators."""

    def get(self, request):
        school = _school_from_request(request)
        if school is None and request.user.is_staff:
            sid = request.GET.get("school_id")
            if sid:
                from apps.schools.models import School

                school = School.objects.filter(pk=sid).first()
        if school is None:
            return JsonResponse({"error": "school required"}, status=400)
        from django.db.models import Count

        from apps.people.models import StudentProfile

        qs = StudentProfile.objects.filter(school=school)
        active = qs.filter(is_active=True).count()
        rows = (
            qs.filter(is_active=True)
            .values("classroom__name")
            .annotate(c=Count("id"))
        )
        by_class = {
            str(r["classroom__name"] or "unassigned"): r["c"] for r in rows
        }
        return JsonResponse(
            {
                "school_id": school.id,
                "active_students": active,
                "by_classroom_name": by_class,
                "runbook": "docs/WAVE_EXECUTION_RUNBOOKS.md",
                "note": "Extend with YoY enrollment velocity and forecast models.",
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class ClimateReportingHooksView(_StaffSchoolMixin, View):
    """Wave 7: statutory/extension hooks for sustainability reporting (jurisdiction-dependent)."""

    def get(self, request):
        return JsonResponse(
            {
                "hooks": [
                    "report_pack_optional_esg_stub",
                    "statutory_csv_extension_energy",
                    "ministry_placeholder_agreement_ref",
                ],
                "doc": "docs/WAVE_EXECUTION_RUNBOOKS.md",
                "note": "Wire to region pack when jurisdiction mandates climate disclosures.",
            }
        )
