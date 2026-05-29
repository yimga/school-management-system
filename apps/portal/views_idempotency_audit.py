"""v4.00.57 — OneRoster Idempotency-Key audit operator UI.

Surfaces the in-process ring buffer maintained by
``apps.api.oneroster_results._log_idem_event`` so operators can see the
last N Idempotency-Key events (entity / method / path / status /
replayed?) per Result Service write endpoint.

This is an operational debugging surface. The buffer is in-process; it
is NOT a forensic record. The underlying writes are still audited by
the model layer.
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
def idempotency_audit_index(request: HttpRequest):
    """v4.00.57 — Operator UI listing recent Idempotency-Key events."""
    from apps.api.oneroster_results import get_idem_audit_snapshot, get_idem_audit_totals

    try:
        limit = int(request.GET.get("limit") or 200)
    except (ValueError, TypeError):
        limit = 200
    limit = max(1, min(limit, 500))

    entity_filter = (request.GET.get("entity") or "").strip()
    replayed_filter = (request.GET.get("replayed") or "").strip().lower()
    idem_filter = (request.GET.get("idem") or "").strip()

    snap = get_idem_audit_snapshot(limit=limit)
    if entity_filter:
        snap = [e for e in snap if e.get("entity", "") == entity_filter]
    if replayed_filter in ("1", "true", "yes", "only"):
        snap = [e for e in snap if e.get("replayed")]
    elif replayed_filter in ("0", "false", "no", "exclude"):
        snap = [e for e in snap if not e.get("replayed")]
    if idem_filter:
        snap = [e for e in snap if e.get("idempotency_key", "") == idem_filter]

    totals = get_idem_audit_totals()

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "events": snap,
            "totals": totals,
            "filter": {
                "entity": entity_filter,
                "replayed": replayed_filter,
                "idem": idem_filter,
                "limit": limit,
            },
        })

    return render(request, "super/integrations/idempotency_audit.html", {
        "events": snap,
        "totals": totals,
        "filter_entity": entity_filter,
        "filter_replayed": replayed_filter,
        "filter_idem": idem_filter,
        "filter_limit": limit,
    })
