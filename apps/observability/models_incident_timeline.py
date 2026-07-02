"""Incident timeline of record + postmortem artifact (9.8 incidents wave, 2026-07-02).

Before this module, ``PlatformIncident`` had a state machine but no memory:
status flips overwrote each other with no trail, operator notes had nowhere
to live, and nothing in code captured a postmortem — the lifecycle could
never close the loop from "resolved" to "learned". An ``IncidentUpdate`` row
is the unit of record: status changes are auto-recorded by the transition
API and the idempotent incident services, operators append updates/action
items, and a ``POSTMORTEM`` entry is the artifact that marks the loop closed
(surfaced as a chip on the console and in the JSON payload).
"""
from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


class IncidentUpdate(models.Model):
    """Append-oriented timeline entry for a PlatformIncident."""

    class Kind(models.TextChoices):
        UPDATE = "update", "Update"
        STATUS_CHANGE = "status_change", "Status change"
        POSTMORTEM = "postmortem", "Postmortem"
        ACTION_ITEM = "action_item", "Action item"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        "observability.PlatformIncident",
        on_delete=models.CASCADE,
        related_name="updates",
    )
    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
        default=Kind.UPDATE,
        db_index=True,
    )
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "observability"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["incident", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.incident_id} {self.kind} @ {self.created_at:%Y-%m-%d %H:%M}"


def record_incident_update(incident, *, kind: str, body: str, user=None):
    """Best-effort timeline write — never breaks the calling path.

    Auto-recorders (status-transition API, incident services) route through
    here so a timeline failure can never block incident handling itself.
    """
    try:
        return IncidentUpdate.objects.create(
            incident=incident,
            kind=kind,
            body=(body or "")[:4000],
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "incident_timeline.record_failed incident=%s kind=%s err=%s",
            getattr(incident, "pk", None), kind, exc,
        )
        return None


def incident_has_postmortem(incident) -> bool:
    try:
        return incident.updates.filter(kind=IncidentUpdate.Kind.POSTMORTEM).exists()
    except Exception:  # noqa: BLE001
        return False


__all__ = ["IncidentUpdate", "record_incident_update", "incident_has_postmortem"]
