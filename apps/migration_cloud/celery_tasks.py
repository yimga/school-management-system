"""Celery task wrappers for Migration Cloud long-running operations.

The wizard's HTTP view stays responsive: heavy work (`advance_bundle`
profile → classify → map, and `apply_bundle` write-fanout) hands off to
these tasks. Test runs use `CELERY_TASK_ALWAYS_EAGER = True` so the
synchronous path is also test-friendly.

Tasks never raise to the worker — failures are caught and written back
onto the bundle's `size_summary["error"]` so the UI can surface them.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.platform_runtime.workflow_tracker import track_workflow

logger = logging.getLogger("apps.migration_cloud.celery_tasks")


@shared_task(name="migration_cloud.advance_bundle", bind=True, ignore_result=False)
@track_workflow(
    "migration_bundle_advance",
    steps=("profile", "classify", "map"),
    expected_duration_seconds=900,  # magic-number-allow: workflow-expected-duration-seconds
    email_on_failure=True,
)
def advance_bundle_task(self, bundle_id: int, use_accelerator: bool = True) -> dict[str, Any]:
    """Run profile → classify → map on a bundle off the request thread."""
    from .models import BundleStatus, MigrationBundle
    from .pipeline import advance_bundle

    try:
        summary = advance_bundle(bundle_id=bundle_id, use_accelerator=use_accelerator)
        return {"ok": True, "bundle_id": bundle_id, **summary}
    except MigrationBundle.DoesNotExist:
        logger.warning("advance_bundle_task: bundle %s missing", bundle_id)
        return {"ok": False, "bundle_id": bundle_id, "error": "bundle_not_found"}
    except Exception as exc:  # noqa: BLE001 — never crash the worker
        logger.exception("advance_bundle_task: bundle %s failed", bundle_id)
        try:
            bundle = MigrationBundle.objects.get(pk=bundle_id)  # tenant-isolation-allow: PK lookup by internal task arg
            bundle.mark_status(
                BundleStatus.FAILED,
                summary_patch={
                    "error": f"{type(exc).__name__}: {exc}",
                    "stage": "advance_task",
                    "task_id": getattr(self.request, "id", None) if self else None,
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("advance_bundle_task: failure-state write also failed")
        return {"ok": False, "bundle_id": bundle_id, "error": str(exc)}


@shared_task(name="migration_cloud.apply_bundle", bind=True, ignore_result=False)
@track_workflow(
    "migration_bundle_apply",
    steps=("prepare", "apply_waves", "finalize"),
    expected_duration_seconds=1800,  # magic-number-allow: workflow-expected-duration-seconds
    email_on_failure=True,
)
def apply_bundle_task(self, bundle_id: int, dry_run: bool = True) -> dict[str, Any]:
    """Apply a MAPPED bundle to its tenant off the request thread."""
    from .models import MigrationBundle
    from .orchestrator import apply_bundle

    try:
        result = apply_bundle(bundle_id=bundle_id, dry_run=dry_run)
        return {
            "ok": True,
            "bundle_id": result.bundle_id,
            "dry_run": result.dry_run,
            "status": result.status,
            "totals": {
                "created": result.total_created,
                "updated": result.total_updated,
                "quarantined": result.total_quarantined,
            },
        }
    except MigrationBundle.DoesNotExist:
        logger.warning("apply_bundle_task: bundle %s missing", bundle_id)
        return {"ok": False, "bundle_id": bundle_id, "error": "bundle_not_found"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("apply_bundle_task: bundle %s failed", bundle_id)
        return {"ok": False, "bundle_id": bundle_id, "error": str(exc)}


def enqueue_advance(bundle_id: int, *, use_accelerator: bool = True):
    """Best-effort enqueue. Returns the AsyncResult, or None if Celery is
    unavailable; the caller should fall back to synchronous advance.

    A broker outage must not block intake — that would defeat the whole
    point of moving the work off-thread. We always have the synchronous
    pipeline.advance_bundle() as a fallback.
    """
    try:
        return advance_bundle_task.delay(bundle_id, use_accelerator)
    except Exception:  # noqa: BLE001 — broker outage / no worker pool
        logger.warning(
            "migration_cloud.celery_tasks: enqueue_advance failed; caller should fall back",
            exc_info=True,
        )
        return None


def enqueue_apply(bundle_id: int, *, dry_run: bool = True):
    """Best-effort enqueue for apply. Same fallback contract as enqueue_advance."""
    try:
        return apply_bundle_task.delay(bundle_id, dry_run)
    except Exception:  # noqa: BLE001
        logger.warning(
            "migration_cloud.celery_tasks: enqueue_apply failed; caller should fall back",
            exc_info=True,
        )
        return None


@shared_task(name="migration_cloud.fetch_assets", bind=True, ignore_result=False)
@track_workflow(
    "migration_bundle_fetch_assets",
    steps=("fetch",),
    expected_duration_seconds=600,  # magic-number-allow: workflow-expected-duration-seconds
)
def fetch_assets_task(self, bundle_id: int, max_batch: int = 100) -> dict[str, Any]:
    """Stream pending MigrationAsset rows to MEDIA_ROOT off the request thread."""
    from .asset_pipeline import fetch_pending_assets
    from .models import MigrationBundle

    try:
        summary = fetch_pending_assets(bundle_id=bundle_id, max_batch=max_batch)
        return {"ok": True, "bundle_id": bundle_id, **summary}
    except MigrationBundle.DoesNotExist:
        logger.warning("fetch_assets_task: bundle %s missing", bundle_id)
        return {"ok": False, "bundle_id": bundle_id, "error": "bundle_not_found"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("fetch_assets_task: bundle %s failed", bundle_id)
        return {"ok": False, "bundle_id": bundle_id, "error": str(exc)}


advance_bundle_task.rmc_workflow_explicit = True
apply_bundle_task.rmc_workflow_explicit = True
fetch_assets_task.rmc_workflow_explicit = True


def enqueue_fetch_assets(bundle_id: int, *, max_batch: int = 100):
    """Best-effort enqueue for asset fetching."""
    try:
        return fetch_assets_task.delay(bundle_id, max_batch)
    except Exception:  # noqa: BLE001
        logger.warning(
            "migration_cloud.celery_tasks: enqueue_fetch_assets failed; caller should fall back",
            exc_info=True,
        )
        return None
