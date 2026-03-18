"""Versioned public API manifest (§0.3 pillar 4 — contract surface)."""

from django.http import JsonResponse
from django.urls import reverse


def api_v1_manifest(request):
    """Discovery for integrators: stable paths and deprecation policy."""
    base = request.build_absolute_uri("/").rstrip("/")
    return JsonResponse(
        {
            "api": "RunMyCampus",
            "version": "1.0",
            "policy": "Non-breaking additive changes without version bump; breaking changes announced 90d via changelog.",
            "endpoints": {
                "oneroster_v1p1": f"{base}/api/oneroster/v1p1/",
                "health": f"{base}/healthz/",
                "openapi_staff": f"{base}/api/schema/",
                "developer_public_api_doc": f"{base}/developers/api-docs/",
            },
            "webhooks": {
                "finance_payments": "POST /finance/payments/webhook/<provider>/",
                "idempotency": "Optional header Idempotency-Key; X-Webhook-Idempotency-Key on outbound",
            },
            "lti": {
                "jwks": f"{base}{reverse('lti_jwks')}",
                "configure_lti_tool_jwks_uri": "Set lti_tool_jwks_uri + lti_tool_issuer on LTI ServiceIntegration for signed id_token verify.",
            },
        }
    )
