"""Apply Sync Center resolutions, including bulk and school policy."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

BULK_MAX = 200  # magic-number-allow: cap one bulk-resolve request


def _status_for_token(token: str):
    from apps.siteconfig.models import SyncConflict

    key = (token or "").strip().lower()
    if key == "server":
        return SyncConflict.Status.RESOLVED_SERVER
    if key == "client":
        return SyncConflict.Status.RESOLVED_CLIENT
    if key == "discard":
        return SyncConflict.Status.DISCARDED
    return None


def _policy_payload(conflict) -> dict[str, Any]:
    payload: dict[str, Any] = {"entity": conflict.entity_type or ""}
    if conflict.client_updated_at is not None:
        payload["remote_clock"] = conflict.client_updated_at.isoformat()
    if conflict.server_updated_at is not None:
        payload["server_clock"] = conflict.server_updated_at.isoformat()
    return payload


def _decision_to_status(conflict, decision: dict[str, Any]):
    from apps.siteconfig.models import SyncConflict

    action = (decision or {}).get("action") or ""
    if action == "keep_server":
        return SyncConflict.Status.RESOLVED_SERVER, action
    if action == "keep_remote":
        return SyncConflict.Status.RESOLVED_CLIENT, action
    if action == "reject_offline":
        return SyncConflict.Status.DISCARDED, action
    # Causal LWW without HLC clocks: honest wall-clock fallback when both
    # timestamps exist. Otherwise leave the row for a human.
    if (
        action == "manual_review"
        and conflict.client_updated_at
        and conflict.server_updated_at
    ):
        if conflict.client_updated_at > conflict.server_updated_at:
            return SyncConflict.Status.RESOLVED_CLIENT, "keep_remote"
        return SyncConflict.Status.RESOLVED_SERVER, "keep_server"
    return None, action


def resolve_sync_conflict_row(conflict, resolution, resolved_by):
    """Persist one resolution, applying the client payload when the client wins."""
    from django.utils import timezone

    from apps.siteconfig.models import SyncConflict

    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = resolution
    if resolution == SyncConflict.Status.RESOLVED_CLIENT:
        from apps.api.sync_services import _get_entity_config

        # Resolving an edge-sync conflict is itself an edge-scoped operation, so it must
        # use the FULL two-way registry — otherwise "keep client version" silently writes
        # NOTHING for a derived entity (applicant/student_note/academic_year/term/department)
        # while still stamping the record RESOLVED_CLIENT.
        config = _get_entity_config(include_derived=True)
        if conflict.entity_type in config:
            model, allowed = config[conflict.entity_type]
            updates = {
                k: v for k, v in (conflict.client_data or {}).items() if k in allowed
            }
            if updates:
                try:
                    instance = model.objects.get(pk=conflict.entity_id)
                    for key, value in updates.items():
                        setattr(instance, key, value)
                    instance.save(update_fields=list(updates.keys()) + ["updated_at"])
                except model.DoesNotExist:
                    pass
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])


def apply_resolution(conflict, resolution_token: str, resolved_by, *, note: str = ""):
    """Resolve one PENDING conflict. Returns (ok, reason)."""
    from apps.siteconfig.models import SyncConflict

    if conflict.status != SyncConflict.Status.PENDING:
        return False, "already_resolved"
    token = (resolution_token or "").strip().lower()
    if token == "policy":
        from apps.sync_engine.conflict_resolver import resolve_one

        decision = resolve_one(_policy_payload(conflict))
        status, action = _decision_to_status(conflict, decision)
        if status is None:
            return False, (decision or {}).get("reason") or "manual_review"
        reason = (decision or {}).get("reason") or action
        resolve_sync_conflict_row(conflict, status, resolved_by)
        if note or reason:
            conflict.resolution_note = (note or reason)[:255]
            conflict.save(update_fields=["resolution_note"])
        return True, action
    status = _status_for_token(token)
    if status is None:
        return False, "invalid_resolution"
    resolve_sync_conflict_row(conflict, status, resolved_by)
    if note:
        conflict.resolution_note = note[:255]
        conflict.save(update_fields=["resolution_note"])
    return True, token


def bulk_resolve(*, school, ids, resolution: str, resolved_by, entity_type: str = ""):
    """Resolve many PENDING conflicts for ``school`` only. Never crosses tenants."""
    from apps.siteconfig.models import SyncConflict

    result = {
        "ok": True,
        "resolved": 0,
        "skipped": 0,
        "errors": [],
        "message": "",
    }
    token = (resolution or "").strip().lower()
    type_filter = (entity_type or "").strip()
    qs = SyncConflict.objects.filter(school=school, status=SyncConflict.Status.PENDING)
    if type_filter:
        qs = qs.filter(entity_type=type_filter)
    clean_ids = []
    for raw in ids or []:
        try:
            clean_ids.append(int(raw))
        except (TypeError, ValueError):
            result["skipped"] += 1
    if clean_ids:
        qs = qs.filter(pk__in=clean_ids)
    elif not type_filter:
        result["ok"] = False
        result["message"] = str(_("Select at least one conflict."))
        return result
    rows = list(qs.order_by("pk")[:BULK_MAX])
    if not rows:
        result["message"] = str(_("No pending conflicts matched."))
        return result
    for conflict in rows:
        ok, reason = apply_resolution(conflict, token, resolved_by)
        if ok:
            result["resolved"] += 1
        else:
            result["skipped"] += 1
            result["errors"].append({"id": conflict.pk, "reason": str(reason)})
    result["ok"] = result["resolved"] > 0
    if result["resolved"]:
        result["message"] = str(
            _("Resolved %(count)s conflict(s).") % {"count": result["resolved"]}
        )
    elif result["errors"]:
        result["message"] = str(_("Could not auto-resolve the selected conflicts."))
    return result
