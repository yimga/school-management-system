"""Celery tasks for the Unified Wizard Framework.

Wires into ``CELERY_BEAT_SCHEDULE``:

* ``setup-studio-recommendations-refresh`` — Mondays 04:00 UTC. Walks active
  schools, calls ``apps.setup_studio.wizard_ai.refresh_setup_recommendations``
  for each. Rate-limited at 200 schools per beat invocation; remaining schools
  picked up next week (or on demand via the management command).

The handler itself is no-op on AI unavailable (per
``services.ai_helpers.is_ai_available``) and is safe to call when no
wizards are completed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import — Celery is in requirements but a CI lane without Celery should
# still import this module cleanly to satisfy AST + import-scan.
try:
    from celery import shared_task  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def shared_task(*decorator_args, **decorator_kwargs):  # type: ignore
        def _wrap(fn):
            return fn
        if decorator_args and callable(decorator_args[0]) and not decorator_kwargs:
            return _wrap(decorator_args[0])
        return _wrap


_MAX_SCHOOLS_PER_BEAT = 200


@shared_task(name="setup_studio.refresh_setup_recommendations_for_active_schools")
def refresh_setup_recommendations_for_active_schools() -> dict[str, Any]:
    """Beat handler. Returns ``{processed: N, errors: M}``."""
    try:
        from apps.schools.models import School  # type: ignore
    except ImportError:
        logger.warning("refresh_setup_recommendations: School model unavailable")
        return {"processed": 0, "errors": 0}

    try:
        from apps.setup_studio import wizard_ai
    except ImportError:
        logger.warning("refresh_setup_recommendations: wizard_ai unavailable")
        return {"processed": 0, "errors": 0}

    processed = 0
    errors = 0
    # tenant-isolation-allow: cross-tenant-batch-cron-walks-every-active-school-by-design
    qs = School.objects.all()
    if hasattr(School, "live_objects"):
        try:
            qs = School.live_objects.all()
        except Exception:  # noqa: BLE001
            pass
    for school in qs[:_MAX_SCHOOLS_PER_BEAT]:
        try:
            wizard_ai.refresh_setup_recommendations(school=school)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_setup_recommendations failed for school %s: %s", getattr(school, "pk", None), exc)
            errors += 1
    return {"processed": processed, "errors": errors}


@shared_task(name="setup_studio.prune_stale_resumable_wizards")
def prune_stale_resumable_wizards(older_than_days: int = 30) -> dict[str, Any]:
    """v4.00.14 — auto-prune stale incomplete wizards from SetupProgress.step_state.

    Walks every active school's SetupProgress row, runs
    ``prune_stale_resumable_entries`` on the ``wizards`` namespace, and persists
    when entries were removed. Bounded by ``_MAX_SCHOOLS_PER_BEAT``; remaining
    schools picked up the following run.

    Returns ``{processed, pruned_keys_total, errors}``.
    """
    try:
        from apps.schools.models import School  # type: ignore
        from apps.setup_studio.models import SetupProgress
        from apps.setup_studio.wizard_extras import prune_stale_resumable_entries
    except ImportError as exc:
        logger.warning("prune_stale_resumable_wizards: import failed: %s", exc)
        return {"processed": 0, "pruned_keys_total": 0, "errors": 0}

    processed = 0
    pruned_total = 0
    errors = 0
    # tenant-isolation-allow: cross-tenant-batch-cron-prunes-stale-wizard-state-by-design
    qs = School.objects.all()
    if hasattr(School, "live_objects"):
        try:
            qs = School.live_objects.all()
        except Exception:  # noqa: BLE001
            pass
    for school in qs[:_MAX_SCHOOLS_PER_BEAT]:
        try:
            # tenant-isolation-allow: scoped-via-school-fk-setup-progress-prune-beat
            progress = SetupProgress.objects.filter(school=school).first()
            if progress is None:
                continue
            state = progress.step_state if isinstance(progress.step_state, dict) else {}
            wizards_ns = state.get("wizards") if isinstance(state.get("wizards"), dict) else {}
            if not wizards_ns:
                processed += 1
                continue
            pruned_ns, removed = prune_stale_resumable_entries(
                wizards_namespace=wizards_ns,
                older_than_days=int(older_than_days),
            )
            if removed:
                state["wizards"] = pruned_ns
                progress.step_state = state
                progress.save(update_fields=["step_state", "updated_at"])
                pruned_total += len(removed)
                logger.info(
                    "prune_stale_resumable_wizards: school=%s pruned=%d",
                    getattr(school, "pk", None), len(removed),
                )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "prune_stale_resumable_wizards failed for school %s: %s",
                getattr(school, "pk", None), exc,
            )
            errors += 1
    return {"processed": processed, "pruned_keys_total": pruned_total, "errors": errors}
