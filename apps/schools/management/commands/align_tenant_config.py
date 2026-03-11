"""
Align a tenant to the codebase's configuration direction without
changing name, slug, or subdomain. Ensures:

- default_region is set (canonical source for currency, grading, timezone)
- country_code is set from region (ISO alpha-2 for analytics/onboarding)
- timezone is synced from default_region
- tenant_compiled_config and related keys are persisted (policy/layers)
- School.features is synced from get_tenant_modules (module manifest alignment)

Run after migrations and when adding new tenants. Safe to run repeatedly.
"""
from django.core.management.base import BaseCommand

from apps.schools.models import School


def _get_region_for_school(school, region_code_hint: str | None):
    from apps.global_registries.models import RegionConfig

    if region_code_hint:
        code = (region_code_hint or "").strip().upper()
        if code:
            region = RegionConfig.objects.filter(code=code).first()
            if region:
                return region
    return RegionConfig.get_default()


def _alpha2_for_region(region) -> str:
    if not region or not getattr(region, "code", None):
        return ""
    from apps.siteconfig.global_catalog import GlobalGeoCatalog
    return (GlobalGeoCatalog.alpha2_for_country(region.code) or "").upper()[:2]


class Command(BaseCommand):
    help = (
        "Align tenant configuration to codebase defaults: default_region, country_code, "
        "timezone, compiled config, and features. Defaults to DEFAULT_TENANT_SLUG or the first active tenant. Safe to re-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            type=str,
            default="",
            help="School slug to align (default: DEFAULT_TENANT_SLUG or first active tenant).",
        )
        parser.add_argument(
            "--region",
            type=str,
            default=None,
            help="RegionConfig code to use (e.g. CMR, USA). If omitted, uses RegionConfig.get_default().",
        )
        parser.add_argument(
            "--no-compile",
            action="store_true",
            help="Skip persisting compiled tenant config (tenant_compiled_config, etc.).",
        )
        parser.add_argument(
            "--no-features",
            action="store_true",
            help="Skip syncing School.features from get_tenant_modules.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be changed without saving.",
        )

    def handle(self, *args, **options):
        slug = (options.get("slug") or "").strip()
        if not slug:
            import os

            slug = (os.environ.get("DEFAULT_TENANT_SLUG") or "").strip()
        if not slug:
            slug = (
                School.objects.filter(is_active=True)
                .order_by("name")
                .values_list("slug", flat=True)
                .first()
                or ""
            )
        region_code = (options.get("region") or "").strip() or None
        no_compile = options.get("no_compile", False)
        no_features = options.get("no_features", False)
        dry_run = options.get("dry_run", False)

        if not slug:
            self.stdout.write(self.style.WARNING("No active tenant found to align."))
            return

        school = School.objects.filter(slug=slug, is_active=True).first()
        if not school:
            self.stdout.write(
                self.style.WARNING("School with slug '%s' not found or inactive." % slug)
            )
            return

        changes = []
        region = getattr(school, "default_region", None)
        if region is None:
            region = _get_region_for_school(school, region_code)
            if region:
                changes.append(("default_region", None, region))
                if not dry_run:
                    school.default_region = region
                    school.save(update_fields=["default_region", "updated_at"])

        region = school.default_region if not dry_run else (region or school.default_region)
        if region:
            alpha2 = _alpha2_for_region(region)
            if alpha2 and (not getattr(school, "country_code", None) or not school.country_code.strip()):
                changes.append(("country_code", getattr(school, "country_code", ""), alpha2))
                if not dry_run:
                    school.country_code = alpha2
                    school.save(update_fields=["country_code", "updated_at"])

            tz = getattr(region, "timezone", None) or "UTC"
            current_tz = getattr(school, "timezone", "") or "UTC"
            if tz and current_tz != tz:
                changes.append(("timezone", current_tz, tz))
                if not dry_run:
                    school.timezone = tz
                    school.save(update_fields=["timezone", "updated_at"])

        if dry_run:
            if changes:
                self.stdout.write("Would apply:")
                for key, old_val, new_val in changes:
                    self.stdout.write("  %s: %r -> %r" % (key, old_val, new_val))
            else:
                self.stdout.write("No field changes needed.")
            if not no_compile or not no_features:
                self.stdout.write("Would run compile/features steps (use --no-compile / --no-features to skip).")
            return

        if not no_compile:
            try:
                from apps.siteconfig.tenant_config import persist_compiled_tenant_config
                persist_compiled_tenant_config(school, persist=True)
                changes.append(("tenant_compiled_config", "(persisted)", "ok"))
            except Exception as e:
                self.stdout.write(self.style.WARNING("persist_compiled_tenant_config: %s" % e))

        if not no_features:
            try:
                from apps.siteconfig.tenant_config import sync_tenant_modules_to_school_features
                sync_tenant_modules_to_school_features(school, persist=True)
                changes.append(("features (synced from modules)", "", "ok"))
            except Exception as e:
                self.stdout.write(self.style.WARNING("sync_tenant_modules_to_school_features: %s" % e))

        if changes:
            self.stdout.write(
                self.style.SUCCESS(
                    "Aligned tenant '%s': %s"
                    % (slug, ", ".join("%s set" % c[0] for c in changes))
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Tenant '%s' already aligned; no changes." % slug))
