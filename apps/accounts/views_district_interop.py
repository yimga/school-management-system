"""
Tenant hub: district / LMS interoperability (OneRoster, SSO, LTI discovery).
Clever/ClassLink-class motion = Bearer + OneRoster pull + CSV for ops, plus optional
native vendor HTTP when the district stores Clever/ClassLink bearer tokens (see
district_interop_save_native_vendor / district_interop_native_probe).
"""

from __future__ import annotations

import csv
import io
import secrets
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from django.contrib import messages

from apps.accounts.district_interop_helpers import integration_readiness_snapshot
from apps.accounts.models import FederationSsoHealth
from apps.marketplace.ecosystem_links import build_phase9_ecosystem_links
from apps.integrations_marketplace.models import ServiceIntegration
from apps.interop.oneroster.constants import ONEROSTER_DISTRICT_API_SERVICE_NAME
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import TenantInteropAccessLog
from apps.academics.models import Classroom
from apps.platform_runtime.learning_institution_catalog import (
    INSTITUTION_TYPE_PACKS,
    LEARNING_DELIVERY_MODES,
)
from apps.platform_runtime.learning_institution_runtime import (
    apply_learning_institution_packs,
)
from apps.platform_runtime.school_settings_kv import (
    get_school_settings_dict,
    toggle_school_setting_bool,
)
from apps.accounts.district_interop_native import (
    log_native_vendor_access,
    mask_token_preview,
    native_probe_rate_allow,
    summarize_api_result,
)


ONEROSTER_INTEGRATION_NAME = ONEROSTER_DISTRICT_API_SERVICE_NAME


def _can_district_interop(user: Any) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    role = getattr(user, "role", None) or ""
    return role in ("ADMIN", "IT_ADMIN", "PROPRIETOR", "LEADERSHIP")


def _school_or_redirect(request):
    school = getattr(request, "school", None)
    if not school:
        return None, HttpResponseRedirect(reverse("accounts:backend_dashboard"))
    return school, None


