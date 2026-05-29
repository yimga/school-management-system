"""v4.00.36 — storage-bytes metering hook.

Closes the audit gap: ``UsageMeter`` already declares a ``storage_bytes``
dimension and ``apps/billing/management/commands/aggregate_storage_usage.py``
aggregates from external storage at end-of-period. Real-time write paths
(file upload / delete) never incremented the meter, so dashboards
showed an aggregate-only number lagging by a full period.

This module ships:

* ``record_storage_change(school, delta_bytes)`` — pure helper, can be
  called from any signal handler or service to push a positive or
  negative byte delta into the canonical day-grain ``UsageMeter`` row;
* a generic ``connect_storage_metering(model_cls, file_field_name="file")``
  helper that wires ``post_save`` / ``post_delete`` signals on a model
  to auto-emit deltas. Models opt in from their app's ``AppConfig.ready``.

Metering is best-effort: every error path is swallowed because losing a
byte-count is never worth a 500 to the user uploading their attachment.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def record_storage_change(school: Any, delta_bytes: int) -> None:
    """Increment (or decrement when negative) the ``storage_bytes`` meter.

    ``UsageMeter.quantity`` is ``PositiveBigInteger`` so values cannot go
    below 0. For deletes we clamp the floor — a tenant who deletes more
    than the recorded total just lands at 0, never negative.
    """
    if school is None:
        return
    try:
        delta = int(delta_bytes or 0)
    except (TypeError, ValueError):
        return
    if not delta:
        return
    try:
        from apps.billing.models_metering import record

        if delta > 0:
            record(school, "storage_bytes", delta=delta)
        else:
            # Recording a negative delta would underflow the
            # PositiveBigInteger column. Clamp to 0 via a careful update.
            _decrement_clamped(school, abs(delta))
    except (ImportError, RuntimeError, AttributeError, ValueError) as exc:
        logger.debug("storage metering record failed: %s", exc)


def _decrement_clamped(school: Any, amount: int) -> None:
    from datetime import date as _date_cls

    from django.db import transaction
    from django.utils import timezone

    try:
        from apps.billing.models import UsageMeter
        from apps.billing.services import ensure_billing_account_for_school
    except (ImportError, RuntimeError):
        return
    try:
        account, _ = ensure_billing_account_for_school(school)
    except (AttributeError, RuntimeError, ValueError):
        return
    today: _date_cls = timezone.now().date()
    with transaction.atomic():
        try:
            row = UsageMeter.objects.select_for_update().filter(
                billing_account=account,
                school=school,
                metric_code="storage_bytes",
                period_start=today,
                period_end=today,
            ).first()
        except (AttributeError, RuntimeError, ValueError):
            row = None
        if row is None:
            return
        new_qty = max(0, int(row.quantity or 0) - amount)
        row.quantity = new_qty
        try:
            row.save(update_fields=["quantity", "updated_at"])
        except (AttributeError, RuntimeError, ValueError) as exc:
            logger.debug("storage metering decrement save failed: %s", exc)


def _resolve_school(instance: Any) -> Any | None:
    school = getattr(instance, "school", None)
    if school is not None:
        return school
    # Fall back to a top-level resolver if the model exposes one.
    resolver = getattr(instance, "resolve_school", None)
    if callable(resolver):
        try:
            return resolver()
        except (AttributeError, RuntimeError, ValueError):
            return None
    return None


def _safe_size(file_field: Any) -> int:
    if file_field is None:
        return 0
    name = getattr(file_field, "name", "") or ""
    if not name:
        return 0
    try:
        return int(getattr(file_field, "size", 0) or 0)
    except (AttributeError, RuntimeError, ValueError, OSError):
        return 0


def connect_storage_metering(model_cls: Any, file_field_name: str = "file") -> None:
    """Wire ``post_save`` / ``post_delete`` on ``model_cls`` to emit deltas.

    Idempotent — re-calling with the same args is a no-op because
    ``dispatch_uid`` collapses duplicate receivers.
    """
    dispatch_uid = f"storage_metering_{model_cls._meta.app_label}_{model_cls._meta.model_name}_{file_field_name}"

    @receiver(post_save, sender=model_cls, dispatch_uid=f"{dispatch_uid}_save", weak=False)
    def _on_save(sender, instance, created, **kwargs):  # noqa: ARG001
        if not created:
            return
        size = _safe_size(getattr(instance, file_field_name, None))
        if size:
            record_storage_change(_resolve_school(instance), size)

    @receiver(post_delete, sender=model_cls, dispatch_uid=f"{dispatch_uid}_delete", weak=False)
    def _on_delete(sender, instance, **kwargs):  # noqa: ARG001
        size = _safe_size(getattr(instance, file_field_name, None))
        if size:
            record_storage_change(_resolve_school(instance), -size)


__all__ = ["record_storage_change", "connect_storage_metering"]
