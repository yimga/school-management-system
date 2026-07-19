"""High-frequency substitute shift market — DB-durable + optional cache fence.

Source of truth is ``SubstituteMarketShift`` in the DB.  Cache (Redis when
``REDIS_URL`` is set) is an optional race-fence for the slot lock, NOT the
durable state.  A ``cache.clear()`` never loses an open shift.

WebSocket notifications use Channels group ``school-{school_id}-substitute-market``.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from django.core.cache import cache
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

LOCK_PREFIX = "rmc:substitute:lock:"
SHIFT_PREFIX = "rmc:substitute:shift:"
OPEN_INDEX_PREFIX = "rmc:substitute:open_index:"
DEFAULT_LOCK_TTL_SEC = 120  # magic-number-allow: short-lived cache race fence
DEFAULT_SHIFT_TTL_SEC = 86400  # magic-number-allow: substitute shift availability TTL = 1 day (seconds)


def substitute_market_room_name(school_id: Any) -> str:
    """Per-SCHOOL Channels group for the substitute-shift market.

    Every ops-admin and teacher socket on a tenant joins this ONE group, so an
    opened / claimed cover shift fans out to the whole school's substitute
    market at once. This is a per-SCHOOL broadcast (a shift opening must reach
    every eligible substitute + the ops desk), NOT a per-(school, user) room
    like ``tenant_sync_room_name``.

    ``apps.api.consumers.SubstituteMarketConsumer`` derives ``school_id`` from
    the authenticated socket scope (``scope["school_id"]``, bound by
    ``TenantChannelsMiddleware`` from the host + membership check) — never from
    client input — so a user can only ever join their OWN school's group and a
    cross-tenant subscription is impossible. This helper is the single source of
    the group name for BOTH the producer (below) and that consumer; the two are
    locked byte-for-byte by
    ``test_substitute_market_realtime.test_room_formula_matches_consumer``.

    Pass the CANONICAL ``str(school.pk)`` (what ``scope["school_id"]`` holds).
    ``School.pk`` is a UUID, so the module's internal integer ``school_id`` (used
    for cache-lock keys) must NOT be used here: ``int(uuid)`` and ``str(uuid)``
    differ, and the consumer only ever has the ``str`` form.
    """
    return f"school-{school_id}-substitute-market"


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
    notify_attempted: int = 0
    notify_accepted: int = 0
    notify_used_override: bool = False


# ---------------------------------------------------------------------------
# Cache helpers (optional speed fence — DB is SOT)
# ---------------------------------------------------------------------------

def _lock_key(*, school_id: int, work_date: date, period_label: str) -> str:
    slot = (period_label or "full_day").strip().lower().replace(" ", "_")
    return f"{LOCK_PREFIX}{school_id}:{work_date.isoformat()}:{slot}"


def _shift_cache_key(shift_id: str) -> str:
    return f"{SHIFT_PREFIX}{shift_id}"


def _open_index_key(school_id: int) -> str:
    return f"{OPEN_INDEX_PREFIX}{school_id}"


def _cache_mirror_open(school_id: int, shift_id: str, payload: dict) -> None:
    """Best-effort cache mirror for fast reads."""
    try:
        cache.set(_shift_cache_key(shift_id), payload, DEFAULT_SHIFT_TTL_SEC)
        key = _open_index_key(school_id)
        current = list(cache.get(key) or [])
        if shift_id not in current:
            current.append(shift_id)
            cache.set(key, current, DEFAULT_SHIFT_TTL_SEC)
    except Exception:  # noqa: BLE001
        pass


def _cache_mirror_claim(school_id: int, shift_id: str) -> None:
    """Best-effort remove from cache index on claim."""
    try:
        cached = cache.get(_shift_cache_key(shift_id))
        if cached:
            cached["status"] = "claimed"
            cache.set(_shift_cache_key(shift_id), cached, DEFAULT_SHIFT_TTL_SEC)
        key = _open_index_key(school_id)
        current = [sid for sid in (cache.get(key) or []) if sid != shift_id]
        cache.set(key, current, DEFAULT_SHIFT_TTL_SEC)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def acquire_shift_slot_lock(
    *,
    school_id: int,
    work_date: date,
    period_label: str = "",
    ttl_sec: int = DEFAULT_LOCK_TTL_SEC,
) -> bool:
    """Atomic lock via cache.add — returns True when this caller owns the slot."""
    return cache.add(
        _lock_key(school_id=school_id, work_date=work_date, period_label=period_label),
        "1",
        ttl_sec,
    )


def release_shift_slot_lock(*, school_id: int, work_date: date, period_label: str = "") -> None:
    cache.delete(_lock_key(school_id=school_id, work_date=work_date, period_label=period_label))


def list_open_shifts(*, school_id: int) -> list[dict[str, Any]]:
    """Return open shift payloads for a school (for ops claim UI).

    Queries the DB as source of truth.  The ``school_id`` parameter accepts
    ``int(school.pk)`` for backwards compatibility with callers that pass that.
    """
    from apps.schoolops.models import SubstituteMarketShift

    qs = SubstituteMarketShift.objects.filter(
        school_id=school_id,
        status=SubstituteMarketShift.STATUS_OPEN,
    ).order_by("-created_at")

    rows: list[dict[str, Any]] = []
    for shift in qs:
        rows.append({
            "shift_id": str(shift.pk),
            "school_id": int(shift.school_id),
            "absent_teacher_id": shift.absent_teacher_id,
            "work_date": shift.work_date.isoformat(),
            "period_label": shift.period_label,
            "status": shift.status,
        })
    return rows


def open_shift(
    *,
    school: Any,
    absent_teacher_id: int,
    work_date: date,
    period_label: str = "",
    publish_fn: Callable[[dict[str, Any]], None] | None = None,
    notify: bool = True,
    send_whatsapp_fn=None,
    send_sms_fn=None,
) -> OpenShift:
    """Open a substitute shift; persists to DB first (durable), cache second.

    Idempotent: if an open shift already exists for this (school, work_date,
    period_label, absent_teacher), raises ShiftAlreadyBooked.  The cache lock
    remains as a fast-path race fence but is NOT required for correctness.

    Metric 12 DoD: opening a market shift also ranks available substitutes and
    broadcasts WhatsApp/SMS to the qualified tier (or override when none), so
    ops do not need a separate "Find and broadcast" click after open.
    """
    from apps.schoolops.models import SubstituteMarketShift

    school_id = int(getattr(school, "pk"))

    # Fast-path cache fence (non-authoritative)
    cache_locked = acquire_shift_slot_lock(
        school_id=school_id, work_date=work_date, period_label=period_label
    )

    # DB is SOT — enforce uniqueness inside a transaction
    try:
        with transaction.atomic():
            existing = SubstituteMarketShift.objects.filter(
                school_id=school_id,
                absent_teacher_id=absent_teacher_id,
                work_date=work_date,
                period_label=period_label,
                status=SubstituteMarketShift.STATUS_OPEN,
            ).exists()
            if existing:
                raise ShiftAlreadyBooked("substitute slot already locked or booked")

            db_shift = SubstituteMarketShift.objects.create(
                school_id=school_id,
                absent_teacher_id=absent_teacher_id,
                work_date=work_date,
                period_label=period_label,
                status=SubstituteMarketShift.STATUS_OPEN,
            )
    except ShiftAlreadyBooked:
        raise
    except IntegrityError:
        raise ShiftAlreadyBooked("substitute slot already locked or booked")

    shift = OpenShift(
        shift_id=str(db_shift.pk),
        school_id=school_id,
        absent_teacher_id=absent_teacher_id,
        work_date=work_date,
        period_label=period_label,
    )

    # Mirror to cache for speed
    _cache_mirror_open(school_id, shift.shift_id, {
        "shift_id": shift.shift_id,
        "school_id": shift.school_id,
        "absent_teacher_id": shift.absent_teacher_id,
        "work_date": shift.work_date.isoformat(),
        "period_label": shift.period_label,
        "status": shift.status,
    })

    from apps.schoolops.substitute_handover import (
        broadcast_substitute_request,
        find_substitute_candidates,
        select_qualified_or_override,
    )

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
    _publish_substitute_event(
        room_school_id=str(getattr(school, "pk")),
        payload=payload,
        publish_fn=publish_fn,
    )

    notify_attempted = 0
    notify_accepted = 0
    notify_used_override = False
    if notify and candidates:
        selected = select_qualified_or_override(candidates)
        if selected:
            notify_used_override = not selected[0].qualified
            try:
                broker_results = broadcast_substitute_request(
                    school=school,
                    candidates=selected,
                    work_date=work_date,
                    period_label=period_label,
                    send_whatsapp_fn=send_whatsapp_fn,
                    send_sms_fn=send_sms_fn,
                )
                notify_attempted = len(broker_results)
                notify_accepted = sum(1 for result in broker_results if result.accepted)
            except Exception:  # noqa: BLE001 — notify must never unwind an open shift
                logger.warning(
                    "substitute_market.notify_failed shift=%s school=%s",
                    shift.shift_id,
                    school_id,
                    exc_info=True,
                )

    shift.notify_attempted = notify_attempted
    shift.notify_accepted = notify_accepted
    shift.notify_used_override = notify_used_override

    # Persist notify stats back to the durable row
    SubstituteMarketShift.objects.filter(pk=db_shift.pk).update(
        notify_attempted=notify_attempted,
        notify_accepted=notify_accepted,
        notify_used_override=notify_used_override,
    )

    logger.info(
        "substitute_market.open shift=%s school=%s absent=%s candidates=%s "
        "notify_accepted=%s/%s override=%s",
        shift.shift_id,
        school_id,
        absent_teacher_id,
        len(candidates),
        notify_accepted,
        notify_attempted,
        notify_used_override,
    )
    return shift


def claim_shift(
    *,
    school: Any,
    shift_id: str,
    substitute_teacher_id: int,
    publish_fn: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    """Atomically claim an open shift and persist ``SubstituteCover``.

    Works after cache.clear() — loads shift from DB as source of truth.
    """
    from apps.schoolops.models import SubstituteCover, SubstituteMarketShift

    school_id = int(getattr(school, "pk"))

    with transaction.atomic():
        try:
            db_shift = (
                SubstituteMarketShift.objects
                .select_for_update()
                .get(pk=shift_id, school_id=school_id, status=SubstituteMarketShift.STATUS_OPEN)
            )
        except SubstituteMarketShift.DoesNotExist:
            raise SubstituteMarketError("shift_not_open")

        cover, _created = SubstituteCover.objects.get_or_create(
            school_id=school_id,
            work_date=db_shift.work_date,
            absent_teacher_id=db_shift.absent_teacher_id,
            period_label=db_shift.period_label,
            defaults={"covering_teacher_id": substitute_teacher_id},
        )
        if cover.covering_teacher_id and cover.covering_teacher_id != substitute_teacher_id:
            raise ShiftAlreadyBooked("cover already assigned")
        if not cover.covering_teacher_id:
            cover.covering_teacher_id = substitute_teacher_id
            cover.save(update_fields=["covering_teacher_id"])

        db_shift.status = SubstituteMarketShift.STATUS_CLAIMED
        db_shift.claimed_by_id = substitute_teacher_id
        db_shift.cover = cover
        db_shift.save(update_fields=["status", "claimed_by_id", "cover_id", "updated_at"])

    # Best-effort cache mirror
    _cache_mirror_claim(school_id, shift_id)

    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]

    payload = SubstituteShiftClaimEvent(
        shift_id=shift_id,
        school_id=str(school_id),
        substitute_teacher_id_hash=_hash(str(substitute_teacher_id)),
        cover_id=cover.pk,
    ).to_dict()
    _publish_substitute_event(
        room_school_id=str(getattr(school, "pk")),
        payload=payload,
        publish_fn=publish_fn,
    )
    return int(cover.pk)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _publish_substitute_event(
    *,
    room_school_id: Any,
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
        group = substitute_market_room_name(room_school_id)
        async_to_sync(layer.group_send)(
            group,
            {"type": "substitute.shift.event", "payload": payload},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("substitute_market channels publish skipped: %s", exc)
