"""High-frequency substitute shift market — Redis/cache locks + realtime fan-out.

Uses Django cache (Redis when ``REDIS_URL`` is set) to prevent double-bookings.
WebSocket notifications use Channels group ``school-{school_id}-substitute-market``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

LOCK_PREFIX = "rmc:substitute:lock:"
SHIFT_PREFIX = "rmc:substitute:shift:"
DEFAULT_LOCK_TTL_SEC = 120
DEFAULT_SHIFT_TTL_SEC = 86400  # magic-number-allow: substitute shift availability TTL = 1 day (seconds)


class SubstituteMarketError(RuntimeError):
    pass


class ShiftAlreadyBooked(SubstituteMarketError):
    pass


@dataclass(frozen=True)
class SubstituteShiftOpenEvent:
    """WebSocket / SSE payload when a cover shift opens."""

    schema_version: str = "substitute_shift.v1"
    event: str = "shift.open"
    shift_id: str = ""
    school_id: str = ""
    work_date: str = ""
    period_label: str = ""
    absent_teacher_id_hash: str = ""
    candidate_count: int = 0
    expires_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubstituteShiftClaimEvent:
    schema_version: str = "substitute_shift.v1"
    event: str = "shift.claimed"
    shift_id: str = ""
    school_id: str = ""
    substitute_teacher_id_hash: str = ""
    cover_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OpenShift:
    shift_id: str
    school_id: int
    absent_teacher_id: int
    work_date: date
    period_label: str = ""
    status: str = "open"
    claimed_by_id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _lock_key(*, school_id: int, work_date: date, period_label: str) -> str:
    slot = (period_label or "full_day").strip().lower().replace(" ", "_")
    return f"{LOCK_PREFIX}{school_id}:{work_date.isoformat()}:{slot}"


def _shift_cache_key(shift_id: str) -> str:
    return f"{SHIFT_PREFIX}{shift_id}"


def acquire_shift_slot_lock(
    *,
    school_id: int,
    work_date: date,
    period_label: str = "",
    ttl_sec: int = DEFAULT_LOCK_TTL_SEC,
) -> bool:
    """Atomic lock via cache.add — returns True when this caller owns the slot."""
    return cache.add(_lock_key(school_id=school_id, work_date=work_date, period_label=period_label), "1", ttl_sec)


def release_shift_slot_lock(*, school_id: int, work_date: date, period_label: str = "") -> None:
    cache.delete(_lock_key(school_id=school_id, work_date=work_date, period_label=period_label))


def open_shift(
    *,
    school: Any,
    absent_teacher_id: int,
    work_date: date,
    period_label: str = "",
    publish_fn: Callable[[dict[str, Any]], None] | None = None,
) -> OpenShift:
    """Open a substitute shift; fails fast when slot lock cannot be acquired."""
    school_id = int(getattr(school, "pk"))
    if not acquire_shift_slot_lock(school_id=school_id, work_date=work_date, period_label=period_label):
        raise ShiftAlreadyBooked("substitute slot already locked or booked")

    shift = OpenShift(
        shift_id=str(uuid.uuid4()),
        school_id=school_id,
        absent_teacher_id=absent_teacher_id,
        work_date=work_date,
        period_label=period_label,
    )
    cache.set(
        _shift_cache_key(shift.shift_id),
        {
            "shift_id": shift.shift_id,
            "school_id": shift.school_id,
            "absent_teacher_id": shift.absent_teacher_id,
            "work_date": shift.work_date.isoformat(),
            "period_label": shift.period_label,
            "status": shift.status,
        },
        DEFAULT_SHIFT_TTL_SEC,
    )

    from apps.schoolops.substitute_handover import find_substitute_candidates
    import hashlib

    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    candidates = find_substitute_candidates(
        school=school,
        absent_teacher_user_id=absent_teacher_id,
        work_date=work_date,
    )
    payload = SubstituteShiftOpenEvent(
        shift_id=shift.shift_id,
        school_id=str(school_id),
        work_date=work_date.isoformat(),
        period_label=period_label,
        absent_teacher_id_hash=_hash(str(absent_teacher_id)),
        candidate_count=len(candidates),
        expires_at=(datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
    ).to_dict()
    _publish_substitute_event(school_id=school_id, payload=payload, publish_fn=publish_fn)
    logger.info(
        "substitute_market.open shift=%s school=%s absent=%s candidates=%s",
        shift.shift_id,
        school_id,
        absent_teacher_id,
        len(candidates),
    )
    return shift


def claim_shift(
    *,
    school: Any,
    shift_id: str,
    substitute_teacher_id: int,
    publish_fn: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    """Atomically claim an open shift and persist ``SubstituteCover``."""
    from apps.schoolops.models import SubstituteCover
    import hashlib

    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    cached = cache.get(_shift_cache_key(shift_id))
    if not cached or cached.get("status") != "open":
        raise SubstituteMarketError("shift_not_open")

    school_id = int(getattr(school, "pk"))
    if int(cached.get("school_id", 0)) != school_id:
        raise SubstituteMarketError("tenant_mismatch")

    work_date = date.fromisoformat(cached["work_date"])
    period_label = cached.get("period_label") or ""

    if not acquire_shift_slot_lock(school_id=school_id, work_date=work_date, period_label=period_label):
        raise ShiftAlreadyBooked("slot claimed by another substitute")

    try:
        with transaction.atomic():
            cover, _created = SubstituteCover.objects.get_or_create(
                school_id=school_id,
                work_date=work_date,
                absent_teacher_id=int(cached["absent_teacher_id"]),
                period_label=period_label,
                defaults={"covering_teacher_id": substitute_teacher_id},
            )
            if cover.covering_teacher_id and cover.covering_teacher_id != substitute_teacher_id:
                raise ShiftAlreadyBooked("cover already assigned")
            if not cover.covering_teacher_id:
                cover.covering_teacher_id = substitute_teacher_id
                cover.save(update_fields=["covering_teacher_id"])
    except ShiftAlreadyBooked:
        release_shift_slot_lock(school_id=school_id, work_date=work_date, period_label=period_label)
        raise

    cached["status"] = "claimed"
    cached["claimed_by_id"] = substitute_teacher_id
    cache.set(_shift_cache_key(shift_id), cached, DEFAULT_SHIFT_TTL_SEC)

    payload = SubstituteShiftClaimEvent(
        shift_id=shift_id,
        school_id=str(school_id),
        substitute_teacher_id_hash=_hash(str(substitute_teacher_id)),
        cover_id=cover.pk,
    ).to_dict()
    _publish_substitute_event(school_id=school_id, payload=payload, publish_fn=publish_fn)
    return int(cover.pk)


def _publish_substitute_event(
    *,
    school_id: int,
    payload: dict[str, Any],
    publish_fn: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    if publish_fn is not None:
        try:
            publish_fn(payload)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("substitute_market custom publish failed: %s", exc)

    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        group = f"school-{school_id}-substitute-market"
        async_to_sync(layer.group_send)(
            group,
            {"type": "substitute.shift.event", "payload": payload},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("substitute_market channels publish skipped: %s", exc)
