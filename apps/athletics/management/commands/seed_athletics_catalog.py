"""
Seed a starter Sport catalog per school so the athletics module is not empty on
first run. Idempotent (get_or_create by (school, code); never overwrites an
existing row). Run:

    python manage.py seed_athletics_catalog                 # all active schools
    python manage.py seed_athletics_catalog --school <id_or_slug>

Mirrors the ``seed_marketplace_apps`` idiom: a module-level catalog of dicts, a
``BaseCommand`` that walks it school-scoped, and a summary written via
``self.stdout.write`` (never ``print()``).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.athletics.constants import DEFAULT_SQUAD_SIZE
from apps.athletics.models import Sport
from apps.athletics.models.catalog import GenderCategory, SportCategory

# Starter sports every school gets seeded with. Squad size is intentionally NOT
# hardcoded here — it flows from apps.athletics.constants.DEFAULT_SQUAD_SIZE so
# operators tune it in one place.
STARTER_SPORTS: list[dict[str, str]] = [
    {
        "name": "Football/Soccer",
        "code": "soccer",
        "category": SportCategory.TEAM,
        "gender_category": GenderCategory.MIXED,
    },
    {
        "name": "Basketball",
        "code": "basketball",
        "category": SportCategory.TEAM,
        "gender_category": GenderCategory.MIXED,
    },
    {
        "name": "Track & Field",
        "code": "track",
        "category": SportCategory.INDIVIDUAL,
        "gender_category": GenderCategory.MIXED,
    },
    {
        "name": "Volleyball",
        "code": "volleyball",
        "category": SportCategory.TEAM,
        "gender_category": GenderCategory.MIXED,
    },
    {
        "name": "Netball",
        "code": "netball",
        "category": SportCategory.TEAM,
        "gender_category": GenderCategory.GIRLS,
    },
    {
        "name": "Cricket",
        "code": "cricket",
        "category": SportCategory.TEAM,
        "gender_category": GenderCategory.MIXED,
    },
    {
        "name": "Rugby",
        "code": "rugby",
        "category": SportCategory.TEAM,
        "gender_category": GenderCategory.BOYS,
    },
    {
        "name": "Swimming",
        "code": "swimming",
        "category": SportCategory.INDIVIDUAL,
        "gender_category": GenderCategory.MIXED,
    },
]


class Command(BaseCommand):
    help = (
        "Seed a starter Sport catalog per school (idempotent). "
        "Seeds all active schools unless --school is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            dest="school",
            default=None,
            help="School id or slug to seed. Omit to seed every active school.",
        )

    def handle(self, *args, **options):
        schools = self._resolve_schools(options.get("school"))
        if not schools:
            self.stdout.write(self.style.WARNING("No matching active schools; nothing to seed."))
            return

        total_created = 0
        total_existing = 0
        for school in schools:
            created, existing = self._seed_school(school)
            total_created += created
            total_existing += existing
            self.stdout.write(
                f"  {school.slug or school.pk}: {created} created, {existing} already present."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Athletics catalog seeded across {len(schools)} school(s): "
                f"{total_created} sport(s) created, {total_existing} already present."
            )
        )

    def _resolve_schools(self, school_arg):
        """Return the list of School rows to seed (single --school, else all active)."""
        from apps.schools.models import School

        if school_arg:
            arg = str(school_arg).strip()
            if arg.isdigit():
                row = School.objects.filter(pk=int(arg)).first()
            else:
                row = School.objects.filter(slug=arg).first()
            if row is None:
                raise CommandError(f"--school {school_arg!r} did not resolve to a School row.")
            return [row]

        return list(School.objects.filter(is_active=True))

    def _seed_school(self, school) -> tuple[int, int]:
        """get_or_create every starter sport for one school. Never overwrites."""
        created = 0
        existing = 0
        for spec in STARTER_SPORTS:
            _, was_created = Sport.objects.get_or_create(
                school=school,
                code=spec["code"],
                defaults={
                    "name": spec["name"],
                    "category": spec["category"],
                    "gender_category": spec["gender_category"],
                    "default_squad_size": DEFAULT_SQUAD_SIZE,
                },
            )
            if was_created:
                created += 1
            else:
                existing += 1
        return created, existing
