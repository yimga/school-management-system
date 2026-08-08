from django.core.management.base import BaseCommand

from apps.schools.models import School
from apps.schools.onboarding_recommendations import ensure_school_recommendations


class Command(BaseCommand):
    help = "Grandfather deterministic local-first recommendation manifests for existing tenants."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Persist changes (default is audit-only).")
        parser.add_argument("--limit", type=int, default=0, help="Optional maximum tenant count.")

    def handle(self, *args, **options):
        queryset = School.objects.order_by("pk")
        if options["limit"] > 0:
            queryset = queryset[: options["limit"]]
        scanned = missing = written = 0
        for school in queryset.iterator(chunk_size=200):
            scanned += 1
            current = (dict(school.settings or {})).get("recommendation_manifest")
            proposed = ensure_school_recommendations(school, save=False)
            if current == proposed:
                continue
            missing += 1
            if options["apply"]:
                ensure_school_recommendations(school, save=True)
            written += int(options["apply"])
        mode = "APPLY" if options["apply"] else "AUDIT"
        self.stdout.write(self.style.SUCCESS(f"{mode}: scanned={scanned} missing={missing} written={written}"))
