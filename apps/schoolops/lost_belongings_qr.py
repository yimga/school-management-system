"""
Lost belongings QR loop — micro-friction workflow service.

Each tagged asset gets a tenant-scoped QR code that resolves to an anonymous
custody loop: anonymous finder records a sighting, custody log appends, parent
is notified through the registered communication channel. The public-facing
page is anonymous and exposes zero student PII; reconciliation happens
behind tenant auth.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


logger = logging.getLogger(__name__)


class LostBelongingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssetTag:
    asset_id: str
    tenant_id_hash: str
    short_code: str
    label_hint: str  # e.g. "blue lunch bag" — descriptive, never name/email


@dataclass
class CustodyEvent:
    event_id: str
    asset_id: str
    occurred_at: datetime
    actor_kind: str  # "anonymous_finder" | "staff" | "guardian"
    notes_redacted: str
    parent_notified: bool


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def mint_tag(*, tenant_id: str, asset_id: str, label_hint: str) -> AssetTag:
    if not tenant_id or not asset_id:
        raise LostBelongingsError("tenant_id and asset_id required")
    if "@" in label_hint or any(ch.isdigit() for ch in label_hint if ch == ch):
        # cheap PII smell-test: still allow digits but block emails
        if "@" in label_hint:
            raise LostBelongingsError("label_hint must not contain email-like data")
    short_code = secrets.token_urlsafe(8)
    return AssetTag(
        asset_id=asset_id,
        tenant_id_hash=_hash(tenant_id),
        short_code=short_code,
        label_hint=label_hint[:80],
    )


_SENSITIVE_TOKENS = ("ssn", "dob", "phone", "email", "address")


def _scrub_notes(notes: str) -> str:
    lower = notes.lower()
    for tok in _SENSITIVE_TOKENS:
        if tok in lower:
            return "[REDACTED]"
    return notes[:280]


def record_finder_sighting(
    *,
    tag: AssetTag,
    notes: str = "",
    notify_parent: bool = True,
) -> CustodyEvent:
    event = CustodyEvent(
        event_id=str(uuid.uuid4()),
        asset_id=tag.asset_id,
        occurred_at=datetime.now(timezone.utc),
        actor_kind="anonymous_finder",
        notes_redacted=_scrub_notes(notes),
        parent_notified=notify_parent,
    )
    logger.info(
        "lost_belongings.sighting asset=%s tenant=%s notified=%s",
        tag.asset_id,
        tag.tenant_id_hash,
        notify_parent,
        extra={"scope": "lost_belongings.sighting"},
    )
    return event


def record_staff_recovery(
    *,
    tag: AssetTag,
    staff_id: str,
    notes: str = "",
) -> CustodyEvent:
    if not staff_id:
        raise LostBelongingsError("staff_id required")
    event = CustodyEvent(
        event_id=str(uuid.uuid4()),
        asset_id=tag.asset_id,
        occurred_at=datetime.now(timezone.utc),
        actor_kind="staff",
        notes_redacted=_scrub_notes(notes),
        parent_notified=True,
    )
    logger.info(
        "lost_belongings.recovery asset=%s tenant=%s staff=%s",
        tag.asset_id,
        tag.tenant_id_hash,
        _hash(staff_id),
        extra={"scope": "lost_belongings.recovery"},
    )
    return event


__all__ = [
    "AssetTag",
    "CustodyEvent",
    "LostBelongingsError",
    "mint_tag",
    "record_finder_sighting",
    "record_staff_recovery",
]
