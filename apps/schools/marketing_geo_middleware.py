"""
Isomorphic optimization layer — geo_context on public marketing hosts.

Wraps ``build_geo_context`` (country resolution + localization) so views,
template tags, and APIs read ``request.geo_context`` before render without a
separate glocal_kernel app.
"""

from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from apps.schools.host_routing import is_public_host
from apps.schools.marketing_geo_context import build_geo_context


class RunMyCampusGeoMiddleware(MiddlewareMixin):
    """Attach ``request.geo_context`` on runmycampus.com / public marketing hosts."""

    def process_request(self, request):
        host = (request.get_host() or "").split(":")[0].lower()
        if not is_public_host(host):
            return None
        geo = build_geo_context(request)
        request.geo_context = geo  # type: ignore[attr-defined]
        return None
