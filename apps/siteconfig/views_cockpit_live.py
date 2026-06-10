"""Live JSON snapshots for control-plane cockpit widgets (pulse, heatmap, ticker)."""
from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.schools.fleet_status import FLEET_POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

FLEET_HEATMAP_CAP = 500


@staff_member_required
@require_GET
def cockpit_live_json(request):
    """GET /super/api/cockpit/live.json — refreshable cockpit metrics for /super/ landing."""

    from apps.schools.fleet_status import fleet_revision, resolve_fleet_tiles
    from apps.siteconfig.cockpit_activity_ticker_realdata import resolve_manager_ticker_cards
    from apps.siteconfig.cockpit_panels_realdata_service import resolve_panel_overrides
    from apps.siteconfig.cockpit_platform_pulse_service import resolve_pulse_cards

    pulse_cards = resolve_pulse_cards()
    panels = resolve_panel_overrides(include_honest_empty=False)
    heatmap = panels.get("tenant_heatmap") or {}
    tiles = heatmap.get("tiles") or []
    summary = heatmap.get("fleet_summary") or {}

    if not tiles:
        tiles, summary = resolve_fleet_tiles(max_tiles=FLEET_HEATMAP_CAP)

    ticker_cards = resolve_manager_ticker_cards()
    ticker_cards = [
        c
        for c in ticker_cards
        if isinstance(c, dict) and str(c.get("text") or "").strip()
    ]

    capped = tiles[:FLEET_HEATMAP_CAP]
    payload = {
        "generated_at": timezone.now().isoformat(),
        "poll_interval_seconds": FLEET_POLL_INTERVAL_SECONDS,
        "pulse_cards": pulse_cards,
        "tenant_heatmap": {
            "meta_text": heatmap.get("meta_text") or "",
            "tiles": capped,
            "total": int(summary.get("total") or len(tiles)),
            "shown": len(capped),
            "fleet_summary": summary,
            "revision": fleet_revision(capped, summary),
        },
        "activity_ticker": {"cards": ticker_cards[:16]},
    }
    return JsonResponse(payload)
