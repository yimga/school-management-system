"""Enqueue + drain helpers for :class:`HeavyWorkOutbox`."""

from __future__ import annotations

import logging
import threading
from typing import Any

from django.db import close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Reclaim rows left PROCESSING after a worker/deploy kill mid-migrate.
_STALE_PROCESSING_SECONDS = 900  # magic-number-allow: heavy-work-stale-processing-reclaim-seconds
_DEFAULT_DRAIN_LIMIT = 3  # magic-number-allow: heavy-work-outbox-drain-batch-size


def enqueue_heavy_work(
    kind: str,
    *,
    school_id: str = "",
    tenant_schema: str = "",
    bundle_id: int | None = None,
    payload: dict | None = None,
    idempotency_key: str = "",
    kick: bool = True,
) -> Any:
    """Insert (or reuse) a durable outbox row and optionally kick a drain."""
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    sid = str(school_id or "").strip()
    key = str(idempotency_key or "").strip()
    payload = dict(payload or {})

    existing = None
    if key:
        existing = (
            # tenant-isolation-allow: platform-provisioning-outbox-in-public-schema-deduped-by-global-idempotency-key
            HeavyWorkOutbox.objects.filter(
                idempotency_key=key,
                status__in=(
                    HeavyWorkOutbox.Status.PENDING,
                    HeavyWorkOutbox.Status.PROCESSING,
                ),
            )
            .order_by("-created_at")
            .first()
        )
    if existing is None and kind == HeavyWorkOutbox.Kind.PROVISION_SCHOOL and sid:
        existing = (
            HeavyWorkOutbox.objects.filter(
                kind=kind,
                school_id=sid,
                status__in=(
                    HeavyWorkOutbox.Status.PENDING,
                    HeavyWorkOutbox.Status.PROCESSING,
                ),
            )
            .order_by("-created_at")
            .first()
        )
    if existing is not None:
        if kick:
            kick_heavy_work_drain()
        return existing

    try:
        row = HeavyWorkOutbox.objects.create(
            kind=kind,
            school_id=sid,
            tenant_schema=str(tenant_schema or "").strip(),
            bundle_id=bundle_id,
            payload=payload,
            idempotency_key=key,
        )
    except Exception:  # noqa: BLE001 — unique race: fetch winner
        logger.debug("heavy_work_outbox enqueue race kind=%s", kind, exc_info=True)
        if kind == HeavyWorkOutbox.Kind.PROVISION_SCHOOL and sid:
            row = (
                HeavyWorkOutbox.objects.filter(
                    kind=kind,
                    school_id=sid,
                    status__in=(
                        HeavyWorkOutbox.Status.PENDING,
                        HeavyWorkOutbox.Status.PROCESSING,
                    ),
                )
                .order_by("-created_at")
                .first()
            )
            if row is not None:
                if kick:
                    kick_heavy_work_drain()
                return row
        raise

    if kick:
        kick_heavy_work_drain()
    return row


def kick_heavy_work_drain() -> None:
    """Ask a worker (or a short-lived thread) to drain pending rows."""
    from django.conf import settings

    def _spawn_thread() -> None:
        def _bg() -> None:
            try:
                drain_heavy_work_outbox(limit=_DEFAULT_DRAIN_LIMIT)
            except Exception:  # noqa: BLE001
                logger.exception("heavy_work_outbox background drain failed")
            finally:
                close_old_connections()

        threading.Thread(
            target=_bg,
            daemon=True,
            name="heavy-work-outbox-drain",
        ).start()

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        _spawn_thread()
        return

    try:
        from apps.platform_runtime.tasks import drain_heavy_work_outbox_task

        drain_heavy_work_outbox_task.delay(limit=_DEFAULT_DRAIN_LIMIT)
    except Exception:  # noqa: BLE001 — broker down → thread kick; row stays durable
        logger.warning(
            "heavy_work_outbox: celery drain kick failed; using thread",
            exc_info=True,
        )
        _spawn_thread()


