"""
Interoperability stubs (Improvement #8): OneRoster and LTI 1.3 API placeholders.
Implement per official specs when needed. Global platform — works with any tenant/school.
"""
from django.http import JsonResponse


def oneroster_stub(request):
    """OneRoster 1.1 API placeholder. Implement /classes, /students, /academicSessions, etc. per spec."""
    return JsonResponse(
        {"message": "OneRoster API not yet implemented", "status": "stub"},
        status=501,
    )


def lti13_stub(request):
    """LTI 1.3 launch and JWKS placeholder. Implement OIDC login and resource link launch per spec."""
    return JsonResponse(
        {"message": "LTI 1.3 API not yet implemented", "status": "stub"},
        status=501,
    )
