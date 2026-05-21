"""Studio OS Co-pilot Rail — JSON endpoints (v3.53.1, 2026-05-21).

Two GET-only endpoints back the persistent AI presence panel:

  * /studio/copilot/rail/context/   — full snapshot + insights + quick_actions
  * /studio/copilot/rail/insights/  — just the insights refresh payload (90s cycle)

Both are login-gated via ``LoginRequiredMixin``. Tenant scoping is inherited
from the request — the service module never accesses a foreign school. PII
isn't logged; only the sha256[:8] of the slug ever lands on a log line.
"""

from __future__ import annotations

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache

from .copilot_rail_service import (
    build_context_snapshot,
    build_rail_payload,
    generate_insights,
)

logger = logging.getLogger(__name__)

# Hard upper bound — the front-end UI only renders 3 insights; we cap to 6 so
# malicious or buggy callers can't ask for a 1000-row prompt.
_INSIGHTS_HARD_MAX = 6
_INSIGHTS_DEFAULT = 3


def _resolve_mode(request: HttpRequest) -> str:
    """Read the active studio mode from query string or referrer hint."""
    mode = (request.GET.get("mode") or "").strip().lower()
    if mode:
        return mode[:24]
    # Fall back to nothing — the service maps unknown surfaces to 'shell'.
    return ""


def _resolve_count(request: HttpRequest, *, default: int) -> int:
    raw = request.GET.get("n") or request.GET.get("count")
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, _INSIGHTS_HARD_MAX))


@method_decorator(never_cache, name="dispatch")
class CopilotRailContextView(LoginRequiredMixin, View):
    """Returns the full rail bootstrap payload for the operator's context."""

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        mode = _resolve_mode(request)
        n = _resolve_count(request, default=_INSIGHTS_DEFAULT)
        try:
            payload = build_rail_payload(request, mode=mode, n=n)
        except Exception:  # noqa: BLE001
            logger.warning(
                "copilot_rail_context: build_rail_payload failed",
                exc_info=True,
            )
            return JsonResponse(
                {
                    "snapshot": None,
                    "insights": [],
                    "quick_actions": [],
                    "error": "unavailable",
                },
                status=200,
            )
        return JsonResponse(payload)


@method_decorator(never_cache, name="dispatch")
class CopilotRailInsightsRefreshView(LoginRequiredMixin, View):
    """Returns just the insights array — called on the 90s refresh cycle."""

    http_method_names = ["get"]
    raise_exception = False

    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        mode = _resolve_mode(request)
        n = _resolve_count(request, default=_INSIGHTS_DEFAULT)
        try:
            snapshot = build_context_snapshot(request, mode=mode)
            insights = generate_insights(snapshot, request=request, n=n)
        except Exception:  # noqa: BLE001
            logger.warning(
                "copilot_rail_insights: refresh failed",
                exc_info=True,
            )
            return JsonResponse({"insights": []}, status=200)
        return JsonResponse(
            {
                "insights": [i.to_dict() for i in insights],
                "posture_mode": snapshot.posture_mode,
            }
        )


__all__ = (
    "CopilotRailContextView",
    "CopilotRailInsightsRefreshView",
)
