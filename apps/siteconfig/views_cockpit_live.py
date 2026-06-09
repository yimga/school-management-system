"""Live JSON snapshots for control-plane cockpit widgets (pulse, heatmap, ticker)."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

_DEBUG_LOG = Path(__file__).resolve().parents[2] / "debug-a48ae2.log"


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "a48ae2",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # endregion


@staff_member_required
@require_GET
def cockpit_live_json(request):
    """GET /super/api/cockpit/live.json — refreshable cockpit metrics for /super/ landing."""

    from apps.siteconfig.cockpit_activity_ticker_realdata import resolve_manager_ticker_cards
    from apps.siteconfig.cockpit_panels_realdata_service import resolve_panel_overrides
    from apps.siteconfig.cockpit_platform_pulse_service import resolve_pulse_cards

    pulse_cards = resolve_pulse_cards()
    panels = resolve_panel_overrides(include_honest_empty=False)
    heatmap = panels.get("tenant_heatmap") or {}
    tiles = heatmap.get("tiles") or []
    ticker_cards = resolve_manager_ticker_cards()
    ticker_cards = [
        c
        for c in ticker_cards
        if isinstance(c, dict) and str(c.get("text") or "").strip()
    ]

    payload = {
        "generated_at": timezone.now().isoformat(),
        "pulse_cards": pulse_cards,
        "tenant_heatmap": {
            "meta_text": heatmap.get("meta_text") or "",
            "tiles": tiles[:60],
            "total": len(tiles),
        },
        "activity_ticker": {"cards": ticker_cards[:16]},
    }
    _agent_debug_log(
        "B",
        "views_cockpit_live.cockpit_live_json",
        "cockpit_live_snapshot",
        {
            "pulse_count": len(pulse_cards),
            "heatmap_tiles": len(tiles),
            "ticker_count": len(ticker_cards),
            "path": getattr(request, "path", ""),
        },
    )
    return JsonResponse(payload)
