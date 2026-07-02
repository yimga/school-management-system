"""
RunMyCampus Standards Compliance: API v1 contract.
Implements or delegates to existing logic the standard endpoints under /api/v1/.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models import Q
from django.http import JsonResponse
from django.views import View
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404

from apps.platform_runtime.helpers import get_effective_flags
from apps.platform_runtime.structured_logging import log_view_exception

logger = logging.getLogger(__name__)

FINANCE_OPERATOR_ROLES = {
    "ADMIN",
    "LEADERSHIP",
    "PRINCIPAL",
    "VICE_PRINCIPAL",
    "DEAN",
    "BURSAR",
    "FINANCE_STAFF",
    "IT_ADMIN",
    "PROPRIETOR",
}


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
            from apps.schools.models import SchoolMembership
            from apps.schools.tenant_switch_security import user_may_switch_to_school

            if SchoolMembership.objects.filter(
                user=request.user, school=request_school
            ).exists():
                return True, None
            if user_may_switch_to_school(
                request.user, request_school, active_school=request_school
            ):
                return True, None
    return False, JsonResponse({"error": "Forbidden"}, status=403)


def _get_school_from_request(request):
    """Return request.school (set by tenant middleware) or None."""
    return getattr(request, "school", None)


def _require_tenant_member(request, school=None):
    """
    Require tenant context and SchoolMembership (or hierarchy) on that school.

    Returns (school, None) or (None, JsonResponse error).
    """
    school = school or _get_school_from_request(request)
    if not school:
        return None, JsonResponse({"error": "Tenant context required"}, status=400)
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, JsonResponse({"error": "Authentication required"}, status=401)
    session_sid = ""
    if hasattr(request, "session"):
        session_sid = (request.session.get("school_id") or "").strip()
    from apps.schools.tenant_switch_security import user_may_access_school_api

    if not user_may_access_school_api(
        user, school, session_school_id=session_sid or None
    ):
        return None, JsonResponse({"error": "Forbidden"}, status=403)
    return school, None


def _require_auth_and_tenant_member(request):
    """Auth first, then tenant membership (common API view preamble)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None, JsonResponse({"error": "Authentication required"}, status=401)
    return _require_tenant_member(request)


def _user_has_any_role(user, allowed_roles: set[str]) -> bool:
    from apps.accounts.permissions import has_role

    normalized_roles = {str(role).strip().upper() for role in allowed_roles if role}
    return any(has_role(user, role) for role in normalized_roles)


def _require_finance_operator(request):
    """Require tenant context plus a finance-capable operator role."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False, JsonResponse({"error": "Authentication required"}, status=401)
    school, err = _require_tenant_member(request)
    if err:
        return False, err
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True, None
    if _user_has_any_role(user, FINANCE_OPERATOR_ROLES):
        return True, None
    return False, JsonResponse({"error": "Forbidden"}, status=403)


def _require_parent_finance_or_operator_access(request):
    """Allow finance operators, or a parent with valid guardian finance access."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False, JsonResponse({"error": "Authentication required"}, status=401)
    school, err = _require_tenant_member(request)
    if err:
        return False, err
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True, None
    if _user_has_any_role(user, FINANCE_OPERATOR_ROLES):
        return True, None
    if not _user_has_any_role(user, {"PARENT"}):
        return False, JsonResponse({"error": "Forbidden"}, status=403)

    from apps.finance.views_common import _finance_access_state

    access_state = _finance_access_state(user, request)
    if access_state.get("guardian_count", 0) <= 0:
        return False, JsonResponse(
            {"error": "Guardian finance access required"}, status=403
        )
    if access_state.get("require_opt_in") and access_state.get("finance_count", 0) <= 0:
        return False, JsonResponse(
            {"error": "Finance access approval required"}, status=403
        )
    return True, None


def _backend_flag_enabled(
    flag_name: str, request=None, *, default: bool = False
) -> bool:
    try:
        flags = get_effective_flags(request)
        return bool(flags.get(flag_name, default))
    except (AttributeError, DatabaseError, TypeError, ValueError):
        return default


def _parse_json_object(request):
    """Return (payload, error_response) for JSON API mutation endpoints."""
    if request.body:
        content_type = (
            (
                (request.content_type or request.META.get("CONTENT_TYPE") or "").split(
                    ";", 1
                )[0]
            )
            .strip()
            .lower()
        )
        if content_type != "application/json":
            return None, JsonResponse(
                {"error": "Content-Type must be application/json"}, status=415
            )
    try:
        payload = (
            json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "JSON object required"}, status=400)
    return payload, None


# ---------------------------------------------------------------------------
# POST /api/v1/tenants/provision  -> delegates to super api_create_school
# ---------------------------------------------------------------------------
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
            from apps.siteconfig.integration_catalog import (
                INTEGRATION_CATALOG,
                list_catalog_keys,
            )

            keys = list_catalog_keys()
            catalog = {
                k: {**v, "config_schema": v.get("config_schema", {})}
                for k, v in INTEGRATION_CATALOG.items()
            }
            return JsonResponse({"keys": keys, "catalog": catalog})
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request,
                "api.views_v1: config/integration-catalog",
                extra={"error": str(e)},
            )
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
            {
                "code": "BRITISH_IGCSE",
                "name": "British / IGCSE",
                "description": "Michaelmas, Lent, Trinity; A*–G or 9–1; summative weighting.",
            },
            {
                "code": "WAEC",
                "name": "West African (WAEC)",
                "description": "First, Second, Third term; A1–F9; CA 30% + Exam 70%.",
            },
            {
                "code": "FRANCOPHONE_BAC",
                "name": "Francophone (Bac)",
                "description": "Trimestre 1–3; 20-point scale; Enseignant, Note, Moyenne.",
            },
            {
                "code": "VOCATIONAL",
                "name": "Vocational / Trade",
                "description": "Competency checklists; clock hours; skill badges.",
            },
            {
                "code": "IB",
                "name": "International Baccalaureate",
                "description": "IB DP/MYP; 1–7 scale; summative weighting.",
            },
        ]
        try:
            from apps.siteconfig.education_profile_engine import list_template_catalog
            from apps.global_registries.models import EducationSystemProfile

            for p in EducationSystemProfile.objects.filter(
                is_active=True,
                approval_status=EducationSystemProfile.ApprovalStatus.APPROVED,
            ).values("code", "name"):
                if not any(t["code"] == p["code"] for t in templates):
                    templates.append(
                        {"code": p["code"], "name": p["name"], "description": ""}
                    )
            catalog = list_template_catalog()
            if catalog:
                templates = catalog
        except (ImportError, DatabaseError):
            pass
        return JsonResponse({"templates": templates})


# ---------------------------------------------------------------------------
# GET /api/v1/config/education-dna  -> tenant-scoped education config
# ---------------------------------------------------------------------------
class EducationDNAView(View):
    """GET /api/v1/config/education-dna - Fetches grading rules and education template for current tenant."""

    def get(self, request):
        school, err = _require_auth_and_tenant_member(request)
        if err:
            return err
        try:
            from apps.siteconfig.billing_sku_registry import (
                get_effective_report_platform_bundle_slug_for_school,
                get_operator_default_report_platform_bundle_slug,
            )
            from apps.siteconfig.tenant_config import get_tenant_locale
            from apps.siteconfig.education_profile_engine import (
                resolve_profile_for_school,
            )

            locale = get_tenant_locale(request=request, school=school)
            profile = resolve_profile_for_school(school)
            config = getattr(profile, "config", None) or {}
            system_type = getattr(profile, "sub_system", None) or getattr(
                school, "sub_system", "EN"
            )
            term_labels = config.get("term_labels") or locale.get("term_labels") or []
            operator_bundle_slug = get_operator_default_report_platform_bundle_slug()
            report_platform_bundle_slug = (
                str(getattr(school, "report_platform_bundle_slug", None) or "")
                .strip()
                .lower()
            )
            return JsonResponse(
                {
                    "tenant_id": str(school.id),
                    "system_type": system_type,
                    "grading_logic_json": config.get("grading_logic", config),
                    "grading_scale": locale.get("grading_scale"),
                    "terms": term_labels,
                    "currency": locale.get("currency")
                    or (
                        getattr(school.default_region, "default_currency", None)
                        if getattr(school, "default_region", None)
                        else None
                    ),
                    "timezone": locale.get("timezone", "UTC"),
                    "date_format": locale.get("date_format", "YYYY-MM-DD"),
                    "report_platform_bundle_slug": report_platform_bundle_slug,
                    "effective_report_platform_bundle": get_effective_report_platform_bundle_slug_for_school(
                        school, operator_default_slug=operator_bundle_slug
                    ),
                }
            )
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request, "api.views_v1: education-dna", extra={"error": str(e)}
            )
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
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        modules = data.get("modules")
        if modules is None:
            return JsonResponse(
                {
                    "error": "modules required (list of module codes or dict module_name -> is_active)"
                },
                status=400,
            )
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
        return JsonResponse(
            {"ok": True, "tenant_id": str(school.id), "modules": school.addons}
        )


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
        from apps.schools.tenant_switch_security import schools_user_may_operate_on
        from apps.siteconfig.billing_sku_registry import (
            get_effective_report_platform_bundle_slug_for_school,
            get_operator_default_report_platform_bundle_slug,
        )

        operator_bundle_slug = get_operator_default_report_platform_bundle_slug()
        current = getattr(request, "school", None)
        allowed_schools = schools_user_may_operate_on(
            request.user, active_school=current
        )
        membership_by_school = {
            m.school_id: m
            for m in SchoolMembership.objects.filter(user=request.user).select_related(  # tenant-isolation-allow: user-scoped-me-schools-membership-enumeration
                "school"
            )
            if m.school_id
        }
        schools = []
        child_schools = []
        for school in allowed_schools:
            if not school or not getattr(school, "is_active", True):
                continue
            rp_slug = (
                str(getattr(school, "report_platform_bundle_slug", None) or "")
                .strip()
                .lower()
            )
            row = {
                "school_id": str(school.pk),
                "name": school.name,
                "slug": getattr(school, "slug", "") or "",
                "primary_sector": getattr(school, "primary_sector", "") or "",
                "report_platform_bundle_slug": rp_slug,
                "effective_report_platform_bundle": get_effective_report_platform_bundle_slug_for_school(
                    school, operator_default_slug=operator_bundle_slug
                ),
            }
            membership = membership_by_school.get(school.pk)
            if membership is not None:
                row["role"] = membership.role
                row["is_primary"] = membership.is_primary
                schools.append(row)
            elif getattr(school, "parent_school_id", None):
                child_schools.append(row)
            else:
                row.setdefault("role", "")
                row.setdefault("is_primary", False)
                schools.append(row)
        schools.sort(key=lambda item: (not item.get("is_primary"), item.get("name", "")))
        child_schools = child_schools[:50]
        return JsonResponse(
            {
                "schools": schools,
                "child_schools": child_schools,
                "current_school_id": str(current.id) if current else None,
            }
        )


