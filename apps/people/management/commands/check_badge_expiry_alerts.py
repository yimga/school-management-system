"""
Send or create notifications for badges/certifications expiring within N days.
Run via cron or Celery Beat (e.g. daily). Creates in-app notifications when
finance.Notification exists; otherwise logs to stdout.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.utils import DatabaseError
from django.db.models import ObjectDoesNotExist
from django.utils import timezone

from apps.people.models import Badge
from apps.platform_runtime.structured_logging import log_exception_with_context

# Typed exceptions for badge expiry alert command (§2.4 broad-except replacement).
_BADGE_EXPIRY_SCHOOL_RESOLVE_ERRORS: tuple[type[BaseException], ...] = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    ObjectDoesNotExist,
)
_BADGE_EXPIRY_NOTIFY_ERRORS: tuple[type[BaseException], ...] = (
    IntegrityError,
    DatabaseError,
    ValidationError,
    ValueError,
    TypeError,
    AttributeError,
)


class Command(BaseCommand):
    help = "Create notifications for badges expiring within the next 60 days (certification expiry/renewal alerts)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=60,
            help="Alert when expiry is within this many days (default 60).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Only print what would be notified."
        )

    def handle(self, *args, **options):
        days = max(1, options["days"])
        dry_run = options["dry_run"]
        now = timezone.now()
        cutoff = now + timedelta(days=days)
        qs = Badge.objects.filter(
            expiry_at__isnull=False,
            expiry_at__gt=now,
            expiry_at__lte=cutoff,
        ).select_related("badge_type", "user", "student", "student__school")
        count = 0
        for badge in qs:
            recipient = badge.user or (
                badge.student.user if getattr(badge.student, "user", None) else None
            )
            _school_id = None
            if badge.student_id and getattr(badge.student, "school_id", None):
                _school_id = badge.student.school_id
            elif badge.user_id:
                try:
                    from apps.schools.models import SchoolMembership

                    m = (
                        SchoolMembership.objects.filter(user_id=badge.user_id)
                        .order_by("-is_primary")
                        .first()
                    )
                    if m:
                        _school_id = str(
                            m.school_id
                        )  # reserved for future scope filter
                except _BADGE_EXPIRY_SCHOOL_RESOLVE_ERRORS as e:
                    log_exception_with_context(
                        "check_badge_expiry_alerts: resolve school for user",
                        school_id=None,
                        extra={
                            "badge_id": badge.pk,
                            "user_id": badge.user_id,
                            "error": str(e),
                        },
                    )
            msg = f"Badge « {badge.badge_type.label} » expires on {badge.expiry_at.date()}."
            if dry_run:
                self.stdout.write(f"Would notify: {badge} — {msg}")
            else:
                if not recipient:
                    continue
                try:
                    from apps.finance.models import Notification

                    Notification.objects.notify_unread(
                        recipient=recipient,
                        title="Badge / certification expiring soon",
                        message=msg,
                        severity="WARNING",
                    )
                    count += 1
                except _BADGE_EXPIRY_NOTIFY_ERRORS as e:
                    log_exception_with_context(
                        "check_badge_expiry_alerts: create notification failed",
                        school_id=_school_id,
                        extra={
                            "badge_id": badge.pk,
                            "recipient_id": getattr(recipient, "pk", None),
                            "error": str(e),
                        },
                    )
                    self.stdout.write(
                        self.style.WARNING(f"Skip notify {badge.pk}: {e}")
                    )
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Created {count} badge expiry notification(s).")
            )
        else:
            self.stdout.write(f"Would create {qs.count()} notification(s).")
