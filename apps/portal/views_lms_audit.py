"""v4.00.53 — LMS push-grade audit operator UI (Wedge 2).

Surfaces the v4.00.52 ``LMSPushGradeAudit`` append-only rows to staff:

  * ``GET /portal/super/integrations/lms/audit/`` — index, filterable by
    ``?provider=<slug>``, ``?ok=1|0``, ``?school=<id>``, ``?since=<iso>``.
  * ``GET /portal/super/integrations/lms/audit/?format=json`` — JSON
    rendering of the same filtered slice (operator API).

The view is staff-only and read-only. The model itself is append-only —
no UPDATE/DELETE surfaces are exposed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

_PAGE_CAP = 500


def _parse_since(raw: str):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@staff_member_required
@require_http_methods(["GET"])
def lms_audit_index(request: HttpRequest):
    from apps.integrations_marketplace.models import LMSPushGradeAudit

    qs = LMSPushGradeAudit.objects.all().order_by("-created_at")  # tenant-isolation-allow: operator-audit-platform-scope-staff-required
    provider = (request.GET.get("provider") or "").strip()
    ok_raw = (request.GET.get("ok") or "").strip()
    school = (request.GET.get("school") or "").strip()
    since_raw = (request.GET.get("since") or "").strip()

    if provider:
        qs = qs.filter(provider=provider)
    if ok_raw in ("1", "true", "True"):
        qs = qs.filter(ok=True)
    elif ok_raw in ("0", "false", "False"):
        qs = qs.filter(ok=False)
    if school:
        qs = qs.filter(school_id=school)
    since_dt = _parse_since(since_raw)
    if since_dt is not None:
        qs = qs.filter(created_at__gte=since_dt)

    rows = list(qs[:_PAGE_CAP])
    totals = {
        "count": len(rows),
        "ok": sum(1 for r in rows if r.ok),
        "failed": sum(1 for r in rows if not r.ok),
    }

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "rows": [
                {
                    "id": r.pk,
                    "school_id": str(r.school_id) if r.school_id else "",
                    "provider": r.provider,
                    "course_id": r.course_id,
                    "assignment_id": r.assignment_id,
                    "user_hash": r.user_hash,
                    "score_text": r.score_text,
                    "ok": r.ok,
                    "status_code": r.status_code,
                    "detail": r.detail,
                    "actor_user_id": r.actor_user_id,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ],
            "totals": totals,
            "filter": {
                "provider": provider,
                "ok": ok_raw,
                "school": school,
                "since": since_raw,
            },
        })

    return render(request, "super/integrations/lms_audit_index.html", {
        "rows": rows,
        "totals": totals,
        "filter_provider": provider,
        "filter_ok": ok_raw,
        "filter_school": school,
        "filter_since": since_raw,
    })
