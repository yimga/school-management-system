"""
Phase I Scale: gap analysis for schema-per-tenant (django-tenants) and multi-region.

Checks:
- Duplicate subdomain/slug (none allowed for schema_name uniqueness)
- Schools with missing slug or subdomain (invalid for schema-per-tenant)
- Lists SHARED_APPS vs TENANT_APPS partition (from docs/PHASE_I_SCALE_GAP_ANALYSIS.md)
- FK/uniqueness rules summary

Usage: python manage.py phase_i_gap_analysis
"""

from django.core.management.base import BaseCommand
from django.apps import apps


# Canonical partition for django-tenants (see PHASE_I_SCALE_GAP_ANALYSIS.md)
SHARED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "unfold",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "rest_framework",
    "rest_framework_simplejwt",
    "apps.accounts",
    "apps.schools",
    "apps.siteconfig",
    "apps.compliance",
    "apps.observability",
    "apps.api",
    "apps.apicenter",
    "apps.portal",
    "apps.automation",
    "apps.requests",
    "emis",
    "django_celery_results",
    "django_celery_beat",
]
TENANT_APPS = [
    "apps.academics",
    "apps.people",
    "apps.finance",
    "apps.evals",
    "apps.reports",
    "apps.communication",
    "apps.analytics",
    "apps.payroll",
]


class Command(BaseCommand):
    help = "Phase I: gap analysis for schema-per-tenant and multi-region (subdomains, slugs, app partition)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output machine-readable JSON summary.",
        )

    def handle(self, *args, **options):
        from apps.schools.models import School

        out = []
        errors = []
        warnings = []

        # 1. Duplicate slug / subdomain (DB unique constraints already enforce; report any bad state)
        slugs = list(School.objects.values_list("slug", flat=True))
        subdomains = list(
            School.objects.filter(subdomain__isnull=False)
            .exclude(subdomain="")
            .values_list("subdomain", flat=True)
        )
        duplicate_slugs = [s for s in slugs if slugs.count(s) > 1]
        duplicate_subdomains = [s for s in subdomains if subdomains.count(s) > 1]
        if duplicate_slugs:
            errors.append(f"Duplicate slugs (invalid): {duplicate_slugs}")
        else:
            out.append("Slugs: no duplicates (OK)")
        if duplicate_subdomains:
            errors.append(f"Duplicate subdomains (invalid): {duplicate_subdomains}")
        else:
            out.append("Subdomains: no duplicates (OK)")

        # 2. Schools with empty slug (invalid for schema_name; slug is required and unique)
        empty_slug = list(
            School.objects.filter(slug="").values_list("id", "name", flat=False)
        )
        if empty_slug:
            errors.append(
                f"Schools with empty slug (invalid for schema_name): {empty_slug}"
            )
        else:
            out.append("All schools have non-empty slug (OK)")

        # 3. schema_name sanitization: PostgreSQL schema names (example)
        first = School.objects.only("id", "slug", "subdomain", "name").first()
        if first:
            raw = first.slug or first.subdomain or str(first.id)
            suggested = raw.lower().replace("-", "_")[:63]
            out.append(f"Example schema_name: '{raw}' -> '{suggested}'")

        # 4. SHARED_APPS vs TENANT_APPS (report partition)
        _installed = [
            a
            for a in SHARED_APPS + TENANT_APPS
            if a in [cfg.label for cfg in apps.get_app_configs()]
        ]
        missing_apps = [
            a
            for a in SHARED_APPS + TENANT_APPS
            if a not in [cfg.label for cfg in apps.get_app_configs()]
        ]
        out.append(
            "SHARED_APPS (django-tenants): " + ", ".join(SHARED_APPS[:8]) + ", ..."
        )
        out.append("TENANT_APPS: " + ", ".join(TENANT_APPS))
        if missing_apps:
            warnings.append(f"Apps in partition not installed: {missing_apps}")

        # 5. Summary
        for line in out:
            self.stdout.write(line)
        for w in warnings:
            self.stdout.write(self.style.WARNING(w))
        for e in errors:
            self.stdout.write(self.style.ERROR(e))

        if options.get("json"):
            import json

            self.stdout.write(
                json.dumps(
                    {
                        "errors": errors,
                        "warnings": warnings,
                        "checks": out,
                        "shared_apps": SHARED_APPS,
                        "tenant_apps": TENANT_APPS,
                    },
                    indent=2,
                )
            )

        if errors:
            self.stdout.write(
                self.style.ERROR(
                    "Gap analysis found errors; fix before schema-per-tenant migration."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Gap analysis complete; no blocking issues.")
            )
