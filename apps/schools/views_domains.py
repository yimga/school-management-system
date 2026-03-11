"""
Tenant-side custom domain API and wizard: list/add/verify domains.
Requires request.school; used in School Settings.
"""
import json
from json import JSONDecodeError
import re
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.schools.domain_sync import is_runtime_domain_in_use, normalize_domain
from apps.schools.dns_verification import verify_and_activate_schooldomain
from apps.schools.models import School, SchoolDomain
from apps.schools.tenant_url import get_base_domain


def _require_school_admin(request):
    """Require authenticated user with admin access to request.school."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return False
    school = getattr(request, "school", None)
    if not school:
        return False
    from apps.schools.models import SchoolMembership
    role = (getattr(request.user, "role", "") or "").upper()
    if role in ("ADMIN", "IT_ADMIN", "LEADERSHIP") or request.user.is_staff or request.user.is_superuser:
        return True
    return SchoolMembership.objects.filter(user=request.user, school=school, role__in=("ADMIN", "IT_ADMIN", "LEADERSHIP")).exists()


@require_http_methods(["GET", "POST"])
@login_required
@ensure_csrf_cookie
def api_domains_list_or_create(request):
    """GET /api/tenant/domains/ — list domains. POST — add a pending custom domain (generates dns_token)."""
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    school = request.school
    if request.method == "GET":
        domains = list(
            SchoolDomain.objects.filter(school=school).order_by("kind", "domain").values(
                "id", "domain", "kind", "is_verified", "dns_token", "verified_at", "created_at"
            )
        )
        for d in domains:
            d["verified_at"] = d["verified_at"].isoformat() if d.get("verified_at") else None
            d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
        return JsonResponse({"domains": domains})
    try:
        body = json.loads(request.body) if request.body else {}
    except (JSONDecodeError, TypeError, UnicodeDecodeError, ValueError):
        body = {}
    domain = (request.POST.get("domain") or body.get("domain") or "").strip()
    if not domain:
        return JsonResponse({"error": "domain is required"}, status=400)
    domain = normalize_domain(domain)
    # Basic hostname check
    if not re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", domain) or ".." in domain:
        return JsonResponse({"error": "Invalid domain format"}, status=400)
    base = get_base_domain()
    if base and domain.endswith("." + base):
        return JsonResponse({"error": "Use a custom domain (e.g. portal.yourschool.edu), not a subdomain of the platform"}, status=400)
    if SchoolDomain.objects.filter(school=school, domain=domain).exists():
        return JsonResponse({"error": "This domain is already added"}, status=409)
    if SchoolDomain.objects.filter(domain=domain).exclude(school=school).exists():
        return JsonResponse({"error": "This domain is already used by another school"}, status=409)
    if is_runtime_domain_in_use(domain, school=school):
        return JsonResponse({"error": "This domain is already used by another school"}, status=409)
    obj = SchoolDomain.objects.create(
        school=school,
        domain=domain,
        kind=SchoolDomain.Kind.CUSTOM,
        is_verified=False,
    )
    return JsonResponse({
        "id": str(obj.id),
        "domain": obj.domain,
        "kind": obj.kind,
        "is_verified": obj.is_verified,
        "dns_token": str(obj.dns_token),
        "verified_at": None,
        "created_at": obj.created_at.isoformat(),
    }, status=201)


@require_POST
@login_required
@ensure_csrf_cookie
def api_domains_verify(request, school_domain_id):
    """POST /api/tenant/domains/<id>/verify/ — run DNS check and mark verified if TXT matches."""
    if not _require_school_admin(request):
        return JsonResponse({"error": "Forbidden"}, status=403)
    school = request.school
    domain_entry = get_object_or_404(SchoolDomain, pk=school_domain_id, school=school)
    if domain_entry.is_verified:
        return JsonResponse({
            "id": str(domain_entry.id),
            "domain": domain_entry.domain,
            "is_verified": True,
            "verified_at": domain_entry.verified_at.isoformat() if domain_entry.verified_at else None,
        })
    ok = verify_and_activate_schooldomain(domain_entry)
    domain_entry.refresh_from_db()
    return JsonResponse({
        "id": str(domain_entry.id),
        "domain": domain_entry.domain,
        "is_verified": domain_entry.is_verified,
        "verified_at": domain_entry.verified_at.isoformat() if domain_entry.verified_at else None,
    })


@require_GET
@login_required
def custom_domain_wizard(request):
    """Custom Domain Wizard page (tenant settings)."""
    if not _require_school_admin(request):
        from django.shortcuts import redirect
        return redirect("accounts:login")
    school = request.school
    cname_target = school.get_cname_target()
    domains = list(SchoolDomain.objects.filter(school=school).order_by("-is_verified", "domain"))
    prefix = getattr(request, "tenant_path_prefix", "") or ""
    return render(request, "schools/custom_domain_wizard.html", {
        "school": school,
        "cname_target": cname_target,
        "domains": domains,
        "api_domains_url": prefix.rstrip("/") + "/api/tenant/domains/",
    })
