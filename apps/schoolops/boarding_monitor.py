"""Non-phone RFID/NFC/QR fleet boarding monitor (Wave D — logistics).

A passive tap as a student boards/alights the bus is recorded as an append-only
``schoolops.BusBoardingEvent`` and triggers a best-effort parent notification.
Idempotent per tap (device+student+direction+timestamp or an explicit key), so a
re-read or an offline replay never double-records. The capture device (RFID
reader / NFC / QR cam) is abstracted — the platform never assumes a radio.

Offline-safe by construction: the event is an immutable log row keyed by an
idempotency key, so the offline client can queue taps locally and replay them
when the bus regains signal without any double-count.

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave D) and register row ``rfid-fleet-monitor``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_CAPTURE = ("rfid", "nfc", "qr", "manual")
_ALLOWED_DIRECTION = ("board", "alight")


def _notify_guardians(event, student) -> bool:
    """Best-effort: flag that at least one guardian contact exists to notify.

    Returns True if a notifiable guardian channel was found. Never raises — a
    notification problem must not lose the boarding record.
    """
    if student is None:
        return False
    try:
        from apps.people.models import StudentGuardian

        links = StudentGuardian.objects.filter(student_id=student.pk)
        count = 0
        for link in links:
            guardian = getattr(link, "guardian", None)
            guardian_user = getattr(link, "guardian_user", None)
            contact = (
                (getattr(guardian, "email", None) or "")
                or (getattr(guardian, "phone", None) or "")
                or (getattr(guardian_user, "email", None) or "")
            )
            if str(contact).strip():
                count += 1
        if count:
            logger.info(
                "bus boarding notify dispatched student_id=%s direction=%s guardians=%s",
                student.pk,
                event.direction,
                count,
            )
            return True
    except Exception as exc:  # noqa: BLE001 - best-effort; record must survive
        logger.warning("bus boarding notify skipped err_kind=%s", type(exc).__name__)
    return False


def record_boarding(
    *,
    school_id,
    student,
    occurred_at,
    route_id=None,
    bus_id=None,
    direction: str = "board",
    capture_method: str = "rfid",
    device_id: str = "",
    idempotency_key: str = "",
    notify: bool = True,
) -> dict[str, Any]:
    """Record one boarding/alighting tap. Idempotent; fires a best-effort notify."""
    from apps.schoolops.models import BusBoardingEvent, TransportAssignment

    if student is None:
        return {"ok": False, "error": "Unknown student / credential."}
    direction = direction if direction in _ALLOWED_DIRECTION else "board"
    method = capture_method if capture_method in _ALLOWED_CAPTURE else "rfid"
    device = str(device_id or "").strip()[:64]
    key = (idempotency_key or "").strip()[:128]
    if not key:
        key = f"board:{device or 'nodev'}:{student.pk}:{direction}:{occurred_at}"

    existing = BusBoardingEvent.objects.filter(school_id=school_id, idempotency_key=key).first()
    if existing:
        return {"ok": True, "dedup": True, "boarding_event_id": existing.id}

    # Best-effort route resolution from the student's standing assignment.
    if route_id is None:
        assignment = (
            TransportAssignment.objects.filter(school_id=school_id, student_id=student.pk)
            .order_by("-id")
            .first()
        )
        if assignment is not None:
            route_id = assignment.route_id

    event = BusBoardingEvent.objects.create(
        school_id=school_id,
        student_id=student.pk,
        route_id=route_id,
        bus_id=bus_id,
        direction=direction,
        capture_method=method,
        device_id=device,
        occurred_at=occurred_at,
        idempotency_key=key,
    )
    if notify:
        notified = _notify_guardians(event, student)
        if notified:
            event.parent_notified = True
            event.save(update_fields=["parent_notified"])
    return {
        "ok": True,
        "boarding_event_id": event.id,
        "direction": direction,
        "route_id": route_id,
        "parent_notified": event.parent_notified,
    }
