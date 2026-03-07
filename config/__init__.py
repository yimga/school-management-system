# Load Celery app when Django starts so shared_task and autodiscover work
from .celery import app as celery_app

__all__ = ("celery_app",)
