"""Bus boarding monitor ingest endpoint (Wave D — logistics).

Accepts a passive RFID/NFC/QR boarding tap and records a
``schoolops.BusBoardingEvent`` (idempotent) with a best-effort parent notify.
Thin, authenticated, tenant-scoped wrapper over
``apps.schoolops.boarding_monitor.record_boarding``.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schoolops.boarding_monitor import record_boarding


@extend_schema(
    operation_id="bus_boarding_ingest",
    request=None,
    responses={202: None, 400: None, 404: None},
    description=(
        "Record a bus boarding/alighting tap (RFID/NFC/QR). Body: student_id OR "
        "credential (badge) (required); direction (board|alight), route_id, bus_id, "
        "capture_method, device_id, occurred_at, idempotency_key (optional)."
    ),
)
class BusBoardingIngestAPI(APIView):
    """POST a boarding tap. Offline-safe (append-only + idempotent) + parent notify."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response(
                {"ok": False, "error": "No active school context."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        data = request.data or {}
        from apps.people.models import StudentProfile

        qs = StudentProfile.objects.filter(school_id=school.id)
        student = None
        if data.get("student_id") or data.get("student"):
            student = qs.filter(pk=data.get("student_id") or data.get("student")).first()
        elif data.get("credential") or data.get("badge"):
            student = qs.filter(
                student_code=str(data.get("credential") or data.get("badge")).strip()
            ).first()
        if student is None:
            return Response(
                {"ok": False, "error": "Unknown student / credential."},
                status=http_status.HTTP_404_NOT_FOUND,
            )
        occurred_at = data.get("occurred_at") or timezone.now()
        result = record_boarding(
            school_id=school.id,
            student=student,
            occurred_at=occurred_at,
            route_id=data.get("route_id"),
            bus_id=data.get("bus_id"),
            direction=data.get("direction", "board"),
            capture_method=data.get("capture_method", "rfid"),
            device_id=data.get("device_id", ""),
            idempotency_key=data.get("idempotency_key", ""),
        )
        status_code = (
            http_status.HTTP_202_ACCEPTED if result.get("ok") else http_status.HTTP_400_BAD_REQUEST
        )
        return Response(result, status=status_code)
