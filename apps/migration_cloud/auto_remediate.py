"""Autonomous quarantine triage — dismiss safe holds and refresh inference before repair."""

from __future__ import annotations

import logging
from typing import Any

from .quarantine_resolution import (
    QUARANTINE_NO_ACTION_CLASSES,
    pending_quarantine_count,
    quarantine_queryset_for_bundle,
)

logger = logging.getLogger(__name__)


def auto_dismiss_informational(bundle, *, user=None) -> dict[str, Any]:
    """Dismiss rows that never needed operator action (deleted-in-source, duplicate)."""
    from apps.automation.quarantine_services import mark_repaired

    qs = quarantine_queryset_for_bundle(bundle, pending_only=True).filter(
        issue_class__in=QUARANTINE_NO_ACTION_CLASSES
    )
    dismissed = 0
    for rec in qs.iterator():
        mark_repaired(
            rec,
            {
                "auto_dismissed": True,
                "note": "Auto-dismissed — no import action required",
                "by": getattr(user, "pk", None),
            },
        )
        dismissed += 1
    return {"dismissed": dismissed}


def auto_remediate_before_repair(bundle, *, user=None) -> dict[str, Any]:
    """Run autonomous pre-repair steps: refresh domains, dismiss informational holds."""
    results: dict[str, Any] = {
        "inference_refreshed": False,
        "informational_dismissed": 0,
        "pending_before": pending_quarantine_count(bundle),
    }
    try:
        from .pipeline import refresh_bundle_inference

        refresh_bundle_inference(bundle_id=bundle.pk, use_accelerator=True)
        results["inference_refreshed"] = True
    except Exception:  # noqa: BLE001 — stale inference must not block repair
        logger.warning(
            "auto_remediate: inference refresh failed for bundle %s",
            bundle.pk,
            exc_info=True,
        )
    dismiss = auto_dismiss_informational(bundle, user=user)
    results["informational_dismissed"] = dismiss["dismissed"]
    results["pending_after"] = pending_quarantine_count(bundle)
    return results
