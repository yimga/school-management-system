"""DRF offline device token mint API (SODP batch 1408)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken


class OfflineTokenMintSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=128)
    public_key_fingerprint = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )
    permission_bitmap = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
    )


@extend_schema_view(
    post=extend_schema(
        tags=["Offline Sync"],
        summary="Mint scoped offline capability token",
        description="Online session required; registers device and mints a 12h-expiry capability token.",
        request=OfflineTokenMintSerializer,
        responses={201: dict},
    ),
)
class OfflineTokenMintView(APIView):
    """Mint scoped offline capability token (online session required)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"error": "school_required"}, status=status.HTTP_400_BAD_REQUEST)
        ser = OfflineTokenMintSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        device_id = ser.validated_data["device_id"].strip()
        perms = ser.validated_data.get("permission_bitmap") or ["attendance.mark", "grade.submit"]
        device, _created = DeviceRegistration.objects.update_or_create(
            school=school,
            user=request.user,
            device_id=device_id,
            defaults={
                "public_key_fingerprint": ser.validated_data.get("public_key_fingerprint") or "",
                "permission_bitmap": perms,
                "revoked_at": None,
                "last_seen_at": timezone.now(),
            },
        )
        raw_token = secrets.token_urlsafe(32)
        fingerprint = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = timezone.now() + timedelta(hours=12)
        OfflineCapabilityToken.objects.create(
            device=device,
            school=school,
            user=request.user,
            token_fingerprint=fingerprint,
            permission_bitmap=perms,
            expires_at=expires_at,
        )
        return Response(
            {
                "capability_blob": raw_token,
                "expires_at": expires_at.isoformat(),
                "permission_bitmap": perms,
            },
            status=status.HTTP_201_CREATED,
        )


__all__ = ["OfflineTokenMintView"]
