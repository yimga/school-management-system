"""
Attach ``request.app_api_key``, ``request.app_installation``, ``request.app_scope``
when the caller uses:

- a tenant API key (``Authorization: Bearer sk_live_…``), or
- an OAuth2 access token from ``/api/v1/oauth/token`` (``Authorization: Bearer rmc_at_…``)
  when the ``DeveloperApplication`` is linked to a ``MarketplaceApp`` with an **active**
  installation on ``request.school``.

Session-only requests leave app fields unset.
"""

from __future__ import annotations

from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

from apps.apicenter.models import APIKey, OAuthTokenPair, _hash_secret
from apps.marketplace.models import AppInstallation
from apps.marketplace.permissions_runtime import (
    effective_scopes_for_api_key,
    effective_scopes_for_oauth_pair,
)

_OAUTH_ACCESS_PREFIX = "rmc_at_"


class AppApiContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.app_api_key = None
        request.app_installation = None
        request.app_scope = None
        request.oauth_access_pair = None

        auth = request.META.get("HTTP_AUTHORIZATION") or ""
        if not auth.startswith("Bearer "):
            return None
        raw = auth[7:].strip()

        # OAuth2 access token (developer platform install + tenant host)
        if raw.startswith(_OAUTH_ACCESS_PREFIX):
            now = timezone.now()
            h = _hash_secret(raw)
            pair = (
                OAuthTokenPair.objects.filter(
                    access_token_hash=h,
                    revoked_at__isnull=True,
                    access_expires_at__gt=now,
                )
                .select_related("application")
                .first()
            )
            if pair is None:
                return None
            application = pair.application
            school = getattr(request, "school", None)
            if (
                school is None
                or not application.marketplace_app_id
                or not application.is_active
            ):
                return None
            inst = AppInstallation.objects.filter(
                school=school,
                app_id=application.marketplace_app_id,
                status=AppInstallation.Status.ACTIVE,
            ).first()
            if inst is None:
                return None
            request.oauth_access_pair = pair
            request.app_installation = inst
            request.app_scope = effective_scopes_for_oauth_pair(pair, inst)
            return None

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
