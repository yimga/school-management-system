"""v3.32.0 — Low-balance notification signal for :class:`MealPlanBalance`.

Fires :func:`apps.schoolops.tasks.notify_low_meal_plan_balance` exactly
once per False -> True transition of the :attr:`MealPlanBalance.is_low`
property. We cache the pre-save :attr:`is_low` on the instance in a
``pre_save`` handler and consult it in ``post_save`` — this is the only
reliable way to detect a transition without an extra SELECT per save
(``instance.refresh_from_db`` would race with the in-flight UPDATE).

Failure to dispatch is logged at WARNING level but NEVER raised — a
notification glitch must not poison the save transaction.

Logging contract (memory-pinned):
  * NEVER log email addresses, phone numbers, names, hash material,
    or balance numerics. Log the row PK + student ID + plan ID only.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver


logger = logging.getLogger(__name__)


# Sentinel set on the instance by pre_save so post_save can detect the
# False -> True is_low transition. Tested via direct attribute presence
# (a missing attribute is treated as "no prior state known").
_PRE_SAVE_IS_LOW_ATTR = "_schoolops_low_balance_pre_save_is_low"


def _publish_low_balance_webhook(instance) -> None:
    """v3.33.0 — fan a ``schoolops.meal_plan.low_balance_triggered`` event
    out to every :class:`MigrationCloudWebhookSubscription` that has
    explicitly opted in to ``schoolops.*``.

    Defensive: a webhook outage NEVER raises out of this signal — the
    save transaction must remain inviolate. PII-free payload: row PK,
    student/plan IDs, school ID, currency, and the boolean ``is_low``
    only. No balance numeric, no names, no emails.
    """
    try:
        from apps.migration_cloud.api.webhook_dispatch import enqueue
        from apps.migration_cloud.models import (
            MigrationCloudWebhookSubscription,
        )
        school_id = getattr(instance, "school_id", None)
        if school_id is None:
            return
        # tenant-isolation-allow: webhook-dispatch-scoped-via-instance-school-fk-tenant-bound
        subs = MigrationCloudWebhookSubscription.objects.filter(
            tenant_id=school_id, active=True,
        )
        event_type = "schoolops.meal_plan.low_balance_triggered"
        payload = {
            "event": event_type,
            "school_id": int(school_id),
            "meal_plan_balance_id": int(instance.pk),
            "student_id": int(getattr(instance, "student_id", 0) or 0),
            "meal_plan_id": (
                int(instance.meal_plan_id) if instance.meal_plan_id else None
            ),
            "currency": getattr(instance, "currency", "") or "",
            "is_low": True,
        }
        published = 0
        for sub in subs:
            try:
                row = enqueue(sub, event_type, payload)
                if row is not None:
                    published += 1
            except Exception:  # noqa: BLE001 -- per-sub isolation
                logger.warning(
                    "schoolops.low_balance_webhook_enqueue_failed "
                    "sub_id=%s row_pk=%s",
                    getattr(sub, "pk", None), getattr(instance, "pk", None),
                )
        logger.info(
            "schoolops.low_balance_webhook_published "
            "row_pk=%s school_id=%s subs_total=%s subs_published=%s",
            instance.pk, school_id, subs.count(), published,
        )
    except Exception:  # noqa: BLE001 -- signal-handler safety
        logger.exception(
            "schoolops.low_balance_webhook_publish_failed row_pk=%s",
            getattr(instance, "pk", None),
        )


@receiver(pre_save, sender="schoolops.MealPlanBalance")
def _cache_pre_save_is_low(
    sender: Any, instance: Any, **kwargs: Any,
) -> None:
    """Capture the database-side :attr:`is_low` BEFORE the save commits."""
    try:
        if instance.pk is None:
            # Brand-new row — there is no "prior" state; pre = False so an
            # already-low new row will fire its first notification.
            setattr(instance, _PRE_SAVE_IS_LOW_ATTR, False)
            return
        # tenant-isolation-allow: signal-handler-pk-lookup-on-existing-row-within-same-tenant
        old = sender.objects.filter(pk=instance.pk).only(
            "balance", "low_balance_threshold",
        ).first()
        if old is None:
            setattr(instance, _PRE_SAVE_IS_LOW_ATTR, False)
            return
        setattr(instance, _PRE_SAVE_IS_LOW_ATTR, bool(old.is_low))
    except Exception:  # noqa: BLE001 -- signal-handler safety
        # Swallow + log so save never breaks. If the cache misses, the
        # post_save handler treats it as "no prior state" => fires once.
        logger.exception(
            "schoolops.signals._cache_pre_save_is_low failed; "
            "row_pk=%s",
            getattr(instance, "pk", None),
        )


@receiver(post_save, sender="schoolops.MealPlanBalance")
def _dispatch_low_balance_notification(
    sender: Any, instance: Any, created: bool, **kwargs: Any,
) -> None:
    """Dispatch low-balance notification on False -> True transition only."""
    try:
        prior_low = getattr(instance, _PRE_SAVE_IS_LOW_ATTR, False)
        try:
            current_low = bool(instance.is_low)
        except Exception:  # noqa: BLE001
            current_low = False

        # Spam guard: only fire on the actual transition.
        if not current_low:
            return
        if prior_low and not created:
            return

        # 7-day cooldown is enforced inside the task (defense-in-depth);
        # we re-check here only to avoid scheduling Celery work that will
        # immediately no-op. Caller-side check uses naive comparison —
        # the task is the SOT.
        from django.utils import timezone
        last_sent = getattr(
            instance, "last_low_balance_notification_sent_at", None,
        )
        if last_sent is not None:
            try:
                delta = timezone.now() - last_sent
                if delta.total_seconds() < 7 * 24 * 60 * 60:
                    return
            except (TypeError, ValueError):
                pass

        from apps.schoolops.tasks import notify_low_meal_plan_balance
        try:
            notify_low_meal_plan_balance.delay(
                meal_plan_balance_id=int(instance.pk),
            )
        except Exception:  # noqa: BLE001 - broker transport errors are diverse
            # Free tier often has no Celery broker, so .delay() raises
            # kombu.OperationalError and the email would be silently dropped.
            # Run the task body inline instead (idempotent via the 7-day
            # cooldown above) so the parent still gets the low-balance alert.
            logger.warning(
                "schoolops.low_balance: broker enqueue failed; sending inline "
                "row_pk=%s",
                instance.pk,
            )
            notify_low_meal_plan_balance(meal_plan_balance_id=int(instance.pk))
        # v3.33.0 — publish a coarse webhook event so partner systems
        # subscribed to ``schoolops.*`` can react (e.g. parent-portal
        # banner refresh, finance-team alerting). NEVER include PII —
        # the payload carries IDs + the boolean "is_low" state only.
        _publish_low_balance_webhook(instance)
        logger.info(
            "schoolops.low_balance_signal dispatched "
            "row_pk=%s student_id=%s plan_id=%s",
            instance.pk,
            getattr(instance, "student_id", None),
            getattr(instance, "meal_plan_id", None),
        )
    except Exception:  # noqa: BLE001 -- signal-handler safety
        logger.exception(
            "schoolops.signals._dispatch_low_balance_notification failed; "
            "row_pk=%s",
            getattr(instance, "pk", None),
        )


# ──────────────────────────────────────────────────────────────────────
# Metric 14 — inventory reorder (low-stock) alerts.
#
# Mirrors the MealPlanBalance low-balance pattern above: a pre_save handler
# caches the database-side ``is_low`` so the post_save handler can detect the
# False -> True transition (crossing to/below the reorder level) and fire the
# alert EXACTLY once per low-stock episode. On the reverse True -> False
# transition (restock above the reorder level) we clear
# ``last_low_stock_notified_at`` via a queryset ``.update()`` (which does NOT
# fire signals — no re-entrancy) so the NEXT dip alerts again.
# ──────────────────────────────────────────────────────────────────────

_PRE_SAVE_INV_IS_LOW_ATTR = "_schoolops_inventory_pre_save_is_low"


@receiver(pre_save, sender="schoolops.InventoryItem")
def _cache_pre_save_inventory_is_low(
    sender: Any, instance: Any, **kwargs: Any,
) -> None:
    """Capture the database-side :attr:`InventoryItem.is_low` BEFORE save."""
    try:
        if instance.pk is None:
            setattr(instance, _PRE_SAVE_INV_IS_LOW_ATTR, False)
            return
        # tenant-isolation-allow: signal-handler-pk-lookup-on-existing-row-within-same-tenant
        old = sender.objects.filter(pk=instance.pk).only(
            "quantity", "reorder_threshold",
        ).first()
        setattr(
            instance,
            _PRE_SAVE_INV_IS_LOW_ATTR,
            bool(old.is_low) if old is not None else False,
        )
    except Exception:  # noqa: BLE001 -- signal-handler safety
        logger.exception(
            "schoolops.signals._cache_pre_save_inventory_is_low failed; row_pk=%s",
            getattr(instance, "pk", None),
        )


@receiver(post_save, sender="schoolops.InventoryItem")
def _dispatch_low_inventory_notification(
    sender: Any, instance: Any, created: bool, **kwargs: Any,
) -> None:
    """Dispatch a low-stock alert on the False -> True ``is_low`` transition."""
    try:
        prior_low = getattr(instance, _PRE_SAVE_INV_IS_LOW_ATTR, False)
        try:
            current_low = bool(instance.is_low)
        except Exception:  # noqa: BLE001
            current_low = False

        # Restock above the reorder level: close the episode so the next dip
        # can fire again. Queryset .update() bypasses signals (no re-entrancy).
        if prior_low and not current_low:
            if getattr(instance, "last_low_stock_notified_at", None) is not None:
                # tenant-isolation-allow: reset-scoped-to-same-row-and-its-school-fk
                sender.objects.filter(
                    pk=instance.pk, school_id=instance.school_id,
                ).update(last_low_stock_notified_at=None, low_stock_notification_count=0)
            return

        if not current_low:
            return
        # Only fire on the actual crossing (or a brand-new already-low row).
        if prior_low and not created:
            return
        # An already-open episode (stamp set) is handled idempotently by the
        # task; don't double-dispatch here.
        if getattr(instance, "last_low_stock_notified_at", None) is not None:
            return

        from apps.schoolops.tasks import notify_low_inventory_stock
        try:
            notify_low_inventory_stock.delay(inventory_item_id=int(instance.pk))
        except Exception:  # noqa: BLE001 — free tier often has no broker
            logger.warning(
                "schoolops.low_inventory: broker enqueue failed; sending inline "
                "item_id=%s",
                instance.pk,
            )
            notify_low_inventory_stock(inventory_item_id=int(instance.pk))
        logger.info(
            "schoolops.low_inventory_signal dispatched item_id=%s school_id=%s",
            instance.pk, getattr(instance, "school_id", None),
        )
    except Exception:  # noqa: BLE001 -- signal-handler safety
        logger.exception(
            "schoolops.signals._dispatch_low_inventory_notification failed; row_pk=%s",
            getattr(instance, "pk", None),
        )
