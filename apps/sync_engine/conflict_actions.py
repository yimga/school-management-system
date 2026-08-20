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


def field_comparison(conflict) -> list:
    """Field-by-field ``[{name, server, client, differs, down_only}]`` for one conflict.

    The review screen previously showed two raw dict dumps side by side. On an entity
    with twenty columns that is not a comparison — the reviewer has to diff two blobs by
    eye, and the ONE field that actually differs is the thing they most reliably miss.
    This is the same two versions, aligned per field, with the differing ones marked and
    the cloud-governed ones flagged as not applicable even if the client version is
    chosen.
    """
    from apps.api.sync_services import _DOWN_ONLY_FIELDS_PER_ENTITY

    client = dict(conflict.client_data or {})
    server = dict(conflict.server_data or {})
    down_only = set(_DOWN_ONLY_FIELDS_PER_ENTITY.get(conflict.entity_type or "", ()))
    rows = []
    for name in sorted(set(client) | set(server)):
        c = client.get(name)
        srv = server.get(name)
        rows.append(
            {
                "name": name,
                "server": srv,
                "client": c,
                # Compared as text: the two sides arrive from different paths (one from a
                # JSON wire payload, one from a live model instance), so 3 and "3" are the
                # same value reported differently and must not read as a difference.
                "differs": (name in client) and str(c) != str(srv),
                "down_only": name in down_only,
            }
        )
    return rows


def may_resolve(user, conflict, resolution_token: str):
    """Is ``user`` allowed to settle THIS conflict this way? ``(bool, reason)``.

    THE HOLE THIS CLOSES. Every inbound write is graded by ``policy_registry``: money and
    grades are cloud-authoritative, a box push to one of them is refused and RECORDED as
    a conflict, and a set of per-field columns (pay, payroll authorization, offboarding,
    the grading coefficient) may never travel upward at all. The conflict surface then
    offered a "Keep client" button to anyone who could reach the Sync Center — which
    wrote the box's rejected value straight into the cloud record. The rail refused it and
    the review screen applied it: a complete bypass of the authority model, reached
    through the very UI built to enforce it.

    So the rule is the one the brief states: a protected entity's conflict may only be
    resolved by someone who could have made that write directly.

      * Keeping the SERVER version, or discarding, changes no data and stays open to
        anyone who may see the page — refusing those would just leave conflicts to rot.
      * Keeping the CLIENT version on a PROTECTED entity (money, grades, identity,
        authorization) requires a superuser or the Django model change permission for the
        entity's own model.
      * An ONLINE_REQUIRED domain may never be settled by keeping an offline value at all.
        The whole point of that strategy is that the change is only valid through a live
        transaction; letting it in through review would make the classification cosmetic.
    """
    from apps.api.sync_services import _get_entity_config, _sync_conflict_policy
    from apps.sync_engine.policy_registry import MergeStrategy

    token = (resolution_token or "").strip().lower()
    # Only a resolution that would WRITE the offline value is gated. Keeping the cloud
    # copy, discarding, and a policy decision that lands on keep-server all change no
    # data — refusing those would leave protected conflicts to rot with nobody able to
    # clear them, which is not safety, only paralysis. "policy" is resolved by the caller
    # and re-checked as "client" only if it actually lands there.
    if token != "client":
        return True, ""

    entity_type = conflict.entity_type or ""
    strategy, protected = _sync_conflict_policy(entity_type)
    if strategy == MergeStrategy.ONLINE_REQUIRED:
        return False, (
            f"{entity_type} may only change through a live online transaction; keep the "
            "server version or discard this conflict"
        )
    if not protected:
        return True, ""
    if getattr(user, "is_superuser", False):
        return True, ""

    config = _get_entity_config(include_derived=True)
    entry = config.get(entity_type)
    if entry is None:
        # Unknown entity + protected: fail closed, exactly as get_policy does.
        return False, f"{entity_type} is cloud-authoritative and needs an operator"
    model = entry[0]
    perm = f"{model._meta.app_label}.change_{model._meta.model_name}"
    if getattr(user, "has_perm", None) and user.has_perm(perm):
        return True, ""
    return False, (
        f"{entity_type} is cloud-authoritative; applying the offline version needs the "
        f"{perm} permission"
    )


def _client_updates_for(conflict):
    """The client fields that may legitimately be written, and those that may not.

    Returns ``(model, updates, refused_fields)`` or ``(None, {}, [])``.

    Direction is a property of the FIELD, not only of the entity
    (``_DOWN_ONLY_FIELDS_PER_ENTITY``): salary, payroll/leave authorization, offboarding
    and the grading coefficient ride DOWN only. The inbound rail strips those from a box
    push; without the same strip here, "Keep client" on an otherwise benign teacher
    conflict would write the box's SALARY into the cloud record — the exact write the rail
    exists to refuse, performed by the review screen.
    """
    from apps.api.sync_services import (
        _DOWN_ONLY_FIELDS_PER_ENTITY,
        _get_entity_config,
    )

    config = _get_entity_config(include_derived=True)
    entry = config.get(conflict.entity_type)
    if entry is None:
        return None, {}, []
    model, allowed = entry
    down_only = set(_DOWN_ONLY_FIELDS_PER_ENTITY.get(conflict.entity_type, ()))
    updates, refused = {}, []
    for key, value in (conflict.client_data or {}).items():
        if key not in allowed:
            continue
        if key in down_only:
            refused.append(key)
            continue
        updates[key] = value
    return model, updates, sorted(refused)


