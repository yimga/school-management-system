"""Persist micro-friction workflow results to tenant DB."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.schoolops.models_micro_friction import (
    LostBelongingsCustodyEventRecord,
    LostBelongingsTagRecord,
    SubstituteHandoverPacketRecord,
)

if TYPE_CHECKING:
    from apps.schoolops.lost_belongings_qr import AssetTag, CustodyEvent
    from apps.schoolops.substitute_handover import HandoverPacket


def _hash12(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12]


def persist_handover_packet(
    *,
    school_id: int,
    user_id: int | None,
    packet: HandoverPacket,
    reason_code: str = "unspecified",
    source: str = SubstituteHandoverPacketRecord.Source.ONLINE,
    client_offline_id: str = "",
) -> SubstituteHandoverPacketRecord:
    key = (client_offline_id or "").strip()[:128]
    if key:
        existing = SubstituteHandoverPacketRecord.objects.filter(
            school_id=school_id,
            client_offline_id=key,
        ).first()
        if existing:
            return existing
    with transaction.atomic():
        return SubstituteHandoverPacketRecord.objects.create(
            school_id=school_id,
            packet_id=packet.packet_id,
            teacher_id_hash=packet.teacher_id_hash,
            substitute_id_hash=packet.substitute_id_hash,
            valid_from=packet.valid_from,
            valid_until=packet.valid_until,
            lesson_outline=list(packet.lesson_outline or []),
            seating_chart_ref=packet.seating_chart_ref or "",
            medical_iep_gated=packet.medical_iep_gated,
            reason_code=(reason_code or "unspecified")[:64],
            audit_event_id=packet.audit_event_id or "",
            source=source,
            created_by_id=user_id,
            client_offline_id=key,
        )


def persist_lost_belongings_tag(
    *,
    school_id: int,
    user_id: int | None,
    tag: AssetTag,
    asset_id: str,
    source: str = "online",
    client_offline_id: str = "",
) -> LostBelongingsTagRecord:
    key = (client_offline_id or "").strip()[:128]
    if key:
        existing = LostBelongingsTagRecord.objects.filter(
            school_id=school_id,
            client_offline_id=key,
        ).first()
        if existing:
            return existing
    with transaction.atomic():
        return LostBelongingsTagRecord.objects.create(
            school_id=school_id,
            asset_id=asset_id[:128],
            short_code=tag.short_code,
            label_hint=tag.label_hint,
            tenant_id_hash=tag.tenant_id_hash,
            created_by_id=user_id,
            client_offline_id=key,
        )


def lookup_tag_by_short_code(*, school_id: int, short_code: str) -> LostBelongingsTagRecord | None:
    code = (short_code or "").strip()
    if not code:
        return None
    return (
        LostBelongingsTagRecord.objects.filter(
            school_id=school_id,
            short_code=code,
            status=LostBelongingsTagRecord.Status.ACTIVE,
        )
        .first()
    )


def lookup_tag_global_short_code(short_code: str) -> LostBelongingsTagRecord | None:
    """Resolve tag for anonymous finder (short_code is unique per school)."""
    code = (short_code or "").strip()
    if not code:
        return None
    # tenant-isolation-allow: anonymous-public-finder-lookup-by-qr-short-code-no-tenant-context-available
    return LostBelongingsTagRecord.objects.filter(
        short_code=code,
        status=LostBelongingsTagRecord.Status.ACTIVE,
    ).first()


def tag_record_to_asset_tag(record: LostBelongingsTagRecord) -> AssetTag:
    from apps.schoolops.lost_belongings_qr import AssetTag

    return AssetTag(
        asset_id=record.asset_id,
        tenant_id_hash=record.tenant_id_hash,
        short_code=record.short_code,
        label_hint=record.label_hint,
    )


def persist_custody_event(
    *,
    school_id: int,
    tag_record: LostBelongingsTagRecord,
    event: CustodyEvent,
    staff_id: str = "",
    client_offline_id: str = "",
) -> LostBelongingsCustodyEventRecord:
    key = (client_offline_id or "").strip()[:128]
    if key:
        existing = LostBelongingsCustodyEventRecord.objects.filter(
            school_id=school_id,
            client_offline_id=key,
        ).first()
        if existing:
            return existing
    staff_hash = _hash12(staff_id) if staff_id else ""
    with transaction.atomic():
        row = LostBelongingsCustodyEventRecord.objects.create(
            school_id=school_id,
            tag=tag_record,
            event_id=event.event_id,
            actor_kind=event.actor_kind,
            notes_redacted=event.notes_redacted,
            parent_notified=event.parent_notified,
            staff_id_hash=staff_hash,
            occurred_at=event.occurred_at,
            client_offline_id=key,
        )
        if event.actor_kind == LostBelongingsCustodyEventRecord.ActorKind.STAFF:
            tag_record.status = LostBelongingsTagRecord.Status.RECOVERED
            tag_record.recovered_at = timezone.now()
            tag_record.save(update_fields=["status", "recovered_at"])
        return row


__all__ = [
    "lookup_tag_by_short_code",
    "lookup_tag_global_short_code",
    "persist_custody_event",
    "persist_handover_packet",
    "persist_lost_belongings_tag",
    "tag_record_to_asset_tag",
]
