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


def _ensure_publisher(user):
    from apps.marketplace.models import PublisherOrganization

    publisher = (
        PublisherOrganization.objects.filter(verified_contact_email=user.email).first()
        if user.email
        else None
    )
    if publisher is not None:
        return publisher
    return PublisherOrganization.objects.create(
        name=f"{user.username}'s apps",
        verified_contact_email=user.email or "",
    )


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
            from apps.marketplace.models import (
                MarketplaceApp,
                MarketplaceListing,
            )
        except ImportError:
            return Response(
                {"detail": "marketplace app unavailable"}, status=503
            )

        publisher = _ensure_publisher(request.user)
        slug = data["slug"].strip().lower()
        kind = (data.get("kind") or "first_party").strip().lower()
        manifest = data.get("manifest") or {}

        app, app_created = MarketplaceApp.objects.update_or_create(
            slug=slug,
            defaults={
                "app_key": slug,
                "publisher": publisher,
                "name": data["name"].strip()[:255],
                "description": (data.get("description") or "").strip(),
                "kind": kind,
                "version": data["version"].strip()[:32],
                "manifest": manifest,
                "is_active": True,
            },
        )

        listing, listing_created = MarketplaceListing.objects.update_or_create(
            app=app,
            defaults={
                "publisher": publisher,
                "category": (data.get("category") or "").strip()[:80],
                "short_description": (data.get("short_description") or "").strip()[:255],
                "preview_image_url": (data.get("preview_image_url") or "").strip()[:500],
                "screenshot_urls": list(data.get("screenshot_urls") or [])[:10],
                "status": MarketplaceListing.Status.PENDING_REVIEW
                if not app_created
                else MarketplaceListing.Status.DRAFT,
                "security_review_status": MarketplaceListing.ReviewStatus.PENDING,
            },
        )

        return Response(
            {
                "app_slug": app.slug,
                "app_id": app.pk,
                "listing_id": listing.pk,
                "status": listing.status,
                "created_app": app_created,
                "created_listing": listing_created,
                "next_steps_url": "https://docs.runmycampus.com/marketplace/submission/",
            },
            status=status.HTTP_201_CREATED if app_created else status.HTTP_200_OK,
        )
