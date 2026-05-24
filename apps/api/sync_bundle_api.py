"""Signed sync bundle upload (SODP batch 1412)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sync_engine.delta_bundle import verify_and_parse_bundle


@extend_schema_view(
    post=extend_schema(
        tags=["Offline Sync"],
        summary="Upload signed sync bundle",
        description="Accepts a signed delta sync bundle from an offline device; verifies signature, school binding, and parses rows.",
        responses={200: dict, 400: dict},
    ),
)
class SyncBundleUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"error": "school_required"}, status=400)
        data = request.body or b""
        rows, errors = verify_and_parse_bundle(data, expected_school_id=school.pk)
        if errors:
            return Response({"ok": False, "errors": errors}, status=400)
        return Response({"ok": True, "imported": len(rows)})


__all__ = ["SyncBundleUploadView"]