def resolve_sync_conflict_row(conflict, resolution, resolved_by):
    """Persist one resolution, applying the client payload when the client wins.

    Returns ``(ok, detail)`` — ``detail`` names what could not be applied, so a partial
    outcome is reported rather than stamped RESOLVED and forgotten.
    """
    from django.core.exceptions import FieldError, ValidationError
    from django.db import DataError, IntegrityError, transaction
    from django.utils import timezone

    from apps.siteconfig.models import SyncConflict

    detail = ""
    conflict.resolved_by = resolved_by
    conflict.resolved_at = timezone.now()
    conflict.status = resolution
    if resolution == SyncConflict.Status.RESOLVED_CLIENT:
        # Resolving an edge-sync conflict is itself an edge-scoped operation, so it must
        # use the FULL two-way registry — otherwise "keep client version" silently writes
        # NOTHING for a derived entity (applicant/student_note/academic_year/term/department)
        # while still stamping the record RESOLVED_CLIENT.
        model, updates, refused = _client_updates_for(conflict)
        if refused:
            detail = "cloud-governed field(s) not applied: " + ", ".join(refused)
        if model is not None and updates:
            from apps.api.sync_services import _unresolvable_fk

            try:
                instance = model.objects.get(pk=conflict.entity_id)
            except model.DoesNotExist:
                instance = None
            if instance is None:
                detail = (detail + "; " if detail else "") + "the record no longer exists"
            else:
                # The same referential preflight the rail runs. On PostgreSQL a bad FK
                # cannot be caught AFTER the write (Django's FKs are DEFERRABLE INITIALLY
                # DEFERRED), so resolving a conflict whose client payload points at a row
                # that has since been deleted would 500 the review screen at COMMIT.
                missing = _unresolvable_fk(model, set(updates), updates, {})
                if missing is not None:
                    detail = (detail + "; " if detail else "") + (
                        f"{missing[0]} points at a {missing[1]} that no longer exists"
                    )
                else:
                    fields = list(updates.keys())
                    if any(
                        getattr(f, "attname", "") == "updated_at"
                        for f in model._meta.get_fields()
                    ):
                        fields.append("updated_at")
                    try:
                        with transaction.atomic():
                            for key, value in updates.items():
                                setattr(instance, key, value)
                            instance.save(update_fields=fields)
                    except (
                        IntegrityError, DataError, ValidationError,
                        ValueError, TypeError, FieldError,
                    ) as exc:
                        detail = (detail + "; " if detail else "") + (
                            f"could not apply: {str(exc)[:120]}"
                        )
    conflict.save(update_fields=["status", "resolved_at", "resolved_by"])
    return True, detail


def apply_resolution(conflict, resolution_token: str, resolved_by, *, note: str = ""):
    """Resolve one PENDING conflict. Returns (ok, reason)."""
    from apps.siteconfig.models import SyncConflict

    if conflict.status != SyncConflict.Status.PENDING:
        return False, "already_resolved"
    token = (resolution_token or "").strip().lower()
    # AUTHORITY FIRST. A conflict on a cloud-authoritative record may only be settled in
    # the client's favour by someone who could have made that write directly — otherwise
    # the review screen is a way around the very policy that created the conflict.
    permitted, refusal = may_resolve(resolved_by, conflict, token)
    if not permitted:
        return False, refusal
    if token == "policy":
        from apps.sync_engine.conflict_resolver import resolve_one

        decision = resolve_one(_policy_payload(conflict))
        status, action = _decision_to_status(conflict, decision)
        if status is None:
            return False, (decision or {}).get("reason") or "manual_review"
        if status == SyncConflict.Status.RESOLVED_CLIENT:
            # The policy landed on the offline value, so it needs the same authority a
            # manual "keep local" would. Checked HERE rather than up front because a
            # policy decision that keeps the cloud copy is harmless and must stay open.
            permitted_client, refusal_client = may_resolve(resolved_by, conflict, "client")
            if not permitted_client:
                return False, refusal_client
        reason = (decision or {}).get("reason") or action
        _ok, detail = resolve_sync_conflict_row(conflict, status, resolved_by)
        stamped = "; ".join(p for p in (note or reason, detail) if p)
        if stamped:
            conflict.resolution_note = stamped[:255]
            conflict.save(update_fields=["resolution_note"])
        return True, action
    status = _status_for_token(token)
    if status is None:
        return False, "invalid_resolution"
    _ok, detail = resolve_sync_conflict_row(conflict, status, resolved_by)
    # WHO and WHY are both persisted. resolved_by/resolved_at come from the row write
    # above; the note carries the operator's reason AND anything the apply could not do,
    # so a partially-applied resolution is never recorded as a clean one.
    stamped = "; ".join(p for p in (note, detail) if p)
    if stamped:
        conflict.resolution_note = stamped[:255]
        conflict.save(update_fields=["resolution_note"])
    return True, token


def bulk_resolve(*, school, ids, resolution: str, resolved_by, entity_type: str = "",
                 note: str = ""):
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
        ok, reason = apply_resolution(conflict, token, resolved_by, note=note)
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
