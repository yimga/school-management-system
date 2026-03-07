"""
Send or create notifications for badges/certifications expiring within N days.
Run via cron or Celery Beat (e.g. daily). Creates in-app notifications when
finance.Notification exists; otherwise logs to stdout.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.people.models import Badge


class Command(BaseCommand):
    help = "Create notifications for badges expiring within the next 60 days (certification expiry/renewal alerts)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=60, help="Alert when expiry is within this many days (default 60).")
        parser.add_argument("--dry-run", action="store_true", help="Only print what would be notified.")

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
            recipient = badge.user or (badge.student.user if getattr(badge.student, "user", None) else None)
            school_id = None
            if badge.student_id and getattr(badge.student, "school_id", None):
                school_id = badge.student.school_id
            elif badge.user_id:
                try:
                    from apps.schools.models import SchoolMembership
                    m = SchoolMembership.objects.filter(user_id=badge.user_id).order_by("-is_primary").first()
                    if m:
                        school_id = str(m.school_id)
                except Exception:
                    pass
            msg = f"Badge « {badge.badge_type.label} » expires on {badge.expiry_at.date()}."
            if dry_run:
                self.stdout.write(f"Would notify: {badge} — {msg}")
            else:
                if not recipient:
                    continue
                try:
                    from apps.finance.models import Notification
                    Notification.objects.create(
                        recipient=recipient,
                        title="Badge / certification expiring soon",
                        message=msg,
                        severity="WARNING",
                    )
                    count += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Skip notify {badge.pk}: {e}"))
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Created {count} badge expiry notification(s)."))
        else:
            self.stdout.write(f"Would create {qs.count()} notification(s).")
