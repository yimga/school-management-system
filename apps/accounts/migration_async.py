"""
Pass 8.B: async Celery wrapper for the Migration Wizard.

The synchronous run path in apps.accounts.views_migration is fine for small
imports, but PowerSchool / Veracross exports routinely have thousands of rows
that time out the web request. This module adds:

  - `enqueue_migration_run(school, migration_type, rows, actor)` — fire-and-forget
    Celery task that runs the importer through `migration_importers.run_importer`,
    stores progress in cache under a job_id, and persists final counts.
  - `get_migration_job_status(job_id)` — returns the current snapshot so the
    polling endpoint can drive a progress bar.
  - HTTP polling endpoint `/api/v1/migration-jobs/<job_id>/` (added in
    apps.api.urls_v1) returns the same snapshot as JSON.

When Celery is unavailable (no REDIS_URL, dev mode), the task falls back to
in-process execution so the wizard works in every environment.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key prefix; value is a snapshot dict — see _snapshot().
KEY_PREFIX = "migration_job:"
TTL_SECONDS = 24 * 60 * 60  # 24h


def _key(job_id: str) -> str:
    return f"{KEY_PREFIX}{job_id}"


def _snapshot(
    *,
    job_id: str,
    status: str,
    migration_type: str,
    row_count: int,
    processed: int = 0,
    created: int = 0,
    updated: int = 0,
    skipped: int = 0,
    error_count: int = 0,
    errors: list[str] | None = None,
    school_id: str = "",
    actor_id: int | None = None,
    started_at: str = "",
    finished_at: str = "",
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": status,
        "migration_type": migration_type,
        "row_count": int(row_count),
        "processed": int(processed),
        "created": int(created),
        "updated": int(updated),
        "skipped": int(skipped),
        "error_count": int(error_count),
        "errors": (errors or [])[:50],
        "school_id": school_id,
        "actor_id": actor_id,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def get_migration_job_status(job_id: str) -> dict[str, Any] | None:
    """Read-only snapshot lookup. Returns None when job_id is unknown."""
    if not job_id:
        return None
    try:
        return cache.get(_key(job_id))
    except Exception:  # noqa: BLE001 - cache failures shouldn't 500 the poll endpoint
        return None


def _run_import_inline(
    *, job_id: str, school, migration_type: str, rows: list[dict], actor=None
) -> dict[str, Any]:
    """Inline (non-Celery) execution path used in dev or as a Celery task body."""
    from django.utils import timezone

    started = timezone.now().isoformat()
    snap = _snapshot(
        job_id=job_id,
        status="running",
        migration_type=migration_type,
        row_count=len(rows),
        school_id=str(getattr(school, "id", "") or ""),
        actor_id=getattr(actor, "id", None),
        started_at=started,
    )
    try:
        cache.set(_key(job_id), snap, TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass

    try:
        from apps.accounts.migration_importers import run_importer

        result = run_importer(migration_type, school, rows, actor=actor)
    except Exception as exc:  # noqa: BLE001 - async batch never propagates
        logger.exception("migration job %s: importer raised", job_id)
        snap.update(
            status="failed",
            error_count=len(rows),
            errors=[str(exc)[:200]],
            finished_at=timezone.now().isoformat(),
        )
        try:
            cache.set(_key(job_id), snap, TTL_SECONDS)
        except Exception:  # noqa: BLE001
            pass
        return snap

    snap.update(
        status="completed" if result.get("error_count", 0) == 0 else "completed_with_errors",
        processed=len(rows),
        created=int(result.get("created", 0)),
        updated=int(result.get("updated", 0)),
        skipped=int(result.get("skipped", 0)),
        error_count=int(result.get("error_count", 0)),
        errors=[str(e) for e in (result.get("errors") or [])][:50],
        finished_at=timezone.now().isoformat(),
    )
    try:
        cache.set(_key(job_id), snap, TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return snap


# Celery task wrapper — falls back to inline execution when Celery isn't installed.
try:
    from celery import shared_task

    @shared_task(name="accounts.run_migration_async")
    def run_migration_async(
        job_id: str, school_id: str, migration_type: str, rows: list[dict], actor_id: int | None
    ) -> dict[str, Any]:
        from apps.schools.models import School

        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            actor = User.objects.filter(pk=actor_id).first() if actor_id else None
        except Exception:  # noqa: BLE001
            actor = None
        school = School.objects.filter(pk=school_id).first()
        if school is None:
            return _snapshot(
                job_id=job_id,
                status="failed",
                migration_type=migration_type,
                row_count=len(rows),
                error_count=len(rows),
                errors=["school not found"],
            )
        return _run_import_inline(
            job_id=job_id,
            school=school,
            migration_type=migration_type,
            rows=rows,
            actor=actor,
        )

except ImportError:
    run_migration_async = None  # type: ignore[assignment]


def enqueue_migration_run(
    *, school, migration_type: str, rows: list[dict], actor=None
) -> str:
    """
    Submit a migration to the background queue. Returns the new job_id.

    Falls back to inline execution when Celery is unavailable (dev / tests),
    so the wizard surface works in every environment.
    """
    job_id = uuid.uuid4().hex
    if run_migration_async is None:
        _run_import_inline(
            job_id=job_id,
            school=school,
            migration_type=migration_type,
            rows=rows,
            actor=actor,
        )
        return job_id
    try:
        run_migration_async.delay(
            job_id,
            str(getattr(school, "id", "") or ""),
            migration_type,
            rows,
            getattr(actor, "id", None),
        )
    except Exception:  # noqa: BLE001 - broker down → inline fallback so user isn't blocked
        logger.warning("celery enqueue failed for migration job %s; running inline", job_id)
        _run_import_inline(
            job_id=job_id,
            school=school,
            migration_type=migration_type,
            rows=rows,
            actor=actor,
        )
    return job_id
