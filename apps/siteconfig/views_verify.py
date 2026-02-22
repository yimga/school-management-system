"""
Public verify page for Digital ID (plan 3.17). QR points to /verify/<token>/.
Rate-limit by IP; JWT short expiry; return JSON or HTML with name, photo, status only.
"""
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache

from apps.siteconfig.student_id_service import verify_student_token, rate_limit_verify


def _get_client_ip(request):
    try:
        from ipware import get_client_ip
        ip, _ = get_client_ip(request)
        return ip or ""
    except ImportError:
        return (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )


@require_GET
@never_cache
@csrf_exempt
def verify_student_id(request, token: str):
    """
    GET /verify/<token>/ — Public verification; no auth.
    Returns 401 if token invalid/expired; 429 if rate limited; 200 JSON { name, photo, status }.
    """
    ip = _get_client_ip(request)
    if rate_limit_verify(ip):
        return HttpResponse(status=429)
    payload = verify_student_token(token)
    if not payload:
        return HttpResponse(status=401)
    # Expose only name, photo, status (no address, grades)
    return JsonResponse({
        "name": payload.get("name", ""),
        "photo": payload.get("photo", ""),
        "status": payload.get("status", "active"),
        "grade": payload.get("grade", ""),
    })
