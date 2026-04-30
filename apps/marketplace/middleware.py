"""
Attach ``request.app_api_key``, ``request.app_installation``, ``request.app_scope``
when the caller uses a tenant API key (``Authorization: Bearer sk_live_…``).
Session/OAuth requests leave ``app_api_key`` unset and ``app_scope`` as ``None``.
"""

from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from apps.apicenter.models import APIKey
from apps.marketplace.permissions_runtime import effective_scopes_for_api_key


class AppApiContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.app_api_key = None
        request.app_installation = None
        request.app_scope = None

        auth = request.META.get("HTTP_AUTHORIZATION") or ""
        if not auth.startswith("Bearer "):
            return None
        raw = auth[7:].strip()
        if not raw.startswith(APIKey.PREFIX):
            return None

        prefix_len = len(APIKey.PREFIX) + 8
        key_prefix = raw[:prefix_len]
        key = APIKey.verify(key_prefix, raw)
        if not key:
            return None

        school = getattr(request, "school", None)
        if key.school_id:
            if not school or str(key.school_id) != str(school.id):
                return None

        request.app_api_key = key
        request.app_installation = key.marketplace_installation
        request.app_scope = effective_scopes_for_api_key(key)
        return None
