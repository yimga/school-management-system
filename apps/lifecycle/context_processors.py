"""Lifecycle context processors.

Injects `lifecycle_readiness` + `lifecycle_concierge_enabled` into every
template context so the portal_base concierge modal can decide whether
to render itself, and any dashboard widget can show the unified score.

NEVER bleeds onto manager / operator surfaces — the context processor
checks `request.public_host_kind` and returns an empty dict for
non-tenant hosts.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def lifecycle_readiness(request):
    """Return {'lifecycle_readiness': UnifiedReadiness-as-dict, 'lifecycle_concierge_enabled': bool}.

    Safe to call from any view — silent failure returns empty dict.
    """
    try:
        # Skip manager / operator hosts — they don't render the tenant
        # concierge modal and shouldn't pay the DB cost.
        host_kind = getattr(request, "public_host_kind", None) or ""
        if host_kind == "manager":
            return {}
        school = _resolve_school(request)
        if school is None:
            return {}
        from .readiness import compute_unified_score, needs_concierge

        readiness = compute_unified_score(school)
        if readiness is None:
            return {}
        return {
            "lifecycle_readiness": readiness.to_dict(),
            "lifecycle_concierge_enabled": needs_concierge(school),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle.context_processor.failed err=%s",
            type(exc).__name__,
        )
        return {}


def _resolve_school(request):
    school = (
        getattr(request, "school", None)
        or getattr(request, "tenant_school", None)
        or getattr(request, "tenant", None)
    )
    if school and hasattr(school, "id"):
        return school
    return None
