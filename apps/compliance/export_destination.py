"""Resolve operator export destination region for cross-border gates."""

from __future__ import annotations

from typing import Any


def resolve_export_destination_region(
    *,
    request: Any = None,
    params: dict | None = None,
) -> str:
    """Where the export is going, or ``""`` when that is not knowable.

    Precedence: explicit param → tenant_runtime.export_restrictions →
    request.data_region.

    Takes no ``school`` ON PURPOSE. It used to, and fell back to that school's
    own ``data_region`` -- answering "the destination is wherever the data
    already is". That made every cross-border check a comparison of a region to
    ITSELF, structurally unable to block, and it simultaneously made the gate's
    ``if not dest`` branch (which exists for exactly this case) unreachable,
    because ``dest`` was never empty. The source region is not evidence about
    the destination, so this resolver cannot see it.

    ``""`` means unknown, and what to do about an unknown destination is the
    gate's decision, not this resolver's: ``cross_border_export_blocked``
    consults ``strict_unknown_regions()``, which defaults to the
    backward-compatible posture of letting it pass.
    """
    params = params or {}
    explicit = (params.get("destination_region") or params.get("dest_region") or "").strip()
    if explicit:
        return explicit.lower()

    if request is not None:
        runtime = getattr(request, "tenant_runtime", None)
        if runtime is not None:
            compliance = getattr(runtime, "compliance", None)
            if compliance is not None:
                restrictions = getattr(compliance, "export_restrictions", None) or {}
                if isinstance(restrictions, dict):
                    dest = (
                        restrictions.get("destination_region")
                        or restrictions.get("active_region")
                        or ""
                    )
                    if dest:
                        return str(dest).strip().lower()

        req_region = getattr(request, "data_region", None) or getattr(
            request, "active_data_region", None
        )
        if req_region:
            return str(req_region).strip().lower()

    return ""