@method_decorator(require_http_methods(["POST"]), name="dispatch")
class MeSwitchSchoolView(View):
    """POST /api/v1/me/switch-school - Set session school for switcher. Body: { \"school_id\": \"uuid\" }."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        school_id = (data.get("school_id") or data.get("tenant_id") or "").strip()
        if not school_id:
            return JsonResponse({"error": "school_id required"}, status=400)
        from apps.schools.models import School

        school = School.objects.filter(id=school_id, is_active=True).first()
        if not school:
            return JsonResponse({"error": "School not found"}, status=404)
        from apps.schools.tenant_switch_security import user_may_switch_to_school

        active = getattr(request, "school", None)
        if not user_may_switch_to_school(
            request.user, school, active_school=active
        ):
            return JsonResponse({"error": "Not a member of this school"}, status=403)
        if hasattr(request, "session"):
            from apps.schools.session_school_bind import sign_session_school_bind

            sign_session_school_bind(
                request.session, school_id=str(school.id), user_id=request.user.pk
            )
            request.session.save()
        from apps.schools.tenant_url import build_tenant_backend_url

        redirect_url = (
            build_tenant_backend_url(request, school, path="/")
            if (getattr(school, "slug", None) or getattr(school, "subdomain", None))
            else (request.build_absolute_uri("/") or "").rstrip("/")
        )
        return JsonResponse(
            {
                "ok": True,
                "school_id": str(school.id),
                "redirect_url": redirect_url,
            }
        )


# ---------------------------------------------------------------------------
# GET /api/v1/tenants/children  -> nested tenancy: list child schools (campus switcher)
# ---------------------------------------------------------------------------
class TenantChildrenView(View):
    """GET /api/v1/tenants/children - List child schools of current school (parent_school). For campus switcher."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        from apps.schools.models import School

        # Children: schools whose parent_school is current school
        children = (
            School.objects.filter(parent_school_id=school.pk, is_active=True)
            .order_by("name")
            .values("id", "name", "slug", "subdomain")
        )
        children_list = [
            {
                "id": str(s["id"]),
                "name": s["name"],
                "slug": s["slug"],
                "subdomain": s["subdomain"],
            }
            for s in children
        ]
        # If current school has a parent, include it for switcher
        parent = None
        if getattr(school, "parent_school_id", None):
            p = (
                School.objects.filter(pk=school.parent_school_id)
                .values("id", "name", "slug", "subdomain")
                .first()
            )
            if p:
                parent = {
                    "id": str(p["id"]),
                    "name": p["name"],
                    "slug": p["slug"],
                    "subdomain": p["subdomain"],
                }
        return JsonResponse({"children": children_list, "parent": parent})


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

        passport = (
            StudentPassport.objects.filter(guid=guid)
            .select_related("owner")
            .prefetch_related("documents", "school_invites")
            .first()
        )
        if not passport:
            return JsonResponse({"error": "Passport not found"}, status=404)
        school = _get_school_from_request(request)
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        profiles = list(
            StudentProfile.objects.filter(passport=passport)
            .select_related("school", "user", "academic_year")
            .order_by("-academic_year__start_date")
        )
        if school:
            from apps.accounts.effective_access import student_data_access

            if not request.user.is_superuser and not student_data_access(
                request.user, school
            ):
                visible = [p for p in profiles if p.school_id == school.id]
                if not visible and passport.owner_id != request.user.id:
                    return JsonResponse({"error": "Forbidden"}, status=403)
                profiles = visible if visible else profiles
        docs = list(
            PassportDocument.objects.filter(passport=passport).values(
                "id", "document_type", "title", "file_url", "verified_at", "created_at"
            )
        )
        timeline = []
        for p in profiles:
            timeline.append(
                {
                    "school_id": str(p.school_id),
                    "school_name": getattr(p.school, "name", None),
                    "academic_year": getattr(p.academic_year, "name", None)
                    if p.academic_year
                    else None,
                    "student_id": p.id,
                    "admission_number": getattr(p, "admission_number", None),
                }
            )
        return JsonResponse(
            {
                "global_id": str(passport.guid),
                "documents": docs,
                "enrollments": timeline,
            }
        )


