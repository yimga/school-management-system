"""Platform billing lifecycle Celery beat SOT.

One daily entry that advances every tenant subscription's billing state (trial
conversion, renewal charge, past-due aging, suspend/restore). The FSM is
due-aware per subscription, so a daily sweep invoices each tenant on its own
cycle boundary.

Mirrors ``apps.integrations_marketplace.beat_schedule``: lazy build (celery-less
runtimes/tests don't fail at import), idempotent install (operator-defined keys
are preserved), and a per-entry env disable flag.

* ``RMC_PLATFORM_BILLING_BEAT_ENABLED=1`` — MASTER SWITCH, default OFF. The
  whole billing beat stays empty until this is set. See ``get_billing_beat_schedule``.
* ``RMC_PLATFORM_BILLING_BEAT_DISABLED=1`` — skip the daily lifecycle sweep.
* ``RMC_RENEWAL_REMINDER_BEAT_DISABLED=1`` — skip the daily renewal-reminder sweep.
* ``RMC_DUNNING_REMINDER_BEAT_DISABLED=1`` — skip the daily dunning-reminder sweep.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _env_bool(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def get_billing_beat_schedule() -> dict[str, dict[str, Any]]:
    """Return the billing beat schedule SOT dict (lazy, respects env disable)."""
    try:
        from celery.schedules import crontab  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("billing beat: celery not importable — schedule empty: %s", exc)
        return {}

    # Master switch, default OFF. The lifecycle sweep CHARGES each subscription
    # its renewal, then SUSPENDS it once the balance stays unpaid past
    # `suspension_days` (apps/billing/services.py). It has never run in prod (the
    # beat entry never landed — see the reassignment bug fixed in
    # `install_billing_beat_schedule`). With no PSP adapter `live`, a charge can
    # never be collected, so activating it unconditionally would suspend every
    # paid-tier tenant within the suspension window and convert every long-stale
    # trial in one first-run sweep. Turn it on deliberately (this env var) once
    # collection is possible and prod data is verified. Operators run the sweep
    # by hand via `manage.py run_platform_billing_lifecycle` regardless.
    if not _env_bool("RMC_PLATFORM_BILLING_BEAT_ENABLED"):
        logger.info(
            "billing beat: OFF (set RMC_PLATFORM_BILLING_BEAT_ENABLED=1 to activate "
            "the autonomous lifecycle sweep)"
        )
        return {}

    if _env_bool("RMC_PLATFORM_BILLING_BEAT_DISABLED"):
        return {}

    schedule = {
        "platform-billing-lifecycle-daily": {
            "task": "apps.billing.run_platform_billing_lifecycle",
            # Daily 01:15 UTC — ahead of the 02:30/03:00/03:30/04:00 ops cluster
            # so charges/invoices land before downstream sweeps read them.
            "schedule": crontab(hour=1, minute=15),
            "options": {"expires": 3600},  # magic-number-allow: celery-task-expiry-seconds
        },
        "holding-currency-rollup-daily": {
            "task": "apps.billing.materialize_holding_currency_rollups",
            # Daily 04:30 UTC — after billing lifecycle + fee-invoice sweeps.
            "schedule": crontab(hour=4, minute=30),
            "options": {"expires": 3600},  # magic-number-allow: celery-task-expiry-seconds
        },
    }
    if not _env_bool("RMC_RENEWAL_REMINDER_BEAT_DISABLED"):
        schedule["platform-renewal-reminders-daily"] = {
            "task": "apps.billing.run_subscription_renewal_reminders",
            # Daily 06:00 UTC — after the lifecycle sweep, so reminders reflect the
            # freshest period boundaries.
            "schedule": crontab(hour=6, minute=0),
            "options": {"expires": 3600},  # magic-number-allow: celery-task-expiry-seconds
        }
    if not _env_bool("RMC_DUNNING_REMINDER_BEAT_DISABLED"):
        schedule["platform-dunning-reminders-daily"] = {
            "task": "apps.billing.run_subscription_dunning_reminders",
            # Daily 06:30 UTC — just after the renewal-reminder sweep and well
            # after the 01:15 lifecycle sweep that sets/clears delinquency, so the
            # ladder reads the freshest past-due/suspended state each day.
            "schedule": crontab(hour=6, minute=30),
            "options": {"expires": 3600},  # magic-number-allow: celery-task-expiry-seconds
        }
    return schedule


def install_billing_beat_schedule(app, *, override: bool = False) -> dict[str, dict[str, Any]]:
    """Install billing beat entries on a Celery ``app.conf.beat_schedule``.

    Idempotent: existing keys are preserved unless ``override=True``. Returns the
    dict of entries actually installed (useful for tests + audit logging).
    """
    if app is None or not hasattr(app, "conf"):
        logger.warning("billing beat: install called with invalid app=%r", app)
        return {}

    # Mutate the LIVE schedule dict IN PLACE. Reassigning
    # `app.conf.beat_schedule = <new dict>` is SILENTLY DISCARDED under Celery's
    # `config_from_object("django.conf:settings")`: `app.conf.beat_schedule` IS
    # `settings.CELERY_BEAT_SCHEDULE`, and the assignment never lands, so the
    # entries never reach beat. (Runtime-proven: the install DELTA was empty and
    # all four billing entries were absent from the live schedule.) In-place
    # mutation of that shared dict does land.
    live = getattr(app.conf, "beat_schedule", None)
    if not isinstance(live, dict):
        live = {}
        app.conf.beat_schedule = live
        # ...and re-read, in case the conf proxy ignored the assignment.
        live = getattr(app.conf, "beat_schedule", live)
        if not isinstance(live, dict):
            live = {}

    schedule = get_billing_beat_schedule()
    installed: dict[str, dict[str, Any]] = {}

    for key, entry in schedule.items():
        if key in live and not override:
            logger.debug("billing beat: %s already present — preserving operator config", key)
            continue
        live[key] = entry
        installed[key] = entry

    logger.info(
        "billing beat: installed %d entries (%s)",
        len(installed), ", ".join(installed.keys()) or "none",
    )
    return installed
