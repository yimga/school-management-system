"""Release abandoned RESERVED event ticket holds (Metric #13)."""

from django.core.management.base import BaseCommand

from apps.school_events.services import expire_stale_reservations


class Command(BaseCommand):
    help = (
        "Release unpaid RESERVED event registrations older than N minutes "
        "and restore ticket-tier capacity."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=45,
            help="Age threshold in minutes (default: 45).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Max registrations to release per run (default: 500).",
        )
        parser.add_argument(
            "--school-id",
            type=str,
            default="",
            help="Optional school UUID to scope the sweep.",
        )

    def handle(self, *args, **options):
        school = None
        school_id = (options.get("school_id") or "").strip()
        if school_id:
            from apps.schools.models import School

            school = School.objects.filter(pk=school_id).first()
            if school is None:
                self.stderr.write(self.style.ERROR(f"School not found: {school_id}"))
                return

        released = expire_stale_reservations(
            older_than_minutes=options["minutes"],
            limit=options["limit"],
            school=school,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"expire_stale_event_reservations: released={released} "
                f"minutes={options['minutes']}"
            )
        )
