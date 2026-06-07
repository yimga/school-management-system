"""Offline-optimise a bus route's stop order (Wave D — logistics).

    python manage.py optimize_bus_route --route <id>          # dry-run
    python manage.py optimize_bus_route --route <id> --apply  # persist sequence
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.schoolops.route_optimizer import optimize_route


class Command(BaseCommand):
    help = "Greedy offline optimisation of a bus route's stop ordering."

    def add_arguments(self, parser):
        parser.add_argument("--route", required=True, help="Route id to optimise.")
        parser.add_argument("--apply", action="store_true", help="Persist the new sequence.")
        parser.add_argument("--start", default=None, help="Optional start Stop id.")

    def handle(self, *args, **options):
        result = optimize_route(
            options["route"], persist=options["apply"], start_stop_id=options.get("start")
        )
        if not result.get("ok"):
            raise CommandError(result.get("error", "optimisation failed"))
        self.stdout.write(
            f"route {result['route_id']}: optimised={result['optimised']} "
            f"total_km={result['total_km']} stops={len(result['ordered_stop_ids'])} "
            f"(applied={options['apply']})"
        )
        if result["skipped_no_coords"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(result['skipped_no_coords'])} stop(s) lacked coordinates and kept order."
                )
            )
        self.stdout.write(self.style.SUCCESS("route optimisation OK"))