def drain_heavy_work_outbox(*, limit: int = _DEFAULT_DRAIN_LIMIT) -> dict[str, Any]:
    """Claim and execute up to ``limit`` pending (or stale processing) rows."""
    from django.db.models import F

    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    limit = max(1, min(int(limit or _DEFAULT_DRAIN_LIMIT), 10))  # magic-number-allow: heavy-work-drain-cap
    _reclaim_stale_processing()
    processed = 0
    failed = 0
    # tenant-isolation-allow: platform-heavy-work-outbox-global-drain-by-status
    qs = list(
        HeavyWorkOutbox.objects.filter(status=HeavyWorkOutbox.Status.PENDING).order_by(
            "created_at"
        )[:limit]
    )
    for row in qs:
        claimed = (
            HeavyWorkOutbox.objects.filter(  # tenant-isolation-allow: platform-heavy-work-outbox-claim-by-pk
                pk=row.pk, status=HeavyWorkOutbox.Status.PENDING
            ).update(
                status=HeavyWorkOutbox.Status.PROCESSING,
                claimed_at=timezone.now(),
                attempt_count=F("attempt_count") + 1,
            )
        )
        if not claimed:
            continue
        row.refresh_from_db()
        try:
            _execute_row(row)
            HeavyWorkOutbox.objects.filter(pk=row.pk).update(  # tenant-isolation-allow: platform-heavy-work-outbox-complete-by-pk
                status=HeavyWorkOutbox.Status.SUCCEEDED,
                finished_at=timezone.now(),
                last_error="",
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001 — row failure must not abort batch
            logger.exception("heavy_work_outbox execute failed id=%s kind=%s", row.pk, row.kind)
            HeavyWorkOutbox.objects.filter(pk=row.pk).update(  # tenant-isolation-allow: platform-heavy-work-outbox-fail-by-pk
                status=HeavyWorkOutbox.Status.FAILED,
                finished_at=timezone.now(),
                last_error=f"{type(exc).__name__}: {exc}"[:2000],
            )
            failed += 1
    return {"processed": processed, "failed": failed, "claimed": len(qs)}


def _reclaim_stale_processing() -> int:
    from datetime import timedelta

    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    cutoff = timezone.now() - timedelta(seconds=_STALE_PROCESSING_SECONDS)
    return int(
        HeavyWorkOutbox.objects.filter(  # tenant-isolation-allow: platform-heavy-work-outbox-stale-reclaim
            status=HeavyWorkOutbox.Status.PROCESSING,
            claimed_at__lt=cutoff,
        ).update(status=HeavyWorkOutbox.Status.PENDING, claimed_at=None)
    )


# A provision row PENDING longer than this means the queue is NOT draining (broker
# up but no worker consuming it, and the /health/ in-process drain disabled or
# unpinged). Such a row never became a WorkflowRun, so every provisioning watchdog
# is structurally blind to it — this is the one signal that surfaces the gap.
_STALE_PENDING_ALERT_SECONDS = 600  # magic-number-allow: stale-pending-provision-outbox-alert-seconds


def stale_pending_provision_count(
    *, older_than_seconds: int = _STALE_PENDING_ALERT_SECONDS
) -> int:
    """Count of PROVISION_SCHOOL rows PENDING longer than the threshold."""
    from datetime import timedelta

    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    cutoff = timezone.now() - timedelta(seconds=max(60, int(older_than_seconds or 0)))
    try:
        return int(
            # tenant-isolation-allow: platform-heavy-work-outbox-stale-pending-count
            HeavyWorkOutbox.objects.filter(
                kind=HeavyWorkOutbox.Kind.PROVISION_SCHOOL,
                status=HeavyWorkOutbox.Status.PENDING,
                created_at__lt=cutoff,
            ).count()
        )
    except Exception:  # noqa: BLE001 — a health probe must never raise
        logger.debug("stale_pending_provision_count failed", exc_info=True)
        return 0


def reconcile_stale_pending_provisions(
    *, older_than_seconds: int = _STALE_PENDING_ALERT_SECONDS
) -> dict[str, Any]:
    """Surface + nudge a non-draining provision queue (WorkflowRun-independent).

    The provisioning watchdogs all key on a ``WorkflowRun``, which only exists once
    a row has been DRAINED — so a row stuck PENDING is invisible to all of them.
    This closes that blind spot: it logs a WARNING (ops visibility) whenever a
    PROVISION_SCHOOL row has been PENDING past the threshold, and kicks a drain as
    belt-and-suspenders (a live worker drains it; the /health/-tick in-process
    drain is worker-independent). Wired into the provisioning watchdog sweep (beat
    + /health/ tick). Best-effort — never raises into the sweep.
    """
    stale = stale_pending_provision_count(older_than_seconds=older_than_seconds)
    if stale <= 0:
        return {"stale_pending": 0, "kicked": False}
    logger.warning(
        "heavy_work_outbox: %s PROVISION_SCHOOL row(s) PENDING > %ss — the queue is "
        "not draining (no WorkflowRun exists yet, so provisioning watchdogs are "
        "blind). Check the celery worker / in-process /health/ drain.",
        stale,
        older_than_seconds,
    )
    kicked = False
    try:
        kick_heavy_work_drain()
        kicked = True
    except Exception:  # noqa: BLE001 — the nudge is best-effort
        logger.debug("heavy_work_outbox: stale-pending drain kick failed", exc_info=True)
    return {"stale_pending": stale, "kicked": kicked}


def _execute_row(row) -> None:
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    kind = row.kind
    payload = dict(row.payload or {})

    if kind == HeavyWorkOutbox.Kind.PROVISION_SCHOOL:
        from apps.schools.tasks import provision_school_sync

        contact = str(payload.get("contact_email") or "").strip()
        kwargs = {
            k: v
            for k, v in payload.items()
            if k not in ("contact_email",)
        }
        provision_school_sync(str(row.school_id), contact_email=contact, **kwargs)
        return

    if kind == HeavyWorkOutbox.Kind.HEAL_TENANT_SCHEMA:
        from django.core.management import call_command
        from io import StringIO

        schema = str(row.tenant_schema or payload.get("tenant_schema") or "").strip()
        if not schema:
            raise ValueError("missing_tenant_schema")
        try:
            call_command(
                "heal_tenant_schema_drift",
                "--schema",
                schema,
                "--apply",
                stdout=StringIO(),
                stderr=StringIO(),
            )
        except SystemExit as exc:
            code = int(getattr(exc, "code", 1) or 1)
            if code not in (0, 1):
                raise
        return

    if kind == HeavyWorkOutbox.Kind.RUN_TENANT_MIGRATIONS:
        from django.core.management import call_command
        from io import StringIO

        schema = str(row.tenant_schema or payload.get("tenant_schema") or "").strip()
        stdout, stderr = StringIO(), StringIO()
        if schema:
            # Single-schema migrate. A flag-less ``migrate`` here is django_tenants'
            # ``MigrateSchemasCommand`` with no scope → "sync both" = public + EVERY
            # tenant schema, ignoring the ``schema_context`` (the executor sets the
            # schema itself). ``migrate_schemas --tenant --schema=<this>`` migrates
            # only this one — same fix as onboarding_service._run_tenant_migrations.
            call_command(
                "migrate_schemas",
                schema_name=schema,
                tenant=True,
                run_syncdb=True,
                interactive=False,
                stdout=stdout,
                stderr=stderr,
            )
            return
        call_command(
            "run_tenant_migrations",
            "--noinput",
            stdout=stdout,
            stderr=stderr,
        )
        return

    if kind == HeavyWorkOutbox.Kind.MC_ADVANCE_BUNDLE:
        from apps.migration_cloud.models import BundleStatus, MigrationBundle
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle

        bid = int(row.bundle_id or payload.get("bundle_id") or 0)
        if not bid:
            raise ValueError("missing_bundle_id")
        use_accelerator = bool(payload.get("use_accelerator", True))
        advance_bundle(bundle_id=bid, use_accelerator=use_accelerator)
        if payload.get("apply_after"):
            # tenant-isolation-allow: heavy-work-outbox-mc-pipeline-chain-by-bundle-pk
            bundle = MigrationBundle.objects.filter(pk=bid).first()
            if bundle is not None and bundle.status == BundleStatus.MAPPED:
                apply_bundle(
                    bundle_id=bid,
                    dry_run=bool(payload.get("dry_run_apply", True)),
                )
        return

    if kind == HeavyWorkOutbox.Kind.MC_APPLY_BUNDLE:
        from apps.migration_cloud.orchestrator import apply_bundle

        bid = int(row.bundle_id or payload.get("bundle_id") or 0)
        if not bid:
            raise ValueError("missing_bundle_id")
        dry_run = bool(payload.get("dry_run", True))
        apply_bundle(bundle_id=bid, dry_run=dry_run)
        if payload.get("reconcile_after") and not dry_run:
            try:
                from apps.migration_cloud.reconciliation import reconcile_bundle

                reconcile_bundle(bundle_id=bid)
            except Exception:  # noqa: BLE001 — best-effort post-apply verify
                logger.debug(
                    "heavy_work_outbox: post-apply reconcile failed bundle=%s",
                    bid,
                    exc_info=True,
                )
        return

    raise ValueError(f"unknown_heavy_work_kind:{kind}")


def enqueue_provision_school(
    school_id: str, contact_email: str = "", **kwargs
) -> Any:
    """Durable provision enqueue (preferred over fire-and-forget threads)."""
    from apps.platform_runtime.models_heavy_work_outbox import HeavyWorkOutbox

    sid = str(school_id)
    payload = {"contact_email": (contact_email or "").strip(), **dict(kwargs)}
    return enqueue_heavy_work(
        HeavyWorkOutbox.Kind.PROVISION_SCHOOL,
        school_id=sid,
        payload=payload,
        idempotency_key=f"provision:{sid}:active",
        kick=True,
    )


@transaction.atomic
def enqueue_on_commit_provision(school_id: str, contact_email: str = "", **kwargs) -> None:
    """Enqueue after the surrounding DB transaction commits."""
    sid = str(school_id)
    email = (contact_email or "").strip()
    kw = dict(kwargs)

    def _go() -> None:
        try:
            enqueue_provision_school(sid, contact_email=email, **kw)
        except Exception:  # noqa: BLE001
            logger.exception("enqueue_on_commit_provision failed school_id=%s", sid)

    transaction.on_commit(_go)
