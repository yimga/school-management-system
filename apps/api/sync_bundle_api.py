"""Signed sync-bundle upload — verify, then PERSIST via the delta apply path.

A LAN "data-mule" or a sovereign edge box uploads a signed NDJSON delta bundle
(the same row shape ``DeltaSyncAPI`` accepts online). This receiver verifies the
HMAC trailer + school binding, then routes the rows through
``apps.api.sync_services.apply_changes`` — the SAME tested path ``DeltaSyncAPI``
uses online — so writes actually land and per-record conflicts are recorded
(``SyncConflict``, updated_at check) for Sync Center resolution instead of the
old stub's silent ``{"imported": <count>}`` with no persistence.

The receiver is deliberately NOT gated on the local ``enable_offline_mode`` flag
(unlike ``DeltaSyncAPI``): the endpoint acts as the *receiving* side (e.g. the
operator ingesting an edge box's bundle), which need not itself be in offline
mode. Safety comes from ``apply_changes`` — it enforces per-entity edit
permission and per-row tenant scope regardless of the feature flag.

See docs/plans/TIER3_TENANT_PORTABILITY_AND_EDGE_SYNC.md (Slice 1).
"""

from __future__ import annotations

from django.conf import settings
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.api.edge_auth import EdgeCredentialAuthentication
from apps.api.sync_services import apply_changes
from apps.schools.tenant_api_guards import user_may_operate_on_school
from apps.sync_engine.delta_bundle import verify_and_parse_bundle


@extend_schema_view(
    post=extend_schema(
        tags=["Offline Sync"],
        summary="Upload signed sync bundle",
        description=(
            "Accepts a signed NDJSON delta bundle from an offline device / sovereign "
            "edge box; verifies the HMAC signature + school binding, then applies the "
            "rows through the delta-sync engine (updated_at conflict check; a newer "
            "server record yields a SyncConflict rather than an overwrite)."
        ),
        responses={200: dict, 400: dict, 403: dict},
    ),
)
class SyncBundleUploadView(APIView):
    # Edge machine credential FIRST (so an edge box needs no session/subdomain), then
    # the project defaults so an online session upload still authenticates normally.
    authentication_classes = [EdgeCredentialAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"ok": False, "error": "school_required"}, status=403)
        if not user_may_operate_on_school(request, school):
            return Response({"ok": False, "error": "forbidden"}, status=403)

        data = request.body or b""
        rows, errors = verify_and_parse_bundle(data, expected_school_id=school.pk)
        if errors:
            return Response({"ok": False, "errors": errors}, status=400)

        # Bound the batch so a single sneakernet bundle can't open an unbounded
        # write transaction. Env-overridable; the online DeltaSyncAPI caps at 50.
        max_rows = int(getattr(settings, "RMC_SYNC_BUNDLE_MAX_ROWS", 500))
        if len(rows) > max_rows:
            return Response(
                {"ok": False, "errors": ["bundle_too_large"], "max_rows": max_rows},
                status=400,
            )

        out = apply_changes(str(school.id), request.user, rows, persist_conflicts=True)
        return Response(
            {
                "ok": True,
                "received": len(rows),
                "applied": out["success_count"],
                "conflicts": len(out["conflicts"]),
                "results": out["results"],
                "conflict_details": out["conflicts"],
            }
        )


__all__ = ["SyncBundleUploadView"]
