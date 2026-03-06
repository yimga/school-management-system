"""
RunMyCampus Standards Compliance: API v1 contract.
Implements or delegates to existing logic the standard endpoints under /api/v1/.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)


def _require_super_or_school(request, school_id=None):
    """Return (True, None) if allowed; else (False, JsonResponse)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return False, JsonResponse({"error": "Authentication required"}, status=401)
    if request.user.is_superuser:
        return True, None
    request_school = getattr(request, "school", None)
    role = (getattr(request.user, "role", "") or "").upper()
    allowed_roles = {"ADMIN", "IT_ADMIN", "LEADERSHIP", "PROPRIETOR", "PRINCIPAL"}
    if request_school and role in allowed_roles:
        if school_id is None or str(request_school.id) == str(school_id):
            return True, None
    return False, JsonResponse({"error": "Forbidden"}, status=403)


def _get_school_from_request(request):
    """Return request.school (set by tenant middleware) or None."""
    return getattr(request, "school", None)


def _backend_flag_enabled(flag_name: str, *, default: bool = False) -> bool:
    try:
        from apps.siteconfig.models import SiteSettings, default_backend_feature_flags

        flags = {
            **default_backend_feature_flags(),
            **(SiteSettings.get_solo().backend_feature_flags or {}),
        }
        return bool(flags.get(flag_name, default))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# POST /api/v1/tenants/provision  -> delegates to super api_create_school
# ---------------------------------------------------------------------------
@method_decorator(csrf_exempt, name="dispatch")
class TenantsProvisionView(View):
    """POST /api/v1/tenants/provision - Create new school and start provisioning."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not request.user.is_superuser:
            return JsonResponse({"error": "Superuser required"}, status=403)
        from apps.schools.super_views import api_create_school
        return api_create_school(request)


# ---------------------------------------------------------------------------
# GET /api/v1/config/integration-catalog  -> API Center: tenant integration types (WhatsApp, Stripe, etc.)
# ---------------------------------------------------------------------------
class IntegrationCatalogView(View):
    """GET /api/v1/config/integration-catalog - List integration types and config schemas for API Center."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.siteconfig.integration_catalog import INTEGRATION_CATALOG, list_catalog_keys
            keys = list_catalog_keys()
            catalog = {k: {**v, "config_schema": v.get("config_schema", {})} for k, v in INTEGRATION_CATALOG.items()}
            return JsonResponse({"keys": keys, "catalog": catalog})
        except Exception as e:
            logger.exception("config/integration-catalog")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/config/education-templates  -> one-click presets (British, WAEC, Vocational)
# ---------------------------------------------------------------------------
class EducationTemplatesView(View):
    """GET /api/v1/config/education-templates - List applyable education templates for signup/provisioning."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        templates = [
            {"code": "BRITISH_IGCSE", "name": "British / IGCSE", "description": "Michaelmas, Lent, Trinity; A*–G or 9–1; summative weighting."},
            {"code": "WAEC", "name": "West African (WAEC)", "description": "First, Second, Third term; A1–F9; CA 30% + Exam 70%."},
            {"code": "FRANCOPHONE_BAC", "name": "Francophone (Bac)", "description": "Trimestre 1–3; 20-point scale; Enseignant, Note, Moyenne."},
            {"code": "VOCATIONAL", "name": "Vocational / Trade", "description": "Competency checklists; clock hours; skill badges."},
        ]
        try:
            from apps.siteconfig.education_profile_engine import list_template_catalog
            from apps.siteconfig.models import EducationSystemProfile
            for p in EducationSystemProfile.objects.filter(is_active=True, approval_status=EducationSystemProfile.ApprovalStatus.APPROVED).values("code", "name"):
                if not any(t["code"] == p["code"] for t in templates):
                    templates.append({"code": p["code"], "name": p["name"], "description": ""})
            catalog = list_template_catalog()
            if catalog:
                templates = catalog
        except Exception:
            pass
        return JsonResponse({"templates": templates})


# ---------------------------------------------------------------------------
# GET /api/v1/config/education-dna  -> tenant-scoped education config
# ---------------------------------------------------------------------------
class EducationDNAView(View):
    """GET /api/v1/config/education-dna - Fetches grading rules and education template for current tenant."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.siteconfig.tenant_config import get_tenant_locale
            from apps.siteconfig.education_profile_engine import resolve_profile_for_school
            locale = get_tenant_locale(request=request, school=school)
            profile = resolve_profile_for_school(school)
            config = getattr(profile, "config", None) or {}
            system_type = getattr(profile, "sub_system", None) or getattr(school, "sub_system", "EN")
            term_labels = config.get("term_labels") or locale.get("term_labels") or []
            return JsonResponse({
                "tenant_id": str(school.id),
                "system_type": system_type,
                "grading_logic_json": config.get("grading_logic", config),
                "grading_scale": locale.get("grading_scale"),
                "terms": term_labels,
                "currency": locale.get("currency") or (getattr(school.default_region, "default_currency", None) if getattr(school, "default_region", None) else None),
                "timezone": locale.get("timezone", "UTC"),
                "date_format": locale.get("date_format", "DD/MM/YYYY"),
            })
        except Exception as e:
            logger.exception("education-dna")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# PATCH /api/v1/tenants/{id}/modules  -> set enabled modules for tenant
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["PATCH"]), name="dispatch")
class TenantModulesView(View):
    """PATCH /api/v1/tenants/<id>/modules - Enable or disable modules for the tenant."""

    def patch(self, request, id):
        ok, err = _require_super_or_school(request, school_id=id)
        if not ok:
            return err
        from apps.schools.models import School
        school = get_object_or_404(School, id=id)
        if not request.user.is_superuser and getattr(request, "school", None) != school:
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        modules = data.get("modules")
        if modules is None:
            return JsonResponse({"error": "modules required (list of module codes or dict module_name -> is_active)"}, status=400)
        if isinstance(modules, dict):
            enabled_list = [k for k, v in modules.items() if v]
        elif isinstance(modules, list):
            enabled_list = []
            for m in modules:
                if isinstance(m, dict):
                    if m.get("is_active", False) and m.get("module_name"):
                        enabled_list.append(str(m["module_name"]).strip().lower())
                else:
                    enabled_list.append(str(m).strip().lower())
        else:
            return JsonResponse({"error": "modules must be list or dict"}, status=400)
        school.addons = list(dict.fromkeys(enabled_list))
        school.save(update_fields=["addons", "updated_at"])
        return JsonResponse({"ok": True, "tenant_id": str(school.id), "modules": school.addons})


