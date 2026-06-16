"""
Secure impersonation: switch-to-tenant (BR-12 split from super_views).
"""

from __future__ import annotations

import base64
import json
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.signing import TimestampSigner
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.compliance.models_audit import AuditLog
from apps.siteconfig.models import ImpersonationLog

from .control_plane import log_control_plane_action, user_has_control_plane_access
from .models import School
from .super_views_constants import CONTROL_PLANE_AUDIT_FAILURES
from .tenant_url import build_tenant_backend_url


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _can_impersonate(request):
    """True when actor has control-plane access and platform.impersonate scope."""
    if not getattr(request.user, "is_authenticated", False):
        return False
    if not user_has_control_plane_access(request.user):
        return False
    from apps.platform_runtime.operator_identity import (
        PLATFORM_SCOPE_IMPERSONATE,
        user_has_platform_scope,
    )

    return user_has_platform_scope(request.user, PLATFORM_SCOPE_IMPERSONATE)


def operator_can_impersonate_school(user, school) -> bool:
    """Per-tenant gate: which operators may switch into which tenant.

    ``_can_impersonate`` answers "may this operator impersonate at all"; this
    answers "into THIS tenant". True when ANY of:
      - the actor is a superuser (platform root of trust — never self-lock);
      - an active ``OperatorTenantAssignment`` for (user, school) exists;
      - an active JIT grant for this operator exists in ``school.settings``
        (the existing just-in-time engine — integrated, not duplicated).
    Otherwise False -> the caller returns 403.
    """
    if getattr(user, "is_superuser", False):
        return True
    try:
        from apps.platform_runtime.models import OperatorTenantAssignment

        if OperatorTenantAssignment.has_active(user, school):
            return True
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    try:
        from apps.platform_runtime.jit_operator_controller import (
            check_jit_authorization,
        )

        grant = check_jit_authorization(
            operator_user_id=getattr(user, "id", None),
            school_settings=getattr(school, "settings", None),
        )
        if grant.granted:
            return True
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    return False


