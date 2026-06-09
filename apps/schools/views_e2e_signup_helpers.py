"""CI-only helpers for cold-signup Playwright (never enable in production)."""

from __future__ import annotations

import os

from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_GET

from apps.schools.models import SignupVerification


def _e2e_signup_helpers_enabled() -> bool:
    return os.environ.get("RMC_E2E_SIGNUP_HELPERS", "").strip() == "1"


@require_GET
def e2e_signup_verification_token(request):
    """
    Return the latest unverified SignupVerification token for an email.

    Gated by ``RMC_E2E_SIGNUP_HELPERS=1`` (CI / local E2E only).
    """
    if not _e2e_signup_helpers_enabled():
        return HttpResponseForbidden("E2E signup helpers disabled")

    email = (request.GET.get("email") or "").strip()
    slug = (request.GET.get("slug") or "").strip()
    if not email:
        return JsonResponse({"ok": False, "error": "email required"}, status=400)

    qs = SignupVerification.objects.filter(  # tenant-isolation-allow: e2e-signup-helper-ci-gated-cross-tenant-lookup
        email__iexact=email,
        verified_at__isnull=True,
    ).select_related("school")
    if slug:
        qs = qs.filter(school__slug=slug)
    verification = qs.order_by("-created_at").first()
    if verification is None:
        return JsonResponse({"ok": False, "error": "verification not found"}, status=404)

    return JsonResponse(
        {
            "ok": True,
            "token": str(verification.token),
            "slug": verification.school.slug,
            "school_id": str(verification.school_id),
        }
    )
