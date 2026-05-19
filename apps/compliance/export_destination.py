"""Resolve operator export destination region for cross-border gates."""

from __future__ import annotations

from typing import Any


def resolve_export_destination_region(
    *,
    school: Any = None,
    request: Any = None,
    params: dict | None = None,
) -> str:
    """
    Precedence: explicit param → tenant_runtime.export_restrictions →
    request.data_region → school.data_region.
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

    if school is not None:
        school_region = getattr(school, "data_region", None)
        if school_region:
            return str(school_region).strip().lower()

    return ""
