"""
Substitute handover blueprint — micro-friction workflow runtime.

Generates a redacted, time-boxed handover packet when a teacher is marked
absent. Substitute gets enough to run the classroom (lesson outline, seating,
medical/IEP gates) without long-term identity access. Packet expiry is
enforced; no PII beyond classroom-level need-to-know lands in the packet.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


logger = logging.getLogger(__name__)


class SubstituteHandoverError(RuntimeError):
    pass


@dataclass(frozen=True)
class TeacherAbsenceTrigger:
    tenant_id: str
    teacher_id: str
    absence_start: datetime
    absence_end: datetime
    reason_code: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise SubstituteHandoverError("tenant_id required")
        if not self.teacher_id:
            raise SubstituteHandoverError("teacher_id required")
        if self.absence_end <= self.absence_start:
            raise SubstituteHandoverError("absence_end must follow absence_start")


@dataclass
class HandoverPacket:
    packet_id: str
    tenant_id_hash: str
    teacher_id_hash: str
    substitute_id_hash: str
    valid_from: datetime
    valid_until: datetime
    lesson_outline: list[dict[str, Any]]
    seating_chart_ref: str
    medical_iep_gated: bool
    audit_event_id: str

    def is_expired(self, *, now: datetime | None = None) -> bool:
        ref = now or datetime.now(timezone.utc)
        return ref >= self.valid_until


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def build_packet(
    *,
    trigger: TeacherAbsenceTrigger,
    substitute_id: str,
    lesson_outline: list[dict[str, Any]] | None = None,
    seating_chart_ref: str = "",
    expose_medical_iep: bool = False,
    grace_minutes: int = 30,
) -> HandoverPacket:
    if not substitute_id:
        raise SubstituteHandoverError("substitute_id required")
    valid_from = trigger.absence_start - timedelta(minutes=grace_minutes)
    valid_until = trigger.absence_end + timedelta(minutes=grace_minutes)
    outline = []
    for item in lesson_outline or []:
        outline.append(
            {
                "period": item.get("period", ""),
                "topic": item.get("topic", ""),
                "materials": [str(m) for m in (item.get("materials") or [])],
            }
        )
    packet = HandoverPacket(
        packet_id=str(uuid.uuid4()),
        tenant_id_hash=_hash(trigger.tenant_id),
        teacher_id_hash=_hash(trigger.teacher_id),
        substitute_id_hash=_hash(substitute_id),
        valid_from=valid_from,
        valid_until=valid_until,
        lesson_outline=outline,
        seating_chart_ref=seating_chart_ref or "",
        medical_iep_gated=not expose_medical_iep,
        audit_event_id=str(uuid.uuid4()),
    )
    logger.info(
        "substitute_handover.build packet=%s tenant=%s teacher=%s sub=%s gated=%s",
        packet.packet_id,
        packet.tenant_id_hash,
        packet.teacher_id_hash,
        packet.substitute_id_hash,
        packet.medical_iep_gated,
        extra={"scope": "substitute_handover.build"},
    )
    return packet


def access_check(packet: HandoverPacket, *, now: datetime | None = None) -> bool:
    return not packet.is_expired(now=now)


__all__ = [
    "HandoverPacket",
    "SubstituteHandoverError",
    "TeacherAbsenceTrigger",
    "access_check",
    "build_packet",
]
