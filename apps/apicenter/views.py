"""
API Center: one page for all Integrations (config + governance). Toggle enabled with reason; audit log.
"""

from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect

from django.contrib import messages

from django.utils.translation import gettext as _
from apps.integrations_marketplace.models import Integration
from apps.platform_runtime.helpers import get_effective_flags
from apps.schools.control_plane import user_has_control_plane_access
from .models import APIAuditLog, APIKey, APIQuota, _hash_secret
from services.post_delete_navigation import redirect_after_delete


def _is_manager_host(request):
    return getattr(request, "public_host_kind", None) == "manager"


def _apicenter_back_action(request):
    if request.GET.get("embed"):
        try:
            return reverse("studio_os:control"), _("Back to Control")
        except NoReverseMatch:
            pass
    if _is_manager_host(request):
        try:
            return reverse("super:dashboard"), _("Back to command center")
        except NoReverseMatch:
            pass
    return reverse("accounts:backend_dashboard"), _("Back to dashboard")


#: Why the API Center said no. These are three DIFFERENT KINDS of refusal and
#: they must never share one sentence. The page used to answer every one of them
#: with "API Center is disabled or you do not have permission." -- a single
#: string covering a tenant configuration fact, a missing grant, and a
#: manager-host isolation rule at once. For a platform superadmin, who holds
#: every permission code there is, the "or you do not have permission" half was
#: not merely unhelpful, it was untrue.
API_CENTER_OK = ""
#: Manager host, actor is not a platform operator at all.
API_CENTER_DENY_CONTROL_PLANE = "control-plane"
#: Tenant host, actor may not use this surface.
API_CENTER_DENY_PERMISSION = "permission"
#: Tenant host, actor MAY use this surface -- the school has not switched it on.
API_CENTER_DENY_DISABLED = "disabled"


def _has_api_center_authority(user):
    """May this account use the API Center at all, ignoring the tenant's switch?

    ``has_feature_permission`` already answers True for a platform superadmin on
    any code (see apps/accounts/superadmin.py), so god-mode needs no special case
    here -- adding one would be a second resolver to drift out of step with the
    first.
    """
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "has_feature_permission", lambda _code: False)(
        "api_center.manage"
    ):
        return True
    role = (getattr(user, "role", "") or "").upper()
    return role in ("ADMIN", "IT_ADMIN")


def _api_center_denial_reason(request):
    """Return API_CENTER_OK, or the specific reason this request is refused.

    Authority is checked BEFORE the tenant flag, which is a deliberate ordering
    on two counts. It keeps the tenant's configuration from leaking to someone
    with no business on the surface, and it means an account that IS entitled to
    the API Center -- a superadmin above all -- is never told it lacks
    permission when the real answer is that the school has not enabled it.
    """
    user = getattr(request, "user", None)
    if getattr(request, "public_host_kind", None) == "manager":
        if user_has_control_plane_access(user):
            return API_CENTER_OK
        return API_CENTER_DENY_CONTROL_PLANE
    if not _has_api_center_authority(user):
        return API_CENTER_DENY_PERMISSION
    if not get_effective_flags(request).get("enable_api_center", False):
        return API_CENTER_DENY_DISABLED
    return API_CENTER_OK


def _api_center_allowed(request):
    """Boolean form of :func:`_api_center_denial_reason`, kept for readability."""
    return _api_center_denial_reason(request) == API_CENTER_OK


def _api_center_denied(request):
    """The refusal, worded for the reason it actually happened.

    A tenant feature switch is not a permission. When the school has simply not
    turned the API Center on, this says so and -- for an actor who can flip it --
    hands them the switch instead of a dead end.
    """
    reason = _api_center_denial_reason(request)
    if reason == API_CENTER_DENY_CONTROL_PLANE:
        return HttpResponseForbidden(
            _("Control-plane access is required to open the API Center here.")
        )
    user = getattr(request, "user", None)
    feature_control_url = None
    if reason == API_CENTER_DENY_DISABLED and getattr(
        user, "has_feature_permission", lambda _code: False
    )("settings.feature_control"):
        try:
            feature_control_url = reverse("siteconfig:feature_control_panel")
        except NoReverseMatch:
            feature_control_url = None
    # A refusal page must never be the thing that 500s.
    try:
        back_url = _apicenter_back_action(request)[0]
    except NoReverseMatch:
        back_url = None
    return render(
        request,
        "apicenter/api_center_unavailable.html",
        {
            "reason": reason,
            "is_disabled": reason == API_CENTER_DENY_DISABLED,
            "feature_control_url": feature_control_url,
            "back_url": back_url,
        },
        status=403,
    )


