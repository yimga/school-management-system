"""Cashless campus POS checkout endpoint (Wave C — campus commerce).

Thin, authenticated, tenant-scoped wrapper over
``apps.schoolops.pos_checkout.checkout``. Resolves the student from an explicit
id or a scanned credential (QR/RFID → student_code), runs the allergen barrier +
wallet debit, and maps the service result to HTTP status.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.schoolops.pos_checkout import checkout, resolve_student_for_credential


@extend_schema(
    operation_id="pos_cashless_checkout",
    request=None,
    responses={200: None, 400: None, 402: None, 404: None, 409: None},
    description=(
        "Cashless campus POS checkout. Body: student_id OR credential (badge/QR), "
        "items [{label, unit_price, quantity}] (required); payment_method, "
        "idempotency_key (optional). Refuses sales that hit a student allergen and "
        "debits the campus wallet atomically."
    ),
)
class PosCheckoutAPI(APIView):
    """POST a cashless campus purchase. Allergen-blocked, idempotent, Decimal-safe."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response(
                {"ok": False, "error": "No active school context."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        data = request.data or {}
        items = data.get("items") or []
        if not items:
            return Response(
                {"ok": False, "error": "items is required."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        student = resolve_student_for_credential(
            school.id,
            student_id=data.get("student_id") or data.get("student"),
            credential=data.get("credential") or data.get("badge"),
        )
        if student is None:
            return Response(
                {"ok": False, "error": "Unknown student / credential."},
                status=http_status.HTTP_404_NOT_FOUND,
            )
        result = checkout(
            school_id=school.id,
            student=student,
            items=items,
            cashier_user_id=request.user.id,
            payment_method=data.get("payment_method", "account"),
            idempotency_key=data.get("idempotency_key", ""),
        )
        if result.get("ok"):
            return Response(result, status=http_status.HTTP_200_OK)
        if result.get("insufficient"):
            return Response(result, status=http_status.HTTP_402_PAYMENT_REQUIRED)
        if result.get("blocked"):
            return Response(result, status=http_status.HTTP_409_CONFLICT)
        return Response(result, status=http_status.HTTP_400_BAD_REQUEST)
