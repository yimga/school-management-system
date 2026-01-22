from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academics.models import AcademicYear, Term


class Command(BaseCommand):
    help = "Backfill or fix Term.position values per academic year (1–4) based on start_date order, avoiding conflicts."

    def add_arguments(self, parser):n        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write changes; just report planned updates.",
        )
        parser.add_argument(
            "--year",
            type=str,
            help="Limit to a specific academic year name (exact match).",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        year_name = options.get("year")

        years = AcademicYear.objects.all()
        if year_name:
            years = years.filter(name=year_name)
        if not years.exists():
            self.stdout.write(self.style.WARNING("No academic years matched."))
            return

        total_updates = 0
        for year in years.order_by("-start_date"):
            self.stdout.write(f"Processing {year.name}...")
            qs = Term.objects.filter(academic_year=year).order_by("start_date", "id")

            used_positions = set(
                qs.exclude(position__isnull=True).values_list("position", flat=True)
            )

            next_pos = 1
            updates = []
            for term in qs:
                if term.position:
                    continue
                while next_pos in used_positions and next_pos <= 4:
                    next_pos += 1
                if next_pos > 4:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Skipping {term} — no free positions 1..4 available; set manually."
                        )
                    )
                    continue
                updates.append((term.id, next_pos))
                used_positions.add(next_pos)
                next_pos += 1

            if not updates:
                self.stdout.write("  No changes needed.")
                continue

            self.stdout.write("  Planned updates:")
            for term_id, pos in updates:
                t = next(t for t in qs if t.id == term_id)
                self.stdout.write(f"    {t.name or t.custom_label} -> position {pos}")

            if dry_run:
                continue

            with transaction.atomic():
                for term_id, pos in updates:
                    Term.objects.filter(id=term_id).update(position=pos)
                total_updates += len(updates)
                self.stdout.write(self.style.SUCCESS(f"  Applied {len(updates)} updates."))

        self.stdout.write(self.style.SUCCESS(f"Done. Total updates: {total_updates}"))
