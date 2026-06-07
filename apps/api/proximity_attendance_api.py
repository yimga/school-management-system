"""Proximity attendance ingest endpoint (Wave B — ambient capture).

Accepts a device-agnostic proximity ping (BLE beacon / RFID / NFC / QR) and
queues it as an offline ATTENDANCE action via the existing offline pipeline, so
it works disconnected and drains on reconnect. Idempotent per device+student+date.

Core logic lives in ``apps.academics.proximity_attendance``; this view is a thin,
authenticated, tenant-scoped wrapper.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.proximity_attendance import record_proximity_checkin


@extend_schema(
    operation_id="proximity_attendance_ingest",
    request=None,
    responses={202: None, 400: None},
    description=(
        "Queue a proximity attendance ping (BLE/RFID/NFC/QR). Body: "
        "student_id, classroom_id, date (required); capture_method, device_id, "
        "status, signal_strength (optional). Returns the queued offline action."
    ),
)
class ProximityAttendanceIngestAPI(APIView):
    """POST a proximity attendance ping. Offline-first + idempotent."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response(
                {"ok": False, "error": "No active school context."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        data = request.data or {}
        student_id = data.get("student_id") or data.get("student")
        classroom_id = data.get("classroom_id") or data.get("classroom")
        date_val = data.get("date")
        if not all([student_id, classroom_id, date_val]):
            return Response(
                {"ok": False, "error": "student_id, classroom_id and date are required."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        action = record_proximity_checkin(
            school_id=school.id,
            user_id=request.user.id,
            student_id=student_id,
            classroom_id=classroom_id,
            date=date_val,
            capture_method=data.get("capture_method", "beacon"),
            device_id=data.get("device_id", ""),
            status=data.get("status", "present"),
            signal_strength=data.get("signal_strength"),
        )
        return Response(
            {"ok": True, "offline_action_id": action.id, "status": action.status},
            status=http_status.HTTP_202_ACCEPTED,
        )