@login_required
@require_GET
@csrf_protect
def api_center_dashboard(request):
    """List all Integrations (one module); toggle enabled with reason; audit log."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    school = getattr(request, "school", None)
    if school is None and getattr(request, "public_host_kind", None) != "manager":
        return HttpResponseForbidden("School context required.")
    integrations = (
        Integration.objects.filter(Q(school__isnull=True) | Q(school=school))
        if school
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        else Integration.objects.all()
    )
    integrations = integrations.order_by("provider", "name")
    audit_logs = APIAuditLog.objects.select_related("integration", "changed_by")
    if school is not None:
        audit_logs = audit_logs.filter(
            Q(integration__school__isnull=True) | Q(integration__school=school)
        )
    audit_logs = audit_logs.order_by("-created_at")[:50]
    # Governance: scope/permission/rate visibility per integration (Step 37).
    quotas = list(
        APIQuota.objects.filter(Q(school__isnull=True) | Q(school=school)).order_by(
            "quota_type"
        )
    )
    quotas_by_school = {}
    for q in quotas:
        key = q.school_id or "platform"
        quotas_by_school.setdefault(key, []).append(q)
    action_url, action_text = _apicenter_back_action(request)
    integ_list = list(integrations)
    n_total = len(integ_list)
    n_on = sum(1 for i in integ_list if getattr(i, "enabled", False))
    audit_list = list(audit_logs)[:4]
    activity = []
    for log in audit_list:
        integ = getattr(log, "integration", None)
        integ_name = getattr(integ, "name", "") if integ is not None else ""
        try:
            title = log.get_action_display()
        except (AttributeError, TypeError, ValueError):
            title = str(getattr(log, "action", "change"))
        activity.append({"title": str(title), "meta": str(integ_name)})
    if not activity:
        activity.append({"title": "API Center", "meta": "No recent audit rows."})
    phase7_de = {
        "eyebrow": "Integrations home",
        "headline_label": "Active integrations",
        "headline_value": n_on,
        "headline_meta": f"{n_total} configured",
        "metrics": [
            {
                "label": "Enabled",
                "value": n_on,
                "meta": "Kill-switch ready",
                "status": "ok",
            },
            {
                "label": "Disabled",
                "value": n_total - n_on,
                "meta": "Off or paused",
                "status": "warn" if n_total - n_on else "ok",
            },
            {
                "label": "Quotas",
                "value": len(quotas),
                "meta": "Rate limits",
                "status": "ok",
            },
        ],
        "urgent_queue": [
            {
                "title": "Review disabled integrations",
                "url": request.get_full_path() + "#apicenter-all-integrations",
                "hint": "Each toggle requires a reason and writes audit.",
            }
        ]
        if n_total - n_on
        else [
            {
                "title": "All integrations enabled",
                "url": "",
                "hint": "Keep monitoring audit log.",
            }
        ],
        "next_actions": [
            {"label": action_text, "url": action_url},
            {
                "label": "Domain hub",
                "url": reverse("siteconfig:console_domains_hub"),
            },
            {"label": "Reload", "url": request.get_full_path()},
        ],
        "activity": activity,
    }
    return render(
        request,
        "apicenter/dashboard.html",
        {
            "integrations": integrations,
            "audit_logs": audit_logs,
            "api_quotas": quotas,
            "quotas_by_school": quotas_by_school,
            "page_title": _("Integrations & API Center"),
            "page_subtitle": _(
                "One place for all external integrations. Toggle on or off (kill switch); a reason is required and recorded in the audit log."
            ),
            "action_url": action_url,
            "action_text": action_text,
            "phase7_de": phase7_de,
        },
    )


@login_required
@require_POST
@csrf_protect
def api_center_toggle(request, slug):
    """Toggle Integration.enabled; require reason. Write to APIAuditLog."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    school = getattr(request, "school", None)
    if school is None and getattr(request, "public_host_kind", None) != "manager":
        return HttpResponseForbidden("School context required.")
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    integrations = Integration.objects.all()
    if school is not None:
        integrations = integrations.filter(Q(school__isnull=True) | Q(school=school))
    integration = get_object_or_404(integrations, slug=slug)
    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        messages.error(
            request, _("A reason is required when enabling or disabling an integration.")
        )
        return redirect("apicenter:dashboard")
    new_enabled = not integration.enabled
    integration.enabled = new_enabled
    integration.save(update_fields=["enabled", "updated_at"])
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
        0
    ].strip() or request.META.get("REMOTE_ADDR")
    APIAuditLog.objects.create(
        integration=integration,
        changed_by=request.user,
        action=APIAuditLog.Action.ENABLED
        if new_enabled
        else APIAuditLog.Action.DISABLED,
        reason=reason,
        ip_address=ip or None,
    )
    messages.success(
        request,
        f'"{integration.name}" is now {"enabled" if new_enabled else "disabled"}.',
    )
    return redirect("apicenter:dashboard")


