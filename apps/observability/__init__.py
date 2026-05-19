"""Observability package — Sentry SDK fence + metrics bridge.

Public re-exports for ergonomic imports from app code:

* ``emit_counter`` / ``emit_gauge`` / ``emit_histogram`` — metrics
  dispatch (v3.39.0 Agent 4; backed by ``apps.observability.metrics``).

Sentry SDK helpers live in ``apps.observability.tracing`` and are
imported directly from there to keep this package's import cost
cheap (so Migration Cloud's hot path doesn't pay the sentry_sdk
import on first metric emission).
"""
from apps.observability.metrics import (
    emit_counter,
    emit_gauge,
    emit_histogram,
)

__all__ = ["emit_counter", "emit_gauge", "emit_histogram"]
