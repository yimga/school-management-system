"""Set per-request regional DB alias when ENABLE_MULTI_REGION (batch 1535).

Border-lock (metric #27): when ``settings.DATA_RESIDENCY_ENFORCE`` is on, this
middleware no longer merely *prefers* an in-region alias — it **blocks** a
request that arrives already pinned (via a thread-local override) to a store
whose region contradicts the resolved tenant's regulatory ``data_region``,
raising the typed
:class:`apps.compliance.cross_border_export.ResidencyViolation` (a
``PermissionDenied`` → HTTP 403, audited). When the flag is off the behaviour
is unchanged (prefer-an-alias, never block).

Why check the *pre-existing* override (not the alias we derive): the alias we
resolve from the school is by construction in the school's own region, so it can
never be cross-region. The genuine border-crossing case is when an upstream
layer (a prior request leak, an operator forcing a foreign alias) has already
pinned a foreign region before this middleware runs — that is what we refuse.
The router (``apps.siteconfig.db_router``) is the defence-in-depth choke point
for every ORM op; this is the early request-time block.

HONEST SCOPE: this is an *application-layer* control — it fails the request
closed rather than serving a tenant's PII from out-of-region. True physical
per-region storage replicas (the ``DATABASES`` aliases) remain an ops / deploy
item; this layer is the binding guarantee until those replicas exist.
"""

from __future__ import annotations

from django.conf import settings

from apps.platform_runtime.dynamic_db_routing import (
    clear_request_db_alias,
    get_request_db_alias,
    resolve_school_db_alias,
    set_request_db_alias,
)


class RegionalDatabaseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "ENABLE_MULTI_REGION", False):
            return self.get_response(request)
        school = getattr(request, "school", None)
        if school is not None:
            # Border-lock: if the request already arrived pinned to a region
            # that contradicts this tenant's regulatory region, block before
            # serving. No-op when DATA_RESIDENCY_ENFORCE is off, when nothing
            # is pre-pinned, or when the regions match.
            self._enforce_inbound_residency(school)
        alias = resolve_school_db_alias(school) if school is not None else None
        if alias:
            set_request_db_alias(alias)
        try:
            return self.get_response(request)
        finally:
            clear_request_db_alias()

    @staticmethod
    def _enforce_inbound_residency(school) -> None:
        """Raise ResidencyViolation when a pre-pinned override is out-of-region.

        Import lazily so the middleware has no import-time dependency on the
        compliance app. ``enforce_region_match`` is itself a no-op when strict
        enforcement is off or when ``inbound`` is empty.
        """
        inbound = get_request_db_alias()
        if not inbound:
            return
        from apps.compliance.cross_border_export import enforce_region_match

        enforce_region_match(school, inbound, kind="db_route")
