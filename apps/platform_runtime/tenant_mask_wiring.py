"""v4.00.36 Phase 3 — wire ``apply_regional_mask`` into tenant-facing surfaces.

Up to Phase 1, regional GDPR/CCPA masking lived in
``apps.platform_runtime.jit_operator_controller`` and was reached only
through the JIT operator view path. Tenant-facing DRF/API surfaces
returning student / parent / staff records were unmasked even when the
school's country was an EU/GDPR jurisdiction.

This module ships:

* ``RegionalMaskingMixin`` — a DRF view mixin that wraps ``Response.data``
  through ``apply_regional_mask`` using the tenant's ``country_code`` →
  region map. Drop on any list/detail view returning PII to opt in.

* ``mask_dict_for_school(record, school)`` — pure helper for callers
  outside DRF (Django views, templated reports, exports).

Region derivation rules (lowest cost first):

1. If ``school.data_region`` is set, use the first 2 chars uppercased
   (``"eu_central"`` → ``"EU"``).
2. Else lookup ``school.country_code`` in the EU member set → ``"EU"``;
   in the US states / territories set → ``"US"``; else ``None``.

When region is ``None`` no mask is applied (the existing ``apply_regional_mask``
contract returns the record unchanged).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.platform_runtime.jit_operator_controller import EU_GDPR_COUNTRIES

logger = logging.getLogger(__name__)


# Single source of truth, shared with the mask that consumes it. A second copy
# here is what let the two lists drift: this module knew all 27 member states
# while jit_operator_controller.apply_regional_mask recognised only six.
_EU_MEMBER_COUNTRIES: frozenset[str] = EU_GDPR_COUNTRIES

_US_COUNTRIES: frozenset[str] = frozenset({"US"})


def derive_region_for_school(school: Any) -> str | None:
    if school is None:
        return None
    data_region = (getattr(school, "data_region", "") or "").strip()
    if data_region:
        prefix = data_region[:2].upper()
        if prefix == "EU":
            return "EU"
        if prefix == "US":
            return "US"
    country_code = (getattr(school, "country_code", "") or "").strip().upper()
    if not country_code:
        return None
    if country_code in _EU_MEMBER_COUNTRIES:
        return "EU"
    if country_code in _US_COUNTRIES:
        return "US"
    return None


def mask_dict_for_school(record: Any, school: Any) -> Any:
    """Apply the regional mask to a single dict using the school's region."""
    if not isinstance(record, dict):
        return record
    region = derive_region_for_school(school)
    if region is None:
        return record
    try:
        from apps.platform_runtime.jit_operator_controller import apply_regional_mask

        return apply_regional_mask(record, region=region)
    except (ImportError, RuntimeError, AttributeError, ValueError) as exc:
        logger.debug("regional mask wire failed: %s", exc)
        return record


def mask_payload(payload: Any, school: Any) -> Any:
    """Recursively mask dicts inside ``payload`` (lists / DRF Response.data)."""
    if isinstance(payload, list):
        return [mask_payload(item, school) for item in payload]
    if isinstance(payload, dict):
        # DRF list responses wrap in {"results": [...]}; recurse so the
        # mask reaches each result entry.
        if "results" in payload and isinstance(payload["results"], list):
            out = dict(payload)
            out["results"] = [mask_payload(item, school) for item in payload["results"]]
            return out
        return mask_dict_for_school(payload, school)
    return payload


class RegionalMaskingMixin:
    """DRF mixin: mask ``Response.data`` using ``request.school`` region.

    Usage::

        class StudentListView(RegionalMaskingMixin, generics.ListAPIView):
            ...

    No effect when the request has no tenant-resolved ``request.school``
    or when the school's region is not EU/US (the mask is a no-op).
    """

    def finalize_response(self, request, response, *args, **kwargs):  # type: ignore[override]
        try:
            response = super().finalize_response(request, response, *args, **kwargs)  # type: ignore[misc]
        except (AttributeError, RuntimeError):
            return response
        try:
            school = getattr(request, "school", None) or getattr(
                getattr(request, "user", None), "school", None
            )
            if school is None or response is None:
                return response
            data = getattr(response, "data", None)
            if data is None:
                return response
            response.data = mask_payload(data, school)
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.debug("RegionalMaskingMixin finalize failed: %s", exc)
        return response


__all__ = [
    "derive_region_for_school",
    "mask_dict_for_school",
    "mask_payload",
    "RegionalMaskingMixin",
]
