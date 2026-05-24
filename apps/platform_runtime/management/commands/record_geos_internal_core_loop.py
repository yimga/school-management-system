"""Record GEOS internal pilot core loop + update scorecard (Lane 2)."""

from django.core.management.base import BaseCommand, CommandError

from apps.platform_runtime.geos_lane2_core_loop import execute_core_loop


class Command(BaseCommand):
    help = (
        "Run demo-school core operating loop (attendance, marks check, invoice, "
        "manual payment) and write var/evidence/geos-99/pilot/<slug>/ evidence."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            default="demo-school",
            help="Tenant school slug (default: demo-school).",
        )
        parser.add_argument(
            "--no-seed",
            action="store_true",
            help="Skip ensure_demo_environment when data already present.",
        )

    def handle(self, *args, **options):
        slug = (options.get("school_slug") or "demo-school").strip()
        try:
            evidence = execute_core_loop(
                slug, seed_if_missing=not options.get("no_seed")
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "GEOS internal pilot core loop recorded for %s (invoice=%s payment=%s)"
                % (
                    slug,
                    evidence["core_loop"]["invoice_id"],
                    evidence["core_loop"]["payment_id"],
                )
            )
        )
