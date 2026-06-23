"""
Celery app for background tasks (reminders, reports, etc.).
Uses REDIS_URL as broker when set; otherwise tasks can still be defined but
run synchronously or when a worker with a broker is started.

Deploy: set REDIS_URL, then run:
  celery -A config worker -l info
  celery -A config beat -l info   # optional, for scheduled tasks
"""

import logging
from celery import Celery
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
logger = logging.getLogger(__name__)

try:
    from apps.platform_runtime.celery_task_events import (
        connect_celery_platform_task_signals,
    )

    connect_celery_platform_task_signals()
except Exception as exc:
    logger.warning("Celery platform task signals not connected: %s", exc)

# v4.00.55 — Wire the LMS beat schedule SOT (refresh + rotation + retention
# sweeps). Idempotent: respects any operator-defined CELERY_BEAT_SCHEDULE
# entry with the same key. Each entry has its own env-var disable flag.
try:
    from apps.integrations_marketplace.beat_schedule import install_lms_beat_schedule

    install_lms_beat_schedule(app)
except Exception as exc:
    logger.warning("LMS beat schedule not installed: %s", exc)

# Platform billing lifecycle beat — advances every tenant subscription's billing
# state daily (trial conversion, renewal charge, past-due aging, suspend/restore)
# so invoicing is autonomous, not operator-command-driven. Idempotent + env-
# disablable (RMC_PLATFORM_BILLING_BEAT_DISABLED=1).
try:
    from apps.billing.beat_schedule import install_billing_beat_schedule

    install_billing_beat_schedule(app)
except Exception as exc:
    logger.warning("Platform billing beat schedule not installed: %s", exc)


@app.task(bind=True)
def debug_task(self):
    """Simple task for testing Celery is working."""
    logger.info(
        "Celery debug task invoked", extra={"celery_request": repr(self.request)}
    )
