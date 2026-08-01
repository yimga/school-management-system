"""Per-tenant fee-collection posture — is live collection live, manual, or undecided?

Why this exists
---------------
Four blueprints declare a go-live capability gate (``external_required_items``
= live/multi-currency payment collection). That gate is correctly NOT an apply
blocker, but the readiness meter scored it off a *static contract tuple*: the
check read "does this blueprint mention live payment", never "does this tenant
actually collect online". No tenant could ever satisfy it, so those blueprints
were pinned below 100 forever — an unmovable meter, the same defect as a
hardcoded one.

This module resolves the gate against real per-tenant state, with three
outcomes:

``live``            A payment rail is genuinely available to this tenant —
                    Stripe Connect connected with charges enabled, or a
                    configured tenant payment integration on a corridor the
                    platform has verified live. The gate is satisfied.
``manual_recorded`` The school has EXPLICITLY recorded that it reconciles fees
                    manually (cash / bank / mobile-money receipts). Live
                    collection is out of scope for this tenant, so the check is
                    not-applicable — it drops out of the readiness denominator
                    rather than being credited as done. Every blueprint here
                    already ships ``manual_fallback: True`` and a manual receipt
                    reconciliation workflow, so this is a supported operating
                    model, not a workaround.
``pending``         Neither. The gate is genuinely unmet and the meter says so.

The manual posture is deliberately an explicit, actor-stamped, audited record.
It is never a default and never inferred from the absence of a rail — inferring
it would turn "this school never set up payments" into "this school is done",
which is exactly the false-credit dishonesty the readiness work exists to stop.
"""
from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

#: School.settings key holding the recorded decision.
POSTURE_SETTINGS_KEY = "fee_collection_posture"

POSTURE_LIVE_RAIL = "live_rail"
POSTURE_MANUAL = "manual_reconciliation"
VALID_POSTURES = (POSTURE_LIVE_RAIL, POSTURE_MANUAL)

STATE_LIVE = "live"
STATE_MANUAL_RECORDED = "manual_recorded"
STATE_PENDING = "pending"

#: Free-text note cap, matched by the form field's ``maxlength``.
MAX_NOTE_CHARS = 500
#: Platform event-log idempotency key column width.
_IDEMPOTENCY_KEY_CHARS = 128


def get_recorded_posture(school) -> dict[str, Any]:
    """The tenant's recorded decision, or ``{}`` when none has been made."""
    if school is None:
        return {}
    settings_blob = getattr(school, "settings", None) or {}
    recorded = settings_blob.get(POSTURE_SETTINGS_KEY)
    if not isinstance(recorded, dict):
        return {}
    if recorded.get("mode") not in VALID_POSTURES:
        return {}
    return dict(recorded)


def record_collection_posture(school, *, mode: str, actor=None, note: str = "") -> dict[str, Any]:
    """Record an explicit fee-collection decision on the school and audit it.

    Raises ``ValueError`` for an unknown mode so a typo can never write a
    posture that silently reads as "undecided" forever.
    """
    if school is None:
        raise ValueError("A school is required to record a collection posture.")
    if mode not in VALID_POSTURES:
        raise ValueError(f"Unknown fee-collection posture: {mode!r}")

    record = {
        "mode": mode,
        "recorded_at": timezone.now().isoformat(),
        "recorded_by": getattr(actor, "pk", None),
        "note": str(note or "")[:MAX_NOTE_CHARS],
    }
    settings_blob = dict(getattr(school, "settings", None) or {})
    settings_blob[POSTURE_SETTINGS_KEY] = record
    school.settings = settings_blob
    school.save(update_fields=["settings"])

    try:
        from apps.platform_runtime.events import emit_platform_event

        emit_platform_event(
            "fee_collection_posture_recorded",
            {
                "school_id": str(school.pk),
                "mode": mode,
                "actor_id": getattr(actor, "pk", None),
                "note": record["note"],
            },
            tenant_id=str(school.pk),
            school_id=school.pk,
            idempotency_key=(
                f"fee_collection_posture:{school.pk}:{record['recorded_at']}"
            )[:_IDEMPOTENCY_KEY_CHARS],
        )
    except Exception:  # noqa: BLE001 — audit must never break the decision itself
        logger.warning("fee_collection_posture_audit_failed", exc_info=True)
    return record


def _live_rail_evidence(school) -> dict[str, Any]:
    """Real signals that this tenant can collect money online today."""
    evidence: dict[str, Any] = {"stripe_connect": False, "verified_corridors": []}
    if school is None:
        return evidence

    try:
        from apps.finance.payment_lane2_status import stripe_connect_summary

        connect = stripe_connect_summary(school=school)
        evidence["stripe_connect"] = bool(
            connect.get("connected") and connect.get("charges_enabled")
        )
    except Exception:  # noqa: BLE001 — a rail probe must never break readiness
        logger.warning("fee_collection_stripe_probe_failed", exc_info=True)

    try:
        from apps.finance.payment_lane2_status import build_lane2_corridor_rows

        for row in build_lane2_corridor_rows(school=school):
            # Both halves are required: the platform has filed live settlement
            # evidence for the corridor AND this tenant has the integration on.
            if row.get("live_proof") and row.get("integration_configured"):
                evidence["verified_corridors"].append(row.get("psp_slug", ""))
    except Exception:  # noqa: BLE001 — same posture as above
        logger.warning("fee_collection_corridor_probe_failed", exc_info=True)
    return evidence


def resolve_live_collection_state(school) -> dict[str, Any]:
    """Resolve the live-collection gate for one tenant.

    Returns ``state`` (``live`` / ``manual_recorded`` / ``pending``), the
    evidence behind it, and a human ``label`` a meter caption can show.
    """
    evidence = _live_rail_evidence(school)
    live = bool(evidence["stripe_connect"] or evidence["verified_corridors"])
    recorded = get_recorded_posture(school)
    mode = recorded.get("mode", "")

    if live:
        state = STATE_LIVE
        label = "Live collection enabled"
    elif mode == POSTURE_MANUAL:
        state = STATE_MANUAL_RECORDED
        label = "Manual reconciliation posture recorded — live collection out of scope"
    else:
        state = STATE_PENDING
        label = "Live payment onboarding"

    return {
        "state": state,
        "label": label,
        "live": live,
        "recorded_mode": mode,
        "recorded_at": recorded.get("recorded_at", ""),
        "evidence": evidence,
        # True when this tenant intends live collection but has not got there.
        "gate_open": state == STATE_PENDING,
        # True when the gate does not apply to this tenant at all.
        "not_applicable": state == STATE_MANUAL_RECORDED,
    }
