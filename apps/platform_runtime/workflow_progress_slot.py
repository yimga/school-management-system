"""Workflow Progress Bus — assist-dock chip registration (v4.00.96)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_workflow_progress_assist_dock_slot() -> None:
    """Register the floating chip on portal + manager + admin surfaces.

    Idempotent — re-registers cleanly on every AppConfig.ready (e.g. during tests).
    """

    try:
        from apps.assist_dock.registry import (
            SOURCE_REGISTRY,
            SURFACE_ADMIN,
            SURFACE_MANAGER,
            SURFACE_PORTAL,
            AssistDockSlot,
            register_slot,
        )
    except Exception:
        logger.debug("assist_dock registry not importable; workflow chip skipped", exc_info=True)
        return

    register_slot(
        AssistDockSlot(
            id="workflow-progress",
            label="Workflow",
            icon="bi-hourglass-split",
            surfaces=frozenset({SURFACE_PORTAL, SURFACE_MANAGER, SURFACE_ADMIN}),
            roles=frozenset({"*"}),
            source=SOURCE_REGISTRY,
            badge_source="workflow_progress_badge",
            shortcut="g w",
            aria_keyshortcuts="g w",
            pinned_default=True,
            order=45,
            description="Live workflow progress + AI-suggested fixes when something gets stuck.",
        )
    )
