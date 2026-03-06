from __future__ import annotations

from django.utils import timezone

from apps.observability.models import PlatformIncident


_OPEN_STATUSES = [
    PlatformIncident.Status.OPEN,
    PlatformIncident.Status.ACKNOWLEDGED,
    PlatformIncident.Status.MITIGATED,
]


def _incident_matches_key(incident: PlatformIncident, incident_key: str) -> bool:
    details = incident.details or {}
    return str(details.get("incident_key") or "").strip() == str(incident_key).strip()


def upsert_platform_incident(
    *,
    incident_key: str,
    title: str,
    incident_type: str,
    severity: str,
    summary: str,
    source_system: str,
    affected_school=None,
    affected_schema_name: str = "",
    details: dict | None = None,
    created_by=None,
):
    details = dict(details or {})
    details["incident_key"] = incident_key
    candidates = list(
        PlatformIncident.objects.filter(
            incident_type=incident_type,
            source_system=source_system,
            title=title,
            status__in=_OPEN_STATUSES,
            affected_school=affected_school,
        ).order_by("-detected_at", "-created_at")[:20]
    )
    for incident in candidates:
        if not _incident_matches_key(incident, incident_key):
            continue
        update_fields = []
        if incident.summary != summary:
            incident.summary = summary
            update_fields.append("summary")
        if incident.severity != severity:
            incident.severity = severity
            update_fields.append("severity")
        if incident.details != details:
            incident.details = details
            update_fields.append("details")
        if incident.affected_schema_name != (affected_schema_name or ""):
            incident.affected_schema_name = affected_schema_name or ""
            update_fields.append("affected_schema_name")
        if update_fields:
            incident.save(update_fields=update_fields + ["updated_at"])
        return incident, False

    incident = PlatformIncident.objects.create(
        title=title,
        incident_type=incident_type,
        severity=severity,
        status=PlatformIncident.Status.OPEN,
        summary=summary,
        details=details,
        source_system=source_system,
        affected_school=affected_school,
        affected_schema_name=affected_schema_name or "",
        detected_at=timezone.now(),
        created_by=created_by,
    )
    return incident, True


def resolve_platform_incident(
    *,
    incident_key: str,
    source_system: str,
    incident_type: str | None = None,
    affected_school=None,
    resolved_by=None,
):
    queryset = PlatformIncident.objects.filter(
        source_system=source_system,
        status__in=_OPEN_STATUSES,
        affected_school=affected_school,
    ).order_by("-detected_at", "-created_at")
    if incident_type:
        queryset = queryset.filter(incident_type=incident_type)

    resolved = 0
    now = timezone.now()
    for incident in queryset[:50]:
        if not _incident_matches_key(incident, incident_key):
            continue
        incident.status = PlatformIncident.Status.RESOLVED
        incident.resolved_at = now
        if resolved_by is not None:
            incident.resolved_by = resolved_by
        incident.save(update_fields=["status", "resolved_at", "resolved_by", "updated_at"])
        resolved += 1
    return resolved