@login_required
@require_GET
def api_portal_docs(request):
    """Developer platform documentation and onboarding portal."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    return render(request, "apicenter/api_portal_docs.html", {})


@login_required
@require_GET
def webhook_docs(request):
    """Developer platform (8.1): webhook docs and subscription list UI."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    from apps.events.models import WebhookSubscription
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    school = getattr(request, "school", None)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    subscriptions = WebhookSubscription.objects.all().order_by("-created_at")
    if school is not None:
        subscriptions = subscriptions.filter(school_id=getattr(school, "id", None))
    return render(
        request,
        "apicenter/webhook_docs.html",
        {"subscriptions": subscriptions[:50]},
    )


@login_required
@require_GET
def api_keys(request):
    """Developer platform (8.1): List API keys. Create via api_key_create (POST); revoke via api_key_revoke (POST)."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    school = getattr(request, "school", None)
    qs = APIKey.objects.select_related("created_by", "school").order_by("-created_at")
    if school is not None:
        qs = qs.filter(Q(school__isnull=True) | Q(school=school))
    keys = list(qs[:100])
    quotas = (
        list(
            APIQuota.objects.filter(Q(school__isnull=True) | Q(school=school)).order_by(
                "quota_type"
            )
        )
        if school
        else list(APIQuota.objects.filter(school__isnull=True))
    )
    new_key_display = request.session.pop("apicenter_new_key_display", None)
    return render(
        request,
        "apicenter/api_keys.html",
        {"api_keys": keys, "api_quotas": quotas, "new_key_display": new_key_display},
    )


@login_required
@require_POST
@csrf_protect
def api_key_create(request):
    """Create an API key; show raw secret once in session, then redirect to keys list."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    school = getattr(request, "school", None)
    if school is None and getattr(request, "public_host_kind", None) != "manager":
        return HttpResponseForbidden("School context required.")
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, _("Key name is required."))
        return redirect("apicenter:api_keys")
    key_prefix, raw_secret = APIKey.generate_key_pair()
    key = APIKey.objects.create(
        school=school,
        name=name,
        key_prefix=key_prefix,
        secret_hash=_hash_secret(raw_secret),
        created_by=request.user,
    )
    request.session["apicenter_new_key_display"] = {
        "name": key.name,
        "raw_secret": raw_secret,
        "key_prefix": key.key_prefix,
    }
    messages.success(
        request, _("API key created. Copy the key below; it will not be shown again.")
    )
    return redirect("apicenter:api_keys")


