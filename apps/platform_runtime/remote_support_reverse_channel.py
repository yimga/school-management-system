"""Remote Support P4 — the offline reverse channel (service layer).

Closes the gap the maps surfaced: the platform's offline queue only flows
tenant -> cloud, so a cloud operator cannot reach an offline/edge school. This
adds the missing cloud -> tenant direction:

- ``queue_operator_intent`` — operator queues an action/message for a school.
- ``fetch_pending_intents`` — tenant browser / edge hub polls on (re)connect;
  live intents are returned and marked delivered (FIFO).
- ``acknowledge_intent`` — tenant applied/acked an intent.
- ``record_heartbeat`` — tenant/hub phones home so operators see online/offline.
- ``config_version_for`` — cheap token the tenant compares to decide whether to
  re-pull configuration.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.compliance.models_audit import AuditLog
from apps.platform_runtime.models_remote_support import (
    OperatorIntent,
    TenantConnectivityHeartbeat,
)

logger = logging.getLogger(__name__)


def _intent_json(intent) -> dict:
    return {
        "id": str(intent.id),
        "kind": intent.kind,
        "status": intent.status,
        "payload": intent.payload or {},
        "reason": intent.reason,
        "created_at": (
            intent.created_at.isoformat() if intent.created_at else None
        ),
    }


def _audit_intent(intent, *, actor, action, reason) -> None:
    try:
        AuditLog.objects.create(
            user=actor if getattr(actor, "pk", None) else None,
            action=action,
            model_name="OperatorIntent",
            object_id=str(intent.id or ""),
            object_repr=str(intent)[:500],
            app_label="platform_runtime",
            sensitivity=AuditLog.Sensitivity.HIGH,
            new_values={
                "school_id": str(intent.school_id),
                "kind": intent.kind,
                "status": intent.status,
            },
            reason=str(reason)[:255],
        )
    except Exception:  # noqa: BLE001 — audit best-effort, never breaks delivery
        logger.warning("OperatorIntent audit failed", exc_info=True)


def queue_operator_intent(
    *, school, created_by, kind, payload=None, reason="", session=None, expires_at=None
) -> OperatorIntent:
    """Operator queues an intent for a (possibly offline) tenant."""
    intent = OperatorIntent.objects.create(
        school=school,
        session=session,
        created_by=created_by,
        kind=kind,
        payload=payload or {},
        reason=(reason or "")[:255],
        expires_at=expires_at,
        status=OperatorIntent.Status.PENDING,
    )
    _audit_intent(
        intent,
        actor=created_by,
        action=AuditLog.Action.CREATE,
        reason="Operator intent queued (cloud->tenant)",
    )
    return intent


def fetch_pending_intents(*, school, mark_delivered=True, now=None) -> list[dict]:
    """Tenant/hub polls: return live intents (FIFO), marking them delivered."""
    now = now or timezone.now()
    intents = list(
        OperatorIntent.objects.filter(
            school_id=school.id,
            status__in=OperatorIntent.LIVE_STATUSES,
        ).order_by("created_at")
    )
    out: list[dict] = []
    for intent in intents:
        if not intent.is_live(now=now):
            continue
        if mark_delivered and intent.status == OperatorIntent.Status.PENDING:
            intent.mark_delivered(now=now)
            intent.save(update_fields=["status", "delivered_at", "updated_at"])
        out.append(_intent_json(intent))
    return out


def acknowledge_intent(*, intent, actor=None, note="") -> OperatorIntent:
    """Tenant/hub acknowledges an intent (applied it).

    Idempotent no-op once terminal: only a live (PENDING/DELIVERED) intent may
    transition to ACKNOWLEDGED. A replayed ack on an already-terminal intent
    (acknowledged/expired/cancelled) must never overwrite its terminal status or
    its note — that would corrupt the operator's view of what was actually
    applied.
    """
    if intent.status not in OperatorIntent.LIVE_STATUSES:
        return intent
    intent.mark_acknowledged(note=note)
    intent.save(update_fields=["status", "acknowledged_at", "ack_note", "updated_at"])
    _audit_intent(
        intent,
        actor=actor,
        action=AuditLog.Action.UPDATE,
        reason="Operator intent acknowledged by tenant",
    )
    return intent


def record_heartbeat(
    *, school, profile="", app_version="", pending_sync=0, meta=None, now=None
) -> TenantConnectivityHeartbeat:
    """Tenant/hub phone-home: upsert the connectivity heartbeat for a school."""
    now = now or timezone.now()
    heartbeat, _created = TenantConnectivityHeartbeat.objects.update_or_create(
        school=school,
        defaults={
            "last_seen_at": now,
            "profile": (profile or "")[:16],
            "app_version": (app_version or "")[:64],
            "pending_sync": max(0, int(pending_sync or 0)),
            "meta": meta or {},
        },
    )
    return heartbeat


def config_version_for(school) -> str:
    """A cheap token the tenant/hub compares to decide whether to re-pull config.

    Combines the School row's ``updated_at`` with the global config singletons
    (``RuntimeDefaults`` id=1 and ``SiteSettings``) whose changes drive offline config
    but do NOT touch ``School.updated_at`` — so a platform config change (feature
    defaults, SMS provider, maintenance, etc.) now also moves the token and edge hubs
    re-pull instead of running stale config indefinitely. All reads are single-row and
    cheap; any unavailable source degrades to an empty part (never raises).
    """
    import hashlib

    parts: list[str] = []
    updated = getattr(school, "updated_at", None)
    parts.append(updated.isoformat() if updated else "")
    parts.append(f"school:{getattr(school, 'pk', '')}")

    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd_updated = (
            RuntimeDefaults.objects.filter(pk=1)
            .values_list("updated_at", flat=True)
            .first()
        )
        parts.append(rd_updated.isoformat() if rd_updated else "")
    except Exception:  # noqa: BLE001 — config-version must never raise on a poll
        parts.append("")

    try:
        from apps.siteconfig.models import SiteSettings

        ss_updated = (
            SiteSettings.objects.values_list("updated_at", flat=True).first()
        )
        parts.append(ss_updated.isoformat() if ss_updated else "")
    except Exception:  # noqa: BLE001
        parts.append("")

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
