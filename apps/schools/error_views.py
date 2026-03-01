"""
Dedicated error views for multi-tenant flows (e.g. School Not Found 404).
"""
from django.shortcuts import render


def school_not_found(request):
    """
    Branded "School Not Found" bento-style 404 when a subdomain or /t/<slug>/
    does not map to any tenant. Use in middleware or as handler404 for tenant routes.
    """
    return render(
        request,
        "schools/404_tenant.html",
        status=404,
    )