@login_required
@require_POST
@csrf_protect
def api_key_revoke(request, key_id):
    """Revoke an API key (set revoked_at)."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    school = getattr(request, "school", None)
    qs = APIKey.objects.all()
    if school is not None:
        qs = qs.filter(Q(school__isnull=True) | Q(school=school))
    key = get_object_or_404(qs, pk=key_id)
    if key.revoked_at:
        messages.warning(request, _("This key is already revoked."))
    else:
        key.revoked_at = timezone.now()
        key.save(update_fields=["revoked_at"])
        messages.success(request, f"Key {key.key_prefix}… revoked.")
    return redirect("apicenter:api_keys")


@login_required
@require_GET
def webhook_subscription_list(request):
    """Webhook subscriptions list (alias for webhook_docs)."""
    return webhook_docs(request)


@login_required
@csrf_protect
def webhook_subscription_create(request):
    """Create webhook subscription (8.1). GET: form; POST: create."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    from apps.events.models import WebhookSubscription

    school = getattr(request, "school", None)
    school_id = getattr(school, "id", None) if school else None
    if request.method == "POST":
        url = (request.POST.get("url") or "").strip()
        if not url:
            messages.error(request, _("URL is required."))
            return redirect("apicenter:webhook_subscription_create")
        event_types_raw = (request.POST.get("event_types") or "").strip()
        event_types = (
            [x.strip() for x in event_types_raw.split(",") if x.strip()]
            if event_types_raw
            else []
        )
        desc = (request.POST.get("description") or "").strip()
        secret = (request.POST.get("secret") or "").strip()
        WebhookSubscription.objects.create(
            school_id=school_id,
            url=url,
            event_types=event_types,
            description=desc[:255],
            secret=secret[:255] if secret else "",
            is_active=True,
        )
        messages.success(request, _("Webhook subscription created."))
        return redirect("apicenter:webhook_docs")
    return render(
        request,
        "apicenter/webhook_subscription_form.html",
        {"subscription": None, "is_edit": False},
    )


@login_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def webhook_subscription_edit(request, pk: int):
    """Edit webhook subscription (8.1). GET: form; POST: save."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    from apps.events.models import WebhookSubscription
# tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph

    school = getattr(request, "school", None)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    qs = WebhookSubscription.objects.all()
    if school is not None:
        qs = qs.filter(school_id=getattr(school, "id", None))
    subscription = get_object_or_404(qs, pk=pk)
    if request.method == "POST":
        subscription.url = (request.POST.get("url") or "").strip() or subscription.url
        event_types_raw = (request.POST.get("event_types") or "").strip()
        subscription.event_types = (
            [x.strip() for x in event_types_raw.split(",") if x.strip()]
            if event_types_raw
            else []
        )
        subscription.description = (request.POST.get("description") or "").strip()[:255]
        if request.POST.get("secret"):
            subscription.secret = (request.POST.get("secret") or "").strip()[:255]
        subscription.is_active = (
            request.POST.get("is_active") == "on"
            or request.POST.get("is_active") == "1"
        )
        subscription.save()
        messages.success(request, _("Webhook subscription updated."))
        return redirect("apicenter:webhook_docs")
    return render(
        request,
        "apicenter/webhook_subscription_form.html",
        {"subscription": subscription, "is_edit": True},
    )


@login_required
@require_POST
@csrf_protect
def webhook_subscription_delete(request, pk: int):
    """Delete webhook subscription (8.1)."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    from apps.events.models import WebhookSubscription

    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    school = getattr(request, "school", None)
    qs = WebhookSubscription.objects.all()
    if school is not None:
        qs = qs.filter(school_id=getattr(school, "id", None))
    sub = get_object_or_404(qs, pk=pk)
    sub.delete()
    messages.success(request, _("Webhook subscription deleted."))
    docs_url = reverse("apicenter:webhook_docs")
    return redirect_after_delete(request, docs_url, list_url=docs_url)


@login_required
@require_GET
def sdk_docs(request):
    """SDK and language-neutral REST client guidance."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    return render(request, "apicenter/sdk_docs.html", {})


@login_required
@require_GET
def app_certification(request):
    """Marketplace app certification requirements."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    return render(request, "apicenter/app_certification.html", {})


@login_required
@require_GET
def partner_sandbox(request):
    """Partner sandbox operating and data-handling requirements."""
    if not _api_center_allowed(request):
        return _api_center_denied(request)
    return render(request, "apicenter/partner_sandbox.html", {})
