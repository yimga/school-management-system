"""First-class, auditable, reversible onboarding-waiver primitive.

A school can WAIVE two distinct onboarding decisions, modelled by ONE reusable
mechanism (so the two callers stay in lock-step and every reversal is recorded
the same way):

  * ``migration`` — "we have no legacy data to import from another system".
    Waiving clears every migration-SPECIFIC pending signal (the drafted
    Migration Cloud bundle, the "Data migrated" readiness phase, the signup
    migration step, migration reminders) WITHOUT pretending a migration ran.
    This is the clean opt-out for an optional, composable service.

  * ``roster`` — "launch now with no students yet; we'll add them after".
    Waiving clears the ``data_path`` go-live blocker in Setup Studio so a
    genuinely-empty school can activate and populate in-product later — the
    explicit, audited alternative to fabricating sample records to flip the
    ``has_students`` gate.

The two are deliberately SEPARATE. A school that merely lacks *legacy* data
still enters its *current* roster natively, so ``migration`` waived does NOT
imply ``roster`` waived. That separation is exactly what stops "no data to
migrate" from silently producing an empty tenant.

State lives in ``School.settings["onboarding_waivers"][<kind>]`` (``settings``
is a JSONField, so this needs no migration) and mirrors the established
``owner_onboarding.mfa_waived`` waiver pattern in
``apps/accounts/views_owner_onboarding.py``. Every waive / un-waive stamps
actor + timestamp + reason and appends to a bounded ``history`` list, so the
full decision trail — including every reversal — survives for audit. All
writes are best-effort and never raise into the caller: onboarding must never
500 on a waiver write.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

WAIVER_MIGRATION = "migration"
WAIVER_ROSTER = "roster"
WAIVER_KINDS = (WAIVER_MIGRATION, WAIVER_ROSTER)

STATE_ACTIVE = "active"
STATE_WAIVED = "waived"

# Reason codes the UI offers (free-form ``note`` carries anything else). These
# are informational — the primitive accepts any short reason string.
REASON_NO_LEGACY_DATA = "no_legacy_data"
REASON_STARTING_FRESH = "starting_fresh"
REASON_IMPORT_LATER = "import_later"
REASON_NO_STUDENTS_YET = "no_students_yet"

_SETTINGS_KEY = "onboarding_waivers"
_MAX_HISTORY = 40  # bound the trail; oldest entries drop first
_REASON_CAP = 200
_NOTE_CAP = 500


def _now_iso() -> str:
    from django.utils import timezone

    return timezone.now().isoformat()


def _actor_id(actor) -> Optional[int]:
    try:
        pk = getattr(actor, "pk", None)
        return int(pk) if pk is not None else None
    except (TypeError, ValueError):
        return None


def _all_waivers(school) -> dict[str, Any]:
    blob = getattr(school, "settings", None) or {}
    waivers = blob.get(_SETTINGS_KEY)
    return dict(waivers) if isinstance(waivers, dict) else {}


def get_waiver(school, kind: str) -> dict[str, Any]:
    """Return the waiver record for ``kind`` (empty dict when never set)."""
    if not school or kind not in WAIVER_KINDS:
        return {}
    rec = _all_waivers(school).get(kind)
    return dict(rec) if isinstance(rec, dict) else {}


def is_waived(school, kind: str) -> bool:
    return get_waiver(school, kind).get("state") == STATE_WAIVED


def migration_waived(school) -> bool:
    """True when this school has declared it has no data to migrate."""
    return is_waived(school, WAIVER_MIGRATION)


def roster_waived(school) -> bool:
    """True when this school has explicitly chosen to launch with no roster yet."""
    return is_waived(school, WAIVER_ROSTER)


def _persist(school, waivers: dict[str, Any]) -> None:
    blob = dict(getattr(school, "settings", None) or {})
    blob[_SETTINGS_KEY] = waivers
    school.settings = blob
    try:
        school.save(update_fields=["settings"])
    except Exception:  # noqa: BLE001 - waiver persistence is best-effort
        logger.warning(
            "onboarding_waiver_save_failed school=%s",
            getattr(school, "pk", None),
            exc_info=True,
        )


def _record_transition(
    school, kind, *, to_state, actor, reason, note
) -> dict[str, Any]:
    waivers = _all_waivers(school)
    prev = waivers.get(kind) if isinstance(waivers.get(kind), dict) else {}
    history = list(prev.get("history") or [])
    entry = {
        "state": to_state,
        "at": _now_iso(),
        "by": _actor_id(actor),
        "reason": (reason or "")[:_REASON_CAP],
        "note": (note or "")[:_NOTE_CAP],
    }
    history.append(entry)
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    record: dict[str, Any] = {
        "state": to_state,
        "reason": entry["reason"],
        "note": entry["note"],
        "history": history,
    }
    if to_state == STATE_WAIVED:
        record["waived_by"] = entry["by"]
        record["waived_at"] = entry["at"]
    else:
        # Carry forward who originally waived (the trail must survive a restore)
        # and stamp who restored it.
        record["waived_by"] = prev.get("waived_by")
        record["waived_at"] = prev.get("waived_at")
        record["restored_by"] = entry["by"]
        record["restored_at"] = entry["at"]
    waivers[kind] = record
    _persist(school, waivers)
    return record


def waive(school, kind: str, *, actor=None, reason: str = "", note: str = "") -> dict[str, Any]:
    """Mark ``kind`` waived for ``school``. Idempotent; records who/when/why."""
    if not school or kind not in WAIVER_KINDS:
        raise ValueError(f"unknown waiver kind: {kind!r}")
    record = _record_transition(
        school, kind, to_state=STATE_WAIVED, actor=actor, reason=reason, note=note
    )
    logger.info(
        "onboarding.waiver.waived kind=%s school=%s actor=%s reason=%s",
        kind,
        getattr(school, "pk", None),
        _actor_id(actor),
        record.get("reason") or "",
    )
    _emit_waiver_audit_event(school, kind, STATE_WAIVED, actor, record.get("reason"))
    return record


def unwaive(school, kind: str, *, actor=None, reason: str = "") -> dict[str, Any]:
    """Restore ``kind`` to active for ``school``. Keeps the prior waiver history."""
    if not school or kind not in WAIVER_KINDS:
        raise ValueError(f"unknown waiver kind: {kind!r}")
    record = _record_transition(
        school, kind, to_state=STATE_ACTIVE, actor=actor, reason=reason, note=""
    )
    logger.info(
        "onboarding.waiver.unwaived kind=%s school=%s actor=%s",
        kind,
        getattr(school, "pk", None),
        _actor_id(actor),
    )
    _emit_waiver_audit_event(school, kind, STATE_ACTIVE, actor, "")
    return record


def waive_migration_if_flagged(
    school, flagged, *, actor=None, reason: str = REASON_NO_LEGACY_DATA
):
    """Record a durable migration waiver when ``flagged`` is truthy.

    Convenience for the public-signup path: a user who explicitly chose
    "we have no data to migrate" (a WAIVE, distinct from "set up later" which is
    a defer) carries a session flag that is applied once the school exists. A
    no-op when not flagged; best-effort, never raises into the caller.
    """
    try:
        if not flagged or school is None:
            return None
        return waive(school, WAIVER_MIGRATION, actor=actor, reason=reason)
    except Exception:  # noqa: BLE001 - signup waiver must never block signup
        logger.warning("waive_migration_if_flagged failed", exc_info=True)
        return None


def _emit_waiver_audit_event(school, kind, state, actor, reason):
    """Best-effort tamper-evident audit-chain entry for a waiver transition.

    The durable trail lives in the settings ``history`` list; this ALSO appends a
    hash-chained ``MigrationCloudAuditEvent`` so the decision is forgery-evident
    alongside the rest of the tenant's migration audit log. Never raises.
    """
    try:
        slug = getattr(school, "slug", None)
        if not slug:
            return
        from apps.migration_cloud.models_audit import (
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )

        event_type = (
            MigrationCloudAuditEventType.ONBOARDING_WAIVER_APPLIED.value
            if state == STATE_WAIVED
            else MigrationCloudAuditEventType.ONBOARDING_WAIVER_REVERSED.value
        )
        MigrationCloudAuditEvent.objects.record(
            tenant_slug=slug,
            event_type=event_type,
            actor=actor,
            subject=None,
            payload_summary={"kind": kind, "state": state, "reason": reason or ""},
        )
    except Exception:  # noqa: BLE001 - audit is best-effort; never break the waiver
        logger.debug("onboarding waiver audit emit skipped", exc_info=True)
