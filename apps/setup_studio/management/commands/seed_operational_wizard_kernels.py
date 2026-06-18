"""Seed operational wizard kernels — EAV, grading presets, wizard cockpit defaults.

  python manage.py seed_operational_wizard_kernels
  python manage.py seed_operational_wizard_kernels --school demo-school
  python manage.py seed_operational_wizard_kernels --all-active-schools
  python manage.py seed_operational_wizard_kernels --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.evals.grading_formula_engine import PRESET_GRADING_FORMULAS
from apps.metadata.country_eav_catalog import seed_country_eav_definitions, seed_platform_eav_baseline
from apps.setup_studio import wizard_engine
from apps.setup_studio.sovereignty_kernel import ensure_sovereignty_kernel_for_tenant


class Command(BaseCommand):
    help = "Seed EAV catalogs, grading formula presets, and wizard kernel defaults per tenant."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument("--school", help="School slug to seed.")
        scope.add_argument(
            "--all-active-schools",
            action="store_true",
            help="Seed every active school.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        schools = self._resolve_schools(options)
        platform_stats = seed_platform_eav_baseline(dry_run=dry_run)
        self.stdout.write(f"Platform EAV baseline: {platform_stats}")

        wizard_keys = [
            w.wizard_key for w in wizard_engine.list_wizards_for_audience("tenant_admin")
        ]
        for school in schools:
            with transaction.atomic():
                eav_stats = seed_country_eav_definitions(
                    school=school,
                    country_code=getattr(school, "country_code", None),
                    dry_run=dry_run,
                )
                kernel_patch = self._build_kernel_patch(school, wizard_keys, dry_run=dry_run)
                sovereignty = ensure_sovereignty_kernel_for_tenant(school=school, dry_run=dry_run)
                self.stdout.write(
                    f"{school.slug}: EAV {eav_stats} kernels={kernel_patch['wizard_keys_seeded']} "
                    f"sovereignty={sovereignty.get('country_code')}"
                )
        self.stdout.write(self.style.SUCCESS("Operational wizard kernel seed complete."))

    def _resolve_schools(self, options):
        from apps.schools.models import School

        if options.get("all_active_schools"):
            return list(School.objects.filter(is_active=True).order_by("slug"))
        slug = options.get("school")
        if not slug:
            raise CommandError("Pass --school <slug> or --all-active-schools")
        try:
            return [School.objects.get(slug=slug, is_active=True)]
        except School.DoesNotExist as exc:
            raise CommandError(f"School not found: {slug}") from exc

    def _build_kernel_patch(self, school, wizard_keys, *, dry_run: bool) -> dict:
        settings = dict(school.settings or {})
        wizards = dict(settings.get("wizards") or {})
        seeded = 0
        for key in wizard_keys:
            if key not in wizards:
                wizards[key] = {"kernel_seeded_at": "pending"}
                seeded += 1
        grading = dict(settings.get("grading_formulas") or {})
        grading.update(PRESET_GRADING_FORMULAS)
        settings["wizards"] = wizards
        settings["grading_formulas"] = grading
        settings["operational_kernel_version"] = "v1"
        if not dry_run:
            school.settings = settings
            school.save(update_fields=["settings"])
        return {"wizard_keys_seeded": seeded, "grading_presets": len(PRESET_GRADING_FORMULAS)}
