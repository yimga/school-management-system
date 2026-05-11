"""
Pass 14: public marketplace catalog endpoints.

`GET /api/v1/marketplace/apps/` returns every active first-party / third-party
MarketplaceApp so developer portals, in-product directories, and partner
marketing pages can render a consistent catalog without hitting Django admin.

`GET /api/v1/marketplace/scopes/` returns the OAuth2-style scope vocabulary
from apps.marketplace.scopes_catalog. Both endpoints are public — no auth —
and cacheable for 5 minutes.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


def _serialize_app(app) -> dict:
    """Public projection of a MarketplaceApp row — no internal fields."""
    manifest = app.manifest if isinstance(app.manifest, dict) else {}
    return {
        "slug": app.slug,
        "app_key": app.app_key,
        "name": app.name,
        "description": app.description or "",
        "kind": app.kind,
        "version": app.version,
        "publisher": getattr(getattr(app, "publisher", None), "name", None),
        "pricing": {
            "model": app.pricing_model,
            "price": str(app.price),
            "billing_interval": app.billing_interval,
            "is_intentionally_free": bool(app.is_intentionally_free),
        },
        "scopes_requested": list(manifest.get("scopes") or []),
        "events_consumed": list(manifest.get("events_consumed") or []),
        "events_emitted": list(manifest.get("events_emitted") or []),
        "widgets": list(manifest.get("widgets") or []),
        "required_apps": list(app.required_apps or []),
    }


@extend_schema(
    tags=["Marketplace"],
    summary="List active marketplace apps",
    description=(
        "Returns every active MarketplaceApp the platform exposes — first-party, "
        "premium, and certified third-party — with manifest projections suitable "
        "for in-product directories and developer-portal listings. Public, no auth. "
        "Cache-Control: 5 minutes."
    ),
    auth=[],
    responses={200: dict},
)
class MarketplaceAppsListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        try:
            from apps.marketplace.models import MarketplaceApp
        except ImportError:
            return Response({"apps": [], "count": 0})

        kind = (request.GET.get("kind") or "").strip().lower()
        qs = MarketplaceApp.objects.filter(is_active=True)
        if kind:
            qs = qs.filter(kind=kind)
        qs = qs.select_related("publisher").order_by("name")

        apps = [_serialize_app(app) for app in qs[:200]]
        response = Response(
            {
                "apps": apps,
                "count": len(apps),
                "doc_url": "https://docs.runmycampus.com/marketplace/",
            }
        )
        response["Cache-Control"] = "public, max-age=300"
        return response


@extend_schema(
    tags=["Marketplace"],
    summary="List OAuth2-style scopes a marketplace app can request",
    description=(
        "Returns the platform's scope vocabulary (resource:access pairs) with "
        "human-readable descriptions and audit sensitivity classes. Source of "
        "truth is apps/marketplace/scopes_catalog.py. Public, no auth."
    ),
    auth=[],
    responses={200: dict},
)
class MarketplaceScopesListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        try:
            from apps.marketplace.scopes_catalog import MARKETPLACE_SCOPES
        except ImportError:
            return Response({"scopes": [], "count": 0})

        scopes = [
            {"code": code, **details}
            for code, details in sorted(MARKETPLACE_SCOPES.items())
        ]
        response = Response(
            {
                "scopes": scopes,
                "count": len(scopes),
                "doc_url": "https://docs.runmycampus.com/marketplace/scopes/",
            }
        )
        response["Cache-Control"] = "public, max-age=300"
        return response