@login_required
@require_http_methods(["GET"])
def district_lms_interop(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir

    integration = ServiceIntegration.objects.filter(
        school=school, service_name=ONEROSTER_INTEGRATION_NAME, is_active=True
    ).first()
    token_preview = ""
    if integration and (integration.config or {}).get("bearer_token"):
        t = str((integration.config or {}).get("bearer_token", ""))
        token_preview = t[:6] + "…" if len(t) > 8 else "(set)"

    base = request.build_absolute_uri("/api/oneroster/v1p1/").rstrip("/")
    slug_q = f"?school_slug={school.slug}"
    ctx = {
        "school": school,
        "integration": integration,
        "token_preview": token_preview,
        "oneroster_manifest": f"{base}/manifest{slug_q}",
        "oneroster_academic_sessions": f"{base}/academicSessions{slug_q}",
        "oneroster_classes": f"{base}/classes{slug_q}",
        "oneroster_students": f"{base}/students{slug_q}",
        "oneroster_teachers": f"{base}/teachers{slug_q}",
        "oneroster_enrollments": f"{base}/enrollments{slug_q}",
        "oneroster_orgs": f"{base}/orgs{slug_q}",
        "oneroster_courses": f"{base}/courses{slug_q}",
        "oneroster_users": f"{base}/users{slug_q}",
        "readiness_oneroster": request.build_absolute_uri("/api/interop/oneroster/"),
        "readiness_lti": request.build_absolute_uri("/api/interop/lti13/"),
        "csv_students": reverse("accounts:district_interop_csv_students"),
        "csv_teachers": reverse("accounts:district_interop_csv_teachers"),
        "csv_classes": reverse("accounts:district_interop_csv_classes"),
        "readiness": integration_readiness_snapshot(school, request),
        "synthetic_demo": bool(
            get_school_settings_dict(school).get("interop_synthetic_roster")
        ),
        "advanced": (integration.config or {}) if integration else {},
        "delivery_modes": LEARNING_DELIVERY_MODES,
        "institution_packs": INSTITUTION_TYPE_PACKS,
        "selected_delivery": get_school_settings_dict(school).get(
            "learning_delivery_modes"
        )
        or [],
        "selected_institution": get_school_settings_dict(school).get(
            "institution_type_pack"
        )
        or "",
        "packet_url": reverse("accounts:district_interop_packet"),
        "partner_url": reverse("accounts:district_interop_partner"),
        "studio_interop_doc": "/docs/setup_studio/WEDGE_INTEROP_CHECKLIST.md",
        "studio_institution_doc": "/docs/setup_studio/WEDGE_INSTITUTION_CHECKLIST.md",
        "partner_trust_doc": "/docs/INTEGRATION_PARTNER_TRUST_SIGNALS.md",
        "federation_sso_rows": _federation_sso_health_rows(
            school, ONEROSTER_INTEGRATION_NAME
        ),
        "clever_partnership_doc": "/docs/interop/CLEVER_CLASSLINK_PARTNERSHIP.md",
        "oneroster_delta_hint": "changesSince=ISO8601 on students (updated_at filter).",
        "interop_access_recent": list(
            TenantInteropAccessLog.objects.filter(school=school).order_by("-created_at")[
                :50
            ]
        ),
        "phase9_links": build_phase9_ecosystem_links(),
        "native_clever_preview": mask_token_preview(
            (integration.config or {}).get("native_clever_bearer") if integration else ""
        ),
        "native_classlink_preview": mask_token_preview(
            (integration.config or {}).get("native_classlink_bearer")
            if integration
            else ""
        ),
        "native_classlink_base_url": (
            (integration.config or {}).get("native_classlink_base_url") or ""
        )
        if integration
        else "",
        "native_probe_result": (
            request.session.pop("district_native_probe_result", None)
            if getattr(request, "session", None) is not None
            else None
        ),
    }
    return render(request, "accounts/district_lms_interop.html", ctx)


def _federation_sso_health_rows(school, oneroster_name: str) -> list[dict[str, Any]]:
    """SAML/OIDC integrations (exclude district OneRoster bearer row) + login health."""
    qs = (
        ServiceIntegration.objects.filter(
            school=school,
            is_active=True,
            service_type=ServiceIntegration.ServiceType.OAUTH,
        )
        .exclude(service_name=oneroster_name)
        .order_by("service_name", "pk")
    )
    ids = [s.pk for s in qs]
    health_by_id = {
        h.service_integration_id: h
        for h in FederationSsoHealth.objects.filter(service_integration_id__in=ids)
    }
    rows: list[dict[str, Any]] = []
    for si in qs:
        h = health_by_id.get(si.pk)
        rows.append(
            {
                "id": si.pk,
                "name": si.service_name or str(si.service_type),
                "last_success_at": h.last_success_at if h else None,
                "last_failure_at": h.last_failure_at if h else None,
                "last_error": (h.last_error_summary if h else "") or "",
                "success_count": h.success_count if h else 0,
                "failure_count": h.failure_count if h else 0,
            }
        )
    return rows


@login_required
@require_http_methods(["POST"])
def district_interop_rotate_token(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    token = secrets.token_urlsafe(32)
    integration, _ = ServiceIntegration.objects.get_or_create(
        school=school,
        service_name=ONEROSTER_INTEGRATION_NAME,
        defaults={
            "service_type": ServiceIntegration.ServiceType.OAUTH,
            "is_active": True,
            "config": {},
        },
    )
    cfg = dict(integration.config or {})
    cfg["bearer_token"] = token
    integration.config = cfg
    integration.service_type = ServiceIntegration.ServiceType.OAUTH
    integration.is_active = True
    integration.save(
        update_fields=["config", "service_type", "is_active", "updated_at"]
    )
    from django.contrib import messages

    messages.success(
        request,
        "New OneRoster Bearer token generated. Copy it now; it is not shown in full again.",
    )
    return render(
        request,
        "accounts/district_interop_token_result.html",
        {"plain_token": token, "school": school},
    )


def _csv_response(filename: str, rows: list[list[Any]], header: list[str]):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(row)
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@require_http_methods(["GET"])
def district_interop_csv_students(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    rows = []
    for s in StudentProfile.objects.filter(school=school).order_by("pk")[:5000]:
        rows.append(
            [
                s.pk,
                s.student_code or "",
                s.first_name or "",
                s.last_name or "",
                s.classroom_id or "",
            ]
        )
    return _csv_response(
        f"roster_students_{school.slug}.csv",
        rows,
        ["sourcedId", "student_code", "givenName", "familyName", "classroomId"],
    )


@login_required
@require_http_methods(["GET"])
def district_interop_csv_teachers(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    rows = []
    for t in (
        TeacherProfile.objects.filter(school=school)
        .select_related("user")
        .order_by("pk")[:2000]
    ):
        u = t.user
        rows.append(
            [
                t.pk,
                getattr(u, "username", "") if u else "",
                getattr(u, "first_name", "") if u else "",
                getattr(u, "last_name", "") if u else "",
                getattr(u, "email", "") if u else "",
            ]
        )
    return _csv_response(
        f"roster_teachers_{school.slug}.csv",
        rows,
        ["sourcedId", "username", "givenName", "familyName", "email"],
    )


@login_required
@require_http_methods(["GET"])
def district_interop_csv_classes(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    rows = []
    for c in Classroom.objects.filter(school=school).order_by("pk")[:2000]:
        rows.append([c.pk, c.name or "", c.code or ""])
    return _csv_response(
        f"roster_classes_{school.slug}.csv",
        rows,
        ["sourcedId", "title", "classCode"],
    )


@login_required
@require_http_methods(["POST"])
def district_interop_save_advanced(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    integration, _ = ServiceIntegration.objects.get_or_create(
        school=school,
        service_name=ONEROSTER_INTEGRATION_NAME,
        defaults={
            "service_type": ServiceIntegration.ServiceType.OAUTH,
            "is_active": True,
            "config": {},
        },
    )
    cfg = dict(integration.config or {})
    cfg["roster_webhook_url"] = (request.POST.get("roster_webhook_url") or "").strip()
    sec = (request.POST.get("roster_webhook_secret") or "").strip()
    if sec:
        cfg["roster_webhook_secret"] = sec
    cfg["allowed_ips"] = (request.POST.get("allowed_ips") or "").strip()
    cfg["oneroster_scopes"] = (request.POST.get("oneroster_scopes") or "*").strip()
    cfg["oneroster_export_profile"] = (
        request.POST.get("oneroster_export_profile") or "standard"
    ).strip()
    try:
        cfg["oneroster_rate_limit_per_window"] = max(
            30, min(int(request.POST.get("rate_limit") or 600), 100_000)
        )
    except ValueError:
        cfg["oneroster_rate_limit_per_window"] = 600
    if request.POST.get("disable_audit"):
        cfg["oneroster_audit_disabled"] = True
    else:
        cfg.pop("oneroster_audit_disabled", None)
    integration.config = cfg
    integration.save(update_fields=["config", "updated_at"])
    messages.success(request, "Interop security settings saved.")
    return HttpResponseRedirect(reverse("accounts:district_lms_interop"))


@login_required
@require_http_methods(["POST"])
def district_interop_save_native_vendor(request):
    """Store Clever/ClassLink bearer + ClassLink base URL in OneRoster integration config."""
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    integration, _ = ServiceIntegration.objects.get_or_create(
        school=school,
        service_name=ONEROSTER_INTEGRATION_NAME,
        defaults={
            "service_type": ServiceIntegration.ServiceType.OAUTH,
            "is_active": True,
            "config": {},
        },
    )
    cfg = dict(integration.config or {})
    clever = (request.POST.get("native_clever_bearer") or "").strip()
    if clever:
        cfg["native_clever_bearer"] = clever
    cl = (request.POST.get("native_classlink_bearer") or "").strip()
    if cl:
        cfg["native_classlink_bearer"] = cl
    base = (request.POST.get("native_classlink_base_url") or "").strip()
    if base:
        cfg["native_classlink_base_url"] = base
    integration.config = cfg
    integration.save(update_fields=["config", "updated_at"])
    messages.success(request, "Native vendor credentials saved.")
    return HttpResponseRedirect(reverse("accounts:district_lms_interop"))


@login_required
@require_http_methods(["POST"])
def district_interop_native_probe(request):
    """Rate-limited outbound Clever/ClassLink API probes using stored tenant config."""
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    ok, err = native_probe_rate_allow(school.pk)
    if not ok:
        messages.error(request, err)
        return HttpResponseRedirect(reverse("accounts:district_lms_interop"))
    integration = ServiceIntegration.objects.filter(
        school=school, service_name=ONEROSTER_INTEGRATION_NAME, is_active=True
    ).first()
    cfg = (integration.config or {}) if integration else {}
    from apps.interop.clever_classlink_client import (
        classlink_list_courses,
        classlink_roster_ping,
        clever_list_schools,
        clever_list_sections,
        clever_list_users,
    )

    out: dict[str, Any] = {}
    ct = (cfg.get("native_clever_bearer") or "").strip()
    if ct:
        out["clever"] = {
            "users": clever_list_users(ct, limit=3),
            "schools": clever_list_schools(ct, limit=3),
            "sections": clever_list_sections(ct, limit=3),
        }
        log_native_vendor_access(
            school,
            endpoint="clever_probe",
            client_ip=request.META.get("REMOTE_ADDR", "") or "",
            token_prefix=ct[:6] if len(ct) >= 6 else "",
        )
    cl_tok = (cfg.get("native_classlink_bearer") or "").strip()
    cl_base = (cfg.get("native_classlink_base_url") or "").strip()
    if cl_tok:
        out["classlink"] = {
            "ping": classlink_roster_ping(cl_tok, district_path=cl_base),
            "courses": classlink_list_courses(cl_tok, district_path=cl_base),
        }
        log_native_vendor_access(
            school,
            endpoint="classlink_probe",
            client_ip=request.META.get("REMOTE_ADDR", "") or "",
            token_prefix=cl_tok[:6] if len(cl_tok) >= 6 else "",
        )
    if not out:
        messages.warning(
            request,
            "No native Clever or ClassLink bearer stored. Save credentials first.",
        )
        return HttpResponseRedirect(reverse("accounts:district_lms_interop"))
    request.session["district_native_probe_result"] = summarize_api_result(out)
    messages.success(request, "Native vendor probe complete. See result below.")
    return HttpResponseRedirect(reverse("accounts:district_lms_interop"))


@login_required
@require_http_methods(["POST"])
def district_interop_toggle_synthetic(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    on = toggle_school_setting_bool(school, "interop_synthetic_roster")
    messages.success(
        request,
        "Synthetic demo roster %s." % ("enabled" if on else "disabled"),
    )
    return HttpResponseRedirect(reverse("accounts:district_lms_interop"))


@login_required
@require_http_methods(["GET"])
def district_interop_packet(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    base = request.build_absolute_uri("/api/oneroster/v1p1/").rstrip("/")
    q = f"?school_slug={school.slug}"
    ctx = {
        "school": school,
        "data_map": [
            ("students/users", "StudentProfile → OneRoster users (role=student)"),
            ("teachers", "TeacherProfile → OneRoster users (role=teacher)"),
            ("classes", "Classroom → classes"),
            ("enrollments", "StudentProfile.classroom → enrollments"),
            ("academicSessions", "Term → academicSessions"),
            ("orgs", "School + Department → orgs"),
            ("courses", "Subject → courses"),
        ],
        "auth_model": "Bearer token (server-to-server). Header: Authorization: Bearer <token>.",
        "endpoints": {
            "manifest": f"{base}/manifest{q}",
            "users": f"{base}/users{q}",
            "students": f"{base}/students{q}",
            "teachers": f"{base}/teachers{q}",
            "classes": f"{base}/classes{q}",
            "enrollments": f"{base}/enrollments{q}",
            "academicSessions": f"{base}/academicSessions{q}",
            "orgs": f"{base}/orgs{q}",
            "courses": f"{base}/courses{q}",
        },
        "webhooks": "POST JSON to configured roster_webhook_url; header X-RunMyCampus-Signature: sha256=<hmac> when secret set.",
        "retention": "Per tenant data retention per trust center / DPA.",
    }
    return render(request, "accounts/district_interop_packet.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def district_interop_partner(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    checklist = [
        ("Bearer token generated and stored in secret manager", False),
        ("GET manifest returns 200 with resource URLs", False),
        ("GET users OR students+teachers returns expected counts", False),
        ("IP allowlist tested from district egress IPs", False),
        ("Webhook receives test event on student save (optional)", False),
        ("429 behavior documented for rate limits", False),
    ]
    if request.method == "POST":
        messages.success(
            request,
            "Save checklist progress in your runbook; this page is a harness only.",
        )
        return HttpResponseRedirect(reverse("accounts:district_interop_partner"))
    return render(
        request,
        "accounts/district_interop_partner.html",
        {"school": school, "checklist": checklist},
    )


@login_required
@require_http_methods(["GET", "POST"])
def institution_profile_wizard(request):
    if not _can_district_interop(request.user):
        return HttpResponseForbidden("Not allowed.")
    school, redir = _school_or_redirect(request)
    if redir:
        return redir
    if request.method == "POST":
        modes = request.POST.getlist("delivery_modes")
        inst = (request.POST.get("institution_type") or "").strip().upper()
        apply_learning_institution_packs(
            school,
            delivery_mode_codes=modes or None,
            institution_type_code=inst or None,
        )
        messages.success(
            request, "Institution profile and delivery modes applied to runtime."
        )
        return HttpResponseRedirect(reverse("accounts:institution_profile_wizard"))
    st = get_school_settings_dict(school)
    selected = set(st.get("learning_delivery_modes") or [])
    current_inst = (st.get("institution_type_pack") or "").strip()
    from apps.platform_runtime.learning_institution_catalog import MINISTRY_REPORT_STUBS

    stub_slugs = list(st.get("ministry_report_stub_slugs") or [])
    slug_to_label = {}
    for rows in MINISTRY_REPORT_STUBS.values():
        for r in rows or []:
            slug_to_label[r["slug"]] = r.get("label") or r["slug"]
    ministry_stub_rows = [
        {
            "slug": s,
            "label": slug_to_label.get(s, s),
            "pdf_url": reverse("api:api-ministry-stub-pdf") + f"?stub={s}",
        }
        for s in stub_slugs
    ]
    return render(
        request,
        "accounts/institution_profile_wizard.html",
        {
            "school": school,
            "delivery_modes": LEARNING_DELIVERY_MODES,
            "institution_packs": INSTITUTION_TYPE_PACKS,
            "selected_delivery_codes": selected,
            "current_institution_code": current_inst,
            "suggest_url": reverse("api:api-institution-suggest"),
            "pack_install_url": reverse("api:api-learning-pack-install"),
            "runtime_summary": {
                "delivery_wedges": st.get("learning_delivery_wedges"),
                "institution_wedge": st.get("institution_type_wedge"),
                "ministry_stubs": stub_slugs,
                "workflow_hints_count": len(st.get("workflow_pack_hints") or []),
                "report_hints_count": len(st.get("report_template_hints") or []),
            },
            "ministry_stub_rows": ministry_stub_rows,
        },
    )