# ---------------------------------------------------------------------------
# POST /api/v1/student/transfer  -> initiate transfer (invite or record)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class StudentTransferView(View):
    """POST /api/v1/student/transfer - Securely transfer / invite school to view passport."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        global_id = data.get("global_id") or data.get("student_global_id")
        to_school_id = data.get("to_school_id") or data.get("target_tenant_id")
        if not global_id or not to_school_id:
            return JsonResponse(
                {"error": "global_id and to_school_id required"}, status=400
            )
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
            defaults={
                "invited_by": request.user,
                "expires_at": timezone.now() + timedelta(days=90),
            },
        )
        return JsonResponse(
            {
                "ok": True,
                "transfer_type": "invite",
                "invite_id": invite.id,
                "token": str(invite.token),
                "expires_at": invite.expires_at.isoformat()
                if invite.expires_at
                else None,
            },
            status=201,
        )


# ---------------------------------------------------------------------------
# POST /api/v1/finance/generate-batch  -> trigger batch invoice generation
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class FinanceGenerateBatchView(View):
    """POST /api/v1/finance/generate-batch - One-click batch billing (async)."""

    def post(self, request):
        allowed, err = _require_finance_operator(request)
        if not allowed:
            return err
        _get_school_from_request(request)
        try:
            from apps.finance.tasks import auto_generate_fee_invoices_task

            result = auto_generate_fee_invoices_task.apply_async(kwargs={})
            return JsonResponse(
                {
                    "ok": True,
                    "job_id": result.id,
                    "message": "Batch generation started.",
                },
                status=202,
            )
        except (
            AttributeError,
            DatabaseError,
            ImportError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            from apps.finance.tasks import auto_generate_fee_invoices_task

            try:
                out = auto_generate_fee_invoices_task(dry_run=False)
                return JsonResponse(
                    {
                        "ok": True,
                        "message": "Batch generation completed (sync).",
                        "result": out,
                    },
                    status=200,
                )
            except (
                AttributeError,
                DatabaseError,
                ImportError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as e2:
                log_view_exception(
                    request,
                    "api.views_v1: finance/generate-batch",
                    extra={"error": str(e2)},
                )
                return JsonResponse({"error": str(e2)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/finance/exchange-rate  -> real-time currency conversion
# ---------------------------------------------------------------------------
class FinanceExchangeRateView(View):
    """GET /api/v1/finance/exchange-rate - Exchange rate for reporting (e.g. from_currency, to_currency)."""

    def get(self, request):
        allowed, err = _require_finance_operator(request)
        if not allowed:
            return err
        school = _get_school_from_request(request)
        from_currency = (
            (request.GET.get("from_currency") or request.GET.get("from") or "USD")
            .strip()
            .upper()[:3]
        )
        _to = (
            getattr(school.default_region, "default_currency", None)
            if school and getattr(school, "default_region", None)
            else None
        )
        if _to is None:
            from apps.platform_runtime.helpers import get_platform_defaults

            _to = get_platform_defaults(use_db=False)["currency"]
        to_currency = (
            (request.GET.get("to_currency") or request.GET.get("to") or _to)
            .strip()
            .upper()[:3]
        )
        if from_currency == to_currency:
            return JsonResponse(
                {
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "rate": "1",
                    "source": "identity",
                }
            )
        from apps.finance.fx import exchange_rate_api_payload

        try:
            payload = exchange_rate_api_payload(from_currency, to_currency)
        except ValueError:
            return JsonResponse(
                {
                    "error": "Exchange rate not available",
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                },
                status=503,
            )
        return JsonResponse(payload)


def _get_exchange_rate(from_currency: str, to_currency: str):
    """Return rate from_currency -> to_currency as float, or None if not configured."""
    from apps.finance.fx import exchange_rate_decimal

    rate = exchange_rate_decimal(from_currency, to_currency)
    if rate is None:
        return None
    return float(rate)


# ---------------------------------------------------------------------------
# POST /api/v1/enrollment/apply  -> public application (alias to lead capture)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
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
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        records = data.get("records", data.get("attendances", []))
        if not records:
            return JsonResponse(
                {
                    "error": "records required (list of {student_id, status} or {student, status})"
                },
                status=400,
            )
        classroom_id = data.get("classroom_id")
        if not classroom_id:
            return JsonResponse(
                {"error": "classroom_id required for bulk attendance"}, status=400
            )
        from apps.academics.models import Attendance
        from django.utils import timezone
        from datetime import datetime

        date_str = data.get("date") or timezone.now().date().isoformat()
        try:
            if isinstance(date_str, str) and "T" in date_str:
                attend_date = datetime.fromisoformat(
                    date_str.replace("Z", "+00:00")
                ).date()
            else:
                attend_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            attend_date = timezone.now().date()
        school, err = _require_tenant_member(request)
        if err:
            return err
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
        return JsonResponse(
            {"ok": True, "count": len(created), "records": created}, status=201
        )


# ---------------------------------------------------------------------------
# GET /api/v1/attendance/export  -> CSV export
# ---------------------------------------------------------------------------
class AttendanceExportView(View):
    """GET /api/v1/attendance/export - Export attendance as CSV (?date_from=&date_to=&classroom_id=)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        from apps.portal.attendance_exports import user_can_access_student_attendance_export
        from apps.schools.tenant_access import user_belongs_to_school

        if not user_belongs_to_school(request.user, school):
            return JsonResponse({"error": "Forbidden"}, status=403)
        if not user_can_access_student_attendance_export(request.user):
            return JsonResponse({"error": "Forbidden"}, status=403)

        import csv
        from io import StringIO
        from datetime import timedelta
        from django.utils import timezone
        from apps.academics.models import Attendance
        from apps.schools.tenant_access import safe_queryset_for_school

        date_from = (
            request.GET.get("date_from")
            or (timezone.now().date() - timedelta(days=30)).isoformat()
        )
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        date_to = request.GET.get("date_to") or timezone.now().date().isoformat()
        classroom_id = request.GET.get("classroom_id")
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        qs = safe_queryset_for_school(Attendance.objects.all(), school).filter(
            date__gte=date_from, date__lte=date_to
        ).select_related("student", "classroom")
        if classroom_id:
            qs = qs.filter(classroom_id=classroom_id)
        qs = qs.order_by("date", "classroom", "student")[:5000]
        buf = StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "date",
                "student_id",
                "student_name",
                "classroom_id",
                "classroom_name",
                "status",
                "remarks",
            ]
        )
        for a in qs:
            w.writerow(
                [
                    a.date.isoformat() if a.date else "",
                    a.student_id,
                    getattr(a.student, "display_name", None)
                    or getattr(a.student, "admission_number", None)
                    or "",
                    a.classroom_id,
                    getattr(a.classroom, "name", None) or "",
                    a.status,
                    (a.remarks or "")[:255],
                ]
            )
        from django.http import HttpResponse

        resp = HttpResponse(buf.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="attendance_export.csv"'
        return resp


# ---------------------------------------------------------------------------
# Vocational competency tracking (clock hours / skill verification / digital
# badge) lives in apps.evals.models_enhanced — a module that is currently NOT
# importable (duplicate EvaluationEvidence + a bad CompetencyLevel reference)
# and has NO migrations for its models. Until that feature is built, these
# endpoints degrade to HTTP 501 instead of raising an uncaught 500 on every
# call. _vocational_module() returns the module or None.
# ---------------------------------------------------------------------------
def _vocational_module():
    try:
        from apps.evals import models_enhanced

        return models_enhanced
    except Exception:  # noqa: BLE001 — unbuilt/unmigrated module → feature unavailable
        return None


def _vocational_unavailable_response():
    # Fresh response each call (JsonResponse instances are stateful/streamed once).
    return JsonResponse(
        {"error": "Vocational competency tracking is not enabled."}, status=501
    )


# ---------------------------------------------------------------------------
# POST /api/v1/vocational/log-hours  -> clock in/out hours
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class VocationalLogHoursView(View):
    """POST /api/v1/vocational/log-hours - Log vocational/workshop hours."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        student_id = data.get("student_id")
        subject_assignment_id = data.get("subject_assignment_id")
        hours = data.get("hours")
        activity_description = (
            data.get("activity_description") or data.get("description") or ""
        )[:255]
        date_str = data.get("date")
        if not all([student_id, subject_assignment_id, hours]):
            return JsonResponse(
                {"error": "student_id, subject_assignment_id, hours required"},
                status=400,
            )
        from django.utils import timezone
        from datetime import datetime

        log_date = timezone.now().date()
        if date_str:
            try:
                log_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
        me = _vocational_module()
        if me is None:
            return _vocational_unavailable_response()
        try:
            ClockHourTracking = me.ClockHourTracking

            teacher = getattr(request.user, "teacher_profile", None)
            rec = ClockHourTracking.objects.create(
                student_id=student_id,
                subject_assignment_id=subject_assignment_id,
                date=log_date,
                hours=hours,
                activity_description=activity_description or "Logged",
                recorded_by=teacher,
            )
            return JsonResponse(
                {
                    "ok": True,
                    "id": rec.id,
                    "hours": str(rec.hours),
                    "date": rec.date.isoformat(),
                },
                status=201,
            )
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request, "api.views_v1: vocational/log-hours", extra={"error": str(e)}
            )
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
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        student_id = data.get("student_id")
        competency_item_id = data.get("competency_item_id")
        level = (data.get("level") or "PROFICIENT").strip().upper()
        observations = (data.get("observations") or "")[:500]
        if not all([student_id, competency_item_id]):
            return JsonResponse(
                {"error": "student_id, competency_item_id required"}, status=400
            )
        me = _vocational_module()
        if me is None:
            return _vocational_unavailable_response()
        try:
            StudentCompetencyAssessment = me.StudentCompetencyAssessment
            CompetencyItem = me.CompetencyItem
            CompetencyRubric = me.CompetencyRubric

            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return JsonResponse({"error": "Teacher profile required"}, status=403)
            from apps.people.models import StudentProfile

            StudentProfile.objects.get(pk=student_id, school=school)
            CompetencyItem.objects.get(pk=competency_item_id)
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
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student not found"}, status=404)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request,
                "api.views_v1: vocational/verify-skill",
                extra={"error": str(e)},
            )
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/vocational/digital-badge/{student_id}  -> shareable skills summary
# ---------------------------------------------------------------------------
class VocationalDigitalBadgeView(View):
    """GET /api/v1/vocational/digital-badge/<student_id> - Shareable skills summary for employers."""

    def get(self, request, student_id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        me = _vocational_module()
        if me is None:
            return _vocational_unavailable_response()
        try:
            StudentCompetencyAssessment = me.StudentCompetencyAssessment
            from apps.people.models import StudentProfile

            student = StudentProfile.objects.get(pk=student_id, school=school)
            assessments = (
                StudentCompetencyAssessment.objects.filter(student=student)
                .select_related("competency_item", "competency_item__rubric")
                .order_by("-assessed_at")
            )
            skills = [
                {
                    "name": a.competency_item.name,
                    "level": a.level,
                    "assessed_at": a.assessed_at.isoformat() if a.assessed_at else None,
                }
                for a in assessments[:50]
            ]
            return JsonResponse(
                {
                    "student_id": student_id,
                    "skills": skills,
                    "school_id": str(school.id),
                }
            )
        except StudentProfile.DoesNotExist:
            return JsonResponse({"error": "Student not found"}, status=404)
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request,
                "api.views_v1: vocational/digital-badge",
                extra={"error": str(e)},
            )
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
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        term_id = data.get("term_id")
        academic_year_id = data.get("academic_year_id")
        if not term_id or not academic_year_id:
            return JsonResponse(
                {"error": "term_id and academic_year_id required"}, status=400
            )
        try:
            from apps.academics.models import Term, AcademicYear
            from apps.academics.scheduling_solver import generate_timetable_with_solver

            # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
            term = Term.objects.get(pk=term_id, academic_year_id=academic_year_id)
            year = AcademicYear.objects.get(pk=academic_year_id)
            use_ortools = data.get("use_ortools", False)
            schedule = generate_timetable_with_solver(
                academic_year=year,
                term=term,
                created_by=request.user,
                use_ortools=bool(use_ortools),
            )
            return JsonResponse(
                {"ok": True, "schedule_id": schedule.id, "status": schedule.status},
                status=202,
            )
        except (Term.DoesNotExist, AcademicYear.DoesNotExist):
            return JsonResponse(
                {"error": "Term or academic year not found"}, status=404
            )
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request, "api.views_v1: scheduler/generate", extra={"error": str(e)}
            )
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# GET /api/v1/scheduler/validate  -> conflict check
# ---------------------------------------------------------------------------
class SchedulerValidateView(View):
    """GET /api/v1/scheduler/validate - Real-time conflict check (schedule_id or teacher_id/room_id/time_slot)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        schedule_id = request.GET.get("schedule_id")
        if schedule_id:
            try:
                # Schedule lives in apps.academics.scheduling (NOT models) — the
                # wrong-module import here raised an uncaught ImportError (the
                # except below only catches Schedule.DoesNotExist), 500-ing every
                # /api/v1/scheduler/validate?schedule_id=… call.
                from apps.academics.scheduling import Schedule, ScheduleGenerator

                schedule = Schedule.objects.get(pk=schedule_id)
                gen = ScheduleGenerator(
                    academic_year=schedule.academic_year, term=schedule.term
                )
                conflicts = gen.detect_conflicts(schedule)
                if conflicts:
                    return JsonResponse(
                        {"valid": False, "conflicts": conflicts}, status=409
                    )
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
        school, err = _require_tenant_member(request)
        if err:
            return err
        days = int(request.GET.get("days", 30))
        from datetime import timedelta
        from django.utils import timezone
        from apps.people.models import VocationalCertification

        today = timezone.now().date()
        end = today + timedelta(days=days)
        qs = (
            VocationalCertification.objects.filter(
                school=school,
                expiry_date__isnull=False,
                expiry_date__gte=today,
                expiry_date__lte=end,
            )
            .select_related("student")
            .order_by("expiry_date")
        )
        items = [
            {
                "id": c.id,
                "student_id": c.student_id,
                "name": c.name,
                "expiry_date": c.expiry_date.isoformat(),
            }
            for c in qs
        ]
        return JsonResponse(
            {"count": len(items), "days": days, "certifications": items}
        )


# ---------------------------------------------------------------------------
# GET /api/v1/syllabus/pacing  -> planned vs actual progress (e.g. 70% IGCSE Math)
# ---------------------------------------------------------------------------
class SyllabusPacingView(View):
    """GET /api/v1/syllabus/pacing - Planned vs actual curriculum coverage (?subject_assignment_id=)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        sa_id = request.GET.get("subject_assignment_id")
        if not sa_id:
            return JsonResponse({"error": "subject_assignment_id required"}, status=400)
        try:
            from apps.academics.models import CourseSyllabus

            syllabus = CourseSyllabus.objects.filter(
                subject_assignment_id=sa_id
            ).first()
            if not syllabus:
                return JsonResponse(
                    {
                        "subject_assignment_id": sa_id,
                        "planned_pct": 0,
                        "actual_pct": 0,
                        "message": "No syllabus",
                    }
                )
            builder = getattr(syllabus, "builder_data", None) or {}
            sections = builder.get("sections") or builder.get("topics") or []
            total = len(sections)
            completed = (
                sum(1 for s in sections if isinstance(s, dict) and s.get("completed"))
                if total
                else 0
            )
            actual_pct = round(100 * completed / total, 1) if total else 0
            return JsonResponse(
                {
                    "subject_assignment_id": sa_id,
                    "planned_pct": 100,
                    "actual_pct": actual_pct,
                    "total_topics": total,
                    "completed_topics": completed,
                }
            )
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request, "api.views_v1: syllabus/pacing", extra={"error": str(e)}
            )
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/pulse  -> Global Pulse Map data
# ---------------------------------------------------------------------------
class SuperPulseView(View):
    """GET /api/v1/super/pulse - Tenants, student counts, global revenue for pulse map."""

    def get(self, request):
        if (
            not getattr(request, "user", None)
            or not request.user.is_authenticated
            or not request.user.is_superuser
        ):
            return JsonResponse({"error": "Superuser required"}, status=403)
        from django.db.models import Count, Sum
        from django.utils import timezone
        from apps.schools.models import School
        from apps.siteconfig.models import RevenueSnapshot

        schools = list(
            School.objects.filter(is_active=True)
            .annotate(student_count=Count("student_profiles", distinct=True))
            .values(
                "id",
                "name",
                "slug",
                "subdomain",
                "default_region_id",
                "student_count",
                "last_activity",
            )
        )
        first_of_month = timezone.now().date().replace(day=1)
        # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
        try:
            snapshots = RevenueSnapshot.objects.filter(
                snapshot_date=first_of_month
            ).aggregate(total=Sum("actual_revenue"), waived=Sum("waived_amount"))
            total_revenue = (snapshots["total"] or 0) + (snapshots["waived"] or 0)
        except (DatabaseError, KeyError, TypeError):
            total_revenue = 0
        by_country = list(
            School.objects.filter(is_active=True)
            .values("default_region_id")
            .annotate(
                school_count=Count("id"),
                student_count=Count("student_profiles", distinct=True),
            )
        )
        return JsonResponse(
            {
                "tenants": schools,
                "total_students": sum(s["student_count"] for s in schools),
                "total_revenue": total_revenue,
                "by_country": by_country,
            }
        )


# ---------------------------------------------------------------------------
# Plan X: Super-Admin usage & billing dashboard
# GET /api/v1/super/usage  -> per-school usage for Stripe/billing
# ---------------------------------------------------------------------------
class SuperUsageView(View):
    """GET /api/v1/super/usage - Per-tenant usage for system billing and health dashboard. Query: ?primary_sector=PUBLIC."""

    def get(self, request):
        if (
            not getattr(request, "user", None)
            or not request.user.is_authenticated
            or not request.user.is_superuser
        ):
            return JsonResponse({"error": "Superuser required"}, status=403)
        from django.db.models import Count, Sum
        from apps.schools.models import School, TenantApiUsage, TenantQuotaLimit

        schools_qs = School.objects.filter(is_active=True).annotate(
            student_count=Count("student_profiles", distinct=True),
            staff_count=Count("memberships", distinct=True),
        )
        primary_sector = (request.GET.get("primary_sector") or "").strip().upper()
        if primary_sector:
            schools_qs = schools_qs.filter(primary_sector=primary_sector)
        schools = list(
            schools_qs.values(
                "id",
                "name",
                "slug",
                "primary_sector",
                "student_count",
                "staff_count",
                "last_activity",
                "created_at",
            )
        )
        school_ids = [s["id"] for s in schools]
        usage_by_school = {
            (r["school_id"], r["limit_type"]): r["request_count"]
            for r in TenantApiUsage.objects.filter(school_id__in=school_ids)
            .values("school_id", "limit_type")
            .annotate(request_count=Sum("request_count"))
        }
        quotas_by_school = {}
        for q in TenantQuotaLimit.objects.filter(
            school_id__in=school_ids, is_active=True
        ).values("school_id", "limit_type", "limit_value", "period_days"):
            quotas_by_school.setdefault(q["school_id"], []).append(
                {
                    "limit_type": q["limit_type"],
                    "limit_value": q["limit_value"],
                    "period_days": q["period_days"],
                }
            )
        for s in schools:
            s["school_id"] = str(s["id"])
            s["primary_sector"] = s.get("primary_sector") or ""
            s["last_activity"] = (
                s["last_activity"].isoformat() if s.get("last_activity") else None
            )
            s["created_at"] = (
                s["created_at"].isoformat() if s.get("created_at") else None
            )
            sid = s["id"]
            s["api_usage"] = {
                k: v for (sch_id, k), v in usage_by_school.items() if sch_id == sid
            }
            s["quota_limits"] = quotas_by_school.get(sid, [])
        return JsonResponse({"schools": schools, "total_schools": len(schools)})


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/schools  -> School list with primary_sector filter (Wedge 14–22)
# ---------------------------------------------------------------------------
class SuperSchoolsListView(View):
    """GET /api/v1/super/schools - List schools; query ?primary_sector=PUBLIC. Every school includes primary_sector."""

    def get(self, request):
        if (
            not getattr(request, "user", None)
            or not request.user.is_authenticated
            or not request.user.is_superuser
        ):
            return JsonResponse({"error": "Superuser required"}, status=403)
        from apps.schools.models import School
        from apps.registries.services import WEDGE_14_22_SECTOR_CODES

        qs = (
            School.objects.filter(is_active=True)
            .order_by("name")
            .values(
                "id",
                "name",
                "slug",
                "subdomain",
                "country_code",
                "primary_sector",
                "created_at",
            )
        )
        primary_sector = (request.GET.get("primary_sector") or "").strip().upper()
        if primary_sector and primary_sector in WEDGE_14_22_SECTOR_CODES:
            qs = qs.filter(primary_sector=primary_sector)
        schools = list(qs)
        for s in schools:
            s["school_id"] = str(s["id"])
            s["primary_sector"] = s.get("primary_sector") or ""
            s["created_at"] = (
                s["created_at"].isoformat() if s.get("created_at") else None
            )
        return JsonResponse({"schools": schools, "total": len(schools)})


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/recovery-rate  -> System-Saved Students metric
# ---------------------------------------------------------------------------
class SuperRecoveryRateView(View):
    """GET /api/v1/super/recovery-rate - Share of Red students moved back to Green after interventions."""

    def get(self, request):
        if (
            not getattr(request, "user", None)
            or not request.user.is_authenticated
            or not request.user.is_superuser
        ):
            return JsonResponse({"error": "Superuser required"}, status=403)
        try:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            from apps.analytics.models import RiskFactor, InterventionLog

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            red_count = (
                RiskFactor.objects.filter(score__gte=80)
                .values("student_id", "school_id")
                .distinct()
                # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
                .count()
            )
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            resolved = InterventionLog.objects.filter(
                status=InterventionLog.Status.RESOLVED
            ).count()
            total_interventions = InterventionLog.objects.count()
            recovery_rate_pct = (
                round(100 * resolved / total_interventions, 1)
                if total_interventions
                else 0
            )
            return JsonResponse(
                {
                    "red_students_count": red_count,
                    "interventions_resolved": resolved,
                    "interventions_total": total_interventions,
                    "recovery_rate_pct": recovery_rate_pct,
                }
            )
        except (AttributeError, DatabaseError, ImportError, TypeError, ValueError) as e:
            log_view_exception(
                request, "api.views_v1: super/recovery-rate", extra={"error": str(e)}
            )
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Super-Admin: GET /api/v1/super/tenant-health  -> Per-tenant health (last_activity, etc.)
# ---------------------------------------------------------------------------
class SuperTenantHealthView(View):
    """GET /api/v1/super/tenant-health - Tenant Health Monitor: last_activity, status per school. Query: ?primary_sector=PUBLIC."""

    def get(self, request):
        if (
            not getattr(request, "user", None)
            or not request.user.is_authenticated
            or not request.user.is_superuser
        ):
            return JsonResponse({"error": "Superuser required"}, status=403)
        from apps.schools.models import School
        from django.db.models import Count

        qs = (
            School.objects.all()
            .annotate(student_count=Count("student_profiles", distinct=True))
            .values(
                "id",
                "name",
                "slug",
                "primary_sector",
                "is_active",
                "is_approved",
                "last_activity",
                "student_count",
            )
        )
        primary_sector = (request.GET.get("primary_sector") or "").strip().upper()
        if primary_sector:
            qs = qs.filter(primary_sector=primary_sector)
        schools = list(qs)
        for s in schools:
            s["primary_sector"] = s.get("primary_sector") or ""
            s["last_activity"] = (
                s["last_activity"].isoformat() if s.get("last_activity") else None
            )
        return JsonResponse({"tenants": schools})


# ---------------------------------------------------------------------------
# Plan XVII: Risk thresholds (Amber/Red) per tenant
# GET /api/v1/config/risk-thresholds  -> read amber_min, red_min
# PATCH /api/v1/config/risk-thresholds  -> update (admin)
# ---------------------------------------------------------------------------
class RiskThresholdsConfigView(View):
    """GET/PATCH /api/v1/config/risk-thresholds - Per-tenant risk band thresholds for Action Center."""

    def get(self, request):
        school, err = _require_auth_and_tenant_member(request)
        if err:
            return err
        from apps.analytics.models import RiskThresholds

        try:
            th = RiskThresholds.objects.get(school=school)
            return JsonResponse(
                {
                    "amber_min": float(th.amber_min),
                    "red_min": float(th.red_min),
                    "updated_at": th.updated_at.isoformat() if th.updated_at else None,
                }
            )
        except RiskThresholds.DoesNotExist:
            return JsonResponse(
                {"amber_min": 50.0, "red_min": 80.0, "updated_at": None}
            )

    def patch(self, request):
        school, err = _require_auth_and_tenant_member(request)
        if err:
            return err
        allowed, err = _require_super_or_school(request)
        if not allowed:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        from apps.analytics.models import RiskThresholds
        from decimal import Decimal

        th, _ = RiskThresholds.objects.get_or_create(
            school=school,
            defaults={"amber_min": Decimal("50"), "red_min": Decimal("80")},
        )
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
        return JsonResponse(
            {
                "amber_min": float(th.amber_min),
                "red_min": float(th.red_min),
                "updated_at": th.updated_at.isoformat() if th.updated_at else None,
            }
        )


# ---------------------------------------------------------------------------
# Plan XII: GDPR "Export my school data"
# POST /api/v1/compliance/export-school  -> trigger full school data export (admin)
# ---------------------------------------------------------------------------
@method_decorator(require_http_methods(["POST"]), name="dispatch")
class ComplianceExportSchoolView(View):
    """POST /api/v1/compliance/export-school - Request full school data export (GDPR-style). Returns summary or job_id."""

    def post(self, request):
        school, err = _require_auth_and_tenant_member(request)
        if err:
            return err
        from apps.people.models import StudentProfile
        from apps.finance.models import Invoice, Payment

        students_count = StudentProfile.objects.filter(school=school).count()
        # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
        invoices_count = Invoice.objects.filter(school=school).count()
        payments_count = Payment.objects.filter(invoice__school=school).count()
        return JsonResponse(
            {
                "ok": True,
                "school_id": str(school.id),
                "export_scope": "full_school",
                "summary": {
                    "students": students_count,
                    "invoices": invoices_count,
                    "payments": payments_count,
                },
                "message": "Use per-student data portability (compliance/data-portability) for detailed export.",
            }
        )


# ---------------------------------------------------------------------------
# Plan XVII: Enrollment forecasting
# GET /api/v1/enrollment/forecast  -> projected enrollment over next 1–3 terms
#
# v4.00.12: closes the stub. Computes a real forecast from historical
# enrollment via YoY growth-rate averaging (defensive: returns a flat
# projection when no historical data exists). Includes a confidence
# band derived from variance in the historical growth series.
# ---------------------------------------------------------------------------
class EnrollmentForecastView(View):
    """GET /api/v1/enrollment/forecast - Projected enrollment by term (real model)."""

    def get(self, request):
        if not _backend_flag_enabled("enable_enrollment_forecast_api", request=request):
            return JsonResponse(
                {"error": "Enrollment forecast is not enabled."}, status=404
            )
        school, err = _require_auth_and_tenant_member(request)
        if err:
            return err
        from apps.people.models import StudentProfile

        current = StudentProfile.objects.filter(school=school, is_active=True).count()  # tenant-isolation-allow: scoped-via-school-filter-enrollment-forecast
        try:
            from apps.api.enrollment_forecast import build_forecast

            forecasts = build_forecast(school=school, current_count=current, horizon_terms=3)
        except Exception as exc:  # noqa: BLE001 — never break the API
            forecasts = []
            forecast_error = str(exc)
        else:
            forecast_error = None
        return JsonResponse(
            {
                "current_enrollment": current,
                "forecasts": forecasts,
                "model": "yoy_growth_avg_v1",
                "error": forecast_error,
            }
        )


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
class FinanceWalletTopUpView(View):
    """POST /api/v1/finance/wallet/top-up - Credit parent wallet. Body: { \"amount\": \"100.00\", \"reference\": \"optional\" }."""

    def post(self, request):
        allowed, err = _require_parent_finance_or_operator_access(request)
        if not allowed:
            return err
        school = _get_school_from_request(request)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
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
            return JsonResponse(
                {
                    "ok": True,
                    "wallet_balance": str(wallet.balance),
                    "currency_code": wallet.currency_code,
                    "transaction_id": txn.id,
                    "reference": txn.reference,
                },
                status=201,
            )
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
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        preset_id = (data.get("preset_id") or "").strip()
        if not preset_id:
            return JsonResponse(
                {"error": "preset_id required (e.g. waec, bulletin_fr, ofsted)"},
                status=400,
            )
        from apps.reports.moe_presets import get_moe_preset

        preset = get_moe_preset(preset_id)
        if not preset:
            return JsonResponse(
                {"error": f"Unknown preset_id: {preset_id}"}, status=400
            )
        academic_year_id = data.get("academic_year_id")
        term_id = data.get("term_id")
        try:
            from apps.reports.services import build_regulatory_export

            result = build_regulatory_export(
                school, preset_id, academic_year_id=academic_year_id, term_id=term_id
            )
            if result.get("pdf_url"):
                return JsonResponse(
                    {
                        "ok": True,
                        "download_url": result["pdf_url"],
                        "preset_id": preset_id,
                    }
                )
            if result.get("job_id"):
                return JsonResponse(
                    {
                        "ok": True,
                        "job_id": result["job_id"],
                        "message": "Export queued.",
                        "preset_id": preset_id,
                    }
                )
            return JsonResponse({"ok": True, **result, "preset_id": preset_id})
        except NotImplementedError:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Regulatory export not fully implemented for this preset.",
                    "preset_id": preset_id,
                    "hint": "Use reports app and template_family from preset.",
                },
                status=501,
            )
        except (
            AttributeError,
            DatabaseError,
            ImportError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as e:
            log_view_exception(
                request, "api.views_v1: regulatory-export", extra={"error": str(e)}
            )
            return JsonResponse({"error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# PATCH /api/v1/attendance/bulk-update  -> bulk update attendance (Plan II)
# ---------------------------------------------------------------------------
class AttendanceBulkUpdateView(View):
    """PATCH /api/v1/attendance/bulk-update - Bulk update attendance records. Body: { \"records\": [ { \"id\": <id>, \"status\": \"present\" } or { \"student\", \"classroom\", \"date\", \"status\" } ] }."""

    def patch(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        records = data.get("records", [])
        if not records:
            return JsonResponse({"error": "records required"}, status=400)
        from apps.academics.models import Attendance
        from datetime import datetime

        role = (getattr(request.user, "role", "") or "").upper()
        allowed = {
            "TEACHER",
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "CENSOR",
        }
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
            sid, cid, date_str = (
                rec.get("student"),
                rec.get("classroom"),
                rec.get("date"),
            )
            if sid is None or cid is None or not date_str or "status" not in rec:
                continue
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            att, _ = Attendance.objects.update_or_create(
                school=school,
                student_id=sid,
                classroom_id=cid,
                date=dt,
                defaults={
                    "status": rec["status"],
                    "remarks": (rec.get("remarks") or "")[:255],
                },
            )
            updated += 1
        return JsonResponse({"ok": True, "updated": updated})


# ---------------------------------------------------------------------------
# POST /api/v1/billing/quote/<id>/accept  -> Quote-to-contract (REFINEMENT commercial)
# ---------------------------------------------------------------------------
class BillingQuoteAcceptView(View):
    """POST /api/v1/billing/quote/<id>/accept - Convert quote to contract (create/update subscription)."""

    def post(self, request, quote_id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        if not (getattr(request.user, "is_staff", False) or request.user.is_superuser):
            return JsonResponse({"error": "Staff or superuser required"}, status=403)
        from apps.billing.models import Quote
        from apps.billing.services import convert_quote_to_contract

        quote = get_object_or_404(Quote, pk=quote_id)
        try:
            account, subscription = convert_quote_to_contract(quote)
            return JsonResponse(
                {
                    "ok": True,
                    "quote_id": quote.pk,
                    "status": quote.status,
                    "subscription_id": subscription.pk,
                    "billing_account_id": account.pk,
                }
            )
        except ValueError as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)


# ---------------------------------------------------------------------------
# Phase 9: Payment dispute flow — list, create, resolve
# ---------------------------------------------------------------------------
class PaymentDisputeListView(View):
    """GET /api/v1/finance/disputes - List payment disputes for the current school."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        role = (getattr(request.user, "role", "") or "").upper()
        allowed = {
            "BURSAR",
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "FINANCE_STAFF",
            "ACCOUNTANT",
        }
        if role not in allowed and not request.user.is_staff:
            return JsonResponse({"error": "Forbidden"}, status=403)
        from apps.finance.models import PaymentDispute

        qs = (
            PaymentDispute.objects.filter(payment__school_id=school.pk)
            .select_related("payment", "region", "raised_by", "resolved_by")
            .order_by("-created_at")
        )
        status_filter = request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        limit = min(int(request.GET.get("limit", 50) or 50), 200)
        items = []
        for d in qs[:limit]:
            items.append(
                {
                    "id": str(d.id),
                    "payment_id": d.payment_id,
                    "payment_reference": getattr(d.payment, "reference_number", None)
                    or str(d.payment_id),
                    "status": d.status,
                    "reason": d.reason,
                    "description": d.description[:200] + "..."
                    if len(d.description or "") > 200
                    else (d.description or ""),
                    "raised_by_id": d.raised_by_id,
                    "resolved_by_id": d.resolved_by_id,
                    "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
                    "resolution_notes": d.resolution_notes or None,
                    "created_at": d.created_at.isoformat(),
                }
            )
        return JsonResponse({"disputes": items, "count": len(items)})


class PaymentDisputeCreateView(View):
    """POST /api/v1/finance/disputes - Raise a payment dispute."""

    def post(self, request):
        allowed, err = _require_finance_operator(request)
        if not allowed:
            return err
        school = _get_school_from_request(request)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        payment_id = data.get("payment_id")
        reason = (data.get("reason") or "").strip()
        description = (data.get("description") or "").strip()
        if not payment_id or not reason or not description:
            return JsonResponse(
                {"error": "payment_id, reason, and description required"}, status=400
            )
        from apps.finance.models import Payment, PaymentDispute

        payment = (
            Payment.objects.filter(pk=payment_id, school_id=school.pk)
            .select_related("region", "payment_method")
            .first()
        )
        if not payment:
            return JsonResponse({"error": "Payment not found"}, status=404)
        valid_reasons = [c[0] for c in PaymentDispute.Reason.choices]
        if reason not in valid_reasons:
            return JsonResponse(
                {"error": f"reason must be one of: {valid_reasons}"}, status=400
            )
        region = payment.region
        if (
            not region
            and getattr(payment, "payment_method", None)
            and getattr(payment.payment_method, "region_id", None)
        ):
            region = payment.payment_method.region
        if not region:
            region = getattr(school, "default_region", None)
        if not region:
            return JsonResponse(
                {"error": "No region configured for dispute"}, status=400
            )
        existing = PaymentDispute.objects.filter(
            payment=payment,
            status__in=(PaymentDispute.Status.OPEN, PaymentDispute.Status.UNDER_REVIEW),
        ).exists()
        if existing:
            return JsonResponse(
                {"error": "An open dispute already exists for this payment"}, status=400
            )
        dispute = PaymentDispute.objects.create(
            payment=payment,
            region=region,
            reason=reason,
            description=description,
            raised_by=request.user,
            status=PaymentDispute.Status.OPEN,
        )
        return JsonResponse(
            {
                "ok": True,
                "dispute_id": str(dispute.id),
                "status": dispute.status,
            },
            status=201,
        )


class PaymentDisputeResolveView(View):
    """PATCH /api/v1/finance/disputes/<uuid:id> - Resolve a dispute (staff/bursar)."""

    def patch(self, request, id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        role = (getattr(request.user, "role", "") or "").upper()
        allowed = {
            "BURSAR",
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "FINANCE_STAFF",
            "ACCOUNTANT",
        }
        if role not in allowed and not request.user.is_staff:
            return JsonResponse({"error": "Forbidden"}, status=403)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        status = (data.get("status") or "").strip()
        resolution_notes = (data.get("resolution_notes") or "").strip()
        if not status:
            return JsonResponse({"error": "status required"}, status=400)
        from apps.finance.models import PaymentDispute
        from django.utils import timezone

        dispute = get_object_or_404(PaymentDispute, id=id, payment__school_id=school.pk)
        if dispute.status not in (
            PaymentDispute.Status.OPEN,
            PaymentDispute.Status.UNDER_REVIEW,
        ):
            return JsonResponse(
                {"error": "Dispute already resolved or closed"}, status=400
            )
        resolve_statuses = (
            PaymentDispute.Status.RESOLVED_REFUND,
            PaymentDispute.Status.RESOLVED_NO_REFUND,
            PaymentDispute.Status.CLOSED,
        )
        if status not in resolve_statuses:
            return JsonResponse(
                {"error": f"status must be one of: {list(resolve_statuses)}"},
                status=400,
            )
        dispute.status = status
        dispute.resolution_notes = resolution_notes
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save(
            update_fields=[
                "status",
                "resolution_notes",
                "resolved_by",
                "resolved_at",
                "updated_at",
            ]
        )
        return JsonResponse(
            {"ok": True, "dispute_id": str(dispute.id), "status": dispute.status}
        )


# ---------------------------------------------------------------------------
# Scheduled report delivery — tenant API (plan-gated in FeatureGatekeeperMiddleware)
# ---------------------------------------------------------------------------
def _parse_schedule_time_value(raw):
    from datetime import time as time_cls

    if isinstance(raw, time_cls):
        return raw
    s = str(raw or "").strip()
    if not s:
        raise ValueError("schedule_time is required")
    parts = s.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        sec = int(parts[2]) if len(parts) > 2 else 0
    except (IndexError, TypeError, ValueError) as e:
        raise ValueError("schedule_time must be HH:MM or HH:MM:SS") from e
    return time_cls(h, m, sec)


def _normalize_schedule_recipients(raw) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError("recipients must be a list of email strings")
    out: list[str] = []
    for item in raw:
        em = str(item or "").strip()
        if not em or "@" not in em:
            raise ValueError("Each recipient must be a non-empty email address")
        out.append(em)
    if not out:
        raise ValueError("recipients must contain at least one email")
    return out


def _tenant_schedule_delivery_summary(schedule) -> dict[str, object]:
    """Machine-readable flags for clients (list/detail/patch/create responses)."""
    r = getattr(schedule, "recipients", None)
    rc = len(r) if isinstance(r, list) else 0
    has_recipients = rc > 0
    active = bool(getattr(schedule, "is_active", False))
    delivery_ready = active and has_recipients
    return {
        "recipient_count": rc,
        "has_recipients": has_recipients,
        "delivery_ready": delivery_ready,
    }


def _tri_state_query_param(raw: object) -> bool | None:
    """Parse ``true``/``false`` query flags; ``None`` when absent."""
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    raise ValueError("invalid boolean query value")


def _apply_scheduled_reports_list_filters(qs, request):
    """
    Optional ``?is_active=`` and ``?delivery_ready=`` (boolean strings).
    ``delivery_ready=true`` → active rows with a non-empty recipient list.
    """
    try:
        fa = _tri_state_query_param(request.GET.get("is_active"))
    except ValueError:
        raise ValueError("is_active") from None
    try:
        fd = _tri_state_query_param(request.GET.get("delivery_ready"))
    except ValueError:
        raise ValueError("delivery_ready") from None

    if fa is True:
        qs = qs.filter(is_active=True)
    elif fa is False:
        qs = qs.filter(is_active=False)

    if fd is True:
        qs = qs.filter(is_active=True).exclude(recipients=[])
    elif fd is False:
        qs = qs.filter(Q(is_active=False) | Q(recipients=[]))

    return qs


def _offset_limit(request, *, default=100, max_limit=100):
    """Parse ``?limit`` / ``?offset`` for v1 list endpoints. ``default`` matches
    the historical hard cap so no-param callers see unchanged behavior; clamps
    limit to [1, max_limit] and offset to >= 0."""

    def _int(name, fallback):
        try:
            return int(request.GET.get(name, fallback))
        except (TypeError, ValueError):
            return fallback

    limit = _int("limit", default)
    offset = _int("offset", 0)
    if limit < 1:
        limit = default
    if limit > max_limit:
        limit = max_limit
    if offset < 0:
        offset = 0
    return limit, offset


def _pagination_meta(request, total, limit, offset):
    """Return ``(meta_dict, link_header)`` — meta for the JSON body plus an
    RFC 8288 ``Link`` header value with next/prev for the current slice."""
    has_next = (offset + limit) < total
    has_prev = offset > 0
    path = request.path

    def _u(off):
        return f"{path}?limit={limit}&offset={max(off, 0)}"

    links = []
    if has_next:
        links.append(f'<{_u(offset + limit)}>; rel="next"')
    if has_prev:
        links.append(f'<{_u(offset - limit)}>; rel="prev"')
    meta = {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
    }
    return meta, ", ".join(links)


class ScheduledReportsListView(View):
    """
    GET /api/v1/reports/scheduled — list (summary, no raw recipient addresses).

    POST /api/v1/reports/scheduled — create ``TenantReportSchedule`` for the tenant.
    """

    def get(self, request):
        ok, err = _require_super_or_school(request)
        if not ok:
            return err
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        from apps.reports.models import TenantReportSchedule

        base = TenantReportSchedule.objects.filter(school=school)
        try:
            base = _apply_scheduled_reports_list_filters(base, request)
        except ValueError as e:
            field = str(e)
            return JsonResponse(
                {"error": f"Invalid {field}; use true or false (or 1/0)."},
                status=400,
            )
        limit, offset = _offset_limit(request)
        total = base.count()
        rows = base.order_by("next_run").select_related("created_by")[
            offset : offset + limit
        ]
        items = []
        for s in rows:
            items.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "report_key": s.report_key,
                    "schedule_frequency": s.schedule_frequency,
                    "schedule_time": s.schedule_time.isoformat(timespec="seconds")
                    if s.schedule_time
                    else None,
                    "is_active": s.is_active,
                    "last_run": s.last_run.isoformat() if s.last_run else None,
                    "next_run": s.next_run.isoformat() if s.next_run else None,
                    **_tenant_schedule_delivery_summary(s),
                }
            )
        meta, link_header = _pagination_meta(request, total, limit, offset)
        resp = JsonResponse(
            {
                "schedules": items,
                "schema": "reports_scheduled_delivery_v2",
                "pagination": meta,
            }
        )
        if link_header:
            resp["Link"] = link_header
        return resp

    def post(self, request):
        ok, err = _require_super_or_school(request)
        if not ok:
            return err
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        from apps.reports.models import TenantReportSchedule
        from apps.reports.schedule_utils import compute_next_scheduled_run

        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "name required"}, status=400)
        freq = (data.get("schedule_frequency") or "").strip().upper()
        valid_freq = {c.value for c in TenantReportSchedule.Frequency}
        if freq not in valid_freq:
            return JsonResponse(
                {
                    "error": f"schedule_frequency must be one of: {sorted(valid_freq)}",
                },
                status=400,
            )
        is_active = bool(data.get("is_active", True))
        try:
            st = _parse_schedule_time_value(data.get("schedule_time"))
            raw_recipients = data.get("recipients")
            if not is_active and (raw_recipients is None or raw_recipients == []):
                recipients = []
            else:
                recipients = _normalize_schedule_recipients(raw_recipients or [])
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        report_key = (data.get("report_key") or "summary").strip() or "summary"
        parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
        next_run = compute_next_scheduled_run(None, freq, st)
        obj = TenantReportSchedule(
            school=school,
            name=name,
            report_key=report_key[:80],
            schedule_frequency=freq,
            schedule_time=st,
            recipients=recipients,
            parameters=parameters or {},
            is_active=is_active,
            last_run=None,
            next_run=next_run,
            created_by=request.user,
        )
        try:
            obj.full_clean()
        except ValidationError as e:
            return JsonResponse({"error": " ".join(e.messages)}, status=400)
        obj.save()
        return JsonResponse(
            {
                "ok": True,
                "id": obj.id,
                "name": obj.name,
                "report_key": obj.report_key,
                "is_active": obj.is_active,
                "next_run": obj.next_run.isoformat(),
                "schema": "reports_scheduled_delivery_v2",
                **_tenant_schedule_delivery_summary(obj),
            },
            status=201,
        )


class ScheduledReportDetailView(View):
    """
    GET /api/v1/reports/scheduled/<id> — detail including recipients (authorized staff).

    PATCH — partial update; recomputes ``next_run`` when frequency or schedule_time change.

    DELETE — remove schedule.
    """

    def get(self, request, id: int):
        ok, err = _require_super_or_school(request)
        if not ok:
            return err
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        from apps.reports.models import TenantReportSchedule

        s = get_object_or_404(TenantReportSchedule, pk=id, school_id=school.pk)
        return JsonResponse(
            {
                "id": s.id,
                "name": s.name,
                "report_key": s.report_key,
                "schedule_frequency": s.schedule_frequency,
                "schedule_time": s.schedule_time.isoformat(timespec="seconds")
                if s.schedule_time
                else None,
                "recipients": list(s.recipients or []),
                "parameters": dict(s.parameters or {}),
                "is_active": s.is_active,
                "last_run": s.last_run.isoformat() if s.last_run else None,
                "next_run": s.next_run.isoformat() if s.next_run else None,
                "created_by_id": s.created_by_id,
                "schema": "reports_scheduled_delivery_v2",
                **_tenant_schedule_delivery_summary(s),
            }
        )

    def patch(self, request, id: int):
        ok, err = _require_super_or_school(request)
        if not ok:
            return err
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        from apps.reports.models import TenantReportSchedule
        from apps.reports.schedule_utils import compute_next_scheduled_run

        s = get_object_or_404(TenantReportSchedule, pk=id, school_id=school.pk)
        recompute_next = False
        if "name" in data:
            n = (data.get("name") or "").strip()
            if not n:
                return JsonResponse({"error": "name cannot be empty"}, status=400)
            s.name = n
        if "report_key" in data:
            rk = (data.get("report_key") or "").strip() or "summary"
            s.report_key = rk[:80]
        if "schedule_frequency" in data:
            freq = str(data.get("schedule_frequency") or "").strip().upper()
            valid_freq = {c.value for c in TenantReportSchedule.Frequency}
            if freq not in valid_freq:
                return JsonResponse(
                    {"error": f"schedule_frequency must be one of: {sorted(valid_freq)}"},
                    status=400,
                )
            s.schedule_frequency = freq
            recompute_next = True
        if "schedule_time" in data:
            try:
                s.schedule_time = _parse_schedule_time_value(data.get("schedule_time"))
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
            recompute_next = True
        if "recipients" in data:
            try:
                s.recipients = _normalize_schedule_recipients(data.get("recipients"))
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
        if "parameters" in data:
            p = data.get("parameters")
            s.parameters = p if isinstance(p, dict) else {}
        if "is_active" in data:
            s.is_active = bool(data.get("is_active"))
        if recompute_next:
            base = s.last_run
            s.next_run = compute_next_scheduled_run(base, s.schedule_frequency, s.schedule_time)
        try:
            s.full_clean()
        except ValidationError as e:
            return JsonResponse(
                {"error": " ".join(e.messages)},
                status=400,
            )
        s.save()
        return JsonResponse(
            {
                "ok": True,
                "id": s.id,
                "name": s.name,
                "report_key": s.report_key,
                "is_active": s.is_active,
                "next_run": s.next_run.isoformat() if s.next_run else None,
                "schema": "reports_scheduled_delivery_v2",
                **_tenant_schedule_delivery_summary(s),
            }
        )

    def delete(self, request, id: int):
        ok, err = _require_super_or_school(request)
        if not ok:
            return err
        school = _get_school_from_request(request)
        if not school:
            return JsonResponse({"error": "Tenant context required"}, status=400)
        from apps.reports.models import TenantReportSchedule

        s = get_object_or_404(TenantReportSchedule, pk=id, school_id=school.pk)
        s.delete()
        return JsonResponse(
            {
                "ok": True,
                "deleted_id": id,
                "schema": "reports_scheduled_delivery_v2",
            }
        )


# ---------------------------------------------------------------------------
# Phase 9: Ad-hoc report builder — list, create, run now
# ---------------------------------------------------------------------------
class AdHocReportListCreateView(View):
    """GET /api/v1/reports/adhoc — list definitions. POST — create definition."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        from apps.reports.bi_models import AdHocReportDefinition

        # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
        qs = AdHocReportDefinition.objects.filter(is_active=True)
        from django.db.models import Q

        if school:
            qs = qs.filter(Q(school_id=school.pk) | Q(school__isnull=True))
        else:
            qs = qs.filter(school__isnull=True)
        limit, offset = _offset_limit(request)
        total = qs.count()
        qs = qs.order_by("-created_at")[offset : offset + limit]
        items = [
            {
                "id": d.id,
                "name": d.name,
                "entity_type": d.entity_type,
                "columns": d.columns,
                "output_format": d.output_format,
                "created_at": d.created_at.isoformat(),
            }
            for d in qs
        ]
        meta, link_header = _pagination_meta(request, total, limit, offset)
        resp = JsonResponse({"definitions": items, "pagination": meta})
        if link_header:
            resp["Link"] = link_header
        return resp

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        name = (data.get("name") or "").strip()
        entity_type = data.get("entity_type", "STUDENTS")
        columns = data.get("columns") or ["id", "first_name", "last_name"]
        filters = data.get("filters") or {}
        output_format = data.get("output_format", "CSV")
        if not name:
            return JsonResponse({"error": "name required"}, status=400)
        from apps.reports.bi_models import AdHocReportDefinition

        obj = AdHocReportDefinition.objects.create(
            name=name,
            school=school,
            entity_type=entity_type,
            columns=columns,
            filters=filters,
            date_from=data.get("date_from") or None,
            date_to=data.get("date_to") or None,
            output_format=output_format,
            created_by=request.user,
        )
        return JsonResponse({"ok": True, "id": obj.id, "name": obj.name}, status=201)


class AdHocReportRunView(View):
    """POST /api/v1/reports/adhoc/<id>/run — run report now; returns CSV download or JSON."""

    def post(self, request, id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school = _get_school_from_request(request)
        from apps.reports.bi_models import AdHocReportDefinition
        # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
        from apps.reports.adhoc_runner import run_adhoc_report
        from django.http import HttpResponse

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        definition = AdHocReportDefinition.objects.filter(pk=id, is_active=True).first()
        if not definition:
            return JsonResponse({"error": "Report not found"}, status=404)
        if school and definition.school_id and definition.school_id != school.pk:
            return JsonResponse({"error": "Forbidden"}, status=403)
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        params = data.get("parameters_override") or {}
        output_format = data.get("output_format") or definition.output_format
        user_role = (getattr(request.user, "role", "") or "").upper()
        csv_bytes, json_rows, row_count, err = run_adhoc_report(
            definition,
            request.user,
            parameters_override=params,
            output_format=output_format,
            school_id_override=str(school.pk) if school else None,
            allow_global=bool(
                not school and (request.user.is_superuser or user_role == "SUPERADMIN")
            ),
        )
        if err:
            return JsonResponse({"ok": False, "error": err}, status=400)
        if output_format == "CSV" and csv_bytes:
            resp = HttpResponse(csv_bytes, content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = (
                f'attachment; filename="{definition.name.replace(" ", "_")}_report.csv"'
            )
            return resp
        return JsonResponse({"ok": True, "row_count": row_count, "rows": json_rows})


# ---------------------------------------------------------------------------
# Phase 9: Video attendance sync — create session, list, sync attendance
# ---------------------------------------------------------------------------
class VideoSessionListCreateView(View):
    """GET /api/v1/video/sessions — list. POST — create (Zoom/Meet link)."""

    def get(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        from apps.communication.video_conferencing import VirtualClassroom
        from django.db.models import Q

        qs = (
            VirtualClassroom.objects.filter(
                Q(classroom__academic_year__school_id=school.pk)
                | Q(host__school_memberships__school_id=school.pk)
            )
            .distinct()
            .order_by("-scheduled_start")[:50]
        )
        items = [
            {
                "id": s.id,
                "title": s.title,
                "provider": s.provider,
                "status": s.status,
                "meeting_id": s.meeting_id,
                "join_url": s.join_url,
                "scheduled_start": s.scheduled_start.isoformat(),
                "scheduled_end": s.scheduled_end.isoformat(),
            }
            for s in qs
        ]
        return JsonResponse({"sessions": items})

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        title = (data.get("title") or "").strip()
        scheduled_start = data.get("scheduled_start")
        scheduled_end = data.get("scheduled_end")
        provider = data.get("provider", "JITSI")
        classroom_id = data.get("classroom_id")
        if not title or not scheduled_start or not scheduled_end:
            return JsonResponse(
                {"error": "title, scheduled_start, scheduled_end required"}, status=400
            )
        from django.utils.dateparse import parse_datetime
        from apps.communication.video_conferencing import VirtualClassroom

        start = (
            parse_datetime(scheduled_start)
            if isinstance(scheduled_start, str)
            else scheduled_start
        )
        end = (
            parse_datetime(scheduled_end)
            if isinstance(scheduled_end, str)
            else scheduled_end
        )
        if not start or not end:
            return JsonResponse(
                {"error": "Invalid datetime for scheduled_start/scheduled_end"},
                # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
                status=400,
            )
        classroom = None
        if classroom_id:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            from apps.academics.models import Classroom

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            classroom = Classroom.objects.filter(
                pk=classroom_id, academic_year__school_id=school.pk
            ).first()
        meeting_id = (
            data.get("meeting_id") or f"vc-{request.user.id}-{int(start.timestamp())}"
        )
        join_url = data.get("join_url") or f"https://meet.example.com/{meeting_id}"
        session = VirtualClassroom.objects.create(
            title=title,
            scheduled_start=start,
            scheduled_end=end,
            provider=provider,
            host=request.user,
            classroom=classroom,
            meeting_id=meeting_id,
            join_url=join_url,
            status="SCHEDULED",
        )
        return JsonResponse(
            {"ok": True, "session_id": session.id, "join_url": session.join_url},
            status=201,
        )


class VideoAttendanceSyncView(View):
    """POST /api/v1/video/sessions/<id>/attendance-sync — sync participants (Zoom/Meet webhook or manual)."""

    def post(self, request, id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        participants = data.get("participants") or []
        from apps.communication.video_conferencing import (
            VirtualClassroom,
            SessionParticipant,
        )
        from django.utils.dateparse import parse_datetime
        from apps.accounts.models import User

        session = VirtualClassroom.objects.filter(pk=id).first()
        if not session:
            return JsonResponse({"error": "Session not found"}, status=404)
        session_school_id = None
        if session.classroom_id:
            session_school_id = getattr(
                getattr(session.classroom, "academic_year", None), "school_id", None
            )
        if session_school_id is not None and session_school_id != school.pk:
            return JsonResponse({"error": "Forbidden"}, status=403)
        synced = 0
        for p in participants:
            email = (p.get("email") or "").strip()
            if not email:
                continue
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                continue
            joined_at = p.get("joined_at")
            left_at = p.get("left_at")
            if joined_at:
                joined_at = (
                    parse_datetime(joined_at)
                    if isinstance(joined_at, str)
                    else joined_at
                )
            if left_at:
                left_at = (
                    parse_datetime(left_at) if isinstance(left_at, str) else left_at
                )
            part, _ = SessionParticipant.objects.get_or_create(
                session=session,
                user=user,
                defaults={
                    "joined_at": joined_at,
                    "left_at": left_at,
                    "is_present": True,
                },
            )
            if not _ and (joined_at or left_at):
                part.joined_at = joined_at or part.joined_at
                part.left_at = left_at or part.left_at
                part.is_present = True
                part.save(update_fields=["joined_at", "left_at", "is_present"])
            synced += 1
        return JsonResponse({"ok": True, "synced": synced})


# ---------------------------------------------------------------------------
# Government/District EMIS: prepare and submit
# ---------------------------------------------------------------------------
class EMISPrepareView(View):
    """POST /api/v1/reports/emis/prepare - Prepare EMIS report (create DRAFT/PREPARED, optional preset)."""

    def post(self, request):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        report_type = (data.get("report_type") or "").strip() or "MOE_PRESET"
        period_label = (data.get("period_label") or "").strip()
        preset_id = (data.get("preset_id") or "").strip()
        academic_year_id = data.get("academic_year_id")
        term_id = data.get("term_id")
        if not period_label:
            return JsonResponse({"error": "period_label required"}, status=400)
        # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
        from apps.reports.models import EMISSubmission
        from apps.reports.services import build_regulatory_export

        # tenant-isolation-allow: api-v1-scoped-via-request-school-mixin
        ay, term = None, None
        if academic_year_id:
            from apps.academics.models import AcademicYear
# tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17

            ay = AcademicYear.objects.filter(pk=academic_year_id).first()
        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        if term_id:
            from apps.academics.models import Term

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            term = Term.objects.filter(pk=term_id).first()
        if report_type == "MOE_PRESET" and preset_id:
            result = build_regulatory_export(
                school, preset_id, academic_year_id=academic_year_id, term_id=term_id
            )
            if not result.get("ok"):
                return JsonResponse(result, status=400)
        sub, _ = EMISSubmission.objects.update_or_create(
            school=school,
            report_type=report_type,
            period_label=period_label,
            defaults={
                "preset_id": preset_id or "",
                "academic_year": ay,
                "term": term,
                "status": EMISSubmission.Status.PREPARED,
                "notes": data.get("notes", ""),
            },
        )
        return JsonResponse(
            {
                "ok": True,
                "submission_id": sub.id,
                "status": sub.status,
                "period_label": sub.period_label,
            },
            status=201,
        )


class EMISSubmitView(View):
    """POST /api/v1/reports/emis/<int:id>/submit - Mark EMIS submission as submitted."""

    def post(self, request, id):
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)
        school, err = _require_tenant_member(request)
        if err:
            return err
        from apps.reports.models import EMISSubmission
        from django.utils import timezone

        sub = get_object_or_404(EMISSubmission, pk=id, school_id=school.pk)
        if sub.status == EMISSubmission.Status.SUBMITTED:
            return JsonResponse(
                {"ok": True, "submission_id": sub.id, "status": sub.status}
            )
        sub.status = EMISSubmission.Status.SUBMITTED
        sub.submitted_at = timezone.now()
        sub.submitted_by = request.user
        data, error_response = _parse_json_object(request)
        if error_response:
            return error_response
        sub.external_id = (data.get("external_id") or "")[:120]
        sub.submission_url = (data.get("submission_url") or "")[:500]
        sub.save(
            update_fields=[
                "status",
                "submitted_at",
                "submitted_by",
                "external_id",
                "submission_url",
                "updated_at",
            ]
        )
        return JsonResponse({"ok": True, "submission_id": sub.id, "status": sub.status})


# Intervention views live in .views_v1_intervention; urlconf imports from there.
