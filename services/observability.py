"""Services-layer observability bridge (v3.39.0 Agent 4).

Thin re-export shim for ``apps.observability.metrics`` so callers
that follow the ``services.*`` import convention (notably
v3.38.0 Agent 4's ``apps.migration_cloud.metrics._resolve_backend``
introspection) resolve to the same backend dispatch as
``from apps.observability import emit_counter``.

Sentry SDK access remains fenced inside ``apps/observability/``
per the architectural boundary documented in CLAUDE.md and
enforced by ``scripts/scan_sentry_boundary.py`` — this module
imports only the prometheus / statsd / structured-log shim,
never sentry_sdk directly.
"""
from __future__ import annotations

from apps.observability.metrics import (
    emit_counter,
    emit_gauge,
    emit_histogram,
)

__all__ = ["emit_counter", "emit_gauge", "emit_histogram"]
