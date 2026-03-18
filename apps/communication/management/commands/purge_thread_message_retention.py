"""
BR-08: Soft-delete or hard-purge thread messages older than retention window.
school.settings['comms_thread_retention_days'] (default 730). Run via cron/Celery.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.communication.models import ThreadMessage
from apps.schools.models import School


class Command(BaseCommand):
    help = "Purge thread messages older than each school's comms_thread_retention_days (default 730)."

    def add_arguments(self, parser):
        parser.add_argument("--school-id", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        sid = options.get("school_id")
        dry = options.get("dry_run")
        qs = School.objects.filter(is_active=True)
        if sid:
            qs = qs.filter(pk=sid)
        total = 0
        now = timezone.now()
        for school in qs.iterator():
            settings = getattr(school, "settings", None) or {}
            days = int(settings.get("comms_thread_retention_days", 730) or 730)
            if days <= 0:
                continue
            cutoff = now - timedelta(days=days)
            msg_qs = ThreadMessage.objects.filter(
                school_id=school.id, created_at__lt=cutoff, is_deleted=False
            )
            cnt = msg_qs.count()
            if cnt and not dry:
                msg_qs.update(is_deleted=True, deleted_at=now)
            total += cnt
            if cnt:
                self.stdout.write(
                    f"school={school.id} purged={cnt} (cutoff {cutoff.date()})"
                )
        self.stdout.write(
            self.style.SUCCESS(f"Done. affected_messages={total} dry_run={dry}")
        )
