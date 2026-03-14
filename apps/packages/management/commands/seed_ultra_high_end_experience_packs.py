"""
Seed Ultra High-End Experience Packs so tenants can select a super ultra high-end
theme + experience (luxury palette, statement header, 600ms motion).
Run after seed_admin_dashboard_palettes. Idempotent.
Run: python manage.py seed_ultra_high_end_experience_packs
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.brand_experience.models import ThemePack
from apps.packages.models import ExperiencePack

# Theme pack slugs created by seed_admin_dashboard_palettes (portal Ultra High-End)
ULTRA_PORTAL_SLUGS = (
    ("portal-ultra-gallery", "ultra-high-end-gallery"),
    ("portal-ultra-noir", "ultra-high-end-noir"),
    ("portal-ultra-platinum", "ultra-high-end-platinum"),
)

EXPERIENCE_DEFAULTS = {
    "ultra-high-end-gallery": {
        "name": "Ultra High-End Gallery",
        "description": "Super ultra high-end experience. Gallery White, Rich Black typography, gold accent. Statement header, luxury motion, hairline borders. For portal.",
        "layout_schema": {"style": "luxury", "statement_header": True, "motion_duration_ms": 600},
        "communication_style": {"tone": "premium", "letter_spacing_caps": "0.1em"},
    },
    "ultra-high-end-noir": {
        "name": "Ultra High-End Noir",
        "description": "Super ultra high-end dark experience. Rich Black background, Platinum text, gold accent. Premium portal experience.",
        "layout_schema": {"style": "luxury_dark", "statement_header": True, "motion_duration_ms": 600},
        "communication_style": {"tone": "premium", "letter_spacing_caps": "0.1em"},
    },
    "ultra-high-end-platinum": {
        "name": "Ultra High-End Platinum",
        "description": "Super ultra high-end neutral experience. Platinum surfaces, navy and gold. Magazine-style authority for portal.",
        "layout_schema": {"style": "luxury_neutral", "statement_header": True, "motion_duration_ms": 600},
        "communication_style": {"tone": "premium", "letter_spacing_caps": "0.1em"},
    },
}


class Command(BaseCommand):
    help = "Seed Ultra High-End Experience Packs (theme_pack_id linked to portal-ultra-* ThemePacks). Run after seed_admin_dashboard_palettes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing Ultra High-End experience packs before creating",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get("reset", False)
        codes = [code for _, code in ULTRA_PORTAL_SLUGS]

        if reset:
            deleted, _ = ExperiencePack.objects.filter(code__in=codes).delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing Ultra High-End experience pack(s)."))

        created = 0
        updated = 0
        for theme_slug, exp_code in ULTRA_PORTAL_SLUGS:
            theme_pack = ThemePack.objects.filter(slug=theme_slug, is_active=True).first()
            if not theme_pack:
                self.stdout.write(self.style.WARNING(f"  Skip {exp_code}: ThemePack slug={theme_slug} not found. Run seed_admin_dashboard_palettes first."))
                continue
            defaults = EXPERIENCE_DEFAULTS.get(exp_code, {})
            pack, was_created = ExperiencePack.objects.update_or_create(
                code=exp_code,
                defaults={
                    "name": defaults.get("name", exp_code.replace("-", " ").title()),
                    "description": defaults.get("description", "Ultra high-end experience pack."),
                    "theme_pack_id": theme_pack.pk,
                    "layout_schema": defaults.get("layout_schema", {}),
                    "communication_style": defaults.get("communication_style", {}),
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"  + Created: {pack.name} (code={pack.code}, theme_pack_id={pack.theme_pack_id})"))
            else:
                updated += 1
                self.stdout.write(self.style.WARNING(f"  ~ Updated: {pack.name}"))

        self.stdout.write(self.style.SUCCESS(f"\nUltra High-End experience packs: {created} created, {updated} updated. Tenants can select these in Theme & Experience or experience pack settings."))
