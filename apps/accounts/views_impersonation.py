"""
Tenant-side handling of super-admin impersonation: consume signed token and set session;
exit impersonation and log audit.
"""
import base64
import json

from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_http_methods


def _parse_impersonation_token(token, max_age_seconds=3600):
    """Return payload dict (school_id, user_id) or None if invalid/expired."""
    if not token:
        return None
    signer = TimestampSigner(key=getattr(settings, "SECRET_KEY", "fallback"))
    try:
        payload_b64 = signer.unsign(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    try:
        payload = json.loads(base64.b64decode(payload_b64).decode())
        if isinstance(payload.get("school_id"), str) and isinstance(payload.get("user_id"), int):
            return payload
    except Exception:
        pass
    return None


@require_GET
@login_required
def impersonate_entry(request):
    """
    GET ?impersonate=TOKEN&next=/. Validates token (signed, short-lived), ensures request.school
    matches token school_id, sets session and redirects to next.
    """
    token = request.GET.get("impersonate", "").strip()
    next_url = (request.GET.get("next") or "/").strip() or "/"
    payload = _parse_impersonation_token(token)
    if not payload:
        return redirect(next_url)
    school = getattr(request, "school", None)
    if not school or str(school.id) != payload["school_id"]:
        return redirect(next_url)
    # Only the actor (super-admin) should be logging in; token user_id is the actor
    if request.user.id != payload["user_id"]:
        return redirect(next_url)
    request.session["impersonation"] = {
        "school_id": str(school.id),
        "actor_id": payload["user_id"],
    }
    request.session.modified = True
    return redirect(next_url)


@require_http_methods(["GET", "POST"])
@login_required
def end_impersonation(request):
    """
    Clear session impersonation, log ImpersonationLog.END, redirect to super dashboard.
    """
    from apps.schools.tenant_url import build_manager_absolute_url
    from apps.siteconfig.models import ImpersonationLog
    from apps.schools.models import School

    impersonation = request.session.pop("impersonation", None)
    request.session.modified = True
    if impersonation:
        school_id = impersonation.get("school_id")
        try:
            school = School.objects.get(id=school_id)
            ImpersonationLog.objects.create(
                actor_id=impersonation.get("actor_id"),
                school=school,
                action=ImpersonationLog.Action.END,
                ip_address=_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            )
        except School.DoesNotExist:
            pass
    return redirect(build_manager_absolute_url(request, "/super/"))


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
