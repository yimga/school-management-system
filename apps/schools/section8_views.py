"""
Section 8: Industry Interoperability — landing, Caddy ask, LTI placeholder, global login.
"""
import os
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import redirect
from django.db.models import Q


def _caddy_ip_allowed(request) -> bool:
    """If CADDY_CHECK_ALLOWED_IPS is set (comma-separated), only those IPs are allowed. Otherwise all allowed."""
    allowed = os.getenv("CADDY_CHECK_ALLOWED_IPS", "").strip()
    if not allowed:
        return True
    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    return remote in [ip.strip() for ip in allowed.split(",") if ip.strip()]


@require_GET
@csrf_exempt
def verify_caddy_domain(request):
    """
    Section 8.5: Caddy on-demand TLS "ask" endpoint.
    GET ?domain=greenwood.yoursystem.com → 200 if domain allowed, 404 otherwise.
    If CADDY_CHECK_ALLOWED_IPS is set (comma-separated), only those IPs get 200/404; others get 403.
    """
    if not _caddy_ip_allowed(request):
        return HttpResponseForbidden("IP not allowed")
    domain = (request.GET.get("domain") or "").strip()
    if not domain:
        return HttpResponseNotFound("Missing domain parameter")
    domain_lower = domain.lower()
    if domain_lower in ("localhost", "127.0.0.1", "::1"):
        return HttpResponseNotFound("Internal domains not allowed")
    from .models import School
    # Subdomain: first label (e.g. greenwood from greenwood.yoursystem.com)
    subdomain = domain_lower.split(".")[0] if "." in domain_lower else domain_lower
    # Subdomain: any matching school; custom_domain: only if verified (Section 8.5)
    by_subdomain = School.objects.filter(subdomain=subdomain).exists()
    if by_subdomain:
        return HttpResponse(status=200)
    by_custom = School.objects.filter(
        custom_domain=domain_lower, custom_domain_verified=True
    ).exists()
    if by_custom:
        return HttpResponse(status=200)
    return HttpResponseNotFound("Domain not recognized")


DISCOVERY_RATE_LIMIT_KEY = "discovery_post:{ip}"
DISCOVERY_RATE_LIMIT_MAX = 10
DISCOVERY_RATE_LIMIT_WINDOW = 60 * 15  # 15 minutes


def _discovery_rate_limit_exceeded(request) -> bool:
    """True if this IP has exceeded POST rate limit for /discover/."""
    from django.core.cache import cache
    ip = (request.META.get("REMOTE_ADDR") or "unknown").strip()
    key = DISCOVERY_RATE_LIMIT_KEY.format(ip=ip)
    count = cache.get(key, 0)
    return count >= DISCOVERY_RATE_LIMIT_MAX


def _discovery_rate_limit_incr(request) -> None:
    """Increment POST count for this IP."""
    from django.core.cache import cache
    ip = (request.META.get("REMOTE_ADDR") or "unknown").strip()
    key = DISCOVERY_RATE_LIMIT_KEY.format(ip=ip)
    try:
        count = cache.get(key, 0) + 1
        cache.set(key, count, timeout=DISCOVERY_RATE_LIMIT_WINDOW)
    except Exception:
        pass


@require_http_methods(["GET", "POST"])
def global_login_discovery(request):
    """
    Section 8.4: Global login / discovery. Email → lookup school(s) → redirect to school portal.
    GET: show form (email). POST: lookup user/school, redirect to school URL or show "Get Started".
    Rate limited: max DISCOVERY_RATE_LIMIT_MAX POSTs per IP per 15 minutes to reduce email enumeration.
    """
    if request.method == "GET":
        from django.shortcuts import render
        return render(request, "schools/global_login_discovery.html", {})
    if _discovery_rate_limit_exceeded(request):
        from django.shortcuts import render
        return render(request, "schools/global_login_discovery.html", {
            "error": "Too many attempts. Please try again later.",
        }, status=429)
    email = (request.POST.get("email") or "").strip()
    if not email:
        from django.shortcuts import render
        return render(request, "schools/global_login_discovery.html", {"error": "Please enter your email."})
    from django.conf import settings
    from .models import SchoolMembership
    memberships = SchoolMembership.objects.filter(
        user__email__iexact=email,
        school__is_active=True,
    ).select_related("school")[:1]
    membership = memberships.first()
    if membership:
        _discovery_rate_limit_incr(request)
        school = membership.school
        base = getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or request.get_host().split(":")[0]
        if school.subdomain:
            scheme = "https" if request.is_secure() else "http"
            school_url = f"{scheme}://{school.subdomain}.{base}"
            return redirect(school_url)
        try:
            from django.urls import reverse
            return redirect(reverse("accounts:login") + f"?next=/portal/")
        except Exception:
            return redirect("accounts:login")
    _discovery_rate_limit_incr(request)
    from django.shortcuts import render
    return render(request, "schools/global_login_discovery.html", {
        "error": "No school found for this email. Get started by creating a school.",
        "email": email,
    })


@require_GET
def lti_launch_placeholder(request, tool_id):
    """
    Section 8.3: Single launcher /lti/launch/<tool_id>/.
    Placeholder: load ServiceIntegration by tool_id (pk or slug), return 501 or redirect when LTI 1.3 implemented.
    """
    from apps.siteconfig.models import ServiceIntegration
    from django.shortcuts import get_object_or_404
    try:
        pk = int(tool_id)
        integration = ServiceIntegration.objects.filter(pk=pk, service_type="LTI", is_active=True).select_related("school").first()
    except ValueError:
        integration = None
    if not integration:
        return JsonResponse({"error": "LTI tool not found or inactive."}, status=404)
    return JsonResponse({
        "message": "LTI 1.3 launch not yet implemented. Configure PyLTI1p3 and AGS/NRPS for full support.",
        "school": str(integration.school_id),
        "service_name": integration.service_name,
    }, status=501)


@require_GET
def jwks_json(request):
    """
    Section 8.3: Public keys endpoint for LTI 1.3. Placeholder: return empty keys until keys stored in DB.
    """
    return JsonResponse({"keys": []})


def frozen_account(request):
    """
    Section 8.6: Frozen account page. Shown when TenantFreezeMiddleware redirects;
    display frozen_reason and link to billing/upgrade. No auth required to view.
    """
    from django.shortcuts import render
    school = getattr(request, "school", None)
    reason = getattr(school, "frozen_reason", None) or "STORAGE"
    return render(request, "schools/frozen_account.html", {"frozen_reason": reason})
