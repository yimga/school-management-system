"""Cross-rail sync-health operator console (9.8 sync-observability wave, 2026-07-02).

Before this surface, an operator could only see ONE of the three sync rails
(delta ``SyncConflict`` on the SLO dashboard). SODP conflicts were tenant-portal
only and the WAL dead-letter/conflict Redis streams had no reader at all.

  * ``GET /portal/super/sync-health/`` — one page for all three rails:
    per-rail backlog/conflict/dead-letter counts + lag, and the first-ever
    dead-letter/conflict stream samples for triage. JSON via ``?format=json``.
"""
from __future__ import annotations

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@staff_member_required
@require_http_methods(["GET"])
def sync_health_index(request: HttpRequest):
    from apps.observability.sync_health import collect_sync_health, peek_wal_review_streams

    snapshot = collect_sync_health()
    deadletter = peek_wal_review_streams("deadletter")
    conflicts = peek_wal_review_streams("conflict")

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "snapshot": snapshot,
            "wal_deadletter_streams": deadletter,
            "wal_conflict_streams": conflicts,
        })
    return render(request, "super/sync/health_index.html", {
        "snapshot": snapshot,
        "deadletter_streams": deadletter,
        "conflict_streams": conflicts,
    })
