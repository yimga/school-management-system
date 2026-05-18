"""Public Redoc / OpenAPI schema mounts for the Migration Cloud REST API.

Two views:

  * :data:`schema_view`  — :class:`SpectacularAPIView` serving the raw
    OpenAPI YAML at ``/api/v1/schema/``.
  * :data:`redoc_view`   — :class:`SpectacularRedocView` serving the
    Redoc HTML UI at ``/api/v1/docs/``.

Both views are subclassed locally so we can attach ``@extend_schema``
metadata and disable auth-only access (the schema is public — partners
need to read it before they have a token). The Redoc page pulls the
Redoc CDN bundle with a pinned-version + SRI marker via the existing
``sri-allow`` infrastructure.
"""

from __future__ import annotations

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
)
from rest_framework.permissions import AllowAny


class MigrationCloudSchemaView(SpectacularAPIView):
    """Raw OpenAPI YAML for the Migration Cloud REST API.

    Public-readable — the schema documents the contract, not secrets.
    Authentication is still required for any *call* against the surface.
    """

    permission_classes = [AllowAny]
    serve_public = True


class MigrationCloudRedocView(SpectacularRedocView):
    """Redoc HTML UI for the Migration Cloud REST API.

    The Redoc bundle is loaded from jsDelivr at a pinned version; the
    ``<!-- sri-allow: redoc-standalone-cdn-pinned -->`` marker pattern
    is already on the project's allowlist (see CLAUDE.md scanner row
    for ``scan_sri_required``).

    Both mounts (super + portal) share this view class, so we resolve
    the schema URL from the matched request's own namespace at runtime
    rather than baking a fixed ``url_name`` at class declaration time.
    """

    permission_classes = [AllowAny]
    serve_public = True

    def _get_schema_url(self, request) -> str:
        """Return the absolute path of the schema view for THIS request's mount."""
        from django.urls import reverse

        resolver = getattr(request, "resolver_match", None)
        ns = resolver.namespace if resolver else None
        if ns:
            try:
                return reverse(f"{ns}:migration-cloud-schema")
            except Exception:
                pass
        # Fallback — relative sibling URL works because Redoc is mounted
        # next to schema/ under the same prefix.
        return "../schema/"
