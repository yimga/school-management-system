"""Release abandoned RESERVED event ticket holds (Metric #13)."""

from django.core.management.base import BaseCommand, CommandError

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
            help="School UUID to scope the sweep (required unless --all-schools).",
        )
        parser.add_argument(
            "--all-schools",
            action="store_true",
            help=(
                "Sweep EVERY tenant on this deployment. Only meaningful on a "
                "single-school box; on a shared edge box this cancels other "
                "schools' held tickets."
            ),
        )

    def handle(self, *args, **options):
        # --school-id used to default to "", so the documented invocation
        # (`manage.py expire_stale_event_reservations`) passed school=None and
        # swept every tenant in the schema. EventRegistration has no school
        # column -- it reaches its tenant through `event` -- so "no filter"
        # means "all schools", which under USE_DJANGO_TENANTS=0 is every school
        # on the box. The unscoped sweep is still available; it now has to be
        # asked for by name.
        school = None
        school_id = (options.get("school_id") or "").strip()
        all_schools = bool(options.get("all_schools"))
        if school_id and all_schools:
            raise CommandError("Pass either --school-id or --all-schools, not both.")
        if not school_id and not all_schools:
            raise CommandError(
                "Refusing an unscoped sweep: pass --school-id=<uuid>, or "
                "--all-schools to release held tickets for every tenant."
            )
        if school_id:
            from apps.schools.models import School

            school = School.objects.filter(pk=school_id).first()
            if school is None:
                raise CommandError(f"School not found: {school_id}")

        released = expire_stale_reservations(
            older_than_minutes=options["minutes"],
            limit=options["limit"],
            school=school,
            all_schools=all_schools,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"expire_stale_event_reservations: released={released} "
                f"minutes={options['minutes']}"
            )
        )
