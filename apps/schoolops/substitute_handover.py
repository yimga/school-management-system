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
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class SubstituteCandidate:
    teacher_id: str
    display_name: str
    phone: str = ""
    department_id: str = ""
    active_cover_count: int = 0
    priority: int = 0
    # Set by ``rank_substitute_candidates`` against the cover's required
    # department. ``False`` marks an out-of-department teacher who may only be
    # contacted as an explicit override (no qualified substitute available).
    qualified: bool = True


@dataclass(frozen=True)
class SubstituteBroadcastResult:
    candidate_id: str
    channel: str
    accepted: bool


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


def rank_substitute_candidates(
    *,
    absent_teacher_id: str,
    candidates: list[SubstituteCandidate],
    unavailable_ids: set[str] | None = None,
    required_department_id: str = "",
) -> list[SubstituteCandidate]:
    unavailable = {str(value) for value in (unavailable_ids or set())}
    required = str(required_department_id or "")
    eligible = [
        candidate
        for candidate in candidates
        if candidate.teacher_id != str(absent_teacher_id)
        and candidate.teacher_id not in unavailable
        and candidate.phone
    ]
    # Qualification is a HARD tier, not a tie-breaker. When the cover names a
    # required department, a substitute whose department does not match is
    # flagged ``qualified=False`` and ranked strictly below EVERY qualified
    # candidate — so a higher-priority out-of-department teacher can never
    # outrank an in-department one (the old code merely used it as the first
    # sort key AND never received it in production, so it was inert). With no
    # required department (e.g. the absent teacher has none on file) every
    # candidate stays qualified and the ranking degrades to priority/load.
    ranked = [
        replace(
            candidate,
            qualified=(not required) or (candidate.department_id == required),
        )
        for candidate in eligible
    ]
    ranked.sort(
        key=lambda candidate: (
            0 if candidate.qualified else 1,
            -candidate.priority,
            candidate.active_cover_count,
            candidate.display_name.casefold(),
            candidate.teacher_id,
        )
    )
    return ranked


def select_qualified_or_override(
    candidates: list[SubstituteCandidate],
) -> list[SubstituteCandidate]:
    """Turn the ranked list into the actual set of teachers to contact.

    Returns ONLY qualified (in-department) candidates. Falls back to the full
    ranked list — the explicit "override" tier — solely when no qualified
    substitute exists, so a small school with nobody in the absent teacher's
    department is not stranded. A qualified substitute is always preferred, and
    an unqualified one is never contacted while a qualified one is available.
    """
    qualified = [candidate for candidate in candidates if candidate.qualified]
    return qualified or list(candidates)


def find_substitute_candidates(
    *,
    school: Any,
    absent_teacher_user_id: int,
    work_date: Any,
) -> list[SubstituteCandidate]:
    from django.db.models import Count

    from apps.people.models import TeacherProfile
    from apps.schoolops.models import SubstituteCover

    # The qualification a cover needs is the ABSENT teacher's department: a
    # substitute who shares it can actually run that classroom's subjects. This
    # is the real production input the matcher was missing — without it
    # ``required_department_id`` stayed "" and the qualification tier was inert.
    # If the absent teacher has no department on file we cannot infer a
    # requirement, so every candidate stays eligible (no false exclusion).
    required_department_id = ""
    absent_department_id = (
        TeacherProfile.objects.filter(
            school=school,
            user_id=absent_teacher_user_id,
        )
        .values_list("department_id", flat=True)
        .first()
    )
    if absent_department_id:
        required_department_id = str(absent_department_id)

    unavailable_ids = {
        str(value)
        for value in SubstituteCover.objects.filter(
            school=school,
            work_date=work_date,
        ).values_list("absent_teacher_id", flat=True)
    }
    unavailable_ids.update(
        str(value)
        for value in SubstituteCover.objects.filter(
            school=school,
            work_date=work_date,
            covering_teacher_id__isnull=False,
        ).values_list("covering_teacher_id", flat=True)
    )
    active_counts = {
        row["covering_teacher_id"]: row["total"]
        for row in (
            SubstituteCover.objects.filter(school=school)
            .exclude(covering_teacher_id__isnull=True)
            .values("covering_teacher_id")
            .annotate(total=Count("id"))
        )
    }
    profiles = (
        TeacherProfile.objects.filter(school=school, is_active=True)
        .select_related("user", "department")
        .order_by("user__last_name", "user__first_name", "user_id")
    )
    candidates = []
    for profile in profiles:
        attrs = profile.custom_attributes or {}
        candidates.append(
            SubstituteCandidate(
                teacher_id=str(profile.user_id),
                display_name=profile.user.get_full_name() or profile.user.username,
                phone=(profile.phone or "").strip(),
                department_id=str(profile.department_id or ""),
                active_cover_count=int(active_counts.get(profile.user_id, 0)),
                priority=int(attrs.get("substitute_priority") or 0),
            )
        )
    return rank_substitute_candidates(
        absent_teacher_id=str(absent_teacher_user_id),
        candidates=candidates,
        unavailable_ids=unavailable_ids,
        required_department_id=required_department_id,
    )


def broadcast_substitute_request(
    *,
    school: Any,
    candidates: list[SubstituteCandidate],
    work_date: Any,
    period_label: str = "",
    limit: int = 5,
    send_whatsapp_fn=None,
    send_sms_fn=None,
) -> list[SubstituteBroadcastResult]:
    from apps.communication.notification_service import send_sms, send_whatsapp

    whatsapp_sender = send_whatsapp_fn or send_whatsapp
    sms_sender = send_sms_fn or send_sms
    body = (
        f"{getattr(school, 'name', 'School')} needs substitute cover on "
        f"{work_date}{' for ' + period_label if period_label else ''}. "
        "Reply to the school if you are available."
    )
    results = []
    for candidate in candidates[: max(1, min(int(limit), 25))]:
        idempotency_key = (
            f"substitute:{getattr(school, 'pk', '')}:{work_date}:"
            f"{candidate.teacher_id}:{period_label}"
        )[:255]
        accepted = bool(
            whatsapp_sender(
                school,
                candidate.phone,
                body=body,
                idempotency_key=idempotency_key,
            )
        )
        channel = "whatsapp"
        if not accepted:
            accepted = bool(
                sms_sender(
                    candidate.phone,
                    body,
                    school=school,
                    idempotency_key=idempotency_key,
                )
            )
            channel = "sms"
        results.append(
            SubstituteBroadcastResult(
                candidate_id=candidate.teacher_id,
                channel=channel,
                accepted=accepted,
            )
        )
    return results


__all__ = [
    "HandoverPacket",
    "SubstituteHandoverError",
    "TeacherAbsenceTrigger",
    "SubstituteBroadcastResult",
    "SubstituteCandidate",
    "access_check",
    "broadcast_substitute_request",
    "build_packet",
    "find_substitute_candidates",
    "rank_substitute_candidates",
    "select_qualified_or_override",
]
