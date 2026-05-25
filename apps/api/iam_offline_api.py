"""IAM snapshot + offline intent APIs (batch 1507)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.iam_snapshot import build_permission_snapshot, sign_snapshot
from apps.accounts.rebac_intents import apply_offline_access_intent, enqueue_request_access
from apps.platform_runtime.helpers import get_effective_offline_runtime_settings


class PermissionSnapshotSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    offline_token = serializers.BooleanField(required=False, default=False)


@extend_schema_view(
    get=extend_schema(
        tags=["Offline Sync", "IAM"],
        summary="Signed read-only permission snapshot",
        description=(
            "Returns capabilities + relations for offline navigation cache. "
            "Never grants admin offline; snapshot is read-only."
        ),
    ),
)
class PermissionSnapshotAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"error": "school_required"}, status=status.HTTP_400_BAD_REQUEST)
        offline = bool(
            get_effective_offline_runtime_settings(request=request).get(
                "enable_offline_mode",
                False,
            ),
        )
        device_id = (request.query_params.get("device_id") or "").strip()
        offline_token = request.query_params.get("offline_token") in (
            "1",
            "true",
            "yes",
        )
        body = build_permission_snapshot(
            request.user,
            school=school,
            offline_token=offline_token,
            device_id=device_id,
        )
        signed = sign_snapshot(body)
        return Response(
            {
                "snapshot": signed,
                "offline_mode_enabled": offline,
            },
        )


class OfflineIamIntentSerializer(serializers.Serializer):
    permission_code = serializers.CharField(max_length=120)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(
        max_length=128, required=False, allow_blank=True,
    )


@extend_schema_view(
    post=extend_schema(
        tags=["Offline Sync", "IAM"],
        summary="Queue low-risk IAM intent (request access)",
        request=OfflineIamIntentSerializer,
    ),
)
class OfflineIamIntentAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"error": "school_required"}, status=status.HTTP_400_BAD_REQUEST)
        if not bool(
            get_effective_offline_runtime_settings(request=request).get(
                "enable_offline_mode",
                False,
            ),
        ):
            return Response(
                {"error": "offline_disabled"},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = OfflineIamIntentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        key = (ser.validated_data.get("idempotency_key") or "").strip()
        if key:
            from apps.accounts.models_rebac import OfflineAccessIntent

            existing = OfflineAccessIntent.objects.filter(
                school=school,
                idempotency_key=key,
            ).first()
            if existing:
                return Response(
                    {
                        "intent_id": existing.pk,
                        "status": existing.status,
                        "server_note": existing.server_note,
                    },
                    status=status.HTTP_200_OK,
                )
        intent = enqueue_request_access(
            user=request.user,
            school=school,
            permission_code=ser.validated_data["permission_code"],
            reason=ser.validated_data.get("reason") or "",
            idempotency_key=key,
        )
        applied, note = apply_offline_access_intent(intent)
        return Response(
            {
                "intent_id": intent.pk,
                "applied": applied,
                "status": intent.status,
                "server_note": note,
            },
            status=status.HTTP_201_CREATED,
        )
