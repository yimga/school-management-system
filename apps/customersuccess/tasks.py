"""Celery tasks for customer success (Move 4)."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="customersuccess.run_auto_ticket_rules")
def run_auto_ticket_rules() -> dict:
    """Move 4 — drive AutoTicketRule evaluations. Returns count map per rule."""

    try:
        from apps.customersuccess.auto_ticket_runner import run_all_rules

        return run_all_rules()
    except Exception as exc:
        logger.exception("run_auto_ticket_rules failed: %s", exc)
        return {}


@shared_task(name="customersuccess.recompute_benchmark_cohorts")
def recompute_benchmark_cohorts_task() -> dict:
    """Produce peer-benchmark cohorts + k-anonymous aggregate metrics.

    Thin wrapper over the ``recompute_benchmark_cohorts`` management command so
    the producer can run on a schedule (Celery beat) as well as on demand. Never
    raises into the worker loop.
    """
    try:
        from django.core.management import call_command

        call_command("recompute_benchmark_cohorts")
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — never break the worker on analytics
        logger.exception("recompute_benchmark_cohorts task failed: %s", exc)
        return {"ok": False, "error": str(exc)}


@shared_task(name="customersuccess.deliver_onboarding_day_n_nudges")
def deliver_onboarding_day_n_nudges(*, limit: int = 50) -> dict:
    """Emit due onboarding nudges for active schools (idempotent markers in school.settings)."""
    from datetime import date

    from apps.customersuccess.onboarding_day_n_nudges import (
        compute_due_nudges,
        get_sent_markers,
        record_nudge_sent,
    )
    from apps.schools.models import School

    sent = 0
    scanned = 0
    for school in School.objects.filter(is_active=True).order_by("id")[: max(1, limit)]:  # tenant-isolation-allow: cross-tenant-sweep-active-schools-each-iteration-school-scoped
        scanned += 1
        settings_blob = dict(getattr(school, "settings", None) or {})
        cs = dict(settings_blob.get("customersuccess") or {})
        completed = set(cs.get("completed_tasks") or [])
        signup = getattr(school, "created_at", None)
        if signup is None:
            continue
        batch = compute_due_nudges(
            school_id=school.pk,
            signup_date=signup.date(),
            today=date.today(),
            completed_task_keys=completed,
            already_sent_markers=get_sent_markers(settings_blob),
        )
        for nudge in batch.due:
            settings_blob = record_nudge_sent(
                school_settings=settings_blob,
                marker=nudge.marker,
            )
            sent += 1
        if batch.due:
            school.settings = settings_blob
            school.save(update_fields=["settings", "updated_at"])
    return {"scanned": scanned, "sent": sent}


@shared_task(name="customersuccess.sweep_tenant_health_scores")
def sweep_tenant_health_scores(*, limit: int = 200) -> dict:
    """Persist tenant health scores for active schools (daily sweep)."""
    from apps.customersuccess.services import ensure_health_score_record
    from apps.schools.models import School

    updated = 0
    for school in School.objects.filter(is_active=True).order_by("id")[: max(1, limit)]:  # tenant-isolation-allow: cross-tenant-sweep-active-schools-each-iteration-school-scoped
        ensure_health_score_record(school)
        updated += 1
    return {"updated": updated}


@shared_task(name="customersuccess.compute_maturity_scores")
def compute_maturity_scores(*, limit: int = 200) -> dict:
    """Write TenantMaturityScore rows from health dimensions."""
    from decimal import Decimal

    from apps.customersuccess.models import TenantMaturityScore
    from apps.customersuccess.services import compute_tenant_health_score
    from apps.schools.models import School

    written = 0
    for school in School.objects.filter(is_active=True).order_by("id")[: max(1, limit)]:  # tenant-isolation-allow: cross-tenant-sweep-active-schools-each-iteration-school-scoped
        _score, dimensions = compute_tenant_health_score(school)
        for dim_key, dim_val in dimensions.items():
            TenantMaturityScore.objects.update_or_create(
                school=school,
                dimension=str(dim_key)[:60],
                defaults={
                    "score": Decimal(str(dim_val)),
                    "payload": {"source": "compute_maturity_scores"},
                },
            )
            written += 1
    return {"written": written}
