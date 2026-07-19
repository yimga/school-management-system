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


# Default match radius when campus coords are known (metric 12). Schools may
# override via ``custom_attributes.substitute_match_radius_km`` or effective
# config key ``substitute_match_radius_km``. ``0`` disables the radius tier.
DEFAULT_SUBSTITUTE_RADIUS_KM = 25.0  # magic-number-allow: substitute match default radius km


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
    # Optional home / commute coords (WGS84) from TeacherProfile.custom_attributes.
    home_lat: float | None = None
    home_lng: float | None = None
    # Filled by ``rank_substitute_candidates`` when campus coords are known.
    distance_km: float | None = None
    # Hard radius tier (mirrors ``qualified``): ``False`` only when the candidate
    # has coords AND is outside ``max_radius_km``. Missing coords stay ``True``
    # so schools without geo data are not stranded.
    within_radius: bool = True


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


def _coerce_coord(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_teacher_home_coords(attrs: dict[str, Any] | None) -> tuple[float | None, float | None]:
    data = attrs or {}
    lat = _coerce_coord(
        data.get("home_latitude")
        if data.get("home_latitude") is not None
        else data.get("substitute_latitude")
    )
    lng = _coerce_coord(
        data.get("home_longitude")
        if data.get("home_longitude") is not None
        else data.get("substitute_longitude")
    )
    if lat is None or lng is None:
        return None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None, None
    return lat, lng


def resolve_campus_coords(school: Any) -> tuple[float | None, float | None]:
    """Campus WGS84 from school attrs, then weather/header effective config."""
    attrs = getattr(school, "custom_attributes", None) or {}
    if isinstance(attrs, dict):
        lat = _coerce_coord(attrs.get("campus_latitude") or attrs.get("latitude"))
        lng = _coerce_coord(attrs.get("campus_longitude") or attrs.get("longitude"))
        if lat is not None and lng is not None:
            return lat, lng
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        lat = _coerce_coord(
            get_effective_config(school, "header_weather_latitude", default=None)
        )
        lng = _coerce_coord(
            get_effective_config(school, "header_weather_longitude", default=None)
        )
        if lat is not None and lng is not None and (lat != 0.0 or lng != 0.0):
            return lat, lng
    except Exception:  # noqa: BLE001 — config is optional for ranking
        logger.debug("substitute_handover.campus_coords config skipped", exc_info=True)
    return None, None


def resolve_substitute_radius_km(school: Any) -> float | None:
    """Max commute radius in km, or None when radius matching is disabled."""
    attrs = getattr(school, "custom_attributes", None) or {}
    raw: Any = None
    if isinstance(attrs, dict) and "substitute_match_radius_km" in attrs:
        raw = attrs.get("substitute_match_radius_km")
    else:
        try:
            from apps.platform_runtime.config_resolver import get_effective_config

            raw = get_effective_config(
                school, "substitute_match_radius_km", default=DEFAULT_SUBSTITUTE_RADIUS_KM
            )
        except Exception:  # noqa: BLE001
            raw = DEFAULT_SUBSTITUTE_RADIUS_KM
    km = _coerce_coord(raw)
    if km is None:
        return DEFAULT_SUBSTITUTE_RADIUS_KM
    if km <= 0:
        return None
    return km


def rank_substitute_candidates(
    *,
    absent_teacher_id: str,
    candidates: list[SubstituteCandidate],
    unavailable_ids: set[str] | None = None,
    required_department_id: str = "",
    campus_lat: float | None = None,
    campus_lng: float | None = None,
    max_radius_km: float | None = None,
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
    #
    # Radius is the second HARD tier when campus coords + max_radius_km are set:
    # candidates with known home coords outside the radius rank below everyone
    # inside it. Missing coords stay ``within_radius=True`` (graceful).
    apply_radius = (
        campus_lat is not None
        and campus_lng is not None
        and max_radius_km is not None
        and max_radius_km > 0
    )
    ranked: list[SubstituteCandidate] = []
    for candidate in eligible:
        qualified = (not required) or (candidate.department_id == required)
        distance_km = candidate.distance_km
        within = True
        if apply_radius and candidate.home_lat is not None and candidate.home_lng is not None:
            from apps.schoolops.route_optimizer import haversine_km

            distance_km = haversine_km(
                campus_lat, campus_lng, candidate.home_lat, candidate.home_lng
            )
            within = distance_km <= float(max_radius_km)
        elif apply_radius and campus_lat is not None and campus_lng is not None:
            # Soft distance when campus known but teacher has no home coords —
            # leave distance_km None; within_radius stays True.
            pass
        ranked.append(
            replace(
                candidate,
                qualified=qualified,
                distance_km=distance_km,
                within_radius=within,
            )
        )
    ranked.sort(
        key=lambda candidate: (
            0 if candidate.qualified else 1,
            0 if candidate.within_radius else 1,
            candidate.distance_km if candidate.distance_km is not None else float("inf"),
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

    Prefers qualified (in-department) candidates, then within-radius. Falls back
    to the next tier only when the preferred pool is empty so a small school is
    not stranded. An out-of-radius or unqualified teacher is never contacted
    while a better-tier candidate is available.
    """
    qualified = [candidate for candidate in candidates if candidate.qualified]
    pool = qualified or list(candidates)
    nearby = [candidate for candidate in pool if candidate.within_radius]
    return nearby or pool


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
        home_lat, home_lng = _parse_teacher_home_coords(attrs)
        candidates.append(
            SubstituteCandidate(
                teacher_id=str(profile.user_id),
                display_name=profile.user.get_full_name() or profile.user.username,
                phone=(profile.phone or "").strip(),
                department_id=str(profile.department_id or ""),
                active_cover_count=int(active_counts.get(profile.user_id, 0)),
                priority=int(attrs.get("substitute_priority") or 0),
                home_lat=home_lat,
                home_lng=home_lng,
            )
        )
    campus_lat, campus_lng = resolve_campus_coords(school)
    max_radius_km = (
        resolve_substitute_radius_km(school) if campus_lat is not None else None
    )
    return rank_substitute_candidates(
        absent_teacher_id=str(absent_teacher_user_id),
        candidates=candidates,
        unavailable_ids=unavailable_ids,
        required_department_id=required_department_id,
        campus_lat=campus_lat,
        campus_lng=campus_lng,
        max_radius_km=max_radius_km,
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
    "DEFAULT_SUBSTITUTE_RADIUS_KM",
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
    "resolve_campus_coords",
    "resolve_substitute_radius_km",
    "select_qualified_or_override",
]
