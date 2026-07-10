"""Wave E follow-up (Gap 3, 2026-05-15): data residency enforcement middleware.

For every request that resolves to a tenant, compares the tenant's
**regulatory** ``data_region`` (Wave E field on ``School``) with the
**operational** DB alias the request is routed to (existing
``regional_cluster`` + ``TenantDatabaseRouter``). When they disagree:

* Default mode: **soft-log** via ``apps.schools.data_residency.assert_aligned_or_log``.
  The request still completes — useful during region-replica rollouts
  when some tenants are mid-migration.

* Strict mode (``settings.DATA_RESIDENCY_ENFORCE = True``): raises
  ``CrossRegionWriteError`` from ``assert_aligned_or_log``, which
  bubbles up as a 500. The expectation is that strict mode is flipped
  AFTER ``verify_data_residency --fix-derive`` has been run and at
  least one region replica is provisioned. A tenant with NO operational
  binding is adjudicated against the declared default-store region
  (2026-07-09 unresolvable-region closeout) — that arm raises the typed
  ``ResidencyViolation`` (→ HTTP 403, audited).

This middleware never raises in default mode; telemetry must not break
production. Failures inside the alignment check itself are caught and
logged — EXCEPT under enforcement, where a crashed check fails CLOSED
(mirrors ``pdp_enforce`` and the router's fail-closed arm): a residency
decision we cannot compute is not permission.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class DataResidencyMiddleware:
    """Soft-log (or hard-raise) cross-region routing mismatches per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            school = getattr(request, "school", None)
            if school is not None:
                from apps.schools.data_residency import assert_aligned_or_log

                assert_aligned_or_log(school)
        except Exception as exc:  # noqa: BLE001 — swallow-only when NOT enforcing
            # `CrossRegionWriteError` is intentional in strict mode, and
            # `PermissionDenied` covers the typed ResidencyViolation from the
            # blank-binding arm — re-raise both so the block binds.
            from apps.schools.data_residency import CrossRegionWriteError

            if isinstance(exc, (CrossRegionWriteError, PermissionDenied)):
                raise
            from apps.compliance.cross_border_export import residency_enforced

            if residency_enforced():
                # Fail CLOSED: under enforcement a crashed residency check
                # must not silently admit the request.
                logger.error(
                    "data_residency check crashed under enforcement — denying",
                    exc_info=True,
                )
                raise PermissionDenied("Data residency decision unavailable") from exc
            logger.debug("data_residency_middleware swallow: %s", exc)
        return self.get_response(request)
