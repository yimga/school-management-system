"""Consent helpers — write + query the cross-channel consent log.

Thin functional surface over :class:`apps.communication.models_consent.ConsentEvent`.
Every function is best-effort and NEVER raises into a send/receive hot path: a
consent-log outage must not block a STOP from being honoured (we fail-CLOSED on
the suppression read — an error means "treat as suppressed" only for explicit
prior withdrawals we can see; an unreadable log returns False so we don't block
legitimate mail on a transient blip — see :func:`is_channel_suppressed`).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_ID_HASH_LEN = 12


def hash_identifier(value: str) -> str:
    """sha256(value.lower())[:12] — stable per email/phone, never stored raw."""
    norm = (value or "").strip().lower()
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:_ID_HASH_LEN]


def record_consent_event(
    *,
    channel: str,
    identifier: str,
    action: str,
    reason: str = "",
    source: str = "",
    school: Any = None,
) -> bool:
    """Append one consent event. Returns True on success, never raises."""
    id_hash = hash_identifier(identifier)
    if not id_hash:
        return False
    try:
        from apps.communication.models_consent import ConsentEvent

        ConsentEvent.objects.create(
            channel=(channel or "")[:12],
            identifier_hash=id_hash,
            action=(action or "")[:16],
            reason=(reason or "")[:64],
            source=(source or "")[:48],
            school=school if (school is not None and getattr(school, "pk", None)) else None,
        )
        logger.info(
            "communication.consent.recorded channel=%s action=%s id_hash=%s source=%s",
            channel, action, id_hash, source,
        )
        return True
    except Exception as exc:  # broad-by-design — consent log never breaks a flow
        logger.warning(
            "communication.consent.record_failed err_type=%s", type(exc).__name__,
        )
        return False


def is_channel_suppressed(channel: str, identifier: str) -> bool:
    """True when the latest consent event for this (channel, identifier) is a
    withdrawal (opt-out). Returns False on empty input or any read error
    (fail-open: a transient DB blip must not block legitimate messages — an
    explicit STOP is durable in the log and re-evaluated on the next send)."""
    id_hash = hash_identifier(identifier)
    if not id_hash:
        return False
    try:
        from apps.communication.models_consent import ConsentAction, ConsentEvent

        latest = (
            ConsentEvent.objects.filter(  # tenant-isolation-allow: consent keyed by hashed identifier, not tenant
                channel=(channel or "")[:12], identifier_hash=id_hash,
            )
            .exclude(action=ConsentAction.HELP_REQUESTED)
            .order_by("-created_at")
            .only("action")
            .first()
        )
        return bool(latest and latest.action == ConsentAction.WITHDRAWN)
    except Exception as exc:  # broad-by-design — fail-open on read error
        logger.warning(
            "communication.consent.suppression_check_failed err_type=%s",
            type(exc).__name__,
        )
        return False


__all__ = ["hash_identifier", "record_consent_event", "is_channel_suppressed"]
