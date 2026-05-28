"""Lightweight parent finance health probe (batch 1518 — no views_parent_finance edits)."""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def parent_finance_health(request):
    """Anonymous JSON probe: finance models importable and route stack healthy."""
    try:
        from apps.finance.models import Invoice, ParentWallet  # noqa: F401
        from django.urls import reverse

        reverse("portal:parent_finance")
        return JsonResponse(
            {
                "status": "healthy",
                "detail": "Parent finance route and finance models reachable.",
            }
        )
    except Exception as exc:
        return JsonResponse(
            {
                "status": "degraded",
                "detail": "Parent finance health probe failed.",
                "error_kind": type(exc).__name__,
            },
            status=503,
        )
