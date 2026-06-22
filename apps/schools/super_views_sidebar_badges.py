"""Live sidebar-badge endpoint for the operator control plane (intelligent
sidebars Phase 2).

The operator sidebar had NO badges. This gives it its first one: the count of
pending signup verifications — exactly what the ``super:signup_verifications``
console lists (``verified_at__isnull=True``), so the at-a-glance number and the
console never disagree. ``rmc-sidebar-intelligence.js`` polls this and paints the
count on the matching nav item.

Returns ``{"badges": {item_id: count}, "interval": <seconds>}``. Access is
gated at the URL (``require_super_access_with_host``). Fails soft to empty.
"""
from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60
_BADGE_DISPLAY_CAP = 999  # magic-number-allow: badge count display cap


@require_GET
def operator_sidebar_badges(request):
    badges: dict[str, int] = {}
    try:
        from apps.schools.models import SignupVerification

        # tenant-isolation-allow: platform-level pre-tenant signup records, queried on the operator/manager host
        pending = SignupVerification.objects.filter(verified_at__isnull=True).count()
        if pending > 0:
            badges["super_signup_verifications"] = min(pending, _BADGE_DISPLAY_CAP)
    except Exception:  # noqa: BLE001 — a badge poll must never break the operator shell.
        logger.debug("operator_sidebar_badges failed", exc_info=False)
    return JsonResponse({"badges": badges, "interval": _POLL_INTERVAL_SECONDS})
