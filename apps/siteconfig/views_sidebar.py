"""Live sidebar-badge endpoint for the tenant portal (intelligent sidebars Phase 2).

The portal sidebar already computes pending counts (workflow / finance /
signatures) into the item dicts at render time. Rather than re-derive them here
(and risk drift), this endpoint re-runs the SAME builder and returns the badges
it produced, keyed by item id. ``rmc-sidebar-intelligence.js`` polls this and
updates the nav badges in place — so a teacher sees a new "marks pending" count
without reloading. The underlying counts are cached ~60s, so the poll is cheap.

Returns ``{"badges": {item_id: count, ...}, "interval": <seconds>}``. Fails
soft to an empty payload — a badge poll must never error the shell.
"""
from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60


@login_required
@require_GET
def sidebar_badge_counts(request):
    badges: dict[str, int] = {}
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings
        from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

        site = get_effective_site_settings(request=request)
        for item in build_portal_sidebar_items(request, site) or []:
            count = item.get("badge")
            try:
                count = int(count or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0 and item.get("id"):
                badges[str(item["id"])] = count
    except Exception:  # noqa: BLE001 — a badge poll must never break; degrade to empty.
        logger.debug("sidebar_badge_counts failed", exc_info=False)
    return JsonResponse({"badges": badges, "interval": _POLL_INTERVAL_SECONDS})
