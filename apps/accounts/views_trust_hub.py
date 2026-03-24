"""
Phase 8 — in-product trust surfaces for tenants (MFA, sessions, governance links,
impersonation audit for leadership).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse

from apps.schools.mixins import require_school


def _leadership_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    r = (getattr(user, "role", "") or "").upper()
    return r in ("ADMIN", "LEADERSHIP", "PRINCIPAL", "IT_ADMIN")


def _safe_reverse(name: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return ""


@login_required
@require_school
def security_trust_hub(request):
    """
    Visible trust posture for the signed-in user on this school: MFA, sessions,
    personal security export, links to RBAC / compliance / API Center for admins.
    """
    user = request.user
    school = request.school
    mfa_enabled = False
    try:
        from django_otp import user_has_device

        try:
            mfa_enabled = bool(user_has_device(user, confirmed=True))
        except TypeError:
            mfa_enabled = bool(user_has_device(user))
    except (ImportError, AttributeError, TypeError):
        pass

    leadership = _leadership_ok(user)
    ctx = {
        "school": school,
        "mfa_enabled": mfa_enabled,
        "show_governance_links": leadership,
        "urls": {
            "mfa_setup": _safe_reverse("accounts:mfa_setup"),
            "sessions": _safe_reverse("accounts:sessions_page"),
            "security_export": _safe_reverse("accounts:api_security_export_log"),
            "security_activity": _safe_reverse("accounts:api_security_activity"),
            "rbac": _safe_reverse("accounts:rbac"),
            "compliance": _safe_reverse("compliance:dashboard"),
            "apicenter": _safe_reverse("apicenter:dashboard"),
            "tenant_activity": _safe_reverse("accounts:tenant_activity_log"),
            "impersonation_audit": _safe_reverse("accounts:tenant_impersonation_audit"),
            "feature_control": _safe_reverse("siteconfig:feature_control_panel"),
            "feature_control_audit": _safe_reverse("siteconfig:feature_control_audit"),
            "backend_home": _safe_reverse("accounts:backend_dashboard"),
        },
    }
    return render(request, "accounts/security_trust_hub.html", ctx)


@login_required
@require_school
def tenant_impersonation_audit(request):
    """Support impersonation events for this school (break-glass visibility)."""
    if not _leadership_ok(request.user):
        return HttpResponseForbidden("Not allowed.")
    from apps.siteconfig.models import ImpersonationLog

    school = request.school
    rows = list(
        ImpersonationLog.objects.filter(school=school)
        .select_related("actor", "peer_actor")
        .order_by("-created_at")[:200]
    )
    return render(
        request,
        "accounts/tenant_impersonation_audit.html",
        {"school": school, "rows": rows},
    )
