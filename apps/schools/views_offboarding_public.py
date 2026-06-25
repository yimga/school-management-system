"""Public offboarding utilities (certificate verification)."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.lifecycle.purge_certificate import verify_deletion_certificate


@require_http_methods(["POST"])
def api_verify_deletion_certificate(request):
    """Verify an HMAC-signed purge deletion certificate (public, no tenant data)."""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    certificate = body.get("certificate")
    signature = str(body.get("certificate_signature") or body.get("signature") or "").strip()
    if not isinstance(certificate, dict) or not signature:
        return JsonResponse(
            {"ok": False, "error": "certificate_and_signature_required"},
            status=400,
        )

    verified = verify_deletion_certificate(certificate, signature)
    return JsonResponse(
        {
            "ok": True,
            "verified": verified,
            "school_slug": certificate.get("school_slug"),
            "purge_operation_id": certificate.get("purge_operation_id"),
        }
    )
