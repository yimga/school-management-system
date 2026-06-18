"""Wizard → Migration Cloud intake bootstrap (account_migration kick_off step)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle, SlaTier

logger = logging.getLogger(__name__)

_SOURCE_TO_HINT = {
    "powerschool": "PowerSchool export",
    "blackbaud": "Blackbaud export",
    "veracross": "Veracross export",
    "alma": "Alma export",
    "facts": "FACTS / RenWeb export (read-only)",
    "skyward": "Skyward export (read-only)",
    "csv_canonical": "Canonical CSV manual export",
    "other": "Other legacy source",
}


def bootstrap_migration_bundle(
    *,
    school: Any,
    source: str | None,
    actor_id: int | None = None,
) -> int | None:
    """Create a pending ``MigrationBundle`` and queue profiling when Celery is live.

    Returns the bundle primary key, or ``None`` when ``school`` is missing.
    Idempotent per (school, source) wizard session via stable idempotency_key prefix.
    """
    if school is None or getattr(school, "pk", None) is None:
        return None

    source_key = (source or "csv_canonical").strip().lower() or "csv_canonical"
    school_id = getattr(school, "pk")
    idem = f"wizard-account-migration-{school_id}-{source_key}"
    label = f"Account migration ({_SOURCE_TO_HINT.get(source_key, source_key)})"

    with transaction.atomic():
        bundle, created = MigrationBundle.objects.get_or_create(
            idempotency_key=idem,
            defaults={
                "school_id": school_id,
                "schema_name": getattr(school, "schema_name", "") or "",
                "label": label,
                "intake_method": IntakeMethod.FILE_UPLOAD,
                "source_hint": _SOURCE_TO_HINT.get(source_key, source_key),
                "sla_tier": SlaTier.SMALL,
                "status": BundleStatus.PENDING,
                "intake_source_uri": f"wizard:account_migration:{source_key}",
                "size_summary": {
                    "wizard_source": source_key,
                    "bootstrapped_at": timezone.now().isoformat(),
                    "actor_user_id": actor_id,
                    "worker_log": [
                        {
                            "ts": timezone.now().isoformat(),
                            "event": "bundle.bootstrap",
                            "source": source_key,
                        }
                    ],
                },
            },
        )
        if not created:
            summary = dict(bundle.size_summary or {})
            logs = list(summary.get("worker_log") or [])
            logs.append(
                {
                    "ts": timezone.now().isoformat(),
                    "event": "bundle.rebootstrap",
                    "source": source_key,
                    "actor_user_id": actor_id,
                }
            )
            summary["worker_log"] = logs[-50:]
            bundle.size_summary = summary
            bundle.save(update_fields=["size_summary", "updated_at"])

    _enqueue_advance(bundle.pk)
    logger.info(
        "migration_intake.bootstrap bundle=%s school=%s source=%s created=%s",
        bundle.pk,
        school_id,
        source_key,
        created,
    )
    return int(bundle.pk)


def _enqueue_advance(bundle_id: int) -> None:
    try:
        from apps.migration_cloud.celery_tasks import advance_bundle_task

        advance_bundle_task.delay(bundle_id, use_accelerator=True)
    except Exception as exc:  # noqa: BLE001 — broker optional in dev
        logger.debug("migration_intake.advance enqueue skipped: %s", exc)


def worker_log_fingerprint(*, school_id: int, source: str, row_count: int) -> str:
    """Deterministic worker batch id for ingestion audit rows (no PII)."""
    raw = f"{school_id}:{source}:{row_count}:{secrets.token_hex(4)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
