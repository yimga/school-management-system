"""
Fleet governed change records (WHATS_LEFT §2.1 thin slice).

Persists draft → approval → schedule → apply lifecycle for cross-tenant operator work.
Apply execution still uses existing surfaces (staged activation, package rollout, etc.);
this model is the auditable spine and state machine hook.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

    from apps.platform_runtime.models import FleetGovernedChange


# Valid transitions: from_status -> allowed to_status values (matches FleetGovernedChange.Status)
_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PENDING_APPROVAL", "CANCELLED"}),
    "PENDING_APPROVAL": frozenset({"SCHEDULED", "CANCELLED", "DRAFT"}),
    "SCHEDULED": frozenset({"APPLYING", "CANCELLED"}),
    "APPLYING": frozenset({"SUCCEEDED", "FAILED"}),
}


def transition_fleet_governed_change(
    change: "FleetGovernedChange",
    to_status: str,
    *,
    actor: "AbstractUser | None" = None,
    error_message: str = "",
) -> "FleetGovernedChange":
    """Apply a legal status transition; raises ValueError if illegal."""
    from apps.platform_runtime.models import FleetGovernedChange

    St = FleetGovernedChange.Status
    to_status = (to_status or "").strip().upper()
    current = (change.status or "").strip().upper()
    if current in frozenset({St.SUCCEEDED, St.FAILED, St.CANCELLED}):
        raise ValueError(f"Terminal status {current} cannot transition")
    allowed = _TRANSITIONS.get(current)
    if allowed is None:
        raise ValueError(f"No transitions defined from {current}")
    if to_status not in allowed:
        raise ValueError(f"Cannot transition {current} -> {to_status}")

    with transaction.atomic():
        change.status = to_status
        if to_status == St.SCHEDULED and actor is not None:
            change.approved_by = actor
        if to_status in (St.SUCCEEDED, St.FAILED):
            change.applied_at = timezone.now()
        if to_status == St.FAILED and error_message:
            change.error_message = (error_message or "")[:4000]
        change.save()

    from apps.platform_runtime.events import emit_platform_event

    payload: dict = {
        "change_id": change.pk,
        "from_status": current,
        "to_status": to_status,
        "change_type": change.change_type,
        "actor_id": getattr(actor, "pk", None) if actor is not None else None,
    }
    if to_status == St.FAILED:
        payload["error_message"] = (error_message or "")[:500]
    emit_platform_event("fleet_governed_change_transitioned", payload)
    return change
