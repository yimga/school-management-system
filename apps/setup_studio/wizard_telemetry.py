"""Wizard telemetry — thin wrappers over ``apps.observability.metrics``.

All label values pass through the metrics backend's ``_sanitize_labels``
contract, so PII bleed is structurally impossible at the boundary.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "emit_step_viewed",
    "emit_step_applied",
    "emit_step_validation_failed",
    "emit_wizard_completed",
    "emit_wizard_abandoned",
    "emit_ai_smart_defaults_outcome",
    "emit_ai_branch_rationale_outcome",
    "emit_ai_translate_mesh_outcome",
    "emit_persistence_failed",
    "emit_gate_blocked",
    "emit_state_cache_event",
]


def _safe_emit_counter(name: str, labels: dict[str, Any], value: int = 1) -> None:
    try:
        from apps.observability.metrics import emit_counter
        emit_counter(name=name, labels=labels, value=value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("wizard_telemetry: counter emission skipped (%s): %s", name, exc)


def _safe_emit_histogram(name: str, labels: dict[str, Any], value: float) -> None:
    try:
        from apps.observability.metrics import emit_histogram
        emit_histogram(name=name, labels=labels, value=value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("wizard_telemetry: histogram emission skipped (%s): %s", name, exc)


def emit_step_viewed(wizard_key: str, step_key: str, audience: str) -> None:
    _safe_emit_counter(
        "wizard.step.viewed",
        {"wizard_key": wizard_key, "step_key": step_key, "audience": audience},
    )


def emit_step_applied(wizard_key: str, step_key: str, audience: str, outcome: str = "success") -> None:
    _safe_emit_counter(
        "wizard.step.applied",
        {"wizard_key": wizard_key, "step_key": step_key, "audience": audience, "outcome": outcome},
    )


def emit_step_validation_failed(wizard_key: str, step_key: str, field_name: str) -> None:
    _safe_emit_counter(
        "wizard.step.validation_failed",
        {"wizard_key": wizard_key, "step_key": step_key, "field_name": field_name},
    )


def emit_wizard_completed(wizard_key: str, audience: str, duration_seconds: int) -> None:
    _safe_emit_counter("wizard.completed", {"wizard_key": wizard_key, "audience": audience})
    _safe_emit_histogram(
        "wizard.duration_seconds",
        {"wizard_key": wizard_key, "audience": audience},
        float(duration_seconds),
    )


def emit_wizard_abandoned(wizard_key: str, last_step_key: str, audience: str) -> None:
    _safe_emit_counter(
        "wizard.abandoned",
        {"wizard_key": wizard_key, "last_step_key": last_step_key, "audience": audience},
    )


def emit_ai_smart_defaults_outcome(
    wizard_key: str, step_key: str, outcome: str, latency_ms: int,
) -> None:
    _safe_emit_counter(
        f"wizard.ai.smart_defaults.{outcome}",
        {"wizard_key": wizard_key, "step_key": step_key},
    )
    _safe_emit_histogram(
        "wizard.ai.smart_defaults.latency_ms",
        {"wizard_key": wizard_key, "step_key": step_key, "outcome": outcome},
        float(latency_ms),
    )


def emit_ai_branch_rationale_outcome(
    wizard_key: str, step_key: str, outcome: str, latency_ms: int,
) -> None:
    _safe_emit_counter(
        f"wizard.ai.branch_rationale.{outcome}",
        {"wizard_key": wizard_key, "step_key": step_key},
    )
    _safe_emit_histogram(
        "wizard.ai.branch_rationale.latency_ms",
        {"wizard_key": wizard_key, "step_key": step_key, "outcome": outcome},
        float(latency_ms),
    )


def emit_ai_translate_mesh_outcome(
    wizard_key: str, source_locale: str, target_locale: str, outcome: str,
) -> None:
    _safe_emit_counter(
        f"wizard.ai.translate_mesh.{outcome}",
        {"wizard_key": wizard_key, "source_locale": source_locale, "target_locale": target_locale},
    )


def emit_persistence_failed(wizard_key: str, step_key: str, target: str) -> None:
    _safe_emit_counter(
        "wizard.persistence.failed",
        {"wizard_key": wizard_key, "step_key": step_key, "target": target},
    )


def emit_gate_blocked(wizard_key: str, reason: str) -> None:
    _safe_emit_counter("wizard.gate.blocked", {"wizard_key": wizard_key, "reason": reason})


def emit_state_cache_event(wizard_key: str, event: str) -> None:
    """event ∈ {'quota_exceeded', 'schema_mismatch', 'restored', 'cleared'}"""
    _safe_emit_counter(f"wizard.cache.{event}", {"wizard_key": wizard_key})
