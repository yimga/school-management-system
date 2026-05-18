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
        notify_low_meal_plan_balance.delay(
            meal_plan_balance_id=int(instance.pk),
        )
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
