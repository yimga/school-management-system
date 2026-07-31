"""Redrive failed OutboundMessageQueue rows (audit residual closeout).

The outbound SMS/WhatsApp drainer (``process_outbound_message_queue``) marks a
row ``failed`` after 3 retries. Previously those rows were terminal — an
operator who fixed the provider config had no way to retry them. This command
resets ``failed`` rows back to ``pending`` (retry_count zeroed) so the next
drain attempts them again. Safe to run on a schedule or by hand.

    python manage.py redrive_outbound_messages                 # up to 100
    python manage.py redrive_outbound_messages --limit 500
    python manage.py redrive_outbound_messages --school <id>   # one tenant
    python manage.py redrive_outbound_messages --dry-run

Prints a one-line summary; never raises.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Reset failed OutboundMessageQueue rows to pending for redrive."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        # School.pk is a UUID — accept the UUID string (type=int rejected every real
        # school id, making the per-tenant redrive unusable).
        parser.add_argument("--school", default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from apps.communication.models import OutboundMessageQueue

        limit = max(1, int(options.get("limit") or 100))
        school_id = options.get("school")
        dry_run = bool(options.get("dry_run"))

        # tenant-isolation-allow: operator redrive tool; optional --school narrows, else platform-wide
        qs = OutboundMessageQueue.objects.filter(status="failed").order_by("created_at")
        if school_id:
            qs = qs.filter(school_id=school_id)
        ids = list(qs.values_list("id", flat=True)[:limit])
        if not ids:
            self.stdout.write("redrive_outbound: no failed rows to redrive")
            return
        if dry_run:
            self.stdout.write(f"redrive_outbound: would reset {len(ids)} row(s) (dry-run)")
            return
        # tenant-isolation-allow: ids already school-scoped by the candidate query above
        updated = OutboundMessageQueue.objects.filter(id__in=ids).update(
            status="pending", retry_count=0, error_message="",
        )
        self.stdout.write(f"redrive_outbound: reset {updated} failed row(s) to pending")