@require_POST
def switch_to_tenant(request):
    """
    Super-admin only. Accepts school_id (POST), creates a short-lived signed token,
    logs ImpersonationLog.SWITCH, redirects to the tenant's impersonation entry URL.
    """
    if not _can_impersonate(request):
        return HttpResponseForbidden("Super Admin access required.")

    school_id = request.POST.get("school_id", "").strip()
    if not school_id:
        return HttpResponseBadRequest("school_id required.")
    school = get_object_or_404(School, id=school_id, is_active=True)

    # Per-tenant assignment gate: holding platform.impersonate is not enough —
    # the operator must be assigned to THIS tenant (or hold an active JIT grant).
    if not operator_can_impersonate_school(request.user, school):
        try:
            log_control_plane_action(
                request,
                AuditLog.Action.ACCESS_DENIED,
                "School",
                str(school.id),
                object_repr=school.name or str(school.id),
                reason="Impersonation denied: operator not assigned to this tenant",
                sensitivity=AuditLog.Sensitivity.HIGH,
            )
        except CONTROL_PLANE_AUDIT_FAILURES:
            pass
        return HttpResponseForbidden(
            "You are not assigned to this tenant. Request a tenant assignment "
            "or a just-in-time grant before impersonating."
        )

    _User = get_user_model()
    peer_user = None
    if getattr(school, "impersonation_dual_control", False):
        from django.contrib import messages
        from apps.platform_runtime.operator_identity import (
            PLATFORM_SCOPE_IMPERSONATE,
            user_has_platform_scope,
        )

        peer_id = (request.POST.get("peer_approver_id") or "").strip()
        peer_email = (request.POST.get("peer_approver_email") or "").strip().lower()
        if peer_id:
            try:
                peer_user = _User.objects.get(pk=int(peer_id))
            except (ValueError, _User.DoesNotExist):
                messages.error(request, "Peer approver was not found.")
                return redirect("super:dashboard")
        elif peer_email:
            try:
                peer_user = _User.objects.get(email__iexact=peer_email)
            except _User.DoesNotExist:
                messages.error(request, "Peer approver email was not found.")
                return redirect("super:dashboard")
        else:
            messages.error(
                request,
                "This school requires a second approver (four-eyes impersonation).",
            )
            return redirect("super:dashboard")
        if peer_user.pk == request.user.pk:
            messages.error(
                request,
                "Second approver must be a different platform operator than the requester.",
            )
            return redirect("super:dashboard")
        if not user_has_control_plane_access(peer_user):
            messages.error(
                request,
                "Peer approver must be a platform operator (superuser or SUPERADMIN).",
            )
            return redirect("super:dashboard")
        if not user_has_platform_scope(peer_user, PLATFORM_SCOPE_IMPERSONATE):
            messages.error(
                request,
                "Peer approver must have platform.impersonate scope.",
            )
            return redirect("super:dashboard")
    reason = (request.POST.get("impersonation_reason") or "").strip()
    ticket_ref = (request.POST.get("support_ticket_ref") or "").strip()[:120]
    if getattr(settings, "IMPERSONATION_REQUIRE_JUSTIFICATION", True):
        if len(reason) < 3:
            from django.contrib import messages

            messages.error(
                request,
                "Impersonation requires a short justification (reason for access).",
            )
            return redirect("super:dashboard")
    allow_writes = request.POST.get("allow_writes") == "1"
    if getattr(settings, "IMPERSONATION_DEFAULT_READ_ONLY", True):
        read_only = not allow_writes
    else:
        read_only = False
    # JIT: principal consent required before impersonation (195-country governance; configurable).
    if getattr(settings, "JIT_IMPERSONATION_REQUIRE_CONSENT", True):
        from datetime import timedelta

        from django.utils import timezone

        consent_at = getattr(school, "impersonation_consent_granted_at", None)
        if not consent_at:
            from django.contrib import messages

            messages.error(
                request,
                "Impersonation requires principal consent for this school. Ask the school admin to grant consent in their Backend settings.",
            )
            return redirect("super:dashboard")
        # Optional: consent expires after N days (e.g. 30)
        consent_days = getattr(settings, "JIT_IMPERSONATION_CONSENT_DAYS", 30)
        if consent_days and timezone.now() - consent_at > timedelta(days=consent_days):
            from django.contrib import messages

            messages.warning(
                request,
                "Impersonation consent for this school has expired. Principal must re-grant.",
            )
            return redirect("super:dashboard")
    payload = {
        "school_id": str(school.id),
        "user_id": request.user.id,
        "read_only": read_only,
    }
    payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    signer = TimestampSigner(key=getattr(settings, "SECRET_KEY", "fallback"))
    token = signer.sign(payload_b64)
    # Audit
    ImpersonationLog.objects.create(
        actor=request.user,
        peer_actor=peer_user,
        school=school,
        action=ImpersonationLog.Action.SWITCH,
        ip_address=_get_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
        reason=reason,
        support_ticket_ref=ticket_ref,
        read_only=read_only,
    )
    try:
        log_control_plane_action(
            request,
            AuditLog.Action.VIEW,
            "School",
            str(school.id),
            object_repr=school.name or str(school.id),
            reason="Impersonation switch (control plane)",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
        )
    except CONTROL_PLANE_AUDIT_FAILURES:
        pass
    if peer_user:
        try:
            AuditLog.objects.create(
                action=AuditLog.Action.APPROVE,
                user=peer_user,
                ip_address=_get_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
                model_name="ImpersonationSession",
                object_id=str(school.id),
                object_repr=school.name or str(school.id),
                app_label="schools",
                sensitivity=AuditLog.Sensitivity.CRITICAL,
                new_values={
                    "peer_approval": True,
                    "initiator_id": request.user.pk,
                    "school_id": str(school.id),
                    "read_only": read_only,
                },
                reason="Dual-control impersonation peer recorded (four-eyes)",
            )
        except Exception:
            pass
    entry_path = "/authentication/impersonate/"
    next_url = request.POST.get("next", "/").strip() or "/"
    url = build_tenant_backend_url(request, school, path=entry_path)
    sep = "&" if "?" in url else "?"
    query = urlencode({"impersonate": token, "next": next_url})
    redirect_to = f"{url}{sep}{query}"
    return redirect(redirect_to)
