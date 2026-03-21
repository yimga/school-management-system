"""
Runtime resolution tracing (GAP.5 / PATH_TO_100 III.5).

Provides a request-scoped trace id for resolver resolution so logs and future
observability can correlate get_effective_site_settings / build_tenant_runtime
with downstream work. Set at entry to resolution; include in structured_logging
via request_context_for_log.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

RUNTIME_TRACE_ID_ATTR = "_runtime_trace_id"


def _trace_id_from_request(request: Any) -> Optional[str]:
    """Read trace id from request.__dict__ only (avoids Mock.__getattr__ returning a Mock)."""
    d = getattr(request, "__dict__", None)
    if not isinstance(d, dict):
        return None
    val = d.get(RUNTIME_TRACE_ID_ATTR)
    return val if isinstance(val, str) and val else None


def set_runtime_trace_context(request: Any) -> str:
    """
    Set a trace id on the request for this resolution path (if not already set).
    Returns the trace id (e.g. for logging).
    """
    if request is None:
        return ""
    existing = _trace_id_from_request(request)
    if existing:
        return existing
    trace_id = secrets.token_hex(8)
    setattr(request, RUNTIME_TRACE_ID_ATTR, trace_id)
    return trace_id


def get_runtime_trace_id(request: Any) -> Optional[str]:
    """Return the current runtime trace id on the request, or None."""
    if request is None:
        return None
    return _trace_id_from_request(request)
