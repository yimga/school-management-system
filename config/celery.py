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


@app.task(bind=True)
def debug_task(self):
    """Simple task for testing Celery is working."""
    logger.info("Celery debug task invoked", extra={"celery_request": repr(self.request)})
