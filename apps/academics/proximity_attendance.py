"""Device-agnostic proximity attendance ingest (Wave B — ambient capture).

A *proximity ping* — emitted by a BLE beacon, an RFID/NFC tap, or a QR scan —
is normalised into a standard attendance record and routed through the existing
offline queue (``action_type=ATTENDANCE``). That means it works fully
disconnected on a campus edge device and drains on reconnect, exactly like the
manual teacher attendance path.

Deliberately reuses ``academics.Attendance`` (no new model, no migration): the
proximity nature is carried in the payload + recorded in ``remarks`` for audit.
The capture device is abstracted — the platform never assumes a specific radio,
so the same endpoint serves beacon, RFID, NFC and QR hardware.

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave B) and the register row
``bluetooth-proximity-attendance``.
"""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import enqueue_offline_action

# Capture methods we annotate; anything unknown is normalised to "beacon".
ALLOWED_CAPTURE_METHODS: tuple[str, ...] = ("beacon", "rfid", "nfc", "qr", "manual")

_DEFAULT_CAPTURE_METHOD = "beacon"
_DEFAULT_STATUS = "present"


def normalize_capture_method(method: Any) -> str:
    """Lower-case + allow-list a capture method, defaulting to ``beacon``."""
    candidate = str(method or "").strip().lower()
    return candidate if candidate in ALLOWED_CAPTURE_METHODS else _DEFAULT_CAPTURE_METHOD


def build_proximity_remarks(method: str, device_id: str, signal_strength: Any) -> str:
    """Human-readable audit note for a proximity check-in (handler truncates)."""
    bits = [f"Proximity check-in via {method}"]
    device = str(device_id or "").strip()[:64]
    if device:
        bits.append(f"(device {device})")
    if signal_strength is not None and str(signal_strength).strip() != "":
        bits.append(f"rssi={signal_strength}")
    return " ".join(bits)


def record_proximity_checkin(
    *,
    school_id,
    user_id: int,
    student_id,
    classroom_id,
    date,
    capture_method: Any = _DEFAULT_CAPTURE_METHOD,
    device_id: str = "",
    status: Any = _DEFAULT_STATUS,
    signal_strength: Any = None,
) -> OfflineAction:
    """Queue a proximity attendance ping as an offline ATTENDANCE action.

    Idempotent per (device, student, date) so a beacon that re-emits the same
    ping (or a flaky reconnect) never double-records attendance.
    Returns the persisted :class:`OfflineAction` (QUEUED, or the existing row).
    """
    method = normalize_capture_method(capture_method)
    device = str(device_id or "").strip()[:64]
    payload: dict[str, Any] = {
        "student_id": student_id,
        "classroom_id": classroom_id,
        "date": date,
        "status": str(status or _DEFAULT_STATUS),
        "remarks": build_proximity_remarks(method, device, signal_strength),
        "capture_method": method,
        "device_id": device,
    }
    idempotency_key = f"proximity:{device or 'nodev'}:{student_id}:{date}"
    return enqueue_offline_action(
        user_id=user_id,
        school_id=school_id,
        action_type=OfflineAction.ActionType.ATTENDANCE,
        payload=payload,
        idempotency_key=idempotency_key,
    )
