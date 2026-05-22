"""Unified readiness score.

Two scoring systems live side-by-side in the platform:
- SchoolOnboardingProgress.progress_percent (operator-driven checklist)
- SetupProgress.health_score (data-driven multi-dimension)

This module merges them into a single 0-100 readiness score with
sub-score breakdown so the UI can show "you're 73% to launch" instead
of two competing numbers.

Public API:
    compute_unified_score(school) -> UnifiedReadiness
    maybe_record_launch_ready_stage(school) -> bool

When `unified_score >= 90` AND `launch_ready` is true on SetupProgress,
this module records lifecycle stage ONBOARDING_LAUNCH_READY exactly
once (idempotent — re-running doesn't duplicate).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .models import SchoolLifecycleStage
from .services import current_stage, record_stage

logger = logging.getLogger(__name__)


# Weight schedule. checklist_weight + health_weight must sum to 1.0.
# Checklist is operator intent (they marked things done); health is
# data-driven (do the actual records exist). Weight slightly toward
# health because operators sometimes mark things done prematurely.
_CHECKLIST_WEIGHT = 0.4
_HEALTH_WEIGHT = 0.6

LAUNCH_READY_THRESHOLD = 90


@dataclass
class UnifiedReadiness:
    school_id: str
    unified_score: int  # 0-100
    checklist_percent: int
    health_score: int
    launch_ready: bool
    launch_blockers: list
    band: str  # "not-started" / "in-progress" / "near-launch" / "launch-ready"

    def to_dict(self) -> dict:
        return {
            "school_id": self.school_id,
            "unified_score": self.unified_score,
            "checklist_percent": self.checklist_percent,
            "health_score": self.health_score,
            "launch_ready": self.launch_ready,
            "launch_blockers": list(self.launch_blockers or [])[:8],
            "band": self.band,
        }


def _band_for(score: int, launch_ready: bool) -> str:
    if launch_ready and score >= LAUNCH_READY_THRESHOLD:
        return "launch-ready"
    if score >= 70:
        return "near-launch"
    if score >= 20:
        return "in-progress"
    return "not-started"


def _safe_get_checklist_percent(school) -> int:
    try:
        from apps.platform_runtime.models import SchoolOnboardingProgress

        row = SchoolOnboardingProgress.objects.filter(school=school).only(
            "progress_percent"
        ).first()
        if row is None:
            return 0
        return max(0, min(100, int(row.progress_percent or 0)))
    except Exception:  # noqa: BLE001
        return 0


def _safe_get_setup_progress(school):
    try:
        from apps.setup_studio.models import SetupProgress

        return SetupProgress.objects.filter(school=school).first()
    except Exception:  # noqa: BLE001
        return None


def compute_unified_score(school) -> Optional[UnifiedReadiness]:
    """Return a unified readiness snapshot, or None for unknown school."""
    if not school or not getattr(school, "id", None):
        return None
    checklist_percent = _safe_get_checklist_percent(school)
    setup = _safe_get_setup_progress(school)
    health_score = int(getattr(setup, "health_score", 0) or 0)
    launch_ready = bool(getattr(setup, "launch_ready", False))
    blockers = list(getattr(setup, "launch_blockers", []) or [])
    weighted = (checklist_percent * _CHECKLIST_WEIGHT) + (health_score * _HEALTH_WEIGHT)
    unified = max(0, min(100, int(round(weighted))))
    return UnifiedReadiness(
        school_id=str(school.id),
        unified_score=unified,
        checklist_percent=checklist_percent,
        health_score=health_score,
        launch_ready=launch_ready,
        launch_blockers=blockers,
        band=_band_for(unified, launch_ready),
    )


def maybe_record_launch_ready_stage(school) -> bool:
    """Record ONBOARDING_LAUNCH_READY iff threshold met AND not already recorded.

    Returns True if a new stage row was written, False otherwise.
    Idempotent — call freely from cron or post-save handlers.
    """
    snapshot = compute_unified_score(school)
    if snapshot is None:
        return False
    if not snapshot.launch_ready:
        return False
    if snapshot.unified_score < LAUNCH_READY_THRESHOLD:
        return False
    # Idempotency: only record if the most recent LAUNCH_READY-or-later
    # stage isn't already on the timeline.
    already = SchoolLifecycleStage.objects.filter(
        school=school,
        stage=SchoolLifecycleStage.Stage.ONBOARDING_LAUNCH_READY,
    ).exists()
    if already:
        return False
    record_stage(
        school,
        SchoolLifecycleStage.Stage.ONBOARDING_LAUNCH_READY,
        note=f"unified score {snapshot.unified_score}",
        payload={
            "source": "readiness.maybe_record_launch_ready_stage",
            "unified_score": snapshot.unified_score,
            "checklist_percent": snapshot.checklist_percent,
            "health_score": snapshot.health_score,
        },
    )
    return True


def needs_concierge(school) -> bool:
    """Should we show the first-login concierge for this school?

    Returns True when:
    - The school is not yet LAUNCH_READY
    - Unified score is < 50% (concierge is for early-onboarding schools)
    - The school is not in an OFFBOARDING / FAILED stage

    Best-effort: returns False on any exception so we never block the
    portal from rendering.
    """
    try:
        snapshot = compute_unified_score(school)
        if snapshot is None:
            return False
        if snapshot.band == "launch-ready":
            return False
        if snapshot.unified_score >= 50:
            return False
        latest = current_stage(school)
        if latest and latest.startswith("OFFBOARDING"):
            return False
        if latest == SchoolLifecycleStage.Stage.FAILED:
            return False
        return True
    except Exception:  # noqa: BLE001
        return False