# ---------------------------------------------------------------------------
# Plan VIII: Cross-tenant identity — single identity, school switcher
# GET /api/v1/me/schools  -> list schools the user belongs to
# POST /api/v1/me/switch-school  -> set session school, return redirect URL
# ---------------------------------------------------------------------------
class MeSchoolsView(View):
    """GET /api/v1/me/schools - List schools the current user is a member of (for switcher)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.schools.models import SchoolMembership
        memberships = (
            SchoolMembership.objects.filter(user=request.user)
            .select_related("school")
            .order_by("-is_primary", "school__name")
        )
        schools = []
        for m in memberships:
            if not m.school or not m.school.is_active:
                continue
            schools.append({
                "school_id": str(m.school_id),
                "name": m.school.name,
                "slug": getattr(m.school, "slug", "") or "",
                "role": m.role,
                "is_primary": m.is_primary,
            })
        current = getattr(request, "school", None)
        return JsonResponse({
            "schools": schools,
            "current_school_id": str(current.id) if current else None,
        })


@method_decorator(require_http_methods(["POST"]), name="dispatch")
class MeSwitchSchoolView(View):
    """POST /api/v1/me/switch-school - Set session school for switcher. Body: { \"school_id\": \"uuid\" }."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        school_id = (data.get("school_id") or data.get("tenant_id") or "").strip()
        if not school_id:
            return JsonResponse({"error": "school_id required"}, status=400)
        from apps.schools.models import School, SchoolMembership
        school = School.objects.filter(id=school_id, is_active=True).first()
        if not school:
            return JsonResponse({"error": "School not found"}, status=404)
        if not request.user.is_superuser and not SchoolMembership.objects.filter(user=request.user, school=school).exists():
            return JsonResponse({"error": "Not a member of this school"}, status=403)
        if hasattr(request, "session"):
            request.session["school_id"] = str(school.id)
            request.session.save()
        from apps.schools.tenant_url import build_tenant_backend_url
        redirect_url = build_tenant_backend_url(request, school, path="/") if (getattr(school, "slug", None) or getattr(school, "subdomain", None)) else (request.build_absolute_uri("/") or "").rstrip("/")
        return JsonResponse({
            "ok": True,
            "school_id": str(school.id),
            "redirect_url": redirect_url,
        })


# ---------------------------------------------------------------------------
# GET /api/v1/student/passport/{global_id}  -> student passport timeline
# ---------------------------------------------------------------------------
class StudentPassportView(View):
    """GET /api/v1/student/passport/<global_id> - Fetches student's entire history across tenants."""

    def get(self, request, global_id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            guid = UUID(global_id)
        except ValueError:
            return JsonResponse({"error": "Invalid global_id (UUID)"}, status=400)
        from apps.people.models import StudentPassport, StudentProfile, PassportDocument
        passport = StudentPassport.objects.filter(guid=guid).select_related("owner").prefetch_related("documents", "school_invites").first()
        if not passport:
            return JsonResponse({"error": "Passport not found"}, status=404)
        school = _get_school_from_request(request)
        profiles = list(
            StudentProfile.objects.filter(passport=passport)
            .select_related("school", "user", "academic_year")
            .order_by("-academic_year__start_date")
        )
        if school:
            from apps.accounts.permissions import can_view_student_data
            if not request.user.is_superuser and not can_view_student_data(request.user, school):
                visible = [p for p in profiles if p.school_id == school.id]
                if not visible and passport.owner_id != request.user.id:
                    return JsonResponse({"error": "Forbidden"}, status=403)
                profiles = visible if visible else profiles
        docs = list(PassportDocument.objects.filter(passport=passport).values("id", "document_type", "title", "file_url", "verified_at", "created_at"))
        timeline = []
        for p in profiles:
            timeline.append({
                "school_id": str(p.school_id),
                "school_name": getattr(p.school, "name", None),
                "academic_year": getattr(p.academic_year, "name", None) if p.academic_year else None,
                "student_id": p.id,
                "admission_number": getattr(p, "admission_number", None),
            })
        return JsonResponse({
            "global_id": str(passport.guid),
            "documents": docs,
            "enrollments": timeline,
        })


# ---------------------------------------------------------------------------
# POST /api/v1/student/transfer  -> initiate transfer (invite or record)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class StudentTransferView(View):
    """POST /api/v1/student/transfer - Securely transfer / invite school to view passport."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        global_id = data.get("global_id") or data.get("student_global_id")
        to_school_id = data.get("to_school_id") or data.get("target_tenant_id")
        if not global_id or not to_school_id:
            return JsonResponse({"error": "global_id and to_school_id required"}, status=400)
        try:
            guid = UUID(global_id)
        except ValueError:
            return JsonResponse({"error": "Invalid global_id"}, status=400)
        from apps.people.models import StudentPassport, PassportSchoolInvite
        from apps.schools.models import School
        from django.utils import timezone
        from datetime import timedelta
        passport = get_object_or_404(StudentPassport, guid=guid)
        to_school = get_object_or_404(School, id=to_school_id)
        if passport.owner_id != request.user.id and not request.user.is_superuser:
            return JsonResponse({"error": "Forbidden"}, status=403)
        invite, created = PassportSchoolInvite.objects.get_or_create(
            passport=passport,
            school=to_school,
            defaults={"invited_by": request.user, "expires_at": timezone.now() + timedelta(days=90)},
        )
        return JsonResponse({
            "ok": True,
            "transfer_type": "invite",
            "invite_id": invite.id,
            "token": str(invite.token),
            "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        }, status=201)


# ---------------------------------------------------------------------------
# POST /api/v1/finance/generate-batch  -> trigger batch invoice generation
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class FinanceGenerateBatchView(View):
    """POST /api/v1/finance/generate-batch - One-click batch billing (async)."""

    def post(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.finance.tasks import auto_generate_fee_invoices_task
            result = auto_generate_fee_invoices_task.apply_async(kwargs={})
            return JsonResponse({"ok": True, "job_id": result.id, "message": "Batch generation started."}, status=202)
        except Exception as e:
            from apps.finance.tasks import auto_generate_fee_invoices_task
            try:
                out = auto_generate_fee_invoices_task(dry_run=False)
                return JsonResponse({"ok": True, "message": "Batch generation completed (sync).", "result": out}, status=200)
            except Exception as e2:
                logger.exception("finance/generate-batch")
                return JsonResponse({"error": str(e2)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/finance/exchange-rate  -> real-time currency conversion
# ---------------------------------------------------------------------------
class FinanceExchangeRateView(View):
    """GET /api/v1/finance/exchange-rate - Exchange rate for reporting (e.g. from_currency, to_currency)."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from_currency = (request.GET.get("from_currency") or request.GET.get("from") or "USD").strip().upper()[:3]
        to_currency = (request.GET.get("to_currency") or request.GET.get("to") or (getattr(school.default_region, "default_currency", None) if school and getattr(school, "default_region", None) else "XAF")).strip().upper()[:3]
        if from_currency == to_currency:
            return JsonResponse({"from_currency": from_currency, "to_currency": to_currency, "rate": 1.0, "source": "identity"})
        rate = _get_exchange_rate(from_currency, to_currency)
        if rate is None:
            return JsonResponse({"error": "Exchange rate not available", "from_currency": from_currency, "to_currency": to_currency}, status=503)
        return JsonResponse({"from_currency": from_currency, "to_currency": to_currency, "rate": rate, "source": "settings_or_api"})


def _get_exchange_rate(from_currency: str, to_currency: str):
    """Return rate from_currency -> to_currency, or None if not configured."""
    from django.conf import settings
    rates = getattr(settings, "EXCHANGE_RATES", None) or {}
    if isinstance(rates, dict):
        key = f"{from_currency}_{to_currency}"
        if key in rates:
            return float(rates[key])
        base = rates.get("BASE", "USD")
        from_rate = rates.get(from_currency if base == "USD" else f"{base}_{from_currency}", 1.0)
        to_rate = rates.get(to_currency if base == "USD" else f"{base}_{to_currency}", 1.0)
        if from_rate and to_rate:
            return float(to_rate) / float(from_rate)
    return None


# ---------------------------------------------------------------------------
# GET /api/v1/intervention/red-flags  -> students with risk score > 80
# ---------------------------------------------------------------------------
class InterventionRedFlagsView(View):
    """GET /api/v1/intervention/red-flags - At-risk students (score > 80)."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.analytics.models import RiskFactor
            threshold = int(request.GET.get("threshold", 80))
            qs = RiskFactor.objects.filter(school=school, score__gte=threshold).select_related("student", "student__user").order_by("-score")[:200]
            items = [{"student_id": r.student_id, "score": r.score, "reason_summary": r.reason_summary, "band": r.band, "computed_at": r.computed_at.isoformat() if r.computed_at else None} for r in qs]
            return JsonResponse({"count": len(items), "threshold": threshold, "students": items})
        except Exception as e:
            logger.exception("intervention/red-flags")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# POST /api/v1/intervention/calculate-risk  -> trigger risk calculation
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class InterventionCalculateRiskView(View):
    """POST /api/v1/intervention/calculate-risk - Trigger risk score calculation (background)."""

    def post(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            from apps.analytics.tasks import compute_risk_factors_task
            result = compute_risk_factors_task.apply_async(kwargs={"school_id": str(school.id)})
            return JsonResponse({"ok": True, "job_id": result.id, "message": "Risk calculation started."}, status=202)
        except Exception as e:
            if hasattr(e, "message"):
                msg = e.message
            else:
                msg = str(e)
            return JsonResponse({"error": msg}, status=500)


# ---------------------------------------------------------------------------
# Plan XIX: Action Center — list interventions, approve/dismiss
# GET /api/v1/intervention/action-center  -> list ongoing interventions with risk
# PATCH /api/v1/intervention/action-center/<id>  -> dismiss or resolve
# ---------------------------------------------------------------------------
class InterventionActionCenterView(View):
    """GET /api/v1/intervention/action-center - List interventions for Action Center (approve/dismiss)."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.analytics.models import InterventionLog, RiskFactor, get_risk_band_for_school
        status_filter = (request.GET.get("status") or "ONGOING").strip().upper()
        if status_filter == "ALL":
            qs = InterventionLog.objects.filter(school=school)
        else:
            qs = InterventionLog.objects.filter(school=school, status=status_filter)
        qs = qs.select_related("student", "student__user").order_by("-created_at")[:100]
        items = []
        for log in qs:
            risk = RiskFactor.objects.filter(school=school, student=log.student).order_by("-computed_at").first()
            risk_band = get_risk_band_for_school(risk.score, school) if risk else None
            items.append({
                "id": log.id,
                "student_id": log.student_id,
                "trigger_reason": log.trigger_reason,
                "action_taken": log.action_taken,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "draft_email_subject": log.draft_email_subject or "",
                "draft_email_body": (log.draft_email_body or "")[:500],
                "meeting_link": log.meeting_link or "",
                "risk_score": float(risk.score) if risk else None,
                "risk_band": risk_band,
            })
        return JsonResponse({"count": len(items), "interventions": items})


@method_decorator(require_http_methods(["PATCH"]), name="dispatch")
class InterventionActionCenterDetailView(View):
    """PATCH /api/v1/intervention/action-center/<id> - Dismiss or resolve an intervention."""

    def patch(self, request, id):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}
        from apps.analytics.models import InterventionLog
        from django.utils import timezone
        log = get_object_or_404(InterventionLog, pk=id, school=school)
        action = (data.get("action") or "dismiss").strip().lower()
        if action == "dismiss":
            log.status = InterventionLog.Status.DISMISSED
            log.dismissed_at = timezone.now()
            log.dismissed_by = request.user
        elif action == "resolve":
            log.status = InterventionLog.Status.RESOLVED
            log.resolved_at = timezone.now()
        else:
            return JsonResponse({"error": "action must be dismiss or resolve"}, status=400)
        log.save(update_fields=["status", "dismissed_at", "dismissed_by", "resolved_at"])
        return JsonResponse({"ok": True, "id": log.id, "status": log.status})


# ---------------------------------------------------------------------------
# POST /api/v1/intervention/generate-roadmap  -> LLM recovery roadmap (stub)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class InterventionGenerateRoadmapView(View):
    """POST /api/v1/intervention/generate-roadmap - Generate recovery roadmap for student (LLM)."""

    def post(self, request):
        if not _backend_flag_enabled("enable_intervention_llm_roadmap"):
            return JsonResponse({"error": "Intervention roadmap is not enabled."}, status=404)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        student_id = data.get("student_id")
        if not student_id:
            return JsonResponse({"error": "student_id required"}, status=400)
        try:
            from apps.analytics.models import RiskFactor
            from apps.people.models import StudentProfile
            student = StudentProfile.objects.get(id=student_id, school=school)
            risk = RiskFactor.objects.filter(school=school, student=student).order_by("-computed_at").first()
            summary = risk.reason_summary if risk else "No risk data"
            roadmap = {"student_id": student_id, "summary": summary, "suggestions": ["Schedule 1-on-1 with teacher", "Assign remedial module"], "status": "draft"}
            return JsonResponse(roadmap, status=200)
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student not found"}, status=404)
        except Exception as e:
            logger.exception("intervention/generate-roadmap")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# POST /api/v1/enrollment/apply  -> public application (alias to lead capture)
# ---------------------------------------------------------------------------
@method_decorator(csrf_exempt, name="dispatch")
class EnrollmentApplyView(View):
    """POST /api/v1/enrollment/apply - Public application submission (delegates to lead capture)."""

    def post(self, request):
        from apps.api.lead_capture_api import LeadCaptureAPI
        return LeadCaptureAPI.as_view()(request)


# ---------------------------------------------------------------------------
# POST /api/v1/attendance/bulk  -> bulk attendance (alias)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class AttendanceBulkView(View):
    """POST /api/v1/attendance/bulk - Bulk mark attendance."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        records = data.get("records", data.get("attendances", []))
        if not records:
            return JsonResponse({"error": "records required (list of {student_id, status} or {student, status})"}, status=400)
        classroom_id = data.get("classroom_id")
        if not classroom_id:
            return JsonResponse({"error": "classroom_id required for bulk attendance"}, status=400)
        from apps.academics.models import Attendance
        from django.utils import timezone
        from datetime import datetime
        date_str = data.get("date") or timezone.now().date().isoformat()
        try:
            if isinstance(date_str, str) and "T" in date_str:
                attend_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            else:
                attend_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            attend_date = timezone.now().date()
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        created = []
        for r in records:
            student_id = r.get("student_id") or r.get("student")
            status = (r.get("status") or "present").strip().lower()
            if not student_id:
                continue
            att, _ = Attendance.objects.update_or_create(
                school=school,
                student_id=student_id,
                classroom_id=classroom_id,
                date=attend_date,
                defaults={"status": status},
            )
            created.append({"student_id": student_id, "status": att.status})
        return JsonResponse({"ok": True, "count": len(created), "records": created}, status=201)


# ---------------------------------------------------------------------------
# GET /api/v1/attendance/export  -> CSV export
# ---------------------------------------------------------------------------
class AttendanceExportView(View):
    """GET /api/v1/attendance/export - Export attendance as CSV (?date_from=&date_to=&classroom_id=)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        import csv
        from io import StringIO
        from datetime import timedelta
        from django.utils import timezone
        from apps.academics.models import Attendance
        date_from = request.GET.get("date_from") or (timezone.now().date() - timedelta(days=30)).isoformat()
        date_to = request.GET.get("date_to") or timezone.now().date().isoformat()
        classroom_id = request.GET.get("classroom_id")
        qs = Attendance.objects.filter(school=school, date__gte=date_from, date__lte=date_to).select_related("student", "classroom")
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        qs = qs.order_by("date", "classroom", "student")[:5000]
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(["date", "student_id", "student_name", "classroom_id", "classroom_name", "status", "remarks"])
        for a in qs:
            w.writerow([
                a.date.isoformat() if a.date else "",
                a.student_id,
                getattr(a.student, "display_name", None) or getattr(a.student, "admission_number", None) or "",
                a.classroom_id,
                getattr(a.classroom, "name", None) or "",
                a.status,
                (a.remarks or "")[:255],
            ])
        from django.http import HttpResponse
        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="attendance_export.csv"'
        return resp


# ---------------------------------------------------------------------------
# POST /api/v1/vocational/log-hours  -> clock in/out hours
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class VocationalLogHoursView(View):
    """POST /api/v1/vocational/log-hours - Log vocational/workshop hours."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        student_id = data.get("student_id")
        subject_assignment_id = data.get("subject_assignment_id")
        hours = data.get("hours")
        activity_description = (data.get("activity_description") or data.get("description") or "")[:255]
        date_str = data.get("date")
        if not all([student_id, subject_assignment_id, hours]):
            return JsonResponse({"error": "student_id, subject_assignment_id, hours required"}, status=400)
        from django.utils import timezone
        from datetime import datetime
        log_date = timezone.now().date()
        if date_str:
            try:
                log_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
        try:
            from apps.evals.models_enhanced import ClockHourTracking
            from apps.people.models import TeacherProfile
            teacher = getattr(request.user, "teacher_profile", None)
            rec = ClockHourTracking.objects.create(
                student_id=student_id,
                subject_assignment_id=subject_assignment_id,
                date=log_date,
                hours=hours,
                activity_description=activity_description or "Logged",
                recorded_by=teacher,
            )
            return JsonResponse({"ok": True, "id": rec.id, "hours": str(rec.hours), "date": rec.date.isoformat()}, status=201)
        except Exception as e:
            logger.exception("vocational/log-hours")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# PATCH /api/v1/vocational/verify-skill  -> instructor sign-off on competency
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["PATCH"]), name="dispatch")
class VocationalVerifySkillView(View):
    """PATCH /api/v1/vocational/verify-skill - Verify/sign off a skill for a student."""

    def patch(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        student_id = data.get("student_id")
        competency_item_id = data.get("competency_item_id")
        level = (data.get("level") or "PROFICIENT").strip().upper()
        observations = (data.get("observations") or "")[:500]
        if not all([student_id, competency_item_id]):
            return JsonResponse({"error": "student_id, competency_item_id required"}, status=400)
        try:
            from apps.evals.models_enhanced import StudentCompetencyAssessment, CompetencyItem, CompetencyRubric
            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return JsonResponse({"error": "Teacher profile required"}, status=403)
            item = CompetencyItem.objects.get(pk=competency_item_id)
            valid_levels = [c[0] for c in CompetencyRubric.CompetencyLevel.choices]
            if level not in valid_levels:
                level = "PROFICIENT"
            rec = StudentCompetencyAssessment.objects.create(
                student_id=student_id,
                competency_item_id=competency_item_id,
                teacher=teacher,
                level=level,
                observations=observations,
            )
            return JsonResponse({"ok": True, "id": rec.id, "level": rec.level})
        except CompetencyItem.DoesNotExist:
            return JsonResponse({"error": "Competency item not found"}, status=404)
        except Exception as e:
            logger.exception("vocational/verify-skill")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/vocational/digital-badge/{student_id}  -> shareable skills summary
# ---------------------------------------------------------------------------
class VocationalDigitalBadgeView(View):
    """GET /api/v1/vocational/digital-badge/<student_id> - Shareable skills summary for employers."""

    def get(self, request, student_id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            from apps.evals.models_enhanced import StudentCompetencyAssessment
            from apps.people.models import StudentProfile
            student = StudentProfile.objects.get(pk=student_id, school=school)
            assessments = StudentCompetencyAssessment.objects.filter(
                student=student
            ).select_related("competency_item", "competency_item__rubric").order_by("-assessed_at")
            skills = [{"name": a.competency_item.name, "level": a.level, "assessed_at": a.assessed_at.isoformat() if a.assessed_at else None} for a in assessments[:50]]
            return JsonResponse({"student_id": student_id, "skills": skills, "school_id": str(school.id)})
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student not found"}, status=404)
        except Exception as e:
            logger.exception("vocational/digital-badge")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# POST /api/v1/scheduler/generate  -> generate draft schedule
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class SchedulerGenerateView(View):
    """POST /api/v1/scheduler/generate - Trigger constraint-based schedule generation."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            data = {}
        term_id = data.get("term_id")
        academic_year_id = data.get("academic_year_id")
        if not term_id or not academic_year_id:
            return JsonResponse({"error": "term_id and academic_year_id required"}, status=400)
        try:
            from apps.academics.scheduling import ScheduleGenerator
            from apps.academics.models import Term, AcademicYear
            term = Term.objects.get(pk=term_id, academic_year_id=academic_year_id)
            year = AcademicYear.objects.get(pk=academic_year_id)
            gen = ScheduleGenerator(academic_year=year, term=term)
            schedule = gen.generate_schedule(created_by=request.user)
            return JsonResponse({"ok": True, "schedule_id": schedule.id, "status": schedule.status}, status=202)
        except (Term.DoesNotExist, AcademicYear.DoesNotExist) as e:
            return JsonResponse({"error": "Term or academic year not found"}, status=404)
        except Exception as e:
            logger.exception("scheduler/generate")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/scheduler/validate  -> conflict check
# ---------------------------------------------------------------------------
class SchedulerValidateView(View):
    """GET /api/v1/scheduler/validate - Real-time conflict check (schedule_id or teacher_id/room_id/time_slot)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        schedule_id = request.GET.get("schedule_id")
        if schedule_id:
            try:
                from apps.academics.scheduling import ScheduleGenerator
                from apps.academics.models import Schedule
                schedule = Schedule.objects.get(pk=schedule_id)
                gen = ScheduleGenerator(academic_year=schedule.academic_year, term=schedule.term)
                conflicts = gen.detect_conflicts(schedule)
                if conflicts:
                    return JsonResponse({"valid": False, "conflicts": conflicts}, status=409)
                return JsonResponse({"valid": True, "conflicts": []})
            except Schedule.DoesNotExist:
                return JsonResponse({"error": "Schedule not found"}, status=404)
        return JsonResponse({"error": "schedule_id required"}, status=400)


# ---------------------------------------------------------------------------
# GET /api/v1/vocational/certifications-expiring  -> watchdog (e.g. 30 days)
# ---------------------------------------------------------------------------
class VocationalCertificationsExpiringView(View):
    """GET /api/v1/vocational/certifications-expiring - Certifications expiring within N days."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        days = int(request.GET.get("days", 30))
        from datetime import timedelta
        from django.utils import timezone
        from apps.people.models import VocationalCertification
        today = timezone.now().date()
        end = today + timedelta(days=days)
        qs = VocationalCertification.objects.filter(
            school=school,
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=end,
        ).select_related("student").order_by("expiry_date")
        items = [{"id": c.id, "student_id": c.student_id, "name": c.name, "expiry_date": c.expiry_date.isoformat()} for c in qs]
        return JsonResponse({"count": len(items), "days": days, "certifications": items})


# ---------------------------------------------------------------------------
# GET /api/v1/syllabus/pacing  -> planned vs actual progress (e.g. 70% IGCSE Math)
# ---------------------------------------------------------------------------
class SyllabusPacingView(View):
    """GET /api/v1/syllabus/pacing - Planned vs actual curriculum coverage (?subject_assignment_id=)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        sa_id = request.GET.get("subject_assignment_id")
        if not sa_id:
            return JsonResponse({"error": "subject_assignment_id required"}, status=400)
        try:
            from apps.academics.models import CourseSyllabus
            syllabus = CourseSyllabus.objects.filter(subject_assignment_id=sa_id).first()
            if not syllabus:
                return JsonResponse({"subject_assignment_id": sa_id, "planned_pct": 0, "actual_pct": 0, "message": "No syllabus"})
            builder = getattr(syllabus, "builder_data", None) or {}
            sections = builder.get("sections") or builder.get("topics") or []
            total = len(sections)
            completed = sum(1 for s in sections if isinstance(s, dict) and s.get("completed")) if total else 0
            actual_pct = round(100 * completed / total, 1) if total else 0
            return JsonResponse({"subject_assignment_id": sa_id, "planned_pct": 100, "actual_pct": actual_pct, "total_topics": total, "completed_topics": completed})
        except Exception as e:
            logger.exception("syllabus/pacing")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/pulse  -> Global Pulse Map data
# ---------------------------------------------------------------------------
class SuperPulseView(View):
    """GET /api/v1/super/pulse - Tenants, student counts, global revenue for pulse map."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({"error": "Superuser required"}, status=403)
        from django.db.models import Count, Sum
        from django.utils import timezone
        from apps.schools.models import School
        from apps.siteconfig.models import RevenueSnapshot
        schools = list(
            School.objects.filter(is_active=True)
            .annotate(student_count=Count("student_profiles", distinct=True))
            .values("id", "name", "slug", "subdomain", "default_region_id", "student_count", "last_activity")
        )
        first_of_month = timezone.now().date().replace(day=1)
        try:
            snapshots = RevenueSnapshot.objects.filter(snapshot_date=first_of_month).aggregate(total=Sum("actual_revenue"), waived=Sum("waived_amount"))
            total_revenue = (snapshots["total"] or 0) + (snapshots["waived"] or 0)
        except Exception:
            total_revenue = 0
        by_country = list(
            School.objects.filter(is_active=True)
            .values("default_region_id")
            .annotate(school_count=Count("id"), student_count=Count("student_profiles", distinct=True))
        )
        return JsonResponse({
            "tenants": schools,
            "total_students": sum(s["student_count"] for s in schools),
            "total_revenue": total_revenue,
            "by_country": by_country,
        })


# ---------------------------------------------------------------------------
# Plan X: Super-Admin usage & billing dashboard
# GET /api/v1/super/usage  -> per-school usage for Stripe/billing
# ---------------------------------------------------------------------------
class SuperUsageView(View):
    """GET /api/v1/super/usage - Per-tenant usage for system billing and health dashboard."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({"error": "Superuser required"}, status=403)
        from django.db.models import Count, Sum
        from apps.schools.models import School, TenantApiUsage, TenantQuotaLimit
        schools_qs = School.objects.filter(is_active=True).annotate(
            student_count=Count("student_profiles", distinct=True),
            staff_count=Count("memberships", distinct=True),
        )
        schools = list(schools_qs.values("id", "name", "slug", "student_count", "staff_count", "last_activity", "created_at"))
        school_ids = [s["id"] for s in schools]
        usage_by_school = {
            (r["school_id"], r["limit_type"]): r["request_count"]
            for r in TenantApiUsage.objects.filter(school_id__in=school_ids).values("school_id", "limit_type").annotate(
                request_count=Sum("request_count")
            )
        }
        quotas_by_school = {}
        for q in TenantQuotaLimit.objects.filter(school_id__in=school_ids, is_active=True).values("school_id", "limit_type", "limit_value", "period_days"):
            quotas_by_school.setdefault(q["school_id"], []).append(
                {"limit_type": q["limit_type"], "limit_value": q["limit_value"], "period_days": q["period_days"]}
            )
        for s in schools:
            s["school_id"] = str(s["id"])
            s["last_activity"] = s["last_activity"].isoformat() if s.get("last_activity") else None
            s["created_at"] = s["created_at"].isoformat() if s.get("created_at") else None
            sid = s["id"]
            s["api_usage"] = {k: v for (sch_id, k), v in usage_by_school.items() if sch_id == sid}
            s["quota_limits"] = quotas_by_school.get(sid, [])
        return JsonResponse({"schools": schools, "total_schools": len(schools)})


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/recovery-rate  -> System-Saved Students metric
# ---------------------------------------------------------------------------
class SuperRecoveryRateView(View):
    """GET /api/v1/super/recovery-rate - Share of Red students moved back to Green after interventions."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({"error": "Superuser required"}, status=403)
        try:
            from apps.analytics.models import RiskFactor, InterventionLog
            from django.db.models import Count
            red_count = RiskFactor.objects.filter(score__gte=80).values("student_id", "school_id").distinct().count()
            resolved = InterventionLog.objects.filter(status=InterventionLog.Status.RESOLVED).count()
            total_interventions = InterventionLog.objects.count()
            recovery_rate_pct = round(100 * resolved / total_interventions, 1) if total_interventions else 0
            return JsonResponse({
                "red_students_count": red_count,
                "interventions_resolved": resolved,
                "interventions_total": total_interventions,
                "recovery_rate_pct": recovery_rate_pct,
            })
        except Exception as e:
            logger.exception("super/recovery-rate")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/tenant-health  -> Per-tenant health (last_activity, etc.)
# ---------------------------------------------------------------------------
class SuperTenantHealthView(View):
    """GET /api/v1/super/tenant-health - Tenant Health Monitor: last_activity, status per school."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.is_superuser:
            return JsonResponse({"error": "Superuser required"}, status=403)
        from apps.schools.models import School
        from django.db.models import Count
        schools = list(
            School.objects.all()
            .annotate(student_count=Count("student_profiles", distinct=True))
            .values("id", "name", "slug", "is_active", "is_approved", "last_activity", "student_count")
        )
        for s in schools:
            s["last_activity"] = s["last_activity"].isoformat() if s.get("last_activity") else None
        return JsonResponse({"tenants": schools})


# ---------------------------------------------------------------------------
# Plan XVII: Risk thresholds (Amber/Red) per tenant
# GET /api/v1/config/risk-thresholds  -> read amber_min, red_min
# PATCH /api/v1/config/risk-thresholds  -> update (admin)
# ---------------------------------------------------------------------------
class RiskThresholdsConfigView(View):
    """GET/PATCH /api/v1/config/risk-thresholds - Per-tenant risk band thresholds for Action Center."""

    def get(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.analytics.models import RiskThresholds
        try:
            th = RiskThresholds.objects.get(school=school)
            return JsonResponse({
                "amber_min": float(th.amber_min),
                "red_min": float(th.red_min),
                "updated_at": th.updated_at.isoformat() if th.updated_at else None,
            })
        except RiskThresholds.DoesNotExist:
            return JsonResponse({"amber_min": 50.0, "red_min": 80.0, "updated_at": None})

    def patch(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        allowed, err = _require_super_or_school(request)
        if not allowed:
            return err
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        from apps.analytics.models import RiskThresholds
        from decimal import Decimal
        th, _ = RiskThresholds.objects.get_or_create(school=school, defaults={"amber_min": Decimal("50"), "red_min": Decimal("80")})
        if "amber_min" in data:
            try:
                th.amber_min = Decimal(str(data["amber_min"]))
            except (TypeError, ValueError):
                pass
        if "red_min" in data:
            try:
                th.red_min = Decimal(str(data["red_min"]))
            except (TypeError, ValueError):
                pass
        th.save()
        return JsonResponse({
            "amber_min": float(th.amber_min),
            "red_min": float(th.red_min),
            "updated_at": th.updated_at.isoformat() if th.updated_at else None,
        })


# ---------------------------------------------------------------------------
# Plan XII: GDPR "Export my school data"
# POST /api/v1/compliance/export-school  -> trigger full school data export (admin)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class ComplianceExportSchoolView(View):
    """POST /api/v1/compliance/export-school - Request full school data export (GDPR-style). Returns summary or job_id."""

    def post(self, request):
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from django.db.models import Count
        from apps.people.models import StudentProfile
        from apps.finance.models import Invoice, Payment
        students_count = StudentProfile.objects.filter(school=school).count()
        invoices_count = Invoice.objects.filter(school=school).count()
        payments_count = Payment.objects.filter(invoice__school=school).count()
        return JsonResponse({
            "ok": True,
            "school_id": str(school.id),
            "export_scope": "full_school",
            "summary": {
                "students": students_count,
                "invoices": invoices_count,
                "payments": payments_count,
            },
            "message": "Use per-student data portability (compliance/data-portability) for detailed export.",
        })


# ---------------------------------------------------------------------------
# Plan XVII: Enrollment forecasting stub
# GET /api/v1/enrollment/forecast  -> projected enrollment (stub)
# ---------------------------------------------------------------------------
class EnrollmentForecastView(View):
    """GET /api/v1/enrollment/forecast - Projected enrollment by term/class (stub)."""

    def get(self, request):
        if not _backend_flag_enabled("enable_enrollment_forecast_api"):
            return JsonResponse({"error": "Enrollment forecast is not enabled."}, status=404)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.people.models import StudentProfile
        from django.db.models import Count
        current = StudentProfile.objects.filter(school=school, is_active=True).count()
        return JsonResponse({
            "current_enrollment": current,
            "forecasts": [],
            "message": "Forecast model can be wired to historical enrollment and term start dates.",
        })


# ---------------------------------------------------------------------------
# Rosetta Stone: cross-tenant / cross-system grade conversion (Plan III, XXI)
# GET /api/v1/rosetta/convert  GET /api/v1/rosetta/scales
# ---------------------------------------------------------------------------
class RosettaConvertView(View):
    """GET /api/v1/rosetta/convert - Convert grade between scales (normalized 0-1 anchor). Frictionless global student mobility."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.api.rosetta_views import RosettaStoneConvertAPI
        return RosettaStoneConvertAPI.as_view()(request)


class RosettaScalesView(View):
    """GET /api/v1/rosetta/scales - List supported grading scale ids for conversion."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.api.rosetta_views import RosettaStoneScalesAPI
        return RosettaStoneScalesAPI.as_view()(request)


# ---------------------------------------------------------------------------
# Parent Wallet top-up (Plan V)
# POST /api/v1/finance/wallet/top-up
# ---------------------------------------------------------------------------
@method_decorator(csrf_exempt, name="dispatch")
class FinanceWalletTopUpView(View):
    """POST /api/v1/finance/wallet/top-up - Credit parent wallet. Body: { \"amount\": \"100.00\", \"reference\": \"optional\" }."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        amount = data.get("amount")
        if amount is None:
            return JsonResponse({"error": "amount required"}, status=400)
        try:
            from apps.finance.services import top_up_wallet
            wallet, txn = top_up_wallet(
                school=school,
                user=request.user,
                amount=amount,
                reference=data.get("reference"),
            )
            return JsonResponse({
                "ok": True,
                "wallet_balance": str(wallet.balance),
                "currency_code": wallet.currency_code,
                "transaction_id": txn.id,
                "reference": txn.reference,
            }, status=201)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)


# ---------------------------------------------------------------------------
# Regulatory Export / MoE presets (Plan IV)
# GET /api/v1/reports/regulatory-presets  POST /api/v1/reports/regulatory-export
# ---------------------------------------------------------------------------
class RegulatoryPresetsView(View):
    """GET /api/v1/reports/regulatory-presets - List MoE/regulatory export presets (WAEC, Bulletin, Ofsted, etc.)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        from apps.reports.moe_presets import get_moe_presets
        return JsonResponse({"presets": get_moe_presets()})


class RegulatoryExportView(View):
    """POST /api/v1/reports/regulatory-export - Generate regulatory PDF by preset_id. Body: { preset_id, academic_year_id?, term_id? }."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        preset_id = (data.get("preset_id") or "").strip()
        if not preset_id:
            return JsonResponse({"error": "preset_id required (e.g. waec, bulletin_fr, ofsted)"}, status=400)
        from apps.reports.moe_presets import get_moe_preset
        preset = get_moe_preset(preset_id)
        if not preset:
            return JsonResponse({"error": f"Unknown preset_id: {preset_id}"}, status=400)
        academic_year_id = data.get("academic_year_id")
        term_id = data.get("term_id")
        try:
            from apps.reports.services import build_regulatory_export
            result = build_regulatory_export(school, preset_id, academic_year_id=academic_year_id, term_id=term_id)
            if result.get("pdf_url"):
                return JsonResponse({"ok": True, "download_url": result["pdf_url"], "preset_id": preset_id})
            if result.get("job_id"):
                return JsonResponse({"ok": True, "job_id": result["job_id"], "message": "Export queued.", "preset_id": preset_id})
            return JsonResponse({"ok": True, **result, "preset_id": preset_id})
        except Exception as e:
            if "build_regulatory_export" in str(e) or "build_regulatory_export" in str(type(e)):
                return JsonResponse({
                    "ok": False,
                    "error": "Regulatory export not fully implemented for this preset.",
                    "preset_id": preset_id,
                    "hint": "Use reports app and template_family from preset.",
                }, status=501)
            logger.exception("regulatory-export")
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# PATCH /api/v1/attendance/bulk-update  -> bulk update attendance (Plan II)
# ---------------------------------------------------------------------------
@method_decorator(csrf_exempt, name="dispatch")
class AttendanceBulkUpdateView(View):
    """PATCH /api/v1/attendance/bulk-update - Bulk update attendance records. Body: { \"records\": [ { \"id\": <id>, \"status\": \"present\" } or { \"student\", \"classroom\", \"date\", \"status\" } ] }."""

    def patch(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        try:
            data = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        records = data.get("records", [])
        if not records:
            return JsonResponse({"error": "records required"}, status=400)
        from apps.academics.models import Attendance
        from datetime import datetime
        from django.utils import timezone
        role = (getattr(request.user, "role", "") or "").upper()
        allowed = {"TEACHER", "ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN", "CENSOR"}
        if role not in allowed and not request.user.is_staff:
            return JsonResponse({"error": "Permission denied"}, status=403)
        base_qs = Attendance.objects.filter(school=school)
        updated = 0
        for rec in records:
            pk = rec.get("id")
            if pk is not None:
                att = base_qs.filter(pk=pk).first()
                if att and "status" in rec:
                    att.status = rec["status"]
                    if "remarks" in rec:
                        att.remarks = str(rec["remarks"])[:255]
                    att.save()
                    updated += 1
                continue
            sid, cid, date_str = rec.get("student"), rec.get("classroom"), rec.get("date")
            if sid is None or cid is None or not date_str or "status" not in rec:
                continue
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            att, _ = Attendance.objects.update_or_create(
                school=school, student_id=sid, classroom_id=cid, date=dt,
                defaults={"status": rec["status"], "remarks": (rec.get("remarks") or "")[:255]},
            )
            updated += 1
        return JsonResponse({"ok": True, "updated": updated})
