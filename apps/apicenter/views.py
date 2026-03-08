"""
API Center: one page for all Integrations (config + governance). Toggle enabled with reason; audit log.
"""
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect

from apps.siteconfig.models import Integration, SiteSettings
from apps.platform_runtime.helpers import get_effective_flags
from apps.schools.control_plane import user_has_control_plane_access
from .models import APIAuditLog


def _api_center_allowed(request):
    """Require enable_api_center flag and api_center.manage permission (or ADMIN/IT_ADMIN)."""
    flags = get_effective_flags(request)
    if not flags.get("enable_api_center", False):
        return False
    if getattr(request, "public_host_kind", None) == "manager":
        return user_has_control_plane_access(getattr(request, "user", None))
    if getattr(request.user, "is_superuser", False):
        return True
    if getattr(request.user, "has_feature_permission", lambda _: False)("api_center.manage"):
        return True
    role = (getattr(request.user, "role", "") or "").upper()
    return role in ("ADMIN", "IT_ADMIN")


@login_required
@require_GET
@csrf_protect
def api_center_dashboard(request):
    """List all Integrations (one module); toggle enabled with reason; audit log."""
    if not _api_center_allowed(request):
        return HttpResponseForbidden("API Center is disabled or you do not have permission.")
    school = getattr(request, "school", None)
    if school is None and getattr(request, "public_host_kind", None) != "manager":
        return HttpResponseForbidden("School context required.")
    integrations = Integration.objects.filter(Q(school__isnull=True) | Q(school=school)) if school else Integration.objects.all()
    integrations = integrations.order_by("provider", "name")
    audit_logs = APIAuditLog.objects.select_related("integration", "changed_by")
    if school is not None:
        audit_logs = audit_logs.filter(Q(integration__school__isnull=True) | Q(integration__school=school))
    audit_logs = audit_logs.order_by("-created_at")[:50]
    return render(
        request,
        "apicenter/dashboard.html",
        {
            "integrations": integrations,
            "audit_logs": audit_logs,
        },
    )


@login_required
@require_POST
@csrf_protect
def api_center_toggle(request, slug):
    """Toggle Integration.enabled; require reason. Write to APIAuditLog."""
    if not _api_center_allowed(request):
        return HttpResponseForbidden("You do not have permission to manage the API Center.")
    school = getattr(request, "school", None)
    if school is None and getattr(request, "public_host_kind", None) != "manager":
        return HttpResponseForbidden("School context required.")
    integrations = Integration.objects.all()
    if school is not None:
        integrations = integrations.filter(Q(school__isnull=True) | Q(school=school))
    integration = get_object_or_404(integrations, slug=slug)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(request, "A reason is required when enabling or disabling an integration.")
        return redirect("apicenter:dashboard")
    new_enabled = not integration.enabled
    integration.enabled = new_enabled
    integration.save(update_fields=["enabled", "updated_at"])
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    APIAuditLog.objects.create(
        integration=integration,
        changed_by=request.user,
        action=APIAuditLog.Action.ENABLED if new_enabled else APIAuditLog.Action.DISABLED,
        reason=reason,
        ip_address=ip or None,
    )
    messages.success(request, f'"{integration.name}" is now {"enabled" if new_enabled else "disabled"}.')
    return redirect("apicenter:dashboard")
