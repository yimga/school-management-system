"""v4.00.36 Phase 3 — regional-mask primitives for non-JIT callers.

STATUS (audited 2026-08-23): nothing outside this app's tests imports any name
below. Read that as "an available primitive", NOT as "a protection in force" —
an earlier version of this docstring claimed the latter, and the passing
contract tests below made the claim look sealed.

It is deliberately not wired to tenant-facing DRF views, despite the module's
original framing. ``apply_regional_mask`` redacts ``first_name`` /
``last_name`` / ``full_name`` / ``email`` / ``phone``, so dropping
``RegionalMaskingMixin`` on a tenant's own student or staff API would hide a
German school's pupils from that school's own registrar. GDPR constrains what
the PLATFORM may see of a tenant's people, not what the school may see of its
own; that boundary is enforced on the operator path, which composes the same
mask through ``jit_operator_controller.compose_operator_view`` (see
``views_operator_tenant_inspect.py``).

Use these helpers when a NEW surface exposes one tenant's person records to a
party outside that tenant — an operator console, a cross-tenant export, a
support tool. ``RegionalMaskingMixin.finalize_response`` only rewrites
``Response.data``, so a plain Django ``JsonResponse`` endpoint must call
``mask_dict_for_school`` itself.

This module ships:

* ``RegionalMaskingMixin`` — a DRF view mixin that wraps ``Response.data``
  through ``apply_regional_mask`` using the tenant's ``country_code`` →
  region map. Opt a CROSS-TENANT view in; never a tenant's own.

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

        class OperatorStudentSampleView(RegionalMaskingMixin, generics.ListAPIView):
            ...

    For a CROSS-TENANT reader only — see the module docstring. A tenant's own
    roster API must not carry this mixin or the school loses sight of its own
    pupils.

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
