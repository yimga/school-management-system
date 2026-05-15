"""
Pass 14.C: developer-facing app submission endpoint.

`POST /api/v1/marketplace/submissions/` accepts a minimal manifest from a
publisher and creates (or updates) a MarketplaceApp + MarketplaceListing in
DRAFT / PENDING_REVIEW status, ready for security review.

This is intentionally scoped — the full publisher dashboard (with screenshot
upload + version compat + revenue-share negotiation) lands in a separate
change. This endpoint exists so first-party teams can submit through CI
without needing the Django admin.

Auth: IsAuthenticated. The platform requires a verified PublisherOrganization
membership in production; this scaffold falls back to creating a personal
publisher record on the fly so first-party devs can iterate.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


_REQUIRED_FIELDS = ("slug", "name", "version")
_VALID_KINDS = {"first_party", "third_party", "premium", "tenant_private", "connector"}


def _validate_payload(data: dict) -> tuple[bool, dict]:
    missing = [f for f in _REQUIRED_FIELDS if not (data.get(f) or "").strip()]
    if missing:
        return False, {"missing_fields": missing}
    kind = (data.get("kind") or "first_party").strip().lower()
    if kind not in _VALID_KINDS:
        return False, {"invalid_kind": kind, "allowed": sorted(_VALID_KINDS)}
    manifest = data.get("manifest") or {}
    if not isinstance(manifest, dict):
        return False, {"invalid_manifest": "must be an object"}
    return True, {}


@extend_schema(
    tags=["Marketplace"],
    summary="Submit a draft marketplace app for review",
    description=(
        "Create or update a MarketplaceApp + MarketplaceListing. New apps land "
        "in DRAFT status; existing ones move to PENDING_REVIEW. Required body: "
        "{slug, name, version, kind?, manifest?, description?, "
        "preview_image_url?, screenshot_urls?}."
    ),
    request=dict,
    responses={201: dict, 400: dict},
)
class MarketplaceSubmissionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        ok, errors = _validate_payload(data)
        if not ok:
            return Response(
                {"detail": "validation failed", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from apps.marketplace.services import upsert_marketplace_submission
        except ImportError:
            return Response(
                {"detail": "marketplace app unavailable"}, status=503
            )

        result = upsert_marketplace_submission(user=request.user, payload=data)
        return Response(
            result,
            status=(
                status.HTTP_201_CREATED
                if result["created_app"]
                else status.HTTP_200_OK
            ),
        )
