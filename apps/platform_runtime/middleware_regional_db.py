"""Set per-request regional DB alias when ENABLE_MULTI_REGION (batch 1535).

Border-lock (metric #27): when ``settings.DATA_RESIDENCY_ENFORCE`` is on, this
middleware no longer merely *prefers* an in-region alias — it **blocks** a
request that arrives already pinned (via a thread-local override) to a store
whose region contradicts the resolved tenant's regulatory ``data_region``,
raising the typed
:class:`apps.compliance.cross_border_export.ResidencyViolation` (a
``PermissionDenied`` → HTTP 403, audited). When the flag is off the behaviour
is unchanged (prefer-an-alias, never block).

**Wave 15 (2026-07-18):** residency enforcement is **decoupled** from
``ENABLE_MULTI_REGION``. Alias pinning still requires multi-region + real
``DATABASES`` aliases; inbound / default-store adjudication still runs when
``DATA_RESIDENCY_ENFORCE`` is on so sovereignty is not dead behind the
routing scaffold.

Why check the *pre-existing* override (not the alias we derive): the alias we
resolve from the school is by construction in the school's own region, so it can
never be cross-region. The genuine border-crossing case is when an upstream
layer (a prior request leak, an operator forcing a foreign alias) has already
pinned a foreign region before this middleware runs — that is what we refuse.
The router (``apps.siteconfig.db_router``) is the defence-in-depth choke point
for every ORM op; this is the early request-time block.

Unresolvable-region closeout (2026-07-09): when NO alias resolves for the
tenant (or multi-region is off), the request is about to be served from the
DEFAULT store. That is no longer a silent early-return — the tenant's region
is adjudicated against the declared default-store region
(``apps.schools.data_residency.default_store_region``), so a tenant with a
foreign residency promise is refused up front instead of only per-op at the
router. No-op when enforcement is off.

HONEST SCOPE: this is an *application-layer* control — it fails the request
closed rather than serving a tenant's PII from out-of-region. True physical
per-region storage replicas (the ``DATABASES`` aliases) remain an ops / deploy
item; this layer is the binding guarantee until those replicas exist.
Do **not** flip ``ENABLE_MULTI_REGION`` in prod without real aliases.
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
        school = getattr(request, "school", None)
        multi = bool(getattr(settings, "ENABLE_MULTI_REGION", False))

        if school is not None:
            # Border-lock always (enforce_region_match no-ops when flag off).
            self._enforce_inbound_residency(school)

        if not multi:
            # Alias routing stays inert; default-store landing still adjudicated.
            if school is not None:
                self._enforce_unresolved_region(school)
            return self.get_response(request)

        alias = resolve_school_db_alias(school) if school is not None else None
        if alias:
            set_request_db_alias(alias)
        elif school is not None:
            self._enforce_unresolved_region(school)
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
        from apps.schools.data_residency import region_for_alias

        enforce_region_match(school, region_for_alias(inbound), kind="db_route")

    @staticmethod
    def _enforce_unresolved_region(school) -> None:
        """Raise ResidencyViolation when the default-store landing is foreign.

        The request-time twin of the router's per-op unresolvable-region
        check: compares the tenant's effective region against the DECLARED
        default-store region. ``enforce_region_match`` no-ops when enforcement
        is off, so the flag-off posture is unchanged.
        """
        from apps.compliance.cross_border_export import enforce_region_match
        from apps.schools.data_residency import default_store_region

        enforce_region_match(school, default_store_region(), kind="db_route")
