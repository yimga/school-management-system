"""Discipline incident API — offline-queue friendly (batches 1740–1742)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.academics.models import Incident
from apps.people.models import StudentProfile


def _teacher_may_refer(user) -> bool:
    role = (getattr(user, "role", "") or "").upper()
    if role == "TEACHER":
        return True
    return getattr(user, "has_feature_permission", lambda _: False)("discipline.refer")


def create_incident_from_fields(
    *,
    school_id: int,
    user,
    fields: dict[str, Any],
    offline_marker: str | None = None,
) -> dict[str, Any]:
    """Shared incident creation for live API and offline field_capture replay."""
    from apps.schools.models import School

    if not School.objects.filter(pk=school_id).exists():
        return {"ok": False, "error": "school_not_found"}

    if not _teacher_may_refer(user):
        return {"ok": False, "error": "forbidden"}

    student_id = fields.get("student_id")
    if not student_id:
        return {"ok": False, "error": "student_id_required"}

    student = StudentProfile.objects.filter(pk=student_id, school_id=school_id).first()
    if not student:
        return {"ok": False, "error": "student_not_found"}

    incident_type = str(fields.get("incident_type") or Incident.Type.OTHER)
    if incident_type not in Incident.Type.values:
        incident_type = Incident.Type.OTHER

    severity = str(fields.get("severity") or Incident.Severity.MEDIUM)
    if severity not in Incident.Severity.values:
        severity = Incident.Severity.MEDIUM

    mtss_tier = str(fields.get("mtss_tier") or "1")
    if mtss_tier not in ("1", "2", "3"):
        mtss_tier = "1"

    incident_date = fields.get("date")
    if isinstance(incident_date, str) and incident_date:
        try:
            parsed_date = date.fromisoformat(incident_date[:10])
        except ValueError:
            parsed_date = timezone.localdate()
    else:
        parsed_date = timezone.localdate()

    notify_parent_raw = fields.get("notify_parent", True)
    if isinstance(notify_parent_raw, str):
        notify_parent = notify_parent_raw.lower() in ("1", "true", "yes", "on")
    else:
        notify_parent = bool(notify_parent_raw)

    description = str(fields.get("description") or "")[:4000]
    if offline_marker:
        marker = f"[offline:{offline_marker[:64]}]"
        if marker not in description:
            description = (description + " " + marker).strip()[:4000]

    incident = Incident(
        school_id=school_id,
        student=student,
        incident_type=incident_type,
        severity=severity,
        status=Incident.Status.REFERRED,
        mtss_tier=mtss_tier,
        date=parsed_date,
        description=description,
        notify_parent=notify_parent,
        created_by=user,
    )
    incident.save()

    if notify_parent and incident.notify_parent:
        Incident.objects.filter(pk=incident.pk).update(
            parent_notified_at=timezone.now()
        )

    return {
        "ok": True,
        "incident_id": incident.pk,
        "status": incident.status,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_discipline_incidents(request: HttpRequest) -> JsonResponse:
    school = getattr(request, "school", None)
    if school is None:
        return JsonResponse({"ok": False, "error": "tenant_required"}, status=403)

    if request.method == "GET":
        if not _teacher_may_refer(request.user) and not getattr(
            request.user, "has_feature_permission", lambda _: False
        )("discipline.manage"):
            return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
        qs = (
            Incident.objects.filter(school=school)
            .select_related("student", "teacher")
            .order_by("-date", "-created_at")[:50]
        )
        rows = [
            {
                "id": inc.pk,
                "date": inc.date.isoformat(),
                "incident_type": inc.incident_type,
                "severity": inc.severity,
                "status": inc.status,
                "mtss_tier": inc.mtss_tier,
                "student_id": inc.student_id,
                "notify_parent": inc.notify_parent,
                "parent_notified_at": (
                    inc.parent_notified_at.isoformat() if inc.parent_notified_at else None
                ),
            }
            for inc in qs
        ]
        return JsonResponse({"ok": True, "incidents": rows, "cached_at": timezone.now().isoformat()})

    if not _teacher_may_refer(request.user):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    result = create_incident_from_fields(
        school_id=school.pk,
        user=request.user,
        fields=body,
        offline_marker=str(body.get("client_offline_id") or "") or None,
    )
    if not result.get("ok"):
        status = 403 if result.get("error") == "forbidden" else 400
        if result.get("error") == "student_not_found":
            status = 404
        return JsonResponse(result, status=status)

    return JsonResponse(
        {
            **result,
            "queued_offline": bool(body.get("client_offline_id")),
        },
        status=201,
    )
